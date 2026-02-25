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
    left = (
        f"Child Name: {submission.child_name or ''}<br/>"
        f"Child Age: {age}<br/>"
        f"Child Gender: {submission.gender or ''}<br/>"
        f"Completed By: {submission.completed_by or ''}"
    )
    right = f"Date: {submission.assessment_date or ''}"
    return left, right


def _disclaimer_html(form, report_type):
    t = _report_template(form, report_type)
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


def _report_template(form, report_type):
    return EsCfgReportTemplate.objects.filter(form=form, report_type=report_type).first()


def _resolve_logo_path(logo_value: str) -> str | None:
    if not logo_value:
        return None

    raw = Path(str(logo_value).strip())
    candidates = []
    if raw.is_absolute():
        candidates.append(raw)
    else:
        base = Path(getattr(settings, "BASE_DIR", Path.cwd()))
        media_root = Path(getattr(settings, "MEDIA_ROOT", ""))
        candidates.extend(
            [
                base / raw,
                base / "paid" / "assets" / "reporting" / "logos" / raw.name,
                base / "static" / "paid" / "reporting" / "logos" / raw.name,
                media_root / raw,
            ]
        )

    for candidate in candidates:
        if candidate and candidate.exists() and candidate.is_file():
            return str(candidate)
    return None


def _draw_page_footer(canvas, doc, template: EsCfgReportTemplate | None):
    canvas.saveState()
    page_width, _ = A4
    left_x = doc.leftMargin
    right_x = page_width - doc.rightMargin
    base_y = 14 * mm

    canvas.setStrokeColor(colors.HexColor("#d1d5db"))
    canvas.setLineWidth(0.6)
    canvas.line(left_x, base_y + 11 * mm, right_x, base_y + 11 * mm)

    company = (template.footer_company if template else "") or "EQUIPOISE Learning Private Limited"
    tagline = (template.footer_tagline if template else "") or (
        "The ISO 9001-2015 Certified\nEmotional Intelligence Research & Training Organisation"
    )
    phone = (template.footer_phone if template else "") or "+91 9004806077"
    email = (template.footer_email if template else "") or "equip2006@gmail.com"

    canvas.setFont("Helvetica-Bold", 11)
    canvas.drawString(left_x, base_y + 7 * mm, company)
    canvas.setFont("Helvetica", 9.5)
    for idx, line in enumerate(str(tagline).splitlines()):
        canvas.drawString(left_x, base_y + (3 - idx * 4) * mm, line)

    canvas.setFont("Helvetica-Bold", 11)
    canvas.drawRightString(right_x, base_y + 7 * mm, "Contact us")
    canvas.setFont("Helvetica", 9.5)
    canvas.drawRightString(right_x, base_y + 3 * mm, str(phone))
    canvas.drawRightString(right_x, base_y - 1 * mm, str(email))
    canvas.restoreState()


def _draw_page_header(canvas, doc, template: EsCfgReportTemplate | None, submission, report_type: str):
    canvas.saveState()
    page_width, page_height = A4
    left_x = doc.leftMargin
    right_x = page_width - doc.rightMargin
    top_y = page_height - 18 * mm

    title = "Doctor Report for EmoScreen" if report_type == "doctor" else "Patient Report for EmoScreen"
    canvas.setFont("Helvetica-Bold", 18)
    canvas.drawString(left_x, top_y, title)

    logo_path = _resolve_logo_path(template.header_logo_path if template else "")
    logo_y = top_y - 12 * mm
    if logo_path:
        canvas.drawImage(
            logo_path,
            left_x,
            logo_y,
            width=95 * mm,
            height=14 * mm,
            preserveAspectRatio=True,
            mask="auto",
        )

    header_left, header_right = _header_band(submission)
    band_top = logo_y - 4 * mm
    band_height = 18 * mm
    canvas.setFillColor(colors.HexColor("#4caf50"))
    canvas.rect(left_x, band_top - band_height, right_x - left_x, band_height, stroke=0, fill=1)

    clean_left = re.sub(r"<br\s*/?>", "\n", header_left)
    lines = [line for line in clean_left.splitlines() if line.strip()]
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica", 8.8)
    text_y = band_top - 4.0 * mm
    for line in lines:
        canvas.drawString(left_x + 3 * mm, text_y, line.strip())
        text_y -= 3.8 * mm

    canvas.drawRightString(right_x - 3 * mm, band_top - 4.0 * mm, re.sub(r"<[^>]*>", "", header_right))
    canvas.restoreState()


