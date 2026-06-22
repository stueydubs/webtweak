"""Integration tests: the full capture-and-save loop over HTTP, stdlib only.

Boots the real `webtweak` CLI against an isolated copy of the fixture on an
ephemeral port (--port 0, port read back from stdout), then drives the loop the
way the Overlay does. No browser needed; the browser-driven view is in
test_e2e_browser.
"""

import http.client
import json
import shutil
import unittest

from _server import make_page, start, stop


class LoopTests(unittest.TestCase):
    def setUp(self):
        self.tmp, self.page = make_page()
        self.proc, self.port = start(self.page)

    def tearDown(self):
        stop(self.proc)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _get(self, path):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=2)
        conn.request("GET", path)
        r = conn.getresponse()
        body = r.read()
        ctype = r.getheader("Content-Type")
        conn.close()
        return r.status, body, ctype

    def _post(self, path, raw):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=2)
        conn.request("POST", path, raw, {"Content-Type": "application/json"})
        r = conn.getresponse()
        body = r.read().decode("utf-8")
        conn.close()
        return r.status, body

    # --- serving -----------------------------------------------------------
    def test_page_is_served_with_overlay_injected(self):
        status, body, _ = self._get("/sample.html")
        body = body.decode("utf-8")
        self.assertEqual(status, 200)
        self.assertIn("webtweak overlay", body)
        self.assertIn('"target": "sample.html"', body)
        self.assertIn("A page worth tweaking by eye", body)  # original content intact

    def test_reserved_overlay_assets_serve(self):
        for name, kind in [("overlay.js", "javascript"), ("overlay.css", "css"),
                           ("interact.min.js", "javascript")]:
            status, body, ctype = self._get("/__webtweak__/" + name)
            self.assertEqual(status, 200, name)
            self.assertIn(kind, ctype)
            self.assertTrue(len(body) > 0, name)

    def test_unknown_reserved_asset_404s(self):
        status, _, _ = self._get("/__webtweak__/bogus.js")
        self.assertEqual(status, 404)

    def test_overlay_asset_traversal_blocked(self):
        status, _, _ = self._get("/__webtweak__/../webtweak")
        self.assertIn(status, (400, 404))  # never serves the script itself

    # --- save loop ---------------------------------------------------------
    def _save_payload(self):
        return json.dumps({
            "sessionId": "test-session",
            "viewport": 1440,
            "patches": [{
                "fingerprint": {"tag": "h1", "id": "headline", "classes": ["title"],
                                "text": "A page worth tweaking by eye", "selector": "#headline",
                                "openTag": '<h1 class="title" id="headline">'},
                "changes": {"font-size": "52px"},
            }],
        })

    def test_save_writes_pending_batch_with_patch(self):
        status, body = self._post("/__webtweak__/save", self._save_payload())
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["ok"])

        edits = json.loads((self.tmp / "sample.webtweak.json").read_text())
        self.assertEqual(len(edits["batches"]), 1)
        batch = edits["batches"][0]
        self.assertEqual(batch["status"], "pending")
        self.assertEqual(batch["viewport"], 1440)
        self.assertEqual(batch["patches"][0]["changes"], {"font-size": "52px"})
        self.assertEqual(batch["patches"][0]["fingerprint"]["id"], "headline")

    def test_edits_readback_endpoint_returns_saved_doc(self):
        self._post("/__webtweak__/save", self._save_payload())
        status, body, ctype = self._get("/__webtweak__/edits")
        self.assertEqual(status, 200)
        self.assertIn("json", ctype)
        doc = json.loads(body)
        self.assertEqual(doc["batches"][0]["sessionId"], "test-session")

    def test_edits_readback_empty_before_any_save(self):
        status, body, _ = self._get("/__webtweak__/edits")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body).get("batches"), [])

    def test_source_file_is_not_mutated(self):
        before = self.page.read_text()
        self._post("/__webtweak__/save", self._save_payload())
        self.assertEqual(self.page.read_text(), before)

    # --- error paths -------------------------------------------------------
    def test_bad_json_returns_400(self):
        status, _ = self._post("/__webtweak__/save", "{not json")
        self.assertEqual(status, 400)

    def test_unknown_post_endpoint_returns_404(self):
        status, _ = self._post("/__webtweak__/wrong", "{}")
        self.assertEqual(status, 404)

    def _post_with_content_length(self, cl_value, body=b""):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=2)
        conn.putrequest("POST", "/__webtweak__/save", skip_host=False, skip_accept_encoding=True)
        conn.putheader("Content-Length", cl_value)
        conn.putheader("Content-Type", "application/json")
        conn.endheaders()
        if body:
            conn.send(body)
        r = conn.getresponse()
        r.read()
        conn.close()
        return r.status

    def test_oversized_content_length_returns_413(self):
        # declare a body far over the 8MB cap (without sending it)
        self.assertEqual(self._post_with_content_length(str(8 * 1024 * 1024 + 1)), 413)

    def test_non_numeric_content_length_returns_400(self):
        self.assertEqual(self._post_with_content_length("abc"), 400)

    # --- recovery paths ----------------------------------------------------
    def test_corrupt_edits_file_is_backed_up_and_recovered(self):
        edits = self.tmp / "sample.webtweak.json"
        edits.write_text("{ this is not valid json")
        status, body = self._post("/__webtweak__/save", self._save_payload())
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["ok"])
        baks = list(self.tmp.glob("sample.webtweak.json*.bak"))
        self.assertEqual(len(baks), 1)
        self.assertIn("not valid json", baks[0].read_text())  # original preserved
        doc = json.loads(edits.read_text())                   # fresh, clean doc
        self.assertEqual(len(doc["batches"]), 1)
        self.assertEqual(doc["batches"][0]["status"], "pending")

    def test_serve_edits_falls_back_when_file_unreadable(self):
        import os
        import stat
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            self.skipTest("root can read mode-000 files")
        edits = self.tmp / "sample.webtweak.json"
        edits.write_text('{"batches": [{"sessionId": "x", "status": "pending", "patches": []}]}')
        os.chmod(edits, 0)
        try:
            status, body, _ = self._get("/__webtweak__/edits")
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body).get("batches"), [])  # graceful empty fallback
        finally:
            os.chmod(edits, stat.S_IRUSR | stat.S_IWUSR)

    def test_serve_edits_falls_back_on_corrupt_json(self):
        # readable but invalid JSON must not be handed to the Overlay's restore parse
        (self.tmp / "sample.webtweak.json").write_text("{ not valid json")
        status, body, _ = self._get("/__webtweak__/edits")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body).get("batches"), [])

    def test_directory_listing_is_disabled(self):
        # the served root holds the edits/.bak files - no listing
        status, _, _ = self._get("/")
        self.assertEqual(status, 404)

    def test_empty_save_clears_persisted_batch_over_http(self):
        # a real save creates a pending batch; an empty save for the same session
        # must drop it on disk (not leave a stale or empty batch)
        self._post("/__webtweak__/save", self._save_payload())
        doc = json.loads((self.tmp / "sample.webtweak.json").read_text())
        self.assertEqual(len(doc["batches"]), 1)
        empty = json.dumps({"sessionId": "test-session", "viewport": 1440, "patches": []})
        status, body = self._post("/__webtweak__/save", empty)
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["ok"])
        doc = json.loads((self.tmp / "sample.webtweak.json").read_text())
        self.assertEqual(doc["batches"], [])  # batch cleared, not left empty

    def test_non_object_body_returns_400(self):
        # a valid-JSON body that isn't an object must be a clean 400, not a 500 crash
        for body in ("[]", "5", '"hi"', "null"):
            status, _ = self._post("/__webtweak__/save", body)
            self.assertEqual(status, 400, body)

    def test_unreadable_edits_file_on_save_returns_500_not_reset(self):
        # a transient READ failure must NOT be treated as corruption - the good file is
        # left untouched (no backup, no reset) and the save reports failure
        import os
        import stat
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            self.skipTest("root can read mode-000 files")
        self._post("/__webtweak__/save", self._save_payload())  # create a real batch
        edits = self.tmp / "sample.webtweak.json"
        before = edits.read_text()
        os.chmod(edits, 0)
        try:
            status, body = self._post("/__webtweak__/save", self._save_payload())
            self.assertEqual(status, 500)
            self.assertFalse(json.loads(body)["ok"])
        finally:
            os.chmod(edits, stat.S_IRUSR | stat.S_IWUSR)
        self.assertEqual(edits.read_text(), before)             # untouched
        self.assertEqual(list(self.tmp.glob("*.bak")), [])      # NOT backed up

    def test_short_body_returns_400(self):
        # declare more bytes than we send, then close the write side: the server's
        # read returns short and must answer 400, not hang or 500
        import socket
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.putrequest("POST", "/__webtweak__/save", skip_host=False, skip_accept_encoding=True)
        conn.putheader("Content-Length", "1000")
        conn.putheader("Content-Type", "application/json")
        conn.endheaders()
        conn.send(b'{"patches": []}')           # 15 bytes of a declared 1000
        conn.sock.shutdown(socket.SHUT_WR)        # signal EOF so the read returns short
        r = conn.getresponse()
        r.read()
        conn.close()
        self.assertEqual(r.status, 400)


if __name__ == "__main__":
    unittest.main()
