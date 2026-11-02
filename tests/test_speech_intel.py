import array, json, math, os, sys, tempfile, unittest, wave

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from lib import speech_intel as si  # noqa: E402


def make_wav(path, secs, loud_spans, quiet=0.01, loud=0.4, sr=16000):
    a = array.array("h")
    for n in range(int(secs * sr)):
        t = n / sr
        amp = loud if any(x <= t < y for x, y in loud_spans) else quiet
        a.append(int(32767 * amp * math.sin(2 * math.pi * 220 * t)))
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(a.tobytes())


def W(text, s, e):
    return {"text": text, "start": s, "end": e}


class SpeechIntelTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.words = [W("اهلا", 0.0, 0.5), W("اممم", 0.6, 0.9), W("المتجر", 1.0, 1.6), W("المتجر", 1.65, 2.2),
                      W("يعني", 2.3, 2.6), W("بس", 2.7, 2.9),            # ends a phrase on a connector, then a long pause
                      W("رقم", 4.5, 5.0), W("خمسة", 5.05, 5.6), W("ي", 5.7, 5.75)]
        make_wav(os.path.join(self.d, "audio16k.wav"), 6.0, [(1.0, 1.6), (5.05, 5.6)])
        json.dump(self.words, open(os.path.join(self.d, "transcript_asr.json"), "w"), ensure_ascii=False)
        corrected = [dict(w) for w in self.words]; corrected[6]["text"] = "رقم"
        json.dump(corrected, open(os.path.join(self.d, "transcript.json"), "w"), ensure_ascii=False)
        json.dump({"changes": [{"i": 7, "from": "xx", "to": "خمسة"}]}, open(os.path.join(self.d, "transcript_fix_meta.json"), "w"))
        open(os.path.join(self.d, "loudness.txt"), "w").write("I: -20.0 LUFS\n")
        self.r = si.build(self.d, "ar", [{"spoken": "ستور", "write": "المتجر", "confirmed": True}])

    def test_writes_file_and_keeps_raw_transcript(self):
        self.assertTrue(os.path.exists(os.path.join(self.d, "speech_intel.json")))
        raw = json.load(open(os.path.join(self.d, "transcript_asr.json")))
        self.assertEqual(raw[6]["text"], "رقم"); self.assertEqual(self.r["transcript"]["raw_file"], "transcript_asr.json")

    def test_delivery_finds_filler_repeat_pause_and_unfinished(self):
        d = self.r["delivery"]
        self.assertEqual([f["i"] for f in d["fillers"]], [1])
        self.assertTrue(any(x["i"] == 3 for x in d["repeats"]))
        self.assertTrue(any(p["seconds"] >= 1.5 for p in d["pauses"]))
        self.assertTrue(d["unfinished_sentences"])

    def test_loud_words_are_emphasis(self):
        self.assertIn(2, [e["i"] for e in self.r["delivery"]["emphasis_words"]])

    def test_scores_are_separate_and_semantic_is_honest(self):
        s = self.r["scores"]
        for k in ("transcription_confidence", "timestamp_reliability", "audio_quality", "delivery_energy"):
            self.assertIsInstance(s[k]["value"], int); self.assertTrue(0 <= s[k]["value"] <= 100)
        self.assertIsNone(s["semantic_importance"]["value"])
        self.assertTrue(self.r["speakers"]["assumed"])

    def test_low_confidence_flags_changed_and_single_letter_words(self):
        low = {w["i"]: w for w in self.r["low_confidence_words"]}
        self.assertIn(8, low)                                   # single letter, quiet
        self.assertEqual(self.r["transcript"]["corrections"], 1)

    def test_language_detection(self):
        ar = si.languages([W("مرحبا", 0, 1)] * 9 + [W("ads", 1, 2)])
        self.assertEqual(ar["main"], "arabic + english mixed")
        ku = si.languages([W("ئەڤە", 0, 1)] * 3 + [W("مرحبا", 1, 2)] * 7)
        self.assertEqual(ku["main"], "kurdish (Sorani)"); self.assertIn("Kurdish", ku["note"])
        self.assertEqual(si.languages([W("hello", 0, 1)] * 10)["main"], "english")

    def test_unfixed_glossary_spelling_is_flagged(self):
        v = si.vocabulary([W("ستور", 0, 1), W("المتجر", 1, 2)], [{"spoken": "ستور", "write": "المتجر"}])
        self.assertEqual(v["unfixed_spellings"][0]["should_be"], "المتجر"); self.assertEqual(v["used"], {"المتجر": 1})

    def test_no_transcript_means_nothing_written(self):
        self.assertIsNone(si.build(tempfile.mkdtemp()))


if __name__ == "__main__":
    unittest.main()
