import json, os, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from lib import visual_plan as vp, brand_memory as bm, hfbuild  # noqa: E402


def W(t, s, e):
    return {"text": t, "start": s, "end": e}


def job_with(words, scenes=(), punch=(), face=None, horizontal=False, kw=(), dur=20.0):
    d = tempfile.mkdtemp()
    J = lambda n, v: json.dump(v, open(os.path.join(d, n), "w"), ensure_ascii=False)
    J("edl.json", {"words": words, "segments": [{"src_in": 0, "src_out": dur, "t_in": 0, "t_out": dur}], "duration": dur})
    J("timeline.json", {"duration": dur, "scenes": list(scenes), "punch_ins": [list(p) for p in punch], "keyword_ids": list(kw), "caption_gaps": []})
    if face:
        J("shot_log.json", [{"t": 1, "face": face}])
    if horizontal:
        J("media_manifest.json", {"files": [{"name": "wide.mp4", "use": True, "orientation": "horizontal"}]})
    return d


class VisualPlanTests(unittest.TestCase):
    def setUp(self):
        os.environ["RF_BRAND_MEMORY"] = os.path.join(tempfile.mkdtemp(), "bm.json")

    def test_captions_match_renderer_rule_and_languages(self):
        words = [W("اهلا", 0, .4), W("بكم", .45, .8), W("ads", .85, 1.2), W("اليوم", 3.0, 3.5)]
        evs = hfbuild.caption_events(words)
        d = job_with(words, kw=[2])
        p = vp.build(d)
        self.assertEqual(len(p["captions"]["events"]), len(evs))
        e0 = p["captions"]["events"][0]
        self.assertEqual((e0["language"], e0["direction"]), ("mixed", "rtl")); self.assertEqual(e0["keywords"], ["ads"])
        self.assertEqual(e0["y_band"], [1200, 1450]); self.assertEqual(p["captions"]["mixed_language_groups"], 1)

    def test_fast_captions_are_flagged(self):
        words = [W("كلمةطويلةجدا" * 2, 0, .1), W("وكلمةأخرى" * 2, .11, .2), W("وثالثة" * 3, .21, .3)]
        p = vp.build(job_with(words))
        self.assertTrue(any("characters per second" in c for c in p["checks"]))

    def test_roles_are_kept_apart_and_face_check(self):
        sc = [{"id": "hook", "block": "hook_two_tone", "t_in": 0, "t_out": 3, "values": {"line1": "a", "line2": "b"}},
              {"id": "m1", "block": "number_graph", "t_in": 5, "t_out": 9, "values": {"value": "40"}},
              {"id": "m2", "block": "flash", "t_in": 12, "t_out": 12.8, "values": {"word": "x"}}]
        p = vp.build(job_with([W("a", 0, .5)], sc, punch=[(6.0, 1.25)], face={"x": .3, "y": .4, "w": .3, "h": .4}))
        self.assertEqual([g["role"] for g in p["graphics"]], ["editorial title", "editorial graphic", "emphasis"])
        self.assertEqual(p["animations"]["punch_ins"], [{"t": 6.0, "scale": 1.25}])
        self.assertTrue(any("caption area" in c for c in p["checks"]))              # face bottom at y=1536

    def test_horizontal_source_is_mentioned(self):
        p = vp.build(job_with([W("a", 0, .5)], horizontal=True, face={"x": .0, "y": .2, "w": .2, "h": .2}))
        self.assertTrue(any("horizontally" in c and "cut the face" in c for c in p["checks"]))

    def test_nothing_without_a_timeline(self):
        self.assertIsNone(vp.build(tempfile.mkdtemp()))


class BrandMemoryTests(unittest.TestCase):
    def setUp(self):
        os.environ["RF_BRAND_MEMORY"] = os.path.join(tempfile.mkdtemp(), "bm.json")

    def test_needs_two_approved_reels_then_learns_and_compares(self):
        self.assertIsNone(bm.profile()); self.assertEqual(bm.hint(), "")
        bm.record("r1", {"moments_per_min": 4, "punch_ins_per_min": 6}, {"info_card": 3})
        self.assertIsNone(bm.profile())
        bm.record("r2", {"moments_per_min": 6, "punch_ins_per_min": 8}, {"info_card": 1, "text_card": 2})
        p = bm.profile()
        self.assertEqual((p["n"], p["intensity"]["moments_per_min"]), (2, 5.0))
        self.assertIn("5.0", bm.hint()); self.assertIn("info_card", bm.hint())
        self.assertTrue(any("busier" in n for n in bm.compare({"moments_per_min": 10})))
        self.assertTrue(any("calmer" in n for n in bm.compare({"moments_per_min": 2})))
        self.assertEqual(bm.compare({"moments_per_min": 5}), [])

    def test_same_reel_twice_counts_once_and_user_can_override_or_switch_off(self):
        bm.record("r1", {"moments_per_min": 4}); bm.record("r1", {"moments_per_min": 5}); bm.record("r2", {"moments_per_min": 5})
        self.assertEqual(bm.profile()["n"], 2)
        d = json.load(open(bm.path())); d["overrides"] = {"moments_per_min": 9}; json.dump(d, open(bm.path(), "w"))
        self.assertEqual(bm.profile()["intensity"]["moments_per_min"], 9)
        d["enabled"] = False; json.dump(d, open(bm.path(), "w"))
        self.assertIsNone(bm.profile())

    def test_damaged_memory_file_is_ignored(self):
        open(bm.path(), "w").write("{not json") if os.path.isdir(os.path.dirname(bm.path())) else None
        self.assertIsNone(bm.profile())


if __name__ == "__main__":
    unittest.main()
