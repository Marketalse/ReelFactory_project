"""BUG-005 / BUG-006 (pre-UAT audit 2026-11-03): two runs on one reel trampled each other (a crash with a raw traceback, lost cost records);
a half-written video made the QA check crash on ffprobe's 'N/A'."""
import json, os, signal, subprocess, sys, tempfile, time, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from lib import joblock
import qa_check

HOLD = "import sys,time; sys.path.insert(0, %r); from lib import joblock; f = joblock.acquire(sys.argv[1]); print('held', flush=True); time.sleep(60)" % os.path.join(ROOT, "scripts")


@unittest.skipUnless(joblock.fcntl, "needs a Unix system")
class Lock(unittest.TestCase):
    def holder(self, job):
        p = subprocess.Popen([sys.executable, "-c", HOLD, job], stdout=subprocess.PIPE, text=True); p.stdout.readline(); return p

    def test_second_run_is_refused_and_kill9_frees_the_lock(self):
        job = tempfile.mkdtemp(); h = self.holder(job)
        try:
            self.assertTrue(joblock.held(job))
            with self.assertRaises(joblock.Busy) as ctx: joblock.acquire(job)
            self.assertIn("already being made", str(ctx.exception))
            h.send_signal(signal.SIGKILL); h.wait(); time.sleep(0.2)                         # the system releases the lock when the run dies, even by kill -9
            self.assertFalse(joblock.held(job))
            f = joblock.acquire(job); self.assertIsNotNone(f); f.close()
        finally:
            if h.poll() is None: h.kill()

    def test_reel_py_refuses_a_second_run_without_touching_the_reel(self):
        job = tempfile.mkdtemp(); json.dump({"status": "ingested"}, open(os.path.join(job, "job.json"), "w"))
        h = self.holder(job)
        try:
            r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "reel.py"), job], capture_output=True, text=True, timeout=60)
            self.assertEqual(r.returncode, 3); self.assertIn("already being made", r.stdout)
            self.assertFalse(os.path.exists(os.path.join(job, "run.log")))                    # nothing was written
            self.assertNotIn("Traceback", r.stdout + r.stderr)
        finally:
            h.kill()


class Duration(unittest.TestCase):
    def test_half_written_video_reports_length_zero_instead_of_crashing(self):
        from unittest import mock
        fake = subprocess.CompletedProcess([], 0, stdout="N/A\n", stderr="")                 # exactly what ffprobe printed for the video being written by the other run
        with mock.patch.object(qa_check.subprocess, "run", return_value=fake):
            self.assertEqual(qa_check.duration("x.mp4"), 0.0)


if __name__ == "__main__":
    unittest.main()
