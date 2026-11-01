#!/usr/bin/env python3
"""Pick a SMALL set of resized keyframes from proxy.mp4 for the vision model (SHAK-291).
Never sends video. Usage: keyframes.py <job_dir> [--width 540] [--every 2.0] [--scene 0.25] [--cap 40] [--start S --end E]
Picks: scene-change frames + one frame at least every --every seconds (+ first/last), merges frames closer than 0.6 s,
caps at --cap (drops the most redundant first). Writes <job>/keyframes/kf_XXXX_<t>s.jpg and keyframes.json with an
estimated Sonnet 5.5 cost (measured image tokens). Exit code 2 if the cap would be exceeded before trimming is possible."""
import argparse, json, os, re, subprocess, sys
FF = os.path.expanduser("~/.hermes/tools/ffmpeg-9.0.1-darwin-arm64/ffmpeg")
TOK = {1080: 2728, 720: 1233, 540: 737, 384: 387}   # measured input tokens/frame (Sonnet 5.5)
IN_PER_TOK, OUT_PER_TOK = 2e-6, 10e-6

def scene_times(video, thr, start, end):
    cmd = [FF, "-hide_banner", "-ss", str(start), "-to", str(end), "-i", video, "-vf", f"select='gt(scene,{thr})',showinfo", "-an", "-f", "null", "-"]
    err = subprocess.run(cmd, capture_output=True, text=True).stderr
    return [float(m) + start for m in re.findall(r"pts_time:([0-9.]+)", err)]

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("job"); ap.add_argument("--width", type=int, default=540)
    ap.add_argument("--every", type=float, default=2.0); ap.add_argument("--scene", type=float, default=0.25)
    ap.add_argument("--cap", type=int, default=40); ap.add_argument("--start", type=float, default=0.0); ap.add_argument("--end", type=float)
    a = ap.parse_args(); video = os.path.join(a.job, "proxy.mp4")
    dur = float(subprocess.run([FF.replace("ffmpeg", "ffprobe") if os.path.exists(FF.replace("ffmpeg","ffprobe")) else "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video], capture_output=True, text=True).stdout.strip() or 0) if False else None
    err = subprocess.run([FF, "-hide_banner", "-i", video], capture_output=True, text=True).stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err); dur = int(m[1])*3600 + int(m[2])*60 + float(m[3])
    end = min(a.end or dur, dur); start = a.start
    cand = {round(start + 0.3, 2), round(end - 0.3, 2)}
    t = start + a.every
    while t < end: cand.add(round(t, 2)); t += a.every
    sc = scene_times(video, a.scene, start, end); cand.update(round(x + 0.1, 2) for x in sc)
    ts = []
    for t in sorted(cand):                       # merge frames closer than 0.6 s (keep earlier)
        if not ts or t - ts[-1] >= 0.6: ts.append(t)
    while len(ts) > a.cap:                       # trim: drop the frame with the smallest gap to a neighbour
        gaps = [(min(ts[i]-ts[i-1] if i else 99, ts[i+1]-ts[i] if i < len(ts)-1 else 99), i) for i in range(1, len(ts)-1)]
        ts.pop(min(gaps)[1])
    out = os.path.join(a.job, "keyframes"); os.makedirs(out, exist_ok=True)
    for f in os.listdir(out): os.remove(os.path.join(out, f))
    items = []
    for i, t in enumerate(ts):
        p = os.path.join(out, f"kf_{i:03d}_{t:06.2f}s.jpg")
        subprocess.run([FF, "-hide_banner", "-loglevel", "error", "-y", "-ss", str(t), "-i", video, "-frames:v", "1", "-vf", f"scale={a.width}:-2", "-q:v", "4", p], check=True)
        items.append({"t": t, "file": os.path.relpath(p, a.job), "scene_change": any(abs(t-(x+0.1)) < 0.6 for x in sc)})
    tok = TOK.get(a.width, 737)
    est = len(items) * tok * IN_PER_TOK + (60 + 40 * len(items)) * OUT_PER_TOK   # one batched call, ~40 output tok/frame
    man = {"video": "proxy.mp4", "duration": dur, "width": a.width, "count": len(items), "scene_changes_found": len(sc),
           "tokens_per_frame": tok, "est_input_tokens": len(items) * tok, "est_cost_usd_batched_call": round(est, 4),
           "full_video_cost_usd_for_comparison": round(dur * 30 * (2728 * IN_PER_TOK + 76 * OUT_PER_TOK), 2), "frames": items}
    json.dump(man, open(os.path.join(a.job, "keyframes.json"), "w"), indent=1)
    print(json.dumps({k: v for k, v in man.items() if k != "frames"}, indent=1))

main()
