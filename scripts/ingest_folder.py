#!/usr/bin/env python3
"""Ingest one reel's inbox folder (or a single clip) into a job folder. $0, no AI.

    python3 scripts/ingest_folder.py inbox/<slug> --slug <slug>
    python3 scripts/ingest_folder.py path/to/clip.MOV --slug <slug>

inbox/<slug>/clips/*   footage, joined in filename order (or video files directly in inbox/<slug>/)
inbox/<slug>/assets/*  logos (SVG/PNG) and screenshots -> jobs/<job>/assets/ (SVGs cleaned)
inbox/<slug>/refs/*    reference videos for this reel  -> jobs/<job>/refs/
inbox/<slug>/brief.md  optional notes                  -> jobs/<job>/brief.md

Each clip goes through scripts/ingest.sh (proxy, tone-mapping, checks; the original moves to assets/raw/ read-only).
The proxies are joined into jobs/<job>/proxy.mp4 and clip_map.json records where each clip sits on the timeline.
"""
import argparse, datetime, json, os, re, shutil, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import config as cfg   # noqa: E402

VIDEO = (".mov", ".mp4", ".m4v")


def sh(cmd, **k):
    r = subprocess.run(cmd, capture_output=True, text=True, **k)
    if r.returncode:
        raise SystemExit(f"FAILED: {' '.join(cmd[:4])}…\n{(r.stderr or r.stdout)[-600:]}")
    return r


def dur(path):
    return float(sh(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path]).stdout.strip())


def clean_svg(text):
    text = re.sub(r"<script\b.*?</script\s*>", "", text, flags=re.S | re.I)
    text = re.sub(r"\son[a-z]+\s*=\s*(\"[^\"]*\"|'[^']*')", "", text, flags=re.I)
    text = re.sub(r"(xlink:)?href\s*=\s*(\"(?!#)[^\"]*\"|'(?!#)[^']*')", "", text, flags=re.I)
    text = re.sub(r"<foreignObject\b.*?</foreignObject\s*>", "", text, flags=re.S | re.I)
    return text


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input"); ap.add_argument("--slug", required=True)
    a = ap.parse_args()
    if not re.match(r"^[a-z0-9][a-z0-9-]{1,40}$", a.slug):
        sys.exit("slug: lowercase letters, digits and dashes only")
    src = os.path.abspath(a.input)
    if os.path.isfile(src):
        folder, clips = None, [src]
    else:
        folder = src
        cdir = os.path.join(src, "clips") if os.path.isdir(os.path.join(src, "clips")) else src
        clips = sorted(os.path.join(cdir, f) for f in os.listdir(cdir) if f.lower().endswith(VIDEO))
    if not clips:
        sys.exit(f"no video files found in {src}")
    job = os.path.join(cfg.ROOT, "jobs", f"{datetime.date.today().isoformat()}-{a.slug}")
    if os.path.exists(os.path.join(job, "proxy.mp4")):
        sys.exit(f"{job} already has a proxy; use that job folder, or choose another slug")
    os.makedirs(job, exist_ok=True)

    parts = []
    for n, clip in enumerate(clips, 1):
        sub = f"{a.slug}/c{n:02d}"
        print(f"ingest {n}/{len(clips)}: {os.path.basename(clip)}")
        sh(["bash", os.path.join(cfg.ROOT, "scripts", "ingest.sh"), clip, sub], cwd=cfg.ROOT)
        p = os.path.join(job, f"c{n:02d}", "proxy.mp4")
        parts.append({"clip": os.path.basename(clip), "proxy": os.path.relpath(p, job), "duration": dur(p)})

    proxy = os.path.join(job, "proxy.mp4")
    if len(parts) == 1:
        shutil.copy(os.path.join(job, parts[0]["proxy"]), proxy)
    else:
        lst = os.path.join(job, "concat.txt")
        open(lst, "w").write("".join(f"file '{os.path.join(job, p['proxy'])}'\n" for p in parts))
        sh(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy",
            "-movflags", "+faststart", proxy])
    total, t = dur(proxy), 0.0
    for p in parts:
        p["start"] = round(t, 3); t += p["duration"]; p["end"] = round(t, 3)
    if abs(total - t) > 0.3:
        sys.exit(f"joined proxy is {total:.2f}s but clips add up to {t:.2f}s")
    json.dump({"clips": parts, "duration": total}, open(os.path.join(job, "clip_map.json"), "w"), indent=1)

    wav = os.path.join(job, "audio16k.wav")
    sh(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", proxy, "-vn", "-ac", "1", "-ar", "16000", wav])
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", wav, "-af", "silencedetect=noise=-35dB:d=0.4", "-f", "null", "-"],
                       capture_output=True, text=True)
    open(os.path.join(job, "silences.txt"), "w").write("\n".join(l for l in r.stderr.splitlines() if "silence_" in l) + "\n")
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", proxy, "-af", "ebur128", "-f", "null", "-"], capture_output=True, text=True)
    m = re.findall(r"I:\s+(-?[0-9.]+) LUFS", r.stderr)
    open(os.path.join(job, "loudness.txt"), "w").write((f"I: {m[-1]} LUFS" if m else "unknown") + "\n")

    if folder:
        for name in ("assets", "refs"):
            s = os.path.join(folder, name)
            if os.path.isdir(s):
                d = os.path.join(job, name); os.makedirs(d, exist_ok=True)
                for f in sorted(os.listdir(s)):
                    fp = os.path.join(s, f)
                    if not os.path.isfile(fp) or f.startswith("."):
                        continue
                    if f.lower().endswith(".svg"):
                        open(os.path.join(d, f), "w", encoding="utf-8").write(clean_svg(open(fp, encoding="utf-8", errors="replace").read()))
                    else:
                        shutil.copy(fp, os.path.join(d, f))
        if os.path.isfile(os.path.join(folder, "brief.md")):
            shutil.copy(os.path.join(folder, "brief.md"), os.path.join(job, "brief.md"))

    jp = os.path.join(job, "job.json")
    jobd = json.load(open(jp)) if os.path.exists(jp) else {}
    jobd.update({"id": os.path.basename(job), "status": "ingested", "clips": [p["clip"] for p in parts], "duration": total})
    json.dump(jobd, open(jp, "w"), indent=1, ensure_ascii=False)
    print(f"INGEST OK: {job}  ({len(parts)} clip(s), {total:.1f}s)")
    print(job)


if __name__ == "__main__":
    main()
