"""ResendEmailService — production email provider using the Resend REST API.

Selected when EMAIL_PROVIDER=resend. Uses httpx.AsyncClient (already a
project dependency via ai_service_http_client.py) to call Resend's
POST /emails endpoint — no Resend SDK installed, following the same
"use the HTTP client we already have" pattern as AiServiceClient.
"""

from __future__ import annotations

import httpx
from observability import get_logger

from src.infrastructure.email.email_templates import (
    render_password_reset_email,
    render_verification_email,
)

logger = get_logger(__name__)

_RESEND_API_URL = "https://api.resend.com/emails"


class ResendEmailService:
    """Sends transactional emails via the Resend REST API.

    Satisfies the EmailService protocol. All delivery failures are caught,
    logged, and reported as False — never raised to callers.
    """

    def __init__(
        self,
        api_key: str,
        from_email: str,
        from_name: str,
        frontend_url: str,
    ) -> None:
        self._api_key = api_key
        self._from_email = from_email
        self._from_name = from_name
        self._frontend_url = frontend_url
        self._from_header = f"{from_name} <{from_email}>"
        logger.info(
            "email.provider.initialized",
            provider="resend",
            from_email=from_email,
            from_name=from_name,
        )

    async def _send(
        self, to_email: str, subject: str, html_body: str, text_body: str
    ) -> bool:
        """Send a single email via the Resend API. Returns True on success."""
        payload = {
            "from": self._from_header,
            "to": [to_email],
            "subject": subject,
            "html": html_body,
            "text": text_body,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    _RESEND_API_URL, json=payload, headers=headers
                )

            if response.status_code in (200, 201):
                logger.info(
                    "email.sent",
                    provider="resend",
                    recipient=to_email,
                    subject=subject,
                    status_code=response.status_code,
                )
                return True

            # Non-success status — log the response body for debugging
            # but never log the API key or token.
            logger.error(
                "email.send_failed",
                provider="resend",
                recipient=to_email,
                subject=subject,
                status_code=response.status_code,
                response_body=response.text[:500],
            )
            return False

        except httpx.TimeoutException:
            logger.error(
                "email.send_failed",
                provider="resend",
                recipient=to_email,
                subject=subject,
                reason="timeout",
            )
            return False
        except httpx.HTTPError as exc:
            logger.error(
                "email.send_failed",
                provider="resend",
                recipient=to_email,
                subject=subject,
                reason=str(exc),
            )
            return False
        except Exception:
            logger.error(
                "email.send_failed",
                provider="resend",
                recipient=to_email,
                subject=subject,
                reason="unexpected_error",
                exc_info=True,
            )
            return False

    async def send_verification_email(self, to_email: str, token: str) -> bool:
        verify_url = f"{self._frontend_url}/verify-email?token={token}"
        html_body, text_body = render_verification_email(verify_url)

        if not html_body and not text_body:
            logger.error(
                "email.template.empty",
                provider="resend",
                template="verify_email",
                recipient=to_email,
            )
            return False

        return await self._send(
            to_email=to_email,
            subject="Verify your INVEST IQ email",
            html_body=html_body,
            text_body=text_body,
        )

    async def send_password_reset_email(self, to_email: str, token: str) -> bool:
        reset_url = f"{self._frontend_url}/reset-password?token={token}"
        html_body, text_body = render_password_reset_email(reset_url)

        if not html_body and not text_body:
            logger.error(
                "email.template.empty",
                provider="resend",
                template="password_reset",
                recipient=to_email,
            )
            return False

        return await self._send(
            to_email=to_email,
            subject="Reset your INVEST IQ password",
            html_body=html_body,
            text_body=text_body,
        )
