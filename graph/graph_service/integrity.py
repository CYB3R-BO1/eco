"""Graph integrity verification.

Five checks, each backed by a single Cypher query in
:mod:`graph.queries.integrity`. The checker assembles them into an
:class:`IntegrityReport`. A non-empty report is the signal the
:class:`graph.correlation.GraphCorrelator` uses to route an investigation
to REVIEW_REQUIRED.

Stale-enrichment retention thresholds come from CLAUDE.md invariant #12
(privacy / retention). They are encoded here rather than in config because
changing them shifts what counts as a violation — that should be a code
review, not a config flip.
"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog

from evidence.provenance import ProvenanceLevel
from graph.governance.cardinality import QUERY_TIMEOUT_SECONDS
from graph.neo4j.driver import Neo4jClient
from graph.queries.integrity import (
    CONFIDENCE_ANOMALY_EDGES,
    CONFIDENCE_OUT_OF_RANGE_NODES,
    CYCLES_IN_INVESTIGATION,
    ORPHANS_IN_INVESTIGATION,
    PROVENANCE_GAPS,
    STALE_ENRICHMENTS,
)

log = structlog.get_logger(__name__)


# Retention thresholds — days — per provenance level. Values are
# intentionally generous; tightening here triggers stale flags everywhere.
RETENTION_DAYS: dict[ProvenanceLevel, int] = {
    ProvenanceLevel.PRIMARY_SOURCE: 180,
    ProvenanceLevel.DERIVED_SOURCE: 90,
    ProvenanceLevel.AI_GENERATED: 30,
    ProvenanceLevel.THIRD_PARTY: 60,
    ProvenanceLevel.USER_SUPPLIED: 365,
}


@dataclass(frozen=True)
class IntegrityReport:
    investigation_id: uuid.UUID
    orphans: list[dict[str, Any]] = field(default_factory=list)
    cycles: list[dict[str, Any]] = field(default_factory=list)
    confidence_anomalies: list[dict[str, Any]] = field(default_factory=list)
    provenance_gaps: list[dict[str, Any]] = field(default_factory=list)
    stale_enrichments: list[dict[str, Any]] = field(default_factory=list)

    @property
    def has_violations(self) -> bool:
        return bool(
            self.orphans
            or self.cycles
            or self.confidence_anomalies
            or self.provenance_gaps
            or self.stale_enrichments
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "investigation_id": str(self.investigation_id),
            "orphans": self.orphans,
            "cycles": self.cycles,
            "confidence_anomalies": self.confidence_anomalies,
            "provenance_gaps": self.provenance_gaps,
            "stale_enrichments": self.stale_enrichments,
            "has_violations": self.has_violations,
        }


class IntegrityChecker:
    def __init__(self, client: Neo4jClient) -> None:
        self._client = client

    async def check(self, investigation_id: uuid.UUID) -> IntegrityReport:
        """Run all five checks against an investigation subgraph.

        Each check is its own Cypher call so a slow check doesn't block the
        others. Tasks run concurrently against the same driver.
        """
        orphans_task = asyncio.create_task(self._run(ORPHANS_IN_INVESTIGATION, investigation_id))
        cycles_task = asyncio.create_task(self._run(CYCLES_IN_INVESTIGATION, investigation_id))
        conf_nodes_task = asyncio.create_task(
            self._run(CONFIDENCE_OUT_OF_RANGE_NODES, investigation_id)
        )
        conf_edges_task = asyncio.create_task(
            self._run(CONFIDENCE_ANOMALY_EDGES, investigation_id)
        )
        provenance_task = asyncio.create_task(self._run(PROVENANCE_GAPS, investigation_id))
        stale_task = asyncio.create_task(self._stale_enrichments(investigation_id))

        orphans = await orphans_task
        cycles = await cycles_task
        confidence_anomalies = (await conf_nodes_task) + (await conf_edges_task)
        provenance_gaps = await provenance_task
        stale = await stale_task

        report = IntegrityReport(
            investigation_id=investigation_id,
            orphans=orphans,
            cycles=cycles,
            confidence_anomalies=confidence_anomalies,
            provenance_gaps=provenance_gaps,
            stale_enrichments=stale,
        )
        log.info(
            "graph.integrity.checked",
            investigation_id=str(investigation_id),
            has_violations=report.has_violations,
            counts={
                "orphans": len(orphans),
                "cycles": len(cycles),
                "confidence_anomalies": len(confidence_anomalies),
                "provenance_gaps": len(provenance_gaps),
                "stale_enrichments": len(stale),
            },
        )
        return report

    async def _run(
        self, cypher: str, investigation_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        async with self._client.driver.session(database=self._client.database) as session:
            result = await asyncio.wait_for(
                session.run(cypher, investigation_id=str(investigation_id)),
                timeout=QUERY_TIMEOUT_SECONDS,
            )
            return [record.data() async for record in result]

    async def _stale_enrichments(
        self, investigation_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        """One query per provenance level (the cutoff differs per level)."""
        now = datetime.now(timezone.utc)
        results: list[dict[str, Any]] = []
        for level, days in RETENTION_DAYS.items():
            cutoff = (now - timedelta(days=days)).isoformat()
            async with self._client.driver.session(database=self._client.database) as session:
                cursor = await asyncio.wait_for(
                    session.run(
                        STALE_ENRICHMENTS,
                        investigation_id=str(investigation_id),
                        cutoff=cutoff,
                        level=level.value,
                    ),
                    timeout=QUERY_TIMEOUT_SECONDS,
                )
                rows = [record.data() async for record in cursor]
            for r in rows:
                r["threshold_days"] = days
            results.extend(rows)
        return results
