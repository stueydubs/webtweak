# Issue 0009: Border group - composed border, corner radius, and the Stroke rename

> Labels: enhancement, ready-for-agent · Type: AFK

## Parent

[PRD: webtweak 0.4.0](../PRD-0.4.0.md)

## What to build

Existing elements gain a border. Today a decorative shape can have a border but the card beside it cannot, which reads as a bug rather than a scope boundary.

A new Border group appears in the properties panel, hidden for shapes the same way typography and colour already are. It carries Width (a number), Style (a dropdown) and Colour (a swatch), which together compose **one** `border` declaration, plus a corner radius number.

The behaviour that matters is what happens on an element with no border: **touching any one of the three controls seeds the other two**, so a border renders the moment the user acts. Without that, two of the three controls do nothing visible on first use - a colour alone and a width alone both render nothing, because the initial border style is `none` - while the Overlay's invalid-value gate still passes the value through and records it. That would put a Patch for an invisible change into the Edits file, and from there into real source. The seeded colour needs no invention: computed border colour defaults to the element's own text colour.

Because the three controls share one property, each control's handler must compose from the current value of all three fields rather than writing its own in isolation. This bends the control table's long-standing one-control-one-property assumption and is the highest-risk change in the release; its failure mode is silent, because three controls overwriting each other's contribution still produces a valid-looking Patch.

The shape controls are relabelled **Stroke** and **Stroke width**, so "Border" means one thing in the panel. Their underlying properties are already the SVG stroke properties, so this is a label-only change with no Patch or Reconcile impact. The shape's Radius keeps its name - unlike stroke versus border, a shape's radius and an element's corner radius are the same concept in the same units.

Scope here is border-less and uniformly-bordered elements. Elements bordered on one side only, or on several sides differently, are Issue 0010.

See [ADR-0003](../adr/0003-compose-shorthands-from-discrete-controls.md).

## Acceptance criteria

- [ ] A Border group appears in the panel with Width, Style, Colour and Radius
- [ ] The Border group is hidden when a shape is selected, and shown for other elements
- [ ] Setting only a colour on a border-less element renders a visible border and records a single composed declaration
- [ ] Setting only a width on a border-less element likewise renders and records
- [ ] The controls populate from an element that already has a uniform border, so an existing border is adjusted rather than replaced from a default
- [ ] A style of `none` is expressible and records
- [ ] Clearing any of the three fields reverts the border change entirely
- [ ] Undo steps back through a border change like any other property
- [ ] The corner radius records
- [ ] The shape controls read Stroke and Stroke width; the shape's Radius label is unchanged
- [ ] The Reconcile skill documents the new properties
- [ ] Browser tests cover the above and carry the browser marker

## Blocked by

- None - can start immediately
