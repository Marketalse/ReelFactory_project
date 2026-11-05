"""LAYOUTS: reel structures chosen as templates (templates/layouts/<name>.json). Free, no AI.

A layout is a list of ZONES on the 1080x1920 canvas (where the animation stage, the caption band, the footage container and the hero cut-out
live) plus which blocks may play in the stage. It never contains template code: the existing blocks are FITTED into a zone (scaled and moved
by their measured natural box, `natural_box` in templates/blocks/registry.json, made by scripts/measure_blocks.py) so every block and every
future layout can be combined without rewriting blocks. Every layout is checked against the safe zone (config/rules.json -> safe_zone) before use.

  layouts.load("stage")                -> the spec
  layouts.problems(spec)               -> [text]  (empty = every zone inside the safe zone and no overlapping zones)
  layouts.fit(zone_rect, natural_box)  -> (tx, ty, scale) to place a block's 1080x1920 host so its box sits centred inside the zone (never enlarged)
  layouts.plan(spec, tl, edl, ...)     -> what the compiler needs: frame scene, fitted stage scenes, caption variables, hero transform
"""
import json, os

from . import config as cfg, hfbuild

DIR = os.path.join(cfg.ROOT, "templates", "layouts")


def names():
    return sorted(f[:-5] for f in os.listdir(DIR) if f.endswith(".json")) if os.path.isdir(DIR) else []


def load(name):
    with open(os.path.join(DIR, os.path.basename(name) + ".json"), encoding="utf-8") as f:
        return json.load(f)


def _inside(r, box):
    return r[0] >= box[0] and r[1] >= box[1] and r[2] <= box[2] and r[3] <= box[3]


def _overlap(a, b):
    return min(a[2], b[2]) - max(a[0], b[0]) > 1 and min(a[3], b[3]) - max(a[1], b[1]) > 1


def problems(spec):
    z = cfg.RULES["safe_zone"]
    W, H = z["canvas"]
    box = [z["left"], z["top"], W - z["right"], H - z["bottom"]]
    out, zs = [], spec["zones"]
    for name, zone in zs.items():
        if name == "footage": continue                                      # a transform, not a rectangle
        r = zone.get("rect") or zone.get("clip")
        if not r or len(r) != 4 or r[0] >= r[2] or r[1] >= r[3]: out.append(f"zone {name}: no valid rectangle"); continue
        if name in ("container", "hero") and zone.get("bleeds_to_bottom", name == "hero" and zs.get("container", {}).get("bleeds_to_bottom")):
            if not (r[0] >= 0 and r[2] <= W and r[1] >= box[1]): out.append(f"zone {name} {r} is outside the canvas or above y {box[1]}")      # footage may reach the bottom edge, only when the layout says so
        elif not _inside(r, [0, box[1], W, box[3]]): out.append(f"zone {name} {r} leaves the safe zone (y {box[1]}-{box[3]})")
        if name in ("stage", "caption") and not _inside(r, box): out.append(f"text zone {name} {r} is outside x {box[0]}-{box[2]}, y {box[1]}-{box[3]}")
    for a, b in (("stage", "caption"), ("stage", "container"), ("caption", "container"), ("stage", "hero")):          # (zones a layout does not have are skipped; the cut-out is transparent, so it may overlap the caption band: captions are drawn above it)
        if a in zs and b in zs:
            ra, rb = zs[a].get("rect") or zs[a].get("clip"), zs[b].get("rect") or zs[b].get("clip")
            if _overlap(ra, rb): out.append(f"zones {a} and {b} overlap")
    return out


def fit(zone, box, max_scale=1.0):
    """Place a block whose content covers `box` inside `zone` (both [x0,y0,x1,y1]): scale = largest that fits, never above 1; centred. -> (tx, ty, s) for
    transform-origin 0 0: translate(tx, ty) scale(s)."""
    zw, zh, bw, bh = zone[2] - zone[0], zone[3] - zone[1], box[2] - box[0], box[3] - box[1]
    s = min(max_scale, zw / bw, zh / bh)
    tx = (zone[0] + zw / 2) - s * (box[0] + bw / 2)
    ty = (zone[1] + zh / 2) - s * (box[1] + bh / 2)
    return round(tx, 1), round(ty, 1), round(s, 4)


