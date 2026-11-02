import json, os, subprocess, sys, tempfile, unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from lib import segcache as sc  # noqa: E402
import render  # noqa: E402


def vid(path, secs, audio_secs=None, size="270x480"):
    a = audio_secs if audio_secs is not None else secs
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size={size}:rate=30:duration={secs}", "-f", "lavfi", "-i", f"sine=f=300:d={a}",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-g", "60", "-keyint_min", "60", "-sc_threshold", "0", "-bf", "0", "-c:a", "aac", path], check=True)


def project(card_text="hello", caption="two", proxy=b"x" * 3000, script="//root"):
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "compositions")); os.makedirs(os.path.join(d, "assets"))
    open(os.path.join(d, "assets", "proxy.mp4"), "wb").write(proxy)
    caps = ('<style>x</style>\n'
            f'  <div id="caps-g0" class="clip caps-g" data-start="1" data-duration="1.5"><div>one</div></div>\n'
            f'  <div id="caps-g1" class="clip caps-g" data-start="8" data-duration="1.5"><div>{caption}</div></div>\n'
            '  <div id="caps-g2" class="clip caps-g" data-start="15" data-duration="1.5"><div>three</div></div>\n<script>t</script>')
    open(os.path.join(d, "compositions", "caps.html"), "w").write(caps)
    open(os.path.join(d, "compositions", "card1.html"), "w").write(f"<div>{card_text}</div>")
    open(os.path.join(d, "index.html"), "w").write(
        f'<html><script>{script}</script>\n<video id="seg0" class="clip" src="assets/proxy.mp4" data-start="0" data-duration="20"></video>\n'
        '<div id="card1" class="clip" data-composition-src="compositions/card1.html" data-start="13" data-duration="3"></div>\n'
        '<div id="caps" class="clip" data-composition-src="compositions/caps.html" data-start="0" data-duration="20"></div></html>')
    return d


class KeyTests(unittest.TestCase):
    def keys(self, **kw):
        return sc.piece_keys(project(**kw), sc.grid(20))

    def test_grid(self):
        self.assertEqual(sc.grid(20), [(0, 6), (6, 12), (12, 18), (18, 20)])
        self.assertEqual(sc.grid(19.0), [(0, 6), (6, 12), (12, 19.0)])        # a tail under 1.5 s joins the piece before it

    def changed(self, a, b):
        return [i for i, (x, y) in enumerate(zip(a, b)) if x != y]

    def test_same_project_same_keys(self):
        self.assertEqual(self.keys(), self.keys())

    def test_one_caption_changes_only_its_piece(self):
        self.assertEqual(self.changed(self.keys(), self.keys(caption="TWO")), [1])        # the caption at 8 s sits in piece 6-12 s

    def test_card_changes_only_pieces_it_overlaps(self):
        self.assertEqual(self.changed(self.keys(), self.keys(card_text="bye")), [2])      # card 13-16 s is inside piece 12-18 s

    def test_footage_or_page_setup_changes_everything(self):
        self.assertEqual(self.changed(self.keys(), self.keys(proxy=b"y" * 3000)), [0, 1, 2, 3])
        self.assertEqual(self.changed(self.keys(), self.keys(script="//other")), [0, 1, 2, 3])


class JoinTests(unittest.TestCase):
    def test_join_is_frame_and_sound_exact_even_if_pieces_have_uneven_sound(self):
        d = tempfile.mkdtemp()
        a, b, c = [os.path.join(d, f"{n}.mp4") for n in "abc"]
        vid(a, 6, 6.04); vid(b, 6, 5.97); vid(c, 3, 3.02)
        out = os.path.join(d, "j.mp4")
        self.assertEqual(sc.join([a, b, c], [6, 6, 3], out), "")
        r = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-show_entries", "stream=codec_type,nb_read_frames,duration", "-of", "csv=p=0", out],
                           capture_output=True, text=True).stdout.split()
        v = [x for x in r if x.startswith("video")][0].split(","); au = [x for x in r if x.startswith("audio")][0].split(",")
        self.assertEqual(v[2], "450"); self.assertAlmostEqual(float(au[1]), 15.0, delta=0.05)
        self.assertEqual(subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-i", out, "-f", "null", "-"], capture_output=True).returncode, 0)


    def test_lost_frames_are_refused_not_shipped(self):
        d = tempfile.mkdtemp(); a = os.path.join(d, "a.mp4"); vid(a, 4)
        err = sc.join([a], [6], os.path.join(d, "j.mp4"))                   # the plan says 6 s but the piece has 4 s
        self.assertIn("frames", err)


class QuickRerenderTests(unittest.TestCase):
    def setUp(self):
        self.calls = []

    def fake_render(self, project, out, quality, extra=()):
        extra = list(extra)
        a = float(extra[extra.index("--start") + 1]) if "--start" in extra else 0.0
        b = float(extra[extra.index("--end") + 1]) if "--end" in extra else 20.0
        self.calls.append((a, b))
        vid(out, b - a)
        return out

    def run_draft(self, job, proj):
        with mock.patch.object(render, "render", side_effect=self.fake_render), mock.patch.object(render, "verify"):
            return render.draft_render(job, proj, {"duration": 20.0}, say=lambda *a: None)

    def test_first_render_seeds_then_only_changed_pieces_are_rendered(self):
        job = tempfile.mkdtemp(); os.makedirs(os.path.join(job, "review"))
        p1 = project()
        full, st = self.run_draft(job, p1)
        self.assertEqual((st["mode"], len(self.calls)), ("whole+seeded", 1))
        self.assertEqual(len([f for f in os.listdir(os.path.join(job, "render_cache")) if f.endswith(".mp4")]), 4)
        self.calls.clear()
        p2 = project(caption="TWO")                                              # one caption changed (piece 6-12 s)
        full, st = self.run_draft(job, p2)
        self.assertEqual((st["mode"], st["rendered"], st["reused"]), ("pieces", 1, 3))
        self.assertEqual(self.calls, [(6.0, 12.0)])
        self.assertTrue(os.path.getsize(full) > 0)
        self.calls.clear()
        full, st = self.run_draft(job, p2)                                       # nothing changed: nothing is rendered
        self.assertEqual((st["rendered"], self.calls), (0, []))

    def test_when_most_pieces_changed_it_makes_the_whole_draft(self):
        job = tempfile.mkdtemp(); os.makedirs(os.path.join(job, "review"))
        self.run_draft(job, project()); self.calls.clear()
        full, st = self.run_draft(job, project(proxy=b"z" * 3000))               # footage changed: every piece differs
        self.assertEqual(st["mode"], "whole+seeded"); self.assertEqual(len(self.calls), 1)

    def test_a_broken_cache_falls_back_to_a_whole_render(self):
        job = tempfile.mkdtemp(); os.makedirs(os.path.join(job, "review"))
        self.run_draft(job, project()); self.calls.clear()
        calls = []
        def flaky(project, out, quality, extra=()):
            calls.append(list(extra))
            if "--start" in extra:
                raise render.RenderError("piece failed")
            return self.fake_render(project, out, quality, extra)
        with mock.patch.object(render, "render", side_effect=flaky), mock.patch.object(render, "verify"):
            full, st = render.draft_render(job, project(caption="TWO"), {"duration": 20.0}, say=lambda *a: None)
        self.assertEqual(st["mode"], "whole+seeded"); self.assertTrue(os.path.getsize(full) > 0)


if __name__ == "__main__":
    unittest.main()
