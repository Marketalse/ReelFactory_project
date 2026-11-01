"""Reels API for the dashboard: list reels, start one, stream the draft, send comments, approve.
Runs scripts/reel.py in the background (one at a time) and never through a shell. Local only."""
import glob, json, os, re, subprocess, sys, threading, time

ROOT = os.environ.get("RF_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOBS, INBOX = os.path.join(ROOT, "jobs"), os.path.join(ROOT, "inbox")
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")
JOB = re.compile(r"^\d{4}-\d{2}-\d{2}-[a-z0-9][a-z0-9-]{1,40}$")
VIDEO = (".mov", ".mp4", ".m4v", ".avi", ".webm", ".mkv")
RUNS = os.path.join(ROOT, "dashboard", ".runs")      # output of each background run (shows why a run stopped early)
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
            os.makedirs(RUNS, exist_ok=True)
            with open(os.path.join(RUNS, key + ".log"), "w", encoding="utf-8") as out:
                subprocess.run([sys.executable, "-u", os.path.join(ROOT, "scripts", "reel.py")] + args, cwd=cwd,
                               stdout=out, stderr=subprocess.STDOUT)
        finally:
            with _lock:
                _running.pop(key, None)
    with _lock:
        if _running:
            return False, f"busy: {', '.join(_running)} is still running; one reel at a time"
        _running[key] = {"what": args, "started": time.time()}
    threading.Thread(target=work, daemon=True).start()
    return True, "started"


def _clips(d):
    cdir = os.path.join(d, "clips") if os.path.isdir(os.path.join(d, "clips")) else d
    return [f for f in os.listdir(cdir) if f.lower().endswith(VIDEO)] if os.path.isdir(cdir) else []


def start(slug):
    if not SLUG.match(slug or ""):
        return False, "folder name: lowercase letters, digits and dashes only"
    d = os.path.join(INBOX, slug)
    if not os.path.isdir(d):
        return False, f"no folder inbox/{slug}"
    if not _clips(d):
        return False, "this reel has no video yet: add your video first"
    if _job_for_slug(slug):
        return False, f"a reel called {slug} already exists today: choose another name"
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


# ----------------------------------------------------------------------------- upload page (make.html)
# Files are streamed straight into inbox/<slug>/ by the browser, one file per request. A random
# "session" id from the page claims a new folder, so two tabs (or an old folder) can never be mixed.
UPLOAD_KINDS = {                       # kind -> (sub-folder, allowed extensions, max bytes)
    "clip": ("clips", VIDEO, 20 << 30),
    "logo": ("assets", (".svg", ".png"), 50 << 20),
}
SESSION = re.compile(r"^[a-z0-9]{8,40}$")
MARK = ".upload_session"


def _safe_name(name):
    base = os.path.basename((name or "").replace("\\", "/"))
    stem, ext = os.path.splitext(base)
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-.")[:60] or "file"
    return stem + ext.lower()


def _job_for_slug(slug):
    if not os.path.isdir(JOBS):
        return None
    hits = sorted(n for n in os.listdir(JOBS) if JOB.match(n) and n[11:] == slug and os.path.isdir(os.path.join(JOBS, n)))
    return hits[-1] if hits else None


def _claim(slug, session):
    """The first upload of a page session creates inbox/<slug>/; a name used by anyone else is refused."""
    d = os.path.join(INBOX, slug)
    mark = os.path.join(d, MARK)
    if os.path.isdir(d) and os.listdir(d):
        try:
            if open(mark, encoding="utf-8").read().strip() == session:
                return True, d
        except OSError:
            pass
        return False, f"the name {slug} is already used by another reel: choose another name"
    os.makedirs(d, exist_ok=True)
    open(mark, "w", encoding="utf-8").write(session)
    return True, d


def upload(slug, kind, name, session, length, stream, order=0):
    """Save one uploaded file. Returns (ok, message_or_saved_name)."""
    if not SLUG.match(slug or ""):
        return False, "reel name: use letters, digits and dashes"
    if not SESSION.match(session or ""):
        return False, "reload the page and try again (missing upload session)"
    if kind not in UPLOAD_KINDS:
        return False, f"unknown file type {kind!r}"
    sub, exts, limit = UPLOAD_KINDS[kind]
    safe = _safe_name(name)
    if not safe.lower().endswith(exts):
        return False, f"{name}: this file type can't be used here (allowed: {', '.join(e[1:].upper() for e in exts)})"
    if not 0 < length <= limit:
        return False, f"{name}: file is empty or larger than {limit >> 20} MB"
    if slug in _running or _job_for_slug(slug):
        return False, f"a reel called {slug} already exists: choose another name"
    with _lock:
        ok, d = _claim(slug, session)
    if not ok:
        return False, d
    if kind == "clip" and order:
        safe = f"{int(order):02d}-{safe}"          # takes are joined in name order
    dest = os.path.join(d, sub); os.makedirs(dest, exist_ok=True)
    path = os.path.join(dest, safe); tmp = path + ".part"
    left = length
    with open(tmp, "wb") as f:
        while left > 0:
            chunk = stream.read(min(1 << 20, left))
            if not chunk:
                break
            f.write(chunk); left -= len(chunk)
    if left:
        os.remove(tmp)                              # our own partial temp file, never Hesham's footage
        return False, f"{name}: upload was interrupted, try again"
    os.replace(tmp, path)
    return True, safe


def check_name(slug, session):
    """Asked before any upload starts, so nobody uploads gigabytes only to be refused."""
    if not SLUG.match(slug or "") or not SESSION.match(session or ""):
        return False, "reel name: use letters, digits and dashes"
    if _running:
        return False, f"busy: {', '.join(_running)} is still being made; one reel at a time"
    if _job_for_slug(slug):
        return False, f"the name {slug} is already used by another reel: choose another name"
    d = os.path.join(INBOX, slug)
    if os.path.isdir(d) and os.listdir(d):
        try:
            if open(os.path.join(d, MARK), encoding="utf-8").read().strip() == session:
                return True, "ok"
        except OSError:
            pass
        return False, f"the name {slug} is already used by another reel: choose another name"
    return True, "ok"


def save_notes(slug, session, text):
    text = (text or "").strip()
    if len(text) > 4000:
        return False, "notes are too long (max 4000 characters)"
    if not SLUG.match(slug or "") or not SESSION.match(session or ""):
        return False, "reload the page and try again"
    with _lock:
        ok, d = _claim(slug, session)
    if not ok:
        return False, d
    open(os.path.join(d, "brief.md"), "w", encoding="utf-8").write(text + "\n")
    return True, "saved"


# ----------------------------------------------------------------------------- live progress
# The page shows 5 plain-language steps; each groups pipeline stages from scripts/reel.py.
STEPS = [
    ("prepare", "Preparing your video", "Joining your takes and making a working copy", ["ingest"]),
    ("listen", "Listening to your words", "Writing down every word with its timing, then fixing spellings", ["transcribe", "fix", "review"]),
    ("story", "Choosing the story and cutting", "Picking the strongest part and removing pauses and false starts", ["selects", "edl"]),
    ("plan", "Planning captions and visuals", "Placing captions, titles, cards and zooms on your words", ["keyframes", "shotlog", "plan", "compile"]),
    ("render", "Rendering and checking the draft", "Making the draft video and checking every frame", ["draft", "report"]),
]
FINAL_STEPS = [
    ("instagram", "Rendering the Instagram video", "High quality, with your Instagram handle"),
    ("tiktok", "Rendering the TikTok video", "High quality, with your TikTok handle"),
    ("capcut", "Making the CapCut files", "Your cut video and a see-through graphics layer"),
]
DEFAULT_SECS = {"ingest": 60, "transcribe": 270, "fix": 15, "review": 1, "selects": 20, "edl": 2, "keyframes": 15,
                "shotlog": 25, "plan": 25, "compile": 5, "draft": 300, "report": 2}
FINAL_SECS = {"instagram": 300, "tiktok": 300, "capcut": 420}
ORDER = [s for st in STEPS for s in st[3]]


def expected_secs():
    """Typical time per stage, learned from earlier reels (jobs/*/timing.json); defaults until there are some."""
    seen = {}
    if os.path.isdir(JOBS):
        for n in os.listdir(JOBS):
            t = _j(os.path.join(JOBS, n, "timing.json"), {}) or {}
            for k, v in t.items():
                if isinstance(v, (int, float)) and v > 1:
                    seen.setdefault(k, []).append(v)
    out = dict(DEFAULT_SECS)
    for k, v in seen.items():
        v = sorted(v); out[k] = v[len(v) // 2]
    return out


def _last_run(log):
    i = max((k for k, l in enumerate(log) if l.startswith("=====")), default=-1)
    return log[i:] if i >= 0 else []


def _stop_text(lines):
    crash = next((k for k in range(len(lines) - 1, -1, -1) if lines[k].startswith("CRASH")), None)
    if crash is not None:                     # a crash: the useful line is the error at the end of the traceback
        err = [l.strip() for l in lines[crash + 1:] if l.strip() and not l.startswith((" ", "Traceback", "TOTAL", "====="))]
        err = [l for l in err if re.match(r"^[A-Za-z_.]+(Error|Exception|Exit)\b|^\w+:", l)] or err
        if err:
            return "crash: " + err[-1][:300]
    for l in reversed(lines):
        if l.startswith(("STOP:", "CRASH", "RENDER STOPPED", "FAILED", "INGEST FAILED")) or l.startswith("ingest failed"):
            return l.replace("STOP:", "").strip()
    tail = [l for l in lines if l.strip()]
    return tail[-1].strip() if tail else ""


_seen = {}            # reel ref -> last time a tab that can show notifications asked for its progress


def mark_seen(*refs):
    for r in refs:
        if r:
            _seen[r] = time.time()


def watching(ref):
    return time.time() - _seen.get(ref or "", 0) < 15


def progress(ref):
    """Everything the page needs to draw the progress bar, for a job name or an inbox slug.
    state: running | ready | final | stopped | paused | missing."""
    now = time.time()
    job = ref if JOB.match(ref or "") and os.path.isdir(os.path.join(JOBS, ref)) else (_job_for_slug(ref) if SLUG.match(ref or "") else None)
    slug = job[11:] if job else ref
    key = job if job in _running else (slug if slug in _running else None)
    run = _running.get(key) if key else None
    mode = "final" if run and "--approve" in run["what"] else ("fix" if run and "--fix" in run["what"] else "draft")
    out = {"ref": ref, "job": job, "slug": slug, "running": bool(run), "mode": mode, "now": now}
    jd = os.path.join(JOBS, job) if job else None
    jj = _j(os.path.join(jd, "job.json"), {}) if jd else {}
    status = jj.get("status", "")
    log = _tail(os.path.join(jd, "run.log"), 400) if jd else []
    last = _last_run(log)
    out["last_mode"] = "final" if last and "--approve" in last[0] else ("fix" if last and "--fix" in last[0] else "draft")
    runlog = _tail(os.path.join(RUNS, (key or job or slug or "x") + ".log"), 40)
    if not job and not run:
        stop = _stop_text(_tail(os.path.join(RUNS, slug + ".log"), 40)) if slug else ""
        out.update(state="stopped" if stop else "missing", message=stop or "no reel with this name")
        return out
    started = run["started"] if run else now

    if mode == "final":
        steps, done_s = [], 0.0
        t0 = started
        files = {"instagram": "final/reel_v*_instagram.mp4", "tiktok": "final/reel_v*_tiktok.mp4", "capcut": "edit_package/2_graphics.mov"}
        import glob as _g
        for k, label, detail in FINAL_STEPS:
            hit = [p for p in _g.glob(os.path.join(jd, files[k])) if os.path.getmtime(p) >= started - 1]
            steps.append({"key": k, "label": label, "detail": detail, "state": "done" if hit else "waiting", "expected": FINAL_SECS[k]})
            if hit:
                t0 = max(t0, max(os.path.getmtime(p) for p in hit)); done_s += FINAL_SECS[k]
        cur = next((s for s in steps if s["state"] == "waiting"), None)
        total = sum(FINAL_SECS.values()); part = 0.0; eta = 0
        if cur:
            el = now - t0; cur["state"] = "active"; cur["elapsed"] = round(el)
            part = min(0.95, el / cur["expected"]); cur["fraction"] = round(part, 3)
            eta = max(10, cur["expected"] - el) + sum(s["expected"] for s in steps if s["state"] == "waiting")
        out.update(steps=steps, percent=round(100 * (done_s + part * (cur["expected"] if cur else 0)) / total, 1), eta=round(eta),
                   message=cur["label"] if cur else "Finishing")
    else:
        exp = expected_secs()
        stages = ORDER if mode == "draft" else ORDER[ORDER.index("plan"):]
        done = set()
        for l in last:
            m = re.match(r"^(\w+)\s+ok\s", l)
            if m:
                done.add(m.group(1))
        if not jd or not last:
            done = set()
        elif mode == "draft" or not run:
            done.add("ingest")
        if not run and status in ("preview_ready", "rendered"):
            done.update(ORDER)
        cur = next((s for s in stages if s not in done), None)
        stage_t0 = started
        tp = os.path.join(jd, "timing.json") if jd else ""
        if tp and os.path.exists(tp) and os.path.getmtime(tp) > started:
            stage_t0 = os.path.getmtime(tp)
        el = now - stage_t0
        part = min(0.95, el / max(1, exp.get(cur, 30))) if cur and run else 0.0
        total = sum(exp[s] for s in stages)
        donesum = sum(exp[s] for s in stages if s in done)
        eta = (max(10, exp.get(cur, 30) - el) + sum(exp[s] for s in stages if s not in done and s != cur)) if cur and run else 0
        steps = []
        for k, label, detail, group in STEPS:
            g = [s for s in group if s in stages]
            if not g:
                st = "done"
            elif all(s in done for s in g):
                st = "done"
            elif cur in g and run:
                st = "active"
            else:
                st = "waiting"
            item = {"key": k, "label": label, "detail": detail, "state": st, "expected": round(sum(exp[s] for s in g))}
            if st == "active":
                gd = sum(exp[s] for s in g if s in done) + part * exp.get(cur, 30)
                item["fraction"] = round(min(0.97, gd / max(1, item["expected"])), 3)
                item["elapsed"] = round(el)
                if k == "prepare":
                    m = [l for l in runlog if l.startswith("ingest ")]
                    if m:
                        item["note"] = "Take " + m[-1].split()[1].rstrip(":")
            steps.append(item)
        msg = next((s["label"] for s in steps if s["state"] == "active"), "")
        out.update(steps=steps, percent=round(100 * (donesum + part * exp.get(cur, 30)) / max(1, total), 1) if cur else 100.0,
                   eta=round(eta), message=msg)

    if run:
        out["state"] = "running"
        return out
    stop = _stop_text(last) if any(l.startswith(("STOP:", "CRASH")) for l in last) else ""
    if not stop and not job:
        stop = _stop_text(runlog)
    if status == "rendered" and not stop:
        finals = sorted(f for f in os.listdir(os.path.join(jd, "final")) if f.endswith(".mp4") and "QA_FAILED" not in f) if os.path.isdir(os.path.join(jd, "final")) else []
        latest = max([int(m) for f in finals for m in re.findall(r"reel_v(\d+)_", f)] or [0])
        out.update(state="final", percent=100.0, eta=0, message="Your videos are ready",
                   finals=[f for f in finals if f.startswith(f"reel_v{latest}_")],
                   package=[f for f in ("1_video.mp4", "2_graphics.mov", "captions_ar.srt") if os.path.exists(os.path.join(jd, "edit_package", f))])
    elif status == "preview_ready" and not stop:
        out.update(state="ready", percent=100.0, eta=0, message="Your draft is ready")
    elif stop:
        out.update(state="stopped", message=stop)
    else:
        out.update(state="paused", message="This reel was interrupted (the dashboard was closed?). Click Try again to continue.")
    if jd and os.path.exists(os.path.join(jd, "review", "draft_540p.mp4")):
        out["draft"] = f"{job}/review/draft_540p.mp4"
        out["draft_mtime"] = int(os.path.getmtime(os.path.join(jd, "review", "draft_540p.mp4")))
    out["feedback"] = jj.get("feedback_history", [])
    out["handles_set"] = _handles_set()
    return out


def _handles_set():
    b = _j(os.path.join(ROOT, "config", "brand.json"), {}) or {}
    h = b.get("handles") or {}
    return bool(h) and all(isinstance(v, str) and v.startswith("@") and "CONFIRM" not in v for v in h.values())


STAGE_WORDS = {"fix": "Fixing transcript words", "selects": "Choosing the story", "plan": "Planning the edit",
               "repair": "Repairing the plan", "shotlog": "Looking at the video", "committee": "Quality review"}


def spend(month=None):
    """This month's AI cost by step and by model (from jobs/*/cost.json), plus a month-end projection."""
    import calendar
    from datetime import date
    today = date.today(); month = month or today.isoformat()[:7]
    by_step, by_model, reels, total = {}, {}, set(), 0.0
    for p in glob.glob(os.path.join(ROOT, "jobs", month + "-*", "cost.json")):
        try:
            calls = json.load(open(p, encoding="utf-8")).get("calls") or []
        except (OSError, ValueError):
            continue
        for c in calls:
            amt = float(c.get("cost") or 0); total += amt
            st = str(c.get("stage", "?")).split(":")[0]
            step = STAGE_WORDS.get(st, st)
            by_step[step] = by_step.get(step, 0) + amt
            m = str(c.get("model", "?")).split("/")[-1]
            by_model[m] = by_model.get(m, 0) + amt
        if calls:
            reels.add(os.path.basename(os.path.dirname(p)))
    days = calendar.monthrange(int(month[:4]), int(month[5:7]))[1]
    elapsed = today.day if month == today.isoformat()[:7] else days
    rnd = lambda d: [{"name": k, "amount": round(v, 4)} for k, v in sorted(d.items(), key=lambda x: -x[1])]
    return {"month": month, "total": round(total, 4), "reels": len(reels),
            "per_reel": round(total / len(reels), 4) if reels else 0.0,
            "projection": round(total / max(1, elapsed) * days, 2), "by_step": rnd(by_step), "by_model": rnd(by_model)}
