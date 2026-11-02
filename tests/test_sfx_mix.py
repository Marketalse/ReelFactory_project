import json, os, subprocess, sys, tempfile, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from lib import sfx_mix, hfbuild, director, config as cfg  # noqa: E402
import compile as comp  # noqa: E402

REG = hfbuild.REGISTRY["blocks"]


class PlanTests(unittest.TestCase):
    def tl(self):
        return {"duration": 30.0, "scenes": [{"id": "hook", "block": "hook_two_tone", "t_in": 0, "t_out": 2.6}, {"id": "m1", "block": "info_card", "t_in": 6.0, "t_out": 9.0},
                {"id": "m2", "block": "split", "t_in": 12.0, "t_out": 15.0}, {"id": "m3", "block": "name_tag", "t_in": 20.0, "t_out": 22.0}],
                "punch_ins": [[6.1, 1.25], [18.0, 1.25]]}

    def test_each_moment_plays_its_registry_sound(self):
        ev = sfx_mix.plan(self.tl(), REG)
        got = [(e["name"], round(e["t"], 2)) for e in ev]
        self.assertIn(("hit", 0.12), got); self.assertIn(("whoosh", 6.0), got); self.assertIn(("whoosh", 12.0), got); self.assertIn(("ding", 12.8), got); self.assertIn(("pop", 20.0), got)

    def test_key_words_pop_at_most_every_three_seconds_and_effects_never_pile_up(self):
        words = [{"text": "w", "start": i * 1.0, "end": i * 1.0 + .3} for i in range(25)]
        ev = sfx_mix.plan(self.tl(), REG, words, list(range(25)))
        pops = [e for e in ev if e.get("kind") == "keyword"]
        self.assertGreaterEqual(len(pops), 2); self.assertTrue(all(b["t"] - a["t"] >= 3 - 1e-6 for a, b in zip(pops, pops[1:])))
        self.assertTrue(all(b["t"] - a["t"] >= sfx_mix.QUIET_GAP - 1e-6 for a, b in zip(ev, ev[1:])))

    def test_can_be_switched_off(self):
        with mock.patch.dict(cfg.BRAND, {"sfx": {"enabled": False}}):
            self.assertEqual(sfx_mix.plan(self.tl(), REG), [])
        with mock.patch.dict(cfg.BRAND, {"sfx": {"punch_ins": False}}):
            self.assertFalse(any(e.get("quiet") for e in sfx_mix.plan(self.tl(), REG)))


class CompileTests(unittest.TestCase):
    def make_job(self):
        d = tempfile.mkdtemp()
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=270x480:rate=30:duration=10", "-f", "lavfi", "-i", "sine=f=200:d=10",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", os.path.join(d, "proxy.mp4")], check=True)
        words = [{"text": "كلمة", "start": 0.3 + i * 0.4, "end": 0.6 + i * 0.4, "src_i": i} for i in range(24)]
        J = lambda n, x: json.dump(x, open(os.path.join(d, n), "w"), ensure_ascii=False)
        J("edl.json", {"words": words, "segments": [{"src_in": 0.0, "src_out": 10.0, "t_in": 0.0, "t_out": 10.0}], "duration": 10.0})
        J("timeline.json", {"duration": 10.0, "scenes": [{"id": "dc1", "block": "doc_card", "t_in": 3.0, "t_out": 5.5, "values": {"title": "خطة", "highlight": "رد خلال دقيقة"}}],
                            "punch_ins": [[7.0, 1.25]], "keyword_ids": [3], "caption_gaps": [], "face_cy": 0.38})
        return d

    def test_compile_puts_the_sounds_in_the_project(self):
        out = comp.compile_job(self.make_job())
        page = open(os.path.join(out, "index.html"), encoding="utf-8").read()
        self.assertGreaterEqual(page.count("<audio"), 3)                                       # a whoosh, a key-word pop, a quiet punch-in pop
        self.assertTrue(os.path.exists(os.path.join(out, "assets", "sfx", "whoosh.wav")))
        self.assertGreaterEqual(json.load(open(os.path.join(out, "compile_info.json")))["sfx"], 3)

    def test_the_clean_video_layer_has_no_effects_and_off_means_off(self):
        d = self.make_job()
        out = comp.compile_job(d, layer="video")
        self.assertEqual(open(os.path.join(out, "index.html"), encoding="utf-8").read().count("<audio"), 0)
        with mock.patch.dict(cfg.BRAND, {"sfx": {"enabled": False}}):
            self.assertEqual(json.load(open(os.path.join(comp.compile_job(d), "compile_info.json")))["sfx"], 0)


class ZoomTests(unittest.TestCase):
    def build(self, cuts):
        out = tempfile.mkdtemp(); v = os.path.join(out, "v.mp4"); open(v, "wb").write(b"x")
        hfbuild.build_project(out, duration=10, face_cuts=cuts, scenes=[], video_src=v)
        return open(os.path.join(out, "index.html"), encoding="utf-8").read()

    def test_a_zoom_inside_one_take_snaps_and_a_real_cut_stays_instant(self):
        page = self.build([{"id": "s0", "t_in": 0, "t_out": 3, "src_in": 0, "scale": 1.0}, {"id": "s1", "t_in": 3, "t_out": 4.6, "src_in": 3, "scale": 1.25},
                           {"id": "s2", "t_in": 4.6, "t_out": 7, "src_in": 4.6, "scale": 1.0}, {"id": "s3", "t_in": 7, "t_out": 10, "src_in": 20, "scale": 1.25}])
        self.assertIn('tl.to("#face", { scale: 1.25, x: 0, y: 0, duration: 0.14, ease: "power2.out" }, 3);', page)        # zoom in: fast snap
        self.assertIn('duration: 0.2, ease: "power2.out" }, 4.6);', page)                                                  # zoom out: a bit slower
        self.assertTrue('tl.set("#face", { scale: 1.25, x: 0, y: 0 }, 7);' in page)                                          # a real jump cut stays instant


if __name__ == "__main__":
    unittest.main()
