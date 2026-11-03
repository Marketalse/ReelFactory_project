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


# ----------------------------------------------------------------------------- Edit page (manual editing)
def _editor_job(job):
    if not JOB.match(job or "") or not os.path.isdir(os.path.join(JOBS, job)):
        return None, "unknown reel"
    if job in _running:
        return None, "this reel is being made right now; edit it when it's finished"
    if not os.path.exists(os.path.join(JOBS, job, "timeline.json")):
        return None, "this reel has no draft yet"
    return os.path.join(JOBS, job), ""


def editor(job, edit=None):
    """(ok, data|message) for the Edit page. With `edit`: an unsaved preview of that version."""
    jd, msg = _editor_job(job)
    if not jd:
        return False, msg
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    from lib import manual_edit as me
    try:
        data = me.state(jd, edit)
        if edit is None:
            data["waveform"] = me.waveform(jd)
            data["draft_mtime"] = int(os.path.getmtime(os.path.join(jd, "review", "draft_540p.mp4"))) if os.path.exists(os.path.join(jd, "review", "draft_540p.mp4")) else 0
        return True, data
    except me.EditError as e:
        return False, str(e)


def editor_save(job, edit):
    jd, msg = _editor_job(job)
    if not jd:
        return False, msg, []
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    from lib import manual_edit as me
    try:
        return me.save(jd, edit or {})
    except me.EditError as e:
        return False, str(e), []


def rebuild(job):
    jd, msg = _editor_job(job)
    if not jd:
        return False, msg
    if not os.path.exists(os.path.join(jd, "manual_edit.json")):
        return False, "save your edit first"
    return _run(job, [jd, "--rebuild"])


def _seq_job(job):
    if not JOB.match(job or "") or not os.path.isdir(os.path.join(JOBS, job)):
        return None, "unknown reel"
    if job in _running or _running:
        return None, "a reel is being made right now; use the timeline when it's finished"
    return os.path.join(JOBS, job), ""


def timeline(job):
    """(ok, data|message) for the timeline page (T81)."""
    if not JOB.match(job or "") or not os.path.isdir(os.path.join(JOBS, job)):
        return False, "unknown reel"
    jd = os.path.join(JOBS, job)
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    from lib import sequence
    if not sequence.clips(jd):
        return False, "this reel has no footage pieces yet: upload clips first"
    d = sequence.state(jd); d["job"] = job
    return True, d


def timeline_save(job, seq):
    jd, msg = _seq_job(job)
    if not jd:
        return False, msg, None
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    from lib import sequence
    return sequence.save(jd, seq or {})


def timeline_check(job, seq):
    """Check my cuts (T82): markers with plain reasons. Free."""
    jd, msg = _seq_job(job)
    if not jd:
        return False, msg
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    from lib import sequence
    clean, err = sequence.validate(jd, seq or sequence.load(jd))
    if err:
        return False, "; ".join(err[:2])
    return True, sequence.check_cuts(jd, clean)


def timeline_apply(job, seq):
    """Auto-edit (T83): save the sequence, then build the new footage and run the whole pipeline on it in the background."""
    jd, msg = _seq_job(job)
    if not jd:
        return False, msg
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    from lib import sequence
    ok, m, _ = sequence.save(jd, seq or {})
    if not ok:
        return False, m
    return _run(job, [jd, "--apply-sequence"])


def timeline_undo(job):
    jd, msg = _seq_job(job)
    if not jd:
        return False, msg
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    from lib import sequence
    return sequence.undo(jd)


def make_variation(job, sel_id):
    """Make another version of this reel from one of the other candidate stories (T106). Returns (ok, new job name | message)."""
    if not JOB.match(job or "") or not os.path.isdir(os.path.join(JOBS, job)):
        return False, "unknown reel"
    if _running:
        return False, f"busy: {', '.join(_running)} is still running; one reel at a time"
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    from lib import variations
    try:
        name = variations.prepare(JOBS, job, sel_id)
    except ValueError as e:
        return False, str(e)
    ok, msg = _run(name, [os.path.join(JOBS, name)])
    return (True, name) if ok else (False, msg)


