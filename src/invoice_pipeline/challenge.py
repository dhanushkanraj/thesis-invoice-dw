"""Challenge set: invoices in a 4th layout ("ledger") with different label wording.

The development and tuning sets were used to build and tune M1 and the prompt,
and the held-out set has the same three layouts and the same wording. The
challenge set asks a harder question: how do the methods cope with a layout and
with label words they have never seen? It is used once, at the final evaluation.

What is different from the three known layouts
  * the customer ("Billed to") is printed first; the issuer ("Issued by") only in the footer
  * the totals come BEFORE the item table, in a shaded box, left-aligned
  * every label uses other words (Document No., Issued, Payable by, Rate, Amount Due, ...)
Dates, number formats and currencies are unchanged, so what is measured is the
layout and the wording together, nothing else. (The two effects cannot be
separated with this set; say so in the thesis.)

Same rule as the other layouts: a field that is None in the ground truth is NOT
printed (neither label nor value).
"""
import json
import random
from dataclasses import replace
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from invoice_pipeline.dataset import (
    LOCALE_ORDER,
    check_against_pdf,
    pdf_text,
    read_split_rows,
    write_split_rows,
)
from invoice_pipeline.fakedata import GeneratedInvoice, generate_invoice
from invoice_pipeline.formats import Locale, format_date, format_money, get_locale
from invoice_pipeline.render import FONT, FONT_BOLD, _esc, format_quantity, page_size_for
from invoice_pipeline.scan import PROFILES, assign_profiles, make_scan

CHALLENGE_LAYOUT = "ledger"
CHALLENGE_SPLIT = "challenge"
CHALLENGE_SEED = 3030  # different from the main dataset seed (2026)
DEFAULT_N = 40

_DE = {
    "title": "Rechnungsbeleg", "invoice_number": "Beleg-Nr.", "invoice_date": "Ausstellungsdatum",
    "due_date": "Zahlbar bis", "tax_id": "Umsatzsteuer-ID", "purchase_order": "Ihre Bestellung",
    "customer_number": "Kunden-Nr.", "description": "Leistung", "quantity": "Anzahl",
    "unit_price": "Stückpreis", "line_total": "Betrag", "subtotal": "Nettosumme",
    "tax": "Umsatzsteuer", "total": "Rechnungsbetrag", "page": "Blatt",
}
_EN = {
    "title": "Tax Invoice", "invoice_number": "Document No.", "invoice_date": "Issued",
    "due_date": "Payable by", "tax_id": "Tax Reg. No.", "purchase_order": "Your Ref.",
    "customer_number": "Account No.", "description": "Item", "quantity": "Units",
    "unit_price": "Rate", "line_total": "Net Amount", "subtotal": "Net Total",
    "tax": "VAT", "total": "Amount Due", "page": "Sheet",
}
CHALLENGE_LABELS = {
    "de": _DE,
    "en_eu": dict(_EN),
    "uk": dict(_EN),
    "us": {**_EN, "tax": "Sales Tax"},
}
EXTRA_LABELS = {
    "de": {"billed_to": "Rechnungsempfänger", "issued_by": "Ausgestellt von"},
    "en": {"billed_to": "Billed to", "issued_by": "Issued by"},
}

SHADE = colors.HexColor("#FFF6DD")


def challenge_id(i: int) -> str:
    return f"ch_{i:04d}"


def challenge_plan(n: int) -> list[tuple[str, str]]:
    """(layout, locale) for challenge invoice 1..n; locales are cycled evenly."""
    return [(CHALLENGE_LAYOUT, LOCALE_ORDER[i % len(LOCALE_ORDER)]) for i in range(n)]


def challenge_locale(code: str) -> Locale:
    """The normal locale (money, date formats, currency) with the challenge label wording."""
    return replace(get_locale(code), labels=CHALLENGE_LABELS[code])


