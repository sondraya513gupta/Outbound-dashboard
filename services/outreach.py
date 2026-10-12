from __future__ import annotations

import smtplib
from email.message import EmailMessage

from config import SMTP_FROM, SMTP_HOST, SMTP_PASSWORD, SMTP_PORT, SMTP_USER
from models import Lead


def smtp_ready() -> bool:
    return bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD and SMTP_FROM)


def send_smtp(lead: Lead) -> None:
    if not smtp_ready():
        raise RuntimeError("SMTP is not configured. Use the mail-client button instead.")
    if not lead.contact_email:
        raise RuntimeError("This lead has no contact email.")

    message = EmailMessage()
    message["From"] = SMTP_FROM
    message["To"] = lead.contact_email
    message["Subject"] = lead.email_subject
    message.set_content(lead.email_body)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(message)
