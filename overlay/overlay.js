/* webtweak Overlay - injected into the target page, not part of any source.
 *
 * Captures visual edits as Patches and POSTs them to the local server, which
 * writes them to <page>.webtweak.json for Claude to reconcile. The Overlay only
 * captures *intent* - it never rewrites source. See CONTEXT.md / ADR-0001.
 *
 * Note: the `wt-` class prefix is load-bearing - fingerprint() strips classes
 * starting with `wt-`, so the Overlay must never add a non-`wt-` class to a page
 * element or it would pollute the captured identity.
 */
(function () {
  "use strict";

  // Idempotent: a second injection (SPA soft-nav, double include) is a no-op.
  if (window.__WEBTWEAK_ACTIVE__) return;
  window.__WEBTWEAK_ACTIVE__ = true;

  var CFG = window.__WEBTWEAK__ || {};
  var RESERVED = "/__webtweak__/";

  // Only activate on the target page (not on links the user follows away).
  var here = location.pathname.endsWith("/")
    ? "index.html"
    : decodeURIComponent(location.pathname.split("/").pop() || "index.html");
  if (CFG.target && here !== CFG.target) return;

  // One session per tab, stable across reloads, so re-saving overwrites the same
  // pending Batch rather than orphaning a new one (running-history contract).
  var SKEY = "wt-session-" + (CFG.target || here);
  var SESSION = sessionStorage.getItem(SKEY) ||
    ("s" + Math.random().toString(36).slice(2, 10));
  sessionStorage.setItem(SKEY, SESSION);

  // el -> { changes, _x, _y, origStyle } for every selected/edited element.
  var edited = new Map();
  var selectedEl = null;
  var dirty = false;       // unsaved changes since the last successful save
  var saving = false;      // a save POST is in flight (see save(), localSafe())
  var persisted = false;   // this session has a saved/restored batch on disk to clear
  var missed = [];         // restored patches we couldn't re-locate - preserved across saves
  var interacting = false; // a drag/resize gesture is in progress
  var gestureEndedAt = 0;  // when the last drag/resize finished (see endGesture)

  // A drag or resize is followed by a browser `click` on whatever sits under the
  // release point - typically a child of the element being dragged. Without this
  // the selection silently jumps to that child, so the grips end up on the wrong
  // element and the next resize targets something the user never chose.
  function endGesture() {
    interacting = false;
    gestureEndedAt = Date.now();
    refreshChanges();   // refreshes skipped during the gesture land here
  }
  function clickEndsGesture() {
    // Time-boxed rather than a sticky flag: if a gesture ever ends without a
    // trailing click, the guard must not swallow the user's next real click.
    return Date.now() - gestureEndedAt < 300;
  }
  var undoStack = [];      // stack of batches: each [{el, prop, prev}]
  var redoStack = [];      // inverses of undone batches, cleared by any new edit
  var pendingShape = null; // shape kind awaiting a placement click (place mode)

  function entry(el) {
    var e = edited.get(el);
    if (!e) {
      // origStyle captured on first contact = the authored baseline, used by reset.
      e = { changes: {}, _x: 0, _y: 0, origStyle: el.getAttribute("style") };
      edited.set(el, e);
    }
    return e;
  }
  function record(el, prop, value) {
    entry(el).changes[prop] = value;
    dirty = true;
    // The status line reports the most recent notable thing, and a successful edit
    // supersedes whatever it said - an "ignored invalid" warning has no timer, so
    // without this it sits there through every later edit, reading as current. Safe
    // to clear here: restore() writes `changes` directly and never comes through
    // record(), so its own "restored N of M" notice survives.
    status("");
    refreshChanges();
  }
  // True iff any edited element still holds real changes - the single source of
  // truth for the unsaved-changes (beforeunload) guard, so resets that empty the
  // map don't leave a stale dirty flag.
  function hasRealEdits() {
    var any = false;
    edited.forEach(function (e) { if (Object.keys(e.changes).length) any = true; });
    return any;
  }
  // ---- undo / redo ----------------------------------------------------------
  // Every user edit goes through here, so this is where an abandoned redo branch
  // dies: stepping forward must never splice work the user has moved on from back
  // into the session.
  function pushUndo(batch) {
    undoStack.push(batch);
    redoStack.length = 0;
    refreshHistory();
  }
  // Push a panel-input undo step before mutating changes[prop].
  // Consecutive calls for the same el+prop collapse into one step so typing
  // into a field leaves a single undo step regardless of how many keystrokes.
  function pushUndoWrite(el, prop) {
    var ch = (edited.get(el) || {}).changes;
    var prev = ch ? ch[prop] : undefined;
    var top = undoStack[undoStack.length - 1];
    // Only collapse consecutive PANEL writes of the same prop into one step. A gesture
    // batch (a drag/resize, tagged below) must stay its own step, or a single-axis grip
    // resize followed by typing the same prop would fuse into one undo.
    // The redo branch dies either way: a collapsed keystroke is still a new edit, and
    // after an undo the step it collapses into is one the user has stepped back past.
    if (top && !top.gesture && top.length === 1 && top[0].el === el && top[0].prop === prop) {
      redoStack.length = 0;
      refreshHistory();
      return;
    }
    pushUndo([{ el: el, prop: prop, prev: prev }]);
  }
  // Gesture-batched undo: snapshot the props at gesture start, then at end push one
  // batch for those that actually changed. Shared by shape move + both resize paths.
  function snapshotProps(el, props) {
    var ch = (edited.get(el) || {}).changes || {};
    var snap = {};
    props.forEach(function (p) { snap[p] = ch[p]; });
    return snap;
  }
  function pushGestureUndo(el, props, prev) {
    var ch = (edited.get(el) || {}).changes || {};
    var batch = [];
    props.forEach(function (p) {
      if (ch[p] !== prev[p]) batch.push({ el: el, prop: p, prev: prev[p] });
    });
    if (batch.length) { batch.gesture = true; pushUndo(batch); }  // own undo step, never collapsed
  }
  var MOVE_PROPS = ["left", "top"];                                  // a shape drag
  var RESIZE_PROPS = ["width", "height", "max-width", "min-height"]; // any resize gesture

  // Apply one history batch and RETURN ITS INVERSE, so redo needs no separate
  // recording of forward operations: each step already carries the previous value,
  // and the inverse only needs the current one, captured here as the step is applied.
  // Creation and removal are already exact inverses of each other in this vocabulary,
  // so undoing a creation yields a removal and vice versa - which means applying an
  // inverse returns the original batch, and one applier serves both directions.
  function applyHistory(batch) {
    // Collect unique elements so each element's inline is rebuilt exactly once.
    var els = [], inverse = [];
    batch.forEach(function (u) {
      // Removes the element and its edited entry outright; the inverse puts both back,
      // which needs the parent and following sibling captured before the removal.
      if (u.create) {
        inverse.push({ el: u.el, restore: {
          entry: edited.get(u.el), parent: u.el.parentNode, before: u.el.nextSibling } });
        if (u.el === selectedEl) deselect();
        if (u.el.parentNode) u.el.parentNode.removeChild(u.el);
        edited.delete(u.el);
        return;
      }
      // Puts the element back where it was; the inverse removes it again.
      if (u.restore) {
        if (u.restore.parent) u.restore.parent.insertBefore(u.el, u.restore.before);
        edited.set(u.el, u.restore.entry);
        if (els.indexOf(u.el) < 0) els.push(u.el);
        inverse.push({ el: u.el, create: true });
        return;
      }
      // entry() creates on miss, so undoing past a reset would resurrect a
      // deleted element as a fresh entry - and save it as a patch whose
      // fingerprint is computed on a node no longer in the document.
      var ent = edited.get(u.el);
      if (!ent) {
        if (!document.contains(u.el)) return;      // element is gone; nothing to undo onto
        ent = entry(u.el);
      }
      // The value being replaced IS the inverse's `prev` - including undefined, which
      // both directions read as "this property was not in changes".
      inverse.push({ el: u.el, prop: u.prop, prev: ent.changes[u.prop] });
      if (u.prev === undefined) {
        delete ent.changes[u.prop];
        // rebuildInline only seeds _x/_y when nudge IS in changes; reset manually here.
        if (u.prop === "nudge") { ent._x = 0; ent._y = 0; }
      } else {
        ent.changes[u.prop] = u.prev;
      }
      if (els.indexOf(u.el) < 0) els.push(u.el);
    });
    els.forEach(function (el) {
      rebuildInline(el, edited.get(el));
      if (el === selectedEl) { positionBox(selBox, el); populate(el); }
    });
    // Recomputed in both directions, so the save prompt and the reconcile badge stay
    // honest however far through history the user has stepped.
    dirty = hasRealEdits();
    refreshChanges();
    if (batch.gesture) inverse.gesture = true;   // keep a gesture batch its own step
    return inverse;
  }

  function undo() {
    if (!undoStack.length) { status("nothing to undo"); return; }
    redoStack.push(applyHistory(undoStack.pop()));
    refreshHistory();
    status("undone");
  }
  function redo() {
    if (!redoStack.length) { status("nothing to redo"); return; }
    // Straight onto the undo stack, NOT via pushUndo: stepping forward through
    // history is not a new edit, so it must not clear the branch behind it.
    undoStack.push(applyHistory(redoStack.pop()));
    refreshHistory();
    status("redone");
  }
  // The buttons are the only place history is visible, so they have to be exact.
  function refreshHistory() {
    var u = document.getElementById("wt-undo"), r = document.getElementById("wt-redo");
    if (u) u.disabled = !undoStack.length;
    if (r) r.disabled = !redoStack.length;
  }

  // The value each control was populated with this selection, so an unchanged
  // re-entry (e.g. opening the colour picker on a transparent swatch and clicking
  // the same shown value) is treated as a no-op and not recorded.
  var baselines = {};

  // The editable properties, declared once. The panel markup, the live binding,
  // and the populate-from-computed-style read all derive from this single table,
  // so adding a property is one entry, not three hand-synced lists.
  // `read(cs)` maps a computed style to the control's display value; `unit` (if
  // set) is appended on write; `box` re-fits the selection box after the change.
  var CONTROLS = [
    { group: "Type", id: "wt-ff", prop: "font-family", label: "Font", kind: "text",
      suggest: pageFonts, suggestTitle: "Fonts on this page", suggestPreview: true,
      read: function (cs) { return cs.fontFamily; } },  // full stack, so editing keeps fallbacks
    { group: "Type", id: "wt-fs", prop: "font-size", label: "Size", kind: "number", unit: "px",
      read: function (cs) { return px(cs.fontSize); } },
    { group: "Type", id: "wt-fw", prop: "font-weight", label: "Weight", kind: "select",
      opts: ["100", "200", "300", "400", "500", "600", "700", "800", "900"],
      read: function (cs) { return String(parseInt(cs.fontWeight, 10) || 400); } },
    { group: "Type", id: "wt-lh", prop: "line-height", label: "Line", kind: "text",
      // Stepper rather than a number input, because a number input could hold none of
      // `normal`, `1.4em` or `24px` - all of which real stylesheets author and all of
      // which this field accepts today.
      step: 0.1,
      // show the unitless ratio (computed resolves to px); writing a bare number keeps it unitless
      read: function (cs) {
        if (cs.lineHeight === "normal") return "normal";
        var fs = parseFloat(cs.fontSize), lh = parseFloat(cs.lineHeight);
        return (fs > 0 && lh > 0) ? String(+(lh / fs).toFixed(2)) : cs.lineHeight;
      } },
    // Tracking is a value nobody holds in their head, so it gets the same picker the
    // Font and Shadow fields use - presets, still typeable. Deliberately not a closed
    // <select>: an arbitrary em or px value has always worked here.
    { group: "Type", id: "wt-ls", prop: "letter-spacing", label: "Spacing", kind: "text",
      suggest: function () { return SPACING_PRESETS; }, suggestTitle: "Tracking presets",
      suggestPreview: true,   // each row is tracked at its own value
      read: function (cs) { return cs.letterSpacing === "normal" ? "normal" : cs.letterSpacing; } },
    { group: "Type", id: "wt-align", prop: "text-align", label: "Align", kind: "align",
      read: function (cs) { var a = cs.textAlign; return a === "start" ? "left" : (a === "end" ? "right" : a); } },
    { group: "Colour", id: "wt-color", prop: "color", label: "Text", kind: "color",
      read: function (cs) { return rgbToHex(cs.color); } },
    { group: "Colour", id: "wt-bg", prop: "background-color", label: "Background", kind: "color",
      read: function (cs) { return rgbToHex(cs.backgroundColor); } },
    { group: "Box", id: "wt-w", prop: "width", label: "Width", kind: "number", unit: "px", box: true,
      read: function (cs) { return px(cs.width); } },
    { group: "Box", id: "wt-h", prop: "height", label: "Height", kind: "number", unit: "px", box: true,
      read: function (cs) { return px(cs.height); } },
    // Four boxes on one row, not a shorthand in one box. Editing a single side used
    // to mean reading `30px 168px 0px 168px`, doing the arithmetic and retyping it -
    // and the Patch then carried all four sides whatever you touched, which is why
    // reconcile has to guess whether a computed `168px` was an authored `auto`.
    // Recording per-side removes that guess at the source. See sideProp/writeSides.
    { group: "Box", id: "wt-margin", prop: "margin", label: "Margin", kind: "sides",
      read: function (cs, side) { return cs["margin" + capitalise(side)]; } },
    { group: "Box", id: "wt-padding", prop: "padding", label: "Padding", kind: "sides",
      read: function (cs, side) { return cs["padding" + capitalise(side)]; } },
    // Width/Style/Colour are three controls over ONE `border` declaration - the
    // first entry in this table to break one-control-one-property. `part` marks
    // them, and writeBorder() composes all three (see ADR-0003); each still reads
    // its own part from computed style - from the edited side, which is the top
    // unless the element carries a single-sided rule (see borderMode).
    { group: "Border", id: "wt-bw", prop: "border", part: "width", label: "Width", kind: "number", unit: "px",
      read: function (cs) { return px(cs[sideKey("Width")]); } },
    { group: "Border", id: "wt-bs", prop: "border", part: "style", label: "Style", kind: "select",
      opts: ["none", "solid", "dashed", "dotted", "double"],
      read: function (cs) { return cs[sideKey("Style")]; } },
    { group: "Border", id: "wt-bc", prop: "border", part: "color", label: "Colour", kind: "color",
      read: function (cs) { return rgbToHex(cs[sideKey("Color")]); } },
    // An ordinary single-property control; `min: 0` because 0 is meaningful (sharp
    // corners), as it is for a shape's rx.
    { group: "Border", id: "wt-brad", prop: "border-radius", label: "Radius", kind: "number", unit: "px", min: 0,
      read: function (cs) { return px(cs.borderRadius); } },
    // A text field with presets rather than discrete controls: building a shadow out
    // of parts needs four lengths, a colour and an inset flag - six controls for one
    // declaration - and a shadow's colour is almost always translucent while the
    // panel's swatch is opaque hex. So it reuses the Font control's suggestion list.
    // No per-row preview: a 24px row cannot show a 45px shadow, only smudge it.
    { group: "Border", id: "wt-shadow", prop: "box-shadow", label: "Shadow", kind: "text",
      suggest: function () { return SHADOW_PRESETS; }, suggestTitle: "Shadow presets",
      read: function (cs) { return cs.boxShadow; } },
    // Shape-only: fill/stroke/stroke-width are inherited SVG presentation properties,
    // so writing them on the <svg> cascades to its child shape (one place to edit
    // colour for every shape kind). `rx` is NOT inherited - it's a <rect> geometry
    // property, so its control reads/writes the child via `host` (see applyChange).
    // shapeOnly controls skip the CSS.supports gate: a colour swatch or a px number
    // is always valid, and CSS.supports can report SVG presentation props unevenly.
    { group: "Shape", id: "wt-fill", prop: "fill", label: "Fill", kind: "color", shapeOnly: true,
      read: function (cs) { return rgbToHex(cs.fill); } },
    // Labelled Stroke, not Border: a shape's line is an SVG stroke and an element's
    // is a CSS border, and since 0.4.0 the panel offers both. Label-only - the props
    // were always the SVG ones. Radius keeps its name (rx and border-radius are the
    // same concept in the same units, so renaming adds noise without removing any
    // ambiguity). See ADR-0003.
    { group: "Shape", id: "wt-stroke", prop: "stroke", label: "Stroke", kind: "color", shapeOnly: true,
      read: function (cs) { return rgbToHex(cs.stroke); } },
    { group: "Shape", id: "wt-sw", prop: "stroke-width", label: "Stroke width", kind: "number", unit: "px", shapeOnly: true,
      read: function (cs) { return px(cs.strokeWidth); } },
    { group: "Shape", id: "wt-rx", prop: "rx", label: "Radius", kind: "number", unit: "px",
      shapeOnly: true, rectOnly: true, host: function (el) { return el.firstElementChild; },
      read: function (cs) { return px(cs.rx); } },
  ];
  var GROUPS = ["Type", "Colour", "Box", "Border", "Shape"];
  var SIDES = ["top", "right", "bottom", "left"];

  // Tracking, in the em steps editorial type is actually set in: tightened for a big
  // display line, opened up for small caps and uppercase labels, plus `normal` to take
  // it off. Kept in em, not px, so the tracking scales with the type it is set on.
  var SPACING_PRESETS = [
    "normal",
    "-0.02em",
    "0.02em",
    "0.05em",
    "0.08em",
    "0.12em",
    "0.18em",
  ];

  // Enough to cover the range an editorial page actually wants - a hairline, a card
  // lift, a modal lift, a dramatic drop, an inset press - plus `none` to take a
  // shadow off. Typing a custom value still works, so this is a shortcut not a cage.
  var SHADOW_PRESETS = [
    "none",
    "0 1px 2px rgba(0, 0, 0, 0.08)",
    "0 2px 8px rgba(0, 0, 0, 0.12)",
    "0 8px 24px rgba(0, 0, 0, 0.18)",
    "0 18px 45px rgba(0, 0, 0, 0.22)",
    "inset 0 1px 3px rgba(0, 0, 0, 0.15)",
  ];

  // ---- the page's own fonts -------------------------------------------------
  // What the Font control offers as suggestions. Computed style is the primary
  // source because it is the only origin-proof one: reading rules from a
  // CDN-hosted sheet raises SecurityError, so a page whose display face comes
  // from a hosted webfont yields nothing from its font-face declarations - while
  // computed style returns the whole stack exactly as authored, fallbacks and all,
  // which is precisely what the control wants to write.

  // Collapse whitespace only for the dedupe key: the entry itself is kept verbatim
  // so picking it writes the stack the page's author actually wrote.
  function fontKey(stack) { return stack.replace(/\s+/g, " ").trim().toLowerCase(); }

  function inUseFontStacks() {
    // Deliberately body-scoped: the rule is "what something on the page renders
    // in". That does include a UA default an element genuinely uses (Chromium
    // gives <code> monospace and a <button> Arial) - those are real answers to
    // "what font is that?". <html> is skipped because its font renders nothing of
    // its own: a page that authors one there has <body> inherit it anyway, and a
    // page that doesn't hands back the browser's default ("Times New Roman"),
    // which would otherwise be offered as one of the page's own fonts on every
    // page ever opened.
    if (!document.body) return [];
    var nodes = [document.body].concat(
      Array.prototype.slice.call(document.body.querySelectorAll("*")));
    var out = [];
    nodes.forEach(function (el) {
      // Skip the Overlay's own nodes, or the editor's interface fonts would be
      // offered as suggestions for the page.
      if (!el || isOverlay(el)) return;
      var stack = (getComputedStyle(el).fontFamily || "").trim();
      if (stack) out.push(stack);
    });
    return out;
  }

  // Families declared as @font-face - a supplement, so a self-hosted face that is
  // set up but not yet applied anywhere is still offered. Gathered defensively:
  // an unreadable sheet is skipped, degrading the list rather than throwing.
  function fontFaceFamilies() {
    var out = [];
    Array.prototype.forEach.call(document.styleSheets || [], function (sheet) {
      if ((sheet.href || "").indexOf(RESERVED) >= 0) return;   // webtweak's own sheet
      collectFaces(sheet, out);
    });
    return out;
  }
  function collectFaces(node, out, depth) {
    depth = depth || 0;
    var rules;
    try { rules = node.cssRules; } catch (e) { return; }  // cross-origin: unreadable, not fatal
    if (!rules) return;
    Array.prototype.forEach.call(rules, function (r) {
      var fam = r.style && (r.style.fontFamily || "").trim();
      if (r.type === 5 /* CSSRule.FONT_FACE_RULE */ && fam) out.push(fam);
      // @font-face is legal inside @media/@supports, so recurse into grouping
      // rules. Bounded, so a pathologically nested sheet can't spin.
      else if (r.cssRules && depth < 3) collectFaces(r, out, depth + 1);
    });
  }

  function pageFonts() {
    var seen = {}, out = [];
    // In-use stacks first (document order, so the body's own font leads), then any
    // declared family the sweep couldn't see.
    inUseFontStacks().concat(fontFaceFamilies()).forEach(function (stack) {
      var k = fontKey(stack);
      if (k && !seen[k]) { seen[k] = true; out.push(stack); }
    });
    return out;
  }

  // ---- shapes ---------------------------------------------------------------
  // Every shape is one inline <svg> wrapper containing a single child primitive,
  // drawn into a fixed 0..100 viewBox. `preserveAspectRatio="none"` lets it stretch
  // to any width x height; `vector-effect="non-scaling-stroke"` keeps the stroke an
  // even thickness under that stretch. rect/ellipse fill the box via attributes; the
  // rest are <polygon>s with precomputed points. Element creation is webtweak's first
  // departure from "only edit what already exists" - see ADR-0002.
  var SVGNS = "http://www.w3.org/2000/svg";
  var SHAPES = {
    square:    { el: "rect",    attrs: { x: 0, y: 0, width: 100, height: 100 }, size: { w: 80, h: 80 } },
    rectangle: { el: "rect",    attrs: { x: 0, y: 0, width: 100, height: 100 }, size: { w: 140, h: 80 } },
    circle:    { el: "ellipse", attrs: { cx: 50, cy: 50, rx: 50, ry: 50 }, size: { w: 80, h: 80 } },
    ellipse:   { el: "ellipse", attrs: { cx: 50, cy: 50, rx: 50, ry: 50 }, size: { w: 140, h: 80 } },
    triangle:  { el: "polygon", points: "50,0 100,100 0,100", size: { w: 90, h: 80 } },
    star:      { el: "polygon", points: "50,2 61,38 98,38 68,60 79,96 50,74 21,96 32,60 2,38 39,38", size: { w: 90, h: 90 } },
    diamond:   { el: "polygon", points: "50,0 100,50 50,100 0,50", size: { w: 90, h: 90 } },
    pentagon:  { el: "polygon", points: "50,0 98,36 80,98 20,98 2,36", size: { w: 90, h: 90 } },
    hexagon:   { el: "polygon", points: "25,2 75,2 100,50 75,98 25,98 0,50", size: { w: 100, h: 86 } },
  };
  var SHAPE_LIST = ["square", "rectangle", "circle", "ellipse", "triangle", "star", "diamond", "pentagon", "hexagon"];
  var DEFAULT_FILL = "#e8c468";

  // The self-describing structural payload carried in a create patch, so reconcile
  // can render the shape without webtweak's SHAPES table.
  function shapeGeometry(kind) {
    var spec = SHAPES[kind] || SHAPES.square;
    return { viewBox: "0 0 100 100", el: spec.el, points: spec.points || null, attrs: spec.attrs || null };
  }

  // Build the inner-shape markup string (for palette icons and nothing else - the
  // live shape uses real createElementNS nodes, below).
  function innerMarkup(spec) {
    if (spec.points) return '<polygon points="' + spec.points + '"/>';
    return "<" + spec.el + " " + Object.keys(spec.attrs).map(function (k) {
      return k + '="' + spec.attrs[k] + '"';
    }).join(" ") + "/>";
  }

  // Create a shape <svg> at document coords (x, y), register it in `edited` with a
  // seeded full-style `changes` snapshot so its create patch is self-contained even
  // if no control is ever touched. opts.restore re-injects a saved shape (keeps its
  // id + changes, no undo step). The `wt-shape-` id prefix keeps it out of
  // fingerprint class capture, and reconcile strips it for a clean source hook.
  function makeShape(kind, x, y, opts) {
    opts = opts || {};
    var spec = SHAPES[kind] || SHAPES.square;
    var svg = document.createElementNS(SVGNS, "svg");
    var id = opts.id || ("wt-shape-" + Math.random().toString(36).slice(2, 8));
    svg.setAttribute("id", id);
    svg.setAttribute("class", "wt-shape");
    svg.setAttribute("data-wt-shape", kind);
    svg.setAttribute("viewBox", "0 0 100 100");
    svg.setAttribute("preserveAspectRatio", "none");
    var child = document.createElementNS(SVGNS, spec.el);
    if (spec.points) child.setAttribute("points", spec.points);
    if (spec.attrs) Object.keys(spec.attrs).forEach(function (k) { child.setAttribute(k, spec.attrs[k]); });
    child.setAttribute("vector-effect", "non-scaling-stroke");
    svg.appendChild(child);
    svg.__wtShape = true;
    document.body.appendChild(svg);

    var e = entry(svg);                     // origStyle = null (no style attr yet)
    e.shape = { kind: kind, geometry: opts.geometry || shapeGeometry(kind) };
    e.changes = opts.changes || {
      "position": "absolute",
      "left": Math.round(x) + "px",
      "top": Math.round(y) + "px",
      "width": spec.size.w + "px",
      "height": spec.size.h + "px",
      "fill": DEFAULT_FILL,
      "stroke": "none",
      "stroke-width": "0",
    };
    rebuildInline(svg, e);                   // apply the seeded style inline
    if (!opts.restore) {
      // If <body> is a positioned/transformed containing block, an absolute child's
      // left/top are measured from its padding box rather than the viewport, so the
      // shape would land offset from the cursor. Re-seat it to the actual click point
      // by measuring and correcting (a no-op on the common static-body case). The
      // viewport-pixel error is divided by the on-screen scale (derived from the
      // shape's own known layout size vs its measured box) so it also lands correctly
      // under a transform:scale() ancestor, matching the grip-resize path.
      var r = svg.getBoundingClientRect();
      var scx = parseFloat(e.changes.width) > 0 ? r.width / parseFloat(e.changes.width) : 1;
      var scy = parseFloat(e.changes.height) > 0 ? r.height / parseFloat(e.changes.height) : 1;
      var nx = Math.round(parseFloat(e.changes.left) + (x - window.scrollX - r.left) / (scx || 1));
      var ny = Math.round(parseFloat(e.changes.top) + (y - window.scrollY - r.top) / (scy || 1));
      if (nx + "px" !== e.changes.left || ny + "px" !== e.changes.top) {
        e.changes.left = nx + "px";
        e.changes.top = ny + "px";
        rebuildInline(svg, e);
      }
      dirty = true;                          // a fresh shape is an unsaved edit; a restored one is not
      pushUndo([{ el: svg, create: true }]);        // Cmd+Z removes the shape
    }
    return svg;
  }

  // ---- DOM scaffolding ------------------------------------------------------
  var root = document.createElement("div");
  root.id = "wt-root";
  root.innerHTML = [
    '<div class="wt-bar wt-ui">',
    '  <span class="wt-logo">webtweak</span>',
    '  <span class="wt-crumb" id="wt-crumb">click an element to select</span>',
    '  <span class="wt-status" id="wt-status"></span>',
    '  <button class="wt-badge" id="wt-badge" hidden></button>',
    '  <div class="wt-shapes" id="wt-shapes">',
    '    <button class="wt-btn" id="wt-shape-btn">Shape ▾</button>',
    '    <div class="wt-palette" id="wt-palette" hidden></div>',
    "  </div>",
    // History was invisible: the only mention of undo was a sentence in the hint bar,
    // and the only feedback a status line after the user had already lost their place.
    '  <button class="wt-btn" id="wt-undo" title="Undo (Cmd/Ctrl+Z)" disabled>Undo</button>',
    '  <button class="wt-btn" id="wt-redo" title="Redo (Shift+Cmd/Ctrl+Z)" disabled>Redo</button>',
    '  <button class="wt-btn" id="wt-deselect">Deselect</button>',
    '  <button class="wt-btn wt-primary" id="wt-save">Save</button>',
    "</div>",
    '<div class="wt-box wt-hover" id="wt-hover" hidden></div>',
    '<div class="wt-box wt-selected" id="wt-selected" hidden>',
    '  <span class="wt-tag" id="wt-seltag"></span>',
    '  <span class="wt-grip wt-grip-r"></span><span class="wt-grip wt-grip-b"></span>',
    '  <span class="wt-grip wt-grip-br"></span>',
    "</div>",
    panelHTML(),
    // Change list and hint share the bottom-left corner, so they live in one
    // flow container - fixed offsets on both let them overlap and swallow
    // each other's clicks.
    '<div class="wt-dock">',
    '  <div class="wt-changes wt-ui" id="wt-changes" hidden>',
    '    <button class="wt-changes-head" id="wt-changes-head" aria-expanded="false"></button>',
    '    <ul class="wt-changes-list" id="wt-changes-list" hidden></ul>',
    "  </div>",
    '  <div class="wt-hint wt-ui">Click to select. Drag the interior to <b>nudge</b>, drag the right/bottom/corner grips to <b>resize</b>. <b>Esc</b> deselect, <b>Cmd/Ctrl+Z</b> undo, <b>Shift+Cmd/Ctrl+Z</b> redo, <b>Cmd/Ctrl+S</b> save.</div>',
    "</div>",
    '<div class="wt-place-hint wt-ui" id="wt-place-hint" hidden><b>Click anywhere</b> to drop the shape. <b>Esc</b> to cancel.</div>',
  ].join("\n");
  // Mounted on <html>, not <body>: a transformed ancestor becomes the containing
  // block for position:fixed descendants, so a page with `body { transform:
  // scale(...) }` (the A4/print layouts webtweak explicitly supports) would
  // render the whole Overlay scaled and anchored to the body box.
  document.documentElement.appendChild(root);

  var hoverBox = document.getElementById("wt-hover");
  var selBox = document.getElementById("wt-selected");
  var selTag = document.getElementById("wt-seltag");
  var crumbEl = document.getElementById("wt-crumb");
  var statusEl = document.getElementById("wt-status");
  var panel = document.getElementById("wt-panel");
  var palette = document.getElementById("wt-palette");
  var placeHint = document.getElementById("wt-place-hint");

  // ---- shape palette + place mode -------------------------------------------
  SHAPE_LIST.forEach(function (kind) {
    var btn = document.createElement("button");
    btn.className = "wt-shape-item";
    btn.dataset.shape = kind;
    btn.title = "Click then click the page, or drag me onto the page";
    btn.setAttribute("draggable", "true");   // also draggable straight onto the page
    btn.innerHTML = '<svg viewBox="-8 -8 116 116" preserveAspectRatio="none">' +
      innerMarkup(SHAPES[kind]) + "</svg>";
    palette.appendChild(btn);
  });
  document.getElementById("wt-shape-btn").addEventListener("click", function () {
    palette.hidden = !palette.hidden;
  });
  palette.addEventListener("click", function (ev) {
    var btn = ev.target.closest(".wt-shape-item");
    if (btn) enterPlaceMode(btn.dataset.shape);   // click-to-place: next canvas click drops it
  });
  // Drag-and-drop placement: drag a palette shape onto the page and release to drop
  // it at the cursor. A real drag suppresses the click, so click-to-place still works.
  palette.addEventListener("dragstart", function (ev) {
    var btn = ev.target.closest(".wt-shape-item");
    if (!btn) return;
    pendingShape = btn.dataset.shape;
    if (ev.dataTransfer) {
      ev.dataTransfer.effectAllowed = "copy";
      ev.dataTransfer.setData("text/plain", btn.dataset.shape);  // some engines need data set
    }
    showPlaceModeUI();
  });
  document.addEventListener("dragover", function (ev) {
    if (!pendingShape) return;
    ev.preventDefault();                         // allow the drop
    if (ev.dataTransfer) ev.dataTransfer.dropEffect = "copy";
  });
  document.addEventListener("drop", function (ev) {
    if (!pendingShape) return;
    ev.preventDefault();
    var kind = pendingShape;
    if (isOverlay(ev.target)) { exitPlaceMode(); status("placement cancelled"); return; }  // dropped on the UI
    placeShape(kind, ev.clientX + window.scrollX, ev.clientY + window.scrollY);
  });
  document.addEventListener("dragend", function () {
    if (pendingShape) exitPlaceMode();           // drag released outside a drop target: cancel
  });
  function enterPlaceMode(kind) {
    deselect();   // clear any selection + its grips so they can't swallow the placement click
    pendingShape = kind;
    showPlaceModeUI();
    status("click to place " + kind);
  }
  function showPlaceModeUI() {
    palette.hidden = true;
    placeHint.hidden = false;
    document.documentElement.classList.add("wt-placing");
  }
  function exitPlaceMode() {
    pendingShape = null;
    placeHint.hidden = true;
    document.documentElement.classList.remove("wt-placing");
  }
  // Drop a shape at document coords (x, y), leave place mode, and select it -
  // shared by the click-to-place and drag-and-drop paths.
  function placeShape(kind, x, y) {
    exitPlaceMode();
    var svg = makeShape(kind, x, y);
    selectEl(svg);
    status("added " + kind);
    return svg;
  }

  function panelHTML() {
    var parts = ['<div class="wt-panel wt-ui" id="wt-panel" hidden>', "  <h3>Properties</h3>"];
    GROUPS.forEach(function (g) {
      parts.push('  <div class="wt-group" data-group="' + g + '"><div class="wt-legend">' + g + "</div>");
      CONTROLS.filter(function (c) { return c.group === g; }).forEach(function (c) {
        // A sides row needs its label column narrowed to fit four boxes, so it is
        // marked rather than special-cased in CSS by descendant guesswork.
        parts.push(field(c.label, controlMarkup(c), c.kind === "sides" ? " wt-field-wide" : ""));
      });
      parts.push("  </div>");
    });
    parts.push('  <button class="wt-btn wt-block" id="wt-reset">Reset this element</button>');
    // Save writes a file; reconcile is a separate step the user asks for.
    parts.push('  <p class="wt-note">Changes preview live and are captured as intent. On Save, webtweak writes them to the edits file - then ask Claude to reconcile.</p>');
    parts.push("</div>");
    return parts.join("\n");
  }
  function controlMarkup(c) {
    // 0 is meaningful for box sizes and shape props (stroke-width 0 = no border, rx 0 =
    // sharp corners); other numbers (font-size) floor at 1. `min` on the control
    // itself overrides, for a property that is neither but still means something at
    // 0 (corner radius).
    if (c.kind === "number") {
      var min = c.min === undefined ? (c.box || c.shapeOnly ? 0 : 1) : c.min;
      return '<input type="number" id="' + c.id + '" min="' + min + '"> px';
    }
    if (c.kind === "color") return '<input type="color" id="' + c.id + '">';
    if (c.kind === "select") return select(c.id, c.opts);
    if (c.kind === "align") return alignButtons(c.id);
    if (c.suggest) return suggestField(c);
    if (c.step) return stepperField(c);
    if (c.kind === "sides") return sidesField(c);
    return '<input type="text" id="' + c.id + '">';
  }
  // Top/right/bottom/left on one row, plus a link toggle for "the same on all sides",
  // which is the one thing the old single box did well. Four boxes on the SAME row
  // cost no vertical space, which matters: the panel already scrolls on a short
  // window. Text inputs rather than numbers, so a unit - or `auto` - still works.
  function sidesField(c) {
    return '<span class="wt-sides">' +
      SIDES.map(function (s) {
        return '<input type="text" id="' + c.id + "-" + s + '" title="' +
          capitalise(s) + '" aria-label="' + c.label + " " + s + '">';
      }).join("") +
      '<button class="wt-link" id="' + c.id + '-link" type="button" aria-pressed="false"' +
      ' title="Link all four sides">&#128279;</button>' +
      "</span>";
  }
  // A text input with up/down buttons. The input stays free text, so a keyword or a
  // unit the stepper cannot compute on is still typeable - the buttons are an
  // addition to the field, not a replacement for it.
  function stepperField(c) {
    return '<span class="wt-stepper">' +
      '<input type="text" id="' + c.id + '">' +
      '<span class="wt-step-btns">' +
      '<button id="' + c.id + '-up" type="button" title="Increase" aria-label="Increase">&#9650;</button>' +
      '<button id="' + c.id + '-down" type="button" title="Decrease" aria-label="Decrease">&#9660;</button>' +
      "</span></span>";
  }
  // A text input plus a dropdown of suggestions - deliberately not a closed
  // dropdown, so free text still works and nothing that was possible before this
  // control existed becomes impossible. The list itself is filled at open time by
  // c.suggest(), never from markup.
  // The list escapes the panel's scroll box by being positioned in viewport
  // coordinates on open (see placeSuggest), so a field anywhere in the panel can
  // have one - Font sits at the top and Shadow at the very bottom.
  function suggestField(c) {
    return '<span class="wt-suggest">' +
      '<input type="text" id="' + c.id + '">' +
      '<button class="wt-suggest-toggle" id="' + c.id + '-toggle" type="button"' +
      ' aria-expanded="false" aria-controls="' + c.id + '-list"' +
      ' title="' + (c.suggestTitle || "Suggestions") + '">&#9662;</button>' +
      '<ul class="wt-suggest-list" id="' + c.id + '-list" hidden></ul>' +
      "</span>";
  }
  function field(label, control, extra) {
    return '  <div class="wt-field' + (extra || "") + '"><label>' + label + "</label>" +
      control + "</div>";
  }
  function select(id, opts) {
    return '<select id="' + id + '">' +
      opts.map(function (o) { return '<option value="' + o + '">' + o + "</option>"; }).join("") +
      "</select>";
  }
  function alignButtons(id) {
    return '<div class="wt-align" id="' + id + '">' +
      ["left", "center", "right", "justify"].map(function (a) {
        return '<button data-align="' + a + '">' + a[0].toUpperCase() + "</button>";
      }).join("") + "</div>";
  }

  // ---- helpers --------------------------------------------------------------
  function isOverlay(el) { return el && el.closest && el.closest("#wt-root"); }

  function cssEsc(s) {
    if (window.CSS && CSS.escape) return CSS.escape(s);
    return String(s).replace(/[^\w-]/g, "\\$&");
  }

  function rgbToHex(rgb) {
    var m = (rgb || "").match(/\d+/g);
    if (!m) return "#000000";
    return "#" + m.slice(0, 3).map(function (n) {
      return ("0" + (+n).toString(16)).slice(-2);
    }).join("");
  }

  function px(v) { var n = parseInt(v, 10); return isNaN(n) ? "" : n; }

  function positionBox(box, el) {
    var r = el.getBoundingClientRect();
    box.style.top = r.top + "px";
    box.style.left = r.left + "px";
    box.style.width = r.width + "px";
    box.style.height = r.height + "px";
    box.hidden = false;
  }

  // Only strip the classes the Overlay itself writes onto a page element. A
  // prefix match would erase a page's own `wt-` design-system classes from the
  // fingerprint, leaving Claude nothing but a fragile positional selector.
  var WT_OWN_CLASSES = { "wt-shape": 1 };

  function nonWtClasses(el) {
    return Array.prototype.filter.call(el.classList, function (c) {
      return !WT_OWN_CLASSES[c];
    });
  }

  function cssPath(el) {
    if (!el || el === document.body) return "body";
    var parts = [];
    while (el && el.nodeType === 1 && el !== document.body) {
      if (el.id) { parts.unshift("#" + cssEsc(el.id)); return parts.join(" > "); }
      var part = el.tagName.toLowerCase() +
        nonWtClasses(el).map(function (c) { return "." + cssEsc(c); }).join("");
      var parent = el.parentElement;
      if (parent) {
        var sibs = Array.prototype.filter.call(parent.children, function (c) {
          return c.tagName === el.tagName && c.id !== "wt-root";  // ignore the overlay root
        });
        if (sibs.length > 1) part += ":nth-of-type(" + (sibs.indexOf(el) + 1) + ")";
      }
      parts.unshift(part);
      el = el.parentElement;
    }
    return "body > " + parts.join(" > ");
  }

  // Build the opening tag from attributes (robust against '>' inside attribute
  // values) and exclude the Overlay's injected inline `style`.
  function openTag(el) {
    var s = "<" + el.tagName.toLowerCase();
    Array.prototype.forEach.call(el.attributes, function (a) {
      if (a.name === "style") return;
      s += " " + a.name + (a.value !== "" ? '="' + a.value.replace(/"/g, "&quot;") + '"' : "");
    });
    return (s + ">").slice(0, 300);
  }

  function ownText(el) {
    return Array.prototype.filter.call(el.childNodes, function (n) { return n.nodeType === 3; })
      .map(function (n) { return n.textContent; }).join("").trim().replace(/\s+/g, " ").slice(0, 80);
  }

  // Index of `el` among siblings sharing its tag + classes - the ordinal that lets
  // reconcile name "the 2nd of 3 identical blocks" when nothing else distinguishes them.
  function siblingIndex(el) {
    var parent = el.parentElement;
    if (!parent) return 0;
    var key = el.tagName + "|" + nonWtClasses(el).join(".");
    var same = Array.prototype.filter.call(parent.children, function (c) {
      return c.id !== "wt-root" && (c.tagName + "|" + nonWtClasses(c).join(".")) === key;
    });
    return same.indexOf(el);
  }

  function fingerprint(el) {
    return {
      tag: el.tagName.toLowerCase(),
      id: el.id || "",
      classes: nonWtClasses(el),
      text: (el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 80),
      ownText: ownText(el),
      selector: cssPath(el),
      siblingIndex: siblingIndex(el),
      openTag: openTag(el),
    };
  }

  function describe(el) {
    var s = el.tagName.toLowerCase();
    if (el.id) s += "#" + el.id;
    else { var cls = nonWtClasses(el); if (cls.length) s += "." + cls[0]; }
    return s;
  }

  function setCrumb(el) {
    var chain = [], n = el;
    while (n && n.nodeType === 1 && n !== document.body) { chain.unshift(n); n = n.parentElement; }
    // Built with textContent, never innerHTML: describe() returns the page's own
    // tag/id/class names, and webtweak is routinely pointed at repos the user did
    // not write. An id like `a"><img src=x onerror=...>` used to execute here, in
    // the overlay's origin - which can POST patches that Claude later reconciles
    // into real source.
    crumbEl.textContent = "";
    chain.forEach(function (node, i) {
      if (i) crumbEl.appendChild(document.createTextNode(" › "));
      var last = i === chain.length - 1;
      var part = document.createElement(last ? "b" : "span");
      part.textContent = describe(node);
      crumbEl.appendChild(part);
    });
  }

  function status(msg, ok) {
    statusEl.textContent = msg || "";
    statusEl.style.color = ok === false ? "#ff8a8a" : "#8ad18a";
  }

  // ---- selection ------------------------------------------------------------
  function selectEl(el) {
    if (!el || el === document.body || el === document.documentElement) { deselect(); return; }
    if (selectedEl && window.interact) interact(selectedEl).unset();
    interacting = false;  // unset() can abort an in-flight gesture without firing 'end'
    selectedEl = el;
    entry(el); // lock the authored baseline before any edit
    positionBox(selBox, el);
    selTag.textContent = describe(el);
    setCrumb(el);
    populate(el);
    panel.hidden = false;
    attachInteract(el);
    refreshChanges();      // keep the list's current-selection highlight honest
  }

  function deselect() {
    if (pendingShape) exitPlaceMode();  // a Deselect/Esc during place mode also cancels placement
    if (selectedEl && window.interact) interact(selectedEl).unset();
    interacting = false;  // unset() can abort an in-flight gesture without firing 'end'
    selectedEl = null;
    selBox.hidden = true;
    closeAllSuggests();   // else it reopens with the panel on the next selection
    panel.hidden = true;
    crumbEl.textContent = "click an element to select";
    refreshChanges();            // drop the list's stale current-selection highlight
  }

  function resetEl(el) {
    var e = edited.get(el);
    // A created shape has no authored baseline to revert to - resetting it removes it.
    if (e && e.shape) {
      // Removing a shape is a delete, so it must be undoable: without this the
      // button silently destroys work and Ctrl+Z pops some older, unrelated step.
      var sib = el.nextSibling, parent = el.parentNode;
      pushUndo([{ el: el, restore: { entry: e, parent: parent, before: sib } }]);
      if (el === selectedEl) deselect();
      if (parent) parent.removeChild(el);
      edited.delete(el);
      dirty = hasRealEdits();
      refreshChanges();
      status("shape removed - Cmd/Ctrl+Z to undo");
      return;
    }
    if (e) {
      // Record every change being discarded so one Ctrl+Z brings them all back.
      var steps = Object.keys(e.changes).map(function (p) {
        return { el: el, prop: p, prev: e.changes[p] };
      });
      if (steps.length) pushUndo(steps);
      if (e.origStyle == null) el.removeAttribute("style");
      else el.setAttribute("style", e.origStyle);
      edited.delete(el);
      dirty = hasRealEdits();  // don't leave a false 'unsaved changes' flag when nothing remains
    }
    if (el === selectedEl) {
      entry(el); // re-arm a fresh baseline
      positionBox(selBox, el);
      populate(el);
    }
    refreshChanges();
    status("reset - save to drop these edits");
  }

  // Replaced (and replaced-like) inline elements that DO honour width/height and
  // transform, unlike ordinary inline text boxes. Keyed by lowercase tagName
  // (HTML elements have uppercase tagName, SVG/MathML elements have lowercase —
  // always compare via .toLowerCase() to match both).
  var REPLACED = { img: 1, svg: 1, video: 1, canvas: 1, iframe: 1, embed: 1,
    object: 1, picture: 1, input: 1, textarea: 1, select: 1, button: 1, audio: 1 };

  function populate(el) {
    var cs = getComputedStyle(el);
    var ent = edited.get(el);
    baselines = {};
    closeAllSuggests();   // a list left open would hang over the repopulated fields
    // Before the reads: the border controls read (and write) whichever side they are
    // editing, so the mode has to be settled first.
    var mode = borderMode(cs);
    borderSide = mode.side;
    borderMixed = mode.mixed;
    CONTROLS.forEach(function (c) {
      // Most controls read/write the element itself; `host` (rx only) targets the
      // child shape node, since rx is a non-inherited <rect> geometry property. Only
      // resolve it for shapes, so selecting a normal element never probes (and forces
      // a style recalc on) a child node for a control it will never show.
      var host = (c.host && ent && ent.shape && c.host(el)) || el;
      var hcs = host === el ? cs : getComputedStyle(host);
      // A sides control is four fields with four baselines, each read from its own
      // computed longhand - so no shorthand ever has to be parsed to fill them.
      if (c.kind === "sides") return populateSides(c, host, hcs, ent);
      var shown = c.read(hcs);            // current (possibly already-edited) value -> the panel
      var base = shown;
      // After a reload+restore the override is applied inline, so computed == the
      // edited value. Recover the true authored baseline by reading computed with
      // just this property's override peeled off, so "revert to original" is still
      // detected (and doesn't record a no-op patch setting a prop to its own origin).
      var prop = propOf(c);   // `border-bottom` for a one-sided rule, else c.prop
      if (ent && ent.changes && prop && Object.prototype.hasOwnProperty.call(ent.changes, prop)) {
        base = withTempStyle(host,
          function (s) { s.removeProperty(prop); },
          function () { return c.read(getComputedStyle(host)); });
      }
      baselines[c.id] = String(base);
      if (c.kind === "align") {
        Array.prototype.forEach.call(document.querySelectorAll("#" + c.id + " button"), function (b) {
          b.classList.toggle("on", b.dataset.align === shown);
        });
      } else {
        set(c.id, shown);
      }
    });
    // Group/field visibility: the Shape group shows only for shapes; Type + Colour
    // hide for shapes (typography/text colour are irrelevant); Box always shows.
    // The Radius field shows only for rect/square (rx is meaningless elsewhere).
    var isShape = !!(ent && ent.shape);
    GROUPS.forEach(function (g) {
      var node = document.querySelector('#wt-panel .wt-group[data-group="' + g + '"]');
      if (node) node.hidden = (g === "Shape") ? !isShape : (g === "Box" ? false : isShape);
    });
    CONTROLS.forEach(function (c) {
      if (!c.rectOnly) return;
      var node = document.getElementById(c.id), wrap = node && node.closest(".wt-field");
      if (wrap) wrap.hidden = !(isShape && (ent.shape.kind === "square" || ent.shape.kind === "rectangle"));
    });
    // Name the side being edited, or say why the controls are off. A border edit on
    // an element carrying a single rule must not be a surprise, and an element whose
    // sides differ is declined out loud rather than silently given a box.
    var legend = document.querySelector('#wt-panel .wt-group[data-group="Border"] .wt-legend');
    if (legend) {
      legend.textContent = borderMixed ? "Border (sides differ)"
        : (borderSide ? "Border (" + borderSide + ")" : "Border");
    }
    Object.keys(BORDER).forEach(function (part) {
      var n = document.getElementById(BORDER[part]);
      if (n) { n.disabled = borderMixed; n.title = borderMixed ? MIXED_TIP : ""; }
    });
    // Radius is judged on its own - it is not a per-side property, so differing sides
    // say nothing about whether a corner radius can be set. But differing CORNERS are
    // the same problem one property along: a card rounded on its top two corners is a
    // deliberate shape, and one value in this field would round all four. Computed
    // border-radius is a single length only when all four corners agree, so a space
    // in it is the whole test (it also catches an elliptical `10px / 20px`, which one
    // number cannot express either).
    var mixedCorners = cs.borderRadius.indexOf(" ") >= 0;
    var rad = document.getElementById("wt-brad");
    if (rad) { rad.disabled = mixedCorners; rad.title = mixedCorners ? MIXED_CORNERS_TIP : ""; }
    // width/height + nudge are inert on NON-REPLACED inline elements - disable them
    // so a user can't record a dead patch the element never honours. Replaced inline
    // elements (img, svg, video, form controls...) DO honour sizing/transform, so they
    // stay enabled even at display:inline.
    var inlineOnly = cs.display === "inline" && !REPLACED[el.tagName.toLowerCase()];
    ["wt-w", "wt-h"].forEach(function (id) {
      var n = document.getElementById(id);
      if (n) { n.disabled = inlineOnly; n.title = inlineOnly ? "width/height are ignored on inline elements" : ""; }
    });
    el.__wtInline = inlineOnly;  // also gate the resize grips (see attachInteract)
  }
  function set(id, v) { var el = document.getElementById(id); if (el) el.value = v; }

  // Fill the four side fields, peeling this session's own override off each one so a
  // revert is still recognised after a reload - the same trick the single-value
  // controls use, applied per side. The shorthand is peeled too, since a linked write
  // records `padding` rather than four longhands.
  function populateSides(c, host, hcs, ent) {
    SIDES.forEach(function (side) {
      var prop = sideProp(c, side);
      var shown = c.read(hcs, side);
      var base = shown;
      var edits = (ent && ent.changes) || {};
      if (Object.prototype.hasOwnProperty.call(edits, prop) ||
          Object.prototype.hasOwnProperty.call(edits, c.prop)) {
        base = withTempStyle(host, function (s) {
          s.removeProperty(prop);
          s.removeProperty(c.prop);
        }, function () { return c.read(getComputedStyle(host), side); });
      }
      baselines[c.id + "-" + side] = String(base);
      set(c.id + "-" + side, shown);
    });
  }

  // ---- property wiring (all from the CONTROLS table) ------------------------
  // Wrap a single multi-word font family in quotes so the live preview applies
  // (a stack with commas, an already-quoted value, or a single word is left alone).
  function quoteFamily(val) {
    if (/[,'"]/.test(val) || !/\s/.test(val)) return val;
    return '"' + val + '"';
  }
  // Run `mutate(el.style)`, return `read()`, then restore the element's FULL inline
  // cssText verbatim - so a temporary shorthand write/removal can't drop a coexisting
  // authored longhand (e.g. an inline margin-top) the caller didn't mean to touch.
  function withTempStyle(el, mutate, read) {
    var savedCss = el.style.cssText;
    mutate(el.style);
    var result = read();
    el.style.cssText = savedCss;
    return result;
  }
  // Properties whose authored form never matches their computed form, so a typed value
  // has to be resolved through the element before it can be compared to the baseline.
  // Chromium reorders a computed box-shadow colour-first ("0 1px 2px rgba(0,0,0,.08)"
  // -> "rgba(0, 0, 0, 0.08) 0px 1px 2px 0px"), so a literal comparison never matches.
  // Margin and padding used to be here too; they now have their own comparison in
  // isRevert(), which also has to keep `auto` distinguishable from the `0px` it
  // resolves to.
  var RESOLVE_TO_COMPARE = { "box-shadow": 1 };
  function resolveValue(prop, value) {
    return withTempStyle(selectedEl,
      function (s) { s.setProperty(prop, value); },
      // getPropertyValue, not [prop]: the property names here are kebab-case.
      function () { return getComputedStyle(selectedEl).getPropertyValue(prop); });
  }
  // Re-apply one recorded change (a nudge transform or a plain property) to an element.
  // Shape fill/stroke/stroke-width are inherited SVG props, so they're set on the
  // <svg> and cascade to the child. `rx` is a non-inherited <rect> geometry property,
  // so it's routed to the child node instead (the patch still records it on the shape).
  function applyChange(el, prop, value) {
    if (prop === "nudge") { el.style.transform = "translate(" + value.dx + "px, " + value.dy + "px)"; return; }
    if (prop === "rx" && el.__wtShape && el.firstElementChild) {
      el.firstElementChild.style.setProperty("rx", value);
      return;
    }
    el.style.setProperty(prop, value);
  }
  // Rebuild an element's inline style from its authored original plus the session's
  // remaining changes. Used to revert a single property without a removeProperty() that
  // would wipe a coexisting authored inline longhand the user never touched.
  function rebuildInline(el, ent) {
    if (!ent || ent.origStyle == null) el.removeAttribute("style");
    else el.setAttribute("style", ent.origStyle);
    // For shapes, `rx` lives on the child node (not in the svg's own style attr),
    // so clear the child too before re-applying or a reverted radius would linger.
    if (el.__wtShape && el.firstElementChild) el.firstElementChild.removeAttribute("style");
    if (ent) Object.keys(ent.changes).forEach(function (p) {
      var v = ent.changes[p];
      applyChange(el, p, v);
      if (p === "nudge") { ent._x = v.dx; ent._y = v.dy; }  // re-seed the drag accumulator to the snapped value
    });
  }
  // Drop the override and the recorded change for one control, restoring the
  // authored inline style plus whatever other edits remain on the element.
  function revertControl(c) {
    var ent = edited.get(selectedEl);
    var prop = propOf(c);
    if (ent && ent.changes[prop] !== undefined) pushUndoWrite(selectedEl, prop);
    if (ent) delete ent.changes[prop];
    rebuildInline(selectedEl, ent);  // preserves coexisting authored longhands
    dirty = hasRealEdits();          // reverting the last edit must clear the stale unsaved flag
    status("");                      // abandoning an edit supersedes a stale notice too
    refreshChanges();
    positionBox(selBox, selectedEl);
  }

  function writeControl(c, raw) {
    if (!selectedEl) return;
    // A control the Overlay has declined is not writable by ANY path. The disabled
    // attribute stops a mouse and a keyboard, which is all a user has - but the guard
    // exists to stop a Patch the element will not honour from being recorded at all,
    // so refusing here makes that structural rather than presentational.
    var node = document.getElementById(c.id);
    if (node && node.disabled) return;
    if (c.part) return writeBorder(c, raw);   // three controls, one declaration
    // Clearing a field means "I don't want this change after all", so it must
    // drop any recorded change - not return early and leave the abandoned value
    // sitting in the edits file for Claude to reconcile into real source.
    if (raw === "" && c.kind !== "align") return revertControl(c);
    if (c.box) raw = Math.max(1, parseInt(raw, 10) || 1);   // width/height floor of 1, matching resize
    var v = c.unit ? raw + c.unit : raw;
    if (c.prop === "font-family") v = quoteFamily(raw);
    // Rejected first, before anything can interpret the value (see accepts).
    if (!accepts(c, v, raw)) return;
    // Setting a control back to the value it was populated with means "revert this
    // property" - drop the override + the recorded change rather than baking a no-op
    // (also stops an accidental opaque #000000 from a transparent-shown colour swatch).
    // Some props (margin/padding/box-shadow) have a baseline in computed form that a
    // typed value never matches literally, so resolve it through the element first.
    var revertTarget = RESOLVE_TO_COMPARE[c.prop] ? resolveValue(c.prop, raw) : String(raw);
    // A shape's seeded properties (fill/stroke/stroke-width/rx and width/height) have
    // no authored baseline and must stay in the self-contained create patch, so those
    // writes are always recorded - a 1px border or a #000000 fill can't be mistaken for
    // a revert against the SVG UA default the baseline peel resolves to. But margin/
    // padding on a shape ARE ordinary (not seeded), so they still revert normally.
    var noRevert = selectedEl.__wtShape && (c.shapeOnly || c.box);
    // Guard the "" === "" trap: an engine that serialises an asymmetric computed
    // shorthand as "" must not make every typed value look like a revert.
    if (!noRevert && revertTarget !== "" && revertTarget === baselines[c.id]) return revertControl(c);
    commit(c, v);
  }
  // Would the browser accept this value? If not, the live preview never changed, so
  // recording it would be a phantom patch the page never showed.
  //
  // Checked BEFORE the revert comparison, in both write paths. After it, a typo in a
  // resolve-to-compare property would be destructive: an invalid value resolves to
  // the element's CURRENT computed value, which is indistinguishable from the user
  // setting the field back to its baseline - so mistyping over a shadow you had just
  // set would silently delete it instead of being ignored.
  function accepts(c, v, raw) {
    var prop = propOf(c);
    if (c.box || c.shapeOnly) return true;   // a px number or a swatch is always valid
    if (CSS.supports(prop, v)) return true;
    status("ignored invalid " + prop + ": " + raw, false);
    return false;
  }
  // The shared tail of every write - the plain path above and the composed border
  // path below both end here, so there is one place a Patch can be created.
  function commit(c, v) {
    var prop = propOf(c);
    pushUndoWrite(selectedEl, prop);
    applyChange(selectedEl, prop, v);    // routes rx to the child node; plain setProperty otherwise
    record(selectedEl, prop, v);
    positionBox(selBox, selectedEl);                        // any edit can reflow - always re-fit the box
  }

  // ---- per-side spacing -----------------------------------------------------
  // The mirror image of the composed border: instead of three controls composing one
  // declaration, four controls each emit their own longhand. Safe from the
  // phantom-Patch rule that forced border to compose, because a single side IS
  // individually visible - setting one padding renders on its own, so nothing has to
  // be seeded to make the change show.
  var linked = {};   // control id -> "same on all sides" state, per control

  function sideProp(c, side) { return c.prop + "-" + side; }
  function writeSides(c, side, raw) {
    var ids = SIDES.map(function (s) { return c.id + "-" + s; });
    // Linked writes express one intent - "this much all round" - so they record the
    // shorthand the user actually meant rather than four identical longhands.
    if (linked[c.id]) {
      SIDES.forEach(function (s, i) { if (SIDES[i] !== side) set(ids[i], raw); });
      return writeOne(c, c.prop, ids, raw);
    }
    return writeOne(c, sideProp(c, side), c.id + "-" + side, raw);
  }
  // One side (or the whole shorthand) through the shared write tail, so revert
  // detection, the invalid gate, undo and the change list all behave as everywhere
  // else. `baseId` is whichever field(s) hold this property's baseline.
  function writeOne(c, prop, baseId, raw) {
    var probe = { prop: prop, box: false, shapeOnly: false, label: c.label };
    if (raw === "") return revertSide(c, prop, baseId);
    if (!accepts(probe, raw, raw)) return;
    var baseline = String(typeof baseId === "string" ? baselines[baseId] : baselines[baseId[0]]);
    if (isRevert(prop, raw, baseline)) return revertSide(c, prop, baseId);
    pushUndoWrite(selectedEl, prop);
    applyChange(selectedEl, prop, raw);
    record(selectedEl, prop, raw);
    positionBox(selBox, selectedEl);
  }
  // Is this write just putting the side back to what it already renders? Two lengths
  // are compared RESOLVED, so `2rem` is recognised as the computed `32px` it equals.
  // A keyword is compared literally, because resolving it destroys the distinction:
  // `auto` computes to `0px` on a block that is not centred, so a resolved comparison
  // would read "auto" as a revert against a `0px` baseline and record nothing - which
  // is exactly how you would try to centre something and watch nothing happen.
  function isRevert(prop, raw, baseline) {
    var lengths = /\d/.test(raw) && /\d/.test(baseline);
    return lengths ? resolveValue(prop, raw) === resolveValue(prop, baseline)
                   : raw.trim() === baseline.trim();
  }
  function revertSide(c, prop, baseId) {
    var ent = edited.get(selectedEl);
    if (ent && ent.changes[prop] !== undefined) pushUndoWrite(selectedEl, prop);
    if (ent) delete ent.changes[prop];
    rebuildInline(selectedEl, ent);
    dirty = hasRealEdits();
    status("");
    refreshChanges();
    // Put the field(s) back to the value the element is rendering again.
    [].concat(baseId).forEach(function (id) { set(id, baselines[id]); });
    positionBox(selBox, selectedEl);
  }

  // ---- the composed border --------------------------------------------------
  // Width, Style and Colour are one `border` declaration, so a write reads all
  // three fields instead of just its own - three independent writes would each
  // overwrite the others' contribution, and the result would still look like a
  // valid Patch. See ADR-0003.
  var BORDER = { width: "wt-bw", style: "wt-bs", color: "wt-bc" };
  var SEEDED_WIDTH = "1", SEEDED_STYLE = "solid";
  var MIXED_TIP = "this element's sides have different borders - editing them here " +
    "would replace them with one box";
  var MIXED_CORNERS_TIP = "this element's corners have different radii - a single " +
    "value here would round all four";

  // Which single side the controls edit, and whether they are declined outright.
  // Recomputed per selection in populate(), so it always describes the element in
  // front of the user.
  var borderSide = null;    // "bottom" etc. in per-side mode, else null
  var borderMixed = false;  // several sides differ: decline rather than wreck a design

  function capitalise(s) { return s.charAt(0).toUpperCase() + s.slice(1); }
  // The computed-style key for one border component on the edited side.
  function sideKey(component) { return "border" + capitalise(borderSide || "top") + component; }
  function visibleSides(cs) {
    return SIDES.filter(function (s) {
      return parseFloat(cs["border" + capitalise(s) + "Width"]) > 0 &&
        cs["border" + capitalise(s) + "Style"] !== "none";
    });
  }
  // A bottom rule under a heading is everywhere on the editorial pages webtweak is
  // for, and composing a four-sided `border` onto one turns a divider into a box -
  // so when exactly one side is visible, that side is what the controls edit.
  //
  // Chromium serialises the computed `border` shorthand to "" the moment the four
  // sides differ in any component, which is an exact, browser-provided test needing
  // no parsing of a multi-value width. But "differ" is not "one side", and two cases
  // prove it: `border-style: solid; border-width: 1px 2px` serialises empty with all
  // four sides visible, and `border-color: red blue` serialises empty with none
  // visible at all. So the empty shorthand only means "look closer" - the count of
  // visible sides is what decides.
  function borderMode(cs) {
    if (cs.border !== "") return { side: null, mixed: false };   // uniform, or no border
    var vis = visibleSides(cs);
    if (vis.length === 1) return { side: vis[0], mixed: false }; // a single rule: edit it
    if (vis.length === 0) return { side: null, mixed: false };   // nothing renders
    return { side: null, mixed: true };                          // a deliberate design
  }
  // The property a control writes right now. Only the composed border controls are
  // dynamic: in per-side mode the Patch must say `border-bottom`, because the side
  // IS the intent - reconcile is told never to normalise it back to all sides.
  function propOf(c) { return (c.part && borderSide) ? "border-" + borderSide : c.prop; }

  // `none` is the canonical way to say "no border"; a width and colour beside a
  // style that hides them is noise reconcile would have to see through.
  function borderDecl(w, s, col) {
    if (s === "none" || s === "") return "none";
    return w + "px " + s + " " + col;
  }
  function fieldValue(id) { var n = document.getElementById(id); return n ? n.value : ""; }
  // What the three fields describe once the parts the user did NOT touch are seeded
  // to something visible. Without the seeding, a colour alone and a width alone both
  // render nothing (the initial border style is `none`) while CSS.supports still
  // passes them - a Patch for a change the page never showed.
  function composeBorder(part, raw) {
    var w = part === "width" ? String(raw) : fieldValue(BORDER.width);
    var s = part === "style" ? String(raw) : fieldValue(BORDER.style);
    var col = part === "color" ? String(raw) : fieldValue(BORDER.color);
    if (part !== "style" && (s === "none" || s === "")) s = SEEDED_STYLE;
    if (!(parseFloat(w) > 0)) w = SEEDED_WIDTH;
    return { decl: borderDecl(w, s, col), width: w, style: s, color: col };
  }
  // The declaration the element was populated with, composed the same way, so
  // setting a colour back to the border's own colour reverts the whole change.
  function baselineBorder() {
    return borderDecl(baselines[BORDER.width], baselines[BORDER.style], baselines[BORDER.color]);
  }
  function writeBorder(c, raw) {
    // Clearing one field abandons the declaration: the three controls share one
    // property, so there is no partial border left to keep.
    if (raw === "") return revertBorder(c);
    var made = composeBorder(c.part, raw);
    // Show the seeded parts, or the panel would claim a `none` style over a page
    // that is rendering a solid border.
    set(BORDER.width, made.width);
    set(BORDER.style, made.style);
    set(BORDER.color, made.color);
    // Composed from a number input, a select and a colour swatch, so it is valid by
    // construction - checked anyway, because "valid by construction" is exactly the
    // claim that stops being true when a fourth part is added.
    if (!accepts(c, made.decl, raw)) return;
    if (made.decl === baselineBorder()) return revertBorder(c);
    commit(c, made.decl);
  }
  function revertBorder(c) {
    revertControl(c);   // c.prop is `border` for all three, so this drops the lot
    // revertControl restored the authored border on the page; put the fields back to
    // match it, including any sibling this session had seeded.
    Object.keys(BORDER).forEach(function (part) { set(BORDER[part], baselines[BORDER[part]]); });
  }
  CONTROLS.forEach(function (c) {
    var node = document.getElementById(c.id);
    if (c.kind === "sides") {
      SIDES.forEach(function (side) {
        var input = document.getElementById(c.id + "-" + side);
        if (input) input.addEventListener("input", function () { writeSides(c, side, this.value); });
      });
      var link = document.getElementById(c.id + "-link");
      if (link) link.addEventListener("click", function () {
        linked[c.id] = !linked[c.id];
        link.setAttribute("aria-pressed", linked[c.id] ? "true" : "false");
        link.classList.toggle("on", !!linked[c.id]);
      });
      return;
    }
    if (c.kind === "align") {
      node.addEventListener("click", function (ev) {
        var btn = ev.target.closest("button");
        if (!btn || !selectedEl) return;
        writeControl(c, btn.dataset.align);
        Array.prototype.forEach.call(node.querySelectorAll("button"), function (b) {
          b.classList.toggle("on", b === btn);
        });
      });
    } else {
      node.addEventListener("input", function () { writeControl(c, this.value); });
      if (c.suggest) attachSuggest(c);
      if (c.step) attachStepper(c);
    }
  });

  // ---- steppers -------------------------------------------------------------
  // Nudging a value by eye wants arrows, not typing. The arithmetic has three cases,
  // and the awkward ones are the reason this is not just <input type="number">:
  //   1.6      -> unitless, step the number
  //   1.4em    -> keep the unit, or a step would silently change what the value means
  //   normal   -> resolve to the ratio the browser is already rendering, then step it,
  //               so the first press does something instead of nothing
  function attachStepper(c) {
    var input = document.getElementById(c.id);
    ["up", "down"].forEach(function (dir) {
      var btn = document.getElementById(c.id + "-" + dir);
      if (!btn || !input) return;
      btn.addEventListener("click", function () {
        if (!selectedEl) return;
        var next = stepValue(c, input.value, dir === "up" ? 1 : -1);
        if (next === null) return;
        input.value = next;
        writeControl(c, next);   // one write path: revert, undo and validity all apply
      });
    });
  }
  // What `line-height: normal` is actually rendering as, as a ratio. It is font
  // dependent (the browser uses the face's own metrics), so it is measured rather
  // than assumed: a hidden one-line probe in the element's own font, its rendered
  // height over its font-size. The probe lives inside the Overlay's own root, so the
  // page's DOM is never touched even for an instant.
  function measuredRatio(el) {
    var cs = getComputedStyle(el);
    var size = parseFloat(cs.fontSize);
    if (!(size > 0)) return null;
    var probe = document.createElement("span");
    probe.style.cssText = "position:absolute;visibility:hidden;white-space:nowrap;" +
      "line-height:normal;padding:0;border:0;" +
      "font-family:" + cs.fontFamily + ";font-size:" + cs.fontSize +
      ";font-weight:" + cs.fontWeight + ";font-style:" + cs.fontStyle;
    probe.textContent = "Mg";
    root.appendChild(probe);
    var h = probe.getBoundingClientRect().height;
    root.removeChild(probe);
    return h > 0 ? +(h / size).toFixed(2) : null;
  }
  function stepValue(c, raw, sign) {
    var m = String(raw).trim().match(/^(-?[\d.]+)([a-z%]*)$/i);
    var value, unit;
    if (m) {
      value = parseFloat(m[1]);
      unit = m[2];
    } else {
      // A keyword has no number to step. `line-height: normal` does not even compute
      // to a length - it stays the keyword - so the ratio has to be measured.
      value = measuredRatio(selectedEl);
      unit = "";
      if (value === null) return null;
    }
    if (isNaN(value)) return null;
    var stepped = value + sign * c.step;
    if (stepped < 0) stepped = 0;               // a negative line-height is not a thing
    // Trim float noise (1.6 + 0.1 = 1.7000000000000002) without forcing decimals on
    // a value that does not need them.
    return String(+stepped.toFixed(4)) + unit;
  }

  // ---- suggestion lists -----------------------------------------------------
  // Entries are rebuilt every time a list opens rather than cached: the page's own
  // fonts are the source, and an edit (or a reconcile reload) can change them
  // mid-session.
  function attachSuggest(c) {
    var input = document.getElementById(c.id);
    var toggle = document.getElementById(c.id + "-toggle");
    var list = document.getElementById(c.id + "-list");
    if (!input || !toggle || !list) return;
    toggle.addEventListener("click", function () {
      if (list.hidden) openSuggest(c, list, toggle);
      else closeSuggest(list, toggle);
    });
    list.addEventListener("click", function (ev) {
      var item = ev.target.closest && ev.target.closest(".wt-suggest-item");
      if (!item) return;
      // Write the entry verbatim - the whole point of the list is that the
      // fallbacks the page's author intended survive the edit.
      var value = item.dataset.value;
      input.value = value;
      writeControl(c, value);
      closeSuggest(list, toggle);
    });
  }
  function openSuggest(c, list, toggle) {
    var entries = c.suggest();
    // An empty bordered box reads as broken, so say it in the status line instead.
    if (!entries.length) { status("nothing to suggest for " + c.label.toLowerCase()); return; }
    list.textContent = "";
    entries.forEach(function (value) {
      var li = document.createElement("li");
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "wt-suggest-item";
      btn.dataset.value = value;
      // textContent, never innerHTML: an entry harvested from the page is untrusted
      // input (a font family can be named anything the page's author likes).
      btn.textContent = value;
      btn.title = value;                    // the full stack, when the row ellipsises
      // Each row rendered in its own value, so a font is picked by how it looks.
      // Opt-in per control: a shadow preset row wants no such treatment.
      if (c.suggestPreview) btn.style.setProperty(c.prop, value);
      li.appendChild(btn);
      list.appendChild(li);
    });
    list.hidden = false;
    placeSuggest(list, toggle);   // measured, so only once it is visible
    toggle.setAttribute("aria-expanded", "true");
  }
  // The list is positioned in viewport coordinates because the panel is a scroll box
  // and would otherwise clip it (Shadow is the last field of the last group). Drops
  // below its toggle, flipping above when the space below is too short - and its
  // right edge lines up with the toggle's, so it reads as belonging to that field.
  function placeSuggest(list, toggle) {
    var r = toggle.getBoundingClientRect();
    var h = list.offsetHeight, w = list.offsetWidth;
    var roomBelow = window.innerHeight - r.bottom - 8;
    var top = (roomBelow >= h || r.top < h + 8) ? r.bottom + 4 : r.top - h - 4;
    list.style.top = Math.max(4, Math.min(top, window.innerHeight - h - 4)) + "px";
    list.style.left = Math.max(4, r.right - w) + "px";
  }
  function closeSuggest(list, toggle) {
    list.hidden = true;
    toggle.setAttribute("aria-expanded", "false");
  }
  // Close any open list on Esc, on a click outside it, and whenever the selection
  // changes - an open dropdown left hanging over the panel swallows clicks meant
  // for the fields beneath it.
  function eachOpenSuggest(fn) {
    Array.prototype.forEach.call(panel.querySelectorAll(".wt-suggest"), function (wrap) {
      var list = wrap.querySelector(".wt-suggest-list");
      var toggle = wrap.querySelector(".wt-suggest-toggle");
      if (list && !list.hidden) fn(list, toggle, wrap);
    });
  }
  function closeAllSuggests(exceptWrap) {
    eachOpenSuggest(function (list, toggle, wrap) {
      if (wrap !== exceptWrap) closeSuggest(list, toggle);
    });
  }
  // An open list is placed in viewport coordinates, so it has to follow its toggle
  // when the page or the panel scrolls - otherwise it strands itself beside a
  // different field, or over one.
  function repositionSuggests() { eachOpenSuggest(placeSuggest); }
  document.addEventListener("click", function (ev) {
    var wrap = ev.target.closest && ev.target.closest(".wt-suggest");
    closeAllSuggests(wrap);
  }, true);

  document.getElementById("wt-reset").addEventListener("click", function () {
    if (selectedEl) resetEl(selectedEl);
  });

  // ---- interact.js: nudge (drag interior) + resize (right/bottom grips) ------

  // Return the ratio of viewport pixels to CSS layout pixels for el's coordinate
  // space.  If an ancestor has transform:scale() (common in A4/print-preview
  // layouts to fit a large page in the viewport), getBoundingClientRect() reflects
  // the scaled viewport size while offsetWidth/Height stay in CSS layout pixels.
  // Dividing interact.js's viewport-pixel deltas by this ratio converts them to
  // the CSS translate units the element actually honours.
  // Falls back to 1 for SVG elements (no offsetWidth) and zero-size elements.
  function getParentScale(el) {
    var ow = el.offsetWidth, oh = el.offsetHeight;
    if (!ow || !oh) return { x: 1, y: 1 };
    var r = el.getBoundingClientRect();
    var sx = r.width / ow, sy = r.height / oh;
    return {
      x: (isFinite(sx) && sx > 0) ? sx : 1,
      y: (isFinite(sy) && sy > 0) ? sy : 1,
    };
  }

  // interact's rect is border-box; convert to the element's own box model so the
  // recorded value matches the panel (content-box for content-box elements) and
  // the element doesn't jump by its padding+border on the first drag.
  function resizeWrite(el, rect) {
    var cs = getComputedStyle(el);
    var w = Math.round(rect.width), h = Math.round(rect.height);
    if (cs.boxSizing !== "border-box") {
      w -= parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight) +
        parseFloat(cs.borderLeftWidth) + parseFloat(cs.borderRightWidth);
      h -= parseFloat(cs.paddingTop) + parseFloat(cs.paddingBottom) +
        parseFloat(cs.borderTopWidth) + parseFloat(cs.borderBottomWidth);
    }
    w = Math.max(1, Math.round(w));
    h = Math.max(1, Math.round(h));
    el.style.width = w + "px";
    el.style.height = h + "px";
    record(el, "width", w + "px");
    record(el, "height", h + "px");
    // If a stylesheet max-width/min-height would override the resize, pin it inline
    // so the element actually reaches the desired size.
    var cMaxW = getComputedStyle(el).maxWidth;
    if (cMaxW && cMaxW !== "none" && w > parseFloat(cMaxW)) {
      el.style.maxWidth = w + "px";
      record(el, "max-width", w + "px");
    }
    var cMinH = getComputedStyle(el).minHeight;
    if (cMinH && cMinH !== "0px" && h < parseFloat(cMinH)) {
      el.style.minHeight = h + "px";
      record(el, "min-height", h + "px");
    }
    set("wt-w", w); set("wt-h", h);
    // NB: baselines["wt-w"/"wt-h"] deliberately stay at the select-time original, so
    // typing the original size still reverts; re-typing the shown size just re-records
    // the same value (idempotent). Syncing them here would make retyping the shown size
    // delete the resize - the opposite of what's wanted.
  }
  function attachInteract(el) {
    if (!window.interact) {
      status(window.__WEBTWEAK_INTERACT_ERR__
        ? "interact.js failed to load — check browser console"
        : "interact.js not ready — drag/resize unavailable", false);
      return;
    }
    // Scale the resize grab-band to the element so small elements stay nudgeable.
    var margin = el.offsetHeight < 40 ? 4 : 10;
    // Gesture-batched undo: snapshot at start, push one batch at end.
    var nudgePrev, resizePrev, movePrev;
    interact(el)
      .draggable({
        // a nudge is a CSS transform, which has no effect on non-replaced inline
        // elements - disable it there so a drag can't record a dead nudge patch.
        // (Shapes are absolute SVGs, so they're always draggable.)
        enabled: !el.__wtInline,
        listeners: {
          start: function () {
            interacting = true; hoverBox.hidden = true;
            if (el.__wtShape) movePrev = snapshotProps(el, MOVE_PROPS);
            else nudgePrev = ((edited.get(el) || {}).changes || {}).nudge;
          },
          end: function () {
            endGesture();
            if (el.__wtShape) {
              pushGestureUndo(el, MOVE_PROPS, movePrev);
            } else {
              var cur = ((edited.get(el) || {}).changes || {}).nudge;
              if (cur !== nudgePrev) pushUndo([{ el: el, prop: "nudge", prev: nudgePrev }]);
            }
          },
          move: function (event) {
            var e = entry(el);
            var sc = getParentScale(el);
            // A shape is an absolute element: dragging is a true move - update its
            // left/top inline and record them, not a transform nudge (ADR-0002).
            // Read back from the inline style we set last frame (cheaper than
            // getComputedStyle, which would force a style recalc every pointermove).
            if (el.__wtShape) {
              var left = Math.round((parseFloat(el.style.left) || 0) + event.dx / sc.x);
              var top = Math.round((parseFloat(el.style.top) || 0) + event.dy / sc.y);
              el.style.left = left + "px";
              el.style.top = top + "px";
              record(el, "left", left + "px");
              record(el, "top", top + "px");
              positionBox(selBox, el);
              return;
            }
            e._x += event.dx / sc.x; e._y += event.dy / sc.y;
            var sx = Math.round(e._x / 4) * 4, sy = Math.round(e._y / 4) * 4;
            if (sx === 0 && sy === 0) {            // dragged back to origin: not a real nudge
              el.style.removeProperty("transform");
              delete e.changes.nudge;
              dirty = hasRealEdits();             // clear the stale unsaved flag if this was the only edit
              refreshChanges();                   // this branch skips record()
            } else {
              el.style.transform = "translate(" + sx + "px, " + sy + "px)";
              record(el, "nudge", { dx: sx, dy: sy });
            }
            positionBox(selBox, el);
          },
        },
      })
      .resizable({
        // resize is meaningless on inline (non-replaced) elements - disable it there.
        // Shapes resize via the visible grips instead (setupGripResize): interact's
        // edge band sits *inside* the element, but users aim at the grips, which
        // straddle the edge - so for shapes the whole body stays draggable (move)
        // and resize is grip-only, with no confusing near-edge dead zone.
        enabled: !el.__wtInline && !el.__wtShape,
        edges: { right: true, bottom: true, top: false, left: false },
        margin: margin,
        listeners: {
          start: function () {
            interacting = true; hoverBox.hidden = true;
            resizePrev = snapshotProps(el, RESIZE_PROPS);
          },
          end: function () {
            endGesture();
            pushGestureUndo(el, RESIZE_PROPS, resizePrev);
          },
          move: function (event) {
            resizeWrite(el, event.rect);
            positionBox(selBox, el);
          },
        },
      });
  }

  // ---- grip resize ----------------------------------------------------------
  // The visible grips are now functional handles (not just hints): interact's
  // edge band sits inside the element, so users aiming at a grip - which straddles
  // or sits outside the edge - kept missing it. Driving resize straight off the
  // grips fixes that for shapes (whose interact resize is disabled) and is a free
  // win for every other element too. width=right grip, height=bottom, both=corner.
  [{ cls: "wt-grip-r", doW: true, doH: false },
   { cls: "wt-grip-b", doW: false, doH: true },
   { cls: "wt-grip-br", doW: true, doH: true }]
    .forEach(function (spec) {
      var grip = selBox.querySelector("." + spec.cls);
      if (!grip) return;
      var doW = spec.doW, doH = spec.doH;
      grip.addEventListener("pointerdown", function (ev) {
        if (!selectedEl || selectedEl.__wtInline) return;
        ev.preventDefault();
        ev.stopPropagation();               // don't let it bubble into a select/drag
        var el = selectedEl;
        var start = el.getBoundingClientRect();
        var sc = getParentScale(el);
        var startX = ev.clientX, startY = ev.clientY;
        var prev = snapshotProps(el, RESIZE_PROPS);
        interacting = true; hoverBox.hidden = true;
        try { grip.setPointerCapture(ev.pointerId); } catch (e) { /* older engines */ }
        function move(e) {
          if (selectedEl !== el) return;   // deselected mid-gesture (e.g. Esc) - stop writing
          // start.* is the border-box in viewport px; the pointer delta is too. Add them
          // in that space, THEN divide by the parent scale once, so both terms land in the
          // CSS layout px resizeWrite writes - correct even under a transform-scaled ancestor.
          resizeWrite(el, {
            width: (doW ? start.width + (e.clientX - startX) : start.width) / sc.x,
            height: (doH ? start.height + (e.clientY - startY) : start.height) / sc.y,
          });
          positionBox(selBox, el);
        }
        function up() {
          endGesture();
          grip.removeEventListener("pointermove", move);
          grip.removeEventListener("pointerup", up);
          grip.removeEventListener("pointercancel", up);
          pushGestureUndo(el, RESIZE_PROPS, prev);
        }
        grip.addEventListener("pointermove", move);
        grip.addEventListener("pointerup", up);
        grip.addEventListener("pointercancel", up);
      });
    });

  // ---- picker ---------------------------------------------------------------
  var lastHoverEl = null;
  document.addEventListener("mousemove", function (ev) {
    if (interacting) { hoverBox.hidden = true; return; }  // don't flicker during drag/resize
    if (pendingShape) { hoverBox.hidden = true; return; }  // place mode: no select-hover
    var el = ev.target;
    if (isOverlay(el) || el === document.body || el === document.documentElement) {
      hoverBox.hidden = true;
      lastHoverEl = null;
      return;
    }
    if (el === lastHoverEl && !hoverBox.hidden) return;  // same element, already drawn
    lastHoverEl = el;
    positionBox(hoverBox, el);
  });
  document.addEventListener("mouseleave", function () { hoverBox.hidden = true; });

  // Prevent the browser's native drag (text selection drag, element drag) from
  // stealing pointer events before interact.js can track them. In editor mode,
  // native drag is never wanted on page content.
  document.addEventListener("dragstart", function (ev) {
    if (!isOverlay(ev.target)) ev.preventDefault();
  }, true);

  // Belt-and-suspenders against text selection: the overlay CSS sets
  // user-select:none on html, but a page's own CSS may override it on specific
  // selectors (e.g. p { user-select: text }).  The selectstart event fires just
  // before the browser enters selection mode, so we can veto it here regardless.
  document.addEventListener("selectstart", function (ev) {
    if (!isOverlay(ev.target)) ev.preventDefault();
  }, true);

  document.addEventListener("click", function (ev) {
    if (isOverlay(ev.target)) return;          // let panel/bar controls work
    ev.preventDefault();                        // editor mode: no navigation
    ev.stopPropagation();
    if (pendingShape) {                         // place mode: drop a shape at the click point
      placeShape(pendingShape, ev.clientX + window.scrollX, ev.clientY + window.scrollY);
      return;
    }
    if (clickEndsGesture()) return;             // tail of a drag/resize: keep the selection
    // A click inside a shape lands on its child <polygon>/<rect>; select the <svg>
    // wrapper (the thing in `edited`) instead of the inert child.
    var target = ev.target;
    var wrap = target.closest && target.closest("svg.wt-shape");
    selectEl(wrap || target);                   // otherwise select the deepest target
  }, true);

  window.addEventListener("scroll", reposition, true);
  window.addEventListener("resize", reposition);
  function reposition() {
    if (selectedEl) positionBox(selBox, selectedEl);
    hoverBox.hidden = true;
    // Also fires for the panel's own scroll: the listener is capture-phase on window,
    // and a scroll event does not bubble but is still seen on the way down.
    repositionSuggests();
  }

  document.getElementById("wt-deselect").addEventListener("click", deselect);
  document.getElementById("wt-undo").addEventListener("click", undo);
  document.getElementById("wt-redo").addEventListener("click", redo);

  // ---- keyboard -------------------------------------------------------------
  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape") {
      if (pendingShape) { exitPlaceMode(); status("placement cancelled"); return; }
      // An open suggestion list is what Esc dismisses first; the selection behind
      // it is not what the user was trying to leave.
      if (panel.querySelector(".wt-suggest-list:not([hidden])")) { closeAllSuggests(); return; }
      deselect();
      return;
    }
    if ((ev.metaKey || ev.ctrlKey) && (ev.key === "s" || ev.key === "S")) {
      ev.preventDefault();
      save();
    }
    if ((ev.metaKey || ev.ctrlKey) && !ev.shiftKey && (ev.key === "z" || ev.key === "Z")) {
      ev.preventDefault();
      undo();
    }
    // The undo binding above already excluded shift, so redo needs nothing reassigned.
    // Both keys are checked in either case: holding shift makes ev.key "Z".
    if ((ev.metaKey || ev.ctrlKey) && ev.shiftKey && (ev.key === "z" || ev.key === "Z")) {
      ev.preventDefault();
      redo();
    }
    if (ev.ctrlKey && !ev.shiftKey && (ev.key === "y" || ev.key === "Y")) {
      ev.preventDefault();
      redo();
    }
  });

  window.addEventListener("beforeunload", function (ev) {
    // `saving` too: `dirty` is cleared before the POST resolves, so without it
    // the guard goes quiet exactly while the work is still only in the browser.
    if (dirty || saving) { ev.preventDefault(); ev.returnValue = ""; }
  });

  // ---- save -----------------------------------------------------------------
  function save() {
    var patches = [];
    edited.forEach(function (e, el) {
      if (e.shape) {
        // A created shape is an insert, not a restyle: carry the shape kind +
        // self-describing geometry, an anchor (where to insert in source), and the
        // full seeded style as `changes`. Server stores patches verbatim (ADR-0002).
        patches.push({
          op: "create",
          shape: e.shape.kind,
          renderer: "svg",
          geometry: e.shape.geometry,
          anchor: { parent: fingerprint(el.parentElement || document.body), position: "append" },
          fingerprint: fingerprint(el),
          changes: e.changes,
        });
      } else if (Object.keys(e.changes).length) {
        patches.push({ fingerprint: fingerprint(el), changes: e.changes });
      }
    });
    // Re-attach patches a partial restore couldn't re-locate, so saving the elements
    // that DID restore never silently drops the ones that didn't (apply_batch replaces
    // this session's whole batch). Skip any whose element the user has since edited this
    // session (same id/selector) - the fresh patch supersedes the stranded one, so we
    // don't emit two conflicting patches for one element.
    var idKey = function (fp) { return fp.id ? "id:" + fp.id : (fp.selector ? "sel:" + fp.selector : null); };
    var covered = {};
    patches.forEach(function (p) { var k = idKey(p.fingerprint || {}); if (k) covered[k] = true; });
    missed.forEach(function (p) { var k = idKey(p.fingerprint || {}); if (!k || !covered[k]) patches.push(p); });
    // No patches AND nothing on disk for this session: genuinely nothing to do.
    // No patches but a batch IS persisted (edits saved then all reverted): fall
    // through so the empty save clears that stale batch on disk.
    if (!patches.length && !persisted) { status("nothing changed yet"); return; }
    status("saving...");
    // Cleared BEFORE the request, not in the response handler: anything the user
    // records while it is in flight is not in this payload, and its own
    // record() sets `dirty` back to true. Clearing afterwards would mark that
    // work as saved, and the live-reload guard would then reload over it.
    dirty = false;
    saving = true;
    fetch(RESERVED + "save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sessionId: SESSION, viewport: window.innerWidth, patches: patches }),
    })
      .then(function (r) { return r.json(); })
      .then(function (j) {
        saving = false;
        if (j.ok) {
          if (patches.length) wasPending = true;
          persisted = patches.length > 0;  // empty save just cleared the batch
          status(patches.length
            // Name the artefact: it teaches the hand-off for free, and it is the
            // file the user is about to ask Claude to reconcile.
            ? "saved " + j.patches + " change" + (j.patches === 1 ? "" : "s") +
              (j.file ? " -> " + j.file : "")
            : "reverted - cleared saved edits", true);
          // A save clears the unsaved-work blocker, but the source that changed
          // is still stale and no further event will fire for it. Re-run the
          // decision rather than silently dropping the warning.
          if (offeredReason) { offeredReason = null; onSourceChange(); }
          else refreshStatus();
        } else {
          dirty = hasRealEdits();    // the save did not land; it is still unsaved
          status("save failed: " + (j.error || "unknown"), false);
        }
      })
      .catch(function () {
        saving = false;
        dirty = hasRealEdits();
        status("save failed", false);
      });
  }
  document.getElementById("wt-save").addEventListener("click", save);

  // ---- restore this session's pending edits after a reload ------------------
  function restore() {
    fetchEdits()
      .then(function (doc) {
        var batch = myPending(doc)[0];
        if (!batch) return;
        persisted = true;  // a saved batch exists on disk; a full revert must clear it
        missed = [];
        var n = 0, total = (batch.patches || []).length;
        (batch.patches || []).forEach(function (p) {
          // A create patch re-injects the shape via makeShape (it has no source element
          // to relocate); its stored id + changes reproduce it exactly (ADR-0002).
          if (p.op === "create") {
            var cfp = p.fingerprint || {};
            var cid = cfp.id || ("wt-shape-" + Math.random().toString(36).slice(2, 8));
            if (document.getElementById(cid)) { n++; return; }  // already on the page
            var cch = p.changes || {};
            makeShape(p.shape, parseFloat(cch.left) || 0, parseFloat(cch.top) || 0,
              { id: cid, restore: true, geometry: p.geometry, changes: Object.assign({}, cch) });
            n++;
            return;
          }
          var fp = p.fingerprint || {}, el = null;
          try {
            el = fp.id ? document.getElementById(fp.id)
              : (fp.selector ? document.querySelector(fp.selector) : null);
          } catch (e) { /* invalid selector */ }
          // Confirm the located element is really the one that was edited. The tag must
          // match (an id can be moved to a different-tag element in source), and if the
          // fingerprint recorded ownText it must still match (a positional selector or a
          // reused id can otherwise hit the wrong same-tag element after a source reorder).
          // On any mismatch, keep the patch for reconcile rather than mis-applying it.
          var elOwn = el ? ownText(el) : "";
          // A recorded ownText that no longer matches (including a now-empty element)
          // means this isn't the same element - strand the patch rather than mis-apply it.
          if (!el || (fp.tag && el.tagName.toLowerCase() !== fp.tag) ||
              (fp.ownText && elOwn !== fp.ownText)) {
            missed.push(p);  // keep the patch; the next save must NOT drop it
            return;
          }
          var e = entry(el); // captures authored baseline before re-applying
          Object.keys(p.changes || {}).forEach(function (prop) {
            var v = p.changes[prop];
            applyChange(el, prop, v);           // single place that maps a change to inline style
            e.changes[prop] = v;
            if (prop === "nudge") { e._x = v.dx; e._y = v.dy; }  // also seed the interact offset
          });
          n++;
        });
        refreshChanges();
        if (total) {
          var lost = total - n;
          status("restored " + n + " of " + total + " edited element" + (total === 1 ? "" : "s") +
            (lost ? "; " + lost + " could not be re-located (kept for reconcile)" : ""), lost === 0);
        }
      })
      .catch(function () { /* no edits file yet */ });
  }
  // ---- session change list --------------------------------------------------
  // `edited` holds the whole session but the panel only ever shows one element,
  // so after a handful of edits there was no way to review what you had done
  // without saving and opening the JSON. Save should not be a leap of faith.

  var changesBox  = document.getElementById("wt-changes");
  var changesHead = document.getElementById("wt-changes-head");
  var changesList = document.getElementById("wt-changes-list");
  var changesOpen = false;
  var changesSig = null;    // row signature, so an unchanged list is not rebuilt

  function changeSummary(e) {
    return Object.keys(e.changes).map(function (p) {
      return p === "nudge" ? "nudge " + e.changes[p].dx + "," + e.changes[p].dy : p;
    }).join(", ");
  }

  // record() fires per pointermove, so rebuilding on every one churned the whole
  // list DOM dozens of times per drag. Skip while a gesture is running;
  // endGesture() refreshes once on pointer-up. Nobody reads the list mid-drag.
  function refreshChanges() {
    if (!changesBox) return;          // called before the overlay finished mounting
    if (interacting) return;
    repaintBadge();                   // the badge depends on hasRealEdits() too
    var rows = [];
    edited.forEach(function (e, el) {
      if (Object.keys(e.changes).length) rows.push({ el: el, e: e });
    });
    if (!rows.length) {
      changesBox.hidden = true;
      changesList.textContent = "";   // drop element refs held by stale rows
      changesHead.textContent = "";   // ...and don't leave it claiming a change that is gone
      changesSig = null;
      return;
    }
    changesBox.hidden = false;
    changesHead.textContent = rows.length + " element" + (rows.length === 1 ? "" : "s") +
      " changed " + (changesOpen ? "▾" : "▸");
    changesHead.setAttribute("aria-expanded", changesOpen ? "true" : "false");
    changesList.hidden = !changesOpen;
    if (!changesOpen) return;

    // Rebuild only when the rows themselves changed. Selecting an element, and
    // typing in a panel field, both call in here - tearing down every row for
    // those made the list flicker and reset its scroll position mid-review.
    var sig = rows.map(function (r) {
      return (r.e.shape ? "shape:" + r.e.shape.kind : describe(r.el)) + "|" + changeSummary(r.e);
    }).join("\n");
    if (sig === changesSig) return paintSelection(rows);
    changesSig = sig;

    changesList.textContent = "";
    rows.forEach(function (row) {
      var li  = document.createElement("li");
      var btn = document.createElement("button");
      btn.className = "wt-change";
      btn.__wtEl = row.el;             // so paintSelection can find its row
      // textContent, never innerHTML: these strings come from the page's own
      // markup (tag, id, class names) and must never be parsed as HTML.
      var name = document.createElement("span");
      name.className = "wt-change-el";
      // A shape's id is a throwaway overlay handle (wt-shape-<rand>) that
      // reconcile strips, so name the kind the user actually drew instead.
      name.textContent = row.e.shape
        ? "shape: " + (row.e.shape.kind || "shape")
        : describe(row.el);
      var props = document.createElement("span");
      props.className = "wt-change-props";
      props.textContent = changeSummary(row.e);
      btn.appendChild(name);
      btn.appendChild(props);
      btn.addEventListener("click", function () {
        if (!document.contains(row.el)) { status("that element is no longer on the page", false); return; }
        selectEl(row.el);
        row.el.scrollIntoView({ block: "center", behavior: "smooth" });
      });
      li.appendChild(btn);
      changesList.appendChild(li);
    });
    paintSelection(rows);
  }

  // The `.on` highlight is the only thing a selection change affects, so move it
  // in place rather than rebuilding the list around it.
  function paintSelection() {
    Array.prototype.forEach.call(changesList.querySelectorAll(".wt-change"), function (btn) {
      btn.classList.toggle("on", btn.__wtEl === selectedEl);
    });
  }

  changesHead.addEventListener("click", function () {
    changesOpen = !changesOpen;
    changesSig = null;      // rows are discarded when collapsed; force a rebuild
    refreshChanges();
  });

  // ---- live source reload + reconcile status --------------------------------
  // The other half of the loop runs in a different window: you save, tell Claude
  // to reconcile, and until now had no way to know whether it worked without
  // reloading by hand. The server watches the served tree and pushes an event
  // when the source under the page changes, so a reconcile lands visibly here.

  var badge = document.getElementById("wt-badge");
  var offeredReason = null;  // 'unsaved' | 'pending' | 'vanished' while an offer stands
  var lastDoc = null;        // last edits doc we read, so the badge can repaint free
  var wasPending = false;    // our batch has been seen pending -> a later reconcile is news
  var es = null;

  function setBadge(text, kind, title) {
    // Always drop any previous handler: a stale one from the "reload" badge
    // would otherwise stay live on a later chip that styles itself
    // cursor:default and does not look clickable.
    badge.onclick = null;
    if (!text) { badge.hidden = true; badge.textContent = ""; badge.title = ""; return; }
    badge.hidden = false;
    badge.textContent = text;
    badge.className = "wt-badge" + (kind ? " wt-badge-" + kind : "");
    badge.title = title || "";
  }

  function fetchEdits() {
    return fetch(RESERVED + "edits", { cache: "no-store" })
      .then(function (r) { return r.json(); })
      .catch(function () { return null; });
  }

  function myBatches(doc) {
    return ((doc && doc.batches) || []).filter(function (b) {
      return b && b.sessionId === SESSION;
    });
  }

  function myPending(doc) {
    return myBatches(doc).filter(function (b) { return b.status === "pending"; });
  }

  function noteDoc(doc) {
    if (!doc) return;
    lastDoc = doc;
    if (myPending(doc).length) wasPending = true;
  }

  // --- "is it safe to reload right now?" -------------------------------------
  // One question, asked in exactly one place. Re-deriving it per call site is
  // how one path ends up checking only half of it. Every half FAILS CLOSED: a
  // reload we decline costs a click, a reload we should not have taken costs
  // the user's session.

  // Unsaved work would be lost. `dirty`, not hasRealEdits(): after a Save the
  // batch is on disk and restore() brings it back, and reloading after a save is
  // the whole point - that is when Claude reconciles. `interacting` matters
  // because `dirty` flickers false mid-drag when a nudge passes back through its
  // origin; `saving` because `dirty` is cleared before the POST resolves, so
  // during the round trip the page looks clean while nothing is on disk yet.
  function localSafe() { return !dirty && !interacting && !saving; }

  // Reasons the on-disk state makes a reload unsafe:
  //  - we could not read the edits file at all, so we know nothing (fail closed);
  //  - our batch is still `pending`, because reconcile writes source FIRST and
  //    marks second (SKILL.md steps 7 then 8), so restore() would re-apply it on
  //    top of source Claude already rewrote - doubling a nudge;
  //  - we saved a batch but the file no longer carries it. That is a deleted or
  //    reverted edits file, NOT a reconcile, and `serveEdits` reports a missing
  //    file as `{"batches": []}` - indistinguishable from "reconciled" unless we
  //    check for our batch rather than for the absence of a pending one.
  function diskSafe(doc) {
    if (!doc) return false;
    if (myPending(doc).length) return false;
    if (persisted && !myBatches(doc).length) return false;
    return true;
  }

  // Our batch is present AND every part of it is reconciled. Deliberately not
  // "no pending batch": that is also true when the file has vanished, and when
  // the only pending batch belongs to another session.
  function myReconciled(doc) {
    var mine = myBatches(doc);
    return mine.length > 0 && mine.every(function (b) { return b.status === "reconciled"; });
  }

  // The only path to location.reload(). `onBlocked(reason)` decides what the
  // user sees when it refuses.
  function tryReload(onBlocked) {
    if (!localSafe()) return onBlocked("unsaved");
    return fetchEdits().then(function (doc) {
      noteDoc(doc);
      if (!localSafe()) return onBlocked("unsaved");   // changed while we asked
      if (!diskSafe(doc)) {
        return onBlocked(myPending(doc).length ? "pending" : "vanished");
      }
      location.reload();
    });
  }

  var OFFERS = {
    unsaved: ["source changed - reload",
      "Your source changed on disk. You have unsaved edits; click to reload and lose them."],
    pending: ["reconciling...",
      "Your source changed while this session's edits are still pending. " +
      "Waiting for Claude to mark them reconciled - reloading now would apply them twice."],
    vanished: ["edits file gone",
      "This session's saved edits are no longer in the edits file. Reloading would " +
      "discard the changes still shown on the page; click only if you meant to lose them."],
  };

  function offerReload(reason) {
    offeredReason = reason;
    var copy = OFFERS[reason] || OFFERS.unsaved;
    setBadge(copy[0], "warn", copy[1]);
    // The click re-asks rather than reloading blind: the user may have started
    // editing since the offer went up, or the batch may still be pending.
    badge.onclick = function () {
      tryReload(function (why) {
        status(why === "pending"
          ? "still reconciling - your saved edits would be applied twice"
          : why === "vanished"
            ? "the edits file no longer has this session's batch"
            : "unsaved edits - save or reset first", false);
        offerReload(why);        // re-state the current reason; never latch a stale one
      });
    };
  }

  // Reflect the edits file's own view of the world: our session's batch is
  // pending until Claude flips it to reconciled. Takes an already-fetched doc
  // when the caller has one, so an event does not read the same file twice.
  function refreshStatus(doc) {
    if (doc === undefined) {
      return fetchEdits().then(function (d) { lastDoc = d || lastDoc; refreshStatus(d); });
    }
    if (!doc || offeredReason) return;   // an outstanding offer is the louder message
    var pending = myPending(doc);
    if (pending.length) {
      var n = pending.reduce(function (t, b) { return t + ((b.patches || []).length); }, 0);
      return setBadge(n + " pending", "pending",
        n + " change(s) waiting for Claude to reconcile into source");
    }
    var mine = (doc.batches || []).filter(function (b) { return b && b.sessionId === SESSION; });
    if (mine.length && !hasRealEdits()) {
      return setBadge("reconciled", "ok",
        "Claude has folded this session's changes into your source");
    }
    setBadge("");
  }

  // Repaint from the last doc we read - no fetch, so it is cheap enough to call
  // on every local mutation. Without this the green "reconciled" chip stayed up
  // over fresh unsaved work, reading as "already in source" when it was not.
  function repaintBadge() {
    if (lastDoc) refreshStatus(lastDoc);
  }

  function onSourceChange() {
    tryReload(offerReload);
  }

  // The edits file is watched separately from source, because `mark` touches
  // only that file - without this the badge could never reach "reconciled".
  function onEditsChange() {
    fetchEdits().then(function (doc) {
      if (!doc) return;
      var pendingBefore = wasPending;
      noteDoc(doc);
      wasPending = pendingBefore || wasPending;
      // Reload only on the pending -> reconciled TRANSITION, never on the state
      // alone: after the reload our batch is still reconciled, so reloading on
      // state would loop forever (es.onopen fires on every reconnect). "No
      // pending batch" is also true when the file was deleted and when the only
      // pending batch belongs to another session - neither is a reason to reload.
      if (localSafe() && wasPending && myReconciled(doc)) {
        offeredReason = null;
        location.reload();       // batch marked and source final: the real result
        return;
      }
      // An outstanding offer is re-evaluated, not preserved: reconcile can leave
      // a batch pending on purpose (SKILL.md step 8), and the old latch left the
      // badge stuck on "reconciling..." for the rest of the session.
      // Our saved batch is no longer in the file (deleted, or reverted by a VCS
      // checkout). Say so: the edits are still on screen and can be re-saved,
      // but nothing else would tell the user the on-disk copy is gone.
      if (persisted && !myBatches(doc).length) return offerReload("vanished");
      if (offeredReason) {
        offeredReason = null;
        return void tryReload(offerReload);
      }
      refreshStatus(doc);
    });
  }

  function connectEvents() {
    if (typeof EventSource === "undefined") return;   // no live reload; everything else works
    try { es = new EventSource(RESERVED + "events"); }
    catch (_) { return; }
    es.addEventListener("source-change", onSourceChange);
    es.addEventListener("edits-change", onEditsChange);
    es.onerror = function () {
      // EventSource reconnects on its own, so a transient error is not worth
      // reporting. A CLOSED stream is terminal though, and silently losing live
      // reload is exactly the kind of thing the user should be told about.
      if (es && es.readyState === 2 && !offeredReason) {
        setBadge("live reload offline", null,
          "Lost the connection to webtweak; source changes will not reload the page.");
      }
    };
    // ...and take the notice back down once it reconnects, or the page keeps
    // claiming to be offline after the server returns.
    es.onopen = function () { refreshStatus(); };   // clear an offline notice; never reload
    // Release the socket promptly: an open SSE stream occupies one of the
    // browser's six per-origin connections.
    window.addEventListener("pagehide", function () { if (es) es.close(); });
  }

  restore();
  refreshChanges();
  refreshStatus();
  connectEvents();
})();
