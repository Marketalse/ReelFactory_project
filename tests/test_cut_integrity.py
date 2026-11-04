import copy, os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from lib import edl, integrity


def W(texts, gaps=None, dur=0.3):
    """Words one after another; gaps[k] = silence before word k (default 0.1 s)."""
    t, out = 0.5, []
    for k, tx in enumerate(texts):
        t += (gaps or {}).get(k, 0.1)
        out.append({"text": tx, "start": round(t, 3), "end": round(t + dur, 3)}); t += dur
    return out


class Pauses(unittest.TestCase):
    def test_a_long_pause_after_a_number_is_kept_short_and_a_mid_sentence_pause_is_cut(self):
        w = W(["عندي", "300", "طلب", "بالشهر", "وهاي", "مو", "مزحة"], gaps={2: 0.9, 5: 0.9})     # pause after "300" and a pause before "مو"
        e = edl.build(w, 0, 12)
        kept = [k["src_i"] for k in e["kept_pauses"]]
        self.assertEqual(kept, [2])                                                              # the one after the number (budget: one per 10 s)
        self.assertEqual(e["kept_pauses"][0]["kept_s"], 0.5)
        plain = edl.build(w, 0, 12, pause=0.35)
        self.assertGreater(e["duration"], plain["duration"] - 0.001)

    def test_a_pause_before_a_louder_word_is_kept(self):
        w = W(["هاي", "الفكرة", "الاهم"], gaps={2: 0.8})
        e = edl.build(w, 0, 5, emphasis={2})
        self.assertEqual([k["src_i"] for k in e["kept_pauses"]], [2])

    def test_dead_air_without_a_reason_is_still_removed_and_logged(self):
        w = W(["هاي", "الفكرة", "الاهم"], gaps={2: 0.8})
        e = edl.build(w, 0, 5)
        self.assertEqual(e["kept_pauses"], [])
        self.assertTrue([c for c in e["cut_log"] if c["kind"] == "pause"])

    def test_the_budget_stops_the_reel_from_dragging(self):
        w = W(["1", "a", "2", "b", "3", "c", "4", "d"], gaps={1: 0.9, 3: 0.9, 5: 0.9, 7: 0.9})
        self.assertEqual(len(edl.build(w, 0, 20)["kept_pauses"]), 2)                            # 20 s -> 2 allowed, not 4


class CutLog(unittest.TestCase):
    def test_every_removal_has_words_time_reel_position_and_a_reason(self):
        w = W(["يعني", "هاي", "الفكرة", "اممم", "الاهم", "كلشي", "شي", "غلط", "وبس"], gaps={2: 0.1})
        e = edl.build(w, 0, 9, ai_drop={7}, reasons={7: "a side story"}, drop={6})
        kinds = {c["kind"]: c for c in e["cut_log"]}
        self.assertIn("filler", kinds); self.assertEqual(kinds["filler"]["words"], ["اممم"])
        self.assertEqual(kinds["ai"]["why"], "a side story"); self.assertEqual(kinds["manual"]["words"], ["شي"])
        for c in e["cut_log"]:
            self.assertTrue(c["why"]); self.assertIn("reel_t", c); self.assertLess(c["src_from"], c["src_to"] + 1e-9)


class Meaning(unittest.TestCase):
    def setUp(self):
        self.w = W(["هاي", "الفكرة", "الاهم", "عندي", "300", "طلب"], gaps={3: 0.9})
        self.e = edl.build(self.w, 0, 8)

    def test_a_normal_cut_passes(self):
        r = integrity.check(self.e, self.w)
        self.assertTrue(r["ok"], r)

    def test_reordering_repeating_and_rewording_are_hard_errors(self):
        e = copy.deepcopy(self.e); e["words"][1], e["words"][2] = e["words"][2], e["words"][1]
        self.assertFalse(integrity.check(e, self.w)["ok"])
        e = copy.deepcopy(self.e); e["words"].append(dict(e["words"][0]))
        self.assertTrue(any("twice" in x for x in integrity.check(e, self.w)["errors"]))
        e = copy.deepcopy(self.e); e["words"][0]["text"] = "كلام ثاني"
        self.assertTrue(any("differs" in x for x in integrity.check(e, self.w)["errors"]))
        self.assertTrue(integrity.check(e, self.w, texts={e["words"][0]["src_i"]: "كلام ثاني"})["ok"])      # allowed when he changed the spelling by hand

    def test_a_gap_or_overlap_between_pieces_is_an_error(self):
        e = copy.deepcopy(self.e)
        if len(e["segments"]) > 1:
            e["segments"][1]["t_in"] += 0.5
            self.assertFalse(integrity.check(e, self.w)["ok"])

    def test_a_clipped_word_is_a_warning(self):
        e = copy.deepcopy(self.e); e["segments"][0]["src_out"] = self.w[0]["start"] + 0.1
        r = integrity.check(e, self.w)
        self.assertTrue(any("cut short" in x for x in r["warnings"]), r)

    def test_a_removed_filler_that_is_still_audible_is_found(self):
        tight = W(["هاي", "اممم", "الفكرة"], gaps={1: 0.02, 2: 0.02}, dur=0.15)               # filler squeezed between two words: the safe padding brings a bit of it back
        r = integrity.check(edl.build(tight, 0, 3), tight)
        self.assertEqual(r["stats"]["removed_words_still_audible"], 1)
        self.assertTrue(any("still heard" in x for x in r["warnings"]))
        roomy = W(["هاي", "اممم", "الفكرة"], gaps={1: 0.1, 2: 0.1}, dur=0.15)                  # a normal gap: nothing leaks
        self.assertEqual(integrity.check(edl.build(roomy, 0, 3), roomy)["stats"]["removed_words_still_audible"], 0)


if __name__ == "__main__":
    unittest.main()
