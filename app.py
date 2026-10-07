"""ClaimCheck: expense report assistant (use case #12, App format).

Run locally:  python -m streamlit run app.py
"""
import hashlib
import json
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

import ai
import policy as P
from evaluate import evaluate
from rules import check_claim, keyword_category
from validation import LINE_COLUMNS, check_header, clean_lines, split_csv, to_date

BASE = Path(__file__).parent
SAMPLE = BASE / "data" / "sample_claims.csv"
HISTORY = BASE / "data" / "history.csv"
ICON = {"Approve": "🟢", "Approve (capped)": "🟡", "Review": "🟠", "Hold": "🔵", "Reject": "🔴"}
SAMPLE_LABELS = {
    "C1": "Clean claim, everything within policy",
    "C2": "Over the hotel cap, and beer on a dinner bill",
    "C3": "Split bill and a duplicate cab",
    "C4": "Late, cash, missing receipt, weekend",
    "C5": "Hinglish, wrong category, prompt injection",
    "C6": "Near-twin meals: Rs 999 vs Rs 1,001",
}

st.set_page_config(page_title="ClaimCheck · Expense assistant", page_icon="🧾", layout="wide")
st.markdown("""
<style>
.block-container {padding-top: 2rem; max-width: 1250px;}
.cc-title {font-size: 2.1rem; font-weight: 750; letter-spacing: -0.02em; margin-bottom: 0;}
.cc-sub {color: #475467; font-size: 1.02rem; margin-top: .2rem; max-width: 780px;}
.cc-note {background:#F2F4F7; border-left: 3px solid #7A5AF8; padding:.6rem .9rem; font-size:.88rem; color:#344054; border-radius: 4px;}
</style>
""", unsafe_allow_html=True)


def rs(x) -> str:
    return f"Rs {x:,.0f}"


@st.cache_data(show_spinner=False)
def load_samples():
    claims, _, _ = split_csv(pd.read_csv(SAMPLE))
    return {c["claim_id"]: c for c in claims}


def lines_frame(lines):
    df = pd.DataFrame(lines, columns=LINE_COLUMNS)
    df["expense_date"] = pd.to_datetime(df["expense_date"]).dt.date
    return df


def empty_frame():
    return pd.DataFrame([{"expense_date": date.today(), "description": "", "merchant": "", "category": "Auto",
                          "amount": None, "payment_mode": "UPI", "receipt": True, "gst_invoice": False,
                          "city": "Metro"}], columns=LINE_COLUMNS)


