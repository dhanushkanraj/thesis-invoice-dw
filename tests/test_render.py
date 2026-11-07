import random
from datetime import date

import pymupdf
import pytest

from invoice_pipeline.fakedata import GeneratedInvoice, PrintExtras, generate_invoice
from invoice_pipeline.formats import LOCALES, format_date, format_money, get_locale
from invoice_pipeline.render import format_quantity, page_size_for, render_classic
from invoice_pipeline.schema import Invoice, LineItem

ALL_LOCALES = sorted(LOCALES)


def pdf_text(path) -> str:
    """All text of the PDF, whitespace-normalised to single spaces."""
    doc = pymupdf.open(path)
    text = " ".join(page.get_text() for page in doc)
    doc.close()
    return " ".join(text.split())


def fixed_invoice(**overrides) -> GeneratedInvoice:
    truth = Invoice(
        invoice_number="RE-2025-0042",
        supplier_name="Müller Bürotechnik GmbH",
        supplier_tax_id="DE123456789",
        invoice_date="2025-03-14",
        due_date="2025-04-13",
        currency="EUR",
        subtotal=1234.56,
        tax_amount=234.57,
        total_amount=1469.13,
        line_items=[
            LineItem(description="Monitor 27 Zoll", quantity=2, unit_price=617.28, line_total=1234.56)
        ],
    )
    if overrides:
        truth = truth.model_copy(update=overrides)
    extras = PrintExtras(
        supplier_address=("Hauptstraße 1", "10115 Berlin"),
        buyer_name="Nordlicht Handels GmbH",
        buyer_address=("Gartenweg 2", "50667 Köln"),
        purchase_order="BE-2025-1111",
        customer_number="KD-22222",
        iban="DE12 3456 7890 1234 5678 90",
    )
    return GeneratedInvoice(locale_code="de", truth=truth, extras=extras)


def test_known_german_invoice_prints_expected_strings(tmp_path):
    text = pdf_text(render_classic(fixed_invoice(), tmp_path / "a.pdf"))
    for expected in [
        "Müller Bürotechnik GmbH",
        "Rechnungsnummer: RE-2025-0042",
        "Rechnungsdatum: 14.03.2025",
        "Fällig am: 13.04.2025",
        "USt-IdNr.: DE123456789",
        "Monitor 27 Zoll 2 617,28 € 1.234,56 €",
        "Zwischensumme 1.234,56 €",
        "MwSt. 234,57 €",
        "Gesamtbetrag 1.469,13 €",
    ]:
        assert expected in text, f"missing in PDF: {expected!r}"


def test_missing_fields_are_not_printed(tmp_path):
    g = fixed_invoice(due_date=None, supplier_tax_id=None, subtotal=None)
    text = pdf_text(render_classic(g, tmp_path / "b.pdf"))
    assert "Fällig am" not in text
    assert "13.04.2025" not in text
    assert "USt-IdNr." not in text
    assert "DE123456789" not in text
    assert "Zwischensumme" not in text
    assert "Gesamtbetrag 1.469,13 €" in text


def test_special_characters_survive(tmp_path):
    g = fixed_invoice(supplier_name="Schmidt & Söhne <Export> GmbH")
    assert "Schmidt & Söhne <Export> GmbH" in pdf_text(render_classic(g, tmp_path / "c.pdf"))


@pytest.mark.parametrize("code", ALL_LOCALES)
def test_every_truth_value_is_printed_in_the_pdf(code, tmp_path):
    locale = get_locale(code)
    rng = random.Random(100)
    for i in range(25):
        g = generate_invoice(rng, code)
        t = g.truth
        text = pdf_text(render_classic(g, tmp_path / f"{code}_{i}.pdf"))
        assert t.invoice_number in text
        assert t.supplier_name in text
        assert format_date(date.fromisoformat(t.invoice_date), locale) in text
        for value in (t.tax_amount, t.total_amount):
            assert format_money(value, locale) in text
        for item in t.line_items:
            row = (
                f"{item.description} {format_quantity(item.quantity, locale)} "
                f"{format_money(item.unit_price, locale)} {format_money(item.line_total, locale)}"
            )
            assert row in text, f"row missing: {row!r}"
        # a field that is null in the truth must not be printed
        if t.supplier_tax_id is None:
            assert locale.labels["tax_id"] not in text
        else:
            assert t.supplier_tax_id in text
        if t.due_date is None:
            assert locale.labels["due_date"] not in text
        else:
            assert format_date(date.fromisoformat(t.due_date), locale) in text
        if t.subtotal is None:
            assert locale.labels["subtotal"] not in text
        else:
            assert format_money(t.subtotal, locale) in text


def test_same_input_gives_identical_bytes(tmp_path):
    g = generate_invoice(random.Random(5), "de")
    a = render_classic(g, tmp_path / "one.pdf").read_bytes()
    b = render_classic(g, tmp_path / "two.pdf").read_bytes()
    assert a == b


def test_page_sizes(tmp_path):
    de_pdf = render_classic(generate_invoice(random.Random(1), "de"), tmp_path / "de.pdf")
    us_pdf = render_classic(generate_invoice(random.Random(1), "us"), tmp_path / "us.pdf")
    with pymupdf.open(de_pdf) as d:
        assert round(d[0].rect.width) == 595 and round(d[0].rect.height) == 842
    with pymupdf.open(us_pdf) as d:
        assert round(d[0].rect.width) == 612 and round(d[0].rect.height) == 792
    assert page_size_for("uk") != page_size_for("us")


def test_format_quantity():
    de, us = get_locale("de"), get_locale("us")
    assert format_quantity(12, de) == "12"
    assert format_quantity(7.5, de) == "7,5"
    assert format_quantity(7.5, us) == "7.5"
    assert format_quantity(1234.0, de) == "1.234"


def test_fifteen_items_render(tmp_path):
    g = generate_invoice(random.Random(8), "uk", n_items=15)
    text = pdf_text(render_classic(g, tmp_path / "many.pdf"))
    for item in g.truth.line_items:
        assert item.description in text