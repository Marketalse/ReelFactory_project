#!/usr/bin/env python3
"""Compile a job's resolved timeline into a HyperFrames project. Deterministic, no AI, $0.

    python3 scripts/compile.py jobs/<job> [--platform instagram|tiktok] [--final]

Reads timeline.json + edl.json (written by reel.py) and writes jobs/<job>/hyperframes[_<platform>]/.
"""
import argparse, json, os, shutil, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import config as cfg, matte, sfx_mix       # noqa: E402
from lib import hfbuild, director, pack, broll, layouts   # noqa: E402


def handle_for(platform, final):
    h = (cfg.BRAND.get("handles") or {}).get(platform, "")
    if not h or "CONFIRM" in h:
        if final:
            raise hfbuild.BuildError(f"No {platform} handle in config/brand.json -> handles.{platform}. Set it before the final render.")
        return "@your_handle"
    return h


def _behind_top(text, face_cy):
    """Text height so the head covers only the lower ~38% of the letters (still readable). Head top is about 0.11 of the frame above the face centre."""
    size = hfbuild.fit_size(text, 230, 80)
    return int(max(250, (face_cy - 0.11) * 1920 - 0.62 * size * 1.05))


def compile_job(job, platform="instagram", final=False, out=None, layer="full"):
    """layer: full (the reel), video (you, cut + zooms, with sound) or graphics (everything else, transparent)."""
    tl = json.load(open(os.path.join(job, "timeline.json"), encoding="utf-8"))
    edl = json.load(open(os.path.join(job, "edl.json"), encoding="utf-8"))
    out = out or os.path.join(job, ("hyperframes" if not final else f"hyperframes_{platform}") + ("" if layer == "full" else f"_{layer}"))
    scenes = [dict(s) for s in tl["scenes"]]
    for s in scenes:
        if s["block"] == "cta_card":
            s["values"] = dict(s["values"], handle=handle_for(platform, final))
    words = edl["words"]
    kw = set(tl["keyword_ids"])
    lay_name = layouts.active_name()                          # a chosen LAYOUT (templates/layouts/): stage = animation on top, caption band, cut-out hero at the bottom
    pk = None if lay_name else pack.plan(job, tl, edl)        # FORMAT PACK (T129) decided first: no loose cards = no caption gaps; its highlight words shape the captions (T133)
    gaps = [] if (pk or lay_name) else tl["caption_gaps"]
    keep = [i for i, w in enumerate(words) if not any(a - 0.05 <= w["start"] < b for a, b in gaps)]
    cap_words = [words[i] for i in keep]
    cap_kw = [k for k, i in enumerate(keep) if i in kw]
    hl = [k for k, i in enumerate(keep) if pk and i in pk["highlight"]]
    scenes.append({"id": "caps", "block": "captions", "t_in": 0.0, "t_out": tl["duration"], "values": {},
                   "groups_html": hfbuild.caption_groups(cap_words, cap_kw, "caps", stops=[a for a, _ in gaps],
                                                         pill_idx=hl, pill_style=pk["pill_style"] if pk else "")})
    # FORMAT PACK (T129): an explainer/tips reel gets ONE designed frame; the director's loose cards are replaced by it
    pack_dropped = [x["id"] for x in tl["scenes"]] if pk else []          # the director's loose cards are replaced by the pack: tell the render check they are gone on purpose
    if pk:
        scenes = (pk["scenes"] if layer != "video" else [])  + [s for s in scenes if s["block"] == "captions" and layer != "video"]
        tl = dict(tl, scenes=[])                                  # no split/zoom cards: the face window stays put (punch-ins still work)
        os.makedirs(os.path.join(out, "assets", "icons"), exist_ok=True)
        accent = (cfg.PROJECT.get("format_pack", {}).get("colors") or {}).get("accent") if cfg.PROJECT.get("format_pack", {}).get("theme") == "custom" else cfg.BRAND["colors"]["accent"]
        for f in pk["icons"]:
            src = pack.icon_src(f)
            if not src: continue
            if f.lower().endswith(".svg") and not f.startswith("icon-"):         # the big library: paint dark icons in the accent colour
                open(os.path.join(out, "assets", "icons", f), "w", encoding="utf-8").write(pack.paint(open(src, encoding="utf-8").read(), accent))
            else:
                shutil.copy(src, os.path.join(out, "assets", "icons", f))
    lay_args, lay_dropped, lay_notes = None, [], []
    if lay_name and layer == "full":
        spec = layouts.load(lay_name)
        probs = layouts.problems(spec)
        if probs: raise RuntimeError(f"layout {lay_name} breaks the safe zone: " + "; ".join(probs))
        pl = layouts.plan(spec, [x for x in scenes if x["block"] != "captions"], tl["duration"], theme=cfg.PROJECT.get("format_pack", {}).get("theme", "dark"))
        lay_dropped = list(pl["dropped"])
        scenes = ([dict(pl["frame"], groups_html=layouts.frame_groups("stg", spec, pl["frame"]["values"].get("theme", "dark")))] if pl["frame"] else []) + pl["stage"] + [x for x in scenes if x["block"] == "captions"]
        ft = layouts.face_transform(pl["hero"]) if pl["hero"] else None
        tl = dict(tl, scenes=[])
        lay_args = {"stage_rect": pl["stage_rect"], "vars": pl["caption_vars"], "hero": None}
        try:
            if not pl["hero"]: raise matte.MatteError("")        # this layout keeps him full-screen: no cut-out needed
            src = matte.cutout(job, edl, 0.0, tl["duration"], final)
            os.makedirs(os.path.join(out, "assets"), exist_ok=True)
            shutil.copy(src, os.path.join(out, "assets", "hero.webm"))
            lay_args["hero"] = dict(pl["hero"], src="assets/hero.webm")
        except matte.MatteError as ex:
            if pl["hero"]:
                lay_notes.append(f"hero cut-out skipped (the footage shows plainly in its container): {ex}")
                print("   ", lay_notes[-1])
    # text behind the head (T119): the person cutout is made here (local AI model, cached); a moment that can't get one is dropped, not fatal
    behind = [s for s in scenes if s["block"] == "text_behind"]
    dropped = []
    if behind and layer != "video":
        shots = []
        try:
            shots = json.load(open(os.path.join(job, "shot_log.json"), encoding="utf-8"))
        except (OSError, ValueError):
            pass
        for s in behind:
            try:
                if not matte.face_ok(shots):
                    raise matte.MatteError("the face is not in the middle of the frame")
                src = matte.cutout(job, edl, s["t_in"], s["t_out"], final)
                os.makedirs(os.path.join(out, "assets"), exist_ok=True)
                shutil.copy(src, os.path.join(out, "assets", f"matte_{s['id']}.webm"))
                s["values"] = dict(s.get("values") or {}, matte=f"assets/matte_{s['id']}.webm", top=_behind_top(s["values"].get("text", ""), tl.get("face_cy", 0.38)))
            except matte.MatteError as e:
                print(f"   text behind the head dropped at {s['t_in']:.1f}s: {e}")
                scenes.remove(s); dropped.append(s["id"])
        tl = dict(tl, scenes=[x for x in tl["scenes"] if x["block"] != "text_behind" or any(y["id"] == x["id"] for y in scenes)])
    elif behind:
        dropped = [s["id"] for s in behind]
        scenes = [s for s in scenes if s["block"] != "text_behind"]
    cuts = director.face_cuts(tl, edl["segments"])
    if lay_args and ft:                                       # the footage sits in the container; the layout has no punch-ins (the hero stays steady)
        cuts = [dict(c, scale=ft["scale"], cx=0.5, cy=0.38, y=ft["y"]) for c in cuts]
    # logos used by this reel
    src_logos = os.path.join(job, "assets")
    if os.path.isdir(src_logos):
        os.makedirs(os.path.join(out, "assets", "logos"), exist_ok=True)
        for f in os.listdir(src_logos):
            if f.lower().endswith((".svg", ".png", ".jpg", ".jpeg", ".webp")):
                shutil.copy(os.path.join(src_logos, f), os.path.join(out, "assets", "logos", f))
    if layer == "video":
        scenes = []
    audio = []
    if layer == "full":                                       # sound effects (T127): only in the full reel, never in the clean video layer
        try:
            ev = sfx_mix.plan(dict(tl, scenes=[s for s in scenes if s["block"] != "captions"]), hfbuild.REGISTRY["blocks"], cap_words, cap_kw)
            audio = sfx_mix.project_audio(ev, tl["duration"], out)
        except Exception as ex:                               # noqa: BLE001 - no sound effects is better than no reel
            print("   sound effects skipped:", ex)
    hfbuild.build_project(out, duration=tl["duration"], face_cuts=[] if layer == "graphics" else cuts, scenes=scenes,
                          video_src=os.path.join(job, "proxy.mp4"), transparent=layer == "graphics", audio=audio or None, layout=lay_args)
    json.dump({"platform": platform, "final": final, "face_cuts": cuts, "caption_words": len(cap_words), "dropped_scenes": dropped + pack_dropped + lay_dropped, "layout": lay_name if lay_args else None, "layout_notes": lay_notes, "sfx": len(audio), "format_pack": bool(pk)},
              open(os.path.join(out, "compile_info.json"), "w"), indent=1)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("job"); ap.add_argument("--platform", default="instagram", choices=["instagram", "tiktok"])
    ap.add_argument("--final", action="store_true")
    a = ap.parse_args()
    print(compile_job(os.path.abspath(a.job), a.platform, a.final))
