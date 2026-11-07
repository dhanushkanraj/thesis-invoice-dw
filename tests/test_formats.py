import re
from datetime import date

import pytest

from invoice_pipeline.formats import (
    LOCALES,
    format_date,
    format_money,
    format_number,
    get_locale,
)

D = date(2025, 3, 5)


def test_number_german():
    de = get_locale("de")
    assert format_number(1234.56, de) == "1.234,56"
    assert format_number(1234567.5, de) == "1.234.567,50"
    assert format_number(5, de) == "5,00"
    assert format_number(0, de) == "0,00"


def test_number_english_locales():
    for code in ("us", "uk", "en_eu"):
        loc = get_locale(code)
        assert format_number(1234.56, loc) == "1,234.56"
        assert format_number(1234567.5, loc) == "1,234,567.50"
        assert format_number(5, loc) == "5.00"


def test_number_negative():
    assert format_number(-1234.5, get_locale("de")) == "-1.234,50"
    assert format_number(-1234.5, get_locale("us")) == "-1,234.50"


def test_dates():
    assert format_date(D, get_locale("de")) == "05.03.2025"
    assert format_date(D, get_locale("uk")) == "05/03/2025"
    assert format_date(D, get_locale("us")) == "March 5, 2025"
    assert format_date(D, get_locale("en_eu")) == "5 March 2025"


def test_money():
    assert format_money(1234.56, get_locale("de")) == "1.234,56 €"
    assert format_money(1234.56, get_locale("us")) == "$1,234.56"
    assert format_money(1234.56, get_locale("uk")) == "£1,234.56"
    assert format_money(1234.56, get_locale("en_eu")) == "€1,234.56"


def test_currency_codes_are_iso_format():
    for loc in LOCALES.values():
        assert re.fullmatch(r"[A-Z]{3}", loc.currency)


def test_all_locales_define_the_same_labels():
    reference = set(LOCALES["de"].labels)
    for loc in LOCALES.values():
        assert set(loc.labels) == reference


def test_unknown_locale_raises():
    with pytest.raises(ValueError):
        get_locale("fr")