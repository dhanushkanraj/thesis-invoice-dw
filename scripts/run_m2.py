"""Run M2 (local LLM alone) and save its predictions.

Usage:  python scripts/run_m2.py [--model qwen3:4b] [--limit N] [--kinds digital,scanned] [--heldout]
Resumable: invoices that already have a prediction file are skipped.
Score the result with:  python scripts/score.py m2_qwen3-4b
"""
import argparse
import csv
import json
from pathlib import Path

from dotenv import load_dotenv

from invoice_pipeline.llm import extract_with_llm

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

ap = argparse.ArgumentParser()
ap.add_argument("--model", default="qwen3:4b")
ap.add_argument("--limit", type=int, default=0, help="only the first N invoices (smoke test)")
ap.add_argument("--kinds", default="digital,scanned")
ap.add_argument("--heldout", action="store_true", help="final evaluation only")
args = ap.parse_args()

splits = {"heldout"} if args.heldout else {"development", "tuning"}
with (ROOT / "data" / "split.csv").open(encoding="utf-8") as f:
    rows = [r for r in csv.DictReader(f) if r["split"] in splits]
if args.limit:
    rows = rows[: args.limit]

method = "m2_" + args.model.replace(":", "-")
total = len(rows) * len(args.kinds.split(","))
done = 0
for kind in args.kinds.split(","):
    out = ROOT / "outputs" / method / kind
    out.mkdir(parents=True, exist_ok=True)
    for r in rows:
        iid = r["invoice_id"]
        done += 1
        target = out / f"{iid}.json"
        if target.exists():
            continue
        text_file = ROOT / "outputs" / "text" / kind / f"{iid}.txt"
        if not text_file.exists():
            raise SystemExit(f"Missing {text_file}. Run: python scripts\\run_m1.py first (it creates the text files).")
        lines = text_file.read_text(encoding="utf-8").splitlines()
        res = extract_with_llm(lines, args.model)
        target.write_text(json.dumps(res["pred"], indent=2, ensure_ascii=False), encoding="utf-8")
        (out / f"{iid}.meta.json").write_text(
            json.dumps({"parse_ok": res["parse_ok"], "seconds": res["seconds"], "raw": res["raw"]}, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"[{done}/{total}] {kind} {iid}  {res['seconds']}s  json_ok={res['parse_ok']}", flush=True)
print("Finished. Next: python scripts\\score.py", method)
