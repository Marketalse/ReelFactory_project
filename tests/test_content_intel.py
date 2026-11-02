import array, json, math, os, sys, tempfile, types, unittest, wave
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from lib import content_intel as ci, speech_intel as si  # noqa: E402
import reel  # noqa: E402


def W(t, s, e):
    return {"text": t, "start": s, "end": e}


def make_job():
    d = tempfile.mkdtemp()
    words = [W("اهلا", 0.0, 0.5), W("اممم", 0.6, 0.9), W("المتجر", 1.0, 1.6), W("المتجر", 1.65, 2.2), W("يعني", 2.3, 2.6),
             W("رقم", 4.5, 5.0), W("خمسة", 5.05, 5.6), W("جدا", 5.65, 6.0)]
    json.dump(words, open(os.path.join(d, "transcript_asr.json"), "w"), ensure_ascii=False)
    json.dump(words, open(os.path.join(d, "transcript.json"), "w"), ensure_ascii=False)
    sr, a = 16000, array.array("h")
    for n in range(int(7 * sr)):
        t = n / sr
        a.append(int(32767 * (0.4 if 1.0 <= t < 1.6 else 0.01) * math.sin(2 * math.pi * 220 * t)))
    with wave.open(os.path.join(d, "audio16k.wav"), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(a.tobytes())
    si.build(d)
    json.dump({"clips": [{"id": "c01", "start": 0.0, "scenes": [{"start": 0, "end": 4}, {"start": 5.2, "end": 7}]}]}, open(os.path.join(d, "media_index.json"), "w"))
    json.dump([{"t": 5.0, "face": {"x": .3, "y": .2, "w": .3, "h": .3}}], open(os.path.join(d, "shot_log.json"), "w"))
    return d


class ContentIntelTests(unittest.TestCase):
    def test_joined_file_has_every_source(self):
        d = make_job()
        out = ci.build(d)
        self.assertTrue(os.path.exists(os.path.join(d, "content_intel.json")))
        self.assertEqual(out["sources"], {"speech_intel": True, "media_index": True, "shot_log": True})
        p0, p1 = out["phrases"]
        self.assertEqual((p0["i0"], p0["i1"]), (0, 4)); self.assertAlmostEqual(p0["pause_after_s"], 1.9, places=1)
        self.assertEqual(p1["scene_changes"], [5.2]); self.assertEqual(p1["face"]["x"], 0.3)
        self.assertIn("المتجر", p0["emphasis"]); self.assertGreaterEqual(p0["fillers"], 1); self.assertGreaterEqual(p0["repeats"], 1)

    def test_marks_and_prompt_lines(self):
        out = ci.build(make_job())
        line = ci.marked_lines(out).splitlines()[0]
        self.assertTrue(line.startswith("[0.0-2.6] "))
        for m in ("pause 1.9s", "emphasis", "false start"):
            self.assertIn(m, line)
        self.assertIn("scene change", ci.marked_lines(out).splitlines()[1])

    def test_works_with_only_a_transcript_and_nothing_without_one(self):
        d = tempfile.mkdtemp()
        json.dump([W("a", 0, .4), W("b", .5, .9)], open(os.path.join(d, "transcript.json"), "w"))
        out = ci.build(d)
        self.assertEqual(out["sources"], {"speech_intel": False, "media_index": False, "shot_log": False}); self.assertEqual(ci.marks(out["phrases"][0]), "")
        self.assertIsNone(ci.build(tempfile.mkdtemp()))

    def test_story_prompt_carries_the_marks_and_legend(self):
        d = make_job()
        c = reel.Ctx(d, types.SimpleNamespace(select="auto", fresh_selects=False, effort="low", budget=5, img_tok=800))
        seen = []
        def fake(stage, model, content, mt, effort="low", **k):
            seen.append(content[0]["text"])
            return json.dumps({"selects": [{"id": "A", "range": [0, 6], "label": "l", "hook_line": "", "why": "w", "score": 5}]})
        with mock.patch.object(reel, "proxy_duration", return_value=300.0), mock.patch.object(c, "llm", side_effect=fake):
            reel.st_selects(c)
        self.assertIn("{pause 1.9s", seen[0]); self.assertIn("Marks in braces", seen[0])


if __name__ == "__main__":
    unittest.main()
