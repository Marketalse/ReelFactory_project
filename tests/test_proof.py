import json, os, sys, tempfile, types, unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from lib import transcript as tr  # noqa: E402
import reel  # noqa: E402


def words():
    toks = "اهلا بكم اليوم نحچي عن الكستمر سيرفس وكيف نرد على الزبايين بسرعه".split()
    return [{"text": t, "start": round(i * 0.45, 2), "end": round(i * 0.45 + 0.4, 2)} for i, t in enumerate(toks)]


class PieceTests(unittest.TestCase):
    def test_chunks_mark_doubtful_words_and_split(self):
        w = words() * 40
        ch = tr.proof_chunks(w, {5})
        self.assertIn("(5)الكستمر?", ch[0]); self.assertNotIn("(4)عن?", ch[0]); self.assertGreater(len(ch), 1)
        self.assertTrue(all(len(c.split()) < 400 for c in ch))

    def test_only_one_to_one_single_word_fixes_are_applied(self):
        w = words()
        done = tr.apply_proof(w, [{"i": 5, "text": "customer", "why": "english term"}, {"i": 6, "text": "two words", "why": "x"}, {"i": 99, "text": "x"}, {"i": 7, "text": ""},
                                  {"i": 11, "text": "الزبائن"}, "junk", {"i": 5, "text": "customer"}])
        self.assertEqual([d["i"] for d in done], [5, 11] if False else [5, 11]); self.assertEqual(w[5]["text"], "customer")
        self.assertEqual(w[6]["text"], "سيرفس"); self.assertEqual(len(w), 12)


class StageTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); json.dump(words(), open(os.path.join(self.d, "transcript_asr.json"), "w"), ensure_ascii=False)
        self.c = reel.Ctx(self.d, types.SimpleNamespace(effort="low", budget=5, img_tok=800))

    def run_fix(self, proof_answer):
        calls = []
        def fake(stage, model, content, mt, effort="low", **k):
            calls.append(stage)
            if stage == "fix":
                return json.dumps({"fixes": [{"i": 6, "text": "service"}], "notes": ""})
            if isinstance(proof_answer, Exception):
                raise proof_answer
            return proof_answer
        with mock.patch.object(self.c, "llm", side_effect=fake):
            return reel.st_fix(self.c), calls

    def test_the_second_pass_fixes_in_context_and_is_recorded(self):
        msg, calls = self.run_fix(json.dumps({"fixes": [{"i": 5, "text": "customer", "why": "english term"}, {"i": 11, "text": "الزبائن", "why": "dialect spelling"}]}))
        self.assertEqual(calls, ["fix", "proof"]); self.assertIn("2 more by the proofreader", msg)
        w = json.load(open(os.path.join(self.d, "transcript.json")))
        self.assertEqual((w[5]["text"], w[6]["text"], w[11]["text"]), ("customer", "service", "الزبائن"))
        meta = json.load(open(os.path.join(self.d, "transcript_fix_meta.json")))
        self.assertEqual(len(meta["proof"]), 2); self.assertEqual(json.load(open(os.path.join(self.d, "transcript_asr.json")))[5]["text"], "الكستمر")   # the raw transcript is untouched

    def test_a_bad_proof_answer_never_stops_the_reel_but_the_money_guard_does(self):
        msg, calls = self.run_fix("not json")
        self.assertNotIn("proofreader", msg); self.assertEqual(json.load(open(os.path.join(self.d, "transcript.json")))[6]["text"], "service")
        d2 = tempfile.mkdtemp(); json.dump(words(), open(os.path.join(d2, "transcript_asr.json"), "w"), ensure_ascii=False)
        c2 = reel.Ctx(d2, types.SimpleNamespace(effort="low", budget=5, img_tok=800))
        def fake(stage, *a, **k):
            if stage == "fix": return json.dumps({"fixes": []})
            raise reel.Stop("BUDGET GUARD: x")
        with mock.patch.object(c2, "llm", side_effect=fake):
            with self.assertRaises(reel.Stop):
                reel.st_fix(c2)


if __name__ == "__main__":
    unittest.main()
