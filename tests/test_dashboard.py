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

    def up(self, data=b"x" * 1000, name="take.MOV", kind="clip", slug="store-tips", session="abcdefgh12", order=1, length=None, offset=0, total=None):
        return self.api.upload(slug, kind, name, session, len(data) if length is None else length, io.BytesIO(data), order, offset, total)

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

    def test_interrupted_upload_keeps_a_part_and_resumes_from_it(self):
        data = bytes(range(256)) * 40
        ok, msg = self.up(data=data[:3000], length=len(data))                       # connection drops after 3000 bytes
        self.assertFalse(ok); self.assertIn("interrupted", msg)
        clips = os.path.join(self.root, "inbox", "store-tips", "clips")
        self.assertEqual(os.listdir(clips), ["01-take.mov.part"])                  # no half-finished clip is ever used
        st = self.api.upload_status("store-tips", "clip", "take.MOV", "abcdefgh12", 1)
        self.assertEqual(st["bytes"], 3000)
        ok, msg = self.up(data=data[3000:], length=len(data) - 3000, offset=3000, total=len(data))   # resume from there
        self.assertTrue(ok, msg)
        self.assertEqual(open(os.path.join(clips, "01-take.mov"), "rb").read(), data)
        self.assertEqual(os.listdir(clips), ["01-take.mov"])

    def test_resume_from_the_wrong_place_is_told_where_to_continue(self):
        self.up(data=b"x" * 100, length=1000)
        ok, msg = self.up(data=b"y" * 900, length=900, offset=500, total=1000)
        self.assertFalse(ok); self.assertEqual(msg, "resume:100")

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
        for f in ("reel_v1_instagram.mp4", "reel_v1_tiktok.mp4", "reel_v2.mp4", "reel_v3_QA_FAILED.mp4"):   # old per-platform files + new single file
            open(os.path.join(d, "final", f), "wb").write(b"0")
        p = self.api.progress("cc")
        self.assertEqual(p["state"], "final"); self.assertEqual(p["last_mode"], "final")
        self.assertEqual(p["finals"], ["reel_v2.mp4"]); self.assertEqual(p["version"], 2)
        self.assertNotIn("package", p)                                                  # no CapCut step any more

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

    def test_handles_not_needed_without_end_card(self):
        json.dump({"handles": {"instagram": "CONFIRM"}, "cta": {"enabled": False}}, open(os.path.join(self.root, "config", "brand.json"), "w"))
        self.assertTrue(self.api._handles_set())

    def test_final_steps_are_video_then_cover(self):
        self.assertEqual([k for k, _, _ in self.api.FINAL_STEPS], ["video", "cover"])


class PerformanceTests(ApiTest):
    def test_save_check_and_rates(self):
        d = self.job("2026-11-01-stock", "rendered", [])
        json.dump({"duration": 50.0, "scenes": [{"block": "hook_two_tone", "values": {"line1": "شكد بضاعة", "line2": "لازم تجيب"}},
                                                {"block": "text_card"}, {"block": "flash"}], "frames": [[0, 1.0, 0], [3, 1.25, 0]]},
                  open(os.path.join(d, "timeline.json"), "w"), ensure_ascii=False)
        api = self.api
        self.assertFalse(api.save_performance("2026-11-01-stock", {"platform": "x", "when": "48h", "views": 5})[0])
        self.assertFalse(api.save_performance("2026-11-01-stock", {"platform": "tiktok", "when": "48h"})[0])          # views needed
        self.assertFalse(api.save_performance("2026-11-01-stock", {"platform": "tiktok", "when": "48h", "views": "abc"})[0])
        self.assertFalse(api.save_performance("2026-11-01-stock", {"platform": "tiktok", "when": "48h", "views": 9, "full_pct": 140})[0])
        self.assertFalse(api.save_performance("../x", {"platform": "tiktok", "when": "48h", "views": 9})[0])
        ok, _ = api.save_performance("2026-11-01-stock", {"platform": "instagram", "when": "48h", "views": "12,000", "avg_watch_s": "20", "saves": "60"})
        self.assertTrue(ok)
        api.save_performance("2026-11-01-stock", {"platform": "instagram", "when": "48h", "views": 13000})            # same slot replaces
        api.save_performance("2026-11-01-stock", {"platform": "instagram", "when": "7d", "views": 20000, "avg_watch_s": 25, "saves": 100})
        r = api.performance("2026-11-01-stock")[0]
        self.assertEqual(len(r["entries"]), 2)
        e = [x for x in r["entries"] if x["when"] == "7d"][0]
        self.assertEqual((e["watch_pct"], e["saves_per_1k"]), (50.0, 5.0))
        self.assertEqual((r["facts"]["moments"], r["facts"]["zooms"], r["facts"]["hook_chars"]), (2, 1, 18))
        csv_ = api.performance_csv().splitlines()
        self.assertEqual(len(csv_), 3); self.assertIn("2026-11-01-stock,instagram,7d,20000", csv_[2])


