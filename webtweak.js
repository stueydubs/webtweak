#!/usr/bin/env node
// webtweak - a local visual editor for hand-coded HTML/CSS pages.
//
// Opens a local source .html file in the browser with an editing overlay,
// captures visual changes as machine-readable patches, and writes them to a
// running-history edits file (<name>.webtweak.json) next to the page. Claude
// then reconciles those patches into the real source. See CONTEXT.md / ADR-0001.
//
// Node.js stdlib only. No dependencies.
'use strict';

const http  = require('node:http');
const fs    = require('node:fs');
const path  = require('node:path');
const os    = require('node:os');
const { execFile } = require('node:child_process');

const TOOL_DIR   = path.dirname(path.resolve(__filename));
const OVERLAY_DIR = path.join(TOOL_DIR, 'overlay');
const RESERVED   = '/__webtweak__/';
const MAX_BODY   = 8 * 1024 * 1024; // 8 MB cap on a save payload
const MAX_BAKS   = 3;               // keep only the newest N corrupt-file backups
const VERSION    = readVersion();

function readVersion() {
  try {
    return JSON.parse(fs.readFileSync(path.join(TOOL_DIR, 'package.json'), 'utf8')).version || '0.0.0';
  } catch (_) { return '0.0.0'; }
}

const OVERLAY_ASSETS = {
  'overlay.js':       'application/javascript; charset=utf-8',
  'overlay.css':      'text/css; charset=utf-8',
  'interact.min.js':  'application/javascript; charset=utf-8',
};

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.htm':  'text/html; charset=utf-8',
  '.css':  'text/css; charset=utf-8',
  '.js':   'application/javascript; charset=utf-8',
  '.mjs':  'application/javascript; charset=utf-8',
  '.json': 'application/json',
  '.png':  'image/png',
  '.jpg':  'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif':  'image/gif',
  '.svg':  'image/svg+xml',
  '.ico':  'image/x-icon',
  '.webp': 'image/webp',
  '.avif': 'image/avif',
  '.woff': 'font/woff',
  '.woff2':'font/woff2',
  '.ttf':  'font/ttf',
  '.otf':  'font/otf',
  '.eot':  'application/vnd.ms-fontobject',
  '.txt':  'text/plain; charset=utf-8',
  '.xml':  'text/xml; charset=utf-8',
  '.mp4':  'video/mp4',
  '.webm': 'video/webm',
  '.mp3':  'audio/mpeg',
  '.ogg':  'audio/ogg',
  '.wasm': 'application/wasm',
  '.map':  'application/json',
  '.csv':  'text/csv; charset=utf-8',
  '.jsonld':      'application/ld+json',
  '.webmanifest': 'application/manifest+json',
};

// --- pure functions (no I/O) -----------------------------------------------

function overlayMarkup(targetName) {
  // Use ': ' separator to match Python's json.dumps format (tests rely on this).
  const cfg = '{"target": ' + JSON.stringify(targetName) + '}';
  return (
    '\n<!-- webtweak overlay (injected, not part of source) -->\n' +
    `<script>window.__WEBTWEAK__ = ${cfg};</script>\n` +
    `<link rel="stylesheet" href="${RESERVED}overlay.css">\n` +
    `<script src="${RESERVED}interact.min.js" onerror="window.__WEBTWEAK_INTERACT_ERR__=true"></script>\n` +
    `<script src="${RESERVED}overlay.js" defer></script>\n`
  );
}

function injectOverlay(html, targetName) {
  const markup = overlayMarkup(targetName);
  const idx = html.toLowerCase().lastIndexOf('</body>');
  if (idx === -1) return html + markup;
  return html.slice(0, idx) + markup + html.slice(idx);
}

function applyBatch(doc, payload, now) {
  if (doc && typeof doc === 'object' && Array.isArray(doc.batches)) {
    doc = Object.assign({}, doc);
  } else {
    doc = { target: payload.target || null, batches: [] };
  }
  if (!doc.target && payload.target) doc.target = payload.target;

  const patches = Array.isArray(payload.patches) ? payload.patches : [];
  const session = payload.sessionId || 'unknown';
  const batches = doc.batches.slice();

  if (!patches.length) {
    // Empty save: user reverted every edit this session - drop their pending batch.
    doc.batches = batches.filter(b =>
      !(b && typeof b === 'object' && b.sessionId === session && b.status === 'pending')
    );
    return doc;
  }

  const batch = {
    sessionId: session,
    savedAt:   now,
    viewport:  payload.viewport || null,
    status:    'pending',
    patches,
  };

  const idx = batches.findIndex(b =>
    b && typeof b === 'object' && b.sessionId === session && b.status === 'pending'
  );
  if (idx >= 0) batches[idx] = batch;
  else batches.push(batch);
  doc.batches = batches;
  return doc;
}

