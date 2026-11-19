"""Read-only audit: what did the M3 checks do to each field? (development data only)

Usage:  python scripts/m3_audit.py m2_qwen2.5-3b m3_qwen2.5-3b [digital|scanned]
For every field it counts, over invoices where M3 changed the value to empty:
  removed a CORRECT value   (M2 was right, M3 emptied it: the checks hurt the score)
  removed a WRONG value     (M2 was wrong, M3 emptied it: no score change, still wrong)
and shows a few examples of the first kind with the text the check saw.
No model is run and nothing is written.
"""
import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

from invoice_pipeline.evaluate import field_outcome

ROOT = Path(__file__).resolve().parents[1]
m2, m3 = sys.argv[1], sys.argv[2]
kind = sys.argv[3] if len(sys.argv) > 3 else "scanned"

split = pd.read_csv(ROOT / "data" / "split.csv")
ids = split[split.split.isin(["development", "tuning"])].invoice_id
fields = ("invoice_number", "supplier_name", "invoice_date", "due_date", "supplier_tax_id",
          "subtotal", "tax_amount", "total_amount", "currency")
correct, wrong = Counter(), Counter()
examples = {}
for iid in ids:
    p2, p3 = (ROOT / "outputs" / m / kind / f"{iid}.json" for m in (m2, m3))
    if not (p2.exists() and p3.exists()):
        continue
    a, b = json.loads(p2.read_text(encoding="utf-8")), json.loads(p3.read_text(encoding="utf-8"))
    truth = json.loads((ROOT / "data" / "ground_truth" / f"{iid}.json").read_text(encoding="utf-8"))
    for f in fields:
        if a.get(f) is not None and b.get(f) is None:
            if field_outcome(f, a.get(f), truth.get(f)) == "correct":
                correct[f] += 1
                examples.setdefault(f, []).append((iid, a.get(f)))
            else:
                wrong[f] += 1
print(f"{m3} vs {m2} / {kind}: values emptied by the checks\n")
print(f"{'field':16s} {'correct value removed':>22s} {'wrong value removed':>20s}")
for f in fields:
    print(f"{f:16s} {correct[f]:22d} {wrong[f]:20d}")
print(f"\nTOTAL            {sum(correct.values()):22d} {sum(wrong.values()):20d}")
tot = examples.get("total_amount", [])[:4]
if tot:
    print("\nExamples (total_amount, M2 was right). Lines of OCR text that mention it:")
    for iid, v in tot:
        lines = (ROOT / "outputs" / "text" / kind / f"{iid}.txt").read_text(encoding="utf-8").splitlines()
        digits = f"{v:.2f}".split(".")[0][-3:]
        hits = [l for l in lines if digits in l.replace(".", "").replace(",", "").replace(" ", "")][:2]
        print(f"  {iid}: M2 total = {v}")
        for l in hits:
            print(f"      {l!r}")
