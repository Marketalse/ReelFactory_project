#!/usr/bin/env python3
"""Check and render a compiled job. $0 (local).

    python3 scripts/render.py jobs/<job> --draft            check + contact sheet + review/draft_540p.mp4 + edit_package/
    python3 scripts/render.py jobs/<job> --final            after Hesham's approval: final/reel_vN.mp4 + cover suggestion

The HyperFrames CLI version is pinned in config/project.json -> tools.hyperframes.
"""
import argparse, glob, json, os, re, shutil, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import config as cfg       # noqa: E402
from lib import hfbuild             # noqa: E402
import qa_check                     # noqa: E402

HF = ["npx", "--yes", f"hyperframes@{cfg.PROJECT.get('tools', {}).get('hyperframes', '0.8.226')}"]


class RenderError(Exception):
    pass


ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
NOISE = re.compile(r"^\s*(npm (notice|warn|WARN)|npx: |\[?[0-9:.]+\]?\s*$|$)")
ENV = dict(os.environ, NPM_CONFIG_UPDATE_NOTIFIER="false", NPM_CONFIG_FUND="false", NO_UPDATE_NOTIFIER="1")


def run(cmd, cwd, timeout=1800):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=ENV)
    return r.returncode, r.stdout, r.stderr


def explain(out, err, limit=400):
    """The lines that say what went wrong, without npm's update notices."""
    clean = ANSI.sub("", err + "\n" + out).replace("\r", "\n")
    lines = [l.rstrip() for l in clean.splitlines() if not NOISE.match(l) and "npm notice" not in l and "npm warn" not in l.lower()]
    hits = [l for l in lines if re.search(r"error|fail|cannot|not found|missing|denied|ENOENT|killed|timed? ?out", l, re.I)]
    text = " | ".join((hits or lines)[-4:]).strip()
    return (text or "no error text (see review/render_error.log)")[-limit:]


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True).stdout.strip()
    return float(out) if out else 0.0


def check(project):
    """hyperframes check: errors stop the job; warnings are returned for the report."""
    code, out, err = run(HF + ["check", "--json"], project, 900)
    try:
        d = json.loads(out[out.find("{"):])
    except ValueError:
        raise RenderError("hyperframes check did not return JSON: " + explain(out, err))
    found = []

    def walk(x):
        if isinstance(x, dict):
            if "severity" in x:
                found.append(x)
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(d)
    errors = [f for f in found if f.get("severity") == "error"]
    if errors or not d.get("ok", False):
        raise RenderError("hyperframes check failed: " + "; ".join(f"{e.get('code')}: {(e.get('message') or '')[:160]}" for e in errors[:5]))
    return [f"{f.get('code')}: {(f.get('message') or f.get('text') or '')[:140]}" for f in found]


def snapshot(project, total):
    ts = ",".join(f"{t:.2f}" for t in [0.0] + [total * k / 7 for k in range(1, 7)] + [max(0.0, total - 1.0)])
    code, out, err = run(HF + ["snapshot", "--at", ts], project, 900)
    m = re.findall(r"(\S+contact-sheet\.jpg)", out + err)
    return m[-1] if m else None


def render(project, out_path, quality):
    code, out, err = run(HF + ["render", "--quality", quality, "-o", out_path], project, 3600)
    if code or not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        log = os.path.join(os.path.dirname(os.path.abspath(out_path)), "render_error.log")
        try:
            open(log, "w", encoding="utf-8").write(f"$ {' '.join(HF)} render --quality {quality}\nexit {code}\n--- stdout\n{out}\n--- stderr\n{err}\n")
        except OSError:
            pass
        raise RenderError(f"render failed ({code}): " + explain(out, err))
    return out_path


SOUND = cfg.PROJECT.get("sound", {})
LUFS = float(SOUND.get("lufs", -14.0)); TRUE_PEAK = float(SOUND.get("true_peak", -1.5)); LRA = float(SOUND.get("lra", 9.0))
VOICE = SOUND.get("voice_filter", "highpass=f=75,lowpass=f=15000,acompressor=threshold=-21dB:ratio=2.5:attack=15:release=200:makeup=2")


def measure(path, pre=""):
    """First loudnorm pass: the numbers the second pass needs."""
    af = (pre + "," if pre else "") + f"loudnorm=I={LUFS}:TP={TRUE_PEAK}:LRA={LRA}:print_format=json"
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-vn", "-af", af, "-f", "null", "-"],
                       capture_output=True, text=True, env=ENV)
    txt = r.stderr
    try:
        return json.loads(txt[txt.rindex("{"):txt.rindex("}") + 1])
    except ValueError:
        return None


