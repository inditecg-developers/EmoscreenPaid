from django.db import models

from content.models import RegisteredProfessional


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class EsCfgForm(TimestampedModel):
    form_code = models.CharField(primary_key=True, max_length=50)
    title = models.CharField(max_length=255)
    age_min_months = models.PositiveIntegerField()
    age_max_months = models.PositiveIntegerField()
    language = models.CharField(max_length=8, default="en")
    version = models.CharField(max_length=64)
    is_active = models.BooleanField(default=True)
    symptom_question_count = models.PositiveIntegerField(default=0)
    question_field_count = models.PositiveIntegerField(default=0)
    total_score_max_php = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    total_score_max_computed = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "es_cfg_forms"


class EsCfgSection(TimestampedModel):
    section_code = models.CharField(primary_key=True, max_length=64)
    form = models.ForeignKey(EsCfgForm, on_delete=models.CASCADE, db_column="form_code")
    section_key = models.CharField(max_length=64)
    title = models.CharField(max_length=255)
    instructions_html = models.TextField(blank=True)
    display_order = models.IntegerField(default=0)
    display_if_jsonlogic = models.JSONField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "es_cfg_sections"


class EsCfgOptionSet(TimestampedModel):
    option_set_code = models.CharField(primary_key=True, max_length=64)
    name = models.CharField(max_length=255)
    widget = models.CharField(max_length=32)
    is_multi = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "es_cfg_option_sets"


class EsCfgOption(TimestampedModel):
    option_code = models.CharField(primary_key=True, max_length=64)
    option_set = models.ForeignKey(EsCfgOptionSet, on_delete=models.CASCADE, db_column="option_set_code")
    option_order = models.IntegerField(default=0)
    value = models.CharField(max_length=128)
    label = models.CharField(max_length=255)
    score_value = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "es_cfg_options"


class EsCfgQuestion(TimestampedModel):
    question_code = models.CharField(primary_key=True, max_length=64)
    form = models.ForeignKey(EsCfgForm, on_delete=models.CASCADE, db_column="form_code")
    section = models.ForeignKey(EsCfgSection, on_delete=models.CASCADE, db_column="section_code")
    question_key = models.CharField(max_length=64)
    question_order = models.IntegerField(default=0)
    global_order = models.IntegerField(default=0)
    legacy_field_name = models.CharField(max_length=128, blank=True)
    question_text = models.TextField()
    question_type = models.CharField(max_length=32)
    option_set = models.ForeignKey(
        EsCfgOptionSet,
        on_delete=models.SET_NULL,
        db_column="option_set_code",
        null=True,
        blank=True,
    )
    is_required = models.BooleanField(default=False)
    response_data_type = models.CharField(max_length=32, default="text")
    is_scored = models.BooleanField(default=False)
    store_target = models.CharField(max_length=64, blank=True)
    validation_json = models.JSONField(null=True, blank=True)
    display_if_jsonlogic = models.JSONField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "es_cfg_questions"


class EsCfgScale(TimestampedModel):
    scale_code = models.CharField(primary_key=True, max_length=64)
    form = models.ForeignKey(EsCfgForm, on_delete=models.CASCADE, db_column="form_code")
    scale_key = models.CharField(max_length=64)
    label = models.CharField(max_length=255)
    calculation = models.CharField(max_length=32, default="SUM")
    max_score_override = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    group = models.CharField(max_length=64, blank=True)
    notes = models.TextField(blank=True)
    max_score_computed = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    max_mismatch = models.BooleanField(default=False)
    max_mismatch_note = models.TextField(blank=True)

    class Meta:
        db_table = "es_cfg_scales"


class EsCfgScaleItem(TimestampedModel):
    scale = models.ForeignKey(EsCfgScale, on_delete=models.CASCADE, db_column="scale_code")
    question = models.ForeignKey(EsCfgQuestion, on_delete=models.CASCADE, db_column="question_code")
    weight = models.DecimalField(max_digits=8, decimal_places=2, default=1)
    item_order = models.IntegerField(default=0)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "es_cfg_scale_items"
        unique_together = (("scale", "question"),)


class EsCfgThreshold(TimestampedModel):
    threshold_code = models.CharField(primary_key=True, max_length=64)
    scale = models.ForeignKey(EsCfgScale, on_delete=models.CASCADE, db_column="scale_code")
    basis = models.CharField(max_length=32)
    comparator = models.CharField(max_length=8)
    threshold_value = models.DecimalField(max_digits=8, decimal_places=3)
    risk_level = models.CharField(max_length=64)
    include_in_risk_table = models.BooleanField(default=True)
    include_in_patient_summary = models.BooleanField(default=False)
    priority = models.IntegerField(default=0)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "es_cfg_thresholds"