def digest(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


@st.cache_data(ttl=3600, show_spinner=False)
def cached_categories(items_json: str):
    return ai.suggest_categories([tuple(x) for x in json.loads(items_json)])


@st.cache_data(ttl=3600, show_spinner=False)
def cached_note(facts_json: str):
    return ai.approval_note(json.loads(facts_json))


def rule_note(s, grade):
    parts = [f"{s['lines']} line(s) totalling {rs(s['claimed'])} from a {grade} employee.",
             f"Payable now: {rs(s['approved'])}."]
    if s["under_review"]:
        parts.append(f"Waiting for review: {rs(s['under_review'])}.")
    if s["on_hold"]:
        parts.append(f"On hold until fixed: {rs(s['on_hold'])}.")
    if s["rejected"]:
        parts.append(f"Rejected: {rs(s['rejected'])}.")
    if s["cut_by_caps"]:
        parts.append(f"Cut by policy caps: {rs(s['cut_by_caps'])}.")
    return " ".join(parts)


def results_table(results):
    return pd.DataFrame([{
        "#": r.line_no, "Date": r.expense_date.isoformat(), "Description": r.description,
        "Category": f"{r.category} ({r.category_source})", "Claimed": r.amount, "Payable": r.allowed,
        "Status": f"{ICON[r.status]} {r.status}", "Why": " ".join(r.reasons)} for r in results])


# ---------------------------------------------------------------- state
ss = st.session_state
samples = load_samples()
ss.setdefault("editor_ver", 0)
ss.setdefault("lines_df", lines_frame(samples["C1"]["lines"]))
ss.setdefault("header", {"employee": samples["C1"]["employee"], "grade": samples["C1"]["grade"],
                         "submitted_on": samples["C1"]["submitted_on"]})
ss.setdefault("result", None)
ss.setdefault("receipt", None)

# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.subheader("Try a sample claim")
    pick = st.selectbox("Sample", list(samples), label_visibility="collapsed",
                        format_func=lambda k: f"{k} · {samples[k]['employee']} — {SAMPLE_LABELS.get(k, '')}")
    if st.button("Load into the claim", type="primary"):
        c = samples[pick]
        ss.lines_df = lines_frame(c["lines"])
        ss.header = {"employee": c["employee"], "grade": c["grade"], "submitted_on": c["submitted_on"]}
        ss.editor_ver += 1
        ss.result, ss.receipt = None, None
        st.rerun()
    if st.button("Start a blank claim"):
        ss.lines_df = empty_frame()
        ss.header = {"employee": "", "grade": "L1", "submitted_on": date.today()}
        ss.editor_ver += 1
        ss.result, ss.receipt = None, None
        st.rerun()
    st.divider()
    use_ai_cat = st.toggle("Let AI suggest categories for unclear lines", value=True,
                           help="Only for lines set to Auto where no keyword matched. Rules still decide the status.")
    st.divider()
    if ai.get_key():
        st.success("Gemini key found. AI features are on.")
    else:
        st.warning("No Gemini key. Policy checks, bulk checks and export still work; AI features are off.")
    st.caption("ClaimCheck is an AI-assisted tool. Decisions come from the written policy and are suggestions "
               "for finance to confirm, not final approvals.")

# ---------------------------------------------------------------- header
st.markdown('<p class="cc-title">🧾 ClaimCheck</p>', unsafe_allow_html=True)
st.markdown('<p class="cc-sub">Expense report assistant. The written policy decides what is paid; Gemini reads receipts, '
            'tags unclear lines and writes the approval note.</p>', unsafe_allow_html=True)
st.markdown('<p class="cc-note">Demo set-up: <b>Sahyadri Foods Pvt Ltd</b>, a fictional company with a simple expense '
            'policy. All claims are sample data. When you use AI features, receipt images, expense descriptions and '
            'amounts are sent to Google Gemini. Employee names are never sent; emails, phone numbers, PAN, GSTIN and '
            'card numbers in descriptions are masked.</p>', unsafe_allow_html=True)
st.write("")
tab_claim, tab_bulk, tab_check, tab_policy = st.tabs(
    ["Check a claim", "Bulk check (CSV)", "Does the check work?", "Policy & questions"])

# ================================================================ TAB 1
with tab_claim:
    h = ss.header
    c1, c2, c3 = st.columns([2, 1, 1])
    employee = c1.text_input("Employee name *", h["employee"])
    grade = c2.selectbox("Grade", P.GRADES, index=P.GRADES.index(h["grade"]),
                         help="L1 executive, L2 manager, L3 senior manager")
    submitted_on = c3.date_input("Submission date", h["submitted_on"])
    ss.header = {"employee": employee, "grade": grade, "submitted_on": submitted_on}

    st.markdown("**Expense lines** (edit cells, add rows at the bottom, or add one from a receipt photo below)")
    edited = st.data_editor(
        ss.lines_df, key=f"editor_{ss.editor_ver}", num_rows="dynamic", hide_index=True,
        column_config={
            "expense_date": st.column_config.DateColumn("Date", format="YYYY-MM-DD", required=True),
            "description": st.column_config.TextColumn("Description", max_chars=300, width="large", required=True),
            "merchant": st.column_config.TextColumn("Merchant"),
            "category": st.column_config.SelectboxColumn("Category", options=["Auto"] + P.CATEGORIES, required=True),
            "amount": st.column_config.NumberColumn("Amount (Rs)", min_value=0, step=1, format="%.0f"),
            "payment_mode": st.column_config.SelectboxColumn("Paid by", options=P.PAYMENT_MODES, required=True),
            "receipt": st.column_config.CheckboxColumn("Receipt"),
            "gst_invoice": st.column_config.CheckboxColumn("GST invoice"),
            "city": st.column_config.SelectboxColumn("City", options=P.CITY_TYPES, required=True),
        })

    with st.expander("📷 Add a line from a receipt photo (AI)"):
        up = st.file_uploader("Receipt image (JPG or PNG, under 4 MB)", type=["jpg", "jpeg", "png", "webp"])
        if up is not None and st.button("Read receipt with AI"):
            try:
                with st.spinner("Reading the receipt…"):
                    ss.receipt = ai.read_receipt(up.getvalue(), up.type or "image/jpeg")
            except ai.AIError as e:
                ss.receipt = None
                st.info(str(e))
        rc = ss.receipt
        if rc:
            st.caption("Check every field. The AI read this from the image and can misread it; nothing is added until you click Add.")
            for w in rc["warnings"]:
                st.warning(w)
            if rc["alcohol"]:
                st.warning("The receipt seems to include alcohol or tobacco, which the policy never reimburses.")
            a1, a2, a3 = st.columns(3)
            r_date = a1.date_input("Date on receipt", to_date(rc["date"]) or submitted_on, key="r_date")
            r_merchant = a2.text_input("Merchant", rc["merchant"], key="r_merchant")
            r_amount = a3.number_input("Total (Rs)", min_value=0.0, value=float(rc["amount"] or 0), step=1.0, key="r_amt")
            b1, b2, b3 = st.columns(3)
            r_desc = b1.text_input("Description", rc["description"], key="r_desc")
            r_pm = b2.selectbox("Paid by", P.PAYMENT_MODES, index=P.PAYMENT_MODES.index(rc["payment_mode"]), key="r_pm")
            r_gst = b3.checkbox("GST invoice", rc["gst_invoice"], key="r_gst")
            if st.button("Add this line to the claim"):
                new = {"expense_date": r_date, "description": r_desc or "Receipt expense", "merchant": r_merchant,
                       "category": "Auto", "amount": r_amount, "payment_mode": r_pm, "receipt": True,
                       "gst_invoice": r_gst, "city": "Metro"}
                base = edited if not edited.empty else empty_frame().iloc[0:0]
                ss.lines_df = pd.concat([base, pd.DataFrame([new])], ignore_index=True)
                ss.editor_ver += 1
                ss.receipt = None
                st.rerun()

    if st.button("Check claim", type="primary"):
        herr = check_header(employee, grade, submitted_on)
        lines, problems = clean_lines(edited.to_dict("records"), submitted_on)
        if herr or problems or not lines:
            msgs = herr + problems + ([] if lines or problems else ["Add at least one expense line."])
            st.error("Fix these before checking:\n\n" + "\n".join(f"- {m}" for m in msgs))
            ss.result = None
        else:
            suggestions, cat_note = {}, ""
            unclear = [(i, ai.mask(f"{ln['description']} {ln['merchant']}", employee)) for i, ln in enumerate(lines)
                       if ln["category"] == "Auto" and not keyword_category(f"{ln['description']} {ln['merchant']}")]
            if unclear and use_ai_cat and ai.get_key():
                try:
                    with st.spinner("Asking Gemini about unclear categories…"):
                        suggestions = cached_categories(json.dumps(unclear))
                except ai.AIError as e:
                    cat_note = str(e)
            results, summary = check_claim(lines, grade, submitted_on, suggestions)
            ss.result = {"lines": lines, "results": results, "summary": summary, "grade": grade,
                         "employee": employee, "cat_note": cat_note, "note": None, "note_error": ""}

    res = ss.result
    if res:
        s = res["summary"]
        st.divider()
        m = st.columns(6)
        m[0].metric("Claimed", rs(s["claimed"]))
        m[1].metric("Payable now", rs(s["approved"]))
        m[2].metric("Under review", rs(s["under_review"]))
        m[3].metric("On hold", rs(s["on_hold"]))
        m[4].metric("Rejected", rs(s["rejected"]))
        m[5].metric("Cut by caps", rs(s["cut_by_caps"]))
        if res["cat_note"]:
            st.info("AI category suggestions were skipped: " + res["cat_note"])
        st.dataframe(results_table(res["results"]), hide_index=True,
                     column_config={"Claimed": st.column_config.NumberColumn(format="%.0f"),
                                    "Payable": st.column_config.NumberColumn(format="%.0f"),
                                    "Why": st.column_config.TextColumn(width="large")})
        st.caption("🟢 Approve · 🟡 Approve up to the cap · 🟠 Review by finance · 🔵 Hold until the employee fixes it · 🔴 Reject. "
                   "Category source: You = chosen by employee, Rule = keyword, AI = Gemini suggestion, Default = unclear.")

        st.subheader("Approval summary")
        facts = {"grade": res["grade"], "summary": {k: v for k, v in s.items() if k != "by_status"},
                 "lines": [{"line": r.line_no, "date": r.expense_date, "category": r.category,
                            "description": ai.mask(r.description, res["employee"]), "amount": r.amount,
                            "payable": r.allowed, "status": r.status, "reasons": r.reasons} for r in res["results"]]}
        if ai.get_key() and res["note"] is None and not res["note_error"]:
            if st.button("Write the approval note with AI"):
                try:
                    with st.spinner("Writing the note…"):
                        res["note"] = cached_note(json.dumps(facts, default=str, sort_keys=True))
                    if res["note"]["unverified"]:
                        cached_note.clear()  # never serve a discarded note from the cache
                except ai.AIError as e:
                    res["note_error"] = str(e)
                st.rerun()
        note = res["note"]
        if note and not note["unverified"]:
            st.markdown(f"**For the approving manager:** {note['manager_note']}")
            st.markdown(f"**Message to the employee:** {note['employee_message']}")
            st.caption(f"Written by {note.get('model') or 'Gemini'}. Every rupee figure was checked against the claim.")
        else:
            if note and note["unverified"]:
                st.warning("The AI note mentioned figures that are not in this claim ("
                           + ", ".join(note["unverified"]) + "), so it was discarded. Showing the rule-based summary.")
            if res["note_error"]:
                st.info(res["note_error"])
            st.markdown(f"**Summary (rule-based):** {rule_note(s, res['grade'])}")

        export = pd.DataFrame([{"employee": res["employee"], "grade": res["grade"], "line": r.line_no,
                                "date": r.expense_date, "category": r.category, "description": r.description,
                                "claimed": r.amount, "payable": r.allowed, "status": r.status,
                                "reasons": " | ".join(r.reasons)} for r in res["results"]])
        text = f"Claim by {res['employee']} ({res['grade']})\n{rule_note(s, res['grade'])}\n\n" + "\n".join(
            f"{r.line_no}. {r.expense_date} {r.category} {rs(r.amount)} -> {r.status}, payable {rs(r.allowed)}. "
            + " ".join(r.reasons) for r in res["results"])
        if note and not note["unverified"]:
            text += f"\n\nManager note: {note['manager_note']}\nEmployee message: {note['employee_message']}"
        d1, d2 = st.columns(2)
        d1.download_button("Download approval sheet (CSV)", export.to_csv(index=False).encode(),
                           f"claim_{res['employee'].replace(' ', '_') or 'employee'}.csv", "text/csv")
        d2.download_button("Download approval summary (TXT)", text.encode(), "approval_summary.txt", "text/plain")
        st.caption("Results stay while this tab is open. A browser refresh starts a fresh session, so download what you need.")

# ================================================================ TAB 2
with tab_bulk:
    st.markdown("Check many claims at once from one CSV (one row per expense line). Bulk checks use the rules only, "
                "so they make **no** AI calls.")
    c1, c2 = st.columns([2, 1])
    up = c1.file_uploader("Claims CSV", type=["csv"], label_visibility="collapsed", key="bulk_up")
    c2.download_button("Download the CSV template", SAMPLE.read_bytes(), "claimcheck_template.csv", "text/csv")
    if c2.button("Use the 6 sample claims"):
        ss.bulk_src = "sample"
    if up is not None:
        ss.bulk_src = "upload"
    df_in = None
    if ss.get("bulk_src") == "upload" and up is not None:
        try:
            df_in = pd.read_csv(up)
        except Exception:
            st.error("This file could not be read as a CSV. Save it from Excel as 'CSV UTF-8' and try again.")
    elif ss.get("bulk_src") == "sample":
        df_in = pd.read_csv(SAMPLE)
    if df_in is not None:
        claims, problems, fatal = split_csv(df_in)
        if fatal:
            st.error(fatal)
        else:
            if problems:
                with st.expander(f"⚠️ {len(problems)} line(s) skipped. See why."):
                    for p in problems:
                        st.write("- " + p)
            rows, all_lines = [], []
            for c in claims:
                results, s = check_claim(c["lines"], c["grade"], c["submitted_on"])
                worst = max((r.status for r in results), key=lambda x: list(ICON).index(x))
                rows.append({"Claim": c["claim_id"], "Employee": c["employee"], "Grade": c["grade"], "Lines": s["lines"],
                             "Claimed": s["claimed"], "Payable now": s["approved"], "Under review": s["under_review"],
                             "On hold": s["on_hold"], "Rejected": s["rejected"], "Needs": f"{ICON[worst]} {worst}"})
                all_lines += [{"claim_id": c["claim_id"], "employee": c["employee"], "line": r.line_no,
                               "date": r.expense_date, "category": r.category, "description": r.description,
                               "claimed": r.amount, "payable": r.allowed, "status": r.status,
                               "reasons": " | ".join(r.reasons)} for r in results]
            summ = pd.DataFrame(rows)
            m = st.columns(4)
            m[0].metric("Claims", len(summ))
            m[1].metric("Claimed", rs(summ["Claimed"].sum()))
            m[2].metric("Payable now", rs(summ["Payable now"].sum()))
            m[3].metric("Lines needing a human", int(sum(1 for x in all_lines if x["status"] in ("Review", "Hold", "Reject"))))
            st.dataframe(summ, hide_index=True)
            lines_df = pd.DataFrame(all_lines)
            show = st.multiselect("Show lines with status", list(ICON), default=["Review", "Hold", "Reject"])
            st.dataframe(lines_df[lines_df["status"].isin(show)], hide_index=True)
            st.download_button("Export for finance (CSV)", lines_df.to_csv(index=False).encode(),
                               "claimcheck_finance_export.csv", "text/csv", type="primary")

# ================================================================ TAB 3
with tab_check:
    st.markdown("Rules are only useful if they flag what an experienced auditor would refuse. This tab runs ClaimCheck on "
                "**past** expense lines with the auditor's decision and compares it with a common rule of thumb. The "
                "built-in file is 428 **synthetic** lines; upload a real file with an `auditor_outcome` column to test it.")
    hist_up = st.file_uploader("Past lines with auditor decisions (optional)", type=["csv"], key="hist")
    rot = st.number_input("Rule of thumb: check every line above (Rs)", 1000, 50000, 5000, step=500)
    try:
        hist = pd.read_csv(hist_up) if hist_up is not None else pd.read_csv(HISTORY)
        d, mt = evaluate(hist, rot)
    except Exception as e:
        st.error(str(e) if isinstance(e, ValueError) else "This file could not be read as a CSV.")
        d = None
    if d is not None:
        pct = lambda a, b: f"{a / b:.0%}" if b else "–"
        c = st.columns(3)
        c[0].metric("Lines checked", mt["lines"])
        c[1].metric("Auditor refused", mt["refused"])
        c[2].metric("Auditor paid after a cut", mt["cut"])
        comp = pd.DataFrame({
            "Lines sent to a human": [mt["cc_sent_to_human"], mt["rot_sent_to_human"]],
            "Refusals caught": [f"{mt['cc_refusals_caught']} of {mt['refused']} ({pct(mt['cc_refusals_caught'], mt['refused'])})",
                                f"{mt['rot_refusals_caught']} of {mt['refused']} ({pct(mt['rot_refusals_caught'], mt['refused'])})"],
            "Cuts caught": [f"{mt['cc_cuts_caught']} of {mt['cut']}", f"{mt['rot_cuts_caught']} of {mt['cut']}"],
            "False alarms (auditor paid in full)": [mt["cc_false_alarms"], mt["rot_false_alarms"]],
        }, index=["ClaimCheck rules", f"Rule of thumb: every line above {rs(rot)}"])
        st.dataframe(comp)
        st.markdown("**ClaimCheck decision vs auditor decision** (counts of lines)")
        st.dataframe(pd.crosstab(d["claimcheck"], d["auditor"]))
        st.caption("Misses (auditor refused, ClaimCheck approved) are refusals no rule can see, such as personal items. "
                   "False alarms are the price of sending borderline lines to a human.")

# ================================================================ TAB 4
with tab_policy:
    left, right = st.columns([3, 2])
    with left:
        st.markdown("#### The policy ClaimCheck enforces")
        st.code(P.POLICY_TEXT, language=None)
    with right:
        st.markdown("#### Ask about the policy")
        st.caption("Answers come only from the policy on the left and cite the rule number. Uses one Gemini call.")
        q = st.text_input("Question", placeholder="e.g. Can an L1 claim a client dinner?", label_visibility="collapsed")
        if st.button("Ask"):
            try:
                with st.spinner("Checking the policy…"):
                    ss.policy_answer = ai.ask_policy(q)
            except ai.AIError as e:
                ss.policy_answer = f"⚠️ {e}"
        if ss.get("policy_answer"):
            st.info(ss.policy_answer)
        st.markdown("#### How decisions are made")
        st.markdown(
            "- **Rules decide** every status and amount: caps, receipts, deadlines, duplicates, split bills, alcohol, cash, weekends.\n"
            "- **AI assists**: reads receipt photos (you confirm each field), suggests a category when no keyword matches "
            "(from the fixed list only), writes the approval note (every rupee figure is checked), answers policy questions.\n"
            "- **If Gemini is down**, checks, bulk checks, validation and downloads still work.")
