"""Timeline editor engine (T81-T83). Free, local, ffmpeg only; nothing here is destructive.

A SEQUENCE is the order of footage pieces that becomes the reel's raw material: segments {id, clip, in, out} (seconds inside that clip's
working copy). The default is every clip whole, in order. Hesham splits, trims, deletes and reorders on the timeline page; "Check my cuts"
proposes cuts from facts already measured (pauses, false starts, repeats, long silences at the edges); "Auto-edit" applies the sequence
and runs the whole pipeline on it. Applying builds ONE new proxy.mp4 from the clip proxies in a single exact pass and MOVES everything
derived from the old footage (transcript, story, plan, draft...) to before_sequence/<stamp>/ so "Undo" can put it all back.
Originals and clip proxies are never touched.
"""
import json, os, re, shutil, subprocess, time

MIN_SEG = 0.3
DERIVED = ("transcript_asr.json", "transcript.json", "transcript_fix_meta.json", "transcript_review_meta.json", "transcript_asr_dropped.json",
           "selects.json", "chosen_select.json", "edl.json", "keyframes.json", "shot_log.json", "scene_plan.json", "timeline.json", "validation.json",
           "speech_intel.json", "content_intel.json", "editorial.json", "visual_plan.json", "qa.json", "qa_final.json", "manual_edit.json",
           "ready_score.json", "report.md", "waveform.json", "audio16k.wav", "silences.txt", "loudness.txt", "cost_before.json")
DIRS = ("review", "hyperframes", "render_cache", "edit_package", "frames", "_asr")


