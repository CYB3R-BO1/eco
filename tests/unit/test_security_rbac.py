"""Phase 6 WP4 — role/permission matrix contract.

The matrix is consumed by every route's ``Depends(requires(...))``; a
silent change here would change authorization behaviour platform-wide.
These tests pin the contract so any future edit shows up in a diff.
"""
from __future__ import annotations

import pytest

from core.security.principal import Principal
from core.security.rbac import (
    ROLE_MATRIX,
    Permission,
    PermissionDeniedError,
    Role,
    has_permission,
    require,
)


def test_every_role_present_in_matrix() -> None:
    assert set(ROLE_MATRIX.keys()) == set(Role)


def test_admin_has_every_permission() -> None:
    assert ROLE_MATRIX[Role.ADMIN] == frozenset(Permission)


def test_admin_holds_each_permission_by_name() -> None:
    """Phase 7 WP1 — pin the contract member-by-member.

    The matrix entry ``Role.ADMIN: frozenset(Permission)`` relies on
    ``frozenset(EnumClass)`` iterating to all members. A future refactor
    that swaps the right-hand side to ``frozenset(set(Permission))`` or
    a comprehension would still pass the equality test above if the
    derivation is correct — but a typo like ``frozenset({Permission})``
    (wrapping the enum class itself in a literal set) would silently
    yield a one-element set. Iterating each known permission catches
    that class of regression directly.
    """
    perms = ROLE_MATRIX[Role.ADMIN]
    for permission in Permission:
        assert permission in perms, (
            f"ADMIN role is missing {permission.value!r} — "
            "the RBAC matrix is broken"
        )


@pytest.mark.parametrize("role", [Role.READONLY, Role.AI_AGENT, Role.SERVICE_ACCOUNT])
def test_non_write_roles_lack_investigation_write(role: Role) -> None:
    assert Permission.INVESTIGATION_WRITE not in ROLE_MATRIX[role]


def test_readonly_truly_readonly() -> None:
    perms = ROLE_MATRIX[Role.READONLY]
    write_perms = {
        Permission.INVESTIGATION_WRITE,
        Permission.WORKFLOW_WRITE,
        Permission.AGENT_EXECUTE,
        Permission.IOC_INGEST,
    }
    assert not (perms & write_perms)


def test_external_user_cannot_execute_agents_or_read_graph() -> None:
    perms = ROLE_MATRIX[Role.EXTERNAL_USER]
    assert Permission.AGENT_EXECUTE not in perms
    assert Permission.GRAPH_READ not in perms


def test_require_raises_when_role_lacks_permission() -> None:
    principal = Principal(subject="bob", role="readonly")
    with pytest.raises(PermissionDeniedError) as exc:
        require(principal, Permission.INVESTIGATION_WRITE)
    assert exc.value.permission == Permission.INVESTIGATION_WRITE
    assert exc.value.role == "readonly"
    assert exc.value.subject == "bob"


def test_require_allows_matching_permission() -> None:
    principal = Principal(subject="alice", role="analyst")
    require(principal, Permission.INVESTIGATION_WRITE)  # no exception


def test_unknown_role_denies_everything() -> None:
    principal = Principal(subject="x", role="nonexistent")
    assert not has_permission("nonexistent", Permission.INVESTIGATION_READ)
    with pytest.raises(PermissionDeniedError):
        require(principal, Permission.INVESTIGATION_READ)


def test_principal_immutable() -> None:
    principal = Principal(subject="alice", role="readonly")
    with pytest.raises((AttributeError, TypeError)):
        principal.role = "admin"  # type: ignore[misc]
