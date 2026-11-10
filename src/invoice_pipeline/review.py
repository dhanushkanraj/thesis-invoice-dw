"""Logic behind the review screen: find pending invoices, check a corrected record, save and load it.

A person corrects a flagged invoice while looking at the document, so grounding against the OCR text
is NOT applied here. What is checked: the schema (types, ISO dates, currency code) as errors that
block saving, and the arithmetic as warnings the reviewer may confirm.
"""
import json
import re
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import select

from invoice_pipeline.loader import load_invoice, unloadable_reasons
from invoice_pipeline.schema import Invoice
from invoice_pipeline.validate import TOLERANCE
from invoice_pipeline.warehouse import review_queue

HEADER_KEYS = (
    "invoice_number", "supplier_name", "supplier_tax_id", "invoice_date", "due_date",
    "currency", "subtotal", "tax_amount", "total_amount",
)


def parse_number(text: str) -> float | None:
    """Read a number the way a document prints it: 2,739.43 / 2.739,43 / 7,5 / 7.5 / EUR-free.

    Empty text gives None. With one kind of separator and exactly three digits after it
    (1,234 or 2.739), the separator is a thousands separator; otherwise it is the decimal point.
    Raises ValueError when the text is not a number.
    """
    s = re.sub(r"[€$£\s]", "", text.strip())
    if not s:
        return None
    if "," in s and "." in s:
        decimal = "," if s.rfind(",") > s.rfind(".") else "."
        thousands = "." if decimal == "," else ","
        s = s.replace(thousands, "").replace(decimal, ".")
    elif "," in s or "." in s:
        sep = "," if "," in s else "."
        parts = s.split(sep)
        if len(parts) > 2 or (len(parts[1]) == 3 and parts[0] not in ("", "0", "-0")):
            s = "".join(parts)
        else:
            s = s.replace(",", ".")
    return float(s)


def invoice_id_of(document_id: str) -> str:
    return document_id.rsplit("_", 1)[0]


def pending_documents(engine) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(
            select(review_queue).where(review_queue.c.status == "pending").order_by(review_queue.c.document_id)
        ).mappings().all()
    return [
        {"document_id": r["document_id"], "input_type": r["input_type"], "issues": json.loads(r["issues"])}
        for r in rows
    ]


def pdf_path(root: Path, input_type: str, invoice_id: str) -> Path:
    folder = "pdf" if input_type == "digital" else "scanned"
    return root / "data" / "synthetic" / folder / f"{invoice_id}.pdf"


def load_prediction(root: Path, source: str, input_type: str, invoice_id: str) -> dict:
    """The pipeline's (repaired) prediction as the starting point of the form; every key present."""
    path = root / "outputs" / source / input_type / f"{invoice_id}.json"
    pred = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    record = {k: pred.get(k) for k in HEADER_KEYS}
    record["line_items"] = [
        {k: item.get(k) for k in ("description", "quantity", "unit_price", "line_total")}
        for item in (pred.get("line_items") or []) if isinstance(item, dict)
    ]
    return record


def record_problems(record: dict) -> tuple[list[str], list[str]]:
    """(errors that block saving, warnings the reviewer can confirm)."""
    errors, warnings = [], []
    try:
        Invoice.model_validate(record)
    except ValidationError as e:
        for err in e.errors():
            where = ".".join(str(p) for p in err["loc"])
            errors.append(f"{where}: {err['msg']}")
        return errors, warnings
    errors += [f"{r}" for r in unloadable_reasons(record)]
    items = record["line_items"]
    for n, item in enumerate(items, start=1):
        if abs(item["quantity"] * item["unit_price"] - item["line_total"]) > TOLERANCE:
            warnings.append(f"Item {n}: quantity x unit price is not the line total")
    items_sum = round(sum(i["line_total"] for i in items), 2)
    sub, tax, total = record.get("subtotal"), record.get("tax_amount"), record.get("total_amount")
    if sub is not None and items and abs(items_sum - sub) > TOLERANCE:
        warnings.append(f"Line totals add up to {items_sum}, but the subtotal is {sub}")
    if sub is not None and tax is not None and total is not None and abs(sub + tax - total) > TOLERANCE:
        warnings.append(f"Subtotal + tax is {round(sub + tax, 2)}, but the total is {total}")
    if sub is None and items and tax is not None and total is not None and abs(items_sum + tax - total) > TOLERANCE:
        warnings.append(f"Line totals + tax is {round(items_sum + tax, 2)}, but the total is {total}")
    return errors, warnings


def submit_review(engine, root: Path, document_id: str, input_type: str, record: dict) -> Path:
    """Save the corrected record under outputs/reviewed/ and load it into the warehouse."""
    errors, _ = record_problems(record)
    if errors:
        raise ValueError("; ".join(errors))
    path = root / "outputs" / "reviewed" / input_type / f"{invoice_id_of(document_id)}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    with engine.begin() as conn:  # also removes the document from the review queue
        load_invoice(conn, document_id, input_type, record, "human_reviewed")
    return path
