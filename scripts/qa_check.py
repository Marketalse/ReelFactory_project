#!/usr/bin/env python3
"""Deterministic QA on a rendered reel: free, no AI. Runs automatically on every draft and final.

    python3 scripts/qa_check.py jobs/<job> [--video review/draft_540p.mp4] [--final]

Errors stop the job before Hesham sees it; warnings go into report.md. Results: jobs/<job>/qa.json.
"""
import argparse, glob, json, os, re, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import config as cfg          # noqa: E402
from lib.director import spoken_numbers, DIGITS   # noqa: E402

BANNED = re.compile(r"\b(TODO|TBD|FIXME|lorem|ipsum|placeholder|undefined|NaN|null|pending|debug)\b|CONFIRM", re.I)
LOUD_TARGET, LOUD_TOL = -14.0, 3.0          # LUFS for social video; outside +-3 is a warning (music mixing comes later)


def ff(args):
    return subprocess.run(["ffmpeg", "-hide_banner", "-nostats"] + args, capture_output=True, text=True).stderr


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True).stdout.strip()
    return float(out) if out else 0.0


def black_spans(path, min_d=0.25):
    txt = ff(["-i", path, "-vf", f"blackdetect=d={min_d}:pix_th=0.08", "-an", "-f", "null", "-"])
    return [(float(a), float(b)) for a, b in re.findall(r"black_start:([0-9.]+) black_end:([0-9.]+)", txt)]


def freeze_spans(path, min_d):
    txt = ff(["-i", path, "-vf", f"freezedetect=n=0.003:d={min_d}", "-an", "-f", "null", "-"])
    starts = [float(x) for x in re.findall(r"freeze_start: ([0-9.]+)", txt)]
    ends = [float(x) for x in re.findall(r"freeze_end: ([0-9.]+)", txt)]
    total = duration(path)
    return [(s, ends[i] if i < len(ends) else total) for i, s in enumerate(starts)]


def loudness(path):
    txt = ff(["-i", path, "-af", "ebur128=peak=true", "-f", "null", "-"])
    i = re.findall(r"I:\s+(-?[0-9.]+) LUFS", txt)
    p = re.findall(r"Peak:\s+(-?[0-9.]+) dBFS", txt)
    return (float(i[-1]) if i else None), (float(p[-1]) if p else None)


def screen_texts(project):
    """Every text value that will appear on screen: block variable values + caption words."""
    out = []
    idx = open(os.path.join(project, "index.html"), encoding="utf-8").read()
    import html as h
    for m in re.finditer(r'id="([a-z0-9_]+)" class="clip" data-composition-id="[^"]+"[^>]*data-variable-values="([^"]*)"', idx):
        vals = json.loads(h.unescape(m.group(2)) or "{}")
        for k, v in vals.items():
            if isinstance(v, str) and v and not v.startswith(("assets/", "data:")):
                out.append((m.group(1), k, v))
    caps = os.path.join(project, "compositions", "caps.html")
    if os.path.exists(caps):
        for w in re.findall(r'<span class="caps-w[^"]*" data-t="[0-9.]+">([^<]*)</span>', open(caps, encoding="utf-8").read()):
            out.append(("caps", "word", h.unescape(w)))
    return out


def run(job, video, final=False, project=None):
    err, warn, m = [], [], {}
    tl = json.load(open(os.path.join(job, "timeline.json"), encoding="utf-8"))
    edl = json.load(open(os.path.join(job, "edl.json"), encoding="utf-8"))
    project = project or os.path.join(job, "hyperframes")

    d = duration(video); m["duration"] = round(d, 3)
    if abs(d - tl["duration"]) > 0.2:
        err.append(f"length {d:.2f}s but the plan is {tl['duration']:.2f}s")
    lmin, lmax = cfg.RULES["reel_length_s"]["min"], cfg.RULES["reel_length_s"]["max"]
    if not lmin <= d <= lmax:
        warn.append(f"length {d:.1f}s is outside the {lmin}-{lmax}s target")

    blacks = black_spans(video); m["black"] = blacks
    if blacks and blacks[0][0] < 0.05:
        err.append("the first frame is black (it becomes the thumbnail)")
    for a, b in blacks:
        if a >= 0.05:
            err.append(f"black screen {a:.1f}s-{b:.1f}s")

    hold = cfg.RULES["max_still_hold_s"]
    freezes = freeze_spans(video, hold + 0.5); m["frozen"] = freezes
    for a, b in freezes:
        (err if b - a > hold + 1.5 else warn).append(f"picture frozen {a:.1f}s-{b:.1f}s ({b - a:.1f}s)")

    lufs, peak = loudness(video); m["lufs"], m["true_peak"] = lufs, peak
    if lufs is None:
        err.append("no audio")
    else:
        if abs(lufs - LOUD_TARGET) > LOUD_TOL:
            warn.append(f"loudness {lufs:.1f} LUFS (target {LOUD_TARGET:.0f} +-{LOUD_TOL:.0f})")
        if peak is not None and peak > -0.5:
            warn.append(f"audio peaks at {peak:.1f} dBFS (risk of clipping)")

    # captions cover every spoken word outside full-screen cards and the CTA
    texts = screen_texts(project)
    cap_words = [t for s, k, t in texts if s == "caps"]
    expected = [w["text"] for w in edl["words"] if not any(a - 0.05 <= w["start"] < b for a, b in tl["caption_gaps"])]
    m["caption_words"], m["spoken_words_shown"] = len(cap_words), len(expected)
    if cap_words != expected:
        missing = len(expected) - len(cap_words)
        err.append(f"captions don't match the speech ({len(cap_words)} caption words vs {len(expected)} spoken; {missing:+d})")

    # numbers on screen must have been said; no placeholder text
    said = set(spoken_numbers(edl["words"]))
    for scene, key, text in texts:
        if scene == "caps":
            continue
        for n in DIGITS.findall(text):
            n = n.rstrip(".,")
            if n not in said and key != "kicker":          # chapter labels ("Rule 1") are not claims
                err.append(f"{scene}.{key} shows the number {n}, which was not said")
        if BANNED.search(text):
            err.append(f"{scene}.{key} contains placeholder text: {text!r}")
        if "@your_handle" in text:
            (err if final else warn).append(f"{scene}.{key}: handle not set (config/brand.json -> handles)")

    res = {"video": os.path.relpath(video, job), "final": final, "errors": err, "warnings": warn, "metrics": m}
    json.dump(res, open(os.path.join(job, "qa.json" if not final else "qa_final.json"), "w"), indent=1, ensure_ascii=False)
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("job"); ap.add_argument("--video"); ap.add_argument("--final", action="store_true")
    a = ap.parse_args()
    job = os.path.abspath(a.job)
    video = os.path.join(job, a.video) if a.video else os.path.join(job, "review", "draft_540p.mp4")
    r = run(job, video, a.final)
    print(json.dumps(r, indent=1, ensure_ascii=False))
    sys.exit(1 if r["errors"] else 0)
