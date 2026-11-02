import json, os, shutil, subprocess, sys, tempfile, unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import cover  # noqa: E402


def shot(t, **k):
    d = {"t": t, "face": {"x": .3, "y": .2, "w": .4, "h": .2}, "eyes": "open", "energy": 3, "usable": ["cut"], "headroom": "ok", "bg": "low"}
    d.update(k); return d


class FrameChoiceTests(unittest.TestCase):
    def job(self, rows):
        d = tempfile.mkdtemp(); json.dump(rows, open(os.path.join(d, "shot_log.json"), "w")); return d

    def test_best_moment_prefers_open_eyes_a_hook_look_energy_and_a_centred_face(self):
        d = self.job([shot(1, eyes="closed", energy=5), shot(2, usable=["avoid"]), shot(3, face=None), shot(4, face={"x": .0, "y": .2, "w": .2, "h": .2}, energy=5),
                      shot(5, energy=2), shot(6, usable=["hook"], energy=4), shot(7, usable=["hook"], energy=4, bg="high")])
        self.assertEqual(cover.best_moment(d)["t"], 6.0)

    def test_no_shot_log_means_no_choice(self):
        self.assertIsNone(cover.best_moment(tempfile.mkdtemp())); self.assertIsNone(cover.best_moment(self.job([shot(1, eyes="closed")])))


class LayoutTests(unittest.TestCase):
    def test_title_size_short_is_big_long_uses_two_lines_inside_the_box(self):
        self.assertEqual(cover.title_size("شنو تتصور؟")[1], 1); big, _ = cover.title_size("شنو تتصور؟"); self.assertGreaterEqual(big, 120)
        size, lines = cover.title_size("حاط بيج وما حاط رقم تواصل وياك؟")
        self.assertGreaterEqual(lines, 2); self.assertLessEqual(0.62 * size * len("حاط بيج وما حاط رقم تواصل وياك؟") / lines, 780 * 1.15)

    def test_the_head_covers_the_lower_part_of_the_title(self):
        g = cover.hero_geometry({"x": .3, "y": .25, "w": .4, "h": .2}, True, 140, 140)
        head_top = g["p_top"] + .25 * g["p_h"]
        title_h = 280 * .98
        self.assertGreater(g["title_top"] + title_h, head_top); self.assertLess(g["title_top"], head_top)       # the title reaches behind the head but starts above it
        self.assertGreaterEqual(g["title_top"], 340)

    def test_make_uses_the_hero_layout_with_a_cutout_and_falls_back_without(self):
        d = tempfile.mkdtemp()
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=270x480:rate=30:duration=4", "-pix_fmt", "yuv420p", os.path.join(d, "proxy.mp4")], check=True)
        json.dump({"hook": {"line1": "عنوان", "line2": "سطر"}}, open(os.path.join(d, "scene_plan.json"), "w"), ensure_ascii=False)
        json.dump([shot(1.0)], open(os.path.join(d, "shot_log.json"), "w"))
        def fake_shoot(project, dest):
            shutil.copy(os.path.join(project, "index.html"), dest + ".html"); open(dest, "wb").write(b"jpg"); return dest
        def fake_cut(photo, dest, runner=None):
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=gray:s=100x100", "-frames:v", "1", dest], check=True); return dest
        with mock.patch.object(cover, "shoot", side_effect=fake_shoot), mock.patch.object(cover, "cutout", side_effect=fake_cut):
            r = cover.make(d)
        self.assertEqual(r["layout"], "hero (cutout)"); self.assertIn("assets/cutout.png", open(os.path.join(d, "review", "cover.jpg.html"), encoding="utf-8").read())
        with mock.patch.object(cover, "shoot", side_effect=fake_shoot), mock.patch.object(cover, "cutout", return_value=None):
            r = cover.make(d)
        self.assertEqual(r["layout"], "classic"); self.assertNotIn("cutout.png", open(os.path.join(d, "review", "cover.jpg.html"), encoding="utf-8").read())

    def test_a_failing_model_gives_none_not_an_error(self):
        self.assertIsNone(cover.cutout("x.jpg", "y.png", runner=lambda *a, **k: subprocess.CompletedProcess(a, 1, "", "no model")))
        def boom(*a, **k): raise OSError("npx missing")
        self.assertIsNone(cover.cutout("x.jpg", "y.png", runner=boom))


if __name__ == "__main__":
    unittest.main()