// webtweak binds to loopback, but "loopback" is not an origin boundary: any page
// the user has open can POST to a guessable localhost port, and a text/plain body
// is a CORS *simple* request so no preflight stands in the way. The edits file is
// read back as instructions during reconcile, so an unauthenticated write reaches
// real source. Only same-origin (or origin-less, i.e. curl) requests may save.
function originAllowed(req, port) {
  const origin = req.headers['origin'];
  if (origin === undefined) return true;      // non-browser client; no ambient authority
  return origin === `http://127.0.0.1:${port}` || origin === `http://localhost:${port}`;
}

// Reject a forged Host header (DNS rebinding): an attacker-controlled name that
// resolves to 127.0.0.1 would otherwise make the served directory same-origin.
function hostAllowed(req, port) {
  const host = req.headers['host'];
  if (host === undefined) return true;        // HTTP/1.0 client
  return host === `127.0.0.1:${port}` || host === `localhost:${port}`;
}

// Returns the exact bytes written, so a caller can recognise its own write.
function writeJsonAtomic(filePath, doc) {
  const body = JSON.stringify(doc, null, 2) + '\n';
  // Namespace the temp file by pid so two webtweak processes on the same page
  // cannot clobber each other's half-written file.
  const tmp = `${filePath}.${process.pid}.tmp`;
  try {
    const fd = fs.openSync(tmp, 'w');
    try {
      fs.writeFileSync(fd, body, 'utf8');
      fs.fsyncSync(fd);            // durability parity with the reference implementation
    } finally { fs.closeSync(fd); }
    fs.renameSync(tmp, filePath);
    return body;
  } catch (e) {
    try { fs.unlinkSync(tmp); } catch (_) {}
    throw e;
  }
}

// Keep only the newest MAX_BAKS corrupt-file backups; they land in the user's own
// site repo next to the page, so unbounded growth is their mess, not ours.
function pruneBackups(editsPath) {
  const dir  = path.dirname(editsPath);
  const base = path.basename(editsPath) + '.';
  let baks;
  try {
    baks = fs.readdirSync(dir)
      .filter(f => f.startsWith(base) && f.endsWith('.bak'))
      .sort();
  } catch (_) { return; }
  for (const f of baks.slice(0, Math.max(0, baks.length - MAX_BAKS))) {
    try { fs.unlinkSync(path.join(dir, f)); } catch (_) {}
  }
}

// --- source watching -------------------------------------------------------

const MAX_WATCHED_DIRS = 2000;   // inotify has a per-user ceiling; degrade before hitting it

// webtweak's own writes must never trigger a reload, or every Save would bounce
// the page the user is still editing. This one regex covers all of them - the
// atomic temp (`x.webtweak.json.<pid>.tmp`) and the corrupt-file backup
// (`x.webtweak.json.<iso>.bak`) both keep the `.webtweak.json.` infix. Matching
// bare `.tmp`/`.bak` as well would hide the *user's* files of those names.
function isOwnArtefact(name) {
  return /\.webtweak\.json(\.|$)/.test(name);
}

// The edits file itself, so a reconcile marking a batch can be told apart from
// webtweak writing its own save.
function isEditsFile(name) {
  return /\.webtweak\.json$/.test(name);
}

function isSkippedDir(name) {
  return name === 'node_modules' || name.startsWith('.');
}

