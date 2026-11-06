#!/usr/bin/env python3
"""Drop folder: put raw clips in one folder, drafts come out in another. Stdlib only. Never posts anything.

    python3 scripts/watch_folder.py            keep watching (Ctrl+C to stop)
    python3 scripts/watch_folder.py --once     process what is there now, then stop

Folder (default ~/Desktop/Reel Factory Drop, setting drop.path in config/local.json):
    Drop/        put your clips here. One video = one reel. A sub-folder of clips = one reel (joined in name order).
    Drop/Ready/  the finished drafts appear here (<name>.mp4), plus <name>.txt with a short plain note.
    Drop/Done/   your original clips are moved here after they are safely copied. Nothing is ever deleted.
A reel that fails is tried ONCE; then Ready/<name>_PROBLEM.txt says why, in plain words. No loops.
Status for the dashboard: ~/.reelfactory/drop_status.json
"""
import json, os, re, shutil, subprocess, sys, time, unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import config as cfg   # noqa: E402

ROOT = cfg.ROOT
INBOX = os.path.join(ROOT, "inbox")
JOBS = os.path.join(ROOT, "jobs")
VIDEO = (".mov", ".mp4", ".m4v", ".avi", ".webm", ".mkv")
STATE_DIR = os.path.expanduser("~/.reelfactory")
STATUS = os.path.join(STATE_DIR, "drop_status.json")
SKIP_DIRS = {"ready", "done"}
POLL = 5


def drop_path():
    p = (cfg.PROJECT.get("drop") or {}).get("path") or "~/Desktop/Reel Factory Drop"
    return os.path.expanduser(p)


def setup(drop):
    for sub in ("", "Ready", "Done"):
        os.makedirs(os.path.join(drop, sub), exist_ok=True)


def slugify(name, taken=()):
    """Folder-safe name for the reel (lowercase letters, digits, dashes). Arabic names get a numbered name."""
    base = os.path.splitext(name)[0]
    s = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:30].strip("-")
    if len(s) < 2:
        s = "reel"
    cand, n = s, 2
    while cand in taken or os.path.exists(os.path.join(INBOX, cand)) or find_job(cand):
        cand = f"{s}-{n}"; n += 1
    return cand


def _is_video(f):
    return f.lower().endswith(VIDEO) and not f.startswith(".")


def _size_now(path):
    if os.path.isdir(path):
        return sum(os.path.getsize(os.path.join(path, f)) for f in os.listdir(path) if os.path.isfile(os.path.join(path, f)))
    return os.path.getsize(path)


def items(drop):
    """What is waiting: a list of (kind, path). A video file, or a folder that holds videos."""
    out = []
    for name in sorted(os.listdir(drop)):
        p = os.path.join(drop, name)
        if name.startswith(".") or name.lower() in SKIP_DIRS:
            continue
        if os.path.isfile(p) and _is_video(name):
            out.append(("file", p))
        elif os.path.isdir(p) and any(_is_video(f) for f in os.listdir(p)):
            out.append(("folder", p))
    return out


def is_stable(path, wait=2.0, sleep=time.sleep):
    """True when the file stopped growing (a copy from a phone or card can take a while)."""
    try:
        a = _size_now(path); sleep(wait); b = _size_now(path)
    except OSError:
        return False
    return a == b and a > 0


def stage(kind, path, slug):
    """Copy the clip(s) into inbox/<slug>. Returns the inbox folder."""
    d = os.path.join(INBOX, slug)
    os.makedirs(d, exist_ok=True)
    if kind == "file":
        shutil.copy2(path, os.path.join(d, os.path.basename(path)))
    else:
        for f in sorted(os.listdir(path)):
            fp = os.path.join(path, f)
            if os.path.isfile(fp) and (_is_video(f) or f.lower() == "brief.md"):
                shutil.copy2(fp, os.path.join(d, f))
    return d


def archive(path, drop):
    """Move the original into Done/ (never delete)."""
    dest = os.path.join(drop, "Done", os.path.basename(path))
    n = 2
    while os.path.exists(dest):
        dest = os.path.join(drop, "Done", f"{n}-{os.path.basename(path)}"); n += 1
    shutil.move(path, dest)
    return dest


def find_job(slug):
    if not os.path.isdir(JOBS):
        return None
    hits = sorted(n for n in os.listdir(JOBS) if re.match(r"^\d{4}-\d{2}-\d{2}-" + re.escape(slug) + "$", n))
    return os.path.join(JOBS, hits[-1]) if hits else None


