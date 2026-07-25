"""Dependency-injection wiring for auth use cases — Document 3 §7.5's
"use FastAPI dependency injection" pattern. Each use case is constructed
via a small factory function taking already-injected repositories/services,
composed with Depends() in auth_router.py.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.auth.audit_logger import AuditLogger
from src.application.auth.list_login_history_use_case import ListLoginHistoryUseCase
from src.application.auth.login_use_case import LoginUseCase
from src.application.auth.logout_use_case import LogoutEverywhereUseCase, LogoutUseCase
from src.application.auth.refresh_token_use_case import RefreshTokenUseCase
from src.application.auth.register_use_case import RegisterUseCase
from src.application.auth.reset_password_use_case import (
    RequestPasswordResetUseCase,
    ResetPasswordUseCase,
)
from src.application.auth.verify_email_use_case import (
    RequestEmailVerificationUseCase,
    VerifyEmailUseCase,
)
from src.infrastructure.persistence.postgres.repositories.audit_log_repository import (
    SqlAlchemyAuditLogRepository,
)
from src.infrastructure.persistence.postgres.repositories.login_history_repository import (
    SqlAlchemyLoginHistoryRepository,
)
from src.infrastructure.persistence.postgres.repositories.refresh_token_repository import (
    SqlAlchemyRefreshTokenRepository,
)
from src.infrastructure.persistence.postgres.repositories.user_repository import (
    SqlAlchemyUserRepository,
)
from src.infrastructure.persistence.postgres.session import get_db_session
from src.infrastructure.persistence.redis.clients import RedisClients, get_redis_clients
from src.infrastructure.rate_limiting.login_rate_limiter import LoginRateLimiter
from src.infrastructure.security.jwt_provider import JwtProvider
from src.infrastructure.security.password_hasher import Argon2PasswordHasher
from src.infrastructure.security.token_blacklist import TokenBlacklist
from src.infrastructure.security.verification_token_store import (
    email_verification_store,
    password_reset_store,
)
from src.presentation.dependencies.auth import get_jwt_provider, get_token_blacklist


def get_password_hasher() -> Argon2PasswordHasher:
    return Argon2PasswordHasher()


def get_register_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    hasher: Annotated[Argon2PasswordHasher, Depends(get_password_hasher)],
) -> RegisterUseCase:
    return RegisterUseCase(SqlAlchemyUserRepository(session), hasher)


def get_login_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    redis_clients: Annotated[RedisClients, Depends(get_redis_clients)],
    hasher: Annotated[Argon2PasswordHasher, Depends(get_password_hasher)],
    jwt_provider: Annotated[JwtProvider, Depends(get_jwt_provider)],
) -> LoginUseCase:
    return LoginUseCase(
        user_repository=SqlAlchemyUserRepository(session),
        refresh_token_repository=SqlAlchemyRefreshTokenRepository(session),
        login_history_repository=SqlAlchemyLoginHistoryRepository(session),
        audit_logger=AuditLogger(SqlAlchemyAuditLogRepository(session)),
        rate_limiter=LoginRateLimiter(redis_clients.session),
        password_hasher=hasher,
        jwt_provider=jwt_provider,
    )


def get_refresh_token_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    jwt_provider: Annotated[JwtProvider, Depends(get_jwt_provider)],
) -> RefreshTokenUseCase:
    return RefreshTokenUseCase(
        SqlAlchemyUserRepository(session),
        SqlAlchemyRefreshTokenRepository(session),
        jwt_provider,
    )


def get_logout_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    token_blacklist: Annotated[TokenBlacklist, Depends(get_token_blacklist)],
) -> LogoutUseCase:
    return LogoutUseCase(SqlAlchemyRefreshTokenRepository(session), token_blacklist)


def get_logout_everywhere_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> LogoutEverywhereUseCase:
    return LogoutEverywhereUseCase(
        SqlAlchemyUserRepository(session), SqlAlchemyRefreshTokenRepository(session)
    )


def get_request_email_verification_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    redis_clients: Annotated[RedisClients, Depends(get_redis_clients)],
) -> RequestEmailVerificationUseCase:
    return RequestEmailVerificationUseCase(
        SqlAlchemyUserRepository(session), email_verification_store(redis_clients.session)
    )


def get_verify_email_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    redis_clients: Annotated[RedisClients, Depends(get_redis_clients)],
) -> VerifyEmailUseCase:
    return VerifyEmailUseCase(
        SqlAlchemyUserRepository(session), email_verification_store(redis_clients.session)
    )


def get_request_password_reset_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    redis_clients: Annotated[RedisClients, Depends(get_redis_clients)],
) -> RequestPasswordResetUseCase:
    return RequestPasswordResetUseCase(
        SqlAlchemyUserRepository(session), password_reset_store(redis_clients.session)
    )


def get_reset_password_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    redis_clients: Annotated[RedisClients, Depends(get_redis_clients)],
    hasher: Annotated[Argon2PasswordHasher, Depends(get_password_hasher)],
) -> ResetPasswordUseCase:
    return ResetPasswordUseCase(
        SqlAlchemyUserRepository(session),
        SqlAlchemyRefreshTokenRepository(session),
        password_reset_store(redis_clients.session),
        hasher,
        audit_logger=AuditLogger(SqlAlchemyAuditLogRepository(session)),
    )


def get_list_login_history_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ListLoginHistoryUseCase:
    return ListLoginHistoryUseCase(SqlAlchemyLoginHistoryRepository(session))
