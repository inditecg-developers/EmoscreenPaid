import secrets
from datetime import timedelta
from decimal import Decimal

from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from content.models import RegisteredProfessional
from content.utils import normalize_phone, whatsapp_link
from content.views import _gate_google_and_email

from .forms import DemographicsForm, PaidPrescriptionForm, PatientEmailForm
from .models import EsCfgOption, EsCfgQuestion, EsPayOrder, EsPayRevenueSplit, EsPayTransaction, EsSubAnswer, EsSubSubmission
from .services.mailer import log_email
from .services.payment import RazorpayAdapter
from .services.scoring import compute_submission_scores
from .services.tokens import build_order_token_payload, hash_token, sign_payload, unsign_payload


PRICE_MAP = {
    "INR_499": 49900,
    "INR_100": 10000,
    "INR_20": 2000,
    "INR_1": 100,
    "INR_0": 0,
}


@require_http_methods(["GET", "POST"])
def prescribe_order(request, doctor_code):
    doctor = get_object_or_404(RegisteredProfessional, unique_doctor_code=doctor_code)
    gate = _gate_google_and_email(request, doctor, request.get_full_path())
    if gate is not None:
        return gate

    if request.method == "POST":
        form = PaidPrescriptionForm(request.POST)
        if form.is_valid():
            cfg_form = form.cleaned_data["form_code"]
            price_variant = form.cleaned_data["price_variant"]
            discount_paise = (form.cleaned_data.get("discount_rupees") or 0) * 100
            base_amount = PRICE_MAP[price_variant]
            final_amount = max(0, base_amount - discount_paise)

            order_code = secrets.token_hex(6).upper()
            order = EsPayOrder.objects.create(
                order_code=order_code,
                doctor=doctor,
                form=cfg_form,
                price_variant=price_variant,
                base_amount_paise=base_amount,
                discount_paise=discount_paise,
                final_amount_paise=final_amount,
                patient_name=form.cleaned_data["patient_name"],
                patient_whatsapp=normalize_phone(form.cleaned_data["patient_whatsapp"]),
                patient_email=form.cleaned_data.get("patient_email") or None,
                status=EsPayOrder.Status.PAYMENT_SKIPPED if final_amount == 0 else EsPayOrder.Status.PAYMENT_PENDING,
                link_token_hash="pending",
                link_expires_at=timezone.now() + timedelta(days=7),
                created_ip=request.META.get("REMOTE_ADDR"),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
            payload = build_order_token_payload(order, doctor_code)
            token = sign_payload(payload)
            order.link_token_hash = hash_token(token)
            order.status = EsPayOrder.Status.LINK_SENT
            order.save(update_fields=["link_token_hash", "status", "updated_at"])
            link = request.build_absolute_uri(
                reverse(
                    "paid:patient_entry",
                    args=[order.order_code, doctor.unique_doctor_code, order.form_id, order.final_amount_paise, token],
                )
            )
            msg = (
                "Dear Parents,\n\n"
                f"I’m prescribing Emo Screen tool – {order.form.title}.\n\n"
                "To complete your order,\n"
                "CLICK HERE\n\n"
                f"{link}\n\n"
                "For any further queries or support, please send a WhatsApp message to +91-8297634553."
            )
            return render(request, "paid/prescribe_done.html", {"order": order, "form_link": link, "wa_link": whatsapp_link(order.patient_whatsapp, msg), "message": msg, "final_amount_rupees": order.final_amount_paise / 100})
    else:
        form = PaidPrescriptionForm()

    return render(request, "paid/prescribe.html", {"doctor": doctor, "form": form})


def orders_list(request, doctor_code):
    doctor = get_object_or_404(RegisteredProfessional, unique_doctor_code=doctor_code)
    gate = _gate_google_and_email(request, doctor, request.get_full_path())
    if gate is not None:
        return gate
    orders = EsPayOrder.objects.filter(doctor=doctor).order_by("-created_at")
    return render(request, "paid/orders_list.html", {"doctor": doctor, "orders": orders})


def order_detail(request, doctor_code, order_code):
    doctor = get_object_or_404(RegisteredProfessional, unique_doctor_code=doctor_code)
    gate = _gate_google_and_email(request, doctor, request.get_full_path())
    if gate is not None:
        return gate
    order = get_object_or_404(EsPayOrder, doctor=doctor, order_code=order_code)
    return render(request, "paid/order_detail.html", {"order": order, "doctor": doctor, "final_amount_rupees": order.final_amount_paise / 100})


@require_http_methods(["GET", "POST"])
def patient_entry(request, order_code, doctor_code, form_code, final_amount_paise, token):
    order = get_object_or_404(EsPayOrder, order_code=order_code, form_id=form_code)
    payload = unsign_payload(token)
    if payload["order_code"] != order_code or payload["doctor_code"] != doctor_code:
        raise Http404("Invalid token context")
    if order.link_token_hash != hash_token(token):
        raise Http404("Token mismatch")

    if request.method == "POST":
        form = PatientEmailForm(request.POST)
        if form.is_valid():
            order.patient_email = form.cleaned_data["patient_email"]
            order.save(update_fields=["patient_email", "updated_at"])
    else:
        form = PatientEmailForm(initial={"patient_email": order.patient_email})

    if order.final_amount_paise == 0:
        return redirect("paid:patient_form", order_code=order.order_code)
    if order.status == EsPayOrder.Status.PAID:
        return redirect("paid:patient_form", order_code=order.order_code)

    return render(request, "paid/patient_entry.html", {"order": order, "email_form": form, "amount_path": final_amount_paise, "final_amount_rupees": order.final_amount_paise / 100})


@require_http_methods(["GET", "POST"])
def patient_payment(request, order_code):
    order = get_object_or_404(EsPayOrder, order_code=order_code)
    adapter = RazorpayAdapter()

    if request.method == "POST":
        gateway_order = adapter.create_order(order.order_code, order.final_amount_paise)
        tx = EsPayTransaction.objects.create(
            order=order,
            gateway="razorpay",
            gateway_order_id=gateway_order.gateway_order_id,
            status=EsPayTransaction.Status.CREATED,
            amount_paise=order.final_amount_paise,
        )
        payload = {
            "gateway_payment_id": request.POST.get("gateway_payment_id"),
            "gateway_signature": request.POST.get("gateway_signature"),
        }
        if adapter.verify_signature(payload):
            tx.status = EsPayTransaction.Status.SUCCESS
            tx.gateway_payment_id = payload["gateway_payment_id"]
            tx.gateway_signature = payload["gateway_signature"] or ""
            tx.raw_payload_json = payload
            tx.save(update_fields=["status", "gateway_payment_id", "gateway_signature", "raw_payload_json", "updated_at"])
            order.status = EsPayOrder.Status.PAID
            order.paid_at = timezone.now()
            order.save(update_fields=["status", "paid_at", "updated_at"])
            _create_revenue_split(tx)
            if order.patient_email:
                link = request.build_absolute_uri(reverse("paid:patient_form", args=[order.order_code]))
                log_email(order, "PAYMENT_LINK", order.patient_email, "EmoScreen Assessment Link", status="SENT")
            return redirect("paid:patient_form", order_code=order.order_code)

        tx.status = EsPayTransaction.Status.FAILED
        tx.raw_payload_json = payload
        tx.save(update_fields=["status", "raw_payload_json", "updated_at"])

    return render(request, "paid/patient_payment.html", {"order": order, "final_amount_rupees": order.final_amount_paise / 100})


@require_http_methods(["GET", "POST"])
def patient_form(request, order_code):
    order = get_object_or_404(EsPayOrder, order_code=order_code)
    if order.final_amount_paise > 0 and order.status != EsPayOrder.Status.PAID:
        return redirect("paid:patient_payment", order_code=order.order_code)

    submission, _ = EsSubSubmission.objects.get_or_create(
        order=order,
        defaults={
            "form": order.form,
            "config_version": order.form.version,
            "child_name": order.patient_name,
        },
    )
    if submission.status == EsSubSubmission.Status.FINAL:
        return redirect("paid:patient_thank_you", order_code=order.order_code)

    questions = list(EsCfgQuestion.objects.filter(form=order.form).select_related("option_set").order_by("global_order"))
    option_set_codes = {q.option_set_id for q in questions if q.option_set_id}
    options_by_set = {}
    for opt in EsCfgOption.objects.filter(option_set_id__in=option_set_codes).order_by("option_order"):
        options_by_set.setdefault(opt.option_set_id, []).append(opt)

    demo_form = DemographicsForm(request.POST or None, initial={
        "child_name": submission.child_name,
        "child_dob": submission.child_dob,
        "assessment_date": submission.assessment_date,
        "gender": submission.gender,
        "completed_by": submission.completed_by,
        "consent_given": submission.consent_given,
    })

    if request.method == "POST" and demo_form.is_valid():
        _save_draft(submission, demo_form.cleaned_data, request.POST, questions, options_by_set)
        return redirect("paid:patient_review", order_code=order.order_code)

    answers = {a.question_id: str(a.value_json) for a in EsSubAnswer.objects.filter(submission=submission)}
    question_rows = []
    for q in questions:
        opts = options_by_set.get(q.option_set_id, [])
        question_rows.append({"question": q, "options": opts, "selected": answers.get(q.question_code, "")})

    return render(
        request,
        "paid/patient_form.html",
        {
            "order": order,
            "submission": submission,
            "demo_form": demo_form,
            "question_rows": question_rows,
            "final_amount_rupees": order.final_amount_paise / 100,
        },
    )


def patient_review(request, order_code):
    order = get_object_or_404(EsPayOrder, order_code=order_code)
    submission = get_object_or_404(EsSubSubmission, order=order)
    questions = list(EsCfgQuestion.objects.filter(form=order.form).select_related("option_set").order_by("global_order"))
    option_set_codes = {q.option_set_id for q in questions if q.option_set_id}
    option_labels = {
        opt.option_code: opt.label
        for opt in EsCfgOption.objects.filter(option_set_id__in=option_set_codes)
    }
    answers = {a.question_id: str(a.value_json) for a in EsSubAnswer.objects.filter(submission=submission)}
    review_rows = []
    for q in questions:
        selected = answers.get(q.question_code, "")
        review_rows.append({
            "question_text": q.question_text,
            "answer_text": option_labels.get(selected, selected),
        })
    return render(request, "paid/patient_review.html", {"order": order, "submission": submission, "review_rows": review_rows})


@require_http_methods(["POST"])
def patient_submit_final(request, order_code):
    order = get_object_or_404(EsPayOrder, order_code=order_code)
    submission = get_object_or_404(EsSubSubmission, order=order)
    if submission.status == EsSubSubmission.Status.FINAL:
        return redirect("paid:patient_thank_you", order_code=order.order_code)

    compute_submission_scores(submission)
    submission.status = EsSubSubmission.Status.FINAL
    submission.save(update_fields=["status", "updated_at"])
    order.status = EsPayOrder.Status.SUBMITTED
    order.submitted_at = timezone.now()
    order.save(update_fields=["status", "submitted_at", "updated_at"])
    return redirect("paid:patient_thank_you", order_code=order.order_code)


def patient_thank_you(request, order_code):
    order = get_object_or_404(EsPayOrder, order_code=order_code)
    return render(request, "paid/patient_thank_you.html", {"order": order})


def _save_draft(submission, demo_data, posted_data, questions, options_by_set):
    submission.child_name = demo_data["child_name"]
    submission.child_dob = demo_data["child_dob"]
    submission.assessment_date = demo_data["assessment_date"]
    submission.gender = demo_data["gender"]
    submission.completed_by = demo_data["completed_by"]
    submission.consent_given = demo_data["consent_given"]
    submission.status = EsSubSubmission.Status.DRAFT
    submission.save()

    for q in questions:
        key = f"q_{q.question_code}"
        raw_val = posted_data.get(key)
        if raw_val is None:
            continue

        score_val = None
        if q.option_set_id:
            option_lookup = {opt.option_code: opt for opt in options_by_set.get(q.option_set_id, [])}
            selected_option = option_lookup.get(raw_val)
            if q.is_scored and selected_option and selected_option.score_value is not None:
                score_val = Decimal(str(selected_option.score_value))
        elif q.is_scored and raw_val not in ("", None):
            score_val = Decimal(str(raw_val))

        EsSubAnswer.objects.update_or_create(
            submission=submission,
            question=q,
            defaults={"value_json": raw_val, "score_value": score_val},
        )


def _create_revenue_split(transaction):
    half = int(transaction.amount_paise / 2)
    EsPayRevenueSplit.objects.create(
        transaction=transaction,
        party=EsPayRevenueSplit.Party.INDITECH,
        percent=50,
        amount_paise=half,
    )
    EsPayRevenueSplit.objects.create(
        transaction=transaction,
        party=EsPayRevenueSplit.Party.EQUIPOISE,
        percent=50,
        amount_paise=transaction.amount_paise - half,
    )
