import copy

import pytest
from pydantic import ValidationError

from invoice_pipeline.schema import Invoice

VALID = {
    "invoice_number": "INV-001",
    "supplier_name": "Muster GmbH",
    "supplier_tax_id": "DE123456789",
    "invoice_date": "2025-03-14",
    "due_date": "2025-04-13",
    "currency": "EUR",
    "subtotal": 100.0,
    "tax_amount": 19.0,
    "total_amount": 119.0,
    "line_items": [
        {"description": "Widget", "quantity": 2, "unit_price": 50.0, "line_total": 100.0}
    ],
}


def test_valid_invoice_parses():
    inv = Invoice(**VALID)
    assert inv.invoice_number == "INV-001"
    assert inv.line_items[0].line_total == 100.0


def test_null_allowed_for_absent_fields():
    data = {k: None for k in VALID}
    data["line_items"] = []
    inv = Invoice(**data)
    assert inv.due_date is None and inv.line_items == []


def test_missing_key_is_rejected():
    data = copy.deepcopy(VALID)
    del data["due_date"]
    with pytest.raises(ValidationError):
        Invoice(**data)


def test_invalid_dates_are_rejected():
    for bad in ["14.03.2025", "2025-02-30", "March 14, 2025"]:
        data = copy.deepcopy(VALID)
        data["invoice_date"] = bad
        with pytest.raises(ValidationError):
            Invoice(**data)


def test_currency_format_is_checked():
    for bad in ["euro", "eur", "EURO", "€"]:
        data = copy.deepcopy(VALID)
        data["currency"] = bad
        with pytest.raises(ValidationError):
            Invoice(**data)


def test_extra_keys_are_rejected():
    data = copy.deepcopy(VALID)
    data["invented_field"] = "x"
    with pytest.raises(ValidationError):
        Invoice(**data)


def test_json_schema_contains_all_fields():
    props = Invoice.model_json_schema()["properties"]
    assert set(props) == set(VALID)


def test_json_roundtrip():
    inv = Invoice(**VALID)
    assert Invoice.model_validate_json(inv.model_dump_json()) == inv