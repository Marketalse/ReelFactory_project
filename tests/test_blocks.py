"""Offline checks for the block registry and the HyperFrames builder (no network, no spend)."""
import os, re, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from lib import hfbuild  # noqa: E402

REG = hfbuild.REGISTRY


class RegistryTests(unittest.TestCase):
    def test_every_scene_block_has_a_file_with_the_required_pattern(self):
        for name, spec in REG["blocks"].items():
            if spec["kind"] != "scene":
                continue
            src = open(os.path.join(hfbuild.BLOCKS_DIR, spec["file"]), encoding="utf-8").read()
            self.assertIn("<template>", src, name)
            self.assertIn('id="root" data-composition-id="__ID__"', src, name)
            self.assertIn('window.__timelines["__ID__"] = tl', src, name)
            self.assertNotRegex(src, r"#[0-9A-Fa-f]{6}\b(?![^<]*data-composition-variables)", f"{name}: hard-coded colour; use var(--...)")
            for bad in ("Math.random", "Date.now", "setTimeout", "repeat: -1", "fetch("):
                self.assertNotIn(bad, src, f"{name} uses {bad}")

    def test_declared_variables_match_registry_inputs(self):
        for name, spec in REG["blocks"].items():
            if spec["kind"] != "scene" or name == "captions":
                continue
            src = open(os.path.join(hfbuild.BLOCKS_DIR, spec["file"]), encoding="utf-8").read()
            declared = set(re.findall(r'"id":"([a-z_0-9]+)"', src.split("<template>")[0]))
            self.assertEqual(declared, set(spec["inputs"]), name)


class BuilderTests(unittest.TestCase):
    def test_bad_values_are_rejected_with_the_field_name(self):
        with self.assertRaisesRegex(hfbuild.BuildError, "'word' is required"):
            hfbuild.check_values("flash", {}, "b7")
        with self.assertRaisesRegex(hfbuild.BuildError, "max 12"):
            hfbuild.check_values("flash", {"word": "x" * 13}, "b7")
        with self.assertRaisesRegex(hfbuild.BuildError, "unknown field"):
            hfbuild.check_values("flash", {"word": "2x", "colour": "red"}, "b7")
        with self.assertRaisesRegex(hfbuild.BuildError, "unknown block"):
            hfbuild.check_values("glitch", {}, "b7")

    def test_stamp_uses_one_id_for_host_root_and_timeline(self):
        txt = hfbuild.stamp("flash", "flash2", 1.0)
        self.assertNotIn("__ID__", txt); self.assertNotIn("__DUR__", txt)
        self.assertIn('data-composition-id="flash2"', txt)
        self.assertIn('window.__timelines["flash2"]', txt)

    def test_caption_groups(self):
        words = [{"text": t, "start": i * 0.4, "end": i * 0.4 + 0.3} for i, t in enumerate("واحد اثنين ثلاثة اربعة خمسة".split())]
        words[3]["start"] += 1.0; words[3]["end"] += 1.0; words[4]["start"] += 1.0; words[4]["end"] += 1.0
        html = hfbuild.caption_groups(words, [1], "caps", max_words=3)
        groups = re.findall(r'class="clip caps-g" data-start="([0-9.]+)" data-duration="([0-9.]+)"', html)
        self.assertEqual(len(groups), 2)                       # pause splits the groups
        self.assertEqual(html.count("caps-kw"), 1)             # one keyword
        s1, d1 = map(float, groups[0]); s2 = float(groups[1][0])
        self.assertLessEqual(s1 + d1, s2 + 1e-6)               # groups never overlap
        self.assertGreaterEqual(s1, 0.1)                        # never exactly at 0 s

    def test_build_project_writes_a_complete_project(self):
        with tempfile.TemporaryDirectory() as d:
            vid = os.path.join(d, "v.mp4"); open(vid, "wb").write(b"0")
            hfbuild.build_project(os.path.join(d, "p"), duration=4, video_src=vid,
                                  face_cuts=[{"id": "seg0", "t_in": 0, "t_out": 4, "src_in": 10}],
                                  scenes=[{"id": "flash1", "block": "flash", "t_in": 1, "t_out": 2, "values": {"word": "300"}}])
            idx = open(os.path.join(d, "p", "index.html"), encoding="utf-8").read()
            self.assertIn('id="flash1" class="clip" data-composition-id="flash1"', idx)
            self.assertIn('data-media-start="10"', idx)
            self.assertIn("--lime: #B6FF00", idx)
            for f in ("compositions/flash1.html", "vendor/gsap.min.js", "assets/fonts/ReadexPro.ttf", "assets/proxy.mp4"):
                self.assertTrue(os.path.exists(os.path.join(d, "p", f)), f)


if __name__ == "__main__":
    unittest.main()
