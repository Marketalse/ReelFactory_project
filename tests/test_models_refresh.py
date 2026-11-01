"""Model catalogue check: notices removed models and price changes; never switches models."""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import models_refresh as mr


class CatalogTests(unittest.TestCase):
    def test_per_token_and_per_million(self):
        self.assertEqual(mr.per_mtok({"prompt": "0.0000001", "completion": "0.0000005"}), {"in": 0.1, "out": 0.5})
        self.assertEqual(mr.per_mtok({"input": 2, "output": 10}), {"in": 2.0, "out": 10.0})
        self.assertIsNone(mr.per_mtok(None))

    def test_compare(self):
        project = {"models": {"a": "x/cheap", "b": "x/gone", "c": "x/same"},
                   "prices_per_mtok": {"x/cheap": {"in": 0.1, "out": 0.5}, "x/gone": {"in": 1, "out": 1}, "x/same": {"in": 2.0, "out": 10.0}}}
        catalog = {"x/cheap": {"pricing": {"prompt": "0.0000002", "completion": "0.0000005"}},
                   "x/same": {"pricing": {"prompt": "0.000002", "completion": "0.00001"}}}
        rows, new = mr.compare(catalog, project)
        states = {m: s for m, s, _, _ in rows}
        self.assertIn("NOT OFFERED", states["x/gone"]); self.assertEqual(states["x/cheap"], "price changed"); self.assertEqual(states["x/same"], "ok")
        self.assertEqual(new, {"x/cheap": {"in": 0.2, "out": 0.5}})
        self.assertEqual(project["models"]["a"], "x/cheap")


if __name__ == "__main__":
    unittest.main()
