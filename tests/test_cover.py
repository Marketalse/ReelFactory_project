"""Cover image: text only from his words, his own image wins, uploads are checked."""
import io, json, os, shutil, sys, tempfile, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts")); sys.path.insert(0, os.path.join(ROOT, "dashboard"))
import cover


class CoverValueTests(unittest.TestCase):
    def job(self, plan, words):
        d = tempfile.mkdtemp()
        json.dump(plan, open(os.path.join(d, "scene_plan.json"), "w"), ensure_ascii=False)
        json.dump({"words": [{"text": t, "start": 0, "end": 1} for t in words]}, open(os.path.join(d, "edl.json"), "w"), ensure_ascii=False)
        return d

    def test_spoken_numbers_kept_unspoken_dropped(self):
        d = self.job({"hook": {"line1": "شكد بضاعة", "line2": "لازم تجيب؟"},
                      "cover": {"tag": "STOCK 101", "sticker": "OUT OF STOCK?", "card_label": "SAFE STOCK FORMULA", "card_value": "1,200 × 3 = 3,600"}},
                     ["1,200", "3", "3,600"])
        v = cover.values(d)
        self.assertEqual(v["tag"], "")                                  # 101 was never said
        self.assertEqual(v["card_value"], "1,200 × 3 = 3,600"); self.assertEqual(v["sticker"], "OUT OF STOCK?")
        self.assertEqual((v["line1"], v["line2"]), ("شكد بضاعة", "لازم تجيب؟"))

    def test_card_without_value_drops_label_and_long_text_dropped(self):
        d = self.job({"hook": {"line1": "a", "line2": "b"}, "cover": {"card_label": "X", "card_value": "", "sticker": "x" * 40}}, [])
        v = cover.values(d)
        self.assertEqual((v["card_label"], v["sticker"]), ("", ""))

    def test_own_cover_is_used_as_is(self):
        if not shutil.which("ffmpeg"):
            self.skipTest("needs ffmpeg")
        import subprocess
        d = self.job({"hook": {"line1": "a", "line2": "b"}}, []); os.makedirs(os.path.join(d, "cover"))
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=red:s=800x800", "-frames:v", "1",
                        os.path.join(d, "cover", "own.png")], check=True)
        r = cover.make(d)
        self.assertEqual(r["source"], "your own cover")
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height", "-of", "csv=p=0", r["cover"]],
                             capture_output=True, text=True).stdout.strip()
        self.assertEqual(out, "1080,1920")


class CoverApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(); os.makedirs(os.path.join(self.tmp, "jobs", "2026-11-01-xx", "review"))
        os.makedirs(os.path.join(self.tmp, "config"))
        json.dump({"handles": {}}, open(os.path.join(self.tmp, "config", "brand.json"), "w"))
        os.environ["RF_ROOT"] = self.tmp
        import importlib, reels_api
        self.api = importlib.reload(reels_api)
        self.api._remake_cover = lambda job: None

    def tearDown(self):
        os.environ.pop("RF_ROOT", None)

    def test_upload_replaces_earlier_choice(self):
        ok, _ = self.api.cover_upload("2026-11-01-xx", "photo", "me.JPG", 3, io.BytesIO(b"abc")); self.assertTrue(ok)
        ok, _ = self.api.cover_upload("2026-11-01-xx", "own", "cover.png", 3, io.BytesIO(b"abc")); self.assertTrue(ok)
        self.assertEqual(sorted(os.listdir(os.path.join(self.tmp, "jobs", "2026-11-01-xx", "cover"))), ["own.png"])

    def test_bad_uploads_refused(self):
        self.assertFalse(self.api.cover_upload("../etc", "photo", "a.jpg", 3, io.BytesIO(b"abc"))[0])
        self.assertFalse(self.api.cover_upload("2026-11-01-xx", "photo", "a.gif", 3, io.BytesIO(b"abc"))[0])
        self.assertFalse(self.api.cover_upload("2026-11-01-xx", "hack", "a.jpg", 3, io.BytesIO(b"abc"))[0])

    def test_cover_is_served(self):
        open(os.path.join(self.tmp, "jobs", "2026-11-01-xx", "review", "cover.jpg"), "wb").write(b"j")
        self.assertTrue(self.api.media_path("2026-11-01-xx/review/cover.jpg"))
        self.assertIsNone(self.api.media_path("2026-11-01-xx/cover/own.png"))


if __name__ == "__main__":
    unittest.main()
