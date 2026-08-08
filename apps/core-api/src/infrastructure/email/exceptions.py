"""Email infrastructure exceptions — internal to the email subsystem,
never propagated to use cases or the presentation layer."""

from __future__ import annotations


class EmailSendError(Exception):
    """Raised when an email fails to send. Always caught within the email
    service implementation — callers (use cases) never see this."""

    def __init__(self, provider: str, recipient: str, reason: str) -> None:
        self.provider = provider
        self.recipient = recipient
        self.reason = reason
        super().__init__(f"[{provider}] Failed to send email to {recipient}: {reason}")
