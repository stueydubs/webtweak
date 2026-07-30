# Issue 0010: Per-side border editing and the mixed-side guard

> Labels: enhancement, ready-for-agent · Type: AFK

## Parent

[PRD: webtweak 0.4.0](../PRD-0.4.0.md)

## What to build

A heading with a bottom rule must stay a heading with a bottom rule after you recolour it. Bottom borders under headings and above footers are everywhere on the editorial sites webtweak is built for, and composing a full four-sided `border` onto one would turn a divider into a box - a silent, destructive edit.

When the selected element has a visible border on **exactly one side**, the Border controls target that side and emit a per-side declaration. The panel says which side is being edited, so the outcome is not a surprise.

When **several sides differ**, the controls are disabled with an explanatory tooltip. The Overlay declines rather than quietly wrecking a deliberate design, following the existing precedent that disables width and height on non-replaced inline elements so a user cannot record a Patch the element will not honour. Per-side controls are deliberately out of scope: four sets would roughly triple the densest part of the panel for an uncommon case.

Detection needs no string parsing. A browser prototype established that the computed border shorthand serialises to the empty string exactly when the sides differ:

| element's CSS | computed shorthand |
|---|---|
| uniform border | `"2px dashed rgb(255, 0, 0)"` |
| no border | `"0px none rgb(0, 0, 0)"` |
| bottom only | `""` |
| left and bottom differ | `""` |

The Reconcile skill must also learn that a per-side declaration is deliberate and must never be normalised into an all-sides border - the side *is* the intent.

## Acceptance criteria

- [ ] An element bordered on one side only has its controls target that side and emit a per-side declaration
- [ ] Editing such an element leaves the other three sides unbordered, in the rendered page and in the Patch
- [ ] The panel indicates which side is being edited
- [ ] An element whose sides differ has the Border controls disabled, with a tooltip explaining why
- [ ] A uniformly-bordered and a border-less element are unaffected by this change
- [ ] The Reconcile skill states that a per-side declaration must not be normalised into an all-sides border
- [ ] The shared page fixture gains an element bordered on one side and an element with several sides differing, and the existing suite still passes against it
- [ ] Browser tests cover the above and carry the browser marker

## Blocked by

- Issue 0009 (Border group - composed border, corner radius, and the Stroke rename)
