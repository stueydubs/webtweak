# PRD: webtweak 0.5.0 - per-breakpoint authoring

> The release that makes webtweak a responsive tool. You author at a width, webtweak knows which of *your page's own* breakpoints you are inside, and the Patch says so - Claude writes the media query. Changes the Patch contract for the first time; ADR-0001 still holds. See [CONTEXT.md](../CONTEXT.md), [ADR-0001](./adr/0001-capture-intent-not-rewrite-source.md), [ADR-0003](./adr/0003-compose-shorthands-from-discrete-controls.md) and [ADR-0004](./adr/0004-breakpoint-scoped-patches.md).

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
- **The browser suite runs locally now.** 0.4.0's PRD assumed it could not (Playwright absent on the dev machine); it was installed during that release and the whole suite ran green before each commit. A ticket in this release documents the setup so that stops being folklore.
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
