"""Offline checks for the pipeline: no paid calls, no network. Run:  python3 -m unittest discover tests -v"""
import io, json, os, sys, tempfile, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from lib import config as cfg  # noqa: E402
import reel  # noqa: E402


class ConfigTests(unittest.TestCase):
    def test_every_configured_model_has_a_price(self):
        for role, model in cfg.MODELS.items():
            self.assertTrue(cfg.price(model), role)

    def test_budget_levels_are_ordered(self):
        b = cfg.BUDGET
        self.assertLess(b["per_reel_warn"], b["per_reel_stop"])
        self.assertLess(b["per_reel_stop"], b["monthly_stop"])

    def test_pipeline_reads_models_from_config(self):
        self.assertEqual(reel.M_DIR, cfg.MODELS["director"])
        self.assertEqual(reel.M_SEL, cfg.MODELS["selects"])
        self.assertNotIn("opus", reel.M_DIR)

    def test_story_length_comes_from_rules(self):
        self.assertEqual((reel.LEN_MIN, reel.LEN_MAX), (40, 90))
        self.assertIn("{lmin}-{lmax}", reel.SELECTS_PROMPT)

    def test_month_spent_reads_ledger(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "expenses.json")
            json.dump({"rows": [{"date": "2026-11-01", "amount": 0.5}, {"date": "2026-11-20", "amount": 0.25},
                                {"date": "2026-10-31", "amount": 9}, {"date": "2026-11-02", "amount": 3, "archived": True}]},
                      open(p, "w"))
            with mock.patch.object(cfg, "LEDGER", p):
                self.assertAlmostEqual(cfg.month_spent("2026-11"), 0.75)


class BudgetGuardTests(unittest.TestCase):
    """The guard must refuse BEFORE any network call."""

    def make_ctx(self, job, budget=1.0):
        a = mock.Mock(budget=budget, img_tok=800)
        return reel.Ctx(job, a)

    def test_per_reel_stop(self):
        with tempfile.TemporaryDirectory() as job:
            c = self.make_ctx(job, budget=0.001)
            with mock.patch.object(reel.urllib.request, "urlopen") as net:
                with self.assertRaises(reel.Stop) as e:
                    c.llm("plan", reel.M_DIR, [{"type": "text", "text": "x" * 4000}], 9000)
                net.assert_not_called()
            self.assertIn("BUDGET GUARD", str(e.exception))

    def test_monthly_cap(self):
        with tempfile.TemporaryDirectory() as job:
            c = self.make_ctx(job, budget=5.0)
            with mock.patch.object(cfg, "month_spent", return_value=cfg.BUDGET["monthly_stop"] - 0.0001), \
                 mock.patch.object(reel.urllib.request, "urlopen") as net:
                with self.assertRaises(reel.Stop) as e:
                    c.llm("plan", reel.M_DIR, [{"type": "text", "text": "x" * 4000}], 9000)
                net.assert_not_called()
            self.assertIn("MONTHLY CAP", str(e.exception))


class RunLogTests(unittest.TestCase):
    def test_tee_writes_log(self):
        with tempfile.TemporaryDirectory() as d:
            out = io.StringIO(); t = reel.Tee(os.path.join(d, "run.log"), out)
            t.write("hello\n"); t.flush()
            self.assertEqual(out.getvalue(), "hello\n")
            self.assertEqual(open(os.path.join(d, "run.log")).read(), "hello\n")


if __name__ == "__main__":
    unittest.main()
