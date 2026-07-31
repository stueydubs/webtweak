# PRD: per-breakpoint authoring

> The release that makes webtweak a responsive tool. You author at a width, webtweak knows which of *your page's own* breakpoints you are inside, and the Patch says so - Claude writes the media query. Changes the Patch contract for the first time; ADR-0001 still holds. See [CONTEXT.md](../CONTEXT.md), [ADR-0001](./adr/0001-capture-intent-not-rewrite-source.md), [ADR-0003](./adr/0003-compose-shorthands-from-discrete-controls.md) and [ADR-0004](./adr/0004-breakpoint-scoped-patches.md).

## Progress

*Last updated 2026-07-31. Update this section in place - it is the one place that says where the epic actually stands.*

| Issue | State |
|---|---|
| 0014 discovery + band picker | **Shipped** (`4d209fb`) |
| 0015 banded preview + recording | **Shipped, unpushed.** `tests/test_e2e_banded_edits.py` (23 tests, now tracked) all green; `test_e2e_breakpoints.py`'s transitional pin replaced by its documented opposite. A dynamic-team review + Codex verify pass (see below) found and fixed four real bugs before any of it reached a tagged release. |
| 0016 reconcile merges media groups | **Shipped, unpushed.** `reconcile/SKILL.md` now documents the `media` map (shape, absent-key = base-only), the three merge rules (merge into the existing block, never reorder, create only when none exists), and that the chosen condition is intent, not a nearby breakpoint to round to. `wtreconcile.py`'s pending summary now reports each patch's media groups instead of only `changes`; `tests/test_wtreconcile.py` covers a banded patch, a media-only patch, a batch predating `media` staying unchanged, `mark` round-tripping a media group untouched, and two new malformed-`media` corrupt-input cases. The CSS-merge judgment itself is not script-testable (it is Claude reading source in a live reconcile session) - only its documented rules and the scriptable half are covered, matching the issue's own stated scope. |
| 0017 restore banded edits after reload | **Partial, untested.** `restore()` already reconstructs a `media` group from a saved patch (added alongside 0015, since restoring naturally has to undo whatever save() did) - but no test exercises a reload with banded edits, so this stays open until that's verified. |
| 0018 document the local browser-test setup | **Shipped** (`4d209fb`, same commit) |
| 0019 release | Not started |

**0015 is itself not shippable on its own**, for the same reason `4d209fb` wasn't: restore-after-reload for banded groups (0017) is untested past what the overlay's own restore() does. A save now genuinely records a banded Patch, and reconcile (0016) now knows how to fold a `media` group into an existing `@media` block in real source - but the round-trip through a reload is still the open gap.

