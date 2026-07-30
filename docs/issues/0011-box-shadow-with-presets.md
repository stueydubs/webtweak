# Issue 0011: box-shadow with preset suggestions

> Labels: enhancement, ready-for-agent · Type: AFK

## Parent

[PRD: webtweak 0.4.0](../PRD-0.4.0.md)

## What to build

A Shadow field joins the Border group, offering a handful of sensible presets while still accepting any typed value.

Shadow is the one property in this release that resists discrete controls. Building it out of parts would need four lengths, a colour and an inset flag - six controls for one property - and a shadow's colour is almost always translucent while the Overlay's colour swatch is opaque hex. So it stays a text field, but backed by the same suggestion list the Font control uses, which turns the property nobody remembers the syntax of into one you pick rather than recall. Typing a custom shadow still works, so the presets are a shortcut and not a cage.

Invalid input needs no new handling: the Overlay's existing invalid-value gate rejects a malformed shadow without recording a Patch, exactly as it does for any other free-text property.

## Acceptance criteria

- [ ] A Shadow field appears in the Border group and is hidden for shapes with the rest of that group
- [ ] It offers a small set of presets, including one that removes the shadow
- [ ] Choosing a preset applies it live and records it into the element's Patch
- [ ] Typing a custom shadow applies and records
- [ ] Typing an invalid shadow records nothing
- [ ] Clearing the field reverts the change
- [ ] The Reconcile skill documents the property
- [ ] Browser tests cover the above and carry the browser marker

## Blocked by

- Issue 0008 (Font picker fed by the Target page's own fonts) - for the suggestion-list widget
- Issue 0009 (Border group - composed border, corner radius, and the Stroke rename) - for the group it lives in
