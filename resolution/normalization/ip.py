"""IP normalization.

stdlib ``ipaddress`` handles all the edge cases that catch hand-rolled regex:
v6 compression, leading-zero v4, dotted-decimal canonicalisation, etc.
"""
from __future__ import annotations

import ipaddress


def normalize_ip(raw: str) -> str:
    if not isinstance(raw, str) or not raw:
        raise ValueError("ip must be a non-empty string")
    try:
        return str(ipaddress.ip_address(raw.strip()))
    except ValueError as e:
        raise ValueError(f"invalid ip: {raw!r}") from e
