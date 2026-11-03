"""Regression tests from the crash test (2026-11-03): damaged files and wrong-typed data must never crash the dashboard."""
import io, json, os, sys, threading, unittest, urllib.request, http.client
sys.path.insert(0, os.path.dirname(__file__))
from test_dashboard import ApiTest, ROOT
sys.path.insert(0, os.path.join(ROOT, "dashboard"))


class Robust(ApiTest):
    def test_damaged_timing_ledger_and_cost_files_do_not_break_pages(self):
        self.job("2026-11-03-aaa", "preview_ready", ["x"], timing=5)                 # timing.json holds a number
        d = os.path.join(self.root, "jobs", "2026-11-03-aaa")
        for f, txt in (("cost.json", "[]"), ("timeline.json", "nope")):
            open(os.path.join(d, f), "w").write(txt)
        self.assertIsInstance(self.api.expected_secs(), dict)
        self.assertIsInstance(self.api.spend("2026-11"), dict)
        open(os.path.join(d, "cost.json"), "w").write(json.dumps({"calls": [5, {"cost": "x"}, {"cost": 0.1, "stage": "plan", "model": "a/b"}]}))
        self.assertAlmostEqual(self.api.spend("2026-11")["total"], 0.1, 3) if "total" in self.api.spend("2026-11") else None

    def test_wrong_typed_results_data_is_refused_plainly(self):
        self.job("2026-11-03-bbb", "preview_ready", ["x"])
        self.assertFalse(self.api.save_performance("2026-11-03-bbb", "text")[0])
        self.assertFalse(self.api.save_performance("2026-11-03-bbb", ["a"])[0])
        self.assertFalse(self.api.save_posted("2026-11-03-bbb", ["x"])[0])

    def test_save_key_accepts_only_text(self):
        import settings_api
        for bad in (12345, ["a"], None, {"k": 1}, ""):
            self.assertFalse(settings_api.save_key(bad)[0])


class Server(unittest.TestCase):
    """A real dashboard on a spare port: bad bodies and hostile paths get plain answers, never a dropped connection."""
    @classmethod
    def setUpClass(cls):
        import importlib, tempfile
        cls.tmp = tempfile.mkdtemp()
        for d in ("jobs", "inbox"): os.makedirs(os.path.join(cls.tmp, d))
        os.environ["RF_ROOT"] = cls.tmp; os.environ["RF_DASH_PORT"] = "8787"
        import reels_api, settings_api, serve
        importlib.reload(reels_api); cls.serve = importlib.reload(serve)
        cls.srv = cls.serve.Server(("127.0.0.1", 8787), cls.serve.H)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown(); cls.srv.server_close(); os.environ.pop("RF_ROOT", None); os.environ.pop("RF_DASH_PORT", None)

    def call(self, method, path, body=None, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", 8787, timeout=10)
        c.request(method, path, body=body, headers=headers or {}); r = c.getresponse(); b = r.read().decode(); c.close(); return r.status, b

    def test_posts_with_wrong_types_never_drop_the_connection(self):
        for act, body in (("posted", {"job": 5, "platform": []}), ("performance", {"job": "x", "data": "str"}), ("start", {"slug": 7}), ("fix", {"job": [], "text": {}}), ("notes", [1, 2])):
            s, b = self.call("POST", f"/api/reels/{act}", json.dumps(body))
            self.assertLess(s, 500, (act, s, b))
        s, b = self.call("POST", "/api/settings/key", json.dumps({"key": 12345})); self.assertLess(s, 500)

    def test_only_the_pages_are_served_and_junk_gets_404(self):
        self.assertEqual(self.call("GET", "/make.html")[0], 200)
        for p in ("/serve.py", "/reels_api.py", "/expenses.json", "/tasks.json", "/.backups/", "/../config/project.json", "/%2e%2e/%2e%2e/etc/passwd"):
            s, b = self.call("GET", p); self.assertIn(s, (400, 403, 404), (p, s)); self.assertNotIn("import ", b)


if __name__ == "__main__":
    unittest.main()
