# Roadmap

Rough, and deliberately so. This is a holding place for work that is **not in 1.0**, written down
because the alternative was five capabilities surviving only inside a closed issue's comment.

Everything here comes out of [#15](https://github.com/stueydubs/webtweak/issues/15), which decided
which of Pinegrow's capabilities 1.0 closes and which it does not. The reasoning lives on that
ticket; this file is the index, not the argument.

**Status: this file answers the map's "where the post-1.0 roadmap lives" question by existing.** It
is not itself a decision about what gets built or when. Nothing here is scheduled, estimated, or
promised.

## The rules that govern this file

Four standing rules from the map's Notes ([#1](https://github.com/stueydubs/webtweak/issues/1)).
They matter more than the list below, because they decide what happens to the list.

1. **Nothing is permanently conceded.** Three buckets exist, not four: in 1.0, deferred with a named
   trigger, and roadmap. There is no "never".
2. **A deferral must name what would bring it back**, and it should name a live ticket rather than a
   mood. A deferral with no trigger is a concession nobody has admitted to.
3. **A roadmap feature is turned away if it costs a 1.0 win.** Pinegrow's complaint list is largely
   the bill for its feature list, and the bill is itemised below. Without this rule, 1.0 wins the
   argument and 2.0 loses it back.
4. **1.0 may hedge on file format, never on features.** No machinery in 1.0 for anything on this
   page. But where a cheap format field keeps a door open, take it - a field is reversible and a data
   model is not.

Rules 3 and 4 are opposites on purpose. One stops this file damaging 1.0; the other stops 1.0
quietly killing this file.

## Two principles that decide most requests before they reach this list

Both from #15, both now in the map's Notes:

- **webtweak edits the properties you cannot get right without looking at them.** This is why hover
  is in 1.0 and text editing is not. You cannot guess a hover colour without seeing it; you already
  know what the word should say.
- **webtweak edits one thing you clicked on, not the relationship between things.** This is why
  there is no grid editor and no flex editor, and it will answer the next several requests of that
  shape without re-arguing each one.

## Deferred, with a trigger

These are not roadmap items. They have a named condition that brings them back, and the condition is
a live ticket.

| Item | Trigger | Why |
|---|---|---|
| **Editing text content in place** | [#14](https://github.com/stueydubs/webtweak/issues/14) landing injected identity | `fingerprint()` captures `text` and `ownText` as two of its eight signals, so editing text corrupts the identity every other patch in the batch was built from. Cheap if identity becomes a lookup; hard for as long as it is text matching. |
| **Multi-element parallel structural edits** | [#13](https://github.com/stueydubs/webtweak/issues/13) deciding 1.0 reorders at all | It is a bigger version of moving one thing. If #13 says no, the question does not arise. |

**DOM reordering itself is not on this page.** [#13](https://github.com/stueydubs/webtweak/issues/13)
owns it, and answering it in two places is how a map contradicts itself.

## Roadmap

No trigger. Revisit after 1.0. Ordered roughly by how well the current architecture already
accommodates them, best first.

### Remaining pseudo-states - `:focus`, `:active`, `:visited`

Purely additive once `:hover` ships in 1.0. `:focus` is usually a site-wide accessibility decision
rather than a per-element tweak, which is why it did not make 1.0, but nothing architectural is owed.

### Selector-building tool

1.0 ships the **hint** - where the edited element carries a class, the panel offers "3 other things
on this page look like this. Change all 4?", defaulting to just the one. Pinegrow's full selector
maker builds a selector from the element path, assigns missing classes and picks the target
stylesheet. That machinery was declined because it is a large part of why Pinegrow is hard to learn,
which is a 1.0 win worth protecting (rule 3).

Note the mandatory caveat that comes with the hint and would come with the tool: the count is of
**this page**, but the rule reconcile writes lands in a stylesheet that probably governs the whole
site.

### Element creation from component libraries

Pinegrow drags in Bootstrap, Foundation, Tailwind Blocks, Flowbite and TailwindUI components.
webtweak creates six decorative SVG shapes.

Better positioned than it looks. `CONTEXT.md` records that the shape `create` patch is deliberately
**self-contained** - it carries its own geometry, to the point where restore can rebuild a shape kind
this build has never heard of. That generality is already load-bearing and already tested, so
"insert a pre-built block" is the same op with different contents rather than a new mechanism.

The open question is not the op. It is whether someone with a hand-coded editorial site wants a
Bootstrap navbar dropped into it at all.

### Visual CSS Grid editor

Excluded by the second principle above rather than by effort. Every control webtweak has edits one
element you pointed at. A grid editor edits the relationship between a container and its children,
which is a different interaction model with a different selection model. It is not a bigger
properties panel, it is a second product.

`CONTEXT.md` already excluded flex and grid alignment editors by decision, so this confirms an
existing position rather than taking a new one.

### Components, master pages and editable areas

"Change the footer once, it changes on 40 pages."

**This is the only item on the page that constrains 1.0**, and it is why rule 4 exists. Project-wide
propagation needs webtweak to reason about a whole Project at once, and
[#9](https://github.com/stueydubs/webtweak/issues/9) decides whether the edits file is one per page
or one per Project. Per-page is the cheap answer, is what 0.8.x already does, and will look obviously
correct when #9 is worked - which makes it a hazard rather than a trade-off, because 1.0 would ship
with every check passing and this item quietly turned into a rewrite.

The hedge is a field, not a feature: whichever way #9 goes, a Batch should record the page it belongs
to as a Project-relative path. Noted on #9 itself, because #9 sits three levels deep behind
[#19](https://github.com/stueydubs/webtweak/issues/19) and
[#5](https://github.com/stueydubs/webtweak/issues/5).

## What is on this page because of who 1.0 is for

1.0 targets **a developer who already has Claude Code and does not want to leave the browser for
small visual changes.** The pain removed is the guess-a-value, save, alt-tab, refresh loop.

Every roadmap item above is about **building or restructuring a page**. That user already has tools
for that - their editor, and Claude. What they do not have is a way to see a colour or a spacing
while they change it. That is the product, and it is why this page is as long as it is.

## The 1.0 wins this page is subordinate to

Rule 3 turns a feature away if it costs one of these. Most arrive free from webtweak being a website
rather than an NWJS desktop app; the point of listing them is that the roadmap above is roughly the
feature list that cost Pinegrow each one.

| Win | Pinegrow's position |
|---|---|
| Never reformats hand-written code | Ten forum threads, 2017 to 2026; staff confirmed February 2026 that a fix is not planned |
| Does not crash or lose hours of work | Continuous reports 2017 to June 2026, largely the NWJS desktop wrapper |
| Nothing to learn | Steep learning curve is its most-cited criticism; prompted a full workspace redesign in Pinegrow 9 |
| Nothing to install | No AppImage; an unofficial and outdated Flathub build |
| Class lists cannot go stale | Theirs shows every class ever used, including deleted ones |
| Free and MIT | Paid add-ons, and a recurring complaint about the packaging of plans |

**Two of these are not free and need build-failing tests rather than intentions:**

- **Undo.** Reported broken on their side since 2014. webtweak's is structurally easier because it
  only ever undoes unsaved Overlay patches and never touches files. Easier is not done.
- **Not reformatting the file.** Won for free on the *capture* half only. Reconcile does rewrite CSS.
  [#4](https://github.com/stueydubs/webtweak/issues/4) measured postcss round-tripping this repo's own
  `overlay/overlay.css` byte-identically, 139 rules and 79 comments intact. That has to become a test
  that fails the build, or it is the same promise Pinegrow made and broke.

**One is unproven in either direction:** support responsiveness. Their small team against one person,
and a solo operator with AI triage may well answer faster than a small team does. Recorded as unknown
rather than as a known loss.

## Not on this page, and not coming back to it

From the map's **Out of scope**, which is a different thing from this roadmap. Out of scope never
graduates; roadmap items might.

- **Monetisation** - accounts, licence keys, payments, entitlements.
- **A desktop app** - a Tauri or Electron shell was a planned later phase before the runtime redraw
  removed it. If it returns it is a fresh effort against a redrawn destination, not a resumption.
