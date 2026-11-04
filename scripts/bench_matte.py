#!/usr/bin/env python3
"""CUT-OUT BENCHMARK: compares ways to cut a person out of a talking-head clip, on YOUR computer, with YOUR clip. Free, no AI keys, nothing is uploaded.

    python3 scripts/bench_matte.py "/path/to/clip.MOV"            (about 15-30 minutes the first time, mostly downloads)
    python3 scripts/bench_matte.py "/path/to/clip.MOV" --only current,rvm      (just some of them)

What it does (read this before you run it):
  1. makes a private folder  ~/matte_bench/  and a Python environment inside it (nothing is installed anywhere else);
  2. installs these packages from the official Python package index: numpy, pillow, opencv-python-headless, torch, mediapipe, rembg, onnxruntime;
  3. downloads these model files, each from its official source:
       Robust Video Matting (TorchScript, GPL-3.0)   github.com/PeterL1n/RobustVideoMatting  (release v1.0.0)
       MediaPipe selfie segmenters (Apache-2.0)       storage.googleapis.com/mediapipe-models
       rembg models u2net_human_seg / isnet-general-use (the rembg package downloads them itself)
  4. cuts the first SECONDS (default 2 s) of your clip into 540x960 frames and runs each method on the SAME frames;
  5. writes  ~/matte_bench/RESULT/compare.jpg  (each method over green, same frames side by side) and  results.txt  (seconds per frame and how long a
     60 s reel would take). Send both files to Claude.
Nothing in your project is touched. To remove everything afterwards:  rm -rf ~/matte_bench
Models and licences: some are non-commercial or copyleft; this benchmark only LOOKS at quality and speed. Check the licence before using any in reels."""
import argparse, json, os, shutil, subprocess, sys, time, urllib.request

HOME = os.path.expanduser("~/matte_bench")
VENV = os.path.join(HOME, "venv")
RVM_URL = "https://github.com/PeterL1n/RobustVideoMatting/releases/download/v1.0.0/rvm_mobilenetv3_fp32.torchscript"
MP_URL = "https://storage.googleapis.com/mediapipe-models/image_segmenter/{p}"
MP_MODELS = {"mp_selfie": "selfie_segmenter/float16/latest/selfie_segmenter.tflite",
             "mp_multiclass": "selfie_multiclass_256x256/float32/latest/selfie_multiclass_256x256.tflite"}
PACKAGES = ["numpy", "pillow", "opencv-python-headless", "torch", "mediapipe", "rembg", "onnxruntime"]
METHODS = ["current", "rvm", "mp_selfie", "mp_multiclass", "rembg_human", "rembg_isnet"]
LABEL = {"current": "A  current (HyperFrames u2net)", "rvm": "B  Robust Video Matting", "mp_selfie": "C  MediaPipe selfie (OpenReel)", "mp_multiclass": "D  MediaPipe multiclass",
         "rembg_human": "E  rembg u2net_human_seg (OpenMontage)", "rembg_isnet": "F  rembg isnet-general"}


def say(*a): print(*a, flush=True)


def find_ffmpeg():
    """ffmpeg is where Reel Factory finds it; a fresh Terminal window may not have that folder on its search path, so look in the usual places too."""
    for c in [shutil.which("ffmpeg"), "/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/opt/local/bin/ffmpeg", os.path.expanduser("~/.reelfactory/bin/ffmpeg")]:
        if c and os.path.exists(c): return c
    return None


FFMPEG = find_ffmpeg() or "ffmpeg"
os.environ["PATH"] = os.path.dirname(FFMPEG) + os.pathsep + os.environ.get("PATH", "") if os.path.dirname(FFMPEG) else os.environ.get("PATH", "")


def download(url, dest):
    if os.path.exists(dest) and os.path.getsize(dest) > 1000: return dest
    say(f"   downloading {os.path.basename(dest)} ...")
    urllib.request.urlretrieve(url, dest + ".part"); os.replace(dest + ".part", dest); return dest


def ensure_env():
    """Create the private environment and re-run this script inside it. Returns only when already inside it."""
    if os.path.realpath(sys.prefix) == os.path.realpath(VENV): return
    os.makedirs(HOME, exist_ok=True)
    py = os.path.join(VENV, "bin", "python")
    if not os.path.exists(py):
        say("1/4 making a private Python environment in", VENV); subprocess.run([sys.executable, "-m", "venv", VENV], check=True)
    marker = os.path.join(HOME, ".installed")
    if not os.path.exists(marker):
        say("2/4 installing packages (official Python package index): " + ", ".join(PACKAGES) + "  (a few minutes)")
        subprocess.run([py, "-m", "pip", "install", "-q", "--upgrade", "pip"], check=True)
        subprocess.run([py, "-m", "pip", "install", "-q"] + PACKAGES, check=True); open(marker, "w").write("ok")
    os.execv(py, [py, os.path.abspath(__file__)] + sys.argv[1:])


