"""Score any method's predictions against the answer keys.

Usage:  python scripts/score.py m1            (reads outputs/m1/{digital,scanned}/*.json)
        python scripts/score.py m2_qwen3-4b
Scores every invoice that has a prediction file, restricted to the development
and tuning splits (or heldout with --heldout).
"""
import csv
import json
import sys
from pathlib import Path

import pandas as pd

from invoice_pipeline.evaluate import HEADER_FIELDS, evaluate_invoice

ROOT = Path(__file__).resolve().parents[1]
method = sys.argv[1]
splits = {"heldout"} if "--heldout" in sys.argv else {"development", "tuning"}
with (ROOT / "data" / "split.csv").open(encoding="utf-8") as f:
    rows = [r for r in csv.DictReader(f) if r["split"] in splits]

records, item_records, meta_records = [], [], []
for kind in ("digital", "scanned"):
    for r in rows:
        iid = r["invoice_id"]
        pred_file = ROOT / "outputs" / method / kind / f"{iid}.json"
        if not pred_file.exists():
            continue
        pred = json.loads(pred_file.read_text(encoding="utf-8"))
        truth = json.loads((ROOT / "data" / "ground_truth" / f"{iid}.json").read_text(encoding="utf-8"))
        res = evaluate_invoice(pred, truth)
        base = {"invoice_id": iid, "input": kind, "layout": r["layout"], "locale": r["locale"],
                "split": r["split"], "scan_profile": r["scan_profile"] if kind == "scanned" else "digital"}
        for field, outcome in res["outcomes"].items():
            records.append({**base, "field": field, "outcome": outcome})
        item_records.append({**base, **res["items"], "invoice_exact": res["invoice_exact"]})
        meta_file = pred_file.with_suffix(".meta.json")
        if meta_file.exists():
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            meta_records.append({**base, **{k: meta[k] for k in ("parse_ok", "seconds", "needs_review") if k in meta}})

if not records:
    raise SystemExit(f"No predictions found in outputs/{method}/")
fields, items = pd.DataFrame(records), pd.DataFrame(item_records)
out_dir = ROOT / "outputs" / method
fields.to_csv(out_dir / "fields.csv", index=False)
items.to_csv(out_dir / "items.csv", index=False)

print(f"{method}: scored {items.groupby('input').size().to_dict()} invoices, splits {sorted(splits)}\n")
acc = fields.assign(ok=fields.outcome == "correct").pivot_table(
    index="field", columns="input", values="ok", aggfunc="mean").reindex(HEADER_FIELDS)
acc.loc["line items (F1)"] = items.groupby("input")["f1"].mean()
acc.loc["WHOLE INVOICE exact"] = items.groupby("input")["invoice_exact"].mean()
print("Accuracy per field (%)")
print((acc * 100).round(1).to_string(), "\n")
print("Whole-invoice exact match by scan profile (%)")
print((items.groupby("scan_profile")["invoice_exact"].mean() * 100).round(1).to_string(), "\n")
print("Whole-invoice exact match by layout and input (%)")
print((items.pivot_table(index="layout", columns="input", values="invoice_exact", aggfunc="mean") * 100).round(1).to_string(), "\n")
print("Outcome counts (all fields)")
print(fields.groupby(["input", "outcome"]).size().unstack(fill_value=0).to_string())
if meta_records:
    meta = pd.DataFrame(meta_records)
    if "parse_ok" in meta:
        print(f"\nValid JSON replies: {meta.parse_ok.mean() * 100:.1f}%   mean seconds per invoice: {meta.seconds.mean():.1f}")
    if "needs_review" in meta:
        m = items.merge(meta[["invoice_id", "input", "needs_review"]], on=["invoice_id", "input"])
        print("\nValidation and review queue (M3 flags, M4 = flagged invoices corrected by a perfect reviewer)")
        rows_out = {}
        for kind, g in m.groupby("input"):
            wrong, right = g[~g.invoice_exact], g[g.invoice_exact]
            rows_out[kind] = {
                "invoices": len(g),
                "flagged %": g.needs_review.mean() * 100,
                "errors caught %": wrong.needs_review.mean() * 100 if len(wrong) else float("nan"),
                "false alarms %": right.needs_review.mean() * 100 if len(right) else float("nan"),
                "M3 exact %": g.invoice_exact.mean() * 100,
                "M4 exact %": (g.invoice_exact | g.needs_review).mean() * 100,
            }
        print(pd.DataFrame(rows_out).round(1).to_string())
        print("(errors caught = share of invoices with at least one wrong field that were flagged;"
              " false alarms = share of fully correct invoices that were flagged anyway)")
