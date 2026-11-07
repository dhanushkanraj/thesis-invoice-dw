"""Render one sample invoice per locale (PDF plus its ground-truth JSON).

Usage (from the project root, with .venv active):
    python scripts/preview_invoices.py          # seed 42
    python scripts/preview_invoices.py 7        # another seed
Output goes to outputs/preview/.
"""
import random
import sys
from pathlib import Path

from invoice_pipeline.fakedata import generate_invoice
from invoice_pipeline.formats import LOCALES
from invoice_pipeline.render import render_classic

OUT = Path("outputs/preview")


def main() -> None:
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 42
    OUT.mkdir(parents=True, exist_ok=True)
    for code in sorted(LOCALES):
        g = generate_invoice(random.Random(seed), code)
        pdf = render_classic(g, OUT / f"classic_{code}_seed{seed}.pdf")
        (OUT / f"classic_{code}_seed{seed}.json").write_text(
            g.truth.model_dump_json(indent=2), encoding="utf-8"
        )
        print(f"{pdf}  (items: {len(g.truth.line_items)}, total: {g.truth.total_amount} {g.truth.currency})")


if __name__ == "__main__":
    main()