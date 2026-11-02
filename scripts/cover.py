#!/usr/bin/env python3
"""Cover image (thumbnail) for a reel. $0 (local).

    python3 scripts/cover.py jobs/<job>            -> jobs/<job>/review/cover.jpg (1080x1920)

Look (Hesham's reference, 2026-11-01): dark brand background with a dot grid, a lime topic pill, a two-line title
(line 1 white, line 2 lime) from the hook, his photo in the lower half fading into the background, an optional violet
sticker and an optional lime formula card.

His own image wins: put it in jobs/<job>/cover/ as
    photo.<jpg|png|webp>   -> used as the photo inside the generated cover
    own.<jpg|png|webp>     -> used as the whole cover, as is (cropped to 9:16)
Everything written on the cover comes from his words (the hook, and cover fields checked against spoken numbers).
"""
import glob, html, json, os, re, shutil, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import config as cfg       # noqa: E402
from lib import hfbuild             # noqa: E402

W, H = 1080, 1920
IMG = (".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif")
LIMITS = {"tag": 16, "sticker": 18, "card_label": 24, "card_value": 26}
DIGITS = re.compile(r"[0-9][0-9,.]*")
HF = ["npx", "--yes", f"hyperframes@{cfg.PROJECT.get('tools', {}).get('hyperframes', '0.8.226')}"]


class CoverError(Exception):
    pass


def _jload(p, default):
    try:
        return json.load(open(p, encoding="utf-8"))
    except (OSError, ValueError):
        return default


def own_file(job, name):
    for e in IMG:
        p = os.path.join(job, "cover", name + e)
        if os.path.exists(p):
            return p
    return None


def spoken(job):
    w = _jload(os.path.join(job, "edl.json"), {}).get("words") or _jload(os.path.join(job, "transcript.json"), {}).get("words") or []
    return {DIGITS.search(x["text"]).group(0).rstrip(".,").replace(",", "") for x in w if DIGITS.search(x.get("text", ""))}


def values(job):
    """Cover text: the hook + the AI's cover fields, each dropped if too long or if it shows a number he didn't say."""
    plan = _jload(os.path.join(job, "scene_plan.json"), {})
    hook = plan.get("hook") or {}
    if not (hook.get("line1") or hook.get("line2")):         # no plan file: the hook as built into the video
        tl = _jload(os.path.join(job, "timeline.json"), {})
        hook = next((x.get("values", {}) for x in tl.get("scenes", []) if x.get("block") == "hook_two_tone"), {})
    said = spoken(job)
    v = {"line1": " ".join(str(hook.get("line1", "")).split()), "line2": " ".join(str(hook.get("line2", "")).split())}
    for k, lim in LIMITS.items():
        t = " ".join(str((plan.get("cover") or {}).get(k, "")).split())
        nums = {n.rstrip(".,").replace(",", "") for n in DIGITS.findall(t)}
        if not t or len(t) > lim or not nums <= said:
            t = ""
        v[k] = t
    if not v["card_value"]:
        v["card_label"] = ""
    return v


def best_moment(job):
    """The best cover moment from the shot log (free, already paid for): face found, eyes open, not a 'avoid' frame, headroom ok, a face
    near the middle, the most animated / best 'hook' look. -> {"t", "face"} or None."""
    rows = _jload(os.path.join(job, "shot_log.json"), []) or []
    best, score = None, -1e9
    for r in rows if isinstance(rows, list) else []:
        f = r.get("face")
        if not isinstance(r, dict) or not f or r.get("eyes") != "open" or "avoid" in (r.get("usable") or []):
            continue
        cx = f["x"] + f["w"] / 2
        sc = (3 if "hook" in (r.get("usable") or []) else 0) + float(r.get("energy") or 1) + (1 if r.get("headroom") == "ok" else -1) - 6 * abs(cx - 0.5) - (2 if r.get("bg") == "high" else 0)
        if sc > score:
            best, score = {"t": float(r["t"]), "face": f}, sc
    return best


