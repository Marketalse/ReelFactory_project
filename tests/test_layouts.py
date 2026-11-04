import json, os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from lib import hfbuild, layouts, director


class Layouts(unittest.TestCase):
    def test_every_layout_stays_inside_the_safe_zone(self):
        for n in layouts.names():
            self.assertEqual(layouts.problems(layouts.load(n)), [], n)

    def test_a_layout_that_leaves_the_safe_zone_or_overlaps_is_refused(self):
        s = layouts.load("stage")
        s["zones"]["stage"]["rect"] = [108, 100, 920, 790]                                   # starts above y 250
        self.assertTrue(any("stage" in p for p in layouts.problems(s)))
        s = layouts.load("stage"); s["zones"]["caption"]["rect"] = [108, 700, 920, 840]      # overlaps the stage
        self.assertTrue(any("overlap" in p for p in layouts.problems(s)))
        s = layouts.load("stage"); s["zones"]["container"].pop("bleeds_to_bottom"); s["zones"]["hero"]["clip"] = [108, 900, 972, 1500]   # below y 1500 is refused unless the layout says it bleeds
        self.assertTrue(any("container" in p for p in layouts.problems(s)))

    def test_fit_never_enlarges_and_centres_the_block_in_the_zone(self):
        z = [108, 250, 920, 790]
        tx, ty, s = layouts.fit(z, [176, 418, 852, 940])                                      # smaller than the zone: scale 1, centred
        self.assertEqual(s, 1.0)
        tx, ty, s = layouts.fit(z, [0, 286, 1080, 1313])                                      # bigger: scaled down to fit
        self.assertLess(s, 1.0)
        cx = tx + s * 540; cy = ty + s * (286 + 1313) / 2
        self.assertAlmostEqual(cx, 514, delta=1); self.assertAlmostEqual(cy, 520, delta=1)

    def test_plan_keeps_stage_blocks_fitted_and_drops_the_rest(self):
        spec = layouts.load("stage")
        sc = [{"id": "a", "block": "hook_two_tone", "t_in": 0, "t_out": 2, "values": {}}, {"id": "b", "block": "tier_list", "t_in": 3, "t_out": 6, "values": {}},
              {"id": "c", "block": "captions", "t_in": 0, "t_out": 9, "values": {}}]
        pl = layouts.plan(spec, sc, 9.0)
        self.assertEqual([s["id"] for s in pl["stage"]], ["a"]); self.assertEqual(pl["dropped"], ["b"])
        self.assertEqual(pl["caption_vars"]["cap-top"], "790px"); self.assertEqual(pl["caption_vars"]["cap-pill-bg"], "transparent")
        self.assertEqual(layouts.face_transform(pl["hero"]), {"scale": 1.35, "x": 0, "y": 450.4})

    def test_the_overlay_layout_keeps_him_full_screen_with_one_card_zone_and_no_frame_or_cutout(self):
        spec = layouts.load("overlay")
        pl = layouts.plan(spec, [{"id": "a", "block": "info_card", "t_in": 1, "t_out": 4, "values": {}}, {"id": "b", "block": "tier_list", "t_in": 5, "t_out": 8, "values": {}}], 9.0)
        self.assertIsNone(pl["frame"]); self.assertIsNone(pl["hero"])
        self.assertEqual([s["id"] for s in pl["stage"]], ["a"]); self.assertEqual(pl["dropped"], ["b"])
        self.assertEqual(pl["stage_rect"], [108, 1060, 920, 1500])

    def test_the_frame_has_a_hole_exactly_where_the_container_is(self):
        spec = layouts.load("stage"); g = layouts.frame_groups("stg", spec)
        self.assertIn("M152 1080H928", g)                                                     # x 108 + radius 44 ... x 972 - radius 44, top of the container
        self.assertIn("left:108px;top:1080px;width:864px;height:884px", g)

    def test_natural_boxes_exist_for_every_block_the_stage_allows(self):
        for b in layouts.load("stage")["blocks_in_stage"]:
            self.assertIn("natural_box", hfbuild.REGISTRY["blocks"][b], b)

    def test_build_project_fits_stage_blocks_clips_them_and_adds_the_hero(self):
        import shutil, tempfile
        out = tempfile.mkdtemp(); src = os.path.join(out, "p.mp4"); open(src, "wb").write(b"x")
        spec = layouts.load("stage")
        sc = [{"id": "hook", "block": "hook_two_tone", "t_in": 0.0, "t_out": 3.0, "values": {"line1": "أ", "line2": "ب"}}]
        pl = layouts.plan(spec, sc, 8.0)
        ft = layouts.face_transform(pl["hero"])
        allsc = [dict(pl["frame"], groups_html=layouts.frame_groups("stg", spec))] + pl["stage"]
        lay = {"stage_rect": pl["stage_rect"], "vars": pl["caption_vars"], "hero": dict(pl["hero"], src="assets/hero.webm")}
        hfbuild.build_project(out, duration=8.0, face_cuts=[{"id": "f0", "src_in": 0, "t_in": 0, "t_out": 8, "scale": ft["scale"], "cx": 0.5, "cy": 0.38, "y": ft["y"]}],
                              scenes=allsc, video_src=src, layout=lay)
        idx = open(os.path.join(out, "index.html"), encoding="utf-8").read()
        self.assertIn('id="stage-clip"', idx); self.assertIn("translate(", idx); self.assertIn('id="hero-clip"', idx)
        self.assertIn("clip-path:inset(900px 108px 0px 108px)", idx)                           # the hero may rise 180 px above the container, nowhere else
        self.assertIn("--cap-top: 790px", idx); self.assertIn("--cap-pill-bg: transparent", idx)
        self.assertEqual(idx.count('tl.set("#hero"'), idx.count('tl.set("#face"'))             # the cut-out follows the footage exactly
        self.assertIn("-scrim{display:none}", open(os.path.join(out, "compositions", "hook.html"), encoding="utf-8").read())


class DirectorWithLayout(unittest.TestCase):
    def test_only_stage_blocks_are_offered_when_a_layout_is_active(self):
        old = hfbuild.cfg.PROJECT["format_pack"].get("layout")
        try:
            hfbuild.cfg.PROJECT["format_pack"]["layout"] = "stage"
            self.assertNotIn("tier_list", director.offered_blocks()); self.assertIn("pixel_scene", director.offered_blocks())
            self.assertIn("REEL LAYOUT", director.build_prompt([{"text": "ك", "start": 0, "end": 1}], 10.0))
        finally:
            hfbuild.cfg.PROJECT["format_pack"]["layout"] = old
        self.assertIn("tier_list", director.offered_blocks())


if __name__ == "__main__":
    unittest.main()
