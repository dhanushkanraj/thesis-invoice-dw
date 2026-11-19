import csv
import hashlib
import json
import random

import pymupdf
import pytest

from invoice_pipeline.challenge import (
    CHALLENGE_LABELS,
    build_challenge,
    build_challenge_scans,
    challenge_id,
    challenge_locale,
    challenge_plan,
    render_ledger,
)
from invoice_pipeline.dataset import build_dataset, check_against_pdf, pdf_text, read_split_rows
from invoice_pipeline.extract_text import get_lines
from invoice_pipeline.fakedata import generate_invoice
from invoice_pipeline.formats import LOCALES
from invoice_pipeline.layouts import LAYOUTS


def test_plan_is_balanced_and_uses_a_new_layout():
    combos = challenge_plan(40)
    assert {c[0] for c in combos} == {"ledger"}
    assert "ledger" not in LAYOUTS  # really unseen: not one of the three known layouts
    assert {loc: [c[1] for c in combos].count(loc) for loc in LOCALES} == {"de": 10, "en_eu": 10, "us": 10, "uk": 10}


def test_challenge_id_format():
    assert challenge_id(7) == "ch_0007"


@pytest.mark.parametrize("code", sorted(LOCALES))
def test_every_label_word_differs_from_the_known_wording(code):
    base = LOCALES[code].labels
    new = CHALLENGE_LABELS[code]
    assert set(new) == set(base)
    same = [k for k in base if new[k] == base[k]]
    assert same == []


@pytest.mark.parametrize("code", sorted(LOCALES))
def test_challenge_locale_changes_only_the_labels(code):
    base, new = LOCALES[code], challenge_locale(code)
    assert (new.currency, new.decimal, new.thousands, new.date_style) == (
        base.currency, base.decimal, base.thousands, base.date_style)
    assert new.labels != base.labels


@pytest.mark.parametrize("code", sorted(LOCALES))
def test_ledger_prints_every_truth_value(code, tmp_path):
    g = generate_invoice(random.Random(11), code)
    locale = challenge_locale(code)
    pdf = render_ledger(g, tmp_path / "x.pdf", locale)
    assert check_against_pdf(g, pdf_text(pdf), labels=locale.labels) == []


def test_missing_fields_are_not_printed(tmp_path):
    g = generate_invoice(random.Random(3), "uk", missing_rates={"due_date": 1.0, "supplier_tax_id": 1.0, "subtotal": 1.0})
    locale = challenge_locale("uk")
    text = pdf_text(render_ledger(g, tmp_path / "x.pdf", locale))
    assert locale.labels["due_date"] not in text
    assert locale.labels["tax_id"] not in text
    assert locale.labels["subtotal"] not in text


def test_fifteen_items_all_printed(tmp_path):
    g = generate_invoice(random.Random(5), "de", n_items=15)
    locale = challenge_locale("de")
    assert check_against_pdf(g, pdf_text(render_ledger(g, tmp_path / "x.pdf", locale)), labels=locale.labels) == []


def _first_line_with(lines, fragment):
    return next(i for i, line in enumerate(lines) if fragment in line)


def test_customer_comes_first_and_supplier_is_in_the_footer(tmp_path):
    g = generate_invoice(random.Random(8), "en_eu")
    pdf = render_ledger(g, tmp_path / "x.pdf", challenge_locale("en_eu"))
    lines, method = get_lines(pdf)  # the lines as the pipeline sees them (top to bottom)
    assert method == "native"
    buyer = _first_line_with(lines, g.extras.buyer_name)
    supplier = _first_line_with(lines, g.truth.supplier_name)
    assert buyer < supplier
    assert supplier > len(lines) * 0.6  # in the lower part of the page


def test_totals_come_before_the_items(tmp_path):
    g = generate_invoice(random.Random(9), "us")
    locale = challenge_locale("us")
    lines, _ = get_lines(render_ledger(g, tmp_path / "x.pdf", locale))
    assert _first_line_with(lines, locale.labels["total"]) < _first_line_with(lines, g.truth.line_items[0].description)


def test_same_input_gives_identical_bytes(tmp_path):
    g = generate_invoice(random.Random(2), "de")
    a = render_ledger(g, tmp_path / "a.pdf", challenge_locale("de")).read_bytes()
    b = render_ledger(g, tmp_path / "b.pdf", challenge_locale("de")).read_bytes()
    assert a == b


def test_build_challenge_small(tmp_path):
    result = build_challenge(tmp_path, n=8, seed=4)
    assert result["failures"] == {}
    assert len(list((tmp_path / "data" / "synthetic" / "pdf").glob("ch_*.pdf"))) == 8
    rows = read_split_rows(tmp_path)
    assert len(rows) == 8
    assert {r["split"] for r in rows} == {"challenge"}
    assert {r["layout"] for r in rows} == {"ledger"}
    assert {r["scan_profile"] for r in rows} <= {"good", "typical", "poor"}
    for r in rows:
        json.loads((tmp_path / "data" / "ground_truth" / f"{r['invoice_id']}.json").read_text(encoding="utf-8"))


def test_building_twice_does_not_duplicate_rows(tmp_path):
    build_challenge(tmp_path, n=8, seed=4)
    build_challenge(tmp_path, n=8, seed=4)
    assert len(read_split_rows(tmp_path)) == 8


def test_original_dataset_is_untouched_and_rows_are_kept(tmp_path):
    build_dataset(tmp_path, n=6, seed=5)
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
              for p in (tmp_path / "data" / "synthetic" / "pdf").glob("inv_*.pdf")}
    build_challenge(tmp_path, n=4, seed=4)
    rows = read_split_rows(tmp_path)
    assert len(rows) == 10
    assert sum(r["split"] == "challenge" for r in rows) == 4
    after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
             for p in (tmp_path / "data" / "synthetic" / "pdf").glob("inv_*.pdf")}
    assert before == after
    # rebuilding the original dataset keeps the challenge rows
    build_dataset(tmp_path, n=6, seed=5)
    rows = read_split_rows(tmp_path)
    assert len(rows) == 10
    assert sum(r["split"] == "challenge" for r in rows) == 4
    assert len({r["invoice_id"] for r in rows}) == 10


def test_challenge_ids_never_collide_with_original_ids(tmp_path):
    build_dataset(tmp_path, n=6, seed=5)
    build_challenge(tmp_path, n=4, seed=4)
    ids = [r["invoice_id"] for r in read_split_rows(tmp_path)]
    assert len(ids) == len(set(ids))
    assert all(i.startswith(("inv_", "ch_")) for i in ids)


def test_scans_have_no_text_layer(tmp_path):
    result = build_challenge(tmp_path, n=3, seed=4)
    build_challenge_scans(tmp_path, result["rows"], seed=4)
    for r in result["rows"]:
        doc = pymupdf.open(tmp_path / "data" / "synthetic" / "scanned" / f"{r['invoice_id']}.pdf")
        assert doc[0].get_text().strip() == ""
        assert doc[0].get_images()


def test_split_csv_columns_stay_usable_by_the_scripts(tmp_path):
    build_dataset(tmp_path, n=6, seed=5)
    build_challenge(tmp_path, n=4, seed=4)
    with (tmp_path / "data" / "split.csv").open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert {"invoice_id", "layout", "locale", "split", "scan_profile"} <= set(reader.fieldnames)
    assert all(r["scan_profile"] in ("good", "typical", "poor") for r in rows if r["split"] == "challenge")
