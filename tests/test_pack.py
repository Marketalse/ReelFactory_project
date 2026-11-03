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


class Highlights(unittest.TestCase):
    def test_up_to_two_words_per_section_from_inside_the_title(self):
        o = outline.clean(ANS, W)
        hl = pack.highlight_idx(o, W)
        for s in o["sections"]:
            mine = [i for i in hl if s["title_from"] <= i <= s["title_to"]]
            self.assertTrue(1 <= len(mine) <= 2)
        self.assertEqual(pack.highlight_idx(o, W, keyword_ids=[1]) & {1}, {1})          # a director keyword inside a title wins
        self.assertIn("--kw-bg", pack.pill_style("violet"))

    def test_pill_markup_and_no_caption_gaps_in_pack_mode(self):
        from lib import hfbuild
        g = hfbuild.caption_groups(W[:3], [], "c", pill_idx=[1], pill_style="--kw-bg:red")
        self.assertEqual(g.count("c-kwp"), 1); self.assertIn("--kw-bg:red", g)
        self.assertEqual(hfbuild.caption_groups(W[:3], [], "c").count("c-kwp"), 0)