// Watch the served tree so a reconcile (Claude rewriting the CSS) can push the
// page a reload. Deliberately NOT fs.watch(recursive) - that only landed on
// Linux in Node 20 and this package supports 18 - so we walk and watch each
// directory. Failures degrade to "no live reload", never to a crash.
//
// `contains(realPath)` gates which directories may be watched: the initial walk
// uses Dirent.isDirectory() (does not follow symlinks) but an fs.watch event only
// gives a name, so the child has to be stat'd - and a stat follows links. Without
// the gate, a symlink created at runtime would have us watching outside the root.
function createWatcher(root, onChange, contains) {
  const watchers = new Map();
  const timers = new Map();      // one debounce per event kind, not one shared
  let capped = false;

  function fire(name) {
    // A nameless event (fs.watch permits one on some platforms) cannot be
    // classified, so treating it as source would let our own Save bounce the
    // page - the exact failure this design exists to prevent. Ignore it.
    if (!name) return;
    const base = path.basename(name);
    if (isOwnArtefact(base) && !isEditsFile(base)) return;   // .tmp / .bak churn
    // Editors write in bursts (temp file, rename, chmod); one reload is enough.
    // Debounce per kind: a shared timer let an edits write cancel a pending
    // source write, losing the reload that actually mattered.
    const kind = isEditsFile(base) ? 'edits' : 'source';
    clearTimeout(timers.get(kind));
    timers.set(kind, setTimeout(() => { timers.delete(kind); onChange(kind, name); }, 120));
  }

  function forget(dir, w) {
    try { w.close(); } catch (_) {}
    if (watchers.get(dir) === w) watchers.delete(dir);
  }

  function mayWatch(child) {
    let real;
    try { real = fs.realpathSync(child); }
    catch (_) { return false; }
    return contains(real);
  }

  function watchDir(dir, depth) {
    if (watchers.has(dir) || depth > 12) return;
    if (watchers.size >= MAX_WATCHED_DIRS) { capped = true; return; }
    let w;
    try {
      w = fs.watch(dir, (_ev, name) => {
        // Reap a directory that has been deleted. Without this its stale entry
        // keeps watchers.has() true, so a recreated directory of the same name
        // is never re-watched and live reload silently dies for that subtree -
        // and repeated churn leaks handles until MAX_WATCHED_DIRS is exhausted.
        if (!fs.existsSync(dir)) { forget(dir, w); return fire(name); }
        fire(name);
        if (!name || isSkippedDir(path.basename(name))) return;
        const child = path.join(dir, name);
        try {
          if (fs.lstatSync(child).isDirectory() && mayWatch(child)) watchDir(child, depth + 1);
        } catch (_) {}                     // vanished between event and stat
      });
    } catch (_) { return; }                // permissions, ENOSPC - just skip it
    w.on('error', () => forget(dir, w));
    watchers.set(dir, w);

    let entries;
    try { entries = fs.readdirSync(dir, { withFileTypes: true }); }
    catch (_) { return; }
    for (const e of entries) {
      if (e.isDirectory() && !isSkippedDir(e.name)) watchDir(path.join(dir, e.name), depth + 1);
    }
  }

  watchDir(root, 0);
  return {
    // Getters, not snapshots: the walk continues at runtime as directories are
    // created, so a value frozen at boot could only ever describe the first walk.
    get count()  { return watchers.size; },
    get capped() { return capped; },
    close() {
      for (const t of timers.values()) clearTimeout(t);
      timers.clear();
      for (const w of watchers.values()) { try { w.close(); } catch (_) {} }
      watchers.clear();
    },
  };
}

// --- server-sent events ----------------------------------------------------

function serveEvents(req, res, clients) {
  res.writeHead(200, {
    'Content-Type':  'text/event-stream; charset=utf-8',
    'Cache-Control': 'no-store',
    'Connection':    'keep-alive',
  });
  if (res.socket) res.socket.setTimeout(0);   // an SSE stream is meant to idle
  res.write('retry: 2000\n\n');
  clients.add(res);
  req.on('close', () => clients.delete(res));
}

