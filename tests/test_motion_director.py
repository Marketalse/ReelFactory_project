import json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from lib import director, hfbuild, icon_tags

GOOD = {"v": "5.5", "fr": 30, "ip": 0, "op": 30, "w": 100, "h": 100, "layers": [{"ty": 4, "ks": {}}]}


def words(texts):
    return [{"text": t, "start": 1.0 + i * 0.4, "end": 1.3 + i * 0.4} for i, t in enumerate(texts)]


class MotionDirector(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(); self.old_root = icon_tags.cfg.ROOT; icon_tags.cfg.ROOT = self.root
        self.m = os.path.join(self.root, "library", "assets", "motion"); os.makedirs(self.m)
        json.dump(GOOD, open(os.path.join(self.m, "shopping-bag.json"), "w"))
        json.dump(GOOD, open(os.path.join(self.m, "bell.json"), "w"))
        self.old_dir = hfbuild.MOTION_DIR; hfbuild.MOTION_DIR = self.m

    def tearDown(self):
        icon_tags.cfg.ROOT = self.old_root; hfbuild.MOTION_DIR = self.old_dir

    def tag(self):
        icon_tags.save({"shopping bag": ["طلب", "طلبات"], "bell": ["اشعار"]}, kind="motion")

    def plan(self, at_word):
        return {"hook": {"line1": "يعني لما انت", "line2": "حاط بيج"}, "moments": [{"block": "motion_card", "at_word": at_word, "duration": 2.0, "values": {"motion": "evil.json", "label": "invented"}}]}

    def test_motion_names_are_scanned_and_tagged_like_icons(self):
        self.assertEqual(sorted(icon_tags.pending(kind="motion")), ["bell", "shopping bag"])
        self.assertEqual(icon_tags.pending(kind="icons"), [])                    # icons are untouched
        self.assertFalse(icon_tags.motion_ready()); self.tag(); self.assertTrue(icon_tags.motion_ready())
        self.assertEqual(icon_tags.pending(kind="motion"), [])

    def test_director_is_offered_the_motion_card_only_after_tagging(self):
        self.assertNotIn("motion_card", director.offered_blocks())
        self.tag(); self.assertIn("motion_card", director.offered_blocks()); self.assertIn("motion_card:", director.catalogue())

    def test_the_file_and_label_come_from_his_words_not_from_the_ai(self):
        self.tag()
        w = words(["يعني", "لما", "انت", "حاط", "بيج", "وتبيع", "كل", "يوم", "طلبات", "كثيرة", "وهاي", "مزحة"] + ["كلمة"] * 12)
        tl, err, warn = director.resolve(self.plan(5), w, 12.0)
        self.assertEqual(err, [], err)
        sc = [s for s in tl["scenes"] if s["block"] == "motion_card"][0]
        self.assertEqual(sc["values"], {"motion": "shopping-bag.json", "label": "طلبات"})      # the AI's 'evil.json' / 'invented' were ignored

    def test_no_matching_word_means_the_moment_is_dropped_not_guessed(self):
        self.tag()
        w = words(["كلمة"] * 24)
        tl, err, warn = director.resolve(self.plan(5), w, 12.0)
        self.assertFalse([s for s in tl["scenes"] if s["block"] == "motion_card"]); self.assertTrue(any("no motion file" in x for x in warn))

    def test_a_card_that_runs_a_little_past_the_end_is_shortened_not_a_reason_to_stop_the_reel(self):
        w = words(["كلمة"] * 30)                                    # word 24 starts at 10.55 s; the reel ends at 13 s
        plan = {"hook": {"line1": "يعني لما انت", "line2": "حاط بيج"},
                "moments": [{"block": "info_card", "at_word": 24, "duration": 4.0, "values": {"kicker": "ك", "headline": "كلمة", "caption": "كلمة"}}]}
        tl, err, warn = director.resolve(plan, w, 13.0)
        self.assertEqual(err, [], err)
        sc = [s for s in tl["scenes"] if s["block"] == "info_card"][0]
        self.assertLessEqual(sc["t_out"], 13.0 + 0.01); self.assertTrue(any("shortened" in x for x in warn))
        plan["moments"][0]["at_word"] = 29                           # starts too close to the end for even the shortest card: it is DROPPED with a warning, the reel is not stopped
        tl2, err2, warn2 = director.resolve(plan, w, 13.0)
        self.assertEqual(err2, [], err2); self.assertFalse([s for s in tl2["scenes"] if s["block"] == "info_card"]); self.assertTrue(any("dropped" in x for x in warn2))


if __name__ == "__main__":
    unittest.main()
