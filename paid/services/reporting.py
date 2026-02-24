import io
import os
from pathlib import Path

from django.conf import settings
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from paid.models import EsRepReport


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


def _simple_pdf_bytes(title: str, rows: list[tuple[str, str]]) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    y = h - 50
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, y, title)
    y -= 30
    c.setFont("Helvetica", 10)
    for k, v in rows:
        c.drawString(50, y, f"{k}: {v}")
        y -= 18
        if y < 60:
            c.showPage()
            y = h - 50
            c.setFont("Helvetica", 10)
    c.showPage()
    c.save()
    return buf.getvalue()


def _encrypt_pdf(raw_pdf: bytes, password: str) -> bytes:
    reader = PdfReader(io.BytesIO(raw_pdf))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.encrypt(password)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def generate_and_store_reports(submission):
    order = submission.order
    doctor = order.doctor

    patient_pwd = build_pdf_password(submission.child_name or order.patient_name, order.patient_whatsapp)
    doctor_pwd = build_pdf_password(doctor.email, doctor.whatsapp or "")

    shared_rows = [
        ("Form", order.form.title),
        ("Child Name", submission.child_name or order.patient_name),
        ("Assessment Date", str(submission.assessment_date or "")),
        ("Completed By", submission.completed_by),
        ("Gender", submission.gender),
        ("Total Score", str(submission.total_score or "0")),
    ]
    patient_pdf = _encrypt_pdf(_simple_pdf_bytes("Patient Report for EmoScreen", shared_rows), patient_pwd)
    doctor_rows = shared_rows + [
        ("Has Concerns", "Yes" if submission.has_concerns else "No"),
    ]
    doctor_pdf = _encrypt_pdf(_simple_pdf_bytes("Doctor Report for EmoScreen", doctor_rows), doctor_pwd)

    paths = report_paths(order.order_code)
    with open(paths["patient"], "wb") as f:
        f.write(patient_pdf)
    with open(paths["doctor"], "wb") as f:
        f.write(doctor_pdf)

    report, _ = EsRepReport.objects.update_or_create(
        submission=submission,
        defaults={
            "patient_pdf_path": paths["patient"],
            "doctor_pdf_path": paths["doctor"],
            "patient_pdf_password_hint": f"{(submission.child_name or order.patient_name)[:4]} + last 4 digits of patient WhatsApp",
            "doctor_pdf_password_hint": f"{(doctor.email or '')[:4]} + last 4 digits of doctor WhatsApp",
        },
    )
    return report, patient_pdf, doctor_pdf
