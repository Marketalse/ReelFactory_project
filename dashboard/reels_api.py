"""Reels API for the dashboard: list reels, start one, stream the draft, send comments, approve.
Runs scripts/reel.py in the background (one at a time) and never through a shell. Local only."""
import json, os, re, subprocess, sys, threading, time

ROOT = os.environ.get("RF_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOBS, INBOX = os.path.join(ROOT, "jobs"), os.path.join(ROOT, "inbox")
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")
JOB = re.compile(r"^\d{4}-\d{2}-\d{2}-[a-z0-9][a-z0-9-]{1,40}$")
VIDEO = (".mov", ".mp4", ".m4v")
_lock = threading.Lock()
_running = {}          # job or slug -> {"what", "started"}

STATUS_LABEL = {
    "ingested": "working", "transcribed": "working", "transcript_fixed": "working", "transcript_reviewed": "working",
    "story_picked": "working", "cut": "working", "planned": "working", "built": "working",
    "preview_ready": "ready to review", "rendered": "final ready",
}


def _j(p, default=None):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return default


def _tail(p, n=12):
    try:
        return open(p, encoding="utf-8", errors="replace").read().splitlines()[-n:]
    except OSError:
        return []


def busy():
    return {k: v for k, v in _running.items()}


def list_reels():
    reels = []
    done_slugs = set()
    if os.path.isdir(JOBS):
        for name in sorted(os.listdir(JOBS), reverse=True):
            jd = os.path.join(JOBS, name)
            if not JOB.match(name) or not os.path.isdir(jd):
                continue
            job = _j(os.path.join(jd, "job.json"), {})
            log = _tail(os.path.join(jd, "run.log"))
            last_stop = next((l for l in reversed(log) if l.startswith(("STOP:", "CRASH"))), "")
            last_run = max((i for i, l in enumerate(log) if l.startswith("=====")), default=-1)
            stopped = bool(last_stop) and log.index(last_stop) > last_run
            st = job.get("status", "")
            state = "running" if name in _running else ("needs attention" if stopped else STATUS_LABEL.get(st, st or "new"))
            dr = _j(os.path.join(jd, "review", "draft.json"), {})
            cost = sum(c.get("cost", 0) for c in (_j(os.path.join(jd, "cost.json"), {}) or {}).get("calls", []))
            finals = sorted(f for f in os.listdir(os.path.join(jd, "final"))) if os.path.isdir(os.path.join(jd, "final")) else []
            pkg = [f for f in ("1_video.mp4", "2_graphics.mov", "captions_ar.srt") if os.path.exists(os.path.join(jd, "edit_package", f))]
            done_slugs.add(name[11:])
            reels.append({
                "job": name, "status": st, "state": state, "stop": last_stop if stopped else "",
                "has_draft": os.path.exists(os.path.join(jd, "review", "draft_540p.mp4")),
                "draft_mtime": int(os.path.getmtime(os.path.join(jd, "review", "draft_540p.mp4"))) if os.path.exists(os.path.join(jd, "review", "draft_540p.mp4")) else 0,
                "qa": (dr.get("qa") or {}).get("warnings", []), "cost": round(cost, 4),
                "length": ((dr.get("qa") or {}).get("metrics") or {}).get("duration"),
                "feedback": job.get("feedback_history", []), "finals": finals, "package": pkg, "log": log[-6:],
            })
    inbox = []
    if os.path.isdir(INBOX):
        for slug in sorted(os.listdir(INBOX)):
            d = os.path.join(INBOX, slug)
            if not os.path.isdir(d) or not SLUG.match(slug) or slug in done_slugs:
                continue
            cdir = os.path.join(d, "clips") if os.path.isdir(os.path.join(d, "clips")) else d
            clips = [f for f in os.listdir(cdir) if f.lower().endswith(VIDEO)]
            inbox.append({"slug": slug, "clips": len(clips), "running": slug in _running})
    return {"reels": reels, "inbox": inbox, "busy": list(_running)}


def _run(key, args, cwd=ROOT):
    def work():
        try:
            subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "reel.py")] + args, cwd=cwd,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        finally:
            with _lock:
                _running.pop(key, None)
    with _lock:
        if _running:
            return False, f"busy: {', '.join(_running)} is still running; one reel at a time"
        _running[key] = {"what": args, "started": time.time()}
    threading.Thread(target=work, daemon=True).start()
    return True, "started"


def start(slug):
    if not SLUG.match(slug or ""):
        return False, "folder name: lowercase letters, digits and dashes only"
    d = os.path.join(INBOX, slug)
    if not os.path.isdir(d):
        return False, f"no folder inbox/{slug}"
    return _run(slug, [d, "--slug", slug])


def resume(job):
    if not JOB.match(job or "") or not os.path.isdir(os.path.join(JOBS, job)):
        return False, "unknown reel"
    return _run(job, [os.path.join(JOBS, job)])


def fix(job, text):
    text = (text or "").strip()
    if not JOB.match(job or "") or not os.path.isdir(os.path.join(JOBS, job)):
        return False, "unknown reel"
    if not text:
        return False, "write what to change"
    if len(text) > 2000:
        return False, "comment too long (max 2000 characters)"
    return _run(job, [os.path.join(JOBS, job), "--fix", text])


def approve(job):
    if not JOB.match(job or "") or not os.path.exists(os.path.join(JOBS, job, "review", "draft_540p.mp4")):
        return False, "no draft to approve"
    return _run(job, [os.path.join(JOBS, job), "--approve"])


def media_path(rel):
    """Only drafts, contact sheets and finals inside jobs/ may be served."""
    m = re.match(r"^(\d{4}-\d{2}-\d{2}-[a-z0-9-]+)/(review/draft_540p\.mp4|review/contact_sheet\.jpg|final/[A-Za-z0-9_.-]+\.mp4"
                 r"|edit_package/(?:1_video\.mp4|2_graphics\.mov|captions_ar\.srt))$", rel or "")
    if not m:
        return None
    p = os.path.realpath(os.path.join(JOBS, rel))
    return p if p.startswith(os.path.realpath(JOBS) + os.sep) and os.path.isfile(p) else None


def reveal(job):
    """Open the reel's folder in Finder (macOS) so files can be dragged into CapCut."""
    if not JOB.match(job or "") or not os.path.isdir(os.path.join(JOBS, job)):
        return False, "unknown reel"
    target = os.path.join(JOBS, job, "edit_package") if os.path.isdir(os.path.join(JOBS, job, "edit_package")) else os.path.join(JOBS, job)
    try:
        subprocess.run(["open", target], capture_output=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return False, "could not open Finder here"
    return True, "opened in Finder"