def even_sound(path):
    """Voice clean-up + two-pass loudness to the social-media level (about -14 LUFS, peaks under -1.5 dB).
    Re-encodes the audio only; the picture is copied untouched. No audio track = nothing to do."""
    has_audio = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", path],
                               capture_output=True, text=True, env=ENV).stdout.strip()
    if not has_audio or not SOUND.get("enabled", True):
        return None
    m = measure(path, VOICE)
    if not m or m.get("input_i") in (None, "-inf"):
        return None
    af = (f"{VOICE},loudnorm=I={LUFS}:TP={TRUE_PEAK}:LRA={LRA}:measured_I={m['input_i']}:measured_TP={m['input_tp']}"
          f":measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    tmp = path + ".sound" + os.path.splitext(path)[1]
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", path, "-map", "0", "-c:v", "copy",
                        "-af", af, "-ar", "48000", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", tmp],
                       capture_output=True, text=True, env=ENV)
    if r.returncode or not os.path.exists(tmp):
        if os.path.exists(tmp):
            os.remove(tmp)
        raise RenderError("sound levelling failed: " + explain(r.stdout, r.stderr))
    os.replace(tmp, path)
    return float(m["input_i"])


def verify(path, expected):
    d = duration(path)
    if abs(d - expected) > 0.2:
        raise RenderError(f"{os.path.basename(path)} is {d:.2f}s, expected {expected:.2f}s")
    return d


def srt(words_html_groups):
    def ts(t):
        h, r = divmod(t, 3600); m, s = divmod(r, 60)
        return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int(round((s - int(s)) * 1000)):03d}"
    out = []
    for n, (a, b, text) in enumerate(words_html_groups, 1):
        out.append(f"{n}\n{ts(a)} --> {ts(b)}\n{text}\n")
    return "\n".join(out)


def captions_srt(project, out_path):
    caps = open(os.path.join(project, "compositions", "caps.html"), encoding="utf-8").read()
    groups = []
    for m in re.finditer(r'data-start="([0-9.]+)" data-duration="([0-9.]+)"><div[^>]*>(.*?)</div></div>', caps):
        text = " ".join(re.sub("<[^>]+>", " ", m.group(3)).split())
        groups.append((float(m.group(1)), float(m.group(1)) + float(m.group(2)), text))
    open(out_path, "w", encoding="utf-8").write(srt(groups))


README = """Edit package - for small changes in CapCut (or any editor)

CapCut: new project, 9:16. Drag in:
  track 1:  1_video.mp4     you, already cut, with zooms and your voice
  track 2:  2_graphics.mov  captions, titles, cards, CTA on a transparent background (put it ABOVE track 1)
Both start at 0:00 and are the same length, so they line up by themselves.
- Want CapCut's own captions instead? Delete track 2 and import captions_ar.srt (Text > Captions > Import).
- 2_graphics.mov uses the Instagram handle on the last card. For TikTok, use the final TikTok video,
  or cover the handle in CapCut.

Bigger changes (any text, colours, timing): open the hyperframes/ folder in the HyperFrames desktop app,
or just write what to change on the dashboard and click Send changes.
"""


def edit_package(job, project):
    """At draft time: captions_ar.srt + the editable HyperFrames project (the heavy CapCut layers come on Approve)."""
    pkg = os.path.join(job, "edit_package"); os.makedirs(pkg, exist_ok=True)
    captions_srt(project, os.path.join(pkg, "captions_ar.srt"))
    dst = os.path.join(pkg, "hyperframes")
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(project, dst, ignore=shutil.ignore_patterns(".hyperframes", "*.mp4"))
    rel = os.path.relpath(os.path.join(project, "assets", "proxy.mp4"), os.path.join(dst, "assets"))
    try:
        os.symlink(rel, os.path.join(dst, "assets", "proxy.mp4"))
    except OSError:
        pass
    open(os.path.join(pkg, "README.txt"), "w", encoding="utf-8").write(README)
    return pkg


