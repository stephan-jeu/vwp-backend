from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from core.settings import get_settings

logger = logging.getLogger(__name__)


def start_smtp_session() -> smtplib.SMTP:
    settings = get_settings()
    server = smtplib.SMTP(settings.smtp_host, settings.smtp_port)
    server.starttls()
    server.login(settings.smtp_user, settings.smtp_password.get_secret_value())
    return server

def send_email(to: str, subject: str, body: str) -> None:
    settings = get_settings()
    msg = EmailMessage()
    msg.set_content(body)
    msg["Subject"] = subject
    msg["From"] = settings.admin_email
    msg["To"] = to

    if not settings.smtp_host:
        print(f"SMTP not configured. Mock email to {to}: {subject}\n{body}")
        return

    try:
        with start_smtp_session() as server:
            server.send_message(msg)
    except Exception as e:
        print(f"Failed to send email to {to}: {e}")

def send_activation_email(email: str, token: str) -> None:
    activ_url = f"http://localhost:3000/auth/reset-password?token={token}&type=activation"
    logger.info("Activation link for %s: %s", email, activ_url)

    subject = "Account Activation - Veldwerkplanning"
    body = (
        f"Welcome to Veldwerkplanning!\n\n"
        f"Please click the link below to activate your account and set your password:\n"
        f"{activ_url}\n\n"
        f"If you did not request this, please ignore this email."
    )
    send_email(email, subject, body)


def send_reset_password_email(email: str, token: str) -> None:
    reset_url = f"http://localhost:3000/auth/reset-password?token={token}&type=reset"
    logger.info("Password reset link for %s: %s", email, reset_url)

    subject = "Password Reset - Veldwerkplanning"
    body = (
        f"You have requested a password reset.\n\n"
        f"Please click the link below to set a new password:\n"
        f"{reset_url}\n\n"
        f"If you did not request this, please ignore this email."
    )
    send_email(email, subject, body)
