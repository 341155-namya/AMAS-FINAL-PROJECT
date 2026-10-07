"""Checks that run before anything is scored or sent to the AI."""
from datetime import date, datetime

import pandas as pd

import policy as P

MAX_AMOUNT = 1_000_000
MAX_DESC = 300
LINE_COLUMNS = ["expense_date", "description", "merchant", "category", "amount", "payment_mode",
                "receipt", "gst_invoice", "city"]
CSV_REQUIRED = ["claim_id", "employee", "grade", "submitted_on"] + LINE_COLUMNS
YES, NO = {"1", "true", "yes", "y"}, {"0", "false", "no", "n", "", "nan", "none"}


def to_date(v):
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() == "":
        return None
    try:
        return pd.to_datetime(str(v).strip(), dayfirst=False).date()
    except Exception:
        return None


def to_bool(v):
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in YES:
        return True
    if s in NO:
        return False
    return None


def check_header(employee: str, grade: str, submitted_on):
    errs = []
    if not str(employee or "").strip():
        errs.append("Employee name is required.")
    if grade not in P.GRADES:
        errs.append(f"Grade must be one of {', '.join(P.GRADES)}.")
    if to_date(submitted_on) is None:
        errs.append("Submission date is missing or not a date.")
    return errs


def clean_lines(rows: list, submitted_on: date):
    """Validate claim lines. Returns (clean_lines, problems). Bad lines are skipped, never guessed."""
    clean, problems = [], []
    for i, raw in enumerate(rows, start=1):
        errs = []
        desc = "" if raw.get("description") is None or pd.isna(raw.get("description")) else str(raw["description"]).strip()
        merchant = "" if raw.get("merchant") is None or pd.isna(raw.get("merchant")) else str(raw["merchant"]).strip()
        if not desc:
            if all(raw.get(k) in (None, "") or (isinstance(raw.get(k), float) and pd.isna(raw.get(k))) for k in ("amount", "expense_date")):
                continue  # fully empty row from the table editor
            errs.append("description is required")
        if len(desc) > MAX_DESC:
            errs.append(f"description is longer than {MAX_DESC} characters")
        d = to_date(raw.get("expense_date"))
        if d is None:
            errs.append("expense date is missing or not a date (use YYYY-MM-DD)")
        elif d > submitted_on:
            errs.append(f"expense date {d.isoformat()} is after the submission date")
        try:
            amt = float(raw.get("amount"))
            if pd.isna(amt):
                raise ValueError
            if amt <= 0:
                errs.append("amount must be more than zero")
            elif amt > MAX_AMOUNT:
                errs.append(f"amount above Rs {MAX_AMOUNT:,} looks like a typo")
        except (TypeError, ValueError):
            amt = None
            errs.append("amount must be a number")
        cat = str(raw.get("category") or "Auto").strip() or "Auto"
        if cat not in P.CATEGORIES + ["Auto"]:
            errs.append(f"category '{cat}' is not in the policy list")
        pm = str(raw.get("payment_mode") or "UPI").strip()
        if pm not in P.PAYMENT_MODES:
            errs.append(f"payment mode '{pm}' must be one of {', '.join(P.PAYMENT_MODES)}")
        city = str(raw.get("city") or "Metro").strip()
        if city not in P.CITY_TYPES:
            errs.append("city must be Metro or Other")
        receipt, gst = to_bool(raw.get("receipt", False)), to_bool(raw.get("gst_invoice", False))
        if receipt is None or gst is None:
            errs.append("receipt and gst_invoice must be yes/no")
        if errs:
            problems.append(f"Line {i} ({desc[:30] or 'no description'}): " + "; ".join(errs))
            continue
        clean.append({"expense_date": d, "description": desc, "merchant": merchant, "category": cat,
                      "amount": round(amt, 2), "payment_mode": pm, "receipt": receipt, "gst_invoice": gst,
                      "city": city})
    return clean, problems


def split_csv(df: pd.DataFrame):
    """Turn a bulk CSV into claims. Returns (claims, problems, fatal)."""
    df = df.copy()
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    missing = [c for c in CSV_REQUIRED if c not in df.columns]
    if missing:
        return [], [], "The file is missing these columns: " + ", ".join(missing) + ". Download the template."
    if df.empty:
        return [], [], "The file has headers but no expense lines."
    if len(df) > 5000:
        return [], [], "Upload 5,000 lines or fewer at a time."
    claims, problems = [], []
    for cid, g in df.groupby("claim_id", sort=False):
        first = g.iloc[0]
        sub = to_date(first["submitted_on"])
        herr = check_header(first["employee"], str(first["grade"]).strip(), sub)
        if herr:
            problems.append(f"Claim {cid}: " + "; ".join(herr))
            continue
        lines, lp = clean_lines(g[LINE_COLUMNS].to_dict("records"), sub)
        problems += [f"Claim {cid}, {p}" for p in lp]
        if lines:
            claims.append({"claim_id": str(cid), "employee": str(first["employee"]).strip(),
                           "grade": str(first["grade"]).strip(), "submitted_on": sub, "lines": lines})
    return claims, problems, ""