class SpendTests(ApiTest):
    def test_spend_by_step_model_and_projection(self):
        from datetime import date
        m = date.today().isoformat()[:7]
        for job, calls in ((m + "-01-a", [{"stage": "fix", "model": "anthropic/claude-haiku-5.5", "cost": 0.01},
                                           {"stage": "plan", "model": "anthropic/claude-haiku-5.5", "cost": 0.02}]),
                           (m + "-02-b", [{"stage": "repair", "model": "anthropic/claude-sonnet-5.5", "cost": 0.05}])):
            d = os.path.join(self.root, "jobs", job); os.makedirs(d)
            json.dump({"calls": calls}, open(os.path.join(d, "cost.json"), "w"))
        s = self.api.spend()
        self.assertAlmostEqual(s["total"], 0.08); self.assertEqual(s["reels"], 2); self.assertAlmostEqual(s["per_reel"], 0.04)
        steps = {x["name"]: x["amount"] for x in s["by_step"]}
        self.assertEqual(steps["Repairing the plan"], 0.05); self.assertEqual(steps["Planning the edit"], 0.02)
        self.assertEqual({x["name"] for x in s["by_model"]}, {"claude-haiku-5.5", "claude-sonnet-5.5"})
        self.assertGreaterEqual(s["projection"], 0.08)


if __name__ == "__main__":
    unittest.main()


class HomeAndDropApi(unittest.TestCase):
    """The Iraqi home page: its data comes from files the pipeline already wrote."""
    def test_live_reads_the_plan_and_the_cuts(self):
        import json, tempfile, importlib
        root = tempfile.mkdtemp()
        job = os.path.join(root, "jobs", "2026-11-06-tips-one"); os.makedirs(os.path.join(job, "review"))
        json.dump({"duration": 20, "scenes": [{"id": "a", "block": "info_card", "t_in": 2, "t_out": 5}, {"id": "b", "block": "number_graph", "t_in": 8, "t_out": 11},
                                              {"id": "c", "block": "captions", "t_in": 0, "t_out": 20}]}, open(os.path.join(job, "timeline.json"), "w"))
        json.dump({"segments": [{"t_in": 0, "t_out": 9}, {"t_in": 9, "t_out": 20}], "cut_log": [{"kind": "retake", "reel_t": 9, "src_from": 9, "src_to": 11}]}, open(os.path.join(job, "edl.json"), "w"))
        old = os.environ.get("RF_ROOT"); os.environ["RF_ROOT"] = root
        self.addCleanup(lambda: os.environ.__setitem__("RF_ROOT", old) if old else os.environ.pop("RF_ROOT", None))
        import reels_api, live_api
        importlib.reload(reels_api); importlib.reload(live_api)
        d = live_api.live()
        self.assertEqual(d["job"], "2026-11-06-tips-one")
        self.assertEqual(len(d["tracks"]["card"]), 1); self.assertEqual(len(d["tracks"]["motion"]), 1); self.assertEqual(len(d["tracks"]["caption"]), 1)
        self.assertEqual(d["cut_kinds"], {"retake": 1}); self.assertEqual(d["removed_s"], 2.0)
        self.assertEqual(live_api.live("../../etc")["job"], None)

    def test_drop_status_when_off(self):
        import drop_api
        s = drop_api.status()
        self.assertFalse(s["watching"]); self.assertTrue(s["path"].endswith("Reel Factory Drop"))
