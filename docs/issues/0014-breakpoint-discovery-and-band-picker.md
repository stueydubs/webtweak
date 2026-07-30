# Issue 0014: Breakpoint discovery and the band picker

> Labels: enhancement, ready-for-agent · Type: AFK

## Parent

[PRD: per-breakpoint authoring](../PRD-per-breakpoint-authoring.md)

## What to build

The Overlay learns which breakpoints the Target page declares, and lets the user say which one they are editing. Nothing is recorded differently yet - this ticket is the target selector that Issue 0015 writes through, and it must be shippable and honest on its own.

A control in the top bar reads **`Applies at:`** followed by the current scope - `all widths` by default, or a width such as `≤600px`. Opening it lists every media query the page's own stylesheets declare, with the real condition text beside the readable form, marking which of them match at the current window width. Picking one sets the scope. The list is the second consumer of the suggestion-list widget the font picker introduced.

**The control must not say "editing".** A mock that labelled it `Editing: (max-width: 480px)` read as though the media query were the thing being edited, which is not what it is: the element is the subject and the band is the condition. The breadcrumb keeps naming the selected object, and the properties panel states both together (`div.card at ≤480px`) so neither can be mistaken for the other.

**A band the window is not currently inside is listed but not selectable**, showing the resize needed to reach it (`resize under 480px`). Authoring in a band you cannot see means typing a value the panel cannot display - `getComputedStyle` at 640px does not contain a 480px-only declaration, so the field snaps back to what renders now and fights the user - and, worse, recording a change that was never previewed. Same rule as `print`, reached from the other direction.

**Dragging out of the band being authored moves the scope** to the narrowest band that still matches, ending at `all widths`. The bar shows the scope at all times, so the change is observable rather than silent.

Bands are gathered the way `@font-face` families are: `CSSMediaRule.conditionText` over readable stylesheets in a try/catch, so a CDN-hosted sheet degrades the list instead of throwing. Nested grouping rules are walked. webtweak's own stylesheet is skipped, or the Overlay would offer its own queries as the page's.

**Several bands match at once**, which a browser prototype confirmed: at a 480px window both `(max-width: 900px)` and `(max-width: 600px)` match. So the target cannot be inferred silently. The default is the **narrowest matching band** - the most specific, and what someone who has just dragged their window narrow is thinking about - and the picker always shows which it chose. `base` stays selectable at any width, because "this is wrong everywhere and I happened to notice it on mobile" is a real edit.

**Non-width conditions are listed as unavailable, with the reason.** The same sweep finds `print` and `prefers-color-scheme`; neither can be previewed by resizing a window, so offering them would invite a Patch for a change the user was never shown. They appear, greyed, saying why - following the mixed-side border guard, which declines out loud rather than hiding the case.

**A manual condition can be typed**, so a page whose stylesheets are entirely unreadable, or which declares no queries at all, is not locked out of the release. The list is a convenience, never a gate - exactly as the font list is.

## Acceptance criteria

- [ ] The band picker lists every width media query the Target page declares
- [ ] Bands matching the current window width are marked as matching
- [ ] The control is labelled as a scope (`Applies at`), never as the editing subject
- [ ] The breadcrumb still names the selected element, and the panel states element and scope together
- [ ] The bar shows a readable width form; the picker shows the real condition text
- [ ] The default scope is the narrowest matching band, and `base` when none match
- [ ] `base` is selectable while a narrow band matches
- [ ] A band that does not match the current window is listed but not selectable, showing the resize needed to reach it
- [ ] Dragging out of the current band moves the scope to the narrowest band that still matches
- [ ] A `print` (or other non-width) query is listed as unavailable, with a reason
- [ ] An unreadable cross-origin stylesheet leaves the list populated from the readable ones rather than throwing
- [ ] A page declaring no media queries offers `base` plus manual entry
- [ ] A manually typed condition becomes the editing target
- [ ] The picker shows the current target at a glance, without opening it
- [ ] The shared page fixture gains media queries, and the existing suite still passes against it
- [ ] Browser tests cover the above and carry the browser marker

## Blocked by

- None - can start immediately
