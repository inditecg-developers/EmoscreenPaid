import io
import re
import requests
from typing import Dict, List, Tuple, Set, Optional
import pandas as pd
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from datetime import datetime

REQUIRED_SHEETS = {
    "languages": ["lang_code", "lang_name_english", "lang_name_native"],
    "questions": ["question_code", "display_order", "active"],
    "questions_i18n": ["question_code", "lang_code", "question_text"],
    "options": ["option_code", "question_code", "display_order", "triggers_red_flag", "red_flag_code"],
    "options_i18n": ["option_code", "lang_code", "option_text"],
    "red_flags": ["red_flag_code", "education_url_slug"],
    "red_flags_i18n": ["red_flag_code", "lang_code", "parent_label"],
    "doctor_education": ["red_flag_code", "lang_code", "education_markdown", "reference_1", "reference_2"],
    "result_messages": ["message_code", "lang_code", "message_text"],
    "ui_strings": ["key", "lang_code", "text"],
}

# Which columns to strip/normalize per sheet
CODE_COLUMNS = {
    "languages": ["lang_code"],
    "questions": ["question_code"],
    "questions_i18n": ["question_code", "lang_code"],
    "options": ["option_code", "question_code", "red_flag_code"],
    "options_i18n": ["option_code", "lang_code"],
    "red_flags": ["red_flag_code"],
    "red_flags_i18n": ["red_flag_code", "lang_code"],
    "doctor_education": ["red_flag_code", "lang_code"],
    "result_messages": ["message_code", "lang_code"],
    "ui_strings": ["key", "lang_code"],
}

def _export_url(share_url: str) -> str:
    m = re.search(r"/d/([a-zA-Z0-9-_]+)", share_url)
    if not m:
        raise ValueError("Could not parse Google Sheet ID from URL.")
    gid = m.group(1)
    return f"https://docs.google.com/spreadsheets/d/{gid}/export?format=xlsx"

def _load_workbook(sheet_url: str = None, xlsx_path: str = None) -> Dict[str, pd.DataFrame]:
    if not (sheet_url or xlsx_path):
        raise ValueError("Provide either --sheet-url or --xlsx")
    if sheet_url:
        url = _export_url(sheet_url)
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        bio = io.BytesIO(r.content)
        xls = pd.ExcelFile(bio)
    else:
        xls = pd.ExcelFile(xlsx_path)
    frames: Dict[str, pd.DataFrame] = {}
    for name in xls.sheet_names:
        frames[name] = pd.read_excel(xls, sheet_name=name).replace({pd.NA: None})
    return frames

def _normalize_doctor_education_columns(frames: Dict[str, pd.DataFrame]):
    """
    Map your current column names to the expected ones:
    - at_a_glance_information -> education_markdown
    - reference -> reference_1
    Ensure reference_2 exists.
    """
    if "doctor_education" not in frames:
        return
    df = frames["doctor_education"].copy()
    if "at_a_glance_information" in df.columns and "education_markdown" not in df.columns:
        df = df.rename(columns={"at_a_glance_information": "education_markdown"})
    if "reference" in df.columns and "reference_1" not in df.columns:
        df = df.rename(columns={"reference": "reference_1"})
    if "reference_2" not in df.columns:
        df["reference_2"] = ""
    frames["doctor_education"] = df

def _normalize_result_messages_columns(frames: Dict[str, pd.DataFrame]):
    """
    Some workbooks use pluralized column names:
      - messages_code  -> message_code
      - messages_text  -> message_text
    Normalize them so REQUIRED_SHEETS + ingest logic work unchanged.
    """
    if "result_messages" not in frames:
        return
    df = frames["result_messages"].copy()
    if "messages_code" in df.columns and "message_code" not in df.columns:
        df = df.rename(columns={"messages_code": "message_code"})
    if "messages_text" in df.columns and "message_text" not in df.columns:
        df = df.rename(columns={"messages_text": "message_text"})
    frames["result_messages"] = df

def _strip_val(v):
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None

