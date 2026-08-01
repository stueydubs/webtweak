# Changelog

All notable changes to webtweak are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Shapes turn in 45° steps.** A new Rotate control in the Shape group offers the
  eight orientations a decorative shape actually wants. An arbitrary angle would be
  one more value to nudge by eye when nothing else on the page sits at 37°.
- **Drag on the page to draw a shape at the size you want**, instead of dropping one
  at a default size and resizing it afterwards. A plain click still drops a default.
- **The Overlay discovers the page's own breakpoints** and a Scope picker in the bar
  says which one you are editing at, defaulting to the narrowest that matches your
  window. Conditions that cannot be previewed by resizing (`print`,
  `prefers-color-scheme`) are listed as unavailable with the reason, and a manual
  entry covers a stylesheet the browser will not let us read.
- **A banded edit now previews and records against the picker.** Pick a band, edit a
  plain field (Type, Colour, Box), and the change applies only inside that band - drag
  your window out of it and the page reverts to base, exactly as it will once
  reconciled. The Patch gains a `media` map sibling to `changes`, one group per
  condition; a patch carrying no band stays byte-identical to what every release
  before this one wrote. Undo, the change list, and revert are all band-aware, so a
  base edit and a banded edit of the same property never overwrite one another. See
  ADR-0004. Border, per-side spacing, and every control on a shape stay base-only for
  now (`controlBand()`) - a banded border, padding, or shape fill is not yet
  expressible, and each is refused at the point it would otherwise be recorded,
  not merely documented as unsupported. Declined out loud, too, per ADR-0004's own
  principle: the properties panel's scope note says "Border and spacing always apply
  at every width" (or the Shape equivalent) whenever a band is selected on an
  element carrying one of these controls, rather than silently ignoring the band it
  is still visibly showing.
- **The reconcile skill is told how to merge a banded edit into the page's own
  media queries.** A patch's `media` map goes into the `@media` block that already
  governs that condition - never a duplicate block for a condition the stylesheet
  already has, and existing `@media` blocks are never reordered, since media order
  is cascade order. A block is created only when the page genuinely has none for
  that condition, and the condition the user picked is intent, not a suggestion to
  round to a nearby breakpoint the site uses elsewhere. The wide-viewport
  responsiveness warning is now asked per declaration rather than per patch, since
  one patch routinely carries an un-banded resize alongside an unrelated banded
  edit. `wtreconcile.py`'s pending-batch summary surfaces each patch's media groups
  (condition + properties) instead of showing only `changes`, so a media-only patch
  no longer reads as a no-op. On a patch carrying both it also appends `base-only:
  <props>`, naming the base declarations no band covers - the set difference step 6
  needs is mechanical, and leaving it to be re-derived by eye is what read the rule
  at the wrong granularity once already. And it flags a `create` patch carrying
  `media`, which has no way to carry a band and so cannot have come from webtweak:
  `media?!` inline in the summary, plus a stderr warning in both modes, since
  `--full` dumps patches verbatim and is the path the skill sends Claude to for real
  work. A condition is quoted in that summary when it holds the summary's own
  delimiters (`;` or `[]`, both of which survive inside parens per CSS MQ4
  `<general-enclosed>`) or is blank - unquoted, one group could print as two, with a
  property list that was never there.
- **Drag a margin or padding box up and down to change it.** Spacing is tuned by eye
  against the page rather than by typing a figure, so the four boxes take a vertical
  drag - up adds, down subtracts, one CSS unit per pixel, the unit preserved. Typing
  still works: the drag only takes over once the pointer has travelled 3px, so a plain
  click still lands a caret. A whole drag is one Ctrl+Z, not one per pointermove.
  Padding stops at zero; margin does not, because a negative margin is a real
  technique. A box showing `auto` is left alone rather than turned into a number
  nobody asked for - that one silently kills a centred block.
