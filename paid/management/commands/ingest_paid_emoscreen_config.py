from pathlib import Path
import json
import math
from decimal import Decimal, InvalidOperation

import pandas as pd
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.utils import OperationalError, IntegrityError
from django.core.exceptions import ValidationError

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
        for index, row in enumerate(records, start=2):
            normalized = self._normalize_row(model_cls, row)
            key = normalized.get(key_field)
            if not key:
                continue
            try:
                model_cls.objects.update_or_create(**{key_field: key}, defaults=normalized)
            except ValidationError as exc:
                raise CommandError(f"Validation failed in {model_cls.__name__} row {index}: {exc}") from exc
            except OperationalError as exc:
                if "Invalid JSON text" not in str(exc):
                    raise
                repaired = self._drop_invalid_json_fields(model_cls, normalized)
                self.stderr.write(
                    f"Retrying {model_cls.__name__} row {index} with JSON fields nulled after DB JSON error."
                )
                model_cls.objects.update_or_create(**{key_field: key}, defaults=repaired)
            except IntegrityError as exc:
                if "cannot be null" not in str(exc).lower():
                    raise
                repaired = self._fill_required_non_nullable_fields(model_cls, normalized)
                self.stderr.write(
                    f"Retrying {model_cls.__name__} row {index} with required non-null fields backfilled."
                )
                model_cls.objects.update_or_create(**{key_field: key}, defaults=repaired)

    def _bulk_insert(self, model_cls, records):
        for index, row in enumerate(records, start=2):
            normalized = self._normalize_row(model_cls, row)
            try:
                model_cls.objects.create(**normalized)
            except ValidationError as exc:
                raise CommandError(f"Validation failed in {model_cls.__name__} row {index}: {exc}") from exc
            except OperationalError as exc:
                if "Invalid JSON text" not in str(exc):
                    raise
                repaired = self._drop_invalid_json_fields(model_cls, normalized)
                self.stderr.write(
                    f"Retrying {model_cls.__name__} row {index} with JSON fields nulled after DB JSON error."
                )
                model_cls.objects.create(**repaired)
            except IntegrityError as exc:
                if "cannot be null" not in str(exc).lower():
                    raise
                repaired = self._fill_required_non_nullable_fields(model_cls, normalized)
                self.stderr.write(
                    f"Retrying {model_cls.__name__} row {index} with required non-null fields backfilled."
                )
                model_cls.objects.create(**repaired)

    def _normalize_row(self, model_cls, row):
        """
        Map workbook column names to Django model field names.
        Notably, FK workbook columns use DB column names like `form_code`,
        while Django model kwargs must use `form_id` (the FK attname).
        """
        normalized = {}
        direct_fields = {f.name for f in model_cls._meta.get_fields() if hasattr(f, "attname")}
        field_by_attname = {f.attname: f for f in model_cls._meta.fields}
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

            field = field_by_attname.get(target_key)
            if target_key in json_fields:
                value = self._coerce_json_value(value)
            else:
                value = self._coerce_non_json_value(field, value)

            value = self._coerce_nullability(field, value)
            normalized[target_key] = value

        return normalized

    def _coerce_nullability(self, field, value):
        if field is None:
            return value

        if value is not None:
            return value

        # Prefer explicit model defaults for non-null fields.
        if not field.null and field.has_default():
            default = field.get_default()
            return default() if callable(default) else default

        internal_type = field.get_internal_type()

        # Avoid sending NULL to non-null textual columns.
        if not field.null and internal_type in {"CharField", "TextField", "EmailField"}:
            return ""

        if not field.null and internal_type in {"IntegerField", "PositiveIntegerField", "BigIntegerField", "SmallIntegerField", "PositiveSmallIntegerField"}:
            return 0

        if not field.null and internal_type == "DecimalField":
            return Decimal("0")

        if not field.null and internal_type == "BooleanField":
            return False

        return value

    def _fill_required_non_nullable_fields(self, model_cls, normalized):
        repaired = dict(normalized)
        for field in model_cls._meta.fields:
            name = field.attname
            if field.primary_key:
                continue
            repaired[name] = self._coerce_nullability(field, repaired.get(name))
        return repaired

    def _coerce_non_json_value(self, field, value):
        if value is None or pd.isna(value):
            return None

        if isinstance(value, str):
            raw = value.strip()
            lowered = raw.lower()
            if lowered in {"nan", "na", "n/a", "none", "null", "-", "#n/a", "#value!", "#div/0!"}:
                return None

            if field is not None and field.get_internal_type() == "BooleanField":
                if lowered in {"true", "1", "yes", "y", "t"}:
                    return True
                if lowered in {"false", "0", "no", "n", "f"}:
                    return False
                # Some sheets use semantic markers (e.g., "MISMATCH") in bool columns.
                return bool(raw)

            if field is not None and field.get_internal_type() == "DecimalField":
                try:
                    return Decimal(raw)
                except (InvalidOperation, ValueError):
                    return None
            return value

        if field is not None and field.get_internal_type() == "BooleanField":
            if isinstance(value, (int, float)):
                if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
                    return None
                return bool(int(value))

        if field is not None and field.get_internal_type() == "DecimalField":
            if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
                return None
            try:
                return Decimal(str(value))
            except (InvalidOperation, ValueError):
                return None

        return value

    def _drop_invalid_json_fields(self, model_cls, normalized):
        json_field_names = {
            f.attname
            for f in model_cls._meta.fields
            if f.get_internal_type() == "JSONField"
        }
        repaired = dict(normalized)
        for field_name in json_field_names:
            if field_name in repaired:
                repaired[field_name] = None
        return repaired

    def _coerce_json_value(self, value):
        if value is None or pd.isna(value):
            return None

        # Keep valid Python JSON structures.
        if isinstance(value, (dict, list, bool, int)):
            return value

        if isinstance(value, float):
            if math.isnan(value) or math.isinf(value):
                return None
            return value

        if isinstance(value, str):
            raw = value.strip()
            if not raw or raw.lower() in {
                "none", "null", "nan", "na", "n/a", "-", "#n/a", "#value!", "#div/0!"
            }:
                return None
            if raw.lower() == "true":
                return True
            if raw.lower() == "false":
                return False
            try:
                parsed = json.loads(raw)
                # Prevent non-standard numeric values from leaking into MySQL JSON columns.
                if isinstance(parsed, float) and (math.isnan(parsed) or math.isinf(parsed)):
                    return None
                return parsed
            except json.JSONDecodeError:
                # Invalid JSON strings must not be written to MySQL JSON columns.
                return None

        return None
