import csv
import hashlib
import json

from invoice_pipeline.dataset import assign_splits, build_dataset, invoice_id, plan
from invoice_pipeline.schema import Invoice


def test_plan_covers_all_combinations_evenly():
    combos = plan(120)
    assert len(set(combos)) == 12
    assert {combos.count(c) for c in set(combos)} == {10}


def test_split_is_stratified_and_reproducible():
    combos = plan(120)
    a, b = assign_splits(combos, 7), assign_splits(combos, 7)
    assert a == b
    assert {s: a.count(s) for s in set(a)} == {"development": 72, "tuning": 24, "heldout": 24}
    for combo in set(combos):
        in_cell = [s for s, c in zip(a, combos) if c == combo]
        assert set(in_cell) == {"development", "tuning", "heldout"}


def test_invoice_id_format():
    assert invoice_id(7) == "inv_0007"


def test_build_small_dataset(tmp_path):
    result = build_dataset(tmp_path, n=12, seed=5)
    assert result["failures"] == {}
    assert len(list((tmp_path / "data" / "synthetic" / "pdf").glob("*.pdf"))) == 12
    keys = sorted((tmp_path / "data" / "ground_truth").glob("*.json"))
    assert len(keys) == 12
    for k in keys:
        Invoice.model_validate(json.loads(k.read_text(encoding="utf-8")))
    with (tmp_path / "data" / "split.csv").open(encoding="utf-8") as f:
        assert len(list(csv.DictReader(f))) == 12


def test_dataset_is_reproducible(tmp_path):
    def digest(root):
        build_dataset(root, n=6, seed=9)
        return [
            hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((root / "data").rglob("*"))
            if p.is_file()
        ]

    assert digest(tmp_path / "a") == digest(tmp_path / "b")