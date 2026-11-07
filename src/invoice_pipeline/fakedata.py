"""Synthetic invoice CONTENT generator (no PDF drawing here).

Produces the ground-truth Invoice plus printed-only details (addresses,
distractor numbers). All money uses Decimal with half-up rounding, so every
answer key is arithmetically exact. A "missing" field is None in the ground
truth; layouts must print a field only if it is not None.

All randomness comes from the Random instance passed in, so a fixed seed
reproduces the same data.
"""
import random
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from invoice_pipeline.formats import LOCALES
from invoice_pipeline.schema import Invoice, LineItem

CENT = Decimal("0.01")
MAX_ITEMS = 15
START_DATE = date(2025, 1, 1)
END_DATE = date(2026, 6, 30)

DEFAULT_MISSING_RATES = {"due_date": 0.20, "supplier_tax_id": 0.25, "subtotal": 0.10}

# (description, min_price, max_price, quantity_kind)
PRODUCTS = {
    "de": [
        ("Druckerpapier A4, 500 Blatt", 4, 9, "int"),
        ("Toner schwarz, Kartusche", 45, 120, "int"),
        ("Netzwerkkabel Cat6, 5 m", 3, 12, "int"),
        ("USB-C Docking Station", 70, 220, "int"),
        ("Monitor 27 Zoll", 180, 420, "int"),
        ("Kabellose Tastatur", 25, 90, "int"),
        ("Ergonomischer Bürostuhl", 150, 480, "int"),
        ("LED-Schreibtischlampe", 20, 70, "int"),
        ("Software-Lizenz, jährlich", 90, 600, "int"),
        ("Beratungsleistung, Stunden", 80, 160, "hours"),
        ("Server-Wartung, Stunden", 70, 140, "hours"),
        ("Lieferung und Montage", 40, 180, "int"),
        ("Verpackungskartons, 25 Stück", 12, 35, "int"),
        ("Reinigungsservice, monatlich", 150, 600, "int"),
        ("Ordner A4, breit", 2, 5, "int"),
    ],
    "en": [
        ("Printer paper A4, 500 sheets", 4, 9, "int"),
        ("Toner cartridge, black", 45, 120, "int"),
        ("Network cable Cat6, 5 m", 3, 12, "int"),
        ("USB-C docking station", 70, 220, "int"),
        ("27-inch monitor", 180, 420, "int"),
        ("Wireless keyboard", 25, 90, "int"),
        ("Ergonomic office chair", 150, 480, "int"),
        ("LED desk lamp", 20, 70, "int"),
        ("Software license, annual", 90, 600, "int"),
        ("Consulting services, hours", 80, 160, "hours"),
        ("Server maintenance, hours", 70, 140, "hours"),
        ("Delivery and installation", 40, 180, "int"),
        ("Shipping cartons, pack of 25", 12, 35, "int"),
        ("Cleaning service, monthly", 150, 600, "int"),
        ("Ring binder A4", 2, 5, "int"),
    ],
}

HOUR_CHOICES = ["1", "1.5", "2", "2.5", "4", "7.5", "8"]

# (rate in percent, weight) per locale. Illustrative, not tied to real jurisdictions.
TAX_RATES = {
    "de": [("19", 70), ("7", 20), ("0", 10)],
    "en_eu": [("21", 40), ("23", 25), ("9", 15), ("0", 20)],
    "uk": [("20", 85), ("0", 15)],
    "us": [("0", 40), ("6.25", 15), ("7", 15), ("8.25", 20), ("8.875", 10)],
}

NAME_PARTS = {
    "de": (
        ["Müller", "Schneider", "Fischer", "Weber", "Becker", "Hoffmann", "Wagner", "Koch"],
        ["Bürotechnik", "Elektro", "Logistik", "Maschinenbau", "Software", "Großhandel", "IT-Service"],
        ["GmbH", "AG", "GmbH & Co. KG", "e.K."],
    ),
    "en_eu": (
        ["Ashford", "Brightline", "Harbor", "Summit", "Evergreen", "Crestview", "Bluepeak", "Ironwood"],
        ["Supplies", "Logistics", "Systems", "Consulting", "Industrial", "Technologies", "Wholesale"],
        ["B.V.", "Ltd", "GmbH"],
    ),
    "us": (
        ["Ashford", "Brightline", "Harbor", "Summit", "Evergreen", "Crestview", "Bluepeak", "Ironwood"],
        ["Supplies", "Logistics", "Systems", "Consulting", "Industrial", "Technologies", "Wholesale"],
        ["Inc.", "LLC", "Corp."],
    ),
    "uk": (
        ["Ashford", "Brightline", "Harbor", "Summit", "Evergreen", "Crestview", "Bluepeak", "Ironwood"],
        ["Supplies", "Logistics", "Systems", "Consulting", "Industrial", "Technologies", "Wholesale"],
        ["Ltd", "Ltd", "PLC"],
    ),
}

