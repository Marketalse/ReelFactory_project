"""Face pieces shorter than 0.3 s are folded into a neighbour instead of stopping the reel."""
import json, os, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from lib import director  # noqa: E402


def C(t_in, t_out, src_in, scale=1.0, y=0):
    return {"id": "x", "t_in": t_in, "t_out": t_out, "src_in": src_in, "scale": scale, "cy": 0.36, "y": y}


class ShortCutTests(unittest.TestCase):
    def test_sliver_at_start_joins_the_same_footage(self):
        # zoom starts 0.2 s in: piece 0-0.2 (1.0x) then 0.2-3 (1.08x), same footage
        out = director.absorb_short([C(0, 0.2, 5.0), C(0.2, 3.0, 5.2, 1.08)])
        self.assertEqual(len(out), 1); self.assertEqual((out[0]["t_in"], out[0]["t_out"], out[0]["src_in"]), (0, 3.0, 5.0))

    def test_sliver_between_different_takes_extends_the_previous(self):
        out = director.absorb_short([C(0, 2.0, 0.0), C(2.0, 2.15, 9.0), C(2.15, 5.0, 20.0)])
        self.assertEqual([(c["t_in"], c["t_out"]) for c in out], [(0, 2.15), (2.15, 5.0)])

    def test_first_piece_alone_borrows_from_the_next(self):
        out = director.absorb_short([C(0, 0.1, 50.0), C(0.1, 4.0, 3.0)])
        self.assertEqual(len(out), 1); self.assertEqual(out[0]["t_in"], 0); self.assertAlmostEqual(out[0]["src_in"], 2.9)

    def test_real_timeline_never_yields_short_pieces(self):
        tl = {"duration": 10.0, "punch_ins": [(0.15, 1.12)], "face_cy": 0.36,
              "scenes": [{"block": "split", "t_in": 4.1, "t_out": 6.0}]}
        segs = [{"t_in": 0.0, "t_out": 4.0, "src_in": 1.0}, {"t_in": 4.0, "t_out": 10.0, "src_in": 8.0}]
        cuts = director.face_cuts(tl, segs)
        self.assertTrue(all(c["t_out"] - c["t_in"] >= 0.3 - 1e-6 for c in cuts), cuts)
        self.assertEqual(cuts[0]["t_in"], 0.0); self.assertEqual(cuts[-1]["t_out"], 10.0)
        for a, b in zip(cuts, cuts[1:]):
            self.assertAlmostEqual(a["t_out"], b["t_in"])


    def test_zoom_just_after_a_cut_leaves_no_black_gap(self):
        # found by the stress test: a punch-in 0.03 s after a cut used to leave a 1-frame hole
        tl = {"duration": 12.0, "punch_ins": [(4.03, 1.25)], "face_cy": 0.36, "scenes": []}
        segs = [{"t_in": 0.0, "t_out": 4.0, "src_in": 0.0}, {"t_in": 4.0, "t_out": 12.0, "src_in": 9.0}]
        cuts = director.face_cuts(tl, segs)
        self.assertEqual(cuts[0]["t_in"], 0.0); self.assertEqual(cuts[-1]["t_out"], 12.0)
        for a, b in zip(cuts, cuts[1:]):
            self.assertAlmostEqual(a["t_out"], b["t_in"], places=6)

    def test_exactly_point_three_seconds_is_accepted(self):
        import tempfile
        from lib import hfbuild
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "v.mp4"), "wb").write(b"0")
            hfbuild.build_project(os.path.join(d, "p"), duration=0.6, scenes=[], video_src=os.path.join(d, "v.mp4"),
                                  face_cuts=[C(47.92, 48.22, 1.0), C(48.22, 48.52, 1.3)])


class CaptionStopTests(unittest.TestCase):
    def test_caption_never_runs_into_a_card_or_the_cta(self):
        # found in render loop 1: the last caption was held 0.35 s into the CTA and covered its text
        import re
        from lib import hfbuild
        words = [{"text": f"w{i}", "start": 46.0 + 0.4 * i, "end": 46.3 + 0.4 * i} for i in range(5)]   # last word ends 47.9
        html_ = hfbuild.caption_groups(words, [], "caps", stops=[48.12])
        ends = [float(a) + float(b) for a, b in re.findall(r'data-start="([0-9.]+)" data-duration="([0-9.]+)"', html_)]
        self.assertTrue(all(e <= 48.12 + 1e-6 for e in ends), ends)


