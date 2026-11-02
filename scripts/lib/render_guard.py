"""Stage 6 safety net around rendering. Free, local. Everything here explains itself in plain words.

  preflight(job)            T92  before a render: the plan is readable, every block and file it needs exists, enough disk
  write_manifest(...)       T93  the render recipe + export metadata saved next to the video
  verify_video(path, ...)   T94  the finished file: codec, size, 9:16, frame rate, length, plays to the very end
  sync_and_silence(...)     T95  voice vs planned words (drift), silences, peaks
  caption_checks(...)       T96  captions/cards really appear; caption widths fit the safe area
  recoverable(text)/retry   T97  one automatic retry for temporary render failures (never for full disk or a bad plan)
Warnings never stop a reel; only real defects (missing files, broken or wrong-size video) are errors.
"""
import hashlib, json, os, re, shutil, subprocess, sys, time

from lib import config as cfg

REGISTRY = os.path.join(cfg.ROOT, "templates", "blocks", "registry.json")
MIN_FREE_GB = 3.0
TARGET_FPS = 30.0


def _jl(path, d=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return d


def _ff(args, timeout=600):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


# ----------------------------------------------------------------------------- T92 preflight
def preflight(job, project=None, min_free_gb=MIN_FREE_GB):
    """-> list of problems in plain words ([] = ready to render)."""
    project = project or os.path.join(job, "hyperframes")
    bad = []
    free = shutil.disk_usage(job).free / 1e9
    if free < min_free_gb:
        bad.append(f"only {free:.1f} GB of disk space is free (rendering needs about {min_free_gb:g} GB): free some space first")
    tl, edl = _jl(os.path.join(job, "timeline.json")), _jl(os.path.join(job, "edl.json"))
    if not isinstance(tl, dict) or not tl.get("scenes"):
        bad.append("timeline.json is missing or empty: make the plan first (Try again)")
        return bad
    if not isinstance(edl, dict) or not edl.get("words"):
        bad.append("edl.json is missing or empty: the cut was not made (Try again)")
    blocks = (_jl(REGISTRY, {}) or {}).get("blocks", {})
    dur = tl.get("duration", 0)
    for s in tl["scenes"]:
        b = s.get("block")
        if b not in blocks:
            bad.append(f"scene {s.get('id')} uses an unknown block '{b}'"); continue
        f = blocks[b].get("file")
        if f and not os.path.exists(os.path.join(cfg.ROOT, "templates", "blocks", f)):
            bad.append(f"the template file for '{b}' is missing (templates/blocks/{f})")
        if not 0 <= s.get("t_in", 0) < s.get("t_out", 0) <= dur + 0.05:
            bad.append(f"scene {s.get('id')} ({b}) has impossible times {s.get('t_in')}-{s.get('t_out')} (reel is {dur}s)")
    if not os.path.exists(os.path.join(job, "proxy.mp4")) or os.path.getsize(os.path.join(job, "proxy.mp4")) == 0:
        bad.append("proxy.mp4 (your working copy of the footage) is missing or empty: upload the clips again")
    if not os.path.isdir(project) or not os.path.exists(os.path.join(project, "index.html")):
        bad.append("the video project was not built (hyperframes/index.html missing): Try again")
    else:
        for s in tl["scenes"]:
            if s.get("block") in blocks and blocks[s["block"]].get("file") and not os.path.exists(os.path.join(project, "compositions", s["id"] + ".html")):
                bad.append(f"the project is missing the file for scene {s['id']} ({s['block']})")
        pa = os.path.join(project, "assets")
        for need in ("proxy.mp4", os.path.join("fonts", "ReadexPro.ttf")):
            if not os.path.exists(os.path.join(pa, need)):
                bad.append(f"the project is missing assets/{need}")
        for s in tl["scenes"]:
            for k in ("logo_a", "logo_b"):
                v = (s.get("values") or {}).get(k)
                if v and not os.path.exists(os.path.join(project, v)) and not os.path.exists(os.path.join(job, "assets", os.path.basename(v))):
                    bad.append(f"logo file {os.path.basename(v)} (scene {s['id']}) is missing from the reel's assets")
    return bad


# ----------------------------------------------------------------------------- T93 recipe + metadata
def _sha(path, limit=None):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read(limit) if limit else f.read())
    return h.hexdigest()[:16]


def _version(cmd):
    try:
        return _ff(cmd, 20).stdout.splitlines()[0][:80]
    except (OSError, IndexError, subprocess.SubprocessError):
        return None


