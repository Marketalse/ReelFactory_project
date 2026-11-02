import os, sys, tempfile, threading, time, types, unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import reel  # noqa: E402


def ctx(budget=5.0, **kw):
    job = tempfile.mkdtemp()
    a = types.SimpleNamespace(stop_after=kw.get("stop_after"), replan=kw.get("replan", False), budget=budget, img_tok=800)
    return reel.Ctx(job, a), a, job


class OverlapTests(unittest.TestCase):
    def funcs(self, delays=None, boom=None):
        out = {}
        for s in reel.STAGES:
            def f(c, s=s):
                time.sleep((delays or {}).get(s, 0))
                if boom == s:
                    raise reel.Stop("vision down")
                return s + " done"
            out[s] = f
        return out

    def test_shot_log_and_plan_run_side_by_side(self):
        c, a, job = ctx()
        t = time.time()
        with mock.patch.object(reel, "FUNCS", self.funcs({"shotlog": 0.5, "plan": 0.5})):
            # the real st_plan joins the shot log itself; the fake one does it here
            real = reel.FUNCS["plan"]
            reel.FUNCS["plan"] = lambda c, real=real: (real(c), reel.join_shots(c))[0]
            self.assertTrue(reel.run_stages(c, a, job))
        self.assertLess(time.time() - t, 0.9)                          # 1.0 s if they ran one after the other
        self.assertIsNone(getattr(c, "shot_thread", None)); self.assertIn("shotlog", c.timing)

    def test_a_failing_shot_log_stops_the_reel_with_its_own_message(self):
        c, a, job = ctx()
        with mock.patch.object(reel, "FUNCS", self.funcs({"plan": 0.1}, boom="shotlog")):
            with self.assertRaises(reel.Stop) as cm:
                reel.run_stages(c, a, job)
        self.assertIn("vision down", str(cm.exception))

    def test_no_overlap_when_either_is_cached_or_asked_to_stop(self):
        c, a, job = ctx()
        self.assertTrue(reel.can_overlap_shotlog(c, a))
        open(os.path.join(job, "shot_log.json"), "w").write("[]")
        self.assertFalse(reel.can_overlap_shotlog(c, a))
        os.remove(os.path.join(job, "shot_log.json")); open(os.path.join(job, "timeline.json"), "w").write("{}")
        self.assertFalse(reel.can_overlap_shotlog(c, a))
        a.replan = True; self.assertTrue(reel.can_overlap_shotlog(c, a))                  # a re-plan with a missing shot log may overlap
        a.stop_after = "shotlog"; self.assertFalse(reel.can_overlap_shotlog(c, a))

    def test_plan_error_still_waits_for_the_shot_log_thread(self):
        c, a, job = ctx()
        ran = []
        fs = self.funcs()
        fs["shotlog"] = lambda c: (time.sleep(0.3), ran.append("shot"))[1]
        fs["plan"] = lambda c: (_ for _ in ()).throw(reel.Stop("plan broke"))
        with mock.patch.object(reel, "FUNCS", fs):
            with self.assertRaises(reel.Stop):
                reel.run_stages(c, a, job)
        self.assertEqual(ran, ["shot"])                                                    # the paid call was not abandoned mid-way


class BudgetWhileInFlightTests(unittest.TestCase):
    def test_second_call_is_counted_against_the_first_one_in_flight(self):
        c, a, job = ctx(budget=0.5)
        gate, started = threading.Event(), threading.Event()
        resp = {"usage": {"prompt_tokens": 1, "completion_tokens": 1, "cost": 0.0}, "choices": [{"finish_reason": "stop", "message": {"content": "{}"}}]}
        def slow_post(req, stage, **k):
            started.set(); gate.wait(5); return resp
        with mock.patch.object(reel, "nous", return_value=("http://x", "k")), mock.patch.object(reel, "post_with_retry", side_effect=slow_post), \
             mock.patch.object(reel.cfg, "price", return_value=(0.0, 1.0)), mock.patch.object(reel.cfg, "month_spent", return_value=0.0):
            t = threading.Thread(target=lambda: c.llm("a", "m/x", [{"type": "text", "text": "hi"}], 400000))      # worst case $0.40
            t.start(); self.assertTrue(started.wait(5))
            with self.assertRaises(reel.Stop) as cm:                                                              # $0.40 + $0.40 > $0.50
                c.llm("b", "m/x", [{"type": "text", "text": "hi"}], 400000)
            self.assertIn("BUDGET GUARD", str(cm.exception))
            gate.set(); t.join(5)
            self.assertEqual(c._reserved, 0.0)                                                                    # released after the call
            self.assertEqual(c.llm("c", "m/x", [{"type": "text", "text": "hi"}], 400000), "{}")                  # fine once the first is done


if __name__ == "__main__":
    unittest.main()
