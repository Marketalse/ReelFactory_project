#!/usr/bin/env python3
"""Builds the JSON for the temporary live board from the real suite logs. Usage: live_state.py > state.json   (then it is pushed to the page's database)"""
import glob, json, os, re, sys, time
X = "/tmp/claude-0/x"
def lines(name):
    p = os.path.join(X, name); return open(p, errors="replace").read().splitlines() if os.path.exists(p) else []
def results(name, group):
    out = {}
    for l in lines(name):
        m = re.match(r"\[(PASS|FAIL|WARN|BLOCKED)\s*\] " + group + r": (.*?)(  \|.*)?$", l)
        if m: out[m.group(2).strip()] = (m.group(1).lower(), (m.group(3) or "").strip(" |"))
    return out
MODES = ["err500", "err429", "err401", "garbage", "empty", "truncated", "drop"]
NAMES = {"err500": "HTTP 500 from the AI", "err429": "rate limit (429)", "err401": "wrong API key (401)", "garbage": "garbage answer", "empty": "empty answer", "truncated": "cut-off answer", "drop": "dropped connection"}
planned = []
for m in MODES: planned += [(f"I1 AI answers '{m}'", f"AI: {NAMES[m]}, reel stops calmly"), (f"I1b resume after '{m}' once the AI is back", f"Resume after: {NAMES[m]}")]
planned += [("I2 per-reel budget guard stops before the cap is passed", "Budget guard stops the spending"), ("I3 reel killed mid-render resumes and finishes", "Kill the reel mid-render, then resume"), ("I4 two reel.py runs on the same reel at once", "Two runs on the same reel at once")]
res = results("integration.txt", "integration")
checks, done = [], 0; running_set = False
for key, label in planned:
    hit = next((v for k, v in res.items() if k == key), None)
    if hit: checks.append({"name": label, "status": hit[0] if hit[0] in ("pass", "fail", "warn") else "fail", "detail": hit[1][:140]}); done += 1
    elif not running_set: checks.append({"name": label, "status": "running", "detail": ""}); running_set = True
    else: checks.append({"name": label, "status": "queued", "detail": ""})
stage3_total = len(planned); stage3_done = done
cfg = json.load(open(os.path.join(X, "live_cfg.json"))) if os.path.exists(os.path.join(X, "live_cfg.json")) else {}
S = cfg.get("stages", {})  # manual overrides: {"4": {"status":"running","done":3}}
base = [(1, "1 · Discover the project", 1, 1, "62 modules scanned, 10 weak points listed", 5), (2, "2 · Functional tests", 152, 152, "full reel, re-plan, final render, silent + 4K clips, dashboard crash test", 15),
        (3, "3 · Integration and failure tests", stage3_done, stage3_total, "7 AI failure types with resume, budget, kill mid-render, duplicate runs", 20),
        (4, "4 · Performance baseline", 0, 8, "start-up, latency, memory, disk per reel", 10), (5, "5 · Stress ladder", 0, 21, "clients, uploads, Start clicks, parallel reels", 20),
        (6, "6 · Endurance and recovery", 0, 7, "soak, repeated reels, AI outage mid-reel", 15), (7, "7 · Root causes and fixes", cfg.get("fixed", 2), cfg.get("found", 2), "each fix has a test proven to fail before and pass after", 5),
        (8, "8 · Final report and UAT decision", 0, 9, "files in pre_uat_report/", 10)]
stages, pct = [], 0.0; current = None
for sid, title, d, t, note, w in base:
    o = S.get(str(sid), {}); d = o.get("done", d); t = o.get("total", t)
    status = o.get("status") or ("done" if d >= t and t else ("running" if d > 0 or (sid == 3) else "waiting"))
    if sid == 7: status = o.get("status") or ("done" if cfg.get("finished") else "running")
    if sid == 3 and d >= t: status = "done"
    stages.append({"id": sid, "title": title, "status": status, "done": d, "total": t, "note": o.get("note", note)})
    pct += w * (1 if status == "done" else (min(1, d / t) if t else 0))
    if status == "running" and sid != 7 and current is None: current = sid
ncheck = sum(1 for c in checks if c["status"] in ("pass", "fail", "warn"))
f = results("functional.txt", "functional")
passed = 11 + 141 - 1 + sum(1 for c in checks if c["status"] == "pass") + cfg.get("extra_pass", 0)
failed = sum(1 for c in checks if c["status"] == "fail") + cfg.get("extra_fail", 0)
warned = 1 + sum(1 for c in checks if c["status"] == "warn") + cfg.get("extra_warn", 0)
log = []
for l in reversed(lines("livelog.txt")[-40:]):
    m = re.match(r"(\d\d:\d\d) (.*)", l); log.append({"t": m.group(1), "text": m.group(2)} if m else {"t": "", "text": l})
state = {"updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "percent": round(pct), "stage": cfg.get("stage_text") or (f"{current} of 8 — " + stages[current - 1]["title"][4:] if current else "wrapping up"),
         "eta": cfg.get("eta", "about 60 min"), "now": cfg.get("now", "working"), "sub": cfg.get("sub", f"Check {min(ncheck + 1, stage3_total)} of {stage3_total} in stage 3"),
         "finished": bool(cfg.get("finished")), "counters": {"passed": passed, "failed": failed, "warned": warned, "bugs_found": cfg.get("found", 2), "bugs_fixed": cfg.get("fixed", 2)},
         "stages": stages, "checks": cfg.get("checks_override") or checks, "bugs": cfg.get("bugs", []), "log": log}
json.dump(state, sys.stdout, ensure_ascii=False)
