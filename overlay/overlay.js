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
  var persisted = false;   // this session has a saved/restored batch on disk to clear
  var missed = [];         // restored patches we couldn't re-locate - preserved across saves
  var interacting = false; // a drag/resize gesture is in progress
  var undoStack = [];      // stack of batches: each [{el, prop, prev}]
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
  }
  // True iff any edited element still holds real changes - the single source of
  // truth for the unsaved-changes (beforeunload) guard, so resets that empty the
  // map don't leave a stale dirty flag.
  function hasRealEdits() {
    var any = false;
    edited.forEach(function (e) { if (Object.keys(e.changes).length) any = true; });
    return any;
  }
  // ---- undo -----------------------------------------------------------------
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
    if (top && !top.gesture && top.length === 1 && top[0].el === el && top[0].prop === prop) return;
    undoStack.push([{ el: el, prop: prop, prev: prev }]);
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
    if (batch.length) { batch.gesture = true; undoStack.push(batch); }  // own undo step, never collapsed
  }
  var MOVE_PROPS = ["left", "top"];                                  // a shape drag
  var RESIZE_PROPS = ["width", "height", "max-width", "min-height"]; // any resize gesture

  function applyUndoBatch(batch) {
    // Collect unique elements so each element's inline is rebuilt exactly once.
    var els = [];
    batch.forEach(function (u) {
      // Undoing a shape's creation removes the element and its edited entry outright.
      if (u.create) {
        if (u.el === selectedEl) deselect();
        if (u.el.parentNode) u.el.parentNode.removeChild(u.el);
        edited.delete(u.el);
        return;
      }
      var ent = entry(u.el);
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
    dirty = hasRealEdits();
    status("undone");
  }

  function undo() {
    if (!undoStack.length) { status("nothing to undo"); return; }
    applyUndoBatch(undoStack.pop());
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
      read: function (cs) { return cs.fontFamily; } },  // full stack, so editing keeps fallbacks
    { group: "Type", id: "wt-fs", prop: "font-size", label: "Size", kind: "number", unit: "px",
      read: function (cs) { return px(cs.fontSize); } },
    { group: "Type", id: "wt-fw", prop: "font-weight", label: "Weight", kind: "select",
      opts: ["100", "200", "300", "400", "500", "600", "700", "800", "900"],
      read: function (cs) { return String(parseInt(cs.fontWeight, 10) || 400); } },
    { group: "Type", id: "wt-lh", prop: "line-height", label: "Line", kind: "text",
      // show the unitless ratio (computed resolves to px); writing a bare number keeps it unitless
      read: function (cs) {
        if (cs.lineHeight === "normal") return "normal";
        var fs = parseFloat(cs.fontSize), lh = parseFloat(cs.lineHeight);
        return (fs > 0 && lh > 0) ? String(+(lh / fs).toFixed(2)) : cs.lineHeight;
      } },
    { group: "Type", id: "wt-ls", prop: "letter-spacing", label: "Spacing", kind: "text",
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
    { group: "Box", id: "wt-margin", prop: "margin", label: "Margin", kind: "text",
      read: function (cs) { return cs.margin; } },
    { group: "Box", id: "wt-padding", prop: "padding", label: "Padding", kind: "text",
      read: function (cs) { return cs.padding; } },
    // Shape-only: fill/stroke/stroke-width are inherited SVG presentation properties,
    // so writing them on the <svg> cascades to its child shape (one place to edit
    // colour for every shape kind). `rx` is NOT inherited - it's a <rect> geometry
    // property, so its control reads/writes the child via `host` (see applyChange).
    // shapeOnly controls skip the CSS.supports gate: a colour swatch or a px number
    // is always valid, and CSS.supports can report SVG presentation props unevenly.
    { group: "Shape", id: "wt-fill", prop: "fill", label: "Fill", kind: "color", shapeOnly: true,
      read: function (cs) { return rgbToHex(cs.fill); } },
    { group: "Shape", id: "wt-stroke", prop: "stroke", label: "Border", kind: "color", shapeOnly: true,
      read: function (cs) { return rgbToHex(cs.stroke); } },
    { group: "Shape", id: "wt-sw", prop: "stroke-width", label: "Border width", kind: "number", unit: "px", shapeOnly: true,
      read: function (cs) { return px(cs.strokeWidth); } },
    { group: "Shape", id: "wt-rx", prop: "rx", label: "Radius", kind: "number", unit: "px",
      shapeOnly: true, rectOnly: true, host: function (el) { return el.firstElementChild; },
      read: function (cs) { return px(cs.rx); } },
  ];
  var GROUPS = ["Type", "Colour", "Box", "Shape"];

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
      undoStack.push([{ el: svg, create: true }]);  // Cmd+Z removes the shape
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
    '  <div class="wt-shapes" id="wt-shapes">',
    '    <button class="wt-btn" id="wt-shape-btn">Shape ▾</button>',
    '    <div class="wt-palette" id="wt-palette" hidden></div>',
    "  </div>",
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
    '<div class="wt-hint wt-ui">Click to select. Drag the interior to <b>nudge</b>, drag the right/bottom/corner grips to <b>resize</b>. <b>Esc</b> deselect, <b>Cmd/Ctrl+S</b> save.</div>',
    '<div class="wt-place-hint wt-ui" id="wt-place-hint" hidden><b>Click anywhere</b> to drop the shape. <b>Esc</b> to cancel.</div>',
  ].join("\n");
  document.body.appendChild(root);

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
        parts.push(field(c.label, controlMarkup(c)));
      });
      parts.push("  </div>");
    });
    parts.push('  <button class="wt-btn wt-block" id="wt-reset">Reset this element</button>');
    parts.push('  <p class="wt-note">Changes preview live and are captured as intent. Claude reconciles them into clean CSS on save.</p>');
    parts.push("</div>");
    return parts.join("\n");
  }
  function controlMarkup(c) {
    // 0 is meaningful for box sizes and shape props (stroke-width 0 = no border, rx 0 =
    // sharp corners); other numbers (font-size) floor at 1.
    if (c.kind === "number") return '<input type="number" id="' + c.id + '" min="' + (c.box || c.shapeOnly ? 0 : 1) + '"> px';
    if (c.kind === "color") return '<input type="color" id="' + c.id + '">';
    if (c.kind === "select") return select(c.id, c.opts);
    if (c.kind === "align") return alignButtons(c.id);
    return '<input type="text" id="' + c.id + '">';
  }
  function field(label, control) {
    return '  <div class="wt-field"><label>' + label + "</label>" + control + "</div>";
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

  function nonWtClasses(el) {
    return Array.prototype.filter.call(el.classList, function (c) {
      return c.indexOf("wt-") !== 0;
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
    crumbEl.innerHTML = chain.map(function (node, i) {
      var label = describe(node);
      return i === chain.length - 1 ? "<b>" + label + "</b>" : label;
    }).join(" &rsaquo; ");
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
  }

  function deselect() {
    if (pendingShape) exitPlaceMode();  // a Deselect/Esc during place mode also cancels placement
    if (selectedEl && window.interact) interact(selectedEl).unset();
    interacting = false;  // unset() can abort an in-flight gesture without firing 'end'
    selectedEl = null;
    selBox.hidden = true;
    panel.hidden = true;
    crumbEl.textContent = "click an element to select";
  }

  function resetEl(el) {
    var e = edited.get(el);
    // A created shape has no authored baseline to revert to - resetting it removes it.
    if (e && e.shape) {
      if (el === selectedEl) deselect();
      if (el.parentNode) el.parentNode.removeChild(el);
      edited.delete(el);
      dirty = hasRealEdits();
      status("shape removed");
      return;
    }
    if (e) {
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
    CONTROLS.forEach(function (c) {
      // Most controls read/write the element itself; `host` (rx only) targets the
      // child shape node, since rx is a non-inherited <rect> geometry property. Only
      // resolve it for shapes, so selecting a normal element never probes (and forces
      // a style recalc on) a child node for a control it will never show.
      var host = (c.host && ent && ent.shape && c.host(el)) || el;
      var hcs = host === el ? cs : getComputedStyle(host);
      var shown = c.read(hcs);            // current (possibly already-edited) value -> the panel
      var base = shown;
      // After a reload+restore the override is applied inline, so computed == the
      // edited value. Recover the true authored baseline by reading computed with
      // just this property's override peeled off, so "revert to original" is still
      // detected (and doesn't record a no-op patch setting a prop to its own origin).
      if (ent && ent.changes && c.prop && Object.prototype.hasOwnProperty.call(ent.changes, c.prop)) {
        base = withTempStyle(host,
          function (s) { s.removeProperty(c.prop); },
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
  // Resolve a typed value to its computed form via the element, so a shorthand like
  // margin "10px 20px" can be compared to the computed 4-value baseline.
  function resolveValue(prop, value) {
    return withTempStyle(selectedEl,
      function (s) { s.setProperty(prop, value); },
      function () { return getComputedStyle(selectedEl)[prop]; });
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
  function writeControl(c, raw) {
    if (!selectedEl) return;
    if (raw === "" && c.kind !== "align") return;           // cleared field: nothing to apply/record
    if (c.box) raw = Math.max(1, parseInt(raw, 10) || 1);   // width/height floor of 1, matching resize
    // Setting a control back to the value it was populated with means "revert this
    // property" - drop the override + the recorded change rather than baking a no-op
    // (also stops an accidental opaque #000000 from a transparent-shown colour swatch).
    // Shorthand props (margin/padding) carry a computed 4-value baseline, so resolve
    // the typed value through the element before comparing.
    var revertTarget = (c.prop === "margin" || c.prop === "padding") ? resolveValue(c.prop, raw) : String(raw);
    // A shape's seeded properties (fill/stroke/stroke-width/rx and width/height) have
    // no authored baseline and must stay in the self-contained create patch, so those
    // writes are always recorded - a 1px border or a #000000 fill can't be mistaken for
    // a revert against the SVG UA default the baseline peel resolves to. But margin/
    // padding on a shape ARE ordinary (not seeded), so they still revert normally.
    var noRevert = selectedEl.__wtShape && (c.shapeOnly || c.box);
    // Guard the "" === "" trap: an engine that serialises an asymmetric computed
    // shorthand as "" must not make every typed value look like a revert.
    if (!noRevert && revertTarget !== "" && revertTarget === baselines[c.id]) {
      var ent = edited.get(selectedEl);
      if (ent && ent.changes[c.prop] !== undefined) pushUndoWrite(selectedEl, c.prop);
      if (ent) delete ent.changes[c.prop];
      rebuildInline(selectedEl, ent);  // restore authored inline + remaining edits (preserves longhands)
      dirty = hasRealEdits();          // reverting the last edit must clear the stale unsaved flag
      positionBox(selBox, selectedEl);
      return;
    }
    var v = c.unit ? raw + c.unit : raw;
    if (c.prop === "font-family") v = quoteFamily(raw);
    // Don't bake a phantom patch the page never showed: if the browser would
    // reject this value (a typo like "banana" in a free-text field), the live
    // preview wouldn't change either, so leave any prior valid edit untouched.
    if (!c.box && !c.shapeOnly && !CSS.supports(c.prop, v)) { status("ignored invalid " + c.prop + ": " + raw, false); return; }
    pushUndoWrite(selectedEl, c.prop);
    applyChange(selectedEl, c.prop, v);  // routes rx to the child node; plain setProperty otherwise
    record(selectedEl, c.prop, v);
    positionBox(selBox, selectedEl);                        // any edit can reflow - always re-fit the box
  }
  CONTROLS.forEach(function (c) {
    var node = document.getElementById(c.id);
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
    }
  });

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
            interacting = false;
            if (el.__wtShape) {
              pushGestureUndo(el, MOVE_PROPS, movePrev);
            } else {
              var cur = ((edited.get(el) || {}).changes || {}).nudge;
              if (cur !== nudgePrev) undoStack.push([{ el: el, prop: "nudge", prev: nudgePrev }]);
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
            interacting = false;
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
          interacting = false;
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
  }

  document.getElementById("wt-deselect").addEventListener("click", deselect);

  // ---- keyboard -------------------------------------------------------------
  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape") {
      if (pendingShape) { exitPlaceMode(); status("placement cancelled"); return; }
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
  });

  window.addEventListener("beforeunload", function (ev) {
    if (dirty) { ev.preventDefault(); ev.returnValue = ""; }
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
    fetch(RESERVED + "save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sessionId: SESSION, viewport: window.innerWidth, patches: patches }),
    })
      .then(function (r) { return r.json(); })
      .then(function (j) {
        if (j.ok) {
          dirty = false;
          persisted = patches.length > 0;  // empty save just cleared the batch
          status(patches.length
            ? "saved " + j.patches + " change" + (j.patches === 1 ? "" : "s")
            : "reverted - cleared saved edits", true);
        } else {
          status("save failed: " + (j.error || "unknown"), false);
        }
      })
      .catch(function () { status("save failed", false); });
  }
  document.getElementById("wt-save").addEventListener("click", save);

  // ---- restore this session's pending edits after a reload ------------------
  function restore() {
    fetch(RESERVED + "edits")
      .then(function (r) { return r.json(); })
      .then(function (doc) {
        var batch = (doc.batches || []).filter(function (b) {
          return b.status === "pending" && b.sessionId === SESSION;
        })[0];
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
        if (total) {
          var lost = total - n;
          status("restored " + n + " of " + total + " edited element" + (total === 1 ? "" : "s") +
            (lost ? "; " + lost + " could not be re-located (kept for reconcile)" : ""), lost === 0);
        }
      })
      .catch(function () { /* no edits file yet */ });
  }
  restore();
})();
