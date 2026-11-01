"""Offline checks for the upload page backend (dashboard/reels_api.py): uploads, names, live progress. No spend."""
import importlib, io, json, os, sys, tempfile, time, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "dashboard"))


class ApiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = self.tmp.name
        for d in ("jobs", "inbox", "config"):
            os.makedirs(os.path.join(self.root, d))
        json.dump({"handles": {"instagram": "@a", "tiktok": "@b"}}, open(os.path.join(self.root, "config", "brand.json"), "w"))
        os.environ["RF_ROOT"] = self.root
        import reels_api
        self.api = importlib.reload(reels_api)

    def tearDown(self):
        os.environ.pop("RF_ROOT", None); self.tmp.cleanup()

    def up(self, data=b"x" * 1000, name="take.MOV", kind="clip", slug="store-tips", session="abcdefgh12", order=1, length=None):
        return self.api.upload(slug, kind, name, session, len(data) if length is None else length, io.BytesIO(data), order)

    def job(self, name, status, log, timing=None):
        d = os.path.join(self.root, "jobs", name); os.makedirs(os.path.join(d, "review"), exist_ok=True)
        json.dump({"status": status}, open(os.path.join(d, "job.json"), "w"))
        open(os.path.join(d, "run.log"), "w").write("\n".join(log) + "\n")
        if timing is not None:
            json.dump(timing, open(os.path.join(d, "timing.json"), "w"))
        return d


class UploadTests(ApiTest):
    def test_clip_is_saved_in_order_with_a_safe_name(self):
        ok, name = self.up(name="../My Take (1).MOV", order=2)
        self.assertTrue(ok, name)
        self.assertEqual(name, "02-My-Take-1.mov")
        self.assertTrue(os.path.exists(os.path.join(self.root, "inbox", "store-tips", "clips", name)))

    def test_wrong_types_and_empty_files_are_refused(self):
        self.assertFalse(self.up(name="notes.txt")[0])
        self.assertFalse(self.up(name="logo.jpg", kind="logo")[0])
        self.assertFalse(self.up(data=b"")[0])
        self.assertTrue(self.up(name="logo.svg", kind="logo")[0])

    def test_interrupted_upload_leaves_nothing_behind(self):
        ok, msg = self.up(data=b"x" * 10, length=100)
        self.assertFalse(ok); self.assertIn("interrupted", msg)
        clips = os.path.join(self.root, "inbox", "store-tips", "clips")
        self.assertEqual(os.listdir(clips), [])

    def test_a_name_used_by_another_session_or_job_is_refused(self):
        self.assertTrue(self.up()[0])
        self.assertTrue(self.up(name="b.mp4", order=2)[0])                     # same page: fine
        ok, msg = self.up(session="otherpage99")
        self.assertFalse(ok); self.assertIn("already used", msg)
        self.assertFalse(self.api.check_name("store-tips", "otherpage99")[0])
        self.assertTrue(self.api.check_name("store-tips", "abcdefgh12")[0])
        self.job("2026-11-01-old-reel", "preview_ready", [])
        self.assertFalse(self.api.check_name("old-reel", "abcdefgh12")[0])

    def test_busy_server_refuses_before_any_upload(self):
        self.api._running["someone"] = {"what": [], "started": time.time()}
        ok, msg = self.api.check_name("new-one", "abcdefgh12")
        self.assertFalse(ok); self.assertIn("one reel at a time", msg)

    def test_start_needs_a_video(self):
        self.api.save_notes("empty-one", "abcdefgh12", "hello")
        ok, msg = self.api.start("empty-one")
        self.assertFalse(ok); self.assertIn("no video", msg)


class ProgressTests(ApiTest):
    RUN = "===== run 2026-11-01 10:00:00 | inbox/x --slug x"

    def test_running_job_reports_steps_percent_and_eta(self):
        self.job("2026-11-01-xx", "transcribed", [self.RUN, "ingest      ok    0.0s  +$0.0000  cached",
                                                 "transcribe  ok  200.0s  +$0.0000  216 words"], {"ingest": 0.0, "transcribe": 200.0})
        self.api._running["xx"] = {"what": ["inbox/xx", "--slug", "xx"], "started": time.time() - 210}
        p = self.api.progress("xx")
        self.assertEqual(p["state"], "running"); self.assertEqual(p["job"], "2026-11-01-xx")
        states = {s["key"]: s["state"] for s in p["steps"]}
        self.assertEqual(states["prepare"], "done"); self.assertEqual(states["listen"], "active"); self.assertEqual(states["render"], "waiting")
        self.assertTrue(0 < p["percent"] < 100); self.assertGreater(p["eta"], 0)
        self.assertEqual(p["message"], "Listening to your words")

    def test_ready_stopped_and_final(self):
        d = self.job("2026-11-01-aa", "preview_ready", [self.RUN, "draft       ok  100.0s", "GATE 2: watch"])
        open(os.path.join(d, "review", "draft_540p.mp4"), "wb").write(b"0")
        p = self.api.progress("2026-11-01-aa")
        self.assertEqual((p["state"], p["percent"], p["draft"]), ("ready", 100.0, "2026-11-01-aa/review/draft_540p.mp4"))
        self.assertTrue(p["handles_set"])

        self.job("2026-11-01-bb", "transcribed", [self.RUN, "STOP: monthly budget reached", "TOTAL this job $0.01"])
        p = self.api.progress("bb")
        self.assertEqual(p["state"], "stopped"); self.assertEqual(p["message"], "monthly budget reached")

        d = self.job("2026-11-01-cc", "rendered", ["===== run 2026-11-01 | jobs/c --approve", "FINAL:"])
        os.makedirs(os.path.join(d, "final"))
        for f in ("reel_v1_instagram.mp4", "reel_v2_instagram.mp4", "reel_v2_tiktok.mp4", "reel_v2_tiktok_QA_FAILED.mp4"):
            open(os.path.join(d, "final", f), "wb").write(b"0")
        p = self.api.progress("cc")
        self.assertEqual(p["state"], "final"); self.assertEqual(p["last_mode"], "final")
        self.assertEqual(p["finals"], ["reel_v2_instagram.mp4", "reel_v2_tiktok.mp4"])

    def test_early_failure_before_the_job_exists_is_explained(self):
        os.makedirs(self.api.RUNS, exist_ok=True)
        open(os.path.join(self.api.RUNS, "yy.log"), "w").write("ingest 1/1: a.mov\nINGEST FAILED: no video stream\ningest failed\n")
        p = self.api.progress("yy")
        self.assertEqual(p["state"], "stopped"); self.assertIn("ingest failed", p["message"])

    def test_crash_shows_the_actual_error(self):
        self.job("2026-11-01-dd", "planned", [self.RUN, "plan        ok   3.0s", "CRASH (full error below, also in run.log):",
                                             "Traceback (most recent call last):", '  File "reel.py", line 9, in <module>',
                                             "KeyError: 'segments'", "TOTAL this job $0.02 | wall 9s"])
        p = self.api.progress("dd")
        self.assertEqual(p["state"], "stopped"); self.assertEqual(p["message"], "crash: KeyError: 'segments'")

    def test_unset_handles_are_reported(self):
        json.dump({"handles": {"instagram": "CONFIRM (proposed)", "tiktok": "CONFIRM"}}, open(os.path.join(self.root, "config", "brand.json"), "w"))
        self.assertFalse(self.api._handles_set())


if __name__ == "__main__":
    unittest.main()
