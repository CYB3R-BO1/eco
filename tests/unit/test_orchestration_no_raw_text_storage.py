"""Static enforcement of CLAUDE.md invariant #12 for Phase 5 tables.

None of ``workflow_runs``, ``agent_runs``, ``dead_letter_entries``, or
``memory_audits`` may store raw prompt/completion/memory text — only
fingerprints. This test inspects the SQLAlchemy column metadata so it
fails immediately on PR review if a future change adds a forbidden
column, without needing a live database.
"""
from __future__ import annotations

import pytest

from storage.postgres.models.agent_run import AgentRunRow
from storage.postgres.models.dead_letter_entry import DeadLetterEntry
from storage.postgres.models.memory_audit import MemoryAuditRow
from storage.postgres.models.workflow_run import WorkflowRunRow

_FORBIDDEN_SUBSTRINGS = (
    "prompt_text",
    "response_text",
    "raw_prompt",
    "raw_response",
    "completion_text",
    "memory_content",
    "plaintext",
)

_TABLES = [WorkflowRunRow, AgentRunRow, DeadLetterEntry, MemoryAuditRow]


@pytest.mark.parametrize("model", _TABLES, ids=lambda m: m.__tablename__)
def test_table_has_no_raw_text_columns(model) -> None:
    bad = [
        c.name
        for c in model.__table__.columns
        if any(s in c.name.lower() for s in _FORBIDDEN_SUBSTRINGS)
    ]
    assert not bad, f"{model.__tablename__} has forbidden columns: {bad}"


def test_memory_audits_only_holds_fingerprint() -> None:
    cols = {c.name for c in MemoryAuditRow.__table__.columns}
    assert "content_fingerprint" in cols
    # No "summary", "text", "content" columns.
    forbidden = {"summary", "text", "content", "raw"}
    leaked = cols & forbidden
    assert not leaked, f"memory_audits leaks raw text columns: {leaked}"


def test_dlq_only_holds_fingerprint() -> None:
    cols = {c.name for c in DeadLetterEntry.__table__.columns}
    assert "payload_fingerprint" in cols
    assert "payload" not in cols  # raw payload would be a violation


def test_workflow_runs_only_holds_fingerprint() -> None:
    cols = {c.name for c in WorkflowRunRow.__table__.columns}
    assert "inputs_fingerprint" in cols
    # No "inputs" / "request_body" raw column.
    assert "inputs" not in cols
    assert "request_body" not in cols
