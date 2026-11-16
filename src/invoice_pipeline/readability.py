"""How much of an invoice's answer key can be found in a text? (a measure of OCR quality)

The answer key's values are formatted the way the invoice prints them (locale) and searched in
the text. Currency symbols are ignored, because the extraction does not depend on them.
A 'fact' is one value: invoice number, supplier name, tax id, dates, the three totals, and for
every line item its description, unit price and line total.
"""
from datetime import date

from invoice_pipeline.formats import format_date, format_number, get_locale


def facts(truth: dict, locale_code: str) -> list[tuple[str, str]]:
    locale = get_locale(locale_code)
    out = []
    for key in ("invoice_number", "supplier_name", "supplier_tax_id"):
        if truth.get(key) is not None:
            out.append((key, truth[key]))
    for key in ("invoice_date", "due_date"):
        if truth.get(key) is not None:
            out.append((key, format_date(date.fromisoformat(truth[key]), locale)))
    for key in ("subtotal", "tax_amount", "total_amount"):
        if truth.get(key) is not None:
            out.append((key, format_number(truth[key], locale)))
    for item in truth.get("line_items", []):
        out.append(("item_description", item["description"]))
        out.append(("item_unit_price", format_number(item["unit_price"], locale)))
        out.append(("item_line_total", format_number(item["line_total"], locale)))
    return out


def readability(truth: dict, locale_code: str, lines: list[str]) -> dict:
    text = " ".join(" ".join(lines).split())
    found = [(name, value in text) for name, value in facts(truth, locale_code)]
    n_found = sum(ok for _, ok in found)
    return {"found": n_found, "total": len(found), "all_found": n_found == len(found),
            "missed": [name for name, ok in found if not ok]}
