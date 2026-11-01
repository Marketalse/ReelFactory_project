"""Settings: the key is saved privately and never returned; other websites can't post to the dashboard."""
import io, json, os, sys, tempfile, unittest, urllib.error
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "dashboard")); sys.path.insert(0, os.path.join(ROOT, "scripts"))
import settings_api
from lib import config as cfg


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.keyf = os.path.join(self.tmp.name, "rf", "nous_api_key")
        self.saved = dict(cfg.PROJECT["route"]); cfg.PROJECT["route"]["key_file"] = self.keyf; os.environ.pop("RF_API_KEY", None)
        self.real_test = settings_api.test_key; settings_api.test_key = lambda: (True, "It works.")

    def tearDown(self):
        settings_api.test_key = self.real_test
        cfg.PROJECT["route"].clear(); cfg.PROJECT["route"].update(self.saved); self.tmp.cleanup()

    def test_key_is_saved_private_and_not_echoed(self):
        ok, msg = settings_api.save_key("  sk-test-" + "a" * 30 + "\n")
        self.assertTrue(ok); self.assertNotIn("aaaa", msg)
        self.assertEqual(open(self.keyf).read(), "sk-test-" + "a" * 30)
        self.assertEqual(os.stat(self.keyf).st_mode & 0o777, 0o600)
        self.assertNotIn("aaaa", json.dumps(settings_api.health()))

    def test_bad_paste_is_refused(self):
        self.assertFalse(settings_api.save_key("mkdir -p ~/.reelfactory && read")[0])
        self.assertFalse(settings_api.save_key("abc")[0])
        self.assertFalse(os.path.exists(self.keyf))

    def test_refused_key_is_explained(self):
        open(os.path.dirname(self.keyf) and (os.makedirs(os.path.dirname(self.keyf)) or self.keyf), "w").write("x" * 30)
        def refuse(req, timeout):
            raise urllib.error.HTTPError(req.full_url, 401, "no", {}, io.BytesIO(b""))
        ok, msg = self.real_test(opener=refuse)
        self.assertFalse(ok); self.assertIn("refused", msg)


if __name__ == "__main__":
    unittest.main()