BUYERS = {
    "de": ["Nordlicht Handels GmbH", "Rheinwerk Services GmbH", "Alpenblick Vertrieb GmbH"],
    "en": ["Lakeside Retail Ltd", "Redwood Trading Co.", "Meridian Services Inc."],
}

STREETS = {
    "de": ["Hauptstraße", "Bahnhofstraße", "Gartenweg", "Industriestraße", "Lindenallee"],
    "en_eu": ["Kerkstraat", "Dorpsstraat", "Stationsweg", "Molenlaan", "Industrieweg"],
    "us": ["Maple Street", "Oak Avenue", "Cedar Lane", "Washington Boulevard", "Lakeview Drive"],
    "uk": ["High Street", "Station Road", "Church Lane", "Victoria Road", "Mill Lane"],
}

CITY_LINES = {
    "de": ["10115 Berlin", "80331 München", "20095 Hamburg", "50667 Köln", "60311 Frankfurt am Main"],
    "en_eu": ["1011 AB Amsterdam", "3011 AA Rotterdam", "3511 AB Utrecht", "5611 AB Eindhoven"],
    "us": ["New York, NY 10001", "Chicago, IL 60601", "Austin, TX 73301", "Seattle, WA 98101"],
    "uk": ["London EC1A 1BB", "Manchester M1 1AE", "Bristol BS1 4DJ", "Leeds LS1 1UR"],
}

INVOICE_NUMBER_STYLES = {
    "de": ["RE-{y}-{n:04d}", "R{y}{n:05d}", "{y}/{n:04d}", "RN-{n:06d}"],
    "en": ["INV-{y}-{n:04d}", "INV{n:06d}", "{y}/{n:04d}", "#{n:05d}"],
}


@dataclass(frozen=True)
class PrintExtras:
    """Details printed on the invoice but NOT part of the extraction schema."""

    supplier_address: tuple
    buyer_name: str
    buyer_address: tuple
    purchase_order: str
    customer_number: str
    iban: str | None


@dataclass(frozen=True)
class GeneratedInvoice:
    locale_code: str
    truth: Invoice
    extras: PrintExtras


def money(x: Decimal) -> Decimal:
    """Round to cents, half-up (how invoices round)."""
    return x.quantize(CENT, rounding=ROUND_HALF_UP)


def compute_amounts(lines, tax_rate_percent):
    """lines: iterable of (quantity, unit_price) as Decimals.

    Returns (line_totals, subtotal, tax_amount, total_amount).
    """
    line_totals = [money(q * p) for q, p in lines]
    subtotal = sum(line_totals, Decimal("0.00"))
    tax = money(subtotal * tax_rate_percent / Decimal(100))
    return line_totals, subtotal, tax, money(subtotal + tax)


def _language(locale_code: str) -> str:
    return "de" if locale_code == "de" else "en"


def _digits(rng: random.Random, n: int) -> str:
    return "".join(str(rng.randint(0, 9)) for _ in range(n))


def make_supplier_name(rng: random.Random, locale_code: str) -> str:
    stems, sectors, suffixes = NAME_PARTS[locale_code]
    return f"{rng.choice(stems)} {rng.choice(sectors)} {rng.choice(suffixes)}"


def make_tax_id(rng: random.Random, locale_code: str) -> str:
    if locale_code == "de":
        return "DE" + _digits(rng, 9)
    if locale_code == "uk":
        return "GB" + _digits(rng, 9)
    if locale_code == "us":
        return f"{_digits(rng, 2)}-{_digits(rng, 7)}"
    if rng.random() < 0.5:
        return f"NL{_digits(rng, 9)}B{_digits(rng, 2)}"
    return f"FR{_digits(rng, 11)}"


