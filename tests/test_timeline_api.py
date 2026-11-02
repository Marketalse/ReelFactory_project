import json, os, shutil, sys, tempfile, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts")); sys.path.insert(0, os.path.join(ROOT, "dashboard")); sys.path.insert(0, os.path.join(ROOT, "tests"))
import reels_api  # noqa: E402
import test_sequence as ts  # noqa: E402


class TimelineApiTests(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp(); self.job = "2026-11-02-demo"
        shutil.copytree(ts.make_job(), os.path.join(self.base, self.job))
        self.p = mock.patch.object(reels_api, "JOBS", self.base); self.p.start(); self.addCleanup(self.p.stop)

    def test_state_save_check(self):
        ok, d = reels_api.timeline(self.job)
        self.assertTrue(ok); self.assertEqual(len(d["clips"]), 2)
        seg = d["sequence"]["segments"]
        ok, msg, clean = reels_api.timeline_save(self.job, {"segments": seg[:1]})
        self.assertTrue(ok, msg); self.assertTrue(os.path.exists(os.path.join(self.base, self.job, "sequence.json")))
        ok, markers = reels_api.timeline_check(self.job, {"segments": seg})
        self.assertTrue(ok); self.assertTrue(markers)
        self.assertFalse(reels_api.timeline_check(self.job, {"segments": []})[0])
        self.assertFalse(reels_api.timeline("../../etc")[0]); self.assertFalse(reels_api.timeline_save("nope", {})[0])

    def test_auto_edit_saves_then_starts_the_background_run_with_the_flag(self):
        seg = reels_api.timeline(self.job)[1]["sequence"]["segments"]
        ran = []
        with mock.patch.object(reels_api, "_run", side_effect=lambda k, a, **kw: ran.append((k, a)) or (True, "started")):
            ok, msg = reels_api.timeline_apply(self.job, {"segments": seg})
        self.assertTrue(ok); self.assertEqual(ran, [(self.job, [os.path.join(self.base, self.job), "--apply-sequence"])])
        self.assertTrue(os.path.exists(os.path.join(self.base, self.job, "sequence.json")))
        with mock.patch.object(reels_api, "_run", return_value=(True, "x")):
            self.assertFalse(reels_api.timeline_apply(self.job, {"segments": []})[0])                  # an empty timeline is refused before anything starts

    def test_busy_server_refuses_changes_but_not_viewing(self):
        reels_api._running["other"] = {"what": [], "started": 0}
        try:
            self.assertTrue(reels_api.timeline(self.job)[0])
            self.assertFalse(reels_api.timeline_save(self.job, {"segments": []})[0]); self.assertFalse(reels_api.timeline_undo(self.job)[0])
        finally:
            reels_api._running.pop("other", None)

    def test_media_whitelist_has_clip_proxies_and_thumbs_only(self):
        os.makedirs(os.path.join(self.base, self.job, "thumbs")); open(os.path.join(self.base, self.job, "thumbs", "c01_s01.jpg"), "wb").write(b"x")
        self.assertIsNotNone(reels_api.media_path(f"{self.job}/c01/proxy.mp4")); self.assertIsNotNone(reels_api.media_path(f"{self.job}/thumbs/c01_s01.jpg"))
        for bad in (f"{self.job}/c01/../job.json", f"{self.job}/sequence.json", f"{self.job}/c1/proxy.mp4", f"{self.job}/thumbs/../job.json"):
            self.assertIsNone(reels_api.media_path(bad))


if __name__ == "__main__":
    unittest.main()
