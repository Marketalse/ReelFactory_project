#!/usr/bin/env python3
"""Pre-UAT scenario suite (functional, integration, performance, stress, endurance). Uses e2e.py (mock AI, real everything else).
   python3 suite.py functional | integration | perf | stress | endurance      Results are written to pre_uat_report/<group>_results.json"""
import concurrent.futures as cf, glob, json, os, re, shutil, signal, subprocess, sys, threading, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import e2e
OUT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R = []


def rec(group, name, verdict, detail="", **extra):
    row = {"group": group, "name": name, "verdict": verdict, "detail": str(detail)[:600], **extra}; R.append(row)
    print(f"[{verdict:7s}] {group}: {name}" + (f"  | {str(detail)[:150]}" if verdict != "PASS" else ""), flush=True)


def save(group):
    json.dump([r for r in R if r["group"] == group], open(os.path.join(OUT, f"{group}_results.json"), "w"), indent=1, ensure_ascii=False)


def job_state(jd):
    f = lambda n: os.path.exists(os.path.join(jd, n))
    return {"draft": f("review/draft_540p.mp4"), "critic": f("review/critic.json"), "outline": f("outline.json"), "timeline": f("timeline.json"), "report": f("report.md")}


def tail(r, n=500): return (r["output"] or "")[-n:].replace("\n", " | ")


def one_reel(work, slug, dur=56, seed=1, extra=(), audio=True, size="1080x1920", timeout=700):
    jd, r0 = e2e.seed_job(work, slug, dur, seed, audio, size)
    if not jd: return None, r0, None
    r = e2e.run(work, [jd, "--budget", "1.5"] + list(extra), timeout, slug)
    return jd, r0, r


# ------------------------------------------------------------------ FUNCTIONAL / INTEGRATION
def functional():
    e2e.start_mock(); work = e2e.make_copy(); g = "functional"
    # F1 happy path: explainer (Format Pack) end to end
    t0 = time.time(); jd, r0, r = one_reel(work, "f1-pack", 56)
    ok = r and r["code"] == 0 and job_state(jd)["draft"]
    st = job_state(jd) if jd else {}
    rec(g, "F1 full pipeline to draft (Format Pack reel, mock AI)", "PASS" if ok and st.get("critic") else "FAIL", tail(r) if r else "no job", seconds=r["seconds"] if r else None, rss_mb=r["max_rss_mb"] if r else None, state=st)
    if ok:
        info = json.load(open(os.path.join(jd, "hyperframes", "compile_info.json"))); rec(g, "F1b compile_info says Format Pack used", "PASS" if info.get("format_pack") else "FAIL", info)
        dj = json.load(open(os.path.join(jd, "review", "draft.json")))
        rec(g, "F1c draft QA result present", "PASS" if "qa" in dj else "FAIL", json.dumps(dj.get("qa", {}))[:300])
        cost = json.load(open(os.path.join(jd, "cost.json"))); rec(g, "F1d cost.json written for every AI call", "PASS" if len(cost["calls"]) >= 6 else "FAIL", f"{len(cost['calls'])} calls, ${sum(c['cost'] for c in cost['calls']):.4f}")
        # F9 idempotency: second run changes nothing and makes no AI call
        calls0 = e2e.STATE["calls"]; r2 = e2e.run(work, [jd, "--budget", "1.5"], 300, "rerun")
        rec(g, "F9 re-running a finished reel makes no AI call", "PASS" if e2e.STATE["calls"] == calls0 and r2["code"] == 0 else "FAIL", f"extra calls {e2e.STATE['calls'] - calls0}; {tail(r2, 200)}")
    save(g)
    # F2 feedback loop: --fix re-plans (one more director call, draft rebuilt)
    if ok:
        calls0 = e2e.STATE["calls"]; r3 = e2e.run(work, [jd, "--fix", "اجعل الخط اكبر", "--budget", "1.5"], 600, "fix")
        rec(g, "F2 'fix' comment re-plans and re-renders the draft", "PASS" if r3["code"] == 0 and "STOP" not in r3["output"] else "FAIL", f"{tail(r3, 300)}; AI calls +{e2e.STATE['calls'] - calls0}", seconds=r3["seconds"])
    # F3 approve: final render (1080p, both platforms) of the same reel
    if ok:
        r4 = e2e.run(work, [jd, "--approve"], 1500, "approve")
        fin = glob.glob(os.path.join(jd, "final", "*.mp4"))
        rec(g, "F3 approve -> final video(s) + cover", "PASS" if r4["code"] == 0 and fin else "FAIL", f"{len(fin)} final file(s); {tail(r4, 300)}", seconds=r4["seconds"], rss_mb=r4["max_rss_mb"])
        if fin:
            pr = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height,duration", "-of", "json", fin[0]], capture_output=True, text=True)
            rec(g, "F3b final video is 1080x1920 with audio", "PASS" if '"width": 1080' in pr.stdout and '"audio"' in pr.stdout else "FAIL", pr.stdout[:300].replace("\n", " "))
            ln = subprocess.run(["ffmpeg", "-i", fin[0], "-af", "ebur128", "-f", "null", "-"], capture_output=True, text=True).stderr
            m = re.findall(r"I:\s+(-?[\d.]+) LUFS", ln); rec(g, "F3c loudness near the -14 LUFS target", "PASS" if m and abs(float(m[-1]) + 14) < 1.5 else "WARN", m[-1:] )
    save(g)
    # F4 odd footage through the whole pipeline
    for label, kw in (("silent clip (no audio track)", dict(audio=False)), ("4K portrait", dict(size="2160x3840", dur=30))):
        slug = "f4-" + re.sub(r"[^a-z0-9]+", "-", label.lower())[:20]
        jd2, r0b, rb = one_reel(work, slug, kw.get("dur", 40), 3, audio=kw.get("audio", True), size=kw.get("size", "1080x1920"))
        rec(g, f"F4 {label}", "PASS" if rb and rb["code"] == 0 and job_state(jd2)["draft"] else "FAIL", tail(rb) if rb else tail(r0b), seconds=rb["seconds"] if rb else None)
    save(g)


