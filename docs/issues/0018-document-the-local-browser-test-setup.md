# Issue 0018: Document the local browser-test setup

> Labels: chore, ready-for-agent · Type: AFK

## Parent

[PRD: webtweak 0.5.0](../PRD-0.5.0.md)

## What to build

The browser suite runs on the development machine, and the repo does not say so.

0.4.0's PRD recorded the opposite - "none of this release's tests run on the development machine, because Playwright is not installed there" - and planned around it, accepting that the release's own tests would only ever be seen green in CI. Playwright was then installed during that release and the full suite ran locally before every commit, which is how several defects were caught before they were committed rather than after. That capability is currently folklore: it lives in one session's shell history, not in the repo.

Write it down, and make it one command. A `requirements-dev.txt` (pytest, playwright) plus the `playwright install chromium` step, referenced from the README's Development section, so the next person - or the next agent - does not plan a release around a constraint that no longer exists.

Worth stating plainly in the docs: the stdlib suite needs nothing but pytest, and the browser suite needs the extra two steps. That distinction is why CI has two jobs, and knowing it is what stops someone reading a `-m "not browser"` run as full coverage.

## Acceptance criteria

- [ ] `requirements-dev.txt` exists and installs everything the full suite needs
- [ ] The README's Development section documents both suites and how to run each
- [ ] The browser-suite instructions include the `playwright install chromium` step
- [ ] The docs state that a `not browser` run is not full coverage
- [ ] The stale claim in `docs/PRD-0.4.0.md` is corrected, or annotated as superseded
- [ ] Nothing in CI changes - it already installs what it needs

## Blocked by

- None - can start immediately
