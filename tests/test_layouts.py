import random
from datetime import date

import pymupdf
import pytest

from invoice_pipeline.fakedata import GeneratedInvoice, PrintExtras, generate_invoice
from invoice_pipeline.formats import LOCALES, format_date, format_money, get_locale
from invoice_pipeline.layouts import LAYOUTS, render
from invoice_pipeline.render import format_quantity
from invoice_pipeline.schema import Invoice, LineItem

ALL_LOCALES = sorted(LOCALES)
ALL_LAYOUTS = sorted(LAYOUTS)


def pdf_text(path) -> str:
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
        line_items=[LineItem(description="Monitor 27 Zoll", quantity=2, unit_price=617.28, line_total=1234.56)],
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


def check_truth_in_text(g: GeneratedInvoice, text: str) -> None:
    """Every truth value is printed (formatted per locale); null fields leave no trace."""
    locale = get_locale(g.locale_code)
    t = g.truth
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


@pytest.mark.parametrize("layout", ALL_LAYOUTS)
@pytest.mark.parametrize("code", ALL_LOCALES)
def test_every_truth_value_is_printed(layout, code, tmp_path):
    rng = random.Random(200)
    for i in range(15):
        g = generate_invoice(rng, code)
        check_truth_in_text(g, pdf_text(render(layout, g, tmp_path / f"{layout}_{code}_{i}.pdf")))


@pytest.mark.parametrize("layout", ALL_LAYOUTS)
def test_missing_fields_are_not_printed(layout, tmp_path):
    g = fixed_invoice(due_date=None, supplier_tax_id=None, subtotal=None)
    text = pdf_text(render(layout, g, tmp_path / "m.pdf"))
    for absent in ["Fällig am", "13.04.2025", "USt-IdNr.", "DE123456789", "Zwischensumme"]:
        assert absent not in text, f"{absent!r} should not be printed"
    assert "1.469,13 €" in text


@pytest.mark.parametrize("layout", ALL_LAYOUTS)
def test_all_present_fields_are_printed(layout, tmp_path):
    text = pdf_text(render(layout, fixed_invoice(), tmp_path / "p.pdf"))
    for expected in [
        "RE-2025-0042", "14.03.2025", "13.04.2025", "DE123456789", "Zwischensumme",
        "1.234,56 €", "234,57 €", "1.469,13 €", "Monitor 27 Zoll 2 617,28 € 1.234,56 €",
    ]:
        assert expected in text, f"missing in {layout}: {expected!r}"


@pytest.mark.parametrize("layout", ALL_LAYOUTS)
def test_special_characters_survive(layout, tmp_path):
    g = fixed_invoice(supplier_name="Schmidt & Söhne <Export> GmbH")
    assert "Schmidt & Söhne <Export> GmbH" in pdf_text(render(layout, g, tmp_path / "s.pdf"))


@pytest.mark.parametrize("layout", ALL_LAYOUTS)
def test_same_input_gives_identical_bytes(layout, tmp_path):
    g = generate_invoice(random.Random(5), "uk")
    a = render(layout, g, tmp_path / "a.pdf").read_bytes()
    b = render(layout, g, tmp_path / "b.pdf").read_bytes()
    assert a == b


@pytest.mark.parametrize("layout", ALL_LAYOUTS)
def test_fifteen_items_all_printed(layout, tmp_path):
    g = generate_invoice(random.Random(8), "us", n_items=15)
    check_truth_in_text(g, pdf_text(render(layout, g, tmp_path / "many.pdf")))


def test_layouts_really_differ(tmp_path):
    g = generate_invoice(random.Random(3), "de")
    blobs = {name: render(name, g, tmp_path / f"{name}.pdf").read_bytes() for name in ALL_LAYOUTS}
    assert len(set(blobs.values())) == len(ALL_LAYOUTS)


def test_registry_contains_three_layouts():
    assert ALL_LAYOUTS == ["classic", "modern", "twocol"]


def test_unknown_layout_raises(tmp_path):
    with pytest.raises(ValueError):
        render("fancy", generate_invoice(random.Random(1), "de"), tmp_path / "x.pdf")


def test_page_size_follows_locale(tmp_path):
    for layout in ALL_LAYOUTS:
        us = render(layout, generate_invoice(random.Random(1), "us"), tmp_path / f"{layout}_us.pdf")
        de = render(layout, generate_invoice(random.Random(1), "de"), tmp_path / f"{layout}_de.pdf")
        with pymupdf.open(us) as d:
            assert round(d[0].rect.width) == 612
        with pymupdf.open(de) as d:
            assert round(d[0].rect.width) == 595