"""Settings page backend: health checks and saving the API key. Never returns or logs the key."""
import json, os, platform, shutil, subprocess, sys, urllib.request, urllib.error

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
    key = (key or "").strip()
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
