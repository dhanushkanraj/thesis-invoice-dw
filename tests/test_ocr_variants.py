import numpy as np
import pytest
from PIL import Image, ImageDraw

from invoice_pipeline.ocr_variants import SPECS, VARIANTS, apply_step, binarize, clean, deskew, estimate_skew, ocr_lines
from invoice_pipeline.readability import facts, readability

TRUTH = {
    "invoice_number": "RE-1", "supplier_name": "Müller GmbH", "supplier_tax_id": None,
    "invoice_date": "2025-03-14", "due_date": None, "currency": "EUR",
    "subtotal": None, "tax_amount": 19.0, "total_amount": 1234.56,
    "line_items": [{"description": "Monitor", "quantity": 2, "unit_price": 600.0, "line_total": 1200.0}],
}


def text_lines_image(angle: float = 0.0) -> Image.Image:
    img = Image.new("L", (800, 1000), 255)
    d = ImageDraw.Draw(img)
    for y in range(100, 900, 40):
        d.rectangle([80, y, 720, y + 10], fill=0)  # a "line of text"
    return img.rotate(angle, resample=Image.BICUBIC, fillcolor=255)


def test_facts_use_locale_formatting_and_skip_null_values():
    de = dict(facts(TRUTH, "de"))
    assert ("total_amount", "1.234,56") in facts(TRUTH, "de")
    assert ("total_amount", "1,234.56") in facts(TRUTH, "us")
    assert not any(name in ("supplier_tax_id", "due_date", "subtotal") for name, _ in facts(TRUTH, "de"))
    assert de["invoice_date"] == "14.03.2025"


def test_readability_counts_found_and_missed():
    lines = ["Rechnung RE-1 Müller GmbH", "Datum 14.03.2025", "Monitor 2 600,00 € 1.200,00 €", "MwSt 19,00 €"]
    r = readability(TRUTH, "de", lines)
    assert r["missed"] == ["total_amount"] and not r["all_found"] and r["found"] == r["total"] - 1
    lines.append("Gesamt 1.234,56 €")
    assert readability(TRUTH, "de", lines)["all_found"]


@pytest.mark.parametrize("angle", [-2.5, 1.0, 3.0])
def test_estimate_skew_finds_the_tilt_and_deskew_removes_it(angle):
    img = text_lines_image(angle)
    assert abs(abs(estimate_skew(img)) - abs(angle)) <= 0.5
    assert abs(estimate_skew(deskew(img))) <= 0.5


def test_straight_page_is_left_straight():
    assert abs(estimate_skew(text_lines_image(0.0))) <= 0.25


def test_clean_and_binarize_return_images_of_expected_kind():
    img = text_lines_image(1.0)
    out = clean(img)
    assert out.mode == "L" and out.size[0] >= 800
    bw = binarize(out)
    assert set(np.unique(np.asarray(bw))) <= {0, 255}
    assert (np.asarray(bw) == 0).sum() > 0  # the dark bars survive


def test_binarize_turns_thin_dark_strokes_black_on_a_light_page():
    img = Image.new("L", (400, 200), 235)
    ImageDraw.Draw(img).line([(50, 100), (350, 100)], fill=40, width=3)
    arr = np.asarray(binarize(img))
    assert arr[100, 200] == 0 and arr[20, 20] == 255 and set(np.unique(arr)) <= {0, 255}


def test_unknown_variant_is_rejected():
    with pytest.raises(ValueError):
        ocr_lines("nofile.pdf", "magic")
    assert set(VARIANTS) <= set(SPECS) and VARIANTS[0] == "base"


def test_median_step_removes_speckle_but_keeps_strokes():
    img = text_lines_image(0.0)
    noisy = np.asarray(img).copy()
    rng = np.random.default_rng(1)
    for _ in range(300):
        noisy[rng.integers(0, 1000), rng.integers(0, 800)] = 0  # single black speckles
    cleaned = np.asarray(apply_step(Image.fromarray(noisy), "median"))
    assert (cleaned < 128).sum() < (noisy < 128).sum()      # speckles gone
    assert cleaned[105, 400] == 0                            # a real bar (10 px thick) survives
