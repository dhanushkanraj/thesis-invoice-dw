from invoice_pipeline.evaluate import evaluate_invoice, field_outcome, item_scores


def item(desc="A", q=1, up=2.0, lt=2.0):
    return {"description": desc, "quantity": q, "unit_price": up, "line_total": lt}


def test_field_outcomes():
    assert field_outcome("invoice_number", "X1", "X1") == "correct"
    assert field_outcome("invoice_number", " X1 ", "X1") == "correct"
    assert field_outcome("invoice_number", "X2", "X1") == "wrong"
    assert field_outcome("invoice_number", None, "X1") == "missing"
    assert field_outcome("due_date", "2025-01-01", None) == "spurious"
    assert field_outcome("due_date", None, None) == "correct"
    assert field_outcome("total_amount", 10.001, 10.0) == "correct"
    assert field_outcome("total_amount", 10.01, 10.0) == "wrong"


def test_item_scores_perfect_partial_and_empty():
    t = [item("A"), item("B", 2, 3.0, 6.0)]
    assert item_scores(t, t)["exact"]
    s = item_scores([item("A")], t)
    assert s["precision"] == 1.0 and s["recall"] == 0.5 and round(s["f1"], 3) == 0.667 and not s["exact"]
    assert item_scores([], [])["f1"] == 0.0 or item_scores([], [])["exact"]
    assert item_scores([], t)["recall"] == 0.0


def test_item_scores_ignore_case_and_order_but_not_numbers():
    t = [item("Monitor"), item("Lamp", 3, 1.0, 3.0)]
    assert item_scores([item("lamp", 3, 1.0, 3.0), item("MONITOR")], t)["exact"]
    assert not item_scores([item("Monitor", 1, 2.0, 2.5), item("Lamp", 3, 1.0, 3.0)], t)["exact"]


def test_invoice_exact_needs_all_fields_and_items():
    truth = {"invoice_number": "A", "supplier_name": "S", "supplier_tax_id": None, "invoice_date": "2025-01-01",
             "due_date": None, "currency": "EUR", "subtotal": None, "tax_amount": 1.0, "total_amount": 2.0,
             "line_items": [item()]}
    assert evaluate_invoice(dict(truth), truth)["invoice_exact"]
    assert not evaluate_invoice({**truth, "currency": "USD"}, truth)["invoice_exact"]
    assert not evaluate_invoice({**truth, "line_items": []}, truth)["invoice_exact"]


def test_malformed_model_output_never_crashes():
    t = [item("A"), item("B", 2, 3.0, 6.0)]
    bad = [item("A", None, 2.0, 2.0), "text", {"description": "B"}, item("B", "2", 3.0, 6.0), None]
    s = item_scores(bad, t)
    assert s["recall"] == 0.0 and not s["exact"]
    assert item_scores("not a list", t)["recall"] == 0.0
    assert item_scores([item("A")], t)["recall"] == 0.5


def test_strict_types_for_fields():
    assert field_outcome("total_amount", "1.234,56", 1234.56) == "wrong"
    assert field_outcome("total_amount", True, 1.0) == "wrong"
    assert field_outcome("invoice_number", 2025, "2025") == "wrong"
    assert field_outcome("invoice_number", ["x"], "x") == "wrong"
