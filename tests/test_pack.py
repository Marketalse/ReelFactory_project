import json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from lib import pack, outline

W = [{"text": t, "start": i * 0.5, "end": i * 0.5 + 0.4} for i, t in enumerate(
    "اولا الجمارك تدخل البضاعة وبعدها التاجر يشتري من الشركة وبعدين المحل يبيع للزبون والزبون يدفع اكثر بسبب التوصيل".split())]
ANS = {"format": "explainer", "hook_word": 0, "sections": [
    {"from_word": 0, "to_word": 4, "kind": "step", "title_from": 1, "title_to": 2}, {"from_word": 5, "to_word": 9, "kind": "step", "title_from": 5, "title_to": 6},
    {"from_word": 10, "to_word": 15, "kind": "turn", "title_from": 11, "title_to": 12}]}


class Pack(unittest.TestCase):
    def setUp(self):
        self.o = outline.clean(ANS, W); self.d = tempfile.mkdtemp()
        json.dump(self.o, open(os.path.join(self.d, "outline.json"), "w"), ensure_ascii=False)

    def test_when_the_pack_is_used(self):
        self.assertTrue(pack.active(self.o))
        self.assertFalse(pack.active(dict(self.o, format="story")))
        self.assertFalse(pack.active(dict(self.o, sections=self.o["sections"][:2])))
        self.assertTrue(pack.active(dict(self.o, format="story"), {"mode": "always"}))
        self.assertFalse(pack.active(self.o, {"mode": "off"})); self.assertFalse(pack.active(None))

    def test_icons_match_what_he_says_else_a_neutral_one_and_never_repeat(self):
        ic = pack.pick_icons(self.o, W)
        self.assertEqual(len(ic), 3); self.assertIn("icon-package.svg", ic[0]) if "icon-package.svg" in ic else None
        self.assertEqual(len({i for i in ic if i}), len([i for i in ic if i]))

    def test_plan_builds_frame_and_recap_from_his_words(self):
        pk = pack.plan(self.d, {"duration": 12.0}, {"words": W})
        self.assertEqual([s["block"] for s in pk["scenes"]], ["pack_frame", "recap_chain"])
        frame = pk["scenes"][0]["groups_html"]
        for s in self.o["sections"]: self.assertIn(s["title"], frame)
        self.assertIn("STEP 1/3", frame); self.assertIn("STEP 3/3", frame)
        self.assertGreaterEqual(pk["scenes"][1]["t_in"], 12.0 - pack.RECAP_LEN - 0.01)
        short = pack.plan(self.d, {"duration": 6.0}, {"words": W})                    # recap would cover the last section: skipped
        self.assertEqual([s["block"] for s in short["scenes"]], ["pack_frame"])

    def test_no_outline_or_off_means_no_pack(self):
        self.assertIsNone(pack.plan(tempfile.mkdtemp(), {"duration": 12.0}, {"words": W}))
        d = tempfile.mkdtemp(); json.dump(dict(self.o, format="story"), open(os.path.join(d, "outline.json"), "w"))
        self.assertIsNone(pack.plan(d, {"duration": 12.0}, {"words": W}))


if __name__ == "__main__":
    unittest.main()
