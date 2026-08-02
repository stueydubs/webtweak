"""Gates on the prose that ships inside the npm tarball.

Every other surface in this project is gated by something. This one was not, and it
showed twice in one release: `package.json`'s description and five lines of README
shipped with em dashes, and the README credited peek to 0.7.0 when it shipped in 0.8.0.
Both were found by a person reading, and one of them only after publishing - a
published tarball cannot be edited, so the wrong text sits on npmjs.com until the next
version.

Scope is every prose file npm actually ships, taken from `npm pack` rather than
guessed: README.md and package.json (npm includes README, LICENSE and package.json
whatever the `files` allowlist says), plus LICENSE, overlay/VENDOR.md and
reconcile/SKILL.md, which ride along inside the allowlisted directories. SKILL.md is
in scope precisely because it is easy to forget - it is 26KB of prose that users paste
into a Claude conversation.

Deliberately NOT in scope: CHANGELOG.md and everything under docs/. Those are not
shipped, they quote history verbatim, and a dash rule over 900 lines of changelog
would be noise rather than a gate.
"""

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
PKG = ROOT / "package.json"

# The prose files that end up in the tarball. Verified against `npm pack` output; the
# allowlist test below fails if the shipped set grows past what is listed here.
SHIPPED_PROSE = ["README.md", "package.json", "LICENSE",
                 "overlay/VENDOR.md", "reconcile/SKILL.md"]

# U+2014 EM DASH and U+2013 EN DASH. This project writes " - " instead, everywhere a
# user can see it. "â" is the leading pair both dashes decode to when UTF-8
# is read as Windows-1252 - the form that actually reaches a reader, and the one a
# grep for the real character misses.
DASHES = {"—": "em dash",
          "–": "en dash",
          "â": "mojibake dash (UTF-8 read as Windows-1252)"}


def _package():
    return json.loads(PKG.read_text(encoding="utf-8"))


def test_no_em_or_en_dashes_in_anything_that_ships():
    found = []
    for rel in SHIPPED_PROSE:
        path = ROOT / rel
        assert path.exists(), f"{rel} is listed as shipped prose but does not exist"
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for ch, name in DASHES.items():
                if ch in line:
                    found.append(f"{rel}:{line_no} {name}: {line.strip()[:70]}")
    assert not found, "use a spaced hyphen instead:\n" + "\n".join(found)


def test_every_version_the_readme_credits_a_feature_to_has_shipped():
    """The README says "Shipped in X.Y.Z" in a few places, and one of them was wrong -
    peek and the bottom sheet were credited to 0.7.0, having shipped in 0.8.0, because
    they were written into a bullet that already ended with the older attribution."""
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    released = set(re.findall(r'^## \[([0-9]+\.[0-9]+\.[0-9]+)\]', changelog, flags=re.M))
    assert released, "no released versions parsed from CHANGELOG.md"
    credited = set(re.findall(r'Shipped in \*\*([0-9]+\.[0-9]+\.[0-9]+)\*\*',
                              README.read_text(encoding="utf-8")))
    assert credited, "no 'Shipped in **X.Y.Z**' claims found; has the wording changed?"
    unknown = credited - released
    assert not unknown, (
        f"README credits a feature to {sorted(unknown)}, which the CHANGELOG has no "
        f"entry for. Released: {sorted(released)}")


def test_the_package_version_is_the_newest_the_changelog_records():
    """Two statements of one fact, and a release that bumps one and forgets the other
    publishes a lie in whichever it forgot. Ordered by value rather than by position:
    the CHANGELOG lists newest first, but that is a convention, not a guarantee."""
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    versions = re.findall(r'^## \[([0-9]+\.[0-9]+\.[0-9]+)\]', changelog, flags=re.M)
    newest = max(versions, key=lambda v: tuple(int(p) for p in v.split(".")))
    assert _package()["version"] == newest, (
        f"package.json says {_package()['version']}, the CHANGELOG's newest entry is "
        f"{newest}")


def test_the_shipped_set_has_not_grown_past_what_this_module_checks():
    """The gate is only worth what its scope covers, and the scope is a hand-written
    list. If the `files` allowlist grows a directory, prose can start shipping that
    nothing here reads - so the allowlist is asserted rather than trusted."""
    files = _package().get("files")
    assert files, "package.json has no `files` allowlist; the tarball is unbounded"
    assert set(files) == {"webtweak.js", "overlay/", "reconcile/"}, (
        f"`files` is now {files}. Anything prose-like inside it must be added to "
        f"SHIPPED_PROSE above, or this module quietly stops covering the tarball.")