def capcut_layers(job, platform="instagram"):
    """On Approve: 1_video.mp4 (you + zooms + sound) and 2_graphics.mov (transparent ProRes 4444), same length."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from compile import compile_job
    tl = json.load(open(os.path.join(job, "timeline.json"), encoding="utf-8"))
    pkg = os.path.join(job, "edit_package"); os.makedirs(pkg, exist_ok=True)
    out = []
    for layer, name, fmt in (("video", "1_video.mp4", "mp4"), ("graphics", "2_graphics.mov", "mov")):
        try:
            project = compile_job(job, platform, final=True, layer=layer)
        except hfbuild.BuildError as e:
            raise RenderError(str(e))
        check(project)
        path = os.path.join(pkg, name)
        if os.path.exists(path):
            os.remove(path)
        code, o, e = run(HF + ["render", "--format", fmt, "--quality", "high", "-o", path], project, 3600)
        if code or not os.path.exists(path):
            open(os.path.join(pkg, "render_error.log"), "w", encoding="utf-8").write(f"{name}\nexit {code}\n--- stdout\n{o}\n--- stderr\n{e}\n")
            raise RenderError(f"{name} failed: " + explain(o, e))
        verify(path, tl["duration"])
        if fmt == "mp4":
            even_sound(path)
        out.append(path)
    open(os.path.join(pkg, "README.txt"), "w", encoding="utf-8").write(README)
    return out


def make_cover(job):
    """The cover image (review/cover.jpg). A cover problem never stops the reel: it is reported instead."""
    import cover as cov
    try:
        return cov.make(job)
    except Exception as e:              # noqa: BLE001
        return {"error": str(e)[:300]}


def draft(job):
    project = os.path.join(job, "hyperframes")
    tl = json.load(open(os.path.join(job, "timeline.json"), encoding="utf-8"))
    warnings = check(project)
    sheet = snapshot(project, tl["duration"])
    os.makedirs(os.path.join(job, "review"), exist_ok=True)
    full = render(project, os.path.join(job, "review", "_draft_full.mp4"), "draft")
    verify(full, tl["duration"])
    even_sound(full)
    qa = qa_check.run(job, full, final=False, project=project)
    small = os.path.join(job, "review", "draft_540p.mp4")
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", full, "-vf", "scale=540:-2",
                        "-c:v", "libx264", "-crf", "28", "-preset", "veryfast", "-c:a", "aac", "-b:a", "128k", small], capture_output=True, text=True)
    if r.returncode:
        raise RenderError("draft downscale failed: " + explain(r.stdout, r.stderr))
    os.remove(full)
    if sheet and os.path.exists(sheet):
        shutil.copy(sheet, os.path.join(job, "review", "contact_sheet.jpg"))
    pkg = edit_package(job, project)
    return {"draft": small, "contact_sheet": os.path.join(job, "review", "contact_sheet.jpg") if sheet else None,
            "edit_package": pkg, "check_warnings": warnings, "qa": qa}


def final(job, platforms=None):
    """After Hesham's Approve: ONE high-quality video (final/reel_vN.mp4), then the cover suggestion (review/cover.jpg).
    Per-platform copies and CapCut layers were dropped (Hesham, 2026-11-01): the reel has no handle or end card,
    so Instagram and TikTok get the same file. `platforms` is kept for old callers and ignored."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from compile import compile_job
    tl = json.load(open(os.path.join(job, "timeline.json"), encoding="utf-8"))
    os.makedirs(os.path.join(job, "final"), exist_ok=True)
    v = 1 + max([int(m) for f in glob.glob(os.path.join(job, "final", "reel_v*.mp4"))
                 for m in re.findall(r"reel_v(\d+)", os.path.basename(f))] or [0])
    try:
        project = compile_job(job, "instagram", final=True)
    except hfbuild.BuildError as e:
        raise RenderError(str(e))
    check(project)
    path = os.path.join(job, "final", f"reel_v{v}.mp4")
    if os.path.exists(path):
        raise RenderError(f"{path} exists; never overwritten")
    render(project, path, "high")
    verify(path, tl["duration"])
    even_sound(path)
    qa = qa_check.run(job, path, final=True, project=project)
    if qa["errors"]:
        bad = path.replace(".mp4", "_QA_FAILED.mp4"); os.rename(path, bad)
        raise RenderError("final video failed QA (kept as " + os.path.basename(bad) + "): " + "; ".join(qa["errors"][:4]))
    outs = [path]
    cover = make_cover(job)                       # step 2: the cover suggestion; a cover problem never stops the reel
    if isinstance(cover, dict) and cover.get("cover"):
        outs.append(cover["cover"])
    elif isinstance(cover, dict) and cover.get("error"):
        print(f"   cover not made: {cover['error']}")
    return outs


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("job"); g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--draft", action="store_true"); g.add_argument("--final", action="store_true")
    a = ap.parse_args()
    job = os.path.abspath(a.job)
    try:
        res = draft(job) if a.draft else final(job, cfg.PROJECT["review"]["platforms"])
    except RenderError as e:
        sys.exit(f"RENDER STOPPED: {e}")
    print(json.dumps(res, indent=1, ensure_ascii=False))
