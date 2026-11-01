"""The API key comes from env, then Reel Factory's own key file. Never from the repo, never from Hermes."""
import json, os, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from lib import config as cfg  # noqa: E402


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); d = self.tmp.name
        self.keyf = os.path.join(d, "key")
        self.saved = dict(cfg.PROJECT["route"]); os.environ.pop("RF_API_KEY", None)
        cfg.PROJECT["route"].update(key_file=self.keyf, base_url="https://n.example/v1")

    def tearDown(self):
        cfg.PROJECT["route"].clear(); cfg.PROJECT["route"].update(self.saved)
        os.environ.pop("RF_API_KEY", None); self.tmp.cleanup()

    def test_order(self):
        with self.assertRaises(SystemExit) as cm:
            cfg.auth()                                                               # no key: clear message, no Hermes
        self.assertIn("Settings", str(cm.exception)); self.assertEqual(cfg.key_source(), "no key saved (Settings)")
        open(self.keyf, "w").write("  own-key\n")
        self.assertEqual(cfg.auth(), ("https://n.example/v1", "own-key"))
        os.environ["RF_API_KEY"] = "env-key"
        self.assertEqual(cfg.auth(), ("https://n.example/v1", "env-key"))             # env wins

    def test_no_hermes_in_config(self):
        self.assertNotIn("hermes", json.dumps(cfg.PROJECT["route"]).lower())

    def test_repo_default_key_file_is_outside_the_repo(self):
        self.assertFalse(os.path.abspath(os.path.expanduser(self.saved["key_file"])).startswith(ROOT))


if __name__ == "__main__":
    unittest.main()
