"""Minimal SMTP email sender (stdlib only) — used for password-reset emails."""

import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger("vbots.email")


def smtp_configured() -> bool:
    return bool(settings.SMTP_HOST and settings.SMTP_USER and settings.SMTP_PASSWORD)


def send_email(to: str, subject: str, body_text: str, body_html: str | None = None) -> bool:
    """Send a plain-text (and optional HTML) email. Returns True on success."""
    if not smtp_configured():
        logger.warning("SMTP not configured — cannot send email to %s", to)
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_FROM or settings.SMTP_USER
    msg["To"] = to
    msg.set_content(body_text)
    if body_html:
        msg.add_alternative(body_html, subtype="html")

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
            if settings.SMTP_USE_TLS:
                server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)
        logger.info("Sent email to %s (subject=%r)", to, subject)
        return True
    except Exception as e:
        logger.error("Failed to send email to %s: %s", to, e)
        return False


def send_password_reset_email(to: str, reset_link: str) -> bool:
    subject = "Reset your VBots password"
    text = (
        f"You requested a password reset.\n\n"
        f"Click the link below to set a new password (valid for "
        f"{settings.RESET_TOKEN_EXPIRE_MINUTES} minutes):\n\n{reset_link}\n\n"
        f"If you didn't request this, you can ignore this email."
    )
    html = (
        f"<p>You requested a password reset.</p>"
        f"<p><a href=\"{reset_link}\">Click here to set a new password</a> "
        f"(valid for {settings.RESET_TOKEN_EXPIRE_MINUTES} minutes).</p>"
        f"<p>If you didn't request this, you can ignore this email.</p>"
    )
    return send_email(to, subject, text, html)