class ShortEdlTests(unittest.TestCase):
    def test_short_first_word_is_widened_into_silence_not_merged_across_a_pause(self):
        from lib import edl
        words = [{"text": "و", "start": 0.0, "end": 0.08}] + [
            {"text": f"w{i}", "start": round(3.0 + 0.4 * i, 2), "end": round(3.3 + 0.4 * i, 2)} for i in range(10)]
        e = edl.build(words, 0.0, 8.0, drop_fillers=False, retakes=False)
        self.assertTrue(all(s["t_out"] - s["t_in"] >= 0.3 - 1e-6 for s in e["segments"]), e["segments"])
        self.assertLess(e["duration"], 5.0)          # the 2.9 s pause after the first word is still cut


if __name__ == "__main__":
    unittest.main()


class RhythmAutoFixTests(unittest.TestCase):
    def test_still_stretch_gets_zooms_for_free(self):

        words = [{"text": f"w{i}", "start": i * 0.5, "end": i * 0.5 + 0.4} for i in range(40)]      # 20 s of speech
        segs = [{"t_in": 0.0, "t_out": 20.0}]

        def resolve(plan):
            tl = {"duration": 20.0, "scenes": [], "keyword_ids": [],
                  "punch_ins": sorted((words[p["at_word"]]["start"], p["scale"]) for p in plan.get("punch_ins") or [])}
            cuts = [{"t_in": a, "t_out": b} for a, b in zip([0.0] + [t for t, _ in tl["punch_ins"]], [t for t, _ in tl["punch_ins"]] + [20.0])]
            return tl, director.check_rhythm(tl, cuts), []
        plan, tl, err, warn, added = director.fix_rhythm({"punch_ins": []}, words, resolve)
        self.assertEqual(err, []); self.assertGreater(added, 0); self.assertLessEqual(added, 12)
        self.assertTrue(all(1.1 <= p["scale"] <= 1.5 for p in plan["punch_ins"]))

    def test_other_errors_are_left_alone(self):

        plan, tl, err, warn, added = director.fix_rhythm({}, [{"start": 0}], lambda p: ({}, ["card too long"], []))
        self.assertEqual(added, 0); self.assertEqual(err, ["card too long"])


class OverlapAutoFixTests(unittest.TestCase):
    def test_overlapping_moments_fixed_for_free(self):
        words = [{"text": f"w{i}", "start": round(i * 0.45, 2), "end": round(i * 0.45 + 0.38, 2)} for i in range(120)]
        dur = words[-1]["end"]
        plan = {"hook": {"line1": "عنوان", "line2": "سطر"}, "keyword_ids": [], "punch_ins": [], "cta": {}, "cover": {},
                "moments": [{"block": "info_card", "at_word": 30, "duration": 4.0, "values": {"headline": "خدمة الزبائن"}},
                            {"block": "name_tag", "at_word": 36, "duration": 2.5, "values": {"name": "هشام"}}]}
        resolve = lambda p: director.resolve(p, words, dur, logos=[])
        _, e0, _ = resolve(json.loads(json.dumps(plan)))
        if not e0:
            self.skipTest("sample does not overlap with this template range")
        self.assertTrue(all(director.OVERLAP_ERR.search(x) for x in e0), e0)
        plan2, tl, err, warn, n = director.fix_overlaps(plan, resolve)
        self.assertEqual(err, []); self.assertGreater(n, 0)

    def test_other_errors_left_alone(self):
        plan, tl, err, warn, n = director.fix_overlaps({}, lambda p: ({}, ["card too long"], []))
        self.assertEqual((n, err), (0, ["card too long"]))


class RelaxedDurationTests(unittest.TestCase):
    def test_edit_page_may_stretch_and_shrink_clips(self):
        words = [{"text": f"w{i}", "start": round(i * 0.45, 2), "end": round(i * 0.45 + 0.38, 2)} for i in range(120)]
        plan = {"hook": {"line1": "عنوان", "line2": "سطر"}, "keyword_ids": [], "punch_ins": [], "cta": {}, "cover": {},
                "moments": [{"block": "text_card", "at_word": 12, "duration": 9.0, "values": {"headline": "خدمة الزبائن"}},
                            {"block": "info_card", "at_word": 60, "duration": 0.6, "values": {"headline": "قصير"}}]}
        strict, _, w1 = director.resolve(json.loads(json.dumps(plan)), words, words[-1]["end"], logos=[])
        loose, e2, w2 = director.resolve(json.loads(json.dumps(plan)), words, words[-1]["end"], logos=[], relaxed=True)
        d = lambda tl, b: next(round(s["t_out"] - s["t_in"], 1) for s in tl["scenes"] if s["block"] == b)
        self.assertEqual(d(strict, "text_card"), 3.5)                    # the AI is kept to the template's range
        self.assertEqual((d(loose, "text_card"), d(loose, "info_card")), (9.0, 0.6)); self.assertEqual((e2, w2), ([], []))
