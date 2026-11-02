"""Stage 1 media check: look at every uploaded file ON ITS OWN before any processing. Free, local, ffmpeg only.

For each file: is it readable, what is in it (codec, length, size, frame rate, sound), a unique ID and checksum, a visual
fingerprint to spot duplicates, how much of it is speech, and a plain-words verdict. One bad file never stops the others.
Originals are only READ here, never changed. The result is written to jobs/<job>/media_manifest.json."""
import glob, hashlib, json, os, re, subprocess

MIN_SHORT_SIDE = 720            # below this the picture is soft
MIN_SECONDS = 1.0
SIMILAR_BITS = 6                # fingerprint difference (of 64) that still counts as "looks the same"
AUDIO_EXT = (".wav", ".m4a", ".mp3", ".aac")


def _run(cmd, timeout=120):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def sha256(path, block=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(block), b""):
            h.update(chunk)
    return h.hexdigest()


def probe(path):
    r = _run(["ffprobe", "-v", "error", "-show_entries",
              "format=duration,size,bit_rate,format_name:stream=index,codec_type,codec_name,width,height,r_frame_rate,avg_frame_rate,pix_fmt,sample_rate,channels:stream_tags=rotate:stream_side_data=rotation",
              "-of", "json", path])
    if r.returncode or not r.stdout.strip():
        return None
    try:
        return json.loads(r.stdout)
    except ValueError:
        return None


def _fps(s):
    try:
        a, b = (s or "0/1").split("/")
        return round(float(a) / float(b), 2) if float(b) else 0.0
    except (ValueError, ZeroDivisionError):
        return 0.0


def decodes(path, dur):
    """Really decode a few seconds at the start and at the end: catches files that probe fine but are cut off or damaged."""
    for extra in (["-t", "3"], ["-ss", str(max(0, dur - 3))]):
        r = _run(["ffmpeg", "-v", "error", *extra, "-i", path, "-f", "null", "-"], timeout=180)
        if r.returncode or r.stderr.strip():
            return False, (r.stderr.strip().splitlines() or ["decode error"])[-1][:160]
    return True, ""


