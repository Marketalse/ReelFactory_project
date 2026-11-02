"""B-roll library: a file is attached only when its name is said; nothing is invented, overwritten or deleted. Offline, free."""
import json, os, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from lib import broll  # noqa: E402


class BrollTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(); d = os.path.join(self.root, "library", "broll"); os.makedirs(d)
        for f in ("instagram.svg", "whatsapp.png", "meta-ads.jpg", "notes.txt"):
            open(os.path.join(d, f), "w").write("x")
        json.dump({"whatsapp.png": ["واتساب"]}, open(os.path.join(d, "tags.json"), "w", encoding="utf-8"), ensure_ascii=False)
        self.job = os.path.join(self.root, "jobs", "j"); os.makedirs(self.job)

    def words(self, *ws):
        return [{"text": w} for w in ws]

    def test_only_spoken_names_are_attached(self):
        got = broll.attach(self.job, self.words("نستخدم", "Instagram،", "كثير"), self.root)
        self.assertEqual(got, ["instagram.svg"])
        self.assertEqual(sorted(os.listdir(os.path.join(self.job, "assets"))), ["instagram.svg"])

    def test_arabic_tag_and_multiword_name(self):
        got = broll.attach(self.job, self.words("واتساب", "meta", "ads"), self.root)
        self.assertEqual(sorted(got), ["meta-ads.jpg", "whatsapp.png"])

    def test_nothing_said_nothing_attached_and_non_images_ignored(self):
        self.assertEqual(broll.attach(self.job, self.words("مرحبا", "notes"), self.root), [])
        self.assertFalse(os.path.exists(os.path.join(self.job, "assets")))

    def test_never_overwrites(self):
        os.makedirs(os.path.join(self.job, "assets")); p = os.path.join(self.job, "assets", "instagram.svg"); open(p, "w").write("MINE")
        broll.attach(self.job, self.words("instagram"), self.root)
        self.assertEqual(open(p).read(), "MINE")


if __name__ == "__main__":
    unittest.main()


class SmartMatchTests(unittest.TestCase):
    def idx(self):
        from lib import broll as b
        return [{"file": "instagram.svg", "tags": ["instagram"]}, {"file": "whatsapp.png", "tags": ["whatsapp", "واتساب"]}, {"file": "meta-ads.jpg", "tags": ["meta", "ads", "meta-ads"]}]

    def test_attached_arabic_letters_and_one_letter_typos_match(self):
        from lib import broll as b
        W = lambda t, s: {"text": t, "start": s, "end": s + 0.4}
        hits = {h["file"]: h for h in b.suggest([W("بالواتساب", 3.0), W("instgram", 5.0), W("ماتشوف", 7.0)], self.idx())}
        self.assertIn(hits["whatsapp.png"]["kind"], ("contains", "prefix")); self.assertEqual(hits["whatsapp.png"]["t"], 3.0)
        self.assertEqual(hits["instagram.svg"]["kind"], "close")
        self.assertNotIn("meta-ads.jpg", hits)

    def test_exact_beats_close_and_unrelated_words_match_nothing(self):
        from lib import broll as b
        W = lambda t, s: {"text": t, "start": s, "end": s + 0.4}
        h = b.suggest([W("instgram", 1.0), W("instagram", 4.0)], self.idx())
        self.assertEqual((h[0]["kind"], h[0]["t"]), ("exact", 4.0))
        self.assertEqual(b.suggest([W("مرحبا", 1.0), W("متجر", 2.0), W("meat", 3.0)], self.idx()), [])         # 'meat' is not 'meta' (4 letters)
