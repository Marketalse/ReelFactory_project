"""ffmpeg is copied once from the old Hermes folder into ~/.reelfactory/tools and put on PATH for every tool."""
import os, stat, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from lib import config as cfg


class FfmpegPathTests(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(); self.env = dict(os.environ)
        self.saved = (cfg.TOOLS, cfg.FFMPEG_DIRS, cfg.OLD_TOOLS)
        cfg.TOOLS = os.path.join(self.home, ".reelfactory", "tools"); cfg.FFMPEG_DIRS = [cfg.TOOLS]
        cfg.OLD_TOOLS = os.path.join(self.home, ".hermes", "tools", "ffmpeg-*")
        os.environ["PATH"] = "/nonexistent"

    def tearDown(self):
        cfg.TOOLS, cfg.FFMPEG_DIRS, cfg.OLD_TOOLS = self.saved; os.environ.clear(); os.environ.update(self.env)

    def test_hermes_ffmpeg_is_copied_and_put_on_path(self):
        old = os.path.join(self.home, ".hermes", "tools", "ffmpeg-9.0.1-darwin-arm64"); os.makedirs(old)
        for n in ("ffmpeg", "ffprobe"):
            f = os.path.join(old, n); open(f, "w").write("#!/bin/sh\n"); os.chmod(f, stat.S_IRWXU)
        self.assertTrue(cfg.ffmpeg_on_path())
        self.assertEqual(os.environ["PATH"].split(os.pathsep)[0], cfg.TOOLS)
        self.assertTrue(os.path.exists(os.path.join(cfg.TOOLS, "ffprobe")))
        self.assertTrue(os.path.exists(os.path.join(old, "ffmpeg")))                 # Hermes folder untouched

    def test_nothing_found_is_reported(self):
        self.assertFalse(cfg.ffmpeg_on_path())


if __name__ == "__main__":
    unittest.main()
