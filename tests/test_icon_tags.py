import json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import reel
from lib import icon_tags, pack, outline

SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M2 2h20v20H2z" fill="#000000"/></svg>'


class Names(unittest.TestCase):
    def test_concept_drops_style_and_numbers(self):
        self.assertEqual(icon_tags.concept("Truck-Delivery_fill-24.svg"), "truck delivery")
        self.assertEqual(icon_tags.concept("shopping-cart2-outline.svg"), "shopping cart")
        self.assertEqual(icon_tags.concept("123.svg"), "")

    def test_clean_keeps_only_sent_names_and_short_tags(self):
        ans = {"truck": ["شاحنة", " توصيل ", "x", "شاحنة", "كلمة طويلة جدا جدا جدا جدا جدا"], "ghost": ["شيء"], "bad": "no"}
        self.assertEqual(icon_tags.clean(ans, {"truck", "bad"}), {"truck": ["شاحنة", "توصيل"]})

    def test_cost_estimate_is_small(self):
        self.assertLess(icon_tags.estimate(10000), 1.0); self.assertGreater(icon_tags.estimate(10000), 0.0)


class Library(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(); d = os.path.join(self.root, "library", "assets", "ok"); os.makedirs(d)
        for f in ("truck-delivery-fill.svg", "truck-delivery-outline-2.svg", "chevron-left.svg"):
            open(os.path.join(d, f), "w").write(SVG)

    def test_pending_save_and_match(self):
        self.assertEqual(sorted(icon_tags.pending(self.root)), ["chevron left", "truck delivery"])
        icon_tags.save({"truck delivery": ["شاحنة", "توصيل"], "chevron left": []}, self.root)
        self.assertEqual(icon_tags.pending(self.root), [])
        w = [{"text": "بالتوصيل"}]                                                  # Arabic attached letters still match
        self.assertEqual(icon_tags.match(w, root=self.root), "truck-delivery-fill.svg")      # shortest file name of the concept
        self.assertIsNone(icon_tags.match([{"text": "شيء"}], root=self.root))
        self.assertIsNone(icon_tags.match(w, exclude={"truck-delivery-fill.svg"}, root=self.root))

    def test_painting_makes_dark_icons_visible_but_leaves_colourful_ones(self):
        self.assertIn("#B6FF00", pack.paint(SVG, "#B6FF00")); self.assertNotIn("#000000", pack.paint(SVG, "#B6FF00"))
        many = '<svg><path fill="#111111"/><path fill="#222222"/><path fill="#333333"/></svg>'
        self.assertEqual(pack.paint(many, "#B6FF00"), many)


class Step(unittest.TestCase):
    def test_tag_run_saves_per_batch_and_logs_through_the_guard(self):
        d = tempfile.mkdtemp(); ok = os.path.join(d, "library", "assets", "ok"); os.makedirs(ok)
        for n in ("truck-fill.svg", "gift-fill.svg"): open(os.path.join(ok, n), "w").write(SVG)
        reel.ROOT = d; icon_tags.cfg.ROOT = d
        calls = []
        class C:
            def __init__(s, job, a): s.cost = {"calls": []}; s.cost_path = os.path.join(job, "cost.json"); s.a = a
            def spent(s): return 0.001
            def llm(s, stage, model, content, mt, effort="low", **k):
                calls.append((stage, model)); return json.dumps({"truck": ["شاحنة"], "gift": ["هدية"]})
        orig = reel.Ctx; reel.Ctx = C
        try:
            a = type("A", (), {"max_names": 0, "estimate_icons": False, "effort": None, "budget": 1.0})()
            reel.run_tag_icons(a)
        finally:
            reel.Ctx = orig; reel.ROOT = os.path.dirname(os.path.dirname(os.path.abspath(reel.__file__)))
            icon_tags.cfg.ROOT = reel.ROOT
        self.assertEqual(calls[0][0], "icon_tags")
        self.assertEqual(icon_tags.load(d)["concepts"], {"gift": ["هدية"], "truck": ["شاحنة"]})


if __name__ == "__main__":
    unittest.main()