def ask_doctor(job):
    """The user clicked "Ask the AI doctor": one cheap question about why the reel stopped. It only proposes (T84)."""
    if not JOB.match(job or "") or not os.path.isdir(os.path.join(JOBS, job)):
        return False, "unknown reel"
    if job in _running:
        return False, "this reel is being made right now"
    return _run(job + "-doctor", [os.path.join(JOBS, job), "--doctor"])


def use_hook(job, n):
    """Hook picker (T103): put one of the three hooks (his own words) on the opening title card, then rebuild the draft.
    Free: no AI. The words come from editorial.json and were checked to be in his transcript."""
    jd, msg = _editor_job(job)
    if not jd:
        return False, msg
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    from lib import manual_edit as me, director
    ed = _j(os.path.join(jd, "editorial.json"), {}) or {}
    try:
        h = [x for x in ed.get("hooks", []) if x.get("found")][int(n)]
    except (TypeError, ValueError, IndexError):
        return False, "that hook is not available"
    try:
        edit = me.current(jd)
        edit["hook"] = director.fix_hook({"line1": h["line"]}, [])
        ok, m, _notes = me.save(jd, edit)
    except me.EditError as e:
        return False, str(e)
    if not ok:
        return False, m
    return _run(job, [jd, "--rebuild"])


def use_version(job, n):
    """Go back to an earlier draft (its plan and preview become the current ones). Nothing is deleted."""
    jd, msg = _editor_job(job)
    if not jd:
        return False, msg
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    from lib import versions
    try:
        return versions.restore(jd, int(n))
    except (TypeError, ValueError):
        return False, "unknown version"


def approve(job):
    if not JOB.match(job or "") or not os.path.exists(os.path.join(JOBS, job, "review", "draft_540p.mp4")):
        return False, "no draft to approve"
    return _run(job, [os.path.join(JOBS, job), "--approve"])


def media_path(rel):
    """Only drafts, contact sheets and finals inside jobs/ may be served."""
    m = re.match(r"^(\d{4}-\d{2}-\d{2}-[a-z0-9-]+)/(review/draft_540p\.mp4|review/contact_sheet\.jpg|final/[A-Za-z0-9_.-]+\.mp4"
                 r"|review/versions/v\d+\.mp4|c\d\d/proxy\.mp4|thumbs/c\d\d_s\d\d\.jpg|proxy\.mp4|review/cover\.jpg|final/cover_v\d+\.jpg|edit_package/(?:1_video\.mp4|2_graphics\.mov|captions_ar\.srt))$", rel or "")
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
    "cover_photo": ("cover", (".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"), 40 << 20),
    "cover_own": ("cover", (".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"), 40 << 20),
}
COVER_EXT = (".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif")
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


def upload(slug, kind, name, session, length, stream, order=0, offset=0, total=None):
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
    total = int(total or (offset + length))
    if not 0 < total <= limit or length < 0 or offset < 0:
        return False, f"{name}: file is empty or larger than {limit >> 20} MB"
    if slug in _running or _job_for_slug(slug):
        return False, f"a reel called {slug} already exists: choose another name"
    with _lock:
        ok, d = _claim(slug, session)
    if not ok:
        return False, d
    if kind == "clip" and order:
        safe = f"{int(order):02d}-{safe}"          # takes are joined in name order
    if kind.startswith("cover_"):
        safe = ("photo" if kind == "cover_photo" else "own") + os.path.splitext(safe)[1]
        for e in COVER_EXT:                         # one photo / one own cover per reel
            old = os.path.join(d, sub, safe.rsplit(".", 1)[0] + e)
            if os.path.exists(old):
                os.remove(old)
    dest = os.path.join(d, sub); os.makedirs(dest, exist_ok=True)
    path = os.path.join(dest, safe); tmp = path + ".part"
    if offset:                                      # resuming: only continue exactly where the saved part ends
        have = os.path.getsize(tmp) if os.path.exists(tmp) else 0
        if have != offset:
            return False, f"resume:{have}"
    left = length
    with open(tmp, "ab" if offset else "wb") as f:
        while left > 0:
            chunk = stream.read(min(1 << 20, left))
            if not chunk:
                break
            f.write(chunk); left -= len(chunk)
    if left or offset + length != total:
        return False, f"{name}: upload was interrupted, resuming…"      # the saved part is kept so the next try continues from it
    os.replace(tmp, path)
    return True, safe


