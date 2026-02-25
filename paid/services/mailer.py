import base64
import logging
from typing import Iterable

from django.conf import settings
from django.core.mail import EmailMultiAlternatives

from paid.models import EsPayEmailLog

logger = logging.getLogger(__name__)


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
        logger.warning("[Paid Email] SENDGRID_API_KEY missing; falling back to Django SMTP backend")
        return _smtp_send_with_attachments(to_email, subject, html, attachments)

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
            attachment = Attachment(
                FileContent(base64.b64encode(payload).decode("utf-8")),
                FileName(fname),
                FileType("application/pdf"),
                Disposition("attachment"),
            )
            message.add_attachment(attachment)

        sg = SendGridAPIClient(api_key)
        resp = sg.send(message)
        ok = 200 <= resp.status_code < 300
        msg_id = ""
        headers = getattr(resp, "headers", {}) or {}
        if isinstance(headers, dict):
            msg_id = headers.get("X-Message-Id", "")
        if not ok:
            logger.error("[Paid Email] SendGrid send failed status=%s body=%s", getattr(resp, "status_code", ""), getattr(resp, "body", ""))
        return ok, msg_id or f"status:{getattr(resp, 'status_code', 'unknown')}"
    except Exception as exc:
        logger.exception("[Paid Email] SendGrid attachment email error")
        return _smtp_send_with_attachments(to_email, subject, html, attachments)


def _smtp_send_with_attachments(to_email: str, subject: str, html: str, attachments: Iterable[tuple[str, bytes]]) -> tuple[bool, str]:
    try:
        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "")
        message = EmailMultiAlternatives(subject=subject, body="Please see attached report.", from_email=from_email, to=[to_email])
        message.attach_alternative(html, "text/html")
        for fname, payload in attachments:
            message.attach(filename=fname, content=payload, mimetype="application/pdf")
        sent = message.send(fail_silently=False)
        if sent:
            return True, "smtp:sent"
        logger.error("[Paid Email] SMTP backend returned sent=0 for %s", to_email)
        return False, "smtp:no_delivery"
    except Exception as exc:
        logger.exception("[Paid Email] SMTP attachment email error")
        return False, str(exc)
