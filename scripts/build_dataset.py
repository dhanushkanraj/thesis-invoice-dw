"""Build the synthetic dataset and print a summary.

Usage:  python scripts/build_dataset.py [n_invoices] [seed]
"""
import sys
from collections import Counter
from pathlib import Path

from invoice_pipeline.dataset import build_dataset

ROOT = Path(__file__).resolve().parents[1]
n = int(sys.argv[1]) if len(sys.argv) > 1 else 120
seed = int(sys.argv[2]) if len(sys.argv) > 2 else 2026

result = build_dataset(ROOT, n=n, seed=seed)
rows, failures = result["rows"], result["failures"]

print(f"Built {len(rows)} invoices (seed {seed}) in {ROOT / 'data'}")
print("By split:   ", dict(Counter(r["split"] for r in rows)))
print("By layout:  ", dict(Counter(r["layout"] for r in rows)))
print("By locale:  ", dict(Counter(r["locale"] for r in rows)))
print("Null fields:", {k: sum(not r[k] for r in rows) for k in ("has_tax_id", "has_due_date", "has_subtotal")})
print("Line items: ", min(r["n_items"] for r in rows), "to", max(r["n_items"] for r in rows))
if failures:
    print(f"\nFAILED: {len(failures)} PDFs do not match their answer key")
    for iid, problems in list(failures.items())[:5]:
        print(" ", iid, problems[:2])
    sys.exit(1)
print(f"\nPDF vs answer key: {len(rows)}/{len(rows)} match. OK")