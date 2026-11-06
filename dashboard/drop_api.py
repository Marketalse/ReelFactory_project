"""Drop folder inside the dashboard: clips put in ~/Desktop/Reel Factory Drop become draft reels in its Ready folder.
Uses the same one-at-a-time runner as the Make page, so progress shows on the home page. Never posts anything. Local only."""
import json, os, subprocess, sys, threading, time

import reels_api

ROOT = reels_api.ROOT
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import watch_folder as wf          # noqa: E402
from lib import config as cfg      # noqa: E402

_state = {"thread": None, "stop": False, "drop": None, "now": None, "ready": [], "failed": [], "slugs": []}
_lock = threading.Lock()


def enabled():
    return bool((cfg.PROJECT.get("drop") or {}).get("enabled"))


def _runner(cmd):
    """Start the reel through the dashboard's own runner (one at a time) and wait for it."""
    slug = cmd[cmd.index("--slug") + 1]
    while not _state["stop"]:
        ok, msg = reels_api.start(slug)
        if ok:
            break
        if not msg.startswith("busy"):
            class R: stdout = "STOP: " + msg
            return R()
        time.sleep(5)
    while slug in reels_api.busy() and not _state["stop"]:
        time.sleep(3)
    class R: stdout = ""
    return R()


def _loop():
    drop = wf.drop_path()
    wf.setup(drop)
    _state["drop"] = drop
    while not _state["stop"]:
        for kind, path in wf.items(drop):
            if _state["stop"]:
                break
            if not wf.is_stable(path):
                continue
            wf.process(kind, path, drop, _state, runner=_runner)
        for _ in range(wf.POLL):
            if _state["stop"]:
                break
            time.sleep(1)


def start():
    with _lock:
        t = _state["thread"]
        if t and t.is_alive():
            return True
        _state["stop"] = False
        _state["thread"] = threading.Thread(target=_loop, daemon=True)
        _state["thread"].start()
    return True


def stop():
    _state["stop"] = True


def status():
    t = _state["thread"]
    return {"enabled": enabled(), "watching": bool(t and t.is_alive() and not _state["stop"]), "path": wf.drop_path(),
            "now": _state.get("now"), "ready": _state.get("ready", [])[-8:], "failed": _state.get("failed", [])[-8:]}


def set_on(on):
    try:
        cfg.local_set(["drop", "enabled"], bool(on))
        cfg.PROJECT.setdefault("drop", {})["enabled"] = bool(on)
    except Exception:                  # noqa: BLE001
        return False, "ما قدرت أحفظ الإعداد"
    if on:
        start()
        return True, "تم تشغيل مجلد السحب"
    stop()
    return True, "تم إيقاف مجلد السحب"


def open_folder():
    p = wf.drop_path()
    wf.setup(p)
    if sys.platform == "darwin":
        try:
            subprocess.Popen(["open", p])
            return True, "فتحت المجلد"
        except OSError:
            return False, "ما قدرت أفتح المجلد"
    return True, p
