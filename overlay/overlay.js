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
  ];
  var GROUPS = ["Type", "Colour", "Box"];

  // ---- DOM scaffolding ------------------------------------------------------
  var root = document.createElement("div");
  root.id = "wt-root";
  root.innerHTML = [
    '<div class="wt-bar wt-ui">',
    '  <span class="wt-logo">webtweak</span>',
    '  <span class="wt-crumb" id="wt-crumb">click an element to select</span>',
    '  <span class="wt-status" id="wt-status"></span>',
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
  ].join("\n");
  document.body.appendChild(root);

  var hoverBox = document.getElementById("wt-hover");
  var selBox = document.getElementById("wt-selected");
  var selTag = document.getElementById("wt-seltag");
  var crumbEl = document.getElementById("wt-crumb");
  var statusEl = document.getElementById("wt-status");
  var panel = document.getElementById("wt-panel");

  function panelHTML() {
    var parts = ['<div class="wt-panel wt-ui" id="wt-panel" hidden>', "  <h3>Properties</h3>"];
    GROUPS.forEach(function (g) {
      parts.push('  <div class="wt-group"><div class="wt-legend">' + g + "</div>");
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
    if (c.kind === "number") return '<input type="number" id="' + c.id + '" min="' + (c.box ? 0 : 1) + '"> px';
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
    if (!el || el === document.body || el === document.documentElement) return;
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
    if (selectedEl && window.interact) interact(selectedEl).unset();
    interacting = false;  // unset() can abort an in-flight gesture without firing 'end'
    selectedEl = null;
    selBox.hidden = true;
    panel.hidden = true;
    crumbEl.textContent = "click an element to select";
  }

  function resetEl(el) {
    var e = edited.get(el);
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
  // transform, unlike ordinary inline text boxes. Keyed by uppercase tagName.
  var REPLACED = { IMG: 1, SVG: 1, VIDEO: 1, CANVAS: 1, IFRAME: 1, EMBED: 1,
    OBJECT: 1, PICTURE: 1, INPUT: 1, TEXTAREA: 1, SELECT: 1, BUTTON: 1, AUDIO: 1 };

  function populate(el) {
    var cs = getComputedStyle(el);
    var ent = edited.get(el);
    baselines = {};
    CONTROLS.forEach(function (c) {
      var shown = c.read(cs);            // current (possibly already-edited) value -> the panel
      var base = shown;
      // After a reload+restore the override is applied inline, so computed == the
      // edited value. Recover the true authored baseline by reading computed with
      // just this property's override peeled off, so "revert to original" is still
      // detected (and doesn't record a no-op patch setting a prop to its own origin).
      if (ent && ent.changes && c.prop && Object.prototype.hasOwnProperty.call(ent.changes, c.prop)) {
        base = withTempStyle(el,
          function (s) { s.removeProperty(c.prop); },
          function () { return c.read(getComputedStyle(el)); });
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
    // width/height + nudge are inert on NON-REPLACED inline elements - disable them
    // so a user can't record a dead patch the element never honours. Replaced inline
    // elements (img, svg, video, form controls...) DO honour sizing/transform, so they
    // stay enabled even at display:inline.
    var inlineOnly = cs.display === "inline" && !REPLACED[el.tagName];
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
  function applyChange(el, prop, value) {
    if (prop === "nudge") el.style.transform = "translate(" + value.dx + "px, " + value.dy + "px)";
    else el.style.setProperty(prop, value);
  }
  // Rebuild an element's inline style from its authored original plus the session's
  // remaining changes. Used to revert a single property without a removeProperty() that
  // would wipe a coexisting authored inline longhand the user never touched.
  function rebuildInline(el, ent) {
    if (!ent || ent.origStyle == null) el.removeAttribute("style");
    else el.setAttribute("style", ent.origStyle);
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
    // Guard the "" === "" trap: an engine that serialises an asymmetric computed
    // shorthand as "" must not make every typed value look like a revert.
    if (revertTarget !== "" && revertTarget === baselines[c.id]) {
      var ent = edited.get(selectedEl);
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
    if (!c.box && !CSS.supports(c.prop, v)) { status("ignored invalid " + c.prop + ": " + raw, false); return; }
    selectedEl.style.setProperty(c.prop, v);
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
    set("wt-w", w); set("wt-h", h);
    // NB: baselines["wt-w"/"wt-h"] deliberately stay at the select-time original, so
    // typing the original size still reverts; re-typing the shown size just re-records
    // the same value (idempotent). Syncing them here would make retyping the shown size
    // delete the resize - the opposite of what's wanted.
  }
  function attachInteract(el) {
    if (!window.interact) return;
    // Scale the resize grab-band to the element so small elements stay nudgeable.
    var margin = el.offsetHeight < 40 ? 4 : 10;
    interact(el)
      .draggable({
        // a nudge is a CSS transform, which has no effect on non-replaced inline
        // elements - disable it there so a drag can't record a dead nudge patch
        enabled: !el.__wtInline,
        listeners: {
          start: function () { interacting = true; hoverBox.hidden = true; },
          end: function () { interacting = false; },
          move: function (event) {
            var e = entry(el);
            e._x += event.dx; e._y += event.dy;
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
        // resize is meaningless on inline (non-replaced) elements - disable it there
        enabled: !el.__wtInline,
        edges: { right: true, bottom: true, top: false, left: false },
        margin: margin,
        listeners: {
          start: function () { interacting = true; hoverBox.hidden = true; },
          end: function () { interacting = false; },
          move: function (event) {
            resizeWrite(el, event.rect);
            positionBox(selBox, el);
          },
        },
      });
  }

  // ---- picker ---------------------------------------------------------------
  var lastHoverEl = null;
  document.addEventListener("mousemove", function (ev) {
    if (interacting) { hoverBox.hidden = true; return; }  // don't flicker during drag/resize
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

  document.addEventListener("click", function (ev) {
    if (isOverlay(ev.target)) return;          // let panel/bar controls work
    ev.preventDefault();                        // editor mode: no navigation
    ev.stopPropagation();
    selectEl(ev.target);                        // always select the deepest target
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
    if (ev.key === "Escape") { deselect(); return; }
    if ((ev.metaKey || ev.ctrlKey) && (ev.key === "s" || ev.key === "S")) {
      ev.preventDefault();
      save();
    }
  });

  window.addEventListener("beforeunload", function (ev) {
    if (dirty) { ev.preventDefault(); ev.returnValue = ""; }
  });

  // ---- save -----------------------------------------------------------------
  function save() {
    var patches = [];
    edited.forEach(function (e, el) {
      if (Object.keys(e.changes).length) {
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
