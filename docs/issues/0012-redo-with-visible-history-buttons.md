# Issue 0012: Redo, with visible undo/redo buttons

> Labels: enhancement, ready-for-agent · Type: AFK

## Parent

[PRD: webtweak 0.4.0](../PRD-0.4.0.md)

## What to build

Undo is currently one-way and invisible. Stepping back too far means redoing the work by hand, and nothing on screen says undo exists or whether anything is left to undo - the only mention is a sentence in the hint bar, and the only feedback is a status line after the user has already lost their place.

Undo and redo buttons appear in the top bar and disable when their stack is empty, so the state of history is legible at a glance and undo becomes discoverable at all. `Shift+Cmd/Ctrl+Z` and `Ctrl+Y` both redo; the existing undo binding already excludes the shift modifier, so nothing needs reassigning.

Redo is built by having the undo path produce an **inverse batch** rather than by recording forward operations. Each ordinary undo step already carries the previous value, so the inverse only needs the current value captured at the moment of undo. Creation and removal are already exact inverses of each other in the undo vocabulary - undoing a creation removes an element, undoing a removal reinserts it - so undoing a creation yields a removal step and vice versa, capturing the parent, the following sibling and the element's edit entry at undo time. No existing undo-push site needs to change.

Making a new edit clears the redo stack, so stepping forward can never splice an abandoned branch of history into current work. After any undo or redo, the unsaved-changes state and the session change list are recomputed as they already are for undo, so the save prompt and the reconcile badge stay honest.

## Acceptance criteria

- [ ] Undo and redo buttons appear in the top bar
- [ ] Each button is disabled exactly when its stack is empty
- [ ] `Shift+Cmd/Ctrl+Z` and `Ctrl+Y` both redo
- [ ] Redo restores an undone property change
- [ ] Redo after an undone shape creation restores the shape, in the right place in the document
- [ ] Redo after an undone shape removal removes it again
- [ ] Making a new edit clears the redo stack
- [ ] The unsaved-changes prompt and the reconcile badge remain correct across undo and redo
- [ ] The hint bar mentions redo
- [ ] Browser tests cover the above and carry the browser marker

## Blocked by

- None - can start immediately
