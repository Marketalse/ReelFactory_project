"""energy.py finds the picture changes and the loudness of a known test video. Offline, free."""
import os, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import energy  # noqa: E402


class EnergyTests(unittest.TestCase):
    def test_known_video(self):
        d = tempfile.mkdtemp(); out = os.path.join(d, "t.mp4")
        # 3 colour blocks of 2 s (2 picture changes at 2 s and 4 s) with a quiet tone starting at 0.5 s
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=red:s=160x90:d=2:r=25",
                        "-f", "lavfi", "-i", "color=c=blue:s=160x90:d=2:r=25", "-f", "lavfi", "-i", "color=c=green:s=160x90:d=2:r=25",
                        "-f", "lavfi", "-i", "sine=f=440:d=5.5", "-filter_complex",
                        "[0][1][2]concat=n=3:v=1:a=0[v];[3]adelay=500|500,volume=0.3[a]", "-map", "[v]", "-map", "[a]", "-shortest", out], check=True)
        r = energy.measure(out)
        self.assertEqual(r["changes"], 2)
        self.assertAlmostEqual(r["longest_hold_s"], 2.0, delta=0.3)
        self.assertAlmostEqual(r["first_sound_s"], 0.5, delta=0.2)
        self.assertIsNotNone(r["lufs"])
        t = energy.targets([r, r])
        self.assertEqual(t["reels_measured"], 2); self.assertEqual(t["changes_per_min"], r["changes_per_min"])


if __name__ == "__main__":
    unittest.main()
