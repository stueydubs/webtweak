"""Gates added with the dash-key fix: the mojibake key must match what Windows-1252
really produces, and shipped prose must not name a maintainer path or a private client."""

import pathlib

from test_shipped_prose import DASHES

ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_every_cp1252_mojibake_dash_contains_a_dashes_key():
    """cp1252 maps byte 0x80 to the euro sign, not U+0080, so the real mojibake is
    U+00E2 U+20AC U+201D/U+201C. Build it rather than typing it, so the key cannot
    drift from the real form."""
    for ch in ("\u2014", "\u2013"):
        mojibake = ch.encode("utf-8").decode("cp1252")
        assert any(key in mojibake for key in DASHES), (
            f"{mojibake!r} (cp1252 mojibake of U+{ord(ch):04X}) matches no DASHES key")


def test_shipped_prose_names_no_maintainer_path_or_private_client():
    for rel in ("reconcile/SKILL.md", "README.md", "overlay/VENDOR.md"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        for needle in ("~/projects/", "Walker Scientific"):
            assert needle not in text, f"{rel} contains {needle!r}"
