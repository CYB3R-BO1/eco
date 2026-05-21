"""BaseAgent idempotency-key determinism."""
from __future__ import annotations

import uuid

from agents.base import compute_idempotency_key, inputs_fingerprint


def test_idempotency_key_is_deterministic() -> None:
    workflow_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    inputs = {"a": 1, "b": "two", "c": None}
    k1 = compute_idempotency_key(
        agent_name="reasoning",
        workflow_run_id=workflow_id,
        node_name="reasoning",
        inputs=inputs,
    )
    k2 = compute_idempotency_key(
        agent_name="reasoning",
        workflow_run_id=workflow_id,
        node_name="reasoning",
        inputs=inputs,
    )
    assert k1 == k2


def test_idempotency_key_invariant_under_dict_order() -> None:
    workflow_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    k1 = compute_idempotency_key(
        agent_name="x", workflow_run_id=workflow_id, node_name="n", inputs={"a": 1, "b": 2}
    )
    k2 = compute_idempotency_key(
        agent_name="x", workflow_run_id=workflow_id, node_name="n", inputs={"b": 2, "a": 1}
    )
    assert k1 == k2


def test_idempotency_key_changes_with_inputs() -> None:
    workflow_id = uuid.uuid4()
    k1 = compute_idempotency_key(
        agent_name="x", workflow_run_id=workflow_id, node_name="n", inputs={"a": 1}
    )
    k2 = compute_idempotency_key(
        agent_name="x", workflow_run_id=workflow_id, node_name="n", inputs={"a": 2}
    )
    assert k1 != k2


def test_idempotency_key_changes_with_node() -> None:
    workflow_id = uuid.uuid4()
    inputs = {"a": 1}
    k1 = compute_idempotency_key(
        agent_name="x", workflow_run_id=workflow_id, node_name="alpha", inputs=inputs
    )
    k2 = compute_idempotency_key(
        agent_name="x", workflow_run_id=workflow_id, node_name="beta", inputs=inputs
    )
    assert k1 != k2


def test_inputs_fingerprint_is_sha256_hex() -> None:
    fp = inputs_fingerprint({"x": "y"})
    assert len(fp) == 64
    int(fp, 16)  # raises if not hex
