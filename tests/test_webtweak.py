"""Unit tests for webtweak's pure functions: injectOverlay and applyBatch.

These drive **webtweak.js** - the implementation the npm package ships and users
actually run - via tests/_wtjs.py. They previously tested a parallel Python
reference that was not shipped, which meant a breakage in the real code (for
instance a resave clobbering a *reconciled* batch) left the suite fully green.

Tests exercise the public function signatures only - never HTTP or private
handler internals (see docs/issues/0001, 0006).
"""

import unittest

import _wtjs as wt


class InjectOverlayTests(unittest.TestCase):
    def test_inserts_before_final_body_close(self):
        html = "<html><body><h1>Hi</h1></body></html>"
        out = wt.inject_overlay(html, "index.html")
        self.assertIn("webtweak overlay", out)
        # markup sits before </body>, and the body close is preserved
        self.assertLess(out.index("webtweak overlay"), out.index("</body>"))
        self.assertTrue(out.rstrip().endswith("</body></html>"))

    def test_uses_the_last_body_close(self):
        html = "<body>a</body><!-- </body> in a comment --><body>b</body>"
        out = wt.inject_overlay(html, "p.html")
        self.assertEqual(out.count("webtweak overlay"), 1)
        # Exactly one </body> may follow the injection point. Comparing indices
        # instead would also pass if the markup went in before the *first*
        # </body>, since a later one would still sit after it.
        tail = out[out.index("webtweak overlay"):]
        self.assertEqual(tail.count("</body>"), 1)

    def test_appends_when_no_body_close(self):
        html = "<div>no body tag here</div>"
        out = wt.inject_overlay(html, "x.html")
        self.assertTrue(out.startswith(html))
        self.assertIn("webtweak overlay", out)

    def test_config_carries_target_name(self):
        out = wt.inject_overlay("<body></body>", "about.html")
        self.assertIn('"target": "about.html"', out)

    def test_page_content_otherwise_unchanged(self):
        html = "<body><main><p>keep me</p></main></body>"
        out = wt.inject_overlay(html, "i.html")
        self.assertIn("<main><p>keep me</p></main>", out)


def _payload(session="s1", viewport=1440, patches=None):
    return {"sessionId": session, "viewport": viewport, "patches": patches or []}


