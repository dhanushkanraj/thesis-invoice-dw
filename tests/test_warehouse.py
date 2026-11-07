import json
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select, text

from invoice_pipeline.loader import load_invoice, queue_invoice, route_invoice, unloadable_reasons
from invoice_pipeline.warehouse import (
    create_schema, date_row, dim_date, dim_item, dim_supplier, fact_invoice, fact_invoice_line, review_queue,
)


@pytest.fixture()
def engine():
    eng = create_engine("sqlite://")
    create_schema(eng)
    return eng


def rec(**changes):
    base = {
        "invoice_number": "RE-1", "supplier_name": "Müller GmbH", "supplier_tax_id": "DE1",
        "invoice_date": "2025-03-14", "due_date": "2025-04-13", "currency": "EUR",
        "subtotal": 100.0, "tax_amount": 19.0, "total_amount": 119.0,
        "line_items": [
            {"description": "Monitor", "quantity": 2, "unit_price": 30.0, "line_total": 60.0},
            {"description": "Lampe", "quantity": 1.5, "unit_price": 26.67, "line_total": 40.0},
        ],
    }
    return {**base, **changes}


def count(conn, table):
    return conn.execute(select(func.count()).select_from(table)).scalar_one()


def test_dim_date_is_complete_and_correct(engine):
    with engine.connect() as conn:
        assert count(conn, dim_date) == 1461  # 2024-2027
    row = date_row(__import__("datetime").date(2025, 3, 14))
    assert (row["date_key"], row["quarter"], row["month_name"], row["weekday_name"], row["is_weekend"]) == (
        20250314, 1, "March", "Friday", False)


def test_create_schema_twice_changes_nothing(engine):
    create_schema(engine)
    with engine.connect() as conn:
        assert count(conn, dim_date) == 1461


def test_load_invoice_writes_facts_and_dimensions(engine):
    with engine.begin() as conn:
        key = load_invoice(conn, "inv_1_digital", "digital", rec(), "auto")
    with engine.connect() as conn:
        f = conn.execute(select(fact_invoice)).mappings().one()
        assert f["invoice_key"] == key and f["total_amount"] == Decimal("119.00") and f["line_count"] == 2
        assert f["invoice_date_key"] == 20250314 and f["due_date_key"] == 20250413
        lines = conn.execute(select(fact_invoice_line).order_by(fact_invoice_line.c.line_no)).mappings().all()
        assert [float(l["quantity"]) for l in lines] == [2.0, 1.5]
        assert count(conn, dim_item) == 2 and count(conn, dim_supplier) == 1


def test_supplier_and_item_dimensions_are_shared(engine):
    with engine.begin() as conn:
        load_invoice(conn, "a", "digital", rec(), "auto")
        load_invoice(conn, "b", "digital", rec(invoice_number="RE-2"), "auto")
        load_invoice(conn, "c", "digital", rec(invoice_number="RE-3", supplier_tax_id=None), "auto")
    with engine.connect() as conn:
        assert count(conn, fact_invoice) == 3 and count(conn, dim_item) == 2
        assert count(conn, dim_supplier) == 2  # same name with and without tax id are two rows


def test_reload_replaces_instead_of_duplicating(engine):
    with engine.begin() as conn:
        load_invoice(conn, "a", "digital", rec(), "auto")
        load_invoice(conn, "a", "digital", rec(total_amount=120.0), "human_reviewed")
    with engine.connect() as conn:
        assert count(conn, fact_invoice) == 1 and count(conn, fact_invoice_line) == 2
        f = conn.execute(select(fact_invoice)).mappings().one()
        assert f["total_amount"] == Decimal("120.00") and f["review_status"] == "human_reviewed"


def test_missing_optional_values_load_as_null(engine):
    with engine.begin() as conn:
        load_invoice(conn, "a", "digital", rec(due_date=None, subtotal=None, supplier_tax_id=None), "auto")
    with engine.connect() as conn:
        f = conn.execute(select(fact_invoice)).mappings().one()
        assert f["due_date_key"] is None and f["subtotal"] is None


def test_unloadable_reasons_and_error(engine):
    assert unloadable_reasons(rec()) == []
    assert set(unloadable_reasons(rec(currency=None, line_items=[]))) == {"currency is missing", "no line items"}
    with pytest.raises(ValueError), engine.begin() as conn:
        load_invoice(conn, "a", "digital", rec(currency=None), "auto")


def test_routing_clean_flagged_and_reviewed(engine):
    with engine.begin() as conn:
        assert route_invoice(conn, "ok", "digital", rec(), [], False) == "loaded"
        assert route_invoice(conn, "bad", "digital", rec(), [{"rule": "x"}], True) == "queued"
        assert route_invoice(conn, "nocur", "digital", rec(currency=None), [], False) == "queued"
    with engine.connect() as conn:
        assert count(conn, fact_invoice) == 1 and count(conn, review_queue) == 2
    with engine.begin() as conn:  # the flagged one is corrected by a person
        out = route_invoice(conn, "bad", "digital", rec(), [{"rule": "x"}], True, reviewed_rec=rec(total_amount=121.0))
        assert out == "loaded_after_review"
    with engine.connect() as conn:
        assert count(conn, fact_invoice) == 2 and count(conn, review_queue) == 1


def test_queue_issues_are_stored_as_json(engine):
    with engine.begin() as conn:
        queue_invoice(conn, "bad", "scanned", [{"field": "total_amount", "message": "ü"}])
    with engine.connect() as conn:
        row = conn.execute(select(review_queue)).mappings().one()
        assert row["status"] == "pending" and json.loads(row["issues"])[0]["message"] == "ü"


def test_views_aggregate_correctly(engine):
    with engine.begin() as conn:
        load_invoice(conn, "a", "digital", rec(), "auto")
        load_invoice(conn, "b", "digital", rec(invoice_number="2", total_amount=81.0), "auto")
        load_invoice(conn, "c", "digital", rec(invoice_number="3", currency="USD", invoice_date="2025-04-01"), "auto")
    with engine.connect() as conn:
        monthly = conn.execute(text("SELECT year, month, currency_code, invoices, total_spend FROM v_monthly_spend "
                                    "ORDER BY month, currency_code")).all()
        assert [(m[1], m[2], m[3], Decimal(str(m[4]))) for m in monthly] == [
            (3, "EUR", 2, Decimal("200")), (4, "USD", 1, Decimal("119"))]
        top = conn.execute(text("SELECT description, line_spend FROM v_item_spend "
                                "WHERE currency_code='EUR' ORDER BY description")).all()
        assert [(t[0], Decimal(str(t[1]))) for t in top] == [("Lampe", Decimal("80")), ("Monitor", Decimal("120"))]


def test_existing_views_are_not_dropped_again(engine):
    with engine.begin() as conn:
        conn.execute(text("DROP VIEW v_monthly_spend"))
        conn.execute(text("CREATE VIEW v_monthly_spend AS SELECT 42 AS marker"))
    create_schema(engine)  # default: leave existing views alone
    with engine.connect() as conn:
        assert conn.execute(text("SELECT marker FROM v_monthly_spend")).scalar_one() == 42
    create_schema(engine, refresh_views=True)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM v_monthly_spend")).scalar_one() >= 0
