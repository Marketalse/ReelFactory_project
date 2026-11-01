"""The AI editor remembers Hesham's taste and his earlier comments (not word fixes or retries)."""
import json, os, sys, tempfile, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from lib import director


class TasteTests(unittest.TestCase):
    def test_taste_collects_lessons_and_comments(self):
        r = tempfile.mkdtemp(); os.makedirs(os.path.join(r, ".reel-agent"))
        open(os.path.join(r, ".reel-agent", "lessons.md"), "w").write(
            "# L\n## Hesham's taste\n- Keep captions big\n\n## Known failures\n- Never X\n")
        for job, hist in (("2026-11-01-a", [{"time": "2026-11-01 10:00", "fix": "hook shorter\nمتجر => متجري"}]),
                          ("2026-11-02-b", [{"time": "2026-11-02 10:00", "fix": "(try again)"}, {"time": "2026-11-02 11:00", "fix": "Hook shorter"}])):
            os.makedirs(os.path.join(r, "jobs", job)); json.dump({"feedback_history": hist}, open(os.path.join(r, "jobs", job, "job.json"), "w"))
        t = director.taste(root=r)
        self.assertIn("Keep captions big", t); self.assertNotIn("Never X", t)
        self.assertEqual(t.lower().count("hook shorter"), 1)
        self.assertNotIn("=>", t); self.assertNotIn("try again", t)

    def test_prefs_reach_the_prompt(self):
        words = [{"text": "مرحبا", "start": 0.0, "end": 0.5}]
        p = director.build_prompt(words, 30.0, prefs="- Keep captions big")
        self.assertIn("STANDING PREFERENCES", p); self.assertIn("Keep captions big", p)
        self.assertNotIn("STANDING PREFERENCES", director.build_prompt(words, 30.0))


if __name__ == "__main__":
    unittest.main()
