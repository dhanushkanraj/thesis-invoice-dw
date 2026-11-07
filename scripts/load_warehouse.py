"""Route validated invoices: clean ones into the warehouse, flagged ones to the review queue.

Usage:  python scripts/load_warehouse.py [--source m3_qwen3-4b] [--input digital|scanned]
                                         [--simulate-review] [--reset]
  --simulate-review  flagged invoices are loaded with the answer-key values (a perfect reviewer, M4)
  --reset            empty the warehouse first
Invoices a person corrected in the review app (outputs/reviewed/<input>/<id>.json) are
loaded as 'human_reviewed'. Load one input type per run: digital and scanned copies of the same
invoice are different documents and would be counted twice.
"""
import argparse
import csv
import json
import time
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select, text

from invoice_pipeline.db import get_engine
from invoice_pipeline.evaluate import evaluate_invoice
from invoice_pipeline.loader import route_invoice
from invoice_pipeline.warehouse import create_schema, drop_schema, fact_invoice, dim_currency, review_queue

ROOT = Path(__file__).resolve().parents[1]
ap = argparse.ArgumentParser()
ap.add_argument("--source", default="m3_qwen3-4b")
ap.add_argument("--input", default="digital", choices=["digital", "scanned"])
ap.add_argument("--simulate-review", action="store_true")
ap.add_argument("--reset", action="store_true")
args = ap.parse_args()

engine = get_engine()
if args.reset:
    drop_schema(engine)
create_schema(engine)

with (ROOT / "data" / "split.csv").open(encoding="utf-8") as f:
    rows = [r for r in csv.DictReader(f) if r["split"] in {"development", "tuning"}]

outcomes = Counter()
started = time.perf_counter()
loaded_auto_wrong = 0
sums = defaultdict(Decimal)
for r in rows:
    iid = r["invoice_id"]
    pred_file = ROOT / "outputs" / args.source / args.input / f"{iid}.json"
    if not pred_file.exists():
        continue
    rec = json.loads(pred_file.read_text(encoding="utf-8"))
    meta = json.loads(pred_file.with_suffix(".meta.json").read_text(encoding="utf-8"))
    truth = json.loads((ROOT / "data" / "ground_truth" / f"{iid}.json").read_text(encoding="utf-8"))
    reviewed, status = None, "human_reviewed"
    reviewed_file = ROOT / "outputs" / "reviewed" / args.input / f"{iid}.json"
    if reviewed_file.exists():
        reviewed = json.loads(reviewed_file.read_text(encoding="utf-8"))
    elif args.simulate_review:
        reviewed, status = truth, "simulated_review"
    with engine.begin() as conn:
        outcome = route_invoice(conn, f"{iid}_{args.input}", args.input, rec, meta["issues"],
                                meta["needs_review"], reviewed, status)
    outcomes[outcome] += 1
    if sum(outcomes.values()) % 10 == 0:
        print(f"  ... {sum(outcomes.values())}/{len(rows)} invoices done, {time.perf_counter() - started:.0f}s", flush=True)
    if outcome == "loaded":
        if not evaluate_invoice(rec, truth)["invoice_exact"]:
            loaded_auto_wrong += 1
        sums[rec["currency"]] += Decimal(str(rec["total_amount"]))
    elif outcome == "loaded_after_review":
        sums[reviewed["currency"]] += Decimal(str(reviewed["total_amount"]))

n = sum(outcomes.values())
print(f"Routed {n} {args.input} invoices from {args.source} in {time.perf_counter() - started:.0f}s:")
for k in ("loaded", "loaded_after_review", "queued"):
    print(f"  {k:20s} {outcomes[k]:4d}")
print(f"\nSilent errors: {loaded_auto_wrong} of the {outcomes['loaded']} automatically loaded invoices "
      f"contain at least one wrong value (checked against the answer keys).")

with engine.connect() as conn:
    n_fact = conn.execute(select(func.count()).select_from(fact_invoice)).scalar_one()
    n_queue = conn.execute(select(func.count()).select_from(review_queue)).scalar_one()
    db_sums = dict(conn.execute(
        select(dim_currency.c.currency_code, func.sum(fact_invoice.c.total_amount))
        .join(fact_invoice, fact_invoice.c.currency_key == dim_currency.c.currency_key)
        .where(fact_invoice.c.input_type == args.input)
        .group_by(dim_currency.c.currency_code)).all())
    print(f"\nWarehouse now holds {n_fact} invoices; review queue holds {n_queue}.")
    ok = all(Decimal(str(db_sums.get(c, 0))) == v for c, v in sums.items())
    print(f"Reconciliation for {args.input} documents (sum of totals per currency, database vs loaded records):", "OK" if ok else "MISMATCH")
    for c in sorted(db_sums):
        print(f"  {c}: {db_sums[c]}")
    print("\nTop 5 suppliers by spend (v_supplier_spend):")
    for row in conn.execute(text("SELECT supplier_name, currency_code, invoices, total_spend "
                                 "FROM v_supplier_spend ORDER BY total_spend DESC LIMIT 5")):
        print("  ", row[0], row[1], row[2], row[3])
    print("\nSpend by month, first 6 rows (v_monthly_spend):")
    for row in conn.execute(text("SELECT year, month, currency_code, invoices, total_spend "
                                 "FROM v_monthly_spend ORDER BY year, month, currency_code LIMIT 6")):
        print("  ", *row)
if not ok:
    raise SystemExit(1)
