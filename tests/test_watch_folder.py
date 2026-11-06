import json, os, sys, tempfile, unittest, types
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import watch_folder as wf


class DropFolder(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp()
        self.drop = os.path.join(self.t, "drop")
        wf.INBOX = os.path.join(self.t, "inbox"); wf.JOBS = os.path.join(self.t, "jobs")
        wf.STATE_DIR = os.path.join(self.t, "state"); wf.STATUS = os.path.join(wf.STATE_DIR, "s.json")
        os.makedirs(wf.INBOX); os.makedirs(wf.JOBS)
        wf.setup(self.drop)
        wf.notify = lambda text: None

    def clip(self, name, data=b"x" * 50):
        p = os.path.join(self.drop, name); open(p, "wb").write(data); return p

    def runner(self, ok=True):
        def run(cmd):
            slug = cmd[cmd.index("--slug") + 1]
            job = os.path.join(wf.JOBS, "2026-11-06-" + slug)
            os.makedirs(os.path.join(job, "review"))
            if ok:
                open(os.path.join(job, "review", "draft_540p.mp4"), "wb").write(b"d")
                json.dump({"qa": {"warnings": ["caption small"]}}, open(os.path.join(job, "review", "draft.json"), "w"))
            else:
                open(os.path.join(job, "run.log"), "w").write("STOP: no credit\n")
            return types.SimpleNamespace(stdout="")
        return run

    def test_slug(self):
        self.assertEqual(wf.slugify("My Clip 01.MOV"), "my-clip-01")
        self.assertEqual(wf.slugify("فيديو.mov"), "reel")
        self.assertEqual(wf.slugify("a.mov", taken={"a"}), "reel")

    def test_items_skip_folders_and_hidden(self):
        self.clip("a.mov"); self.clip(".hid.mov"); self.clip("notes.txt")
        self.assertEqual([os.path.basename(p) for _, p in wf.items(self.drop)], ["a.mov"])

    def test_good_reel(self):
        self.clip("tips one.mov")
        st = wf.run(once=True, runner=self.runner(True), sleep=lambda s: None, drop=self.drop)
        self.assertEqual(st["ready"], ["tips one"])
        self.assertTrue(os.path.exists(os.path.join(self.drop, "Ready", "tips one.mp4")))
        self.assertIn("caption small", open(os.path.join(self.drop, "Ready", "tips one.txt")).read())
        self.assertTrue(os.path.exists(os.path.join(self.drop, "Done", "tips one.mov")))   # original kept
        self.assertFalse(os.path.exists(os.path.join(self.drop, "tips one.mov")))
        self.assertTrue(os.path.exists(os.path.join(wf.INBOX, "tips-one", "tips one.mov")))

    def test_failure_tried_once(self):
        self.clip("bad.mov")
        st = wf.run(once=True, runner=self.runner(False), sleep=lambda s: None, drop=self.drop)
        self.assertEqual(st["failed"], ["bad"])
        self.assertIn("no credit", open(os.path.join(self.drop, "Ready", "bad_PROBLEM.txt")).read())
        self.assertTrue(os.path.exists(os.path.join(self.drop, "Done", "bad.mov")))

    def test_folder_is_one_reel(self):
        d = os.path.join(self.drop, "story"); os.makedirs(d)
        open(os.path.join(d, "1.mov"), "wb").write(b"a" * 9); open(os.path.join(d, "2.mov"), "wb").write(b"b" * 9)
        st = wf.run(once=True, runner=self.runner(True), sleep=lambda s: None, drop=self.drop)
        self.assertEqual(st["ready"], ["story"])
        self.assertEqual(sorted(os.listdir(os.path.join(wf.INBOX, "story"))), ["1.mov", "2.mov"])

    def test_growing_file_waits(self):
        p = self.clip("a.mov"); n = {"i": 0}
        def sleep(s):
            n["i"] += 1; open(p, "ab").write(b"y")
        self.assertFalse(wf.is_stable(p, sleep=sleep))


if __name__ == "__main__":
    unittest.main()
