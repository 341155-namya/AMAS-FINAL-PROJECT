"""Rule-based policy checks. The rules decide every line's status and amount.

The AI never approves or rejects anything: it can only suggest a category for a
line the keyword rules could not tag, and that suggestion is marked as AI.
"""
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

import policy as P

ORDER = {"Approve": 0, "Approve (capped)": 1, "Review": 2, "Hold": 3, "Reject": 4}
INJECTION_RE = re.compile(
    r"(ignore|disregard|forget|bypass)\s+(all\s+|any\s+|the\s+|your\s+)?(previous\s+|prior\s+)?(instructions|rules|policy|limits|prompt)"
    r"|system\s+prompt|you\s+are\s+now|approve\s+this|auto[- ]?approve|mark\s+(this|it)\s+as\s+approved",
    re.IGNORECASE)


@dataclass
class LineResult:
    line_no: int
    expense_date: date
    description: str
    merchant: str
    amount: float
    category: str
    category_source: str           # You / Rule / AI / Default
    status: str = "Approve"
    allowed: float = 0.0
    reasons: list = field(default_factory=list)

    def push(self, status, reason):
        if ORDER[status] > ORDER[self.status]:
            self.status = status
        self.reasons.append(reason)


def keyword_category(text: str):
    t = f" {str(text).lower()} "
    for cat, words in P.KEYWORDS:
        for w in words:
            if re.search(r"(?<![a-z])" + re.escape(w) + r"(?![a-z])", t):
                return cat
    return None


def has_injection(text: str) -> bool:
    return bool(INJECTION_RE.search(str(text or "")))


def has_non_reimbursable(text: str):
    t = str(text).lower()
    return [w for w in P.NON_REIMBURSABLE_WORDS if re.search(r"(?<![a-z])" + re.escape(w) + r"s?(?![a-z])", t)]


def cap_for(category: str, grade: str, city: str):
    c = P.CAPS.get(category)
    if c is None:
        return None
    if isinstance(c, (int, float)):
        return c
    if category == "Hotel":
        return c[(city, grade)]
    if category == "Meals":
        base = c[grade]
        return base if city == "Metro" else round(base * P.MEALS_NON_METRO_FACTOR)
    return c[grade]


def resolve_category(line: dict, ai_suggestions: dict, idx: int):
    """Return (category, source, mismatch_hint)."""
    text = f"{line.get('description', '')} {line.get('merchant', '')}"
    guess = keyword_category(text)
    chosen = line.get("category") or "Auto"
    if chosen != "Auto":
        mismatch = guess if (guess and guess != chosen) else None
        return chosen, "You", mismatch
    if guess:
        return guess, "Rule", None
    sug = ai_suggestions.get(idx)
    if sug and sug.get("category") in P.CATEGORIES and sug.get("confidence") == "high":
        return sug["category"], "AI", None
    return "Other", "Default", None