FILL_MIN_GAP, FILL_MAX, FILL_MIN = 1.8, 3.0, 1.4


def fill_stage(kept, words, kw_idx, duration, *, limit=36):
    """The stage must not sit empty. Any stretch without a stage card longer than FILL_MIN_GAP gets simple text cards made ONLY from his own words in
    that stretch: windows of up to FILL_MAX s, each showing the highlighted keyword in it (else the longest word) plus up to 3 words after it, at most
    `limit` characters, 0.4 s apart. Nothing is invented. -> list of scenes (block text_card), no `fit` yet."""
    cov = sorted((s["t_in"], s["t_out"]) for s in kept)
    gaps, cur = [], 0.0
    for a, b in cov + [(duration, duration)]:
        if a - cur > FILL_MIN_GAP: gaps.append((cur, a))
        cur = max(cur, b)
    kws, out, n = set(kw_idx), [], 0
    for ga, gb in gaps:
        t = ga + 0.1
        while gb - t >= FILL_MIN + 0.1:
            win = [k for k, w in enumerate(words) if t <= w["start"] < min(t + FILL_MAX, gb - 0.1) and w["text"].strip()]
            if not win:
                nxt = [w["start"] for w in words if w["start"] >= t + FILL_MAX and w["start"] < gb - FILL_MIN]
                if not nxt: break
                t = nxt[0] - 0.1; continue
            k = next((i for i in win if i in kws), None)
            if k is None: k = max(win[:3], key=lambda i: len(words[i]["text"]))            # no keyword: the longest of the first words, so the card starts with the window
            t_in = max(t, words[k]["start"] - 0.15); t_out = min(gb - 0.1, t_in + FILL_MAX)
            if t_out - t_in < FILL_MIN: t_in = max(t, t_out - FILL_MIN)
            run = [words[k]["text"]]
            for nx in words[k + 1:k + 4]:
                if len(" ".join(run + [nx["text"]])) > limit or nx["start"] > t_out: break
                run.append(nx["text"])
            if t_out - t_in >= FILL_MIN:
                n += 1; out.append({"id": f"fill{n}", "block": "text_card", "t_in": round(t_in, 2), "t_out": round(t_out, 2), "values": {"kicker": "", "headline": " ".join(run), "sub": ""}})
            t = t_out + 0.4
    return out


def plan(spec, scenes, duration, *, theme="dark", registry=None, words=None, kw_idx=()):
    """scenes = the director's moments. -> dict(frame (scene), stage (fitted scenes), dropped (ids), caption_vars, hero (dict), face (dict))."""
    reg = registry or hfbuild.REGISTRY["blocks"]
    zs = spec["zones"]
    keep, dropped = [], []
    for s in scenes:
        b = s["block"]
        box = reg.get(b, {}).get("natural_box")
        if b == "captions": continue
        if b not in spec.get("blocks_in_stage", []) or not box:
            dropped.append(s["id"]); continue
        tx, ty, sc = fit(zs["stage"]["rect"], box)
        keep.append(dict(s, fit={"tx": tx, "ty": ty, "s": sc}))
    if words and "text_card" in spec.get("blocks_in_stage", []) and reg.get("text_card", {}).get("natural_box"):          # fill the stage gaps from his own words
        for f in fill_stage(keep, words, kw_idx, duration):
            tx, ty, sc = fit(zs["stage"]["rect"], reg["text_card"]["natural_box"]); keep.append(dict(f, fit={"tx": tx, "ty": ty, "s": sc}))
    cx = zs.get("container", {}).get("rect")
    frame = {"id": "stg", "block": "stage_frame", "t_in": 0.0, "t_out": duration, "values": {"theme": theme}} if cx else None        # no container = no frame: he stays full-screen
    cap = zs["caption"]["rect"]
    return {"frame": frame, "stage": keep, "dropped": dropped,
            "caption_vars": {"cap-top": f"{cap[1]}px", "cap-h": f"{cap[3] - cap[1]}px", "cap-size": f"{spec.get('captions', {}).get('size_px', 58)}px",
                             **({} if spec.get("captions", {}).get("pill", True) else {"cap-pill-bg": "transparent"})},
            "hero": ({k: v for k, v in zs["hero"].items() if k != "holds"} if "hero" in zs else None),
            "container": cx, "stage_rect": zs["stage"]["rect"]}


