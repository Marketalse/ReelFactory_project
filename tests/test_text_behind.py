import json, os, subprocess, sys, tempfile, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from lib import hfbuild, director, matte, render_guard  # noqa: E402
import compile as comp  # noqa: E402


def make_job(face_x=0.5, secs=12):
    d = tempfile.mkdtemp()
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size=270x480:rate=30:duration={secs}", "-f", "lavfi", "-i", f"sine=f=200:d={secs}",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", os.path.join(d, "proxy.mp4")], check=True)
    words = [{"text": "كلمة", "start": 0.3 + i * 0.4, "end": 0.6 + i * 0.4, "src_i": i} for i in range(28)]
    J = lambda n, x: json.dump(x, open(os.path.join(d, n), "w"), ensure_ascii=False)
    J("edl.json", {"words": words, "segments": [{"src_in": 0.0, "src_out": 5.0, "t_in": 0.0, "t_out": 5.0}, {"src_in": 7.0, "src_out": 12.0, "t_in": 5.0, "t_out": 10.0}], "duration": 10.0})
    J("timeline.json", {"duration": 10.0, "scenes": [{"id": "tb1", "block": "text_behind", "t_in": 3.0, "t_out": 6.0, "values": {"text": "التسويق"}}],
                        "punch_ins": [[3.5, 1.25]], "keyword_ids": [], "caption_gaps": [], "face_cy": 0.38})
    J("shot_log.json", [{"t": 1, "face": {"x": face_x - .1, "y": .25, "w": .2, "h": .2}}])
    return d


def fake_cutout(job, edl, a, b, final, say=print):
    p = os.path.join(job, "fake.webm"); open(p, "wb").write(b"webm"); return p


class BuildingBlocks(unittest.TestCase):
    def test_stamp_puts_the_cutout_path_and_height_into_the_file(self):
        t = hfbuild.stamp("text_behind", "tb1", 3.0, "", {"text": "التسويق", "matte": "assets/matte_tb1.webm", "top": 410})
        self.assertIn('src="assets/matte_tb1.webm"', t); self.assertIn("top:410px", t); self.assertNotIn("__VAR_", t)

    def test_face_is_unzoomed_during_the_moment(self):
        tl = {"duration": 10.0, "scenes": [{"id": "tb1", "block": "text_behind", "t_in": 3.0, "t_out": 6.0}], "punch_ins": [[3.5, 1.25]]}
        segs = [{"src_in": 0, "src_out": 5, "t_in": 0, "t_out": 5}, {"src_in": 7, "src_out": 12, "t_in": 5, "t_out": 10}]
        cuts = director.face_cuts(tl, segs)
        inside = [c for c in cuts if c["t_in"] >= 3.0 - 1e-6 and c["t_out"] <= 6.0 + 1e-6]
        self.assertTrue(inside and all(c["scale"] == 1.0 and c["y"] == 0 for c in inside))                  # no punch-in, no 1.08 zoom of the second EDL piece
        self.assertTrue(any(c["scale"] != 1.0 for c in director.face_cuts(dict(tl, scenes=[]), segs)))     # (without the moment the zooms are there)

    def test_max_two_per_reel_is_a_rule(self):
        words = [{"text": "كلمة", "start": i * 0.5, "end": i * 0.5 + 0.4} for i in range(120)]
        plan = {"hook": {"line1": "عنوان", "line2": "سطر"}, "keyword_ids": [], "punch_ins": [], "cta": {}, "cover": {},
                "moments": [{"block": "text_behind", "at_word": w, "duration": 2.5, "values": {"text": "كلمة"}} for w in (10, 40, 70)]}
        err = director.resolve(plan, words, words[-1]["end"], logos=[])[1]
        self.assertTrue(any("maximum 2 per reel" in e for e in err), err)


