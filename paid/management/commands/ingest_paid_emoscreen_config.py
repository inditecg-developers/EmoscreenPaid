from pathlib import Path
import json

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
            normalized = self._normalize_row(model_cls, row)
            key = normalized.get(key_field)
            if not key:
                continue
            model_cls.objects.update_or_create(**{key_field: key}, defaults=normalized)

    def _bulk_insert(self, model_cls, records):
        objs = [model_cls(**self._normalize_row(model_cls, row)) for row in records]
        if objs:
            model_cls.objects.bulk_create(objs)

    def _normalize_row(self, model_cls, row):
        """
        Map workbook column names to Django model field names.
        Notably, FK workbook columns use DB column names like `form_code`,
        while Django model kwargs must use `form_id` (the FK attname).
        """
        normalized = {}
        direct_fields = {f.name for f in model_cls._meta.get_fields() if hasattr(f, "attname")}
        db_column_to_attname = {
            f.db_column: f.attname
            for f in model_cls._meta.fields
            if getattr(f, "db_column", None)
        }
        json_fields = {
            f.attname
            for f in model_cls._meta.fields
            if f.get_internal_type() == "JSONField"
        }

        for key, value in row.items():
            target_key = None
            if key in direct_fields:
                target_key = key
            elif key in db_column_to_attname:
                target_key = db_column_to_attname[key]

            if not target_key:
                continue

            if target_key in json_fields:
                value = self._coerce_json_value(value)

            normalized[target_key] = value

        return normalized

    def _coerce_json_value(self, value):
        if value is None:
            return None
        if isinstance(value, (dict, list, int, float, bool)):
            return value
        if isinstance(value, str):
            raw = value.strip()
            if not raw or raw.lower() in {"none", "null", "nan", "na", "n/a", "-"}:
                return None
            if raw.lower() == "true":
                return True
            if raw.lower() == "false":
                return False
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                # Invalid JSON strings must not be written to MySQL JSON columns.
                return None
        return None
