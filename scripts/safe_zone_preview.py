#!/usr/bin/env python3
"""Draw the platform UI zones over a frame or cover (the 'UI overlay mask' check). For looking only; never exported.

    python3 scripts/safe_zone_preview.py jobs/<job>/review/cover.jpg [-o out.jpg]
    python3 scripts/safe_zone_preview.py jobs/<job>/review/draft_540p.mp4 --at 12.5

Red = covered by Instagram/TikTok buttons and captions. Lime frame = safe box. Violet = caption band. White = feed square.
"""
import argparse, os, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import config as cfg  # noqa: E402


def overlay_filter():
    z = cfg.RULES["safe_zone"]; W, H = z["canvas"]
    t, b, l, r = z["top"], z["bottom"], z["left"], z["right"]
    c0, c1 = z["captions_y"]; f0, f1 = z["feed_square_y"]
    red = "color=red@0.32:t=fill"
    return ",".join([
        f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}",
        f"drawbox=x=0:y=0:w={W}:h={t}:{red}", f"drawbox=x=0:y={H - b}:w={W}:h={b}:{red}",
        f"drawbox=x=0:y={t}:w={l}:h={H - t - b}:{red}", f"drawbox=x={W - r}:y={t}:w={r}:h={H - t - b}:{red}",
        f"drawbox=x={l}:y={t}:w={W - l - r}:h={H - t - b}:color=0xB6FF00@0.95:t=5",
        f"drawbox=x={z['text_x']}:y={c0}:w={z['text_max_width']}:h={c1 - c0}:color=0x7D53FF@0.9:t=4",
        f"drawbox=x=0:y={f0}:w={W}:h={f1 - f0}:color=white@0.55:t=3",
    ])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src"); ap.add_argument("--at", type=float); ap.add_argument("-o", "--out")
    a = ap.parse_args()
    out = a.out or os.path.splitext(a.src)[0] + "_safezones.jpg"
    cmd = ["ffmpeg", "-v", "error", "-y"] + (["-ss", str(a.at)] if a.at is not None else []) + ["-i", a.src, "-frames:v", "1",
                                                                                               "-vf", overlay_filter(), "-q:v", "3", out]
    subprocess.run(cmd, check=True)
    print(out)


if __name__ == "__main__":
    main()