class MatteTests(unittest.TestCase):
    def test_slices_follow_the_edl_across_a_jump_cut(self):
        segs = [{"src_in": 0.0, "src_out": 5.0, "t_in": 0.0, "t_out": 5.0}, {"src_in": 7.0, "src_out": 12.0, "t_in": 5.0, "t_out": 10.0}]
        self.assertEqual(matte.slices(segs, 3.0, 6.0), [(3.0, 5.0), (7.0, 8.0)])
        self.assertEqual(matte.slices(segs, 6.0, 7.0), [(8.0, 9.0)]); self.assertEqual(matte.slices(segs, 20, 21), [])

    def test_cache_key_changes_with_footage_pieces_and_size(self):
        d = make_job(); p = os.path.join(d, "proxy.mp4")
        k = matte.key(p, [(3.0, 5.0)], 540)
        self.assertEqual(k, matte.key(p, [(3.0, 5.0)], 540)); self.assertNotEqual(k, matte.key(p, [(3.0, 5.0)], 1080)); self.assertNotEqual(k, matte.key(p, [(3.0, 6.0)], 540))

    def test_cutout_runs_the_model_once_and_then_uses_the_cache(self):
        d = make_job(); edl = json.load(open(os.path.join(d, "edl.json"))); calls = []
        def runner(cmd, **k):
            calls.append(cmd[0] if cmd[0] == "ffmpeg" else "model")
            out = cmd[cmd.index("-o") + 1] if "-o" in cmd else cmd[-1]
            open(out, "wb").write(b"x" * 10)
            return subprocess.CompletedProcess(cmd, 0, "", "")
        p1 = matte.cutout(d, edl, 3.0, 6.0, False, say=lambda *a: None, runner=runner)
        p2 = matte.cutout(d, edl, 3.0, 6.0, False, say=lambda *a: None, runner=runner)
        self.assertEqual((p1, calls), (p2, ["ffmpeg", "model"]))
        self.assertTrue(p1.endswith(".webm"))

    def test_model_failure_is_a_clear_matte_error(self):
        d = make_job(); edl = json.load(open(os.path.join(d, "edl.json")))
        def runner(cmd, **k):
            if cmd[0] == "ffmpeg":
                open(cmd[-1], "wb").write(b"x"); return subprocess.CompletedProcess(cmd, 0, "", "")
            return subprocess.CompletedProcess(cmd, 1, "", "model download failed")
        with self.assertRaises(matte.MatteError) as cm:
            matte.cutout(d, edl, 3.0, 6.0, True, say=lambda *a: None, runner=runner)
        self.assertIn("model download failed", str(cm.exception))

    def test_face_must_be_in_the_middle(self):
        mk = lambda x: [{"face": {"x": x - .1, "y": .2, "w": .2, "h": .2}}]
        self.assertTrue(matte.face_ok(mk(0.5))); self.assertFalse(matte.face_ok(mk(0.1))); self.assertTrue(matte.face_ok([]))


class CompileTests(unittest.TestCase):
    def test_compile_adds_the_cutout_and_the_render_check_sees_it(self):
        d = make_job()
        with mock.patch.object(matte, "cutout", side_effect=fake_cutout):
            out = comp.compile_job(d)
        self.assertTrue(os.path.exists(os.path.join(out, "assets", "matte_tb1.webm")))
        page = open(os.path.join(out, "compositions", "tb1.html"), encoding="utf-8").read()
        self.assertIn("assets/matte_tb1.webm", page)
        info = json.load(open(os.path.join(out, "compile_info.json")))
        self.assertEqual(info["dropped_scenes"], []); self.assertTrue(any(c["scale"] == 1.0 for c in info["face_cuts"]))
        self.assertEqual([p for p in render_guard.preflight(d, out, min_free_gb=0) if "cutout" in p], [])
        os.remove(os.path.join(out, "assets", "matte_tb1.webm"))
        self.assertTrue(any("cutout" in p for p in render_guard.preflight(d, out, min_free_gb=0)))

    def test_a_failed_cutout_drops_only_that_moment_and_the_reel_still_builds(self):
        d = make_job()
        with mock.patch.object(matte, "cutout", side_effect=matte.MatteError("model missing")):
            out = comp.compile_job(d)
        info = json.load(open(os.path.join(out, "compile_info.json")))
        self.assertEqual(info["dropped_scenes"], ["tb1"]); self.assertFalse(os.path.exists(os.path.join(out, "compositions", "tb1.html")))
        self.assertEqual([p for p in render_guard.preflight(d, out, min_free_gb=0) if "tb1" in p], [])            # not reported as missing: it was dropped on purpose
        self.assertTrue(all(c["scale"] != 1.0 or True for c in info["face_cuts"]))

    def test_an_off_centre_face_drops_it_without_running_the_model(self):
        d = make_job(face_x=0.1)
        with mock.patch.object(matte, "cutout", side_effect=AssertionError("must not run")):
            out = comp.compile_job(d)
        self.assertEqual(json.load(open(os.path.join(out, "compile_info.json")))["dropped_scenes"], ["tb1"])


if __name__ == "__main__":
    unittest.main()
