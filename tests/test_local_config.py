import json, os, sys, tempfile, unittest
from unittest import mock
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
from lib import config  # noqa: E402


class LocalConfig(unittest.TestCase):
    def test_local_settings_override_and_keep_the_rest(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(config, "CONFIG_DIR", d):
            self.assertEqual(config._local(), {})
            config.local_set(("matte", "engine"), "rvm"); config.local_set(("format_pack", "layout"), "stage"); config.local_set(("matte", "auto_install"), False)
            self.assertEqual(json.load(open(os.path.join(d, "local.json"))), {"matte": {"engine": "rvm", "auto_install": False}, "format_pack": {"layout": "stage"}})
            base = {"matte": {"engine": "hyperframes", "_note": "x"}, "format_pack": {"layout": "panel", "theme": "dark"}, "other": 1}
            m = config._merge(base, config._local())
            self.assertEqual((m["matte"]["engine"], m["matte"]["_note"], m["format_pack"]["layout"], m["format_pack"]["theme"], m["other"]), ("rvm", "x", "stage", "dark", 1))

    def test_broken_local_file_is_ignored_and_it_is_not_tracked_by_git(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(config, "CONFIG_DIR", d):
            open(os.path.join(d, "local.json"), "w").write("{oops"); self.assertEqual(config._local(), {})
        self.assertIn("config/local.json", open(os.path.join(os.path.dirname(__file__), "..", ".gitignore")).read())


if __name__ == "__main__":
    unittest.main()
