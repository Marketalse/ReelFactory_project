import json, os, subprocess, sys, tempfile, types, unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from lib import broll_ai as ba  # noqa: E402
import reel  # noqa: E402


def make_root(files=("ads_dashboard.png", "invoice.png"), svg=True):
    root = tempfile.mkdtemp(); d = os.path.join(root, "library", "broll"); os.makedirs(d)
    for i, n in enumerate(files):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size=320x200:rate=1:duration=1", "-vf", f"hue=h={i * 60}", "-frames:v", "1", os.path.join(d, n)], check=True)
    if svg:
        open(os.path.join(d, "logo.svg"), "w").write("<svg xmlns='http://www.w3.org/2000/svg'/>")
    return root


WORDS = [{"text": "اعلانات", "start": 0, "end": .5}, {"text": "فاتورة", "start": 1, "end": 1.5}]


class PieceTests(unittest.TestCase):
    def test_pending_cache_and_changes(self):
        root = make_root()
        self.assertEqual(ba.pending(root), ["ads_dashboard.png", "invoice.png"])                 # the svg is not described by a vision model
        content, sent = ba.describe_content(root, ba.pending(root))
        self.assertEqual(sent, ["ads_dashboard.png", "invoice.png"]); self.assertEqual(sum(1 for c in content if c["type"] == "image_url"), 2)
        self.assertTrue(content[2]["image_url"]["url"].startswith("data:image/jpeg;base64,"))
        rows = [{"file": "ads_dashboard.png", "desc": "an ads dashboard", "tags": ["ads", "إعلانات"], "kind": "screenshot"}, {"file": "ghost.png", "desc": "x"}, {"file": "invoice.png", "desc": ""}]
        new = ba.clean_descriptions(rows, sent)
        self.assertEqual(list(new), ["ads_dashboard.png"])                                       # unknown file and empty description are dropped
        ba.save(root, new)
        self.assertEqual(ba.pending(root), ["invoice.png"])
        open(os.path.join(root, "library", "broll", "ads_dashboard.png"), "ab").write(b"changed")
        self.assertIn("ads_dashboard.png", ba.pending(root))                                     # a changed file is described again

    def test_picks_only_from_the_library(self):
        cat = [{"file": "a.png", "desc": "d", "tags": [], "kind": "photo"}]
        self.assertEqual(ba.clean_picks({"picks": [{"file": "a.png", "why": "x"}, {"file": "evil.png", "why": "y"}, {"file": "a.png", "why": "again"}]}, cat), [{"file": "a.png", "why": "x"}])
        self.assertEqual(ba.clean_picks("junk", cat), []); self.assertEqual(ba.brief_note([], cat), "")


class StepTests(unittest.TestCase):
    def ctx(self):
        job = tempfile.mkdtemp()
        return reel.Ctx(job, types.SimpleNamespace(budget=5, img_tok=800)), job

    def test_describes_once_then_picks_per_reel_and_copies_into_assets(self):
        root = make_root(); calls = []
        def fake(stage, model, content, mt, effort="low", **k):
            calls.append(stage)
            if stage == "broll_describe":
                return json.dumps([{"file": "ads_dashboard.png", "desc": "an ads dashboard with charts", "tags": ["ads"], "kind": "screenshot"},
                                   {"file": "invoice.png", "desc": "an invoice document", "tags": ["invoice"], "kind": "document"}])
            return json.dumps({"picks": [{"file": "ads_dashboard.png", "why": "he talks about ads"}, {"file": "not_in_library.png", "why": "x"}]})
        c, job = self.ctx()
        with mock.patch.object(c, "llm", side_effect=fake):
            got, note = reel.broll_ai_step(c, WORDS, root)
        self.assertEqual(calls, ["broll_describe", "broll_pick"]); self.assertEqual(got, ["ads_dashboard.png"])
        self.assertTrue(os.path.exists(os.path.join(job, "assets", "ads_dashboard.png"))); self.assertIn("an ads dashboard with charts", note)
        self.assertFalse(os.path.exists(os.path.join(job, "assets", "not_in_library.png")))
        c2, job2 = self.ctx(); calls.clear()
        with mock.patch.object(c2, "llm", side_effect=fake):
            got2, _ = reel.broll_ai_step(c2, WORDS, root)
        self.assertEqual(calls, ["broll_pick"])                                                  # descriptions are cached: only the small pick call

    def test_no_pictures_or_switched_off_means_no_ai_call(self):
        c, job = self.ctx()
        with mock.patch.object(c, "llm", side_effect=AssertionError("no call expected")):
            self.assertEqual(reel.broll_ai_step(c, WORDS, make_root(files=(), svg=True)), ([], ""))
            self.assertEqual(reel.broll_ai_step(c, WORDS, tempfile.mkdtemp()), ([], ""))
            with mock.patch.dict(reel.cfg.PROJECT, {"broll_ai": {"enabled": False}}):
                self.assertEqual(reel.broll_ai_step(c, WORDS, make_root()), ([], ""))

    def test_a_failing_ai_answer_never_stops_the_reel_but_the_money_guard_does(self):
        c, job = self.ctx(); root = make_root()
        with mock.patch.object(c, "llm", return_value="not json at all"):
            self.assertEqual(reel.broll_ai_step(c, WORDS, root), ([], ""))
        with mock.patch.object(c, "llm", side_effect=reel.Stop("BUDGET GUARD: x")):
            with self.assertRaises(reel.Stop):
                reel.broll_ai_step(c, WORDS, root)


if __name__ == "__main__":
    unittest.main()
