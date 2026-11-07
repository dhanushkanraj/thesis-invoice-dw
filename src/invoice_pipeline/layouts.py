"""Additional invoice layouts and the layout registry.

Layout 2 ("modern"):  coloured banner with supplier name and address, bill-to
                      block plus a label/value grid, striped item table, tax ID
                      and IBAN in the footer.
Layout 3 ("twocol"):  From/To address blocks side by side, a meta row with
                      labels above values, item table with a position column,
                      payment block at the bottom.

Same rule as the classic layout: a field that is None in the ground truth is
NOT printed (neither label nor value).
"""
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from invoice_pipeline.fakedata import GeneratedInvoice
from invoice_pipeline.formats import format_date, format_money, get_locale
from invoice_pipeline.render import (
    FONT,
    FONT_BOLD,
    _esc,
    format_quantity,
    page_size_for,
    render_classic,
)

BRAND = colors.HexColor("#1F4E5F")
STRIPE = colors.HexColor("#F2F6F8")

# Labels used only by these layouts (the shared label sets live in formats.py).
EXTRA_LABELS = {
    "de": {"bill_to": "Rechnung an", "from": "Von", "to": "An", "pos": "Pos.", "payment": "Zahlungsinformationen"},
    "en": {"bill_to": "Bill to", "from": "From", "to": "To", "pos": "No.", "payment": "Payment details"},
}


def _extra(locale_code: str) -> dict:
    return EXTRA_LABELS["de" if locale_code == "de" else "en"]


def _styles():
    body = ParagraphStyle("body", fontName=FONT, fontSize=9, leading=12)
    return {
        "body": body,
        "bold": ParagraphStyle("bold", parent=body, fontName=FONT_BOLD),
        "muted": ParagraphStyle("muted", parent=body, fontSize=7.5, leading=9, textColor=colors.grey),
        "right": ParagraphStyle("right", parent=body, alignment=TA_RIGHT),
        "bold_right": ParagraphStyle("bold_right", parent=body, fontName=FONT_BOLD, alignment=TA_RIGHT),
        "head_white": ParagraphStyle("head_white", parent=body, fontName=FONT_BOLD, textColor=colors.white),
        "head_white_right": ParagraphStyle(
            "head_white_right", parent=body, fontName=FONT_BOLD, textColor=colors.white, alignment=TA_RIGHT
        ),
        "title": ParagraphStyle("title", fontName=FONT_BOLD, fontSize=20, leading=24),
    }


def _build(path, g, story, top_margin_cm, first_page, later_pages):
    t = g.truth
    labels = get_locale(g.locale_code).labels
    doc = SimpleDocTemplate(
        str(path),
        pagesize=page_size_for(g.locale_code),
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=top_margin_cm * cm,
        bottomMargin=2.6 * cm,
        title=f"{labels['title']} {t.invoice_number}",
        author=t.supplier_name,
        invariant=1,  # identical bytes for identical input
    )
    doc.build(story, onFirstPage=first_page, onLaterPages=later_pages)
    return path


