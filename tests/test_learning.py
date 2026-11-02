import json, os, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from lib import learning as L  # noqa: E402


def reel(watch, length, moments, zooms, hook=30, score=70):
    return {"facts": {"length_s": length, "moments": moments, "zooms": zooms, "hook_chars": hook, "ready_score": score},
            "entries": [{"when": "7d", "watch_pct": watch}]}


class LearningTests(unittest.TestCase):
    def setUp(self):
        os.environ["RF_LEARNED"] = os.path.join(tempfile.mkdtemp(), "l.json")

    def test_too_few_reels_means_no_lessons(self):
        r = L.analyze([reel(50, 60, 3, 5)] * 4)
        self.assertEqual(r["lessons"], []); self.assertIn("needs 10", r["note"]); self.assertEqual(L.hint(), "")

    def test_clear_pattern_becomes_a_careful_lesson(self):
        good = [reel(70 + i, 45, 2 + i % 2, 6) for i in range(6)]          # shorter reels, fewer cards: watched more
        weak = [reel(30 + i, 80, 9 + i % 2, 6) for i in range(6)]
        r = L.update(good + weak)
        text = " ".join(r["lessons"])
        self.assertTrue(r["lessons"] and len(r["lessons"]) <= 3)
        self.assertIn("lower cards and graphics per minute", text); self.assertIn("a pattern, not proof", text)
        h = L.hint()
        self.assertIn("his comments always win", h)
        d = json.load(open(L.path())); d["enabled"] = False; json.dump(d, open(L.path(), "w"))
        self.assertEqual(L.hint(), "")                                      # he can switch it off

    def test_no_difference_no_lesson_and_missing_results_are_skipped(self):
        same = [reel(50 + (i % 3), 60, 4, 5) for i in range(12)]
        self.assertEqual(L.analyze(same)["lessons"], [])
        noresult = [{"facts": {"length_s": 50}, "entries": []}] * 12
        self.assertEqual(L.analyze(noresult)["n"], 0)


if __name__ == "__main__":
    unittest.main()
