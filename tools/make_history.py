"""Generate data/history.csv: 400 SYNTHETIC past expense lines with the auditor's decision.

The hidden auditor is deliberately not identical to ClaimCheck's rules (auditors tolerate some late
claims, refuse some weekend spends, and refuse a few lines for reasons no rule can see), so the
"Does the check work?" tab shows realistic misses and false alarms.
Run from the project folder:  python tools/make_history.py
"""
import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd  # noqa: E402

from rules import cap_for, has_non_reimbursable, keyword_category  # noqa: E402

random.seed(11)
TEMPLATES = {
    "Local conveyance": [("Cab to client office", "Uber", 200, 900), ("Auto to warehouse", "Auto rickshaw", 80, 300),
                         ("Ola to airport", "Ola", 500, 1400), ("Parking at mall", "Parking", 40, 200)],
    "Meals": [("Lunch with team", "Zomato", 250, 1300), ("Dinner on tour", "Restaurant", 300, 1800),
              ("Breakfast at hotel cafe", "Cafe", 150, 600)],
    "Hotel": [("Hotel stay 1 night", "Treebo", 2000, 7500), ("Hotel 1 night near plant", "OYO", 1500, 4500)],
    "Train / bus": [("Train ticket", "IRCTC", 300, 2500), ("Volvo bus ticket", "redBus", 400, 1600)],
    "Air travel": [("Flight to Delhi", "IndiGo", 4000, 14000), ("Flight to Bengaluru", "Akasa", 3500, 16000)],
    "Internet & phone": [("Broadband bill", "Airtel", 600, 1300), ("Phone recharge", "Jio", 300, 900)],
    "Office supplies": [("Printer toner", "Stationery Mart", 600, 2600), ("Stationery for branch", "Stationery Mart", 200, 1500)],
    "Training & books": [("Excel course", "Udemy", 500, 4000), ("Book on negotiation", "Book store", 300, 1200)],
    "Client entertainment": [("Client dinner", "Restaurant", 2000, 9000)],
    "Other": [("Misc purchase", "Croma", 500, 5000), ("Gift hamper", "Archies", 400, 3000)],
}
WEIGHTS = [22, 20, 10, 8, 6, 6, 6, 5, 5, 4]
rows = []
sub = date(2026, 9, 30)
n_claims = 120
for c in range(n_claims):
    grade = random.choices(["L1", "L2", "L3"], weights=[55, 35, 10])[0]
    city = random.choice(["Metro", "Metro", "Other"])
    n = random.randint(2, 5)
    lines = []
    for _ in range(n):
        cat = random.choices(list(TEMPLATES), weights=WEIGHTS)[0]
        desc, merch, lo, hi = random.choice(TEMPLATES[cat])
        amt = round(random.uniform(lo, hi), -1)
        age = random.choices([random.randint(1, 30), random.randint(31, 60), random.randint(61, 100)], weights=[70, 20, 10])[0]
        d = sub - timedelta(days=age)
        if random.random() < 0.05 and cat == "Meals":
            desc += " (incl. beer)"
        lines.append(dict(expense_date=d, description=desc, merchant=merch, category="Auto", amount=amt,
                          payment_mode=random.choices(["UPI", "Card", "Company card", "Cash"], weights=[45, 30, 10, 15])[0],
                          receipt=(amt <= 500) or random.random() < 0.9, gst_invoice=random.random() < 0.6, city=city))
    if random.random() < 0.08:
        lines.append(dict(lines[0]))  # duplicate
    for ln in lines:
        rows.append(dict(claim_id=f"H{c+1:03d}", employee=f"Employee {c+1}", grade=grade, submitted_on=sub, **ln))

# Hidden auditor
seen = set()
for r in rows:
    key = (r["claim_id"], r["expense_date"], r["merchant"], r["amount"])
    cat = keyword_category(r["description"] + " " + r["merchant"]) or "Other"
    age = (r["submitted_on"] - r["expense_date"]).days
    cap = cap_for(cat, r["grade"], r["city"])
    p_refuse = 0.04
    outcome = None
    if key in seen:
        outcome = "Refused"
    seen.add(key)
    if outcome is None:
        if has_non_reimbursable(r["description"]):
            p_refuse = 0.95
        elif r["amount"] > 500 and not r["receipt"]:
            p_refuse = 0.85
        elif age > 60:
            p_refuse = 0.70
        elif age > 45:
            p_refuse = 0.15
        elif cat == "Other":
            p_refuse = 0.40
        elif r["payment_mode"] == "Cash" and r["amount"] > 2000:
            p_refuse = 0.25
        elif r["expense_date"].weekday() >= 5 and cat not in ("Air travel", "Train / bus", "Hotel", "Local conveyance", "Meals"):
            p_refuse = 0.35
        if random.random() < p_refuse:
            outcome = "Refused"
        elif cap and r["amount"] > cap:
            outcome = "Paid after cut"
        else:
            outcome = "Paid in full"
    r["auditor_outcome"] = outcome

out = Path(__file__).resolve().parents[1] / "data" / "history.csv"
pd.DataFrame(rows).to_csv(out, index=False)
df = pd.DataFrame(rows)
print("wrote", len(df), "lines;", df.auditor_outcome.value_counts().to_dict())
