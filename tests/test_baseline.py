import random

import pytest

from invoice_pipeline.baseline import (
    extract_invoice, find_supplier, parse_date, parse_money, parse_quantity,
)
from invoice_pipeline.extract_text import get_lines
from invoice_pipeline.evaluate import evaluate_invoice
from invoice_pipeline.fakedata import generate_invoice
from invoice_pipeline.layouts import LAYOUTS, render
from invoice_pipeline.formats import LOCALES


@pytest.mark.parametrize("text,expected", [
    ("1.867,96 €", 1867.96), ("37,01 €", 37.01), ("€2,739.43", 2739.43),
    ("$6,291.41", 6291.41), ("£11,831.98", 11831.98), ("€91.55", 91.55), ("12", None),
])
def test_parse_money(text, expected):
    assert parse_money(text) == expected


@pytest.mark.parametrize("text,expected", [
    ("04.10.2025", "2025-10-04"), ("21/05/2026", "2026-05-21"),
    ("16 May 2025", "2025-05-16"), ("April 7, 2025", "2025-04-07"),
    ("31.02.2025", None), ("yesterday", None),
])
def test_parse_date(text, expected):
    assert parse_date(text) == expected


def test_parse_quantity():
    assert parse_quantity("1,5") == 1.5 and parse_quantity("2") == 2.0


def test_find_supplier_takes_first_name_in_two_column_line():
    assert find_supplier(["Invoice", "From To", "Summit Consulting GmbH Meridian Services Inc."]) == "Summit Consulting GmbH"
    assert find_supplier(["Hoffmann Elektro GmbH & Co. KG"]) == "Hoffmann Elektro GmbH & Co. KG"


def test_extract_german_label_value_lines():
    lines = [
        "Müller Elektro e.K.", "USt-IdNr.: DE214263669", "Rechnung",
        "Rechnungsnummer: RE-2025-2947", "Rechnungsdatum: 02.02.2025", "Fällig am: 04.03.2025",
        "Beschreibung Menge Einzelpreis Gesamt",
        "Lieferung und Montage 17 109,88 € 1.867,96 €",
        "Server-Wartung, Stunden 1,5 117,90 € 176,85 €",
        "Zwischensumme 2.044,81 €", "MwSt. 19 % 388,51 €", "Gesamtbetrag 2.433,32 €",
    ]
    r = extract_invoice(lines)
    assert (r["invoice_number"], r["invoice_date"], r["due_date"]) == ("RE-2025-2947", "2025-02-02", "2025-03-04")
    assert r["supplier_name"] == "Müller Elektro e.K." and r["supplier_tax_id"] == "DE214263669"
    assert (r["subtotal"], r["tax_amount"], r["total_amount"], r["currency"]) == (2044.81, 388.51, 2433.32, "EUR")
    assert len(r["line_items"]) == 2 and r["line_items"][1]["quantity"] == 1.5


def test_extract_label_grid_with_missing_column():
    lines = [
        "Invoice", "From To", "Harbor Consulting LLC Meridian Services Inc.",
        "Invoice No. Invoice Date Customer No. PO Number",
        "#04823 April 7, 2025 CUST-25772 PO-2025-2199",
        "No. Description Qty Unit Price Amount",
        "1 Wireless keyboard 8 $34.14 $273.12",
        "Total $273.12",
    ]
    r = extract_invoice(lines)
    assert r["invoice_number"] == "#04823" and r["invoice_date"] == "2025-04-07"
    assert r["due_date"] is None and r["subtotal"] is None and r["currency"] == "USD"
    assert r["line_items"][0]["description"] == "Wireless keyboard"  # position number stripped


def test_nothing_found_gives_nulls_not_crash():
    r = extract_invoice(["hello world"])
    assert r["invoice_number"] is None and r["line_items"] == [] and r["total_amount"] is None


@pytest.mark.parametrize("layout", sorted(LAYOUTS))
@pytest.mark.parametrize("locale", sorted(LOCALES))
def test_round_trip_on_digital_pdf(tmp_path, layout, locale):
    """On a clean digital PDF the rules get every field except possibly a wrapped supplier name."""
    for seed in (1, 2):
        g = generate_invoice(random.Random(seed), locale)
        pdf = tmp_path / f"{layout}_{locale}_{seed}.pdf"
        render(layout, g, pdf)
        lines, method = get_lines(pdf)
        assert method == "native"
        res = evaluate_invoice(extract_invoice(lines), g.truth.model_dump(mode="json"))
        bad = {f: o for f, o in res["outcomes"].items() if o != "correct" and f != "supplier_name"}
        assert bad == {}
        assert res["items"]["exact"]
