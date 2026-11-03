"""Asset check (Hesham 2026-11-03): every icon / picture he brings is tested ONCE against the safe-zone rule, and the result says
where it may sit in the video and where it may not. Free, offline, no AI. The result is saved next to the asset as
<name>.placement.json and the director must follow it.

Formats accepted: SVG (best: sharp at any size, can take the brand colours) or PNG with a transparent background (at least 512 px).
Nothing else is needed; the .placement.json is made by this tool, never by hand."""
import json, os, re, struct, xml.etree.ElementTree as ET
from lib import config as cfg

SZ = cfg.RULES["safe_zone"]
BOX = (SZ["left"], SZ["top"], SZ["canvas"][0] - SZ["right"], SZ["never_below_y"])        # x0, y0, x1, y1 = 108, 250, 920, 1500
CAP = tuple(SZ["captions_y"])                                                           # captions band 1200-1450
# named places an icon/picture may sit (resting position, 1080x1920 canvas). The face is checked per reel from the shot log.
ZONES = {
    "top":    (BOX[0], BOX[1], BOX[2], 600),
    "middle": (BOX[0], 600, BOX[2], CAP[0]),
}
FORBIDDEN = [
    ("above_y250", "top 250 px: Instagram header and TikTok tabs"),
    ("below_y1500", "below y 1500: caption, handle and sound bar"),
    ("right_160", "right 160 px: like/comment/share buttons"),
    ("left_108", "left 108 px: screen edge"),
    ("caption_band", f"y {CAP[0]}-{CAP[1]}: the captions sit here"),
    ("over_face", "on the speaker's face (checked per reel with the shot log)"),
]
MAX_BYTES = 300_000
BAD_SVG = re.compile(r"<\s*(script|foreignObject|iframe|image\b[^>]*href\s*=\s*['\"]\s*https?:)|\son\w+\s*=|<!ENTITY|<!DOCTYPE", re.I)


def _svg(path):
    raw = open(path, "rb").read().decode("utf-8", "replace")
    if BAD_SVG.search(raw):
        return None, ["the SVG contains a script, an outside link or an entity: not allowed"]
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        return None, [f"the SVG cannot be read: {e}"]
    why = []
    vb = root.get("viewBox")
    w = h = None
    if vb:
        p = [float(x) for x in re.split(r"[ ,]+", vb.strip())]
        if len(p) == 4 and p[2] > 0 and p[3] > 0: w, h = p[2], p[3]
    if w is None:
        num = lambda v: float(re.match(r"[\d.]+", v or "").group()) if re.match(r"[\d.]+", v or "") else None
        w, h = num(root.get("width")), num(root.get("height"))
    if not w or not h:
        return None, ["the SVG has no viewBox (or width and height): add a viewBox"]
    tags = [e.tag.split("}")[-1] for e in root.iter()]
    shapes = sum(t in ("path", "circle", "rect", "ellipse", "polygon", "polyline", "line") for t in tags)
    colours = set(re.findall(r"#[0-9a-fA-F]{3,8}\b", raw)) | set(re.findall(r"(?:fill|stroke)\s*[:=]\s*[\"']?(?!none|currentColor|url)([a-z]+)", raw, re.I))
    recolour = "currentColor" in raw or len(colours) <= 2
    return {"kind": "svg", "w": w, "h": h, "shapes": shapes, "colours": sorted(colours)[:6], "recolourable": recolour}, why


def _png(path):
    d = open(path, "rb").read(64)
    if d[:8] != b"\x89PNG\r\n\x1a\n":
        return None, ["not a real PNG file"]
    w, h = struct.unpack(">II", d[16:24]); ctype = d[25]
    alpha = ctype in (4, 6) or b"tRNS" in open(path, "rb").read(4096)
    why = []
    if not alpha: why.append("the PNG has no transparent background: a white or coloured box will show; export it with transparency")
    if min(w, h) < 512: why.append(f"the PNG is {w}x{h}: at least 512 px on the short side so it stays sharp")
    return {"kind": "png", "w": w, "h": h, "shapes": None, "colours": [], "recolourable": False}, why


