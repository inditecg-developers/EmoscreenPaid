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