class ApplyBatchTests(unittest.TestCase):
    def setUp(self):
        self.doc = {"target": "p.html", "batches": []}

    def test_first_save_creates_pending_batch(self):
        out = wt.apply_batch(self.doc, _payload(patches=[{"a": 1}]), "T0")
        self.assertEqual(len(out["batches"]), 1)
        b = out["batches"][0]
        self.assertEqual(b["status"], "pending")
        self.assertEqual(b["sessionId"], "s1")
        self.assertEqual(b["savedAt"], "T0")
        self.assertEqual(b["viewport"], 1440)
        self.assertEqual(b["patches"], [{"a": 1}])

    def test_same_session_resave_overwrites(self):
        out = wt.apply_batch(self.doc, _payload(patches=[{"a": 1}]), "T0")
        out = wt.apply_batch(out, _payload(patches=[{"a": 1}, {"b": 2}]), "T1")
        self.assertEqual(len(out["batches"]), 1)
        self.assertEqual(out["batches"][0]["savedAt"], "T1")
        self.assertEqual(out["batches"][0]["patches"], [{"a": 1}, {"b": 2}])

    def test_new_session_appends(self):
        out = wt.apply_batch(self.doc, _payload(session="s1", patches=[{"a": 1}]), "T0")
        out = wt.apply_batch(out, _payload(session="s2", patches=[{"b": 2}]), "T1")
        self.assertEqual([b["sessionId"] for b in out["batches"]], ["s1", "s2"])

    def test_reconciled_batch_never_modified(self):
        doc = {"target": "p.html", "batches": [
            {"sessionId": "s1", "status": "reconciled", "savedAt": "T0",
             "viewport": 1440, "patches": [{"old": True}]},
        ]}
        out = wt.apply_batch(doc, _payload(session="s1", patches=[{"new": True}]), "T1")
        # a same-session save must NOT overwrite a reconciled batch - it appends
        self.assertEqual(len(out["batches"]), 2)
        self.assertEqual(out["batches"][0]["status"], "reconciled")
        self.assertEqual(out["batches"][0]["patches"], [{"old": True}])
        self.assertEqual(out["batches"][1]["status"], "pending")

    def test_missing_session_is_deterministic(self):
        out = wt.apply_batch(self.doc, {"viewport": 800, "patches": [{"a": 1}]}, "T0")
        out = wt.apply_batch(out, {"viewport": 800, "patches": [{"a": 2}]}, "T1")
        # two session-less saves collapse into one pending batch, not two
        self.assertEqual(len(out["batches"]), 1)
        self.assertEqual(out["batches"][0]["patches"], [{"a": 2}])
        # ...and the documented default sessionId is pinned by name
        self.assertEqual(out["batches"][0]["sessionId"], "unknown")

    def test_empty_or_new_doc_initialised(self):
        out = wt.apply_batch({}, _payload(patches=[{"a": 1}]), "T0")
        self.assertIn("batches", out)
        self.assertEqual(len(out["batches"]), 1)

    def test_other_top_level_keys_preserved(self):
        doc = {"target": "p.html", "notes": "keep me", "batches": []}
        out = wt.apply_batch(doc, _payload(patches=[{"a": 1}]), "T0")
        self.assertEqual(out["notes"], "keep me")
        self.assertEqual(out["target"], "p.html")  # not clobbered by payload

    def test_non_list_batches_reinitialised(self):
        out = wt.apply_batch({"target": "p.html", "batches": 42},
                             _payload(patches=[{"a": 1}]), "T0")
        self.assertEqual(len(out["batches"]), 1)

    def test_empty_save_is_noop_when_nothing_pending(self):
        # An empty/null-patches save with no matching batch creates nothing - it is
        # the "clear my edits" signal, not a request to store an empty batch.
        out = wt.apply_batch(self.doc, {"sessionId": "s1", "viewport": 1440, "patches": None}, "T0")
        self.assertEqual(out["batches"], [])
        out = wt.apply_batch(self.doc, _payload(patches=[]), "T0")
        self.assertEqual(out["batches"], [])

    def test_empty_save_clears_this_sessions_pending_batch(self):
        # Edit + save, then revert everything + save: the stale pending batch must
        # be dropped, not left on disk for reconcile to pick up.
        out = wt.apply_batch(self.doc, _payload(session="s1", patches=[{"a": 1}]), "T0")
        self.assertEqual(len(out["batches"]), 1)
        out = wt.apply_batch(out, _payload(session="s1", patches=[]), "T1")
        self.assertEqual(out["batches"], [])

    def test_empty_save_only_clears_matching_session(self):
        doc = {"target": "p.html", "batches": [
            {"sessionId": "s1", "status": "pending", "savedAt": "T0", "viewport": 1440, "patches": [{"a": 1}]},
            {"sessionId": "s2", "status": "pending", "savedAt": "T0", "viewport": 1440, "patches": [{"b": 2}]},
        ]}
        out = wt.apply_batch(doc, _payload(session="s1", patches=[]), "T1")
        self.assertEqual([b["sessionId"] for b in out["batches"]], ["s2"])

    def test_empty_save_preserves_reconciled_batch(self):
        # The audit trail is immutable: clearing a session's pending edits must never
        # touch a reconciled batch, even one with the same sessionId.
        doc = {"target": "p.html", "batches": [
            {"sessionId": "s1", "status": "reconciled", "savedAt": "T0", "viewport": 1440, "patches": [{"old": True}]},
        ]}
        out = wt.apply_batch(doc, _payload(session="s1", patches=[]), "T1")
        self.assertEqual(len(out["batches"]), 1)
        self.assertEqual(out["batches"][0]["status"], "reconciled")
        self.assertEqual(out["batches"][0]["patches"], [{"old": True}])

    def test_create_patch_stored_verbatim(self):
        # A shape-creation patch (op:"create") must survive apply_batch untouched: the
        # server is patch-agnostic, so element creation needed no apply_batch change
        # (ADR-0002). Guards against a future regression that special-cases patches.
        create = {
            "op": "create", "shape": "triangle", "renderer": "svg",
            "geometry": {"viewBox": "0 0 100 100", "el": "polygon",
                         "points": "50,0 100,100 0,100", "attrs": None},
            "anchor": {"parent": {"tag": "body", "selector": "body"}, "position": "append"},
            "fingerprint": {"tag": "svg", "id": "wt-shape-abc123", "selector": "#wt-shape-abc123"},
            "changes": {"position": "absolute", "left": "400px", "top": "350px",
                        "width": "90px", "height": "80px", "fill": "#3366cc",
                        "stroke": "#cc2222", "stroke-width": "4px"},
        }
        out = wt.apply_batch(self.doc, _payload(patches=[create]), "T0")
        self.assertEqual(out["batches"][0]["patches"], [create])  # preserved exactly

    def test_mixed_order_preserved_only_matching_pending_replaced(self):
        doc = {"target": "p.html", "batches": [
            {"sessionId": "s1", "status": "reconciled", "savedAt": "T0", "viewport": 1440, "patches": []},
            {"sessionId": "s2", "status": "pending", "savedAt": "T1", "viewport": 1440, "patches": [{"x": 1}]},
        ]}
        out = wt.apply_batch(doc, _payload(session="s2", patches=[{"x": 2}]), "T2")
        self.assertEqual(len(out["batches"]), 2)
        self.assertEqual(out["batches"][0]["status"], "reconciled")
        self.assertEqual(out["batches"][1]["sessionId"], "s2")
        self.assertEqual(out["batches"][1]["patches"], [{"x": 2}])
        self.assertEqual(out["batches"][1]["savedAt"], "T2")


