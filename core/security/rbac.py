"""Role-based access control (Phase 6 WP4).

The role/permission matrix is the load-bearing implementation of CLAUDE.md
invariant #11: deny by default, every (role, resource, action) checked,
denials audit-logged. The matrix is a literal table — no dynamic loading
from a database, no runtime mutation — because invariant #11 needs to be
auditable by reading one file. Adding a permission for a role is a code
change reviewable in a diff.

Roles come from CLAUDE.md / PLAN §11.7:

- ``admin``           — full surface, including token issuance + rotation.
- ``analyst``         — day-to-day investigator: ingest, read, run agents.
- ``readonly``        — view-only across investigations, evidence, graph.
- ``external_user``   — limited ingest + read of own investigations only
                        (ownership check is route-side, see WP4 plan note
                        about ``resource_owner`` in ``require``).
- ``ai_agent``        — server-side automation: execute agents, read.
- ``service_account`` — non-human integration: ingest + read.

Why a literal ``frozenset`` per role: hash-based membership check stays
O(1), the object is immutable so a route handler cannot promote itself
mid-request, and a test can diff the matrix against this docstring.
"""
from __future__ import annotations

import enum
from collections.abc import Iterable
from dataclasses import dataclass


class Role(str, enum.Enum):
    ADMIN = "admin"
    ANALYST = "analyst"
    READONLY = "readonly"
    EXTERNAL_USER = "external_user"
    AI_AGENT = "ai_agent"
    SERVICE_ACCOUNT = "service_account"


class Permission(str, enum.Enum):
    """Closed set of (resource, action) tuples used at every authz check.

    Names follow ``RESOURCE_ACTION`` so the metric label
    ``permission_denials_total{permission=...}`` stays self-describing.
    """

    INVESTIGATION_READ = "investigation:read"
    INVESTIGATION_WRITE = "investigation:write"
    IOC_INGEST = "ioc:ingest"
    IOC_EXTRACT = "ioc:extract"
    EVIDENCE_READ = "evidence:read"
    GRAPH_READ = "graph:read"
    FIREWALL_USE = "firewall:use"
    AGENT_EXECUTE = "agent:execute"
    WORKFLOW_READ = "workflow:read"
    WORKFLOW_WRITE = "workflow:write"


# The matrix. Every entry is reviewed in CLAUDE.md §11.7 — add a permission
# by name, never use ``set | {extra}`` tricks that hide additions in a diff.
ROLE_MATRIX: dict[Role, frozenset[Permission]] = {
    Role.ADMIN: frozenset(Permission),
    Role.ANALYST: frozenset(
        {
            Permission.INVESTIGATION_READ,
            Permission.INVESTIGATION_WRITE,
            Permission.IOC_INGEST,
            Permission.IOC_EXTRACT,
            Permission.EVIDENCE_READ,
            Permission.GRAPH_READ,
            Permission.FIREWALL_USE,
            Permission.AGENT_EXECUTE,
            Permission.WORKFLOW_READ,
            Permission.WORKFLOW_WRITE,
        }
    ),
    Role.READONLY: frozenset(
        {
            Permission.INVESTIGATION_READ,
            Permission.EVIDENCE_READ,
            Permission.GRAPH_READ,
            Permission.WORKFLOW_READ,
        }
    ),
    Role.EXTERNAL_USER: frozenset(
        {
            Permission.INVESTIGATION_READ,
            Permission.IOC_EXTRACT,
            Permission.IOC_INGEST,
            Permission.FIREWALL_USE,
        }
    ),
    Role.AI_AGENT: frozenset(
        {
            Permission.INVESTIGATION_READ,
            Permission.EVIDENCE_READ,
            Permission.GRAPH_READ,
            Permission.AGENT_EXECUTE,
            Permission.FIREWALL_USE,
        }
    ),
    Role.SERVICE_ACCOUNT: frozenset(
        {
            Permission.IOC_INGEST,
            Permission.IOC_EXTRACT,
            Permission.INVESTIGATION_READ,
            Permission.EVIDENCE_READ,
        }
    ),
}


class PermissionDeniedError(Exception):
    """Raised by :func:`require` when the principal lacks ``permission``.

    Mapped to HTTP 403 by the registered exception handler, which also
    emits the ``AUTH_PERMISSION_DENIED`` audit event and increments
    ``permission_denials_total``.
    """

    def __init__(self, *, role: str, permission: Permission, subject: str) -> None:
        super().__init__(f"{role!r} cannot perform {permission.value!r}")
        self.role = role
        self.permission = permission
        self.subject = subject


@dataclass(frozen=True)
class _PrincipalProtocol:
    """Minimal duck-type used by ``require`` so this module stays free of
    a hard dependency on :class:`apps.api.auth.Principal`."""

    subject: str
    role: str


def _resolve_role(role_name: str) -> Role | None:
    try:
        return Role(role_name)
    except ValueError:
        return None


def has_permission(role: str, permission: Permission) -> bool:
    resolved = _resolve_role(role)
    if resolved is None:
        return False
    return permission in ROLE_MATRIX[resolved]


def require(
    principal: _PrincipalProtocol | object,
    permission: Permission,
) -> None:
    """Raise :class:`PermissionDeniedError` when the role lacks ``permission``.

    Accepts any object with ``role`` and ``subject`` attributes — typically
    an :class:`apps.api.auth.Principal`, but the duck-type lets RBAC
    decisions be tested without constructing the FastAPI dependency.
    """
    role = getattr(principal, "role", "")
    subject = getattr(principal, "subject", "")
    if not has_permission(role, permission):
        raise PermissionDeniedError(role=role, permission=permission, subject=subject)


def known_role_names() -> Iterable[str]:
    """Closed set of role label values — used to bound the
    ``permission_denials_total{role=...}`` cardinality."""
    return tuple(r.value for r in Role)
