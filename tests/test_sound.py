"""Every video's sound is levelled to the social-media loudness without touching the picture."""
import os, shutil, subprocess, sys, tempfile, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import render, qa_check


@unittest.skipUnless(shutil.which("ffmpeg"), "needs ffmpeg")
class SoundTests(unittest.TestCase):
    def make(self, vol):
        d = tempfile.mkdtemp(); p = os.path.join(d, "v.mp4")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=180x320:r=30:d=6",
                        "-f", "lavfi", "-i", "sine=f=300:d=6,apulsator=hz=2", "-af", f"volume={vol}dB",
                        "-c:v", "libx264", "-c:a", "aac", "-shortest", p], check=True)
        return p

    def test_quiet_voice_is_brought_to_target(self):
        p = self.make(-24)
        before = render.duration(p)
        self.assertLess(qa_check.loudness(p)[0], -25)
        render.even_sound(p)
        lufs, peak = qa_check.loudness(p)
        self.assertLess(abs(lufs - render.LUFS), 1.5, lufs)
        self.assertLessEqual(peak, -0.5)
        self.assertLess(abs(render.duration(p) - before), 0.1)

    def test_loud_voice_is_brought_down(self):
        p = self.make(+6)
        render.even_sound(p)
        self.assertLess(abs(qa_check.loudness(p)[0] - render.LUFS), 1.5)

    def test_silent_video_is_left_alone(self):
        d = tempfile.mkdtemp(); p = os.path.join(d, "s.mp4")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=180x320:r=30:d=2", "-c:v", "libx264", p], check=True)
        self.assertIsNone(render.even_sound(p))


if __name__ == "__main__":
    unittest.main()
