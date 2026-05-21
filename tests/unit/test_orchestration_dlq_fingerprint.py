"""DLQ payload-fingerprinting helper."""
from __future__ import annotations

from orchestration.dlq.store import fingerprint_payload


def test_fingerprint_is_64_char_hex() -> None:
    fp = fingerprint_payload("hello world")
    assert len(fp) == 64
    int(fp, 16)


def test_fingerprint_is_deterministic() -> None:
    assert fingerprint_payload("same") == fingerprint_payload("same")


def test_fingerprint_accepts_bytes_and_str() -> None:
    assert fingerprint_payload("abc") == fingerprint_payload(b"abc")


def test_fingerprint_changes_with_payload() -> None:
    assert fingerprint_payload("a") != fingerprint_payload("b")
