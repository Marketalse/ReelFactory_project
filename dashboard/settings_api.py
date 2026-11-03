"""Settings page backend: health checks and saving the API key. Never returns or logs the key."""
import json, os, platform, shutil, subprocess, sys, time, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))
from lib import config as cfg  # noqa: E402

MIN_KEY, MAX_KEY = 20, 400


def _tool(name):
    p = shutil.which(name)
    if not p:
        return None
    try:
        v = subprocess.run([p, "--version" if name != "ffmpeg" else "-version"], capture_output=True, text=True, timeout=10)
        first = (v.stdout or v.stderr).strip().splitlines()[0] if (v.stdout or v.stderr).strip() else ""
    except Exception:
        first = ""
    return {"path": p, "version": first[:80]}


def health():
    """A list of plain-language checks: {key, label, ok, detail}. Problems say what to do."""
    out = []
    src = cfg.key_source()
    out.append({"key": "api_key", "label": "AI key", "ok": not src.startswith("no key"),
                "detail": "saved" if not src.startswith("no key") else "not saved yet: paste your Nous key below"})
    for name, label, fix in (("ffmpeg", "Video tool (FFmpeg)", "missing: install with 'brew install ffmpeg'"),
                             ("ffprobe", "Video reader (FFprobe)", "missing: comes with FFmpeg"),
                             ("node", "Node.js (for the video maker)", "missing: install Node.js from nodejs.org"),
                             ("npx", "npx (for the video maker)", "missing: comes with Node.js")):
        t = _tool(name)
        hermes = bool(t and ".hermes" in t["path"])
        out.append({"key": name, "label": label, "ok": bool(t) and not hermes,
                    "detail": fix if not t else ("still inside the old Hermes folder" if hermes else "ready")})
    out.append({"key": "python", "label": "Python", "ok": sys.version_info >= (3, 9), "detail": platform.python_version()})
    try:
        free = shutil.disk_usage(cfg.ROOT).free / 1e9
        out.append({"key": "disk", "label": "Free disk space", "ok": free >= 10, "detail": f"{free:.0f} GB free" + ("" if free >= 10 else ": free up space (each reel needs a few GB)")})
    except OSError:
        pass
    return {"checks": out, "all_ok": all(c["ok"] for c in out)}


def save_key(key):
    key = key.strip() if isinstance(key, str) else ""
    if any(c.isspace() for c in key) or not (MIN_KEY <= len(key) <= MAX_KEY):
        return False, "That doesn't look like an API key. Copy it again from portal.nousresearch.com and paste only the key."
    path = cfg.key_file()
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(key)
    os.replace(tmp, path); os.chmod(path, 0o600)
    ok, msg = test_key()
    return True, "Key saved. " + msg


def test_key(opener=urllib.request.urlopen):
    """Ask the AI service whether the key works (lists models: costs nothing)."""
    try:
        base, key = cfg.auth()
    except SystemExit as e:
        return False, str(e)
    req = urllib.request.Request(base.rstrip("/") + "/models", headers={"Authorization": "Bearer " + key})
    try:
        with opener(req, timeout=20) as r:
            r.read(1)
        return True, "It works."
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return False, "The AI service refused this key: check it on portal.nousresearch.com (and that you have credit)."
        return False, f"The AI service answered with an error ({e.code}). Try again in a minute."
    except Exception:
        return False, "Couldn't reach the AI service. Check your internet connection."


ROOT = os.path.dirname(HERE)


def _git(*args, timeout=60):
    return subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True, timeout=timeout)


def version():
    """Which version is running, and whether it auto-starts. No network."""
    head = _git("rev-parse", "--short", "HEAD").stdout.strip()
    branch = _git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    agent = os.path.expanduser("~/Library/LaunchAgents/com.reelfactory.dashboard.plist")
    return {"version": head or "unknown", "branch": branch, "autostart": os.path.exists(agent), "git": bool(head)}


def update_ready():
    """Is a newer version waiting on GitHub? (Looks only; changes nothing.)"""
    try:
        if not _git("rev-parse", "--is-inside-work-tree").stdout.strip():
            return False
        _git("fetch", "--quiet", timeout=30)
        n = _git("rev-list", "--count", "HEAD..@{u}")
        return n.returncode == 0 and int(n.stdout.strip() or 0) > 0
    except Exception:                                          # noqa: BLE001 - offline etc.: just say no
        return False


BOARD = "dashboard/tasks.json"


