#!/usr/bin/env python3
"""Cut-out worker (runs INSIDE Reel Factory's private matte environment, never in the system Python).
    matte_worker.py rvm|mp_selfie IN.mp4 OUT.webm [ffmpeg-path]
Reads a video, writes a transparent WebM (person kept, rest transparent). Models come from ~/.reelfactory/matte/models."""
import os, subprocess, sys

HOME = os.path.expanduser("~/.reelfactory/matte")


def frames(path, ffmpeg, w, h):
    p = subprocess.Popen([ffmpeg, "-v", "error", "-i", path, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    n = w * h * 3
    while True:
        b = p.stdout.read(n)
        if len(b) < n: break
        yield b
    p.wait()


def probe(path, ffmpeg):
    import cv2
    c = cv2.VideoCapture(path); w, h = int(c.get(3)), int(c.get(4)); c.release(); return w, h


def main():
    import numpy as np
    engine, src, out = sys.argv[1:4]; ffmpeg = sys.argv[4] if len(sys.argv) > 4 else "ffmpeg"
    w, h = probe(src, ffmpeg)
    enc = subprocess.Popen([ffmpeg, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{w}x{h}", "-r", "30", "-i", "-",
                            "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-auto-alt-ref", "0", "-b:v", "0", "-crf", "24", "-an", out], stdin=subprocess.PIPE)
    if engine == "rvm":
        import torch
        dev = "mps" if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available() else "cpu"
        m = torch.jit.load(os.path.join(HOME, "models", "rvm_mobilenetv3_fp32.torchscript"), map_location=dev).eval()
        rec = [None] * 4
        def alpha(rgb):
            nonlocal rec
            x = torch.from_numpy(rgb).permute(2, 0, 1)[None].float().to(dev) / 255
            fgr, pha, *rec = m(x, *rec, 0.5)
            return pha[0, 0].float().cpu().numpy()
        ctx = torch.no_grad()
    elif engine == "mp_selfie":
        import mediapipe as mp
        from mediapipe.tasks import python as mpp
        from mediapipe.tasks.python import vision
        seg = vision.ImageSegmenter.create_from_options(vision.ImageSegmenterOptions(
            base_options=mpp.BaseOptions(model_asset_path=os.path.join(HOME, "models", "selfie_segmenter.tflite")), output_confidence_masks=True, output_category_mask=False))
        def alpha(rgb):
            r = seg.segment(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
            a = np.asarray(r.confidence_masks[0].numpy_view(), dtype="float32")
            return a if a.mean() < 0.9 else 1.0 - a            # the selfie model gives "person"; guard against an inverted mask
        ctx = open(os.devnull)
    else:
        sys.exit(f"unknown engine {engine}")
    with ctx:
        for b in frames(src, ffmpeg, w, h):
            rgb = np.frombuffer(b, np.uint8).reshape(h, w, 3)
            a = (np.clip(alpha(rgb), 0, 1) * 255).astype(np.uint8)
            enc.stdin.write(np.dstack([rgb, a]).tobytes())
    enc.stdin.close()
    if enc.wait(): sys.exit("ffmpeg could not write the cut-out")


if __name__ == "__main__":
    main()
