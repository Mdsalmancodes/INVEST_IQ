"""Mapping between SQLAlchemy ORM models and domain entities/value objects.

Kept as standalone functions (not methods on the ORM models themselves) so
the ORM layer has zero knowledge of the domain layer — the dependency arrow
points from infrastructure to domain, never the reverse (Document 2 §4.1).
"""

from __future__ import annotations

from src.domain.auth.entities import LoginHistoryEntry, RefreshToken, Role, User
from src.domain.auth.value_objects import Email, HashedPassword, UserId
from src.infrastructure.persistence.postgres.models import (
    LoginHistoryModel,
    RefreshTokenModel,
    UserModel,
)


def user_to_domain(model: UserModel) -> User:
    return User(
        id=UserId(model.id),
        email=Email(model.email),
        hashed_password=HashedPassword(model.hashed_password)
        if model.hashed_password is not None
        else None,
        full_name=model.full_name,
        role=Role(model.role),
        token_version=model.token_version,
        email_verified_at=model.email_verified_at,
        created_at=model.created_at,
        updated_at=model.updated_at,
        risk_profile=None,
    )


def user_to_model(entity: User, *, existing: UserModel | None = None) -> UserModel:
    """Builds/updates a UserModel from a domain User.

    If `existing` is provided, mutates and returns it (correct pattern for
    an update within an active SQLAlchemy session — the identity map means
    this instance is already tracked); otherwise constructs a new one for
    insertion.
    """
    model = existing if existing is not None else UserModel(id=entity.id.value)
    model.email = str(entity.email)
    model.hashed_password = (
        entity.hashed_password.value if entity.hashed_password is not None else None
    )
    model.full_name = entity.full_name
    model.role = entity.role.value
    model.token_version = entity.token_version
    model.email_verified_at = entity.email_verified_at
    return model


def refresh_token_to_domain(model: RefreshTokenModel) -> RefreshToken:
    return RefreshToken(
        id=UserId(model.id),
        user_id=UserId(model.user_id),
        token_hash=model.token_hash,
        expires_at=model.expires_at,
        created_at=model.created_at,
        revoked_at=model.revoked_at,
    )


def refresh_token_to_model(entity: RefreshToken) -> RefreshTokenModel:
    return RefreshTokenModel(
        id=entity.id.value,
        user_id=entity.user_id.value,
        token_hash=entity.token_hash,
        expires_at=entity.expires_at,
        revoked_at=entity.revoked_at,
    )


def login_history_to_domain(model: LoginHistoryModel) -> LoginHistoryEntry:
    return LoginHistoryEntry(
        id=UserId(model.id),
        user_id=UserId(model.user_id),
        ip_address=model.ip_address,
        user_agent=model.user_agent,
        device_label=model.device_label,
        success=model.success,
        failure_reason=model.failure_reason,
        created_at=model.created_at,
    )


def login_history_to_model(entity: LoginHistoryEntry) -> LoginHistoryModel:
    return LoginHistoryModel(
        id=entity.id.value,
        user_id=entity.user_id.value,
        ip_address=entity.ip_address,
        user_agent=entity.user_agent,
        device_label=entity.device_label,
        success=entity.success,
        failure_reason=entity.failure_reason,
    )
