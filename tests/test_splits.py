import pytest

from invoice_pipeline.splits import select_splits


def test_default_is_development_and_tuning():
    assert select_splits() == ({"development", "tuning"}, "")


def test_heldout_and_challenge_have_their_own_suffix():
    assert select_splits(heldout=True) == ({"heldout"}, "_heldout")
    assert select_splits(challenge=True) == ({"challenge"}, "_challenge")


def test_both_flags_together_are_refused():
    with pytest.raises(SystemExit):
        select_splits(heldout=True, challenge=True)
