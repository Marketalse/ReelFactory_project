import csv, json, os, subprocess, sys, tempfile, unittest, zipfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import make_asset_pack, install_assets

SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M2 2h20v20H2z"/></svg>'


class Pack(unittest.TestCase):
    def setUp(self):
        d = tempfile.mkdtemp(); self.src = os.path.join(d, "orig"); self.assets = os.path.join(d, "assets"); self.d = d
        for s, lic in (("Lucide", True), ("Mystery", False)):
            os.makedirs(os.path.join(self.src, s));
            if lic: open(os.path.join(self.src, s, "LICENSE"), "w").write("ISC licence text")
        ok = os.path.join(self.assets, "ok"); os.makedirs(ok); rep = os.path.join(self.assets, "_reports", "t"); os.makedirs(rep)
        w = csv.DictWriter(open(os.path.join(rep, "report.csv"), "w", newline=""), fieldnames=["file", "result", "saved_as"]); w.writeheader()
        for s, n in (("Lucide", "truck"), ("Lucide", "gift"), ("Mystery", "ghost")):
            open(os.path.join(ok, n + ".svg"), "w").write(SVG + n); w.writerow({"file": f"{s}/icons/{n}.svg", "result": "PASS", "saved_as": n + ".svg"})
        json.dump({"concepts": {"truck": ["شاحنة"]}, "files": {"truck.svg": "truck"}}, open(os.path.join(self.assets, "icon_index.json"), "w"))

    def test_pack_leaves_out_sets_without_a_licence_and_installs_safely(self):
        z = os.path.join(self.d, "pack.zip")
        n, ex = make_asset_pack.build(self.src, self.assets, z)
        self.assertEqual(n, 2); self.assertEqual(ex, {"Mystery": 1})
        names = zipfile.ZipFile(z).namelist()
        self.assertIn("LICENSES/Lucide.txt", names); self.assertNotIn("icons/ghost.svg", names); self.assertIn("icon_index.json", names)
        root = os.path.join(self.d, "newuser"); os.makedirs(os.path.join(root, "library"))
        self.assertEqual(install_assets.install(z, root), (2, 0, 0, 0))
        self.assertEqual(install_assets.install(z, root), (0, 2, 0, 0))                               # second run: nothing changes
        self.assertTrue(os.path.exists(os.path.join(root, "library", "assets", "LICENSES", "Lucide.txt")))
        open(os.path.join(root, "library", "assets", "ok", "truck.svg"), "w").write("my own")          # his own different file is never overwritten
        self.assertEqual(install_assets.install(z, root)[2], 1)

    def test_motion_files_travel_with_their_licence_and_are_checked_again_on_install(self):
        good = {"v": "5.5", "fr": 30, "ip": 0, "op": 30, "w": 100, "h": 100, "layers": [{"ty": 4, "ks": {}}]}
        ms = os.path.join(self.d, "motion_src"); os.makedirs(ms)
        json.dump({"license": {"name": "MIT License", "license_text": "MIT text"}}, open(os.path.join(ms, "index.json"), "w"))
        md = os.path.join(self.assets, "motion"); os.makedirs(md); json.dump(good, open(os.path.join(md, "spin.json"), "w"))
        json.dump({"asset": "spin.json"}, open(os.path.join(md, "spin.placement.json"), "w"))
        z = os.path.join(self.d, "pm.zip"); make_asset_pack.build(self.src, self.assets, z, motion_src=ms)
        names = zipfile.ZipFile(z).namelist()
        self.assertIn("motion/spin.json", names); self.assertIn("LICENSES/motion-mit-license.txt", names); self.assertNotIn("motion/spin.placement.json", names)
        root = os.path.join(self.d, "u3"); os.makedirs(os.path.join(root, "library")); install_assets.install(z, root)
        m = os.path.join(root, "library", "assets", "motion")
        self.assertTrue(os.path.exists(os.path.join(m, "spin.json"))); self.assertTrue(os.path.exists(os.path.join(m, "spin.placement.json")))
        z2 = os.path.join(self.d, "nolic.zip"); os.remove(os.path.join(ms, "index.json"))                   # no licence text: motion is LEFT OUT
        make_asset_pack.build(self.src, self.assets, z2, motion_src=ms)
        self.assertNotIn("motion/spin.json", zipfile.ZipFile(z2).namelist())

    def test_damaged_icons_are_skipped(self):
        z = os.path.join(self.d, "p.zip"); make_asset_pack.build(self.src, self.assets, z)
        bad = os.path.join(self.d, "bad.zip")
        with zipfile.ZipFile(z) as zi, zipfile.ZipFile(bad, "w") as zo:
            for n in zi.namelist(): zo.writestr(n, b"tampered" if n == "icons/truck.svg" else zi.read(n))
        root = os.path.join(self.d, "u2"); os.makedirs(os.path.join(root, "library"))
        new, same, clash, badn = install_assets.install(bad, root)
        self.assertEqual((new, badn), (1, 1))


if __name__ == "__main__":
    unittest.main()