def check_claim(lines: list, grade: str, submitted_on: date, ai_suggestions: dict = None):
    """Check every line of one claim. Returns (results, summary)."""
    ai_suggestions = ai_suggestions or {}
    results = []
    for i, ln in enumerate(lines):
        cat, src, mismatch = resolve_category(ln, ai_suggestions, i)
        r = LineResult(line_no=i + 1, expense_date=ln["expense_date"], description=str(ln["description"]),
                       merchant=str(ln.get("merchant", "")), amount=float(ln["amount"]), category=cat,
                       category_source=src)
        r.allowed = r.amount
        text = f"{r.description} {r.merchant}"

        if mismatch:
            r.push("Review", f"Category check: you chose {cat}, but the description looks like {mismatch}.")
        if src == "Default":
            r.push("Review", "Could not tell the category from the description; finance will classify it.")
        if src == "AI":
            r.reasons.append(f"Category suggested by AI ({cat}); no keyword matched.")
        if cat == "Other":
            r.push("Review", "Policy: anything in 'Other' is reviewed by finance.")
        if has_injection(text):
            r.push("Review", "The description contains instructions aimed at the checker. They were ignored.")

        if r.amount > P.RECEIPT_REQUIRED_ABOVE and not ln.get("receipt", False):
            r.push("Hold", f"Receipt missing for an expense above Rs {P.RECEIPT_REQUIRED_ABOVE}.")
        bad = has_non_reimbursable(text)
        if bad:
            r.push("Hold", f"Mentions non-reimbursable items ({', '.join(bad)}). Resubmit with those items removed.")
        age = (submitted_on - r.expense_date).days
        if age > P.SUBMIT_WITHIN_DAYS:
            r.push("Review", f"Submitted {age} days after the expense (limit {P.SUBMIT_WITHIN_DAYS}). Needs manager override.")
        if ln.get("payment_mode") == "Cash" and r.amount > P.CASH_REVIEW_ABOVE:
            r.push("Review", f"Cash payment above Rs {P.CASH_REVIEW_ABOVE:,}.")
        if r.expense_date.weekday() >= 5 and cat not in P.WEEKEND_OK_CATEGORIES:
            r.push("Review", f"{cat} expense on a weekend.")
        if cat == "Hotel" and r.amount > P.GST_INVOICE_REQUIRED_ABOVE and not ln.get("gst_invoice", False):
            r.push("Review", f"Hotel bill above Rs {P.GST_INVOICE_REQUIRED_ABOVE:,} without a GST invoice (company loses tax credit).")
        if cat == "Air travel":
            if re.search(r"business\s+class|first\s+class", text, re.I):
                r.push("Review", "Policy allows economy class only.")
            if r.amount > P.AIR_PREAPPROVAL_ABOVE:
                r.push("Review", f"Airfare above Rs {P.AIR_PREAPPROVAL_ABOVE:,} needs pre-approval.")
        if cat == "Client entertainment" and grade == "L1":
            r.push("Review", "L1 employees need written pre-approval for client entertainment.")
        results.append(r)

    # Duplicates: same date, merchant and amount
    seen = {}
    for r, ln in zip(results, lines):
        key = (r.expense_date, r.merchant.strip().lower() or r.description.strip().lower(), round(r.amount, 2))
        if key in seen:
            r.push("Reject", f"Duplicate of line {seen[key]} (same date, merchant and amount).")
            r.allowed = 0
        else:
            seen[key] = r.line_no

    # Caps. Meals and local conveyance are per day; the rest per line.
    daily = defaultdict(list)
    for r, ln in zip(results, lines):
        if r.status in ("Reject", "Hold"):
            continue
        cap = cap_for(r.category, grade, ln.get("city", "Metro"))
        if cap is None:
            continue
        if cap == 0:
            continue  # pre-approval case already flagged
        if r.category in ("Meals", "Local conveyance"):
            daily[(r.category, r.expense_date, cap)].append(r)
        elif r.amount > cap:
            r.allowed = cap
            r.push("Approve (capped)", f"Above the {r.category.lower()} cap of Rs {cap:,} for {grade}. Rs {r.amount - cap:,.0f} not reimbursable.")

    for (cat, d, cap), rs in daily.items():
        total = sum(x.amount for x in rs)
        remaining = cap
        for x in rs:
            x.allowed = min(x.amount, remaining)
            remaining -= x.allowed
            if x.allowed < x.amount:
                x.push("Approve (capped)", f"Daily {cat.lower()} cap is Rs {cap:,} for {grade}; "
                                           f"{d.isoformat()} totals Rs {total:,.0f}. Rs {x.amount - x.allowed:,.0f} not reimbursable.")

    # Split bills: same merchant, same day, same category, each under the cap but together over it
    groups = defaultdict(list)
    for r, ln in zip(results, lines):
        if r.status not in ("Reject", "Hold") and r.merchant.strip():
            groups[(r.category, r.expense_date, r.merchant.strip().lower())].append((r, ln))
    for (cat, d, m), items in groups.items():
        if len(items) < 2:
            continue
        cap = cap_for(cat, grade, items[0][1].get("city", "Metro"))
        if cap and all(x.amount <= cap for x, _ in items) and sum(x.amount for x, _ in items) > cap:
            for x, _ in items:
                x.push("Review", f"Possible split bill: {len(items)} bills from {x.merchant} on {d.isoformat()} "
                                 f"add up to more than the Rs {cap:,} cap.")

    for r in results:
        if r.status in ("Hold", "Reject"):
            r.allowed = 0
        if not r.reasons:
            r.reasons.append("Within policy.")
    return results, summarize(results)


def summarize(results):
    s = {"lines": len(results), "claimed": 0.0, "approved": 0.0, "under_review": 0.0, "on_hold": 0.0,
         "rejected": 0.0, "cut_by_caps": 0.0, "by_status": defaultdict(int)}
    for r in results:
        s["claimed"] += r.amount
        s["by_status"][r.status] += 1
        if r.status in ("Approve", "Approve (capped)"):
            s["approved"] += r.allowed
            s["cut_by_caps"] += r.amount - r.allowed
        elif r.status == "Review":
            s["under_review"] += r.allowed
            s["cut_by_caps"] += r.amount - r.allowed
        elif r.status == "Hold":
            s["on_hold"] += r.amount
        else:
            s["rejected"] += r.amount
    s["by_status"] = dict(s["by_status"])
    return s
