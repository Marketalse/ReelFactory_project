#!/usr/bin/env python3
"""Compile a job's resolved timeline into a HyperFrames project. Deterministic, no AI, $0.

    python3 scripts/compile.py jobs/<job> [--platform instagram|tiktok] [--final]

Reads timeline.json + edl.json (written by reel.py) and writes jobs/<job>/hyperframes[_<platform>]/.
"""
import argparse, json, os, shutil, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import config as cfg       # noqa: E402
from lib import hfbuild, director   # noqa: E402


def handle_for(platform, final):
    h = (cfg.BRAND.get("handles") or {}).get(platform, "")
    if not h or "CONFIRM" in h:
        if final:
            raise hfbuild.BuildError(f"No {platform} handle in config/brand.json -> handles.{platform}. Set it before the final render.")
        return "@your_handle"
    return h


def compile_job(job, platform="instagram", final=False, out=None):
    tl = json.load(open(os.path.join(job, "timeline.json"), encoding="utf-8"))
    edl = json.load(open(os.path.join(job, "edl.json"), encoding="utf-8"))
    out = out or os.path.join(job, "hyperframes" if not final else f"hyperframes_{platform}")
    scenes = [dict(s) for s in tl["scenes"]]
    for s in scenes:
        if s["block"] == "cta_card":
            s["values"] = dict(s["values"], handle=handle_for(platform, final))
    words = edl["words"]
    kw = set(tl["keyword_ids"])
    keep = [i for i, w in enumerate(words) if not any(a - 0.05 <= w["start"] < b for a, b in tl["caption_gaps"])]
    cap_words = [words[i] for i in keep]
    cap_kw = [k for k, i in enumerate(keep) if i in kw]
    scenes.append({"id": "caps", "block": "captions", "t_in": 0.0, "t_out": tl["duration"], "values": {},
                   "groups_html": hfbuild.caption_groups(cap_words, cap_kw, "caps")})
    cuts = director.face_cuts(tl, edl["segments"])
    # logos used by this reel
    src_logos = os.path.join(job, "assets")
    if os.path.isdir(src_logos):
        os.makedirs(os.path.join(out, "assets", "logos"), exist_ok=True)
        for f in os.listdir(src_logos):
            if f.lower().endswith((".svg", ".png", ".jpg", ".jpeg", ".webp")):
                shutil.copy(os.path.join(src_logos, f), os.path.join(out, "assets", "logos", f))
    hfbuild.build_project(out, duration=tl["duration"], face_cuts=cuts, scenes=scenes,
                          video_src=os.path.join(job, "proxy.mp4"))
    json.dump({"platform": platform, "final": final, "face_cuts": cuts, "caption_words": len(cap_words)},
              open(os.path.join(out, "compile_info.json"), "w"), indent=1)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("job"); ap.add_argument("--platform", default="instagram", choices=["instagram", "tiktok"])
    ap.add_argument("--final", action="store_true")
    a = ap.parse_args()
    print(compile_job(os.path.abspath(a.job), a.platform, a.final))
