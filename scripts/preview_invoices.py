"""Render one sample invoice per layout and locale (PDF plus its ground-truth JSON).

Usage (from the project root, with .venv active):
    python scripts/preview_invoices.py          # seed 42
    python scripts/preview_invoices.py 7        # another seed
Output goes to outputs/preview/ (the old classic_* preview files are replaced).
"""
import random
import sys
from pathlib import Path

from invoice_pipeline.fakedata import generate_invoice
from invoice_pipeline.formats import LOCALES
from invoice_pipeline.layouts import LAYOUTS, render

OUT = Path("outputs/preview")


def main() -> None:
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 42
    OUT.mkdir(parents=True, exist_ok=True)
    for code in sorted(LOCALES):
        # Same seed and locale give the same content, so the layouts can be compared side by side.
        g = generate_invoice(random.Random(seed), code)
        (OUT / f"truth_{code}_seed{seed}.json").write_text(g.truth.model_dump_json(indent=2), encoding="utf-8")
        for layout in sorted(LAYOUTS):
            pdf = render(layout, g, OUT / f"{layout}_{code}_seed{seed}.pdf")
            print(pdf.as_posix())
    print(f"Done: {len(LOCALES) * len(LAYOUTS)} PDFs and {len(LOCALES)} answer keys in {OUT.as_posix()}")


if __name__ == "__main__":
    main()