def fingerprint(path, dur):
    """64-bit 'looks like' hash (difference hash of one frame at 30%). Equal or near-equal = the same footage."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{dur * 0.3:.2f}", "-i", path, "-frames:v", "1", "-vf", "scale=9:8,format=gray",
                        "-f", "rawvideo", "-"], capture_output=True, timeout=60)
    px = r.stdout
    if len(px) < 72:
        return None
    bits = 0
    for y in range(8):
        for x in range(8):
            bits = (bits << 1) | (1 if px[y * 9 + x] > px[y * 9 + x + 1] else 0)
    return f"{bits:016x}"


def hamming(a, b):
    return bin(int(a, 16) ^ int(b, 16)).count("1") if a and b else 64


def speech_ratio(path):
    """Share of the file that is not silence (a rough 'someone is talking' signal) and loudness."""
    r = _run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-vn", "-af", "silencedetect=noise=-35dB:d=0.4,ebur128", "-f", "null", "-"], timeout=300)
    dur = 0.0
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
    if m:
        dur = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
    sil = 0.0
    for d in re.findall(r"silence_duration: ([0-9.]+)", r.stderr):
        sil += float(d)
    lu = re.findall(r"I:\s+(-?[0-9.]+) LUFS", r.stderr)
    return (max(0.0, 1 - sil / dur) if dur else 0.0), (float(lu[-1]) if lu else None)


def classify(has_audio, speech):
    """A first guess, never a decision: talking-head / b-roll / mixed."""
    if not has_audio:
        return "b-roll", "no sound"
    if speech >= 0.55:
        return "talking-head", f"{round(speech * 100)}% speech"
    if speech <= 0.15:
        return "b-roll", "almost no speech"
    return "mixed", f"{round(speech * 100)}% speech"


def analyze(path, fast=False):
    """One file -> a dict with 'verdict': ok | warn | fail, plus 'issues' (plain words). Never raises."""
    name = os.path.basename(path)
    out = {"name": name, "source": os.path.abspath(path), "verdict": "ok", "issues": []}
    try:
        out["bytes"] = os.path.getsize(path)
        if out["bytes"] == 0:
            raise ValueError("the file is empty (0 bytes): upload it again")
        info = probe(path)
        if not info:
            raise ValueError("can't be read as a video or audio file (damaged, or not a media file)")
        streams = info.get("streams") or []
        v = next((s for s in streams if s.get("codec_type") == "video"), None)
        a = next((s for s in streams if s.get("codec_type") == "audio"), None)
        dur = float((info.get("format") or {}).get("duration") or 0)
        is_audio_only = bool(a) and not v and name.lower().endswith(AUDIO_EXT)
        if not v and not is_audio_only:
            raise ValueError("has no picture, so it can't be used as footage")
        if dur < MIN_SECONDS:
            raise ValueError(f"is only {dur:.1f} s long")
        out.update(duration=round(dur, 2), container=(info.get("format") or {}).get("format_name", ""), has_audio=bool(a),
                   audio_codec=(a or {}).get("codec_name"), kind="audio" if is_audio_only else "video")
        if v:
            w, h = int(v.get("width") or 0), int(v.get("height") or 0)
            rot = abs(int(float(((v.get("side_data_list") or [{}])[0] or {}).get("rotation", (v.get("tags") or {}).get("rotate", 0)) or 0))) % 180 == 90
            if rot:
                w, h = h, w
            fps = _fps(v.get("avg_frame_rate")) or _fps(v.get("r_frame_rate"))
            out.update(codec=v.get("codec_name"), width=w, height=h, fps=fps, orientation="vertical" if h >= w else "horizontal",
                       pix_fmt=v.get("pix_fmt"))
            if min(w, h) < MIN_SHORT_SIDE:
                out["issues"].append(f"low resolution ({w}×{h}): the picture will look soft")
            if w > h:
                out["issues"].append("filmed horizontally: reels are vertical (9:16), so the sides will be cropped")
            if fps and fps < 24:
                out["issues"].append(f"low frame rate ({fps:g} fps): motion may look choppy")
        ok, why = decodes(path, dur)
        if not ok:
            raise ValueError(f"is damaged or cut off ({why})")
        out["sha256"] = sha256(path)
        out["asset_id"] = "a_" + out["sha256"][:10]
        if v and not fast:
            out["fingerprint"] = fingerprint(path, dur)
        if not fast:
            sp, lufs = speech_ratio(path)
            out["speech_ratio"] = round(sp, 2); out["lufs"] = lufs
            out["role"], out["role_why"] = classify(bool(a), sp)
            if a and lufs is not None and lufs < -30:
                out["issues"].append(f"very quiet sound ({lufs:.0f} LUFS): get closer to the microphone next time")
        if not a and v:
            out["issues"].append("has no sound")
        if out["issues"]:
            out["verdict"] = "warn"
    except (ValueError, OSError, subprocess.SubprocessError) as e:
        out["verdict"] = "fail"; out["issues"].append(str(e))
    return out


def known_hashes(jobs_dir, skip_job=None):
    """sha256 -> reel name, from the manifests of earlier reels (so you hear 'already used in …')."""
    seen = {}
    for mp in glob.glob(os.path.join(jobs_dir, "*", "media_manifest.json")):
        job = os.path.basename(os.path.dirname(mp))
        if job == skip_job:
            continue
        try:
            for f in json.load(open(mp, encoding="utf-8")).get("files", []):
                if f.get("sha256") and f.get("verdict") != "fail":
                    seen.setdefault(f["sha256"], job)
        except (OSError, ValueError):
            pass
    return seen


def check_batch(paths, jobs_dir=None, skip_job=None, fast=False):
    """Check every file separately, then mark duplicates. Returns the manifest dict (nothing is raised for a bad file)."""
    files = [analyze(p, fast=fast) for p in paths]
    earlier = known_hashes(jobs_dir, skip_job) if jobs_dir else {}
    first = {}
    for f in files:
        if f["verdict"] == "fail":
            f["use"] = False
            continue
        f["use"] = True
        h = f.get("sha256")
        if h in first:
            f.update(use=False, duplicate_of=first[h]["name"], duplicate_kind="exact")
            f["issues"].append(f"exact copy of {first[h]['name']}: skipped so the same footage isn't processed twice")
            f["verdict"] = "warn"
            continue
        first[h] = f
        if h in earlier:
            f["issues"].append(f"you already used this exact file in reel {earlier[h]}")
            f["verdict"] = "warn"
    kept = [f for f in files if f.get("use") and f.get("fingerprint")]
    for i, a in enumerate(kept):
        for b in kept[i + 1:]:
            if hamming(a["fingerprint"], b["fingerprint"]) <= SIMILAR_BITS and abs(a.get("duration", 0) - b.get("duration", 0)) < 2.0:
                b["issues"].append(f"looks almost the same as {a['name']} (maybe a re-export): check you want both"); b["verdict"] = "warn"
                b["similar_to"] = a["name"]
    usable = [f for f in files if f.get("use")]
    return {"files": files, "summary": {"total": len(files), "used": len(usable), "failed": sum(f["verdict"] == "fail" for f in files),
                                        "duplicates": sum(1 for f in files if f.get("duplicate_of")),
                                        "warnings": sum(f["verdict"] == "warn" for f in files),
                                        "seconds": round(sum(f.get("duration", 0) for f in usable), 1)}}
