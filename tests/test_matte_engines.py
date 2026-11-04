import json, os, subprocess, sys, tempfile, unittest
from unittest import mock
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
from lib import matte, config as cfg  # noqa: E402
import setup_matte  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_text_behind import make_job  # noqa: E402


def conf(engine):
    return mock.patch.dict(cfg.PROJECT, {"matte": {"engine": engine}})


class Engines(unittest.TestCase):
    def test_default_and_missing_engine_fall_back_to_hyperframes(self):
        with conf("hyperframes"): self.assertEqual(matte.engine_name(), "hyperframes")
        with conf("rvm"), mock.patch.object(setup_matte, "status", return_value={"rvm": False, "mp_selfie": False}):
            self.assertEqual(matte.engine_name(), "hyperframes")
        with conf("nonsense"), mock.patch.object(setup_matte, "status", return_value={"rvm": True, "mp_selfie": True}):
            self.assertEqual(matte.engine_name(), "hyperframes")

    def test_chosen_and_auto_engine_when_ready(self):
        ready = {"rvm": True, "mp_selfie": True}
        with mock.patch.object(setup_matte, "status", return_value=ready):
            with conf("mp_selfie"): self.assertEqual(matte.engine_name(), "mp_selfie")
            with conf("auto"): self.assertEqual(matte.engine_name(), "rvm")
        with conf("auto"), mock.patch.object(setup_matte, "status", return_value={"rvm": False, "mp_selfie": True}):
            self.assertEqual(matte.engine_name(), "hyperframes")

    def test_cache_key_keeps_old_caches_and_separates_engines(self):
        d = make_job(); p = os.path.join(d, "proxy.mp4")
        self.assertEqual(matte.key(p, [(3.0, 5.0)], 540), matte.key(p, [(3.0, 5.0)], 540, "hyperframes"))
        self.assertNotEqual(matte.key(p, [(3.0, 5.0)], 540), matte.key(p, [(3.0, 5.0)], 540, "rvm"))

    def test_rvm_is_used_when_ready(self):
        d = make_job(); edl = json.load(open(os.path.join(d, "edl.json"))); calls = []
        def runner(cmd, **k):
            calls.append("worker" if "matte_worker.py" in " ".join(cmd) else "ffmpeg" if cmd[0] == "ffmpeg" else "hyperframes")
            out = cmd[-1] if calls[-1] == "ffmpeg" else cmd[4] if calls[-1] == "worker" else cmd[cmd.index("-o") + 1]
            open(out, "wb").write(b"x" * 10); return subprocess.CompletedProcess(cmd, 0, "", "")
        with conf("rvm"), mock.patch.object(setup_matte, "status", return_value={"rvm": True, "mp_selfie": False}):
            p = matte.cutout(d, edl, 3.0, 6.0, False, say=lambda *a: None, runner=runner)
        self.assertEqual(calls, ["ffmpeg", "worker"]); self.assertTrue(p.endswith(".webm"))

    def test_failing_engine_falls_back_to_original(self):
        d = make_job(); edl = json.load(open(os.path.join(d, "edl.json"))); calls = []
        def runner(cmd, **k):
            if cmd[0] == "ffmpeg":
                calls.append("ffmpeg"); open(cmd[-1], "wb").write(b"x"); return subprocess.CompletedProcess(cmd, 0, "", "")
            if "matte_worker.py" in " ".join(cmd):
                calls.append("worker"); return subprocess.CompletedProcess(cmd, 1, "", "torch exploded")
            calls.append("hyperframes"); open(cmd[cmd.index("-o") + 1], "wb").write(b"x" * 10); return subprocess.CompletedProcess(cmd, 0, "", "")
        msgs = []
        with conf("rvm"), mock.patch.object(setup_matte, "status", return_value={"rvm": True, "mp_selfie": False}):
            p = matte.cutout(d, edl, 3.0, 6.0, False, say=msgs.append, runner=runner)
        self.assertEqual(calls, ["ffmpeg", "worker", "hyperframes"]); self.assertTrue(os.path.exists(p))
        self.assertTrue(any("torch exploded" in m for m in msgs))

    def test_status_needs_environment_and_model_file(self):
        with tempfile.TemporaryDirectory() as h, mock.patch.object(setup_matte, "HOME", h), mock.patch.object(setup_matte, "VENV", h + "/env"), mock.patch.object(setup_matte, "MODELS", h + "/models"):
            self.assertEqual(setup_matte.status(), {"rvm": False, "mp_selfie": False})
            os.makedirs(h + "/env/bin"); open(h + "/env/bin/python", "w").close(); open(h + "/.installed", "w").write(",".join(setup_matte.PACKAGES))
            os.makedirs(h + "/models"); open(h + "/models/rvm_mobilenetv3_fp32.torchscript", "wb").write(b"x" * 2000)
            self.assertEqual(setup_matte.status(), {"rvm": True, "mp_selfie": False})


if __name__ == "__main__":
    unittest.main()
