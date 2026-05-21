"""ORM model registry.

Importing every model here ensures ``Base.metadata`` is fully populated when
Alembic's ``env.py`` does ``from storage.postgres.models import *``, which is
how autogenerate sees new tables.
"""
from storage.postgres.models.agent_run import AgentRunRow
from storage.postgres.models.dead_letter_entry import DeadLetterEntry, DLQQueue
from storage.postgres.models.entity_alias import EntityAlias
from storage.postgres.models.enrichment_result import EnrichmentResultRow
from storage.postgres.models.evidence import EvidenceRow
from storage.postgres.models.firewall_event import FirewallEvent
from storage.postgres.models.graph_rejection import GraphRejection
from storage.postgres.models.idempotency_key import IdempotencyKeyRow
from storage.postgres.models.investigation import Investigation
from storage.postgres.models.investigation_event import InvestigationEvent
from storage.postgres.models.memory_audit import MemoryAuditRow
from storage.postgres.models.workflow_run import WorkflowRunRow

__all__ = [
    "AgentRunRow",
    "DLQQueue",
    "DeadLetterEntry",
    "EntityAlias",
    "EnrichmentResultRow",
    "EvidenceRow",
    "FirewallEvent",
    "GraphRejection",
    "IdempotencyKeyRow",
    "Investigation",
    "InvestigationEvent",
    "MemoryAuditRow",
    "WorkflowRunRow",
]
