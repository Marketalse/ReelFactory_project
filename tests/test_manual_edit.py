"""Edit page (manual editing): cut/restore words, fix spellings, move/add/remove cards and zooms. No AI, no spend."""
import json, os, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from lib import director, edl as edlmod, manual_edit as me  # noqa: E402

BASE = "يعني لما انت حاط بيج و ما حاط رقم تواصل الزبون راح يخسر 300 طلب لان شغلك كله customer service".split()


def make_job(d, n=110, step=0.42):
    """A small reel on disk exactly as the pipeline leaves it after a draft (no video needed)."""
    words = [{"text": BASE[i % len(BASE)], "start": round(i * step, 3), "end": round(i * step + 0.32, 3)} for i in range(n)]
    words[20]["text"] = "امم"                                                     # a filler the cut removes
    json.dump(words, open(os.path.join(d, "transcript.json"), "w"), ensure_ascii=False)
    s0, s1 = 0.0, words[-1]["end"]
    json.dump({"range": [s0, s1]}, open(os.path.join(d, "chosen_select.json"), "w"))
    e = edlmod.build(words, s0, s1)
    json.dump(e, open(os.path.join(d, "edl.json"), "w"), ensure_ascii=False)
    m = len(e["words"])
    plan = {"hook": {"line1": "حاط بيج وما حاط رقم؟", "line2": "شنو تتصور؟"}, "keyword_ids": [4, 12, 30],
            "moments": [{"block": "text_card", "at_word": 12, "duration": 2.2, "values": {"headline": "شغلك كله خدمة زبائن"}},
                        {"block": "split", "at_word": 30, "duration": 3.0, "values": {"value": "300", "label": "طلب تخسره"}},
                        {"block": "flash", "at_word": 52, "duration": 0.9, "values": {"word": "300"}}],
            "punch_ins": [{"at_word": w, "scale": 1.25} for w in range(6, m - 8, 6)], "cta": {}}
    tl, err, _ = director.resolve(plan, e["words"], e["duration"])
    assert not err, err
    tl["face_cy"] = 0.4
    json.dump(plan, open(os.path.join(d, "scene_plan.json"), "w"), ensure_ascii=False)
    json.dump(tl, open(os.path.join(d, "timeline.json"), "w"), ensure_ascii=False)
    return words, e


class ManualEditTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory(); self.d = self.t.name; self.addCleanup(self.t.cleanup)
        self.words, self.e = make_job(self.d)

    def test_unchanged_edit_gives_the_same_reel(self):
        ed = me.current(self.d)
        e, plan, tl, err, warn = me.compute(self.d, ed)
        self.assertEqual(err, []); self.assertAlmostEqual(e["duration"], self.e["duration"])
        old = json.load(open(os.path.join(self.d, "timeline.json")))
        self.assertEqual([(s["block"], s["t_in"]) for s in tl["scenes"]], [(s["block"], s["t_in"]) for s in old["scenes"]])

    def test_cutting_words_shortens_and_moves_a_card_off_a_cut_word(self):
        ed = me.current(self.d)
        card = ed["moments"][0]["at_src"]
        ed["drop"] = [card, card + 1, card + 2]
        e, plan, tl, err, _ = me.compute(self.d, ed)
        self.assertEqual(err, []); self.assertLess(e["duration"], self.e["duration"] - 0.9)
        self.assertNotIn(card, [w["src_i"] for w in e["words"]])
        self.assertEqual(e["words"][plan["moments"][0]["at_word"]]["src_i"], card + 3)          # next word still in the reel

    def test_restore_a_filler_and_fix_a_spelling(self):
        ed = me.current(self.d)
        self.assertNotIn(20, [w["src_i"] for w in self.e["words"]])
        ed["keep"] = [20]; ed["texts"] = {"3": "انتَ"}
        e, *_ = me.compute(self.d, ed)
        self.assertIn(20, [w["src_i"] for w in e["words"]])
        self.assertEqual(next(w["text"] for w in e["words"] if w["src_i"] == 3), "انتَ")

    def test_move_add_and_remove_cards_and_zooms(self):
        ed = me.current(self.d)
        ed["moments"][1]["at_src"] += 10                                                     # move
        ed["moments"].pop(2)                                                                 # remove the flash
        ed["moments"].append({"block": "text_card", "at_src": 90, "duration": 2.0, "values": {"headline": "رد على الزبون"}})
        ed["punch_ins"] = ed["punch_ins"][:3]
        e, plan, tl, err, _ = me.compute(self.d, ed)
        self.assertEqual(err, [])
        self.assertEqual([s["block"] for s in tl["scenes"] if s["block"] in me.EDITABLE], ["text_card", "split", "text_card"])
        self.assertEqual(len(tl["punch_ins"]), 3)

    def test_save_checks_rules_and_keeps_a_backup(self):
        ed = me.current(self.d)
        ed["moments"][0]["values"]["headline"] = "x" * 80                                    # too long for the card
        ok, msg, errs = me.save(self.d, ed)
        self.assertFalse(ok); self.assertTrue(errs); self.assertFalse(os.path.exists(os.path.join(self.d, "manual_edit.json")))
        ed["moments"][0]["values"]["headline"] = "خدمة زبائن"; ed["drop"] = [40]
        ok, msg, _ = me.save(self.d, ed)
        self.assertTrue(ok, msg)
        self.assertEqual(json.load(open(os.path.join(self.d, "manual_edit.json")))["drop"], [40])
        bk = os.listdir(os.path.join(self.d, "edits"))
        self.assertEqual(len(bk), 1); self.assertIn("timeline.json", os.listdir(os.path.join(self.d, "edits", bk[0])))
        self.assertEqual(json.load(open(os.path.join(self.d, "timeline.json")))["director"], "manual edit")
        st = me.state(self.d)                                                               # the page sees the saved cut
        self.assertFalse(next(w for w in st["words"] if w["i"] == 40)["kept"])
        self.assertEqual(next(w for w in st["words"] if w["i"] == 40)["why"], "you cut it")

    def test_state_lists_every_word_with_reel_times(self):
        st = me.state(self.d)
        self.assertEqual(len(st["words"]), len(self.words))
        k = [w for w in st["words"] if w["kept"]]
        self.assertTrue(all(a["t"] < b["t"] for a, b in zip(k, k[1:])))
        self.assertIn("text_card", st["blocks"]); self.assertEqual(st["errors"], [])


if __name__ == "__main__":
    unittest.main()


class RebuildTests(unittest.TestCase):
    def test_rebuild_runs_compile_draft_report_only_and_costs_nothing(self):
        import reel
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            make_job(d); json.dump({"status": "preview_ready"}, open(os.path.join(d, "job.json"), "w"))
            ran = []
            fake = {k: (lambda k: (lambda c: ran.append(k) or "ok"))(k) for k in reel.FUNCS}
            out = sys.stdout
            try:
                with mock.patch.dict(reel.FUNCS, fake), mock.patch.object(sys, "argv", ["reel.py", d, "--rebuild"]), \
                     mock.patch.object(reel, "notify", lambda *a, **k: None), mock.patch.object(reel.subprocess, "run"):
                    try:
                        reel.main()
                    except SystemExit:
                        pass
            finally:
                sys.stdout = out
            self.assertEqual(ran, ["compile", "draft", "report"])
            hist = json.load(open(os.path.join(d, "job.json")))["feedback_history"]
            self.assertEqual(hist[-1]["fix"], "(manual edit in the editor)")
            self.assertIn("+$0.0000  your manual edit", open(os.path.join(d, "run.log"), encoding="utf-8").read())
