import json, os, shutil, subprocess, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from lib import render_guard as rg  # noqa: E402


def mk(path, w=540, h=960, secs=4, fps=30, vf="testsrc2", audio="sine=f=300:d=4", codec="libx264"):
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"{vf}=size={w}x{h}:rate={fps}:duration={secs}"]
    if audio:
        cmd += ["-f", "lavfi", "-i", audio]
    cmd += ["-c:v", codec, "-pix_fmt", "yuv420p"] + (["-c:a", "aac", "-shortest"] if audio else []) + [path]
    subprocess.run(cmd, check=True)


def fake_job(scenes=None, with_project=True):
    d = tempfile.mkdtemp()
    J = lambda n, v: json.dump(v, open(os.path.join(d, n), "w"))
    J("timeline.json", {"duration": 10, "scenes": scenes if scenes is not None else [{"id": "hook", "block": "hook_two_tone", "t_in": 0, "t_out": 3, "values": {}}]})
    J("edl.json", {"words": [{"text": "a", "start": 0, "end": 1}]})
    open(os.path.join(d, "proxy.mp4"), "wb").write(b"x" * 10)
    if with_project:
        p = os.path.join(d, "hyperframes"); os.makedirs(os.path.join(p, "compositions")); os.makedirs(os.path.join(p, "assets", "fonts"))
        open(os.path.join(p, "index.html"), "w").write("x"); open(os.path.join(p, "assets", "proxy.mp4"), "w").write("x")
        open(os.path.join(p, "assets", "fonts", "ReadexPro.ttf"), "w").write("x"); open(os.path.join(p, "compositions", "hook.html"), "w").write("x")
    return d


class PreflightTests(unittest.TestCase):
    def test_good_job_passes(self):
        self.assertEqual(rg.preflight(fake_job(), min_free_gb=0), [])

    def test_missing_things_are_named(self):
        d = fake_job(scenes=[{"id": "m1", "block": "nonsense", "t_in": 0, "t_out": 2, "values": {}},
                             {"id": "m2", "block": "text_card", "t_in": 5, "t_out": 99, "values": {}}])
        os.remove(os.path.join(d, "proxy.mp4")); os.remove(os.path.join(d, "hyperframes", "assets", "fonts", "ReadexPro.ttf"))
        text = " | ".join(rg.preflight(d, min_free_gb=0))
        for word in ("unknown block", "impossible times", "proxy.mp4", "ReadexPro.ttf", "scene m2"):
            self.assertIn(word, text)

    def test_no_plan_and_no_space(self):
        self.assertTrue(any("timeline.json" in x for x in rg.preflight(tempfile.mkdtemp(), min_free_gb=0)))
        self.assertTrue(any("disk space" in x for x in rg.preflight(fake_job(), min_free_gb=10 ** 6)))


class VerifyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = tempfile.mkdtemp()
        cls.ok = os.path.join(cls.d, "ok.mp4"); mk(cls.ok)
        cls.wide = os.path.join(cls.d, "wide.mp4"); mk(cls.wide, 640, 360)
        cls.silent = os.path.join(cls.d, "silent.mp4"); mk(cls.silent, audio=None)
        cls.cut = os.path.join(cls.d, "cut.mp4"); open(cls.cut, "wb").write(open(cls.ok, "rb").read()[:-3000])

    def test_good_file(self):
        e, w, i = rg.verify_video(self.ok, 4.0, 540, 960)
        self.assertEqual((e, w), ([], [])); self.assertEqual((i["width"], i["codec"], i["fps"]), (540, "h264", 30.0))

    def test_wrong_size_length_and_missing_sound_are_errors(self):
        self.assertTrue(any("not 9:16" in x for x in rg.verify_video(self.wide)[0]))
        self.assertTrue(any("expected 1080x1920" in x for x in rg.verify_video(self.ok, 4.0, 1080)[0]))
        self.assertTrue(any("plan says" in x for x in rg.verify_video(self.ok, 9.0)[0]))
        self.assertTrue(any("no sound" in x for x in rg.verify_video(self.silent)[0]))

    def test_damaged_and_missing_files(self):
        self.assertTrue(rg.verify_video(os.path.join(self.d, "nope.mp4"))[0])
        open(os.path.join(self.d, "junk.mp4"), "wb").write(b"junk")
        self.assertTrue(any("damaged" in x for x in rg.verify_video(os.path.join(self.d, "junk.mp4"))[0]))
        e, _, _ = rg.verify_video(self.cut)
        self.assertTrue(e, "a file cut short must not pass")

    def test_frame_rate_is_a_warning(self):
        p = os.path.join(self.d, "f25.mp4"); mk(p, fps=25)
        e, w, _ = rg.verify_video(p, 4.0)
        self.assertEqual(e, []); self.assertTrue(any("frame rate" in x for x in w))


