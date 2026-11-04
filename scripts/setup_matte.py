#!/usr/bin/env python3
"""Install the extra cut-out engines for Reel Factory (free, once, safe to run again).
    python3 scripts/setup_matte.py            install what is missing (private environment in ~/.reelfactory/matte)
    python3 scripts/setup_matte.py --check    only say what is ready
Installs: Robust Video Matting (model file from its official release) and MediaPipe selfie segmentation (Google's official model file).
Nothing in the project or your system Python changes; to remove it all:  rm -rf ~/.reelfactory/matte
Licences: Robust Video Matting is GPL-3.0 (its model file is only DOWNLOADED to your computer, no code of it is copied into this project);
MediaPipe is Apache-2.0. Check the licence yourself for commercial use. Failure here never stops a reel: the current cut-out keeps working."""
import os, subprocess, sys, urllib.request

HOME = os.path.expanduser("~/.reelfactory/matte")
VENV = os.path.join(HOME, "env")
MODELS = os.path.join(HOME, "models")
PACKAGES = ["numpy", "opencv-python-headless", "torch", "mediapipe==0.10.21"]
FILES = {"rvm": ("rvm_mobilenetv3_fp32.torchscript", "https://github.com/PeterL1n/RobustVideoMatting/releases/download/v1.0.0/rvm_mobilenetv3_fp32.torchscript"),
         "mp_selfie": ("selfie_segmenter.tflite", "https://storage.googleapis.com/mediapipe-models/image_segmenter/selfie_segmenter/float16/latest/selfie_segmenter.tflite")}


def python():
    return os.path.join(VENV, "bin", "python")


def status():
    """-> {engine: bool} (ready = environment installed and its model file present)."""
    marker = os.path.join(HOME, ".installed")
    env = os.path.exists(python()) and os.path.exists(marker) and open(marker).read() == ",".join(PACKAGES)
    return {k: bool(env and os.path.exists(os.path.join(MODELS, f)) and os.path.getsize(os.path.join(MODELS, f)) > 1000) for k, (f, _) in FILES.items()}


def install(say=print):
    os.makedirs(MODELS, exist_ok=True)
    if not os.path.exists(python()):
        say("cut-out engines: making a private Python environment…"); subprocess.run([sys.executable, "-m", "venv", VENV], check=True)
    marker = os.path.join(HOME, ".installed"); want = ",".join(PACKAGES)
    if not os.path.exists(marker) or open(marker).read() != want:
        say("cut-out engines: installing packages (a few minutes, once)…")
        subprocess.run([python(), "-m", "pip", "install", "-q", "--upgrade", "pip"], check=True)
        subprocess.run([python(), "-m", "pip", "install", "-q"] + PACKAGES, check=True); open(marker, "w").write(want)
    for name, (f, url) in FILES.items():
        dest = os.path.join(MODELS, f)
        if os.path.exists(dest) and os.path.getsize(dest) > 1000: continue
        say(f"cut-out engines: downloading {f}…"); urllib.request.urlretrieve(url, dest + ".part"); os.replace(dest + ".part", dest)
    say("cut-out engines ready: " + ", ".join(k for k, v in status().items() if v))


if __name__ == "__main__":
    if "--check" in sys.argv:
        for k, v in status().items(): print(f"{k}: {'ready' if v else 'not installed'}")
    else:
        try: install()
        except Exception as e: sys.exit(f"cut-out engines: setup did not finish ({str(e)[:160]}). Reels still work with the current cut-out.")
