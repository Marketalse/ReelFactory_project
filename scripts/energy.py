#!/usr/bin/env python3
"""Measures how busy and how loud your best reels are, so Reel Factory can aim for the same pace. Free, local, ffmpeg only.

    python3 scripts/energy.py references/own/*.mp4            # prints one line per reel + the target (median)
    python3 scripts/energy.py references/own/*.mp4 --save     # also writes config/energy.json (the targets)

Per reel: length, picture changes per minute, average and longest time without a change, seconds until the first sound,
loudness (LUFS). The target is the median of your reels. It only reads the videos; it never changes them."""
import json, os, re, statistics, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCENE = 0.30


def _ff(args):
    return subprocess.run(["ffmpeg", "-hide_banner", "-nostats", *args], capture_output=True, text=True, timeout=600).stderr


def duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path], capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


def measure(path):
    dur = duration(path)
    log = _ff(["-i", path, "-vf", f"select='gt(scene,{SCENE})',showinfo", "-an", "-f", "null", "-"])
    cuts = sorted(float(m) for m in re.findall(r"pts_time:([0-9.]+)", log))
    pts = [0.0] + cuts + [dur]
    gaps = [b - a for a, b in zip(pts, pts[1:]) if b > a]
    snd = _ff(["-i", path, "-vn", "-af", "silencedetect=noise=-35dB:d=0.1", "-f", "null", "-"])
    first = 0.0
    if re.search(r"silence_start: 0(\.0+)?\s", snd + " "):
        m = re.search(r"silence_end: ([0-9.]+)", snd)
        first = float(m.group(1)) if m else dur
    lu = _ff(["-i", path, "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"])
    m = re.findall(r"I:\s+(-?[0-9.]+) LUFS", lu)
    return {"file": os.path.basename(path), "seconds": round(dur, 1), "changes": len(cuts),
            "changes_per_min": round(len(cuts) / dur * 60, 1) if dur else 0,
            "avg_hold_s": round(sum(gaps) / len(gaps), 2) if gaps else 0, "longest_hold_s": round(max(gaps), 2) if gaps else 0,
            "first_sound_s": round(first, 2), "lufs": float(m[-1]) if m else None}


def targets(rows):
    def med(k):
        v = [r[k] for r in rows if r.get(k) is not None]
        return round(statistics.median(v), 2) if v else None
    return {"reels_measured": len(rows), "changes_per_min": med("changes_per_min"), "avg_hold_s": med("avg_hold_s"),
            "longest_hold_s": med("longest_hold_s"), "first_sound_s": med("first_sound_s"), "lufs": med("lufs"), "seconds": med("seconds"),
            "note": "median of your own best reels (scripts/energy.py). Picture changes include cuts, cards and zooms that change the frame."}


if __name__ == "__main__":
    files = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not files:
        sys.exit(__doc__)
    rows = []
    for f in files:
        try:
            r = measure(f); rows.append(r)
            print(f"{r['file']}: {r['seconds']}s · {r['changes_per_min']} changes/min · avg hold {r['avg_hold_s']}s · longest {r['longest_hold_s']}s · "
                  f"first sound {r['first_sound_s']}s · {r['lufs']} LUFS")
        except Exception as e:                                  # noqa: BLE001
            print(f"{os.path.basename(f)}: could not measure ({e})")
    if rows:
        t = targets(rows); print("TARGET:", json.dumps(t, ensure_ascii=False))
        if "--save" in sys.argv:
            with open(os.path.join(ROOT, "config", "energy.json"), "w", encoding="utf-8") as fh:
                json.dump(t, fh, ensure_ascii=False, indent=1)
            print("saved config/energy.json")