function broadcast(clients, event, data) {
  const payload = `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
  for (const res of clients) {
    // write() on a dead response returns false rather than throwing, so a
    // try/catch alone would never prune. Check the state instead.
    if (res.writableEnded || res.destroyed) { clients.delete(res); continue; }
    try { res.write(payload); } catch (_) { clients.delete(res); }
  }
}

// --- HTTP helpers ----------------------------------------------------------

function send(res, code, body, ctype, method) {
  const buf = Buffer.isBuffer(body) ? body : Buffer.from(body, 'utf8');
  res.writeHead(code, {
    'Content-Type':   ctype,
    'Content-Length': buf.length,
    'Cache-Control':  'no-store',
  });
  if (method === 'HEAD') return res.end();
  res.end(buf);
}

function sendError(res, code, msg) {
  send(res, code, `${code} ${msg}\n`, 'text/plain; charset=utf-8');
}

function log(msg) {
  process.stderr.write(`  webtweak: ${msg}\n`);
}

// --- request handlers ------------------------------------------------------

function serveOverlayAsset(name, res) {
  const asset = path.resolve(OVERLAY_DIR, name);
  // Path-traversal guard: must stay inside OVERLAY_DIR
  if (asset !== OVERLAY_DIR &&
      !asset.startsWith(OVERLAY_DIR + path.sep)) {
    return sendError(res, 404, 'Unknown webtweak asset');
  }
  const ctype = OVERLAY_ASSETS[name];
  if (!ctype) return sendError(res, 404, 'Unknown webtweak asset');
  let buf;
  try { buf = fs.readFileSync(asset); }
  catch (_) { return sendError(res, 404, 'Unknown webtweak asset'); }
  send(res, 200, buf, ctype);
}

function serveEdits(editsPath, res) {
  let body = '{"batches": []}';
  try {
    const raw = fs.readFileSync(editsPath, 'utf8');
    JSON.parse(raw); // validate; fall back to empty on corrupt
    body = raw;
  } catch (_) {}
  send(res, 200, body, 'application/json');
}

function contained(p, root) {
  return p === root || p.startsWith(root + path.sep);
}

function serveHtml(filePath, targetName, method, res) {
  let html;
  try { html = fs.readFileSync(filePath, 'utf8'); }
  catch (e) { return sendError(res, 500, 'Read error'); }
  send(res, 200, injectOverlay(html, targetName), 'text/html; charset=utf-8', method);
}

// Any HTML that is not the target page is served as-is, so following a nav link
// out of the target gives you the real page rather than a mis-aimed editor.
function servePlainHtml(filePath, method, res) {
  let html;
  try { html = fs.readFileSync(filePath, 'utf8'); }
  catch (e) { return sendError(res, 500, 'Read error'); }
  send(res, 200, html, 'text/html; charset=utf-8', method);
}

// Stream rather than readFileSync: this server is single-threaded, so slurping a
// hero video or a large PDF blocks every other request (including the overlay's
// own assets). Range support matters too - Safari and iOS refuse to play a
// <video> without it, which would make the page render unlike production.
function serveStatic(filePath, size, method, range, res) {
  const ctype = MIME[path.extname(filePath).toLowerCase()] || 'application/octet-stream';
  const head  = { 'Content-Type': ctype, 'Cache-Control': 'no-store', 'Accept-Ranges': 'bytes' };

  let start = 0, end = size - 1, code = 200;
  const m = /^bytes=(\d*)-(\d*)$/.exec(range || '');
  if (m && size > 0) {
    if (m[1] === '' && m[2] === '') return sendError(res, 416, 'Range Not Satisfiable');
    if (m[1] === '') { start = Math.max(0, size - parseInt(m[2], 10)); }
    else {
      start = parseInt(m[1], 10);
      if (m[2] !== '') end = Math.min(end, parseInt(m[2], 10));
    }
    if (isNaN(start) || isNaN(end) || start > end || start >= size) {
      res.writeHead(416, { 'Content-Range': `bytes */${size}`, 'Cache-Control': 'no-store' });
      return res.end();
    }
    code = 206;
    head['Content-Range'] = `bytes ${start}-${end}/${size}`;
  }

  head['Content-Length'] = size === 0 ? 0 : end - start + 1;
  res.writeHead(code, head);
  if (method === 'HEAD' || size === 0) return res.end();

  const stream = fs.createReadStream(filePath, { start, end });
  stream.on('error', () => res.destroy());
  res.on('close', () => stream.destroy());
  stream.pipe(res);
}

function editsPathFor(targetPath) {
  const stem = path.basename(targetPath, path.extname(targetPath));
  return path.join(path.dirname(targetPath), stem + '.webtweak.json');
}

function handleSave(body, targetName, editsPath, state, res) {
  let payload;
  try { payload = JSON.parse(body || '{}'); }
  catch (_) { return sendError(res, 400, 'Bad JSON'); }
  if (!payload || typeof payload !== 'object' || Array.isArray(payload))
    return sendError(res, 400, 'Bad JSON: expected an object');

  let doc = null;
  if (fs.existsSync(editsPath)) {
    let raw;
    try { raw = fs.readFileSync(editsPath, 'utf8'); }
    catch (e) {
      // Transient read error - propagate; don't touch the file
      return send(res, 500, JSON.stringify({ ok: false, error: e.message }), 'application/json');
    }
    try { doc = JSON.parse(raw); }
    catch (_) {
      // Corrupt JSON - back up and start fresh. If the backup cannot be taken we
      // must NOT continue: writeJsonAtomic would overwrite the only copy of a
      // file the user may still be able to salvage by hand.
      const backup = `${editsPath}.${new Date().toISOString().replace(/[:.]/g, '-')}.bak`;
      try { fs.renameSync(editsPath, backup); }
      catch (e) {
        return send(res, 500, JSON.stringify({
          ok: false,
          error: `edits file is corrupt and could not be backed up: ${e.message}`,
        }), 'application/json');
      }
      log(`edits file corrupt; backed up to ${path.basename(backup)}`);
      pruneBackups(editsPath);
    }
  }

  if (!payload.target) payload = Object.assign({ target: targetName }, payload);
  const now = new Date().toISOString().slice(0, 19);
  doc = applyBatch(doc, payload, now);
  let written;
  try { written = writeJsonAtomic(editsPath, doc); }
  catch (e) {
    return send(res, 500, JSON.stringify({ ok: false, error: e.message }), 'application/json');
  }

  // Remember exactly what we wrote so the watcher can tell our own save from a
  // reconcile. The bytes we produced, not a re-read: a timestamp window is a
  // race, and re-reading lets an external writer landing in between be recorded
  // as "self", muting the very event we need.
  if (state) state.lastSelfWrite = written;
  const n = (payload.patches || []).length;
  log(`saved ${n} patch(es) -> ${path.basename(editsPath)}`);
  send(res, 200, JSON.stringify({ ok: true, file: path.basename(editsPath), patches: n }), 'application/json');
}

function createHandler(targetPath, serveRoot, state) {
  const targetName = path.basename(targetPath);
  const editsPath  = editsPathFor(targetPath);

  return function (req, res) {
    const rawPath = (req.url || '/').split('?')[0];

    // A forged Host means someone is driving us through a name they control.
    if (!hostAllowed(req, state.port)) return sendError(res, 403, 'Forbidden');

    // --- webtweak API endpoints and overlay assets -------------------------
    if (rawPath.startsWith(RESERVED)) {
      const name = rawPath.slice(RESERVED.length);

      if (name === 'edits' && req.method === 'GET') {
        if (!originAllowed(req, state.port)) return sendError(res, 403, 'Forbidden');
        return serveEdits(editsPath, res);
      }

      if (name === 'events' && req.method === 'GET') {
        if (!originAllowed(req, state.port)) return sendError(res, 403, 'Forbidden');
        return serveEvents(req, res, state.clients);
      }

      if (name === 'save' && req.method === 'POST') {
        if (!originAllowed(req, state.port)) return sendError(res, 403, 'Forbidden');
        // Require a JSON content-type: text/plain would make this a CORS simple
        // request that no preflight can stop.
        const ctype = (req.headers['content-type'] || '').split(';')[0].trim().toLowerCase();
        if (ctype !== 'application/json') return sendError(res, 415, 'Expected application/json');

        const lenStr = req.headers['content-length'];
        const length = parseInt(lenStr, 10);
        if (!lenStr || isNaN(length) || length < 0) return sendError(res, 400, 'Bad Content-Length');
        if (length > MAX_BODY) return sendError(res, 413, 'Payload too large');

        const chunks = [];
        let received = 0;
        req.on('data', chunk => {
          received += chunk.length;
          if (received > MAX_BODY) {   // stop reading rather than draining the whole upload
            sendError(res, 413, 'Payload too large');
            return req.destroy();
          }
          chunks.push(chunk);
        });
        req.on('end', () => {
          if (received > MAX_BODY) return;                 // already answered above
          if (received < length) return sendError(res, 400, 'Incomplete request body');
          handleSave(Buffer.concat(chunks).toString('utf8'), targetName, editsPath, state, res);
        });
        req.on('error', () => sendError(res, 400, 'Incomplete request body'));
        return;
      }

      return serveOverlayAsset(name, res);
    }

    // --- static file serving -----------------------------------------------
    if (req.method !== 'GET' && req.method !== 'HEAD')
      return sendError(res, 405, 'Method not allowed');

    let decoded;
    try { decoded = decodeURIComponent(rawPath); }
    catch (_) { return sendError(res, 400, 'Bad URL'); }

    // Resolve and contain within serveRoot (path-traversal guard)
    let local = path.resolve(serveRoot, decoded.replace(/^\/+/, ''));
    if (!contained(local, serveRoot)) return sendError(res, 403, 'Forbidden');

    let stat;
    try { stat = fs.statSync(local); }
    catch (_) { return sendError(res, 404, 'Not found'); }

    // A directory serves its index.html if present. Listings stay off either way:
    // without this, every root-relative nav link on the page dead-ends.
    if (stat.isDirectory()) {
      const index = path.join(local, 'index.html');
      try {
        if (!fs.statSync(index).isFile()) throw new Error('not a file');
      } catch (_) { return sendError(res, 404, 'No listing'); }
      local = index;
      stat  = fs.statSync(local);
    }

    // path.resolve does not follow symlinks, so a link inside the served
    // directory could otherwise hand out a file from anywhere on disk.
    let real;
    try { real = fs.realpathSync(local); }
    catch (_) { return sendError(res, 404, 'Not found'); }
    if (!contained(real, state.realRoot)) return sendError(res, 403, 'Forbidden');

    const ext = path.extname(local).toLowerCase();
    if (ext === '.html' || ext === '.htm') {
      // Only the target page gets the overlay. Injecting into every HTML file
      // handed the editor a page it could not correctly fingerprint, and wrote
      // those patches into the *target's* edits file.
      if (real === state.realTarget) return serveHtml(local, targetName, req.method, res);
      return servePlainHtml(local, req.method, res);
    }
    serveStatic(local, stat.size, req.method, req.headers['range'], res);
  };
}

// --- browser opener --------------------------------------------------------

function openBrowser(url) {
  const cmds = {
    darwin: ['open',     [url]],
    win32:  ['cmd',      ['/c', 'start', '', url]],
  };
  const [cmd, args] = cmds[os.platform()] || ['xdg-open', [url]];
  const child = execFile(cmd, args, { detached: true }, () => {});
  child.unref();   // detached alone still holds an event-loop reference
}

// --- server ----------------------------------------------------------------

// Edits left pending from a previous session are invisible otherwise: restore()
// only re-applies the current session's own batch, so they silently accumulate.
function countPending(targetPath) {
  const editsPath = editsPathFor(targetPath);
  try {
    const doc = JSON.parse(fs.readFileSync(editsPath, 'utf8'));
    if (!doc || !Array.isArray(doc.batches)) return 0;
    return doc.batches.filter(b => b && b.status === 'pending').length;
  } catch (_) { return 0; }
}

function serve(targetPath, serveRoot, port, openBrowserFlag) {
  // Resolved once at boot: the containment check compares real paths, so the
  // root it compares against must be real too (macOS /tmp -> /private/tmp).
  const state = {
    port:       port,
    realRoot:   fs.realpathSync(serveRoot),
    realTarget: fs.realpathSync(targetPath),
    clients:    new Set(),          // open SSE streams
    lastSelfWrite: null,            // exact bytes we last wrote to the edits file
  };
  const handler   = createHandler(targetPath, serveRoot, state);
  const server    = http.createServer(handler);
  server.requestTimeout = 30_000;   // a lying Content-Length must not park a socket forever

  // Tell open pages when the source under them changes, so a reconcile shows up
  // in the browser instead of the user having to guess and reload. The edits
  // file is reported separately: reconcile writes source first and marks the
  // batch second, so the page needs to distinguish "source moved" from "my
  // batch was reconciled" to avoid re-applying a batch that is still pending.
  const watcher = createWatcher(serveRoot, (kind, changed) => {
    if (kind === 'edits') {
      // Ignore the echo of our own save; only an outside writer is interesting.
      let now = null;
      try { now = fs.readFileSync(editsPathFor(targetPath), 'utf8'); } catch (_) {}
      if (now !== null && now === state.lastSelfWrite) return;
      return broadcast(state.clients, 'edits-change', { file: changed });
    }
    broadcast(state.clients, 'source-change', { file: changed });
  }, real => contained(real, state.realRoot));
  const ping = setInterval(() => {
    for (const res of state.clients) { try { res.write(': ping\n\n'); } catch (_) {} }
  }, 25_000);
  ping.unref();                     // a heartbeat must not hold the process open

  server.listen(port, '127.0.0.1', () => {
    const actual = server.address().port;
    state.port   = actual;          // --port 0 means the real port is only known now
    // With --root the page may sit in a subfolder of the web root, so its URL
    // is its path relative to that root, not just its basename.
    // Encode each segment: --root means intermediate directories now appear in
    // the URL, and a name containing a space or '#' produced a link that opened
    // the wrong path (or 404'd on the fragment).
    const rel    = path.relative(serveRoot, targetPath)
      .split(path.sep).map(encodeURIComponent).join('/');
    const url    = `http://127.0.0.1:${actual}/${rel}`;
    process.stdout.write(`webtweak editing: ${targetPath}\n`);
    process.stdout.write(`  serving ${serveRoot}\n`);
    // Flush before remaining lines so the test harness sees the port immediately.
    process.stdout.write(`  listening on 127.0.0.1:${actual}\n`, () => {
      process.stdout.write(`  open    ${url}\n`);
      const pending = countPending(targetPath);
      if (pending) {
        process.stdout.write(`  note    ${pending} batch(es) from a previous session are not yet reconciled\n`);
      }
      if (watcher.count === 0) {
        process.stdout.write(`  note    could not watch ${serveRoot} - live reload is off\n`);
      } else if (watcher.capped) {
        process.stdout.write(`  note    watching the first ${watcher.count} directories only; deep changes may not reload\n`);
      }
      process.stdout.write(`  Ctrl-C to stop.\n\n`);
    });
    if (openBrowserFlag) openBrowser(url);
  });

  server.on('error', e => {
    const hint = e.code === 'EADDRINUSE'
      ? `cannot bind port ${port}. Try --port 0 for any free port.`
      : e.message;
    process.stderr.write(`webtweak: ${hint}\n`);
    process.exit(1);
  });

  process.on('SIGINT', () => {
    process.stdout.write('\nwebtweak stopped.\n');
    clearInterval(ping);
    watcher.close();
    // An open SSE stream keeps its socket alive, so close() alone would hang.
    for (const res of state.clients) { try { res.end(); } catch (_) {} }
    state.clients.clear();
    server.close(() => process.exit(0));
    setTimeout(() => process.exit(0), 500).unref();
  });
}

