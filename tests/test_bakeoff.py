"""T59 bake-off: runs each model on its own copy, never touches the real reel, writes a report. No real AI call (mocked). Free."""
import json, os, shutil, sys, tempfile, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import reel  # noqa: E402


class BakeoffTests(unittest.TestCase):
    def test_compare_two_models_without_touching_the_reel(self):
        tmp = tempfile.mkdtemp(); job = os.path.join(tmp, "jobs", "2026-11-02-t"); os.makedirs(job)
        words = [{"text": f"w{i}", "start": i * 0.4, "end": i * 0.4 + 0.3} for i in range(30)]
        for f, d in (("transcript_asr.json", words), ("transcript.json", words), ("job.json", {}),
                     ("edl.json", {"words": words, "duration": 12, "segments": []})):
            json.dump(d, open(os.path.join(job, f), "w"))
        before = sorted(os.listdir(job))
        calls = []

        def fake_step(name):
            def run(c):
                calls.append((name, reel.M_FIX if name == "fix" else reel.M_SEL if name == "selects" else reel.M_DIR))
                c.cost["calls"].append({"stage": name, "cost": 0.01 if "haiku" in calls[-1][1] else 0.05}); reel.jsave(c.cost_path, c.cost)
                return f"{name} done"
            return run
        a = mock.Mock(select=None, fresh_selects=False, replan=False)
        with mock.patch.object(reel, "ROOT", tmp), mock.patch.object(reel, "st_fix", fake_step("fix")), \
                mock.patch.object(reel, "st_selects", fake_step("selects")), mock.patch.object(reel, "st_plan", fake_step("plan")):
            path = reel.bakeoff(job, ["cheap/model-x"], a)
        report = open(path, encoding="utf-8").read()
        self.assertIn("| current |", report); self.assertIn("| cheap/model-x |", report)
        self.assertEqual(len(calls), 6)                                   # 3 steps x 2 models
        self.assertTrue(all(m == "cheap/model-x" for n, m in calls[3:]))   # the candidate really ran each step
        self.assertEqual(sorted(os.listdir(job)), before)                 # the real reel is untouched
        self.assertEqual(reel.M_FIX, reel.cfg.MODELS["transcript_fix"])   # models restored


if __name__ == "__main__":
    unittest.main()
