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
        self.assertEqual(pl["stage_rect"], [108, 1080, 920, 1500])

    def test_the_overlay_lifts_the_footage_so_the_face_sits_high_and_never_leaves_a_gap(self):
        spec = layouts.load("overlay")
        ft = layouts.footage_transform(spec, 0.38)                                            # a normal selfie framing: face centre at 38% of the height
        self.assertGreater(ft["scale"], 1.0); self.assertLess(ft["y"], 0)
        origin = 0.38 * 1920
        face_y = origin + (0.38 * 1920 - origin) * ft["scale"] + ft["y"]                      # where the face centre ends up
        self.assertAlmostEqual(face_y, 600, delta=1)
        self.assertGreaterEqual(origin + (1920 - origin) * ft["scale"] + ft["y"], 1920 - 0.5)  # the bottom of the footage still reaches the bottom of the screen
        self.assertEqual(layouts.footage_transform(spec, 0.28), {"scale": 1.0, "x": 0, "y": 0})   # already high: left alone
        self.assertLessEqual(layouts.footage_transform(spec, 0.6)["scale"], 1.4)               # never zoomed more than the layout allows
        self.assertIsNone(layouts.footage_transform(layouts.load("stage")))                    # a layout without a footage zone

    def test_the_frame_has_a_hole_exactly_where_the_container_is(self):
        spec = layouts.load("stage"); g = layouts.frame_groups("stg", spec)
        self.assertIn("M84 930H996", g)                                                     # x 108 + radius 44 ... x 972 - radius 44, top of the container
        self.assertIn("left:40px;top:930px;width:1000px;height:1034px", g)

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
        self.assertIn("clip-path:inset(800px 0px 0px 0px)", idx)                             # the hero may rise above the container; no side walls (head free to move), only the caption band above stays clear
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


class StageFill(unittest.TestCase):
    W = [{"text": t, "start": s, "end": s + 0.4} for t, s in [("ابني", 0.5), ("موقع", 1.0), ("كلش", 5.0), ("مهم", 5.5), ("جدا", 6.0), ("للتسويق", 6.6), ("وبعدين", 9.5)]]

    def test_gap_gets_card_from_his_words_only(self):
        from lib import layouts
        out = layouts.fill_stage([], self.W, [2], 11.0)
        self.assertTrue(out); c = next(o for o in out if o["t_in"] <= 5.0 <= o["t_out"])
        self.assertEqual(c["block"], "text_card"); self.assertTrue(c["values"]["headline"].startswith("كلش"))      # the highlighted keyword leads its window
        said = {w["text"] for w in self.W}
        self.assertTrue(set(c["values"]["headline"].split()) <= said)
        self.assertTrue(1.4 <= c["t_out"] - c["t_in"] <= 3.0 and len(c["values"]["headline"]) <= 36)

    def test_no_card_over_real_card_and_none_without_keyword(self):
        from lib import layouts
        kept = [{"t_in": 4.0, "t_out": 8.0}]
        out = layouts.fill_stage(kept, self.W, [2], 11.0)
        self.assertFalse(any(o["t_in"] < 8.0 and o["t_out"] > 4.0 for o in out))
        out2 = layouts.fill_stage([], self.W, [], 11.0)                                              # no keyword: the longest word of the window leads, still only his words
        self.assertTrue(out2); said = {w["text"] for w in self.W}
        self.assertTrue(all(set(o["values"]["headline"].split()) <= said for o in out2))
        self.assertTrue(all(b["t_in"] >= a["t_out"] for a, b in zip(out2, out2[1:])))

    def test_hero_transform_follows_measured_head_and_keeps_footage_covering(self):
        from lib import layouts
        h = layouts.load("stage")["zones"]["hero"]
        for m in ({"top": 420.0, "head_w": 515.0, "head_cx": 347.0}, {"top": 300.0, "head_w": 400.0, "head_cx": 800.0}, {"top": 900.0, "head_w": 700.0, "head_cx": 540.0}):
            ft = layouts.hero_transform(h, m); s = ft["scale"]
            left = 540 - 540 * s + ft["x"]; right = left + 1080 * s; top = 730 - 730 * s + ft["y"]; bottom = top + 1920 * s
            self.assertTrue(left <= 108 + 1 and right >= 972 - 1 and top <= 1080 and bottom >= 1964 - 1, (m, ft))
            self.assertTrue(h["min_scale"] <= s or s >= h["min_scale"] - 1e-6)
        self.assertEqual(layouts.hero_transform(h, None), layouts.face_transform(h))


class Themes(unittest.TestCase):
    def test_every_theme_points_at_a_real_layout_and_palette(self):
        from lib import themes, layouts
        self.assertTrue({"stage_dark", "stage_violet", "overlay", "classic"} <= set(themes.names()))
        for n in themes.names():
            t = themes.load(n)
            self.assertIn(t["layout"], ["panel"] + layouts.names()); self.assertIn(t["palette"], ("dark", "violet")); self.assertTrue(t["label"])

    def test_dashboard_list_matches_the_theme_files(self):
        import re
        from lib import themes
        html = open(os.path.join(os.path.dirname(__file__), "..", "dashboard", "make.html"), encoding="utf-8").read()
        sel = re.search(r'id="cbTheme"[^>]*>(.*?)</select>', html, re.S).group(1)
        self.assertEqual(sorted(re.findall(r'value="([a-z_]+)"', sel)), themes.names())

    def test_brief_theme_is_used_by_the_reel_and_unknown_is_ignored(self):
        import tempfile
        from lib import themes, layouts, creative_brief
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(themes.use_job(d))
            creative_brief.save(d, {"theme": "overlay"})
            self.assertEqual(themes.use_job(d), "overlay"); self.assertEqual(layouts.active_name(), "overlay")
            creative_brief.save(d, {"theme": "stage_violet"})
            self.assertEqual(themes.palette("dark"), "violet") if themes.use_job(d) else None
            creative_brief.save(d, {"theme": "../../etc"}); open(os.path.join(d, "brief.json"), "w").write('{"theme": "nonsense"}')
            self.assertIsNone(themes.use_job(d))
        self.assertEqual(creative_brief.clean({"theme": "overlay"}), {"theme": "overlay"}); self.assertEqual(creative_brief.clean({"theme": "x"}), {})
        self.assertEqual(creative_brief.to_text({"theme": "overlay"}), "")
