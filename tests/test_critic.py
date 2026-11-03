import json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import reel
from lib import critic

OK = {"scores": {"readable": 8, "layout": 7.5, "consistency": 9, "variety": 4}, "issues": [{"t": 12.3, "what": "text touches the face"}, {"bad": 1}], "verdict": "clean but plain"}


class Clean(unittest.TestCase):
    def test_scores_are_checked_and_averaged(self):
        o = critic.clean(OK); self.assertEqual(o["average"], 7.1); self.assertEqual(len(o["issues"]), 1)
        self.assertEqual(critic.clean({"scores": {k: 99 for k in critic.RUBRIC}})["average"], 10.0)
        with self.assertRaises(ValueError): critic.clean({"scores": {"readable": 5}})
        self.assertIn("variety 4", critic.summary_lines(dict(o, stills=8))[0])

    def test_times_cover_the_reel(self):
        t = critic.pick_times({"scenes": [{"t_in": 1, "t_out": 3}, {"t_in": 5, "t_out": 6}]}, 20)
        self.assertEqual(len(t), 8); self.assertTrue(all(0 < x < 20 for x in t)); self.assertIn(2.0, t)


class Step(unittest.TestCase):
    def ctx(self, answer, stills=True):
        d = tempfile.mkdtemp(); os.makedirs(os.path.join(d, "review")); open(os.path.join(d, "review", "draft_540p.mp4"), "w").write("x")
        json.dump({"scenes": [], "duration": 30}, open(os.path.join(d, "timeline.json"), "w"))
        c = reel.Ctx.__new__(reel.Ctx); c.job = d; c.a = type("A", (), {"replan": False, "effort": None})(); c.calls = []
        def llm(stage, model, content, mt, effort="low", **k):
            c.calls.append((stage, model, len(content)))
            if isinstance(answer, Exception): raise answer
            return json.dumps(answer)
        c.llm = llm
        orig = critic.content; self.addCleanup(setattr, critic, "content", orig)
        critic.content = lambda video, times: ([{"type": "text", "text": "p"}], list(times) if stills else [])
        return c

    def test_step_saves_the_scores_with_the_critic_role(self):
        c = self.ctx(OK); self.assertIn("7.1/10", reel.st_critic(c))
        self.assertEqual(json.load(open(os.path.join(c.job, "review", "critic.json")))["stills"], 8)
        self.assertEqual(c.calls[0][1], reel.cfg.role("critic")[0]); self.assertEqual(reel.st_critic(c), "cached")

    def test_never_stops_the_reel_except_for_the_money_guard(self):
        self.assertEqual(reel.st_critic(self.ctx({"scores": {}})), "skipped")
        self.assertEqual(reel.st_critic(self.ctx(reel.Stop("odd"))), "skipped")
        self.assertIn("skipped", reel.st_critic(self.ctx(OK, stills=False)))
        with self.assertRaises(reel.Stop): reel.st_critic(self.ctx(reel.Stop("MONTHLY CAP: x")))


if __name__ == "__main__":
    unittest.main()