def placements(info):
    """For each named zone: the biggest size this asset may have there while resting completely inside the safe box."""
    ar = info["w"] / info["h"]
    out, floor = [], (96 if (info.get("shapes") or 0) < 40 else 160)            # busy artwork needs more size to stay readable
    for name, (x0, y0, x1, y1) in ZONES.items():
        mw, mh = x1 - x0, y1 - y0
        w = min(mw, mh * ar); h = w / ar
        if w < floor:
            out.append({"zone": name, "ok": False, "why": f"too small to read there (max {w:.0f} px, needs {floor})"}); continue
        out.append({"zone": name, "ok": True, "x": [x0, round(x1 - w)], "y": [y0, round(y1 - h)], "max_w": round(w), "max_h": round(h), "min_w": floor})
    return out


def check(path):
    """-> the placement record for one asset (also tells why it failed)."""
    name = os.path.basename(path); ext = os.path.splitext(name)[1].lower()
    rec = {"asset": name, "ok": False, "problems": [], "hard": [], "never": [{"where": k, "why": v} for k, v in FORBIDDEN]}
    if ext not in (".svg", ".png"):
        rec["problems"] = [f"{ext or 'this file'} is not accepted: bring an SVG or a transparent PNG"]; return rec
    if os.path.getsize(path) > MAX_BYTES:
        rec["problems"].append(f"the file is over {MAX_BYTES // 1000} KB: simplify it")
    info, why = (_svg if ext == ".svg" else _png)(path)
    rec["problems"] += why
    if info is None:
        rec["hard"] = list(why); return rec          # unsafe or unreadable: never usable
    rec.update({k: info[k] for k in ("kind", "w", "h", "recolourable", "colours")}); rec["aspect"] = round(info["w"] / info["h"], 3)
    rec["may_sit"] = placements(info)
    rec["ok"] = not rec["problems"] and any(p["ok"] for p in rec["may_sit"])
    rec["rule"] = ("Place it only in a 'may_sit' zone, resting fully inside x %d-%d, y %d-%d; never in the 'never' list; "
                   "keep it off the face and off the captions." % BOX)
    return rec


def check_bytes(name, data, tmp_dir):
    """check() for a file that is only in memory (zip member): written to a private temp file for the check, then removed."""
    import tempfile
    fd, p = tempfile.mkstemp(suffix=os.path.splitext(name)[1].lower(), dir=tmp_dir)
    try:
        with os.fdopen(fd, "wb") as f: f.write(data)
        r = check(p); r["asset"] = os.path.basename(name); return r
    finally:
        try: os.remove(p)
        except OSError: pass


def run(path, out_dir=None):
    """Check one file or every SVG/PNG in a folder; writes <name>.placement.json next to each. -> list of records."""
    files = [path] if os.path.isfile(path) else sorted(os.path.join(path, f) for f in os.listdir(path) if f.lower().endswith((".svg", ".png", ".jpg", ".gif", ".json")))
    recs = []
    for f in files:
        r = check(f); recs.append(r)
        d = out_dir or os.path.dirname(f)
        json.dump(r, open(os.path.join(d, os.path.splitext(os.path.basename(f))[0] + ".placement.json"), "w"), indent=1, ensure_ascii=False)
    return recs


def inside_safe(x, y, w, h):
    """Does a rectangle rest completely inside the safe box and clear of the captions band? (the test applied at placement time)"""
    if x < BOX[0] or y < BOX[1] or x + w > BOX[2] or y + h > BOX[3]: return False
    return y + h <= CAP[0] or y >= CAP[1]


def job_problems(asset_dir):
    """{file: reason} for the assets of ONE reel that must never be used (unsafe or unreadable SVG/PNG, or a library check that failed hard).
    Quality notes (no transparency, small size) do not block a reel: his screenshots and logos keep working. Free."""
    bad = {}
    if not os.path.isdir(asset_dir): return bad
    for f in sorted(os.listdir(asset_dir)):
        if not f.lower().endswith((".svg", ".png")): continue
        try:
            r = check(os.path.join(asset_dir, f))
        except Exception as e:                                           # noqa: BLE001
            bad[f] = f"cannot be checked: {e}"; continue
        if r["hard"]: bad[f] = r["hard"][0]
    return bad


def rule_for(asset_dir, filename):
    """The saved record for an asset, or None when it was never checked."""
    p = os.path.join(asset_dir, os.path.splitext(filename)[0] + ".placement.json")
    try:
        return json.load(open(p))
    except (OSError, ValueError):
        return None