def upload_status(slug, kind, name, session, order=0):
    """How many bytes of this file are already saved (for resuming an interrupted upload). Reads only."""
    if not SLUG.match(slug or "") or not SESSION.match(session or "") or kind not in UPLOAD_KINDS:
        return {"bytes": 0}
    sub, exts, limit = UPLOAD_KINDS[kind]
    safe = _safe_name(name)
    if kind == "clip" and order:
        safe = f"{int(order):02d}-{safe}"
    d = os.path.join(INBOX, slug)
    try:
        if open(os.path.join(d, MARK), encoding="utf-8").read().strip() != session:
            return {"bytes": 0}
    except OSError:
        return {"bytes": 0}
    part = os.path.join(d, sub, safe + ".part")
    return {"bytes": os.path.getsize(part) if os.path.exists(part) else 0, "done": os.path.exists(os.path.join(d, sub, safe))}


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


def save_notes(slug, session, text, brief=None):
    text = (text or "").strip()
    if len(text) > 4000:
        return False, "notes are too long (max 4000 characters)"
    if not SLUG.match(slug or "") or not SESSION.match(session or ""):
        return False, "reload the page and try again"
    with _lock:
        ok, d = _claim(slug, session)
    if not ok:
        return False, d
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    from lib import creative_brief
    creative_brief.save(d, brief, text)                  # notes + the structured creative brief (goal, audience, style, length, action)
    return True, "saved"


# ----------------------------------------------------------------------------- live progress
# The page shows 5 plain-language steps; each groups pipeline stages from scripts/reel.py.
STEPS = [
    ("prepare", "Preparing your video", "Joining your takes and making a working copy", ["ingest"]),
    ("listen", "Listening to your words", "Writing down every word with its timing, then fixing spellings", ["transcribe", "fix", "review"]),
    ("story", "Choosing the story and cutting", "Picking the strongest part and removing pauses and false starts", ["selects", "tighten", "edl", "outline"]),
    ("plan", "Planning captions and visuals", "Placing captions, titles, cards and zooms on your words", ["keyframes", "shotlog", "plan", "compile"]),
    ("render", "Rendering and checking the draft", "Making the draft video and checking every frame", ["draft", "critic", "report"]),
]
FINAL_STEPS = [
    ("video", "Making your final video", "High quality, one video for Instagram and TikTok"),
    ("cover", "Making your cover image", "A suggestion; you can upload your own after"),
]
DEFAULT_SECS = {"ingest": 60, "transcribe": 270, "fix": 15, "review": 1, "selects": 20, "tighten": 20, "edl": 2, "outline": 25, "keyframes": 15,
                "shotlog": 25, "plan": 25, "compile": 5, "draft": 300, "critic": 15, "report": 2}
