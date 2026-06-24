# Changelog

All notable changes to webtweak are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[0.1.1]: https://github.com/stueydubs/webtweak/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/stueydubs/webtweak/releases/tag/v0.1.0
