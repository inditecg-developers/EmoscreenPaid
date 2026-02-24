import base64
from typing import Iterable

from django.conf import settings

from paid.models import EsPayEmailLog


def log_email(order, email_type: str, to_email: str, subject: str, status: str = "QUEUED", error_text: str = ""):
    return EsPayEmailLog.objects.create(
        order=order,
        email_type=email_type,
        to_email=to_email,
        subject=subject,
        status=status,
        error_text=error_text,
    )


def _sendgrid_send_with_attachments(to_email: str, subject: str, html: str, attachments: Iterable[tuple[str, bytes]]) -> tuple[bool, str]:
    api_key = getattr(settings, "SENDGRID_API_KEY", "")
    if not api_key:
        print("[SendGrid] missing SENDGRID_API_KEY; skipping attachment email")
        return False, ""

    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import (
            Attachment,
            Disposition,
            Email,
            FileContent,
            FileName,
            FileType,
            Mail,
            To,
        )

        message = Mail(
            from_email=Email(settings.DEFAULT_FROM_EMAIL, settings.REPORT_FROM_NAME),
            to_emails=To(to_email),
            subject=subject,
            html_content=html,
        )

        for fname, payload in attachments:
            message.attachment = Attachment(
                FileContent(base64.b64encode(payload).decode("utf-8")),
                FileName(fname),
                FileType("application/pdf"),
                Disposition("attachment"),
            )

        sg = SendGridAPIClient(api_key)
        resp = sg.send(message)
        ok = 200 <= resp.status_code < 300
        msg_id = ""
        headers = getattr(resp, "headers", {}) or {}
        if isinstance(headers, dict):
            msg_id = headers.get("X-Message-Id", "")
        return ok, msg_id
    except Exception as exc:
        print("[SendGrid] attachment email error:", exc)
        return False, str(exc)
