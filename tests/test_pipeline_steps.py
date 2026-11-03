import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import reel
from lib import pipeline, config as cfg


class Steps(unittest.TestCase):
    def test_list_is_sound(self):
        self.assertEqual(pipeline.check(cfg.ROLES), [])

    def test_order_is_the_old_order(self):
        self.assertEqual(pipeline.order(), ["ingest", "transcribe", "fix", "review", "selects", "tighten", "edl", "keyframes",
                                            "shotlog", "plan", "compile", "draft", "report"])
        self.assertEqual(reel.STAGES, pipeline.order())

    def test_ai_steps_have_roles(self):
        self.assertEqual({r["name"] for r in pipeline.ai_steps()}, {"fix", "selects", "tighten", "shotlog", "plan"})

    def test_a_new_step_plugs_in_without_touching_the_runner(self):
        rows, funcs = list(pipeline.ROWS), dict(pipeline.FUNCS)
        try:
            @pipeline.step("outline", after="tighten", role="outline", needs=["chosen_select.json"], makes=["outline.json"])
            def st_outline(c): return "ok"
            o = pipeline.order()
            self.assertEqual(o[o.index("tighten") + 1], "outline")
            self.assertEqual(pipeline.check(cfg.ROLES), [])
            with self.assertRaises(ValueError):
                pipeline.step("x", after="nope")(lambda c: 1)
        finally:
            pipeline.ROWS[:] = rows; pipeline.FUNCS.clear(); pipeline.FUNCS.update(funcs)

    def test_check_finds_problems(self):
        rows = list(pipeline.ROWS)
        try:
            pipeline.ROWS.append(dict(name="ghost", label="", role="no_such_role", needs=["nothing.json"], makes=[]))
            bad = " | ".join(pipeline.check(cfg.ROLES))
            self.assertIn("no function", bad); self.assertIn("unknown AI role", bad); self.assertIn("nothing.json", bad)
        finally:
            pipeline.ROWS[:] = rows


if __name__ == "__main__":
    unittest.main()
