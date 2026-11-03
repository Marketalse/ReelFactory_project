"""Motion-asset check (Lottie .json and dotLottie .lottie), the same idea as asset_check for icons: every file is tested ONCE, and the result says
whether it is safe to use and where it may sit in the video (safe zone) and where it may not. Free, offline, no AI.
Hard failures (never usable): unreadable file, not a Lottie, EXPRESSIONS (Lottie can carry JavaScript), links to files on the internet, path tricks
inside a .lottie, far too big. Soft notes (usable, but you are told): very long, uses a font, embeds pictures, very many colours."""
import json, os, re, zipfile

from . import asset_check as ac

MAX_BYTES = 3_000_000
MAX_SECONDS = 12.0
MIN_SECONDS = 0.3
NEED = ("v", "fr", "ip", "op", "w", "h", "layers")


def _walk(o):
    """Yield every dict inside a nested Lottie structure."""
    if isinstance(o, dict):
        yield o
        for v in o.values(): yield from _walk(v)
    elif isinstance(o, list):
        for v in o: yield from _walk(v)


def _colours(d):
    """Distinct colours used: animated or fixed colour values are lists of 3-4 numbers in 0..1 under key 'c' -> 'k'."""
    cols = set()
    for n in _walk(d):
        c = n.get("c")
        if isinstance(c, dict):
            k = c.get("k")
            if isinstance(k, list) and 3 <= len(k) <= 4 and all(isinstance(x, (int, float)) for x in k):
                cols.add(tuple(round(float(x), 2) for x in k[:3]))
    return cols


def inspect_animation(raw):
    """(info or None, hard problems, soft notes) for one Lottie JSON text."""
    hard, soft = [], []
    try:
        d = json.loads(raw)
    except (ValueError, RecursionError) as e:
        return None, [f"the file cannot be read as JSON: {str(e)[:80]}"], soft
    if not isinstance(d, dict) or any(k not in d for k in NEED):
        return None, ["this is not a Lottie animation (missing " + ", ".join(k for k in NEED if not isinstance(d, dict) or k not in d) + ")"], soft
    try:
        fr, ip, op, w, h = float(d["fr"]), float(d["ip"]), float(d["op"]), float(d["w"]), float(d["h"])
    except (TypeError, ValueError):
        return None, ["frame rate, length or size is not a number"], soft
    if fr <= 0 or w <= 0 or h <= 0 or op <= ip or not isinstance(d["layers"], list) or not d["layers"]:
        return None, ["the animation is empty or has impossible numbers (size, frame rate or length)"], soft
    sec = (op - ip) / fr
    expr = sum(1 for n in _walk(d) if isinstance(n.get("x"), str) and n.get("x").strip())     # a property with a text 'x' is a JavaScript expression
    if expr: hard.append(f"it contains {expr} expression(s): Lottie expressions run JavaScript code, which is not allowed")
    for n in _walk(d.get("assets", [])):
        p, u = str(n.get("p", "")), str(n.get("u", ""))
        if re.match(r"(?i)https?://|//", p) or re.match(r"(?i)https?://|//", u):
            hard.append("it loads a picture from the internet (" + (p or u)[:60] + "): not allowed")
    if sec > MAX_SECONDS: soft.append(f"{sec:.1f} s long (over {MAX_SECONDS:g} s): it will be cut or looped")
    if sec < MIN_SECONDS: soft.append(f"only {sec:.2f} s long")
    layers = sum(1 for n in _walk(d.get("layers", [])) if "ty" in n)
    if any(n.get("ty") == 5 for n in _walk(d.get("layers", []))): soft.append("it uses text with a font: the font may not exist when rendering")
    if any(str(n.get("p", "")).startswith("data:image") for n in _walk(d.get("assets", []))): soft.append("it embeds raster pictures (heavier and not recolourable)")
    cols = _colours(d)
    info = {"kind": "lottie", "w": w, "h": h, "fps": round(fr, 2), "duration_s": round(sec, 2), "shapes": layers, "colours": sorted("#%02X%02X%02X" % tuple(int(x * 255) for x in c) for c in cols)[:8],
            "recolourable": 0 < len(cols) <= 4}
    return info, hard, soft


def _lottie_zip(path):
    """dotLottie (.lottie) is a zip with manifest.json and animations/*.json. -> (raw JSON text of the first animation, hard problems)."""
    try:
        z = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        return None, ["the .lottie file is not a valid zip"]
    names = z.namelist()
    if any(n.startswith("/") or ".." in n.replace("\\", "/").split("/") for n in names):
        return None, ["the .lottie file contains unsafe paths"]
    if sum(i.file_size for i in z.infolist()) > 20 * MAX_BYTES:
        return None, ["the .lottie file expands to a suspicious size"]
    anim = [n for n in names if n.startswith("animations/") and n.endswith(".json")] or [n for n in names if n.endswith(".json") and n != "manifest.json"]
    if not anim:
        return None, ["no animation inside the .lottie file"]
    return z.read(sorted(anim)[0]).decode("utf-8", "replace"), []


def check(path):
    """-> the placement record for one motion file (same shape as asset_check.check)."""
    name = os.path.basename(path); ext = os.path.splitext(name)[1].lower()
    rec = {"asset": name, "ok": False, "problems": [], "hard": [], "never": [{"where": k, "why": v} for k, v in ac.FORBIDDEN]}
    if ext not in (".json", ".lottie"):
        rec["problems"] = [f"{ext or 'this file'} is not a motion file: bring a Lottie .json or a .lottie"]; return rec
    if os.path.getsize(path) > MAX_BYTES:
        rec["hard"] = rec["problems"] = [f"the file is over {MAX_BYTES // 1_000_000} MB"]; return rec
    if ext == ".lottie":
        raw, hard = _lottie_zip(path)
        if hard: rec["hard"] = rec["problems"] = hard; return rec
    else:
        raw = open(path, "rb").read().decode("utf-8", "replace")
    info, hard, soft = inspect_animation(raw)
    rec["problems"] = hard + soft; rec["hard"] = hard
    if info is None:
        rec["hard"] = list(hard); return rec
    rec.update({k: info[k] for k in ("kind", "w", "h", "fps", "duration_s", "recolourable", "colours")}); rec["aspect"] = round(info["w"] / info["h"], 3)
    rec["may_sit"] = ac.placements(info)
    rec["ok"] = not hard and any(p["ok"] for p in rec["may_sit"])
    rec["notes"] = soft
    rec["rule"] = ("Place it only in a 'may_sit' zone, resting fully inside x %d-%d, y %d-%d; never in the 'never' list; keep it off the face and off the captions." % ac.BOX)
    return rec
