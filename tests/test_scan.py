import random

import pymupdf

from invoice_pipeline.dataset import plan
from invoice_pipeline.fakedata import generate_invoice
from invoice_pipeline.layouts import render
from invoice_pipeline.scan import PROFILES, assign_profiles, make_scan


def _make_pdf(tmp_path):
    g = generate_invoice(random.Random(3), "de")
    path = tmp_path / "a.pdf"
    render("classic", g, path)
    return path


def test_scan_has_no_text_layer_but_same_size(tmp_path):
    src = _make_pdf(tmp_path)
    dst = tmp_path / "s.pdf"
    make_scan(src, dst, PROFILES["typical"], seed=1)
    a, b = pymupdf.open(src), pymupdf.open(dst)
    assert a[0].get_text().strip() != ""
    assert b[0].get_text().strip() == ""
    assert len(a) == len(b)
    assert abs(a[0].rect.width - b[0].rect.width) < 0.5
    assert abs(a[0].rect.height - b[0].rect.height) < 0.5


def test_scan_is_reproducible_and_seed_matters(tmp_path):
    src = _make_pdf(tmp_path)
    make_scan(src, tmp_path / "x.pdf", PROFILES["poor"], seed=5)
    make_scan(src, tmp_path / "y.pdf", PROFILES["poor"], seed=5)
    make_scan(src, tmp_path / "z.pdf", PROFILES["poor"], seed=6)
    px = lambda n: pymupdf.open(tmp_path / n)[0].get_pixmap(dpi=72).samples
    assert px("x.pdf") == px("y.pdf")
    assert px("x.pdf") != px("z.pdf")


def test_profiles_are_balanced():
    combos = plan(120)
    profs = assign_profiles(combos)
    assert {p: profs.count(p) for p in set(profs)} == {"good": 40, "typical": 40, "poor": 40}
    for combo in set(combos):
        cell = [p for p, c in zip(profs, combos) if c == combo]
        assert set(cell) == {"good", "typical", "poor"}