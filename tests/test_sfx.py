"""Sound effects are made by our own script: they exist, have the right length, and the catalogue matches. Offline, free."""
import json, os, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import make_sfx  # noqa: E402


class SfxTests(unittest.TestCase):
    def test_made_with_right_lengths_and_catalogue(self):
        d = tempfile.mkdtemp()
        cat = make_sfx.make(d)
        names = {c["name"] for c in cat}
        self.assertTrue({"whoosh", "pop", "ding"} <= names)         # the three the brand file promises
        for c in cat:
            out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", os.path.join(d, c["file"])],
                                 capture_output=True, text=True).stdout
            self.assertAlmostEqual(float(out), c["seconds"], delta=0.05)
        self.assertIn("Own work", json.load(open(os.path.join(d, "catalog.json"), encoding="utf-8"))["licence"])

    def test_every_block_sfx_exists(self):
        reg = json.load(open(os.path.join(ROOT, "templates", "blocks", "registry.json"), encoding="utf-8"))["blocks"]
        for name, b in reg.items():
            for use in [v for v in (b.get("sfx") or {}).values() if isinstance(v, str)]:
                self.assertIn(use, make_sfx.SOUNDS, f"{name} wants an sfx we don't make: {use}")


if __name__ == "__main__":
    unittest.main()
