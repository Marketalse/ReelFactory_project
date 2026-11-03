import json, os, sys, tempfile, unittest, zipfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from lib import motion_check as mc


def lottie(**kw):
    d = {"v": "5.7.0", "fr": 30, "ip": 0, "op": 60, "w": 512, "h": 512, "nm": "t", "assets": [],
         "layers": [{"ty": 4, "ks": {"o": {"a": 0, "k": 100}}, "shapes": [{"ty": "fl", "c": {"a": 0, "k": [0.7, 1, 0, 1]}}]}]}
    d.update(kw); return d


class Motion(unittest.TestCase):
    def setUp(self): self.d = tempfile.mkdtemp()
    def put(self, name, obj):
        p = os.path.join(self.d, name)
        open(p, "w").write(obj if isinstance(obj, str) else json.dumps(obj)); return p

    def test_good_lottie_gets_zones_and_info(self):
        r = mc.check(self.put("good.json", lottie()))
        self.assertTrue(r["ok"], r["problems"]); self.assertEqual(r["duration_s"], 2.0); self.assertTrue(r["recolourable"]); self.assertEqual(r["colours"], ["#B2FF00"])
        for z in (z for z in r["may_sit"] if z["ok"]): self.assertTrue(mc.ac.inside_safe(z["x"][0], z["y"][0], z["max_w"], z["max_h"]))

    def test_expressions_and_internet_pictures_are_refused(self):
        bad = lottie(); bad["layers"][0]["ks"]["o"] = {"a": 0, "k": 1, "x": "var $bm_rt = time * 100;"}
        r = mc.check(self.put("expr.json", bad)); self.assertFalse(r["ok"]); self.assertIn("expression", r["hard"][0])
        net = lottie(assets=[{"id": "image_0", "p": "https://evil.example/x.png", "u": "", "e": 0}])
        self.assertFalse(mc.check(self.put("net.json", net))["ok"])

    def test_broken_and_wrong_files_are_refused(self):
        self.assertFalse(mc.check(self.put("a.json", "{not json"))["ok"])
        self.assertFalse(mc.check(self.put("b.json", {"hello": 1}))["ok"])
        self.assertFalse(mc.check(self.put("c.json", lottie(op=0)))["ok"])
        self.assertFalse(mc.check(self.put("d.json", lottie(layers=[])))["ok"])
        self.assertFalse(mc.check(self.put("e.gif", "x"))["ok"])

    def test_long_or_font_animations_pass_with_notes(self):
        r = mc.check(self.put("long.json", lottie(op=900))); self.assertTrue(r["ok"]); self.assertTrue(any("long" in n for n in r["notes"]))
        t = lottie(); t["layers"].append({"ty": 5}); r = mc.check(self.put("text.json", t)); self.assertTrue(r["ok"]); self.assertTrue(any("font" in n for n in r["notes"]))

    def test_dotlottie_zip_and_zip_slip(self):
        p = os.path.join(self.d, "ok.lottie")
        with zipfile.ZipFile(p, "w") as z: z.writestr("manifest.json", "{}"); z.writestr("animations/a.json", json.dumps(lottie()))
        self.assertTrue(mc.check(p)["ok"])
        q = os.path.join(self.d, "slip.lottie")
        with zipfile.ZipFile(q, "w") as z: z.writestr("../evil.json", "{}")
        self.assertFalse(mc.check(q)["ok"])
        self.assertFalse(mc.check(self.put("notzip.lottie", "plain text"))["ok"])


if __name__ == "__main__":
    unittest.main()
