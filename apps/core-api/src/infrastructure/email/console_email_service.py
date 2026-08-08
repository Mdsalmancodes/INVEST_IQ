"""ConsoleEmailService — development-mode email provider that logs emails
to structured output instead of sending them over the network.

Selected when EMAIL_PROVIDER=console (the default for local development),
following the same mock-vs-live pattern established by ai_service_mode
in src/config.py.
"""

from __future__ import annotations

from observability import get_logger

from src.infrastructure.email.email_templates import (
    render_password_reset_email,
    render_verification_email,
)

logger = get_logger(__name__)


class ConsoleEmailService:
    """Logs transactional emails via structlog — no network calls.

    Satisfies the EmailService protocol without importing it (structural
    typing / duck typing), consistent with how other infrastructure
    implementations in this project relate to their protocols.
    """

    def __init__(self, frontend_url: str, email_from: str, email_from_name: str) -> None:
        self._frontend_url = frontend_url
        self._email_from = email_from
        self._email_from_name = email_from_name
        logger.info(
            "email.provider.initialized",
            provider="console",
            from_email=email_from,
            from_name=email_from_name,
        )

    async def send_verification_email(self, to_email: str, token: str) -> bool:
        verify_url = f"{self._frontend_url}/verify-email?token={token}"
        html_body, text_body = render_verification_email(verify_url)

        logger.info(
            "email.verification.sent",
            provider="console",
            recipient=to_email,
            subject="Verify your INVEST IQ email",
            verify_url=verify_url,
            from_email=self._email_from,
            from_name=self._email_from_name,
            html_rendered=bool(html_body),
            text_rendered=bool(text_body),
        )
        return True

    async def send_password_reset_email(self, to_email: str, token: str) -> bool:
        reset_url = f"{self._frontend_url}/reset-password?token={token}"
        html_body, text_body = render_password_reset_email(reset_url)

        logger.info(
            "email.password_reset.sent",
            provider="console",
            recipient=to_email,
            subject="Reset your INVEST IQ password",
            reset_url=reset_url,
            from_email=self._email_from,
            from_name=self._email_from_name,
            html_rendered=bool(html_body),
            text_rendered=bool(text_body),
        )
        return True
