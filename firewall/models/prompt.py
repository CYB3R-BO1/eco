"""Inputs to the firewall — the prompt itself plus its delivery context.

Kept deliberately small. ``WorkflowContext`` is optional — most callers
won't supply one in Phase 4. If they do, we materialize a ``Workflow``
node in the graph and a ``TRIGGERED`` edge from the prompt.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelTarget:
    provider: str
    model: str

    def identifier(self) -> str:
        """Stable string id used as the graph Agent node's ``id`` derivation."""
        return f"{self.provider.lower()}:{self.model.lower()}"


@dataclass(frozen=True)
class WorkflowContext:
    workflow_id: uuid.UUID
    route: str | None = None


@dataclass(frozen=True)
class PromptInput:
    prompt: str
    target_model: ModelTarget
    workflow_context: WorkflowContext | None = None
