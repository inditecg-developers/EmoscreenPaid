import os
from pathlib import Path

from django.conf import settings


def build_pdf_password(prefix_source: str, phone: str) -> str:
    source = (prefix_source or "").strip()
    phone_digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    return f"{source[:4]}{phone_digits[-4:]}"


def report_paths(order_code: str):
    base = Path(settings.MEDIA_ROOT) / "paid_reports" / order_code
    os.makedirs(base, exist_ok=True)
    return {
        "patient": str(base / "patient.pdf"),
        "doctor": str(base / "doctor.pdf"),
    }
