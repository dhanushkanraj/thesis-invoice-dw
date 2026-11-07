"""Field-level evaluation of extracted invoices against answer keys.

Outcome per field:
  correct   prediction equals the truth (null == null counts as correct)
  missing   truth has a value, prediction is null
  wrong     both have values but they differ
  spurious  truth is null, prediction has a value (a hallucination)
Line items are compared as multisets of (description, quantity, unit price, total).
"""
from collections import Counter

HEADER_FIELDS = (
    "invoice_number", "supplier_name", "supplier_tax_id", "invoice_date", "due_date",
    "currency", "subtotal", "tax_amount", "total_amount",
)
MONEY_FIELDS = {"subtotal", "tax_amount", "total_amount"}


def _norm_text(v):
    return None if v is None else " ".join(str(v).split())


def field_outcome(field: str, pred, truth) -> str:
    if truth is None:
        return "correct" if pred is None else "spurious"
    if pred is None:
        return "missing"
    if field in MONEY_FIELDS:
        return "correct" if abs(float(pred) - float(truth)) < 0.005 else "wrong"
    return "correct" if _norm_text(pred) == _norm_text(truth) else "wrong"


def _item_key(item: dict) -> tuple:
    return (
        " ".join(str(item["description"]).lower().split()),
        round(float(item["quantity"]), 3),
        round(float(item["unit_price"]), 2),
        round(float(item["line_total"]), 2),
    )


def item_scores(pred_items: list[dict], truth_items: list[dict]) -> dict:
    p = Counter(_item_key(i) for i in pred_items)
    t = Counter(_item_key(i) for i in truth_items)
    tp = sum((p & t).values())
    precision = tp / len(pred_items) if pred_items else (1.0 if not truth_items else 0.0)
    recall = tp / len(truth_items) if truth_items else (1.0 if not pred_items else 0.0)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1, "exact": p == t}


def evaluate_invoice(pred: dict, truth: dict) -> dict:
    outcomes = {f: field_outcome(f, pred.get(f), truth.get(f)) for f in HEADER_FIELDS}
    items = item_scores(pred.get("line_items") or [], truth.get("line_items") or [])
    all_header_ok = all(o == "correct" for o in outcomes.values())
    return {
        "outcomes": outcomes,
        "items": items,
        "invoice_exact": all_header_ok and items["exact"],
    }
