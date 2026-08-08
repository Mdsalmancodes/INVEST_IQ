"""EmailService protocol — the single abstraction the application layer
depends on for sending transactional emails. Concrete implementations
(ConsoleEmailService for development, ResendEmailService for production)
live alongside this protocol in the infrastructure.email package.

Provider-agnostic: future providers (SES, SendGrid, Mailgun, SMTP) can be
added by implementing this protocol without changing any application logic.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class EmailService(Protocol):
    """Transactional email delivery abstraction.

    Returns True if the email was accepted for delivery, False otherwise.
    Implementations must never raise — delivery failures are logged
    internally and reported via the return value so callers (use cases)
    can proceed without try/except.
    """

    async def send_verification_email(self, to_email: str, token: str) -> bool:
        """Send an email-verification link to the given address."""
        ...

    async def send_password_reset_email(self, to_email: str, token: str) -> bool:
        """Send a password-reset link to the given address."""
        ...
