"""FastAPI dependency injection for auth — Document 3 §7.5's RBAC pattern.

Uses FastAPI's own Depends() composition (per the "use FastAPI dependency
injection" implementation directive) rather than a custom DI container.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.config import Settings, get_settings
from src.domain.auth.entities import Role
from src.domain.auth.exceptions import InvalidTokenError, TokenExpiredError
from src.domain.auth.value_objects import UserId
from src.infrastructure.security.jwt_provider import JwtProvider

_bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True, slots=True)
class CurrentUser:
    """The authenticated principal for the current request — deliberately
    NOT the full domain User entity (which would require a DB round-trip on
    every authenticated request just to check a role). Route handlers that
    need the full entity fetch it explicitly via the use case/repository;
    this dependency only carries what's already in the verified JWT claims.
    """

    user_id: UserId
    role: Role
    token_version: int


def get_jwt_provider(settings: Annotated[Settings, Depends(get_settings)]) -> JwtProvider:
    return JwtProvider(
        current_kid=settings.jwt_kid,
        current_secret=settings.jwt_secret.get_secret_value(),
        access_token_ttl_minutes=settings.jwt_access_token_ttl_minutes,
        previous_kid=settings.jwt_previous_kid,
        previous_secret=(
            settings.jwt_previous_secret.get_secret_value()
            if settings.jwt_previous_secret is not None
            else None
        ),
    )


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    jwt_provider: Annotated[JwtProvider, Depends(get_jwt_provider)],
) -> CurrentUser:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials",
        )

    try:
        claims = jwt_provider.verify_access_token(credentials.credentials)
    except TokenExpiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Access token has expired"
        ) from exc
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token"
        ) from exc

    return CurrentUser(user_id=claims.user_id, role=claims.role, token_version=claims.token_version)
