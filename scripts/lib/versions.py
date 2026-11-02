"""Draft versions and the QA report. Free, local. Nothing is ever deleted.

Every draft that is made is kept as review/versions/v<N>.mp4 together with the plan files that produced it
(review/versions/v<N>/*), so Hesham can watch an earlier version and go back to it. "Going back" restores that plan and its
preview video; the final video is always made from the current plan, so approving after going back makes THAT version.
The QA report is plain words: what passed, what to look at.
"""
import json, os, shutil, time

SNAP = ("timeline.json", "edl.json", "scene_plan.json", "manual_edit.json", "visual_plan.json", "editorial.json", "validation.json")


def _jl(p, d=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return d


def _dir(job):
    return os.path.join(job, "review", "versions")


def listing(job):
    return _jl(os.path.join(_dir(job), "versions.json"), []) or []


def save(job, note=""):
    """Keep the draft that was just made as the next version. Returns its entry."""
    draft = os.path.join(job, "review", "draft_540p.mp4")
    if not os.path.exists(draft):
        return None
    rows = listing(job)
    n = 1 + max([r["n"] for r in rows] or [0])
    d = _dir(job)
    os.makedirs(os.path.join(d, f"v{n}"), exist_ok=True)
    shutil.copy2(draft, os.path.join(d, f"v{n}.mp4"))
    for f in SNAP:
        if os.path.exists(os.path.join(job, f)):
            shutil.copy2(os.path.join(job, f), os.path.join(d, f"v{n}", f))
    qa = _jl(os.path.join(job, "qa.json"), {}) or {}
    tl = _jl(os.path.join(job, "timeline.json"), {}) or {}
    if not note:
        hist = (_jl(os.path.join(job, "job.json"), {}) or {}).get("feedback_history") or []
        note = hist[-1].get("fix", "") if hist else "first draft"
    row = {"n": n, "time": time.strftime("%Y-%m-%d %H:%M"), "note": str(note)[:200], "errors": len(qa.get("errors", [])),
           "warnings": len(qa.get("warnings", [])), "seconds": tl.get("duration"), "scenes": len(tl.get("scenes", []))}
    rows.append(row)
    tmp = os.path.join(d, "versions.json.tmp")
    json.dump(rows, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, os.path.join(d, "versions.json"))
    return row


def restore(job, n):
    """Go back to version n: its plan files and its preview video become the current ones. -> (ok, message)"""
    rows = listing(job)
    if not any(r["n"] == n for r in rows):
        return False, f"there is no version {n}"
    src, mp4 = os.path.join(_dir(job), f"v{n}"), os.path.join(_dir(job), f"v{n}.mp4")
    if not os.path.isdir(src) or not os.path.exists(mp4):
        return False, f"version {n} is incomplete on disk"
    for f in SNAP:
        if os.path.exists(os.path.join(src, f)):
            shutil.copy2(os.path.join(src, f), os.path.join(job, f))
        elif os.path.exists(os.path.join(job, f)) and f == "manual_edit.json":
            shutil.move(os.path.join(job, f), os.path.join(job, f + f".before-v{n}"))      # that version had no manual edit: set it aside, don't delete
    shutil.copy2(mp4, os.path.join(job, "review", "draft_540p.mp4"))
    jp = os.path.join(job, "job.json")
    j = _jl(jp, {}) or {}
    j.setdefault("feedback_history", []).append({"time": time.strftime("%Y-%m-%d %H:%M"), "fix": f"(went back to version {n})"})
    json.dump(j, open(jp, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    return True, f"Version {n} is the current draft. Approve it to make its final video."


def summary(job):
    """{verdict, errors, warnings, notes, checked} for the dashboard, in plain words. None if there is no QA yet."""
    qa = _jl(os.path.join(job, "qa.json"))
    if qa is None:
        return None
    extra = []
    vp = _jl(os.path.join(job, "visual_plan.json"), {}) or {}
    extra += [f"Look: {c}" for c in vp.get("checks", [])]
    ed = _jl(os.path.join(job, "editorial.json"), {}) or {}
    extra += [f"Story: {c}" for c in ed.get("confidence_flags", [])]
    si = _jl(os.path.join(job, "speech_intel.json"), {}) or {}
    lw = si.get("low_confidence_words", [])
    if lw:
        extra.append("Words to check: " + ", ".join(f"{w['text']} ({w['t']}s)" for w in lw[:6]))
    errs, warns = qa.get("errors", []), qa.get("warnings", [])
    verdict = "Needs attention" if errs else "Passed with notes" if (warns or extra) else "Passed"
    man = _jl(os.path.join(job, "render_manifest_draft.json"), {}) or {}
    out = man.get("output", {})
    tech = f"{out.get('width')}x{out.get('height')} {out.get('codec')} {out.get('fps')} fps" if out.get("width") else ""
    return {"verdict": verdict, "errors": errs, "warnings": warns, "notes": extra[:12], "technical": tech,
            "metrics": {k: (qa.get("metrics") or {}).get(k) for k in ("duration", "lufs", "true_peak")}}


def write_report(job):
    s = summary(job)
    if not s:
        return None
    L = [f"# QA report - {os.path.basename(job)}", "", f"**Result: {s['verdict']}**", ""]
    if s["technical"]:
        L += [f"File: {s['technical']}, length {s['metrics'].get('duration')} s, loudness {s['metrics'].get('lufs')} LUFS", ""]
    L += ["## Must fix"] + [f"- {x}" for x in s["errors"]] if s["errors"] else ["## Must fix", "- nothing"]
    L += ["", "## Worth a look"] + ([f"- {x}" for x in s["warnings"] + s["notes"]] or ["- nothing"])
    p = os.path.join(job, "review", "qa_report.md")
    open(p, "w", encoding="utf-8").write("\n".join(L) + "\n")
    return p