// --- CLI -------------------------------------------------------------------

const USAGE = 'Usage: webtweak <page.html> [--port N] [--no-browser]';

const HELP = `webtweak ${VERSION} - a local visual editor for hand-coded HTML/CSS.

${USAGE}

Opens your page in the browser with an editing overlay. Drag, resize and
restyle by eye; webtweak records what changed - it never edits your source.
On Save it writes <page>.webtweak.json next to the page, and Claude
reconciles those changes into your real HTML/CSS.

Arguments:
  <page.html>       the local source page to edit; its directory is served
                    so CSS, images and fonts resolve as they do in your build

Options:
  --root DIR        serve DIR as the web root instead of the page's own folder.
                    Use it when the page lives in a subfolder and references
                    root-absolute assets (/css/site.css, /assets/...)
  --port N          port to listen on (default 8723; 0 picks any free port)
  --no-browser      start the server without opening a browser
  --install-skill   copy the reconcile skill into ~/.claude/skills/ and exit
  -v, --version     print the version and exit
  -h, --help        show this help and exit

Reconciling needs Python 3 and Claude. Run --install-skill once, then ask
Claude Code to "reconcile page.html".

Home: https://github.com/stueydubs/webtweak`;

// Works identically for a git clone, a global install and npx - the skill is
// copied out of the installed package rather than the user's cwd.
function installSkill() {
  const src  = path.join(TOOL_DIR, 'reconcile');
  const dest = path.join(os.homedir(), '.claude', 'skills', 'webtweak-reconcile');
  if (!fs.existsSync(path.join(src, 'SKILL.md'))) {
    process.stderr.write(`webtweak: bundled skill not found at ${src}\n`);
    process.exit(1);
  }
  try {
    fs.mkdirSync(path.dirname(dest), { recursive: true });
    fs.cpSync(src, dest, { recursive: true });
    // npm does not preserve the +x bit on every install path; the skill invokes
    // this script directly, so make sure it is runnable wherever it landed.
    try { fs.chmodSync(path.join(dest, 'scripts', 'wtreconcile.py'), 0o755); } catch (_) {}
  } catch (e) {
    process.stderr.write(`webtweak: could not install skill: ${e.message}\n`);
    process.exit(1);
  }
  process.stdout.write(`webtweak: reconcile skill installed to ${dest}\n`);
  process.stdout.write('  restart Claude Code, then ask it to "reconcile <page>.html"\n');
  process.exit(0);
}

