# Changelog

All notable changes to webtweak are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Shape creation** - draw decorative shapes (square, rectangle, circle,
  ellipse, triangle, star, diamond, pentagon, hexagon) onto the page from a new
  "Shape" palette in the top bar. Place a shape by clicking the palette then
  clicking the page, **or by dragging the shape straight from the palette onto the
  page** and releasing where you want it. webtweak's first element-creation
  feature. Each shape is one inline `<svg>`, so a real stroke renders on every kind
  and fill/border colour cascade uniformly.
- **Shape panel group** - Fill, Border (stroke) colour, Border width, and corner
  Radius (rect/square only), on top of the existing Box width/height controls.
- Shapes drag anywhere on their body to reposition (true move), resize by grabbing
  the corner/edge grips, undo (Cmd/Ctrl+Z removes a just-created shape), and restore
  after reload like any other edit.

### Changed
- The selection resize grips are now functional drag handles you grab directly,
  rather than visual hints. Previously the resize zone sat just inside the element
  edge while the grips were drawn on the edge, so aiming at a grip often missed;
  resizing (shapes especially) now works wherever the grip is shown.
- New patch op `op: "create"` carrying the shape kind, self-describing geometry,
  an insertion anchor, and a full style snapshot; the reconcile skill gained an
  insert path that writes clean source for it. See ADR-0002.

### Fixed
- A shape's controls now always record (a shape has no authored baseline), so a
  1px border width or a `#000000` fill/stroke is captured rather than mistaken for
  a revert against the SVG default and silently dropped from the patch.
- Restoring saved shapes after a reload no longer marks the page as having unsaved
  changes (no spurious "leave site?" prompt).
- Grip-resize now resolves coordinates correctly under a `transform: scale()`
  ancestor (e.g. A4/print-preview layouts).
- Picking a shape to place now clears any current selection first, so its grips
  can't swallow the placement click; Deselect/Esc cancels an in-progress placement.

## [0.1.1] - 2026-06-24

### Fixed
- Clicking empty space (the page body or root) now deselects the current
  element instead of leaving it stuck selected.
- Drag and resize are more robust on A4, scaled, and SVG pages.
- Removed a stray `./` prefix from the bin path so the npm package resolves
  correctly when installed globally or run via npx.

## [0.1.0] - 2026-06-23

### Added
- Initial release. A local visual editor for hand-coded HTML/CSS pages: drag,
  resize, and restyle an existing page by eye while webtweak captures the
  changes as machine-readable patches.
- Node.js server (`webtweak <page.html>`) that serves the page's own directory
  and injects the editing overlay.
- `--port` and `--no-browser` flags.
- Reconcile skill (`reconcile/`) for folding captured patches into source CSS.
- Published to npm; installable globally or runnable via `npx webtweak`.

[Unreleased]: https://github.com/stueydubs/webtweak/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/stueydubs/webtweak/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/stueydubs/webtweak/releases/tag/v0.1.0
