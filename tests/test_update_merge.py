"""Updating keeps your task-board changes, and names any other changed file. Real git, temp folders, no network. Free."""
import json, os, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts")); sys.path.insert(0, os.path.join(ROOT, "dashboard"))
from lib import board_merge  # noqa: E402

B = lambda *ts: {"tasks": [{"id": i, "status": s, "notes": n} for i, s, n in ts], "log": []}


class MergeTests(unittest.TestCase):
    def test_merge3(self):
        base = B(("T1", "review", ""), ("T2", "todo", ""), ("T3", "todo", ""))
        mine = B(("T1", "done", ""), ("T2", "todo", "my note"), ("T3", "in_progress", ""), ("T9", "todo", "mine only"))
        theirs = B(("T1", "review", "new note"), ("T2", "review", ""), ("T3", "blocked", ""), ("T4", "todo", ""))
        out = {t["id"]: t for t in board_merge.merge3(base, mine, theirs)["tasks"]}
        self.assertEqual(out["T1"]["status"], "done"); self.assertEqual(out["T1"]["notes"], "new note")   # your done kept + their note
        self.assertEqual(out["T2"]["status"], "review"); self.assertEqual(out["T2"]["notes"], "my note")  # their status + your note
        self.assertEqual(out["T3"]["status"], "blocked")                                                   # both changed: theirs
        self.assertIn("T4", out); self.assertIn("T9", out)


def git(d, *a):
    return subprocess.run(["git", "-C", d, "-c", "user.email=t@t", "-c", "user.name=t", *a], capture_output=True, text=True, check=True)


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp(); self.origin = os.path.join(self.t, "origin"); self.mac = os.path.join(self.t, "mac")
        os.makedirs(os.path.join(self.origin, "dashboard")); git(self.origin, "init", "-q", "-b", "main")
        self.put(self.origin, B(("T1", "review", ""), ("T2", "todo", ""))); open(os.path.join(self.origin, "a.txt"), "w").write("1")
        git(self.origin, "add", "-A"); git(self.origin, "commit", "-qm", "one")
        subprocess.run(["git", "clone", "-q", self.origin, self.mac], check=True)
        import settings_api
        self.api = settings_api; settings_api.ROOT = self.mac
        self.home = os.environ.get("HOME"); os.environ["HOME"] = self.t

    def tearDown(self):
        os.environ["HOME"] = self.home

    def put(self, d, data):
        json.dump(data, open(os.path.join(d, "dashboard", "tasks.json"), "w"), indent=1)

    def push_new(self, board=None):
        if board: self.put(self.origin, board)
        open(os.path.join(self.origin, "a.txt"), "w").write("2"); git(self.origin, "add", "-A"); git(self.origin, "commit", "-qm", "two")

    def test_board_changed_on_both_sides_is_merged(self):
        self.put(self.mac, B(("T1", "done", ""), ("T2", "todo", "")))                    # you marked T1 done
        self.push_new(B(("T1", "review", ""), ("T2", "review", "")))                       # new version changes the board too
        ok, msg, restart = self.api.update({})
        self.assertTrue(ok, msg); self.assertTrue(restart)
        got = {t["id"]: t["status"] for t in json.load(open(os.path.join(self.mac, "dashboard", "tasks.json")))["tasks"]}
        self.assertEqual(got, {"T1": "done", "T2": "review"})
        self.assertEqual(open(os.path.join(self.mac, "a.txt")).read(), "2")

    def test_other_changed_file_is_named_and_nothing_is_lost(self):
        open(os.path.join(self.mac, "a.txt"), "w").write("mine"); self.push_new()
        ok, msg, restart = self.api.update({})
        self.assertFalse(ok); self.assertIn("a.txt", msg)
        self.assertEqual(open(os.path.join(self.mac, "a.txt")).read(), "mine")


if __name__ == "__main__":
    unittest.main()
