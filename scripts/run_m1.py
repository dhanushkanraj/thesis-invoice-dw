"""Run M1 (rules only) on digital PDFs and on scanned PDFs and score it.

Usage:  python scripts/run_m1.py [--heldout]
By default only the development and tuning splits are used. The held-out
split is reserved for the final comparison (pass --heldout only then).
"""
import csv
import json
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from invoice_pipeline.baseline import extract_invoice
from invoice_pipeline.evaluate import HEADER_FIELDS, evaluate_invoice
from invoice_pipeline.extract_text import configure_tesseract, get_lines

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
configure_tesseract()

splits = {"heldout"} if "--heldout" in sys.argv else {"development", "tuning"}
with (ROOT / "data" / "split.csv").open(encoding="utf-8") as f:
    rows = [r for r in csv.DictReader(f) if r["split"] in splits]

out_dir = ROOT / "outputs" / "m1"
records, item_records = [], []
for kind, folder in (("digital", "pdf"), ("scanned", "scanned")):
    (out_dir / kind).mkdir(parents=True, exist_ok=True)
    (ROOT / "outputs" / "text" / kind).mkdir(parents=True, exist_ok=True)
    for r in rows:
        iid = r["invoice_id"]
        cache = ROOT / "outputs" / "text" / kind / f"{iid}.txt"
        if cache.exists():
            lines = cache.read_text(encoding="utf-8").splitlines()
        else:
            lines, _ = get_lines(ROOT / "data" / "synthetic" / folder / f"{iid}.pdf")
            cache.write_text("\n".join(lines) + "\n", encoding="utf-8")
        pred = extract_invoice(lines)
        (out_dir / kind / f"{iid}.json").write_text(json.dumps(pred, indent=2, ensure_ascii=False), encoding="utf-8")
        truth = json.loads((ROOT / "data" / "ground_truth" / f"{iid}.json").read_text(encoding="utf-8"))
        res = evaluate_invoice(pred, truth)
        base = {"invoice_id": iid, "input": kind, "layout": r["layout"], "locale": r["locale"],
                "split": r["split"], "scan_profile": r["scan_profile"] if kind == "scanned" else "digital"}
        for field, outcome in res["outcomes"].items():
            records.append({**base, "field": field, "outcome": outcome})
        item_records.append({**base, **res["items"], "invoice_exact": res["invoice_exact"]})

fields = pd.DataFrame(records)
items = pd.DataFrame(item_records)
fields.to_csv(out_dir / "m1_fields.csv", index=False)
items.to_csv(out_dir / "m1_items.csv", index=False)

print(f"M1 rule-based baseline, splits: {sorted(splits)}, invoices: {len(rows)}\n")
acc = fields.assign(ok=fields.outcome == "correct").pivot_table(
    index="field", columns="input", values="ok", aggfunc="mean").reindex(HEADER_FIELDS)
acc.loc["line items (F1)"] = items.groupby("input")["f1"].mean()
acc.loc["WHOLE INVOICE exact"] = items.groupby("input")["invoice_exact"].mean()
print("Accuracy per field (share of invoices)")
print((acc * 100).round(1).to_string(), "\n")

print("Whole-invoice exact match by scan profile (%)")
print((items.groupby("scan_profile")["invoice_exact"].mean() * 100).round(1).to_string(), "\n")
print("Line-item F1 by layout, digital input (%)")
print((items[items.input == "digital"].groupby("layout")["f1"].mean() * 100).round(1).to_string(), "\n")
print("Outcome counts (all fields, digital / scanned)")
print(fields.groupby(["input", "outcome"]).size().unstack(fill_value=0).to_string())
