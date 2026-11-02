"""Media index = a VIRTUAL timeline of the footage. Free, local, ffmpeg only.

Stage 2 joins the clips into one working copy (proxy.mp4) so the pipeline can read it, but the joined file is never the
only truth. jobs/<job>/media_index.json remembers every clip on its own: which original it came from, its source timing, its
proxy, where it sits on the joined timeline, what it is (talking-head / b-roll...), where speech and scene changes are, and
a thumbnail per scene. Later steps (the timeline editor, AI "check my cuts") can rearrange clips from this index without
re-encoding anything. Nothing here changes a video file; the originals stay read-only.

Time mapping (the proxy is constant-frame-rate, starts at 0 and has the same length as its source):
    timeline time = clip["start"] + source time      source time = timeline time - clip["start"]
"""
import json, os, subprocess

THUMB_W = 216
MAX_THUMBS = 24


def _run(cmd, timeout=120):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def source_to_timeline(index, clip_id, t):
    c = next((c for c in index["clips"] if c["id"] == clip_id), None)
    if c is None or not 0 <= t <= c["duration"] + 0.05:
        return None
    return round(c["start"] + t, 3)


def timeline_to_source(index, t):
    """-> (clip_id, source_time) or None when t is outside the footage."""
    for c in index["clips"]:
        if c["start"] <= t < c["end"] or (t == c["end"] and c is index["clips"][-1]):
            return c["id"], round(t - c["start"], 3)
    return None


def _scenes(changes, dur):
    cuts = [0.0] + [c for c in sorted(changes) if 0.5 < c < dur - 0.5] + [round(dur, 2)]
    out = []
    for a, b in zip(cuts, cuts[1:]):
        if b - a >= 0.5:
            out.append({"start": round(a, 2), "end": round(b, 2)})
    return out or [{"start": 0.0, "end": round(dur, 2)}]


def thumbnails(proxy, scenes, out_dir, prefix):
    """One small picture from the middle of each scene (at most MAX_THUMBS, evenly spread). Returns the files written."""
    os.makedirs(out_dir, exist_ok=True)
    picks = scenes if len(scenes) <= MAX_THUMBS else [scenes[int(i * len(scenes) / MAX_THUMBS)] for i in range(MAX_THUMBS)]
    done = []
    for n, s in enumerate(picks, 1):
        f = os.path.join(out_dir, f"{prefix}_s{n:02d}.jpg")
        mid = (s["start"] + s["end"]) / 2
        r = _run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{mid:.2f}", "-i", proxy, "-frames:v", "1",
                  "-vf", f"scale={THUMB_W}:-2", "-q:v", "5", f])
        if r.returncode == 0 and os.path.exists(f):
            s["thumb"] = os.path.basename(f); done.append(f)
    return done


def build(job, parts, root, manifest=None):
    """parts = clip_map entries ({clip, proxy, duration, start, end}); manifest = the Stage 1 media manifest (optional).
    Writes and returns jobs/<job>/media_index.json."""
    from lib import media_check as mc
    by = {f.get("name"): f for f in (manifest or {}).get("files", [])}
    clips = []
    for n, p in enumerate(parts, 1):
        cid = f"c{n:02d}"
        m = by.get(p["clip"], {})
        proxy = os.path.join(job, p["proxy"])
        sub = os.path.dirname(proxy)
        jj, pj = {}, {}
        try:
            jj = json.load(open(os.path.join(sub, "job.json")))
            pj = json.load(open(os.path.join(sub, "probe.json")))
        except (OSError, ValueError):
            pass
        inp = (jj.get("inputs") or [{}])[0]
        v = next((s for s in pj.get("streams", []) if s.get("codec_type") == "video"), {})
        a = next((s for s in pj.get("streams", []) if s.get("codec_type") == "audio"), {})
        scan = m.get("scan") or mc.footage_scan(proxy, p["duration"]) or {}
        scenes = _scenes(scan.get("scene_changes", []), p["duration"])
        thumbnails(proxy, scenes, os.path.join(job, "thumbs"), cid)
        clips.append({
            "id": cid, "name": p["clip"], "asset_id": m.get("asset_id"), "sha256": m.get("sha256"),
            "role": m.get("role"), "role_why": m.get("role_why"),
            "source": inp.get("path"), "source_codec": inp.get("codec"), "source_fps": inp.get("source_fps"),
            "source_resolution": inp.get("resolution"), "rotation": inp.get("rotation"), "hdr": inp.get("hdr"),
            "source_timecode": (pj.get("format", {}).get("tags") or {}).get("timecode") or (v.get("tags") or {}).get("timecode"),
            "av_start_offset_s": round(float(a.get("start_time") or 0) - float(v.get("start_time") or 0), 3) if a and v else 0.0,
            "proxy": p["proxy"], "proxy_fps": 30,
            "start": p["start"], "end": p["end"], "duration": p["duration"],
            "speech_segments": m.get("speech_segments", []), "scenes": scenes,
            "motion": scan.get("motion"), "black_share": scan.get("black_share"), "frozen_share": scan.get("frozen_share"),
            "issues": m.get("issues", []),
        })
    index = {"version": 1, "joined_proxy": "proxy.mp4", "duration": parts[-1]["end"] if parts else 0.0,
             "note": "Virtual timeline: clips are only joined for the working copy; this index keeps each one separate.",
             "clips": clips}
    tmp = os.path.join(job, "media_index.json.tmp")
    json.dump(index, open(tmp, "w"), indent=1, ensure_ascii=False)
    os.replace(tmp, os.path.join(job, "media_index.json"))
    return index
