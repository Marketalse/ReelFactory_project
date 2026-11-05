"""STATES: the pieces of Hesham's Figma drawing (frame, animation card quarter/half/full, clip full/half/half with hero, hero cut-out, text) as fixed
states (templates/states/<name>.json), and a SEQUENCE (a theme's ordered list of states) that the reel walks through, moment by moment. Free, no AI.

  A state = zones on the 1080x1920 canvas: frame (a rounded hole for the footage, or none, or "none" = no frame at all), anim (where an animation card plays),
  text (where text cards play in a "rest" state), caption (the word captions' band), clip (full footage, or a box with the head sized/placed from his
  measured head; hero = his cut-out rises out of the box). kind: "anim" (needs a card) or "rest" (no card: text or just him).
  A theme with a "sequence" list uses this engine (templates/themes/seq_*.json). The director's cards decide WHEN something animates; the sequence decides
  WHICH state each beat gets: a card takes the next animated state in the sequence, a stretch without a card takes the next rest state (else the theme's
  "rest" state). Every zone is checked against the safe zone (text zones x 108-920, y 250-1500); only footage boxes may bleed to the bottom edge.
  states.plan(...) -> segments + frame scenes + fitted card scenes + the small tweens the page needs (hero visible, caption band position)."""
import json, os

from . import config as cfg, layouts

DIR = os.path.join(cfg.ROOT, "templates", "states")
MIN_REST = 1.2


def names():
    return sorted(f[:-5] for f in os.listdir(DIR) if f.endswith(".json")) if os.path.isdir(DIR) else []


def load(name):
    with open(os.path.join(DIR, os.path.basename(name) + ".json"), encoding="utf-8") as f:
        return json.load(f)


def problems(st):
    """[text] (empty = ok): text/animation/caption zones inside the safe zone, footage box allowed to reach the bottom edge only."""
    z = cfg.RULES["safe_zone"]; W, H = z["canvas"]
    box = [z["left"], z["top"], W - z["right"], H - z["bottom"]]
    out = []
    for key in ("anim", "text"):
        r = st.get(key)
        if r and not layouts._inside(r, box): out.append(f"{key} zone {r} leaves the safe zone {box}")
    cap = st.get("caption")
    if cap and not (cap["y"] >= box[1] and cap["y"] + cap["h"] <= box[3]): out.append(f"caption band y {cap['y']}-{cap['y'] + cap['h']} leaves the safe zone")
    cl = st.get("clip")
    if cl and cl.get("rect") and not (cl["rect"][0] >= 0 and cl["rect"][2] <= W and cl["rect"][1] >= box[1] and cl["rect"][3] <= H + 64): out.append("clip box is outside the canvas")
    for a, b in (("anim", "caption"), ("text", "caption")):
        ra = st.get(a)
        if ra and cap and cap["y"] < ra[3] and cap["y"] + cap["h"] > ra[1] and a != "text_over": out.append(f"{a} zone and caption band overlap")
    return out


def sequence_problems(theme):
    out = []
    for n in list(theme.get("sequence", [])) + [theme.get("rest")]:
        if n not in names(): out.append(f"unknown state {n}"); continue
        out += [f"{n}: {p}" for p in problems(load(n))]
    if not any(load(n)["kind"] == "anim" for n in theme.get("sequence", []) if n in names()): out.append("the sequence has no animated state")
    return out


def _segments(cards, duration):
    """[[t_in, t_out, card or None]]: cards in time order; a gap of MIN_REST or more is a rest beat; a shorter gap stays with the beat before it."""
    segs, cur = [], 0.0
    for c in sorted(cards, key=lambda c: c["t_in"]):
        a, b = max(cur, c["t_in"]), min(duration, c["t_out"])
        if b - a < 0.3: continue
        if a - cur >= MIN_REST: segs.append([cur, a, None])
        elif segs: segs[-1][1] = a
        else: a = 0.0
        segs.append([a, b, c]); cur = b
    if duration - cur >= MIN_REST or not segs: segs.append([cur, duration, None])
    else: segs[-1][1] = duration
    return segs


