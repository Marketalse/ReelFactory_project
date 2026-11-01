"""ffmpeg in the old Hermes tools folder must be visible to every tool (HyperFrames render needs it on PATH)."""
import os, stat, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from lib import config as cfg


class FfmpegPathTests(unittest.TestCase):
    def test_hermes_ffmpeg_is_put_on_path(self):
        home = tempfile.mkdtemp(); d = os.path.join(home, ".hermes", "tools", "ffmpeg-9.0.1-darwin-arm64"); os.makedirs(d)
        f = os.path.join(d, "ffmpeg"); open(f, "w").write("#!/bin/sh\n"); os.chmod(f, stat.S_IRWXU)
        old = dict(os.environ)
        try:
            os.environ.update(HOME=home, PATH="/nonexistent")
            old_dirs = cfg.FFMPEG_DIRS; cfg.FFMPEG_DIRS = ["~/.hermes/tools/ffmpeg-9.0.1-darwin-arm64"]
            self.assertTrue(cfg.ffmpeg_on_path())
            self.assertEqual(os.environ["PATH"].split(os.pathsep)[0], d)
        finally:
            cfg.FFMPEG_DIRS = old_dirs; os.environ.clear(); os.environ.update(old)


if __name__ == "__main__":
    unittest.main()
