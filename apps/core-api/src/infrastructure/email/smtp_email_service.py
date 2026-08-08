import aiosmtplib
from email.message import EmailMessage

from src.config import Settings


class SMTPEmailService:
    def __init__(self, settings: Settings):
        self.host = settings.smtp_host
        self.port = settings.smtp_port
        self.username = settings.smtp_username
        self.password = settings.smtp_password.get_secret_value()
        self.from_email = settings.smtp_from_email

    async def send_verification_email(self, to_email: str, token: str) -> bool:
        try:
            subject = "Verify your INVEST IQ account"
            content = f"Click to verify: http://localhost:3000/verify-email?token={token}"

            await self._send_email(to_email, subject, content)
            return True

        except Exception as e:
            print("Email error:", e)
            return False

    async def send_password_reset_email(self, to_email: str, token: str) -> bool:
        try:
            subject = "Reset your INVEST IQ password"
            content = f"Reset here: http://localhost:3000/reset-password?token={token}"

            await self._send_email(to_email, subject, content)
            return True

        except Exception as e:
            print("Email error:", e)
            return False

    async def _send_email(self, to_email: str, subject: str, content: str):
        message = EmailMessage()
        message["From"] = self.from_email
        message["To"] = to_email
        message["Subject"] = subject
        message.set_content(content)

        await aiosmtplib.send(
            message,
            hostname=self.host,
            port=self.port,
            username=self.username,
            password=self.password,
            start_tls=True,
        )