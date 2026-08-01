"""The server's trust-boundary guards, over real HTTP. Stdlib only.

These cover four things the suite could previously not see at all - each one was
deletable with 391 tests green:

* `originAllowed` (CSRF on /edits, /events and /save) and `hostAllowed` (DNS
  rebinding). Both protect the endpoint that writes the file reconcile later folds
  into real source, so a silent regression there is the expensive kind.
* Dotfile exposure. `--root` at a real site root is the documented normal usage and
  that root is usually a git repo, so `/.git/config` was one plain GET away.
* Payload shapes that used to be misread as a deliberate signal rather than rejected.

The named traversal guards have their own tests in test_loop / test_root_flag; those
assert the OUTCOME, which stays correct via the realpath check even with the named
guard removed. That is defence in depth working as intended, and is noted there.
"""

import http.client
import json
import pathlib
import shutil
import unittest

from _server import make_page, start, stop


def _req(port, method, path, body=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    conn.request(method, path, body=body, headers=headers or {})
    r = conn.getresponse()
    payload = r.read()
    conn.close()
    return r.status, payload


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp, self.page = make_page()
        self.proc, self.port = start(self.page)
        self.same_origin = f"http://127.0.0.1:{self.port}"

    def tearDown(self):
        stop(self.proc)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _save(self, headers):
        body = json.dumps({"sessionId": "s1", "patches": [{"fingerprint": {"tag": "h1"},
                                                           "changes": {"color": "red"}}]})
        return _req(self.port, "POST", "/__webtweak__/save", body, headers)

    # --- originAllowed: CSRF on the three API endpoints ----------------------

    def test_cross_origin_save_is_refused(self):
        status, _ = self._save({"Content-Type": "application/json",
                                "Origin": "https://evil.example"})
        self.assertEqual(status, 403)
        # and nothing was written
        self.assertFalse((self.tmp / "sample.webtweak.json").exists())

    def test_same_origin_save_is_accepted(self):
        # The other half of the guard: it must not refuse the Overlay itself.
        status, _ = self._save({"Content-Type": "application/json",
                                "Origin": self.same_origin})
        self.assertEqual(status, 200)

    def test_origin_less_save_is_accepted(self):
        # curl and other non-browser clients carry no ambient authority, so no Origin
        # is allowed by design (webtweak.js originAllowed).
        status, _ = self._save({"Content-Type": "application/json"})
        self.assertEqual(status, 200)

    def test_cross_origin_read_of_the_edits_file_is_refused(self):
        status, _ = _req(self.port, "GET", "/__webtweak__/edits",
                         headers={"Origin": "https://evil.example"})
        self.assertEqual(status, 403)

    def test_cross_origin_event_stream_is_refused(self):
        status, _ = _req(self.port, "GET", "/__webtweak__/events",
                         headers={"Origin": "https://evil.example"})
        self.assertEqual(status, 403)

    # --- hostAllowed: DNS rebinding -----------------------------------------

    def test_forged_host_header_is_refused(self):
        # An attacker-controlled name resolving to 127.0.0.1 would otherwise make the
        # served directory same-origin with a page they control.
        status, _ = _req(self.port, "GET", "/sample.html",
                         headers={"Host": "rebind.evil.example"})
        self.assertEqual(status, 403)

    def test_the_real_host_is_accepted(self):
        status, _ = _req(self.port, "GET", "/sample.html",
                         headers={"Host": f"127.0.0.1:{self.port}"})
        self.assertEqual(status, 200)

    # --- payload shapes ------------------------------------------------------

    def test_a_non_array_patches_value_is_rejected_not_read_as_a_revert(self):
        # It used to coerce to [], which the empty-save branch read as "the user
        # reverted everything" and used to DELETE their pending batch.
        self._save({"Content-Type": "application/json"})          # a real pending batch
        edits = self.tmp / "sample.webtweak.json"
        self.assertEqual(len(json.loads(edits.read_text())["batches"]), 1)

        status, _ = _req(self.port, "POST", "/__webtweak__/save",
                         json.dumps({"sessionId": "s1", "patches": {"0": {}}}),
                         {"Content-Type": "application/json"})
        self.assertEqual(status, 400)
        self.assertEqual(len(json.loads(edits.read_text())["batches"]), 1)  # still there

    def test_a_non_string_session_id_is_rejected_not_appended_forever(self):
        # A truthy non-string never compared equal to the stored sessionId, so every
        # save appended a new batch instead of superseding - and reconcile then applied
        # the same nudge once per save.
        for _ in range(3):
            status, _ = _req(self.port, "POST", "/__webtweak__/save",
                             json.dumps({"sessionId": {}, "patches": [{"a": 1}]}),
                             {"Content-Type": "application/json"})
            self.assertEqual(status, 400)
        self.assertFalse((self.tmp / "sample.webtweak.json").exists())


class DotfileTests(unittest.TestCase):
    """Dotfiles are never served, at either root setting."""

    def setUp(self):
        self.tmp, _ = make_page()
        (self.tmp / "site").mkdir()
        shutil.copy(self.tmp / "sample.html", self.tmp / "site" / "page.html")
        (self.tmp / ".git").mkdir()
        (self.tmp / ".git" / "config").write_text("[core]\n  placeholder = 1\n")
        (self.tmp / ".hidden").mkdir()
        (self.tmp / ".hidden" / "note.txt").write_text("placeholder\n")
        (self.tmp / "ordinary.txt").write_text("fine\n")
        (self.tmp / ".well-known").mkdir()
        (self.tmp / ".well-known" / "security.txt").write_text("contact: someone\n")
        self.proc, self.port = start(self.tmp / "site" / "page.html", root=self.tmp)

    def tearDown(self):
        stop(self.proc)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_a_dotdir_under_the_web_root_is_not_served(self):
        for path in ("/.git/config", "/.hidden/note.txt"):
            with self.subTest(path=path):
                status, body = _req(self.port, "GET", path)
                self.assertEqual(status, 404)
                self.assertNotIn(b"placeholder", body)

    def test_well_known_is_still_served(self):
        # The one standardised dot-path on the web (RFC 8615). A page under test can
        # legitimately reference something under it, and by convention it holds no
        # secrets - so blocking it was a regression the guard introduced, not a fix.
        status, body = _req(self.port, "GET", "/.well-known/security.txt")
        self.assertEqual(status, 200)
        self.assertIn(b"contact:", body)

    def test_an_ordinary_file_under_the_same_root_still_is(self):
        # The guard must be about the dot, not about --root narrowing what is served.
        status, body = _req(self.port, "GET", "/ordinary.txt")
        self.assertEqual(status, 200)
        self.assertIn(b"fine", body)


class EncodingTests(unittest.TestCase):
    """A non-UTF-8 page is served byte-for-byte, under its own declared charset.

    `readFileSync(p, 'utf8')` decoded with U+FFFD replacement and `send` re-encoded as
    UTF-8, so the original bytes were destroyed rather than merely mislabelled - and
    because the Overlay fingerprints elements on their text, every Patch on such an
    element carried the replacement character and could never match its own source.
    """

    def setUp(self):
        self.tmp = pathlib.Path(__import__("tempfile").mkdtemp())
        self.page = self.tmp / "latin.html"
        self.page.write_bytes(
            b'<html><head><meta charset="windows-1252"></head>'
            b'<body><h1 id="t">caf\xe9</h1></body></html>')
        self.proc, self.port = start(self.page)

    def tearDown(self):
        stop(self.proc)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_the_original_bytes_survive(self):
        status, body = _req(self.port, "GET", "/latin.html")
        self.assertEqual(status, 200)
        self.assertIn(b"caf\xe9", body)             # not EF BF BD
        self.assertNotIn(b"\xef\xbf\xbd", body)

    def test_the_declared_charset_is_not_overridden(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        conn.request("GET", "/latin.html")
        r = conn.getresponse()
        r.read()
        ctype = r.getheader("Content-Type") or ""
        conn.close()
        self.assertIn("windows-1252", ctype)

    def test_the_overlay_is_still_injected(self):
        _, body = _req(self.port, "GET", "/latin.html")
        self.assertIn(b"__WEBTWEAK__", body)


if __name__ == "__main__":
    unittest.main()
