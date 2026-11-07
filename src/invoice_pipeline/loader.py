"""Load extracted invoices into the warehouse; send the rest to the review queue.

Idempotent: loading the same document again replaces its rows, so a rerun never
creates duplicates.
"""
import json
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import delete, insert, select

from invoice_pipeline.warehouse import (
    date_row, dim_currency, dim_date, dim_item, dim_supplier, fact_invoice, fact_invoice_line, review_queue,
)

LOAD_REQUIRED = ("invoice_number", "supplier_name", "invoice_date", "currency", "total_amount")


def unloadable_reasons(rec: dict) -> list[str]:
    reasons = [f"{f} is missing" for f in LOAD_REQUIRED if rec.get(f) is None]
    if not rec.get("line_items"):
        reasons.append("no line items")
    return reasons


def money(value, places: int = 2):
    if value is None:
        return None
    quantum = Decimal(1).scaleb(-places)
    return Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP)


def _get_or_create(conn, table, key_col, filters: dict, values: dict) -> int:
    cond = [(table.c[k] == v) if v is not None else table.c[k].is_(None) for k, v in filters.items()]
    found = conn.execute(select(key_col).where(*cond)).scalar_one_or_none()
    if found is not None:
        return found
    return conn.execute(insert(table).values(**values).returning(key_col)).scalar_one()


def ensure_date(conn, iso: str) -> int:
    d = date.fromisoformat(iso)
    row = date_row(d)
    if conn.execute(select(dim_date.c.date_key).where(dim_date.c.date_key == row["date_key"])).first() is None:
        conn.execute(insert(dim_date).values(**row))
    return row["date_key"]


def load_invoice(conn, document_id: str, input_type: str, rec: dict, review_status: str) -> int:
    """Insert one invoice (replacing any earlier load of the same document). Returns invoice_key."""
    reasons = unloadable_reasons(rec)
    if reasons:
        raise ValueError(f"{document_id} cannot be loaded: {reasons}")
    old = conn.execute(select(fact_invoice.c.invoice_key).where(fact_invoice.c.document_id == document_id)).scalar_one_or_none()
    if old is not None:
        conn.execute(delete(fact_invoice_line).where(fact_invoice_line.c.invoice_key == old))
        conn.execute(delete(fact_invoice).where(fact_invoice.c.invoice_key == old))
    conn.execute(delete(review_queue).where(review_queue.c.document_id == document_id))

    supplier_key = _get_or_create(
        conn, dim_supplier, dim_supplier.c.supplier_key,
        {"supplier_name": rec["supplier_name"], "supplier_tax_id": rec.get("supplier_tax_id")},
        {"supplier_name": rec["supplier_name"], "supplier_tax_id": rec.get("supplier_tax_id")},
    )
    currency_key = _get_or_create(
        conn, dim_currency, dim_currency.c.currency_key,
        {"currency_code": rec["currency"]}, {"currency_code": rec["currency"]},
    )
    invoice_date_key = ensure_date(conn, rec["invoice_date"])
    due_date_key = ensure_date(conn, rec["due_date"]) if rec.get("due_date") else None

    invoice_key = conn.execute(
        insert(fact_invoice).values(
            document_id=document_id, invoice_number=rec["invoice_number"], supplier_key=supplier_key,
            invoice_date_key=invoice_date_key, due_date_key=due_date_key, currency_key=currency_key,
            subtotal=money(rec.get("subtotal")), tax_amount=money(rec.get("tax_amount")),
            total_amount=money(rec["total_amount"]), line_count=len(rec["line_items"]),
            input_type=input_type, review_status=review_status,
        ).returning(fact_invoice.c.invoice_key)
    ).scalar_one()

    for n, item in enumerate(rec["line_items"], start=1):
        item_key = _get_or_create(
            conn, dim_item, dim_item.c.item_key,
            {"description": item["description"]}, {"description": item["description"]},
        )
        conn.execute(
            insert(fact_invoice_line).values(
                invoice_key=invoice_key, line_no=n, item_key=item_key, supplier_key=supplier_key,
                invoice_date_key=invoice_date_key, quantity=money(item["quantity"], 3),
                unit_price=money(item["unit_price"]), line_total=money(item["line_total"]),
            )
        )
    return invoice_key


def queue_invoice(conn, document_id: str, input_type: str, issues: list) -> None:
    conn.execute(delete(review_queue).where(review_queue.c.document_id == document_id))
    conn.execute(insert(review_queue).values(
        document_id=document_id, input_type=input_type, status="pending",
        issues=json.dumps(issues, ensure_ascii=False),
    ))


def route_invoice(conn, document_id: str, input_type: str, rec: dict, issues: list, needs_review: bool,
                  reviewed_rec: dict | None = None, reviewed_status: str = "human_reviewed") -> str:
    """Decide where one invoice goes. Returns 'loaded', 'loaded_after_review' or 'queued'."""
    if needs_review:
        if reviewed_rec is not None and not unloadable_reasons(reviewed_rec):
            load_invoice(conn, document_id, input_type, reviewed_rec, reviewed_status)
            return "loaded_after_review"
        queue_invoice(conn, document_id, input_type, issues)
        return "queued"
    reasons = unloadable_reasons(rec)
    if reasons:
        queue_invoice(conn, document_id, input_type, [{"field": "-", "rule": "loadable", "severity": "review",
                                                      "message": "; ".join(reasons)}])
        return "queued"
    load_invoice(conn, document_id, input_type, rec, "auto")
    return "loaded"
