"""Stage 1 media check: each file judged on its own, duplicates found, bad files skipped without stopping the batch. Offline, free."""
import os, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from lib import media_check as mc  # noqa: E402


def make(path, src, w, h, fps, sound=True, secs=4):
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"{src}=size={w}x{h}:rate={fps}:duration={secs}"]
    if sound:
        cmd += ["-f", "lavfi", "-i", f"sine=f=440:d={secs}"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p"] + (["-c:a", "aac", "-shortest"] if sound else []) + [path]
    subprocess.run(cmd, check=True)


class MediaCheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        d = cls.d = tempfile.mkdtemp()
        make(os.path.join(d, "a.mp4"), "testsrc2", 1080, 1920, 30)
        make(os.path.join(d, "b_other.mp4"), "smptebars", 1080, 1920, 30)
        subprocess.run(["cp", os.path.join(d, "a.mp4"), os.path.join(d, "c_copy_of_a.mp4")], check=True)
        make(os.path.join(d, "d_low.mp4"), "smptebars", 640, 360, 15, sound=False)
        open(os.path.join(d, "e_broken.mp4"), "wb").write(open(os.path.join(d, "a.mp4"), "rb").read()[:4000])
        open(os.path.join(d, "f_empty.mp4"), "wb").close()
        cls.r = mc.check_batch(sorted(os.path.join(d, f) for f in os.listdir(d)))
        cls.by = {f["name"]: f for f in cls.r["files"]}

    def test_good_file_has_id_checksum_metadata_and_role(self):
        f = self.by["a.mp4"]
        self.assertEqual(f["verdict"], "ok"); self.assertTrue(f["use"])
        self.assertEqual((f["width"], f["height"], f["fps"]), (1080, 1920, 30.0))
        self.assertEqual(f["asset_id"], "a_" + f["sha256"][:10]); self.assertEqual(f["role"], "talking-head")

    def test_bad_files_fail_alone_and_say_why(self):
        for n in ("e_broken.mp4", "f_empty.mp4"):
            self.assertEqual(self.by[n]["verdict"], "fail"); self.assertFalse(self.by[n]["use"]); self.assertTrue(self.by[n]["issues"])
        self.assertEqual(self.r["summary"]["failed"], 2)
        self.assertTrue(self.by["a.mp4"]["use"] and self.by["b_other.mp4"]["use"])      # the others carry on

    def test_exact_duplicate_is_skipped_not_the_original(self):
        c = self.by["c_copy_of_a.mp4"]
        self.assertFalse(c["use"]); self.assertEqual(c["duplicate_of"], "a.mp4"); self.assertEqual(c["duplicate_kind"], "exact")
        self.assertEqual(self.r["summary"]["duplicates"], 1)

    def test_quality_warnings(self):
        w = " ".join(self.by["d_low.mp4"]["issues"])
        for word in ("low resolution", "horizontally", "frame rate", "no sound"):
            self.assertIn(word, w)
        self.assertEqual(self.by["d_low.mp4"]["role"], "b-roll"); self.assertTrue(self.by["d_low.mp4"]["use"])

    def test_footage_scan_black_scenes_and_speech(self):
        d = self.d
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=540x960:r=30:d=5", "-f", "lavfi", "-i", "sine=f=440:d=5",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", os.path.join(d, "g_black.mp4")], check=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=540x960:rate=30:duration=3",
                        "-f", "lavfi", "-i", "smptebars=size=540x960:rate=30:duration=3", "-filter_complex", "[0][1]concat=n=2:v=1:a=0",
                        "-pix_fmt", "yuv420p", os.path.join(d, "h_cut.mp4")], check=True)
        black = mc.analyze(os.path.join(d, "g_black.mp4"))
        self.assertTrue(black.get("unusable")); self.assertEqual(black["verdict"], "fail")
        cut = mc.analyze(os.path.join(d, "h_cut.mp4"))["scan"]
        self.assertTrue(any(2.5 <= t <= 3.5 for t in cut["scene_changes"]), cut)
        self.assertTrue(self.by["a.mp4"]["speech_segments"])
        self.assertIn(self.by["a.mp4"]["scan"]["motion"], ("steady", "some movement", "lots of movement"))

    def test_originals_untouched(self):
        before = mc.sha256(os.path.join(self.d, "a.mp4"))
        mc.analyze(os.path.join(self.d, "a.mp4"))
        self.assertEqual(mc.sha256(os.path.join(self.d, "a.mp4")), before)


if __name__ == "__main__":
    unittest.main()
