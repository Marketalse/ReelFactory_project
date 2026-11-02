"""Ready-to-post score: points per check, concrete tips, never a crash on a half-made reel."""
import json, os, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import ready_score  # noqa: E402


def job(d, first=0.2, dur=50.0, punch_every=2.0, qa=None, cover=True, kw=15):
    words = [{"text": "كلمة", "start": round(first + i * 0.4, 2), "end": round(first + i * 0.4 + 0.3, 2)} for i in range(int((dur - first) / 0.4))]
    tl = {"duration": dur, "keyword_ids": list(range(0, kw * 3, 3)),
          "punch_ins": [[round(t, 2), 1.2] for t in [x * punch_every for x in range(1, int(dur / punch_every))]],
          "scenes": [{"id": "hook", "block": "hook_two_tone", "t_in": 0.0, "t_out": 2.6, "values": {"line1": "شكد بضاعة", "line2": "لازم تجيب"}},
                     {"id": "m0", "block": "text_card", "t_in": 10.0, "t_out": 12.0, "values": {"headline": "x"}}],
          "caption_gaps": [[10.0, 12.0]]}
    json.dump(tl, open(os.path.join(d, "timeline.json"), "w"))
    json.dump({"words": words, "segments": [{"t_in": 0, "t_out": dur, "src_in": 0, "src_out": dur}]}, open(os.path.join(d, "edl.json"), "w"))
    json.dump(qa if qa is not None else {"metrics": {"duration": dur, "lufs": -14.2, "true_peak": -1.6, "black": [], "frozen": [],
                                                     "caption_words": 100, "spoken_words_shown": 100}}, open(os.path.join(d, "qa.json"), "w"))
    if cover:
        os.makedirs(os.path.join(d, "review"), exist_ok=True); open(os.path.join(d, "review", "cover.jpg"), "w").close()


class ReadyScoreTests(unittest.TestCase):
    def test_a_well_made_reel_scores_high_and_has_no_tips(self):
        with tempfile.TemporaryDirectory() as d:
            job(d); r = ready_score.score(d)
            self.assertGreaterEqual(r["score"], 85, r["checks"]); self.assertEqual(r["grade"], "ready")
            self.assertEqual(r["top_tips"], []); self.assertEqual(sum(c["max"] for c in r["checks"]), 100)
            self.assertTrue(os.path.exists(os.path.join(d, "ready_score.json")))

    def test_slow_start_long_reel_and_no_zooms_are_named(self):
        with tempfile.TemporaryDirectory() as d:
            job(d, first=2.4, dur=88.0, punch_every=30.0, cover=False)
            r = ready_score.score(d)
            self.assertLess(r["score"], 70); self.assertEqual(r["grade"], "fix")
            tips = " ".join(r["top_tips"])
            self.assertIn("2.4 s", tips)                                       # first word time
            self.assertTrue(any("Nothing changes" in c["tip"] for c in r["checks"]))
            self.assertLessEqual(len(r["top_tips"]), 3)
            self.assertEqual(next(c for c in r["checks"] if c["key"] == "cover")["points"], 5)     # draft: cover comes later
            r = ready_score.score(d, final=True)
            self.assertEqual(next(c for c in r["checks"] if c["key"] == "cover")["points"], 0)     # final without cover

    def test_missing_qa_or_plan_never_crashes(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(ready_score.score(d))                            # nothing made yet
            job(d, qa={}); r = ready_score.score(d)
            self.assertIsNotNone(r); self.assertIn(r["grade"], ("ready", "good", "fix"))
