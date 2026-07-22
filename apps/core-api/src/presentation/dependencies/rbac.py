"""RBAC guards — Document 3 §7.5: "resource-level, not just role-level"
authorization. These compose with get_current_user (Document 3 §7.5's
example: `Depends(require_ownership_or_role(...))`).

Per Document 3 §7.5: "Ownership checks are resource-level, not just
role-level — a `user` role can only ever access resources it owns...
enforced at the repository query layer (never trust a role check alone for
row-level access; always scope the query)." These dependency guards are the
role-level half of that; the ownership half is enforced by scoping
repository queries by the current user's ID at the call site (route
handlers pass current_user.user_id into repository/use-case calls, they
never accept an arbitrary user_id from the request body for "which user's
data" — only for admin-only routes, gated by require_role(["admin", ...])).
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, HTTPException, status

from src.domain.auth.entities import Role
from src.presentation.dependencies.auth import CurrentUser, get_current_user


def require_role(
    allowed_roles: list[Role],
) -> Callable[..., Coroutine[Any, Any, CurrentUser]]:
    """Returns a FastAPI dependency that raises 403 unless the current
    user's role is in `allowed_roles`.

    Usage: `Depends(require_role([Role.ADMIN, Role.SUPER_ADMIN]))`.
    """

    async def _guard(
        current_user: Annotated[CurrentUser, Depends(get_current_user)],
    ) -> CurrentUser:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action",
            )
        return current_user

    return _guard


def require_ownership_or_role(
    *, owner_user_id: str, allowed_roles: list[Role]
) -> Callable[..., Coroutine[Any, Any, CurrentUser]]:
    """Returns a FastAPI dependency that permits access if EITHER:
    (a) the current user's id matches `owner_user_id` (they own the resource), OR
    (b) the current user's role is in `allowed_roles` (e.g. admin override).

    `owner_user_id` is resolved by the route handler BEFORE this dependency
    is constructed (typically from a path parameter or a prior DB lookup) —
    this dependency itself does no resource fetching, keeping it reusable
    across every resource type rather than coupled to one repository.
    """

    async def _guard(
        current_user: Annotated[CurrentUser, Depends(get_current_user)],
    ) -> CurrentUser:
        is_owner = str(current_user.user_id) == owner_user_id
        is_privileged = current_user.role in allowed_roles
        if not (is_owner or is_privileged):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this resource",
            )
        return current_user

    return _guard
