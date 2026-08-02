# Pinegrow: what it actually does, and where its users are unhappy

Research for [issue #2](https://github.com/stueydubs/webtweak/issues/2). Evidence gathered 2026-08-02
against Pinegrow's own site, documentation, release notes and community forum, plus third-party
review platforms where noted. Version current at time of writing: **Pinegrow Web Editor 9.3,
released 18 June 2026** ([release notes](https://pinegrow.com/release_notes/pinegrow-web-editor-9-3/)).

Every claim below carries its source. Where a question could not be answered from a primary
source, it is listed under [Gaps](#gaps-what-could-not-be-established) rather than guessed at.

---

## What this changes for webtweak

1. **"Claude writes the CSS" is no longer a clear differentiator.** Pinegrow ships an AI Assistant
   that drives **Claude Code itself**, visually, from inside the editor, with file-edit permissions
   on by default. See [AI Assistant](#ai-assistant-and-claude-code). The differentiator has to move
   to something else - most plausibly *not owning the file*.
2. **The single loudest, longest-running complaint against Pinegrow is that it rewrites source it
   did not author** - reformatting braces, collapsing hand-wrapped lines, moving elements on save.
   It recurs from 2017 to 2026 and Pinegrow staff confirmed in February 2026 that formatting style
   is not configurable and not planned. That is the wound webtweak's capture-intent-not-rewrite
   architecture is shaped to avoid, and it is worth naming explicitly.
3. **DOM reordering is not the only gap, and it is not the biggest one.** Pinegrow also does
   element creation from framework libraries, duplication, deletion, multi-element parallel edits,
   components and master pages, text-content editing, hover/focus state editing, a CSS Grid editor,
   and a repeater. Full list under [What Pinegrow does that webtweak has no answer to](#what-pinegrow-does-that-webtweak-has-no-answer-to).
4. **Per-breakpoint authoring is a genuine, evidence-backed webtweak edge for plain CSS.** In
   Pinegrow the active page-view width does *not* scope a plain-CSS edit to a media query - you pick
   the query by hand - and a 2020 feature request to change that was never granted. Tailwind is the
   exception, where the view width does drive the variant. See [Responsive and media queries](#responsive-and-media-queries).
5. **Pinegrow refuses invalid HTML, loudly and by design.** Its own documentation says malformed
   third-party markup "will severely compromise the proper functioning of Pinegrow" and can crash
   it. webtweak never parses source at all until reconcile, so scrappy hand-coded and legacy pages
   are a segment Pinegrow actively pushes away.

---

## Method, and what counts as evidence here

- **Primary**: pinegrow.com, docs.pinegrow.com, pinegrow.com/release_notes, forum.pinegrow.com
  (Discourse, queried through its public `search.json` and `t/<id>.json` endpoints), and the
  Pinegrow GitHub organisation.
- **Secondary, used only where flagged**: Capterra review text. No SEO listicle is cited.
- **Reddit could not be accessed at all.** Both the tooling's fetcher and Reddit's own JSON
  endpoint refused (`403 Blocked`). Reddit sentiment is therefore **absent** from this document,
  not summarised. That is a real hole in the complaint evidence and should be filled by hand.

---

## 1. Capability list at feature granularity

### The file model: Pinegrow owns your files

> "Pinegrow works with regular HTML files on your computer. Simply open, edit and save HTML files
> without the need to import or export anything. Pinegrow doesn't add any HTML, CSS or JavaScript
> code to your pages. As far as files are concerned Pinegrow works just like any other code editor."
> - [Working with pages](https://pinegrow.com/docs/pages/pages.html)

That page is flagged by Pinegrow as outdated, but it remains the clearest statement of the model and
nothing in the current docs contradicts it. The claim is qualified by Pinegrow's own FAQ, which
states that WordPress creation, Interactions, Actions, CMS and the Tailwind editor **do** add custom
`data-*` attributes, adding roughly 2kb to a page
([FAQ](https://pinegrow.com/faq/)). So "adds no code" holds for the base editor and stops holding
the moment you use an add-on.

Architecturally this is the opposite of webtweak. Pinegrow parses the file into a live DOM, keeps
visual tools and code editors synced against that DOM, and serialises back on save. webtweak never
touches source; it emits a patch list for reconcile.

Pinegrow is an [NWJS](https://nwjs.io) app (Chromium plus Node.js), "99% ... pure client-side web
application", with an internal web server for the page view that serves only project files and
accepts only localhost connections by default
([Technical information and security](https://pinegrow.com/docs/getting-started/install-and-run-pinegrow/technical-information-and-security/)).
Anonymous run telemetry goes to Google Analytics and can be disabled in Settings, but not in trial
mode (same page).

### How it identifies an element in source

It does not need to. Because Pinegrow parses and owns the document, an element is identified by its
position in the live parsed tree, not by any fingerprint or injected marker. Selection happens by
hovering or clicking in the page view, or by clicking in the Tree panel, and the two stay in sync
([Discovering Pinegrow Web Editor](https://pinegrow.com/docs/getting-started/discovering-pinegrow-web-editor-the-overview/)).
Selected elements are also highlighted in the page code editor
([Code editing](https://docs.pinegrow.com/docs/master-pinegrow/code-editing/)).

The one place Pinegrow *does* fall back to text matching is locating a CSS rule in a stylesheet's
code editor, and it says so plainly:

> "The matching of selected rules in the code editor is done by simple selector text search. While
> not perfect, this feature is still very useful to quickly navigate complex stylesheets."
> - [Styling with CSS](https://pinegrow.com/docs/master-pinegrow/style/)

For external file changes it does a structural diff rather than a reload:

> "Instead of simply reloading the whole page, Pinegrow compares both versions of the page and only
> updates the modified elements" - [Code editing](https://docs.pinegrow.com/docs/master-pinegrow/code-editing/)

### Does it round-trip formatting and comments?

**Comments: yes, they are modelled.** The stylesheet CSS List editor states "Everything there is
editable, including selectors, comments, property names and values", and rules and properties can be
hidden by commenting them out
([Styling with CSS](https://pinegrow.com/docs/master-pinegrow/style/)).

**Formatting: no, and this is confirmed by Pinegrow staff.** Asked in February 2026 whether brace
style could be configured, Emmanuel (Pinegrow) answered:

> "Pinegrow doesn't give you any options to change code formatting styles. Its HTML gets
> auto-formatted or not (depending of the settings) according to its built-in rules, and there is no
> way to switch between different brace styles. ... This is not something that is planned for
> development right now. If code formatting is really important to your workflow, you could use an
> external editor for manual code work and keep Pinegrow for the visual side."
> - [forum t/11404](https://forum.pinegrow.com/t/is-it-possible-to-change-code-formatting-to-allman-bracing-in-css-js-answered/11404), 17 Feb 2026

There is an on/off auto-format toggle for HTML and a CSS formatting option (per the screenshots in
that same thread, and confirmed in [t/8802](https://forum.pinegrow.com/t/code-formatting/8802)), but
no control over the style applied when it is on. A 2018 user established that CSS is reformatted **on
load**, not only on save
([t/2134](https://forum.pinegrow.com/t/css-code-formatting-how-can-it-be-stopped/2134)), which is why
turning off save-time formatting does not fully protect a file.

Reported symptoms across the years: opening braces forcibly moved to a new line
([t/883](https://forum.pinegrow.com/t/css-code-auto-formating-stop-abusing-my-brackets/883), 2017),
two blank lines added at the top of every stylesheet (same thread), hand-wrapped code collapsed back
to one line on reopen ([t/8802](https://forum.pinegrow.com/t/code-formatting/8802), 2024), long lines
being combined by the code editor's auto-formatter
([t/8932](https://forum.pinegrow.com/t/code-formating-review/8932), 2024), a set indent size of 2
ignored in favour of 4 in generated SCSS
([t/4144](https://forum.pinegrow.com/t/code-indent-size-not-honoured/4144), 2020), and space rather
than tab indentation with no switch
([t/11167](https://forum.pinegrow.com/t/pinegrow-evaluation-questions/11167), 2025).

The most severe report is not formatting but reordering. In September 2022 a user with 20 years of
hand-coding reported that after hand-editing and saving, "I added code to a page, I saved the page,
Pinegrow moved the code down three divs" and that the move could not be undone
([t/6953](https://forum.pinegrow.com/t/i-hand-edit-code-save-my-page-pinegrow-moves-elements-around-will-not-undo-unacceptable/6953)).
No root cause was ever established in the thread; the exchange became heated and the reporter left.
Treat it as one unreproduced report, but note it is the same failure class as the formatting reports
and it went unresolved.

### How it handles a stylesheet it did not author

Well, and with more control than expected. From
[Styling with CSS](https://pinegrow.com/docs/master-pinegrow/style/):

- The **Active** tab shows every rule affecting the selected element, with framework stylesheets
  hidden by default behind a "Show more" link, since editing framework CSS is treated as bad
  practice.
- Any stylesheet can be marked **"Ignore in Active"** to keep third-party and plugin CSS out of the
  list, hidden from the page view to see what it contributes, reordered, or detached.
- New rules go to a **default stylesheet** you nominate on first use and can change per stylesheet
  via "Set as default for new rules". So Pinegrow will not scatter rules into a vendor file by
  accident.
- Existing `.scss`/`.less` sources sitting beside a `.css` file are auto-discovered and loaded; if
  they live elsewhere you point Pinegrow at the main source file once and it remembers. A plain
  `.css` file can be converted to SASS or LESS in place.
- SASS and LESS compilers are bundled, compile live without saving, and run autoprefixer.

The caveat is that a stylesheet Pinegrow opens is a stylesheet Pinegrow may reformat, per the
previous section. A user working around minified CSS described prettifying it just to read it in
Pinegrow ([t/10950](https://forum.pinegrow.com/t/noodle-no-more-jambo-asanti-sana/10950), 2025).

### Responsive and media queries

Pinegrow generates a list of candidate media queries **from the breakpoint values already used on
the page**, offers a custom query box, and has a "Page -> Manage breakpoints" dialog
([Styling with CSS](https://pinegrow.com/docs/master-pinegrow/style/)). That is the same instinct as
webtweak's Band picker.

The difference is what happens automatically. For plain CSS, selecting a page view does **not** scope
your edit to that view's media query. Pinegrow's own moderator confirmed the "Active View for CSS
Editing" brush only filters which rules are *shown*:

> "It will only show rules that impact ... that view. If you have a new rule without a media query,
> it will also impact that view."
> - RobM, [t/4198](https://forum.pinegrow.com/t/select-active-view-for-css-editing/4198), 2 Jun 2020

The thread became a feature request to write edits into the corresponding media query automatically.
As of 9.3 no release note records that behaviour landing for plain CSS.

For **Tailwind** it is the reverse and users have complained about it: dragging the canvas wider
automatically switches the active Tailwind breakpoint variant, with no way found to disable it
([t/6895](https://forum.pinegrow.com/t/disable-automatic-media-query-for-tailwind-css/6895), 2022).

Pinegrow shows multiple device-size page views side by side, and Pinegrow 9 added live browser
preview windows plus QR-code sharing to preview on a phone with "no extra configuration"
([Pinegrow 9 release notes](https://pinegrow.com/release_notes/pinegrow-web-editor-9/)).

### DOM reordering and structural editing

Fully supported, and considerably richer than a simple move
([Drag & Drop](https://pinegrow.com/docs/master-pinegrow/drag-drop/)):

- Drag from the Library panel, the page view, or the Tree; drop onto the page view or the Tree. An
  orange insertion line shows placement relative to the green-highlighted target. `ESC` aborts.
- Default gesture is **move**; hold `ALT` to **clone**.
- **Grab and move** without selecting first: hold the mouse for about half a second on a highlighted
  element and the drag starts.
- **Repeater**: type a number before or during the drag to insert that many copies.
- **Multi-element drag**: with several elements selected, dragging one brings all of them.
- **Parallel structural edits**: dropping an element into one of several selected elements repeats
  the insertion in all of them, and moving a child within one selected element repeats the same move
  in the others "if possible".

Separately documented: [duplicating elements](https://pinegrow.com/docs/how-to-guides/duplicating-existing-elements/),
[deleting elements](https://pinegrow.com/docs/how-to-guides/delete-elements/), and
[removing the wrapping tag](https://pinegrow.com/docs/how-to-guides/remove-the-tag-span-div-around-the-element/).

### Styling controls

From [Styling with CSS](https://pinegrow.com/docs/master-pinegrow/style/):

- Visual CSS editor covering most CSS properties, grouped into sections, with drag-scrub numeric
  controls and arrow-key stepping.
- Linked directional controls for margin and padding.
- Multi-value controls for shadows, transitions and transforms (add and remove individual items).
- A colour picker that can eyedrop any pixel in the Pinegrow window.
- **Pseudo states**: `:hover`, `:active`, `:focus`, `:visited` can be force-displayed and targeted by
  appending the pseudo-class to a selector.
- A **Selector maker** that builds a selector from the element path, reports how many elements on the
  page it matches, offers to assign missing classes, and lets you pick the media query and target
  stylesheet before creating the rule.
- The **style attribute** is treated as a scratchpad with a one-click "promote to a real CSS rule"
  action that transfers the properties and clears the attribute.
- Any property with no visual control can be typed in the CSS List editor or edited via a floating
  per-rule code editor.
- A visual **CSS Grid editor** with named areas and named lines, which also works with Tailwind since
  Pinegrow 8 ([Tailwind updates](https://pinegrow.com/docs/tailwind/updates/)).

### Text and content editing

Pinegrow edits text content in place, via the browser's inline editing mode. It has been a persistent
sore point rather than a strength: Enter splitting a paragraph into two elements was objected to as
"a terrible idea" in 2017 ([t/1304](https://forum.pinegrow.com/t/3-1-text-editing-return-key-behaivour/1304)),
inline editing breaks when a page sits in a subfolder
([t/3039](https://forum.pinegrow.com/t/editing-text-in-page-view-does-not-work-properly-for-file-located-in-subfolder/3039), 2019)
and when a `p:first-letter` rule is present
([t/3054](https://forum.pinegrow.com/t/editing-text-in-page-view-does-not-work-properly-when-using-p-first-letter-font-size-125/3054), 2019),
and in 2024 a user reported that copy-pasting a block of text in visual mode **loses embedded links**,
calling it "a nightmare ... it essentially makes editing impossible"
([t/9865](https://forum.pinegrow.com/t/mass-deletion-and-renaming-of-selectors-refinement-of-font-manager/9865),
repeated in [t/9129](https://forum.pinegrow.com/t/roadmap-for-pinegrow-whats-cooking/9129)).

### Framework and component support

**Bootstrap and Foundation** (base edition, no add-on). Component library panel with pre-styled
variants, framework-aware property controls that change with the selected element, a Design panel for
theme customisation, display helpers, floating tools, an "edit an existing Bootstrap page or project"
path, and an upgrade-to-latest-Bootstrap-version tool
([Bootstrap Visual Editor docs](https://pinegrow.com/docs/bootstrap-visual-editor/)).

**Tailwind CSS** (paid add-on). What it genuinely covers, from the
[Tailwind Visual Editor docs](https://pinegrow.com/docs/tailwind/) and
[updates](https://pinegrow.com/docs/tailwind/updates/):

- **Tailwind CSS 4 is fully supported** as of Pinegrow 8.4, released 13 March 2025.
- Visual controls in the Properties panel that write utility classes.
- A **Class Tree inspector** for users who find the visual controls too much clicking, with
  multi-select, copy, move-to-variant, move-to-parent, and a right-click `!important` toggle (the
  Tailwind `!` prefix).
- Two style kinds in a Style manager: **Class styles** (utilities on the element) and **Component
  styles**, which compile through Tailwind into ordinary selector-based CSS rules so you can style
  `h1` rather than decorating every heading. Pinegrow describes this as "pure CSS styling with the
  convenience of Tailwind".
- A built-in Tailwind compiler with a **Compiler options** dialog for custom screens, spacings and
  theme values, plus a documented
  [external build process](https://pinegrow.com/docs/tailwind/using-external-build-process/) path.
- Tailwind Blocks library, component libraries, Flowbite Blocks integration, and TailwindUI support
  (TailwindUI licence bought separately from Tailwind Labs).
- A Design panel for custom themes "without editing any config file".
- Extended variant support including custom variants targeting sub-elements by selector.

The Tailwind docs do not state whether **arbitrary value syntax** (`w-[137px]`) is exposed in the
visual controls. Treat as unestablished.

**WordPress** (paid add-on, plus a separate WordPress plugin product). The desktop add-on turns HTML
into "production-ready custom WordPress themes" by attaching smart actions to elements; the docs
cover block themes, classic themes, templates, headers and footers, `theme.json` export, custom
Gutenberg blocks including dynamic and ACF Pro blocks, responsive images, and a Shop Builder for
WooCommerce ([WordPress docs](https://pinegrow.com/docs/wordpress/)). Pinegrow 9.3 added Blocks V3
API export with `block.json` metadata, an automatic Tailwind stylesheet for new WordPress themes, and
a block-vs-classic theme setup choice ([9.3 release notes](https://pinegrow.com/release_notes/pinegrow-web-editor-9-3/)).
The separate **Pinegrow WordPress Plugin** runs inside a WordPress install, exports "straight to the
site's staging or production environment", requires WordPress 6.0+, is subscription-only, and
includes "all Pinegrow features (except static components and SASS compilation)". If the subscription
lapses the plugin stops working, though already-exported themes keep running
([pinegrow.com/wordpress](https://pinegrow.com/wordpress)).

**Vue, Nuxt, Astro, Vite** are **not** in Pinegrow Web Editor. They are a separate product,
**Vue Designer**, with its own docs section and its own quick-start template repos on
[GitHub](https://github.com/Pinegrow). A third product, **Piny**, is a visual React/Next/Tailwind
editor for VS Code. Do not credit Pinegrow Web Editor with framework support that belongs to a
sibling product.

**Components, master pages, projects, CMS.** Reusable smart components, editable areas, master pages,
partials, reusable libraries, and a static-HTML CMS mode for clients are all base-edition features
(feature comparison panel on [pinegrow.com](https://pinegrow.com/)). Pinegrow 9 reworked components
so definitions and instances are labelled, selecting inside a definition selects the component, and
edits propagate to all instances on leaving an explicit "Editing mode"
([Pinegrow 9 release notes](https://pinegrow.com/release_notes/pinegrow-web-editor-9/)).

**Interactions** (paid add-on). GSAP-powered animations, scroll scenes, a timeline editor, and
interaction blueprints for sliders, galleries, tooltips and presentations. The GreenSock licence is
included ([Interactions docs](https://pinegrow.com/docs/interactions/)).

### AI Assistant and Claude Code

This is the most decision-relevant capability for webtweak, and it is recent.

Pinegrow's AI Assistant can drive **Claude Code** as a provider, from inside the visual editor
([Using Claude Code in Pinegrow](https://pinegrow.com/docs/ai-assistant/claude-code/)). Pinegrow's own
words:

> "By default, Pinegrow runs Claude Code with permissions to execute commands and edit files without
> asking for confirmation. Always use it with source control such as Git."

and

> "You can use Claude Code without paying extra if you already have a Claude subscription. And now
> with Pinegrow, you get to work with Claude Code visually."

OpenAI Codex CLI is supported the same way
([Codex CLI docs](https://pinegrow.com/docs/ai-assistant/codex-cli/)). Only the default Claude Code
model is exposed.

Separately, **Smart HTML Edit** gives an AI model tool-calls to update specific elements, set
attributes and remove elements rather than regenerating whole documents, scoped either to all open
pages or to the selected element
([Smart HTML editing with AI](https://pinegrow.com/docs/ai-assistant/smart-html-editing-with-ai/)).
Pinegrow 9.3 added AI image editing, saved reusable AI prompts as project presets, and a hosted
"Pinegrow Online" AI provider with credit tracking
([9.3 release notes](https://pinegrow.com/release_notes/pinegrow-web-editor-9-3/)).

### What it refuses, or breaks on

- **Malformed HTML.** Pinegrow's own guidance is unusually direct: unclosed elements, badly nested
  elements and unclosed attributes "will severely compromise the proper functioning of Pinegrow" and
  "may cause severe malfunctions or even a crash of the application in the most acute cases". It
  advises running third-party templates through the W3C validator before opening them
  ([How to use valid W3C documents](https://pinegrow.com/docs/how-to-guides/how-to-use-valid-w3c-documents-to-maximize-your-experience-with-pinegrow/)).
  Users report being blocked from saving over syntax errors Pinegrow reported but could not locate
  ([t/6953](https://forum.pinegrow.com/t/i-hand-edit-code-save-my-page-pinegrow-moves-elements-around-will-not-undo-unacceptable/6953)).
- **Non-HTML languages.** "Only HTML, and certain templating languages can be visually edited";
  JavaScript opens in the code editor
  ([overview](https://pinegrow.com/docs/getting-started/discovering-pinegrow-web-editor-the-overview/)).
- **Framework stylesheets** are hidden by default and treated as off-limits
  ([Styling with CSS](https://pinegrow.com/docs/master-pinegrow/style/)).
- **Non-coders.** Pinegrow says so itself: it is "probably not a good fit" if "you don't know what
  are HTML elements and CSS rules" or want "a simple drag and drop editor ... without knowing what
  happens in the background"
  ([Is Pinegrow the right choice for you?](https://pinegrow.com/docs/getting-started/is-pinegrow-the-right-choice-for-you/)), and
  separately that it "was never intended to be a 'Photoshop for the web'"
  ([Understanding Pinegrow](https://pinegrow.com/docs/getting-started/understanding-pinegrow-not-just-a-design-tool/)).
- **Open from URL** saves only the HTML and CSS locally; images, scripts and other assets are not
  saved ([Working with pages](https://pinegrow.com/docs/pages/pages.html)).
- **No FTP client**, raised as a con in reviews
  ([Capterra](https://www.capterra.com/p/201850/Pinegrow/reviews/)) and refused deliberately in a 2016
  forum thread ([t/370](https://forum.pinegrow.com/t/when-is-ftp-coming/370)).
- **Code formatting style** is not configurable and not planned
  ([t/11404](https://forum.pinegrow.com/t/is-it-possible-to-change-code-formatting-to-allman-bracing-in-css-js-answered/11404)).

---

## 2. Pricing as it stands today

Read from the live purchase widget on [pinegrow.com/#buy](https://pinegrow.com/#buy) on 2 August 2026,
across all three plan tabs. Pinegrow prices through Paddle, which localises by country, so the same
widget shows different currencies to different buyers. **A 35% "Summer Sale" was running**, so the
sale figures below are temporary; the regular figures are the ones to plan against.

Figures observed from Australia, in AUD. The page's own hardcoded USD fallback markup lists
**USD 99/year** for the editor and **USD 50/year** per add-on, with Interactions at **USD 200
one time**, so the USD and AUD price lists are set separately rather than converted.

| Plan | Editor, regular | Editor, at 35% off | Notes |
|---|---|---|---|
| Annual subscription | AUD 217.36/yr | AUD 141.28/yr | Access ends when the subscription ends |
| Monthly subscription | AUD 26.26/mo | AUD 17.07/mo | Same |
| One time payment | AUD 290.30 | AUD 188.70 | Use the current version forever, plus 1 year of updates |

Add-on pricing, per user:

| Add-on | Annual | Monthly | One time |
|---|---|---|---|
| Tailwind Visual Editor | AUD 72.94/yr regular | AUD 8.75/mo regular | AUD 72.94 regular |
| WordPress Builder | AUD 72.94/yr regular | AUD 8.75/mo regular | AUD 72.94 regular |
| Shop Builder for WooCommerce | AUD 72.94/yr regular | AUD 8.75/mo regular | **Not available** |
| Interactions | bundled free during this sale | bundled free during this sale | **Not available** |

What is gated where, from the widget's own feature comparison panel and the
[FAQ](https://pinegrow.com/faq/):

- **Pinegrow Web Editor Pro (base)**: HTML, CSS/SASS/LESS, live editing, multiple views, code
  editing, open URLs, dynamic HTML elements, HTML snippets, responsive tools, **Bootstrap**,
  **Foundation**, Blocks, PHP/ASP/ERB, Font Awesome, projects, master pages, smart components,
  editable areas, reusable libraries, partials, static CMS. Now also bundles **Pinegrow Online for
  local projects**.
- **Interactions add-on**: interactions, scroll scenes, timeline editor, GreenSock licence included.
  Subscription only.
- **WordPress Theme Builder add-on**: WP theme builder, Blocks for WordPress.
- **Tailwind Visual Editor add-on**: visual controls, responsive editing, Styles, helpers, component
  libraries.
- **Shop Builder for WooCommerce add-on**: requires the WordPress Builder. Subscription only.

Licence terms, verbatim from the widget and FAQ:

- One time payment: "Comes with 1 year of free updates. After the first year you can use your current
  version forever or renew to continue receiving free updates. Interactions are not included."
  Renewal is half the price of a new licence.
- Subscription: "If cancelled, I won't be able to use Pinegrow anymore."
- 30-day money-back guarantee applies to one-time licences, upgrades and annual subscriptions, **not**
  to monthly subscriptions.
- **7-day free trial**, no payment details, all features including add-ons.
- Pricing is **per user**, with volume discounts starting at 5 seats.
- A student, educator and non-profit plan exists
  ([docs](https://pinegrow.com/docs/licensing-questions/students-teachers-ngos-and-npos/)).
- An **All-Inclusive Company** package exists at **USD 200/month or USD 1,920/year**, covering
  unlimited employee and contractor licences of Pinegrow PRO with WordPress Theme Builder, unlimited
  Pinegrow CMS client licences and unlimited Snapshots licences
  ([all-inclusive.html](https://pinegrow.com/all-inclusive.html)).

Platforms: macOS (Apple Silicon and Intel), Windows 64-bit, Linux 64-bit zip
([9.3 release notes](https://pinegrow.com/release_notes/pinegrow-web-editor-9-3/)).

---

## 3. Documented user complaints

There is **no public issue tracker for Pinegrow Web Editor**. The
[Pinegrow GitHub organisation](https://github.com/Pinegrow) has 69 repositories, but they are
quick-start templates for Vue Designer plus `PinegrowReleases`, which is a download host with issues
disabled. All bug reporting flows through the forum and a support email address. The complaints below
are therefore forum-sourced except where marked.

Ranked by recurrence and by how long the complaint has persisted.

### 3.1 Pinegrow reformats and rearranges code you wrote by hand

**Recurrence: at least ten distinct topics, 2017 to 2026. The single most persistent complaint
found.** Confirmed as intended behaviour with no configuration, by staff, in 2026.

| Date | Topic | Complaint |
|---|---|---|
| 2017-04-24 | [t/883](https://forum.pinegrow.com/t/css-code-auto-formating-stop-abusing-my-brackets/883) | Opening braces forced onto a new line; two blank lines added at the top of every stylesheet |
| 2018-08-21 | [t/2134](https://forum.pinegrow.com/t/css-code-formatting-how-can-it-be-stopped/2134) | CSS reformatted **on load**, breaking AMP boilerplate validation; no CSS auto-format toggle at the time |
| 2020-02-04 | [t/3756](https://forum.pinegrow.com/t/css-in-email-gets-formatted-somehow/3756) | HTML email CSS mangled; disabling CSS formatting did not help |
| 2020-05-20 | [t/4144](https://forum.pinegrow.com/t/code-indent-size-not-honoured/4144) | Indent size set to 2, generated SCSS indented at 4 |
| 2021-05-23 | [t/5282](https://forum.pinegrow.com/t/pinegrow-with-auto-formatting-mustache-code/5282) | Mustache conditionals damaged on save |
| 2022-09-12 | [t/6953](https://forum.pinegrow.com/t/i-hand-edit-code-save-my-page-pinegrow-moves-elements-around-will-not-undo-unacceptable/6953) | Hand-added code **moved down three divs** on save, not undoable |
| 2024-03-21 | [t/8802](https://forum.pinegrow.com/t/code-formatting/8802) | Hand-wrapped code collapsed to one line on reopen |
| 2024-05-29 | [t/8932](https://forum.pinegrow.com/t/code-formating-review/8932) | Auto-formatter "keeps combining bunches of my code into one long line"; user turned it off |
| 2025-04-19 | [t/10638](https://forum.pinegrow.com/t/trying-to-format-code-on-mac-with-cmd-f-or-cmd-shift-opt-f/10638) | Format shortcuts do not work on macOS |
| 2025-10-17 | [t/11167](https://forum.pinegrow.com/t/pinegrow-evaluation-questions/11167) | Space indentation with no way to switch to tabs |
| 2026-02-14 | [t/11404](https://forum.pinegrow.com/t/is-it-possible-to-change-code-formatting-to-allman-bracing-in-css-js-answered/11404) | Brace style forced; staff confirm no options, not planned |

Note the arc. In 2022 a community moderator suggested opening a feature request for a formatting
toggle; in 2026 staff answered that no such option exists and none is planned. This is a settled
position, not a backlog item.

### 3.2 Undo is unreliable

**Recurrence: reported since 2014 by one user's account, with at least four separate topics.**

The clearest artefact is [t/6388](https://forum.pinegrow.com/t/fix-the-undo-it-has-been-broken-since-2014/6388)
(March 2022, 1,040 views), titled "Fix the undo it has been broken since 2014!". The poster searched
the forum and quoted other users back at it, including:

> "I am so afraid what PG will do when I type command-Z to Undo that it is completely unusable"

and

> "The undo action breaks when you add any piece of code to the `<head>`. Problem will trigger every
> single time, and when it triggers you cannot 'Undo'"

Supporting reports: [t/1213](https://forum.pinegrow.com/t/is-it-possible-to-undo-edits-in-the-text-editor-which-contains-the-html-page-in-pinegrow-3/1213)
(2017, `Ctrl+Z` does nothing in the page code editor),
[t/7450](https://forum.pinegrow.com/t/stabilize-undo-in-text-editor/7450) (2022, undo in the text
editor removes things from the page instead), and the "will not undo" half of
[t/6953](https://forum.pinegrow.com/t/i-hand-edit-code-save-my-page-pinegrow-moves-elements-around-will-not-undo-unacceptable/6953)
(2022).

### 3.3 Performance and stability

**Recurrence: continuous from 2017 to June 2026.** Some of it is Pinegrow's NWJS/Chromium base
showing through.

| Date | Topic | Complaint |
|---|---|---|
| 2017-07 | [t/1061](https://forum.pinegrow.com/t/pinegrow-3-slow/1061) | General slowness; staff attribute it to page JS/CSS animations and open views |
| 2017-08 | [t/1208](https://forum.pinegrow.com/t/pinegrow-3-0-6-osx-10-10-5-pinegrow-stopped-responding-lost-work-twice/1208) | Freeze, lost three to four hours of work, twice |
| 2019-09 | [t/3303](https://forum.pinegrow.com/t/slow-running-pg-5-7-pro-on-mint-19/3303) | Slow on Linux Mint |
| 2021-12 | [t/5922](https://forum.pinegrow.com/t/pinegrow-6-2-slow-on-macosx-10-15-7-and-freezes-when-typing-in-scss-files/5922) | 6.2 measurably slower than 6.1; staff confirm the NWJS upgrade caused it |
| 2025-07 | [t/10927](https://forum.pinegrow.com/t/pinegrow-desktop-painfully-slow-and-sluggish/10927) | On a maxed M1 Max, "opening a project takes minutes" and "about 2 seconds to register every click" |
| 2025-10 | [t/11185](https://forum.pinegrow.com/t/pinegrowlinux64-8-6-not-starting-fixed/11185) | 8.6 will not start on several Linux distros (NWJS crash) |
| 2025-12 | [t/11276](https://forum.pinegrow.com/t/11276) | 8.6.2 crashes on open; user stayed on 8.5 |
| 2026-04 | [t/11445](https://forum.pinegrow.com/t/11445) | Repeated crashes after editing CSS externally and returning to the project pane |
| 2026-06 | [t/11853](https://forum.pinegrow.com/t/11853) | Crashes every time HTML is pasted via Insert Code or Edit HTML |

Also reported: rules silently lost from a `custom.scss` on save
([t/4981](https://forum.pinegrow.com/t/saving-issues-with-sass-rules-deleted-unexpectedly/4981), 2021),
master page changes lost on project close
([t/7909](https://forum.pinegrow.com/t/master-page-changes-lost-every-time-project-was-closed/7909), 2023),
and spurious "File was changed outside of Pinegrow" prompts triggered by a scheduled backup, leading
to work being reloaded away
([t/9981](https://forum.pinegrow.com/t/file-was-changed-outside-of-pinegrow-but-it-wasnt/9981), 2024).

### 3.4 Learning curve and UI density

**Recurrence: the most common single word in evaluation threads, 2018 to 2023 and beyond.** Users
call it "considerably more complex software with a higher learning curve"
([t/2044](https://forum.pinegrow.com/t/hello-all-blocsapp-user-may-buy-pinegrow/2044), 2018),
"a pretty big learning curve for PG, but for me, it was well worth the effort"
([t/8618](https://forum.pinegrow.com/t/does-pinecone-do-absolute-positioning/8618), 2023), and
"maybe the learning curve is too steep"
([t/8255](https://forum.pinegrow.com/t/advanced-users-how-are-you-using-pinegrow/8255), 2023). One
user posted a paid request for a tutor purely to get up the curve faster
([t/8124](https://forum.pinegrow.com/t/seeking-experienced-pinegrow-user-to-help-me-become-proficient/8124), 2023).
Capterra reviewers echo it, one calling out steep learning curve alongside unpredictable text
selecting, editing and copying (VR, Designer, 31 Jan 2021,
[Capterra](https://www.capterra.com/p/201850/Pinegrow/reviews/)).

Notably, Pinegrow's own response was product change, not denial: Pinegrow 9 (January 2026) introduced
**Smart mode**, "a simpler Pinegrow workspace", with the previous configurable layout renamed
"Flexible mode", and a redesign explicitly aimed at "reduced visual clutter"
([Pinegrow 9 release notes](https://pinegrow.com/release_notes/pinegrow-web-editor-9/)).

### 3.5 Documentation and tutorials lag the product

**Recurrence: 2019 to 2024, several topics.** "Why are the tutorials so outdated?"
([t/5336](https://forum.pinegrow.com/t/why-are-the-tutorials-so-outdated/5336), 2021);
"I'll try to start from the documentation though unfortunately it's very outdated"
([t/2950](https://forum.pinegrow.com/t/2950), 2019); on the Interactions add-on, "it is primarily the
lack of documentation that makes it impossible to work"
([t/3553](https://forum.pinegrow.com/t/introducing-pinegrow-interactions/3553), 2019); and on the
newer Piny product, docs whose "sample code ... has ... placeholders that cause Vite to crash when
copied directly" with "no clear explanation of how to load dependencies"
([t/10726](https://forum.pinegrow.com/t/10726), 2025). Some doc pages are still served with a "THIS
PAGE IS OUTDATED" banner ([Working with pages](https://pinegrow.com/docs/pages/pages.html)).

### 3.6 Add-on unbundling and licence model

**Recurrence: 2020 to 2024, low volume but consistent.** "Are we going to be charged for every
expansion of Pinegrow if we want it?"
([t/4316](https://forum.pinegrow.com/t/are-we-going-to-be-charged-for-every-expansion-of-pinegrow-if-we-want-it/4316), 2020);
"I think that may be the only weird thing about Pinegrow is the packaging of the plans"
([t/8779](https://forum.pinegrow.com/t/im-new-to-pinegrow-and-wow/8779), 2024); a long argument over
whether a one-time licence is a "lifetime" licence
([t/7828](https://forum.pinegrow.com/t/update-on-the-remaining-woo-features/7828), 2023). Capterra
carries the same note: "new features often offered as paid add-ons rather than core features"
(Virgilio V., CTO, 1 May 2021).

### 3.7 Support responsiveness

**Low recurrence, but worth recording.** One three-week no-response report in 2021
([t/4860](https://forum.pinegrow.com/t/no-response-from-support-for-over-3-weeks/4860)); counter-evidence
that support is "responsive and helpful" in 2025
([t/5373](https://forum.pinegrow.com/t/shopify-themes-with-pinegrow/5373)). The forum is small and
tight-knit, which cuts both ways: the 2022 code-mangling thread ended with a community member telling
the reporter to use "the Exit door"
([t/6953](https://forum.pinegrow.com/t/i-hand-edit-code-save-my-page-pinegrow-moves-elements-around-will-not-undo-unacceptable/6953)).

### 3.8 Smaller recurring gripes

- No FTP integration, and no link rewriting when files are renamed (Aleksandar D., 22 Mar 2022,
  [Capterra](https://www.capterra.com/p/201850/Pinegrow/reviews/)).
- Class and ID lists in the Properties panel show every class ever used in the project, including
  deleted ones ([t/3917](https://forum.pinegrow.com/t/deleted-and-renamed-classes-ids-are-not-updated-in-property-panel-please-fix-this/3917), 2020).
- Linux packaging: no AppImage
  ([t/4174](https://forum.pinegrow.com/t/package-and-distribute-pinegrow-for-linux-with-appimage/4174), 2020),
  an unofficial and outdated Flathub build
  ([t/11393](https://forum.pinegrow.com/t/installing-pinegrow-on-linux-via-flathub/11393), 2026).
- Copy and paste behaving unpredictably across the app, 2017 through 2024
  ([t/1187](https://forum.pinegrow.com/t/1187), [t/2960](https://forum.pinegrow.com/t/2960),
  [t/9865](https://forum.pinegrow.com/t/mass-deletion-and-renaming-of-selectors-refinement-of-font-manager/9865)).

---

## 4. What Pinegrow does that webtweak has no answer to

Ordered by how hard each would be to answer.

1. **Structural DOM editing of every kind**, not just reordering: move, clone with `ALT`, grab and
   move without selecting, delete, duplicate, unwrap a tag, insert N copies with the repeater, drag
   several elements at once, and repeat a structural edit across several selected elements in
   parallel ([Drag & Drop](https://pinegrow.com/docs/master-pinegrow/drag-drop/)).
2. **Element creation from a real component library.** webtweak can create exactly six decorative SVG
   shapes. Pinegrow drags in Bootstrap components, Foundation components, Tailwind Blocks, Flowbite
   Blocks and TailwindUI components, and lets you paste arbitrary HTML into a custom-code box and
   drag the result as a reusable component
   ([overview](https://pinegrow.com/docs/getting-started/discovering-pinegrow-web-editor-the-overview/)).
3. **Editing text content in place.** webtweak explicitly does not do this (copy changes are spoken
   to Claude). Pinegrow does it, imperfectly, but it does it.
4. **Pseudo-state editing.** `:hover`, `:active`, `:focus`, `:visited` can be forced on and styled.
   webtweak has no answer at all ([Styling with CSS](https://pinegrow.com/docs/master-pinegrow/style/)).
5. **A visual CSS Grid editor**, with named areas and named lines
   ([Tailwind updates](https://pinegrow.com/docs/tailwind/updates/)). webtweak has no flex or grid
   editors by design.
6. **Multi-page and project-wide work**: master pages, editable areas, partials, reusable component
   libraries, smart components with instance propagation, projects, and a static CMS mode for clients.
   webtweak edits one page at a time.
7. **Framework awareness.** Property controls that change based on the selected framework and element,
   framework-specific design panels, and a Bootstrap version upgrade tool.
8. **Tailwind as a first-class target**, including Tailwind 4, component styles that compile to
   selector-based CSS, and a built-in compiler. webtweak's README concedes that pages needing a
   Tailwind compile "won't render identically to production".
9. **Animation authoring** via the GSAP-backed Interactions add-on.
10. **WordPress theme, block and plugin generation** from static HTML.
11. **Live SASS and LESS compilation** with autoprefixing, and discovery of existing SASS sources.
12. **Selector construction with match counts**, telling you how many elements a selector will hit
    before you create the rule. This is a direct answer to the "just this one or all `.section-title`s?"
    question webtweak currently resolves by asking the user at reconcile time.
13. **Editing pages over HTTP** via File -> Open from URL, and editing remote sites and web
    applications ([docs](https://pinegrow.com/docs/master-pinegrow/edit-remote-websites-and-web-applications/)).
    webtweak is local-file only, deliberately.
14. **Bidirectional sync with VS Code**, and character-level live sync with Atom.
15. **Multiple simultaneous device-size views**, plus QR-code preview on a phone.
16. **Its own AI Assistant driving Claude Code visually**, with saved prompt presets, tool-based smart
    HTML edits, and AI image editing.

---

## 5. What webtweak does that Pinegrow cannot

Held to a higher bar than the list above, because it is the flattering direction.

1. **It never rewrites source, so it cannot mangle it.** This is the strongest claim on the list and
   it is the one with the most evidence behind it, because it is the exact failure Pinegrow's users
   have complained about continuously since 2017 and which Pinegrow confirmed in February 2026 it
   will not fix. Pinegrow reformats a file on load and on save with rules you cannot configure;
   webtweak writes a sidecar JSON file and touches nothing else until a human-supervised reconcile.
   *Caveat*: webtweak's reconcile step does eventually rewrite source, and does so through an LLM,
   which is a different risk rather than no risk.
2. **It runs against pages Pinegrow refuses.** Pinegrow's own docs warn that unclosed tags, bad
   nesting and unclosed attributes may crash it and will disrupt its advanced features, and it
   advises validating third-party markup first. webtweak reads the browser's already-parsed DOM and
   captures a fingerprint; malformed markup that a browser renders is markup webtweak can work on.
   Additionally, webtweak serves non-UTF-8 pages byte-for-byte under their declared charset rather
   than re-encoding them.
3. **Edits scope to a breakpoint automatically, for plain CSS.** Pinegrow's own moderator confirmed
   the active view only *filters* which rules you see; you must choose the media query yourself, and
   a request to change that in 2020 went nowhere. webtweak's Scope picker defaults to the narrowest
   Band matching your window and previews only inside it. *Caveat*: this only holds for plain CSS.
   For Tailwind, Pinegrow already binds view width to variant, to the point where users have asked
   for a way to turn it off.
4. **Zero install cost and zero licence cost.** `npx webtweak page.html`, Node stdlib only, no
   dependencies, MIT. Against a AUD 217/year subscription or a AUD 290 one-time licence plus paid
   add-ons, with a 7-day trial.
5. **Nothing to learn.** "Steep learning curve" is Pinegrow's most-cited criticism, on its own forum
   and on review sites, and it prompted a full workspace redesign in Pinegrow 9. webtweak's surface
   is a click, a drag, a properties panel and Save.
6. **The edits file is a readable, version-controllable record of design intent.** Pinegrow leaves a
   diff in your source and nothing else; the reason for a change is lost. webtweak's
   `page.webtweak.json` is a durable, greppable changelog of what was changed and at what viewport,
   which can be committed alongside the site.
7. **It cannot lose your work, because it has none to lose.** Pinegrow has repeated reports of freezes
   costing hours, SCSS rules vanishing on save, and master-page edits lost on close. webtweak's
   worst case is losing an unreconciled session, and running it at all is consequence-free because
   source is untouched.

**Claims deliberately not made:** webtweak's live reload on source change and its use of the page's
own declared breakpoints and font stacks are not unique - Pinegrow watches and diff-reloads external
file changes, generates its media query list from the page's own breakpoints, and has done both for
years.

---

## Gaps: what could not be established

- **Reddit sentiment.** Reddit blocked every access route tried. Nothing from Reddit is represented
  here.
- **USD one-time and monthly prices.** The purchase widget localised to AUD from this location.
  The AUD figures above are observed; the USD figures quoted are the page's own hardcoded fallback
  markup for the annual plan and add-ons only.
- **Whether Tailwind arbitrary value syntax** (`w-[137px]`) is exposed through the visual controls.
  The Tailwind docs do not say.
- **Whether Pinegrow preserves HTML comments through a save.** CSS comments are demonstrably modelled
  and editable; the HTML side is not documented either way and no forum report was found in either
  direction.
- **What exactly the auto-format toggles cover.** Staff screenshots show an HTML auto-format setting
  and a CSS formatting setting with an "auto-detect" option, but the settings are not documented in
  prose and the 2018 finding that CSS is formatted on load suggests the toggles do not fully protect
  a file.
- **Root cause of the 2022 "moved my code down three divs" report.** One unreproduced report; never
  diagnosed in the thread.
- **Absolute user numbers.** Pinegrow says "thousands of super power users"; there is no independent
  figure. The forum has roughly 2,900 topics across all categories, which is a weak proxy at best.
- **Any public roadmap.** There is a "Roadmap for pinegrow. What's cooking?" forum thread
  ([t/9129](https://forum.pinegrow.com/t/roadmap-for-pinegrow-whats-cooking/9129), 2024) but no
  published roadmap document.
