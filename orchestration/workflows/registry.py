"""Workflow registry — maps workflow name → LangGraph graph factory.

Two workflows are registered in Phase 5:

- ``investigation`` — IngestionPipeline → enrichment → correlation →
  reasoning → finalize.
- ``firewall`` — FirewallService.decide → (optional reasoning) → finalize.

The registry is consulted by :class:`orchestration.service.OrchestrationService.run_workflow`
to look up the graph for a given workflow name.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Callable


class WorkflowName(str, enum.Enum):
    INVESTIGATION = "investigation"
    FIREWALL = "firewall"


@dataclass(frozen=True)
class WorkflowSpec:
    name: WorkflowName
    description: str
    build_graph: Callable[..., "object"]  # returns a CompiledStateGraph
