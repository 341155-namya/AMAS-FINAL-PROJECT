"""Compare ClaimCheck's decisions with past auditor decisions, and with a simple rule of thumb."""
import pandas as pd

from rules import check_claim
from validation import split_csv

FLAG = {"Review", "Hold", "Reject"}


def evaluate(df: pd.DataFrame, rule_of_thumb_above: float = 5000):
    """Returns (per_line_df, metrics) or raises ValueError with a readable message."""
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    if "auditor_outcome" not in df.columns:
        raise ValueError("The file needs an auditor_outcome column (Paid in full / Paid after cut / Refused).")
    claims, problems, fatal = split_csv(df)
    if fatal:
        raise ValueError(fatal)
    outcomes = {cid: list(g["auditor_outcome"].astype(str)) for cid, g in df.groupby("claim_id", sort=False)}
    recs = []
    for c in claims:
        res, _ = check_claim(c["lines"], c["grade"], c["submitted_on"])
        outs = outcomes.get(c["claim_id"], [])
        if len(outs) != len(res):
            continue  # a line was invalid; skip the claim rather than misalign
        for r, o in zip(res, outs):
            recs.append({"claim_id": c["claim_id"], "line": r.line_no, "amount": r.amount, "category": r.category,
                         "claimcheck": r.status, "auditor": o})
    d = pd.DataFrame(recs)
    if d.empty:
        raise ValueError("No lines could be compared.")
    refused = d["auditor"] == "Refused"
    cut = d["auditor"] == "Paid after cut"
    clean = d["auditor"] == "Paid in full"
    flagged = d["claimcheck"].isin(FLAG)
    capped = d["claimcheck"] == "Approve (capped)"
    big = d["amount"] > rule_of_thumb_above
    m = {
        "lines": len(d), "refused": int(refused.sum()), "cut": int(cut.sum()),
        "cc_sent_to_human": int(flagged.sum()),
        "cc_refusals_caught": int((refused & flagged).sum()),
        "cc_cuts_caught": int((cut & (capped | flagged)).sum()),
        "cc_false_alarms": int((clean & flagged).sum()),
        "rot_sent_to_human": int(big.sum()),
        "rot_refusals_caught": int((refused & big).sum()),
        "rot_cuts_caught": int((cut & big).sum()),
        "rot_false_alarms": int((clean & big).sum()),
        "skipped_problems": len(problems),
    }
    return d, m
