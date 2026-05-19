"""FastAPI lifespan — connect the data tier on startup, disconnect on shutdown.

Connection order is fastest-to-slowest (Postgres → Redis → Neo4j); shutdown is
the reverse. Failures during ``connect()`` propagate and prevent the app from
accepting traffic — that's deliberate: a half-up service that 500s every
request is worse than one that fails to start.

Phase 2 also constructs the IOC-pipeline services (EventEmitter,
EvidenceStore, EntityResolutionService, EnrichmentExecutor, LifecycleManager,
BackgroundTaskRunner, IngestionPipeline) and parks them on ``app.state`` so
the FastAPI ``Depends`` providers in ``apps/api/dependencies.py`` can resolve
them without reaching for module-level globals.

Phase 3 adds: SchemaValidator + RejectionStore + GraphCorrelator. The
rewritten GraphService composes Validator + RejectionStore + EventEmitter
+ Neo4jClient. The IngestionPipeline receives the GraphCorrelator so it
can run the CORRELATING phase between ENRICHING and COMPLETED.

Phase 4 adds: FirewallPolicy + PromptAnalysisPipeline + PolicyEngine +
OutputValidator + FirewallAuditStore + FirewallGraphCorrelator composed
into a single FirewallService. The service owns its own investigation
lifecycle (one investigation per /firewall/decision) and shares the
EventEmitter, EvidenceStore, LifecycleManager, and GraphService with the
Phase 1–3 plumbing.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from core.cache.redis import RedisClient
from core.config.settings import Settings, get_settings
from core.database.postgres import Database
from core.events.emitter import EventEmitter
from evidence.store import EvidenceStore
from firewall.analysis.llm_classifier import NullClassifier
from firewall.audit.store import FirewallAuditStore
from firewall.correlation.correlator import FirewallGraphCorrelator
from firewall.output_validation.validator import OutputValidator
from firewall.pipeline import PromptAnalysisPipeline
from firewall.policy.engine import PolicyEngine
from firewall.policy.policy import FirewallPolicy
from firewall.rules.engine import RulesEngine
from firewall.service import FirewallService
from graph.correlation.correlator import GraphCorrelator
from graph.governance.rejection_store import RejectionStore
from graph.governance.validator import SchemaValidator
from graph.graph_service.service import GraphService
from graph.neo4j.driver import Neo4jClient
from investigation.background import BackgroundTaskRunner
from investigation.enrichment.executor import EnrichmentExecutor
from investigation.enrichment.providers import default_providers
from investigation.enrichment.registry import ProviderRegistry
from investigation.ingestion.pipeline import IngestionPipeline
from investigation.lifecycle.manager import LifecycleManager
from resolution.service import EntityResolutionService

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = getattr(app.state, "settings", None) or get_settings()

    db = Database(settings.postgres)
    redis_client = RedisClient(settings.redis)
    neo4j_client = Neo4jClient(settings.neo4j)

    log.info("lifespan.startup.begin", environment=settings.environment)

    await db.connect()
    await redis_client.connect()
    await neo4j_client.connect()

    # Phase 2 services
    event_emitter = EventEmitter()
    evidence_store = EvidenceStore()
    resolver = EntityResolutionService()
    registry = ProviderRegistry(default_providers())
    enrichment_executor = EnrichmentExecutor(
        registry=registry,
        database=db,
        redis=redis_client,
        evidence_store=evidence_store,
        event_emitter=event_emitter,
    )
    lifecycle_manager = LifecycleManager(event_emitter)
    background_runner = BackgroundTaskRunner(max_concurrent=10)

    # Phase 3 services — schema governance + graph gateway + correlator.
    schema_validator = SchemaValidator()
    rejection_store = RejectionStore(event_emitter)
    graph_service = GraphService(
        client=neo4j_client,
        validator=schema_validator,
        rejection_store=rejection_store,
        event_emitter=event_emitter,
    )
    graph_correlator = GraphCorrelator(
        database=db,
        graph_service=graph_service,
        event_emitter=event_emitter,
    )

    ingestion_pipeline = IngestionPipeline(
        database=db,
        evidence_store=evidence_store,
        event_emitter=event_emitter,
        resolver=resolver,
        enrichment_executor=enrichment_executor,
        lifecycle_manager=lifecycle_manager,
        background_runner=background_runner,
        graph_correlator=graph_correlator,
        graph_service=graph_service,
    )

    # Phase 4 services — AI firewall middleware.
    firewall_policy = FirewallPolicy(
        block_threshold=settings.firewall.block_threshold,
        sanitize_threshold=settings.firewall.sanitize_threshold,
        review_threshold=settings.firewall.review_threshold,
        finding_weight_floor=settings.firewall.finding_weight_floor,
        pii_masking_enabled=settings.firewall.pii_masking_enabled,
    )
    firewall_audit_store = FirewallAuditStore()
    firewall_pipeline = PromptAnalysisPipeline(
        policy=firewall_policy,
        rules_engine=RulesEngine(),
        llm_classifier=NullClassifier(),
        detection_timeout_ms=settings.firewall.detection_timeout_ms,
    )
    firewall_policy_engine = PolicyEngine(firewall_policy)
    firewall_output_validator = OutputValidator(firewall_policy)
    firewall_graph_correlator = FirewallGraphCorrelator(
        graph_service=graph_service,
        event_emitter=event_emitter,
        policy=firewall_policy,
    )
    firewall_service = FirewallService(
        settings=settings.firewall,
        database=db,
        evidence_store=evidence_store,
        event_emitter=event_emitter,
        lifecycle_manager=lifecycle_manager,
        audit_store=firewall_audit_store,
        graph_service=graph_service,
        graph_correlator=firewall_graph_correlator,
        pipeline=firewall_pipeline,
        policy_engine=firewall_policy_engine,
        output_validator=firewall_output_validator,
    )

    app.state.db = db
    app.state.redis = redis_client
    app.state.neo4j = neo4j_client
    app.state.graph_service = graph_service
    app.state.schema_validator = schema_validator
    app.state.rejection_store = rejection_store
    app.state.graph_correlator = graph_correlator
    app.state.event_emitter = event_emitter
    app.state.evidence_store = evidence_store
    app.state.resolver = resolver
    app.state.enrichment_executor = enrichment_executor
    app.state.lifecycle_manager = lifecycle_manager
    app.state.background_runner = background_runner
    app.state.ingestion_pipeline = ingestion_pipeline
    app.state.firewall_service = firewall_service
    app.state.firewall_policy = firewall_policy
    app.state.firewall_audit_store = firewall_audit_store

    log.info("lifespan.startup.complete")

    try:
        yield
    finally:
        log.info("lifespan.shutdown.begin")
        await background_runner.drain(timeout=30.0)
        await neo4j_client.disconnect()
        await redis_client.disconnect()
        await db.disconnect()
        log.info("lifespan.shutdown.complete")
