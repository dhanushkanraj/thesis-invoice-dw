"""Compare ways of preparing scans for OCR.

Usage:  python scripts/ocr_experiment.py [--variants base,dpi300,clean,binary,dual] [--limit N]
Uses the scanned development/tuning invoices. Text is cached in outputs/ocr_variants/<variant>/,
so a rerun only reads what is missing. Results go to outputs/ocr_variants/results.csv.
Measures (no LLM involved):
  facts found      share of answer-key values that appear in the OCR text
  fully readable   share of invoices where EVERY answer-key value appears in the text
  M1 exact         share of invoices the rule-based extractor gets completely right
"""
import argparse
import csv
import json
import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from invoice_pipeline.baseline import extract_invoice
from invoice_pipeline.evaluate import evaluate_invoice
from invoice_pipeline.extract_text import configure_tesseract
from invoice_pipeline.ocr_variants import VARIANTS, ocr_lines
from invoice_pipeline.readability import readability

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
configure_tesseract()

ap = argparse.ArgumentParser()
ap.add_argument("--variants", default=",".join(VARIANTS))
ap.add_argument("--limit", type=int, default=0)
args = ap.parse_args()

with (ROOT / "data" / "split.csv").open(encoding="utf-8") as f:
    rows = [r for r in csv.DictReader(f) if r["split"] in {"development", "tuning"}]
if args.limit:
    rows = rows[: args.limit]

records = []
for variant in args.variants.split(","):
    out = ROOT / "outputs" / "ocr_variants" / variant
    out.mkdir(parents=True, exist_ok=True)
    started, read_now = time.perf_counter(), 0
    for r in rows:
        iid = r["invoice_id"]
        cache = out / f"{iid}.txt"
        if cache.exists():
            lines = cache.read_text(encoding="utf-8").splitlines()
        else:
            lines = ocr_lines(ROOT / "data" / "synthetic" / "scanned" / f"{iid}.pdf", variant)
            cache.write_text("\n".join(lines) + "\n", encoding="utf-8")
            read_now += 1
        truth = json.loads((ROOT / "data" / "ground_truth" / f"{iid}.json").read_text(encoding="utf-8"))
        rd = readability(truth, r["locale"], lines)
        exact = evaluate_invoice(extract_invoice(lines), truth)["invoice_exact"]
        records.append({"variant": variant, "invoice_id": iid, "layout": r["layout"], "scan_profile": r["scan_profile"],
                        "found": rd["found"], "total": rd["total"], "all_found": rd["all_found"], "m1_exact": exact})
    secs = (time.perf_counter() - started) / max(read_now, 1) if read_now else float("nan")
    print(f"{variant:8s} done ({read_now} read, {secs:.1f} s per invoice)", flush=True)

df = pd.DataFrame(records)
df.to_csv(ROOT / "outputs" / "ocr_variants" / "results.csv", index=False)
order = args.variants.split(",")

def table(by=None):
    g = df.groupby("variant" if by is None else ["variant", by])
    res = pd.DataFrame({
        "facts found %": g.found.sum() / g.total.sum() * 100,
        "fully readable %": g.all_found.mean() * 100,
        "M1 exact %": g.m1_exact.mean() * 100,
    })
    return res.round(1)

print(f"\nOCR variants on {len(rows)} scanned invoices (development + tuning)\n")
print(table().reindex(order).to_string(), "\n")
print("Fully readable invoices (%), by scan quality")
print((df.pivot_table(index="variant", columns="scan_profile", values="all_found", aggfunc="mean")
       .reindex(order)[["good", "typical", "poor"]] * 100).round(1).to_string(), "\n")
print("Facts found (%), by scan quality")
g = df.groupby(["variant", "scan_profile"])
print((g.found.sum() / g.total.sum() * 100).unstack().reindex(order)[["good", "typical", "poor"]].round(1).to_string())
