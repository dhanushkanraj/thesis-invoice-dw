import json

import pytest
from sqlalchemy import create_engine, func, select

from invoice_pipeline import analytics
from invoice_pipeline.loader import load_invoice, queue_invoice
from invoice_pipeline.review import (
    HEADER_KEYS, invoice_id_of, load_prediction, pdf_path, pending_documents, record_problems, submit_review,
)
from invoice_pipeline.warehouse import create_schema, fact_invoice, review_queue


def rec(**changes):
    base = {
        "invoice_number": "RE-1", "supplier_name": "Müller GmbH", "supplier_tax_id": None,
        "invoice_date": "2025-03-14", "due_date": None, "currency": "EUR",
        "subtotal": 100.0, "tax_amount": 19.0, "total_amount": 119.0,
        "line_items": [
            {"description": "Monitor", "quantity": 2, "unit_price": 30.0, "line_total": 60.0},
            {"description": "Lampe", "quantity": 1, "unit_price": 40.0, "line_total": 40.0},
        ],
    }
    return {**base, **changes}


@pytest.fixture()
def engine():
    eng = create_engine("sqlite://")
    create_schema(eng)
    return eng


def test_invoice_id_of():
    assert invoice_id_of("inv_0007_scanned") == "inv_0007"


def test_pdf_path_depends_on_input_type(tmp_path):
    assert pdf_path(tmp_path, "digital", "inv_1").parts[-2:] == ("pdf", "inv_1.pdf")
    assert pdf_path(tmp_path, "scanned", "inv_1").parts[-2:] == ("scanned", "inv_1.pdf")


def test_load_prediction_fills_all_keys_even_when_file_is_missing_or_partial(tmp_path):
    empty = load_prediction(tmp_path, "m3_x", "digital", "inv_1")
    assert set(empty) == {*HEADER_KEYS, "line_items"} and empty["line_items"] == []
    folder = tmp_path / "outputs" / "m3_x" / "digital"
    folder.mkdir(parents=True)
    (folder / "inv_1.json").write_text(json.dumps({"invoice_number": "A", "line_items": [{"description": "x"}, "junk"]}))
    part = load_prediction(tmp_path, "m3_x", "digital", "inv_1")
    assert part["invoice_number"] == "A" and part["line_items"] == [
        {"description": "x", "quantity": None, "unit_price": None, "line_total": None}]


def test_clean_record_has_no_problems():
    assert record_problems(rec()) == ([], [])


def test_schema_errors_block_and_arithmetic_only_warns():
    errors, _ = record_problems(rec(invoice_date="2025-13-40"))
    assert errors
    errors, _ = record_problems(rec(currency="euro"))
    assert errors
    errors, warnings = record_problems(rec(total_amount=120.0))
    assert errors == [] and any("Subtotal + tax" in w for w in warnings)
    errors, warnings = record_problems(rec(line_items=[dict(rec()["line_items"][0], line_total=61.0), rec()["line_items"][1]]))
    assert errors == [] and any("Item 1" in w for w in warnings) and any("Line totals add up" in w for w in warnings)


def test_missing_required_value_is_an_error():
    errors, _ = record_problems(rec(currency=None))
    assert any("currency" in e for e in errors)
    errors, _ = record_problems(rec(line_items=[]))
    assert any("no line items" in e for e in errors)


def test_pending_list_and_submit_review_roundtrip(engine, tmp_path):
    with engine.begin() as conn:
        queue_invoice(conn, "inv_0001_scanned", "scanned", [{"field": "total_amount", "severity": "review", "message": "m"}])
    pending = pending_documents(engine)
    assert [p["document_id"] for p in pending] == ["inv_0001_scanned"] and pending[0]["issues"][0]["field"] == "total_amount"

    path = submit_review(engine, tmp_path, "inv_0001_scanned", "scanned", rec())
    assert path == tmp_path / "outputs" / "reviewed" / "scanned" / "inv_0001.json"
    assert json.loads(path.read_text(encoding="utf-8"))["invoice_number"] == "RE-1"
    with engine.connect() as conn:
        row = conn.execute(select(fact_invoice)).mappings().one()
        assert row["review_status"] == "human_reviewed" and row["document_id"] == "inv_0001_scanned"
        assert conn.execute(select(func.count()).select_from(review_queue)).scalar_one() == 0
    assert pending_documents(engine) == []


def test_submit_review_refuses_invalid_record_and_writes_nothing(engine, tmp_path):
    with pytest.raises(ValueError):
        submit_review(engine, tmp_path, "inv_0001_scanned", "scanned", rec(invoice_date="nonsense"))
    assert not (tmp_path / "outputs").exists()
    with engine.connect() as conn:
        assert conn.execute(select(func.count()).select_from(fact_invoice)).scalar_one() == 0


def test_analytics_queries(engine):
    with engine.begin() as conn:
        load_invoice(conn, "a", "digital", rec(), "auto")
        load_invoice(conn, "b", "digital", rec(invoice_number="2", invoice_date="2025-04-02"), "human_reviewed")
        load_invoice(conn, "c", "scanned", rec(invoice_number="3", currency="USD"), "auto")
        queue_invoice(conn, "d", "scanned", [])
    assert analytics.overview(engine) == {"invoices": 3, "lines": 6, "pending_review": 1}
    assert analytics.currencies(engine) == ["EUR", "USD"]
    monthly = analytics.monthly_spend(engine, "EUR")
    assert monthly["month"].tolist() == ["2025-03", "2025-04"] and monthly["total_spend"].tolist() == [119.0, 119.0]
    assert analytics.top_suppliers(engine, "EUR").iloc[0]["invoices"] == 2
    assert analytics.top_items(engine, "EUR").iloc[0]["description"] == "Monitor"
    mix = analytics.review_mix(engine)
    assert set(mix["review_status"]) == {"auto", "human_reviewed"} and mix["invoices"].sum() == 3


@pytest.mark.parametrize("text,expected", [
    ("2,739.43", 2739.43), ("2.739,43", 2739.43), ("€2,739.43", 2739.43), ("2739.43", 2739.43),
    ("7,5", 7.5), ("7.5", 7.5), ("1,234", 1234.0), ("2.739", 2739.0), ("0.125", 0.125),
    ("€1.234.567,89", 1234567.89), ("1,234,567.89", 1234567.89), ("  12  ", 12.0), ("", None), ("   ", None),
])
def test_parse_number_reads_numbers_as_documents_print_them(text, expected):
    from invoice_pipeline.review import parse_number
    assert parse_number(text) == expected


def test_parse_number_rejects_text():
    from invoice_pipeline.review import parse_number
    with pytest.raises(ValueError):
        parse_number("abc")
    with pytest.raises(ValueError):
        parse_number("12,3x")