def make_frames(clip, seconds, size=(540, 960)):
    d = os.path.join(HOME, "frames"); shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
    say(f"3/4 cutting the first {seconds} s of the clip into {size[0]}x{size[1]} frames")
    src = os.path.join(HOME, "src540.mp4")
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-i", clip, "-t", str(seconds), "-vf", f"fps=30,scale={size[0]}:{size[1]}:flags=lanczos,format=yuv420p",
                    "-an", "-c:v", "libx264", "-crf", "14", "-preset", "veryfast", src], check=True)
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-i", src, os.path.join(d, "%04d.png")], check=True)
    return src, sorted(os.path.join(d, f) for f in os.listdir(d) if f.endswith(".png"))


def orient(alpha):
    """A segmenter may return 'person' or 'background'. The person is large and central in a talking-head clip: if the centre is mostly empty, flip it."""
    import numpy as np
    h, w = alpha.shape
    c = alpha[int(h * .3):int(h * .7), int(w * .3):int(w * .7)]
    return 1.0 - alpha if c.mean() < 0.3 else alpha


def run_current(files, src):
    import numpy as np, cv2
    cfgp = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "project.json")
    ver = json.load(open(cfgp)).get("tools", {}).get("hyperframes", "0.8.226") if os.path.exists(cfgp) else "0.8.226"
    out = os.path.join(HOME, "current.webm")
    t = time.time()
    subprocess.run(["npx", "--yes", f"hyperframes@{ver}", "remove-background", src, "-o", out, "--quality", "fast"], check=True, capture_output=True, text=True)
    total = time.time() - t
    d = os.path.join(HOME, "current_frames"); shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-c:v", "libvpx-vp9", "-i", out, "-vf", "format=rgba", os.path.join(d, "%04d.png")], check=True)
    alphas = []
    for f in sorted(os.listdir(d))[:len(files)]:
        a = cv2.imread(os.path.join(d, f), cv2.IMREAD_UNCHANGED)
        alphas.append((a[:, :, 3] if a.ndim == 3 and a.shape[2] == 4 else np.zeros(a.shape[:2], np.uint8)).astype("float32") / 255)
    return alphas, total / max(1, len(alphas))


def run_rvm(files, src):
    import numpy as np, cv2, torch
    path = download(RVM_URL, os.path.join(HOME, "rvm_mobilenetv3_fp32.torchscript"))
    dev = "mps" if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available() else "cpu"
    m = torch.jit.load(path, map_location=dev).eval()
    rec = [torch.zeros(1, device=dev)] * 4; ratio = torch.tensor([0.5], device=dev); alphas, times = [], []
    with torch.no_grad():
        for f in files:
            x = torch.from_numpy(cv2.cvtColor(cv2.imread(f), cv2.COLOR_BGR2RGB)).permute(2, 0, 1)[None].float().to(dev) / 255
            t = time.time(); fgr, pha, *rec = m(x, *rec, ratio)
            if dev == "mps": torch.mps.synchronize()
            times.append(time.time() - t); alphas.append(pha[0, 0].float().cpu().numpy())
    say(f"      (Robust Video Matting ran on: {dev})")
    return alphas, sum(times[1:] or times) / max(1, len(times[1:] or times))      # the first frame includes start-up


def run_mp(which):
    def go(files, src):
        import numpy as np, cv2, mediapipe as mp
        from mediapipe.tasks import python as mpp
        from mediapipe.tasks.python import vision
        path = download(MP_URL.format(p=MP_MODELS[which]), os.path.join(HOME, os.path.basename(MP_MODELS[which])))
        seg = vision.ImageSegmenter.create_from_options(vision.ImageSegmenterOptions(base_options=mpp.BaseOptions(model_asset_path=path), output_confidence_masks=True, output_category_mask=False))
        alphas, times = [], []
        for f in files:
            im = cv2.cvtColor(cv2.imread(f), cv2.COLOR_BGR2RGB); mi = mp.Image(image_format=mp.ImageFormat.SRGB, data=im)
            t = time.time(); r = seg.segment(mi); times.append(time.time() - t)
            ms = [np.asarray(x.numpy_view(), dtype="float32") for x in r.confidence_masks]
            a = ms[0] if len(ms) == 1 else 1.0 - ms[0]                         # several masks: index 0 is the background
            alphas.append(orient(a))
        return alphas, sum(times[1:] or times) / max(1, len(times[1:] or times))
    return go


def run_rembg(model):
    def go(files, src):
        import numpy as np
        from PIL import Image
        from rembg import new_session, remove
        sess = new_session(model); alphas, times = [], []
        for f in files:
            im = Image.open(f).convert("RGB"); t = time.time(); r = remove(im, session=sess, only_mask=True); times.append(time.time() - t)
            alphas.append(np.asarray(r.convert("L"), dtype="float32") / 255)
        return alphas, sum(times[1:] or times) / max(1, len(times[1:] or times))
    return go


RUNNERS = {"current": run_current, "rvm": run_rvm, "mp_selfie": run_mp("mp_selfie"), "mp_multiclass": run_mp("mp_multiclass"),
           "rembg_human": run_rembg("u2net_human_seg"), "rembg_isnet": run_rembg("isnet-general-use")}


