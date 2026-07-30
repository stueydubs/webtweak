# Issue 0013: Release 0.4.0 - recorded scope, changelog, version

> Labels: chore, ready-for-agent · Type: AFK

## Parent

[PRD: webtweak 0.4.0](../PRD-0.4.0.md)

## What to build

The release itself, plus the one piece of documentation that ships false the moment the code lands.

The domain context currently states outright that borders and box-shadow are **excluded** from the editable property scope. That was true for v1 and stops being true with Issue 0009, so it is rewritten rather than left to contradict the tool. Stroke joins the glossary as a term distinct from Border, so a later reader does not "fix" the two labels back into one.

Existing users need telling to reinstall the bundled Reconcile skill, since their local copy will not know about the properties this release can emit - the same note the previous release carried.

Nothing here is published to npm or pushed without explicit sign-off.

## Acceptance criteria

- [ ] The domain context's recorded property scope no longer lists borders or box-shadow as excluded, and describes what is now editable
- [ ] Stroke is in the glossary, distinguished from Border
- [ ] CHANGELOG has a 0.4.0 section covering the font picker, the Border group, shadow, redo and the Stroke rename, with its compare links extended
- [ ] The README reflects the new property set
- [ ] The version is bumped to 0.4.0
- [ ] The release notes tell existing users to reinstall the bundled Reconcile skill
- [ ] The full suite passes, including the browser job
- [ ] Publishing and pushing are left for explicit sign-off

## Blocked by

- Issue 0008 (Font picker fed by the Target page's own fonts)
- Issue 0009 (Border group - composed border, corner radius, and the Stroke rename)
- Issue 0010 (Per-side border editing and the mixed-side guard)
- Issue 0011 (box-shadow with preset suggestions)
- Issue 0012 (Redo, with visible undo/redo buttons)