def _changed():
    """Tracked files changed on this Mac (the task board is edited by the dashboard itself)."""
    r = _git("status", "--porcelain", "--untracked-files=no")
    return [l[3:].strip().strip('"') for l in r.stdout.splitlines() if l.strip()]


def _names_after(stderr, marker):
    """File names git lists (one per indented line) after a message containing `marker`."""
    out, on = [], False
    for l in stderr.splitlines():
        if marker in l:
            on = True; continue
        if on:
            if l[:1] in ("\t", " ") and l.strip():
                out.append(l.strip())
            else:
                on = False
    return out


def _move_aside(names):
    """Move files that are in the way of an update into ~/.reelfactory/update-backup/<time>/ (never deleted). Returns the names moved."""
    keep = os.path.join(os.path.expanduser("~/.reelfactory/update-backup"), time.strftime("%Y%m%d-%H%M%S"))
    moved = []
    for n in names:
        src = os.path.normpath(os.path.join(ROOT, n))
        if n.startswith(("/", "..")) or ".." in n.split("/") or not src.startswith(os.path.normpath(ROOT) + os.sep) or not os.path.exists(src):
            continue
        dst = os.path.join(keep, n); os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(src, dst); moved.append(n)
    return moved


def update(busy):
    """Get the latest version from GitHub. Returns (ok, message, restart_needed).
    Your own task-board changes are kept (three-way merge); any other changed file stops the update and is named."""
    if busy:
        return False, "A reel is being made right now. Update when it's finished.", False
    if not _git("rev-parse", "--is-inside-work-tree").stdout.strip():
        return False, "This copy isn't linked to GitHub (a ZIP download?), so it can't update itself.", False
    before = _git("rev-parse", "HEAD").stdout.strip()
    changed = _changed()
    other = [f for f in changed if f != BOARD]
    if other:
        return False, "Couldn't update: these files were changed on this Mac: " + ", ".join(other[:5]) + ". Send this message to Claude.", False
    mine = None
    if BOARD in changed:                          # keep your board changes: save them, update, then merge them back
        try:
            from lib import board_merge
            base = json.loads(_git("show", f"HEAD:{BOARD}").stdout)
            mine = board_merge.load_file(os.path.join(ROOT, BOARD))
            keep = os.path.expanduser("~/.reelfactory/update-backup"); os.makedirs(keep, exist_ok=True)
            board_merge.save_file(os.path.join(keep, "tasks-" + time.strftime("%Y%m%d-%H%M%S") + ".json"), mine)
        except Exception:                         # noqa: BLE001
            return False, "Couldn't read your task board to keep your changes. Send this message to Claude.", False
        _git("checkout", "--", BOARD)
    r = _git("pull", "--ff-only", "--quiet", timeout=120)
    if r.returncode and "untracked working tree files would be overwritten" in r.stderr:
        moved = _move_aside(_names_after(r.stderr, "untracked working tree files would be overwritten"))   # kept in a backup, not deleted
        if moved:
            r = _git("pull", "--ff-only", "--quiet", timeout=120)
    if r.returncode:
        if mine is not None:
            board_merge.save_file(os.path.join(ROOT, BOARD), mine)       # put your board back exactly as it was
        named = _names_after(r.stderr, "local changes to the following files would be overwritten")
        if named:
            return False, "Couldn't update: these files were changed on this Mac: " + ", ".join(named[:5]) + ". Send this message to Claude.", False
        if "local changes" in r.stderr or "overwritten" in r.stderr or "not possible to fast-forward" in r.stderr.lower():
            first = next((l.strip() for l in r.stderr.splitlines() if l.strip()), "")
            return False, "Couldn't update: files in the project were changed on this Mac. Send this message to Claude. [" + first[:160] + "]", False
        return False, "Couldn't reach GitHub. Check your internet connection and try again.", False
    if mine is not None:
        theirs = None
        try:
            theirs = board_merge.load_file(os.path.join(ROOT, BOARD))
            board_merge.save_file(os.path.join(ROOT, BOARD), board_merge.merge3(base, mine, theirs))
        except Exception:                         # noqa: BLE001 - never lose your board: the saved copy is also in ~/.reelfactory/update-backup
            if theirs is None:
                board_merge.save_file(os.path.join(ROOT, BOARD), mine)
    after = _git("rev-parse", "HEAD").stdout.strip()
    if after == before:
        return True, "You already have the latest version.", False
    return True, "Updated. Reel Factory restarts now; this page reloads by itself.", True