def render_modern(g: GeneratedInvoice, path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    locale = get_locale(g.locale_code)
    labels = locale.labels
    extra = _extra(g.locale_code)
    t, x, s = g.truth, g.extras, _styles()
    money = lambda v: format_money(v, locale)  # noqa: E731

    # Bill-to block (left) and label/value grid (right)
    bill_to = [Paragraph(_esc(extra["bill_to"]), s["muted"]), Paragraph(_esc(x.buyer_name), s["bold"])]
    bill_to += [Paragraph(_esc(line), s["body"]) for line in x.buyer_address]

    grid_rows = [
        [Paragraph(_esc(labels["invoice_number"]), s["muted"]), Paragraph(_esc(t.invoice_number), s["right"])],
        [
            Paragraph(_esc(labels["invoice_date"]), s["muted"]),
            Paragraph(format_date(date.fromisoformat(t.invoice_date), locale), s["right"]),
        ],
    ]
    if t.due_date is not None:
        grid_rows.append(
            [
                Paragraph(_esc(labels["due_date"]), s["muted"]),
                Paragraph(format_date(date.fromisoformat(t.due_date), locale), s["right"]),
            ]
        )
    grid_rows.append([Paragraph(_esc(labels["customer_number"]), s["muted"]), Paragraph(_esc(x.customer_number), s["right"])])
    grid_rows.append([Paragraph(_esc(labels["purchase_order"]), s["muted"]), Paragraph(_esc(x.purchase_order), s["right"])])
    grid = Table(grid_rows, colWidths=[3.6 * cm, 4.4 * cm])
    grid.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))

    top = Table([[bill_to, grid]], colWidths=[9 * cm, 8 * cm])
    top.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))

    # Item table with coloured header and striped rows
    rows = [
        [
            Paragraph(_esc(labels["description"]), s["head_white"]),
            Paragraph(_esc(labels["quantity"]), s["head_white_right"]),
            Paragraph(_esc(labels["unit_price"]), s["head_white_right"]),
            Paragraph(_esc(labels["line_total"]), s["head_white_right"]),
        ]
    ]
    for item in t.line_items:
        rows.append(
            [
                Paragraph(_esc(item.description), s["body"]),
                Paragraph(format_quantity(item.quantity, locale), s["right"]),
                Paragraph(_esc(money(item.unit_price)), s["right"]),
                Paragraph(_esc(money(item.line_total)), s["right"]),
            ]
        )
    items = Table(rows, colWidths=[7.4 * cm, 2.2 * cm, 3.7 * cm, 3.7 * cm], repeatRows=1)
    items.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), BRAND),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, STRIPE]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )

    # Totals with the grand total in a coloured box
    total_rows = []
    if t.subtotal is not None:
        total_rows.append([Paragraph(_esc(labels["subtotal"]), s["right"]), Paragraph(_esc(money(t.subtotal)), s["right"])])
    total_rows.append([Paragraph(_esc(labels["tax"]), s["right"]), Paragraph(_esc(money(t.tax_amount)), s["right"])])
    total_rows.append(
        [
            Paragraph(_esc(labels["total"]), s["head_white_right"]),
            Paragraph(_esc(money(t.total_amount)), s["head_white_right"]),
        ]
    )
    totals = Table(total_rows, colWidths=[4 * cm, 3.7 * cm], hAlign="RIGHT")
    totals.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, -1), (-1, -1), BRAND),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )

    story = [top, Spacer(1, 24), items, Spacer(1, 14), totals]

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(FONT, 8)
        canvas.setFillColor(colors.black)
        info = []
        if t.supplier_tax_id is not None:
            info.append(f"{labels['tax_id']}: {t.supplier_tax_id}")
        if x.iban is not None:
            info.append(f"IBAN: {x.iban}")
        if info:
            canvas.drawString(doc.leftMargin, 1.8 * cm, "   |   ".join(info))
        canvas.drawString(doc.leftMargin, 1.2 * cm, t.supplier_name)
        canvas.drawRightString(doc.pagesize[0] - doc.rightMargin, 1.2 * cm, f"{labels['page']} {canvas.getPageNumber()}")
        canvas.restoreState()

    def first_page(canvas, doc):
        w, h = doc.pagesize
        canvas.saveState()
        canvas.setFillColor(BRAND)
        canvas.rect(0, h - 3.4 * cm, w, 3.4 * cm, stroke=0, fill=1)
        canvas.setFillColor(colors.white)
        canvas.setFont(FONT_BOLD, 18)
        canvas.drawString(doc.leftMargin, h - 1.5 * cm, t.supplier_name)
        canvas.setFont(FONT, 8.5)
        y = h - 2.15 * cm
        for line in x.supplier_address:
            canvas.drawString(doc.leftMargin, y, line)
            y -= 0.42 * cm
        canvas.setFont(FONT_BOLD, 22)
        canvas.drawRightString(w - doc.rightMargin, h - 1.7 * cm, labels["title"])
        canvas.restoreState()
        footer(canvas, doc)

    return _build(path, g, story, 4.4, first_page, footer)


