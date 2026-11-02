"""Stage 5 visual plan. Free, local. Describes, in one structured file, what the viewer will see and when:
caption events (timing, words, language, reading speed, where on the 1080x1920 canvas), graphics (role, time, zone),
animations (zooms, keyword pops), the brand styling used, how busy the reel is, and plain-words checks.

It READS the finished timeline; it never changes it. Captions use the same grouping rule as the renderer (hfbuild.caption_events),
so this plan matches the video. Roles are kept apart on purpose: subtitles (every spoken word), emphasis (keyword colour,
zooms, flashes) and editorial titles/graphics (cards that add something the words don't say).
"""
import json, os, re

from lib import config as cfg, hfbuild, brand_memory

ARABIC = re.compile(r"[؀-ۿ]")
LATIN = re.compile(r"[A-Za-z]")
MAX_CPS = 20.0          # characters per second on screen: faster than this is hard to read
MIN_SHOW = 0.35         # a caption shown for less than this is a flicker
ROLE = {"hook_two_tone": "editorial title", "text_card": "editorial title", "name_tag": "editorial title", "info_card": "editorial title",
        "number_graph": "editorial graphic", "before_after": "editorial graphic", "tier_list": "editorial graphic", "split": "editorial graphic",
        "logo_card": "editorial graphic", "cta_card": "call to action", "flash": "emphasis"}
NOT_GRAPHICS = ("captions", "face_cut")


