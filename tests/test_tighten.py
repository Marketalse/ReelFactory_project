import json, os, sys, tempfile, types, unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from lib import tighten as tg, edl as edlmod, manual_edit as me  # noqa: E402
import reel  # noqa: E402

TEXT = ["اهلا بكم اليوم", "راح احچي عن المتجر", "اممم يعني خلني اشرح", "المتجر يحتاج رد سريع", "المتجر يحتاج رد سريع جدا", "هذا اهم شي",
        "قصة عن جاري في الحي", "والنتيجة ثلاثة اضعاف", "شكرا لكم متابعتي"]


def make_words():
    words, t, lines = [], 0.0, []
    for li, line in enumerate(TEXT):
        a = len(words)
        for tok in line.split():
            words.append({"text": tok, "start": round(t, 2), "end": round(t + 0.4, 2)}); t += 0.45
        lines.append((a, len(words) - 1)); t += 0.6
    return words, lines


def make_job():
    d = tempfile.mkdtemp(); words, lines = make_words()
    json.dump(words, open(os.path.join(d, "transcript.json"), "w"), ensure_ascii=False)
    json.dump({"main_message": "fast replies sell", "audience": "store owners", "selects": [{"id": "A", "range": [0, words[-1]["end"]], "label": "x"}]}, open(os.path.join(d, "selects.json"), "w"))
    json.dump({"id": "A", "range": [0.0, words[-1]["end"]], "label": "x"}, open(os.path.join(d, "chosen_select.json"), "w"))
    return d, words, lines


class DecideTests(unittest.TestCase):
    def units(self):
        from lib import content_intel
        d, words, lines = make_job()
        ci = content_intel.build(d)
        return d, words, ci, tg.units(ci, 0.0, words[-1]["end"])

    def test_units_are_whole_lines(self):
        d, words, ci, us = self.units()
        self.assertEqual(len(us), len(TEXT)); self.assertEqual(us[0]["text"], TEXT[0])

    def test_valid_cuts_are_kept_and_unsafe_ones_are_ignored(self):
        d, words, ci, us = self.units()
        dec = tg.decide({"start": 0, "end": 8, "drops": [{"id": 2, "why": "false start"}, {"id": 3, "why": "said twice"}, {"id": 0, "why": "hook!"}, {"id": 99, "why": "x"}, {"id": 2, "why": "again"}],
                         "summary": "tighter"}, us, 5)
        self.assertEqual([d["id"] for d in dec["drops"]], [2, 3])                    # the hook (first line), an unknown line and a repeat are ignored
        self.assertEqual(dec["start_id"], 0)

    def test_it_never_removes_more_than_45_percent_or_goes_below_the_target(self):
        d, words, ci, us = self.units()
        dec = tg.decide({"drops": [{"id": i, "why": "x"} for i in range(1, 9)]}, us, 5)
        total = sum(u["t1"] - u["t0"] for u in us)
        self.assertLessEqual(dec["removed_s"], 0.45 * total + 1e-6); self.assertTrue(dec["notes"])
        dec2 = tg.decide({"drops": [{"id": i, "why": "x"} for i in range(1, 9)]}, us, 60)       # a 60 s target: nothing can be cut from a ~25 s story
        self.assertEqual(dec2["drops"], [])

    def test_garbage_answers_cut_nothing(self):
        d, words, ci, us = self.units()
        for bad in (None, "junk", [], {"drops": "all"}, {"start": 5, "end": 2, "drops": [{"id": "x"}]}):
            dec = tg.decide(bad, us, 5)
            self.assertEqual(dec["drops"], []); self.assertEqual((dec["start_id"], dec["end_id"]), (us[0]["id"], us[-1]["id"]))

    def test_apply_gives_word_numbers_of_whole_lines(self):
        d, words, ci, us = self.units()
        rng, rows = tg.apply(us, tg.decide({"start": 1, "end": 7, "drops": [{"id": 2, "why": "false start"}]}, us, 5))
        self.assertEqual(rows[0]["text"], TEXT[2]); self.assertEqual(rng[0], us[1]["t0"]); self.assertEqual(rng[1], us[7]["t1"])
        self.assertEqual((rows[0]["i1"] - rows[0]["i0"] + 1), len(TEXT[2].split()))


