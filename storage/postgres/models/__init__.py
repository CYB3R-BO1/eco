"""ORM model registry.

Importing every model here ensures ``Base.metadata`` is fully populated when
Alembic's ``env.py`` does ``from storage.postgres.models import *``, which is
how autogenerate sees new tables.
"""
from storage.postgres.models.entity_alias import EntityAlias
from storage.postgres.models.enrichment_result import EnrichmentResultRow
from storage.postgres.models.evidence import EvidenceRow
from storage.postgres.models.firewall_event import FirewallEvent
from storage.postgres.models.graph_rejection import GraphRejection
from storage.postgres.models.idempotency_key import IdempotencyKeyRow
from storage.postgres.models.investigation import Investigation
from storage.postgres.models.investigation_event import InvestigationEvent

__all__ = [
    "EntityAlias",
    "EnrichmentResultRow",
    "EvidenceRow",
    "FirewallEvent",
    "GraphRejection",
    "IdempotencyKeyRow",
    "Investigation",
    "InvestigationEvent",
]
