"""BUG-001 (pre-UAT audit 2026-11-03): a Format Pack reel replaced the director's cards at compile time, but the render check still demanded the
cards' files, so every explainer-style reel stopped with 'the project is missing the file for scene hook'. The compile step now records them as dropped."""
import json, os, shutil, subprocess, sys, tempfile, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import compile as comp
import qa_check
from lib import render_guard, pack

W = [{"text": t, "start": round(0.4 + i * 0.5, 2), "end": round(0.8 + i * 0.5, 2)} for i, t in enumerate("اولا الجمارك تدخل البضاعة وبعدها التاجر يشتري من الشركة وبعدين المحل يبيع للزبون والزبون يدفع اكثر".split())]
OUT = {"format": "explainer", "hook_word": 0, "concept": None, "recap": [], "sections": [
    {"from_word": 0, "to_word": 4, "kind": "step", "title": "الجمارك تدخل", "title_from": 1, "title_to": 2, "t_in": 0.4, "t_out": 2.8},
    {"from_word": 5, "to_word": 9, "kind": "step", "title": "التاجر يشتري", "title_from": 5, "title_to": 6, "t_in": 2.9, "t_out": 5.3},
    {"from_word": 10, "to_word": 15, "kind": "point", "title": "المحل يبيع", "title_from": 11, "title_to": 12, "t_in": 5.4, "t_out": 8.3}]}


@unittest.skipUnless(shutil.which("ffmpeg"), "needs ffmpeg")
class PackRenderCheck(unittest.TestCase):
    def setUp(self):
        self.job = tempfile.mkdtemp()
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=270x480:r=30:d=9", "-f", "lavfi", "-i", "sine=d=9", "-shortest", "-pix_fmt", "yuv420p", os.path.join(self.job, "proxy.mp4")], check=True)
        d = 8.4
        json.dump({"duration": d, "keyword_ids": [3], "caption_gaps": [], "punch_ins": [], "face_cy": 0.36, "director": "mock", "feedback": "",
                   "scenes": [{"id": "hook", "block": "hook_two_tone", "t_in": 0.0, "t_out": 2.6, "values": {"line1": "اولا", "line2": "الجمارك"}}]}, open(os.path.join(self.job, "timeline.json"), "w"), ensure_ascii=False)
        json.dump({"words": W, "duration": d, "segments": [{"src_in": 0.0, "src_out": d, "t_in": 0.0, "t_out": d}]}, open(os.path.join(self.job, "edl.json"), "w"), ensure_ascii=False)
        json.dump(OUT, open(os.path.join(self.job, "outline.json"), "w"), ensure_ascii=False)

    def test_pack_reel_passes_the_render_check(self):
        self.assertTrue(pack.active(OUT))
        comp.compile_job(self.job)
        info = json.load(open(os.path.join(self.job, "hyperframes", "compile_info.json")))
        self.assertTrue(info["format_pack"]); self.assertIn("hook", info["dropped_scenes"])
        bad = [b for b in render_guard.preflight(self.job, min_free_gb=0) if "missing the file for scene" in b]
        self.assertEqual(bad, [])

    def test_qa_counts_highlighted_caption_words_too(self):
        """BUG-002: highlight bars add a style attribute to a caption word; the QA caption count did not see those words and failed every pack reel."""
        comp.compile_job(self.job)
        proj = os.path.join(self.job, "hyperframes")
        caps = open(os.path.join(proj, "compositions", "caps.html"), encoding="utf-8").read()
        self.assertIn("caps-kwp", caps)                                                   # the pack really highlighted some words
        shown = [t for sc, k, t in qa_check.screen_texts(proj) if sc == "caps"]
        self.assertEqual(shown, [w["text"] for w in W])

    def test_classic_reel_still_requires_its_scene_files(self):
        os.remove(os.path.join(self.job, "outline.json"))                                  # no outline = no pack = the director's cards stay
        comp.compile_job(self.job)
        os.remove(os.path.join(self.job, "hyperframes", "compositions", "hook.html"))
        self.assertTrue([b for b in render_guard.preflight(self.job, min_free_gb=0) if "missing the file for scene hook" in b])


if __name__ == "__main__":
    unittest.main()
