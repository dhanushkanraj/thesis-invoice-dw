"""Queries for the dashboard. Every function returns a pandas DataFrame or a small dict."""
import pandas as pd
from sqlalchemy import text


def _df(engine, sql: str, **params) -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params)


def overview(engine) -> dict:
    row = _df(engine, "SELECT COUNT(*) AS n, COALESCE(SUM(line_count), 0) AS lines FROM fact_invoice").iloc[0]
    pending = _df(engine, "SELECT COUNT(*) AS n FROM review_queue WHERE status = 'pending'").iloc[0]["n"]
    return {"invoices": int(row["n"]), "lines": int(row["lines"]), "pending_review": int(pending)}


def currencies(engine) -> list[str]:
    return _df(engine, "SELECT currency_code FROM dim_currency ORDER BY currency_code")["currency_code"].tolist()


def monthly_spend(engine, currency: str) -> pd.DataFrame:
    df = _df(engine, "SELECT year, month, invoices, total_spend FROM v_monthly_spend "
                     "WHERE currency_code = :c ORDER BY year, month", c=currency)
    df["month"] = df["year"].astype(str) + "-" + df["month"].astype(int).astype(str).str.zfill(2)
    df["total_spend"] = df["total_spend"].astype(float)
    return df[["month", "invoices", "total_spend"]]


def top_suppliers(engine, currency: str, n: int = 10) -> pd.DataFrame:
    df = _df(engine, "SELECT supplier_name, invoices, total_spend FROM v_supplier_spend "
                     "WHERE currency_code = :c ORDER BY total_spend DESC LIMIT :n", c=currency, n=n)
    df["total_spend"] = df["total_spend"].astype(float)
    return df


def top_items(engine, currency: str, n: int = 10) -> pd.DataFrame:
    df = _df(engine, "SELECT description, quantity, line_spend FROM v_item_spend "
                     "WHERE currency_code = :c ORDER BY line_spend DESC LIMIT :n", c=currency, n=n)
    df["line_spend"] = df["line_spend"].astype(float)
    df["quantity"] = df["quantity"].astype(float)
    return df


def review_mix(engine) -> pd.DataFrame:
    return _df(engine, "SELECT review_status, input_type, COUNT(*) AS invoices FROM fact_invoice "
                       "GROUP BY review_status, input_type ORDER BY review_status, input_type")
