"""Make a scanned copy of every synthetic PDF and run an OCR sanity check.

Usage:  python scripts/build_scans.py [seed]
Needs:  python scripts/build_dataset.py has been run first.
"""
import csv
import os
import random
import sys
from collections import Counter
from pathlib import Path

import pymupdf
import pytesseract
from dotenv import load_dotenv
from PIL import Image

from invoice_pipeline.dataset import plan, read_split_rows, write_split_rows
from invoice_pipeline.scan import PROFILES, assign_profiles, make_scan

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
if os.getenv("TESSERACT_PATH"):
    pytesseract.pytesseract.tesseract_cmd = os.environ["TESSERACT_PATH"]

seed = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
pdf_dir = ROOT / "data" / "synthetic" / "pdf"
scan_dir = ROOT / "data" / "synthetic" / "scanned"
scan_dir.mkdir(parents=True, exist_ok=True)

all_rows = read_split_rows(ROOT)
rows = [r for r in all_rows if r["split"] != "challenge"]  # the challenge set has its own builder
profiles = assign_profiles(plan(len(rows)))

for row, prof in zip(rows, profiles):
    row["scan_profile"] = prof
    i = int(row["invoice_id"].split("_")[1])
    make_scan(pdf_dir / f"{row['invoice_id']}.pdf", scan_dir / f"{row['invoice_id']}.pdf",
              PROFILES[prof], seed * 100_000 + i)

write_split_rows(ROOT, all_rows)  # rows are the same objects, now with scan_profile

print(f"Built {len(rows)} scanned PDFs in {scan_dir}")
print("By profile:", dict(Counter(r["scan_profile"] for r in rows)))
with_text = sum(
    1 for r in rows
    if pymupdf.open(scan_dir / f"{r['invoice_id']}.pdf")[0].get_text().strip()
)
print("Scans that still contain a text layer:", with_text, "(must be 0)")

# OCR sanity check on every 4th invoice: is the invoice number recognised?
import json
hits = Counter()
total = Counter()
for r in rows[::4]:
    truth = json.loads((ROOT / "data" / "ground_truth" / f"{r['invoice_id']}.json").read_text(encoding="utf-8"))
    doc = pymupdf.open(scan_dir / f"{r['invoice_id']}.pdf")
    pix = doc[0].get_pixmap(dpi=200)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    text = pytesseract.image_to_string(img, lang="deu+eng" if r["locale"] == "de" else "eng")
    total[r["scan_profile"]] += 1
    hits[r["scan_profile"]] += truth["invoice_number"] in text
print("OCR found the invoice number (sample of every 4th invoice):")
for p in ("good", "typical", "poor"):
    print(f"  {p:8s} {hits[p]}/{total[p]}")
if with_text:
    sys.exit(1)
