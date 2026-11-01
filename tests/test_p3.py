"""Offline checks for P3: transcript review (Gate 0), cutting (EDL), Director plan resolution, compile. No spend."""
import json, os, re, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from lib import transcript as tr, edl, director  # noqa: E402


def W(text, a, b):
    return {"text": text, "start": a, "end": b}


def talk(texts, t=0.0, step=0.4, pause_after=()):
    out = []
    for k, x in enumerate(texts):
        out.append(W(x, round(t, 3), round(t + 0.3, 3))); t += step
        if k in pause_after: t += 1.0
    return out


class TranscriptTests(unittest.TestCase):
    def test_words_invented_over_silence_are_dropped(self):
        words = [W("يعني", 0.0, 0.3), W("شكرا", 5.2, 5.5), W("لازم", 1.0, 1.3)]
        kept, dropped = tr.clean_asr(words, [(4.0, 8.0)], 8.0)
        self.assertEqual([w["text"] for w in kept], ["يعني", "لازم"])
        self.assertEqual(dropped[0]["text"], "شكرا")

    def test_gate0_review_roundtrip_keeps_timings(self):
        words = talk("يعني لما انت حاط بيج".split()) + talk("وما حاط رخنه تواصل".split(), t=3.0)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "r.txt")
            tr.write_review(p, words)
            self.assertFalse(tr.review_done(p))
            txt = open(p, encoding="utf-8").read().replace("STATUS: waiting", "STATUS: reviewed").replace("رخنه", "رقم")
            open(p, "w", encoding="utf-8").write(txt)
            self.assertTrue(tr.review_done(p))
            new, stats = tr.apply_review(p, words)
        self.assertEqual(stats["changed"], 1)
        self.assertEqual([w["start"] for w in new], [w["start"] for w in words])
        self.assertIn("رقم", [w["text"] for w in new])

    def test_gate0_added_word_shares_the_line_time(self):
        words = talk("لازم يكون عندك".split())
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "r.txt"); tr.write_review(p, words)
            txt = open(p, encoding="utf-8").read().replace("STATUS: waiting", "STATUS: reviewed").replace("عندك", "عندك customer service")
            open(p, "w", encoding="utf-8").write(txt)
            new, _ = tr.apply_review(p, words)
        self.assertEqual(len(new), 5)
        self.assertAlmostEqual(new[0]["start"], words[0]["start"])
        self.assertLessEqual(new[-1]["end"], words[-1]["end"] + 1e-6)

    def test_gate0_damaged_file_names_the_problem(self):
        words = talk("لازم يكون عندك".split())
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "r.txt"); tr.write_review(p, words)
            open(p, "a", encoding="utf-8").write("this line is broken\n")
            with self.assertRaisesRegex(ValueError, "can't read this line"):
                tr.apply_review(p, words)


class EdlTests(unittest.TestCase):
    def test_pauses_fillers_and_retakes_are_removed(self):
        words = talk("لازم يكون عندك اممم".split(), pause_after=(3,)) + talk("لازم يكون عندك خدمة زبائن".split(), t=3.0)
        e = edl.build(words, 0.0, 6.0)
        texts = [w["text"] for w in e["words"]]
        self.assertEqual(texts, "لازم يكون عندك خدمة زبائن".split())        # first take + filler gone
        self.assertLess(e["duration"], 6.0)
        for a, b in zip(e["words"], e["words"][1:]):
            self.assertLessEqual(a["end"], b["start"] + 1e-6)                 # re-timed in order
        for s in e["segments"]:
            self.assertAlmostEqual(s["t_out"] - s["t_in"], s["src_out"] - s["src_in"], places=3)

    def test_long_pause_becomes_a_cut(self):
        words = talk("واحد اثنين".split()) + talk("ثلاثة اربعة".split(), t=3.0)
        e = edl.build(words, 0.0, 4.0, retakes=False)
        self.assertEqual(len(e["segments"]), 2)
        self.assertEqual(e["removed"]["pauses"], 1)


def reel_words(n=110, step=0.42):
    base = "يعني لما انت حاط بيج و ما حاط رقم تواصل الزبون راح يخسر 300 طلب لان شغلك كله customer service".split()
    return [W(base[i % len(base)], round(i * step, 3), round(i * step + 0.32, 3)) for i in range(n)]


def good_plan(n):
    return {"hook": {"line1": "حاط بيج وما حاط رقم؟", "line2": "شنو تتصور؟"},
            "keyword_ids": [4, 12, 30],
            "moments": [{"block": "text_card", "at_word": 12, "duration": 2.2, "values": {"headline": "شغلك كله خدمة زبائن"}},
                        {"block": "split", "at_word": 30, "duration": 3.0, "values": {"value": "300", "label": "طلب تخسره"}},
                        {"block": "flash", "at_word": 52, "duration": 0.9, "values": {"word": "300"}},
                        {"block": "text_card", "at_word": 70, "duration": 2.0, "values": {"headline": "رد على الزبون"}}],
            "punch_ins": [{"at_word": w, "scale": 1.25} for w in range(6, n - 8, 6)],
            "cta": {"type": "follow", "line": "إذا عجبك المحتوى تابعني", "promise": "كل يوم شي جديد", "keyword": ""}}


