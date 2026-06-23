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
};

// --- pure functions (no I/O) -----------------------------------------------

function overlayMarkup(targetName) {
  // Use ': ' separator to match Python's json.dumps format (tests rely on this).
  const cfg = '{"target": ' + JSON.stringify(targetName) + '}';
  return (
    '\n<!-- webtweak overlay (injected, not part of source) -->\n' +
    `<script>window.__WEBTWEAK__ = ${cfg};</script>\n` +
    `<link rel="stylesheet" href="${RESERVED}overlay.css">\n` +
    `<script src="${RESERVED}interact.min.js"></script>\n` +
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

function writeJsonAtomic(filePath, doc) {
  const tmp = filePath + '.tmp';
  try {
    fs.writeFileSync(tmp, JSON.stringify(doc, null, 2) + '\n', 'utf8');
    fs.renameSync(tmp, filePath);
  } catch (e) {
    try { fs.unlinkSync(tmp); } catch (_) {}
    throw e;
  }
}

// --- HTTP helpers ----------------------------------------------------------

function send(res, code, body, ctype) {
  const buf = Buffer.isBuffer(body) ? body : Buffer.from(body, 'utf8');
  res.writeHead(code, {
    'Content-Type':   ctype,
    'Content-Length': buf.length,
    'Cache-Control':  'no-store',
  });
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

function serveHtml(filePath, targetName, res) {
  let html;
  try { html = fs.readFileSync(filePath, 'utf8'); }
  catch (e) { return sendError(res, 500, 'Read error'); }
  send(res, 200, injectOverlay(html, targetName), 'text/html; charset=utf-8');
}

function serveStatic(filePath, res) {
  let buf;
  try { buf = fs.readFileSync(filePath); }
  catch (_) { return sendError(res, 404, 'Not found'); }
  const ctype = MIME[path.extname(filePath).toLowerCase()] || 'application/octet-stream';
  send(res, 200, buf, ctype);
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
      // Corrupt JSON - back up and start fresh
      const stamp  = Date.now();
      const backup = editsPath + '.' + stamp + '.bak';
      try { fs.renameSync(editsPath, backup); } catch (_) {}
      log(`edits file corrupt; backed up to ${path.basename(backup)}`);
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

function createHandler(targetPath, serveRoot) {
  const targetName = path.basename(targetPath);
  const stem       = path.basename(targetName, path.extname(targetName));

  return function (req, res) {
    const rawPath = (req.url || '/').split('?')[0];

    // --- webtweak API endpoints and overlay assets -------------------------
    if (rawPath.startsWith(RESERVED)) {
      const name = rawPath.slice(RESERVED.length);

      if (name === 'edits' && req.method === 'GET') {
        return serveEdits(path.join(serveRoot, stem + '.webtweak.json'), res);
      }

      if (name === 'save' && req.method === 'POST') {
        const lenStr = req.headers['content-length'];
        const length = parseInt(lenStr, 10);
        if (!lenStr || isNaN(length) || length < 0) return sendError(res, 400, 'Bad Content-Length');
        if (length > MAX_BODY) return sendError(res, 413, 'Payload too large');

        const chunks = [];
        let received = 0;
        req.on('data', chunk => {
          received += chunk.length;
          if (received <= MAX_BODY) chunks.push(chunk);
        });
        req.on('end', () => {
          if (received > MAX_BODY) return sendError(res, 413, 'Payload too large');
          if (received < length)   return sendError(res, 400, 'Incomplete request body');
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
    const local = path.resolve(serveRoot, decoded.replace(/^\/+/, ''));
    if (local !== serveRoot &&
        !local.startsWith(serveRoot + path.sep))
      return sendError(res, 403, 'Forbidden');

    // No directory listings
    let stat;
    try { stat = fs.statSync(local); }
    catch (_) { return sendError(res, 404, 'Not found'); }
    if (stat.isDirectory()) return sendError(res, 404, 'No listing');

    const ext = path.extname(local).toLowerCase();
    if (ext === '.html' || ext === '.htm') return serveHtml(local, targetName, res);
    serveStatic(local, res);
  };
}

// --- browser opener --------------------------------------------------------

function openBrowser(url) {
  const cmds = {
    darwin: ['open',     [url]],
    win32:  ['cmd',      ['/c', 'start', '', url]],
  };
  const [cmd, args] = cmds[os.platform()] || ['xdg-open', [url]];
  execFile(cmd, args, { detached: true }, () => {});
}

// --- server ----------------------------------------------------------------

function serve(targetPath, port, openBrowserFlag) {
  const serveRoot = path.dirname(targetPath);
  const handler   = createHandler(targetPath, serveRoot);
  const server    = http.createServer(handler);

  server.listen(port, '127.0.0.1', () => {
    const actual = server.address().port;
    const url    = `http://127.0.0.1:${actual}/${path.basename(targetPath)}`;
    process.stdout.write(`webtweak editing: ${targetPath}\n`);
    process.stdout.write(`  serving ${serveRoot}\n`);
    // Flush before remaining lines so the test harness sees the port immediately.
    process.stdout.write(`  listening on 127.0.0.1:${actual}\n`, () => {
      process.stdout.write(`  open    ${url}\n`);
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

function main() {
  const args = process.argv.slice(2);
  let htmlFile = null, port = 8723, noBrowser = false;

  for (let i = 0; i < args.length; i++) {
    if ((args[i] === '--port') && args[i + 1]) {
      port = parseInt(args[++i], 10);
      if (isNaN(port)) { process.stderr.write('webtweak: --port must be a number\n'); process.exit(1); }
    } else if (args[i] === '--no-browser') {
      noBrowser = true;
    } else if (args[i] === '--help' || args[i] === '-h') {
      process.stdout.write('Usage: webtweak <page.html> [--port N] [--no-browser]\n');
      process.exit(0);
    } else if (!args[i].startsWith('-')) {
      htmlFile = args[i];
    } else {
      process.stderr.write(`webtweak: unknown option ${args[i]}\n`);
      process.exit(1);
    }
  }

  if (!htmlFile) {
    process.stderr.write('webtweak: path to an .html file is required\n');
    process.stderr.write('Usage: webtweak <page.html> [--port N] [--no-browser]\n');
    process.exit(1);
  }

  const targetPath = path.resolve(htmlFile);
  if (!fs.existsSync(targetPath)) {
    process.stderr.write(`webtweak: not a file: ${targetPath}\n`);
    process.exit(1);
  }
  const ext = path.extname(targetPath).toLowerCase();
  if (ext !== '.html' && ext !== '.htm') {
    process.stderr.write(`webtweak: expected an .html file, got ${ext || 'no extension'}\n`);
    process.exit(1);
  }

  serve(targetPath, port, !noBrowser);
}

main();
