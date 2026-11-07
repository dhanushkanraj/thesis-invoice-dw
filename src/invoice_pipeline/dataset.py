"""Build the synthetic invoice dataset: PDFs, answer keys, split table.

Every invoice i gets its own seeded random generator, so invoice 17 is the same
no matter how many invoices are built. Layout and locale are cycled so that all
layout x locale combinations are equally frequent. The split is stratified per
combination, so development, tuning and held-out sets all see every combination.
"""
import csv
import json
import random
from datetime import date
from pathlib import Path

import pymupdf

from invoice_pipeline.fakedata import GeneratedInvoice, generate_invoice
from invoice_pipeline.formats import format_date, format_money, get_locale
from invoice_pipeline.layouts import render
from invoice_pipeline.render import format_quantity

LAYOUT_ORDER = ("classic", "modern", "twocol")
LOCALE_ORDER = ("de", "en_eu", "us", "uk")
SPLIT_RATIOS = (("development", 0.6), ("tuning", 0.2), ("heldout", 0.2))


def invoice_id(i: int) -> str:
    return f"inv_{i:04d}"


def plan(n: int) -> list[tuple[str, str]]:
    """(layout, locale) for invoice 1..n, cycling through all 12 combinations."""
    return [(LAYOUT_ORDER[i % 3], LOCALE_ORDER[(i // 3) % 4]) for i in range(n)]


def assign_splits(combos: list[tuple[str, str]], seed: int) -> list[str]:
    """Stratified split: inside each (layout, locale) cell, 60/20/20."""
    rng = random.Random(seed)
    cells: dict[tuple[str, str], list[int]] = {}
    for idx, combo in enumerate(combos):
        cells.setdefault(combo, []).append(idx)
    result = [""] * len(combos)
    for combo in sorted(cells):
        members = cells[combo]
        rng.shuffle(members)
        n = len(members)
        n_dev = round(n * SPLIT_RATIOS[0][1])
        n_tune = round(n * SPLIT_RATIOS[1][1])
        for pos, idx in enumerate(members):
            result[idx] = (
                "development" if pos < n_dev else "tuning" if pos < n_dev + n_tune else "heldout"
            )
    return result


def pdf_text(path: Path) -> str:
    doc = pymupdf.open(path)
    text = " ".join(page.get_text() for page in doc)
    doc.close()
    return " ".join(text.split())


def check_against_pdf(g: GeneratedInvoice, text: str) -> list[str]:
    """Return a list of problems (empty = the PDF matches its answer key)."""
    locale = get_locale(g.locale_code)
    t = g.truth
    problems = []

    def need(label: str, fragment: str) -> None:
        if fragment not in text:
            problems.append(f"missing {label}: {fragment!r}")

    need("invoice_number", t.invoice_number)
    need("supplier_name", t.supplier_name)
    need("invoice_date", format_date(date.fromisoformat(t.invoice_date), locale))
    need("tax_amount", format_money(t.tax_amount, locale))
    need("total_amount", format_money(t.total_amount, locale))
    for item in t.line_items:
        row = (
            f"{item.description} {format_quantity(item.quantity, locale)} "
            f"{format_money(item.unit_price, locale)} {format_money(item.line_total, locale)}"
        )
        need("line item", row)
    if t.supplier_tax_id is None:
        if locale.labels["tax_id"] in text:
            problems.append("tax id is null but its label is printed")
    else:
        need("supplier_tax_id", t.supplier_tax_id)
    if t.due_date is None and locale.labels["due_date"] in text:
        problems.append("due date is null but its label is printed")
    return problems


def build_dataset(root: Path, n: int = 120, seed: int = 2026) -> dict:
    pdf_dir = root / "data" / "synthetic" / "pdf"
    truth_dir = root / "data" / "ground_truth"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    truth_dir.mkdir(parents=True, exist_ok=True)

    combos = plan(n)
    splits = assign_splits(combos, seed)
    rows, failures = [], {}
    for i, (layout, locale_code) in enumerate(combos, start=1):
        iid = invoice_id(i)
        rng = random.Random(seed * 100_000 + i)
        g = generate_invoice(rng, locale_code)
        pdf_path = pdf_dir / f"{iid}.pdf"
        render(layout, g, pdf_path)
        (truth_dir / f"{iid}.json").write_text(
            json.dumps(g.truth.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        problems = check_against_pdf(g, pdf_text(pdf_path))
        if problems:
            failures[iid] = problems
        rows.append(
            {
                "invoice_id": iid,
                "layout": layout,
                "locale": locale_code,
                "split": splits[i - 1],
                "n_items": len(g.truth.line_items),
                "has_tax_id": g.truth.supplier_tax_id is not None,
                "has_due_date": g.truth.due_date is not None,
                "has_subtotal": g.truth.subtotal is not None,
            }
        )
    with (root / "data" / "split.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return {"rows": rows, "failures": failures}