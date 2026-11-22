# LLM-assisted transformation of unstructured business documents into an analytics-ready data warehouse

Master's dissertation project (BSBI). Author: Dhanush Kanraj. Supervisor: Dr. Ashish M. Kothari.

A local pipeline turns supplier-invoice PDFs into validated rows in a PostgreSQL star schema, and measures how reliable those rows are.
Everything is free software and runs on one laptop (16 GB RAM, RTX 3050 4 GB). No invoice leaves the machine.

```
PDF  ->  text (PyMuPDF) or OCR (Tesseract, for scans)
     ->  local LLM through Ollama, returns JSON
     ->  Pydantic and business-rule validation (type, grounding, arithmetic, dates, required fields)
     ->  human review queue for flagged invoices (Streamlit)
     ->  PostgreSQL star schema  ->  Streamlit dashboard
```

## What is compared

| Method | What it is |
|---|---|
| M1 | Rules only (regular expressions), no model |
| M2 | Local LLM alone (Qwen3 4B, and Qwen2.5 3B for comparison) |
| M3 | M2 plus automatic validation |
| M4 | M3 plus human review: a perfect reviewer simulated from the answer keys (upper bound), plus a real review sample |

Data: 120 synthetic invoices (seed 2026), 3 layouts x 4 locales, split 72 development / 24 tuning / 24 held-out,
plus a 40-invoice challenge set (ledger layout, different label wording, seed 3030). Each invoice exists as a digital PDF and as scans
in three quality profiles. Synthetic data was chosen for confidentiality and exact answer keys; see the thesis for the limits.

The held-out and challenge sets were scored once. Do not tune anything on them.

## Requirements

- Windows or Linux, Python (the version of your `.venv`), PostgreSQL, Ollama, Tesseract OCR.
- Ollama models: `qwen3:4b` and `qwen2.5:3b` (`ollama pull qwen3:4b`, `ollama pull qwen2.5:3b`).
- Python packages: see `requirements.txt` [CONFIRM: create it with `pip freeze > requirements.txt` if it is missing].
- A `.env` file in the project root (never commit it):

```
DB_USER=...
DB_PASSWORD=...
DB_HOST=localhost
DB_PORT=5432
DB_NAME=...
TESSERACT_PATH=C:\Program Files\Tesseract-OCR\tesseract.exe
```

## Setup (PowerShell)

```powershell
cd <project folder>
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Reproduce the work

1. Data (a few minutes, no model):
```powershell
python scripts\build_dataset.py 120 2026
python scripts\build_scans.py
python scripts\build_challenge.py 40 3030
```
2. Development runs (digital and scanned):
```powershell
python scripts\run_m1.py
python scripts\run_m2.py --model qwen3:4b
python scripts\run_m3.py --source m2_qwen3-4b
python scripts\score.py m3_qwen3-4b
```
3. Final evaluation (run once only; results are already recorded in the notes):
```powershell
python scripts\run_m2.py --model qwen3:4b --heldout
python scripts\run_m3.py --source m2_qwen3-4b --heldout
python scripts\score.py m3_qwen3-4b --heldout
```
Use `--challenge` instead of `--heldout` for the challenge set, and `qwen2.5:3b` for the second model.
4. Warehouse:
```powershell
python scripts\init_db.py
python scripts\load_warehouse.py --source m3_qwen3-4b --input digital
```
5. Apps and statistics:
```powershell
streamlit run app\streamlit_app.py          # pages: Dashboard, Review queue
python results\step22\wilson_step22.py      # Wilson intervals, table CSV, chart (run inside results\step22)
python -m pytest -q                         # unit tests
```

## Repository map

| Folder | Content |
|---|---|
| `src/invoice_pipeline/` | the pipeline: fake data, layouts, scans, extraction, validation, evaluation, loader, warehouse |
| `scripts/` | one script per step (build data, run methods, score, load, audit, diagnose database) |
| `app/streamlit_app.py` | dashboard and review screen |
| `tests/` | unit tests |
| `data/` | synthetic invoices and answer keys (generated) |
| `outputs/` | predictions per method (generated) |
| `results/step22/` | Wilson intervals, results CSV and chart |

## Known limits

- Synthetic invoices: results may not transfer to real invoices.
- On the challenge set, layout and label wording changed together, so their effects cannot be separated.
- Small test sets (24 and 40 invoices), so confidence intervals are wide.
- Scanned invoices are weak for every method without review; OCR quality is the limit.
- M4 with a perfect reviewer is an upper bound, not a measured human result.
