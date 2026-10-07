"""The expense policy of Sahyadri Foods Pvt Ltd (fictional), as data.

Every rule the app enforces lives here, so a finance team can change a number
without touching the logic. The same text is shown in the app and given to the
AI for policy questions.
"""

CATEGORIES = [
    "Air travel", "Train / bus", "Local conveyance", "Hotel", "Meals",
    "Client entertainment", "Internet & phone", "Office supplies", "Training & books", "Other",
]
GRADES = ["L1", "L2", "L3"]          # L1 executive, L2 manager, L3 senior manager
CITY_TYPES = ["Metro", "Other"]
PAYMENT_MODES = ["UPI", "Card", "Company card", "Cash"]

# Caps per line, in rupees. None = no cap (other rules still apply). 0 = not allowed without pre-approval.
CAPS = {
    "Hotel": {("Metro", "L1"): 4000, ("Metro", "L2"): 6000, ("Metro", "L3"): 9000,
              ("Other", "L1"): 2500, ("Other", "L2"): 4000, ("Other", "L3"): 6000},       # per night
    "Meals": {"L1": 1000, "L2": 1500, "L3": 2500},                                       # per day, metro
    "Local conveyance": {"L1": 1000, "L2": 1500, "L3": 2500},                            # per day
    "Client entertainment": {"L1": 0, "L2": 5000, "L3": 10000},                          # per event
    "Internet & phone": 1000,                                                            # per month
    "Office supplies": 2000,
    "Training & books": 5000,
}
MEALS_NON_METRO_FACTOR = 0.8          # meal cap is 80% of the metro cap outside metros
RECEIPT_REQUIRED_ABOVE = 500
SUBMIT_WITHIN_DAYS = 45
CASH_REVIEW_ABOVE = 2000
GST_INVOICE_REQUIRED_ABOVE = 5000     # hotels: company needs a GST invoice to claim input tax credit
AIR_PREAPPROVAL_ABOVE = 15000
WEEKEND_OK_CATEGORIES = {"Air travel", "Train / bus", "Hotel", "Local conveyance", "Meals"}
NON_REIMBURSABLE_WORDS = ("beer", "whisky", "whiskey", "wine", "vodka", "rum", "liquor", "alcohol",
                          "bar tab", "cigarette", "tobacco", "hookah")

# Keyword tagging: first match wins. Checked against description + merchant, lower-cased.
KEYWORDS = [
    ("Air travel", ("indigo", "air india", "akasa", "spicejet", "vistara", "flight", "airfare", "airline")),
    ("Train / bus", ("irctc", "train", "redbus", "volvo bus", "bus ticket", "metro card")),
    ("Local conveyance", ("uber", "ola", "rapido", "auto", "taxi", "cab", "parking", "toll", "fuel")),
    ("Hotel", ("hotel", "oyo", "treebo", "fabhotel", "inn", "lodge", "stay", "resort", "check-in")),
    ("Client entertainment", ("client dinner", "client lunch", "with client", "w/ client", "entertainment")),
    ("Meals", ("swiggy", "zomato", "restaurant", "lunch", "dinner", "breakfast", "cafe", "café", "meal", "dhaba", "food")),
    ("Internet & phone", ("jio", "airtel", "vodafone", "vi postpaid", "broadband", "internet", "recharge", "wifi")),
    ("Office supplies", ("stationery", "printer", "toner", "cartridge", "pen drive", "notebook", "office supplies")),
    ("Training & books", ("udemy", "coursera", "book", "course", "workshop", "certification", "training")),
]

POLICY_TEXT = f"""SAHYADRI FOODS PVT LTD: EMPLOYEE EXPENSE POLICY (demo, fictional)

1. Grades: L1 = executive, L2 = manager, L3 = senior manager.
2. Hotel, per night: Metro L1 Rs 4,000, L2 Rs 6,000, L3 Rs 9,000. Other cities L1 Rs 2,500, L2 Rs 4,000, L3 Rs 6,000.
   Hotel bills above Rs {GST_INVOICE_REQUIRED_ABOVE:,} need a GST invoice in the company's name.
3. Meals, per day in metros: L1 Rs 1,000, L2 Rs 1,500, L3 Rs 2,500. Outside metros the cap is {int(MEALS_NON_METRO_FACTOR*100)}% of this.
4. Local conveyance (cab, auto, parking, fuel), per day: L1 Rs 1,000, L2 Rs 1,500, L3 Rs 2,500.
5. Client entertainment, per event: L2 Rs 5,000, L3 Rs 10,000. L1 needs written pre-approval.
6. Internet & phone: Rs 1,000 per month. Office supplies: Rs 2,000 per bill. Training & books: Rs 5,000 per bill.
7. Air travel: economy class only. Fares above Rs {AIR_PREAPPROVAL_ABOVE:,} need pre-approval.
8. Amounts above a cap are not reimbursed; the claim is paid up to the cap.
9. A receipt is required for any expense above Rs {RECEIPT_REQUIRED_ABOVE}.
10. Claims must be submitted within {SUBMIT_WITHIN_DAYS} days of the expense date.
11. Alcohol and tobacco are never reimbursed.
12. Cash payments above Rs {CASH_REVIEW_ABOVE:,} are reviewed by finance.
13. Weekend expenses outside travel, hotel, local conveyance and meals are reviewed.
14. The same bill must not be claimed twice, and one bill must not be split to stay under a cap.
15. Anything in "Other" is always reviewed by finance.
"""
