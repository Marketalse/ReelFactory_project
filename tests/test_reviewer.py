import json, os, shutil, sys, tempfile, unittest
from unittest import mock
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
from lib import reviewer, states, themes, hfbuild, critic, layouts  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_states import WORDS, CARDS, REG  # noqa: E402

M = {"top": 420.0, "head_w": 510.0, "head_cx": 432.0}


class Geometry(unittest.TestCase):
    def test_head_box_and_problems(self):
        ident = {"scale": 1.0, "x": 0, "y": 0}
        hb = reviewer.head_box(M, ident)
        self.assertAlmostEqual(hb[2] - hb[0], 510.0); self.assertAlmostEqual(hb[1], 420.0)
        self.assertEqual(reviewer.head_problems(hb), [])
        off = reviewer.head_box(M, {"scale": 1.0, "x": 400, "y": 0})                 # pushed right: cut by the screen edge
        self.assertIn("head touches the screen edge", reviewer.head_problems(off))
        self.assertTrue(reviewer.head_problems(reviewer.head_box(M, {"scale": 1.0, "x": 0, "y": -300}), clip_top=800))
        self.assertAlmostEqual(reviewer.overlap_ratio([0, 0, 10, 10], [5, 0, 20, 10]), 0.5)
        self.assertEqual(reviewer.overlap_ratio([0, 0, 10, 10], [20, 20, 30, 30]), 0.0)

    def test_a_head_cut_by_the_edge_is_made_smaller_until_it_fits(self):
        pl = states.plan(themes.load("seq_hero_headline"), CARDS, WORDS, [2], 12.0, REG)
        wide = {"top": 420.0, "head_w": 300.0, "head_cx": 960.0}                    # a small head far to the right: centring it would need a huge zoom
        tfs, notes = states.transforms_checked(pl["segments"], wide, None)
        for s, tf in zip(pl["segments"], tfs):
            hb = reviewer.head_box(wide, tf)
            self.assertEqual(reviewer.head_problems(hb, clip_top=s["spec"]["clip"].get("hero_clip_top")), [], (s["state"], tf, hb))
        shrunk, _ = states.transforms_checked(pl["segments"], M, {"head_scale": 0.7})
        base, _ = states.transforms_checked(pl["segments"], M, None)
        self.assertLess(shrunk[0]["scale"], base[0]["scale"])

    def test_text_on_his_face_is_moved_or_dropped(self):
        th = themes.load("seq_half_clip")
        pl = states.plan(th, CARDS, WORDS, [2, 4, 8, 12], 12.0, REG)
        rest = next(s for s in pl["segments"] if s["state"] == "text_full_clip")
        box = layouts.block_box(REG["line_text"])
        tx, ty, sc = layouts.fit([108, 700, 920, 1300], box)                          # a card right where his head is
        pl["scenes"].append({"id": "face1", "block": "line_text", "t_in": rest["t_in"] + 0.2, "t_out": rest["t_in"] + 2.0, "values": {"headline": "", "number": "", "line1": "ت", "line2": ""}, "zone": [108, 700, 920, 1300], "fit": {"tx": tx, "ty": ty, "s": sc}})
        head = {"top": 600.0, "head_w": 500.0, "head_cx": 540.0}
        notes = states.avoid_face(pl, head, REG)
        self.assertTrue(any("face" in n for n in notes), notes)
        hb = reviewer.head_box(head, {"scale": 1.0, "x": 0, "y": 0})
        for sc2 in pl["scenes"]:
            if sc2["id"] == "face1": self.assertLessEqual(reviewer.overlap_ratio(states._rendered_rect(sc2["fit"], box), hb), 0.12)

    def test_idle_zones_are_found_and_filled_only_from_his_words(self):
        pl = states.plan(themes.load("seq_media_hero"), [CARDS[0]], WORDS, [], 12.0, REG)
        pl["scenes"] = [s for s in pl["scenes"] if s["block"] != "line_text"]         # nothing in the second half
        idle = states.idle_stretches(pl)
        self.assertTrue(idle)
        notes = states.fill_idle(pl, WORDS, [2, 4], REG)
        self.assertTrue(notes); said = {w["text"] for w in WORDS}
        for s in pl["scenes"]:
            if s["id"].startswith("idle"):
                v = s["values"]; self.assertTrue(set(" ".join(v[k] for k in ("headline", "line1") if v[k]).split()) <= said)
        self.assertLess(sum(b - a for a, b in states.idle_stretches(pl)), sum(b - a for a, b in idle))

    def test_critic_named_empty_zone_gets_a_card(self):
        pl = states.plan(themes.load("seq_media_hero"), [CARDS[0]], WORDS, [], 12.0, REG)
        pl["scenes"] = [s for s in pl["scenes"] if s["block"] != "line_text"]
        n0 = len(pl["scenes"])
        states.fill_idle(pl, WORDS, [], REG, {"items": [{"kind": "empty_zone", "t": 5.0}]}, min_idle=99.0)
        self.assertEqual(len(pl["scenes"]), n0 + 1)


