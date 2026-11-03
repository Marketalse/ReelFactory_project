import json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import reel
from lib import outline, director

W = [{"text": t, "start": i * 0.5, "end": i * 0.5 + 0.4} for i, t in enumerate(
    "اولا الجمارك تدخل البضاعة وبعدها التاجر يشتري بسعر اقل وبعدين الزبون يدفع اكثر وهذا اسمه اثر الفراشة".split())]
GOOD = {"format": "explainer", "hook_word": 0, "concept": {"from_word": 14, "to_word": 16},
        "sections": [{"from_word": 0, "to_word": 4, "kind": "step", "title_from": 1, "title_to": 2},
                     {"from_word": 5, "to_word": 9, "kind": "step", "title_from": 5, "title_to": 6},
                     {"from_word": 10, "to_word": 16, "kind": "turn", "title_from": 10, "title_to": 11}]}


class Clean(unittest.TestCase):
    def test_titles_are_built_from_his_words(self):
        o = outline.clean(GOOD, W)
        self.assertEqual(o["sections"][0]["title"], "الجمارك تدخل"); self.assertEqual(o["recap"][1], "التاجر يشتري")
        self.assertEqual(o["concept"]["text"], " ".join(w["text"] for w in W[14:17]))
        self.assertIn("section 1", outline.brief_note(o))

    def test_bad_answers_are_dropped(self):
        bad = json.loads(json.dumps(GOOD))
        bad["sections"][1]["from_word"] = 3                                   # overlaps the first
        bad["sections"][2]["title_to"] = 16                                   # title too long (6 words)
        with self.assertRaises(ValueError): outline.clean(bad, W)
        with self.assertRaises(ValueError): outline.clean("x", W)
        self.assertEqual(outline.clean(dict(GOOD, format="weird"), W)["format"], "opinion")


class Step(unittest.TestCase):
    def ctx(self, answer):
        d = tempfile.mkdtemp(); json.dump({"words": W, "duration": 9.0}, open(os.path.join(d, "edl.json"), "w"))
        c = reel.Ctx.__new__(reel.Ctx); c.job = d
        c.a = type("A", (), {"replan": False, "effort": None})(); c.calls = []
        def llm(stage, model, content, mt, effort="low", **k):
            c.calls.append((stage, model, effort)); 
            if isinstance(answer, Exception): raise answer
            return json.dumps(answer)
        c.llm = llm; return c

    def test_step_writes_outline_with_the_outline_role(self):
        c = self.ctx(GOOD); msg = reel.st_outline(c)
        self.assertIn("3 sections", msg); self.assertEqual(c.calls[0][0], "outline"); self.assertEqual(c.calls[0][2], "high")
        self.assertEqual(reel.st_outline(c), "cached")

    def test_unusable_answer_never_stops_the_reel_but_the_money_guard_does(self):
        self.assertEqual(reel.st_outline(self.ctx({"format": "tips", "sections": []})), "skipped")
        self.assertEqual(reel.st_outline(self.ctx(reel.Stop("some other stop"))), "skipped")
        with self.assertRaises(reel.Stop): reel.st_outline(self.ctx(reel.Stop("BUDGET GUARD: x")))


if __name__ == "__main__":
    unittest.main()
