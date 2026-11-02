"""Other versions of the same footage (T106). Free to prepare; the new reel costs about what the planning part of the first one cost.

The story step already proposes three candidate stories. A variation takes one of the OTHER candidates (it has its own length, style and
hooks) and makes a separate reel from it: a new job folder that shares the footage and everything already paid for (transcript, spelling
fixes, story candidates, speech facts), then runs the rest of the pipeline for that story. The first reel is never touched.
The cost is shown before anything starts and the normal money guard still applies.
"""
import json, os, re, shutil, time

FILES = ("transcript_asr.json", "transcript.json", "transcript_fix_meta.json", "transcript_review_meta.json", "transcript_asr_dropped.json",
         "selects.json", "speech_intel.json", "content_intel.json", "media_index.json", "media_manifest.json", "clip_map.json",
         "silences.txt", "loudness.txt", "audio16k.wav", "brief.md", "brief.json", "probe.json")
DIRS = ("assets", "cover", "thumbs")
PLANNING = ("shotlog", "plan", "repair")


def _jl(p, d=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return d


def chosen_id(job):
    c = _jl(os.path.join(job, "chosen_select.json"), {}) or {}
    return c.get("id")


def alternatives(job):
    """The candidate stories that were NOT used for this reel. [] when the story step had nothing else (e.g. a short take)."""
    sel = (_jl(os.path.join(job, "selects.json"), {}) or {}).get("selects", [])
    keep = chosen_id(job)
    return [{"id": s.get("id"), "label": s.get("label"), "style": s.get("style"), "score": s.get("score"), "range": s.get("range"),
             "seconds": round(s["range"][1] - s["range"][0]) if s.get("range") else None, "why": s.get("why")}
            for s in sel if s.get("id") and s.get("id") != keep and s.get("range") and s.get("label") != "the whole take"]


def estimate(job):
    """Dollars: what the planning steps of THIS reel cost (shot log + director + repairs); a small default when unknown."""
    calls = (_jl(os.path.join(job, "cost.json"), {}) or {}).get("calls", [])
    t = sum(c.get("cost", 0) for c in calls if c.get("stage") in PLANNING)
    return round(t if t > 0 else 0.05, 3)


def next_name(jobs_dir, job):
    date, slug = job[:10], re.sub(r"-alt\d+$", "", job[11:])[:30].strip("-")
    n = 1
    while os.path.exists(os.path.join(jobs_dir, f"{date}-{slug}-alt{n}")):
        n += 1
    return f"{date}-{slug}-alt{n}"


def prepare(jobs_dir, job, sel_id):
    """Create the new job folder for story sel_id. -> its name. Raises ValueError with a plain message."""
    src = os.path.join(jobs_dir, job)
    alt = next((a for a in alternatives(src) if a["id"] == sel_id), None)
    if not alt:
        raise ValueError("that version is not available")
    if not os.path.exists(os.path.join(src, "proxy.mp4")) or not os.path.exists(os.path.join(src, "transcript.json")):
        raise ValueError("the first reel has no footage or transcript yet")
    name = next_name(jobs_dir, job)
    dst = os.path.join(jobs_dir, name)
    os.makedirs(dst)
    try:
        try:
            os.link(os.path.join(src, "proxy.mp4"), os.path.join(dst, "proxy.mp4"))          # same file, no extra disk space
        except OSError:
            shutil.copy2(os.path.join(src, "proxy.mp4"), os.path.join(dst, "proxy.mp4"))
        for f in FILES:
            if os.path.exists(os.path.join(src, f)):
                shutil.copy2(os.path.join(src, f), os.path.join(dst, f))
        for d in DIRS:
            if os.path.isdir(os.path.join(src, d)):
                shutil.copytree(os.path.join(src, d), os.path.join(dst, d))
        j = _jl(os.path.join(src, "job.json"), {}) or {}
        j.update({"id": name, "status": "transcribed", "feedback_history": [], "output": "",
                  "variation_of": job, "created_variation": time.strftime("%Y-%m-%d %H:%M"),
                  "selects": [{"id": alt["id"], "range": alt["range"], "label": alt["label"] or "another version", "chosen": True}]})
        with open(os.path.join(dst, "job.json"), "w", encoding="utf-8") as f:
            json.dump(j, f, indent=1, ensure_ascii=False)
    except Exception:
        shutil.rmtree(dst, ignore_errors=True)                                                  # only the half-made folder created a moment ago
        raise
    return name
