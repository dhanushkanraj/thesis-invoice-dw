"""PDF rendering of synthetic invoices (ReportLab).

Layout 1 ("classic"): supplier block top-left, invoice details top-right,
buyer address, item table, totals block at the right, footer with page number.

Rule: a field that is None in the ground truth is NOT printed (neither label
nor value), so the PDF always agrees with its answer key.
"""
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4, LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from invoice_pipeline.fakedata import GeneratedInvoice
from invoice_pipeline.formats import (
    format_date,
    format_money,
    format_number,
    get_locale,
)

FONT = "Helvetica"
FONT_BOLD = "Helvetica-Bold"


def _esc(text: str) -> str:
    """Escape text for ReportLab Paragraph markup."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def format_quantity(value: float, locale) -> str:
    """12 -> '12'; 7.5 -> '7,5' (de) or '7.5' (others)."""
    if float(value).is_integer():
        return format_number(value, locale, 0)
    return format_number(value, locale, 1)


def page_size_for(locale_code: str):
    return LETTER if locale_code == "us" else A4


def render_classic(g: GeneratedInvoice, path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    locale = get_locale(g.locale_code)
    labels = locale.labels
    t = g.truth
    x = g.extras
    money = lambda v: format_money(v, locale)  # noqa: E731

    body = ParagraphStyle("body", fontName=FONT, fontSize=9, leading=12)
    small = ParagraphStyle("small", parent=body, fontSize=8, leading=10)
    right = ParagraphStyle("right", parent=body, alignment=TA_RIGHT)
    bold_right = ParagraphStyle("bold_right", parent=right, fontName=FONT_BOLD)
    name_style = ParagraphStyle("name", fontName=FONT_BOLD, fontSize=14, leading=18)
    title_style = ParagraphStyle("title", fontName=FONT_BOLD, fontSize=20, leading=24, alignment=TA_RIGHT)

    story = []

    # Header: supplier left, invoice details right
    supplier_lines = [Paragraph(_esc(t.supplier_name), name_style)]
    for line in x.supplier_address:
        supplier_lines.append(Paragraph(_esc(line), body))
    if t.supplier_tax_id is not None:
        supplier_lines.append(Paragraph(f"{_esc(labels['tax_id'])}: {_esc(t.supplier_tax_id)}", body))

    detail_lines = [Paragraph(_esc(labels["title"]), title_style), Spacer(1, 6)]
    detail_lines.append(Paragraph(f"{_esc(labels['invoice_number'])}: {_esc(t.invoice_number)}", right))
    detail_lines.append(
        Paragraph(
            f"{_esc(labels['invoice_date'])}: {format_date(date.fromisoformat(t.invoice_date), locale)}",
            right,
        )
    )
    if t.due_date is not None:
        detail_lines.append(
            Paragraph(
                f"{_esc(labels['due_date'])}: {format_date(date.fromisoformat(t.due_date), locale)}",
                right,
            )
        )
    detail_lines.append(Paragraph(f"{_esc(labels['customer_number'])}: {_esc(x.customer_number)}", right))
    detail_lines.append(Paragraph(f"{_esc(labels['purchase_order'])}: {_esc(x.purchase_order)}", right))

    header = Table([[supplier_lines, detail_lines]], colWidths=[9 * cm, 8 * cm])
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [header, Spacer(1, 18)]

    # Buyer address block
    story.append(Paragraph(_esc(x.buyer_name), ParagraphStyle("buyer", parent=body, fontName=FONT_BOLD)))
    for line in x.buyer_address:
        story.append(Paragraph(_esc(line), body))
    story.append(Spacer(1, 22))

    # Item table
    head_style = ParagraphStyle("head", parent=body, fontName=FONT_BOLD)
    head_right = ParagraphStyle("head_right", parent=head_style, alignment=TA_RIGHT)
    rows = [
        [
            Paragraph(_esc(labels["description"]), head_style),
            Paragraph(_esc(labels["quantity"]), head_right),
            Paragraph(_esc(labels["unit_price"]), head_right),
            Paragraph(_esc(labels["line_total"]), head_right),
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
                ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.black),
                ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.lightgrey),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story += [items, Spacer(1, 14)]

    # Totals block (subtotal row only if present in the ground truth)
    total_rows = []
    if t.subtotal is not None:
        total_rows.append([Paragraph(_esc(labels["subtotal"]), right), Paragraph(_esc(money(t.subtotal)), right)])
    total_rows.append([Paragraph(_esc(labels["tax"]), right), Paragraph(_esc(money(t.tax_amount)), right)])
    total_rows.append(
        [Paragraph(_esc(labels["total"]), bold_right), Paragraph(_esc(money(t.total_amount)), bold_right)]
    )
    totals = Table(total_rows, colWidths=[4 * cm, 3.7 * cm], hAlign="RIGHT")
    totals.setStyle(TableStyle([("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.black)]))
    story.append(totals)

    if x.iban is not None:
        story += [Spacer(1, 26), Paragraph(f"IBAN: {_esc(x.iban)}", small)]

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(FONT, 8)
        canvas.drawString(doc.leftMargin, 1.2 * cm, t.supplier_name)
        canvas.drawRightString(
            doc.pagesize[0] - doc.rightMargin, 1.2 * cm, f"{labels['page']} {canvas.getPageNumber()}"
        )
        canvas.restoreState()

    doc = SimpleDocTemplate(
        str(path),
        pagesize=page_size_for(g.locale_code),
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title=f"{labels['title']} {t.invoice_number}",
        author=t.supplier_name,
        invariant=1,  # no timestamps or random IDs: same input gives identical bytes
    )
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return path