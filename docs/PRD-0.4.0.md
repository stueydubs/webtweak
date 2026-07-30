# PRD: webtweak 0.4.0 - properties and quality of life

> Status: ready-for-agent
> A property-set and quality-of-life release for the Overlay. Adds a font picker fed by the Target page's own fonts, a Border group (border, radius, shadow) for existing elements, and redo. No change to the Patch contract, the Edits file format, or ADR-0001. See [CONTEXT.md](../CONTEXT.md), [ADR-0001](./adr/0001-capture-intent-not-rewrite-source.md), [ADR-0002](./adr/0002-shape-creation.md) and [ADR-0003](./adr/0003-compose-shorthands-from-discrete-controls.md).

## Problem Statement

Three gaps in the Overlay make by-eye work slower than it should be, and one of them makes the tool quietly inconsistent with itself.

**Fonts have to be typed from memory.** Font is the first control in the properties panel and the only one that demands you already know an exact string. The control reads the element's whole font stack deliberately, so fallbacks survive an edit - but that means to change a heading to the site's display face you must type `Fraunces, Georgia, serif` correctly, including its fallbacks, or you silently throw the fallbacks away. Type it wrongly and nothing happens at all: the value is rejected and you get a status line, not a font. The Target page already knows exactly which fonts it uses; the Overlay never asks it.

**A drawn shape can have a border, but the card you drew it next to cannot.** Shape creation brought Fill, Border colour and Border width to the panel, but only for shapes. Select an existing element and there is no border control at all, no corner radius and no shadow - they were excluded from the v1 property set. The result is an editor where a decorative rectangle is more editable than the real card beside it, which reads as a bug rather than a scope boundary.

**Undo is one-way and invisible.** `Cmd/Ctrl+Z` steps back through the session, but there is no way forward again, so an over-eager undo means redoing the work by hand. There is also nothing on screen to say undo exists or whether there is anything left to undo - the only mention is a sentence in the hint bar, and the only feedback is a status line reading `nothing to undo` after you have already lost your place.

## Solution

**The Font control offers the Target page's own fonts.** It becomes a text input backed by a suggestion list built from the page itself: every distinct font stack in use, plus any families declared in stylesheets webtweak can read. Picking one writes that stack verbatim, so fallbacks are preserved by construction rather than by the user's care. Typing an arbitrary stack still works exactly as it does today, so nothing that works now regresses.

**A Border group brings border, corner radius and shadow to real elements.** Border is authored as Width, Style and Colour - a number, a dropdown and a swatch - which together compose one `border` declaration. Touching any one of them on an element with no border seeds the other two, so a border appears the moment you act rather than after you have found all three. When the element already has a border on one side only, the controls edit *that side*, so a heading's bottom rule stays a rule instead of becoming a box. Corner radius is a number; shadow is a text field with a list of sensible presets, so the property nobody remembers the syntax of can be picked rather than recalled.

**The shape controls are renamed to Stroke and Stroke width**, so "Border" means one thing in the panel. A shape's border genuinely is a stroke - it centres on the path and scales with the shape - and calling both things Border after adding a real CSS border would be actively misleading.

**Redo arrives with visible controls.** Undo and redo buttons sit in the top bar and disable when their stack is empty, so the state is legible at a glance and undo becomes discoverable at all. `Shift+Cmd/Ctrl+Z` and `Ctrl+Y` both redo.

## User Stories

### The font picker

1. As a site builder, I want to see the font stacks my Target page already uses, so that I can restyle an element without typing a font name from memory.
2. As a site builder, I want picking a font from the list to write its complete stack, so that I keep the fallbacks the page's author intended instead of silently dropping them.
3. As a site builder, I want to still type an arbitrary font stack by hand, so that a font I am introducing for the first time is not blocked by a list that cannot know about it.
4. As a site builder, I want families declared as `@font-face` to appear too, so that a self-hosted face I have set up but not yet applied anywhere is one click away.
5. As a site builder, I want the list to work when my page loads fonts from a CDN, so that the common case of a hosted webfont is not the case that breaks.
6. As a site builder, I want webtweak's own interface fonts kept out of the list, so that the suggestions are my page's vocabulary and not the editor's.
7. As a site builder, I want the list to show stacks as they are authored, so that I can recognise which entry is my heading face and which is my body face.
8. As a site builder, I want an invalid typed font to be rejected as it is today, so that a typo cannot record a Patch the page never showed.

### Border, radius and shadow

