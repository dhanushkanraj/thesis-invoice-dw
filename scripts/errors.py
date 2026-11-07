"""List what a method got wrong, so we can see the error types.

Usage:  python scripts/errors.py m2_qwen3-4b [digital|scanned] [examples_per_field]
Run  python scripts/score.py <method>  first (it writes fields.csv).
"""
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
method = sys.argv[1]
kind = sys.argv[2] if len(sys.argv) > 2 else "digital"
n_examples = int(sys.argv[3]) if len(sys.argv) > 3 else 3

fields = pd.read_csv(ROOT / "outputs" / method / "fields.csv")
bad = fields[(fields.input == kind) & (fields.outcome != "correct")]
print(f"{method} / {kind}: {len(bad)} wrong field values\n")
print(bad.groupby(["field", "outcome"]).size().unstack(fill_value=0).to_string(), "\n")

for field in bad.field.unique():
    print(f"--- {field}")
    for _, r in bad[bad.field == field].head(n_examples).iterrows():
        truth = json.loads((ROOT / "data" / "ground_truth" / f"{r.invoice_id}.json").read_text(encoding="utf-8"))
        pred_path = ROOT / "outputs" / method / kind / f"{r.invoice_id}.json"
        pred = json.loads(pred_path.read_text(encoding="utf-8"))
        print(f"  {r.invoice_id} [{r.layout}/{r.locale}] {r.outcome}: truth={truth.get(field)!r}  predicted={pred.get(field)!r}")

# line items: which invoices lost items, and how
items = pd.read_csv(ROOT / "outputs" / method / "items.csv")
worst = items[(items.input == kind) & (items.f1 < 1.0)].sort_values("f1").head(n_examples)
print("\n--- line items (lowest F1)")
for _, r in worst.iterrows():
    truth = json.loads((ROOT / "data" / "ground_truth" / f"{r.invoice_id}.json").read_text(encoding="utf-8"))
    pred = json.loads((ROOT / "outputs" / method / kind / f"{r.invoice_id}.json").read_text(encoding="utf-8"))
    print(f"  {r.invoice_id} [{r.layout}/{r.locale}] F1={r.f1:.2f} truth items={len(truth['line_items'])} predicted items={len(pred.get('line_items') or [])}")