def make_iban(rng: random.Random, locale_code: str) -> str | None:
    """Random IBAN-shaped string (checksum NOT valid). Only for euro locales."""
    if locale_code == "de":
        raw = "DE" + _digits(rng, 20)
    elif locale_code == "en_eu":
        raw = "NL" + _digits(rng, 2) + "TEST" + _digits(rng, 10)
    else:
        return None
    return " ".join(raw[i:i + 4] for i in range(0, len(raw), 4))


def make_address(rng: random.Random, locale_code: str) -> tuple:
    street = rng.choice(STREETS[locale_code])
    number = rng.randint(1, 150)
    line1 = f"{number} {street}" if locale_code in ("us", "uk") else f"{street} {number}"
    return (line1, rng.choice(CITY_LINES[locale_code]))


def generate_invoice(
    rng: random.Random,
    locale_code: str,
    n_items: int | None = None,
    missing_rates: dict | None = None,
) -> GeneratedInvoice:
    if locale_code not in LOCALES:
        raise ValueError(f"Unknown locale {locale_code!r}. Available: {sorted(LOCALES)}")
    locale = LOCALES[locale_code]
    lang = _language(locale_code)
    rates = {**DEFAULT_MISSING_RATES, **(missing_rates or {})}

    if n_items is None:
        low, high = rng.choices([(1, 3), (4, 8), (9, 15)], weights=[30, 45, 25])[0]
        n_items = rng.randint(low, high)
    if not 1 <= n_items <= MAX_ITEMS:
        raise ValueError(f"n_items must be between 1 and {MAX_ITEMS}, got {n_items}")

    # Line items
    chosen = rng.sample(PRODUCTS[lang], n_items)
    lines = []
    for description, price_min, price_max, kind in chosen:
        price = Decimal(rng.randint(price_min * 100, price_max * 100)) / 100
        if kind == "int":
            quantity = Decimal(rng.randint(1, 20))
        else:
            quantity = Decimal(rng.choice(HOUR_CHOICES))
        lines.append((description, quantity, price))

    # Tax and totals
    rate_options = TAX_RATES[locale_code]
    rate = Decimal(rng.choices([r for r, _ in rate_options], weights=[w for _, w in rate_options])[0])
    line_totals, subtotal, tax, total = compute_amounts([(q, p) for _, q, p in lines], rate)

    # Dates
    invoice_date = START_DATE + timedelta(days=rng.randint(0, (END_DATE - START_DATE).days))
    due_date = invoice_date + timedelta(days=rng.choice([14, 30, 30, 45, 60]))

    # Identifiers and parties
    invoice_number = rng.choice(INVOICE_NUMBER_STYLES[lang]).format(
        y=invoice_date.year, n=rng.randint(1, 9999)
    )
    supplier_name = make_supplier_name(rng, locale_code)
    tax_id = make_tax_id(rng, locale_code)

    # Missing-field decisions. All draws happen every time, so changing a rate
    # does not shift the random sequence used for everything else.
    miss_due = rng.random() < rates["due_date"]
    miss_tax_id = rng.random() < rates["supplier_tax_id"]
    miss_subtotal = rng.random() < rates["subtotal"]

    truth = Invoice(
        invoice_number=invoice_number,
        supplier_name=supplier_name,
        supplier_tax_id=None if miss_tax_id else tax_id,
        invoice_date=invoice_date.isoformat(),
        due_date=None if miss_due else due_date.isoformat(),
        currency=locale.currency,
        subtotal=None if miss_subtotal else float(subtotal),
        tax_amount=float(tax),
        total_amount=float(total),
        line_items=[
            LineItem(
                description=desc,
                quantity=float(qty),
                unit_price=float(price),
                line_total=float(line_total),
            )
            for (desc, qty, price), line_total in zip(lines, line_totals)
        ],
    )

    # Printed-only details (distractors)
    year = invoice_date.year
    if lang == "de":
        purchase_order = f"BE-{year}-{rng.randint(1000, 9999)}"
        customer_number = f"KD-{rng.randint(10000, 99999)}"
    else:
        purchase_order = f"PO-{year}-{rng.randint(1000, 9999)}"
        customer_number = f"CUST-{rng.randint(10000, 99999)}"

    extras = PrintExtras(
        supplier_address=make_address(rng, locale_code),
        buyer_name=rng.choice(BUYERS[lang]),
        buyer_address=make_address(rng, locale_code),
        purchase_order=purchase_order,
        customer_number=customer_number,
        iban=make_iban(rng, locale_code),
    )
    return GeneratedInvoice(locale_code=locale_code, truth=truth, extras=extras)