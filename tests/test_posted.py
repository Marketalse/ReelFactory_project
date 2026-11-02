import json, os, sys, tempfile, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts")); sys.path.insert(0, os.path.join(ROOT, "dashboard"))
import reels_api  # noqa: E402


class PostedTests(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp(); self.job = "2026-11-02-demo"; os.makedirs(os.path.join(self.base, self.job))
        p = mock.patch.object(reels_api, "JOBS", self.base); p.start(); self.addCleanup(p.stop)

    def test_posted_is_saved_per_platform_and_results_keep_it(self):
        self.assertFalse(reels_api.save_posted("nope", "instagram")[0]); self.assertFalse(reels_api.save_posted(self.job, "youtube")[0])
        self.assertTrue(reels_api.save_posted(self.job, "instagram")[0]); self.assertTrue(reels_api.save_posted(self.job, "tiktok")[0])
        self.assertTrue(reels_api.save_posted(self.job, "instagram")[0])                                   # posting again replaces, never duplicates
        d = json.load(open(os.path.join(self.base, self.job, "performance.json")))
        self.assertEqual(sorted(x["platform"] for x in d["posted"]), ["instagram", "tiktok"])
        ok, msg = reels_api.save_performance(self.job, {"platform": "instagram", "when": "48h", "views": "1200"})
        self.assertTrue(ok, msg)
        d = json.load(open(os.path.join(self.base, self.job, "performance.json")))
        self.assertEqual(len(d["posted"]), 2); self.assertEqual(d["entries"][0]["views"], 1200)           # saving numbers must not lose the 'posted' marks

    def test_the_page_only_shows_the_results_form_after_posting(self):
        html = open(os.path.join(ROOT, "dashboard", "make.html"), encoding="utf-8").read()
        before = html[html.index("function perfBlock"):html.index("async function loadPerf")]
        self.assertIn("I posted it", before); self.assertIn("if(!posted.length) return", before)
        self.assertLess(before.index("if(!posted.length)"), before.index('id="pfSave"'))                  # the numbers form comes after the 'not posted yet' branch


if __name__ == "__main__":
    unittest.main()