class SyncTests(unittest.TestCase):
    def audio(self, bursts, secs=8):
        p = os.path.join(tempfile.mkdtemp(), "a.mp4")
        expr = "+".join(f"between(t,{a},{b})" for a, b in bursts)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=black:s=64x114:r=30:d={secs}", "-f", "lavfi", "-i",
                        f"aevalsrc='0.4*sin(2*PI*300*t)*({expr})':d={secs}", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", p], check=True)
        return p

    def test_in_sync_is_quiet_and_drift_is_flagged(self):
        words = [{"text": "w", "start": s, "end": s + 0.5} for s in (0.5, 2.0, 3.5, 5.0, 6.5)]
        ok = self.audio([(s, s + 0.5) for s in (0.5, 2.0, 3.5, 5.0, 6.5)])
        e, w, m = rg.sync_and_silence(ok, words)
        self.assertEqual(w, []); self.assertLess(abs(m["median_offset_s"]), 0.1)
        late = self.audio([(s + 0.3, s + 0.8) for s in (0.5, 2.0, 3.5, 5.0, 6.5)])
        e, w, m = rg.sync_and_silence(late, words)
        self.assertTrue(any("late" in x for x in w), (w, m))

    def test_long_silence_is_reported_unless_planned(self):
        words = [{"text": "w", "start": 0.5, "end": 1.0}, {"text": "w", "start": 6.5, "end": 7.0}]
        p = self.audio([(0.5, 1.0), (6.5, 7.0)])
        self.assertTrue(any("silence" in x for x in rg.sync_and_silence(p, words)[1]))
        self.assertEqual([x for x in rg.sync_and_silence(p, words, caption_gaps=[(1.0, 6.5)])[1] if "silence" in x], [])


class CaptionCheckTests(unittest.TestCase):
    def test_wide_caption_and_missing_card(self):
        p = os.path.join(tempfile.mkdtemp(), "v.mp4")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=gray:s=540x960:r=30:d=4", "-pix_fmt", "yuv420p", p], check=True)
        plan = {"captions": {"events": [{"start": 1.0, "end": 2.0, "text": "كلمةطويلةجدا" * 3}, {"start": 2.5, "end": 3.0, "text": "قصير"}]},
                "graphics": [{"block": "text_card", "t_in": 1.0, "t_out": 3.0}]}
        w = " | ".join(rg.caption_checks(p, plan))
        self.assertIn("wider than the safe area", w); self.assertIn("do not show up", w)           # a flat grey video shows nothing
        self.assertIn("could not be seen", w)

    def test_visible_card_is_not_flagged(self):
        p = os.path.join(tempfile.mkdtemp(), "v.mp4")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=540x960:r=30:d=4", "-vf",
                        "drawbox=x=0:y=300:w=540:h=300:color=white:t=fill:enable='between(t,1,3)'", "-pix_fmt", "yuv420p", p], check=True)
        w = rg.caption_checks(p, {"captions": {"events": []}, "graphics": [{"block": "text_card", "t_in": 1.0, "t_out": 3.0}]})
        self.assertEqual([x for x in w if "do not show up" in x], [])


class RetryTests(unittest.TestCase):
    class Boom(Exception):
        pass

    def test_what_is_temporary(self):
        for t in ("Protocol error: Target closed", "render timed out", "browser disconnected", "ECONNRESET"):
            self.assertTrue(rg.recoverable(t), t)
        for t in ("No space left on device", "hyperframes check failed: unknown block", "ENOENT file not found", "", None):
            self.assertFalse(rg.recoverable(t), t)

    def test_retries_once_only_when_temporary(self):
        calls = []
        def flaky():
            calls.append(1)
            if len(calls) == 1:
                raise self.Boom("Target closed")
            return "ok"
        self.assertEqual(rg.retry_once(flaky, self.Boom, sleep=lambda s: None, log=lambda *a: None), ("ok", 2))
        n = []
        def always():
            n.append(1); raise self.Boom("Target closed")
        with self.assertRaises(self.Boom):
            rg.retry_once(always, self.Boom, sleep=lambda s: None, log=lambda *a: None)
        self.assertEqual(len(n), 2)                                  # one retry, never a loop
        m = []
        def perm():
            m.append(1); raise self.Boom("No space left on device")
        with self.assertRaises(self.Boom):
            rg.retry_once(perm, self.Boom, sleep=lambda s: None, log=lambda *a: None)
        self.assertEqual(len(m), 1)


class ManifestTests(unittest.TestCase):
    def test_manifest_has_recipe_inputs_and_output(self):
        d = fake_job(); v = os.path.join(d, "v.mp4"); mk(v)
        m = rg.write_manifest(d, "draft", v, "draft", {"width": 540}, {"errors": [], "warnings": ["w"]}, 12.3)
        saved = json.load(open(os.path.join(d, "render_manifest_draft.json")))
        self.assertEqual(saved["recipe"]["quality"], "draft"); self.assertIn("timeline.json", saved["inputs"])
        self.assertEqual(saved["output"]["file"], "v.mp4"); self.assertEqual(saved["qa"]["warnings"], ["w"])
        self.assertEqual(rg.write_manifest(d, "draft", v, "draft")["inputs"], m["inputs"])           # same inputs, same fingerprints


if __name__ == "__main__":
    unittest.main()
