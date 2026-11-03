#!/usr/bin/env python3
"""Dashboard performance, stress ladder and soak test. Starts a COPY of the dashboard (never the real one) and measures it.
   python3 dash_perf.py baseline | ladder | uploads | queue | soak [--minutes N]      -> pre_uat_report/<name>_results.json"""
import argparse, http.client, json, os, shutil, statistics, subprocess, sys, tempfile, threading, time
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.dirname(HERE); SRC = os.path.dirname(OUT)
sys.path.insert(0, os.path.join(SRC, "scripts"))
import stress_dashboard as sd
sd.PORT = 8785
EP = ["/api/health", "/api/progress", "/api/reels", "/api/tasks", "/api/spend", "/api/version", "/make.html"]


def fds(pid):
    try: return len(os.listdir(f"/proc/{pid}/fd"))
    except OSError: return -1


def pct(xs, p):
    xs = sorted(xs); return round(xs[min(len(xs) - 1, int(len(xs) * p / 100))] * 1000, 1) if xs else None


def timed(path):
    t = time.time(); c = http.client.HTTPConnection("127.0.0.1", sd.PORT, timeout=30)
    try:
        c.request("GET", path); r = c.getresponse(); r.read(); return time.time() - t, r.status
    except Exception:
        return time.time() - t, 0
    finally: c.close()


def setup():
    work = sd.setup(); S = sd.Server(work); return work, S


def baseline():
    res = {"environment": {"cpus": os.cpu_count(), "python": sys.version.split()[0]}}
    starts = []
    for _ in range(5):
        work, S = setup(); t = time.time(); up = S.start(); starts.append(round(time.time() - t, 2)); S.stop(); shutil.rmtree(work, ignore_errors=True)
    res["startup_seconds"] = starts
    work, S = setup(); S.start(); time.sleep(1)
    res["idle"] = {"rss_mb": S.rss_mb(), "threads": S.threads(), "fds": fds(S.p.pid)}
    res["endpoints"] = {}
    for p in EP:
        lat = []; bad = 0
        for _ in range(300):
            dt, st = timed(p); lat.append(dt); bad += st != 200
        res["endpoints"][p] = {"n": 300, "errors": bad, "p50_ms": pct(lat, 50), "p95_ms": pct(lat, 95), "p99_ms": pct(lat, 99), "mean_ms": round(statistics.mean(lat) * 1000, 1)}
    res["after"] = {"rss_mb": S.rss_mb(), "threads": S.threads(), "fds": fds(S.p.pid)}
    S.stop(); shutil.rmtree(work, ignore_errors=True)
    return res


def ladder():
    work, S = setup(); S.start(); out = []; first_bad = None; first_slow = None
    for n in (1, 2, 4, 8, 16, 32, 64, 128, 256, 512):
        lat, errs, lock, stop = [], [0], threading.Lock(), time.time() + 8
        def client(i):
            k = i
            while time.time() < stop:
                dt, st = timed(EP[k % 6]); k += 1
                with lock:
                    lat.append(dt)
                    if st != 200: errs[0] += 1
        ts = [threading.Thread(target=client, args=(i,)) for i in range(n)]; t0 = time.time(); [t.start() for t in ts]; [t.join(60) for t in ts]
        el = time.time() - t0; row = {"clients": n, "requests": len(lat), "rps": round(len(lat) / el, 1), "errors": errs[0], "error_rate": round(errs[0] / max(1, len(lat)), 4),
               "p50_ms": pct(lat, 50), "p95_ms": pct(lat, 95), "p99_ms": pct(lat, 99), "rss_mb": S.rss_mb(), "threads": S.threads(), "alive_after": sd.alive(8)}
        out.append(row); print(row, flush=True)
        if row["error_rate"] > 0 and first_bad is None: first_bad = n
        if (row["p95_ms"] or 0) > 2000 and first_slow is None: first_slow = n
        if row["error_rate"] > 0.05 or not row["alive_after"]: break
    S.stop(); shutil.rmtree(work, ignore_errors=True)
    return {"environment": {"cpus": os.cpu_count(), "note": "load generator and server share the same 4 CPUs: numbers are conservative"}, "levels": out, "first_error_level": first_bad, "first_p95_over_2s_level": first_slow}