def face_transform(hero, face_origin=(540, 0.38 * 1920)):
    """The footage is scaled about the face point (540, 730) (the page's transform-origin). To put the face at hero.face_at: scale + translate."""
    fx, fy = hero["face_at"]
    return {"scale": hero["scale"], "x": round(fx - face_origin[0], 1), "y": round(fy - face_origin[1], 1)}


def frame_groups(inst, spec, theme="dark", container="spec"):
    """The stage frame's inner HTML: a full-canvas background with a rounded HOLE where the footage container is (the footage shows through it), and the
    glow border around the hole. All numbers come from the layout's container zone."""
    import html as _h
    cz = spec["zones"]["container"] if container == "spec" else container            # container = None: a full-screen plain frame (no hole)
    if cz is None:
        from . import pack
        th = theme if theme in ("dark", "violet") else "dark"
        return (f'<div id="{inst}-wrap" class="{inst}-{_h.escape(th)}" style="{pack.theme_style()}"><svg id="{inst}-bg" viewBox="0 0 1080 1920">'
                f'<path fill-rule="evenodd" style="fill:var(--pk-bg)" d="M0 0H1080V1920H0Z"/></svg><div id="{inst}-glow" style="display:none"></div></div>')
    x0, y0, x1, y1 = cz["rect"]; r = int(cz.get("radius", 44))
    path = (f"M0 0H1080V1920H0Z M{x0 + r} {y0}H{x1 - r}A{r} {r} 0 0 1 {x1} {y0 + r}V{y1 - r}A{r} {r} 0 0 1 {x1 - r} {y1}H{x0 + r}"
            f"A{r} {r} 0 0 1 {x0} {y1 - r}V{y0 + r}A{r} {r} 0 0 1 {x0 + r} {y0}Z")
    th = theme if theme in ("dark", "violet") else "dark"
    from . import pack
    return (f'<div id="{inst}-wrap" class="{inst}-{_h.escape(th)}" style="{pack.theme_style()}"><svg id="{inst}-bg" viewBox="0 0 1080 1920">'
            f'<path fill-rule="evenodd" style="fill:var(--pk-bg)" d="{path}"/></svg>'
            f'<div id="{inst}-glow" style="left:{x0}px;top:{y0}px;width:{x1 - x0}px;height:{y1 - y0}px;border-radius:{r}px"></div></div>')


def active_name():
    """Which layout the reels use now: config/project.json -> format_pack.layout ("panel" = the Format Pack frame, or a name in templates/layouts/).
    "panel" and unknown names -> None here (the Format Pack handles its own); format_pack.mode "off" switches every layout off."""
    from . import themes
    c = cfg.PROJECT.get("format_pack", {})
    n = c.get("layout", "panel")
    th = themes.current()
    if th: n = th["layout"]                                           # a theme chosen for this reel wins over the project setting
    return n if c.get("mode", "auto") != "off" and n in names() else None


def footage_transform(spec, face_cy=0.38, *, H=1920):
    """For a layout with a 'footage' zone (he stays full-screen but LIFTED so the card does not cover his chest and hands): the scale and shift of the
    full-frame footage (about the page's face point, y = 0.38 H) that put his face centre (face_cy, from the shot log) at footage.face_y with the smallest
    scale that still covers the whole canvas. A face that is already that high is left alone. -> {"scale","x","y"} or None (layout has no footage zone)."""
    z = spec["zones"].get("footage")
    if not z: return None
    origin, fy, target = 0.38 * H, float(face_cy) * H, float(z["face_y"])
    if fy <= target: return {"scale": 1.0, "x": 0, "y": 0}
    s = min(float(z.get("max_scale", 1.4)), max(1.0, (H - target) / (H - fy)))            # bottom edge must still reach the bottom of the canvas
    ty = target - origin - (fy - origin) * s                                                 # the shift that puts the face at the target ...
    ty = max(ty, H - origin - (H - origin) * s)                                              # ... but never so far that the bottom of the footage leaves a gap
    return {"scale": round(s, 4), "x": 0, "y": round(ty, 1)}


