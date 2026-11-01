#!/usr/bin/env python3
"""Check and render a compiled job. $0 (local).

    python3 scripts/render.py jobs/<job> --draft            check + contact sheet + review/draft_540p.mp4 + edit_package/
    python3 scripts/render.py jobs/<job> --final            after Hesham's approval: final/reel_vN_<platform>.mp4 per platform

The HyperFrames CLI version is pinned in config/project.json -> tools.hyperframes.
"""
import argparse, glob, json, os, re, shutil, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import config as cfg       # noqa: E402
from lib import hfbuild             # noqa: E402

HF = ["npx", "--yes", f"hyperframes@{cfg.PROJECT.get('tools', {}).get('hyperframes', '0.8.226')}"]


class RenderError(Exception):
    pass


def run(cmd, cwd, timeout=1800):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout, r.stderr


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
        raise RenderError("hyperframes check did not return JSON: " + (err or out)[-400:])
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
        raise RenderError(f"render failed ({code}): " + (err or out)[-400:])
    return out_path


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


def edit_package(job, project):
    """clean_cut.mp4 (talking head after cutting, no graphics), captions_ar.srt, and the HyperFrames project."""
    pkg = os.path.join(job, "edit_package"); os.makedirs(pkg, exist_ok=True)
    edl = json.load(open(os.path.join(job, "edl.json"), encoding="utf-8"))
    parts = []
    for i, s in enumerate(edl["segments"]):
        parts.append(f"[0:v]trim={s['src_in']}:{s['src_out']},setpts=PTS-STARTPTS[v{i}];[0:a]atrim={s['src_in']}:{s['src_out']},asetpts=PTS-STARTPTS[a{i}]")
    chain = ";".join(parts) + ";" + "".join(f"[v{i}][a{i}]" for i in range(len(parts))) + f"concat=n={len(parts)}:v=1:a=1[v][a]"
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", os.path.join(job, "proxy.mp4"),
                        "-filter_complex", chain, "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "18", "-preset", "veryfast",
                        "-c:a", "aac", "-b:a", "192k", os.path.join(pkg, "clean_cut.mp4")], capture_output=True, text=True)
    if r.returncode:
        raise RenderError("clean_cut failed: " + r.stderr[-300:])
    caps = open(os.path.join(project, "compositions", "caps.html"), encoding="utf-8").read()
    groups = []
    for m in re.finditer(r'data-start="([0-9.]+)" data-duration="([0-9.]+)"><div[^>]*>(.*?)</div></div>', caps):
        text = " ".join(re.sub("<[^>]+>", " ", m.group(3)).split())
        groups.append((float(m.group(1)), float(m.group(1)) + float(m.group(2)), text))
    open(os.path.join(pkg, "captions_ar.srt"), "w", encoding="utf-8").write(srt(groups))
    dst = os.path.join(pkg, "hyperframes")
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(project, dst, ignore=shutil.ignore_patterns(".hyperframes", "*.mp4"))
    rel = os.path.relpath(os.path.join(project, "assets", "proxy.mp4"), os.path.join(dst, "assets"))
    try:
        os.symlink(rel, os.path.join(dst, "assets", "proxy.mp4"))
    except OSError:
        pass
    open(os.path.join(pkg, "README.txt"), "w", encoding="utf-8").write(
        "Edit package\n- clean_cut.mp4: you after cutting (no graphics). Put it on track 1 in CapCut/DaVinci.\n"
        "- captions_ar.srt: the captions as text with timings (import into your editor if you want plain captions).\n"
        "- hyperframes/: the full project. Open it in the HyperFrames desktop app to change any text and export.\n"
        "Coming next: graphics layer with transparency (graphics_alpha.mov) and timeline.fcpxml.\n")
    return pkg


def draft(job):
    project = os.path.join(job, "hyperframes")
    tl = json.load(open(os.path.join(job, "timeline.json"), encoding="utf-8"))
    warnings = check(project)
    sheet = snapshot(project, tl["duration"])
    os.makedirs(os.path.join(job, "review"), exist_ok=True)
    full = render(project, os.path.join(job, "review", "_draft_full.mp4"), "draft")
    verify(full, tl["duration"])
    small = os.path.join(job, "review", "draft_540p.mp4")
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", full, "-vf", "scale=540:-2",
                        "-c:v", "libx264", "-crf", "28", "-preset", "veryfast", "-c:a", "aac", "-b:a", "96k", small], capture_output=True, text=True)
    if r.returncode:
        raise RenderError("draft downscale failed: " + r.stderr[-300:])
    os.remove(full)
    if sheet and os.path.exists(sheet):
        shutil.copy(sheet, os.path.join(job, "review", "contact_sheet.jpg"))
    pkg = edit_package(job, project)
    return {"draft": small, "contact_sheet": os.path.join(job, "review", "contact_sheet.jpg") if sheet else None,
            "edit_package": pkg, "check_warnings": warnings}


def final(job, platforms):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from compile import compile_job
    tl = json.load(open(os.path.join(job, "timeline.json"), encoding="utf-8"))
    os.makedirs(os.path.join(job, "final"), exist_ok=True)
    v = 1 + max([int(m) for f in glob.glob(os.path.join(job, "final", "reel_v*_*.mp4"))
                 for m in re.findall(r"reel_v(\d+)_", f)] or [0])
    outs = []
    for p in platforms:
        try:
            project = compile_job(job, p, final=True)
        except hfbuild.BuildError as e:
            raise RenderError(str(e))
        check(project)
        path = os.path.join(job, "final", f"reel_v{v}_{p}.mp4")
        if os.path.exists(path):
            raise RenderError(f"{path} exists; never overwritten")
        render(project, path, "high")
        verify(path, tl["duration"])
        outs.append(path)
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