def pick_frame(job, out, n=10):
    """The best moment from the shot log when there is one; else the sharpest of n frames from the middle of the take."""
    proxy = os.path.join(job, "proxy.mp4")
    if not os.path.exists(proxy):
        raise CoverError("no proxy.mp4 to take a photo from")
    bm = best_moment(job)
    if bm:
        os.makedirs(os.path.dirname(out), exist_ok=True)
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{bm['t']:.2f}", "-i", proxy, "-frames:v", "1", "-q:v", "2", out], capture_output=True)
        if r.returncode == 0 and os.path.exists(out):
            return out
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", proxy],
                               capture_output=True, text=True).stdout.strip() or 0)
    tmp = os.path.join(os.path.dirname(out), "_frames"); os.makedirs(tmp, exist_ok=True)
    best, size = None, -1
    for k in range(n):
        t = dur * (0.15 + 0.7 * k / max(1, n - 1))
        f = os.path.join(tmp, f"f{k}.jpg")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", proxy, "-frames:v", "1", "-q:v", "2", f], capture_output=True)
        if os.path.exists(f) and os.path.getsize(f) > size:
            best, size = f, os.path.getsize(f)
    if not best:
        raise CoverError("couldn't take a photo from the video")
    shutil.copy(best, out); shutil.rmtree(tmp, ignore_errors=True)
    return out


def _size(text, base, per_char_drop, minimum):
    return max(minimum, base - per_char_drop * max(0, len(text) - 8))


PAGE = """<!doctype html>
<html lang="ar"><head><meta charset="UTF-8"><meta name="viewport" content="width={W}, height={H}">
<script src="vendor/gsap.min.js"></script>
<style>
@font-face {{ font-family: "Readex Pro"; src: url("assets/fonts/ReadexPro.ttf"); font-weight: 160 700; }}
:root {{ {vars} }}
* {{ margin:0; padding:0; box-sizing:border-box; }}
html, body {{ width:{W}px; height:{H}px; overflow:hidden; background:var(--bg); }}
#root {{ position:relative; width:100%; height:100%; overflow:hidden; font-family:var(--font); background:var(--bg); }}
#grid {{ position:absolute; left:0; right:0; top:0; height:900px;
  background-image:radial-gradient(rgba(255,255,255,.13) 2.2px, transparent 2.6px); background-size:54px 54px; background-position:27px 27px;
  -webkit-mask-image:linear-gradient(180deg,#000 70%,transparent); mask-image:linear-gradient(180deg,#000 70%,transparent); }}
#photo {{ position:absolute; left:0; right:0; top:{photo_top}px; bottom:0; overflow:hidden;
  -webkit-mask-image:linear-gradient(180deg,transparent 0,#000 220px,#000 82%,rgba(0,0,0,.35) 100%);
  mask-image:linear-gradient(180deg,transparent 0,#000 220px,#000 82%,rgba(0,0,0,.35) 100%); }}
#photo img {{ width:100%; height:100%; object-fit:cover; object-position:50% 40%; }}
#head {{ position:absolute; left:var(--text-x); width:var(--text-w); top:var(--feed-top); display:flex; flex-direction:column; align-items:flex-end; gap:18px; }}
#tag {{ background:var(--lime); color:#14161d; font-weight:700; font-size:46px; letter-spacing:2px; padding:10px 30px 12px;
  border-radius:40px; direction:ltr; }}
.t {{ direction:rtl; text-align:right; font-weight:700; line-height:1.12; width:100%; }}
#l1 {{ color:var(--text); font-size:{s1}px; }}
#l2 {{ color:var(--lime); font-size:{s2}px; margin-top:-6px; }}
#sticker {{ position:absolute; right:190px; top:{sticker_top}px; max-width:700px; background:var(--violet); color:#fff; font-weight:700;
  font-size:54px; letter-spacing:1px; padding:20px 38px 24px; border-radius:22px; direction:ltr; transform:rotate(4deg);
  box-shadow:0 18px 40px rgba(0,0,0,.35); }}
#card {{ align-self:flex-start; margin:44px 0 0 16px; max-width:740px; background:var(--lime); color:#14161d; border-radius:34px;
  padding:34px 44px 38px; transform:rotate(-3deg); box-shadow:0 22px 50px rgba(0,0,0,.4); direction:ltr; }}
#card .lbl {{ font-size:36px; font-weight:600; letter-spacing:3px; }}
#card .val {{ font-size:{sv}px; font-weight:700; margin-top:6px; white-space:nowrap; }}
#card .val b {{ background:#14161d; color:var(--lime); border-radius:16px; padding:0 18px 6px; margin-left:8px; }}
#fade {{ position:absolute; left:0; right:0; bottom:0; height:260px; background:linear-gradient(180deg,transparent,var(--bg)); }}
</style></head>
<body>
<div id="root" data-composition-id="cover" data-start="0" data-duration="1" data-width="{W}" data-height="{H}">
  <div id="grid"></div>
  {photo}
  <div id="fade"></div>
  <div id="head">
    {tag}
    <div class="t" id="l1">{line1}</div>
    <div class="t" id="l2">{line2}</div>
    {card}
  </div>
  {sticker}
</div>
<script>
const tl = gsap.timeline({{ paused: true }});
window.__timelines["cover"] = tl;
</script>
</body></html>
"""