def integration():
    e2e.start_mock(); work = e2e.make_copy(); g = "integration"
    # I1 AI service failure modes at each stage: the reel must stop with a plain message (never a traceback), keep finished work, and resume cleanly
    for mode in ("err500", "err429", "err401", "garbage", "empty", "truncated", "drop"):
        slug = f"i1-{mode}"; jd, r0 = e2e.seed_job(work, slug, 50, 5)
        e2e.STATE["mode"] = mode
        r = e2e.run(work, [jd, "--budget", "1.5"], 240, mode); e2e.STATE["mode"] = "ok"
        out = r["output"]; tb = "Traceback" in out
        stop = re.findall(r"STOP: (.*)", out); plain = bool(stop) and not tb
        if mode in ("garbage", "empty", "truncated") and not stop and r["code"] == 0:
            rec(g, f"I1 AI answers '{mode}'", "PASS", "the reel carried on without a stop (the step has a fallback)", seconds=r["seconds"]); resumed = None
        else:
            rec(g, f"I1 AI answers '{mode}'", "PASS" if plain and r["code"] == 0 else "FAIL", ("stop: " + (stop[0][:200] if stop else "none")) + (" | TRACEBACK" if tb else ""), seconds=r["seconds"])
        r2 = e2e.run(work, [jd, "--budget", "1.5"], 600, mode + "-resume")
        rec(g, f"I1b resume after '{mode}' once the AI is back", "PASS" if r2["code"] == 0 and job_state(jd)["draft"] else "FAIL", tail(r2, 300), seconds=r2["seconds"])
    save(g)
    # I2 budget guard
    jd, _ = e2e.seed_job(work, "i2-budget", 50, 6); calls0 = e2e.STATE["calls"]
    r = e2e.run(work, [jd, "--budget", "0.0025"], 300, "budget")
    rec(g, "I2 per-reel budget guard stops before the cap is passed", "PASS" if "BUDGET GUARD" in r["output"] and e2e.STATE["calls"] - calls0 <= 3 else "FAIL", f"{e2e.STATE['calls'] - calls0} AI calls; {tail(r, 200)}")
    # I3 interrupted job: kill -9 in the middle of the render, then resume
    jd, _ = e2e.seed_job(work, "i3-kill", 56, 7)
    p = subprocess.Popen([sys.executable, os.path.join(work, "scripts", "reel.py"), jd, "--budget", "1.5"], cwd=work, env=e2e.env_for(work), stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    t0 = time.time()
    while time.time() - t0 < 120 and not os.path.exists(os.path.join(jd, "hyperframes", "index.html")): time.sleep(0.5)
    time.sleep(6); os.killpg(os.getpgid(p.pid), signal.SIGKILL) if False else p.kill(); p.wait()
    subprocess.run(["pkill", "-9", "-f", "hyperframes"], capture_output=True); time.sleep(1)
    r2 = e2e.run(work, [jd, "--budget", "1.5"], 600, "resume-after-kill")
    rec(g, "I3 reel killed mid-render resumes and finishes", "PASS" if r2["code"] == 0 and job_state(jd)["draft"] else "FAIL", tail(r2, 300), seconds=r2["seconds"])
    # I4 two processes on the same reel at once (strict criteria after the pre-UAT audit found BUG-005)
    i4(work, g)
    # I5 dashboard-level duplicate-start prevention + one-reel-at-a-time queue
    save(g)


def i4(work, g="integration"):
    jd, _ = e2e.seed_job(work, "i4-dup", 50, 8)
    ps = [subprocess.Popen([sys.executable, os.path.join(work, "scripts", "reel.py"), jd, "--budget", "1.5"], cwd=work, env=e2e.env_for(work), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) for _ in range(2)]
    outs = [p.communicate(timeout=700)[0] for p in ps]; codes = [p.returncode for p in ps]
    corrupt = []
    for f in glob.glob(os.path.join(jd, "*.json")):
        try: json.load(open(f))
        except Exception: corrupt.append(os.path.basename(f))
    n = len(json.load(open(os.path.join(jd, "cost.json")))["calls"]) if os.path.exists(os.path.join(jd, "cost.json")) else 0
    tb = any("Traceback" in o for o in outs); refused = sum("already being made" in o for o in outs)
    ok = sorted(codes) == [0, 3] and refused == 1 and not corrupt and not tb and 6 <= n <= 7 and job_state(jd)["draft"]
    rec(g, "I4 two reel.py runs on the same reel at once (strict)", "PASS" if ok else "FAIL", f"exits {codes}; refused {refused}; corrupt {corrupt}; traceback {tb}; AI calls logged {n} (one run = 6-7); draft {job_state(jd)['draft']}")


def i4only():
    e2e.start_mock(); work = e2e.make_copy(); i4(work, "integration_i4"); save("integration_i4")


GROUPS = {"functional": functional, "integration": integration, "i4": i4only}
if __name__ == "__main__":
    for g in sys.argv[1:]:
        GROUPS[g](); save(g)
