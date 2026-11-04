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
        r = zone.get("rect") or zone.get("clip")
        if not r or len(r) != 4 or r[0] >= r[2] or r[1] >= r[3]: out.append(f"zone {name}: no valid rectangle"); continue
        if name in ("container", "hero") and zone.get("bleeds_to_bottom", name == "hero" and zs.get("container", {}).get("bleeds_to_bottom")):
            if not (r[0] >= 0 and r[2] <= W and r[1] >= box[1]): out.append(f"zone {name} {r} is outside the canvas or above y {box[1]}")      # footage may reach the bottom edge, only when the layout says so
        elif not _inside(r, [0, box[1], W, box[3]]): out.append(f"zone {name} {r} leaves the safe zone (y {box[1]}-{box[3]})")
        if name in ("stage", "caption") and not _inside(r, box): out.append(f"text zone {name} {r} is outside x {box[0]}-{box[2]}, y {box[1]}-{box[3]}")
    for a, b in (("stage", "caption"), ("stage", "container"), ("caption", "container"), ("stage", "hero"), ("caption", "hero")):          # (zones a layout does not have are skipped)
        if a in zs and b in zs:
            ra, rb = zs[a].get("rect") or zs[a].get("clip"), zs[b].get("rect") or zs[b].get("clip")
            if _overlap(ra, rb): out.append(f"zones {a} and {b} overlap")
    return out


def fit(zone, box):
    """Place a block whose content covers `box` inside `zone` (both [x0,y0,x1,y1]): scale = largest that fits, never above 1; centred. -> (tx, ty, s) for
    transform-origin 0 0: translate(tx, ty) scale(s)."""
    zw, zh, bw, bh = zone[2] - zone[0], zone[3] - zone[1], box[2] - box[0], box[3] - box[1]
    s = min(1.0, zw / bw, zh / bh)
    tx = (zone[0] + zw / 2) - s * (box[0] + bw / 2)
    ty = (zone[1] + zh / 2) - s * (box[1] + bh / 2)
    return round(tx, 1), round(ty, 1), round(s, 4)


def plan(spec, scenes, duration, *, theme="dark", registry=None):
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
    cx = zs.get("container", {}).get("rect")
    frame = {"id": "stg", "block": "stage_frame", "t_in": 0.0, "t_out": duration, "values": {"theme": theme}} if cx else None        # no container = no frame: he stays full-screen
    cap = zs["caption"]["rect"]
    return {"frame": frame, "stage": keep, "dropped": dropped,
            "caption_vars": {"cap-top": f"{cap[1]}px", "cap-h": f"{cap[3] - cap[1]}px", "cap-size": f"{spec.get('captions', {}).get('size_px', 58)}px",
                             **({} if spec.get("captions", {}).get("pill", True) else {"cap-pill-bg": "transparent"})},
            "hero": ({"clip": zs["hero"]["clip"], "scale": zs["hero"]["scale"], "face_at": zs["hero"]["face_at"]} if "hero" in zs else None),
            "container": cx, "stage_rect": zs["stage"]["rect"]}


def face_transform(hero, face_origin=(540, 0.38 * 1920)):
    """The footage is scaled about the face point (540, 730) (the page's transform-origin). To put the face at hero.face_at: scale + translate."""
    fx, fy = hero["face_at"]
    return {"scale": hero["scale"], "x": round(fx - face_origin[0], 1), "y": round(fy - face_origin[1], 1)}


def frame_groups(inst, spec, theme="dark"):
    """The stage frame's inner HTML: a full-canvas background with a rounded HOLE where the footage container is (the footage shows through it), and the
    glow border around the hole. All numbers come from the layout's container zone."""
    import html as _h
    x0, y0, x1, y1 = spec["zones"]["container"]["rect"]; r = int(spec["zones"]["container"].get("radius", 44))
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
    c = cfg.PROJECT.get("format_pack", {})
    n = c.get("layout", "panel")
    return n if c.get("mode", "auto") != "off" and n in names() else None