FINAL_SECS = {"video": 300, "cover": 40}
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
    mode = "final" if run and "--approve" in run["what"] else ("fix" if run and ("--fix" in run["what"] or "--rebuild" in run["what"]) else "draft")
    out = {"ref": ref, "job": job, "slug": slug, "running": bool(run), "mode": mode, "now": now}
    jd = os.path.join(JOBS, job) if job else None
    jj = _j(os.path.join(jd, "job.json"), {}) if jd else {}
    status = jj.get("status", "")
    man = _j(os.path.join(jd, "media_manifest.json")) if jd else None
    if man:
        out["media"] = {"summary": man.get("summary", {}), "files": [{k: f.get(k) for k in (
            "name", "verdict", "use", "duration", "width", "height", "fps", "role", "issues", "duplicate_of", "asset_id", "bytes")}
            for f in man.get("files", [])]}
    log = _tail(os.path.join(jd, "run.log"), 400) if jd else []
    last = _last_run(log)
    out["last_mode"] = "final" if last and "--approve" in last[0] else ("fix" if last and ("--fix" in last[0] or "--rebuild" in last[0]) else "draft")
    runlog = _tail(os.path.join(RUNS, (key or job or slug or "x") + ".log"), 40)
    if not job and not run:
        stop = _stop_text(_tail(os.path.join(RUNS, slug + ".log"), 40)) if slug else ""
        out.update(state="stopped" if stop else "missing", message=stop or "no reel with this name")
        return out
    started = run["started"] if run else now

    if mode == "final":
        steps, done_s = [], 0.0
        t0 = started
        files = {"video": "final/reel_v*.mp4", "cover": "review/cover.jpg"}
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
        latest = max([int(m) for f in finals for m in re.findall(r"reel_v(\d+)", f)] or [0])
        out.update(state="final", percent=100.0, eta=0, message="Your video is ready", version=latest,
                   finals=[f for f in finals if re.match(rf"reel_v{latest}(?:_|\.)", f)])
    elif status == "preview_ready" and not stop:
        out.update(state="ready", percent=100.0, eta=0, message="Your draft is ready")
    elif stop:
        out.update(state="stopped", message=stop)
    else:
        out.update(state="paused", message="This reel was interrupted (the dashboard was closed?). Click Try again to continue.")
    cp = os.path.join(jd, "review", "cover.jpg") if jd else ""
    if cp and os.path.exists(cp):
        out["cover"] = f"{job}/review/cover.jpg"; out["cover_mtime"] = int(os.path.getmtime(cp))
        out["cover_own"] = any(os.path.exists(os.path.join(jd, "cover", n + e)) for n in ("own", "photo") for e in COVER_EXT)
    if job in _covering:
        out["cover_busy"] = True
    if jd and os.path.exists(os.path.join(jd, "review", "draft_540p.mp4")):
        out["draft"] = f"{job}/review/draft_540p.mp4"
        out["draft_mtime"] = int(os.path.getmtime(os.path.join(jd, "review", "draft_540p.mp4")))
    out["feedback"] = jj.get("feedback_history", [])
    if jd:
        out["posted"] = (_j(os.path.join(jd, "performance.json"), {}) or {}).get("posted", [])
    if jd and out.get("state") in ("stopped", "paused"):
        try:
            sys.path.insert(0, os.path.join(ROOT, "scripts"))
            from lib import doctor
            out["doctor"] = {"known": doctor.known(out.get("message")), "ai": doctor.load(jd)}
        except Exception:                           # noqa: BLE001
            pass
    if jd and out.get("state") in ("ready", "final"):
        try:
            sys.path.insert(0, os.path.join(ROOT, "scripts"))
            from lib import versions
            out["qa"] = versions.summary(jd); out["versions"] = versions.listing(jd)
            out["critic"] = _j(os.path.join(jd, "review", "critic.json"), None)      # T134: the AI's look at the draft
            from lib import variations
            out["alternatives"] = variations.alternatives(jd); out["variation_cost"] = variations.estimate(jd)
            ed = _j(os.path.join(jd, "editorial.json"), {}) or {}
            out["hooks"] = [{"type": h.get("type"), "line": h.get("line")} for h in ed.get("hooks", []) if h.get("found")]
            out["hook_now"] = ed.get("hook_on_screen") or (_j(os.path.join(jd, "scene_plan.json"), {}) or {}).get("hook")
        except Exception:                           # noqa: BLE001
            pass
    out["handles_set"] = _handles_set()
    if jd and out.get("state") in ("ready", "final"):
        out["ready_score"] = ready_score(job)
    return out


def ready_score(job):
    """The reel's ready-to-post score; made again when the draft, final or cover is newer than it."""
    jd = os.path.join(JOBS, job)
    p = os.path.join(jd, "ready_score.json")
    srcs = [os.path.join(jd, f) for f in ("qa.json", "qa_final.json", "timeline.json", "review/cover.jpg")]
    newest = max([os.path.getmtime(f) for f in srcs if os.path.exists(f)] or [0])
    if not os.path.exists(p) or os.path.getmtime(p) < newest:
        try:
            sys.path.insert(0, os.path.join(ROOT, "scripts"))
            import ready_score as rs
            final = (_j(os.path.join(jd, "job.json"), {}) or {}).get("status") == "rendered"
            return rs.score(jd, final)
        except Exception:                   # noqa: BLE001
            return None
    return _j(p)


def _handles_set():
    """Handles only matter when the end card is on (config/brand.json -> cta.enabled)."""
    b = _j(os.path.join(ROOT, "config", "brand.json"), {}) or {}
    if (b.get("cta") or {}).get("enabled", True) is False:
        return True
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


# ----------------------------------------------------------------------------- cover image
_covering = set()


def _remake_cover(job):
    def work():
        try:
            subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "cover.py"), os.path.join(JOBS, job)],
                           cwd=ROOT, capture_output=True, text=True, timeout=600)
        finally:
            _covering.discard(job)
    _covering.add(job)
    threading.Thread(target=work, daemon=True).start()


