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


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _norm_text(v):
    return None if v is None else " ".join(str(v).split())


def field_outcome(field: str, pred, truth) -> str:
    if truth is None:
        return "correct" if pred is None else "spurious"
    if pred is None:
        return "missing"
    # Strict typing: a model that answers "1.234,56" (a string) for an amount is wrong,
    # because it did not follow the schema. M3 is where such values get rejected or repaired.
    if field in MONEY_FIELDS:
        if not _is_number(pred):
            return "wrong"
        return "correct" if abs(float(pred) - float(truth)) < 0.005 else "wrong"
    if not isinstance(pred, str):
        return "wrong"
    return "correct" if _norm_text(pred) == _norm_text(truth) else "wrong"


def _item_key(item, index: int) -> tuple:
    """Comparable key for one line item. Malformed items get a unique key that never matches."""
    if not isinstance(item, dict):
        return ("__invalid__", index)
    desc, q, up, lt = (item.get(k) for k in ("description", "quantity", "unit_price", "line_total"))
    if not isinstance(desc, str) or not all(_is_number(x) for x in (q, up, lt)):
        return ("__invalid__", index)
    return (" ".join(desc.lower().split()), round(float(q), 3), round(float(up), 2), round(float(lt), 2))


def item_scores(pred_items, truth_items: list[dict]) -> dict:
    if not isinstance(pred_items, list):
        pred_items = []
    p = Counter(_item_key(i, n) for n, i in enumerate(pred_items))
    t = Counter(_item_key(i, n) for n, i in enumerate(truth_items))
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
