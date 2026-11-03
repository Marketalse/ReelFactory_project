import os, struct, sys, tempfile, unittest, zlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from lib import asset_check as ac

SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M2 2h20v20H2z" fill="currentColor"/></svg>'


def png(w, h, alpha=True):
    raw = b"".join(b"\x00" + (b"\x00\x00\x00\x00" if alpha else b"\x00\x00\x00") * w for _ in range(h))
    ch = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
    return b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6 if alpha else 2, 0, 0, 0)) + ch(b"IDAT", zlib.compress(raw)) + ch(b"IEND", b"")


class Check(unittest.TestCase):
    def setUp(self): self.d = tempfile.mkdtemp()
    def put(self, n, data):
        p = os.path.join(self.d, n); open(p, "wb" if isinstance(data, bytes) else "w").write(data); return p

    def test_good_svg_gets_zones_inside_the_safe_box(self):
        r = ac.check(self.put("box.svg", SVG)); self.assertTrue(r["ok"], r["problems"]); self.assertTrue(r["recolourable"])
        for z in (z for z in r["may_sit"] if z["ok"]):
            self.assertTrue(ac.inside_safe(z["x"][1], z["y"][1], z["max_w"], z["max_h"]), z)       # the farthest corner still fits
            self.assertTrue(ac.inside_safe(z["x"][0], z["y"][0], z["max_w"], z["max_h"]), z)
        self.assertIn("caption_band", [n["where"] for n in r["never"]])

    def test_dangerous_or_broken_files_fail(self):
        self.assertFalse(ac.check(self.put("a.svg", SVG.replace("<path", "<script>x</script><path")))["ok"])
        self.assertFalse(ac.check(self.put("b.svg", "<svg"))["ok"])
        self.assertFalse(ac.check(self.put("c.svg", '<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0"/></svg>'))["ok"])  # no viewBox
        self.assertFalse(ac.check(self.put("d.jpg", b"x"))["ok"])

    def test_png_needs_transparency_and_size(self):
        self.assertTrue(ac.check(self.put("a.png", png(512, 512)))["ok"])
        self.assertFalse(ac.check(self.put("b.png", png(512, 512, alpha=False)))["ok"])
        self.assertFalse(ac.check(self.put("c.png", png(100, 100)))["ok"])

    def test_wide_asset_gets_smaller_height_and_rule_helper_and_files(self):
        r = ac.check(self.put("w.svg", SVG.replace("0 0 24 24", "0 0 100 10")))
        top = next(z for z in r["may_sit"] if z["zone"] == "top"); self.assertEqual(top["max_w"], 812)
        self.assertFalse(ac.inside_safe(100, 300, 50, 50)); self.assertFalse(ac.inside_safe(300, 1250, 100, 100)); self.assertTrue(ac.inside_safe(300, 300, 100, 100))
        ac.run(self.d); self.assertEqual(ac.rule_for(self.d, "w.svg")["asset"], "w.svg"); self.assertIsNone(ac.rule_for(self.d, "none.svg"))


if __name__ == "__main__":
    unittest.main()


class Enforcement(unittest.TestCase):
    def test_director_refuses_a_failed_asset_and_job_problems_only_flags_hard_failures(self):
        from lib import director
        d = tempfile.mkdtemp(); a = os.path.join(d, "assets"); os.makedirs(a)
        open(os.path.join(a, "evil.svg"), "w").write(SVG.replace("<path", "<script>x</script><path"))
        open(os.path.join(a, "ok.svg"), "w").write(SVG)
        open(os.path.join(a, "white.png"), "wb").write(png(512, 512, alpha=False))     # soft problem only: still usable
        bad = ac.job_problems(a)
        self.assertIn("evil.svg", bad); self.assertNotIn("ok.svg", bad); self.assertNotIn("white.png", bad)
        words = [{"text": "انستغرام", "start": 0.0, "end": 0.5}] * 3
        plan = {"moments": [{"block": "logo_card", "at_word": 0, "values": {"logo_a": "evil.svg", "name_a": "X"}}]}
        _, err, _ = director.resolve(plan, [dict(w, i=i) for i, w in enumerate(words)], 5.0, logos=["evil.svg"], asset_bad=bad)
        self.assertTrue(any("failed the asset check" in e for e in err), err)
