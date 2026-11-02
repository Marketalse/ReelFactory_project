"""Stage 2 end to end on a throw-away copy of the project: proxies, audio, virtual timeline, thumbnails."""
import json, os, shutil, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from lib import media_index as mi  # noqa: E402


def clip(path, src, secs, sound=True):
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"{src}=size=720x1280:rate=25:duration={secs}"]
    if sound:
        cmd += ["-f", "lavfi", "-i", f"sine=f=300:d={secs}"]
    subprocess.run(cmd + ["-c:v", "libx264", "-pix_fmt", "yuv420p"] + (["-c:a", "aac", "-shortest"] if sound else []) + [path], check=True)


@unittest.skipUnless(shutil.which("node") and shutil.which("ffmpeg"), "needs node and ffmpeg")
class Stage2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.t = tempfile.mkdtemp()
        for d in ("scripts", "config"):
            shutil.copytree(os.path.join(ROOT, d), os.path.join(cls.t, d), ignore=shutil.ignore_patterns("__pycache__"))
        os.makedirs(os.path.join(cls.t, "jobs"))
        src = os.path.join(cls.t, "in"); os.makedirs(src)
        clip(os.path.join(src, "01_talk.mp4"), "testsrc2", 4)
        clip(os.path.join(src, "02_broll.mp4"), "smptebars", 3, sound=False)
        open(os.path.join(src, "03_bad.mp4"), "wb").write(b"not a video")
        r = subprocess.run([sys.executable, os.path.join(cls.t, "scripts", "ingest_folder.py"), src, "--slug", "s2test"],
                           capture_output=True, text=True, cwd=cls.t)
        cls.out = r.stdout + r.stderr
        cls.ok = r.returncode == 0
        cls.job = os.path.join(cls.t, "jobs", next(iter(os.listdir(os.path.join(cls.t, "jobs"))), "x"))

    def test_runs_and_skips_the_bad_file(self):
        self.assertTrue(self.ok, self.out)
        man = json.load(open(os.path.join(self.job, "media_manifest.json")))
        self.assertEqual(man["summary"]["failed"], 1)
        self.assertEqual(len(json.load(open(os.path.join(self.job, "clip_map.json")))["clips"]), 2)

    def test_virtual_timeline_keeps_clips_separate(self):
        idx = json.load(open(os.path.join(self.job, "media_index.json")))
        a, b = idx["clips"]
        self.assertEqual((a["name"], b["name"]), ("01_talk.mp4", "02_broll.mp4"))
        self.assertEqual(a["start"], 0.0); self.assertAlmostEqual(b["start"], a["end"], places=2)
        self.assertTrue(a["asset_id"].startswith("a_")); self.assertTrue(a["source"].endswith(".mp4"))
        self.assertEqual(a["proxy_fps"], 30); self.assertEqual(b["role"], "b-roll")
        self.assertTrue(os.path.exists(os.path.join(self.job, "thumbs", a["scenes"][0]["thumb"])))

    def test_time_mapping_round_trips(self):
        idx = json.load(open(os.path.join(self.job, "media_index.json")))
        b = idx["clips"][1]
        tl = mi.source_to_timeline(idx, "c02", 1.0)
        self.assertAlmostEqual(tl, b["start"] + 1.0, places=2)
        self.assertEqual(mi.timeline_to_source(idx, tl)[0], "c02")
        self.assertIsNone(mi.timeline_to_source(idx, idx["duration"] + 5))

    def test_proxy_is_30fps_with_sound_in_every_part(self):
        p = os.path.join(self.job, "proxy.mp4")
        pr = lambda *a: subprocess.run(["ffprobe", "-v", "error", *a, p], capture_output=True, text=True).stdout.split()
        one = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=avg_frame_rate", "-of", "csv=p=0",
                              os.path.join(self.job, "c01", "proxy.mp4")], capture_output=True, text=True).stdout.split()
        self.assertEqual(one, ["30/1"])
        dur = 7.0                                                       # 4 s + 3 s of footage
        frames = int(pr("-select_streams", "v:0", "-count_frames", "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0")[0])
        self.assertAlmostEqual(frames, round(dur * 30), delta=2)          # no dropped or doubled stretches
        self.assertEqual(pr("-select_streams", "a", "-show_entries", "stream=codec_type", "-of", "csv=p=0"), ["audio"])
        self.assertTrue(os.path.getsize(os.path.join(self.job, "audio16k.wav")) > 1000)


if __name__ == "__main__":
    unittest.main()
