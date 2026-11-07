"""PostgreSQL star schema for invoices.

Facts
  fact_invoice        one row per invoice document       (grain: invoice)
  fact_invoice_line   one row per invoice line item      (grain: line item)
Dimensions
  dim_date, dim_supplier, dim_currency, dim_item
Operational (outside the star)
  review_queue        invoices that need a person, with the reasons

Defined with SQLAlchemy so the same definition creates the tables on PostgreSQL
(production) and SQLite (unit tests).
"""
import calendar
from datetime import date, timedelta

from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Integer, MetaData, Numeric, String, Table, Text,
    UniqueConstraint, func, insert, inspect, select, text,
)

metadata = MetaData()

dim_date = Table(
    "dim_date", metadata,
    Column("date_key", Integer, primary_key=True, autoincrement=False),  # 20250314
    Column("full_date", Date, nullable=False, unique=True),
    Column("year", Integer, nullable=False),
    Column("quarter", Integer, nullable=False),
    Column("month", Integer, nullable=False),
    Column("month_name", String(10), nullable=False),
    Column("day", Integer, nullable=False),
    Column("iso_week", Integer, nullable=False),
    Column("weekday_name", String(10), nullable=False),
    Column("is_weekend", Boolean, nullable=False),
)

dim_currency = Table(
    "dim_currency", metadata,
    Column("currency_key", Integer, primary_key=True),
    Column("currency_code", String(3), nullable=False, unique=True),
)

dim_supplier = Table(
    "dim_supplier", metadata,
    Column("supplier_key", Integer, primary_key=True),
    Column("supplier_name", String(200), nullable=False),
    Column("supplier_tax_id", String(40)),
    UniqueConstraint("supplier_name", "supplier_tax_id", name="uq_supplier"),
)

dim_item = Table(
    "dim_item", metadata,
    Column("item_key", Integer, primary_key=True),
    Column("description", String(300), nullable=False, unique=True),
)

fact_invoice = Table(
    "fact_invoice", metadata,
    Column("invoice_key", Integer, primary_key=True),
    Column("document_id", String(60), nullable=False, unique=True),  # e.g. inv_0001_digital
    Column("invoice_number", String(60), nullable=False),
    Column("supplier_key", Integer, ForeignKey("dim_supplier.supplier_key"), nullable=False),
    Column("invoice_date_key", Integer, ForeignKey("dim_date.date_key"), nullable=False),
    Column("due_date_key", Integer, ForeignKey("dim_date.date_key")),
    Column("currency_key", Integer, ForeignKey("dim_currency.currency_key"), nullable=False),
    Column("subtotal", Numeric(14, 2)),
    Column("tax_amount", Numeric(14, 2)),
    Column("total_amount", Numeric(14, 2), nullable=False),
    Column("line_count", Integer, nullable=False),
    Column("input_type", String(10), nullable=False),   # digital or scanned
    Column("review_status", String(20), nullable=False),  # auto, human_reviewed, simulated_review
    Column("loaded_at", DateTime, server_default=func.now(), nullable=False),
)

fact_invoice_line = Table(
    "fact_invoice_line", metadata,
    Column("line_key", Integer, primary_key=True),
    Column("invoice_key", Integer, ForeignKey("fact_invoice.invoice_key", ondelete="CASCADE"), nullable=False),
    Column("line_no", Integer, nullable=False),
    Column("item_key", Integer, ForeignKey("dim_item.item_key"), nullable=False),
    Column("supplier_key", Integer, ForeignKey("dim_supplier.supplier_key"), nullable=False),
    Column("invoice_date_key", Integer, ForeignKey("dim_date.date_key"), nullable=False),
    Column("quantity", Numeric(12, 3), nullable=False),
    Column("unit_price", Numeric(14, 2), nullable=False),
    Column("line_total", Numeric(14, 2), nullable=False),
    UniqueConstraint("invoice_key", "line_no", name="uq_invoice_line"),
)

review_queue = Table(
    "review_queue", metadata,
    Column("document_id", String(60), primary_key=True),
    Column("input_type", String(10), nullable=False),
    Column("status", String(10), nullable=False),  # pending or resolved
    Column("issues", Text, nullable=False),  # JSON list
    Column("created_at", DateTime, server_default=func.now(), nullable=False),
)

VIEWS = {
    "v_monthly_spend": """
        SELECT d.year, d.month, c.currency_code,
               COUNT(*) AS invoices, SUM(f.total_amount) AS total_spend
        FROM fact_invoice f
        JOIN dim_date d ON d.date_key = f.invoice_date_key
        JOIN dim_currency c ON c.currency_key = f.currency_key
        GROUP BY d.year, d.month, c.currency_code""",
    "v_supplier_spend": """
        SELECT s.supplier_name, c.currency_code,
               COUNT(*) AS invoices, SUM(f.total_amount) AS total_spend
        FROM fact_invoice f
        JOIN dim_supplier s ON s.supplier_key = f.supplier_key
        JOIN dim_currency c ON c.currency_key = f.currency_key
        GROUP BY s.supplier_name, c.currency_code""",
    "v_item_spend": """
        SELECT i.description, c.currency_code,
               SUM(l.quantity) AS quantity, SUM(l.line_total) AS line_spend
        FROM fact_invoice_line l
        JOIN dim_item i ON i.item_key = l.item_key
        JOIN fact_invoice f ON f.invoice_key = l.invoice_key
        JOIN dim_currency c ON c.currency_key = f.currency_key
        GROUP BY i.description, c.currency_code""",
}


def date_row(d: date) -> dict:
    return {
        "date_key": d.year * 10000 + d.month * 100 + d.day,
        "full_date": d,
        "year": d.year,
        "quarter": (d.month - 1) // 3 + 1,
        "month": d.month,
        "month_name": calendar.month_name[d.month],
        "day": d.day,
        "iso_week": d.isocalendar()[1],
        "weekday_name": calendar.day_name[d.weekday()],
        "is_weekend": d.weekday() >= 5,
    }


def create_schema(engine, first_year: int = 2024, last_year: int = 2027, refresh_views: bool = False) -> None:
    """Create missing tables, fill dim_date (if empty) and create missing analytics views.

    Existing views are left alone unless refresh_views=True: dropping a view waits for every
    other session that is using the database, which can look like a hang.
    """
    metadata.create_all(engine)
    with engine.begin() as conn:
        if conn.execute(select(func.count()).select_from(dim_date)).scalar_one() == 0:
            day, end = date(first_year, 1, 1), date(last_year, 12, 31)
            rows = []
            while day <= end:
                rows.append(date_row(day))
                day += timedelta(days=1)
            conn.execute(insert(dim_date), rows)
        existing = set(inspect(conn).get_view_names())
        for name, sql in VIEWS.items():
            if name in existing and not refresh_views:
                continue
            conn.execute(text(f"DROP VIEW IF EXISTS {name}"))
            conn.execute(text(f"CREATE VIEW {name} AS {sql}"))


def drop_schema(engine) -> None:
    with engine.begin() as conn:
        for name in VIEWS:
            conn.execute(text(f"DROP VIEW IF EXISTS {name}"))
    metadata.drop_all(engine)