def _jl(p, d=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return d


def _jw(p, x):
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(x, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def _run(cmd, timeout=3600):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


# ----------------------------------------------------------------------------- source clips and the sequence
def clips(job):
    """The footage pieces available to the timeline: from media_index.json (the SOURCE index), else from clip_map.json."""
    src = _jl(os.path.join(job, "media_index_source.json")) or _jl(os.path.join(job, "media_index.json"))
    if src and src.get("clips"):
        return src["clips"]
    cm = _jl(os.path.join(job, "clip_map.json"), {}) or {}
    return [{"id": f"c{n:02d}", "name": c["clip"], "proxy": c["proxy"], "duration": c["duration"], "start": c.get("start", 0), "end": c.get("end"),
             "role": None, "scenes": [], "speech_segments": []} for n, c in enumerate(cm.get("clips", []), 1)]


def default(job):
    return {"version": 1, "segments": [{"id": f"s{n}", "clip": c["id"], "in": 0.0, "out": round(float(c["duration"]), 3)} for n, c in enumerate(clips(job), 1)]}


def load(job):
    s = _jl(os.path.join(job, "sequence.json"))
    if s and s.get("segments"):
        return s
    return default(job)


def validate(job, seq):
    """-> (clean sequence, [plain-words problems]). Problems mean it must not be saved/applied."""
    by = {c["id"]: c for c in clips(job)}
    out, err = [], []
    raw = (seq or {}).get("segments") if isinstance(seq, dict) else None
    if not isinstance(raw, list) or not raw:
        return {"version": 1, "segments": []}, ["the timeline is empty: keep at least one piece of footage"]
    for n, s in enumerate(raw, 1):
        try:
            c, a, b = s.get("clip"), round(float(s.get("in")), 3), round(float(s.get("out")), 3)
        except (TypeError, ValueError, AttributeError):
            err.append(f"piece {n} is damaged"); continue
        if c not in by:
            err.append(f"piece {n} uses footage {c!r} that does not exist"); continue
        d = float(by[c]["duration"])
        a, b = max(0.0, a), min(d, b)
        if b - a < MIN_SEG:
            err.append(f"piece {n} is shorter than {MIN_SEG} s: delete it or make it longer"); continue
        out.append({"id": str(s.get("id") or f"s{n}")[:20], "clip": c, "in": a, "out": b})
    ids = [s["id"] for s in out]
    if len(set(ids)) != len(ids):                                  # keep ids unique
        for n, s in enumerate(out, 1):
            s["id"] = f"s{n}"
    return {"version": 1, "segments": out}, err


def duration(seq):
    return round(sum(s["out"] - s["in"] for s in seq["segments"]), 3)


def save(job, seq):
    clean, err = validate(job, seq)
    if err:
        return False, "Not saved: " + "; ".join(err[:3]), clean
    clean["saved_at"] = time.strftime("%Y-%m-%d %H:%M")
    _jw(os.path.join(job, "sequence.json"), clean)
    return True, f"Saved ({len(clean['segments'])} pieces, {duration(clean):.1f} s).", clean


# ----------------------------------------------------------------------------- editing operations (pure, used by the page's logic and by Accept)
def split(seq, seg_id, t):
    """Cut one piece in two at clip time t."""
    out = []
    for s in seq["segments"]:
        if s["id"] == seg_id and s["in"] + MIN_SEG <= t <= s["out"] - MIN_SEG:
            out += [dict(s, out=round(t, 3)), dict(s, id=s["id"] + "b", **{"in": round(t, 3)})]
        else:
            out.append(s)
    return {"version": 1, "segments": out}


def cut_range(seq, clip, a, b):
    """Remove clip time a-b wherever it occurs (a piece may be split in two or shortened); pieces under MIN_SEG vanish."""
    out = []
    for s in seq["segments"]:
        if s["clip"] != clip or b <= s["in"] or a >= s["out"]:
            out.append(s); continue
        left = dict(s, out=round(max(s["in"], a), 3)); right = dict(s, id=s["id"] + "b", **{"in": round(min(s["out"], b), 3)})
        out += [x for x in (left, right) if x["out"] - x["in"] >= MIN_SEG]
    return {"version": 1, "segments": out}


# ----------------------------------------------------------------------------- Check my cuts (T82): facts already measured, plain reasons
def check_cuts(job, seq=None):
    """Markers: [{id, clip, in, out, kind, why}] on SOURCE clip time. Free: uses speech segments, pauses, fillers and repeats (never invents)."""
    seq = seq or load(job)
    by = {c["id"]: c for c in clips(job)}
    marks = []

    def add(c, a, b, kind, why):
        if b - a >= 0.15:
            marks.append({"id": f"m{len(marks) + 1}", "clip": c, "in": round(a, 2), "out": round(b, 2), "kind": kind, "why": why})
    for s in seq["segments"]:
        c = by.get(s["clip"])
        if not c:
            continue
        sp = sorted(c.get("speech_segments") or [])
        if sp:
            inside = [x for x in sp if x[1] > s["in"] and x[0] < s["out"]]
            if inside and inside[0][0] - s["in"] >= 0.8:
                add(s["clip"], s["in"], inside[0][0] - 0.15, "silence", f"{inside[0][0] - s['in']:.1f} s of silence before you start talking")
            if inside and s["out"] - inside[-1][1] >= 0.8:
                add(s["clip"], inside[-1][1] + 0.15, s["out"], "silence", f"{s['out'] - inside[-1][1]:.1f} s of silence after you stop talking")
            for p, q in zip(inside, inside[1:]):
                gap = q[0] - p[1]
                if gap >= 1.2 and s["in"] <= p[1] and q[0] <= s["out"]:
                    add(s["clip"], p[1] + 0.2, q[0] - 0.2, "pause", f"a pause of {gap:.1f} s")
    # false starts and repeats measured on the transcript of the CURRENT footage (when the reel has been through the pipeline)
    si = _jl(os.path.join(job, "speech_intel.json"), {}) or {}
    idx = _jl(os.path.join(job, "media_index.json"), {}) or {}
    cur = {c["id"]: c for c in idx.get("clips", [])}
    d = si.get("delivery", {}) or {}
    words = _jl(os.path.join(job, "transcript.json"), []) or []
    def to_clip(t):
        for c in cur.values():
            if c["start"] <= t < c["end"]:
                return c.get("clip_id", c["id"]), round(t - c["start"] + float(c.get("source_in", 0.0)), 2)
        return None, None
    for kind, items, why in (("repeat", d.get("repeats", []), "the same words said twice (a false start)"),
                             ("filler", d.get("fillers", []), "a filler sound")):
        for e in items[:40]:
            i = e.get("i")
            if not isinstance(i, int) or i >= len(words):
                continue
            cid, a = to_clip(words[i]["start"]); _, b = to_clip(words[i]["end"])
            if cid in by and a is not None and b is not None and any(s["clip"] == cid and s["in"] <= a and b <= s["out"] for s in seq["segments"]):
                add(cid, max(0.0, a - 0.05), b + 0.05, kind, why)
    marks.sort(key=lambda m: (m["clip"], m["in"]))
    for n, m in enumerate(marks, 1):
        m["id"] = f"m{n}"
    return marks


# ----------------------------------------------------------------------------- applying a sequence (T81/T83)
def _has_audio(path):
    r = _run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", path], 60)
    return bool(r.stdout.strip())


def build_command(job, seq, out):
    """One ffmpeg pass that cuts every piece exactly and joins them (frame exact, constant 30 fps, 1080x1920)."""
    by = {c["id"]: c for c in clips(job)}
    used = []
    for s in seq["segments"]:
        if s["clip"] not in used:
            used.append(s["clip"])
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    for cid in used:
        cmd += ["-i", os.path.join(job, by[cid]["proxy"])]
    parts, labels = [], ""
    for n, s in enumerate(seq["segments"]):
        k = used.index(s["clip"]); a, b = s["in"], s["out"]
        parts.append(f"[{k}:v]trim=start={a}:end={b},setpts=PTS-STARTPTS,fps=30,format=yuv420p[v{n}]")
        if _has_audio(os.path.join(job, by[s["clip"]]["proxy"])):
            parts.append(f"[{k}:a]atrim=start={a}:end={b},asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo[a{n}]")
        else:
            parts.append(f"aevalsrc=0|0:d={b - a:.3f}:s=48000[a{n}]")
        labels += f"[v{n}][a{n}]"
    parts.append(f"{labels}concat=n={len(seq['segments'])}:v=1:a=1[v][a]")
    return cmd + ["-filter_complex", ";".join(parts), "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-g", "30",
                  "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", out]


def remap_index(job, seq):
    """media_index.json for the NEW footage: one entry per piece, with scenes and speech shifted to the new timeline (keeps the pipeline's helpers right)."""
    by = {c["id"]: c for c in clips(job)}
    out, t = [], 0.0
    for n, s in enumerate(seq["segments"], 1):
        c = by[s["clip"]]; d = round(s["out"] - s["in"], 3)
        sc = [{"start": round(max(0.0, x["start"] - s["in"]), 2), "end": round(min(d, x["end"] - s["in"]), 2), **({"thumb": x["thumb"]} if "thumb" in x else {})}
              for x in c.get("scenes", []) if x["end"] > s["in"] and x["start"] < s["out"]]
        spk = [[round(max(0.0, a - s["in"]), 2), round(min(d, b - s["in"]), 2)] for a, b in c.get("speech_segments", []) if b > s["in"] and a < s["out"]]
        out.append(dict(c, id=f"p{n:02d}", clip_id=c["id"], start=round(t, 3), end=round(t + d, 3), duration=d, source_in=s["in"], scenes=sc, speech_segments=spk))
        t += d
    return {"version": 1, "joined_proxy": "proxy.mp4", "duration": round(t, 3), "clips": out,
            "note": "Built from the timeline sequence; media_index_source.json keeps the original clips."}


def apply(job, seq, say=print):
    """Build the new proxy, set aside everything derived from the old footage, regenerate audio facts. -> (ok, message)."""
    clean, err = validate(job, seq)
    if err:
        return False, "Can't apply: " + "; ".join(err[:3])
    stamp = time.strftime("%Y%m%d-%H%M%S")
    new = os.path.join(job, "proxy_new.mp4")
    r = _run(build_command(job, clean, new))
    if r.returncode or not os.path.exists(new) or os.path.getsize(new) == 0:
        return False, "Building the new footage failed: " + (r.stderr or "").strip().splitlines()[-1][:160] if (r.stderr or "").strip() else "Building the new footage failed"
    bk = os.path.join(job, "before_sequence", stamp)
    os.makedirs(bk, exist_ok=True)
    if not os.path.exists(os.path.join(job, "media_index_source.json")):                                       # the original clips stay known
        _jw(os.path.join(job, "media_index_source.json"), {"clips": clips(job)})
    for f in DERIVED + ("proxy.mp4", "clip_map.json", "media_index.json", "job.json.before"):
        if os.path.exists(os.path.join(job, f)):
            shutil.move(os.path.join(job, f), os.path.join(bk, f))
    for d in DIRS:
        if os.path.isdir(os.path.join(job, d)):
            shutil.move(os.path.join(job, d), os.path.join(bk, d))
    os.replace(new, os.path.join(job, "proxy.mp4"))
    total = duration(clean)
    _jw(os.path.join(job, "media_index.json"), remap_index(job, clean))
    cm, t = [], 0.0
    for s in clean["segments"]:
        c = next(c for c in clips(job) if c["id"] == s["clip"]); d = round(s["out"] - s["in"], 3)
        cm.append({"clip": c["name"], "proxy": c["proxy"], "duration": d, "start": round(t, 3), "end": round(t + d, 3), "src_in": s["in"]}); t += d
    _jw(os.path.join(job, "clip_map.json"), {"clips": cm, "duration": total})
    wav = os.path.join(job, "audio16k.wav")
    _run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", os.path.join(job, "proxy.mp4"), "-vn", "-ac", "1", "-ar", "16000", wav], 600)
    r = _run(["ffmpeg", "-hide_banner", "-i", wav, "-af", "silencedetect=noise=-35dB:d=0.4", "-f", "null", "-"], 600)
    open(os.path.join(job, "silences.txt"), "w").write("\n".join(l for l in r.stderr.splitlines() if "silence_" in l) + "\n")
    r = _run(["ffmpeg", "-hide_banner", "-i", os.path.join(job, "proxy.mp4"), "-af", "ebur128", "-f", "null", "-"], 600)
    m = re.findall(r"I:\s+(-?[0-9.]+) LUFS", r.stderr)
    open(os.path.join(job, "loudness.txt"), "w").write((f"I: {m[-1]} LUFS" if m else "unknown") + "\n")
    jp = os.path.join(job, "job.json")
    j = _jl(jp, {}) or {}
    j.update(status="ingested", duration=total, sequence_applied=stamp)
    _jw(jp, j)
    _jw(os.path.join(job, "sequence.json"), dict(clean, saved_at=time.strftime("%Y-%m-%d %H:%M"), applied=stamp))
    return True, f"The timeline is applied ({len(clean['segments'])} pieces, {total:.1f} s). Your earlier version is kept: you can undo."


def undo(job):
    """Put back what was there before the last apply. The sequence's own results are moved aside, not deleted. -> (ok, message)"""
    root = os.path.join(job, "before_sequence")
    stamps = sorted(os.listdir(root)) if os.path.isdir(root) else []
    if not stamps:
        return False, "there is nothing to undo"
    last = stamps[-1]; bk = os.path.join(root, last)
    aside = os.path.join(job, "after_sequence_undone", time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(aside, exist_ok=True)
    for f in DERIVED + ("proxy.mp4", "clip_map.json", "media_index.json", "sequence.json"):
        if os.path.exists(os.path.join(job, f)):
            shutil.move(os.path.join(job, f), os.path.join(aside, f))
    for d in DIRS:
        if os.path.isdir(os.path.join(job, d)):
            shutil.move(os.path.join(job, d), os.path.join(aside, d))
    for f in os.listdir(bk):
        shutil.move(os.path.join(bk, f), os.path.join(job, f))
    os.rmdir(bk)                                                  # now empty: it only held what was just moved back
    jp = os.path.join(job, "job.json")
    j = _jl(jp, {}) or {}
    j.pop("sequence_applied", None)
    _jw(jp, j)
    return True, "Back to the version before the timeline change."


# ----------------------------------------------------------------------------- what the page draws
def waveform(job, clip, per_s=10):
    """Loudness peaks (0-100) of one clip's working copy, cached in waveforms/<clip>.json."""
    by = {c["id"]: c for c in clips(job)}
    c = by.get(clip)
    if not c:
        return {"per_s": per_s, "peaks": []}
    cache = os.path.join(job, "waveforms", clip + ".json")
    src = os.path.join(job, c["proxy"])
    if os.path.exists(cache) and os.path.exists(src) and os.path.getmtime(cache) >= os.path.getmtime(src):
        return _jl(cache)
    if not os.path.exists(src):
        return {"per_s": per_s, "peaks": []}
    from array import array
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", src, "-vn", "-ac", "1", "-ar", str(per_s * 100), "-f", "s16le", "-"], capture_output=True, timeout=300)
    a = array("h"); a.frombytes(r.stdout[: len(r.stdout) // 2 * 2])
    peaks = [max((abs(x) for x in a[k:k + 100]), default=0) for k in range(0, len(a), 100)]
    top = max(peaks or [1]) or 1
    data = {"per_s": per_s, "peaks": [round(100 * p / top) for p in peaks]}
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    _jw(cache, data)
    return data


def state(job):
    seq = load(job)
    return {"clips": [{"id": c["id"], "name": c.get("name"), "role": c.get("role"), "duration": c["duration"], "proxy": c["proxy"],
                       "scenes": c.get("scenes", []), "speech_segments": c.get("speech_segments", []), "waveform": waveform(job, c["id"])} for c in clips(job)],
            "sequence": seq, "duration": duration(seq), "applied": bool(_jl(os.path.join(job, "job.json"), {}).get("sequence_applied")),
            "can_undo": bool(os.path.isdir(os.path.join(job, "before_sequence")) and os.listdir(os.path.join(job, "before_sequence")))}
