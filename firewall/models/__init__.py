"""Domain dataclasses shared by every firewall layer.

Kept separate from :mod:`schemas.api.firewall` so that internal layers
don't import pydantic — the analysis pipeline runs in hot paths and
benefits from frozen ``@dataclass`` over pydantic's per-field validation.
The boundary between these dataclasses and the API DTOs lives in
:mod:`schemas.api.firewall`.
"""