def render_twocol(g: GeneratedInvoice, path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    locale = get_locale(g.locale_code)
    labels = locale.labels
    extra = _extra(g.locale_code)
    t, x, s = g.truth, g.extras, _styles()
    money = lambda v: format_money(v, locale)  # noqa: E731

    story = [Paragraph(_esc(labels["title"]), s["title"]), Spacer(1, 14)]

    # From / To blocks side by side
    from_block = [Paragraph(_esc(extra["from"]), s["muted"]), Paragraph(_esc(t.supplier_name), s["bold"])]
    from_block += [Paragraph(_esc(line), s["body"]) for line in x.supplier_address]
    if t.supplier_tax_id is not None:
        from_block.append(Paragraph(f"{_esc(labels['tax_id'])}: {_esc(t.supplier_tax_id)}", s["body"]))
    to_block = [Paragraph(_esc(extra["to"]), s["muted"]), Paragraph(_esc(x.buyer_name), s["bold"])]
    to_block += [Paragraph(_esc(line), s["body"]) for line in x.buyer_address]
    blocks = Table([[from_block, to_block]], colWidths=[8.5 * cm, 8.5 * cm])
    blocks.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.lightgrey)]))
    story += [blocks, Spacer(1, 14)]

    # Meta row: labels above values; the due-date cell exists only if present
    cells = [
        (labels["invoice_number"], t.invoice_number),
        (labels["invoice_date"], format_date(date.fromisoformat(t.invoice_date), locale)),
    ]
    if t.due_date is not None:
        cells.append((labels["due_date"], format_date(date.fromisoformat(t.due_date), locale)))
    cells.append((labels["customer_number"], x.customer_number))
    cells.append((labels["purchase_order"], x.purchase_order))
    width = 17 * cm / len(cells)
    meta = Table(
        [
            [Paragraph(_esc(label), s["muted"]) for label, _ in cells],
            [Paragraph(_esc(value), s["bold"]) for _, value in cells],
        ],
        colWidths=[width] * len(cells),
    )
    meta.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, colors.lightgrey), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [meta, Spacer(1, 18)]

    # Items with a position column
    rows = [
        [
            Paragraph(_esc(extra["pos"]), s["bold"]),
            Paragraph(_esc(labels["description"]), s["bold"]),
            Paragraph(_esc(labels["quantity"]), s["bold_right"]),
            Paragraph(_esc(labels["unit_price"]), s["bold_right"]),
            Paragraph(_esc(labels["line_total"]), s["bold_right"]),
        ]
    ]
    for i, item in enumerate(t.line_items, start=1):
        rows.append(
            [
                Paragraph(str(i), s["body"]),
                Paragraph(_esc(item.description), s["body"]),
                Paragraph(format_quantity(item.quantity, locale), s["right"]),
                Paragraph(_esc(money(item.unit_price)), s["right"]),
                Paragraph(_esc(money(item.line_total)), s["right"]),
            ]
        )
    items = Table(rows, colWidths=[1.2 * cm, 6.4 * cm, 2.0 * cm, 3.7 * cm, 3.7 * cm], repeatRows=1)
    items.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EDEDED")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story += [items, Spacer(1, 12)]

    # Totals, boxed
    total_rows = []
    if t.subtotal is not None:
        total_rows.append([Paragraph(_esc(labels["subtotal"]), s["right"]), Paragraph(_esc(money(t.subtotal)), s["right"])])
    total_rows.append([Paragraph(_esc(labels["tax"]), s["right"]), Paragraph(_esc(money(t.tax_amount)), s["right"])])
    total_rows.append([Paragraph(_esc(labels["total"]), s["bold_right"]), Paragraph(_esc(money(t.total_amount)), s["bold_right"])])
    totals = Table(total_rows, colWidths=[4 * cm, 3.7 * cm], hAlign="RIGHT")
    totals.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, colors.grey), ("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.black)]))
    story.append(totals)

    if x.iban is not None:
        story += [
            Spacer(1, 24),
            Paragraph(_esc(extra["payment"]), s["bold"]),
            Paragraph(f"IBAN: {_esc(x.iban)}", s["body"]),
        ]

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(FONT, 8)
        canvas.drawCentredString(doc.pagesize[0] / 2, 1.2 * cm, f"{labels['page']} {canvas.getPageNumber()}")
        canvas.restoreState()

    return _build(path, g, story, 2, footer, footer)


LAYOUTS = {
    "classic": render_classic,
    "modern": render_modern,
    "twocol": render_twocol,
}


def render(layout: str, g: GeneratedInvoice, path) -> Path:
    try:
        func = LAYOUTS[layout]
    except KeyError:
        raise ValueError(f"Unknown layout {layout!r}. Available: {sorted(LAYOUTS)}") from None
    return func(g, path)