import json, os, sys, tempfile, types, unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from lib import creative_brief as cb  # noqa: E402
import reel  # noqa: E402


class BriefTests(unittest.TestCase):
    def test_clean_keeps_only_valid_values(self):
        b = cb.clean({"goal": "sell", "style": "nonsense", "length": "short", "audience": "  new   owners ", "action": "x" * 500, "evil": "rm -rf"})
        self.assertEqual(b["goal"], "sell"); self.assertNotIn("style", b); self.assertEqual(b["audience"], "new owners")
        self.assertEqual(len(b["action"]), 160); self.assertNotIn("evil", b)
        self.assertEqual(cb.clean(None), {}); self.assertEqual(cb.clean("x"), {})

    def test_length_and_text(self):
        self.assertEqual(cb.length_range({"length": "short"}, (40, 90)), (30, 45))
        self.assertEqual(cb.length_range({}, (40, 90)), (40, 90))
        t = cb.to_text({"goal": "sell", "style": "fast", "length": "short", "action": "comment store"})
        for w in ("sell", "fast", "30-45", "comment store", "never invent"):
            self.assertIn(w, t)
        self.assertEqual(cb.to_text({}), "")

    def test_save_keeps_his_notes_and_adds_the_brief(self):
        d = tempfile.mkdtemp()
        cb.save(d, {"goal": "educate", "length": "long"}, "Main point: reply fast")
        md = open(os.path.join(d, "brief.md"), encoding="utf-8").read()
        self.assertTrue(md.startswith("Main point: reply fast")); self.assertIn("Length: 60-90", md)
        self.assertEqual(cb.load(d), {"goal": "educate", "length": "long"})
        e = tempfile.mkdtemp(); cb.save(e, {}, "")                                   # nothing given: no files
        self.assertEqual(os.listdir(e), [])


class StoryUsesBriefTests(unittest.TestCase):
    def test_story_prompt_has_the_brief_length_and_style(self):
        job = tempfile.mkdtemp()
        json.dump([{"text": "كلمة", "start": i * 0.5, "end": i * 0.5 + 0.4} for i in range(40)], open(os.path.join(job, "transcript.json"), "w"), ensure_ascii=False)
        cb.save(job, {"goal": "sell", "style": "fast", "length": "short"})
        c = reel.Ctx(job, types.SimpleNamespace(select="auto", fresh_selects=False, effort="low", budget=5, img_tok=800))
        seen = []
        def fake_llm(stage, model, content, mt, effort="low", **k):
            seen.append(content[0]["text"])
            return json.dumps({"main_message": "m", "audience": "a", "selects": [{"id": "A", "range": [0, 40], "label": "l", "hook_line": "", "why": "w", "score": 5}]})
        with mock.patch.object(reel, "proxy_duration", return_value=200.0), mock.patch.object(c, "llm", side_effect=fake_llm):
            reel.st_selects(c)
        self.assertIn("30-45 seconds", seen[0]); self.assertIn("CREATIVE BRIEF", seen[0]); self.assertIn("Prefer candidates whose style is fast", seen[0])

    def test_without_a_brief_nothing_changes(self):
        job = tempfile.mkdtemp()
        json.dump([{"text": "كلمة", "start": i * 0.5, "end": i * 0.5 + 0.4} for i in range(40)], open(os.path.join(job, "transcript.json"), "w"), ensure_ascii=False)
        c = reel.Ctx(job, types.SimpleNamespace(select="auto", fresh_selects=False, effort="low", budget=5, img_tok=800))
        seen = []
        def fake_llm(stage, model, content, mt, effort="low", **k):
            seen.append(content[0]["text"])
            return json.dumps({"selects": [{"id": "A", "range": [0, 40], "label": "l", "hook_line": "", "why": "w", "score": 5}]})
        with mock.patch.object(reel, "proxy_duration", return_value=200.0), mock.patch.object(c, "llm", side_effect=fake_llm):
            reel.st_selects(c)
        self.assertIn("40-90 seconds", seen[0]); self.assertNotIn("CREATIVE BRIEF", seen[0])


if __name__ == "__main__":
    unittest.main()