class DirectorTests(unittest.TestCase):
    def setUp(self):
        self.words = reel_words()
        self.dur = self.words[-1]["end"] + 0.1
        self.segments = [{"src_in": 10, "src_out": 10 + self.dur, "t_in": 0, "t_out": self.dur}]

    def test_good_plan_resolves_and_keeps_rhythm(self):
        tl, err, warn = director.resolve(good_plan(len(self.words)), self.words, self.dur)
        self.assertEqual(err, [])
        cuts = director.face_cuts(tl, self.segments)
        self.assertEqual(director.check_rhythm(tl, cuts), [])
        self.assertEqual(tl["scenes"][0]["block"], "hook_two_tone"); self.assertEqual(tl["scenes"][0]["t_in"], 0.0)
        self.assertEqual(tl["scenes"][-1]["block"], "cta_card"); self.assertAlmostEqual(tl["scenes"][-1]["t_out"], tl["duration"])
        self.assertTrue(any(f["y"] == 480 for f in cuts))                        # face moves down under the split
        for f in cuts:                                                          # face cuts tile the reel exactly
            self.assertGreater(f["t_out"], f["t_in"])
        self.assertAlmostEqual(cuts[0]["t_in"], 0.0); self.assertAlmostEqual(cuts[-1]["t_out"], tl["duration"])

    def test_invented_number_and_bad_word_are_named(self):
        p = good_plan(len(self.words))
        p["moments"][1]["values"]["value"] = "500"
        p["moments"][0]["at_word"] = 9999
        _, err, _ = director.resolve(p, self.words, self.dur)
        self.assertTrue(any("'500' is not a number he said" in e for e in err), err)
        self.assertTrue(any("at_word 9999" in e for e in err), err)

    def test_too_many_flashes_and_cta_overlap(self):
        p = good_plan(len(self.words))
        p["moments"] += [{"block": "flash", "at_word": 40, "duration": 0.8, "values": {"word": "300"}},
                         {"block": "flash", "at_word": 62, "duration": 0.8, "values": {"word": "300"}},
                         {"block": "text_card", "at_word": len(self.words) - 2, "duration": 2.0, "values": {"headline": "x"}}]
        _, err, _ = director.resolve(p, self.words, self.dur)
        self.assertTrue(any("flashes; maximum" in e for e in err), err)
        self.assertTrue(any("inside the CTA" in e for e in err), err)

    def test_missing_rhythm_is_reported_with_times(self):
        p = good_plan(len(self.words)); p["punch_ins"] = []
        tl, err, _ = director.resolve(p, self.words, self.dur)
        self.assertEqual(err, [])
        msg = director.check_rhythm(tl, director.face_cuts(tl, self.segments))
        self.assertTrue(msg and "nothing changes on screen from" in msg[0], msg)

    def test_logo_must_exist(self):
        p = good_plan(len(self.words))
        p["moments"].append({"block": "logo_card", "at_word": 85, "duration": 2.0, "values": {"logo_a": "meta.svg", "name_a": "Meta"}})
        _, err, _ = director.resolve(p, self.words, self.dur, logos=["shopify.png"])
        self.assertTrue(any("'meta.svg' is not in the reel's assets/" in e for e in err), err)

    def test_prompt_lists_blocks_numbers_and_word_numbers(self):
        txt = director.build_prompt(self.words, self.dur, brief="Topic: store", logos=["a.svg"])
        for s in ("text_card", "split", "flash", "logo_card", "(4)بيج", "300", "a.svg", "Topic: store"):
            self.assertIn(s, txt)


class CompileTests(unittest.TestCase):
    def test_final_refuses_without_a_real_handle(self):
        import compile as comp
        from lib import config as cfg
        from lib.hfbuild import BuildError
        old = cfg.BRAND.get("handles")
        try:
            cfg.BRAND["handles"] = {"instagram": "CONFIRM (proposed)"}
            self.assertEqual(comp.handle_for("instagram", final=False), "@your_handle")
            with self.assertRaisesRegex(BuildError, "No instagram handle"):
                comp.handle_for("instagram", final=True)
            cfg.BRAND["handles"] = {"instagram": "@real"}
            self.assertEqual(comp.handle_for("instagram", final=True), "@real")
        finally:
            cfg.BRAND["handles"] = old


class WordFixTests(unittest.TestCase):
    def test_comment_word_fixes_change_transcript_and_cut(self):
        import json, tempfile, reel
        with tempfile.TemporaryDirectory() as d:
            words = [W(t, i, i + 0.8) for i, t in enumerate("حاط رخنه تواصل kastomer سيرفس".split())]
            json.dump(words, open(os.path.join(d, "transcript.json"), "w"))
            json.dump({"words": [dict(w, src_i=i) for i, w in enumerate(words)]}, open(os.path.join(d, "edl.json"), "w"))
            n = reel.apply_word_fixes(d, "make the hook shorter\nرخنه => رقم\nkastomer سيرفس -> customer service")
            t = [w["text"] for w in json.load(open(os.path.join(d, "transcript.json")))]
            e = [w["text"] for w in json.load(open(os.path.join(d, "edl.json")))["words"]]
        self.assertEqual(t, "حاط رقم تواصل customer service".split())
        self.assertEqual(e, t)
        self.assertEqual(n, 3)


if __name__ == "__main__":
    unittest.main()
