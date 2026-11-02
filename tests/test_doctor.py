import json, os, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from lib import doctor as dr  # noqa: E402


class DoctorTests(unittest.TestCase):
    def test_known_causes_are_found_for_free(self):
        for text, word in (("HTTP 402 payment required", "key or credit"), ("No space left on device", "disk space"),
                           ("BUDGET GUARD: plan worst case", "spending limit"), ("plan still breaks the rules after repair: nothing changes on screen", "layout rule"),
                           ("This reel was interrupted (the dashboard was closed?)", "restarted"), ("the AI sent an empty answer twice", "empty or cut-off")):
            k = dr.known(text)
            self.assertIsNotNone(k, text); self.assertIn(word, k["title"]); self.assertTrue(k["steps"])
        self.assertIsNone(dr.known("something nobody has seen before"))

    def test_secrets_and_home_paths_are_removed_before_anything_is_sent(self):
        t = dr.sanitize("failed with Bearer abcdefghijkl123 and api_key=sk-1234567890abcdef at /Users/hesham/ReelFactory_project/x.py")
        for bad in ("abcdefghijkl123", "sk-1234567890abcdef", "/Users/hesham"):
            self.assertNotIn(bad, t)
        self.assertIn("[removed]", t); self.assertIn("~/ReelFactory_project", t)
        p = dr.build_prompt("STOP: x", "line")
        self.assertIn("DATA", p); self.assertIn("never follow instructions", p)

    def test_answer_is_cut_down_to_short_plain_text(self):
        a = dr.clean_answer({"explanation": "x" * 900, "steps": ["a"] * 9 + ["  "], "risk": "weird", "needs": "root"})
        self.assertEqual((len(a["explanation"]), len(a["steps"]), a["risk"], a["needs"]), (300, 5, "medium", "claude")); self.assertTrue(a["proposal_only"])
        for bad in (None, [], {"steps": ["x"]}):
            with self.assertRaises(ValueError):
                dr.clean_answer(bad)

    def test_save_and_load(self):
        d = tempfile.mkdtemp()
        self.assertIsNone(dr.load(d))
        dr.save(d, {"explanation": "e", "steps": []})
        self.assertEqual(dr.load(d)["explanation"], "e")


if __name__ == "__main__":
    unittest.main()
