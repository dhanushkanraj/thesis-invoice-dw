"""M3: validate an extracted invoice against its own source text and business rules.

Input:  the model's prediction (dict) and the invoice text lines.
Output: a repaired prediction plus a list of issues.

Two severities:
  repair  an OPTIONAL field (subtotal, due_date, supplier_tax_id) whose value is not printed
          in the document is set to null. Logged, but does not need a person.
  review  something is wrong or suspicious that the code cannot decide: the invoice goes to
          the human review queue. Required fields that fail a check are set to null.

Checks:
  type        every value has the schema's type (strict: "12,5" for a number is rejected)
  grounding   amounts, dates, ids and the supplier name must appear in the source text
  arithmetic  quantity x unit price = line total; line totals = subtotal; subtotal + tax = total
  dates       due date not before invoice date
  supplier    a supplier name holds at most one company legal form
  required    invoice number, supplier, date, total and at least one line item are present
"""
import re
from dataclasses import dataclass
from datetime import date

from invoice_pipeline.baseline import DATE_RE, MONEY_RE, find_currency, parse_date, parse_money

TOLERANCE = 0.011  # euro cents: allows for rounding of line totals
REQUIRED = ("invoice_number", "supplier_name", "invoice_date", "total_amount")
OPTIONAL = ("subtotal", "due_date", "supplier_tax_id")
STRING_FIELDS = ("invoice_number", "supplier_name", "supplier_tax_id", "invoice_date", "due_date", "currency")
MONEY_FIELDS = ("subtotal", "tax_amount", "total_amount")
LEGAL_TOKEN_RE = re.compile(r"(?<!\w)(?:GmbH & Co\. KG|GmbH|AG|e\.K\.|B\.V\.|Ltd|PLC|Inc\.|LLC|Corp\.|KG)(?!\w)")


@dataclass(frozen=True)
class Issue:
    field: str
    rule: str
    severity: str  # "repair" or "review"
    message: str


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _text_facts(lines: list[str]) -> dict:
    text = " ".join(lines)
    amounts = []
    for line in lines:
        for m in re.finditer(MONEY_RE, line):
            value = parse_money(m.group(0))
            if value is not None:
                amounts.append(value)
    dates = set()
    for m in re.finditer(DATE_RE, text, re.I):
        d = parse_date(m.group(0))
        if d:
            dates.add(d)
    return {"text": text, "amounts": amounts, "dates": dates, "currency": find_currency(text)}


def _amount_printed(value: float, facts: dict) -> bool:
    return any(abs(value - a) < 0.005 for a in facts["amounts"])


def validate(pred: dict, lines: list[str]) -> tuple[dict, list[Issue]]:
    issues: list[Issue] = []
    facts = _text_facts(lines)
    out = {k: pred.get(k) for k in (*STRING_FIELDS, *MONEY_FIELDS)}

    def drop(field: str, rule: str, message: str) -> None:
        severity = "repair" if (field in OPTIONAL and rule == "grounding") else "review"
        issues.append(Issue(field, rule, severity, message))
        out[field] = None

    # 1. types
    for f in STRING_FIELDS:
        if out[f] is not None and not isinstance(out[f], str):
            drop(f, "type", f"{f} is not text: {out[f]!r}")
    for f in MONEY_FIELDS:
        if out[f] is not None and not _is_number(out[f]):
            drop(f, "type", f"{f} is not a number: {out[f]!r}")

    # 2. grounding: is the value printed in the document?
    for f in ("invoice_number", "supplier_name", "supplier_tax_id"):
        if out[f] is not None and out[f] not in facts["text"]:
            drop(f, "grounding", f"{f} {out[f]!r} not found in the document")
    for f in ("invoice_date", "due_date"):
        if out[f] is not None:
            try:
                date.fromisoformat(out[f])
            except ValueError:
                drop(f, "type", f"{f} is not a valid ISO date: {out[f]!r}")
                continue
            if out[f] not in facts["dates"]:
                drop(f, "grounding", f"{f} {out[f]} not found in the document")
    for f in MONEY_FIELDS:
        if out[f] is not None and not _amount_printed(out[f], facts):
            drop(f, "grounding", f"{f} {out[f]} not found in the document")
    if out["currency"] is not None and facts["currency"] is not None and out["currency"] != facts["currency"]:
        drop("currency", "grounding", f"currency {out['currency']} does not match the document ({facts['currency']})")

    # 3. line items: structure, grounding, arithmetic
    items = []
    raw_items = pred.get("line_items")
    if not isinstance(raw_items, list):
        raw_items = []
    for n, item in enumerate(raw_items, start=1):
        ok = (
            isinstance(item, dict)
            and isinstance(item.get("description"), str)
            and all(_is_number(item.get(k)) for k in ("quantity", "unit_price", "line_total"))
        )
        if not ok:
            issues.append(Issue("line_items", "type", "review", f"item {n} is malformed and was dropped"))
            continue
        items.append(item)
        for k in ("unit_price", "line_total"):
            if not _amount_printed(item[k], facts):
                issues.append(Issue("line_items", "grounding", "review", f"item {n} {k} {item[k]} not found in the document"))
        if abs(item["quantity"] * item["unit_price"] - item["line_total"]) > TOLERANCE:
            issues.append(Issue("line_items", "arithmetic", "review",
                                f"item {n}: {item['quantity']} x {item['unit_price']} != {item['line_total']}"))
    out["line_items"] = items

    # 4. totals
    items_sum = round(sum(i["line_total"] for i in items), 2)
    subtotal, tax, total = out["subtotal"], out["tax_amount"], out["total_amount"]
    if items and subtotal is not None and abs(items_sum - subtotal) > TOLERANCE:
        issues.append(Issue("subtotal", "arithmetic", "review", f"line totals add up to {items_sum}, subtotal is {subtotal}"))
    if subtotal is not None and tax is not None and total is not None and abs(subtotal + tax - total) > TOLERANCE:
        issues.append(Issue("total_amount", "arithmetic", "review", f"{subtotal} + {tax} != {total}"))
    if items and subtotal is None and tax is not None and total is not None and abs(items_sum + tax - total) > TOLERANCE:
        issues.append(Issue("total_amount", "arithmetic", "review", f"line totals {items_sum} + tax {tax} != total {total}"))

    # 5. dates, supplier, required fields
    if out["invoice_date"] and out["due_date"] and out["due_date"] < out["invoice_date"]:
        issues.append(Issue("due_date", "dates", "review", "due date is before the invoice date"))
    if out["supplier_name"] and len(LEGAL_TOKEN_RE.findall(out["supplier_name"])) > 1:
        issues.append(Issue("supplier_name", "supplier", "review", "supplier name contains two company names"))
    for f in REQUIRED:
        if out[f] is None and not any(i.field == f and i.severity == "review" for i in issues):
            issues.append(Issue(f, "required", "review", f"{f} is missing"))
    if not items and not any(i.field == "line_items" for i in issues):
        issues.append(Issue("line_items", "required", "review", "no line items found"))
    return out, issues


def needs_review(issues: list[Issue]) -> bool:
    return any(i.severity == "review" for i in issues)
