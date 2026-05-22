"""Phase 6 WP10 — slow-query logger fingerprints params, never values."""
from __future__ import annotations

from core.database.slow_query_log import _normalize_statement, _params_fingerprint


def test_params_fingerprint_is_stable_and_hex() -> None:
    a = _params_fingerprint({"x": 1, "y": "secret-value"})
    b = _params_fingerprint({"x": 1, "y": "secret-value"})
    assert a == b
    assert len(a) == 64
    assert all(c in "0123456789abcdef" for c in a)


def test_params_fingerprint_does_not_contain_value() -> None:
    secret = "TOP-SECRET-PROMPT-XYZ"
    fp = _params_fingerprint({"prompt": secret})
    assert secret not in fp


def test_empty_params_yields_empty_fingerprint() -> None:
    assert _params_fingerprint(None) == ""
    assert _params_fingerprint([]) == ""


def test_normalize_statement_collapses_whitespace() -> None:
    raw = "SELECT  *\n  FROM users\n  WHERE id = :id"
    assert _normalize_statement(raw) == "SELECT * FROM users WHERE id = :id"
