# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

## Before exploring, read these

- **`CONTEXT.md`** at the repo root. In this repo it is substantial and load-bearing: a glossary with explicit `_Avoid_` lists, a Relationships section, and a long "Decisions captured" section recording why the design is the shape it is. Read it before proposing anything.
- **`docs/adr/`** - read the ADRs that touch the area you are about to work in.
- **`docs/research/`** - cited findings produced by `/research` agents, each on its own branch. Read one when a ticket links it.

This repo is **single-context**. There is no `CONTEXT-MAP.md` and no per-context `CONTEXT.md`, and none should be created unless the repo genuinely splits into multiple packages.

If any of these files don't exist, **proceed silently**. Don't flag their absence; don't suggest creating them upfront. The `/domain-modeling` skill (reached via `/grill-with-docs` and `/improve-codebase-architecture`) creates them lazily when terms or decisions actually get resolved.

## File structure

```
/
├── CLAUDE.md
├── CONTEXT.md
├── docs/
│   ├── adr/
│   │   ├── 0001-capture-intent-not-rewrite-source.md
│   │   └── ...
│   ├── agents/
│   ├── issues/          ← historical, pre-dates GitHub Issues
│   └── research/
├── overlay/
├── reconcile/
└── webtweak.js
```

Note `docs/issues/` - it holds numbered markdown issue files from before this repo used GitHub Issues. It is a historical record, **not** the issue tracker. New issues go to GitHub (`docs/agents/issue-tracker.md`).

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in `CONTEXT.md`. Don't drift to synonyms the glossary explicitly avoids - it lists them for exactly this reason. Say **Target page**, not "live site" or "URL". Say **Band**, not "breakpoint" or "viewport". Say **Peek**, not "hide" or "preview mode".

If the concept you need isn't in the glossary yet, that's a signal - either you're inventing language the project doesn't use (reconsider) or there's a real gap (note it for `/domain-modeling`).

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> _Contradicts ADR-0001 (capture intent, not rewrite source) - but worth reopening because..._

This is live rather than hypothetical here: the current wayfinder map deliberately revisits ADR-0001, so a change in that area is expected to cite it rather than quietly diverge from it.

## House style

No em-dashes or en-dashes anywhere. Use a hyphen with spaces (" - "). `tests/test_shipped_prose.py` fails CI on them in the shipped files, and house style extends the rule to everything else.