9. As a site builder, I want to put a border on an element that has none, so that I can try a rule or an outline by eye.
10. As a site builder, I want a border to appear as soon as I set only its colour, so that the control does not look broken the first time I use it.
11. As a site builder, I want to choose a border colour from a swatch, so that I am not typing hex into a visual editor.
12. As a site builder, I want to choose a border style from a list, so that I do not have to remember which keywords are valid.
13. As a site builder, I want to change the width of a border that already exists, so that I can thicken a divider without redeclaring it.
14. As a site builder, I want the controls to show the border the element actually has when I select it, so that I am adjusting a real value rather than starting from a default.
15. As a site builder, I want to recolour a heading's bottom rule without gaining a border on the other three sides, so that a divider stays a divider.
16. As a site builder, I want to be told when an element's border is too complex for the controls, so that webtweak declines rather than quietly wrecking a deliberate design.
17. As a site builder, I want to see which side I am editing when only one side has a border, so that the outcome is not a surprise.
18. As a site builder, I want to round an element's corners with a single number, so that a card can be softened by eye.
19. As a site builder, I want to add a shadow by choosing from a few sensible presets, so that I do not have to recall the order of a shadow's four lengths.
20. As a site builder, I want to type a custom shadow when a preset is not right, so that the presets are a shortcut and not a cage.
21. As a site builder, I want to say "no border" explicitly, so that removing an authored border is a change I can express rather than an absence I cannot.
22. As a site builder, I want clearing a border field to forget that change entirely, so that abandoning an experiment does not leave a value behind in the Edits file.
23. As a site builder, I want undo to step back through border changes like any other property, so that the new controls behave like the ones I already trust.
24. As a site builder, I want the Border group hidden when a shape is selected, so that I am not offered a CSS border that would draw a rectangle around a triangle.
25. As a site builder, I want the shape's line control called Stroke, so that I can tell it apart from an element's border now that both exist.
26. As a site builder, I want border controls disabled rather than absent when they cannot apply, so that I learn the constraint instead of wondering where they went.

### Redo

27. As a site builder, I want to redo a change I undid, so that overshooting on undo costs me a keystroke instead of redoing the work by hand.
28. As a site builder, I want undo and redo buttons in the bar, so that I can step through history without knowing a shortcut exists.
29. As a site builder, I want those buttons disabled when their stack is empty, so that I can see whether there is anything to step through.
30. As a site builder, I want `Shift+Cmd/Ctrl+Z` and `Ctrl+Y` to redo, so that whichever convention I have in my fingers works.
31. As a site builder, I want redo to restore a shape I undid the creation of, so that history is symmetric for created elements and not just edited ones.
32. As a site builder, I want redo to re-remove a shape whose removal I undid, so that stepping forward is the exact inverse of stepping back.
33. As a site builder, I want making a new edit to discard the redo stack, so that stepping forward can never graft an abandoned branch of history onto my current work.
34. As a site builder, I want redo to leave the unsaved-changes state honest, so that the save prompt and the reconcile badge still reflect what is really on the page.

### Claude, the reconciler

35. As Claude, I want a border Patch to describe what the user actually saw, so that I write the border they were looking at rather than a fragment that would render differently.
36. As Claude, I want a per-side Patch when only one side was bordered, so that I preserve an asymmetric design instead of replacing it with a box.
37. As Claude, I want the new properties documented in the Reconcile skill, so that I know how to write them cleanly rather than inferring house style from a raw declaration.
38. As Claude, I want to keep the freedom to tidy a composed declaration into the site's conventions, so that the Overlay's job stays capture and mine stays judgement.
39. As Claude, I want no new Patch op for any of this, so that the existing Batch and Edits file semantics carry the release unchanged.

### The release

40. As an existing user, I want to be told to reinstall the bundled Reconcile skill, so that my local copy knows about the properties this release can emit.
41. As a maintainer, I want the recorded property scope in the domain context updated, so that the glossary does not still list borders and shadow as excluded once they ship.

## Implementation Decisions

### Scope and contract

- **No new Patch op, no Edits file change, no Fingerprint change.** Everything here emits ordinary property changes on existing elements. The `create` op stays specific to shape creation, and the running-history Batch semantics are untouched. This is a minor release.
- **ADR-0001 holds.** The Overlay still captures intent and never rewrites the Target page's source. One decision in this release sits in visible tension with it and is recorded as ADR-0003 rather than left implicit: composing a shorthand means the Overlay emits values the user did not individually set.
- **ADR-0002 is respected, not extended.** A shape's line remains an SVG stroke because that is what makes a real outline render on every shape kind; the new CSS border deliberately does not apply to shapes.

### The Overlay's control table

- The Overlay declares its editable properties in one table from which the panel markup, the live binding and the populate-from-computed-style read are all derived. Every control in this release is added as an entry in that table rather than as bespoke markup.
- **The table's one-control-one-property assumption is deliberately bent.** Border's three controls share a single property, which is a new pattern: each control's handler composes from the current value of all three fields rather than writing its own field in isolation. Without that, the three controls would overwrite each other's contribution to the same declaration. This is the highest-risk change in the release and the place a review should look first.
- Border, corner radius and shadow form a new panel group that hides for shapes, using the same group-level visibility rule that already hides typography and colour for shapes. Group-level visibility is how the panel works today; no per-control visibility mechanism is introduced.

