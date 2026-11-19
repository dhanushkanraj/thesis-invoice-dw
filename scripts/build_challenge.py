"""Build the challenge set: invoices in an unseen layout with different label wording,
plus a scanned copy of each (same three scan qualities as before).

Usage:  python scripts/build_challenge.py [n_invoices] [seed]
It does not touch the 120 original invoices. Running it again rebuilds only the
challenge files (ids ch_0001, ch_0002, ...) and their rows in data/split.csv.
Do NOT tune anything on this set: it is used once, at the final evaluation.
"""
import json
import os
import sys
from collections import Counter
from pathlib import Path

import pymupdf
import pytesseract
from dotenv import load_dotenv
from PIL import Image

from invoice_pipeline.challenge import (
    CHALLENGE_SEED,
    DEFAULT_N,
    build_challenge,
    build_challenge_scans,
)

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
if os.getenv("TESSERACT_PATH"):
    pytesseract.pytesseract.tesseract_cmd = os.environ["TESSERACT_PATH"]

n = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_N
seed = int(sys.argv[2]) if len(sys.argv) > 2 else CHALLENGE_SEED

result = build_challenge(ROOT, n=n, seed=seed)
rows, failures = result["rows"], result["failures"]
print(f"Built {len(rows)} challenge invoices (seed {seed}), layout 'ledger'")
print("By locale:  ", dict(Counter(r["locale"] for r in rows)))
print("Null fields:", {k: sum(not r[k] for r in rows) for k in ("has_tax_id", "has_due_date", "has_subtotal")})
print("Line items: ", min(r["n_items"] for r in rows), "to", max(r["n_items"] for r in rows))
if failures:
    print(f"\nFAILED: {len(failures)} PDFs do not match their answer key")
    for iid, problems in list(failures.items())[:5]:
        print(" ", iid, problems[:2])
    sys.exit(1)
print(f"PDF vs answer key: {len(rows)}/{len(rows)} match. OK")

build_challenge_scans(ROOT, rows, seed)
scan_dir = ROOT / "data" / "synthetic" / "scanned"
print("\nScanned copies by quality:", dict(Counter(r["scan_profile"] for r in rows)))
with_text = sum(
    1 for r in rows if pymupdf.open(scan_dir / f"{r['invoice_id']}.pdf")[0].get_text().strip()
)
print("Scans that still contain a text layer:", with_text, "(must be 0)")

# OCR sanity check on every 4th invoice: is the invoice number recognised?
hits, total = Counter(), Counter()
for r in rows[::4]:
    truth = json.loads((ROOT / "data" / "ground_truth" / f"{r['invoice_id']}.json").read_text(encoding="utf-8"))
    pix = pymupdf.open(scan_dir / f"{r['invoice_id']}.pdf")[0].get_pixmap(dpi=200)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    text = pytesseract.image_to_string(img, lang="deu+eng" if r["locale"] == "de" else "eng")
    total[r["scan_profile"]] += 1
    hits[r["scan_profile"]] += truth["invoice_number"] in text
print("OCR found the invoice number (sample of every 4th invoice):")
for p in ("good", "typical", "poor"):
    print(f"  {p:8s} {hits[p]}/{total[p]}")
print("\nNext: open data\\synthetic\\pdf\\ch_0001.pdf and look at it. No results are computed here on purpose.")
if with_text:
    sys.exit(1)