def write_manifest(job, kind, video, quality, info=None, qa=None, seconds=None):
    """jobs/<job>/render_manifest_<kind>.json: same inputs + same recipe = same video. Returns the dict."""
    files = {}
    for n in ("timeline.json", "edl.json", "scene_plan.json", "visual_plan.json", "editorial.json"):
        p = os.path.join(job, n)
        if os.path.exists(p):
            files[n] = _sha(p)
    px = os.path.join(job, "proxy.mp4")
    if os.path.exists(px):
        st = os.stat(px)
        files["proxy.mp4"] = f"{st.st_size} bytes, first MB {_sha(px, 1 << 20)}"
    cfgs = {n: _sha(os.path.join(cfg.CONFIG_DIR, n)) for n in ("rules.json", "brand.json", "project.json") if os.path.exists(os.path.join(cfg.CONFIG_DIR, n))}
    m = {"version": 1, "kind": kind, "made": time.strftime("%Y-%m-%d %H:%M:%S"),
         "recipe": {"hyperframes": cfg.PROJECT.get("tools", {}).get("hyperframes", "0.8.226"), "quality": quality, "fps": TARGET_FPS,
                    "ffmpeg": _version(["ffmpeg", "-version"]), "node": _version(["node", "--version"]), "python": sys.version.split()[0],
                    "sound": cfg.PROJECT.get("sound", {}), "settings_files": cfgs},
         "inputs": files,
         "output": {"file": os.path.relpath(video, job), "bytes": os.path.getsize(video) if os.path.exists(video) else None, **(info or {})},
         "seconds_to_render": seconds,
         "qa": {"errors": (qa or {}).get("errors", []), "warnings": (qa or {}).get("warnings", [])}}
    p = os.path.join(job, f"render_manifest_{kind}.json")
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)
    return m


# ----------------------------------------------------------------------------- T94 the finished file
def probe_video(path):
    r = _ff(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path], 60)
    try:
        return json.loads(r.stdout)
    except ValueError:
        return None


def verify_video(path, expected_s=None, width=None, height=None, decode=True):
    """-> (errors, warnings, info). Errors are real defects (missing/broken/wrong size or length/corrupted);
    warnings are things that may matter for posting (codec, pixel format, frame rate, sound codec)."""
    err, warn = [], []
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return [f"{os.path.basename(path)} was not written (empty or missing)"], [], {}
    p = probe_video(path)
    if not p:
        return [f"{os.path.basename(path)} can't be read: the file is damaged"], [], {}
    v = next((s for s in p.get("streams", []) if s.get("codec_type") == "video"), None)
    a = next((s for s in p.get("streams", []) if s.get("codec_type") == "audio"), None)
    if not v:
        return ["the video has no picture"], [], {}
    w, h = int(v.get("width", 0)), int(v.get("height", 0))
    num, _, den = (v.get("avg_frame_rate") or "0/1").partition("/")
    fps = float(num) / float(den) if float(den or 0) else 0.0
    dur = float((p.get("format") or {}).get("duration") or 0)
    info = {"width": w, "height": h, "fps": round(fps, 2), "codec": v.get("codec_name"), "pix_fmt": v.get("pix_fmt"),
            "audio_codec": (a or {}).get("codec_name"), "seconds": round(dur, 2)}
    if not h or abs(w / h - 9 / 16) > 0.01:
        err.append(f"size {w}x{h} is not 9:16")
    elif width and (w, h) != (width, height or round(width * 16 / 9)):
        err.append(f"size is {w}x{h}, expected {width}x{height or round(width * 16 / 9)}")
    if expected_s is not None and abs(dur - expected_s) > 0.2:
        err.append(f"length is {dur:.2f}s but the plan says {expected_s:.2f}s")
    if not a:
        err.append("the video has no sound track")
    if v.get("codec_name") != "h264":
        warn.append(f"picture codec is {v.get('codec_name')}, not h264 (Instagram and TikTok may refuse it)")
    if v.get("pix_fmt") != "yuv420p":
        warn.append(f"pixel format is {v.get('pix_fmt')}, not yuv420p (colours may look wrong on some phones)")
    if abs(fps - TARGET_FPS) > 0.5:
        warn.append(f"frame rate is {fps:.2f} fps, expected {TARGET_FPS:g}")
    if a and a.get("codec_name") != "aac":
        warn.append(f"sound codec is {a.get('codec_name')}, not aac")
    if decode and not err:                                     # play it to the very end: finds corrupted parts
        r = _ff(["ffmpeg", "-v", "error", "-xerror", "-i", path, "-f", "null", "-"], 900)
        if r.returncode:
            err.append("the file does not play to the end (corrupted part): " + (r.stderr.strip().splitlines() or ["decode error"])[0][:140])
    return err, warn, info