def _jl(path, d=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return d


def lang(text):
    a, l = bool(ARABIC.search(text)), bool(LATIN.search(text))
    return "mixed" if a and l else "ar" if a else "en" if l else "other"


def intensity(tl, n_cap_words):
    dur = max(1.0, tl.get("duration", 1.0)); mins = dur / 60.0
    gr = [s for s in tl.get("scenes", []) if s["block"] not in NOT_GRAPHICS + ("hook_two_tone", "cta_card")]
    cover, last = 0.0, -1.0
    for s in sorted(gr, key=lambda s: s["t_in"]):
        a = max(s["t_in"], last)
        if s["t_out"] > a:
            cover += s["t_out"] - a; last = s["t_out"]
    return {"moments_per_min": round(len(gr) / mins, 2), "punch_ins_per_min": round(len(tl.get("punch_ins", [])) / mins, 2),
            "caption_words_per_min": round(n_cap_words / mins, 1), "text_screen_share": round(min(1.0, cover / dur), 2)}


def build(job):
    tl, edl = _jl(os.path.join(job, "timeline.json")), _jl(os.path.join(job, "edl.json"))
    if not tl or not edl:
        return None
    words = edl["words"]
    zone = cfg.RULES["safe_zone"]; capr = cfg.RULES["captions"]; bcap = cfg.BRAND.get("captions", {})
    kw = set(tl.get("keyword_ids", []))
    keep = [i for i, w in enumerate(words) if not any(a - 0.05 <= w["start"] < b for a, b in tl.get("caption_gaps", []))]
    cw = [words[i] for i in keep]
    kwc = {k for k, i in enumerate(keep) if i in kw}
    events, flags, fast, flick, mixed = [], [], 0, 0, 0
    for ev in hfbuild.caption_events(cw, stops=[a for a, _ in tl.get("caption_gaps", [])]):
        txt = " ".join(cw[i]["text"] for i in ev["idx"]); d = ev["end"] - ev["start"]
        cps = round(len("".join(cw[i]["text"] for i in ev["idx"])) / max(d, 0.01), 1)
        lg = lang(txt)
        fast += cps > MAX_CPS; flick += d < MIN_SHOW; mixed += lg == "mixed"
        events.append({"start": round(ev["start"], 2), "end": round(ev["end"], 2), "text": txt, "language": lg,
                       "direction": "rtl" if lg in ("ar", "mixed") else "ltr", "chars_per_sec": cps,
                       "keywords": [cw[i]["text"] for k, i in enumerate(ev["idx"]) if ev["idx"][k] in kwc],
                       "lines": 1, "y_band": zone["captions_y"], "x_range": [zone["left"], 1080 - zone["right"]]})
    if fast:
        flags.append(f"{fast} caption(s) go faster than {MAX_CPS:g} characters per second: hard to read")
    if flick:
        flags.append(f"{flick} caption(s) stay on screen under {MIN_SHOW} s")
    graphics = [{"id": s["id"], "block": s["block"], "role": ROLE.get(s["block"], "editorial graphic"), "t_in": s["t_in"], "t_out": s["t_out"],
                 "text": [str(v) for v in (s.get("values") or {}).values() if isinstance(v, str)][:4],
                 "zone": {"x": [zone["left"], 1080 - zone["right"]], "y": [zone["top"], zone["never_below_y"]]}}
                for s in tl.get("scenes", []) if s["block"] not in NOT_GRAPHICS]
    # faces vs the caption area: the face must stay above the captions
    shots = _jl(os.path.join(job, "shot_log.json"), []) or []
    fb = sorted((r["face"]["y"] + r["face"]["h"]) * zone["canvas"][1] for r in shots if r.get("face"))
    if fb and fb[len(fb) // 2] > zone["captions_y"][0]:
        flags.append(f"the face reaches down to y={fb[len(fb) // 2]:.0f}, into the caption area (from {zone['captions_y'][0]}): captions may cover the chin")
    fx = sorted((r["face"]["x"] + r["face"]["w"] / 2) for r in shots if r.get("face"))
    man = _jl(os.path.join(job, "media_manifest.json"), {}) or {}
    horizontal = [f["name"] for f in man.get("files", []) if f.get("use") and f.get("orientation") == "horizontal"]
    if horizontal and fx and not 0.35 <= fx[len(fx) // 2] <= 0.65:
        flags.append(f"{', '.join(horizontal[:2])} was filmed horizontally and the face sits off-centre ({fx[len(fx) // 2]:.2f}): the 9:16 crop may cut the face")
    elif horizontal:
        flags.append(f"{', '.join(horizontal[:2])} was filmed horizontally: the sides are cropped to 9:16 around the centre")
    inten = intensity(tl, len(cw))
    flags += brand_memory.compare(inten)
    if inten["text_screen_share"] > 0.6:
        flags.append(f"cards or graphics are on screen {inten['text_screen_share'] * 100:.0f}% of the time: the screen may feel crowded")
    plan = {
        "version": 1, "canvas": zone["canvas"],
        "safe_area": {"x": [zone["left"], 1080 - zone["right"]], "y": [zone["top"], zone["never_below_y"]], "captions_y": zone["captions_y"], "text_max_width": zone["text_max_width"]},
        "brand": {"font": cfg.BRAND.get("font", {}).get("family"), "colors": cfg.BRAND.get("colors"), "digits": cfg.BRAND.get("digits"),
                  "captions": {"max_words_on_screen": capr["max_words"], "min_size_px": bcap.get("min_size_px"), "base_weight": bcap.get("base_weight"),
                               "keyword": bcap.get("keyword")}},
        "captions": {"events": events, "count": len(events), "mixed_language_groups": mixed,
                     "note": "Right-to-left Arabic with English terms in Latin letters; numbers are Western digits."},
        "graphics": graphics,
        "animations": {"punch_ins": [{"t": t, "scale": s} for t, s in tl.get("punch_ins", [])],
                       "keyword_pop_scale": (bcap.get("keyword") or {}).get("pop_scale"), "keywords": len(kw)},
        "intensity": inten, "learned_from_approved": brand_memory.profile(),
        "checks": flags,
    }
    tmp = os.path.join(job, "visual_plan.json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False)
    os.replace(tmp, os.path.join(job, "visual_plan.json"))
    return plan


def summary_lines(vp):
    i = vp["intensity"]
    L = [f"{vp['captions']['count']} caption groups, {len(vp['graphics'])} graphics/cards, {len(vp['animations']['punch_ins'])} zooms; "
         f"{i['moments_per_min']} cards/min, {i['punch_ins_per_min']} zooms/min, text on screen {i['text_screen_share'] * 100:.0f}% of the time"]
    L += [f"check: {c}" for c in vp["checks"][:6]]
    return L


def block_counts(vp):
    out = {}
    for g in vp["graphics"]:
        out[g["block"]] = out.get(g["block"], 0) + 1
    return out