class EsCfgDerivedList(TimestampedModel):
    list_code = models.CharField(primary_key=True, max_length=64)
    form = models.ForeignKey(EsCfgForm, on_delete=models.CASCADE, db_column="form_code")
    name = models.CharField(max_length=128)
    section = models.ForeignKey(
        EsCfgSection,
        on_delete=models.SET_NULL,
        db_column="section_code",
        null=True,
        blank=True,
    )
    filter_response_value = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "es_cfg_derived_lists"


class EsCfgEvaluationRule(TimestampedModel):
    rule_code = models.CharField(primary_key=True, max_length=64)
    form = models.ForeignKey(EsCfgForm, on_delete=models.CASCADE, db_column="form_code")
    output_key = models.CharField(max_length=64)
    expression_jsonlogic = models.JSONField()
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "es_cfg_evaluation_rules"


class EsCfgReportTemplate(TimestampedModel):
    template_code = models.CharField(primary_key=True, max_length=64)
    form = models.ForeignKey(EsCfgForm, on_delete=models.CASCADE, db_column="form_code")
    report_type = models.CharField(max_length=32)
    title = models.CharField(max_length=255)
    output_format = models.CharField(max_length=16, default="pdf")
    header_logo_path = models.CharField(max_length=255, blank=True)
    footer_company = models.CharField(max_length=255, blank=True)
    footer_tagline = models.CharField(max_length=255, blank=True)
    footer_phone = models.CharField(max_length=64, blank=True)
    footer_email = models.CharField(max_length=255, blank=True)
    disclaimer_html = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "es_cfg_report_templates"


class EsCfgReportBlock(TimestampedModel):
    block_code = models.CharField(primary_key=True, max_length=64)
    template = models.ForeignKey(EsCfgReportTemplate, on_delete=models.CASCADE, db_column="template_code")
    block_order = models.IntegerField(default=0)
    block_type = models.CharField(max_length=64)
    title = models.CharField(max_length=255, blank=True)
    text_template_html = models.TextField(blank=True)
    include_if_jsonlogic = models.JSONField(null=True, blank=True)
    params_json = models.JSONField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "es_cfg_report_blocks"


class EsCfgReportBlockSection(TimestampedModel):
    block = models.ForeignKey(EsCfgReportBlock, on_delete=models.CASCADE, db_column="block_code")
    section = models.ForeignKey(EsCfgSection, on_delete=models.CASCADE, db_column="section_code")
    order = models.IntegerField(default=0)

    class Meta:
        db_table = "es_cfg_report_block_sections"
        unique_together = (("block", "section"),)


class EsCfgReportBlockScale(TimestampedModel):
    block = models.ForeignKey(EsCfgReportBlock, on_delete=models.CASCADE, db_column="block_code")
    scale = models.ForeignKey(EsCfgScale, on_delete=models.CASCADE, db_column="scale_code")
    order = models.IntegerField(default=0)

    class Meta:
        db_table = "es_cfg_report_block_scales"
        unique_together = (("block", "scale"),)


class EsPayOrder(TimestampedModel):
    class Status(models.TextChoices):
        CREATED = "CREATED"
        LINK_SENT = "LINK_SENT"
        PAYMENT_PENDING = "PAYMENT_PENDING"
        PAYMENT_SKIPPED = "PAYMENT_SKIPPED"
        PAID = "PAID"
        IN_PROGRESS = "IN_PROGRESS"
        SUBMITTED = "SUBMITTED"
        EXPIRED = "EXPIRED"
        CANCELLED = "CANCELLED"

    order_code = models.CharField(max_length=32, unique=True)
    doctor = models.ForeignKey(RegisteredProfessional, on_delete=models.RESTRICT)
    form = models.ForeignKey(EsCfgForm, on_delete=models.RESTRICT, db_column="form_code")
    price_variant = models.CharField(max_length=32)
    base_amount_paise = models.PositiveIntegerField(default=0)
    discount_paise = models.PositiveIntegerField(default=0)
    final_amount_paise = models.PositiveIntegerField(default=0)
    patient_name = models.CharField(max_length=255)
    patient_whatsapp = models.CharField(max_length=32)
    patient_email = models.EmailField(blank=True, null=True)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.CREATED)
    link_token_hash = models.CharField(max_length=128)
    link_expires_at = models.DateTimeField()
    paid_at = models.DateTimeField(blank=True, null=True)
    submitted_at = models.DateTimeField(blank=True, null=True)
    created_ip = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.TextField(blank=True)

    class Meta:
        db_table = "es_pay_orders"


