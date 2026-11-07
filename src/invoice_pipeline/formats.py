"""Locale-specific formatting for synthetic invoices.

Ground truth always stores plain values (1234.56, 2025-03-14). This module
only controls how those values are PRINTED on a generated invoice, so the
extraction pipeline has to cope with realistic format variation.

No system locale is used, so output is identical on every machine.
"""
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Locale:
    code: str
    currency: str            # ISO 4217 code, as stored in ground truth
    currency_symbol: str     # as printed on the invoice
    symbol_after: bool       # True: "1.234,56 EUR-symbol"; False: symbol before the amount
    decimal: str
    thousands: str
    date_style: str          # key into DATE_FORMATTERS
    labels: dict


DATE_FORMATTERS = {
    "dmy_dot": lambda d: f"{d.day:02d}.{d.month:02d}.{d.year}",       # 14.03.2025
    "dmy_slash": lambda d: f"{d.day:02d}/{d.month:02d}/{d.year}",     # 14/03/2025
    "long_us": lambda d: f"{d:%B} {d.day}, {d.year}",                 # March 14, 2025
    "long_eu": lambda d: f"{d.day} {d:%B} {d.year}",                  # 14 March 2025
}

GERMAN_LABELS = {
    "title": "Rechnung",
    "invoice_number": "Rechnungsnummer",
    "invoice_date": "Rechnungsdatum",
    "due_date": "Fällig am",
    "tax_id": "USt-IdNr.",
    "purchase_order": "Bestellnummer",
    "customer_number": "Kundennummer",
    "description": "Beschreibung",
    "quantity": "Menge",
    "unit_price": "Einzelpreis",
    "line_total": "Gesamt",
    "subtotal": "Zwischensumme",
    "tax": "MwSt.",
    "total": "Gesamtbetrag",
    "page": "Seite",
}

ENGLISH_LABELS = {
    "title": "Invoice",
    "invoice_number": "Invoice No.",
    "invoice_date": "Invoice Date",
    "due_date": "Due Date",
    "tax_id": "VAT ID",
    "purchase_order": "PO Number",
    "customer_number": "Customer No.",
    "description": "Description",
    "quantity": "Qty",
    "unit_price": "Unit Price",
    "line_total": "Amount",
    "subtotal": "Subtotal",
    "tax": "Tax",
    "total": "Total",
    "page": "Page",
}

LOCALES = {
    "de": Locale("de", "EUR", "€", True, ",", ".", "dmy_dot", GERMAN_LABELS),
    "en_eu": Locale("en_eu", "EUR", "€", False, ".", ",", "long_eu", ENGLISH_LABELS),
    "us": Locale("us", "USD", "$", False, ".", ",", "long_us", ENGLISH_LABELS),
    "uk": Locale("uk", "GBP", "£", False, ".", ",", "dmy_slash", ENGLISH_LABELS),
}


def get_locale(code: str) -> Locale:
    try:
        return LOCALES[code]
    except KeyError:
        raise ValueError(f"Unknown locale {code!r}. Available: {sorted(LOCALES)}") from None


def format_number(value: float, locale: Locale, decimals: int = 2) -> str:
    """1234.56 -> '1.234,56' (de) or '1,234.56' (us/uk/en_eu)."""
    s = f"{value:,.{decimals}f}"
    return s.translate(str.maketrans({",": locale.thousands, ".": locale.decimal}))


def format_date(d: date, locale: Locale) -> str:
    return DATE_FORMATTERS[locale.date_style](d)


def format_money(value: float, locale: Locale) -> str:
    """Amount with currency symbol, placed the way the locale prints it."""
    number = format_number(value, locale)
    if locale.symbol_after:
        return f"{number} {locale.currency_symbol}"
    return f"{locale.currency_symbol}{number}"