PAGE_HERO = """<!doctype html>
<html lang="ar"><head><meta charset="UTF-8"><meta name="viewport" content="width={W}, height={H}">
<script src="vendor/gsap.min.js"></script>
<style>
@font-face {{ font-family: "Readex Pro"; src: url("assets/fonts/ReadexPro.ttf"); font-weight: 160 700; }}
:root {{ {vars} }}
* {{ margin:0; padding:0; box-sizing:border-box; }}
html, body {{ width:{W}px; height:{H}px; overflow:hidden; background:var(--bg); }}
#root {{ position:relative; width:100%; height:100%; overflow:hidden; font-family:var(--font); background:linear-gradient(180deg,#1b1e2a 0%,var(--bg) 55%,#1b1e2a 100%); }}
#grid {{ position:absolute; left:0; right:0; top:0; height:1000px;
  background-image:radial-gradient(rgba(255,255,255,.12) 2.2px, transparent 2.6px); background-size:54px 54px; background-position:27px 27px;
  -webkit-mask-image:linear-gradient(180deg,#000 60%,transparent); mask-image:linear-gradient(180deg,#000 60%,transparent); }}
#glow {{ position:absolute; left:50%; top:{glow_y}px; width:1300px; height:1300px; transform:translate(-50%,-50%);
  background:radial-gradient(circle, rgba(125,83,255,.78) 0%, rgba(125,83,255,.30) 38%, transparent 68%); }}
#beam1 {{ position:absolute; left:-260px; top:{beam_y}px; width:1000px; height:120px; background:var(--lime); opacity:.9; transform:rotate(-24deg); }}
#beam2 {{ position:absolute; right:-300px; top:{beam2_y}px; width:760px; height:80px; background:var(--violet); opacity:.9; transform:rotate(-24deg); }}
#title {{ position:absolute; left:var(--text-x); width:var(--text-w); top:{title_top}px; text-align:center; direction:rtl; font-weight:700; line-height:.98;
  text-shadow:0 14px 50px rgba(0,0,0,.45); }}
#l1 {{ color:var(--text); font-size:{s1}px; }}
#l2 {{ color:var(--lime); font-size:{s2}px; }}
#person {{ position:absolute; left:{p_left}px; top:{p_top}px; width:{p_w}px; height:{p_h}px; filter:drop-shadow(0 0 28px rgba(182,255,0,.28)) drop-shadow(0 20px 40px rgba(0,0,0,.5)); }}
#fade {{ position:absolute; left:0; right:0; bottom:0; height:340px; background:linear-gradient(180deg,transparent,var(--bg) 92%); }}
#tag {{ position:absolute; right:170px; top:290px; background:var(--lime); color:#14161d; font-weight:700; font-size:46px; letter-spacing:2px; padding:10px 30px 12px;
  border-radius:40px; direction:ltr; box-shadow:0 12px 30px rgba(0,0,0,.35); }}
#sticker {{ position:absolute; right:190px; top:{sticker_top}px; max-width:700px; background:var(--violet); color:#fff; font-weight:700;
  font-size:54px; letter-spacing:1px; padding:20px 38px 24px; border-radius:22px; direction:ltr; transform:rotate(4deg); box-shadow:0 18px 40px rgba(0,0,0,.35); }}
#card {{ position:absolute; left:var(--text-x); top:{card_top}px; max-width:740px; background:var(--lime); color:#14161d; border-radius:34px;
  padding:34px 44px 38px; transform:rotate(-3deg); box-shadow:0 22px 50px rgba(0,0,0,.4); direction:ltr; }}
#card .lbl {{ font-size:36px; font-weight:600; letter-spacing:3px; }}
#card .val {{ font-size:{sv}px; font-weight:700; margin-top:6px; white-space:nowrap; }}
#card .val b {{ background:#14161d; color:var(--lime); border-radius:16px; padding:0 18px 6px; margin-left:8px; }}
</style></head>
<body>
<div id="root" data-composition-id="cover" data-start="0" data-duration="1" data-width="{W}" data-height="{H}">
  <div id="grid"></div><div id="glow"></div><div id="beam1"></div><div id="beam2"></div>
  <div id="title"><div id="l1">{line1}</div><div id="l2">{line2}</div></div>
  <img id="person" src="assets/cutout.png" alt="">
  <div id="fade"></div>
  {tag}{card}{sticker}
</div>
<script>
const tl = gsap.timeline({{ paused: true }});
window.__timelines["cover"] = tl;
</script>
</body></html>
"""


