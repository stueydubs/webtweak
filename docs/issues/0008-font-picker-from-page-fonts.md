# Issue 0008: Font picker fed by the Target page's own fonts

> Labels: enhancement, ready-for-agent · Type: AFK

## Parent

[PRD: webtweak 0.4.0](../PRD-0.4.0.md)

## What to build

The Font control stops being a bare text box you type a stack into from memory, and starts offering the Target page's own fonts as suggestions.

Selecting an element and opening the Font control shows a list built from the page itself: every distinct font stack in use, plus any families declared as `@font-face` in stylesheets the Overlay can read. Picking an entry writes that stack verbatim, so the fallbacks the page's author intended survive the edit instead of depending on the user retyping them correctly. Typing an arbitrary stack by hand still works exactly as it does today - the list is a suggestion, not a closed set - so no edit that is possible now becomes impossible.

The list must be built without help from the stylesheets, because it cannot rely on them: reading rules from a CDN-hosted sheet raises a `SecurityError`, so a page whose display face comes from a hosted webfont yields nothing from its font-face declarations. Computed style is the origin-proof source and returns the whole stack as authored. Font-face families are a useful supplement for a self-hosted face that is declared but not yet applied anywhere, gathered defensively so an unreadable sheet degrades the list rather than throwing.

This ticket also introduces the suggestion-list widget that Issue 0011 reuses for shadow presets.

## Acceptance criteria

- [ ] The Font control offers every distinct font stack in use on the Target page
- [ ] A family declared as `@font-face` in a readable stylesheet also appears
- [ ] A stylesheet whose rules cannot be read leaves the list populated from computed style rather than throwing
- [ ] The Overlay's own interface fonts do not appear as suggestions
- [ ] Picking a suggestion writes the complete stack into the element's Patch, fallbacks intact
- [ ] Typing an arbitrary stack still applies and still records
- [ ] Typing an invalid value still records nothing, as it does today
- [ ] The shared page fixture gains a font-face declaration, and the existing suite still passes against it
- [ ] Browser tests cover the above and carry the browser marker

## Blocked by

- None - can start immediately