class StageTests(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(reel, "LEN_MIN", 5); p.start(); self.addCleanup(p.stop)
        q = mock.patch.object(reel, "LEN_MAX", 90); q.start(); self.addCleanup(q.stop)

    def ctx(self, job):
        return reel.Ctx(job, types.SimpleNamespace(effort="low", budget=5, img_tok=800, replan=False))

    def test_the_stage_cuts_lines_moves_the_range_and_the_edl_obeys(self):
        d, words, lines = make_job(); c = self.ctx(d)
        ans = {"start": 0, "end": 7, "drops": [{"id": 2, "why": "false start"}, {"id": 3, "why": "said twice, keep the better take"}], "summary": "tighter"}
        with mock.patch.object(c, "llm", return_value=json.dumps(ans)):
            msg = reel.st_tighten(c)
        self.assertIn("AI cut 2 line(s)", msg)
        ch = json.load(open(os.path.join(d, "chosen_select.json")))
        self.assertTrue(ch["tightened"]); self.assertEqual(ch["range_before"], [0.0, words[-1]["end"]]); self.assertLess(ch["range"][1], words[-1]["end"])
        reel.st_edl(c)
        e = json.load(open(os.path.join(d, "edl.json")))
        spoken = " ".join(w["text"] for w in e["words"])
        self.assertNotIn("اممم", spoken); self.assertEqual(spoken.count("المتجر يحتاج"), 1)       # line 3 is gone, the better take (line 4) stays
        self.assertIn("اهلا بكم اليوم", spoken); self.assertNotIn("شكرا", spoken)                  # the hook stays, the outro after line 7 is gone
        self.assertEqual(reel.st_tighten(c), "cached")

    def test_manual_restore_beats_the_ai_cut_and_the_edit_page_shows_the_reason(self):
        d, words, lines = make_job(); c = self.ctx(d)
        with mock.patch.object(c, "llm", return_value=json.dumps({"drops": [{"id": 6, "why": "side story"}]})):
            reel.st_tighten(c)
        json.dump({"id": "A", "range": json.load(open(os.path.join(d, "chosen_select.json")))["range"]}, open(os.path.join(d, "chosen_select.json"), "w"))
        i0, i1 = lines[6]
        reel.st_edl(c)
        self.assertNotIn("جاري", " ".join(w["text"] for w in json.load(open(os.path.join(d, "edl.json")))["words"]))
        st = me.state(d, {"drop": [], "keep": [], "texts": {}, "hook": {}, "moments": [], "punch_ins": [], "keyword_src": []})
        why = {w["i"]: w["why"] for w in st["words"]}
        self.assertTrue(why[i0].startswith("AI cut: side story"))
        st2 = me.state(d, {"drop": [], "keep": list(range(i0, i1 + 1)), "texts": {}, "hook": {}, "moments": [], "punch_ins": [], "keyword_src": []})
        self.assertTrue(all(w["kept"] for w in st2["words"] if i0 <= w["i"] <= i1))              # he restored the lines: they are back

    def test_a_bad_answer_or_an_old_reel_leaves_the_cut_alone(self):
        d, words, lines = make_job(); c = self.ctx(d)
        with mock.patch.object(c, "llm", return_value="not json"):
            self.assertIn("skipped", reel.st_tighten(c))
        self.assertEqual(json.load(open(os.path.join(d, "tighten.json")))["drops"], [])
        d2, _, _ = make_job(); json.dump({"words": [], "segments": []}, open(os.path.join(d2, "edl.json"), "w"))
        c2 = self.ctx(d2)
        with mock.patch.object(c2, "llm", side_effect=AssertionError("no call expected")):
            self.assertIn("already cut", reel.st_tighten(c2))
        c3 = self.ctx(make_job()[0])
        with mock.patch.object(c3, "llm", side_effect=reel.Stop("BUDGET GUARD: x")):
            with self.assertRaises(reel.Stop):
                reel.st_tighten(c3)


if __name__ == "__main__":
    unittest.main()