# ----------------------------------------------------------------------------- T95 sound and picture
def audio_onsets(path, noise=-35, min_sil=0.3):
    """Times where speech starts again after a pause (and silences) in the rendered audio."""
    r = _ff(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-vn", "-af", f"silencedetect=noise={noise}dB:d={min_sil}", "-f", "null", "-"], 600)
    starts = [float(x) for x in re.findall(r"silence_start: (-?[0-9.]+)", r.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([0-9.]+)", r.stderr)]
    sil = list(zip(starts, ends))
    return [e for _, e in sil], sil


def sync_and_silence(video, words, caption_gaps=(), max_drift=0.10, max_silence=1.2):
    """-> (errors, warnings, metrics). Drift = median gap between when speech starts in the video and when the plan says each word starts."""
    err, warn, m = [], [], {}
    onsets, sil = audio_onsets(video)
    starts = sorted(w["start"] for w in words)
    diffs = []
    for t in onsets:
        near = min(starts, key=lambda s: abs(s - t), default=None)
        if near is not None and abs(near - t) <= 0.6:
            diffs.append(t - near)
    m["onsets_matched"], m["onsets"] = len(diffs), len(onsets)
    if len(diffs) >= 3:
        diffs.sort(); med = diffs[len(diffs) // 2]
        m["median_offset_s"] = round(med, 3)
        if abs(med) > max_drift:
            warn.append(f"the voice is {abs(med):.2f}s {'late' if med > 0 else 'early'} compared with the words (sync): captions may not match")
    for a, b in sil:
        if b - a >= max_silence and not any(g0 - 0.3 <= a and b <= g1 + 0.3 for g0, g1 in caption_gaps):
            warn.append(f"{b - a:.1f}s of silence at {a:.1f}s-{b:.1f}s")
    return err, warn[:8], m


# ----------------------------------------------------------------------------- T96 captions and cards on the real frames
def gray_frame(video, t, w=108, h=192, box=None):
    """A tiny grayscale picture at time t as bytes (box = (x0,y0,x1,y1) in 1080x1920 units cuts a region first)."""
    vf = (f"crop=iw*{(box[2] - box[0]) / 1080:.4f}:ih*{(box[3] - box[1]) / 1920:.4f}:iw*{box[0] / 1080:.4f}:ih*{box[1] / 1920:.4f}," if box else "") + f"scale={w}:{h},format=gray"
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0, t):.3f}", "-i", video, "-frames:v", "1", "-vf", vf, "-f", "rawvideo", "-"],
                       capture_output=True, timeout=60)
    return r.stdout if r.returncode == 0 else b""


def diff(a, b):
    if not a or not b or len(a) != len(b):
        return None
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a)


def caption_checks(video, plan, max_samples=8):
    """Warnings (never errors): a planned caption or card that cannot be seen in the real video, and captions too wide for the safe area.
    plan = visual_plan.json."""
    warn = []
    zone = cfg.RULES["safe_zone"]
    room = 1080 - zone["left"] - zone["right"]
    size = (cfg.BRAND.get("captions") or {}).get("min_size_px") or 64
    wide = [e for e in plan.get("captions", {}).get("events", []) if len(e["text"].replace(" ", "")) * size * 0.55 + (len(e["text"].split()) - 1) * size * 0.3 > room]
    if wide:
        warn.append(f"{len(wide)} caption(s) may be wider than the safe area ({room}px), e.g. '{wide[0]['text']}' at {wide[0]['start']}s")
    ev = plan.get("captions", {}).get("events", [])
    band = tuple([zone["left"], zone["captions_y"][0], 1080 - zone["right"], zone["captions_y"][1]])
    step = max(1, len(ev) // max_samples)
    unseen = []
    for e in ev[::step][:max_samples]:
        d = diff(gray_frame(video, max(0, e["start"] - 0.12), 54, 24, band), gray_frame(video, e["start"] + min(0.25, (e["end"] - e["start"]) / 2), 54, 24, band))
        if d is not None and d < 0.5:
            unseen.append(e)
    if unseen:
        warn.append(f"{len(unseen)} of {min(max_samples, len(ev))} sampled captions could not be seen in the video, e.g. '{unseen[0]['text']}' at {unseen[0]['start']}s")
    gone = []
    for g in plan.get("graphics", []):
        if g["block"] in ("flash",) or g["t_out"] - g["t_in"] < 0.8:
            continue
        d = diff(gray_frame(video, max(0, g["t_in"] - 0.15)), gray_frame(video, g["t_in"] + min(0.5, (g["t_out"] - g["t_in"]) / 2)))
        if d is not None and d < 1.0:
            gone.append(g)
    if gone:
        warn.append(f"{len(gone)} planned card(s) do not show up on screen, e.g. {gone[0]['block']} at {gone[0]['t_in']}s")
    return warn[:6]


# ----------------------------------------------------------------------------- T97 retry only what is temporary
TEMP = re.compile(r"Target closed|Protocol error|browser (has )?(disconnected|crashed|closed)|ECONNRESET|ETIMEDOUT|timed? ?out|timeout|"
                  r"killed|SIGKILL|SIGSEGV|out of memory|ENOMEM|Navigation|crash|socket hang up|EAGAIN", re.I)
PERMANENT = re.compile(r"no space left|ENOSPC|disk full|not found|ENOENT|permission denied|EACCES|check failed|unknown block|invalid", re.I)


def recoverable(text):
    """True when the failure text looks temporary. A full disk or a broken plan is never retried."""
    t = text or ""
    return bool(TEMP.search(t)) and not PERMANENT.search(t)


def retry_once(fn, error_cls, sleep=time.sleep, log=print):
    """Run fn(); if it raises error_cls with a temporary-looking message, wait 5 s and run it ONCE more. Returns (result, tries)."""
    try:
        return fn(), 1
    except error_cls as e:
        if not recoverable(str(e)):
            raise
        log(f"   render hit a temporary problem ({str(e)[:120]}); trying that step once more")
        sleep(5)
        return fn(), 2