### Border composition and seeding

- **Border is authored as Width (number), Style (select) and Colour (swatch), composing one declaration.** The alternative - emitting three separate longhand properties - was rejected because two of the three are individually invisible: on an element with no border, setting only a colour or only a width produces no on-screen change, while the browser's own support check still passes, so the Overlay would record a Patch for something the user never saw. That is the phantom-Patch failure the Overlay already guards against elsewhere.
- **Touching any border control on a border-less element seeds the others** to a working default so a border renders immediately. The seeded colour needs no invention: computed border colour defaults to the element's own text colour, so the swatch already shows something sensible. This mirrors how a created shape is seeded with a full style snapshot for the same reason - so its controls always have a real value to read and write.
- **The composed declaration is what the user saw**, which is the reason seeding does not violate capture-intent. Emitting only the one longhand the user touched would record something the preview never displayed.

### Detecting an asymmetric border

- **An element whose sides differ is detected by the computed border shorthand serialising to an empty string.** This came out of a browser prototype and is exact, so no parsing of multi-value width strings is needed:

  | element's CSS | computed shorthand |
  |---|---|
  | uniform border | `"2px dashed rgb(255, 0, 0)"` |
  | no border | `"0px none rgb(0, 0, 0)"` |
  | bottom only | `""` |
  | left and bottom differ | `""` |

- **When exactly one side has a visible border, the controls edit that side** and emit a per-side declaration. This is the common editorial case - bottom rules under headings - and composing a full border there would turn a divider into a box.
- **When several sides differ, the controls are disabled with an explanatory tooltip**, following the existing precedent where width and height are disabled on non-replaced inline elements so a user cannot record a Patch the element will not honour.

### The font suggestion list

- **Primary source is every distinct computed font stack on the Target page.** A browser prototype confirmed this is the only origin-proof source: reading rules from a CDN-hosted stylesheet raises `SecurityError: Cannot access rules`, so a page using a hosted webfont yields nothing from its font-face declarations even though that font is the page's display face. Computed style returns the full stack as authored, which is exactly what the control wants.
- **`@font-face` families are a supplement, gathered in a try/catch** over readable stylesheets only, so an unreadable sheet degrades the list rather than throwing.
- **The sweep skips the Overlay's own interface nodes**, or the editor's fonts would be offered as suggestions for the page.
- **The control stays a text input with a suggestion list, not a closed dropdown.** Free text is preserved, so the change is strictly additive and no currently-working edit becomes impossible.
- Shadow reuses the same suggestion-list mechanism for its presets, so the widget is built once and used twice. This creates the release's only blocking edge between work items.

### Redo

- **Redo is built by having the undo application produce an inverse batch** rather than by recording forward operations. Each ordinary undo step already carries the previous value, so the inverse needs the current value captured at undo time.
- **Creation and removal are already exact inverses of each other** in the undo vocabulary: undoing a creation removes an element, undoing a removal reinserts it. Undoing a creation therefore yields a removal step and vice versa, capturing the parent, the following sibling and the element's edit entry at undo time. No existing push site needs to change.
- **A new edit clears the redo stack**, so stepping forward can never splice an abandoned branch of history into current work.
- Undo and redo buttons live in the top bar and reflect their stacks' emptiness. Keyboard bindings are `Shift+Cmd/Ctrl+Z` and `Ctrl+Y`; the existing undo binding already excludes the shift modifier, so nothing needs to be reassigned.
- After any undo or redo the unsaved-changes state and the change list are recomputed, as they already are for undo, so the save prompt and the reconcile badge stay honest.

### The Stroke rename

- The shape controls' property names are already the SVG stroke properties; only their user-facing labels change. There is no Patch, Edits file or Reconcile impact.
- The shape's corner radius control keeps its name. Unlike stroke versus border, a shape's radius and an element's corner radius are the same concept in the same units, so renaming it would add noise without removing ambiguity.

### Documentation and the Reconcile skill

- **The bundled Reconcile skill learns the new properties**, including that a per-side declaration is deliberate and must not be normalised into an all-sides border. Because the skill is bundled and installed into the user's own skills directory, the release notes must tell existing users to reinstall it.
- **The domain context's recorded property scope is rewritten.** It currently states outright that borders and shadow are excluded, which ships false the moment this release does. Stroke is added to the glossary as distinct from Border.
- **ADR-0003 records the compose-and-seed decision**, the rejected longhand alternative, the empty-shorthand asymmetry test, and Stroke versus Border as distinct terms.

