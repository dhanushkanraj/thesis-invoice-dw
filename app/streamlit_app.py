"""Invoice warehouse app: dashboard and review screen.

Start with:  streamlit run app/streamlit_app.py
"""
from pathlib import Path

import pandas as pd
import pymupdf
import streamlit as st

from invoice_pipeline import analytics
from invoice_pipeline.db import get_engine
from invoice_pipeline.review import (
    HEADER_KEYS, invoice_id_of, load_prediction, parse_number, pdf_path, pending_documents, record_problems,
    submit_review,
)

ROOT = Path(__file__).resolve().parents[1]
st.set_page_config(page_title="Invoice warehouse", layout="wide")


@st.cache_resource
def engine():
    return get_engine()


def page_image(path: Path, dpi: int = 110) -> bytes:
    doc = pymupdf.open(path)
    png = doc[0].get_pixmap(dpi=dpi).tobytes("png")
    doc.close()
    return png


# ----------------------------------------------------------------- dashboard
def dashboard():
    st.title("Spend dashboard")
    info = analytics.overview(engine())
    c1, c2, c3 = st.columns(3)
    c1.metric("Invoices in the warehouse", info["invoices"])
    c2.metric("Line items", info["lines"])
    c3.metric("Waiting for review", info["pending_review"])
    codes = analytics.currencies(engine())
    if not codes:
        st.info("The warehouse is empty. Run scripts/load_warehouse.py first.")
        return
    currency = st.radio("Currency (never mixed, no exchange rates are assumed)", codes, horizontal=True)

    monthly = analytics.monthly_spend(engine(), currency)
    st.subheader(f"Monthly spend in {currency}")
    st.bar_chart(monthly, x="month", y="total_spend")
    left, right = st.columns(2)
    with left:
        st.subheader("Top suppliers")
        st.dataframe(analytics.top_suppliers(engine(), currency), hide_index=True)
    with right:
        st.subheader("Top items by spend")
        st.dataframe(analytics.top_items(engine(), currency), hide_index=True)
    st.subheader("How the invoices reached the warehouse")
    st.dataframe(analytics.review_mix(engine()), hide_index=True)
    st.caption("auto = passed every check; human_reviewed = corrected by a person in this app; "
               "simulated_review = loaded with the answer key for the evaluation.")


# -------------------------------------------------------------- review screen
def review_screen(source: str):
    st.title("Review queue")
    queue = pending_documents(engine())
    if not queue:
        st.success("Nothing is waiting for review.")
        return
    st.write(f"{len(queue)} invoices are waiting.")
    ids = [q["document_id"] for q in queue]
    chosen = st.selectbox("Invoice", ids)
    item = next(q for q in queue if q["document_id"] == chosen)
    invoice_id = invoice_id_of(chosen)
    record = load_prediction(ROOT, source, item["input_type"], invoice_id)

    doc_col, form_col = st.columns([1, 1])
    with doc_col:
        st.subheader("Document")
        path = pdf_path(ROOT, item["input_type"], invoice_id)
        if path.exists():
            st.image(page_image(path), width=560)
        else:
            st.warning(f"File not found: {path}")
    with form_col:
        st.subheader("Why it was flagged")
        for issue in item["issues"]:
            if issue.get("severity") == "review":
                st.markdown(f"- **{issue['field']}** ({issue['rule']}): {issue['message']}")
        st.subheader("Correct the values")
        with st.form(f"form_{chosen}"):
            values = {}
            for key in HEADER_KEYS:
                current = record[key]
                shown = "" if current is None else str(current)
                values[key] = st.text_input(key, shown, key=f"{chosen}_{key}")
            # Force decimal columns: pandas would otherwise treat whole-number columns as integers
            # and the table would not accept a decimal point.
            table = pd.DataFrame(record["line_items"], columns=["description", "quantity", "unit_price", "line_total"])
            table = table.astype({"quantity": "float64", "unit_price": "float64", "line_total": "float64"})
            items_df = st.data_editor(
                table,
                num_rows="dynamic", key=f"{chosen}_items",
                column_config={
                    "quantity": st.column_config.NumberColumn("quantity", step=0.001, format="%g"),
                    "unit_price": st.column_config.NumberColumn("unit_price", step=0.01, format="%.2f"),
                    "line_total": st.column_config.NumberColumn("line_total", step=0.01, format="%.2f"),
                },
            )
            confirm = st.checkbox("I compared every value with the document", key=f"{chosen}_confirm")
            submitted = st.form_submit_button("Save and load into the warehouse")
        if submitted:
            try:
                rec = {k: (values[k].strip() or None) for k in HEADER_KEYS}
                for k in ("subtotal", "tax_amount", "total_amount"):
                    rec[k] = parse_number(values[k])
                rec["line_items"] = []
                for n, r in enumerate(items_df.to_dict("records"), start=1):
                    description = "" if pd.isna(r["description"]) else str(r["description"]).strip()
                    if not description:
                        continue
                    numbers = {k: r[k] for k in ("quantity", "unit_price", "line_total")}
                    if any(v is None or pd.isna(v) for v in numbers.values()):
                        raise ValueError(f"row {n} has an empty number")
                    rec["line_items"].append({"description": description,
                                              **{k: float(v) for k, v in numbers.items()}})
            except (ValueError, TypeError) as e:
                st.error(f"A number could not be read: {e}")
                return
            errors, warnings = record_problems(rec)
            for e in errors:
                st.error(e)
            for w in warnings:
                st.warning(w)
            if errors:
                return
            if not confirm:
                st.error("Tick the box to confirm that you checked the values against the document.")
                return
            submit_review(engine(), ROOT, chosen, item["input_type"], rec)
            st.success(f"{chosen} saved and loaded. Refresh the list or pick the next invoice.")
            st.rerun()


page = st.sidebar.radio("Page", ["Dashboard", "Review queue"])
source = st.sidebar.text_input("Pipeline output used as the starting point", "m3_qwen3-4b")
st.sidebar.caption("Folder under outputs/ that holds the validated predictions.")
(dashboard if page == "Dashboard" else lambda: review_screen(source))()
