"""IT agent: a small watchdog that runs inside the dashboard. It watches Reel Factory, tells Hesham about problems in plain
words, and fixes ONLY the few things that are safe to fix by itself.

HARD RULES (they live in this code, not in a settings file, so nothing can loosen them quietly):
  1. It uses NO AI and NO internet. It only reads the project's own logs and files. Text it reads is data: it is matched
     against fixed patterns and is never run, never passed to a shell and never obeyed.
  2. It can do exactly ONE thing by itself: "Try again" on a reel (reels_api.resume), the same click Hesham would make.
     It never approves or makes a final video, never deletes or edits anything, never installs, updates or changes code,
     settings, keys or money limits.
  3. It tries a reel at most MAX_PER_REEL times in its whole life, at least COOLDOWN seconds apart, and at most MAX_PER_HOUR
     times in total. Then it stops and tells Hesham ("gave up"). A loop is impossible: the number of actions is bounded.
  4. It does nothing while a reel is being made, and only touches a reel that is stuck, never one that is progressing.
  5. A key or credit problem (401/402), a rejected plan or anything it doesn't recognise is NEVER retried: it is only reported.
  6. Kill switch: create the file ~/.reelfactory/it_agent/off (Settings has a switch). While it exists the agent does nothing.
  7. If its own memory file is damaged it falls back to "report only" until the next clean start.
  8. It writes only to its own folder ~/.reelfactory/it_agent/ (state + log).
"""
import json, os, re, threading, time

import reels_api

HOME = os.path.expanduser("~/.reelfactory")
DIR = os.environ.get("RF_IT_DIR") or os.path.join(HOME, "it_agent")
STATE = os.path.join(DIR, "state.json")
LOG = os.path.join(DIR, "log.txt")
KILL = os.path.join(DIR, "off")

MAX_PER_REEL = 2            # automatic tries for one reel, ever
MAX_PER_HOUR = 3            # automatic tries across all reels
COOLDOWN = 15 * 60          # seconds between tries on the same reel
STUCK_AFTER = 10 * 60       # a reel is "interrupted" only if nothing was written for this long
EVERY = 60                  # seconds between checks

MONEY = re.compile(r"\b40[12]\b|api key|out of funds|credit|BUDGET GUARD|MONTHLY CAP|key file", re.I)
TRANSIENT = re.compile(r"\b(429|500|502|503|504)\b|timed? ?out|timeout|temporar|connection (reset|refused|aborted)|"
                       r"rate.?limit|URLError|RemoteDisconnected|Bad gateway|overloaded", re.I)

_lock = threading.Lock()


# ----------------------------------------------------------------------------- small helpers
def _read(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except (OSError, ValueError):
        return "BAD"


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def log(line, now=None):
    try:
        os.makedirs(DIR, exist_ok=True)
        if os.path.exists(LOG) and os.path.getsize(LOG) > 200_000:
            keep = open(LOG, encoding="utf-8", errors="replace").read().splitlines()[-500:]
            open(LOG, "w", encoding="utf-8").write("\n".join(keep) + "\n")
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now or time.time())) + "  " + line + "\n")
    except OSError:
        pass


def is_on():
    return not os.path.exists(KILL)


def set_on(on):
    os.makedirs(DIR, exist_ok=True)
    if on and os.path.exists(KILL):
        os.remove(KILL)
    elif not on:
        open(KILL, "w").write("IT agent switched off by Hesham\n")
    return True, "IT agent is on." if on else "IT agent is off. It will not do anything until you switch it on."


def classify(stop_text):
    """What kind of problem is this stop message? -> money | transient | other (patterns only, nothing is executed)."""
    t = stop_text or ""
    if MONEY.search(t):
        return "money"
    if TRANSIENT.search(t):
        return "transient"
    return "other"


