import io
import os
import re
from pathlib import Path

from django.conf import settings
from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from paid.models import (
    EsCfgDerivedList,
    EsCfgOption,
    EsCfgQuestion,
    EsCfgReportTemplate,
    EsRepReport,
    EsSubAnswer,
    EsSubScaleScore,
)


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


def _encrypt_pdf(raw_pdf: bytes, password: str) -> bytes:
    reader = PdfReader(io.BytesIO(raw_pdf))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.encrypt(password)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def _age_text(dob, assessment_date):
    if not dob or not assessment_date:
        return ""
    months = (assessment_date.year - dob.year) * 12 + (assessment_date.month - dob.month)
    if assessment_date.day < dob.day:
        months -= 1
    years = max(0, months // 12)
    rem = max(0, months % 12)
    return f"{years}y {rem}m"


def _question_rows(submission):
    question_qs = EsCfgQuestion.objects.filter(form=submission.form).order_by("global_order", "question_order")
    answers = {a.question_id: a for a in EsSubAnswer.objects.filter(submission=submission)}
    options = {o.option_code: o for o in EsCfgOption.objects.all()}

    rows = []
    for idx, q in enumerate(question_qs, start=1):
        ans = answers.get(q.question_code)
        if not ans:
            continue
        raw = str(ans.value_json)
        opt = options.get(raw)
        label = opt.label if opt else raw
        rows.append((idx, q.question_text, label))
    return rows


def _ace_items(submission):
    answers = {a.question_id: str(a.value_json) for a in EsSubAnswer.objects.filter(submission=submission)}
    question_map = {q.question_code: q for q in EsCfgQuestion.objects.filter(form=submission.form)}
    option_map = {o.option_code: o for o in EsCfgOption.objects.all()}

    ace_lists = EsCfgDerivedList.objects.filter(form=submission.form, name__icontains="ace")
    items = []
    for dl in ace_lists:
        expected = str(dl.filter_response_value or "").strip().lower()
        section_code = dl.section_id
        for q_code, raw in answers.items():
            q = question_map.get(q_code)
            if not q:
                continue
            if section_code and q.section_id != section_code:
                continue
            opt = option_map.get(raw)
            candidates = {raw.lower()}
            if opt:
                candidates.add(str(opt.value).strip().lower())
                candidates.add(str(opt.label).strip().lower())
            if expected in candidates:
                items.append(q.question_text)
    return list(dict.fromkeys(items))


def _header_band(submission):
    age = _age_text(submission.child_dob, submission.assessment_date)
    return [
        ["Child Name", submission.child_name or "", "Child Age", age],
        ["Child Gender", submission.gender or "", "Completed By", submission.completed_by or ""],
        ["Date", str(submission.assessment_date or ""), "", ""],
    ]


def _disclaimer_html(form, report_type):
    t = EsCfgReportTemplate.objects.filter(form=form, report_type=report_type).first()
    if t and t.disclaimer_html:
        return t.disclaimer_html
    return (
        "Kindly note, this report is purely based on the information submitted by the patient's guardians. "
        "For support, please contact +91-9321450803."
    )


def _normalize_paragraph_html(text: str) -> str:
    """Normalize template HTML to ReportLab Paragraph-friendly markup."""
    cleaned = (text or "").strip()
    if not cleaned:
        return ""

    # ReportLab expects self-closing line breaks and supports a limited markup subset.
    cleaned = re.sub(r"<\s*br\s*>", "<br/>", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<\s*br\s*/\s*>", "<br/>", cleaned, flags=re.IGNORECASE)

    # Strip outer <p> wrapper often present in template HTML.
    cleaned = re.sub(r"^\s*<\s*p\s*>", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<\s*/\s*p\s*>\s*$", "", cleaned, flags=re.IGNORECASE)
    return cleaned


def _build_pdf(report_type: str, submission) -> bytes:
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("title", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=22, spaceAfter=14)
    h_style = ParagraphStyle("h", parent=styles["Heading2"], fontSize=12, textColor=colors.HexColor("#0b2a4d"), spaceBefore=8, spaceAfter=6)
    body = styles["BodyText"]

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm, bottomMargin=14 * mm)
    story = []

    title = "Doctor Report for EmoScreen" if report_type == "doctor" else "Patient Report for EmoScreen"
    story.append(Paragraph(title, title_style))

    head = Table(_header_band(submission), colWidths=[30 * mm, 60 * mm, 30 * mm, 60 * mm])
    head.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#2f855a")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.white),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
    ]))
    story.append(head)
    story.append(Spacer(1, 8))

    story.append(Paragraph("Responses", h_style))
    response_rows = [["Sr.", "Question", "Response"]] + [[str(sr), q, a] for sr, q, a in _question_rows(submission)]
    rt = Table(response_rows, colWidths=[12 * mm, 110 * mm, 50 * mm], repeatRows=1)
    rt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2f855a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1d5db")),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
    ]))
    story.append(rt)

    if report_type == "doctor":
        story.append(Spacer(1, 8))
        story.append(Paragraph(
            f"Total score for this filled questionnaire is {submission.total_score or 0} / {submission.total_score_max_display or 0}",
            body,
        ))

        risk_rows = [["Disorder", "Score", "Risk Factor (%)"]]
        for s in EsSubScaleScore.objects.filter(submission=submission, included_in_doctor_table=True).select_related("scale"):
            risk_rows.append([
                s.scale.label,
                f"{s.score}/{s.max_score}",
                f"{s.risk_percent:.2f}",
            ])
        if len(risk_rows) > 1:
            story.append(Paragraph("The results fall into moderate to high risk for the following disorders:", body))
            risk_table = Table(risk_rows, colWidths=[70 * mm, 40 * mm, 40 * mm], repeatRows=1)
            risk_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2f855a")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1d5db")),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ]))
            story.append(risk_table)

        ace = _ace_items(submission)
        if ace:
            story.append(Spacer(1, 8))
            story.append(Paragraph("ACE:", h_style))
            for item in ace:
                story.append(Paragraph(f"• {item}", body))

        summary = (
            "As per the report, some concerns are observed in the child. This requires thorough evaluation & an urgent referral and support of a family EQ coach."
            if submission.has_concerns
            else "As per the report, no major concerns have been observed in the child. However, close monitoring for changes in behaviour & a follow-up with you is advised after 3 months to review."
        )
        story.append(Spacer(1, 8))
        story.append(Paragraph(summary, body))

    story.append(Spacer(1, 10))
    story.append(Paragraph(_normalize_paragraph_html(_disclaimer_html(submission.form, report_type)), body))

    doc.build(story)
    return buf.getvalue()


def generate_and_store_reports(submission):
    order = submission.order
    doctor = order.doctor

    patient_pwd = build_pdf_password(submission.child_name or order.patient_name, order.patient_whatsapp)
    doctor_pwd = build_pdf_password(doctor.email, doctor.whatsapp or "")

    patient_pdf = _encrypt_pdf(_build_pdf("patient", submission), patient_pwd)
    doctor_pdf = _encrypt_pdf(_build_pdf("doctor", submission), doctor_pwd)

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
