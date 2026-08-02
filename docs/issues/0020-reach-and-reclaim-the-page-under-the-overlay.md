# Issue 0020: Reach - and reclaim - the page under the Overlay

> **Shipped**, 2026-08-01, unreleased at time of writing. Started as "the bar is too tall" and the measurement said otherwise twice over: the bar was never the expensive part, and height was never the real problem. See [ADR-0005](../adr/0005-peek-hides-the-chrome-rather-than-moving-the-page.md).

> Labels: bug, ready-for-agent · Type: AFK

## Parent

[PRD: per-breakpoint authoring](../PRD-per-breakpoint-authoring.md) - the release that made this acute. Its whole workflow is "drag the window narrow and work there", which is exactly where the Overlay takes the most room.

## What to build

Two problems that look like one.

**Anything under the Overlay cannot be selected.** The bar, the properties panel and the change list are all `position: fixed` with pointer events enabled, so a click aimed at the page beneath them works whichever control is there instead. Measured on a page whose `nav` occupies its top 56px, clicked at four widths with a fresh page each time: the click hit `wt-shape-btn` at 360px, `wt-undo` at 480px, `wt-shape-btn` at 700px and `wt-scope-input` at 1280px. Never the nav. A right-hand rail lands in the line-height field. This is a hole in what the tool can reach, not a complaint about how much room the bar takes - and it is not a narrow-window problem to be waited out by maximising.

**And the Overlay is most of a small window.** Sampled with `elementFromPoint` on a 4px grid with an element selected: about 27% of 1280x800, 58% of 480x800, 76% of 360x740. The panel is the expensive part at every width - roughly 19% against the bar's 5% at 1280x900, 63% against the bar's 12% at 360x740 - so shortening the bar was never going to be the fix. (Written first to a tenth of a percent, which the method does not support: the grid's phase against the chrome's edges moves each figure about half a point on its own.)

Peek answers the first: one key hides all the chrome, the click reaches what was underneath, and the chrome comes back with that element selected. The second is a separate, measured shed - the panel's shape below the width where a side column stops fitting, and one bar row where it is not earning its place.

`sample.html` cannot test any of this. Its `.wrap` carries 80px of top padding, so its first text clears a 44px bar by accident, and it has nothing at the right edge or the bottom-left corner at all.

## Acceptance criteria

- [x] A key hides every piece of Overlay chrome and restores it, and a click while hidden selects what was underneath and ends the peek
  - *Over-claimed as first written, corrected on review.* Not **every** piece: the hover and selection outlines (`.wt-box`) stay visible by design, because they are pointer-events:none and are the only feedback about what a click is about to select. The resize grips inside them are hidden, since those do take clicks. `test_the_resize_grips_stop_taking_clicks` asserts both halves of that. What is true is that everything which can intercept a click is hidden - which is the property that matters, and is what this box should have said.
- [x] Esc leaves a peek before it leaves the selection; the key is ignored while a field has focus, mid-gesture, and while placing a shape
- [x] Hiding the chrome does not disturb `--wt-bar-h` - a `display: none` bar measures 0 and misplaces the panel, the dock and the place-hint for as long as the peek lasts
  - *Said "*after* the peek ends" as first written, repeating an overstatement the ADR made and `overlay.css` had already retracted.* The `ResizeObserver` fires again the moment `display` is restored, so a `display: none` bar costs a frame of wrong geometry, not a lasting misplacement. `visibility: hidden` is still the right choice - it keeps the box measured while removing it from hit-testing and the tab order - but for a smaller reason than this box claimed. The tell was that the same file said one thing and the stylesheet said another, and nobody reading either alone could see it.
