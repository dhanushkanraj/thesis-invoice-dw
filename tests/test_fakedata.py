import random
import re
from datetime import date
from decimal import Decimal

import pytest

from invoice_pipeline.fakedata import compute_amounts, generate_invoice, money
from invoice_pipeline.formats import LOCALES

ALL_LOCALES = sorted(LOCALES)


def test_money_rounds_half_up():
    assert money(Decimal("0.025")) == Decimal("0.03")
    assert money(Decimal("2.675")) == Decimal("2.68")
    assert money(Decimal("1.004")) == Decimal("1.00")


def test_compute_amounts_known_values():
    lines = [(Decimal("2"), Decimal("19.99")), (Decimal("1"), Decimal("0.01"))]
    line_totals, subtotal, tax, total = compute_amounts(lines, Decimal("19"))
    assert line_totals == [Decimal("39.98"), Decimal("0.01")]
    assert subtotal == Decimal("39.99")
    assert tax == Decimal("7.60")
    assert total == Decimal("47.59")


def test_compute_amounts_half_up_tax():
    _, _, tax, total = compute_amounts([(Decimal("1"), Decimal("0.50"))], Decimal("5"))
    assert tax == Decimal("0.03")
    assert total == Decimal("0.53")


@pytest.mark.parametrize("code", ALL_LOCALES)
def test_amounts_are_consistent(code):
    rng = random.Random(1)
    for _ in range(50):
        t = generate_invoice(rng, code).truth
        for item in t.line_items:
            assert abs(item.line_total - item.quantity * item.unit_price) <= 0.0051
        sum_lines = sum(item.line_total for item in t.line_items)
        if t.subtotal is not None:
            assert abs(t.subtotal - sum_lines) < 0.001
        assert t.tax_amount >= 0
        assert abs(t.total_amount - (sum_lines + t.tax_amount)) < 0.001


def test_same_seed_same_output():
    assert generate_invoice(random.Random(7), "de") == generate_invoice(random.Random(7), "de")


def test_different_seed_different_output():
    assert generate_invoice(random.Random(7), "de") != generate_invoice(random.Random(8), "de")


def test_missing_rate_one_removes_fields():
    rates = {"due_date": 1.0, "supplier_tax_id": 1.0, "subtotal": 1.0}
    t = generate_invoice(random.Random(3), "de", missing_rates=rates).truth
    assert t.due_date is None
    assert t.supplier_tax_id is None
    assert t.subtotal is None
    assert t.total_amount is not None and t.invoice_number is not None


def test_missing_rate_zero_keeps_fields():
    rates = {"due_date": 0.0, "supplier_tax_id": 0.0, "subtotal": 0.0}
    rng = random.Random(3)
    for _ in range(30):
        t = generate_invoice(rng, "us", missing_rates=rates).truth
        assert t.due_date and t.supplier_tax_id and t.subtotal is not None


def test_default_missing_rates_are_roughly_respected():
    rng = random.Random(5)
    n = 400
    invoices = [generate_invoice(rng, "de").truth for _ in range(n)]
    due = sum(i.due_date is None for i in invoices) / n
    tax_id = sum(i.supplier_tax_id is None for i in invoices) / n
    subtotal = sum(i.subtotal is None for i in invoices) / n
    assert 0.10 <= due <= 0.30
    assert 0.15 <= tax_id <= 0.35
    assert 0.03 <= subtotal <= 0.20


@pytest.mark.parametrize(
    "code,pattern",
    [
        ("de", r"DE\d{9}"),
        ("uk", r"GB\d{9}"),
        ("us", r"\d{2}-\d{7}"),
        ("en_eu", r"(NL\d{9}B\d{2}|FR\d{11})"),
    ],
)
def test_tax_id_format(code, pattern):
    rng = random.Random(2)
    for _ in range(20):
        t = generate_invoice(rng, code, missing_rates={"supplier_tax_id": 0.0}).truth
        assert re.fullmatch(pattern, t.supplier_tax_id)


def test_currency_matches_locale():
    rng = random.Random(4)
    for code in ALL_LOCALES:
        assert generate_invoice(rng, code).truth.currency == LOCALES[code].currency


def test_item_count_override():
    assert len(generate_invoice(random.Random(1), "de", n_items=1).truth.line_items) == 1
    assert len(generate_invoice(random.Random(1), "de", n_items=15).truth.line_items) == 15


def test_item_count_validation():
    for bad in (0, 16):
        with pytest.raises(ValueError):
            generate_invoice(random.Random(1), "de", n_items=bad)


def test_default_item_count_in_range():
    rng = random.Random(6)
    counts = [len(generate_invoice(rng, "uk").truth.line_items) for _ in range(200)]
    assert min(counts) >= 1 and max(counts) <= 15
    assert min(counts) <= 3 and max(counts) >= 9


def test_descriptions_unique_within_invoice():
    t = generate_invoice(random.Random(9), "en_eu", n_items=15).truth
    descriptions = [item.description for item in t.line_items]
    assert len(set(descriptions)) == 15


def test_due_date_not_before_invoice_date():
    rng = random.Random(10)
    for _ in range(100):
        t = generate_invoice(rng, "de", missing_rates={"due_date": 0.0}).truth
        assert date.fromisoformat(t.due_date) >= date.fromisoformat(t.invoice_date)


def test_unknown_locale_raises():
    with pytest.raises(ValueError):
        generate_invoice(random.Random(1), "fr")


def test_iban_only_for_euro_locales():
    rng = random.Random(11)
    for _ in range(10):
        assert re.fullmatch(r"DE\d{2}( \d{4}){4} \d{2}", generate_invoice(rng, "de").extras.iban)
        assert generate_invoice(rng, "us").extras.iban is None
        assert generate_invoice(rng, "uk").extras.iban is None


def test_distractor_numbers_differ_from_invoice_number():
    rng = random.Random(12)
    for code in ALL_LOCALES:
        g = generate_invoice(rng, code)
        assert g.extras.purchase_order and g.extras.customer_number
        assert g.extras.purchase_order != g.truth.invoice_number
        assert g.extras.customer_number != g.truth.invoice_number