def cutout(photo, dest, runner=subprocess.run):
    """The person cut out of the photo (transparent PNG) with HyperFrames' on-device model: free, ~15-30 s. None when it can't be done."""
    try:
        r = runner(HF + ["remove-background", photo, "-o", dest], capture_output=True, text=True, timeout=900)
        return dest if r.returncode == 0 and os.path.exists(dest) and os.path.getsize(dest) > 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def title_size(text, big=190, small=64):
    """Big for short titles; long ones may use two lines (each line of the title stays inside the 780 px text box). -> (font px, lines)."""
    n = max(1, len(text))
    one = 780 / (0.62 * n)
    if one >= 120 or n <= 12:
        return int(max(small, min(big, one))), 1
    two = 780 * 1.85 / (0.62 * n)
    size = int(max(small, min(big, two)))
    return size, max(1, -(-int(0.62 * size * n) // 780))


def hero_geometry(face, two_lines, s1, s2, n1=1, n2=1):
    """Where the person and the title go so the head covers the lower part of the title (the 'text behind the head' look)."""
    cy = (face["y"] + face["h"] * 0.5) if face else 0.36
    top_f = (face["y"]) if face else 0.27
    S = 1.32
    p_w, p_h = int(W * S), int(H * S)
    p_left = int((W - p_w) / 2)
    p_top = int(930 - cy * p_h)                                  # the face centre sits at y = 930
    head_top = p_top + top_f * p_h
    title_h = (s1 * n1 + s2 * n2) * 0.98
    title_top = int(max(340, head_top - 0.55 * title_h))
    return dict(p_w=p_w, p_h=p_h, p_left=p_left, p_top=p_top, title_top=title_top, glow_y=int(930 - 120), beam_y=1330, beam2_y=230)


def build(job, v, photo, cut=None, face=None):
    out = os.path.join(job, "cover", "hf")
    shutil.rmtree(out, ignore_errors=True)
    for d in ("assets/fonts", "vendor"):
        os.makedirs(os.path.join(out, d), exist_ok=True)
    fonts = [f for f in os.listdir(os.path.join(cfg.ROOT, "style", "fonts")) if f.lower().endswith(".ttf")]
    shutil.copy(os.path.join(cfg.ROOT, "style", "fonts", fonts[0]), os.path.join(out, "assets", "fonts", "ReadexPro.ttf"))
    shutil.copy(os.path.join(cfg.ROOT, "templates", "vendor", "gsap.min.js"), os.path.join(out, "vendor", "gsap.min.js"))
    photo = readable(photo)
    ext = os.path.splitext(photo)[1].lower()
    shutil.copy(photo, os.path.join(out, "assets", "photo" + ext))
    e = html.escape
    val = e(v["card_value"])
    if "=" in v["card_value"]:                       # "1,200 × 3 = 3,600": the result in the dark box
        a, b = v["card_value"].rsplit("=", 1)
        val = f"{e(a.strip())} = <b>{e(b.strip())}</b>"
    two_lines = bool(v["line1"]) and bool(v["line2"])
    if cut:                                                  # the hero layout: big title BEHIND the head, the cutout in front
        shutil.copy(cut, os.path.join(out, "assets", "cutout.png"))
        (s1, n1), (s2, n2) = title_size(v["line1"]), title_size(v["line2"])
        g = hero_geometry(face, two_lines, s1, s2, n1, n2)
        page = PAGE_HERO.format(
            W=W, H=H, vars=hfbuild.brand_vars(), s1=s1, s2=s2, sv=hfbuild.fit_size(v["card_value"], 72, 44, 640), sticker_top=(1370 if v["card_value"] else 1330), card_top=1190, **g,
            line1=e(v["line1"]), line2=e(v["line2"]),
            tag=f'<div id="tag">{e(v["tag"])}</div>' if v["tag"] else "",
            sticker=f'<div id="sticker">{e(v["sticker"])}</div>' if v["sticker"] else "",
            card=(f'<div id="card">{"<div class=lbl>" + e(v["card_label"]) + "</div>" if v["card_label"] else ""}<div class="val">{val}</div></div>') if v["card_value"] else "")
        open(os.path.join(out, "index.html"), "w", encoding="utf-8").write(page)
        json.dump({"id": "cover", "name": "cover"}, open(os.path.join(out, "meta.json"), "w"))
        json.dump({"paths": {"blocks": "compositions", "assets": "assets"}, "media": {"autoProxy": False}}, open(os.path.join(out, "hyperframes.json"), "w"), indent=1)
        return out
    page = PAGE.format(
        W=W, H=H, vars=hfbuild.brand_vars(),
        photo_top=(940 if v["card_value"] else 800) if two_lines else 700,
        sticker_top=(1115 if v["card_value"] else 1000),
        s1=hfbuild.fit_size(v["line1"], 130, 64), s2=hfbuild.fit_size(v["line2"], 130, 64), sv=hfbuild.fit_size(v["card_value"], 72, 44, 640),
        photo=f'<div id="photo"><img src="assets/photo{ext}" alt=""></div>',
        tag=f'<div id="tag">{e(v["tag"])}</div>' if v["tag"] else "",
        line1=e(v["line1"]), line2=e(v["line2"]),
        sticker=f'<div id="sticker">{e(v["sticker"])}</div>' if v["sticker"] else "",
        card=(f'<div id="card">{"<div class=lbl>" + e(v["card_label"]) + "</div>" if v["card_label"] else ""}'
              f'<div class="val">{val}</div></div>') if v["card_value"] else "")
    open(os.path.join(out, "index.html"), "w", encoding="utf-8").write(page)
    json.dump({"id": "cover", "name": "cover"}, open(os.path.join(out, "meta.json"), "w"))
    json.dump({"paths": {"blocks": "compositions", "assets": "assets"}, "media": {"autoProxy": False}},
              open(os.path.join(out, "hyperframes.json"), "w"), indent=1)
    return out


def shoot(project, dest):
    shots = os.path.join(os.path.dirname(project), "_shots")
    shutil.rmtree(shots, ignore_errors=True)
    r = subprocess.run(HF + ["snapshot", project, "--at", "0.5", "--no-end", "--keep", "-o", shots],
                       capture_output=True, text=True, timeout=300)
    pngs = sorted(glob.glob(os.path.join(shots, "*.png")))
    if not pngs:
        raise CoverError("cover snapshot failed: " + (r.stderr or r.stdout)[-300:])
    to_jpg(pngs[0], dest)
    shutil.rmtree(shots, ignore_errors=True)
    return dest


def readable(src):
    """iPhone photos (HEIC) -> JPEG with macOS's own `sips` (ffmpeg often can't read them). Other images unchanged."""
    if not src.lower().endswith((".heic", ".heif")):
        return src
    out = os.path.splitext(src)[0] + "_heic.jpg"
    if os.path.exists(out) and os.path.getmtime(out) >= os.path.getmtime(src):
        return out
    if shutil.which("sips"):
        subprocess.run(["sips", "-s", "format", "jpeg", src, "--out", out], capture_output=True)
    if not os.path.exists(out):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-frames:v", "1", out], capture_output=True)
    if not os.path.exists(out):
        raise CoverError("couldn't read this iPhone photo (HEIC): export it as JPG and try again")
    return out


def to_jpg(src, dest):
    """Any image -> 1080x1920 JPEG, filling the frame (centre crop)."""
    src = readable(src)
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-vf",
                        f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}", "-frames:v", "1", "-q:v", "2", dest],
                       capture_output=True, text=True)
    if r.returncode or not os.path.exists(dest):
        raise CoverError("couldn't convert the image: " + r.stderr[-200:])
    return dest


def make(job):
    """Write review/cover.jpg. Returns {"cover", "source"}."""
    os.makedirs(os.path.join(job, "cover"), exist_ok=True); os.makedirs(os.path.join(job, "review"), exist_ok=True)
    dest = os.path.join(job, "review", "cover.jpg")
    own = own_file(job, "own")
    if own:
        return {"cover": to_jpg(own, dest), "source": "your own cover"}
    own_photo = own_file(job, "photo")
    bm = None if own_photo else best_moment(job)
    photo = own_photo or pick_frame(job, os.path.join(job, "cover", "frame.jpg"))
    v = values(job)
    cut = cutout(readable(photo), os.path.join(job, "cover", "cutout.png"))      # the person cut out; without it the older layout is used
    shoot(build(job, v, photo, cut=cut, face=(bm or {}).get("face")), dest)
    json.dump(v, open(os.path.join(job, "cover", "values.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return {"cover": dest, "source": "your photo" if own_file(job, "photo") else "a frame from your video", "values": v, "layout": "hero (cutout)" if cut else "classic"}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    try:
        print(json.dumps(make(os.path.abspath(sys.argv[1])), ensure_ascii=False))
    except CoverError as e:
        sys.exit(f"COVER: {e}")
