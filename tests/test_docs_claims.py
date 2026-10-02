"""Gate on the safety claim in CONTEXT.md's opening paragraph.

CONTEXT.md is the file every agent is told to read first, and its glossary says
Reconcile stops at source and never pushes. The summary paragraph once said Claude
"reconciles ... and pushes", the opposite of the contract, and nothing noticed. This
reads the intro paragraph (line 3) and requires every mention of "push" to be
qualified by "only if you ask".
"""

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
CONTEXT = ROOT / "CONTEXT.md"


def intro_paragraph():
    lines = CONTEXT.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("# "), "CONTEXT.md should open with its title"
    assert lines[1] == "", "line 2 of CONTEXT.md should be blank"
    paragraph = lines[2]
    assert paragraph.strip(), "line 3 of CONTEXT.md should be the intro paragraph"
    return paragraph


def test_intro_does_not_claim_claude_pushes_unconditionally():
    assert not re.search(r"source files and pushes\.", intro_paragraph())


def test_every_push_mention_in_intro_is_qualified():
    paragraph = intro_paragraph()
    mentions = [m.start() for m in re.finditer(r"push", paragraph, re.I)]
    # Guard: if the intro stops mentioning push, this test would pass vacuously.
    assert mentions, "intro paragraph no longer mentions push; update this test"
    for start in mentions:
        assert "only if you ask" in paragraph[start:start + 40], (
            "intro mentions push without 'only if you ask': "
            + paragraph[max(0, start - 30):start + 40])
