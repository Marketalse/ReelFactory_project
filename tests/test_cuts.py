"""Face pieces shorter than 0.3 s are folded into a neighbour instead of stopping the reel."""
import os, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from lib import director  # noqa: E402


def C(t_in, t_out, src_in, scale=1.0, y=0):
    return {"id": "x", "t_in": t_in, "t_out": t_out, "src_in": src_in, "scale": scale, "cy": 0.36, "y": y}


class ShortCutTests(unittest.TestCase):
    def test_sliver_at_start_joins_the_same_footage(self):
        # zoom starts 0.2 s in: piece 0-0.2 (1.0x) then 0.2-3 (1.08x), same footage
        out = director.absorb_short([C(0, 0.2, 5.0), C(0.2, 3.0, 5.2, 1.08)])
        self.assertEqual(len(out), 1); self.assertEqual((out[0]["t_in"], out[0]["t_out"], out[0]["src_in"]), (0, 3.0, 5.0))

    def test_sliver_between_different_takes_extends_the_previous(self):
        out = director.absorb_short([C(0, 2.0, 0.0), C(2.0, 2.15, 9.0), C(2.15, 5.0, 20.0)])
        self.assertEqual([(c["t_in"], c["t_out"]) for c in out], [(0, 2.15), (2.15, 5.0)])

    def test_first_piece_alone_borrows_from_the_next(self):
        out = director.absorb_short([C(0, 0.1, 50.0), C(0.1, 4.0, 3.0)])
        self.assertEqual(len(out), 1); self.assertEqual(out[0]["t_in"], 0); self.assertAlmostEqual(out[0]["src_in"], 2.9)

    def test_real_timeline_never_yields_short_pieces(self):
        tl = {"duration": 10.0, "punch_ins": [(0.15, 1.12)], "face_cy": 0.36,
              "scenes": [{"block": "split", "t_in": 4.1, "t_out": 6.0}]}
        segs = [{"t_in": 0.0, "t_out": 4.0, "src_in": 1.0}, {"t_in": 4.0, "t_out": 10.0, "src_in": 8.0}]
        cuts = director.face_cuts(tl, segs)
        self.assertTrue(all(c["t_out"] - c["t_in"] >= 0.3 - 1e-6 for c in cuts), cuts)
        self.assertEqual(cuts[0]["t_in"], 0.0); self.assertEqual(cuts[-1]["t_out"], 10.0)
        for a, b in zip(cuts, cuts[1:]):
            self.assertAlmostEqual(a["t_out"], b["t_in"])


if __name__ == "__main__":
    unittest.main()
