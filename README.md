# ClaimCheck: expense report assistant

End-term project, use case #12 (Expense report assistant, App format).

An employee enters expense lines (or adds one from a receipt photo). A rule engine built from the written
expense policy checks every line (caps by grade and city, receipts, 45-day deadline, duplicates, split bills,
alcohol, cash, weekends) and decides Approve / Approve up to cap / Review / Hold / Reject. Google Gemini reads
receipt photos, suggests a category when no keyword matches, writes the approval note and answers policy questions.

Demo company: **Sahyadri Foods Pvt Ltd** (fictional). All data is invented.

## Files
| File | What it does |
|---|---|
| `app.py` | The Streamlit app (4 tabs) |
| `policy.py` | The expense policy as data: caps, limits, keywords, policy text |
| `rules.py` | Rule engine: category tagging, policy checks, duplicates, split bills, caps |
| `ai.py` | Gemini calls: receipt reader, category suggestions, approval note, policy Q&A, masking, fallbacks |
| `validation.py` | Input checks for the claim table and CSV uploads |
| `evaluate.py` | Compares ClaimCheck with past auditor decisions and a rule of thumb |
| `data/sample_claims.csv` | 6 demo claims (23 lines) with edge cases; also the CSV template |
| `data/history.csv` | 428 synthetic past lines with auditor decisions |
| `tools/make_history.py` | Script that generated the synthetic history |

## Run it on your laptop (Windows)
1. Install Python 3.11 or 3.12 from python.org (tick "Add Python to PATH").
2. Unzip `claimcheck.zip`, open the `claimcheck` folder, click the address bar, type `cmd`, press Enter.
3. Install the libraries:
   `python -m pip install -r requirements.txt`
4. Add your Gemini key for this window (get one at aistudio.google.com → Get API key):
   `set GEMINI_API_KEY=paste-your-key-here`
5. Start the app:
   `python -m streamlit run app.py`
   It opens at http://localhost:8501. Stop it with Ctrl + C.

On Mac: use `python3` instead of `python`, and `export GEMINI_API_KEY=...` instead of `set`.
If your laptop blocks `pip` or `streamlit` commands, the `python -m ...` form above usually works.

## Put it online (free, browser only)
1. github.com/new → name `claimcheck` → Public → Create repository.
2. Click "uploading an existing file" → drag in everything inside this folder (including the `data` folder) → Commit changes.
3. share.streamlit.io → Create app → Deploy a public app from GitHub →
   GitHub URL: `https://github.com/YOUR-USERNAME/claimcheck/blob/main/app.py`
4. Advanced settings → Secrets → paste `GEMINI_API_KEY = "your-key"` → Deploy.
Never put the key in any file in this folder.

## Demo video script (about 5 minutes)
| Time | Do this | Say this |
|---|---|---|
| 0:00 | Show the home screen | "ClaimCheck, use case 12. The written policy decides what is paid; Gemini reads receipts, tags unclear lines and writes the approval note." |
| 0:20 | Load C1, click Check claim | "A clean claim: every line is within policy and fully payable. Each line shows why." |
| 0:45 | Load C2, Check claim | "Hotel above the L1 cap is paid up to Rs 4,000; the dinner with beer is on hold, because alcohol is never reimbursed." |
| 1:15 | Load C3, Check claim | "Two Zomato bills on one day are flagged as a possible split, and the second identical cab is rejected as a duplicate." |
| 1:40 | Load C4, Check claim | "Late submission, cash above Rs 2,000, a missing receipt and a weekend purchase: each goes to the right queue." |
| 2:10 | Load C5, Check claim | "Hinglish works; a cab tagged as Meals is caught; Croma 'Misc purchase' is unclear so finance classifies it; and the line that says 'ignore policy limits' is flagged, not obeyed." |
| 2:45 | Click Write the approval note with AI | "Gemini writes a note for the manager and the employee. Every rupee figure is checked against the claim, or the note is discarded." |
| 3:10 | Expand Add a line from a receipt photo; upload any receipt; Read receipt | "The AI reads the receipt, but I confirm every field before it is added." |
| 3:40 | Bulk check tab → Use the 6 sample claims → Export | "Bulk checks make no AI calls, so they scale; finance gets one export." |
| 4:05 | Does the check work? tab | "On 428 past lines, ClaimCheck caught most auditor refusals; the simple 'check everything above Rs 5,000' rule caught far fewer. The cost is more lines sent to a human." |
| 4:35 | Policy & questions tab → ask "Can an L1 claim a client dinner?" | "Answers come only from the policy and cite the rule. Off-topic questions are refused." |