def _normalize_codes(frames: Dict[str, pd.DataFrame]):
    """
    Strip whitespace from all code columns. lang_code -> lowercase.
    Drop rows that are missing required key fields.
    """
    for sheet, cols in CODE_COLUMNS.items():
        if sheet not in frames:
            continue
        df = frames[sheet].copy()
        for c in cols:
            if c not in df.columns:
                continue
            if c == "lang_code":
                df[c] = df[c].apply(lambda x: _strip_val(x.lower() if isinstance(x, str) else x))
            else:
                df[c] = df[c].apply(_strip_val)
        # Drop rows with missing key fields
        if sheet == "languages":
            df = df[df["lang_code"].notna()]
        elif sheet == "questions":
            df = df[df["question_code"].notna()]
        elif sheet == "questions_i18n":
            df = df[df["question_code"].notna() & df["lang_code"].notna()]
        elif sheet == "options":
            df = df[df["option_code"].notna() & df["question_code"].notna()]
        elif sheet == "options_i18n":
            df = df[df["option_code"].notna() & df["lang_code"].notna()]
        elif sheet == "red_flags":
            df = df[df["red_flag_code"].notna()]
        elif sheet == "red_flags_i18n":
            df = df[df["red_flag_code"].notna() & df["lang_code"].notna()]
        elif sheet == "doctor_education":
            df = df[df["red_flag_code"].notna() & df["lang_code"].notna()]
        elif sheet == "result_messages":
            df = df[df["message_code"].notna() & df["lang_code"].notna()]
        elif sheet == "ui_strings":
            df = df[df["key"].notna() & df["lang_code"].notna()]
        frames[sheet] = df

def _require_columns(df: pd.DataFrame, required: List[str], sheet_name: str):
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise CommandError(f"Sheet '{sheet_name}' is missing columns: {missing}. Present: {list(df.columns)}")

def _boolify(val):
    if isinstance(val, bool):
        return val
    if val is None:
        return False
    s = str(val).strip().lower()
    return s in ("true", "1", "yes", "y", "हां", "हाँ", "haan")

def _set_of(df: pd.DataFrame, col: str) -> Set[str]:
    return set([str(x) for x in df[col].dropna().unique()])

def _validate_foreign_keys(frames: Dict[str, pd.DataFrame]):
    """
    Pre-validate cross-sheet references to fail early with a clear message.
    """
    errors = []

    langs = _set_of(frames.get("languages", pd.DataFrame(columns=["lang_code"])), "lang_code") if "languages" in frames else set()
    qcodes = _set_of(frames.get("questions", pd.DataFrame(columns=["question_code"])), "question_code") if "questions" in frames else set()
    rfcodes = _set_of(frames.get("red_flags", pd.DataFrame(columns=["red_flag_code"])), "red_flag_code") if "red_flags" in frames else set()

    if "options" in frames:
        opt = frames["options"]
        missing_q = _set_of(opt, "question_code") - qcodes
        if missing_q:
            errors.append(f"options.question_code not found in questions: {sorted(list(missing_q))[:10]} ...")
        miss_rf = set([str(x) for x in opt["red_flag_code"].dropna().unique() if str(x)]) - rfcodes
        if miss_rf:
            errors.append(f"options.red_flag_code not found in red_flags: {sorted(list(miss_rf))[:10]} ...")

    if "options_i18n" in frames:
        oi = frames["options_i18n"]
        if "options" in frames:
            opc = _set_of(frames["options"], "option_code")
            miss_opt = _set_of(oi, "option_code") - opc
            if miss_opt:
                errors.append(f"options_i18n.option_code not found in options: {sorted(list(miss_opt))[:10]} ...")
        miss_lang = _set_of(oi, "lang_code") - langs
        if miss_lang:
            errors.append(f"options_i18n.lang_code not found in languages: {sorted(list(miss_lang))[:10]} ...")

    if "questions_i18n" in frames:
        qi = frames["questions_i18n"]
        miss_q = _set_of(qi, "question_code") - qcodes
        if miss_q:
            errors.append(f"questions_i18n.question_code not found in questions: {sorted(list(miss_q))[:10]} ...")
        miss_lang = _set_of(qi, "lang_code") - langs
        if miss_lang:
            errors.append(f"questions_i18n.lang_code not found in languages: {sorted(list(miss_lang))[:10]} ...")

    if "red_flags_i18n" in frames:
        rfi = frames["red_flags_i18n"]
        miss_rf = _set_of(rfi, "red_flag_code") - rfcodes
        if miss_rf:
            errors.append(f"red_flags_i18n.red_flag_code not found in red_flags: {sorted(list(miss_rf))[:10]} ...")
        miss_lang = _set_of(rfi, "lang_code") - langs
        if miss_lang:
            errors.append(f"red_flags_i18n.lang_code not found in languages: {sorted(list(miss_lang))[:10]} ...")

    if "doctor_education" in frames:
        de = frames["doctor_education"]
        miss_rf = _set_of(de, "red_flag_code") - rfcodes
        if miss_rf:
            errors.append(f"doctor_education.red_flag_code not found in red_flags: {sorted(list(miss_rf))[:10]} ...")
        miss_lang = _set_of(de, "lang_code") - langs
        if miss_lang:
            errors.append(f"doctor_education.lang_code not found in languages: {sorted(list(miss_lang))[:10]} ...")

    if errors:
        msg = "Validation failed before ingest:\n- " + "\n- ".join(errors)
        raise CommandError(msg)