- [x] The key is discoverable at every width, including below 640px where the hint used to be hidden outright
- [x] A fixture exists whose content sits deliberately under each region of the chrome, and every test asserts both halves - that the region swallows the element, and that peek hands it back
- [x] The panel stops being a right-hand column at the width where a column stops fitting, chosen by measurement rather than by eye, and the dock moves clear of it
- [x] The bar gives back a row where that row is not paying for itself, without removing any control - a narrow window is not a reduced overlay
- [x] Every new behaviour is mutation-tested: shown to fail against a deliberately broken implementation
  - *True, but it took four attempts and the first three were wrong.* One mutation - removing `min-width: 110px` from `.wt-crumb` - appeared to survive repeatedly, and each time the response was a comment justifying why an unkillable guard was worth keeping, then an argument that it guarded nothing and should be deleted. All of it was fiction. The test had been given an injected `.wt-status { flex: 0 1 auto }` in an earlier round, added to "make the floor bite", which did the opposite: it hands the crumb more room and hides the floor entirely. The test was masking the thing it existed to prove. With the injection gone the crumb measures 80px without the floor, the mutation dies, and the guard is confirmed load-bearing. The lesson is worth more than the fix: **a surviving mutation is evidence about the test before it is evidence about the code**, and a test that stages the failure it checks for can stage it wrong.
- [x] ADR, CHANGELOG, README and CONTEXT record the decision, the rejected alternative, and the numbers it was argued from

## Blocked by

- None

## Notes

The page-offset alternative (`padding-top` on the page, sized from the already-measured `--wt-bar-h`) is nearly free and is the wrong fix: it addresses the bar and not the panel or the dock, it changes how the page renders, and it does not move a `position: fixed` header - the case most likely to be under the bar in the first place. Reasoning in full in the ADR.

Three cascade bugs of one shape turned up during the work and are worth knowing about before touching `overlay.css`: it declares most of its `@media` blocks around line 200 but its components much further down, so a block written up there silently loses at equal specificity to the base rule below it. One of the three had shipped inert in 0.7.1.

## Second review pass

The first QA round was pointed at `git diff HEAD`, which does not include untracked files - so the fixture, the whole peek test module, this issue and the ADR were all outside the diff that was reviewed. The second round covered them, and the split of what it found is the useful part: **almost nothing was wrong with what the code did, and a lot was wrong with what the code said about itself.**

Five live defects, each closed test-first:

- A drag or resize during a peek recorded an edit with the entire editing UI invisible. Peek hides the grips because they accept clicks, but a nudge is a drag on the element's own body and interact's resize band sits inside the element too - neither consulted the peek flag. Hiding the grips while leaving the body draggable was never a coherent position.
- `Esc` released the Overlay's own fields but not the page's, while the `H` guard treated both as fields and told the user to press `Esc`. One case narrower than the message it serves, which is the same failure the Esc branch was written to fix.
- No `ev.repeat` guard on `H`, so a held key strobed the chrome and finished wherever the repeat count left it.
- The peek note is one unwrappable centred line, so below its own width it hung off both edges at once - and it is the only text on screen during a peek and the only thing naming `Esc`.
- `max-width: 520px` and `min-width: 521px` are not adjacent. At a fractional width like 520.5, which browser zoom produces routinely, neither applied and ~93px of the change list sat under the panel taking no clicks.

The comment and doc corrections outnumbered the code fixes roughly three to one, and most were residue from the mutation-testing saga recorded above: explanations written during the three wrong attempts outlived the code they described. The starkest was a test comment asserting that a CSS floor "was deleted" while the stylesheet six lines away declared it and a live mutation run proved it load-bearing.

Two claims raised as defects were **refuted** by measurement rather than argument - a suspected `ResizeObserver` feedback cascade (instrumenting Chromium showed one bar callback and one panel callback per resize, no cascade) and a second media-query gap at 613/614 (nothing is meant to catch that range; the cap stops and the base rules resume). Both are recorded because a review that only accumulates findings has no way to be wrong.

One fix has **no test**, and that is stated rather than implied: the fractional-width gap cannot be driven in this harness. Playwright takes integer viewports and CDP rejects a float width, and after the fix the change is unobservable at every integer width by construction. The reasoning lives in the stylesheet beside the rule.
