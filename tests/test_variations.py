import json, os, sys, tempfile, types, unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from lib import variations as v  # noqa: E402
import reel  # noqa: E402


def source():
    base = tempfile.mkdtemp(); job = "2026-11-02-my-reel"; d = os.path.join(base, job); os.makedirs(os.path.join(d, "assets"))
    open(os.path.join(d, "proxy.mp4"), "wb").write(b"video-bytes")
    W = lambda n, x: json.dump(x, open(os.path.join(d, n), "w"), ensure_ascii=False)
    W("transcript.json", [{"text": "كلمة", "start": i * 0.5, "end": i * 0.5 + 0.4} for i in range(200)])
    W("selects.json", {"selects": [{"id": "A", "range": [0, 60], "label": "main story", "style": "educational", "score": 8},
                                   {"id": "B", "range": [20, 70], "label": "second story", "style": "fast", "score": 6.5},
                                   {"id": "C", "range": [40, 90], "label": "third story", "style": "storytelling", "score": 5}]})
    W("chosen_select.json", {"id": "A", "range": [0, 60]}); W("job.json", {"id": job, "status": "preview_ready", "feedback_history": [{"fix": "x"}], "selects": []})
    W("cost.json", {"calls": [{"stage": "selects", "cost": 0.01}, {"stage": "shotlog", "cost": 0.08}, {"stage": "plan", "cost": 0.02}]})
    open(os.path.join(d, "assets", "logo.svg"), "w").write("<svg/>")
    return base, job, d


class VariationTests(unittest.TestCase):
    def test_alternatives_estimate_and_naming(self):
        base, job, d = source()
        self.assertEqual([a["id"] for a in v.alternatives(d)], ["B", "C"])
        self.assertEqual(v.estimate(d), 0.1)                                   # shot log + plan, not the story pick
        self.assertEqual(v.next_name(base, job), "2026-11-02-my-reel-alt1")
        os.makedirs(os.path.join(base, "2026-11-02-my-reel-alt1")); self.assertEqual(v.next_name(base, "2026-11-02-my-reel-alt1"), "2026-11-02-my-reel-alt2")
        self.assertEqual(v.estimate(tempfile.mkdtemp()), 0.05)

    def test_prepare_shares_the_footage_and_leaves_the_first_reel_alone(self):
        base, job, d = source()
        before = open(os.path.join(d, "job.json")).read()
        name = v.prepare(base, job, "B")
        n = os.path.join(base, name)
        self.assertEqual(os.stat(os.path.join(n, "proxy.mp4")).st_ino, os.stat(os.path.join(d, "proxy.mp4")).st_ino)       # no extra disk space
        j = json.load(open(os.path.join(n, "job.json")))
        self.assertEqual((j["variation_of"], j["selects"][0]["id"], j["selects"][0]["range"], j["feedback_history"]), (job, "B", [20, 70], []))
        self.assertTrue(os.path.exists(os.path.join(n, "assets", "logo.svg"))); self.assertTrue(os.path.exists(os.path.join(n, "transcript.json")))
        self.assertEqual(open(os.path.join(d, "job.json")).read(), before)                                                  # the first reel is untouched
        for bad in ("A", "Z", None):
            with self.assertRaises(ValueError):
                v.prepare(base, job, bad)

    def test_the_story_step_uses_the_chosen_version_without_asking_the_ai(self):
        base, job, d = source()
        n = os.path.join(base, v.prepare(base, job, "C"))
        c = reel.Ctx(n, types.SimpleNamespace(select=None, fresh_selects=False, effort="low", budget=5, img_tok=800))
        with mock.patch.object(reel, "proxy_duration", return_value=300.0), mock.patch.object(c, "llm", side_effect=AssertionError("no AI call expected")):
            reel.st_selects(c)
        ch = json.load(open(os.path.join(n, "chosen_select.json")))
        self.assertEqual((ch["id"], ch["range"]), ("C", [40, 90]))


if __name__ == "__main__":
    unittest.main()
