"""Domain normalization.

`google.com`, `Google.com`, `HTTPS://Google.com/`, `https://google.com/` and
`https://google.com/login` all map to the canonical domain `google.com`.
URL forms with paths additionally yield a child_url variant so the parent
domain can be queried independently.
"""
from __future__ import annotations

import re

_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(\.([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))+$"
)


def normalize_domain(raw: str) -> str:
    """Return canonical form. Raises ValueError if not a valid domain."""
    if not isinstance(raw, str) or not raw:
        raise ValueError("domain must be a non-empty string")

    value = raw.strip().lower()

    for scheme in ("https://", "http://", "ftp://"):
        if value.startswith(scheme):
            value = value[len(scheme) :]
            break

    # Strip path / port / userinfo if any leaked through.
    for sep in ("/", "?", "#", ":"):
        idx = value.find(sep)
        if idx >= 0:
            value = value[:idx]

    if "@" in value:
        value = value.split("@", 1)[1]

    if value.endswith("."):
        value = value[:-1]

    try:
        value = value.encode("idna").decode("ascii")
    except UnicodeError as e:
        raise ValueError(f"invalid IDN domain: {raw!r}") from e

    if not _DOMAIN_RE.match(value):
        raise ValueError(f"invalid domain: {raw!r}")

    return value
