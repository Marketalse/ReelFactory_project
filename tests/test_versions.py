import json, os, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from lib import versions as v  # noqa: E402


def job(draft=b"v1", qa=None):
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "review"))
    open(os.path.join(d, "review", "draft_540p.mp4"), "wb").write(draft)
    W = lambda n, x: json.dump(x, open(os.path.join(d, n), "w"))
    W("timeline.json", {"duration": 50, "scenes": [1, 2]}); W("edl.json", {"words": []}); W("job.json", {"feedback_history": [{"fix": "hook shorter"}]})
    W("qa.json", qa or {"errors": [], "warnings": ["w1"], "metrics": {"duration": 50, "lufs": -14}})
    return d


class VersionTests(unittest.TestCase):
    def test_versions_are_kept_and_restorable(self):
        d = job(b"first")
        self.assertEqual(v.save(d)["n"], 1)
        json.dump({"duration": 60, "scenes": []}, open(os.path.join(d, "timeline.json"), "w"))
        open(os.path.join(d, "review", "draft_540p.mp4"), "wb").write(b"second")
        self.assertEqual(v.save(d, "bigger captions")["n"], 2)
        self.assertEqual([r["note"] for r in v.listing(d)], ["hook shorter", "bigger captions"])
        ok, msg = v.restore(d, 1)
        self.assertTrue(ok, msg)
        self.assertEqual(open(os.path.join(d, "review", "draft_540p.mp4"), "rb").read(), b"first")
        self.assertEqual(json.load(open(os.path.join(d, "timeline.json")))["duration"], 50)
        self.assertTrue(os.path.exists(os.path.join(d, "review", "versions", "v2.mp4")))                # nothing deleted
        self.assertIn("went back to version 1", json.load(open(os.path.join(d, "job.json")))["feedback_history"][-1]["fix"])

    def test_unknown_version_and_missing_draft(self):
        d = job(); v.save(d)
        self.assertFalse(v.restore(d, 9)[0])
        self.assertIsNone(v.save(tempfile.mkdtemp()))

    def test_manual_edit_of_a_later_version_is_set_aside_not_deleted(self):
        d = job(); v.save(d)
        json.dump({"drop": [1]}, open(os.path.join(d, "manual_edit.json"), "w")); v.save(d, "my edit")
        self.assertTrue(v.restore(d, 1)[0])
        self.assertFalse(os.path.exists(os.path.join(d, "manual_edit.json")))
        self.assertTrue(os.path.exists(os.path.join(d, "manual_edit.json.before-v1")))

    def test_summary_and_report_in_plain_words(self):
        d = job()
        json.dump({"checks": ["captions too fast"]}, open(os.path.join(d, "visual_plan.json"), "w"))
        s = v.summary(d)
        self.assertEqual(s["verdict"], "Passed with notes"); self.assertIn("Look: captions too fast", s["notes"])
        p = v.write_report(d)
        txt = open(p).read()
        self.assertIn("Passed with notes", txt); self.assertIn("w1", txt)
        bad = job(qa={"errors": ["black screen 3s"], "warnings": []})
        self.assertEqual(v.summary(bad)["verdict"], "Needs attention")
        self.assertIn("black screen 3s", open(v.write_report(bad)).read())
        clean = job(qa={"errors": [], "warnings": []})
        self.assertEqual(v.summary(clean)["verdict"], "Passed")
        self.assertIsNone(v.summary(tempfile.mkdtemp()))


if __name__ == "__main__":
    unittest.main()
