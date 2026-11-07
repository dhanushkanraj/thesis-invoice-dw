"""M1: rule-based extraction (regular expressions and keywords, no LLM).

Input: the visual lines of an invoice (see extract_text.py).
Output: a dict with the same fields as the Invoice schema.

The rules know common German and English labels and a few company legal forms.
They do NOT know the layouts used to generate the dataset; they were written
and tuned only by looking at development/tuning invoices.
"""
import re
from datetime import date

MONTHS = {
    m: i + 1
    for i, names in enumerate(
        [
            ("january", "januar"), ("february", "februar"), ("march", "märz"), ("april",),
            ("may", "mai"), ("june", "juni"), ("july", "juli"), ("august",),
            ("september",), ("october", "oktober"), ("november",), ("december", "dezember"),
        ]
    )
    for m in names
}
_MONTH_RE = "|".join(sorted(MONTHS, key=len, reverse=True))
DATE_RE = (
    r"(?:\d{1,2}\.\d{1,2}\.\d{4}"
    r"|\d{1,2}/\d{1,2}/\d{4}"
    rf"|\d{{1,2}}\s+(?:{_MONTH_RE})\s+\d{{4}}"
    rf"|(?:{_MONTH_RE})\s+\d{{1,2}},\s*\d{{4}})"
)
MONEY_RE = r"[€$£]?\s?\d[\d.,]*[.,]\d{2}\s?[€$£]?"

LABELS = {
    "invoice_number": r"(?:Rechnungsnummer|Rechnungs-Nr\.?|Rechnung\s*Nr\.?|Invoice\s*(?:No\.?|Number|#))",
    "invoice_date": r"(?:Rechnungsdatum|Invoice\s*Date)",
    "due_date": r"(?:F[äa]llig\s*am|Zahlbar\s*bis|Due\s*Date|Payment\s*Due)",
    "customer": r"(?:Kundennummer|Customer\s*No\.?)",
    "po": r"(?:Bestellnummer|PO\s*Number|Purchase\s*Order)",
}
TAX_ID_RE = re.compile(r"(?:USt-?IdNr\.?|USt\.?-?ID|VAT\s*ID|Tax\s*ID|VAT\s*No\.?)\s*:?\s*([A-Z0-9][A-Z0-9\-]{5,})")
LEGAL_FORM_RE = re.compile(
    r"^(.*?\s(?:GmbH & Co\. KG|GmbH|AG|e\.K\.|B\.V\.|Ltd|PLC|Inc\.|LLC|Corp\.|KG))(?=\s|$)"
)
SUBTOTAL_RE = re.compile(rf"^(?:Zwischensumme|Nettobetrag|Subtotal|Net\s*Total)\b[^\d]*({MONEY_RE})$", re.I)
TAX_RE = re.compile(rf"^(?:MwSt\.?|USt\.?|Tax|VAT|Sales\s*Tax)\b(?!\s*(?:ID|No))[^\d]*(?:\d+(?:[.,]\d+)?\s?%\s*)?({MONEY_RE})$", re.I)
TOTAL_RE = re.compile(rf"^(?:Gesamtbetrag|Gesamtsumme|Rechnungsbetrag|Total(?:\s*Amount|\s*Due)?|Amount\s*Due)\b[^\d]*({MONEY_RE})$", re.I)
ITEM_RE = re.compile(
    rf"^(?P<desc>.+?)\s+(?P<qty>\d+(?:[.,]\d+)?)\s+(?P<up>{MONEY_RE})\s+(?P<lt>{MONEY_RE})$"
)
POS_HEADER_RE = re.compile(r"^(?:No\.|Nr\.|Pos\.)\s+(?:Description|Beschreibung)", re.I)


def parse_money(text: str) -> float | None:
    s = re.sub(r"[€$£\s]", "", text)
    m = re.search(r"[.,](\d{2})$", s)
    if not m:
        return None
    integer = re.sub(r"[.,]", "", s[: m.start()])
    if not integer.isdigit():
        return None
    return float(f"{integer}.{m.group(1)}")