function die(msg) {
  process.stderr.write(`webtweak: ${msg}\n`);
  process.exit(1);
}

function main() {
  const args = process.argv.slice(2);
  let htmlFile = null, rootArg = null, port = 8723, noBrowser = false;

  for (let i = 0; i < args.length; i++) {
    const a = args[i];
    // Accept --port=N as well as --port N; argparse did, so users expect it.
    const eq = a.startsWith('--port=') ? a.slice('--port='.length) : null;
    const rootEq = a.startsWith('--root=') ? a.slice('--root='.length) : null;

    if (a === '--port' || eq !== null) {
      const raw = eq !== null ? eq : args[++i];
      if (raw === undefined) die('--port needs a number, e.g. --port 8723');
      if (!/^\d+$/.test(raw)) die(`--port must be a whole number, got ${raw}`);
      port = parseInt(raw, 10);
      if (port > 65535) die(`--port must be between 0 and 65535, got ${port}`);
    } else if (a === '--root' || rootEq !== null) {
      const raw = rootEq !== null ? rootEq : args[++i];
      // `--root=` yields '' rather than undefined, and path.resolve('') is the
      // cwd - so without the falsy check it silently served the wrong directory.
      if (!raw) die('--root needs a directory, e.g. --root .');
      rootArg = raw;
    } else if (a === '--no-browser') {
      noBrowser = true;
    } else if (a === '--install-skill') {
      installSkill();
    } else if (a === '--help' || a === '-h') {
      process.stdout.write(HELP + '\n');
      process.exit(0);
    } else if (a === '--version' || a === '-v') {
      process.stdout.write(VERSION + '\n');
      process.exit(0);
    } else if (!a.startsWith('-')) {
      if (htmlFile !== null) die(`expected one page, got two: ${htmlFile} and ${a}`);
      htmlFile = a;
    } else {
      die(`unknown option ${a}\n${USAGE}`);
    }
  }

  if (!htmlFile) die(`path to an .html file is required\n${USAGE}`);

  const targetPath = path.resolve(htmlFile);
  let stat;
  try { stat = fs.statSync(targetPath); }
  catch (_) { die(`no such file: ${targetPath}`); }
  if (stat.isDirectory()) die(`that's a directory, not a page: ${targetPath}\n${USAGE}`);

  const ext = path.extname(targetPath).toLowerCase();
  if (ext !== '.html' && ext !== '.htm')
    die(`expected an .html file, got ${ext || 'no extension'}: ${targetPath}`);

  // Default web root is the page's own directory. --root points it at the real
  // site root so a subfolder page can resolve /css/site.css and friends.
  let serveRoot = path.dirname(targetPath);
  if (rootArg !== null) {
    serveRoot = path.resolve(rootArg);
    let rootStat;
    try { rootStat = fs.statSync(serveRoot); }
    catch (_) { die(`--root: no such directory: ${serveRoot}`); }
    if (!rootStat.isDirectory()) die(`--root must be a directory: ${serveRoot}`);
    // The page has to be reachable from the root, or none of its URLs work.
    if (!contained(fs.realpathSync(targetPath), fs.realpathSync(serveRoot)))
      die(`--root must contain the page.\n  root: ${serveRoot}\n  page: ${targetPath}`);
  }

  serve(targetPath, serveRoot, port, !noBrowser);
}

// Importable as a module so the pure functions can be unit-tested directly.
// Requiring this file must never start a server.
if (require.main === module) main();
else module.exports = { injectOverlay, overlayMarkup, applyBatch };