def plan(theme, cards, words, kw_idx, duration, registry):
    """theme: a theme dict with "sequence" and "rest". cards: the director's scenes (not captions). -> dict(segments, frames, scenes, dropped, tweens, needs_hero)."""
    seq = theme["sequence"]; rest_name = theme.get("rest") or seq[0]
    allowed = set(theme.get("blocks", []))
    keep, dropped = [], []
    for c in cards:
        if c["block"] == "captions": continue
        if c["block"] not in allowed or not registry.get(c["block"], {}).get("natural_box"): dropped.append(c["id"]); continue
        keep.append(c)
    ptr, segs = 0, []
    for a, b, card in _segments(keep, duration):
        want = "anim" if card else "rest"
        name = None
        for k in range(len(seq)):
            cand = seq[(ptr + k) % len(seq)]
            if load(cand)["kind"] == want:
                name = cand; ptr = (ptr + k + 1) % len(seq); break
        if name is None: name = rest_name if want == "rest" else next(n for n in seq if load(n)["kind"] == "anim")
        segs.append({"t_in": round(a, 2), "t_out": round(b, 2), "state": name, "card": card})
    for s in segs: s["spec"] = load(s["state"])
    scenes, frames, tweens = [], [], []
    for n, s in enumerate(segs):                                           # cards fitted into their state's animation zone
        st = s["spec"]
        if s["card"] and st.get("anim"):
            c = s["card"]; tx, ty, sc = layouts.fit(st["anim"], registry[c["block"]]["natural_box"], st.get("anim_max_scale", 1.0))
            scenes.append(dict(c, t_in=max(s["t_in"], c["t_in"]), t_out=min(s["t_out"], c["t_out"]), zone=st["anim"], fit={"tx": tx, "ty": ty, "s": sc}))
        elif not s["card"] and st.get("text") and words and "line_text" in allowed and registry.get("line_text", {}).get("natural_box"):
            for f in _text_cards(words, kw_idx, s["t_in"], s["t_out"], registry):          # text only from his own words, number only if spoken
                tx, ty, sc = layouts.fit(st["text"], registry[f["block"]]["natural_box"])
                scenes.append(dict(f, zone=st["text"], fit={"tx": tx, "ty": ty, "s": sc}, id=f"{f['id']}_{n}"))
    runs = []                                                              # frames: one scene per run of equal frame
    for s in segs:
        fr = s["spec"].get("frame")
        key = json.dumps(fr, sort_keys=True)
        if runs and runs[-1][0] == key and abs(runs[-1][2] - s["t_in"]) < 0.01: runs[-1][2] = s["t_out"]
        else: runs.append([key, s["t_in"], s["t_out"], fr])
    for i, (key, a, b, fr) in enumerate(runs):
        if fr == "none": continue
        frames.append({"id": f"stg{i}", "block": "stage_frame", "t_in": a, "t_out": b, "values": {"theme": theme.get("palette", "dark")},
                       "groups_html": layouts.frame_groups(f"stg{i}", None, theme.get("palette", "dark"), container=fr)})
    base_y = segs[0]["spec"]["caption"]["y"] if segs else 790
    for s in segs:                                                         # tiny tweens: hero on/off, caption band moves
        hero = bool(s["spec"].get("clip") and s["spec"]["clip"].get("hero"))
        tweens.append(f'tl.set("#hero-clip", {{ opacity: {1 if hero else 0} }}, {s["t_in"]});')
        tweens.append(f'tl.set("#caps", {{ y: {s["spec"]["caption"]["y"] - base_y} }}, {s["t_in"]});')
    return {"segments": segs, "frames": frames, "scenes": scenes, "dropped": dropped, "tweens": tweens, "base_caption": segs[0]["spec"]["caption"] if segs else None,
            "needs_hero": any(x["spec"].get("clip") and x["spec"]["clip"].get("hero") for x in segs)}


def _text_cards(words, kw_idx, a, b, registry):
    """Plain text beats for a rest state (block line_text), made only from his own words in the stretch a-b: the highlighted word as a bold headline and the
    words after it as the line; if a number is spoken there, the number is the bold badge. -> scenes (no fit yet)."""
    out = []
    for c in layouts.fill_stage([{"t_in": 0.0, "t_out": a}], words, kw_idx, b):
        run = c["values"]["headline"].split()
        digits = next((w["text"] for w in words if c["t_in"] - 0.2 <= w["start"] <= c["t_out"] and any(ch.isdigit() for ch in w["text"])), None)
        num = "".join(ch for ch in (digits or "") if ch.isdigit() or ch in ".,")[:8]
        if num: vals = {"headline": "", "number": num, "line1": " ".join(run)[:30], "line2": ""}
        elif len(run) > 1: vals = {"headline": run[0][:20], "number": "", "line1": " ".join(run[1:])[:30], "line2": ""}
        else: vals = {"headline": "", "number": "", "line1": run[0][:30], "line2": ""}
        out.append(dict(c, block="line_text", values=vals))
    return out


def transforms(segs, m):
    """Per segment: the footage (and hero) transform {"scale","x","y"} from the measured head m (layouts.measure_matte). Full clip = untouched."""
    out = []
    for s in segs:
        cl = s["spec"].get("clip")
        if not cl or cl.get("full") or not cl.get("rect"): out.append({"scale": 1.0, "x": 0, "y": 0}); continue
        out.append(layouts.hero_transform(dict(cl, cover_rect=cl["rect"]), m))
    return out


def split_cuts(cuts, segs, tfs):
    """Cut the footage cuts at every state boundary (a piece shorter than 0.3 s is merged into its neighbour by moving the boundary to the cut edge) and give
    each piece its state's transform. -> new list of face cuts (dicts with scale, cx, cy, y, x)."""
    out, n = [], 0
    for c in cuts:
        pieces, t = [], c["t_in"]
        bounds = [s["t_in"] for s in segs[1:] if c["t_in"] + 0.3 <= s["t_in"] <= c["t_out"] - 0.3]
        for bnd in bounds + [c["t_out"]]:
            pieces.append((t, bnd)); t = bnd
        for a, b in pieces:
            k = max(i for i, s in enumerate(segs) if s["t_in"] <= a + 1e-6) if segs else 0
            tf = tfs[k]
            n += 1
            out.append(dict(c, id=f"{c['id']}" if len(pieces) == 1 else f"{c['id']}s{n}", t_in=round(a, 3), t_out=round(b, 3), src_in=round(c["src_in"] + (a - c["t_in"]), 3),
                            scale=tf["scale"], cx=0.5, cy=0.38, y=tf["y"], x=tf["x"]))
    return out
