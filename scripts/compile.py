#!/usr/bin/env python3
"""Compile a job's resolved timeline into a HyperFrames project. Deterministic, no AI, $0.

    python3 scripts/compile.py jobs/<job> [--platform instagram|tiktok] [--final]

Reads timeline.json + edl.json (written by reel.py) and writes jobs/<job>/hyperframes[_<platform>]/.
"""
import argparse, json, os, shutil, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import config as cfg, matte, sfx_mix       # noqa: E402
from lib import hfbuild, director, pack, broll, layouts, states, reviewer   # noqa: E402


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
    from lib import themes
    themes.use_job(job)                                       # the look he picked before starting (brief.json), else the project setting
    scenes = [dict(s) for s in tl["scenes"]]
    for s in scenes:
        if s["block"] == "cta_card":
            s["values"] = dict(s["values"], handle=handle_for(platform, final))
    words = edl["words"]
    kw = set(tl["keyword_ids"])
    lay_name = layouts.active_name()                          # a chosen LAYOUT (templates/layouts/): stage = animation on top, caption band, cut-out hero at the bottom
    seq_theme = themes.current() if (themes.current() or {}).get("sequence") else None          # a theme that walks through states (templates/states/)
    pk = None if (lay_name or seq_theme) else pack.plan(job, tl, edl)        # FORMAT PACK (T129) decided first: no loose cards = no caption gaps; its highlight words shape the captions (T133)
    gaps = [] if (pk or lay_name or seq_theme) else tl["caption_gaps"]
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
    lay_args, lay_dropped, lay_notes, seq_plan = None, [], [], None
    rep = reviewer.active(job)                                # repairs the AI reviewer asked for after looking at the last draft (repairs.json), if any
    review_notes = []
    ft = None
    if seq_theme and layer == "full":
        bad = states.sequence_problems(seq_theme)
        if bad: raise RuntimeError(f"theme {seq_theme.get('label')} breaks the safe zone: " + "; ".join(bad))
        reg = hfbuild.REGISTRY["blocks"]
        seq_plan = states.plan(seq_theme, [x for x in scenes if x["block"] != "captions"], edl["words"], tl["keyword_ids"], tl["duration"], reg)
        lay_dropped = list(seq_plan["dropped"])
        caption_scenes = [x for x in scenes if x["block"] == "captions"]
        tl = dict(tl, scenes=[])
        bc = seq_plan["base_caption"] or {"y": 790, "h": 80, "size": 76}
        plate = any(i.get("kind") == "caption_unreadable" for i in rep.get("items", []))          # the reviewer found the captions hard to read: a plate behind them
        lay_args = {"stage_rect": [108, 250, 920, 790], "vars": {"cap-top": f"{bc['y']}px", "cap-h": f"{bc['h']}px", "cap-size": f"{bc['size']}px", "cap-pill-bg": "rgba(36,40,52,.78)" if plate else "transparent"},
                    "hero": None, "extra_tweens": seq_plan["tweens"]}
        try:
            shots = json.load(open(os.path.join(job, "shot_log.json"), encoding="utf-8"))
        except (OSError, ValueError):
            shots = []
        m = None
        if seq_plan["needs_hero"]:
            try:
                src = matte.cutout(job, edl, 0.0, tl["duration"], final)
                os.makedirs(os.path.join(out, "assets"), exist_ok=True)
                shutil.copy(src, os.path.join(out, "assets", "hero.webm"))
                hs = next(s["spec"]["clip"] for s in seq_plan["segments"] if s["spec"].get("clip") and s["spec"]["clip"].get("hero"))
                lay_args["hero"] = {"src": "assets/hero.webm", "clip": [0, hs.get("hero_clip_top", 800), 1080, 1920]}
                m = layouts.measure_matte(src, (cfg.find_ffmpeg() or ("ffmpeg",))[0])
            except matte.MatteError as ex:
                lay_notes.append(f"hero cut-out skipped (he shows plainly in the box): {ex}"); print("   ", lay_notes[-1])
                seq_plan["tweens"] = [x for x in seq_plan["tweens"] if "#hero-clip" not in x]
                lay_args["extra_tweens"] = seq_plan["tweens"]
        if m is None: m = layouts.measure_shots(shots)
        lay_notes.append("states: " + " -> ".join(f"{s['state']}@{s['t_in']:.1f}" for s in seq_plan["segments"][:12]) + (" ..." if len(seq_plan["segments"]) > 12 else ""))
        lay_notes.append("head " + (f"measured: width {m['head_w']:.0f}px, top {m['top']:.0f}px" if m else "not measurable: default size"))
        if m is None: m = {"top": 420.0, "head_w": 500.0, "head_cx": 540.0}
        seq_tfs, rv = states.transforms_checked(seq_plan["segments"], m, rep)             # REVIEWER (free): heads cut by an edge are made smaller
        rv += states.avoid_face(seq_plan, m, reg)                                           # text off his face
        rv += states.fill_idle(seq_plan, edl["words"], tl["keyword_ids"], reg, rep)         # empty zones get a card from his own words
        scenes = seq_plan["frames"] + seq_plan["scenes"] + caption_scenes
        review_notes += rv
        lay_notes += [f"reviewer: {x}" for x in rv]
    elif lay_name and layer == "full":
        spec = layouts.load(lay_name)
        probs = layouts.problems(spec)
        if probs: raise RuntimeError(f"layout {lay_name} breaks the safe zone: " + "; ".join(probs))
        pl = layouts.plan(spec, [x for x in scenes if x["block"] != "captions"], tl["duration"], theme=themes.palette(cfg.PROJECT.get("format_pack", {}).get("theme", "dark")), words=edl["words"], kw_idx=tl["keyword_ids"])
        lay_dropped = list(pl["dropped"])
        scenes = ([dict(pl["frame"], groups_html=layouts.frame_groups("stg", spec, pl["frame"]["values"].get("theme", "dark")))] if pl["frame"] else []) + pl["stage"] + [x for x in scenes if x["block"] == "captions"]
        ft = layouts.face_transform(pl["hero"]) if pl["hero"] else layouts.footage_transform(spec, tl.get("face_cy", 0.38))
        tl = dict(tl, scenes=[])
        lay_args = {"stage_rect": pl["stage_rect"], "vars": dict(pl["caption_vars"], **({"cap-pill-bg": "rgba(36,40,52,.78)"} if any(i.get("kind") == "caption_unreadable" for i in rep.get("items", [])) else {})), "hero": None}
        try:
            if not pl["hero"]: raise matte.MatteError("")        # this layout keeps him full-screen: no cut-out needed
            src = matte.cutout(job, edl, 0.0, tl["duration"], final)
            os.makedirs(os.path.join(out, "assets"), exist_ok=True)
            shutil.copy(src, os.path.join(out, "assets", "hero.webm"))
            lay_args["hero"] = dict(pl["hero"], src="assets/hero.webm")
            m = layouts.measure_matte(src, (cfg.find_ffmpeg() or ("ffmpeg",))[0])        # size and place him from his real head, not a fixed guess
            hp = dict(pl["hero"]); hp["head_w_px"] = hp.get("head_w_px", 500) * float(rep.get("head_scale", 1.0))
            ft = layouts.hero_transform(hp, m)
            for _k in range(6 if m else 0):                      # REVIEWER (free): a head cut by an edge is made smaller
                probs = reviewer.head_problems(reviewer.head_box(m, ft), clip_top=hp["clip"][1])
                if not probs: break
                hp["head_w_px"] *= 0.9; hp["min_scale"] = min(hp.get("min_scale", 0.8), 0.6); ft = layouts.hero_transform(hp, m)
                if _k == 0: review_notes.append(f"{probs[0]}; head made smaller"); lay_notes.append("reviewer: " + review_notes[-1])
            lay_notes.append("head " + (f"measured: width {m['head_w']:.0f}px, top {m['top']:.0f}px; scale {ft['scale']}" if m else "not measurable: fixed position used"))
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
    if seq_plan:                                              # each state has its own footage box: cut the footage at the state changes, each piece gets its transform
        cuts = states.split_cuts(cuts, seq_plan["segments"], seq_tfs)
    elif lay_args and ft:                                       # the footage sits in the container; the layout has no punch-ins (the hero stays steady)
        cuts = [dict(c, scale=ft["scale"], cx=0.5, cy=0.38, y=ft["y"], x=ft.get("x", 0)) for c in cuts]
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
                          video_src=os.path.join(job, "proxy.mp4"), transparent=layer == "graphics", audio=audio or None, layout=lay_args,
                          extra_tweens=(lay_args or {}).get("extra_tweens"))
    json.dump({"platform": platform, "final": final, "face_cuts": cuts, "caption_words": len(cap_words), "dropped_scenes": dropped + pack_dropped + lay_dropped, "layout": (lay_name or (seq_theme and themes.CURRENT["name"])) if lay_args else None, "layout_notes": lay_notes, "review": review_notes, "repairs": rep.get("items", []), "sfx": len(audio), "format_pack": bool(pk)},
              open(os.path.join(out, "compile_info.json"), "w"), indent=1)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("job"); ap.add_argument("--platform", default="instagram", choices=["instagram", "tiktok"])
    ap.add_argument("--final", action="store_true")
    a = ap.parse_args()
    print(compile_job(os.path.abspath(a.job), a.platform, a.final))