def _build_pdf(report_type: str, submission) -> bytes:
    template = _report_template(submission.form, report_type)
    styles = getSampleStyleSheet()
    h_style = ParagraphStyle("h", parent=styles["Heading2"], fontSize=12, textColor=colors.HexColor("#0b2a4d"), spaceBefore=10, spaceAfter=6)
    body = ParagraphStyle("body", parent=styles["BodyText"], fontName="Helvetica", fontSize=10.5, leading=14)
    table_cell = ParagraphStyle(
        "table_cell",
        parent=body,
        fontName="Helvetica",
        fontSize=10,
        leading=13,
        wordWrap="LTR",
    )
    table_cell_bold = ParagraphStyle(
        "table_cell_bold",
        parent=table_cell,
        fontName="Helvetica-Bold",
        textColor=colors.white,
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=74 * mm, bottomMargin=32 * mm)
    story = []
    story.append(Spacer(1, 2))

    greeting = "Dear Doctor," if report_type == "doctor" else "Dear Parent,"
    story.append(Paragraph(f"<b>{greeting}</b>", body))
    story.append(Spacer(1, 4))
    if report_type == "doctor":
        story.append(Paragraph("Your patient has filled the EmoScreen form.", body))
    else:
        story.append(Paragraph("Thank you for completing the EmoScreen form.", body))
    story.append(Paragraph("The responses are as follows:", body))
    story.append(Spacer(1, 8))

    story.append(Paragraph("Responses", h_style))
    response_rows = [[
        Paragraph("Question", table_cell_bold),
        Paragraph("Response", table_cell_bold),
    ]]
    for _, q, a in _question_rows(submission):
        response_rows.append([
            Paragraph(str(q), table_cell),
            Paragraph(str(a), table_cell),
        ])

    rt = Table(response_rows, colWidths=[118 * mm, 54 * mm], repeatRows=1)
    rt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2f855a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1d5db")),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#bfc7cd")),
    ]))
    for row_idx in range(1, len(response_rows)):
        if row_idx % 2 == 0:
            rt.setStyle(TableStyle([("BACKGROUND", (0, row_idx), (-1, row_idx), colors.HexColor("#f4f4f4"))]))
    story.append(rt)

    if report_type == "doctor":
        story.append(Spacer(1, 8))
        story.append(Paragraph(
            f"Total score for this filled questionnaire is {submission.total_score or 0} / {submission.total_score_max_display or 0}",
            body,
        ))

        risk_rows = [[
            Paragraph("Disorder", table_cell_bold),
            Paragraph("Score", table_cell_bold),
            Paragraph("Risk Factor (%)", table_cell_bold),
        ]]
        for s in EsSubScaleScore.objects.filter(submission=submission, included_in_doctor_table=True).select_related("scale"):
            risk_rows.append([
                Paragraph(str(s.scale.label), table_cell),
                Paragraph(f"{s.score}/{s.max_score}", table_cell),
                Paragraph(f"{s.risk_percent:.2f}", table_cell),
            ])
        if len(risk_rows) > 1:
            story.append(Paragraph("The results fall into moderate to high risk for the following disorders:", body))
            risk_table = Table(risk_rows, colWidths=[70 * mm, 40 * mm, 40 * mm], repeatRows=1)
            risk_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2f855a")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1d5db")),
                ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
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
    def _on_page(canvas, doc):
        _draw_page_header(canvas, doc, template, submission, report_type)
        _draw_page_footer(canvas, doc, template)

    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
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
