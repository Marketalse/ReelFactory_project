"""The API key comes from env, then Reel Factory's own key file, then Hermes. Never from the repo."""
import json, os, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from lib import config as cfg  # noqa: E402


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); d = self.tmp.name
        self.keyf, self.hermes = os.path.join(d, "key"), os.path.join(d, "auth.json")
        json.dump({"providers": {"nous": {"agent_key": "hermes-key", "inference_base_url": "https://h.example/v1"}}}, open(self.hermes, "w"))
        self.saved = dict(cfg.PROJECT["route"]); os.environ.pop("RF_API_KEY", None)
        cfg.PROJECT["route"].update(key_file=self.keyf, auth_file=self.hermes, base_url="https://n.example/v1")

    def tearDown(self):
        cfg.PROJECT["route"].clear(); cfg.PROJECT["route"].update(self.saved)
        os.environ.pop("RF_API_KEY", None); self.tmp.cleanup()

    def test_order(self):
        self.assertEqual(cfg.auth(), ("https://h.example/v1", "hermes-key"))          # no own key yet: Hermes
        open(self.keyf, "w").write("  own-key\n")
        self.assertEqual(cfg.auth(), ("https://n.example/v1", "own-key"))             # own key file wins
        os.environ["RF_API_KEY"] = "env-key"
        self.assertEqual(cfg.auth(), ("https://n.example/v1", "env-key"))             # env wins over both

    def test_repo_default_key_file_is_outside_the_repo(self):
        self.assertFalse(os.path.abspath(os.path.expanduser(self.saved["key_file"])).startswith(ROOT))


if __name__ == "__main__":
    unittest.main()
