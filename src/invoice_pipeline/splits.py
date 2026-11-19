"""Which part of the data a script works on.

Default: development + tuning (used to build and tune everything).
--heldout:   the held-out split, used once at the very end.
--challenge: the challenge set (unseen layout, different label wording), used once at the very end.
"""

DEFAULT_SPLITS = {"development", "tuning"}


def select_splits(heldout: bool = False, challenge: bool = False) -> tuple[set[str], str]:
    """Return (split names, file-name suffix). The suffix keeps result files of
    different parts of the data apart ('' for the default, '_heldout', '_challenge')."""
    if heldout and challenge:
        raise SystemExit("Use either --heldout or --challenge, not both.")
    if challenge:
        return {"challenge"}, "_challenge"
    if heldout:
        return {"heldout"}, "_heldout"
    return set(DEFAULT_SPLITS), ""