def measure_matte(webm, ffmpeg="ffmpeg", n=10, runner=None):
    """Where his head really is, measured on the cut-out itself (free, stdlib + ffmpeg): median over n frames of the hair-top row, the head width
    (rows 5-15% of the frame height below the hair top) and the head centre, all in 1080x1920 canvas pixels. -> {"top","head_w","head_cx"} or None."""
    import subprocess, statistics
    run = runner or subprocess.run
    W, H = 108, 192
    try:
        r = run([ffmpeg, "-v", "error", "-c:v", "libvpx-vp9", "-i", webm, "-vf", f"fps=4,alphaextract,scale={W}:{H}:flags=area,format=gray", "-f", "rawvideo", "-"], capture_output=True, timeout=300)
    except Exception:
        return None
    raw = r.stdout or b""
    frames = [raw[i:i + W * H] for i in range(0, len(raw) - W * H + 1, W * H)]
    if r.returncode or not frames: return None
    step = max(1, len(frames) // n); tops, widths, cxs = [], [], []
    for f in frames[::step][:n]:
        rows = [[f[y * W + x] > 128 for x in range(W)] for y in range(H)]
        top = next((y for y, row in enumerate(rows) if sum(row) >= 3), None)
        if top is None: continue
        ext = [(row.index(True), W - 1 - row[::-1].index(True)) for row in rows[top + int(.05 * H): top + int(.15 * H)] if any(row)]
        if not ext: continue
        a, b = min(e[0] for e in ext), max(e[1] for e in ext)
        tops.append(top * 10.0); widths.append((b - a + 1) * 10.0); cxs.append((a + b + 1) / 2 * 10.0)
    if not tops: return None
    return {"top": statistics.median(tops), "head_w": statistics.median(widths), "head_cx": statistics.median(cxs)}


def hero_transform(hero, m, *, canvas=(1080, 1920), origin=(540, 730)):
    """Size and place the footage + cut-out from the MEASURED head (m from measure_matte): head width = hero.head_w_px (scale clamped to
    hero.min_scale..max_scale), hair top at hero.head_top, head centred sideways as far as the footage still covers its container (no dark gaps).
    -> {"scale","x","y"} for the page's transform (about `origin`). m=None -> the old fixed-position transform."""
    if not m or not hero.get("head_w_px"): return face_transform(hero)
    W, H = canvas; ox, oy = origin
    cont = hero.get("cover_rect") or [108, 1080, 972, 1964]
    s = max(hero.get("min_scale", 0.8), min(hero.get("max_scale", 1.5), hero["head_w_px"] / max(m["head_w"], 1.0)))
    s = max(s, (cont[3] - hero["head_top"]) / max(H - m["top"], 1.0))                       # the footage must reach the bottom of its container
    y = hero["head_top"] - oy - s * (m["top"] - oy)                                          # hair top lands on head_top
    x = ox - ox - s * (m["head_cx"] - ox) + (hero.get("head_x", 540) - ox) * 1.0              # head centre lands on head_x ...
    lo, hi = cont[2] - ox - s * (W - ox), cont[0] - ox + s * ox                              # ... but never so far that the footage leaves a gap in its container
    x = max(lo, min(hi, x))
    return {"scale": round(s, 4), "x": round(x, 1), "y": round(y, 1)}


def measure_shots(shots):
    """A rough head measurement from the AI shot log (when no cut-out is made): median face box -> {"top","head_w","head_cx"} in canvas px, or None."""
    import statistics
    fs = [r["face"] for r in (shots or []) if r.get("face") and all(k in r["face"] for k in ("x", "y", "w", "h"))]
    if not fs: return None
    med = lambda k: statistics.median(f[k] for f in fs)
    x, y, w, h = med("x"), med("y"), med("w"), med("h")
    return {"top": max(0.0, (y - 0.3 * h) * 1920), "head_w": max(60.0, w * 1080 * 1.1), "head_cx": (x + w / 2) * 1080}
