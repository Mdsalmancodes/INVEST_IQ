"""auth_router.py — HTTP endpoints wiring all 8 auth use cases.

Per Document 4 §9.4's endpoint catalog (auth section) and Document 3 §7.4's
flow. Every endpoint follows the pattern: extract request context (IP,
user-agent) -> build command -> call use case -> map domain exceptions to
HTTP via raise_as_http() -> return DTO.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from src.application.auth.list_login_history_use_case import ListLoginHistoryCommand
from src.application.auth.list_login_history_use_case import (
    ListLoginHistoryUseCase as ListLoginHistoryUseCaseType,
)
from src.application.auth.login_use_case import LoginCommand
from src.application.auth.login_use_case import LoginUseCase as LoginUseCaseType
from src.application.auth.logout_use_case import LogoutCommand, LogoutEverywhereCommand
from src.application.auth.logout_use_case import (
    LogoutEverywhereUseCase as LogoutEverywhereUseCaseType,
)
from src.application.auth.logout_use_case import LogoutUseCase as LogoutUseCaseType
from src.application.auth.refresh_token_use_case import RefreshTokenCommand
from src.application.auth.refresh_token_use_case import (
    RefreshTokenUseCase as RefreshTokenUseCaseType,
)
from src.application.auth.register_use_case import RegisterCommand
from src.application.auth.register_use_case import RegisterUseCase as RegisterUseCaseType
from src.application.auth.reset_password_use_case import (
    RequestPasswordResetCommand,
    ResetPasswordCommand,
)
from src.application.auth.reset_password_use_case import (
    RequestPasswordResetUseCase as RequestPasswordResetUseCaseType,
)
from src.application.auth.reset_password_use_case import (
    ResetPasswordUseCase as ResetPasswordUseCaseType,
)
from src.application.auth.verify_email_use_case import (
    RequestEmailVerificationCommand,
    VerifyEmailCommand,
)
from src.application.auth.verify_email_use_case import (
    RequestEmailVerificationUseCase as RequestEmailVerificationUseCaseType,
)
from src.application.auth.verify_email_use_case import (
    VerifyEmailUseCase as VerifyEmailUseCaseType,
)
from src.domain.auth.exceptions import AuthDomainError
from src.presentation.dependencies.auth import CurrentUser, get_current_user
from src.presentation.dependencies.use_cases import (
    get_list_login_history_use_case,
    get_login_use_case,
    get_logout_everywhere_use_case,
    get_logout_use_case,
    get_refresh_token_use_case,
    get_register_use_case,
    get_request_email_verification_use_case,
    get_request_password_reset_use_case,
    get_reset_password_use_case,
    get_verify_email_use_case,
)
from src.presentation.dto.auth_dto import (
    LoginHistoryEntryResponse,
    LoginHistoryListResponse,
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    MessageResponse,
    RefreshTokenRequest,
    RefreshTokenResponse,
    RegisterRequest,
    RegisterResponse,
    RequestEmailVerificationRequest,
    RequestPasswordResetRequest,
    ResetPasswordRequest,
    VerifyEmailRequest,
)
from src.presentation.exception_handlers import raise_as_http

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client is not None else None


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    use_case: Annotated[RegisterUseCaseType, Depends(get_register_use_case)],
) -> RegisterResponse:
    try:
        result = await use_case.execute(
            RegisterCommand(email=body.email, password=body.password, full_name=body.full_name)
        )
    except AuthDomainError as exc:
        raise_as_http(exc)
        raise  # unreachable — raise_as_http always raises; satisfies type checker
    return RegisterResponse(user_id=str(result.user_id), email=str(result.email))


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    request: Request,
    use_case: Annotated[LoginUseCaseType, Depends(get_login_use_case)],
) -> LoginResponse:
    try:
        result = await use_case.execute(
            LoginCommand(
                email=body.email,
                password=body.password,
                ip_address=_client_ip(request),
                user_agent=request.headers.get("user-agent"),
                device_label=None,  # derived server-side from user-agent in a later phase
            )
        )
    except AuthDomainError as exc:
        raise_as_http(exc)
        raise
    return LoginResponse(access_token=result.access_token, refresh_token=result.refresh_token)


@router.post("/refresh", response_model=RefreshTokenResponse)
async def refresh_token(
    body: RefreshTokenRequest,
    use_case: Annotated[RefreshTokenUseCaseType, Depends(get_refresh_token_use_case)],
) -> RefreshTokenResponse:
    try:
        result = await use_case.execute(RefreshTokenCommand(body.refresh_token))
    except AuthDomainError as exc:
        raise_as_http(exc)
        raise
    return RefreshTokenResponse(
        access_token=result.access_token, refresh_token=result.refresh_token
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def logout(
    body: LogoutRequest,
    use_case: Annotated[LogoutUseCaseType, Depends(get_logout_use_case)],
) -> None:
    await use_case.execute(LogoutCommand(body.refresh_token))


@router.post("/logout-everywhere", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def logout_everywhere(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    use_case: Annotated[LogoutEverywhereUseCaseType, Depends(get_logout_everywhere_use_case)],
) -> None:
    await use_case.execute(LogoutEverywhereCommand(current_user.user_id))


@router.post("/request-email-verification", response_model=MessageResponse)
async def request_email_verification(
    body: RequestEmailVerificationRequest,
    use_case: Annotated[
        RequestEmailVerificationUseCaseType, Depends(get_request_email_verification_use_case)
    ],
) -> MessageResponse:
    # Response is identical whether or not the account exists/is already
    # verified (Document 6 §15.1 enumeration mitigation) — the result is
    # deliberately not inspected here beyond calling execute().
    await use_case.execute(RequestEmailVerificationCommand(body.email))
    return MessageResponse(
        message="If an account exists for this email, a verification link has been sent."
    )


@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(
    body: VerifyEmailRequest,
    use_case: Annotated[VerifyEmailUseCaseType, Depends(get_verify_email_use_case)],
) -> MessageResponse:
    try:
        await use_case.execute(VerifyEmailCommand(body.token))
    except AuthDomainError as exc:
        raise_as_http(exc)
        raise
    return MessageResponse(message="Email verified successfully.")


@router.post("/request-password-reset", response_model=MessageResponse)
async def request_password_reset(
    body: RequestPasswordResetRequest,
    use_case: Annotated[
        RequestPasswordResetUseCaseType, Depends(get_request_password_reset_use_case)
    ],
) -> MessageResponse:
    # Same enumeration-mitigation rationale as request_email_verification.
    await use_case.execute(RequestPasswordResetCommand(body.email))
    return MessageResponse(
        message="If an account exists for this email, a password reset link has been sent."
    )


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    body: ResetPasswordRequest,
    use_case: Annotated[ResetPasswordUseCaseType, Depends(get_reset_password_use_case)],
) -> MessageResponse:
    try:
        await use_case.execute(ResetPasswordCommand(body.token, body.new_password))
    except AuthDomainError as exc:
        raise_as_http(exc)
        raise
    return MessageResponse(message="Password reset successfully. Please log in again.")


@router.get("/login-history", response_model=LoginHistoryListResponse)
async def list_login_history(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    use_case: Annotated[ListLoginHistoryUseCaseType, Depends(get_list_login_history_use_case)],
) -> LoginHistoryListResponse:
    # Scoped to the current authenticated user's own id — never accepts a
    # user_id from the request, per Document 3 §7.5's resource-level
    # ownership enforcement (no admin override needed for one's own history).
    entries = await use_case.execute(ListLoginHistoryCommand(current_user.user_id))
    return LoginHistoryListResponse(
        entries=[
            LoginHistoryEntryResponse(
                ip_address=entry.ip_address,
                user_agent=entry.user_agent,
                device_label=entry.device_label,
                success=entry.success,
                failure_reason=entry.failure_reason,
                created_at=entry.created_at.isoformat(),
            )
            for entry in entries
        ]
    )
