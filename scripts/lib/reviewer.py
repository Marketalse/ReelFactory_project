"""REVIEWER + REPAIR. Two layers, both free of paid calls except the one cheap look the critic already makes:

 1. GEOMETRY (free, exact, runs inside the compiler): from the measured head and the planned zones it checks the things a person sees at once: the head cut off
    by the screen edge or by its clip box, text sitting on his face, a zone left empty for seconds. Where it can, it FIXES them on the spot (smaller head, text
    moved above/below the head, a card made from his own words) and writes what it did.
 2. VISION (the critic): a small model looks at stills of the draft and now names each problem with a KIND and a time. A problem with a known fix becomes a
    repair item in the job's repairs.json; the compiler reads that file, the draft is made again (only the changed 6-second pieces render again) and the critic
    looks once more. One round at most (config critic.repair_rounds); if the second look scores worse the repair is switched off (repairs.json "disabled").
 Nothing here edits his words, writes template HTML, spends beyond the existing budget guard, or loops."""
import json, os

KINDS = ("head_clipped", "empty_zone", "text_over_face", "caption_unreadable", "overlap", "other")
FIXABLE = ("head_clipped", "empty_zone", "text_over_face", "caption_unreadable")
SHRINK_STEP, MAX_SHRINK = 0.88, 0.6            # each head_clipped repair makes the head 12% smaller, never below 60% of the planned size


def path(job):
    return os.path.join(job, "repairs.json")


def load(job):
    """-> {"items": [{"kind","t","round"}], "disabled": bool, "head_scale": float}. Missing/broken file = nothing to repair."""
    try:
        with open(path(job), encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return {"items": [], "disabled": False, "head_scale": 1.0}
    if not isinstance(d, dict): return {"items": [], "disabled": False, "head_scale": 1.0}
    d.setdefault("items", []); d.setdefault("disabled", False); d.setdefault("head_scale", 1.0)
    return d


def active(job):
    d = load(job)
    return {"items": [], "disabled": True, "head_scale": 1.0} if d.get("disabled") else d


def save(job, d):
    with open(path(job), "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)


def head_box(m, tf, origin=(540, 730)):
    """Where his head sits on the 1080x1920 canvas after the footage transform tf ({"scale","x","y"}) -> [x0, y0, x1, y1]. m from layouts.measure_matte /
    measure_shots: hair top, head width, head centre. Head height is estimated (his head is about 1.7 x as tall as wide with beard and hair)."""
    ox, oy = origin; s = tf["scale"]
    w = m["head_w"] * s; h = 1.7 * w
    cx = ox + s * (m["head_cx"] - ox) + tf["x"]
    top = oy + s * (m["top"] - oy) + tf["y"]
    return [cx - w / 2, top, cx + w / 2, top + h]


def head_problems(hb, *, clip_top=None, box=None, canvas=(1080, 1920)):
    """[text] what is wrong with a head box hb: cut by the screen sides, above the area that may show it, or sticking out of its footage box."""
    W, H = canvas; out = []
    if hb[0] < -2 or hb[2] > W + 2: out.append("head touches the screen edge")
    if clip_top is not None and hb[1] < clip_top - 2: out.append("hair top is above the part of the screen that may show it")
    if box is not None and hb[1] < box[1] - 2: out.append("head sticks out above its box")
    return out


def overlap_ratio(a, b):
    """Share of rectangle a covered by rectangle b (0..1)."""
    w = min(a[2], b[2]) - max(a[0], b[0]); h = min(a[3], b[3]) - max(a[1], b[1])
    return 0.0 if w <= 0 or h <= 0 else (w * h) / max(1.0, (a[2] - a[0]) * (a[3] - a[1]))


def from_issues(issues, prev=None, round_no=1):
    """Turn the critic's issues into a repairs dict (items with a known fix only). Accumulates on `prev`. -> (repairs, applied_texts)."""
    d = dict(prev or {"items": [], "disabled": False, "head_scale": 1.0})
    d["items"] = list(d.get("items", [])); applied = []
    for i in issues or []:
        k = i.get("kind")
        if k not in FIXABLE: continue
        item = {"kind": k, "t": float(i.get("t", 0)), "round": round_no}
        if k == "head_clipped":
            d["head_scale"] = max(MAX_SHRINK, round(float(d.get("head_scale", 1.0)) * SHRINK_STEP, 3))
            applied.append(f"head smaller (x{d['head_scale']})")
        elif k == "empty_zone": applied.append(f"card made from his words near {item['t']:.1f}s")
        elif k == "text_over_face": applied.append(f"text moved off his face near {item['t']:.1f}s")
        elif k == "caption_unreadable": applied.append("captions get a plate behind them")
        if item not in d["items"]: d["items"].append(item)
    d["applied"] = applied
    return d, applied
