"""Issue 26: the edits file's real path is contained, and the untested HTTP guards.

Stdlib only, over real HTTP. Every guard here was deletable with the suite green:

* the edits file read without a realpath check (a symlinked `<stem>.webtweak.json`
  handed any JSON file on disk to the page's own script),
* the realpath block in the static handler, the 415 on a non-JSON save and the 405
  on a non-GET static request,
* Range (206/416) parsing and HEAD handling in serveStatic.
"""

import http.client
import json
import os
import pathlib
import shutil
import tempfile
import unittest

from _server import make_page, start, stop

MARKER = "TOP-SECRET-MARKER-26"


def _req(port, method, path, body=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    conn.request(method, path, body=body, headers=headers or {})
    r = conn.getresponse()
    payload = r.read()
    result = (r.status, payload, dict((k.lower(), v) for k, v in r.getheaders()))
    conn.close()
    return result


class _Served(unittest.TestCase):
    def setUp(self):
        self.tmp, self.page = make_page()
        self.outside = pathlib.Path(tempfile.mkdtemp())
        self.proc, self.port = start(self.page)

    def tearDown(self):
        stop(self.proc)
        shutil.rmtree(self.tmp, ignore_errors=True)
        shutil.rmtree(self.outside, ignore_errors=True)

    def _outside_json(self):
        secret = self.outside / "outside.json"
        secret.write_text(json.dumps({"token": MARKER, "batches": [{"x": MARKER}]}))
        return secret


class EditsContainmentTests(_Served):
    def test_symlinked_edits_file_is_not_served(self):
        secret = self._outside_json()
        link = self.tmp / "sample.webtweak.json"
        link.symlink_to(secret)
        # Guard against a vacuous pass: the link must resolve to the secret.
        self.assertIn(MARKER, link.read_text())

        status, body, _ = _req(self.port, "GET", "/__webtweak__/edits")
        self.assertEqual(status, 200)
        self.assertNotIn(MARKER.encode(), body)
        self.assertEqual(json.loads(body), {"batches": []})

    def test_symlinked_edits_file_is_not_read_or_overwritten_by_save(self):
        secret = self._outside_json()
        before = secret.read_text()
        (self.tmp / "sample.webtweak.json").symlink_to(secret)
        body = json.dumps({"sessionId": "s1", "patches": [
            {"fingerprint": {"tag": "h1"}, "changes": {"color": "red"}}]})
        status, payload, _ = _req(self.port, "POST", "/__webtweak__/save", body,
                                  {"Content-Type": "application/json"})
        self.assertEqual(status, 500)
        self.assertIn(b"outside the served root", payload)
        self.assertEqual(secret.read_text(), before)

    def test_regular_edits_file_is_still_served(self):
        doc = {"batches": [{"sessionId": "s1", "patches": [], "note": MARKER}]}
        (self.tmp / "sample.webtweak.json").write_text(json.dumps(doc))
        status, body, _ = _req(self.port, "GET", "/__webtweak__/edits")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), doc)

    def test_symlinked_edits_file_inside_the_root_is_still_served(self):
        # Containment, not a blanket symlink ban: a link that stays inside is fine.
        doc = {"batches": [{"sessionId": "s1", "patches": [], "note": MARKER}]}
        (self.tmp / "real-edits.json").write_text(json.dumps(doc))
        (self.tmp / "sample.webtweak.json").symlink_to(self.tmp / "real-edits.json")
        status, body, _ = _req(self.port, "GET", "/__webtweak__/edits")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), doc)


class StaticGuardTests(_Served):
    def test_symlinked_file_escaping_the_root_is_forbidden(self):
        secret = self.outside / "secret.txt"
        secret.write_text(MARKER)
        (self.tmp / "leak.txt").symlink_to(secret)
        self.assertEqual((self.tmp / "leak.txt").read_text(), MARKER)  # link is live

        status, body, _ = _req(self.port, "GET", "/leak.txt")
        self.assertEqual(status, 403)
        self.assertNotIn(MARKER.encode(), body)

    def test_non_json_save_is_415_and_writes_nothing(self):
        body = json.dumps({"sessionId": "s1", "patches": [
            {"fingerprint": {"tag": "h1"}, "changes": {"color": "red"}}]})
        status, _, _ = _req(self.port, "POST", "/__webtweak__/save", body,
                            {"Content-Type": "text/plain"})
        self.assertEqual(status, 415)
        self.assertFalse((self.tmp / "sample.webtweak.json").exists())

    def test_non_get_static_request_is_405(self):
        for method in ("PUT", "POST", "DELETE"):
            with self.subTest(method=method):
                status, _, _ = _req(self.port, method, "/sample.html", body=b"x")
                self.assertEqual(status, 405)
        self.assertTrue((self.tmp / "sample.html").exists())


class RangeAndHeadTests(_Served):
    def setUp(self):
        super().setUp()
        self.data = bytes(range(100))
        (self.tmp / "blob.txt").write_bytes(self.data)

    def _range(self, value):
        return _req(self.port, "GET", "/blob.txt", headers={"Range": value})

    def test_plain_get_advertises_accept_ranges(self):
        status, body, h = _req(self.port, "GET", "/blob.txt")
        self.assertEqual(status, 200)
        self.assertEqual(h["accept-ranges"], "bytes")
        self.assertEqual(h["content-length"], "100")
        self.assertEqual(body, self.data)

    def test_closed_range(self):
        status, body, h = self._range("bytes=10-19")
        self.assertEqual(status, 206)
        self.assertEqual(h["content-range"], "bytes 10-19/100")
        self.assertEqual(h["content-length"], "10")
        self.assertEqual(body, self.data[10:20])

    def test_suffix_range(self):
        status, body, h = self._range("bytes=-5")
        self.assertEqual(status, 206)
        self.assertEqual(h["content-range"], "bytes 95-99/100")
        self.assertEqual(body, self.data[-5:])

    def test_open_ended_range(self):
        status, body, h = self._range("bytes=90-")
        self.assertEqual(status, 206)
        self.assertEqual(h["content-range"], "bytes 90-99/100")
        self.assertEqual(body, self.data[90:])

    def test_end_past_the_file_is_clamped(self):
        status, body, h = self._range("bytes=90-500")
        self.assertEqual(status, 206)
        self.assertEqual(h["content-range"], "bytes 90-99/100")
        self.assertEqual(body, self.data[90:])

    def test_start_past_the_end_is_416(self):
        status, _, h = self._range("bytes=200-")
        self.assertEqual(status, 416)
        self.assertEqual(h["content-range"], "bytes */100")

    def test_empty_range_is_416(self):
        status, _, _ = self._range("bytes=-")
        self.assertEqual(status, 416)

    def test_head_has_length_and_no_body(self):
        status, body, h = _req(self.port, "HEAD", "/blob.txt")
        self.assertEqual(status, 200)
        self.assertEqual(h["content-length"], "100")
        self.assertEqual(body, b"")


if __name__ == "__main__":
    unittest.main()
