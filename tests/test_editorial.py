import json, os, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from lib import editorial as ed, config as cfg  # noqa: E402


def W(t, s, e, i=None):
    d = {"text": t, "start": s, "end": e}
    if i is not None:
        d["src_i"] = i
    return d


WORDS = [W(x, i * 0.5, i * 0.5 + 0.4) for i, x in enumerate("اهلا بكم اليوم نحچي عن المتجر الالكتروني وكيف تبدأ بدون راس مال".split())]


class StoryScoreTests(unittest.TestCase):
    def test_formula_and_weights(self):
        w = ed.weights(cfg.RULES)
        self.assertAlmostEqual(sum(w.values()), 1.0)
        self.assertAlmostEqual(w["relevance"], 0.30)
        s = ed.score_select({"range": [0, 5], "score": 9, "scores": {"relevance": 10, "clarity": 10, "delivery": 10, "novelty": 10, "fit": 10}}, w)
        self.assertEqual(s["score"], 10.0); self.assertEqual(s["ai_score"], 9)
        s = ed.score_select({"range": [0, 5], "scores": {"relevance": 8, "clarity": 6, "delivery": 4, "novelty": 2, "fit": 10}}, w)
        self.assertEqual(s["score"], round(.3 * 8 + .25 * 6 + .2 * 4 + .15 * 2 + .1 * 10, 2))

    def test_careless_weights_are_rescaled(self):
        w = ed.weights({"story_score": {"weights": {"relevance": 3, "clarity": 1, "delivery": 0, "novelty": 0, "fit": 0}}})
        self.assertAlmostEqual(w["relevance"], 0.75); self.assertAlmostEqual(sum(w.values()), 1.0)

    def test_without_parts_ai_score_stays(self):
        s = ed.score_select({"range": [0, 5], "score": 7}, ed.weights(None))
        self.assertEqual(s["score"], 7); self.assertEqual(s["parts"], {})

    def test_measured_delivery_is_blended(self):
        si = {"delivery": {"fillers": [{"t": 1}, {"t": 2}, {"t": 3}], "repeats": [], "pauses": [], "unfinished_sentences": [], "emphasis_words": []}}
        w = ed.weights(None)
        s = ed.score_select({"range": [0, 10], "scores": {k: 8 for k in w}}, w, si)
        self.assertLess(s["parts"]["D"], 8); self.assertIn("delivery_measured", s)


class HookTests(unittest.TestCase):
    def test_real_hook_found_and_invented_hook_flagged(self):
        sel = {"range": [0, 7], "hooks": [{"type": "direct", "line": "وكيف تبدأ بدون راس مال"}, {"type": "curiosity", "line": "سر لا يعرفه أحد"}]}
        h = ed.check_hooks(sel, WORDS)
        self.assertTrue(h[0]["found"] and h[0]["inside_range"]); self.assertFalse(h[1]["found"])


class FlagTests(unittest.TestCase):
    def test_range_flags(self):
        f = ed.range_flags({"range": [0.2, 20]}, WORDS, 40, 90)
        self.assertTrue(any("length" in x for x in f)); self.assertTrue(any("inside a word" in x for x in f))
        self.assertEqual([x for x in ed.range_flags({"range": [0, 50]}, WORDS, 40, 90) if "inside" in x], [])

    def test_continuity_tight_cut(self):
        edl = {"segments": [{"src_in": 0, "src_out": 2.0, "t_in": 0, "t_out": 2.0}, {"src_in": 2.05, "src_out": 4, "t_in": 2.0, "t_out": 3.95}],
               "words": [W("a", 0.1, 1.9, 3), W("b", 2.0, 3.0, 4)], "duration": 3.95}
        self.assertTrue(any("tight cut" in x for x in ed.continuity(edl)))
        ok = {"segments": [{"src_in": 0, "src_out": 2.0, "t_in": 0, "t_out": 2.0}, {"src_in": 3.0, "src_out": 5, "t_in": 2.0, "t_out": 4.0}],
              "words": [W("a", 0.1, 1.9, 3), W("b", 2.0, 3.0, 9)], "duration": 4.0}
        self.assertEqual(ed.continuity(ok), [])


class BuildTests(unittest.TestCase):
    def test_editorial_file_written_with_alternatives(self):
        d = tempfile.mkdtemp()
        J = lambda n, v: json.dump(v, open(os.path.join(d, n), "w"), ensure_ascii=False)
        J("transcript.json", WORDS)
        J("selects.json", {"main_message": "start a store with no capital", "audience": "new owners",
                           "selects": [{"id": "A", "range": [0, 7], "label": "a", "score": 8, "parts": {"R": 8}}, {"id": "B", "range": [3, 7], "label": "b", "score": 6}]})
        J("chosen_select.json", {"id": "A", "range": [0, 7], "why": "clear", "hooks": [{"type": "direct", "line": "وكيف تبدأ بدون راس مال"}]})
        J("edl.json", {"segments": [{"src_in": 0, "src_out": 7, "t_in": 0, "t_out": 7}], "words": [W("اهلا", 0.0, 0.4, 0)], "duration": 7, "removed": {"pauses": 2, "fillers": [1]}})
        J("timeline.json", {"scenes": [{"block": "hook_two_tone", "values": {"line1": "x"}}]})
        out = ed.build(d, cfg.RULES, 40, 90)
        self.assertEqual([a["chosen"] for a in out["alternative_stories"]], [True, False])
        self.assertTrue(out["hooks"][0]["found"]); self.assertEqual(out["main_message"], "start a store with no capital")
        self.assertTrue(os.path.exists(os.path.join(d, "editorial.json")))
        self.assertTrue(any("length" in f for f in out["confidence_flags"]))       # 7 s is far below the 40 s target
        self.assertTrue(ed.summary_lines(out))

    def test_nothing_to_build_without_a_chosen_story(self):
        self.assertIsNone(ed.build(tempfile.mkdtemp()))


if __name__ == "__main__":
    unittest.main()
