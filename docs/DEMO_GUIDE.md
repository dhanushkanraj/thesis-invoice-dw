# Demo guide for the supervisor meeting (about 10 minutes)

## Before the meeting (10 minutes earlier)
1. Start PostgreSQL and check that the project's `.env` points to it.
2. Start Ollama (`ollama list` shows `qwen3:4b`).
3. Activate the environment: `.\.venv\Scripts\Activate.ps1`.
4. Make sure the warehouse has data: `python scripts\load_warehouse.py --source m3_qwen3-4b --input digital`.
5. Open `streamlit run app\streamlit_app.py` once and check both pages load.
6. Have these open: the notes doc, `results\step22\fig_exact_match.png`, one sample invoice PDF.

## Story in five steps
1. **The problem (1 minute).** Invoices arrive as PDFs and scans. Analytics needs structured rows. Show one sample invoice.
2. **The pipeline (2 minutes).** Walk through the diagram in the README. Say: free, local, one laptop, nothing leaves the machine.
3. **The review screen (2 minutes).** Open Review queue. Show a flagged invoice next to the PDF, correct a field, submit.
4. **The dashboard (1 minute).** Open Dashboard. Spend by month, supplier and item, always per currency.
5. **The evidence (3 minutes).** Show the chart. Say what the intervals mean: when whiskers do not overlap, the difference is clear.
   Key facts (check against the notes before the meeting):
   - On the unseen layout, rules fell to 0 of 40, and Qwen3 4B reached 92.5% on digital invoices.
   - Scans stay hard for every method without review.
   - Validation adds little to automatic accuracy; its value is the flags.
   - The perfect-reviewer result is an upper bound; the real review effort is being measured on a sample.

## Questions he may ask, and honest answers
- *Why synthetic data?* Confidentiality and exact answer keys. The limit is external validity; this is stated in the Limitations.
- *Why are the intervals wide?* Only 24 and 40 invoices per condition. Small differences cannot be established.
- *Can layout and wording effects be separated?* No, on the challenge set they changed together.
- *Why not improve OCR?* The held-out set is already used; any tuning now would invalidate it. It is listed as future work.
- *Is M4 a real human result?* No. The perfect reviewer is an upper bound. The real effort comes from the review log.
- *What does the warehouse give that the PDFs did not?* Per-currency spend by month, supplier and item, with review status.

## If something fails during the demo
- Dashboard empty: run the load command in step 4 above.
- Database error: check PostgreSQL is running and the `.env` values; `python scripts\diagnose_db.py` shows what is wrong.
- Ollama error: `ollama list`, then start the Ollama app.
