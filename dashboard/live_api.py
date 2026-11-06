"""Data for the 'watch it work' panel on the home page. Reads files the pipeline already wrote; calls no AI, spends nothing."""
import json, os

import reels_api

TRACKS = {                       # block -> (track, short Arabic name)
    "captions": ("caption", "كلمة بكلمة"),
    "hook_two_tone": ("card", "العنوان"), "text_card": ("card", "بطاقة نص"), "line_text": ("card", "سطر نص"), "info_card": ("card", "بطاقة نقاط"),
    "doc_card": ("card", "ورقة"), "ui_card": ("card", "بطاقة"), "tier_list": ("card", "ترتيب"), "recap_chain": ("card", "ملخص"),
    "before_after": ("card", "قبل وبعد"), "split": ("card", "شاشتين"), "name_tag": ("card", "اسم"), "cta_card": ("card", "الختام"),
    "number_graph": ("motion", "رقم يعدّ"), "motion_card": ("motion", "حركة"), "pixel_scene": ("motion", "مشهد"), "flash": ("motion", "ومضة"),
    "text_behind": ("motion", "نص ورا الراس"), "logo_card": ("motion", "شعار"),
}
CUT_WORDS = {"retake": "تكرار", "filler": "حشو", "pause": "صمت", "false_start": "بداية خاطئة", "ai": "قص ذكي"}


def _j(p, default=None):
    try:
        return json.load(open(p, encoding="utf-8"))
    except (OSError, ValueError):
        return default


def current_job():
    """The reel being made now, else the newest one that has a plan."""
    busy = list(reels_api.busy())
    for k in busy:
        if reels_api.JOB.match(k):
            return k
        j = reels_api._job_for_slug(k) if reels_api.SLUG.match(k) else None
        if j:
            return j
    if os.path.isdir(reels_api.JOBS):
        for n in sorted(os.listdir(reels_api.JOBS), reverse=True):
            if reels_api.JOB.match(n) and os.path.exists(os.path.join(reels_api.JOBS, n, "timeline.json")):
                return n
    return None


def live(job=None):
    job = job or current_job()
    if not job or not reels_api.JOB.match(job) or not os.path.isdir(os.path.join(reels_api.JOBS, job)):
        return {"job": None}
    jd = os.path.join(reels_api.JOBS, job)
    tl = _j(os.path.join(jd, "timeline.json"), {}) or {}
    edl = _j(os.path.join(jd, "edl.json"), {}) or {}
    segs = [{"a": s["t_in"], "b": s["t_out"]} for s in edl.get("segments", []) if "t_in" in s]
    cuts_log = edl.get("cut_log", []) or []
    cuts = [{"t": c.get("reel_t", 0), "kind": c.get("kind", ""), "name": CUT_WORDS.get(c.get("kind"), "قص")} for c in cuts_log]
    dur = float(tl.get("duration") or (segs[-1]["b"] if segs else 0) or 0)
    tracks = {"caption": [], "card": [], "motion": []}
    for s in tl.get("scenes", []):
        t = TRACKS.get(s.get("block"))
        if t:
            tracks[t[0]].append({"a": s["t_in"], "b": s["t_out"], "name": t[1], "block": s["block"]})
    kinds = {}
    for c in cuts:
        kinds[c["kind"]] = kinds.get(c["kind"], 0) + 1
    removed_s = round(sum(float(c.get("src_to", 0)) - float(c.get("src_from", 0)) for c in cuts_log), 1)
    prog = reels_api.progress(job)
    return {"job": job, "duration": dur, "segments": segs, "cuts": cuts, "tracks": tracks, "removed_s": removed_s, "cut_kinds": kinds,
            "running": bool(prog.get("running")), "state": prog.get("state"), "percent": prog.get("percent"),
            "message": prog.get("message"), "steps": prog.get("steps", []),
            "draft": prog.get("draft"), "draft_mtime": prog.get("draft_mtime")}