def render_ledger(g: GeneratedInvoice, path, locale: Locale | None = None) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    locale = locale or get_locale(g.locale_code)
    labels = locale.labels
    extra = EXTRA_LABELS["de" if g.locale_code == "de" else "en"]
    t, x = g.truth, g.extras
    money = lambda v: format_money(v, locale)  # noqa: E731

    body = ParagraphStyle("body", fontName=FONT, fontSize=9, leading=12)
    bold = ParagraphStyle("bold", parent=body, fontName=FONT_BOLD)
    muted = ParagraphStyle("muted", parent=body, fontSize=7.5, leading=9, textColor=colors.grey)
    right = ParagraphStyle("right", parent=body, alignment=TA_RIGHT)
    bold_right = ParagraphStyle("bold_right", parent=right, fontName=FONT_BOLD, fontSize=10.5, leading=13)
    bold_big = ParagraphStyle("bold_big", parent=bold, fontSize=10.5, leading=13)
    title = ParagraphStyle("title", fontName=FONT_BOLD, fontSize=18, leading=22)

    story = [Paragraph(_esc(labels["title"]), title), Spacer(1, 16)]

    # Meta list (left) and customer block (right)
    meta_rows = [
        (labels["invoice_number"], t.invoice_number),
        (labels["invoice_date"], format_date(date.fromisoformat(t.invoice_date), locale)),
    ]
    if t.due_date is not None:
        meta_rows.append((labels["due_date"], format_date(date.fromisoformat(t.due_date), locale)))
    meta_rows.append((labels["customer_number"], x.customer_number))
    meta_rows.append((labels["purchase_order"], x.purchase_order))
    meta = Table(
        [[Paragraph(_esc(a), muted), Paragraph(_esc(b), bold)] for a, b in meta_rows],
        colWidths=[3.6 * cm, 4.6 * cm],
    )
    meta.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))

    customer = [Paragraph(_esc(extra["billed_to"]), muted), Paragraph(_esc(x.buyer_name), bold)]
    customer += [Paragraph(_esc(line), body) for line in x.buyer_address]
    top = Table([[meta, customer]], colWidths=[8.6 * cm, 8.4 * cm])
    top.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [top, Spacer(1, 18)]

    # Totals FIRST, left-aligned in a shaded box
    sum_rows = []
    if t.subtotal is not None:
        sum_rows.append([Paragraph(_esc(labels["subtotal"]), body), Paragraph(_esc(money(t.subtotal)), right)])
    sum_rows.append([Paragraph(_esc(labels["tax"]), body), Paragraph(_esc(money(t.tax_amount)), right)])
    sum_rows.append([Paragraph(_esc(labels["total"]), bold_big), Paragraph(_esc(money(t.total_amount)), bold_right)])
    summary = Table(sum_rows, colWidths=[4.6 * cm, 4.0 * cm], hAlign="LEFT")
    summary.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), SHADE),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#D9C58A")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story += [summary, Spacer(1, 20)]

    # Item table with only a top and a bottom rule
    rows = [
        [
            Paragraph(_esc(labels["description"]), bold),
            Paragraph(_esc(labels["quantity"]), ParagraphStyle("hr", parent=bold, alignment=TA_RIGHT)),
            Paragraph(_esc(labels["unit_price"]), ParagraphStyle("hr2", parent=bold, alignment=TA_RIGHT)),
            Paragraph(_esc(labels["line_total"]), ParagraphStyle("hr3", parent=bold, alignment=TA_RIGHT)),
        ]
    ]
    for item in t.line_items:
        rows.append(
            [
                Paragraph(_esc(item.description), body),
                Paragraph(format_quantity(item.quantity, locale), right),
                Paragraph(_esc(money(item.unit_price)), right),
                Paragraph(_esc(money(item.line_total)), right),
            ]
        )
    items = Table(rows, colWidths=[7.4 * cm, 2.2 * cm, 3.7 * cm, 3.7 * cm], repeatRows=1)
    items.setStyle(
        TableStyle(
            [
                ("LINEABOVE", (0, 0), (-1, 0), 0.8, colors.black),
                ("LINEBELOW", (0, 0), (-1, 0), 0.4, colors.grey),
                ("LINEBELOW", (0, -1), (-1, -1), 0.8, colors.black),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(items)

    # Issuer block in the footer of every page
    issuer = [t.supplier_name, *x.supplier_address]
    if t.supplier_tax_id is not None:
        issuer.append(f"{labels['tax_id']}: {t.supplier_tax_id}")
    if x.iban is not None:
        issuer.append(f"IBAN: {x.iban}")
    line_gap = 0.4 * cm
    block_top = 1.9 * cm + line_gap * (len(issuer) + 1)

    def footer(canvas, doc):
        canvas.saveState()
        y = block_top
        canvas.setFont(FONT, 7.5)
        canvas.setFillColor(colors.grey)
        canvas.drawString(doc.leftMargin, y, extra["issued_by"])
        canvas.setFillColor(colors.black)
        for k, line in enumerate(issuer):
            y -= line_gap
            canvas.setFont(FONT_BOLD if k == 0 else FONT, 9 if k == 0 else 8.5)
            canvas.drawString(doc.leftMargin, y, line)
        canvas.setFont(FONT, 8)
        canvas.drawRightString(doc.pagesize[0] - doc.rightMargin, 1.2 * cm, f"{labels['page']} {canvas.getPageNumber()}")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        str(path),
        pagesize=page_size_for(g.locale_code),
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=block_top + 0.6 * cm,
        title=f"{labels['title']} {t.invoice_number}",
        author=t.supplier_name,
        invariant=1,
    )
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return path


def build_challenge(root: Path, n: int = DEFAULT_N, seed: int = CHALLENGE_SEED) -> dict:
    """Write the challenge PDFs and answer keys, add their rows to data/split.csv.

    The 120 original invoices are not touched. Running it again replaces only
    the challenge files and challenge rows.
    """
    pdf_dir = root / "data" / "synthetic" / "pdf"
    truth_dir = root / "data" / "ground_truth"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    truth_dir.mkdir(parents=True, exist_ok=True)

    combos = challenge_plan(n)
    profiles = assign_profiles(combos)
    rows, failures = [], {}
    for i, ((layout, locale_code), profile) in enumerate(zip(combos, profiles), start=1):
        iid = challenge_id(i)
        rng = random.Random(seed * 100_000 + i)
        g = generate_invoice(rng, locale_code)
        locale = challenge_locale(locale_code)
        pdf_path = pdf_dir / f"{iid}.pdf"
        render_ledger(g, pdf_path, locale)
        (truth_dir / f"{iid}.json").write_text(
            json.dumps(g.truth.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        problems = check_against_pdf(g, pdf_text(pdf_path), labels=locale.labels)
        if problems:
            failures[iid] = problems
        rows.append(
            {
                "invoice_id": iid,
                "layout": layout,
                "locale": locale_code,
                "split": CHALLENGE_SPLIT,
                "n_items": len(g.truth.line_items),
                "has_tax_id": g.truth.supplier_tax_id is not None,
                "has_due_date": g.truth.due_date is not None,
                "has_subtotal": g.truth.subtotal is not None,
                "scan_profile": profile,
            }
        )

    kept = [r for r in read_split_rows(root) if r.get("split") != CHALLENGE_SPLIT]
    write_split_rows(root, kept + rows)
    return {"rows": rows, "failures": failures}


def build_challenge_scans(root: Path, rows: list[dict], seed: int = CHALLENGE_SEED) -> None:
    pdf_dir = root / "data" / "synthetic" / "pdf"
    scan_dir = root / "data" / "synthetic" / "scanned"
    scan_dir.mkdir(parents=True, exist_ok=True)
    for row in rows:
        i = int(row["invoice_id"].split("_")[1])
        make_scan(
            pdf_dir / f"{row['invoice_id']}.pdf",
            scan_dir / f"{row['invoice_id']}.pdf",
            PROFILES[row["scan_profile"]],
            seed * 100_000 + i,
        )