def parse_date(text: str) -> str | None:
    s = text.strip()
    try:
        m = re.fullmatch(r"(\d{1,2})[./](\d{1,2})[./](\d{4})", s)
        if m:  # day first (an assumption; US-style slashes are not handled)
            return date(int(m[3]), int(m[2]), int(m[1])).isoformat()
        m = re.fullmatch(rf"(\d{{1,2}})\s+({_MONTH_RE})\s+(\d{{4}})", s, re.I)
        if m:
            return date(int(m[3]), MONTHS[m[2].lower()], int(m[1])).isoformat()
        m = re.fullmatch(rf"({_MONTH_RE})\s+(\d{{1,2}}),\s*(\d{{4}})", s, re.I)
        if m:
            return date(int(m[3]), MONTHS[m[1].lower()], int(m[2])).isoformat()
    except ValueError:
        return None
    return None


def parse_quantity(text: str) -> float:
    return float(text.replace(",", "."))


def _find_labels(line: str) -> list[tuple[int, int, str]]:
    found = []
    for name, pattern in LABELS.items():
        for m in re.finditer(pattern, line, re.I):
            found.append((m.start(), m.end(), name))
    return sorted(found)


_VALUE_RE = {
    "invoice_number": r"\S+",
    "invoice_date": DATE_RE,
    "due_date": DATE_RE,
    "customer": r"\S+",
    "po": r"\S+",
}


def header_fields(lines: list[str]) -> dict[str, str]:
    """invoice_number / invoice_date / due_date as raw strings (None if not found)."""
    out: dict[str, str] = {}
    for idx, line in enumerate(lines):
        labels = _find_labels(line)
        if len(labels) >= 2 and idx + 1 < len(lines):
            # grid: a row of labels, the values follow on the next line in the same order
            rest = lines[idx + 1].strip()
            for _, _, name in labels:
                m = re.match(_VALUE_RE[name], rest, re.I)
                if not m:
                    break
                out.setdefault(name, m.group(0))
                rest = rest[m.end():].lstrip()
            continue
        for _, end, name in labels:
            after = line[end:].lstrip(" :")
            m = re.match(_VALUE_RE[name], after, re.I)
            if m and (name != "invoice_number" or re.search(r"\d", m.group(0))):
                out.setdefault(name, m.group(0))
    return out


def find_currency(text: str) -> str | None:
    for symbol, code in (("€", "EUR"), ("$", "USD"), ("£", "GBP")):
        if symbol in text:
            return code
    m = re.search(r"\b(EUR|USD|GBP)\b", text)
    return m.group(1) if m else None


def find_supplier(lines: list[str]) -> str | None:
    for line in lines:
        m = LEGAL_FORM_RE.match(line)
        if m:
            return m.group(1).strip()
    return None


def _last_money(lines: list[str], regex: re.Pattern) -> float | None:
    value = None
    for line in lines:
        m = regex.match(line.strip())
        if m:
            parsed = parse_money(m.group(1))
            if parsed is not None:
                value = parsed
    return value


def find_items(lines: list[str]) -> list[dict]:
    has_pos = any(POS_HEADER_RE.match(l) for l in lines)
    items = []
    for line in lines:
        text = re.sub(r"^\d+\s+", "", line) if has_pos else line
        m = ITEM_RE.match(text)
        if not m:
            continue
        unit_price, line_total = parse_money(m["up"]), parse_money(m["lt"])
        if unit_price is None or line_total is None:
            continue
        items.append(
            {
                "description": m["desc"].strip(),
                "quantity": parse_quantity(m["qty"]),
                "unit_price": unit_price,
                "line_total": line_total,
            }
        )
    return items


def extract_invoice(lines: list[str]) -> dict:
    text = "\n".join(lines)
    raw = header_fields(lines)
    tax_id = TAX_ID_RE.search(text)
    return {
        "invoice_number": raw.get("invoice_number"),
        "supplier_name": find_supplier(lines),
        "supplier_tax_id": tax_id.group(1) if tax_id else None,
        "invoice_date": parse_date(raw["invoice_date"]) if "invoice_date" in raw else None,
        "due_date": parse_date(raw["due_date"]) if "due_date" in raw else None,
        "currency": find_currency(text),
        "subtotal": _last_money(lines, SUBTOTAL_RE),
        "tax_amount": _last_money(lines, TAX_RE),
        "total_amount": _last_money(lines, TOTAL_RE),
        "line_items": find_items(lines),
    }
