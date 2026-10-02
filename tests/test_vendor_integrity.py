"""Gate overlay/interact.min.js against the pin recorded in overlay/VENDOR.md.

interact.min.js is 96 KB of minified third-party code running in the same origin as
the save endpoint, and the only integrity check used to be a hash a person was meant
to remember to run. Nothing failed if the file was edited, truncated or swapped by a
bad merge or a rushed upgrade, because the gesture tests only prove that gestures
work. This makes the hash in VENDOR.md a check rather than a note.
"""

import hashlib
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
VENDOR_MD = ROOT / "overlay" / "VENDOR.md"
INTERACT = ROOT / "overlay" / "interact.min.js"

SAME_COMMIT = ("Update overlay/VENDOR.md and overlay/interact.min.js in the same "
               "commit: a change to one without the other is a vendored file that "
               "no longer matches its provenance record.")

SHA_ROW = re.compile(r"^\|\s*sha256\s*\|\s*`([0-9a-fA-F]{64})`\s*\|\s*$", re.M)
VERSION_ROW = re.compile(r"^\|\s*Version\s*\|\s*([^|\s]+)\s*\|\s*$", re.M)
BANNER = re.compile(r"\A\s*/\*\s*interact\.js\s+(\S+)\s*\|")


def recorded_sha(text):
    rows = SHA_ROW.findall(text)
    assert len(rows) == 1, (
        f"expected exactly one 64-hex sha256 table row in VENDOR.md, found {len(rows)}")
    return rows[0].lower()


def recorded_version(text):
    rows = VERSION_ROW.findall(text)
    assert len(rows) == 1, (
        f"expected exactly one Version table row in VENDOR.md, found {len(rows)}")
    return rows[0]


def banner_version(data):
    m = BANNER.match(data[:512].decode("utf-8", errors="replace"))
    assert m, "interact.min.js does not start with an '/* interact.js X.Y.Z |' banner"
    return m.group(1)


def test_interact_sha256_matches_vendor_md():
    actual = hashlib.sha256(INTERACT.read_bytes()).hexdigest()
    expected = recorded_sha(VENDOR_MD.read_text(encoding="utf-8"))
    assert actual == expected, (
        f"overlay/interact.min.js hashes to {actual} but VENDOR.md records "
        f"{expected}. {SAME_COMMIT}")


def test_vendor_md_version_matches_banner():
    recorded = recorded_version(VENDOR_MD.read_text(encoding="utf-8"))
    banner = banner_version(INTERACT.read_bytes())
    assert recorded == banner, (
        f"VENDOR.md says version {recorded} but the interact.min.js banner says "
        f"{banner}. {SAME_COMMIT}")


def test_the_checks_can_fail():
    """The two checks above must detect a change, not pass whatever the file holds."""
    data = INTERACT.read_bytes()
    md = VENDOR_MD.read_text(encoding="utf-8")

    flipped = bytes([data[-1] ^ 1])
    assert hashlib.sha256(data[:-1] + flipped).hexdigest() != recorded_sha(md)
    assert hashlib.sha256(data[:-1]).hexdigest() != recorded_sha(md)

    bumped = re.sub(r"(\| Version \| )\S+", r"\g<1>9.9.9", md)
    assert bumped != md
    assert recorded_version(bumped) != banner_version(data)

    with pytest.raises(AssertionError):
        recorded_sha(md.replace("| sha256 |", "| digest |"))
    with pytest.raises(AssertionError):
        banner_version(b"var x = 1;" + data)
