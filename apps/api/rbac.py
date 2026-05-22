"""Per-route RBAC dependency factory (Phase 6 WP4).

``requires(Permission.X)`` returns a FastAPI dependency that resolves the
current principal, calls :func:`core.security.rbac.require`, and raises
:class:`PermissionDeniedError` on failure. The registered exception
handler turns that into a 403, increments
``permission_denials_total{role,permission}``, and emits an
``AUTH_PERMISSION_DENIED`` audit event (fingerprint-only, per
CLAUDE.md invariant #14).

The factory closes over ``permission`` so each call produces a tiny
dependency tied to that permission — useful for OpenAPI naming and
clearer stack traces on 403.
"""
from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Depends

from apps.api.auth import get_current_principal
from core.security.principal import Principal
from core.security.rbac import Permission, require


def requires(
    permission: Permission,
) -> Callable[..., Coroutine[Any, Any, Principal]]:
    async def _dependency(
        principal: Principal = Depends(get_current_principal),
    ) -> Principal:
        require(principal, permission)
        return principal

    _dependency.__name__ = f"requires_{permission.name.lower()}"
    return _dependency
