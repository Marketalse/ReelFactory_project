import os, subprocess, sys, tempfile, unittest, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import ref_learn


@unittest.skipUnless(shutil.which("ffmpeg"), "needs ffmpeg")
class Learn(unittest.TestCase):
    def test_finds_the_moving_window_and_the_palette(self):
        d = tempfile.mkdtemp(); v = os.path.join(d, "ref.mp4")
        # still dark background + a moving test pattern in the middle (like a framed face window)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x242834:s=1080x1920:r=10:d=6", "-f", "lavfi", "-i", "color=c=gray:s=800x700:r=10:d=6,noise=alls=80:allf=t",
                        "-filter_complex", "[0][1]overlay=140:380", "-pix_fmt", "yuv420p", "-an", v], check=True)
        spec, imgs = ref_learn.analyse(v, "t")
        w = spec["layout"]["window"]
        self.assertTrue(120 <= w["x0"] <= 170 and 360 <= w["y0"] <= 420, w)
        self.assertTrue(spec["palette"]["bg"].startswith("#") and len(spec["palette"]["bg"]) == 7)
        self.assertEqual(spec["video"]["width"], 1080); self.assertFalse(spec["layout"]["full_frame"])


if __name__ == "__main__":
    unittest.main()
