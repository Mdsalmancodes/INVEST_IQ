import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


class SmtpEmailProvider:
    def __init__(self, settings):
        self.host = settings.smtp_host
        self.port = settings.smtp_port
        self.username = settings.smtp_username
        self.password = settings.smtp_password.get_secret_value()
        self.from_email = settings.smtp_from_email
        self.from_name = settings.smtp_from_name

    def send_verification_email(self, to_email: str, subject: str, html: str):
        msg = MIMEMultipart()
        msg["From"] = f"{self.from_name} <{self.from_email}>"
        msg["To"] = to_email
        msg["Subject"] = subject

        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(self.host, self.port) as server:
            server.starttls()
            server.login(self.username, self.password)
            server.send_message(msg)