def plain_reason(job, log_text=""):
    """The last STOP/CRASH line from the run log, in one short line."""
    lines = []
    if job and os.path.exists(os.path.join(job, "run.log")):
        lines = open(os.path.join(job, "run.log"), encoding="utf-8", errors="replace").read().splitlines()
    lines += log_text.splitlines()
    for l in reversed(lines):
        if l.startswith(("STOP:", "CRASH")):
            return l[:300]
    return "It stopped before the draft was ready. Open the dashboard (Control page) to see the step."


def write_status(d):
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        d["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
        json.dump(d, open(STATUS, "w"), indent=1, ensure_ascii=False)
    except OSError:
        pass


def notify(text):
    if sys.platform == "darwin":
        try:
            subprocess.run(["osascript", "-e", f'display notification "{text}" with title "Reel Factory"'], timeout=10)
        except Exception:
            pass


def make_reel(inbox_dir, slug, runner=None):
    """Run the pipeline up to the draft. Returns (job_dir or None, error_text)."""
    cmd = [sys.executable, "-u", os.path.join(ROOT, "scripts", "reel.py"), inbox_dir, "--slug", slug]
    run = runner or (lambda c: subprocess.run(c, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True))
    r = run(cmd)
    out = getattr(r, "stdout", "") or ""
    job = find_job(slug)
    if job and os.path.exists(os.path.join(job, "review", "draft_540p.mp4")):
        return job, ""
    return job, plain_reason(job, out)


def deliver(job, name, drop):
    ready = os.path.join(drop, "Ready")
    src = os.path.join(job, "review", "draft_540p.mp4")
    dst = os.path.join(ready, name + ".mp4")
    shutil.copy2(src, dst)
    dr = {}
    try:
        dr = json.load(open(os.path.join(job, "review", "draft.json"), encoding="utf-8"))
    except Exception:
        pass
    warn = (dr.get("qa") or {}).get("warnings", [])
    note = [f"Draft of {name}. Watch it, then open the dashboard to approve or write what to change.",
            "Nothing was posted. You post it yourself.", ""]
    if warn:
        note += ["Things to check:"] + [f"- {w}" for w in warn[:6]]
    open(os.path.join(ready, name + ".txt"), "w", encoding="utf-8").write("\n".join(note) + "\n")
    return dst


def process(kind, path, drop, state, runner=None):
    name = os.path.splitext(os.path.basename(path))[0] if kind == "file" else os.path.basename(path)
    slug = slugify(os.path.basename(path), taken=set(state.get("slugs", [])))
    state.setdefault("slugs", []).append(slug)
    state["now"] = {"name": name, "slug": slug, "step": "copying"}
    write_status(state)
    inbox_dir = stage(kind, path, slug)
    archive(path, drop)                        # the originals are safe in Done/ and a copy is in inbox/
    state["now"]["step"] = "editing"
    write_status(state)
    job, err = make_reel(inbox_dir, slug, runner)
    if err:
        open(os.path.join(drop, "Ready", name + "_PROBLEM.txt"), "w", encoding="utf-8").write(
            f"{name} could not be finished.\n{err}\n\nYour clip is safe in the Done folder.\n"
            "Open the dashboard (Control page) and press Try again, or send Claude a screenshot.\n")
        state.setdefault("failed", []).append(name)
        notify(f"{name}: problem. See the Ready folder.")
    else:
        deliver(job, name, drop)
        state.setdefault("ready", []).append(name)
        notify(f"{name}: draft is ready.")
    state["now"] = None
    write_status(state)
    return not err


def run(once=False, runner=None, sleep=time.sleep, drop=None):
    drop = drop or drop_path()
    setup(drop)
    state = {"drop": drop, "ready": [], "failed": [], "slugs": [], "now": None}
    write_status(state)
    print(f"Drop folder: {drop}\nPut your clips in it. Drafts appear in {os.path.join(drop, 'Ready')}.")
    while True:
        did = False
        for kind, path in items(drop):
            if not is_stable(path, sleep=sleep):
                continue
            print(f"Making a reel from {os.path.basename(path)} ...")
            ok = process(kind, path, drop, state, runner)
            print("  draft ready" if ok else "  problem (see Ready folder)")
            did = True
        if once and not did:
            return state
        if not once:
            sleep(POLL)


if __name__ == "__main__":
    try:
        run(once="--once" in sys.argv)
    except KeyboardInterrupt:
        print("\nStopped.")
