"""Render failures must show the real cause, not npm's update notice."""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import render


class ExplainTests(unittest.TestCase):
    def test_npm_notice_is_skipped(self):
        err = ("Error: Failed to launch the browser process: Chrome not found\n"
               "npm notice\nnpm notice New major version of npm available! 10.8.2 -> 11.6.0\n"
               "npm notice To update run: npm install -g npm@11.6.0\nnpm notice run npx\n")
        msg = render.explain("rendering frames...\n", err)
        self.assertIn("Chrome not found", msg); self.assertNotIn("npm notice", msg)

    def test_coloured_npm_notice_is_skipped(self):
        msg = render.explain("", "Error: out of memory\n\x1b[37;40mnpm\x1b[0m \x1b[34;40mnotice\x1b[0m run npx\n")
        self.assertEqual(msg, "Error: out of memory")

    def test_empty_output_points_to_the_log(self):
        self.assertIn("render_error.log", render.explain("", "npm notice run npx\n"))

    def test_render_failure_saves_full_log(self):
        import tempfile
        d = tempfile.mkdtemp(); old = render.run
        render.run = lambda *a, **k: (1, "frames 10/100", "boom: ffmpeg exited\nnpm notice run npx")
        try:
            with self.assertRaises(render.RenderError) as cm:
                render.render(d, os.path.join(d, "x.mp4"), "draft")
        finally:
            render.run = old
        self.assertIn("ffmpeg exited", str(cm.exception))
        self.assertIn("frames 10/100", open(os.path.join(d, "render_error.log")).read())


if __name__ == "__main__":
    unittest.main()


class SingleFinalTests(unittest.TestCase):
    """Approve makes ONE final video, then the cover suggestion; no per-platform copies, no CapCut layers (2026-11-01)."""
    def test_one_video_then_cover(self):
        import json, tempfile
        from unittest import mock
        import render, compile as comp
        order = []
        with tempfile.TemporaryDirectory() as job:
            json.dump({"duration": 10.0, "scenes": []}, open(os.path.join(job, "timeline.json"), "w"))
            os.makedirs(os.path.join(job, "final")); open(os.path.join(job, "final", "reel_v1_instagram.mp4"), "w").close()
            def fake_render(project, out, q):
                order.append("video:" + os.path.basename(out)); open(out, "w").close(); return out
            def fake_cover(j):
                order.append("cover"); return {"cover": os.path.join(j, "review", "cover.jpg")}
            with mock.patch.object(comp, "compile_job", return_value=job), mock.patch.object(render, "check", return_value=[]), \
                 mock.patch.object(render, "render", side_effect=fake_render), mock.patch.object(render, "verify"), \
                 mock.patch.object(render, "even_sound"), mock.patch.object(render.qa_check, "run", return_value={"errors": []}), \
                 mock.patch.object(render, "make_cover", side_effect=fake_cover), \
                 mock.patch.object(render, "capcut_layers", side_effect=AssertionError("no CapCut step")):
                outs = render.final(job, ["instagram", "tiktok"])
            self.assertEqual(order, ["video:reel_v2.mp4", "cover"])
            self.assertEqual([os.path.basename(o) for o in outs], ["reel_v2.mp4", "cover.jpg"])
