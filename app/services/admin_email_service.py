from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage

from app.core.logging import logger
from core.settings import get_settings


def _send_email_sync(*, subject: str, body: str) -> None:
    settings = get_settings()
    if not settings.smtp_host or not settings.admin_email:
        logger.warning(
            "Admin email alert skipped: SMTP_HOST or ADMIN_EMAIL not configured."
        )
        return

    from_addr = settings.smtp_user or settings.admin_email
    to_addr = settings.admin_email

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.set_content(body)

    port = int(settings.smtp_port)

    if port == 465:
        with smtplib.SMTP_SSL(settings.smtp_host, port, timeout=20) as smtp:
            if settings.smtp_user:
                smtp.login(
                    settings.smtp_user, settings.smtp_password.get_secret_value()
                )
            smtp.send_message(msg)
        return

    with smtplib.SMTP(settings.smtp_host, port, timeout=20) as smtp:
        smtp.ehlo()
        try:
            smtp.starttls()
            smtp.ehlo()
        except smtplib.SMTPException:
            logger.info("SMTP: STARTTLS not available; continuing without TLS")

        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password.get_secret_value())
        smtp.send_message(msg)


async def send_admin_alert_email(*, subject: str, body: str) -> None:
    """Send an admin alert email using SMTP settings.

    Args:
        subject: Email subject.
        body: Email body text.

    Returns:
        None.
    """

    await asyncio.to_thread(_send_email_sync, subject=subject, body=body)
