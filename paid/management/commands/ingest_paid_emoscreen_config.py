from pathlib import Path

import pandas as pd
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from paid import models


SHEETS = {
    "forms": (models.EsCfgForm, "form_code"),
    "sections": (models.EsCfgSection, "section_code"),
    "option_sets": (models.EsCfgOptionSet, "option_set_code"),
    "options": (models.EsCfgOption, "option_code"),
    "questions": (models.EsCfgQuestion, "question_code"),
    "scales": (models.EsCfgScale, "scale_code"),
    "scale_items": (models.EsCfgScaleItem, None),
    "thresholds": (models.EsCfgThreshold, "threshold_code"),
    "derived_lists": (models.EsCfgDerivedList, "list_code"),
    "evaluation_rules": (models.EsCfgEvaluationRule, "rule_code"),
    "report_templates": (models.EsCfgReportTemplate, "template_code"),
    "report_blocks": (models.EsCfgReportBlock, "block_code"),
    "report_block_sections": (models.EsCfgReportBlockSection, None),
    "report_block_scales": (models.EsCfgReportBlockScale, None),
}


class Command(BaseCommand):
    help = "Ingest paid EmoScreen workbook into es_cfg_* tables"

    def add_arguments(self, parser):
        parser.add_argument("xlsx_path", type=str)

    @transaction.atomic
    def handle(self, *args, **options):
        xlsx_path = Path(options["xlsx_path"])
        if not xlsx_path.exists():
            raise CommandError(f"Workbook not found: {xlsx_path}")

        workbook = pd.ExcelFile(xlsx_path)
        missing = [sheet for sheet in SHEETS if sheet not in workbook.sheet_names]
        if missing:
            raise CommandError(f"Missing required sheets: {', '.join(missing)}")

        for sheet_name, (model_cls, key_field) in SHEETS.items():
            df = pd.read_excel(workbook, sheet_name=sheet_name)
            records = df.where(pd.notnull(df), None).to_dict(orient="records")
            self.stdout.write(f"Ingesting {sheet_name}: {len(records)} rows")
            if key_field:
                self._upsert_records(model_cls, key_field, records)
            else:
                model_cls.objects.all().delete()
                self._bulk_insert(model_cls, records)

        self.stdout.write(self.style.SUCCESS("Paid EmoScreen config ingestion complete."))

    def _upsert_records(self, model_cls, key_field, records):
        for row in records:
            key = row.get(key_field)
            if not key:
                continue
            model_cls.objects.update_or_create(**{key_field: key}, defaults=row)

    def _bulk_insert(self, model_cls, records):
        objs = [model_cls(**row) for row in records]
        if objs:
            model_cls.objects.bulk_create(objs)
