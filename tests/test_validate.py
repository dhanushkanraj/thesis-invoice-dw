from invoice_pipeline.validate import needs_review, validate

LINES = [
    "Müller Elektro GmbH & Co. KG", "USt-IdNr.: DE214263669", "Rechnung",
    "Rechnungsnummer: RE-2025-2947", "Rechnungsdatum: 02.02.2025", "Fällig am: 04.03.2025",
    "Beschreibung Menge Einzelpreis Gesamt",
    "Lieferung und Montage 2 100,00 € 200,00 €",
    "Server-Wartung, Stunden 1,5 40,00 € 60,00 €",
    "Zwischensumme 260,00 €", "MwSt. 49,40 €", "Gesamtbetrag 309,40 €",
]
GOOD = {
    "invoice_number": "RE-2025-2947", "supplier_name": "Müller Elektro GmbH & Co. KG",
    "supplier_tax_id": "DE214263669", "invoice_date": "2025-02-02", "due_date": "2025-03-04",
    "currency": "EUR", "subtotal": 260.0, "tax_amount": 49.4, "total_amount": 309.4,
    "line_items": [
        {"description": "Lieferung und Montage", "quantity": 2, "unit_price": 100.0, "line_total": 200.0},
        {"description": "Server-Wartung, Stunden", "quantity": 1.5, "unit_price": 40.0, "line_total": 60.0},
    ],
}


def run(**changes):
    return validate({**GOOD, **changes}, LINES)


def rules(issues, severity=None):
    return {(i.field, i.rule) for i in issues if severity in (None, i.severity)}


def test_correct_invoice_passes_cleanly():
    out, issues = run()
    assert issues == [] and out == GOOD and not needs_review(issues)


def test_invented_subtotal_is_dropped_without_review():
    out, issues = run(subtotal=999.99)
    assert out["subtotal"] is None
    assert rules(issues, "repair") == {("subtotal", "grounding")} and not needs_review(issues)


def test_unprinted_total_is_kept_and_flagged():
    out, issues = run(total_amount=319.40)
    assert out["total_amount"] == 319.40 and needs_review(issues)
    assert ("total_amount", "grounding") in rules(issues, "review")


def test_unprinted_required_fields_keep_their_value_but_are_flagged():
    out, issues = run(invoice_number="ZZ-1", invoice_date="2025-01-01")
    assert out["invoice_number"] == "ZZ-1" and out["invoice_date"] == "2025-01-01"
    assert {("invoice_number", "grounding"), ("invoice_date", "grounding")} <= rules(issues, "review")


def test_total_that_is_printed_but_does_not_add_up_is_flagged():
    _, issues = run(total_amount=260.0, tax_amount=49.4)  # 260.00 is printed (the subtotal)
    assert ("total_amount", "arithmetic") in rules(issues, "review")


def test_two_company_names_flagged_but_ampersand_form_is_one_name():
    assert ("supplier_name", "supplier") not in rules(run()[1])
    _, issues = run(supplier_name="Müller Elektro GmbH & Co. KG Nordlicht GmbH")
    assert ("supplier_name", "grounding") in rules(issues)  # not printed as such in the text
    out, issues = validate({**GOOD, "supplier_name": "Elektro GmbH Nordlicht GmbH"}, LINES + ["Elektro GmbH Nordlicht GmbH"])
    assert ("supplier_name", "supplier") in rules(issues, "review")


def test_item_arithmetic_and_extra_item():
    bad = [dict(GOOD["line_items"][0], line_total=210.0)]
    _, issues = run(line_items=bad + GOOD["line_items"][1:])
    assert ("line_items", "arithmetic") in rules(issues, "review")
    extra = GOOD["line_items"] + [{"description": "Ghost", "quantity": 1, "unit_price": 5.0, "line_total": 5.0}]
    _, issues = run(line_items=extra)
    assert ("line_items", "grounding") in rules(issues, "review") and ("subtotal", "arithmetic") in rules(issues)


def test_wrong_types_never_crash():
    out, issues = run(total_amount="309,40", invoice_number=2025, line_items=["x", None, {"description": "A"}])
    assert out["total_amount"] is None and out["invoice_number"] is None and out["line_items"] == []
    assert needs_review(issues)


def test_invalid_and_inverted_dates():
    out, issues = run(invoice_date="2025-13-45")
    assert out["invoice_date"] is None and ("invoice_date", "type") in rules(issues, "review")
    _, issues = validate({**GOOD, "due_date": "2025-01-01"}, LINES + ["Zahlbar: 01.01.2025"])
    assert ("due_date", "dates") in rules(issues, "review")


def test_empty_prediction_is_flagged_not_crash():
    out, issues = validate({}, LINES)
    assert needs_review(issues) and out["line_items"] == []
    assert {("invoice_number", "required"), ("line_items", "required")} <= rules(issues, "review")


def test_ungrounded_optional_fields_are_repaired_silently():
    out, issues = run(due_date="2025-03-05", supplier_tax_id="DE000000000")
    assert out["due_date"] is None and out["supplier_tax_id"] is None and not needs_review(issues)
