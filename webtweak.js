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

function writeJsonAtomic(filePath, doc) {
  // Namespace the temp file by pid so two webtweak processes on the same page
  // cannot clobber each other's half-written file.
  const tmp = `${filePath}.${process.pid}.tmp`;
  try {
    const fd = fs.openSync(tmp, 'w');
    try {
      fs.writeFileSync(fd, JSON.stringify(doc, null, 2) + '\n', 'utf8');
      fs.fsyncSync(fd);            // durability parity with the reference implementation
    } finally { fs.closeSync(fd); }
    fs.renameSync(tmp, filePath);
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

function handleSave(body, targetName, serveRoot, res) {
  let payload;
  try { payload = JSON.parse(body || '{}'); }
  catch (_) { return sendError(res, 400, 'Bad JSON'); }
  if (!payload || typeof payload !== 'object' || Array.isArray(payload))
    return sendError(res, 400, 'Bad JSON: expected an object');

  const stem      = path.basename(targetName, path.extname(targetName));
  const editsPath = path.join(serveRoot, stem + '.webtweak.json');

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
  try { writeJsonAtomic(editsPath, doc); }
  catch (e) {
    return send(res, 500, JSON.stringify({ ok: false, error: e.message }), 'application/json');
  }

  const n = (payload.patches || []).length;
  log(`saved ${n} patch(es) -> ${path.basename(editsPath)}`);
  send(res, 200, JSON.stringify({ ok: true, file: path.basename(editsPath), patches: n }), 'application/json');
}

function createHandler(targetPath, serveRoot, state) {
  const targetName = path.basename(targetPath);
  const stem       = path.basename(targetName, path.extname(targetName));

  return function (req, res) {
    const rawPath = (req.url || '/').split('?')[0];

    // A forged Host means someone is driving us through a name they control.
    if (!hostAllowed(req, state.port)) return sendError(res, 403, 'Forbidden');

    // --- webtweak API endpoints and overlay assets -------------------------
    if (rawPath.startsWith(RESERVED)) {
      const name = rawPath.slice(RESERVED.length);

      if (name === 'edits' && req.method === 'GET') {
        if (!originAllowed(req, state.port)) return sendError(res, 403, 'Forbidden');
        return serveEdits(path.join(serveRoot, stem + '.webtweak.json'), res);
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
          handleSave(Buffer.concat(chunks).toString('utf8'), targetName, serveRoot, res);
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
  const stem      = path.basename(targetPath, path.extname(targetPath));
  const editsPath = path.join(path.dirname(targetPath), stem + '.webtweak.json');
  try {
    const doc = JSON.parse(fs.readFileSync(editsPath, 'utf8'));
    if (!doc || !Array.isArray(doc.batches)) return 0;
    return doc.batches.filter(b => b && b.status === 'pending').length;
  } catch (_) { return 0; }
}

function serve(targetPath, port, openBrowserFlag) {
  const serveRoot = path.dirname(targetPath);
  // Resolved once at boot: the containment check compares real paths, so the
  // root it compares against must be real too (macOS /tmp -> /private/tmp).
  const state = {
    port:       port,
    realRoot:   fs.realpathSync(serveRoot),
    realTarget: fs.realpathSync(targetPath),
  };
  const handler   = createHandler(targetPath, serveRoot, state);
  const server    = http.createServer(handler);
  server.requestTimeout = 30_000;   // a lying Content-Length must not park a socket forever

  server.listen(port, '127.0.0.1', () => {
    const actual = server.address().port;
    state.port   = actual;          // --port 0 means the real port is only known now
    const url    = `http://127.0.0.1:${actual}/${path.basename(targetPath)}`;
    process.stdout.write(`webtweak editing: ${targetPath}\n`);
    process.stdout.write(`  serving ${serveRoot}\n`);
    // Flush before remaining lines so the test harness sees the port immediately.
    process.stdout.write(`  listening on 127.0.0.1:${actual}\n`, () => {
      process.stdout.write(`  open    ${url}\n`);
      const pending = countPending(targetPath);
      if (pending) {
        process.stdout.write(`  note    ${pending} batch(es) from a previous session are not yet reconciled\n`);
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
    server.close(() => process.exit(0));
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
  let htmlFile = null, port = 8723, noBrowser = false;

  for (let i = 0; i < args.length; i++) {
    const a = args[i];
    // Accept --port=N as well as --port N; argparse did, so users expect it.
    const eq = a.startsWith('--port=') ? a.slice('--port='.length) : null;

    if (a === '--port' || eq !== null) {
      const raw = eq !== null ? eq : args[++i];
      if (raw === undefined) die('--port needs a number, e.g. --port 8723');
      if (!/^\d+$/.test(raw)) die(`--port must be a whole number, got ${raw}`);
      port = parseInt(raw, 10);
      if (port > 65535) die(`--port must be between 0 and 65535, got ${port}`);
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

  serve(targetPath, port, !noBrowser);
}

// Importable as a module so the pure functions can be unit-tested directly.
// Requiring this file must never start a server.
if (require.main === module) main();
else module.exports = { injectOverlay, overlayMarkup, applyBatch };
