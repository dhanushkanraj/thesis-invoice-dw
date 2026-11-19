"""Run M3 (LLM + validation) on saved M2 predictions. No model call, takes seconds.

Usage:  python scripts/run_m3.py [--source m2_qwen3-4b] [--heldout]
Writes outputs/m3_<name>/{digital,scanned}/<id>.json (repaired prediction)
and <id>.meta.json (issues and the needs_review flag).
Score with:  python scripts/score.py m3_qwen3-4b
"""
import argparse
import csv
import json
from dataclasses import asdict
from pathlib import Path

from invoice_pipeline.splits import select_splits
from invoice_pipeline.validate import needs_review, validate

ROOT = Path(__file__).resolve().parents[1]
ap = argparse.ArgumentParser()
ap.add_argument("--source", default="m2_qwen3-4b")
ap.add_argument("--heldout", action="store_true")
ap.add_argument("--challenge", action="store_true")
args = ap.parse_args()

splits, _ = select_splits(args.heldout, args.challenge)
with (ROOT / "data" / "split.csv").open(encoding="utf-8") as f:
    rows = [r for r in csv.DictReader(f) if r["split"] in splits]

method = "m3_" + args.source.split("_", 1)[-1] if args.source.startswith("m2_") else "m3_" + args.source
flagged = total = 0
for kind in ("digital", "scanned"):
    out = ROOT / "outputs" / method / kind
    out.mkdir(parents=True, exist_ok=True)
    for r in rows:
        iid = r["invoice_id"]
        src = ROOT / "outputs" / args.source / kind / f"{iid}.json"
        if not src.exists():
            continue
        pred = json.loads(src.read_text(encoding="utf-8"))
        lines = (ROOT / "outputs" / "text" / kind / f"{iid}.txt").read_text(encoding="utf-8").splitlines()
        repaired, issues = validate(pred, lines)
        review = needs_review(issues)
        (out / f"{iid}.json").write_text(json.dumps(repaired, indent=2, ensure_ascii=False), encoding="utf-8")
        (out / f"{iid}.meta.json").write_text(
            json.dumps({"needs_review": review, "issues": [asdict(i) for i in issues]}, ensure_ascii=False),
            encoding="utf-8",
        )
        total += 1
        flagged += review
print(f"Validated {total} invoices from {args.source}: {flagged} sent to review ({flagged / max(total, 1) * 100:.1f}%)")
print("Next: python scripts\\score.py", method)
