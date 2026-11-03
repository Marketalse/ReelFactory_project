import json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from lib import hfbuild

GOOD = {"v": "5.5", "fr": 30, "ip": 0, "op": 30, "w": 100, "h": 100, "layers": [{"ty": 4, "ks": {}}]}


class MotionCard(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.old = hfbuild.MOTION_DIR; hfbuild.MOTION_DIR = self.d
        json.dump(GOOD, open(os.path.join(self.d, "spin.json"), "w"))
        json.dump(dict(GOOD, layers=[{"ty": 4, "ks": {"p": {"x": "time*9"}}}]), open(os.path.join(self.d, "evil.json"), "w"))

    def tearDown(self):
        hfbuild.MOTION_DIR = self.old

    def test_a_checked_file_is_put_inside_the_scene(self):
        src = hfbuild.stamp("motion_card", "m1", 2.5, "", {"motion": "spin.json", "label": "x"})
        self.assertIn('"layers"', src); self.assertNotIn("__LOTTIE_JSON__", src)

    def test_unsafe_names_missing_and_failed_files_stop_the_build(self):
        for bad in ("../x.json", "/etc/passwd", "sub/spin.json", "", "nothere.json", "evil.json", "spin.txt"):
            with self.assertRaises(hfbuild.BuildError, msg=bad):
                hfbuild.stamp("motion_card", "m1", 2.5, "", {"motion": bad})

    def test_the_closing_script_tag_cannot_be_smuggled_in_through_the_json(self):
        json.dump(dict(GOOD, nm="</script><script>alert(1)</script>"), open(os.path.join(self.d, "tricky.json"), "w"))
        src = hfbuild.stamp("motion_card", "m1", 2.5, "", {"motion": "tricky.json"})
        self.assertNotIn("</script><script>alert", src)


if __name__ == "__main__":
    unittest.main()
