# The real dependency cost of every CSS-parsing option

Research for [issue #4](https://github.com/stueydubs/webtweak/issues/4). Establishes the numbers a
deterministic CSS writer decision will rest on. **This document does not make the decision.**

Every figure marked *measured* was produced on this machine (Linux x86_64, Node v24.18.1, npm
11.16.0, 2026-08-02) by installing into `/tmp` and running the scripts described below. Figures
marked *quoted* come from the npm registry or upstream docs and are cited inline. Nothing here is
taken from a blog post.

## What this changes for webtweak

- **Byte-identical round-trip is not a spectrum, it is a pass/fail, and only one library passed.**
  postcss reproduced all five test stylesheets byte-for-byte, including the repo's own 51 KB
  `overlay/overlay.css`. css-tree and lightningcss both failed every one.
- **The two failing libraries fail in ways that hit reconcile's stated promises directly**, not
  incidentally: lightningcss reorders declarations (breaking "key order is cascade order") and
  rewrites `(max-width: 600px)` into `(width <= 600px)` in blocks the edit never touched (breaking
  "write the block's existing condition text"). css-tree drops every comment.
- **"Zero dependencies" and "vendored like interact.js" turn out to be separable questions.**
  postcss and css-tree each reduce to one self-contained file in the 200 KB range, comparable to the
  98 KB `interact.min.js` already in `overlay/`. lightningcss cannot: it is a 9.6 MB per-platform
  native binary with eleven platform variants.
- **The hand-rolled option's cost is not the tokeniser, it is the comment handling.** A 77-line
  brace scanner that already understands strings, comments, nesting and `url()` still failed to
  locate three of the five top-level rules in a normal hand-written stylesheet, because a comment
  above a rule is absorbed into its selector.
- **Licence shape differs across the three**: two MIT, one MPL-2.0 file-level copyleft against an
  MIT project.

## Comparison table

| | postcss 8.5.25 | css-tree 3.2.1 | lightningcss 1.33.0 | hand-rolled |
|---|---|---|---|---|
| Installed `node_modules` (measured) | **390,358 B** (704 K) | 2,236,119 B (3.2 M) | **10,591,244 B** (11 M) | 0 |
| Transitive deps (measured) | 3 | 2 | 1 + one of 11 platform binaries | 0 |
| Dep names | `nanoid`, `picocolors`, `source-map-js` | `mdn-data`, `source-map-js` | `detect-libc`, `lightningcss-linux-x64-gnu` | none |
| Own package unpacked (quoted) | 217,252 B / 55 files | 1,362,649 B / 278 files | 513,814 B / 14 files | n/a |
| Licence (verified in `LICENSE`) | **MIT** | **MIT** | **MPL-2.0** | n/a |
| Dep licences (quoted) | MIT, ISC, BSD-3-Clause | CC0-1.0, BSD-3-Clause | Apache-2.0 | n/a |
| **Byte-identical round-trip** | **Yes, 5 of 5 fixtures** | No, 0 of 5 | No, 0 of 5 | n/a |
| Comments preserved | **10 of 10** (+ awkward ones in `raws`) | 0 of 10 | 0 of 10 | n/a |
| Declaration order | preserved | preserved | **reordered** | n/a |
| `@media` condition text | preserved verbatim | whitespace-stripped | **rewritten to range syntax** | n/a |
| `@media` nesting structure | preserved | preserved | preserved | n/a |
| Malformed CSS | throws `CssSyntaxError` with line:col | silently recovers, re-nests | silently recovers | n/a |
| Single-file vendorable | **Yes, 215,086 B** (esbuild CJS) | **Yes, 202,536 B** (ships `dist/csstree.esm.js`) | **No** (9.6 MB native `.node`) | Yes |
| Native binary / build step | none | none | **native `.node` per platform** | none |

Vendoring reference points from this repo (measured): `overlay/interact.min.js` is 98,204 B,
`webtweak.js` is 41,854 B.

## Method

Four isolated scratch installs under `/tmp/csspm/`, one package each, nothing installed into the
repo. Sizes are `du -sb` over each `node_modules`. Round-trips parse the fixture and re-serialise
it, then compare with `===` against the source string and with `diff -u`.

Five fixtures were used:

1. `fixture.css` (1,637 B) - the realistic one the ticket asked for: a `:root` custom-property block
   with aligned values, comments in six positions (file header, section header, between two
   declarations, inline after a declaration, inside an `@supports`, inside an `@media`, and a
   trailing one at EOF), tab-indented and space-indented rules side by side, a three-selector rule
   split over three lines, `@supports` with a nested `@media`, `@media (max-width:600px)` written
   with no space after the colon and carrying its own nested `@supports`, and `@media print`.
2. `hard.css` (618 B) - awkward positions: `@charset`, `@import ... layer()`, a mid-selector-list
   comment, a comment between a property and its colon, a comment inside an `@media` prelude, a data
   URI containing `{}`, a string containing `a}b;c{`, a custom property whose value contains braces,
   stray `;;;`, CSS nesting with `&`, `@layer`, `@container`, and an empty rule.
3. `min.css` (386 B) - the whole of fixture 1 minified onto one line.
4. `site/style.css` (6,261 B) - the repo's own demo stylesheet.
5. `overlay/overlay.css` (51,109 B) - the repo's own overlay stylesheet, 139 rules, 538
   declarations, 79 comments.

Beyond round-tripping, each option was also asked to perform the actual reconcile task: **fold
`letter-spacing: 0.01em` into the `h1` rule inside the `@media (max-width: 600px)` block the
stylesheet already has**, matching the condition case- and whitespace-insensitively as
`reconcile/SKILL.md` requires.

---

## postcss 8.5.25

Source: <https://github.com/postcss/postcss>, <https://www.npmjs.com/package/postcss>

### Size and dependencies (measured)

```
390,358 B  node_modules total
217,252 B  postcss
139,872 B  source-map-js
 24,714 B  nanoid
  6,373 B  picocolors
```

`npm view postcss dependencies` returns exactly three, and `npm install` added 4 packages. Grepping
`postcss/lib/` shows all three are confined to source-map generation (`map-generator.js`,
`previous-map.js`, `input.js`) and to colouring syntax errors in a terminal
(`terminal-highlight.js`, `css-syntax-error.js`). None is on the parse-then-stringify path.

### Licence

MIT, confirmed in `node_modules/postcss/LICENSE`. Deps: `nanoid` MIT, `picocolors` ISC,
`source-map-js` BSD-3-Clause (all quoted from `npm view <pkg> license`).

### Round-trip: lossless on all five fixtures

```
fixture.css        identical: true   1637 ->  1637 bytes
hard.css           identical: true    618 ->   618 bytes
min.css            identical: true    386 ->   386 bytes
site/style.css     identical: true   6261 ->  6261 bytes
overlay/overlay.css identical: true 51109 -> 51109 bytes
```

`diff -u` is empty in every case. Comments survive as first-class `Comment` nodes (10 of 10 in
`fixture.css`); comments in positions where a node cannot exist survive inside `raws`, with a clean
parsed value alongside:

```
decl with comment in raws:   margin  {"between":"/*between prop and colon*/:"}
rule with comment in raws:   .a,.b   raws.selector.raw = ".a,/*mid-selector*/.b"
atrule with comment in raws: media   {"afterName":"/*in prelude*/ "}
```

That last one matters: `at.params` reads back as the clean `screen and (max-width:600px)` while the
comment is parked in `raws.afterName`, so a normalised condition comparison works on a prelude that
carries a comment.

### The reconcile task

Folding into the existing `@media` block produced a one-line diff, preserving the odd `h1    {`
alignment, the no-space-after-colon condition text, the trailing prelude comment and every byte of
the rest of the file:

```diff
 @media (max-width:600px) {   /* note: no space after the colon */
   .hero { padding: 12px; }
-  h1    { font-size: 32px; }
+  h1    { font-size: 32px; letter-spacing: 0.01em; }
```

**One gotcha found, with a fix.** Appending a plain object (`r.append({ prop, value })`) makes
postcss infer whitespace by sampling the document, and it samples the *first* declaration in the
file, not a nearby one. Against `fixture.css`, whose first declaration is the aligned
`--ink:        #1a1a1a`, that produced `letter-spacing:        0.01em`. Copying `raws.between` and
`raws.before` from a sibling in the target rule fixes it and yields the diff above. On the minified
fixture the same inference works in webtweak's favour, producing minified output with no special
casing:

```
...@media (max-width:600px){.hero{padding:12px}h1{font-size:32px;letter-spacing:0.01em}}@media print{...
```

### The awkward cases, resolved

| Case | postcss result |
|---|---|
| Rule preceded by a comment | `:root`, `body`, `.byline` each found once by exact selector |
| Nested `@supports` inside `@media` | `at.each()` enumerates direct children, so the depth-1 `.hero` is distinguishable from the one inside `@supports` |
| Multi-selector rule | `rule.selectors` returns `[".card", ".panel > .card", "article .card:not(.is-muted)"]` |
| Custom property containing braces | parsed as a declaration, `--raw` value `"{ this is not css }"`, no phantom rule |
| CSS nesting | `.nest` children read as `decl:color , rule:& .child`, so an insertion point before the nested rule is addressable |
| Malformed input | throws `CssSyntaxError: 2:1: Unclosed block` |

That last row is a behaviour difference worth naming rather than a defect: postcss refuses loudly on
an unclosed block where css-tree and lightningcss both silently recover into a different document.

### Vendorability

Bundles to **one self-contained 215,086 B CommonJS file** with esbuild, verified to round-trip
`fixture.css` byte-identically from a directory containing no `node_modules` at all. No native
binary, no runtime data files, no build step for the consumer.

The ESM format does **not** work: postcss uses dynamic `require()` of node builtins, and an
`--format=esm` bundle throws `Error: Dynamic require of "path" is not supported` at import time. CJS
is the working form. postcss also ships CJS plus a `.mjs` wrapper as published, so copying the
`postcss/lib/` directory wholesale is a second viable route with no bundler involved.

---

## css-tree 3.2.1

Source: <https://github.com/csstree/csstree>, <https://www.npmjs.com/package/css-tree>

### Size and dependencies (measured)

```
2,236,119 B  node_modules total
1,362,649 B  css-tree
  732,388 B  mdn-data
  139,872 B  source-map-js
```

Two direct dependencies. `mdn-data` is the CSS syntax database backing the lexer, loaded at runtime
via `createRequire` in `lib/data.js` (three JSON files: `at-rules.json`, `properties.json`,
`syntaxes.json`), plus css-tree's own `data/patch.json` (45.6 KB).

### Licence

MIT, confirmed in `node_modules/css-tree/LICENSE`. Deps: `mdn-data` CC0-1.0, `source-map-js`
BSD-3-Clause (quoted).

### Round-trip: not lossless, and not close

`csstree.generate()` is a minifying serialiser. There is no formatting option.

```
fixture.css   identical: false   1637 ->  836 bytes  (49% smaller)
hard.css      identical: false    618 ->  489 bytes
min.css       identical: false    386 ->  385 bytes  (only the trailing newline)
```

The `fixture.css` output, in full, is one line:

```css
:root{--ink:        #1a1a1a;--paper:      #fdfcf8;--accent:     #7a5c3e;--measure:    68ch;--space-unit: 8px}body{margin:0;color:var(--ink);background:var(--paper);font-family:"Iowan Old Style",Georgia,serif;line-height:1.6}h1{font-size:48px;margin:0 0 24px}.hero{padding:32px 24px;background:var(--paper);border-bottom:2px solid var(--accent)}.card,.panel>.card,article .card:not(.is-muted){padding:16px;border-radius:12px 12px 0 0}.byline{color:var(--accent);line-height:1.35;letter-spacing:0.02em}@supports (display:grid){.layout{display:grid;grid-template-columns:1fr min(var(--measure),100%) 1fr}@media (min-width:900px){.layout{gap:calc(var(--space-unit)*3)}}}@media (max-width:600px){.hero{padding:12px}h1{font-size:32px}@supports (backdrop-filter:blur(4px)){.hero{backdrop-filter:blur(4px)}}}@media print{.hero{border-bottom:0}}
```

What it **does** get right, and this is worth crediting precisely: declaration order is preserved
exactly; `@supports` containing `@media`, and `@media` containing `@supports`, both survive with
correct nesting; the multi-selector rule keeps all three selectors in order; and the internal
whitespace of custom-property values survives (`--ink:        #1a1a1a`) because those parse as raw
token streams.

What it destroys: **all formatting, and every comment.** Ten comments in, zero out.

Comments never enter the AST at all. `csstree.walk` finds zero `Comment` nodes. The parser instead
accepts an `onComment(value, loc)` **callback**, which fired for all 10 comments with correct source
offsets - so the comments are observable, but there is nothing for `generate()` to re-emit. It is a
reporting channel, not preservation.

On `hard.css` it also rewrote a quoted data URI into an unquoted escaped one:

```
.e{background:url(data:image/svg+xml;utf8,<svg\ xmlns=\'http://www.w3.org/2000/svg\'>{}</svg>)}
```

Semantically equivalent, but it is a rewrite of a line nobody edited.

### The reconcile task, via the position-splice hybrid

css-tree's `positions: true` option is the interesting part. It attaches `loc.start.offset` and
`loc.end.offset` to every node, which makes a different strategy available: **use css-tree only as a
locator and splice the original source string by byte offset, never calling `generate()`.**

Measured offsets on `fixture.css`:

```
@media "(min-width:900px)"  offsets 1216 - 1297
@media "(max-width:600px)"  offsets 1301 - 1550
@media "print"              offsets 1552 - 1598
rule h1 (base)              590 - 631,   block 593 - 631
rule h1 (in @media)        1396 - 1422,  block 1402 - 1422
```

Walking `at.block.children` for direct children only (so the nested `@supports` is not descended
into), locating the `h1` rule, and splicing before its closing brace produced **exactly the same
one-line diff postcss produced**:

```diff
 @media (max-width:600px) {   /* note: no space after the colon */
   .hero { padding: 12px; }
-  h1    { font-size: 32px; }
+  h1    { font-size: 32px; letter-spacing: 0.01em; }
```

So css-tree is losslessly *usable* even though it is not losslessly *round-trippable*, provided the
writer never regenerates. The cost is that all output formatting becomes the writer's own problem,
where postcss's `raws` carry it.

### Malformed input

css-tree recovers silently. Given a stylesheet with an unclosed `@media` block, it produced
`.ok{color:red}@media (max-width:600px){.a{color:blue}.b{color:green}}` with **zero** parse errors
reported through `onParseError` - `.b`, which the author wrote at base level, ended up inside the
media block.

### Vendorability

**Yes, and better than expected.** css-tree ships a prebuilt single-file ESM bundle at
`dist/csstree.esm.js`, **202,536 B**, verified here to run standalone from a directory with no
`node_modules`, exporting working `parse`, `generate` and `walk`. That is 4 KB smaller than the
postcss bundle and needs no bundler at all.

Correcting an earlier reading in this same investigation: bundling css-tree myself with esbuild
**failed** in both formats - CJS threw `ERR_INVALID_ARG_VALUE` on `createRequire(import.meta.url)`,
and ESM threw `Cannot find module '../data/patch.json'`, because the lexer loads its syntax data from
disk at runtime. The shipped `dist/` bundle has that data inlined and does not have the problem. Any
claim that css-tree "cannot be vendored as one file" is wrong; it is the DIY bundle that cannot.

Caveat on that verification: I exercised `parse`, `generate` and `walk` through the dist bundle. I
did **not** exercise the lexer or `definition-syntax` through it, so I cannot state from measurement
that every css-tree API works standalone - only the three a writer would use.

---

## lightningcss 1.33.0

Source: <https://github.com/parcel-bundler/lightningcss>,
<https://www.npmjs.com/package/lightningcss>

### Size and dependencies (measured)

```
10,591,244 B  node_modules total  (11 M)
10,048,780 B  lightningcss-linux-x64-gnu     <- 9.6 MB single native .node binary
   513,814 B  lightningcss
    26,437 B  detect-libc
```

One direct dependency (`detect-libc`, Apache-2.0) plus **eleven** platform-specific
`optionalDependencies`, of which npm installs the one matching the host:

```
lightningcss-darwin-x64        lightningcss-linux-arm64-musl
lightningcss-darwin-arm64      lightningcss-linux-x64-musl
lightningcss-linux-x64-gnu     lightningcss-win32-x64-msvc
lightningcss-linux-arm64-gnu   lightningcss-win32-arm64-msvc
lightningcss-linux-arm-gnueabihf  lightningcss-freebsd-x64
lightningcss-android-arm64
```

The installed package contains a single file of consequence:
`lightningcss.linux-x64-gnu.node`, 9.6 MB.

### Licence

**MPL-2.0**, confirmed in `node_modules/lightningcss/LICENSE`. This is the only non-permissive
licence in the set, and webtweak is MIT (`LICENSE`, `package.json`). MPL-2.0 is file-level copyleft
rather than viral, so linking is not the problem; vendoring modified copies would be. Flagging the
difference in kind, not making the call.

### Round-trip: the most destructive of the three

Run with `minify: false` and no targets:

```
fixture.css          identical: false   1637 ->  1058 bytes
hard.css             identical: false    618 ->   623 bytes
min.css              identical: false    386 ->   544 bytes
site/style.css       identical: false   6261 ->  5670 bytes, comments 9 -> 0
overlay/overlay.css  identical: false  51109 -> 14916 bytes, comments 79 -> 0
```

The `overlay.css` figure surprised me, so I re-ran it and then audited the output rule by rule
rather than trusting the byte count. **Nothing was dropped.** The 71% shrink is 79 comments removed
plus whitespace normalisation, and the apparent rule loss (139 rules in, 136 out) is lightningcss
**merging** two adjacent rules that carried identical declarations:

```css
/* source */
#wt-root.wt-peek .wt-ui { visibility: hidden; }
#wt-root.wt-peek .wt-grip { visibility: hidden; }

/* lightningcss */
#wt-root.wt-peek .wt-ui, #wt-root.wt-peek .wt-grip { ... }
```

Similarly, an apparent loss of 30-odd declarations was value normalisation, not deletion:
`flex: 0 0 auto` became `flex: none` (7 times), `flex: 1 1 auto` became `flex: auto`,
`flex: 0 1 82px` became `flex: 0 82px`, and all 10 `rgba()` colours became hex-with-alpha. It also
rewrote `::after` to the legacy single-colon `:after` (2 selectors). Correcting my own first reading
here: this is aggressive rewriting, not data loss.

The diff on `fixture.css`, abbreviated to the parts that matter:

```diff
-/* ==========================================================================
-   site.css - hand-written editorial stylesheet
-   ========================================================================== */
-
 :root {
-  --ink:        #1a1a1a;
+  --ink: #1a1a1a;
...
 body {
-  margin: 0;
   color: var(--ink);
   background: var(--paper);
-  font-family: "Iowan Old Style", Georgia, serif;
+  margin: 0;
+  font-family: Iowan Old Style, Georgia, serif;
   line-height: 1.6;
 }
...
 .hero {
-	padding: 32px 24px;          /* tab-indented on purpose */
-	background: var(--paper);
-	border-bottom: 2px solid var(--accent);
+  background: var(--paper);
+  border-bottom: 2px solid var(--accent);
+  padding: 32px 24px;
 }
...
-  @media (min-width: 900px) {
+  @media (width >= 900px) {
```

Four behaviours here are load-bearing against `reconcile/SKILL.md`:

1. **Declarations are reordered.** `body`'s `margin: 0` moved from first to third, `.hero`'s
   `padding` moved from first to last, `.byline`'s `letter-spacing` moved above `line-height`. This
   is unconditional - it still happened with explicit legacy targets set. `reconcile/SKILL.md` says
   "**Key order is cascade order and must be preserved**" and describes a patch where
   `{"padding-top": "40px", "padding": "12px"}` renders differently if reordered. A serialiser that
   reorders is directly at odds with that.
2. **`@media` condition text is rewritten**, in blocks the edit never touched. `(min-width: 900px)`
   became `(width >= 900px)`; `(max-width: 600px)` became `(width <= 600px)`; `@container card
   (min-width: 400px)` became `(width >= 400px)`. `reconcile/SKILL.md` rule 1 says to "**Write the
   block's existing condition text when you merge; do not rewrite it**". Setting explicit legacy
   targets (`{ chrome: 80, safari: 13, firefox: 78 }`) does restore `max-width: 600px`, so this one
   is controllable - but it makes correct output depend on a targets configuration that has nothing
   to do with the edit.
3. **All comments are dropped, unconditionally.** 0 of 10 on `fixture.css`, 0 of 79 on
   `overlay.css`, 0 of 10 even with legacy targets set.
4. **`@charset "utf-8";` is removed entirely** (verified absent from the `hard.css` output). Given
   CONTEXT.md's decision that non-UTF-8 pages are served byte-for-byte under their own declared
   charset, silently deleting a stylesheet's charset declaration is a hazard specific to this
   project. `.m {}`, an empty rule, is also removed.

lightningcss is doing exactly what it is built to do. It is a compiler and minifier, and none of
this is a bug in it. It is a mismatch with the job.

### Malformed input

Recovers silently, same as css-tree: the unclosed `@media` fixture came back with `.b` nested inside
the media block.

### Vendorability: no

This is the clearest single finding in the report. lightningcss is a Rust crate compiled to a
platform-specific Node native addon. There is no single JS file to copy. Shipping it the way
`interact.min.js` is shipped would mean either committing a 9.6 MB binary that works on one
platform, or committing all eleven (a quoted 10,048,780 B each from the registry for the linux-x64
one alone).

The WASM route does not rescue it either: `lightningcss-wasm` 1.33.0 is a quoted **16,232,340 B
unpacked**, MPL-2.0, with its own dependency on `napi-wasm`. That is larger than the native package,
not smaller. **Not measured**: I did not install or execute `lightningcss-wasm`, only read its
registry metadata, so I cannot report its runtime behaviour or actual on-disk footprint.

---

## Hand-rolled tokeniser

No source to cite. What follows is measured against an implementation written for this ticket.

### What a writer must actually understand

To fold one declaration into the rule already governing an element, inside an `@media` block that
already exists, the minimum is:

1. **A block scanner that tracks brace depth** and does not count braces inside strings, comments,
   or unquoted `url()` values.
2. **An at-rule stack**, because the target rule's meaning depends on its ancestors. `.hero` inside
   `@media (max-width: 600px)` and `.hero` inside `@supports` inside that same `@media` are
   different cascade positions, and `fixture.css` contains both.
3. **Condition normalisation** on `@media` preludes, case- and whitespace-insensitive, per
   `reconcile/SKILL.md` rule 1.
4. **Selector-list splitting on top-level commas only**, so a comma inside `:not(...)` or inside an
   attribute selector string does not split a selector in half.
5. **Comment position handling everywhere**, which is the part that turns out to dominate.

### The measurement

I wrote that scanner: 101 lines, 77 excluding blanks and comments. It handles strings, block
comments, unquoted `url()`, brace nesting, an ancestor stack, and paren-aware selector-list
splitting. It is not a strawman - it is more careful than a first draft.

**It succeeded at the headline task.** Folding `letter-spacing` into the `h1` rule inside
`@media (max-width:600px)` worked on `fixture.css`, and worked again on the minified single-line
version. If that were the whole job, 77 lines would be enough.

**It failed five other ways on the same two files.** Each of these is a measured result, with the
postcss behaviour on the identical input alongside.

#### 1. A comment above a rule makes the rule unfindable

The scanner records everything between the previous `}` and the next `{` as the prelude. A comment
sitting above a rule therefore becomes part of its selector.

```
selector ":root"   -> exact matches: 0     (postcss: 1)
selector "body"    -> exact matches: 0     (postcss: 1)
selector ".byline" -> exact matches: 0     (postcss: 1)
```

The recorded prelude for `:root` is:

```
"/* ===================================================================\n   site.css - hand-written editorial stylesheet\n   =========== */\n\n:root"
```

Three of the five top-level rules in an ordinary hand-written stylesheet are unfindable by selector.
This is the single largest failure and it is not exotic - a section comment above a rule is how
people write CSS. Stripping comments before scanning fixes lookup and breaks the promise of writing
back into the file unharmed, so the scanner would need to strip for matching and keep the offsets
for splicing: two passes over the same bytes, kept in sync.

#### 2. Nested at-rules produce ambiguous targets

Inside `@media (max-width:600px)`, a descendant search for `.hero` returns two hits: the depth-1
rule, and the one inside the nested `@supports (backdrop-filter: blur(4px))`. Those are different
cascade positions. Distinguishing them means tracking depth *and* the ancestor chain, and then
deciding which one the patch meant. postcss exposes `atrule.each()` for direct children, which
answers this in one call.

#### 3. `@supports` in the ancestor chain is a second axis

`fixture.css` contains `@supports` wrapping `@media` (at the top level) and `@media` wrapping
`@supports` (in the mobile block). A writer that only models "base or media" has no place to put the
answer to "which `.layout` rule governs this element at 900px when `display: grid` is supported".

#### 4. A comment inside an `@media` prelude defeats condition matching

`hard.css` contains `@media/*in prelude*/ screen and (max-width:600px)`. The scanner records the
prelude with the comment embedded, so the normalised comparison against `(max-width: 600px)` does
not match. postcss reads `params` as the clean `screen and (max-width:600px)` and parks the comment
in `raws.afterName`.

The consequence is precisely the one `reconcile/SKILL.md` rule 1 exists to prevent: concluding the
page has no block for that condition, and opening a duplicate one.

#### 5. A custom property containing braces creates a phantom block

`hard.css` contains `.g{--raw: { this is not css };}`, which is legal - custom properties accept an
arbitrary balanced token stream. The scanner produced a spurious block with the prelude `--raw:`:
19 blocks scanned where 18 are real (14 rules plus 4 at-rules). postcss parses it as a declaration
with the value `{ this is not css }` and reports 14 rules, no phantom.

#### 6. CSS nesting puts the insertion point in the wrong place

`.nest { color: red; & .child { color: blue; } }`. The scanner's "splice before the closing brace"
strategy lands the new declaration **after** the nested rule. postcss reads the children as
`decl:color , rule:& .child`, so the position before the nested rule is addressable.

### Cases the hand-rolled scanner handled correctly

Stated for balance, all measured on `hard.css`: `@charset` and `@import ... layer()` passed through;
the string `"a}b;c{"` did not break brace tracking; the data URI containing `{}` did not break brace
tracking; `@layer` and `@container` were scanned as ordinary at-rule blocks; the empty rule `.m {}`
survived; and the minified single-line stylesheet was scanned and edited correctly.

### Honest estimate

The five failures above are each individually fixable, and none is deep. The concerning property is
that all five were found by running 77 lines against two small files written in a single sitting,
which suggests the list is a floor rather than a ceiling. A hand-rolled writer would also need
tests, and the fixtures those tests need are exactly the fixtures used here plus the ones nobody has
thought of yet.

Not measured, and worth naming as a gap: I did not attempt to *fix* the 77-line scanner and measure
what a correct version costs in lines. That number would be the useful one for a build-vs-buy
comparison, and this report does not have it.

---

## Gaps and things not measured

- **Performance.** No parse or serialise timings were taken for any option. The ticket did not ask
  and no benchmark harness was built.
- **Platform coverage.** All measurements are Linux x86_64. lightningcss's install size in
  particular is per-platform; the 10,048,780 B is the `linux-x64-gnu` binary specifically. macOS and
  Windows figures are not measured, only the registry's list of eleven variants.
- **`lightningcss-wasm` runtime behaviour.** Registry metadata only (16,232,340 B unpacked,
  MPL-2.0). Never installed or executed.
- **css-tree's lexer through the dist bundle.** The standalone verification covered `parse`,
  `generate` and `walk` only.
- **postcss plugin ecosystem.** Not surveyed. Only the core parse-and-stringify path was measured,
  which is the only part a deterministic writer would use.
- **Behaviour on non-UTF-8 stylesheets.** All fixtures are UTF-8. Given CONTEXT.md's decision that
  non-UTF-8 pages are served byte-for-byte, how each parser handles a windows-1252 stylesheet is a
  real open question and is not answered here. The lightningcss `@charset` deletion above is the
  only signal in this report that touches it.

## Reproducing

Every script lives under `/tmp/csspm/` on the machine this was run on and is not committed. The
shape is: `npm install --prefix /tmp/csspm/iso-<pkg> <pkg>`, `du -sb .../node_modules`, then a
per-library script that reads a fixture, round-trips it, compares with `===`, writes the output, and
runs `diff -u`. The five fixtures are described under Method and are reproducible from that
description.
