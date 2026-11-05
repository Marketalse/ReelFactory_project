import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
from lib import states, themes, hfbuild, layouts  # noqa: E402

REG = hfbuild.REGISTRY["blocks"]
WORDS = [{"text": t, "start": 0.3 + i * 0.42, "end": 0.62 + i * 0.42} for i, t in enumerate("انا اشتغل كلش حتى اصعب شغلة بالتسويق وبنيت فريق كامل من 300 شخص وكل يوم اتعلم شي جديد بالسوق".split())]
CARDS = [dict(id="c1", block="hook_two_tone", t_in=0.3, t_out=3.3, values={"line1": "أ", "line2": "ب"}),
         dict(id="c2", block="text_card", t_in=3.4, t_out=5.9, values={"kicker": "", "headline": "ت", "sub": ""}),
         dict(id="c3", block="info_card", t_in=9.0, t_out=11.6, values={"kicker": "", "headline": "ث", "caption": ""})]
SEQ = [n for n in themes.names() if themes.load(n).get("sequence")]


class States(unittest.TestCase):
    def test_every_state_and_sequence_is_valid_and_inside_the_safe_zone(self):
        self.assertTrue({"q_anim_frame", "full_anim", "text_full_clip", "half_anim_half_clip", "half_anim_hero", "headline_hero", "media_hero", "media_hero_text"} <= set(states.names()))
        for n in states.names(): self.assertEqual(states.problems(states.load(n)), [], n)
        self.assertEqual(len(SEQ), 4)
        for n in SEQ: self.assertEqual(states.sequence_problems(themes.load(n)), [], n)

    def test_a_state_that_leaves_the_safe_zone_is_caught(self):
        bad = dict(states.load("half_anim_hero"), anim=[0, 100, 1080, 800])
        self.assertTrue(states.problems(bad))
        bad2 = dict(states.load("full_anim"), caption={"y": 1450, "h": 120, "size": 70})
        self.assertTrue(states.problems(bad2))

    def test_cards_take_the_next_animated_state_and_gaps_the_rest_state(self):
        th = themes.load("seq_quarter_full")
        pl = states.plan(th, CARDS, WORDS, [2, 4], 12.0, REG)
        self.assertEqual([s["state"] for s in pl["segments"]], ["q_anim_frame", "full_anim", "text_full_clip", "q_anim_frame"])
        segs = pl["segments"]
        self.assertEqual(segs[0]["t_in"], 0.0); self.assertEqual(segs[-1]["t_out"], 12.0)
        self.assertTrue(all(abs(a["t_out"] - b["t_in"]) < 1e-6 for a, b in zip(segs, segs[1:])))
        self.assertFalse(pl["needs_hero"])
        th3 = themes.load("seq_hero_headline")
        p3 = states.plan(th3, CARDS, WORDS, [2, 4], 12.0, REG)
        self.assertTrue(p3["needs_hero"]); self.assertIn("headline_hero", [s["state"] for s in p3["segments"]])

    def test_cards_are_fitted_into_their_own_zone_and_text_comes_only_from_his_words(self):
        pl = states.plan(themes.load("seq_half_clip"), CARDS, WORDS, [2, 4, 8, 12], 12.0, REG)
        said = {w["text"] for w in WORDS}
        for s in pl["scenes"]:
            self.assertIn("zone", s); self.assertIn("fit", s)
            if s["block"] == "line_text":
                v = s["values"]; spoken = " ".join(v[k] for k in ("headline", "line1", "line2") if v[k]).split()
                self.assertTrue(set(spoken) <= said, spoken)
                if v["number"]: self.assertEqual(v["number"], "300")
        self.assertTrue(any(s["block"] == "line_text" for s in pl["scenes"]))
        self.assertTrue(all(s["t_in"] < s["t_out"] for s in pl["scenes"]))

    def test_frames_are_merged_per_run_and_full_clip_has_none(self):
        pl = states.plan(themes.load("seq_half_clip"), CARDS, WORDS, [2], 12.0, REG)
        self.assertEqual([f["t_in"] for f in pl["frames"]], [0.0, 9.0])                    # first run (two animated beats), then after the full-clip text beat
        self.assertTrue(all("stage_frame" == f["block"] for f in pl["frames"]))

    def test_split_cuts_keep_all_footage_and_give_each_piece_its_state_transform(self):
        pl = states.plan(themes.load("seq_quarter_full"), CARDS, WORDS, [2], 12.0, REG)
        tfs = states.transforms(pl["segments"], {"top": 420.0, "head_w": 510.0, "head_cx": 432.0})
        cuts = [dict(id="f0", src_in=0.0, t_in=0.0, t_out=7.0), dict(id="f1", src_in=20.0, t_in=7.0, t_out=12.0)]
        out = states.split_cuts(cuts, pl["segments"], tfs)
        self.assertAlmostEqual(sum(c["t_out"] - c["t_in"] for c in out), 12.0, places=2)
        self.assertTrue(all(c["t_out"] - c["t_in"] >= 0.3 - 1e-6 for c in out))
        self.assertTrue(all(abs(a["t_out"] - b["t_in"]) < 1e-6 for a, b in zip(out, out[1:])))
        for c in out:                                                                       # source time follows reel time inside each original cut
            base = cuts[0] if c["t_in"] < 7.0 else cuts[1]
            self.assertAlmostEqual(c["src_in"], base["src_in"] + c["t_in"] - base["t_in"], places=2)
        self.assertEqual(out[2]["scale"], 1.0)                                              # the full-clip beat is untouched
        self.assertNotEqual(out[0]["scale"], 1.0)

    def test_a_short_state_never_makes_a_footage_piece_under_0_3_s(self):
        cards = [dict(id="c1", block="text_card", t_in=1.0, t_out=2.4, values={"kicker": "", "headline": "ت", "sub": ""}),
                 dict(id="c2", block="text_card", t_in=2.5, t_out=4.2, values={"kicker": "", "headline": "ت", "sub": ""})]
        pl = states.plan(themes.load("seq_half_clip"), cards, WORDS, [], 6.0, REG)
        out = states.split_cuts([dict(id="f0", src_in=0, t_in=0.0, t_out=6.0)], pl["segments"], states.transforms(pl["segments"], {"top": 400.0, "head_w": 500.0, "head_cx": 540.0}))
        self.assertTrue(all(c["t_out"] - c["t_in"] >= 0.3 - 1e-6 for c in out))

    def test_hero_and_caption_tweens_cover_every_beat(self):
        pl = states.plan(themes.load("seq_hero_headline"), CARDS, WORDS, [2], 12.0, REG)
        self.assertEqual(sum("#hero-clip" in t for t in pl["tweens"]), len(pl["segments"]))
        self.assertEqual(sum('"#caps"' in t for t in pl["tweens"]), len(pl["segments"]))

    def test_media_hero_style_has_a_big_media_zone_on_top_and_the_hero_below(self):
        a = states.load("media_hero")
        self.assertGreaterEqual(a["anim"][3] - a["anim"][1], 650)                 # the upper section is big
        self.assertTrue(a["clip"]["hero"] and a["clip"]["rect"][1] > a["anim"][3])  # the hero box starts below it
        pl = states.plan(themes.load("seq_media_hero"), CARDS + [dict(id="c4", block="motion_card", t_in=6.0, t_out=8.5, values={"motion": "x.json", "label": ""})], WORDS, [2], 12.0, REG)
        self.assertTrue(pl["needs_hero"])
        self.assertTrue(all(s["spec"]["clip"]["hero"] for s in pl["segments"]))

    def test_styles_menu_lists_every_theme_with_a_picture_in_a_fixed_order(self):
        from lib import theme_preview
        menu = theme_preview.themes_menu()
        self.assertEqual({m["name"] for m in menu}, set(themes.names()))
        self.assertEqual(menu[0]["name"], "stage_dark")
        for m in menu:
            self.assertTrue(m["svg"].startswith("<svg") and m["label"], m["name"])

    def test_the_sequence_themes_show_up_in_the_dashboard_list(self):
        self.assertTrue(set(SEQ) <= set(themes.names()))


if __name__ == "__main__":
    unittest.main()