if __name__ == "__main__":
    unittest.main()


class InjectOverlayEncodingTests(unittest.TestCase):
    """Case-insensitive matching must not assume case folding preserves length."""

    def test_a_turkish_capital_i_does_not_shift_the_injection_point(self):
        # U+0130 (LATIN CAPITAL LETTER I WITH DOT ABOVE) is the ONLY code point in the
        # whole of Unicode whose lowercase is a different number of UTF-16 units. The
        # index used to be taken on html.toLowerCase() and then used to slice `html`,
        # so every one of these before the closing tag shifted the injection one unit
        # earlier - and with eight of them the markup landed INSIDE `</body>`, where the
        # parser eats all four overlay tags as attribute soup. The editor simply never
        # appeared, with no error anywhere.
        for n in (0, 1, 3, 8):
            with self.subTest(count=n):
                html = "<html><body>" + ("İ" * n) + "</body></html>"
                out = wt.inject_overlay(html, "p.html")
                self.assertIn("__WEBTWEAK__", out)
                # The markup sits before the closing tag, and the closing tag survives
                # whole - that is what "before the last </body>" has to mean.
                self.assertLess(out.index("__WEBTWEAK__"), out.index("</body>"))
                self.assertEqual(out.count("</body>"), 1)
                self.assertTrue(out.endswith("</body></html>"))

    def test_an_uppercase_closing_tag_is_still_matched(self):
        out = wt.inject_overlay("<html><BODY>x</BODY></html>", "p.html")
        self.assertIn("__WEBTWEAK__", out)
        self.assertLess(out.index("__WEBTWEAK__"), out.index("</BODY>"))

    def test_a_target_name_cannot_close_the_inline_script(self):
        # The name comes from the operator's own CLI argument, so this is correctness
        # rather than a reachable attack - but an overlay that silently fails to boot
        # is the worst kind to diagnose.
        out = wt.overlay_markup('a</script><img src=x onerror=BOOM>.html')
        self.assertNotIn("</script><img", out)
        self.assertIn("\\u003c", out)
