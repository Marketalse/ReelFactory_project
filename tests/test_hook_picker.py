import json, os, sys, tempfile, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts")); sys.path.insert(0, os.path.join(ROOT, "dashboard"))
import reels_api  # noqa: E402
from lib import edl as edlmod  # noqa: E402


def make_job(base):
    job = "2026-11-02-hooks"
    d = os.path.join(base, job); os.makedirs(os.path.join(d, "review"))
    words = [{"text": t, "start": round(i * 0.45, 2), "end": round(i * 0.45 + 0.38, 2)} for i, t in enumerate(
        "اهلا بكم اليوم نحچي عن المتجر الالكتروني وكيف تبدأ بدون راس مال وبدون خبرة سابقة ابدا مع هذه الطريقة السهلة".split() * 6)]
    W = lambda n, x: json.dump(x, open(os.path.join(d, n), "w"), ensure_ascii=False)
    W("transcript.json", words); W("chosen_select.json", {"id": "A", "range": [0.0, 40.0]})
    e = edlmod.build(words, 0.0, 40.0, drop=[], keep=[], texts={})
    W("edl.json", e)
    W("scene_plan.json", {"hook": {"line1": "قديم", "line2": "عنوان"}, "keyword_ids": [], "moments": [], "punch_ins": [], "cta": {}, "cover": {}})
    W("timeline.json", {"duration": e["duration"], "scenes": [], "punch_ins": [], "keyword_ids": [], "caption_gaps": []})
    W("editorial.json", {"hooks": [{"type": "curiosity", "line": "سر لا يعرفه أحد", "found": False},
                                   {"type": "problem", "line": "نحچي عن المتجر الالكتروني وكيف تبدأ بدون", "found": True},
                                   {"type": "direct", "line": "اهلا بكم اليوم", "found": True}]})
    return job, d


class HookPickerTests(unittest.TestCase):
    def test_pick_sets_the_title_from_his_words_and_rebuilds_for_free(self):
        base = tempfile.mkdtemp(); job, d = make_job(base)
        ran = []
        with mock.patch.object(reels_api, "JOBS", base), mock.patch.object(reels_api, "_run", side_effect=lambda k, a, **kw: ran.append(a) or (True, "started")):
            ok, msg = reels_api.use_hook(job, 0)                       # index 0 = the first FOUND hook (the invented one is hidden)
        self.assertTrue(ok, msg)
        hook = json.load(open(os.path.join(d, "scene_plan.json")))["hook"]
        spoken = set("اهلا بكم اليوم نحچي عن المتجر الالكتروني وكيف تبدأ بدون راس مال".split())
        self.assertTrue(set((hook["line1"] + " " + hook["line2"]).split()) <= spoken)           # only words he said
        self.assertNotEqual(hook["line1"], "قديم")
        tl = json.load(open(os.path.join(d, "timeline.json")))
        h = next(s for s in tl["scenes"] if s["block"] == "hook_two_tone")
        self.assertEqual(h["values"]["line1"], hook["line1"])
        self.assertEqual(ran, [[d, "--rebuild"]])                                                # no AI: the free rebuild path

    def test_bad_index_and_busy_job(self):
        base = tempfile.mkdtemp(); job, d = make_job(base)
        with mock.patch.object(reels_api, "JOBS", base), mock.patch.object(reels_api, "_run", return_value=(True, "x")):
            self.assertFalse(reels_api.use_hook(job, 9)[0]); self.assertFalse(reels_api.use_hook(job, "x")[0])
            self.assertFalse(reels_api.use_hook("not-a-job", 0)[0])


if __name__ == "__main__":
    unittest.main()
