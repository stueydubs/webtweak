# How other visual editors locate an element, write into source, and attach to a dev server

Research for [issue #3](https://github.com/stueydubs/webtweak/issues/3), under the [webtweak 1.0 map](https://github.com/stueydubs/webtweak/issues/1). Written 2026-08-02.

Every claim below is cited. Where a tool is closed source, the vendor's own docs are the primary source and I say so. Where I could not establish something from a primary source, it says **NOT ESTABLISHED** rather than an inference.

---

## What this changes for webtweak

1. **Fingerprint-style matching is not naive, and it is not unique either - it is the documented fallback tier of the field.** Two independent projects converged on almost exactly webtweak's signal bundle: [stagewise](#stagewise) serialises `tagName` + XPath + attributes + `innerText` + parent/sibling/child summary, and [Dosmos](#dosmos) ships a weighted, scored, cross-corroborating matcher over `ownText` (truncated to 80 characters, same as webtweak), heading text, id, data attributes and route. Dosmos even labels its own tiers: a build-time stamp is `// Exact`, the signal bundle is `// Heuristic`. So the shape is validated, but so is the ranking - nobody who *can* instrument the build chooses signals instead.

2. **The middle path ADR-0001 never considered: inject an identity into the *served* copy and strip it before anything reaches disk.** This is not a compromise, it is what the two most source-faithful tools in the survey actually do. Pinegrow's `data-pg-id` is removed on save, on external preview and on copy ([release notes](https://docs.pinegrow.com/release_notes/release-1-24-oct-17-2014/)); Utopia's `data-uid` is stripped by the printer on every production save ([`parser-printer.ts`](https://github.com/concrete-utopia/utopia/blob/9b605c1bfb5e9c74c9bb8c2102ca5bd9b515ba77/editor/src/core/workers/parser-printer/parser-printer.ts#L466)). webtweak already serves the page through its own Node server and already injects the Overlay, so it is one transform away from exact, unambiguous identity with the on-disk file untouched. This is the single most actionable finding in the survey.

3. **For CSS writes, element-to-HTML-source identity is not needed at all - and the browser already hands you the CSS half for free.** Chrome DevTools Workspaces saves CSS and JS edits straight to disk with zero instrumentation, and [explicitly refuses DOM edits](https://developer.chrome.com/docs/devtools/workspaces): "DevTools doesn't save changes to DOM that you make in the Elements panel." webtweak 1.0 writes CSS. The Fingerprint's hard problem only bites in two places: adding a selector hook the source lacks (reconcile step 4), and the `create` op.

4. **Formatting preservation is ground nobody in this survey holds, including the paid incumbent.** Onlook re-prints the whole file through Babel then Prettier ([`parse.ts`](https://github.com/onlook-dev/onlook/blob/423e2e924366419e418ee049093872d535eea41a/packages/parser/src/parse.ts)); Utopia re-prints through the TypeScript printer then Prettier; Pinegrow auto-formats by default and makes preservation an opt-in that then leaves the user responsible for anything it inserts ([4.8 release notes](https://pinegrow.com/release_notes/release-4-8-31-may-2018/)). A byte-offset splice via [parse5 `sourceCodeLocationInfo`](https://parse5.js.org/interfaces/parse5.Token.ElementLocation.html) plus PostCSS raws would hold a line all of them concede.

5. **"Attach to a dev server" has no good precedent to copy, and the local-Node-server decision already taken is the right shape.** Onlook and Tempo both rewrite the user's build config to install themselves; Utopia runs its own in-browser bundler and cannot touch a local filesystem at all; Webstudio never leaves its own hosted iframe. The only tools that attach to an *arbitrary* running dev server are the ones that need nothing from it - Polypane and Dosmos just load the URL, stagewise drives a browser over CDP.

---

## Comparison table

### Full visual editors

| Tool | Element identity | Writes real source? Formatting and comments? | Dev server attachment | Refuses |
|---|---|---|---|---|
| **webtweak** (baseline) | Signal bundle: tag, id, classes, truncated `text`/`ownText`, clean `openTag`, `siblingIndex`, weak `nth-of-type` selector. No mutation. | No. Captures Patches; Claude reconciles. | Own Node server serving one directory, injects Overlay, SSE reload | Ambiguous matches are flagged, not guessed |
| **Pinegrow** | `data-pg-id` injected into its own DOM, mapped to a `pgParserNode` in its parse tree. **Stripped on save.** | Yes, real files, no import/export. Auto-formats **by default**; preservation is opt-in. Comments: NOT ESTABLISHED. | Internal HTTP server on `127.0.0.1:40001` serving the unsaved doc, user runs Browsersync in front | Non-HTML templates ("can even lead to corrupted code"), server-side apps, SASS/LESS in remote editing |
| **Onlook** | `data-oid`, a random 7-char nanoid **written into your `.tsx` files on disk and committed to git**. Location lives in a side index `.onlook/index.json`. | Yes. Babel AST, full file re-print, then Prettier. Comments kept, hand formatting reflowed. | Cloud container + iframe + preload script. **Rewrites your root layout and `next.config`/`vite.config`.** | Plain HTML/CSS entirely (JSX extensions only); React Fragments; any element without an OID |
| **Tempo** | `className="... tempo-<uuidv5>"` + `tempoelementid` prop, from `uuid5(relativePath + Nth JSX element)`. SWC plugin, **compiled output only**. | Yes, but server-side and closed. Mechanism NOT ESTABLISHED. | User-committed `swcPlugins` entry gated on `NEXT_PUBLIC_TEMPO`; rsync over SSH into a Tempo container | Plain HTML/CSS; non-React; `node_modules`; Next.js 15+ ("Not yet supported") |
| **Utopia** | `data-uid` = murmur128 hash of (file, source range, element name, cleansed props), plus `data-path` carrying the ElementPath. **Stripped from the file on save.** | Yes. Full re-print from the model via the TS printer, then Prettier. Comments modelled and re-emitted; unmodelled code preserved verbatim. | Own in-browser stack: Babel standalone + TypeScript + BrowserFS in a worker. Canvas is same-document, not an iframe. | "You won't be able to edit projects in the file system on your machine"; auto-focusing map-generated elements |
| **Webstudio** | nanoid `Instance.id` in a Postgres-backed graph; surfaced to the canvas DOM as `data-ws-id` plus a `data-ws-selector` ancestor chain. | No source to edit. Generates one-way into `__generated__/`. No parser back. | Its own hosted `/canvas` iframe. Never a user dev server. | No round-trip; no site importer or URL crawler (it does accept pasted HTML+CSS) |
| **Polypane** | None. Live DOM only. Styles tab shows a rule's stylesheet and line "when available" - standard Chromium origin display, not a project mapping. | No. Exit path is the clipboard. | It is a Chromium browser; you point it at localhost. Watches a directory to reload CSS, one-directional. | Writing to disk at all |
| **Codux** | NOT ESTABLISHED (closed source). User-level: "jump directly to the relevant line of code". | Claims code is "the ultimate source of truth" and changes are "immediately written to your code files". Formatting: NOT ESTABLISHED, but Prettier integration implies normalisation. | NOT ESTABLISHED | "only supports visualizing and editing statically analyzable board objects". **Product discontinued.** |
| **Chrome DevTools Workspaces** | None for elements. Folder-to-network-resource mapping for *files*. | **CSS and JS yes, DOM no**, by explicit design. | Connect a folder, or auto-connect via `/.well-known/appspecific/com.chrome.devtools.json`. localhost only. | Saving Elements-panel DOM edits |
| **Plasmic** | Owns its generated files (`plasmic/PlasmicButton.tsx`); you own the wrapper. | Regenerates its own files on `plasmic sync`. Never rewrites your hand-written wrapper. | N/A (studio + CLI sync) | Editing your files |
| **Webflow / Framer / Builder.io** | Own data model throughout. | Webflow exports one way; Framer refuses to export at all; Builder generates new code. | Own canvas | Round-tripping into hand-written source |

### Click-to-source and agent-context tools

| Tool | Element identity | Writes real source? | Attachment | Needs a build transform? |
|---|---|---|---|---|
| **vite-plugin-vue-inspector** | Primary: vnode positions recorded from compiled render output via Vite source maps, held in a JS-side WeakMap. Fallback: `data-v-inspector="path:line:col"`. | No, opens your editor | Two Vite plugins + injected client script | **Yes** |
| **code-inspector** (zh-lx) | `data-insp-path="<file>:<line>:<col>:<tag>"` | Not directly; hands an exact `file:line:col` to Claude Code / Codex / opencode, which then writes | vite / webpack / rspack / esbuild / turbopack / mako plugin | **Yes** |
| **LocatorJS** (`@locator/babel-jsx`) | `data-locatorjs-id="<projectPath><filePath>::<exprIndex>"`, with line/col in a `window.__LOCATOR_DATA__` side table | No, opens your editor | Babel plugin, webpack loader, npm runtime, or browser extension | **Yes** (its own plugin, or `@babel/plugin-transform-react-jsx-source`) |
| **click-to-react-component** | Injects nothing. Reads React fiber `_debugSource`. | No, opens your editor | npm component | **Yes** (`@babel/plugin-transform-react-jsx-source`) |
| **vite-plugin-react-click-to-component** | Same, plus a Vite transform that string-patches React 19's minified `jsx-dev-runtime` to re-thread `source` | No, opens your editor | Vite plugin | **Yes** |
| **lovable-tagger** | v1.0.19: five `data-component-*` attributes. v1.3.3: no DOM attribute, a `Symbol` property on the node plus a `file:line:col` WeakRef map | Host does | Vite plugin aliasing `react/jsx-dev-runtime` | **Yes** |
| **stagewise** | XPath + tagName + attributes + `innerText` + ~45 computed styles + pseudo-elements + parent/sibling/child summary + React component *names* + screenshot. Serialised to a `.swdomelement` JSON blob. | **Yes** - the agent has `write` / `multiEdit` | Electron browser driving the page over CDP. Nothing installed in the project. | **No** |
| **Dosmos** | Three-tier ladder: `data-dib-source` / `data-inspector-*`, then React fiber `_debugSource`, then a scored signal bundle | Yes, via your CLI agent; also an in-app editor | Electron webview loading your dev server URL | **No** for the third tier |
| **browser-tools-mcp** | `tagName`, `id`, `className`, `textContent` (100 chars), attributes, `innerHTML` (500 chars) from DevTools `$0` | No (the agent may) | Chrome extension + MCP server | **No** |

---

## The finding that matters most

**Which approaches require mutating source or the build to work at all?**

**Cannot work without a build-time transform** (the identity does not exist until something compiles it into being): vite-plugin-vue-inspector, code-inspector, LocatorJS, click-to-react-component, vite-plugin-react-click-to-component, lovable-tagger, Tempo, Onlook, react-dev-inspector. For all of these, a hand-written `.html` file is not merely unsupported, it is unreachable - there is no compile step to hook.

**Cannot work without mutating the user's files on disk**: **Onlook alone**, and it is verifiable in third-party public repositories. Its `data-oid` attributes are written by `CodeFileSystem.writeFile` and, in the current web product, never removed ([`code-fs.ts`](https://github.com/onlook-dev/onlook/blob/423e2e924366419e418ee049093872d535eea41a/packages/file-system/src/code-fs.ts)). GitHub code search returns thousands of `.tsx` hits for `data-oid`, for example [`timeline-studio/promo/src/pages/FAQ.tsx`](https://github.com/chatman-media/timeline-studio/blob/main/promo/src/pages/FAQ.tsx) carrying `data-oid=".h:r10d"`. Pinegrow is a partial case: ordinary visual editing injects nothing durable, but its Pro features (components, master pages, CMS editable areas) deliberately persist `data-pgc-*` into the HTML as their storage format ([Pinegrow CMS docs](https://pinegrow.com/docs/pinegrow-pro/cms/)): "Information about editable areas and components is stored in data-pgc-* attributes directly in the HTML code."

**Mutates a served or in-memory copy only, never the file**: **Pinegrow** (`data-pg-id`), **Utopia** (`data-uid`), **Tempo** (`tempo-<uuid>` class), **Webstudio** (`data-ws-id`, but there is no user source in the first place).

**Can identify the element from the rendered DOM alone, with no transform anywhere**: **stagewise**, **Dosmos** (third tier), **browser-tools-mcp**, **Polypane** (which then declines to write), **Chrome DevTools Workspaces** (for CSS, which needs no element identity at all), and **webtweak**.

### Verdict: is Fingerprint-style matching unusual, naive, or the harder-but-better path?

**It is none of the three cleanly, and the honest answer is worth more than a flattering one.**

It is **not unusual**. Two projects arrived independently at the same bundle, and one of them (Dosmos) has already built the deterministic weighted matcher that webtweak 1.0 wants, in about 200 lines. That is strong evidence the approach is buildable and that the design instincts in ADR-0001 were sound.

It is **not naive** either. The people who chose it chose it deliberately and articulated why. stagewise's entire architecture is a bet that a rich enough DOM snapshot beats a build plugin you have to talk every user into installing - it ships no vite, webpack or babel plugin at all, and its React handling deliberately carries component names but no `_debugSource`. Dosmos's matcher does cross-signal corroboration (`// The strongest signal that we found the RIGHT file is INDEPENDENT signals agreeing on it`), route-aware scoring that demotes `layout.tsx`, and a confidence gap that opens a "wrong file?" picker when the top two files are close - which is the same "ask, do not guess" discipline as reconcile step 3.

But it is **not the harder-but-better path in general**. It is the harder path, and it is better *only where the easier one is unavailable*. Every tool that can instrument a build does, and ranks the instrumented answer first: Dosmos labels the stamped tier `// Exact` and the signal tier `// Heuristic`, in that order. The correct framing for webtweak is therefore narrower and stronger than "we chose the noble path": **hand-coded HTML and CSS has no build to instrument, so the tier everyone else falls back to is the only tier that exists, and webtweak is one of very few tools taking that constraint seriously.** Onlook, Tempo, Utopia, Webstudio, code-inspector, LocatorJS and click-to-component are all structurally incapable of opening a plain `.html` file. Pinegrow can, which is exactly why ADR-0001 names it.

The one thing the survey genuinely undermines is the implicit claim that *any* identity injection would violate the founding decision. Pinegrow and Utopia both inject, both strip before writing, and both keep clean files. webtweak controls its own server and already injects the Overlay. Serve-time injection is available, costs nothing on disk, and would convert the whole matching problem from judgement into a lookup.

---

## Per-tool detail

### Pinegrow

The paid incumbent ADR-0001 names, and the only tool in the survey that opens a plain hand-written HTML file and writes it back.

**Element identity.** Direct, via a temporary attribute. The 1.24 release notes state it plainly: "Pinegrow uses data-pg-id attributes internally to map DOM elements to their source-code representation" ([release notes](https://docs.pinegrow.com/release_notes/release-1-24-oct-17-2014/)). The parse-tree node it maps to is `pgParserNode`, described in Pinegrow's own developer documentation as "the source-code representation of the node" ([PinegrowDevelopersDocumentation](https://github.com/Pinegrow/PinegrowDevelopersDocumentation)). Selection is bidirectional: "Select an element on the page to highlight its code in the code editor", and right-clicking in the code editor selects the element in the page view ([code editing docs](https://pinegrow.com/docs/editing/code.html)).

**The attribute never reaches disk.** Same release notes: "These attributes are removed when you save HTML files, so that you get clean code without any Pinegrow artefacts", extended in 1.24 to external preview and to copying from the code view.

**Writes into source.** Plain files, no project format: "Pinegrow works with regular HTML files on your computer... simply open, edit and save HTML files without the need to import or export anything", and "Pinegrow doesn't add any HTML, CSS or JavaScript code to your pages" ([pages docs](https://pinegrow.com/docs/pages/pages.html)). It also reconciles with external editors rather than clobbering: it "compares both versions of the page and only updates the modified elements".

**Formatting is the weak spot, and it is the vendor's own framing.** From the 4.8 release notes: "By default, Pinegrow auto-formats the HTML code using common-sense formatting options. That is an issue for users that prefer to keep their own HTML formatting when editing documents in Pinegrow. Now, the auto-formatting can be disabled in Settings" ([4.8 release notes](https://pinegrow.com/release_notes/release-4-8-31-may-2018/)). With it disabled, Pinegrow still formats elements it inserts, and the maintainer's position is that the user then owns the result. CSS has a three-way setting including "infer from the first rule in the stylesheet". **Comment preservation: NOT ESTABLISHED** - no Pinegrow doc, release note or vendor statement addresses it.

**Attribute injection that does persist.** Three tiers, and precision matters here. `data-pg-id` and the `pg-empty-placeholder` class are internal and removed. `data-pg-name` is written, but only when the user names an element, and "it has no effect outside of Pinegrow" ([element properties](https://pinegrow.com/docs/master-pinegrow/element-properties/)). `data-pgc-*` is written by design and is the storage format for the entire Pro feature set: "Information about editable areas and components is stored in data-pgc-* attributes directly in the HTML code... It adds just a couple of extra characters to the code and makes pages self-contained with pure HTML" ([CMS docs](https://pinegrow.com/docs/pinegrow-pro/cms/)). Individual `data-pgc-*` names: NOT ESTABLISHED.

**Dev server.** Pinegrow runs an internal HTTP server on `127.0.0.1:40001` serving the *unsaved* in-memory document, and the documented live-preview path is to run Browsersync yourself as a proxy in front of it ([live preview docs](https://pinegrow.com/docs/master-pinegrow/using-external-code-editors/live-preview-on-any-device-or-browser-with-browsersync/)). Browsersync can proxy a foreign dev server instead.

**Refuses.** Non-HTML templates: "At the moment only HTML is officially supported. Opening and editing handlebars templates, PHP, ColdFusion, ASP and similar files can have unpredictable consequences and can even lead to corrupted code" ([pages docs](https://pinegrow.com/docs/pages/pages.html)). Server-side or JavaScript web applications, and SASS/LESS, in the remote-editing context ([remote editing docs](https://pinegrow.com/docs/master-pinegrow/edit-remote-websites-and-web-applications/)). No deployment.

**Versus Fingerprint.** Pinegrow does not need a Fingerprint because it renders its own DOM from its own parse of your file, so the correspondence is constructed rather than recovered. That is the architectural difference: Pinegrow owns the render, webtweak observes someone else's.

### Onlook

**Element identity.** `data-oid`, declared alongside `data-oiid` (instance) and `data-odid` (runtime DOM id) in [`packages/constants/src/editor.ts`](https://github.com/onlook-dev/onlook/blob/423e2e924366419e418ee049093872d535eea41a/packages/constants/src/editor.ts).

The value carries no meaning. It is a random 7-character nanoid ([`packages/utility/src/id.ts`](https://github.com/onlook-dev/onlook/blob/423e2e924366419e418ee049093872d535eea41a/packages/utility/src/id.ts)):

```ts
export const VALID_DATA_ATTR_CHARS = 'abcdefghijklmnopqrstuvwxyz0123456789-._:';
const generateCustomId = customAlphabet(VALID_DATA_ATTR_CHARS, 7);
export function createOid(): string {
    return `${generateCustomId()}`;
}
```

File path and line/column live in a separate index at `.onlook/index.json`, keyed by oid.

**It is written into your files on disk.** There is no babel or SWC plugin in the current repository. Injection happens in the filesystem write path ([`packages/file-system/src/code-fs.ts`](https://github.com/onlook-dev/onlook/blob/423e2e924366419e418ee049093872d535eea41a/packages/file-system/src/code-fs.ts)):

```ts
    async writeFile(path: string, content: string | Uint8Array): Promise<void> {
        if (this.isJsxFile(path) && typeof content === 'string') {
            const processedContent = await this.processJsxFile(path, content);
            await super.writeFile(path, processedContent);
        } else {
            await super.writeFile(path, content);
        }
    }
```

with the attribute built in [`packages/parser/src/ids.ts`](https://github.com/onlook-dev/onlook/blob/423e2e924366419e418ee049093872d535eea41a/packages/parser/src/ids.ts). This is verifiable in the wild: [`timeline-studio/promo/src/pages/FAQ.tsx`](https://github.com/chatman-media/timeline-studio/blob/main/promo/src/pages/FAQ.tsx) has committed `data-oid=".h:r10d"` and `data-oid="jnnz7gi"`, matching that exact alphabet.

**The scheme changed twice**, and the direction is the opposite of everyone else's. The original Electron-era design was a build-time babel/SWC plugin emitting `data-onlook-id` whose value was a gzip-and-base64 `TemplateNode` carrying file path and line/column ([`plugins/babel/src/index.ts`](https://github.com/onlook-dev/desktop/blob/a3685a49bdb9ace3708ee38464874b097e2485d3/plugins/babel/src/index.ts)) - compiled output only, files untouched. Late Electron switched to writing random oids on run and removing them on stop. The current web product writes them and never removes them. The architecture doc still describes the retired design, saying identity is injected "at build-time" ([architecture.mdx](https://github.com/onlook-dev/onlook/blob/423e2e924366419e418ee049093872d535eea41a/docs/content/docs/developers/architecture.mdx)), which no longer matches the code.

**Writes into source.** Babel AST edits, then a full file re-print with `retainLines: true` and comments on, then Prettier unconditionally ([`parse.ts`](https://github.com/onlook-dev/onlook/blob/423e2e924366419e418ee049093872d535eea41a/packages/parser/src/parse.ts), [`prettier/index.ts`](https://github.com/onlook-dev/onlook/blob/423e2e924366419e418ee049093872d535eea41a/packages/parser/src/prettier/index.ts)). Comments survive; hand formatting does not - their own test fixture takes 4-space input to 2-space output.

**Dev server.** Project runs in a cloud container, shown in an iframe, driven by a preload script over penpal. It installs itself by editing your files twice: an Onlook `<Script>` into your root layout ([`code-edit/layout.ts`](https://github.com/onlook-dev/onlook/blob/423e2e924366419e418ee049093872d535eea41a/packages/parser/src/code-edit/layout.ts)) and properties into your `next.config` / `vite.config` / `webpack.config` ([`code-edit/next-config.ts`](https://github.com/onlook-dev/onlook/blob/423e2e924366419e418ee049093872d535eea41a/packages/parser/src/code-edit/next-config.ts)).

**Refuses.** Next.js plus Tailwind in practice ([README](https://github.com/onlook-dev/onlook/blob/423e2e924366419e418ee049093872d535eea41a/README.md)). Plain HTML and CSS entirely: the instrumentation gate is `/\.(jsx?|tsx?)$/i`, the parser only visits `JSXOpeningElement`, and styles are emitted as Tailwind classes. React Fragments are skipped. An element with no oid is refused rather than guessed - `getStyleRequests` throws `'No oid found for style change'`. There is no "known limitations" document.

**Versus Fingerprint.** The strict opposite. Onlook buys perfect identity by permanently altering the artefact it is editing, and has no fallback at all when the attribute is missing.

### Tempo

**Element identity.** Not a data attribute. A CSS class `tempo-<uuid>` appended to `className`, plus a `tempoelementid` prop. From the readable babel plugin at [unpkg 2.0.34](https://unpkg.com/tempo-devtools@2.0.34/dist/babel-plugin/index.js):

```js
const UUID5_NAMESPACE = "1b671a64-40d5-491e-99b0-da01ff1f3341";
const getNextSeed = () => {
    const newSeed = `${filename}${gen_number}`;
    gen_number += 1;
    return newSeed;
};
...
        JSXOpeningElement(path) {
            const uuidToAssign = `tempo-${(0, uuid_1.v5)(getNextSeed(), UUID5_NAMESPACE)}`;
```

So the id is `uuid5(relativeFilePath + Nth JSX element in that file)` against a hard-coded namespace, so that the compiler and Tempo's backend derive the same value independently. The consequence is that inserting or deleting an element renumbers everything after it in that file, which is why the client carries a `prevIdToNewIdMap` and an `applyCodebaseIdChanges` on every change-ledger item ([changeLedgerTypes.d.ts](https://unpkg.com/tempo-devtools@2.0.109/dist/channelMessaging/changeLedgerTypes.d.ts)).

**Compiled output only.** The transform is gated on `NEXT_PUBLIC_TEMPO`, set by Tempo's own runner ([`run.sh`](https://unpkg.com/tempo-devtools@2.0.109/bin/run.sh)), so the ids are absent from a normal build. A real Tempo-built project committed to GitHub, [`090hn/fashion-ai-studio`](https://github.com/090hn/fashion-ai-studio), contains zero `tempo-<uuid>` classes and zero `tempoelementid` occurrences.

**There is a DOM-only fallback layer**, which is the interesting part for webtweak. Every node also gets a structural `uniquePath` - the chain of child indices from `<body>`, computed with no injected marker - and identity is the triple `{codebaseId, storyboardId, uniquePath}` where `codebaseId` is explicitly allowed to be empty: "If codebase ID is undefined then it doesn't exist in our codebase, but is still a valid lookup" ([tempoElement.js](https://unpkg.com/tempo-devtools@2.0.109/dist/channelMessaging/tempoElement.js)). `data-testid` is also accepted as an alternative identity.

**Writes into source.** Server-side and closed. Edits are POSTed as semantic mutations to `canvases/${canvasId}/parseAndMutate/mutate/{styling,addJsxElement,moveJsxElement,removeJsxElement,wrapInDiv,editText}`. **Whether it re-prints an AST or splices, and whether formatting and comments survive: NOT ESTABLISHED.**

**Dev server.** A `swcPlugins` entry the user commits to `next.config.js` ([TempoLabsAI/next-swc-ccp](https://github.com/TempoLabsAI/next-swc-ccp/blob/main/next.config.js)), an iframe plus postMessage, and bidirectional rsync over SSH into a Tempo container at `/app` ([`sync.sh`](https://unpkg.com/tempo-devtools@2.0.109/bin/sync.sh)).

**Refuses.** React only, structurally. Plain HTML and CSS get no id and no fiber. `node_modules` is skipped. Next.js 15+ is marked "Not yet supported, coming soon" and the package has not been published since 2025-07-17.

### Utopia

The most sophisticated identity scheme in the survey, and the closest thing to a proof that serve-time injection works.

**Element identity.** `data-uid`, and it is derived, not assigned ([`parser-printer-parsing.ts`](https://github.com/concrete-utopia/utopia/blob/9b605c1bfb5e9c74c9bb8c2102ca5bd9b515ba77/editor/src/core/workers/parser-printer/parser-printer-parsing.ts#L3055)):

```ts
  const hash = hashObject({
    fileName: sourceFile.fileName,
    bounds: getBoundsOfNodes(sourceFile, originatingElement),
    name: elementName,
    props: cleansedProps,
  })
  const uid = generateConsistentUID(hash, alreadyExistingUIDs)
```

`hashObject` is murmur128 ([`hash.ts`](https://github.com/concrete-utopia/utopia/blob/9b605c1bfb5e9c74c9bb8c2102ca5bd9b515ba77/editor/src/core/shared/hash.ts)), truncated to 32 characters, with a random UUID only on collision. Note what it hashes: file, source range, element name and cleansed props. **That is a content fingerprint, computed over source rather than over the DOM** - conceptually a sibling of webtweak's Fingerprint, derived from the other end.

The injector is Utopia's TypeScript-based parser, not Babel; a narrow Babel plugin handles only JSX nested inside arbitrary JS expressions, and writes into a separate model field (`javascriptWithUIDs`) that the printer never emits ([`parser-printer-transpiling.ts`](https://github.com/concrete-utopia/utopia/blob/9b605c1bfb5e9c74c9bb8c2102ca5bd9b515ba77/editor/src/core/workers/parser-printer/parser-printer-transpiling.ts)).

**Stripped on save.** [`parser-projectcontents-utils.ts`](https://github.com/concrete-utopia/utopia/blob/9b605c1bfb5e9c74c9bb8c2102ca5bd9b515ba77/editor/src/core/shared/parser-projectcontents-utils.ts) sets `const shouldStripUids = PRODUCTION_ENV || !isFeatureEnabled('Debug - Print UIDs')`, and the printer skips the prop:

```ts
        const skip = stripUIDs && propEntry.key === 'data-uid'
        if (!skip) {
```

Identity across edits is preserved not by persistence but by reconciliation: [`uid-fix.ts`](https://github.com/concrete-utopia/utopia/blob/9b605c1bfb5e9c74c9bb8c2102ca5bd9b515ba77/editor/src/core/workers/parser-printer/uid-fix.ts) copies old-parse uids onto structurally corresponding new-parse elements. There is also a second identity channel for text: invisible-unicode steganography embedding `{filePath, startPosition, endPosition, originalString}` into rendered string literals ([`stegano-text.ts`](https://github.com/concrete-utopia/utopia/blob/9b605c1bfb5e9c74c9bb8c2102ca5bd9b515ba77/editor/src/core/shared/stegano-text.ts)).

DOM lookup uses `data-uid` plus a `data-path` carrying the ElementPath, with `React.createElement` globally monkey-patched so identity survives component boundaries and fragments ([`canvas-react-utils.ts`](https://github.com/concrete-utopia/utopia/blob/9b605c1bfb5e9c74c9bb8c2102ca5bd9b515ba77/editor/src/utils/canvas-react-utils.ts)).

**Writes into source.** Full re-print from the model via the TypeScript printer, then Prettier. Comments are modelled on parse and re-emitted as synthesized comments; code Utopia does not model becomes `UNPARSED_CODE` and is re-emitted verbatim. There is a dedicated round-trip fidelity suite - but every assertion pre-normalises through Prettier, which is itself the admission that raw formatting is not preserved.

**Dev server.** There is no dev server. Babel standalone plus TypeScript plus BrowserFS in a Web Worker, npm dependencies from a hosted packager service, and the canvas rendered same-document rather than in an iframe (which is what makes the `createElement` monkey-patch viable).

**Refuses.** From the [readme](https://github.com/concrete-utopia/utopia/blob/9b605c1bfb5e9c74c9bb8c2102ca5bd9b515ba77/readme.md): "you won't be able to edit projects in the file system on your machine if you install it locally". It also refuses to auto-focus map-generated elements, with the reason given in code (a chicken-and-egg with the element path tree). **A published rationale for choosing `data-uid`: NOT ESTABLISHED** - `docs/` holds only an architecture overview and `rfcs/` only a template; the reasoning exists solely as inline comments.

### Webstudio

**Element identity.** A nanoid `Instance.id` in a flat `Map<id, Instance>` ([`packages/sdk/src/schema/instances.ts`](https://github.com/webstudio-is/webstudio/blob/ca08919b130625deacfeca02cbaab08c8fc74063/packages/sdk/src/schema/instances.ts)), persisted as JSON strings on a Postgres `Build` row. The canvas carries `data-ws-id` and `data-ws-selector` (a comma-joined ancestor id chain, which is what disambiguates the same instance rendered in a collection or slot) ([`props.ts`](https://github.com/webstudio-is/webstudio/blob/ca08919b130625deacfeca02cbaab08c8fc74063/packages/react-sdk/src/props.ts), [`dom-utils.ts`](https://github.com/webstudio-is/webstudio/blob/ca08919b130625deacfeca02cbaab08c8fc74063/apps/builder/app/shared/dom-utils.ts)).

**Writes into source.** No. Code is generated one way into `__generated__/` by the CLI ([`prebuild.ts`](https://github.com/webstudio-is/webstudio/blob/ca08919b130625deacfeca02cbaab08c8fc74063/packages/cli/src/prebuild.ts)) with the header "This is a auto generated file for building the project". Nothing parses generated JSX back into instances. The only JSX parser accepts Webstudio's own restricted authoring DSL for clipboard paste.

It does, however, import **pasted** HTML and CSS into real instances and styles using parse5 and css-tree ([`html.ts`](https://github.com/webstudio-is/webstudio/blob/ca08919b130625deacfeca02cbaab08c8fc74063/packages/project-build/src/runtime/html.ts)). There is no URL crawler and no whole-site importer.

**Dev server.** Its own hosted `/canvas` iframe, never a user-supplied localhost URL.

**Refuses.** An explicit written policy: **NOT ESTABLISHED**. The one-way-ness is enforced architecturally rather than declared - there are no ADRs and the CLI package has no README.

**Versus Fingerprint.** Not a comparison so much as the opposite problem. Webstudio has no user source to locate anything in, so identity is authoritative by construction. It is in this survey to mark the boundary of what "visual editor" can mean.

### Polypane

**Element identity.** Essentially none. Editing is live-DOM only: the Elements panel edits selectors, values, attributes and text, and the HTML editor "lets you edit the full HTML of the element, including its children", implemented by "carefully looping over the children and updating them in place, rather than rebuilding the entire DOM tree" ([Elements panel docs](https://polypane.app/docs/elements-panel/), [Polypane 24 release post](https://polypane.app/blog/polypane-24-recording-3-d-view-custom-tab-colors-and-html-editing/)). The Style tab shows a rule's stylesheet "and it's line number when available", which is standard Chromium origin display rather than a project mapping. **That Polypane can resolve a DOM element to a location in authored source: NOT ESTABLISHED.**

**Writes into source.** No, and the documented exit path is the clipboard - right-click to copy "just the selector, just the declarations, the entire ruleset, an individual declaration, property or value". Disabled rules return on reload. Snippets persist inside Polypane and export as JSON, never to project files ([snippets docs](https://polypane.app/docs/snippets/)).

**Method caveat:** Polypane's documentation never says "we do not write to your files" in those words. The boundary is established by absence across the whole doc set plus the affirmative copy-out workflow. Note also that "Projects" and "Workspaces" are not filesystem concepts - a Project is a set of tabs and settings, a Workspace is a saved pane layout ([projects](https://polypane.app/docs/projects/), [workspaces](https://polypane.app/docs/workspaces/)).

**Dev server.** It is a Chromium browser, so you point it at localhost. The only filesystem touch is one-directional read: select a directory and it will "watch your file system and reload CSS automatically on every save", positioned as "a direct replacement" for Browsersync ([live reloading docs](https://polypane.app/docs/live-auto-reloading/)). Editor integrations are launch-only.

**Versus Fingerprint.** Polypane is the tool webtweak would be if it stopped at preview. It confirms that the browser side of this is not the hard part.

### Codux

**Discontinued.** The homepage now reads "The Codux journey may be over... But something Dazzling is coming next!" ([codux.com](https://www.codux.com/)). The last release is v15.42.0 from 5 Feb 2025 ([release notes](https://www.codux.com/release-notes), [codux-versions releases](https://github.com/wixplosives/codux-versions/releases)). No dated formal shutdown announcement found; end-of-life date **NOT ESTABLISHED**.

**Vendor claims.** Code is "the ultimate source of truth", visual changes are "immediately written to your code files", and code edits appear in the visual interface ([FAQ](https://www.codux.com/faq)). Scope is React plus TypeScript with CSS, CSS Modules, SCSS, Tailwind or Stylable. Canvas-to-source mapping is documented only as "Jump directly to the relevant line of code from any element selected on stage" ([features](https://www.codux.com/features)); the mechanism is **NOT ESTABLISHED**.

**Formatting: NOT ESTABLISHED as a claim.** The only evidence is a release note about using the project's own Prettier version, which implies normalisation rather than preservation.

**Refuses.** The real constraint is boards: per the Codux knowledge base, "Codux currently only supports visualizing and editing statically analyzable board objects". ⚠️ That quote comes from the help.codux.com search index rather than a page rendered end to end - treat as vendor-sourced but unverified in context.

### Chrome DevTools Workspaces

Directly relevant because it is the one mainstream tool that writes hand-authored CSS to disk with no instrumentation whatsoever.

Mapping is folder-based, not source-map-based: connect a local folder and green dots mark files where "DevTools has established a mapping between the network resources of the page, and the files in the folder". Source maps are the fallback for build output, not a prerequisite, so plain hand-written CSS with no build step is the easy case. **The asymmetry is the finding: CSS and JS edits save to disk, but "DevTools doesn't save changes to DOM that you make in the Elements panel"** ([Workspaces docs](https://developer.chrome.com/docs/devtools/workspaces)).

Auto-connect is real: your dev server serves `/.well-known/appspecific/com.chrome.devtools.json` containing `{"workspace": {"root": "<absolute path>", "uuid": "<v4 uuid>"}}` and DevTools offers a Connect button. It is "designed exclusively for local development environments and only works when your application is served from localhost" ([automatic workspaces](https://developer.chrome.com/docs/devtools/automatic-workspaces)). The introducing Chrome version: NOT ESTABLISHED. This is a directly copyable pattern for a future webtweak that wants to sit behind someone else's dev server.

### stagewise

**The clearest DOM-only precedent in the survey, and the closest architectural relative to webtweak.**

**Element identity.** No build-time attribute anywhere. The repository contains no vite, webpack or babel plugin. Identity is a serialised DOM snapshot ([`shared/selected-elements/index.ts`](https://github.com/stagewise-io/stagewise/blob/main/apps/browser/src/shared/selected-elements/index.ts)): `tagName`, a positional XPath computed live, `attributes`, `ownProperties`, `innerText`, `boundingClientRect`, about 45 computed styles, pseudo-elements, interaction state, and a flattened parent/sibling/child tag summary. Bounded deliberately: children sliced to 5, siblings to 10, recursion depth 10, `innerText` to 512 characters, XPath to 1024.

React information is carried but is an enrichment, not a requirement, and crucially **carries no source location** ([`shared/selected-elements/react.ts`](https://github.com/stagewise-io/stagewise/blob/main/apps/browser/src/shared/selected-elements/react.ts)) - only `componentName`, truncated `serializedProps` and `isRSC`. There is no `_debugSource`, no `fileName`, no `lineNumber` in stagewise's React handling at all.

**The hand-off artefact is a file, exactly like the edits file.** Selections serialise to `.swdomelement` JSON blobs on disk, described in the schema as "the serialisation format for selected DOM elements", and the agent's environment preamble lists it as one of two blob types alongside `.textclip`. The agent reads the raw JSON as a text part and greps the codebase itself.

**Writes into source.** Yes - the agent has `read`, `glob`, `grepSearch`, `multiEdit` and `write`, with a documented default flow of `read` then `multiEdit`.

**Attachment.** An Electron browser driving the page over the Chrome DevTools Protocol, with a preload script in an isolated world and a second pass in the main world to reach React internals. Nothing is installed in the target project.

**Reserved seam.** A `codeMetadata` field exists (`relation`, `relativePath`, `startLine`, `content`) and is the one place an exact locator could live, but the only writer initialises it empty. **That anything populates it: NOT ESTABLISHED.** Treat it as a reserved slot.

**Versus Fingerprint.** Same bet, richer bundle, and it has already made the choice webtweak is reconsidering - it added no transform even after pivoting to a full agentic browser. Its bundle is a superset of webtweak's in DOM context (XPath, computed styles, pseudo-elements, interaction state, screenshot) and a subset in one respect that matters: it has no equivalent of `openTag`, the clean opening tag that matches source bytes rather than rendered state.

### Dosmos

Formerly "Design In The Browser". MIT-licensed Electron app, [assentorp/dosmos](https://github.com/assentorp/dosmos). This is the tool whose architecture maps most directly onto webtweak's problem, and it has already built the deterministic matcher.

**A three-tier ladder, labelled in its own comments** ([`src/annotation/injected-script.ts`](https://github.com/assentorp/dosmos/blob/main/src/annotation/injected-script.ts)):

```js
        var dataSource = findDataSource(el);
        if (dataSource) {
          // Exact: a build-time plugin stamped the source location onto the DOM.
          ...
        } else if (reactSource) {
          // Exact: React 18 _debugSource (absent on React 19 / server components).
          ...
        } else {
          // Heuristic: send every signal we can scrape so the main process can
          // rank candidate files (component name, own text, heading, attrs, URL).
```

Tier one reads `data-dib-source="relative/path.tsx:line:col"` or the react-dev-inspector convention, walking up to 12 ancestors. Tier two reads React fiber `_debugSource`. Tier three is the signal bundle, and its helper carries a comment that could have been lifted from webtweak's own reconcile notes: `// The element's own (direct) text, ignoring nested children - more specific for grep than the whole subtree's text`, truncated to 80 characters, the same figure webtweak uses.

**The matcher is the interesting part** ([`src/main/ipc.ts`](https://github.com/assentorp/dosmos/blob/main/src/main/ipc.ts)). It fires around 18 concurrent greps and scores candidates on a base-plus-adjustment scale: component name with a filename match 95, data attributes 90, id 88, heading text 84, own text 80, full subtree text 56, two-word phrase 46, single long word 34. Text patterns are built from alphanumeric tokens joined by `.{0,16}` gaps so they tolerate HTML entities, JSX expressions and quote characters - "Far more robust than exact text". Route-aware scoring adds 30 for a file under the page's URL segment and subtracts 40 for `layout.tsx` and friends.

Then it does what webtweak's reconcile step 3 asks Claude to do:

```ts
    // Any single grep strategy can land in the wrong file (a loose text run also
    // appears in a shared component; a common component name is defined in two
    // places). The strongest signal that we found the RIGHT file is INDEPENDENT
    // signals agreeing on it
```

Distinct signal classes (`struct`, `attr`, `content`, `route`) agreeing on a file are worth 45 each beyond the first. Confidence is the score gap between the winning file and the next different file, and a small gap opens a "wrong file?" picker rather than committing - the README calls this "Smart source matching... with a 'wrong file?' picker for close calls".

**One documentation discrepancy worth recording.** The vendor page claims "Click an element and your AI coding agent receives the exact source file and line number to change" ([dosmos.app](https://dosmos.app/)). For the heuristic tier that is not what the code does, and the prompt actually sent to the agent contains neither ([`src/shared/format-prompt.ts`](https://github.com/assentorp/dosmos/blob/main/src/shared/format-prompt.ts)):

```ts
    const parts = [`<${element.tagName}>`];
    if (element.text) parts.push(`"${element.text}"`);
    if (element.attributes) parts.push(`[${element.attributes}]`);
    prompt = `- ${parts.join(' ')}: ${request}`;
```

The rich matcher drives Dosmos's own "Edit code" panel; the CLI agent gets tag, text, attributes and a screenshot path. Its `ElementInfo` type is `{ tagName, id, className, textContent, outerHTML }` - a Fingerprint minus `siblingIndex` and the positional selector.

**Attachment.** Electron with a `webview` loading your dev server URL, plus a built-in static server with hot reload for its starter projects. Nothing installed in your project.

**Versus Fingerprint.** The closest peer, and the most useful one. It proves the deterministic matcher webtweak 1.0 wants is buildable at modest size, and it independently arrived at the same priority order, the same 80-character text truncation, the same preference for own-text over subtree text, and the same refusal to guess when two candidates are close.

### The click-to-source plugin ecosystem

All of these open your editor at a location rather than writing anything, with one exception noted below. All of them require a build-time transform. They are in this survey to establish that the transform-based camp is the mainstream, and to show where it is heading.

**vite-plugin-vue-inspector** ([repo](https://github.com/webfansplz/vite-plugin-vue-inspector)) has two mechanisms, and the DOM attribute is now only the fallback. The README states it directly: "It records source locations from Vue's compiled render output with Vite source maps, and uses dev-only `data-v-inspector` DOM markers as a fallback for cases such as Vapor mode or nodes missed by VNode instrumentation." The primary path wraps vnode factory calls with a `_vueInspectorRecord(line, column, ...)` recorder and keeps positions in a WeakMap keyed by the vnode's props object, actively deleting the attribute from props. The fallback path injects `data-v-inspector="path:line:column"` via `@vue/compiler-dom` plus MagicString. Both plugins are dev-only (`command === 'serve'`) and Vue 3 plus Vite only. It opens your editor via `__open-in-editor`; it writes nothing.

**lovable-tagger** made the identical move independently. Version 1.0.19 injected five `data-component-*` attributes including a URI-encoded JSON blob of the element's text and className. Version 1.3.3 aliases `react/jsx-dev-runtime` and stamps a `Symbol.for("__jsxSource__")` property on the node plus a `file:line:col` keyed WeakRef map, with no DOM attribute at all. Read from published dists on unpkg; no public repository found.

That is two projects, independently, moving identity **off the DOM and into a JS-side map**. Worth noting for a webtweak that considers serve-time injection: the field has already discovered that DOM pollution is avoidable even when you keep the transform.

**code-inspector** ([zh-lx/code-inspector](https://github.com/zh-lx/code-inspector)) injects one attribute carrying everything: `data-insp-path="<filePath>:<line>:<column+1>:<tagName>"`. It supports vite, webpack, rspack, esbuild, turbopack and mako, with separate transforms for jsx, vue, vue-node, vue-pug, svelte, astro and mdx, and is dev-gated. It now routes to Claude Code, Codex or opencode - handing the agent an **exact** `file:line:col` from the build-time attribute. That makes it the cleanest architectural contrast to stagewise and Dosmos: same destination, opposite starting point. It is also where click-to-react-component's own issue tracker now sends people.

**LocatorJS** ([infi-pc/locatorjs](https://github.com/infi-pc/locatorjs)) has two schemes. Its babel plugin injects `data-locatorjs-id="<projectPath><filePath>::<expressionIndex>"` with line and column in a `window.__LOCATOR_DATA__` side table, not in the attribute. Its React adapter, used by the browser extension, needs no LocatorJS plugin at all and reads fiber `_debugSource` - but the extension README is explicit that this depends on `babel-plugin-transform-react-jsx-source` being present, "If you don't have babel-plugin-transform-react-jsx-source, you should set it up manually." There is no DOM-only mode.

**click-to-react-component** ([ericclemmons/click-to-component](https://github.com/ericclemmons/click-to-component)) injects nothing and reads fiber `_debugSource`, with a DevTools-hook-first fiber lookup. Confirmed broken on React 19 (open [issue #99](https://github.com/ericclemmons/click-to-component/issues/99), no fix), and [issue #104](https://github.com/ericclemmons/click-to-component/issues/104) is titled "This repo is no longer maintained, use code-inspector instead". The fix exists in a different package: **vite-plugin-react-click-to-component** string-patches React 19's minified `jsx-dev-runtime` bundle to re-thread `source` into `_debugInfo`. That is a notably fragile transform, and a useful data point on how much the transform-based camp will pay to keep an exact locator.

**react-dev-inspector** ([zthxxx/react-dev-inspector](https://github.com/zthxxx/react-dev-inspector)) requires `@babel/plugin-transform-react-jsx-source` or its own optional babel plugin, plus dev-server middleware to launch the editor. Its `data-inspector-relative-path` / `data-inspector-line` / `data-inspector-column` convention is the one Dosmos reads in its first tier. Exact attribute enumeration from its own README: NOT ESTABLISHED.

**browser-tools-mcp** ([AgentDeskAI](https://github.com/AgentDeskAI/browser-tools-mcp)) is the thin end of the DOM-only camp: a Chrome extension that hooks `chrome.devtools.panels.elements.onSelectionChanged`, reads `$0` for `tagName`, `id`, `className`, `textContent` (100 chars), attributes and `innerHTML` (500 chars), and hands the JSON to an agent over MCP. No transform, no source location, no XPath, no parent context.

### Adjacent prior art

**Self-healing test locators** (Testim "Smart Locators", Mabl "Adaptive Element Locators") solve a very similar problem: identify a DOM element robustly from a weighted bundle of attributes, text, structure and position, and rank candidates by confidence. ⚠️ These are **vendor marketing claims and third-party summaries, not primary sources** - I could find no published specification of either algorithm, so treat the parallel as suggestive rather than as evidence. It is worth naming only because it means the weighted-bundle idea has a commercial track record in an adjacent field.

**Unique-selector generation** ([antonmedv/finder](https://github.com/antonmedv/finder)) generates "shortest", "unique" and "stable and robust" CSS selectors for a DOM node. It makes no claim about surviving page changes. It is the baseline webtweak deliberately does not rely on - the Fingerprint demotes its positional selector to a tiebreaker for exactly this reason, and Dosmos's prompt drops its generated selector entirely.

**Source-preserving parsing.** If webtweak does write HTML, [parse5's `ElementLocation`](https://parse5.js.org/interfaces/parse5.Token.ElementLocation.html) gives zero-based `startOffset`/`endOffset` plus separate `startTag`, `endTag` and per-attribute locations, which is enough for byte-offset splices that leave every other byte of the file untouched. Webstudio already uses parse5 for its HTML paste importer. PostCSS's `raws` do the equivalent for CSS.

---

## Sources

Repositories read at pinned commits: [onlook-dev/onlook](https://github.com/onlook-dev/onlook) `423e2e9`, [onlook-dev/desktop](https://github.com/onlook-dev/desktop) `a3685a4`, [concrete-utopia/utopia](https://github.com/concrete-utopia/utopia) `9b605c1`, [webstudio-is/webstudio](https://github.com/webstudio-is/webstudio) `ca08919`, [webfansplz/vite-plugin-vue-inspector](https://github.com/webfansplz/vite-plugin-vue-inspector) `65ce7c7`, [infi-pc/locatorjs](https://github.com/infi-pc/locatorjs) `ac4ed50`, [ericclemmons/click-to-component](https://github.com/ericclemmons/click-to-component) `f8be09c`, [stagewise-io/stagewise](https://github.com/stagewise-io/stagewise) `1d727de`, [zh-lx/code-inspector](https://github.com/zh-lx/code-inspector) `22c8d1e`, [assentorp/dosmos](https://github.com/assentorp/dosmos) (HEAD, 2026-08-02).

Published artefacts: [tempo-devtools on unpkg](https://unpkg.com/tempo-devtools@2.0.109/), [TempoLabsAI/next-swc-ccp](https://github.com/TempoLabsAI/next-swc-ccp).

Vendor documentation (primary source for closed products): [Pinegrow docs](https://pinegrow.com/docs/), [Polypane docs](https://polypane.app/docs/), [Codux](https://www.codux.com/), [Chrome DevTools Workspaces](https://developer.chrome.com/docs/devtools/workspaces), [Plasmic codegen guide](https://docs.plasmic.app/learn/codegen-components/), [Webflow code export](https://help.webflow.com/hc/en-us/articles/33961386739347-How-do-I-export-my-Webflow-site-code), [Framer export answer](https://www.framer.com/help/articles/can-i-export-my-website-to-html-and-self-host-it/), [Builder.io Visual Copilot](https://www.builder.io/blog/figma-to-code-visual-copilot).