def cover_upload(job, kind, name, length, stream):
    """After the draft: Hesham's own photo (kind 'photo') or whole cover (kind 'own'), then the cover is made again."""
    if not JOB.match(job or "") or not os.path.isdir(os.path.join(JOBS, job)):
        return False, "unknown reel"
    if kind not in ("photo", "own"):
        return False, "unknown cover type"
    ext = os.path.splitext(_safe_name(name))[1]
    if ext not in COVER_EXT:
        return False, f"{name}: use a JPG, PNG, WebP or iPhone (HEIC) photo"
    if not 0 < length <= 40 << 20:
        return False, f"{name}: image is empty or larger than 40 MB"
    d = os.path.join(JOBS, job, "cover"); os.makedirs(d, exist_ok=True)
    tmp = os.path.join(d, ".upload.part"); left = length
    with open(tmp, "wb") as f:
        while left > 0:
            chunk = stream.read(min(1 << 20, left))
            if not chunk:
                break
            f.write(chunk); left -= len(chunk)
    if left:
        os.remove(tmp)
        return False, f"{name}: upload was interrupted, try again"
    for n in ("photo", "own"):                      # the new choice replaces both earlier ones
        for e in COVER_EXT:
            p = os.path.join(d, n + e)
            if os.path.exists(p):
                os.remove(p)
    os.replace(tmp, os.path.join(d, kind + ext))
    _remake_cover(job)
    return True, "Making your cover…"


def cover_reset(job):
    """Back to the automatic cover (a frame from the video)."""
    if not JOB.match(job or "") or not os.path.isdir(os.path.join(JOBS, job)):
        return False, "unknown reel"
    for n in ("photo", "own"):
        for e in COVER_EXT:
            p = os.path.join(JOBS, job, "cover", n + e)
            if os.path.exists(p):
                os.remove(p)
    _remake_cover(job)
    return True, "Making the automatic cover…"


# ----------------------------------------------------------------------------- performance (how a posted reel did)
PERF_FIELDS = {          # key -> (label, max)
    "views": ("Views", 10**10), "avg_watch_s": ("Average watch time (s)", 3600), "full_pct": ("Watched to the end (%)", 100),
    "likes": ("Likes", 10**9), "comments": ("Comments", 10**9), "shares": ("Shares", 10**9), "saves": ("Saves", 10**9),
    "follows": ("New follows", 10**9),
}
PLATFORMS = ("instagram", "tiktok")
WHEN = ("48h", "7d", "30d")


def save_performance(job, data):
    """Hesham types the numbers from Instagram/TikTok Insights. Kept per reel in jobs/<job>/performance.json."""
    if not JOB.match(job or "") or not os.path.isdir(os.path.join(JOBS, job)):
        return False, "unknown reel"
    data = data or {}
    platform, when = data.get("platform"), data.get("when")
    if platform not in PLATFORMS:
        return False, "choose Instagram or TikTok"
    if when not in WHEN:
        return False, "choose when you checked (2 days, 7 days or 30 days after posting)"
    entry = {"platform": platform, "when": when, "saved": time.strftime("%Y-%m-%d %H:%M")}
    for k, (label, hi) in PERF_FIELDS.items():
        v = data.get(k)
        if v in (None, ""):
            continue
        try:
            v = float(str(v).replace(",", "").strip())
        except ValueError:
            return False, f"{label}: type a number"
        if not 0 <= v <= hi:
            return False, f"{label}: that number looks wrong"
        entry[k] = int(v) if k not in ("avg_watch_s", "full_pct") else round(v, 1)
    if "views" not in entry:
        return False, "Views is needed"
    p = os.path.join(JOBS, job, "performance.json")
    d = _j(p, {"entries": []})
    d["entries"] = [e for e in d.get("entries", []) if (e.get("platform"), e.get("when")) != (platform, when)] + [entry]
    tmp = p + ".tmp"
    json.dump(d, open(tmp, "w", encoding="utf-8"), indent=1); os.replace(tmp, p)
    try:                                              # re-learn from all results (T76); never blocks saving
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        from lib import learning
        learning.update(performance())
    except Exception:                                 # noqa: BLE001
        pass
    return True, "Saved. Thanks: every result teaches Reel Factory what works."