**What 0015 actually built**, matching the design that was settled and prototyped before the tests were written: one injected `<style id="wt-band-style">` holding real `@media` blocks, a generated `wt-mq-N` class per element registered in `WT_OWN_CLASSES` (also excluded from `pageConditions()`'s own sweep, or the picker would start offering back its own generated conditions), and declarations written `!important` - necessary, not blunt, because the base edit a banded one competes with is an inline style, which beats any class rule that isn't. Two-band overlap orders narrowest-last in the injected block, so it wins the same way it would in the page's own cascade. Undo, revert, the change list and `hasRealEdits()` are all band-aware now, keyed by `(el, prop, band)` rather than `(el, prop)` - `font-size` at base and `font-size` at `(max-width: 600px)` are two different recorded values on the same element and the same property, per ADR-0004's stated failure mode, and every one of those structures needed the band added to its key to keep them from silently overwriting each other.

**Scoped to plain single-value controls** (Type, Colour, Box) for this pass. Border (composed from three controls), per-side spacing, and every control on a shape stay base-only regardless of which band is selected - a banded border, padding, or shape fill is not yet expressible. This is enforced by a single `controlBand(c)` helper that every band-aware function (`commit`, `populate`, the revert marks, `revertRow`, `revertControl`) reads instead of the picker's own `currentBand()` directly - see the dynamic-team review below for why a single source of truth for this mattered. Gesture-driven edits (drag-nudge, grip-resize, shape move) stay base-only too, since neither is exercised by the PRD's testing decisions and both would need their own review of the same `(el, prop, band)` question this pass answered for the panel-field path alone.

**Two bugs surfaced by 0015's own test coverage, fixed alongside it, both pre-existing:** the status bar could push Save off-screen at a narrow window once its message got long enough (never exercised before, because no earlier test did Reset-then-Save below 700px - and a narrow window is exactly what this epic is for); and `openTag()` built a Fingerprint's opening tag straight off the DOM `class` attribute rather than through `nonWtClasses()` the way `selector` already does, so `wt-shape` (and now `wt-mq-N`) could leak into it. Neither is breakpoint code, both are recorded in CHANGELOG's Fixed section.

**Dynamic-team review + Codex verify, run once 0015's tests were green (five parallel reviewers - band data model, undo/redo keying, save/restore round-trip, scoping boundaries, test adequacy - each finding then adversarially verified by Codex CLI against the running code).** 12 of 13 raw findings survived verification; after deduping two pairs of overlapping findings, ten distinct issues, all fixed same session: (1) a border edit made under a selected band was recorded into `media` instead of `changes`, contradicting the scoping above - `writeBorder()` ends in the shared `commit()` tail, which read the picker's band unconditionally; (2) a banded shape edit was recorded and shown in the change list, then silently dropped on save, because `save()`'s shape branch never read `e.media`; both closed at the source by the `controlBand()` fix rather than patched downstream. (3) Two min-width-only bands (an ordinary mobile-first pattern) could win the cascade in the wrong order - `makeBand()`'s span was `Infinity` for any such band regardless of its actual threshold, so the narrowest-wins sort saw `NaN` for any pair of them; fixed with a large finite sentinel. (4) Switching the Scope picker left the per-field revert dot stale, because `setScope()` never called `refreshChanges()`. The remaining six were test-coverage gaps (two elements sharing a band, a real shape's `openTag`, the status-bar fix, mixed base+band properties) plus one low-severity hardening (`wt-mq-N` class generation now checks the live DOM for a coincidental collision before claiming a name) - all now have regression tests in `test_e2e_banded_edits.py`.

**Three side-quests interrupted the epic before 0015** and are shipped: drag-to-draw shapes (`1b6dcbc`), one distinct picture per palette icon (`7ec26e5`), and 45° rotation replacing the three duplicate shape kinds (`3c5b541`). None touch breakpoint code.

**A `/simplify` pass (`277e434`)** then swept the whole project (not just this epic) for reuse, simplification, efficiency and altitude issues - see CHANGELOG for the full list; nothing behavioural changed, 299 tests passed before and after.

**A two-axis Standards+Spec review against `origin/main` (all ten local commits above)** found and fixed three things: four spots using "editor" where CONTEXT.md's glossary says "Overlay" (a documented-standard violation); the border/per-side/shape controls that stay base-only under a band were doing so silently, with no signal in the panel - `#wt-scope-note` now appends "Border and spacing always apply at every width" (or the Shape equivalent) whenever a band is selected, so ADR-0004's own "decline out loud rather than lie" principle actually holds there too; and this table under-reported 0017 as "Not started" when `restore()` already has (untested) code for it, fixed above. Two tests added for the new scope-note behaviour.

Nothing in this epic has been pushed.

## Problem

**Every edit is a base edit, whatever width you are looking at.** webtweak stamps the session's viewport width into the edits file so Claude can *warn* that a desktop-width change might break mobile - but warning is all it can do. There is no way to say "this heading is too tight, but only at 390px", which is the single most common adjustment on the hand-coded editorial sites webtweak is built for, and the one that most needs to be made by eye rather than by arithmetic. The README says it outright: not a responsive-design tool.

The gap is sharpest right after 0.4.0. Border, corner radius and shadow are exactly the properties that get re-tuned per breakpoint - a 24px radius and a 45px drop shadow that look right on a wide card are usually wrong on a phone - so the release that added them made the missing dimension more obvious, not less.

**And the workaround is worse than it looks.** You can tell Claude "make the lede smaller on mobile" in words, but then you are back to authoring responsive CSS by description, guessing at values, reloading to check. That is the exact loop webtweak exists to replace, still unreplaced for the case that needs it most.

## What we're building

**The Overlay learns your page's breakpoints and lets you choose which one you are editing.** It reads the media queries the page's own stylesheets declare, shows them, marks which ones match at your current window width, and defaults to the narrowest match - so resizing your window narrow and typing a value does the obviously-right thing. Base remains a target you can pick at any width.

**A banded edit previews only in its band.** Because an inline style cannot carry a media query, the Overlay maintains an injected `<style>` block with real `@media` rules. Drag your window wider and the mobile edit stops applying, in front of you, exactly as it will in production.

**The Patch says which query it belongs to**, and Claude merges it into the media block that already governs the element - creating one only when the page has none for that condition, and never reordering the blocks it finds, because media order is cascade order.

**Nothing that works today changes.** A patch with no band is byte-identical to what 0.4.0 wrote, so existing edits files reconcile unchanged, and an edit made without touching the band picker is still a base edit.

## User stories

1. As a site builder, I want to see the breakpoints my page already declares, so that I fix mobile inside my own responsive system instead of adding a fourth breakpoint nobody asked for.
2. As a site builder, I want the Overlay to know which breakpoint my window is currently inside, so that narrowing my window and typing a value lands where I expect.
3. As a site builder, I want to choose the band explicitly when several match, so that a change meant for phones does not also govern tablets.
4. As a site builder, I want to edit base styles while looking at a narrow window, so that "this is wrong everywhere and I noticed it on mobile" is expressible.
5. As a site builder, I want a banded edit to stop applying when I drag my window out of its band, so that I can see what I have actually done before saving it.
6. As a site builder, I want the change list to show which band each change belongs to, so that a session spanning two widths is reviewable.
7. As a site builder, I want my mobile edit reconciled into the media query my stylesheet already has, so that my CSS does not sprout a second `@media (max-width: 600px)` block below the first.
8. As a site builder whose fonts and styles come from a CDN, I want a manual way to name a condition, so that an unreadable stylesheet does not lock me out of responsive editing.
9. As a site builder, I want to be told that `print` and `prefers-color-scheme` are not editable here, so that I do not record a change I was never shown.

## Design Decisions

All of the below are recorded in [ADR-0004](./adr/0004-breakpoint-scoped-patches.md) with their rejected alternatives; the load-bearing ones are summarised here.

- **No device frame.** The Target page stays in the real window and the Overlay stays injected into it. An iframe would make every computed-style read, fingerprint and event cross-document - a re-architecture, not a feature. You resize your own window. Honest cost: you can only author at widths your screen can show.
- **Bands come from the page, gathered defensively.** `CSSMediaRule.conditionText` returns each query verbatim; the sweep reuses the font picker's try/catch over readable sheets, so a CDN sheet degrades the list instead of throwing, and a manual-entry path covers the case where nothing is readable.
- **The editing target is explicit, defaulting to the narrowest matching band.** A prototype at a 480px window found `(max-width: 900px)` and `(max-width: 600px)` matching simultaneously, so "the current breakpoint" is not a single thing and cannot be inferred silently.
- **Non-width conditions are listed as unavailable, with the reason.** They cannot be previewed by resizing, so an edit against one would record what the user never saw.
- **A banded edit is previewed by an injected `<style>` with real `@media` blocks** plus a generated `wt-mq-N` class per element, registered in `WT_OWN_CLASSES` so it can never reach a Fingerprint. Verified in a prototype: applies at 480px, does not apply at 700px or 1280px.
- **The panel populates per band for free.** `getComputedStyle` already resolves the page's own media queries at the current width - the fixture's headline reads 44px at 1280px and 32px at 480px with no extra machinery.
- **`changes` stays base; a sibling `media` map carries one group per condition.** Absent `media` is exactly the 0.4.0 shape, so the format change is additive and the reconcile skill branches on presence.

## Testing Decisions

- **What a good test is here:** set the window to a width, drive the picker and a panel field the way a user does, and assert on three things together - what the page renders *at that width*, what it renders at another width, and what the Patch says. A banded edit that is not checked at a second width is not tested at all, because the entire claim of the release is that the edit is conditional.
- **The seam is the existing browser suite, with one addition:** `open_page` already takes a width, and Playwright can resize mid-test, so a test can author at 480px and verify at 1280px in one session. No new seam.
- **The browser suite runs locally now** - genuinely, as of 0018. ~~it was installed during 0.4.0 and the whole suite ran green before each commit~~ was itself folklore: Playwright was *not* on the dev machine, and every browser module had been skipping as a single line per module, which reads green. It was installed for real during this epic (`.venv` + `requirements-dev.txt` + `playwright install chromium`), the setup is written down in the README's Development section, and the honest reading rule is there too: **check the skip count, not the colour.**
- **Every new test carries the browser marker**, selected by marker and never by filename.
- **Cases to cover:**
  - *Discovery:* the band list contains the page's declared width queries; a `print` query is listed as unavailable; an unreadable cross-origin sheet leaves the list populated from the readable ones; a page with no media queries offers base plus manual entry.
  - *Targeting:* the default target is the narrowest matching band; the matching bands are marked at 1280px, 700px and 480px; base is selectable while a narrow band matches.
  - *Preview:* an edit made in a band applies at a width inside it and does not apply at a width outside it; the generated class does not appear in the Patch's Fingerprint classes.
  - *Recording:* a banded edit lands under its condition in the patch and not in `changes`; a base edit made at a narrow width still lands in `changes`; the same property edited at base and in a band records both values without either overwriting the other.
  - *Session state:* the change list distinguishes the two; undo steps back through a banded edit without touching the base one; clearing a banded field reverts only that band; a reload restores banded edits into the injected block rather than inline.
  - *Reconcile:* the skill's own documented behaviour - merge into an existing block, create only when absent, never reorder - exercised through the reconcile helper's tests where it is scriptable.

## Out of Scope

- **A device menu, and authoring at widths the screen cannot show.** The window is the viewport; the browser's device mode covers the rest.
- **Writing new breakpoints into the site's system.** The Overlay offers what the page declares plus manual entry; deciding a site needs a 390px breakpoint is a design decision, not an edit.
- **Container queries.** Same shape of problem, and a natural follow-on, but the sweep, the picker and the preview would all need a container to resolve against.
- **Non-width conditions** - `print`, `prefers-color-scheme`, `hover` - which cannot be previewed by resizing.
- **Structural DOM reordering**, still the other open v2 feature, and now the cheaper of the two: a `move` Patch carrying the element's Fingerprint plus a target Fingerprint is pure intent, and Claude moves the markup, so ADR-0002's `create` precedent covers it. It is not in this release, but the recorded claim that it "retires ADR-0001's promise" is wrong and should stop being repeated.
- **Editing text copy** and **live-URL editing**, unchanged.

## Further Notes

- **Where a review should start:** anything keyed by `el + prop`. Undo, the change list, the revert-to-baseline check and the restore path all assume one value per element per property, and this release breaks that assumption the way 0.4.0 broke one-control-one-property. The failure mode is identical in shape - a banded edit silently overwriting a base edit still produces a valid-looking Patch - and 0.4.0's answer applies: mutation-test the cases where a plausible wrong result is indistinguishable from a right one.
- **The band picker is the second reuse of the suggestion-list widget** the font picker introduced, after shadow presets. If a third consumer needs it to filter or to mark rows unavailable, that is the point to generalise it rather than before.
- **Work item order:** discovery and the picker first (nothing else can be targeted without them), then the preview-and-record change, which is the hard one and should be built and reviewed alone. Reconcile's media-merging and the restore path both depend on the emitted shape, so they follow. The dev-setup and demo-video chores are independent of all of it.