- **Reset all, in the bar.** Discarding a session meant selecting each edited element
  and resetting it one at a time, with the change list the only place that said which
  ones they were. The button is disabled until there is something to discard
  (selecting an element arms a baseline entry, which does not count), and the whole
  reset is a single undo step - deliberately no confirm dialog, because the undo IS
  the safety net and a modal would block every Overlay event behind it. It is the
  eleventh control on a bar sized for ten, so below 620px it sheds its second word
  (`Reset`, with the full meaning kept in the button's title) and every bar button
  gives up some padding - the same shortened-never-removed treatment the scope label
  already had. The bar itself now wraps rather than relying on that shed alone; see
  Fixed, below.

- **A band you typed by hand survives a reload.** `pageConditions()` re-derives itself
  from the page's stylesheets on every call, so a condition the CSS does not declare
  lives only in memory - and `restore()` re-applied such an edit without re-registering
  its band. The edit came back and still previewed correctly, but its band was gone
  from the Scope picker, so there was no way to return to it and revert it short of
  retyping the exact condition. Both routes to a hand-typed condition now go through
  one `rememberBand()`.

### Changed

- **The shape palette is six kinds, not nine.** `rectangle` and `ellipse` were a wide
  square and a wide circle - the same geometry at a different default size, which
  stopped meaning anything once you could drag one to size. `diamond` was a square at
  45°, now the Rotate control. A saved edits file naming a retired kind still draws
  itself correctly: a create patch carries its own geometry and never depended on the
  shape table.
- Every palette icon is now a distinct picture; square and rectangle had been drawing
  the same one.

### Fixed

- **The alignment buttons read as words.** `L C R J` was an abbreviation you had to
  decode, crammed into the right-hand corner of a row that was otherwise empty: the
  control was sizing to its content while the row's `space-between` pushed it there.
  `.wt-align` now claims the row the way `.wt-colour` and `.wt-sides` already did, and
  the buttons say Left, Centre, Right and Justify. A test asserts none of the four is
  clipped, since four words in one row is tight by design.
- The browser test suite genuinely runs locally now. It had been skipping one line per
  module - which reads green - because Playwright was never installed. See the
  README's Development section, and check the skip count rather than the colour.
- **A long status message could push Save off the right edge of the window at a
  narrow width.** The status column never shrank (`flex-shrink: 0`, like every other
  bar control, to stop it overlapping a clickable one) and never wrapped or
  truncated either, so a message like "reset - save to drop these edits" held the
  bar at its own full width and pushed later buttons past the viewport - at exactly
  the widths band editing exists to be used at. Status has nothing clickable in it,
  so it is now the one control that shrinks, with an ellipsis for whatever doesn't
  fit; the `.wt-status { min-width: 0 }` narrow-window rule this reactivates had
  been dead code since the flex-shrink hardening, doing nothing at any width.
- **Save could sit outside the window, unclickable, once anything had been saved.**
  The reconcile badge appears only after a save, and the 68px it takes was enough to
  push Save past the right edge - 65px past, at 480px. It went unseen because the
  test guarding this had filtered out anything `hidden`, which the badge is until the
  moment it matters, and because no test had saved at a narrow width and then gone
  back to *Save* - one had gone back to the bar, but to a control sitting left of the
  badge, where nothing was wrong. The badge was not the real fault: the bar had been pushed
  past its own width three times, each time answered by shortening a label, and by
  480px the eight controls needed 472 of the 480 before the badge had any width at
  all. There was no shed left to make, and the overflow was never confined to narrow
  windows either - the longest badge text pushed Save out at 640px and 820px too. So
  **the bar wraps now**, at every width, and keeps its labels. Its height is
  therefore a rendered fact rather than a constant, so the Overlay measures it and
  publishes `--wt-bar-h`, which the panel and the place-hint position against -
  replacing two `top: 56px` rules and a `calc(100vh - 72px)` that encoded the same
  guess in three places, none of which knew about the others. The status line gets
  `flex-basis: 0` at narrow widths so a long message fills what is left of its row
  instead of claiming a whole one. Two tests now assert the invariants directly, at
  ten widths each, with the badge showing and every control live: nothing the bar
  shows may fall outside the bar's box, and the panel must clear the bar.
- **A saved edit could be destroyed by editing the same element again.** When a
  reload cannot confirm an element is the one a patch was recorded against - the
  page's own copy changed, say - the patch is stranded and kept for reconcile rather
  than mis-applied. If the user then edited that same element, `save()` dropped the
  stranded patch entirely, on the rule that the fresh patch supersedes it. That is
  true per declaration and false per patch: `changes` and `media` are independent
  per-property maps, so everything the fresh patch happened not to set went with it,
  silently, having just been reported as "kept for reconcile" in the status line. A
  stranded colour and a whole banded group both vanished on one keystroke. Fresh
  values still win; only the declarations nobody re-authored are carried over, into a
  new map rather than into the session's own - `save()` passes those maps through by
  reference, so merging in place would have left the session holding declarations that
  were never applied to the page. This is the same wrong-granularity mistake
  reconcile's step 6 made - anything that asks a question of a whole patch asks it
  too coarsely.
- **A created shape could be erased from the edits file by a reload.** Reconcile writes
  source first and marks the batch second, so there is a window where the shape is
  already in the served page while the batch is still pending. Reload in it and
  `restore()` found the id present, correctly declined to inject a second copy - and
  then recorded the patch nowhere. A save replaces this session's whole batch, so the
  next one dropped the only description of the shape, its geometry and its style, while
  reporting a clean save. It is now kept for the next save, like every other patch
  restore cannot re-apply.
- **Edits kept for reconcile are visible, and Reset all discards them.** A patch whose
  element cannot be confirmed after a reload is preserved rather than mis-applied - but
  it is deliberately not applied to the page either, so nothing showed it: not the page,
  not the panel, not the change list. It still reached reconcile, merged into whatever
  patch was saved next for the same element. They now appear in the change list as their
  own dimmed rows, marked "kept for reconcile", and **Reset all** drops them - the only
  control that can, since a patch with no element on the page is one every per-element
  revert walks straight past. That part of a reset is not undoable and the status line
  says so.
- **An open bar dropdown could be left behind when the bar grew.** The shape palette and
  the band picker are positioned against the bar's bottom, which was computed once when
  they opened and refreshed only on scroll or resize. The bar also grows for reasons
  that are neither - the reconcile badge appearing on a source-change event is enough -
  leaving the dropdown over the row that had just appeared beneath it, taking its
  clicks. The measurement that notices the height changed now says so.
- **On a short window a dropdown could still be pulled up over the bar.** Anchoring to
  the bar's bottom only fed the drop-below branch; the flip-above fallback and the
  viewport clamp both still read the toggle's own rect, so at 360x280 the band picker
  landed across the bar's own rows. Nothing in the bar may now be placed above the
  bar's bottom, and a list with no room below scrolls instead of flipping.
- **Both of the bar's dropdowns covered its controls once the bar wrapped.** The shape
  palette and the band picker each hang off a button that, on a wrapped bar, can sit on
  a middle row - and each is positioned inside the bar's own stacking context, so
  neither merely overlapped the controls beneath it, they took their clicks. Measured at
  360px: Reset all and Deselect could not be clicked while the palette was open. Both
  now drop below the whole bar, which is where a one-row bar was already putting them.
  Two fixes, because the palette is statically positioned and can be moved by a rule
  while the picker's coordinates are inline styles no rule can beat - so the palette
  moved in CSS and the picker in `placeSuggest`, which now anchors to the bar for any
  toggle inside it. The picker was missed on the first pass and found only by asking
  what else drops out of the bar; the regression test covers both, for that reason.
- **The change list's own collapse header could sit under the bar.** `.wt-dock` was a
  fourth place the 44px bar height was hardcoded, and the one missed when the panel
  and the place-hint were converted to `--wt-bar-h`. On a short window with a full
  list, the header rendered under a wrapped bar - visible, and unclickable.
- **The opening tag in a Fingerprint could leak an Overlay-generated class.**
  `openTag()` read `class` straight off the DOM instead of through `nonWtClasses()`
  the way `selector` already does, so a shape's `wt-shape` class (and now a banded
  edit's generated `wt-mq-N`) was reaching Claude as though the page had authored
  it. Fixed to rebuild `class` the same way the rest of the Fingerprint does.

The four below were found by a dynamic-team review of the banded-editing commit
(five parallel reviewers, each Codex-verified against the running code) and fixed
the same session, before any of them shipped to a tagged release:

- **A border edit made while a band was selected recorded into `media` instead of
  `changes`**, contradicting this release's own documented scoping. `writeBorder()`
  ends in the same shared `commit()` tail as every plain control, which read the
  Scope picker's band unconditionally; reconcile does not read `media` yet, so the
  edit previewed and saved but was silently unreachable from real source. Fixed by
  routing every band-aware function (`commit`, `populate`, the revert marks) through
  a `controlBand(c)` that forces base for a composed border, per-side spacing, or
  any control on a shape - one place all of them now agree with, instead of each
  re-deriving it and drifting apart.
- **A banded edit on a shape (fill, stroke, rotate, ...) was recorded and shown in
  the change list, then silently dropped on save** - the shape branch of `save()`
  only ever read `e.changes`, never `e.media`. Closed at the source by the same
  `controlBand()` fix above: a shape control now always writes base, so there is
  nothing for that branch to have dropped.
- **Two bands sharing a min-width but no max-width (e.g. two ordinary mobile-first
  breakpoints) could win the cascade in the wrong order.** `Infinity - anything` is
  `Infinity` in IEEE754, so `makeBand()`'s span collapsed every such band to the
  identical value and the "narrowest wins" sort saw `NaN` for any pair of them -
  which a stable sort treats as equal, silently falling back to edit order instead
  of width order. Fixed with a large finite sentinel in place of `Infinity`, so two
  min-width-only bands stay distinguishable by their actual threshold.
- **Switching the Scope picker's band left the per-field revert dot stale.**
  `setScope()` repopulated each field's shown value for the new band but never
  refreshed the revert marks, so a dot could keep showing (or hiding) a still-active
  override that belonged to the band you had just left.

## [0.6.0] - 2026-07-30

A panel release: the controls stop making you do arithmetic. Spacing is edited per
side, sizes take any unit, colours show their hex, groups fold away and a single
property can be put back. No change to the Patch contract - `padding-bottom` is just
another property under it - so existing edits files reconcile unchanged.

**Reinstalling the reconcile skill is worth it but not required** (`webtweak
--install-skill`). Nothing this release emits will confuse an older copy; the new
guidance is that sides *absent* from a Patch must be left alone, which is what keeps a
`margin: 0 auto` centring intact.

### Added
- **Margin and padding are edited per side.** They were single text boxes holding a
  four-value shorthand, so changing one side meant reading `30px 168px 0px 168px`,
  doing the arithmetic and retyping the lot. Now there are four boxes on one row - no
  taller than before, because vertical space is the panel's scarce dimension - plus a
  link button for "the same all round", which is the one thing the old box did well.

  Each box takes any unit, and `auto`, so centring is now something you can *set*
  rather than only lose. And only the side you touch is recorded: a Patch says
  `padding-bottom: 40px` instead of all four sides. That removes a real hazard rather
  than just some typing - on a centred block, the old shorthand carried the computed
  px where the source said `auto`, and reconciling it literally killed the centring.
  The reconcile skill is told the sides absent from a Patch must stay untouched.


- **Size, Width and Height take any unit.** They were number inputs, so `2rem`, `80%`
  and `4ch` were not awkward to enter - they were impossible, and the panel quietly
  forced px onto layouts that were authored fluid. They are stepper fields now, showing
  their unit and keeping it when you use the arrows. A bare number still means px, so
  the common case is unchanged.

  Two things followed from that. The invalid-value gate now applies to these fields: it
  used to be skipped on the grounds that a number input can only hold a number, which
  stopped being true. And the revert check now compares the value about to be *written*
  rather than what you typed - with a unit in the baseline, a bare `44` had to become
  `44px` before it could be recognised as putting a 44px size back.
- **Colours show their hex.** A bare colour swatch is a rectangle and nothing else:
  you could not read what colour an element already was, and you could not paste a
  brand hex into it without going through the OS picker. Every swatch - Text,
  Background, the border Colour, a shape's Fill and Stroke - now has an editable hex
  beside it, and the two stay in step whichever one you use. It takes a hex with or
  without the `#`, and a half-typed one stays quiet rather than warning on every
  second keystroke about a value you are still typing.
- **Groups fold, and a single property can be undone.** Two navigation problems rather
  than styling ones. The panel is around 780px of content, so it scrolls on any window
  shorter than about 800px and a group you are not using costs you the one you are -
  every heading now collapses, and stays collapsed as you click between elements,
  because that is panel state and not something to redo on every selection. And an
  edited row now shows a small × beside its label that puts just that property back:
  before this, undoing one property meant knowing that clearing its field did that,
  which nothing on screen suggested. It goes through the undo stack like any other
  change, so the revert is itself undoable.## [0.5.0] - 2026-07-30

A small release from using the tool: the last two bare text boxes in the Type group
get proper controls, and three things found by driving the overlay in a real browser
get fixed. No change to the Patch contract or the Edits file format, and **no need to
reinstall the reconcile skill** - this release emits nothing it did not emit before.

### Added
- **Line and Spacing stopped being bare text boxes.** Both were fields you typed a
  value into from memory, which is the same complaint that produced the font picker.
  Line now has up/down arrows, so a leading you are judging by eye can be walked 0.1
  at a time; Spacing has a ▾ of tracking presets in em, from tightened display type
  to opened-up uppercase labels.

  Both stay text inputs, and deliberately so. A number input could hold none of
  `normal`, `1.4em` or `24px`, and a closed dropdown of presets could not hold an
  arbitrary tracking value - each would have removed an edit that already worked. The
  arrows handle the awkward cases instead: they keep whatever unit they were given, and
  on a `line-height: normal` they measure what the browser is actually rendering (it is
  font dependent, and does not even compute to a length) before stepping it, so the
  first press does something rather than nothing.

### Fixed
- **A rejected value no longer warns forever.** The status line has no timer, so
  `ignored invalid margin: banana` sat there through every later successful edit,
  reading as current long after it stopped being true. Any recorded edit - or
  abandoning one - now supersedes it.
- **A declined control refuses a write from any direction.** Disabling an input stops
  a mouse and a keyboard, which is all you have, but the guard exists to stop a Patch
  your element will not honour from being recorded at all - so the write path refuses
  too, rather than trusting the attribute.
- The session change list no longer leaves its header reading "1 element changed"
  after the last change is reverted. The list itself was correctly hidden, so this was
  never visible - but it is the panel's own account of your session, and it was wrong.

## [0.4.0] - 2026-07-30

A property-set and quality-of-life release for the Overlay: a font picker fed by
the Target page's own fonts, a Border group (border, corner radius, shadow) for
existing elements, and redo. No change to the Patch contract, the Edits file
format, or ADR-0001 - your existing edits files still reconcile the same way.

**Upgrading: reinstall the bundled Reconcile skill** with `webtweak
--install-skill`. Your installed copy predates this release, so it does not know
about `border`, `border-radius` or `box-shadow` - and in particular it does not
know that a per-side `border-bottom` must never be normalised into an all-sides
`border`, which would turn a heading's rule into a box.

### Added
- **Existing elements can have a border.** A decorative shape could have one and
  the card beside it could not, which read as a bug rather than a scope boundary.
  A Border group joins the panel with Width, Style, Colour and corner Radius,
  hidden for shapes the way typography and colour already are.

  The three border controls compose **one** `border` declaration, and touching any
  one of them on a border-less element seeds the other two so a border renders
  immediately. Without that, two of the three controls would do nothing visible on
  first use - a colour alone and a width alone both render nothing while the style
  is `none` - and the overlay would still record the value, putting a Patch for an
  invisible change into your source. The seeded colour is your element's own text
  colour, so the swatch was already showing it. Style `none` removes a border and
  records as `border: none`; clearing any field abandons the whole change. See
  [ADR-0003](./docs/adr/0003-compose-shorthands-from-discrete-controls.md).
- **Redo, and visible undo/redo buttons.** Undo was one-way and invisible: stepping
  back too far meant redoing the work by hand, and nothing on screen said undo existed
  or whether anything was left to undo - the only mention was a sentence in the hint
  bar and the only feedback a status line after you had already lost your place. Both
  buttons now sit in the top bar and dim when their stack is empty. `Shift+Cmd/Ctrl+Z`
  and `Ctrl+Y` both redo. Redo covers every kind of change, including restoring a
  shape whose creation you undid, and removing one again whose removal you undid.
  Making a new edit drops the redo trail, so stepping forward can never splice an
  abandoned branch of history into current work.
- **A Shadow field, with presets.** `box-shadow` is the one property here that
  resists discrete controls: building it from parts would need four lengths, a colour
  and an inset flag, and a shadow's colour is almost always translucent while the
  panel's swatch is opaque hex. So it is a text field backed by the same suggestion
  list the Font control uses - a hairline, a card lift, a modal lift, a dramatic drop,
  an inset press, and `none` to remove one. Typing a custom shadow still works.
- **A rule on one side stays a rule.** Bottom borders under headings are everywhere
  on the editorial pages webtweak is for, and composing a four-sided border onto one
  would turn a divider into a box. When exactly one side carries a visible border the
  controls edit *that side*, the group legend names it, and the Patch says
  `border-bottom` - which reconcile is now told never to normalise back to all sides,
  because the side is the intent. When several sides differ the controls switch off
  with an explanation, the same way width and height already switch off on an inline
  element: the overlay declines rather than quietly wrecking a deliberate design.

  **Corner radii work the same way.** A card rounded on its top two corners is a
  deliberate shape, and one value in the Radius field would have rounded all four -
  so an element whose corners differ has that field switched off too, with its own
  explanation. The two guards are independent: an element can have differing corners
  and perfectly ordinary borders, and only Radius is declined.
- **The Font control offers the page's own fonts.** It was the one field that
  demanded you already knew an exact string: to set a heading in the site's
  display face you had to type `Fraunces, Georgia, serif` from memory, fallbacks
  and all, and a typo silently recorded nothing at all. The field now carries a ▾
  listing every distinct font stack in use on the page plus any family it declares
  as `@font-face`, each row previewed in its own face. Picking one writes the whole
  stack, so the fallbacks the page's author intended survive by construction rather
  than by your care. It stays a text input - typing an arbitrary stack still works,
  so a font you are introducing for the first time is not blocked by a list that
  cannot know about it.

  The list is built from computed style, which is the only origin-proof source: a
  page whose display face comes from a CDN-hosted webfont yields nothing readable
  from its stylesheets (`SecurityError`), and that is the common case, not the edge
  case. `@font-face` families are gathered from readable sheets as a supplement, so
  a self-hosted face you have set up but not yet applied anywhere is still one
  click away - and an unreadable sheet degrades the list instead of throwing.

### Fixed
- **A typo no longer deletes the edit you had just made.** An invalid value resolves
  to the element's *current* computed value, which is indistinguishable from setting
  the field back to its original - so mistyping over a margin (or, now, a shadow) you
  had just set silently discarded it instead of being ignored. Values are rejected
  before that comparison, so a typo leaves your work alone and says so.
- **The right-hand shape palette items are clickable again while something is
  selected.** The palette drops out of the top bar into the properties panel's
  column, and the panel painted over it, so three of the nine shapes could not be
  picked at all except with nothing selected.

### Changed
- A shape's controls read **Stroke** and **Stroke width** rather than Border and
  Border width, now that "Border" means a CSS border elsewhere in the same panel.
  Labels only - the properties were always the SVG ones, so nothing changes in a
  Patch or in reconcile. The shape's Radius keeps its name: `rx` and
  `border-radius` are the same concept in the same units.

## [0.3.0] - 2026-07-30

### Security
- **The breadcrumb no longer executes markup from the page you are editing.** It
  was built with `innerHTML` from the element's own tag, id and class names, so
  opening a page from a repo you did not write and clicking an element ran its id
  as HTML - in the overlay's origin, which can POST patches that Claude later
  reconciles into your real source. Now built with `textContent`. The session
  change list added in this release was already safe; the breadcrumb beside it
  never had been.
- **The file watcher can no longer be walked out of the served directory.** Its
  initial scan correctly refuses to follow symlinks, but an `fs.watch` event
  carries only a name, so the child was `stat`ed - and a stat follows links. A
  symlink created while webtweak was running therefore had it watching, and
  reporting filenames from, directories outside the web root.

### Added
- **The loop closes in the browser.** webtweak now watches the files it serves
  and pushes an event when the source under the page changes, so a reconcile
  lands visibly: the page reloads itself and you watch your drag become real
  CSS. Previously the hand-off was blind - you saved, switched to Claude, and
  had no signal at all until you reloaded by hand.
  - A **reconcile badge** in the bar reads `N pending` after a save and
    `reconciled` once Claude has folded the batch into source.
  - A live reload **never runs over unsaved edits**. With unsaved work the badge
    offers the reload instead of taking it.
  - webtweak's own temp and backup files are excluded from the watch, so saving
    cannot bounce the page you are still editing. The edits file itself *is*
    watched, as its own event - reconcile marks a batch by touching only that
    file, so without it the badge could never reach `reconciled`.
- **`--root DIR`** serves an explicit web root instead of the page's own folder,
  so a page in a subfolder can resolve root-absolute assets (`/css/site.css`).
  Previously unsupported, which ruled out most real sites. The edits file still
  lands beside the page, not in the root.
- **Session change list** - a collapsible "N elements changed" panel listing
  every element you have touched and what changed on it; click an entry to
  select and scroll to it. `edited` held the whole session but the properties
  panel only ever showed one element, so reviewing meant saving and opening the
  JSON.

### Changed
- The save confirmation names the edits file it wrote, which teaches the
  hand-off for free.
- The panel note no longer reads as though saving invokes Claude. Save writes a
  file; reconcile is a separate step you ask for.
- `--help` documents `--root`; the opened URL is percent-encoded, so a folder
  named `my blog` or `a#b` no longer produces a link that 404s.

### Fixed
All of the below are in the live-reload machinery added above, found by review
before release rather than in use.
- **A reload can never discard your session.** Every safety check now fails
  closed. Deleting or reverting the edits file - `git checkout .` in your site
  repo, which is an ordinary thing to do since the file is meant to be committed
  there - used to read as "already reconciled" and trigger a reload that threw
  the session away. It now says `edits file gone` and leaves your edits on screen
  so you can re-save them.
- A reload only happens on the *transition* to reconciled, and only for **your**
  session's batch. Another session's batch being marked no longer yanks the page
  out from under you mid-review.
- A save no longer silently dismisses a `source changed - reload` warning. The
  source is still stale and nothing else will raise it again, so the decision is
  re-run instead of dropped.
- The badge cannot get stuck. It used to latch on `reconciling...` for the rest
  of the session whenever reconcile deliberately left a batch pending (which it
  is instructed to do when a patch needs your answer), with no way out.
- The green `reconciled` badge clears the moment you start editing again, instead
  of reading as "already in source" over unsaved work.
- No reload during an in-flight save, and the unsaved-changes prompt stays honest
  for that window - previously both treated the page as saved before the write
  had landed.
- A page in a very deep directory, or a very large tree, now says that live
  reload is partly off rather than silently never firing.
- The change list keeps its scroll position: rows are rebuilt only when they
  actually change, not on every click and keystroke.

## [0.2.0] - 2026-07-29

### Security
- The save endpoint now rejects cross-origin writes. Any page open in the same
  browser could previously POST to webtweak's (fixed, guessable) port and write
  a batch into the edits file - which Claude then reads as instructions during
  reconcile, so an unauthenticated write reached real source. Saves now require a
  same-origin `Origin` (or none, for a non-browser client) and
  `Content-Type: application/json`; `text/plain` was a CORS *simple* request no
  preflight could stop.
- A forged `Host` header is now rejected, closing a DNS-rebinding path that made
  the served directory readable by an attacker-controlled page.
- Symlinks can no longer escape the served directory. The traversal guard resolved
  `..` correctly but did not resolve symlinks, so a link inside your site folder
  served any file on disk.

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
- **Clearing a field now reverts that change** instead of doing nothing. Typing a
  value and then emptying the box left the abandoned value recorded, so it shipped
  to Claude and got written into your real source.
- **The selection no longer jumps after a drag.** Every nudge or resize was
  followed by a browser click that re-selected whichever child sat under the
  cursor, so the grips silently moved to an element you never chose and the next
  resize targeted the wrong thing.
- **Reset is undoable.** It recorded no undo step, so on a shape it was an
  unrecoverable delete, and on any element it discarded every edit with no way back.
- Undoing past a Reset no longer resurrects the deleted element as a phantom
  patch carrying a fingerprint computed on a detached node.
- A directory URL now serves its `index.html` instead of 404ing, so root-relative
  nav links (`href="/"`) work. Directory listings stay off.
- The overlay is only injected into the page you opened. Following a nav link
  previously gave you a fully functional editor pointed at the wrong page, whose
  saves landed in the original page's edits file with mismatched fingerprints.
- The overlay UI mounts on `<html>` rather than `<body>`, so a page with
  `body { transform: scale(...) }` (A4/print layouts) no longer renders the whole
  editor scaled and mis-anchored.
- A page's own `wt-`prefixed classes are no longer stripped from the fingerprint;
  only webtweak's own `wt-shape` class is.
- If a corrupt edits file cannot be backed up, the save now fails loudly instead
  of overwriting the only copy while logging that a backup was taken. Backups are
  capped at the newest 3.
- `--version` works; `--port` validates its range instead of crashing with a raw
  Node stack trace; `--port=N` is accepted; a directory argument says so; passing
  two pages is an error rather than silently using the last.
- The reconcile helper writes UTF-8 rather than `\u` escapes, matching the server,
  so marking a batch no longer rewrites every non-ASCII character in your repo.

### Changed
- `--help` now documents every flag, the loop, and the Python 3 requirement.
- New `--install-skill` flag copies the bundled reconcile skill into
  `~/.claude/skills/`, which works identically for a clone, a global install and
  npx. Previously only a git clone had a documented path.
- Static files stream rather than being read whole, and `Range` requests are
  supported - a large asset no longer blocks the single-threaded server, and
  `<video>` plays in Safari and on iOS.
- Added MIME types for `.webmanifest`, `.map`, `.mp3`, `.ogg`, `.wasm`, `.csv`
  and `.jsonld`, which previously loaded as `application/octet-stream`.
- Startup reports any batches left unreconciled from a previous session.
- `reconcile/scripts/wtreconcile.py` is executable, as the skill's own
  instructions assume. It previously failed with `Permission denied` for everyone.
- The reconcile skill now covers the zero-match case, fingerprint truncation, and
  a verification pass; it requires every patch to be accounted for before a batch
  is marked, so a skipped patch can no longer be silently retired. Its nudge
  guidance is corrected: small offsets are intent, never drag jitter, and
  `position: relative` is an acceptable clean form.

### Removed
- The parallel Python implementation (`webtweak.py`). The unit tests asserted
  against it while users ran `webtweak.js`, so two deliberately broken invariants
  in the shipped code - including "a reconciled batch is never modified" - left the
  suite fully green. The tests now drive `webtweak.js` itself, and CI runs them
  across Node 18/20/22/24 plus a dedicated browser job where Playwright is always
  installed (its 31 e2e tests previously collapsed into one silent skip line).

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

[Unreleased]: https://github.com/stueydubs/webtweak/compare/v0.6.0...HEAD
[0.6.0]: https://github.com/stueydubs/webtweak/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/stueydubs/webtweak/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/stueydubs/webtweak/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/stueydubs/webtweak/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/stueydubs/webtweak/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/stueydubs/webtweak/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/stueydubs/webtweak/releases/tag/v0.1.0