def save_posted(job, platform):
    """He tells us he posted the reel (T126): the results box only makes sense after that. Kept per platform in performance.json."""
    if not JOB.match(job or "") or not os.path.isdir(os.path.join(JOBS, job)):
        return False, "unknown reel"
    if platform not in PLATFORMS:
        return False, "choose Instagram or TikTok"
    p = os.path.join(JOBS, job, "performance.json")
    d = _j(p, {"entries": []}) or {"entries": []}
    posted = [x for x in d.get("posted", []) if x.get("platform") != platform]
    posted.append({"platform": platform, "at": time.strftime("%Y-%m-%d %H:%M"), "ts": int(time.time())})
    d["posted"] = posted
    tmp = p + ".tmp"
    json.dump(d, open(tmp, "w", encoding="utf-8"), indent=1); os.replace(tmp, p)
    return True, "Saved. Come back in 2 days to type the numbers from Insights."


def edit_facts(job):
    """What the edit was (for learning later): length, hook, moments, zooms, captions."""
    jd = os.path.join(JOBS, job)
    tl = _j(os.path.join(jd, "timeline.json"), {})
    scenes = tl.get("scenes", [])
    hook = next((s.get("values", {}) for s in scenes if s.get("block") == "hook_two_tone"), {})
    kinds = {}
    for s in scenes:
        if s.get("block") not in ("hook_two_tone", "captions", "cta_card"):
            kinds[s["block"]] = kinds.get(s["block"], 0) + 1
    zooms = len(tl.get("punch_ins") or []) or sum(1 for f in tl.get("frames", []) if isinstance(f, (list, tuple)) and len(f) > 1 and f[1] and f[1] > 1.01)
    dur = tl.get("duration") or 0
    return {"length_s": round(dur, 1), "hook": " / ".join(x for x in (hook.get("line1"), hook.get("line2")) if x),
            "hook_chars": len((hook.get("line1") or "") + (hook.get("line2") or "")),
            "moments": sum(kinds.values()), "moment_kinds": kinds, "zooms": zooms,
            "own_cover": any(os.path.exists(os.path.join(jd, "cover", n + e)) for n in ("photo", "own") for e in COVER_EXT),
            "ready_score": (_j(os.path.join(jd, "ready_score.json"), {}) or {}).get("score")}


def performance(job=None):
    """All reels with results (or one): edit facts + entries + simple rates. Used by the Results page and the CSV."""
    out = []
    names = [job] if job else (sorted(n for n in os.listdir(JOBS) if JOB.match(n)) if os.path.isdir(JOBS) else [])
    for n in names:
        if not JOB.match(n or "") or not os.path.isdir(os.path.join(JOBS, n)):
            continue
        d = _j(os.path.join(JOBS, n, "performance.json"), {"entries": []})
        st = (_j(os.path.join(JOBS, n, "job.json"), {}) or {}).get("status")
        if not d.get("entries") and st != "rendered" and not job:
            continue
        facts = edit_facts(n)
        rows = []
        for e in d.get("entries", []):
            e = dict(e); v = e.get("views") or 0
            if v:
                for k in ("likes", "comments", "shares", "saves", "follows"):
                    if k in e:
                        e[k + "_per_1k"] = round(1000 * e[k] / v, 1)
            if facts["length_s"] and e.get("avg_watch_s") is not None:
                e["watch_pct"] = round(min(100, 100 * e["avg_watch_s"] / facts["length_s"]), 1)
            rows.append(e)
        out.append({"job": n, "status": st, "facts": facts, "entries": rows})
    return out


def performance_csv():
    cols = ["job", "platform", "when", "views", "avg_watch_s", "watch_pct", "full_pct", "likes", "comments", "shares", "saves",
            "follows", "saves_per_1k", "shares_per_1k", "length_s", "hook_chars", "moments", "zooms", "own_cover", "ready_score", "hook"]
    lines = [",".join(cols)]
    for r in performance():
        for e in r["entries"]:
            row = dict(r["facts"], **e, job=r["job"])
            lines.append(",".join('"' + str(row.get(c, "")).replace('"', "'") + '"' if c == "hook" else str(row.get(c, "")) for c in cols))
    return "\n".join(lines) + "\n"
