# webtweak captures edit intent for an intelligent reconciler, rather than rewriting source itself

Pinegrow and other visual editors need a source-preserving HTML parser that surgically edits real files without mangling hand-formatting - that parser is the hard, expensive heart of such a tool. webtweak deliberately does not build one. Because every webtweak session ends with Claude reconciling the result, the editor only has to *capture what changed* as machine-readable Patches (a rich element Fingerprint plus property/value changes, with nudges stored as snapped intent rather than literal CSS); Claude does the judgment-heavy work of locating each element in real source and writing clean, house-style CSS. This is hard to reverse (the whole capture/serve/reconcile architecture is built around it), surprising to a future reader (no source-rewriting, no stable injected IDs, intent-not-literal nudges), and a genuine trade-off: we accept that webtweak alone cannot produce a finished file and that a nudge may land at a tidy value rather than the exact pixel distance, in exchange for a tool small enough to build and own in Python stdlib.

## Consequences

- webtweak is useless without the Claude reconcile step - it is half a loop by design, not a standalone editor.
- Element identity is a Fingerprint (tag, id/classes, truncated text, `outerHTML` snippet, best-effort selector), never an injected attribute, so source is untouched until Reconcile.
- Genuinely ambiguous matches (identical siblings) and systemic-vs-single-element scope are resolved by Claude asking the user, not by the tool guessing.