def upsert(
    cursor,
    table: str,
    cols: List[str],
    rows: List[Tuple],
    unique_cols: List[str],
    update_cols_override: Optional[List[str]] = None,
):
    if not rows:
        return

    def q(name: str) -> str:
        # quote identifiers with backticks and escape any backticks inside the name
        return "`" + name.replace("`", "``") + "`"

    placeholders = ", ".join(["%s"] * len(cols))
    insert = f"INSERT INTO {q(table)} ({', '.join(q(c) for c in cols)}) VALUES ({placeholders})"

    if update_cols_override is None:
        update_cols = [c for c in cols if c not in unique_cols]
    else:
        update_cols = update_cols_override

    if not update_cols:
        sql = insert + " ON DUPLICATE KEY UPDATE " + ", ".join(f"{q(c)}={q(c)}" for c in unique_cols)
    else:
        sql = insert + " ON DUPLICATE KEY UPDATE " + ", ".join(f"{q(c)}=VALUES({q(c)})" for c in update_cols)

    cursor.executemany(sql, rows)


class Command(BaseCommand):
    help = "Ingest Emoscreen content workbook (Google Sheet or .xlsx) into MySQL."

    def add_arguments(self, parser):
        parser.add_argument("--sheet-url", type=str, help="Google Sheets share URL")
        parser.add_argument("--xlsx", type=str, help=".xlsx file path")

    @transaction.atomic
    def handle(self, *args, **opts):
        frames = _load_workbook(sheet_url=opts.get("sheet_url"), xlsx_path=opts.get("xlsx"))

        # Map doctor_education alt columns, then normalize codes
        _normalize_doctor_education_columns(frames)
        _normalize_result_messages_columns(frames)
        _normalize_codes(frames)

        # Validate required cols exist
        for sheet, cols in REQUIRED_SHEETS.items():
            if sheet not in frames:
                raise CommandError(f"Workbook missing required sheet: {sheet}")
            _require_columns(frames[sheet], cols, sheet)

        # Pre-validate FKs (lists any missing codes)
        _validate_foreign_keys(frames)

        with connection.cursor() as cur:
            # languages
            df = frames["languages"].fillna("")
            rows = [tuple(df[c].iloc[i] for c in REQUIRED_SHEETS["languages"]) for i in range(len(df))]
            self.stdout.write(f"Ingesting languages: {len(rows)}")
            upsert(cur, "languages", REQUIRED_SHEETS["languages"], rows, ["lang_code"])

            # questions (booleans -> 0/1)
            df = frames["questions"].copy()
            df["active"] = df["active"].map(_boolify).astype(int)
            if df["display_order"].dtype != int:
                df["display_order"] = df["display_order"].astype(int)
            rows = [tuple(df[c].iloc[i] for c in REQUIRED_SHEETS["questions"]) for i in range(len(df))]
            self.stdout.write(f"Ingesting questions: {len(rows)}")
            upsert(cur, "questions", REQUIRED_SHEETS["questions"], rows, ["question_code"])

            # questions_i18n
            df = frames["questions_i18n"].fillna("")
            rows = [tuple(df[c].iloc[i] for c in REQUIRED_SHEETS["questions_i18n"]) for i in range(len(df))]
            self.stdout.write(f"Ingesting questions_i18n: {len(rows)}")
            upsert(cur, "questions_i18n", REQUIRED_SHEETS["questions_i18n"], rows, ["question_code", "lang_code"])

            # ---- red_flags (INSERT with created_at; UPDATE only slug) ----
            df = frames["red_flags"].fillna("")
            now = datetime.utcnow()  # naive UTC is fine for MySQL DATETIME
            red_flags_cols = REQUIRED_SHEETS["red_flags"] + ["created_at"]
            rows = [
                (df["red_flag_code"].iloc[i], df["education_url_slug"].iloc[i], now)
                for i in range(len(df))
            ]
            self.stdout.write(f"Ingesting red_flags: {len(rows)}")
            # Only update slug on duplicate, do NOT update created_at
            upsert(
                cur,
                "red_flags",
                red_flags_cols,
                rows,
                ["red_flag_code"],
                update_cols_override=["education_url_slug"],
            )

            # red_flags_i18n
            df = frames["red_flags_i18n"].fillna("")
            rows = [tuple(df[c].iloc[i] for c in REQUIRED_SHEETS["red_flags_i18n"]) for i in range(len(df))]
            self.stdout.write(f"Ingesting red_flags_i18n: {len(rows)}")
            upsert(cur, "red_flags_i18n", REQUIRED_SHEETS["red_flags_i18n"], rows, ["red_flag_code", "lang_code"])

            # doctor_education
            df = frames["doctor_education"].fillna("")
            rows = [tuple(df[c].iloc[i] for c in REQUIRED_SHEETS["doctor_education"]) for i in range(len(df))]
            self.stdout.write(f"Ingesting doctor_education: {len(rows)}")
            upsert(cur, "doctor_education", REQUIRED_SHEETS["doctor_education"], rows, ["red_flag_code", "lang_code"])

            # options (booleans -> 0/1 + check missing RF where triggers=1)
            df = frames["options"].copy()
            df["triggers_red_flag"] = df["triggers_red_flag"].map(_boolify).astype(int)
            if df["display_order"].dtype != int:
                df["display_order"] = df["display_order"].astype(int)
            bad = df[(df["triggers_red_flag"] == 1) & (df["red_flag_code"].isna() | (df["red_flag_code"] == ""))]
            if not bad.empty:
                raise CommandError(f"{len(bad)} option rows set triggers_red_flag=TRUE but have no red_flag_code.")
            rows = [tuple(df[c].iloc[i] for c in REQUIRED_SHEETS["options"]) for i in range(len(df))]
            self.stdout.write(f"Ingesting options: {len(rows)}")
            upsert(cur, "options", REQUIRED_SHEETS["options"], rows, ["option_code"])

            # options_i18n
            df = frames["options_i18n"].fillna("")
            rows = [tuple(df[c].iloc[i] for c in REQUIRED_SHEETS["options_i18n"]) for i in range(len(df))]
            self.stdout.write(f"Ingesting options_i18n: {len(rows)}")
            upsert(cur, "options_i18n", REQUIRED_SHEETS["options_i18n"], rows, ["option_code", "lang_code"])

            # result_messages
            df = frames["result_messages"].fillna("")
            rows = [tuple(df[c].iloc[i] for c in REQUIRED_SHEETS["result_messages"]) for i in range(len(df))]
            self.stdout.write(f"Ingesting result_messages: {len(rows)}")
            upsert(cur, "result_messages", REQUIRED_SHEETS["result_messages"], rows, ["message_code", "lang_code"])

            # ui_strings
            df = frames["ui_strings"].fillna("")
            rows = [tuple(df[c].iloc[i] for c in REQUIRED_SHEETS["ui_strings"]) for i in range(len(df))]
            self.stdout.write(f"Ingesting ui_strings: {len(rows)}")
            upsert(cur, "ui_strings", REQUIRED_SHEETS["ui_strings"], rows, ["key", "lang_code"])

        self.stdout.write(self.style.SUCCESS("Ingestion complete."))
