"""Backup to Google Drive / iCloud Drive: only small text files, never videos or keys; old ZIPs pruned."""
import json, os, sys, tempfile, unittest, zipfile
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "dashboard"))
import backup_api as b  # noqa: E402


def touch(p, data="x"):
    os.makedirs(os.path.dirname(p), exist_ok=True); open(p, "w").write(data)


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory(); d = self.t.name
        self.home, self.root = os.path.join(d, "home"), os.path.join(d, "proj")
        p = mock.patch.object(b, "STATE", os.path.join(self.home, ".reelfactory", "backup.json")); p.start(); self.addCleanup(p.stop)
        self.addCleanup(self.t.cleanup)
        j = os.path.join(self.root, "jobs", "2026-11-01-stock")
        for f in ("job.json", "performance.json", "timeline.json", "review/report.md", "run.log"):
            touch(os.path.join(j, f), "{}")
        for f in ("proxy.mp4", "review/draft_540p.mp4", "review/cover.jpg", "hyperframes/index.html", "hyperframes/x.json"):
            touch(os.path.join(j, f))
        touch(os.path.join(self.root, "config", "brand.json"), "{}"); touch(os.path.join(self.root, "dashboard", "tasks.json"), "{}")
        touch(os.path.join(self.root, ".reel-agent", "lessons.md")); touch(os.path.join(self.root, "inbox", "stock", "brief.md"))
        touch(os.path.join(self.root, "inbox", "stock", "clips", "a.MOV"))

    def test_no_cloud_folder_is_explained(self):
        ok, msg = b.run(self.root, home=self.home)
        self.assertFalse(ok); self.assertIn("Google Drive", msg)

    def test_backup_keeps_text_skips_media_and_prunes(self):
        gd = os.path.join(self.home, "Library", "CloudStorage", "GoogleDrive-me@x.com", "My Drive"); os.makedirs(gd)
        os.makedirs(os.path.join(self.home, "Library", "Mobile Documents", "com~apple~CloudDocs"))
        self.assertEqual([t["label"] for t in b.targets(self.home)], ["Google Drive (me@x.com)", "iCloud Drive"])
        ok, msg = b.run(self.root, home=self.home, now=1_800_000_000)
        self.assertTrue(ok, msg)
        dest = os.path.join(gd, b.FOLDER); zips = [f for f in os.listdir(dest) if f.endswith(".zip")]
        self.assertEqual(len(zips), 1)
        names = zipfile.ZipFile(os.path.join(dest, zips[0])).namelist()
        for want in ("jobs/2026-11-01-stock/performance.json", "jobs/2026-11-01-stock/job.json", "jobs/2026-11-01-stock/review/report.md",
                     "config/brand.json", "dashboard/tasks.json", ".reel-agent/lessons.md", "inbox/stock/brief.md"):
            self.assertIn(want, names)
        self.assertFalse([n for n in names if n.endswith((".mp4", ".jpg", ".MOV", ".html")) or "/hyperframes/" in n], names)
        st = b.status(self.home); self.assertTrue(st["last"]); self.assertFalse(b.due(now=1_800_000_000 + 3600))
        self.assertTrue(b.due(now=1_800_000_000 + 25 * 3600))
        for k in range(b.KEEP + 3):                                     # only the newest KEEP stay
            b.run(self.root, home=self.home, now=1_800_000_000 + (k + 1) * 60)
        self.assertEqual(len([f for f in os.listdir(dest) if b.NAME.match(f)]), b.KEEP)
        ok, _ = b.run(self.root, target="icloud", home=self.home)        # switch place
        self.assertTrue(ok); self.assertEqual(b.status(self.home)["target"], "icloud")
        self.assertFalse(b.run(self.root, target="nowhere", home=self.home)[0])

    def test_auto_can_be_turned_off(self):
        b.set_auto(False); self.assertFalse(b.due())
        b.set_auto(True); self.assertTrue(b.due())
