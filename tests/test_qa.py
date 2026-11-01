"""QA checks catch what they should (tiny generated videos; ffmpeg only, no spend)."""
import json, os, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import qa_check  # noqa: E402
from lib import hfbuild  # noqa: E402


def make(path, vf, dur=6, audio=True):
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"{vf}{':' if '=' in vf else '='}size=108x192:rate=10:duration={dur}"]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=300:duration={dur}", "-c:a", "aac", "-shortest"]
    subprocess.run(cmd + ["-c:v", "libx264", "-pix_fmt", "yuv420p", path], check=True)


def job_with(d, video, words, scenes_vals=None, dur=6.0):
    """A minimal job folder with timeline/edl and a compiled project for screen-text checks."""
    tl = {"duration": dur, "caption_gaps": [], "scenes": [], "keyword_ids": [], "punch_ins": []}
    edl = {"words": words, "segments": [{"src_in": 0, "src_out": dur, "t_in": 0, "t_out": dur}]}
    json.dump(tl, open(os.path.join(d, "timeline.json"), "w")); json.dump(edl, open(os.path.join(d, "edl.json"), "w"))
    scenes = [{"id": "caps", "block": "captions", "t_in": 0, "t_out": dur, "values": {},
               "groups_html": hfbuild.caption_groups(words, [], "caps")}]
    for k, (block, vals) in enumerate(scenes_vals or []):
        scenes.append({"id": f"m{k}", "block": block, "t_in": 1, "t_out": 2.5, "values": vals})
    hfbuild.build_project(os.path.join(d, "hyperframes"), duration=dur, video_src=video,
                          face_cuts=[{"id": "seg0", "t_in": 0, "t_out": dur, "src_in": 0}], scenes=scenes)
    return d


WORDS = [{"text": t, "start": 0.2 + i * 0.5, "end": 0.6 + i * 0.5} for i, t in enumerate("الزبون راح يخسر 300 طلب".split())]


class QaTests(unittest.TestCase):
    def test_clean_video_passes_basic_checks(self):
        with tempfile.TemporaryDirectory() as d:
            v = os.path.join(d, "v.mp4"); make(v, "testsrc2")
            r = qa_check.run(job_with(d, v, WORDS, [("split", {"value": "300", "label": "طلب"})]), v)
            self.assertEqual(r["errors"], [], r)

    def test_black_first_frame_and_frozen_picture_are_caught(self):
        with tempfile.TemporaryDirectory() as d:
            v = os.path.join(d, "v.mp4"); make(v, "color=c=black", dur=6)
            r = qa_check.run(job_with(d, v, WORDS), v)
            self.assertTrue(any("first frame is black" in e for e in r["errors"]), r["errors"])
            self.assertTrue(any("frozen" in e for e in r["errors"] + r["warnings"]), r)

    def test_missing_audio_and_wrong_length(self):
        with tempfile.TemporaryDirectory() as d:
            v = os.path.join(d, "v.mp4"); make(v, "testsrc2", dur=4, audio=False)
            r = qa_check.run(job_with(d, v, WORDS, dur=6.0), v)
            self.assertIn("no audio", r["errors"])
            self.assertTrue(any("length 4.00s but the plan is 6.00s" in e for e in r["errors"]), r["errors"])

    def test_unspoken_number_and_placeholder_text(self):
        with tempfile.TemporaryDirectory() as d:
            v = os.path.join(d, "v.mp4"); make(v, "testsrc2")
            r = qa_check.run(job_with(d, v, WORDS, [("split", {"value": "500", "label": "طلب"}),
                                                     ("text_card", {"kicker": "القاعدة 1", "headline": "TODO"})]), v)
            self.assertTrue(any("number 500, which was not said" in e for e in r["errors"]), r["errors"])
            self.assertTrue(any("placeholder text" in e for e in r["errors"]), r["errors"])
            self.assertFalse(any("number 1," in e for e in r["errors"]), r["errors"])   # chapter labels are fine

    def test_captions_must_match_speech(self):
        with tempfile.TemporaryDirectory() as d:
            v = os.path.join(d, "v.mp4"); make(v, "testsrc2")
            job_with(d, v, WORDS)
            edl = json.load(open(os.path.join(d, "edl.json")))
            edl["words"].append({"text": "زيادة", "start": 5.0, "end": 5.4})
            json.dump(edl, open(os.path.join(d, "edl.json"), "w"))
            r = qa_check.run(d, v)
            self.assertTrue(any("captions don't match the speech" in e for e in r["errors"]), r["errors"])

    def test_handle_placeholder_blocks_only_the_final(self):
        with tempfile.TemporaryDirectory() as d:
            v = os.path.join(d, "v.mp4"); make(v, "testsrc2")
            job_with(d, v, WORDS, [("cta_card", {"line": "تابعني", "handle": "@your_handle"})])
            self.assertTrue(any("handle not set" in w for w in qa_check.run(d, v)["warnings"]))
            self.assertTrue(any("handle not set" in e for e in qa_check.run(d, v, final=True)["errors"]))


if __name__ == "__main__":
    unittest.main()
