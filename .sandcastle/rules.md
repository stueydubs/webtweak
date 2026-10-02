Read `CLAUDE.md` and `CONTEXT.md` before you change anything. They hold the house rules and the glossary, and the `_Avoid_` lists in `CONTEXT.md` exist because the wrong word has caused real confusion.

Never use em-dashes or en-dashes anywhere, in code, comments, docs or commit messages. Use a hyphen with spaces. `tests/test_shipped_prose.py` gates this, and it also catches the Windows-1252 mojibake form.

Add no runtime dependency. `webtweak.js` is Node stdlib only and interact.js is vendored under `overlay/`. A new dependency is a decision for `CONTEXT.md`, which a ticket cannot make for you. If a ticket seems to need one, stop and say so in the issue.

A passing test is evidence about the test first. When a new test passes on its first run, check that it fails when the code under test is broken. Write browser tests with `from _browser import sync_playwright, pytestmark` and never mark them by hand.

The two gates are the two CI jobs. `stdlib` runs `-m "not browser"` and `browser` runs `-m browser`. Check the skip count of the browser gate, not the colour. A browser module that skips reads green and proves nothing.

Generated files: none. No committed file is written by a command.

Drift gate: none, because there are no generated files.

Do not touch:
- `overlay/interact.min.js` is vendored with a pinned sha256 in `overlay/VENDOR.md`.
- `.github/workflows/` and `site/`. CI and the public Pages deploy are not ticket work.
- Releases. Do not bump the `version` in `package.json`, add a release heading to `CHANGELOG.md`, tag, run `npm publish` or create a GitHub release. A release is Stuart's, even when a ticket is called "release".
- `docs/issues/` is a historical record from before this repo used GitHub Issues. The tracker is GitHub Issues.

Do not push, deploy or publish. Commit on your branch and stop.
