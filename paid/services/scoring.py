from decimal import Decimal

from paid.models import EsCfgScale, EsCfgScaleItem, EsSubScaleScore


def compute_submission_scores(submission):
    answers = {a.question_id: Decimal(str(a.score_value or 0)) for a in submission.essubanswer_set.select_related("question")}
    total_score = sum(answers.values(), Decimal("0"))
    scales = EsCfgScale.objects.filter(form=submission.form)
    EsSubScaleScore.objects.filter(submission=submission).delete()

    flagged_count = 0
    for scale in scales:
        items = EsCfgScaleItem.objects.filter(scale=scale).select_related("question")
        scale_score = Decimal("0")
        max_score = Decimal(str(scale.max_score_override or scale.max_score_computed or 0))
        for item in items:
            scale_score += Decimal(str(item.weight)) * answers.get(item.question_id, Decimal("0"))
        risk_factor = (scale_score / max_score) if max_score else Decimal("0")
        included = risk_factor >= Decimal("0.5")
        if included:
            flagged_count += 1
        EsSubScaleScore.objects.create(
            submission=submission,
            scale=scale,
            score=scale_score,
            max_score=max_score,
            risk_factor=risk_factor,
            risk_percent=risk_factor * Decimal("100"),
            included_in_doctor_table=included,
        )

    submission.total_score = total_score
    submission.total_score_max_display = submission.form.total_score_max_php
    submission.has_concerns = flagged_count > 0
    submission.computed_json = {
        "total_score": str(total_score),
        "flagged_scales": flagged_count,
    }
    submission.save(update_fields=["total_score", "total_score_max_display", "has_concerns", "computed_json", "updated_at"])
