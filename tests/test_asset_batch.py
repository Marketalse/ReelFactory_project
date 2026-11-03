import csv, os, subprocess, sys, tempfile, unittest, zipfile
sys.path.insert(0, os.path.dirname(__file__))
from test_asset_check import SVG, png

ROOT = os.path.join(os.path.dirname(__file__), "..")


class Batch(unittest.TestCase):
    def test_zip_is_sorted_into_pass_fail_duplicate_and_unsafe_names_are_skipped(self):
        d = tempfile.mkdtemp(); z = os.path.join(d, "pile.zip")
        with zipfile.ZipFile(z, "w") as f:
            f.writestr("a/Truck Icon.svg", SVG); f.writestr("b/truck-copy.svg", SVG)               # same bytes: duplicate
            f.writestr("bad.svg", SVG.replace("<path", "<script>1</script><path"))
            f.writestr("photo.jpg", b"x"); f.writestr("../evil.svg", SVG); f.writestr("__MACOSX/x.svg", SVG)
            f.writestr("logo.png", png(512, 512))
        out = os.path.join(d, "out")
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "asset_batch.py"), z, "--out", out], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(sorted(f for f in os.listdir(os.path.join(out, "ok")) if not f.endswith(".json")), ["logo.png", "truck-icon.svg"])
        self.assertTrue(os.path.exists(os.path.join(out, "ok", "truck-icon.placement.json")))
        rep = os.path.join(out, "_reports"); rows = list(csv.DictReader(open(os.path.join(rep, os.listdir(rep)[0], "report.csv"), encoding="utf-8")))
        res = {x["file"]: x["result"] for x in rows}
        self.assertEqual(res["bad.svg"], "FAIL"); self.assertEqual(res["photo.jpg"], "FAIL"); self.assertEqual(res["b/truck-copy.svg"], "DUPLICATE")
        self.assertNotIn("../evil.svg", res); self.assertNotIn("__MACOSX/x.svg", res)


if __name__ == "__main__":
    unittest.main()
