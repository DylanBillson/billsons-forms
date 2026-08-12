from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage
from email.utils import formataddr

from app.core.config import settings


class PermanentEmailError(Exception):
    pass


class TemporaryEmailError(Exception):
    pass


def build_submission_email_body(payload: dict[str, object]) -> str:
    lines = ["New form submission", ""]
    for key, value in payload.items():
        lines.append(f"{key}: {value}")
    return "\n".join(lines)


def _send_submission_email(**kwargs) -> None:
    message = EmailMessage()
    message["Subject"] = kwargs["subject"]
    message["From"] = formataddr((kwargs.get("sender_name") or "", kwargs["sender_email"]))
    message["To"] = ", ".join(kwargs["recipients"])
    if kwargs.get("reply_to_email"):
        message["Reply-To"] = kwargs["reply_to_email"]
    message.set_content(kwargs["body"])
    security = kwargs["smtp_security"].lower().strip()
    smtp_class = smtplib.SMTP_SSL if security == "ssl" else smtplib.SMTP
    try:
        with smtp_class(kwargs["smtp_host"], kwargs["smtp_port"], timeout=kwargs.get("timeout", settings.smtp_timeout_seconds)) as server:
            if security == "starttls":
                server.starttls()
            if kwargs.get("smtp_username") and kwargs.get("smtp_password"):
                server.login(kwargs["smtp_username"], kwargs["smtp_password"])
            server.send_message(message)
    except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused, smtplib.SMTPAuthenticationError) as exc:
        raise PermanentEmailError(str(exc)) from exc
    except (smtplib.SMTPException, OSError) as exc:
        raise TemporaryEmailError(str(exc)) from exc


async def send_submission_email(**kwargs) -> None:
    await asyncio.to_thread(_send_submission_email, **kwargs)


async def send_test_email(**kwargs) -> None:
    kwargs["subject"] = "Billson's Forms — SMTP configuration test"
    kwargs["body"] = "This is a configuration test from Billson's Forms. No form submission data is included."
    await send_submission_email(**kwargs)