class EsPayTransaction(TimestampedModel):
    class Status(models.TextChoices):
        CREATED = "CREATED"
        SUCCESS = "SUCCESS"
        FAILED = "FAILED"
        REFUNDED = "REFUNDED"

    order = models.ForeignKey(EsPayOrder, on_delete=models.CASCADE)
    gateway = models.CharField(max_length=32, default="razorpay")
    gateway_order_id = models.CharField(max_length=128, blank=True)
    gateway_payment_id = models.CharField(max_length=128, blank=True)
    gateway_signature = models.CharField(max_length=256, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.CREATED)
    amount_paise = models.PositiveIntegerField(default=0)
    currency = models.CharField(max_length=3, default="INR")
    raw_payload_json = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = "es_pay_transactions"


class EsPayRevenueSplit(models.Model):
    class Party(models.TextChoices):
        INDITECH = "INDITECH"
        EQUIPOISE = "EQUIPOISE"

    transaction = models.ForeignKey(EsPayTransaction, on_delete=models.CASCADE)
    party = models.CharField(max_length=16, choices=Party.choices)
    percent = models.DecimalField(max_digits=5, decimal_places=2)
    amount_paise = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "es_pay_revenue_splits"


class EsPayEmailLog(models.Model):
    class EmailType(models.TextChoices):
        PAYMENT_LINK = "PAYMENT_LINK"
        PATIENT_REPORT = "PATIENT_REPORT"
        DOCTOR_REPORT = "DOCTOR_REPORT"

    class Status(models.TextChoices):
        QUEUED = "QUEUED"
        SENT = "SENT"
        FAILED = "FAILED"

    order = models.ForeignKey(EsPayOrder, on_delete=models.SET_NULL, null=True, blank=True)
    email_type = models.CharField(max_length=32, choices=EmailType.choices)
    to_email = models.EmailField()
    subject = models.CharField(max_length=255)
    sendgrid_message_id = models.CharField(max_length=128, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED)
    error_text = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "es_pay_email_logs"


class EsSubSubmission(TimestampedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT"
        FINAL = "FINAL"

    order = models.OneToOneField(EsPayOrder, on_delete=models.CASCADE)
    form = models.ForeignKey(EsCfgForm, on_delete=models.RESTRICT, db_column="form_code")
    config_version = models.CharField(max_length=64)
    child_name = models.CharField(max_length=255)
    child_dob = models.DateField(null=True, blank=True)
    assessment_date = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=16, blank=True)
    completed_by = models.CharField(max_length=255, blank=True)
    consent_given = models.BooleanField(default=False)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    total_score = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    total_score_max_display = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    has_concerns = models.BooleanField(default=False)
    computed_json = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = "es_sub_submissions"


class EsSubAnswer(models.Model):
    submission = models.ForeignKey(EsSubSubmission, on_delete=models.CASCADE)
    question = models.ForeignKey(EsCfgQuestion, on_delete=models.RESTRICT, db_column="question_code")
    value_json = models.JSONField()
    score_value = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "es_sub_answers"
        unique_together = (("submission", "question"),)


class EsSubScaleScore(models.Model):
    submission = models.ForeignKey(EsSubSubmission, on_delete=models.CASCADE)
    scale = models.ForeignKey(EsCfgScale, on_delete=models.RESTRICT, db_column="scale_code")
    score = models.DecimalField(max_digits=8, decimal_places=2)
    max_score = models.DecimalField(max_digits=8, decimal_places=2)
    risk_factor = models.DecimalField(max_digits=8, decimal_places=4)
    risk_percent = models.DecimalField(max_digits=8, decimal_places=2)
    included_in_doctor_table = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "es_sub_scale_scores"
        unique_together = (("submission", "scale"),)


class EsRepReport(models.Model):
    submission = models.OneToOneField(EsSubSubmission, on_delete=models.CASCADE)
    patient_pdf_path = models.CharField(max_length=500)
    doctor_pdf_path = models.CharField(max_length=500)
    patient_pdf_password_hint = models.CharField(max_length=255, blank=True)
    doctor_pdf_password_hint = models.CharField(max_length=255, blank=True)
    generated_at = models.DateTimeField(auto_now_add=True)
    emailed_to_parent_at = models.DateTimeField(null=True, blank=True)
    emailed_to_doctor_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "es_rep_reports"
