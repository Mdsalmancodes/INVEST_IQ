"""Pydantic request/response DTOs for auth endpoints.

Per Document 2 §5.3: presentation-layer concern, distinct from the domain
value objects — Pydantic models validate/serialize at the HTTP boundary,
domain value objects (Email, PlaintextPassword) enforce business invariants.
A request DTO here is deliberately "dumber" (just str fields with basic
Pydantic constraints) — the real validation happens when the application
layer constructs domain value objects from these fields, which is where
InvalidEmailError/InvalidPasswordError actually get raised.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    email: str = Field(..., examples=["investor@example.com"])
    password: str = Field(..., min_length=1, max_length=256)
    full_name: str = Field(..., min_length=1, max_length=200)


class RegisterResponse(BaseModel):
    user_id: str
    email: str
    message: str = "Registration successful. Please check your email to verify your account."


class LoginRequest(BaseModel):
    email: str
    password: str = Field(..., min_length=1, max_length=256)


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class RefreshTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class LogoutRequest(BaseModel):
    refresh_token: str


class RequestEmailVerificationRequest(BaseModel):
    email: str


class VerifyEmailRequest(BaseModel):
    token: str


class RequestPasswordResetRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=1, max_length=256)


class LoginHistoryEntryResponse(BaseModel):
    ip_address: str | None
    user_agent: str | None
    device_label: str | None
    success: bool
    failure_reason: str | None
    created_at: str


class LoginHistoryListResponse(BaseModel):
    entries: list[LoginHistoryEntryResponse]


class MessageResponse(BaseModel):
    """Generic success acknowledgement for endpoints that don't return a
    resource — used for endpoints where the response must be identical
    whether or not the underlying account exists (Document 6 §15.1
    enumeration mitigation: request-verification-email, request-password-
    reset both return this same shape regardless)."""

    message: str