def steadiness(alphas):
    """Mean change of the cut-out between neighbouring frames (lower = steadier, less edge flicker)."""
    import numpy as np
    if len(alphas) < 2: return 0.0
    return float(np.mean([np.abs(alphas[i] - alphas[i - 1]).mean() for i in range(1, len(alphas))]))


def build_sheet(files, results, out_path, pick=(0.1, 0.5, 0.9)):
    """Rows = methods, columns = three of the frames, person over green. Same frames for everyone."""
    from PIL import Image, ImageDraw
    import numpy as np
    idx = [min(len(files) - 1, int(p * len(files))) for p in pick]
    base = [Image.open(files[i]).convert("RGB") for i in idx]
    w, h = base[0].size; tw, th = w // 2, h // 2
    sheet = Image.new("RGB", (len(idx) * tw + 6 * (len(idx) - 1), len(results) * (th + 28)), (20, 20, 20))
    d = ImageDraw.Draw(sheet)
    for r, (name, alphas, spf) in enumerate(results):
        y = r * (th + 28)
        d.text((6, y + 7), f"{LABEL.get(name, name)}   {spf:.2f} s/frame" if alphas else f"{LABEL.get(name, name)}   FAILED", fill=(235, 235, 235))
        if not alphas: continue
        for c, i in enumerate(idx):
            a = np.clip(alphas[min(i, len(alphas) - 1)], 0, 1)[:, :, None]
            green = np.array([0, 200, 90], dtype="float32")
            comp = (np.asarray(base[c], dtype="float32") * a + green * (1 - a)).astype("uint8")
            sheet.paste(Image.fromarray(comp).resize((tw, th)), (c * (tw + 6), y + 28))
    sheet.save(out_path, quality=90); return out_path


def selftest():
    """No models, no downloads: checks the frame sheet and the numbers with invented masks."""
    import numpy as np
    from PIL import Image
    d = os.path.join(HOME, "selftest"); os.makedirs(d, exist_ok=True)
    files = []
    for k in range(6):
        p = os.path.join(d, f"{k}.png"); Image.fromarray((np.random.rand(960, 540, 3) * 255).astype("uint8")).save(p); files.append(p)
    a = np.zeros((960, 540), "float32"); a[200:900, 100:440] = 1
    res = [("current", [a] * 6, 0.9), ("rvm", [1 - a] * 6, 0.1), ("rembg_isnet", [], 0.0)]
    build_sheet(files, res, os.path.join(d, "sheet.jpg"))
    assert orient(1 - a).mean() == a.mean(), "orientation fix"
    assert steadiness([a, a]) == 0.0 and steadiness([a, 1 - a]) == 1.0
    say("self-test OK:", os.path.join(d, "sheet.jpg"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("clip", nargs="?"); ap.add_argument("--seconds", type=float, default=2.0); ap.add_argument("--only", default=",".join(METHODS))
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest: selftest(); return
    if not a.clip or not os.path.exists(os.path.expanduser(a.clip)): sys.exit("give the path of your clip, e.g.  python3 scripts/bench_matte.py ~/Downloads/IMG_0124.MOV")
    if not find_ffmpeg(): sys.exit("I cannot find ffmpeg. Run  which ffmpeg  in Terminal; if it prints nothing, run  brew install ffmpeg  and try again.")
    ensure_env()
    clip = os.path.expanduser(a.clip); os.makedirs(HOME, exist_ok=True)
    src, files = make_frames(clip, a.seconds)
    say(f"4/4 running the methods on {len(files)} frames (each prints its speed when done)")
    results = []
    for name in [m for m in a.only.split(",") if m in RUNNERS]:
        say(f" - {LABEL[name]} ...")
        try:
            alphas, spf = RUNNERS[name](files, src); results.append((name, alphas, spf)); say(f"   done: {spf:.2f} s per frame; steadiness {steadiness(alphas):.4f}")
        except Exception as e:                                                       # one method failing never stops the others
            results.append((name, [], 0.0)); say(f"   FAILED: {str(e)[:200]}")
    out = os.path.join(HOME, "RESULT"); os.makedirs(out, exist_ok=True)
    sheet = build_sheet(files, results, os.path.join(out, "compare.jpg"))
    lines = ["Cut-out benchmark", f"clip: {os.path.basename(clip)}   frames: {len(files)} (540x960)   machine: {os.uname().sysname} {os.uname().machine}", ""]
    for name, alphas, spf in results:
        lines.append(f"{LABEL[name]:46s} " + (f"{spf:6.2f} s/frame   a 60 s reel (1800 frames) = {spf * 1800 / 60:5.1f} min   edge steadiness {steadiness(alphas):.4f} (lower = steadier)" if alphas else "FAILED"))
    lines += ["", "Licences (check before use in reels): current u2net = Apache-2.0; Robust Video Matting = GPL-3.0; MediaPipe models = Apache-2.0; rembg = MIT (its models have their own licences)."]
    open(os.path.join(out, "results.txt"), "w").write("\n".join(lines) + "\n")
    say("\n".join(lines)); say(f"\nSend these two files to Claude:\n  {sheet}\n  {os.path.join(out, 'results.txt')}")


if __name__ == "__main__":
    main()
