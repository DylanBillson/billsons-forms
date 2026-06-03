import smtplib
from email.message import EmailMessage
from email.utils import formataddr


def build_submission_email_body(payload: dict[str, object]) -> str:
    lines = ["New form submission", ""]

    for key, value in payload.items():
        lines.append(f"{key}: {value}")

    return "\n".join(lines)


def send_submission_email(
    *,
    smtp_host: str,
    smtp_port: int,
    smtp_username: str | None,
    smtp_password: str | None,
    smtp_security: str,
    sender_email: str,
    sender_name: str | None,
    recipients: list[str],
    subject: str,
    body: str,
    reply_to_email: str | None = None,
) -> None:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr((sender_name or "", sender_email))
    message["To"] = ", ".join(recipients)

    if reply_to_email:
        message["Reply-To"] = reply_to_email

    message.set_content(body)

    security = smtp_security.lower().strip()

    if security == "ssl":
        with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=20) as server:
            if smtp_username and smtp_password:
                server.login(smtp_username, smtp_password)
            server.send_message(message)
        return

    with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
        if security == "starttls":
            server.starttls()

        if smtp_username and smtp_password:
            server.login(smtp_username, smtp_password)

        server.send_message(message)