def uploads():
    work, S = setup(); S.start(); out = []; blob = os.urandom(1 << 20) * 20
    for n in (1, 2, 4, 8, 16, 32):
        ok, bad, lock = [0], [0], threading.Lock(); t0 = time.time(); times = []
        def one(i):
            t = time.time(); s, r = sd.upload(f"ul-{n}-{i}", "clip", "c.mp4", blob, session=f"s{n:03d}{i:05d}", timeout=300)
            with lock:
                times.append(time.time() - t)
                if isinstance(r, dict) and r.get("ok"): ok[0] += 1
                else: bad[0] += 1
        ts = [threading.Thread(target=one, args=(i,)) for i in range(n)]; [t.start() for t in ts]; [t.join(400) for t in ts]; el = time.time() - t0
        row = {"parallel_uploads": n, "size_mb_each": 20, "ok": ok[0], "failed": bad[0], "seconds": round(el, 1), "throughput_mb_s": round(n * 20 / el, 1), "p95_s": round(sorted(times)[min(len(times) - 1, int(len(times) * .95))], 1), "server_rss_mb": S.rss_mb(), "alive": sd.alive(8)}
        out.append(row); print(row, flush=True)
    S.stop(); shutil.rmtree(work, ignore_errors=True); return {"levels": out}


def queue():
    work, S = setup(); S.start(); res = []
    clip = os.path.join(work, "_c.mp4"); subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=360x640:r=30:d=4", "-f", "lavfi", "-i", "sine=d=4", "-shortest", "-pix_fmt", "yuv420p", clip], check=True)
    data = open(clip, "rb").read()
    for i in range(10): sd.upload(f"q-{i:02d}", "clip", "a.mp4", data, session=f"qq{i:08d}")
    out = []; lock = threading.Lock()
    def start(i):
        c = http.client.HTTPConnection("127.0.0.1", sd.PORT, timeout=30); c.request("POST", "/api/reels/start", json.dumps({"slug": f"q-{i:02d}"})); r = c.getresponse(); b = r.read().decode(); c.close()
        with lock: out.append((r.status, b[:90]))
    ts = [threading.Thread(target=start, args=(i,)) for i in range(10)]; [t.start() for t in ts]; [t.join(60) for t in ts]
    accepted = [o for o in out if '"ok": true' in o[1]]; busy = [o for o in out if "busy" in o[1]]
    time.sleep(2); procs = subprocess.run(["pgrep", "-fc", "scripts/reel.py"], capture_output=True, text=True).stdout.strip()
    row = {"simultaneous_start_clicks": 10, "accepted": len(accepted), "refused_as_busy": len(busy), "other": [o for o in out if o not in accepted and o not in busy][:3], "reel_processes_running": procs, "alive": sd.alive(8)}
    print(row); subprocess.run(["pkill", "-f", "scripts/reel.py"], capture_output=True); S.stop(); shutil.rmtree(work, ignore_errors=True); return row


def soak(minutes):
    work, S = setup(); S.start(); samples = []; stop = time.time() + minutes * 60; lock = threading.Lock(); errs = [0]; n = [0]; lat = []
    def worker(i):
        k = i
        while time.time() < stop:
            dt, st = timed(EP[k % 6]); k += 1
            with lock:
                n[0] += 1; lat.append(dt); errs[0] += st != 200
            time.sleep(0.15)
    ts = [threading.Thread(target=worker, args=(i,)) for i in range(8)]; [t.start() for t in ts]
    small = os.urandom(1 << 20) * 5; j = 0
    while time.time() < stop:
        j += 1; sd.upload(f"soak-{j}", "clip", "c.mp4", small, session=f"sk{j:08d}")
        samples.append({"t": round(time.time() - (stop - minutes * 60)), "rss_mb": S.rss_mb(), "threads": S.threads(), "fds": fds(S.p.pid), "requests": n[0], "errors": errs[0]})
        time.sleep(15)
    [t.join(30) for t in ts]
    x = [s["t"] for s in samples]; slope = lambda k: round((statistics.linear_regression(x, [s[k] for s in samples]).slope) * 60, 3) if len(x) > 3 else None
    row = {"minutes": minutes, "requests": n[0], "errors": errs[0], "p95_ms": pct(lat, 95), "rss_start_mb": samples[0]["rss_mb"], "rss_end_mb": samples[-1]["rss_mb"], "rss_slope_mb_per_min": slope("rss_mb"),
           "threads_end": samples[-1]["threads"], "fds_start": samples[0]["fds"], "fds_end": samples[-1]["fds"], "fd_slope_per_min": slope("fds"), "alive": sd.alive(8), "samples": samples}
    S.stop(); shutil.rmtree(work, ignore_errors=True); return row


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("what"); ap.add_argument("--minutes", type=float, default=5); a = ap.parse_args()
    res = {"baseline": baseline, "ladder": ladder, "uploads": uploads, "queue": queue}.get(a.what, lambda: soak(a.minutes))()
    json.dump(res, open(os.path.join(OUT, f"{a.what}_results.json"), "w"), indent=1); print(json.dumps(res)[:1500])