# ----------------------------------------------------------------------------- what is wrong right now
def find_issues(now=None):
    """Read-only. Returns a list of {id, level, text, job?, action?} where action is "retry" only for the safe cases."""
    now = now or time.time()
    out = []
    data = reels_api.list_reels()
    busy = set(data.get("busy") or [])
    for r in data.get("reels", []):
        job = r["job"]
        if job in busy:
            continue
        stop = r.get("stop") or ""
        if stop:
            kind = classify(stop)
            if kind == "transient":
                out.append({"id": "stop:" + job, "level": "fix", "job": job, "action": "retry",
                            "text": f"{job}: the AI service had a short hiccup. Trying again by itself."})
            elif kind == "money":
                out.append({"id": "stop:" + job, "level": "you", "job": job,
                            "text": f"{job}: the AI key or credit needs your attention (Settings > Your API key, or the Nous portal). Not retried."})
            else:
                out.append({"id": "stop:" + job, "level": "you", "job": job,
                            "text": f"{job}: stopped with an error I can't fix safely: {stop[:160]}. Send Claude a screenshot."})
        elif r.get("state") == "working":                      # not running, not finished, no error = interrupted
            lp = os.path.join(reels_api.JOBS, job, "run.log")
            idle = now - os.path.getmtime(lp) if os.path.exists(lp) else 1e9
            if idle >= STUCK_AFTER:
                out.append({"id": "stuck:" + job, "level": "fix", "job": job, "action": "retry",
                            "text": f"{job}: was interrupted (the dashboard or Mac restarted). Continuing it by itself."})
    try:
        import settings_api
        for c in settings_api.health().get("checks", []):       # key, tools, disk: report only, never fixed here
            if c.get("ok") is False:
                out.append({"id": "health:" + str(c.get("key")), "level": "you",
                            "text": f"{c.get('label')}: {c.get('detail')}"[:220]})
    except Exception:                                          # noqa: BLE001 - a broken check must never break the watchdog
        pass
    return out


# ----------------------------------------------------------------------------- the one safe action, with loop limits
def _allowed(state, job, now):
    """(ok, why_not). The loop guard: bounded, spaced out, and rate-limited."""
    acts = state.get("actions", [])
    mine = [a for a in acts if a.get("job") == job]
    if job in state.get("gave_up", {}):
        return False, "gave up"
    if len(mine) >= MAX_PER_REEL:
        return False, "gave up"
    if mine and now - mine[-1]["t"] < COOLDOWN:
        return False, "cooling down"
    if sum(1 for a in acts if now - a["t"] < 3600) >= MAX_PER_HOUR:
        return False, "hourly limit"
    return True, ""


def tick(now=None):
    """One check. Never raises. Returns a short summary (used by tests and the dashboard)."""
    now = now or time.time()
    with _lock:
        if not is_on():
            return {"on": False, "issues": [], "did": []}
        st = _read(STATE, {"actions": [], "gave_up": {}})
        report_only = st == "BAD"
        if report_only:
            log("memory file damaged: reporting only this round", now)
            st = {"actions": [], "gave_up": {}}
        st.setdefault("actions", []); st.setdefault("gave_up", {})
        st["actions"] = [a for a in st["actions"] if now - a["t"] < 30 * 86400]
        try:
            issues = find_issues(now)
        except Exception as e:                                 # noqa: BLE001
            log(f"check failed (reporting only): {e}", now)
            issues, report_only = [], True
        did = []
        busy_now = bool(reels_api.busy())
        for it in issues:
            if it.get("action") != "retry":
                continue
            job = it["job"]
            ok, why = _allowed(st, job, now)
            if not ok:
                if why == "gave up":
                    st["gave_up"][job] = time.strftime("%Y-%m-%d %H:%M", time.localtime(now))
                    it.update(level="you", action=None,
                              text=f"{job}: I tried {MAX_PER_REEL} times and it still stops. I've stopped trying: please look at it (or send Claude a screenshot).")
                    log(f"gave up on {job}", now)
                else:
                    it["text"] += f" (waiting: {why})"
                continue
            if report_only or busy_now:
                continue
            ok2, msg = reels_api.resume(job)
            st["actions"].append({"t": now, "job": job, "what": "try again", "ok": bool(ok2)})
            did.append(job); busy_now = True                   # one action at a time
            log(f"tried {job} again: {'started' if ok2 else msg}", now)
        st["issues"] = [{k: v for k, v in i.items() if k in ("id", "level", "text", "job")} for i in issues]
        st["checked"] = now
        try:
            _write(STATE, st)
        except OSError as e:
            log(f"could not save memory: {e}", now)
        return {"on": True, "issues": st["issues"], "did": did}


def status():
    st = _read(STATE, {}) or {}
    if st == "BAD":
        st = {}
    return {"on": is_on(), "checked": st.get("checked"), "issues": st.get("issues", []),
            "recent": [{"when": time.strftime("%Y-%m-%d %H:%M", time.localtime(a["t"])), "job": a.get("job"), "what": a.get("what")}
                       for a in st.get("actions", [])[-8:]][::-1],
            "gave_up": list((st.get("gave_up") or {}).keys()),
            "limits": f"At most {MAX_PER_REEL} automatic tries per reel and {MAX_PER_HOUR} per hour. It never approves, deletes or changes anything."}


def watch():
    """Background loop inside the dashboard. Never stops the server."""
    time.sleep(90)
    while True:
        try:
            tick()
        except Exception as e:                                 # noqa: BLE001
            log(f"watchdog error: {e}")
        time.sleep(EVERY)