## Testing Decisions

- **What a good test is here:** drive the feature the way a user does - select an element, set a field, click a button - and assert on what the user or Claude can observe: the rendered page, the panel's own state, and the Patches written to the Edits file. Never reach into the Overlay's internals. A test that asserts a composed value without a render proving it visible is not testing this release's central claim, which is that the Patch matches what was on screen.
- **One seam, and it already exists: the browser end-to-end suite.** The Overlay is an injected script with no module surface, so a rendered page is the only place its behaviour is observable. The existing fixtures - a served page on an ephemeral port, a launched browser with the Overlay mounted, and a helper that selects an element and sets one panel field - cover every case in this release. No new seam is introduced.
- **A second seam was considered and rejected.** Exporting the composition and harvesting helpers for direct invocation would give fast local feedback, but it would grow a module surface on the Overlay purely for tests and would assert composed values without proving them rendered. A parallel surface that tests asserted against while users ran something else is the specific mistake this project removed in 0.2.0.
- **Prior art:** the existing browser modules, which use the shared fixtures rather than redeclaring them, and which are selected by marker and never by filename - a previous arrangement ran one browser module by name and silently excluded three others from every job.
- **Every new test carries the browser marker**, so it is selected by the browser job and excluded from the stdlib matrix. ~~Consequence to accept: none of this release's tests run on the development machine, because Playwright is not installed there. Installing it locally is worthwhile but is not a precondition for the work.~~ **Superseded.** Playwright was installed during this release and the full suite ran locally before every commit, which is how several defects were caught before landing rather than after. Setup is one command and is now written down — see `requirements-dev.txt` and the README's Development section (issue 0018), rather than one session's shell history.
- **Cases to cover:**
  - *Font:* the suggestion list contains the page's in-use stacks; it contains a declared `@font-face` family; it excludes the Overlay's own fonts; an unreadable cross-origin stylesheet degrades the list instead of throwing; picking an entry writes the full stack to the Patch; a typed arbitrary stack still records; an invalid typed value still records nothing.
  - *Border:* setting only a colour on a border-less element renders a visible border and records a composed declaration; the controls populate from an element that already has a uniform border; setting a width on a bottom-only element records a per-side declaration and leaves the other three sides unbordered; an element with several differing sides disables the controls; clearing a field reverts the change; a style of none is recordable; undo steps back through a border change.
  - *Group visibility:* the Border group is hidden when a shape is selected and shown otherwise; the shape controls read Stroke.
  - *Radius and shadow:* a radius change records; a preset shadow records; a typed shadow records; an invalid shadow records nothing.
  - *Redo:* redo restores an undone property change; redo after an undone shape creation restores the shape; redo after an undone shape removal removes it again; a new edit clears the redo stack; both buttons' disabled states track their stacks; both keyboard bindings work.
- **The shared page fixture is extended additively** with an element bordered on one side, an element with several sides differing, and a font-face declaration. Additive extension keeps a single fixture and leaves the fixture-staging helper unchanged; existing tests must be confirmed still passing after it, since some assert on specific elements of that page.

## Out of Scope

- **Structural DOM reordering** and **per-breakpoint authoring** - these are the v2 features that retire ADR-0001's promise, and nothing in this release approaches that boundary.
- **Per-side border controls.** An element with several differing sides is declined, not editable. Four sets of controls would roughly triple the densest part of the panel for an uncommon case.
- **A colour control that expresses alpha.** The swatch is opaque hex, which is why shadow is a text field with presets rather than discrete controls - a shadow's colour is almost always translucent.
- **Other shorthand properties** - outline, text-decoration, transition, transform - even though ADR-0003's composition pattern would extend to them.
- **Editing text copy**, still spoken to Claude rather than done in the Overlay.
- **Live-URL editing.** Input remains local source files.
- **Reordering the panel or redesigning it** to accommodate the new group beyond hiding it for shapes.

## Further Notes

- **There is one blocking edge in the work:** shadow's preset list reuses the suggestion-list mechanism the font picker introduces, so the font work must land first. Border and redo are independent of both and of each other.
- **The composed-property change is where a review should start.** The control table's one-control-one-property assumption has held for every property so far, and this release is the first to break it. The failure mode is silent - three controls overwriting each other's contribution to one declaration would still produce a valid-looking Patch.
- **The seeding behaviour deserves scrutiny against the project's own principles**, which is why it gets an ADR rather than a changelog line. The defence is that the Patch matches the preview; the cost is that Claude receives a width and style the user never explicitly chose.
- Each work item should be built in its own context, closing with a review of its own diff. The previous release's history is the argument: four sequential review passes each found real defects in the previous pass's fixes, and a single diff spanning a new control pattern, a document-wide harvesting sweep and an inverted undo stack is exactly the shape that hides them.
