import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from lib import ltx


class Slot(unittest.TestCase):
    def test_off_by_default(self):
        ok, msg = ltx.status(); self.assertFalse(ok); self.assertIn("off", msg)

    def test_cost_is_capped(self):
        self.assertEqual(ltx.estimate(100), round(ltx.conf()["max_seconds_per_reel"] * ltx.conf()["price_per_second_usd"], 3))

    def test_never_list_wins(self):
        self.assertFalse(ltx.allowed("replace_speaker_face")); self.assertTrue(ltx.allowed("broll_from_picture"))
        with self.assertRaises(ltx.NotReady): ltx.generate("replace_speaker_face", "x", 3, "o.mp4")


if __name__ == "__main__":
    unittest.main()