class Repairs(unittest.TestCase):
    def test_from_issues_only_known_fixes_and_the_head_never_gets_tiny(self):
        iss = [{"t": 2.0, "kind": "head_clipped"}, {"t": 4.0, "kind": "other"}, {"t": 6.0, "kind": "empty_zone"}, {"t": 7.0, "kind": "overlap"}]
        d, applied = reviewer.from_issues(iss)
        self.assertEqual([i["kind"] for i in d["items"]], ["head_clipped", "empty_zone"]); self.assertEqual(len(applied), 2)
        self.assertLess(d["head_scale"], 1.0)
        for _ in range(20): d, _ = reviewer.from_issues([{"t": 1.0, "kind": "head_clipped", "x": _}], d)
        self.assertGreaterEqual(d["head_scale"], reviewer.MAX_SHRINK)
        self.assertEqual(reviewer.from_issues([{"t": 1, "kind": "other"}])[1], [])

    def test_load_save_disabled_and_broken_files(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(reviewer.load(d)["items"], [])
            reviewer.save(d, {"items": [{"kind": "empty_zone", "t": 1}], "disabled": True})
            self.assertEqual(reviewer.active(d)["items"], []); self.assertTrue(reviewer.active(d)["disabled"])
            open(os.path.join(d, "repairs.json"), "w").write("{nope"); self.assertEqual(reviewer.load(d)["items"], [])

    def test_critic_answers_carry_a_kind_and_unknown_kinds_become_other(self):
        o = critic.clean({"scores": {"readable": 7, "layout": 6, "consistency": 7, "variety": 5}, "issues": [{"t": 3, "kind": "head_clipped", "what": "x"}, {"t": 4, "kind": "weird", "what": "y"}]})
        self.assertEqual([i["kind"] for i in o["issues"]], ["head_clipped", "other"])
        self.assertIn("[head_clipped]", "\n".join(critic.summary_lines(dict(o, stills=8))))


class RepairRound(unittest.TestCase):
    """reel._repair_round with the compile, the draft render and the second look replaced by stand-ins."""
    def setUp(self):
        import reel, render
        import compile as comp
        self.reel, self.render, self.comp = reel, render, comp
        self.job = tempfile.mkdtemp(); os.makedirs(os.path.join(self.job, "review"))
        self.video = os.path.join(self.job, "review", "draft_540p.mp4"); open(self.video, "wb").write(b"FIRST")
        self.c = mock.Mock(job=self.job, a=mock.Mock(effort=None)); self.c.gate2 = None
        self.o = {"scores": {}, "average": 6.0, "issues": [{"t": 3.0, "kind": "head_clipped", "what": "cut"}, {"t": 5.0, "kind": "other", "what": "x"}], "stills": 8}

    def run_round(self, second, rounds=1, repair=True):
        def fake_draft(job):
            open(self.video, "wb").write(b"REPAIRED" if not reviewer.load(job).get("disabled") else b"RESTORED"); return {"qa": {"errors": []}}
        with mock.patch.dict(self.reel.cfg.PROJECT, {"critic": {"enabled": True, "repair": repair, "repair_rounds": rounds}}), \
             mock.patch.object(self.comp, "compile_job", return_value="x"), mock.patch.object(self.render, "draft", side_effect=fake_draft), \
             mock.patch.object(self.reel, "_look", return_value=second):
            return self.reel._repair_round(self.c, self.o, self.video, {}, 30)

    def test_a_better_second_look_keeps_the_repair(self):
        o2 = dict(self.o, average=7.5, issues=[])
        r = self.run_round(o2)
        self.assertEqual(r["repair"]["before"], 6.0); self.assertEqual(r["repair"]["after"], 7.5); self.assertTrue(r["repair"]["applied"])
        self.assertEqual(open(self.video, "rb").read(), b"REPAIRED"); self.assertFalse(reviewer.load(self.job)["disabled"])
        self.assertFalse(os.path.exists(os.path.join(self.job, "review", "_draft_before_repair.mp4")))

    def test_a_worse_second_look_switches_the_repair_off_and_restores_the_first_draft(self):
        r = self.run_round(dict(self.o, average=4.0))
        self.assertEqual(r["repair"]["applied"], []); self.assertIn("switched off", r["repair"]["summary"])
        self.assertTrue(reviewer.load(self.job)["disabled"]); self.assertEqual(open(self.video, "rb").read(), b"RESTORED")      # made again as it was (repair off)
        self.assertEqual(r["average"], 6.0)

    def test_no_fixable_issue_rounds_zero_or_repair_off_changes_nothing(self):
        o = dict(self.o, issues=[{"t": 1, "kind": "other", "what": "x"}]); self.o = o
        self.assertIs(self.run_round(None), o)
        self.o = dict(self.o, issues=[{"t": 3.0, "kind": "head_clipped", "what": "cut"}])
        self.assertIs(self.run_round(None, rounds=0), self.o); self.assertIs(self.run_round(None, repair=False), self.o)
        self.assertFalse(os.path.exists(os.path.join(self.job, "repairs.json")))

    def test_a_failed_second_look_switches_off_and_makes_the_draft_again_as_it_was(self):
        r = self.run_round(None)
        self.assertEqual(open(self.video, "rb").read(), b"RESTORED"); self.assertTrue(reviewer.load(self.job)["disabled"]); self.assertEqual(r["repair"]["applied"], [])

    def test_if_even_the_remake_fails_the_first_draft_file_is_put_back(self):
        calls = []
        def draft(job):
            calls.append(1)
            if len(calls) == 1: open(self.video, "wb").write(b"REPAIRED"); return {"qa": {"errors": []}}
            raise self.render.RenderError("boom")
        with mock.patch.dict(self.reel.cfg.PROJECT, {"critic": {"enabled": True, "repair": True, "repair_rounds": 1}}), mock.patch.object(self.comp, "compile_job", return_value="x"), \
             mock.patch.object(self.render, "draft", side_effect=draft), mock.patch.object(self.reel, "_look", return_value=dict(self.o, average=3.0)):
            self.reel._repair_round(self.c, self.o, self.video, {}, 30)
        self.assertEqual(open(self.video, "rb").read(), b"FIRST")


if __name__ == "__main__":
    unittest.main()
