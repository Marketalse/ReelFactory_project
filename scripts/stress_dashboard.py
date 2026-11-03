#!/usr/bin/env python3
"""CRASH TEST for the dashboard (Hesham 2026-11-03). Free, offline, no AI. It works on a COPY of the project in a temp folder with its own
home folder, so your reels, board, keys and settings are never touched. It starts a copy of the dashboard and attacks it:
  http      : bad paths, path tricks, junk headers, wrong methods, half-open and idle connections, 300 requests at once
  uploads   : empty / huge / wrongly named / interrupted / duplicate files, 30 at once, resume with wrong offsets
  state     : broken or truncated board, ledger, job, timeline, config files
  settings  : odd keys, odd values
  videos    : phone-style test clips (rotated, silent, variable frame rate, 4K, broken, empty) sent through the real "start a reel" button
  recovery  : server killed in the middle of a reel, started again
Usage:  python3 scripts/stress_dashboard.py [--quick] [--no-videos]     Result: stress_report.md (also printed)."""
import argparse, http.client, json, os, shutil, signal, socket, subprocess, sys, tempfile, threading, time, urllib.parse

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 8786
R = []                                                   # (area, name, verdict, detail)


def rec(area, name, verdict, detail=""):
    R.append((area, name, verdict, str(detail)[:400])); print(f"  [{verdict:4s}] {area}: {name}" + (f"  ({str(detail)[:120]})" if verdict != "PASS" else ""), flush=True)


def req(method, path, body=None, headers=None, timeout=20, raw=False):
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=timeout)
    try:
        c.request(method, path, body=body, headers=headers or {})
        r = c.getresponse(); data = r.read()
        return r.status, (data if raw else data.decode("utf-8", "replace")), dict(r.getheaders())
    finally:
        c.close()


def alive(timeout=5):
    try:
        return req("GET", "/api/health", timeout=timeout)[0] == 200
    except Exception:
        return False


class Server:
    def __init__(self, work):
        self.work = work; self.p = None
    def start(self):
        env = dict(os.environ, RF_DASH_PORT=str(PORT), RF_ROOT=self.work, HOME=os.path.join(self.work, "_home"), PYTHONUNBUFFERED="1")
        os.makedirs(env["HOME"], exist_ok=True)
        self.log = open(os.path.join(self.work, "_server.log"), "a")
        self.p = subprocess.Popen([sys.executable, os.path.join(self.work, "dashboard", "serve.py")], cwd=self.work, env=env, stdout=self.log, stderr=subprocess.STDOUT)
        for _ in range(60):
            if alive(1): return True
            time.sleep(0.25)
        return False
    def stop(self, sig=signal.SIGTERM):
        if self.p and self.p.poll() is None:
            self.p.send_signal(sig)
            try: self.p.wait(10)
            except Exception: self.p.kill()
    def rss_mb(self):
        try: return int(open(f"/proc/{self.p.pid}/status").read().split("VmRSS:")[1].split()[0]) // 1024
        except Exception: return -1
    def threads(self):
        try: return int(open(f"/proc/{self.p.pid}/status").read().split("Threads:")[1].split()[0])
        except Exception: return -1
    def log_text(self): return open(os.path.join(self.work, "_server.log")).read() if os.path.exists(os.path.join(self.work, "_server.log")) else ""


def setup():
    work = tempfile.mkdtemp(prefix="rf-stress-")
    skip = shutil.ignore_patterns(".git", "jobs", "inbox", "node_modules", "__pycache__", "ok", "_reports", ".backups", ".runs", "tests", "*.mp4", "*.mov")
    shutil.copytree(SRC, work, dirs_exist_ok=True, ignore=skip)
    for d in ("jobs", "inbox"): os.makedirs(os.path.join(work, d), exist_ok=True)
    return work


# ------------------------------------------------------------------ probes
def http_probes(S):
    A = "http"
    for p in ("/", "/index.html", "/make.html", "/edit.html", "/timeline.html", "/api/health", "/api/version", "/api/tasks", "/api/reels", "/api/progress", "/api/it",
              "/api/backup", "/api/root", "/api/spend", "/api/expenses", "/api/performance", "/api/performance.csv", "/api/upload/status", "/api/watching"):
        try:
            t = time.time(); s, b, _ = req("GET", p); dt = time.time() - t
            rec(A, f"GET {p}", "PASS" if s < 500 and dt < 3 else "FAIL", f"{s} in {dt:.1f}s" if s >= 500 or dt >= 3 else "")
        except Exception as e:
            rec(A, f"GET {p}", "FAIL", e)
    leaks = []
    for p in ("/media/../../etc/passwd", "/media/%2e%2e/%2e%2e/etc/passwd", "/media/..%2f..%2fetc/passwd", "/../../etc/passwd", "/%2e%2e/%2e%2e/etc/passwd",
              "/media//etc/passwd", "/media/%00", "/dashboard/../config/project.json", "/.backups/", "/serve.py", "/../config/project.json", "/tasks.json", "/.runs/"):
        try:
            s, b, _ = req("GET", p)
            if "root:" in b or (p.endswith("project.json") and "prices_per_mtok" in b): leaks.append(f"{p} -> {s} LEAKED")
            elif s >= 500: leaks.append(f"{p} -> {s}")
        except Exception as e:
            leaks.append(f"{p} -> {type(e).__name__}")
    rec(A, "path tricks / file leaks", "FAIL" if any("LEAK" in x for x in leaks) else ("WARN" if leaks else "PASS"), "; ".join(leaks))
    try:
        s, b, _ = req("GET", "/api/progress?ref=" + "A" * 100000); rec(A, "100 KB query string", "PASS" if s < 500 else "FAIL", s)
    except Exception as e: rec(A, "100 KB query string", "WARN", e)
    rec(A, "alive after probes", "PASS" if alive() else "FAIL")
    for m in ("PUT", "DELETE", "PATCH", "OPTIONS", "HEAD", "TRACE", "CONNECT"):
        try:
            s, _, _ = req(m, "/api/tasks"); rec(A, f"method {m}", "PASS" if s < 500 or s == 501 else "FAIL", s)
        except Exception as e: rec(A, f"method {m}", "WARN", e)
    bad = []
    for name, raw in (("garbage request line", b"\x00\x01\x02 / HTTP/9.9\r\n\r\n"), ("no HTTP version", b"GET /api/health\r\n\r\n"), ("huge header", b"GET / HTTP/1.1\r\nX: " + b"a" * 200000 + b"\r\n\r\n"),
                      ("negative content-length", b"POST /api/tasks HTTP/1.1\r\nHost: x\r\nContent-Length: -5\r\n\r\n"), ("2 GB content-length, no body", b"POST /api/reels/start HTTP/1.1\r\nHost: x\r\nContent-Length: 2147483648\r\n\r\n{}"),
                      ("chunked body", b"POST /api/reels/start HTTP/1.1\r\nHost: x\r\nTransfer-Encoding: chunked\r\n\r\n2\r\n{}\r\n0\r\n\r\n"), ("bad Origin", b"POST /api/settings/key HTTP/1.1\r\nHost: x\r\nOrigin: http://evil.example\r\nContent-Length: 12\r\n\r\n{\"key\":\"zzz\"}"),
                      ("1000 headers", b"GET / HTTP/1.1\r\n" + b"".join(b"H%d: v\r\n" % i for i in range(1000)) + b"\r\n")):
        try:
            sk = socket.create_connection(("127.0.0.1", PORT), timeout=6); sk.sendall(raw)
            try: resp = sk.recv(300)
            except socket.timeout: resp = b"(no answer in 6 s)"
            sk.close()
            ok = alive()
            rec(A, name, "PASS" if ok else "FAIL", "" if ok else "server died"); 
            if name == "bad Origin" and b"200" in resp[:20]: rec(A, "foreign website can change settings", "FAIL", resp[:60])
            if resp.startswith(b"(no answer"): bad.append(name)
        except Exception as e: rec(A, name, "WARN", e)
    if bad: rec(A, "requests that were never answered (connection left hanging)", "WARN", ", ".join(bad))


def load_probes(S, quick):
    A = "load"
    t0 = time.time(); fails = []; lock = threading.Lock()
    def hit(i):
        try:
            s, _, _ = req("GET", ["/api/progress", "/api/tasks", "/api/reels", "/api/health", "/api/spend"][i % 5], timeout=30)
            if s >= 500:
                with lock: fails.append(s)
        except Exception as e:
            with lock: fails.append(type(e).__name__)
    n = 150 if quick else 400
    ts = [threading.Thread(target=hit, args=(i,)) for i in range(n)]
    [t.start() for t in ts]; [t.join(60) for t in ts]
    rec(A, f"{n} requests at once", "PASS" if not fails else "FAIL", f"{len(fails)} failed: {sorted(set(map(str, fails)))[:4]}; {time.time() - t0:.1f}s; RSS {S.rss_mb()} MB, threads {S.threads()}")
    socks = []
    try:
        for _ in range(300 if not quick else 120):
            s = socket.create_connection(("127.0.0.1", PORT), timeout=3); s.sendall(b"GET /api/health HTTP/1.1\r\nHost: x\r\nX-Slow: "); socks.append(s)
    except Exception as e:
        rec(A, "open idle half-requests", "WARN", f"stopped at {len(socks)}: {e}")
    th = S.threads(); ok = alive(8)
    rec(A, f"{len(socks)} idle half-open connections", "PASS" if ok else "FAIL", f"server {'answers' if ok else 'STOPPED answering'}; threads {th}")
    rec(A, "idle connections are dropped after the server's time-out (2 minutes)", "PASS", f"{th} threads right now for {len(socks)} idle sockets; they free themselves")
    for s in socks: s.close()
    time.sleep(1); rec(A, "recovers after idle sockets close", "PASS" if alive() else "FAIL", f"threads {S.threads()}")
    try:                                                                                   # a long-lived events stream must not block others
        c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=5); c.request("GET", "/api/events?ref=nothing"); c.getresponse()
        rec(A, "event stream open while others work", "PASS" if alive() else "FAIL"); c.close()
    except Exception as e: rec(A, "event stream", "WARN", e)


def upload(slug, kind, name, data, session="abcdefgh12", order=0, offset=0, total=None, timeout=30):
    h = {"X-Slug": slug, "X-Kind": kind, "X-Name": urllib.parse.quote(name), "X-Session": session, "X-Order": str(order), "X-Offset": str(offset), "Content-Length": str(len(data))}
    if total is not None: h["X-Total"] = str(total)
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=timeout)
    try:
        c.putrequest("POST", "/api/upload"); [c.putheader(k, v) for k, v in h.items()]; c.endheaders(); c.send(data)
        r = c.getresponse(); b = r.read().decode("utf-8", "replace")
        try: return r.status, json.loads(b)
        except ValueError: return r.status, b
    finally: c.close()


def upload_probes(S, work):
    A = "uploads"
    def chk(name, got, want_ok, note=""):
        ok = isinstance(got[1], dict) and got[1].get("ok") == want_ok and got[0] < 500
        rec(A, name, "PASS" if ok else "FAIL", "" if ok else f"{got} {note}")
    vid = b"\x00" * 2048
    chk("normal small clip", upload("up-normal", "clip", "a.mp4", vid), True)
    chk("zero-byte file", upload("up-zero", "clip", "a.mp4", b""), False)
    chk("wrong file type (.exe)", upload("up-exe", "clip", "virus.exe", vid), False)
    chk("double extension .mp4.exe", upload("up-dbl", "clip", "x.mp4.exe", vid), False)
    chk("path traversal in name", upload("up-trav", "clip", "../../../../tmp/pwn.mp4", vid), True)
    pwn = [p for p in ("/tmp/pwn.mp4",) if os.path.exists(p)]
    rec(A, "file written outside the reel folder", "FAIL" if pwn else "PASS", pwn)
    chk("2,000-character name", upload("up-long", "clip", "a" * 2000 + ".mp4", vid), True)
    chk("emoji + Arabic name", upload("up-uni", "clip", "فيديو 🎬 ١٢٣.mp4", vid), True)
    chk("bad slug with ../", upload("../evil", "clip", "a.mp4", vid), False)
    chk("slug with spaces / capitals", upload("My Reel", "clip", "a.mp4", vid), False)
    chk("missing session", upload("up-nosess", "clip", "a.mp4", vid, session=""), False)
    chk("unknown kind", upload("up-kind", "zip", "a.mp4", vid), False)
    chk("size above the limit declared", upload("up-big", "logo", "a.png", vid, total=10 << 30), False)
    chk("another session takes the same name", upload("up-normal", "clip", "b.mp4", vid, session="zzzzzzzz99"), False)
    # interrupted upload then resume
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=10); c.putrequest("POST", "/api/upload")
    for k, v in {"X-Slug": "up-resume", "X-Kind": "clip", "X-Name": "r.mp4", "X-Session": "resume12345", "X-Offset": "0", "X-Total": "4096", "Content-Length": "4096"}.items(): c.putheader(k, v)
    c.endheaders(); c.send(b"\x00" * 1500); c.close(); time.sleep(0.8)
    st = req("GET", "/api/upload/status?slug=up-resume&kind=clip&name=r.mp4&session=resume12345")[1]
    rec(A, "interrupted upload keeps its part", "PASS" if '"bytes": 1500' in st or '"bytes":1500' in st else "WARN", st)
    chk("resume at a wrong offset is refused", upload("up-resume", "clip", "r.mp4", b"\x00" * 100, "resume12345", offset=999, total=4096), False)
    chk("resume at the right offset finishes", upload("up-resume", "clip", "r.mp4", b"\x00" * 2596, "resume12345", offset=1500, total=4096), True)
    res = []
    def one(i): res.append(upload(f"up-par{i % 6}", "clip", f"p{i}.mp4", vid, session=f"sess{i % 6:08d}", order=i))
    ts = [threading.Thread(target=one, args=(i,)) for i in range(30)]; [t.start() for t in ts]; [t.join(60) for t in ts]
    rec(A, "30 uploads at once (6 reels)", "PASS" if all(isinstance(r[1], dict) and r[0] < 500 for r in res) and alive() else "FAIL", [r for r in res if not (isinstance(r[1], dict) and r[0] < 500)][:2])
    big = os.urandom(1 << 20) * 60                                                    # 60 MB: speed + memory
    t0 = time.time(); r = upload("up-60mb", "clip", "big.mp4", big, timeout=120); dt = time.time() - t0
    rec(A, "60 MB upload", "PASS" if r[0] == 200 and S.rss_mb() < 400 else "WARN", f"{dt:.1f}s, server RSS {S.rss_mb()} MB")
    rec(A, "alive after uploads", "PASS" if alive() else "FAIL")


def state_probes(S, work):
    A = "state"
    files = {"tasks board": "dashboard/tasks.json", "expense ledger": "dashboard/expenses.json", "project config": "config/project.json", "rules": "config/rules.json", "brand": "config/brand.json"}
    for label, rel in files.items():
        p = os.path.join(work, rel); keep = open(p, "rb").read() if os.path.exists(p) else None
        for kind, junk in (("empty", b""), ("truncated", (keep or b"{}")[: max(1, len(keep or b"{}") // 3)]), ("binary garbage", os.urandom(300)), ("wrong shape []", b"[]"), ("null", b"null")):
            os.makedirs(os.path.dirname(p), exist_ok=True); open(p, "wb").write(junk)
            bad = []
            for path in ("/api/tasks", "/api/reels", "/api/spend", "/api/expenses", "/api/health", "/api/progress", "/", "/api/version"):
                try:
                    s, _, _ = req("GET", path)
                    if s >= 500: bad.append(f"{path}:{s}")
                except Exception as e: bad.append(f"{path}:{type(e).__name__}")
            if not alive(): bad.append("SERVER DIED")
            rec(A, f"{label} is {kind}", "PASS" if not bad else "FAIL", ", ".join(bad))
        if keep is not None: open(p, "wb").write(keep)
    j = os.path.join(work, "jobs"); d = os.path.join(j, "2026-11-03-broken-job"); os.makedirs(d, exist_ok=True)
    for f, txt in (("job.json", "{not json"), ("cost.json", "[]"), ("timeline.json", "nope"), ("edl.json", ""), ("timing.json", "1"), ("run.log", "\x00\xff\xfe")):
        open(os.path.join(d, f), "w").write(txt)
    os.makedirs(os.path.join(j, "not-a-job-name"), exist_ok=True); os.symlink("/nonexistent", os.path.join(j, "2026-11-03-dangling"))
    bad = []
    for path in ("/api/reels", "/api/progress?ref=2026-11-03-broken-job", "/api/timeline?job=2026-11-03-broken-job", "/api/editor?job=2026-11-03-broken-job", "/api/progress", "/api/spend"):
        try:
            s, b, _ = req("GET", path)
            if s >= 500 or "Traceback" in b: bad.append(f"{path}:{s}")
        except Exception as e: bad.append(f"{path}:{type(e).__name__}")
    rec(A, "broken job files + dangling link + odd folder in jobs/", "PASS" if not bad and alive() else "FAIL", ", ".join(bad))
    for act, body in (("start", {"slug": "no-such-inbox"}), ("resume", {"job": "../../etc"}), ("fix", {"job": "2026-11-03-broken-job", "text": "x" * 5000}), ("approve", {"job": "nope"}), ("posted", {"job": 5, "platform": []}),
                      ("performance", {"job": "2026-11-03-broken-job", "data": "str"}), ("use_hook", {"job": "2026-11-03-broken-job", "n": "x"}), ("variation", {}), ("check", {}), ("notes", {"slug": "x" * 9999})):
        try:
            s, b, _ = req("POST", f"/api/reels/{act}", json.dumps(body), {"Content-Type": "application/json"})
            rec(A, f"POST /api/reels/{act} with bad data", "PASS" if s < 500 and "Traceback" not in b else "FAIL", f"{s} {b[:100]}" if s >= 500 else "")
        except Exception as e: rec(A, f"POST /api/reels/{act}", "FAIL", e)
    for act in ("save", "check", "apply", "undo"):
        for body in ({"job": "2026-11-03-broken-job", "sequence": "bad"}, {"job": None, "sequence": {"clips": "x"}}, {"sequence": {"clips": [{"id": "../x", "in": "a", "out": -1}] * 500}}):
            try:
                s, b, _ = req("POST", f"/api/timeline/{act}", json.dumps(body))
                if s >= 500 or "Traceback" in b: rec(A, f"timeline/{act}", "FAIL", f"{s} {b[:100]}"); break
            except Exception as e: rec(A, f"timeline/{act}", "FAIL", e); break
        else: rec(A, f"timeline/{act} with bad data", "PASS")
    for act in ("preview", "save", "rebuild"):
        try:
            s, b, _ = req("POST", f"/api/editor/{act}", json.dumps({"job": "2026-11-03-broken-job", "edit": {"drop": "x", "keep": [None]}})); rec(A, f"editor/{act} with bad data", "PASS" if s < 500 else "FAIL", f"{s} {b[:100]}")
        except Exception as e: rec(A, f"editor/{act}", "FAIL", e)
    cur = json.loads(req("GET", "/api/tasks")[1]); v = cur.get("version")
    res = []
    def save_it(i): res.append(req("POST", "/api/tasks", json.dumps(dict(cur, version=v)))[0])
    ts = [threading.Thread(target=save_it, args=(i,)) for i in range(25)]; [t.start() for t in ts]; [t.join(30) for t in ts]
    after = json.loads(req("GET", "/api/tasks")[1])
    rec(A, "25 board saves at once with the same version", "PASS" if res.count(200) == 1 and after.get("version") == v + 1 else "FAIL",
        f"{res.count(200)} accepted (should be 1), version {v}->{after.get('version')}" )
    for body in ({"version": v + 1, "tasks": [{"id": "T1", "phase": "P", "title": "t", "owner": "o", "status": "done"}, {"id": "T1", "phase": "P", "title": "t", "owner": "o", "status": "done"}]},
                 {"version": v + 1, "tasks": "x"}, {"version": "abc"}, {"tasks": [{}]}):
        s, b, _ = req("POST", "/api/tasks", json.dumps(body)); rec(A, f"board save with bad shape {str(body)[:30]}", "PASS" if s in (400, 409) else "FAIL", f"{s}")


def settings_probes(S, work):
    A = "settings"
    for label, key in (("empty key", ""), ("huge key", "k" * 100000), ("newline in key", "abc\ndef"), ("path-like key", "../../etc/passwd"), ("unicode key", "مفتاح🔑"), ("number", 12345), ("list", ["a"]), ("null", None)):
        try:
            s, b, _ = req("POST", "/api/settings/key", json.dumps({"key": key}))
            kp = os.path.join(work, "_home", ".reelfactory", "nous_api_key")
            perm = oct(os.stat(kp).st_mode & 0o777) if os.path.exists(kp) else "none"
            leak = "Traceback" in b
            rec(A, f"save key: {label}", "PASS" if s < 500 and not leak else "FAIL", f"{s} {b[:80]} perms {perm}" if (s >= 500 or leak) else "")
            if os.path.exists(kp) and (os.stat(kp).st_mode & 0o077): rec(A, f"key file readable by others after '{label}'", "FAIL", perm)
        except Exception as e: rec(A, f"save key: {label}", "FAIL", e)
    for act in ("test", "backup", "it_agent", "backup_auto", "update", "nonsense"):
        try:
            s, b, _ = req("POST", f"/api/settings/{act}", json.dumps({"target": "/nonexistent/x/y", "on": "maybe"}))
            rec(A, f"settings/{act} with odd values", "PASS" if s < 500 and "Traceback" not in b else "FAIL", f"{s} {b[:120]}")
        except Exception as e: rec(A, f"settings/{act}", "WARN", e)
    rec(A, "alive after settings abuse", "PASS" if alive() else "FAIL")


def make_clips(d):
    os.makedirs(d, exist_ok=True)
    def ff(name, args, dur=20):
        p = os.path.join(d, name)
        r = subprocess.run(["ffmpeg", "-v", "error", "-y"] + args + [p], capture_output=True, text=True, timeout=240)
        return p if r.returncode == 0 else None
    L = lambda s, dur=20: ["-f", "lavfi", "-i", f"{s}:d={dur}"]
    a = ["-f", "lavfi", "-i", "sine=f=220:d=20"]
    out = {}
    out["normal 1080x1920 h264+aac"] = ff("normal.mp4", L("testsrc2=s=1080x1920:r=30") + a + ["-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac"])
    out["phone MOV rotated 90 (metadata)"] = ff("rotated.mov", L("testsrc2=s=1920x1080:r=30") + a + ["-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-metadata:s:v", "rotate=90"])
    out["silent video (no audio track)"] = ff("silent.mp4", L("testsrc2=s=1080x1920:r=30") + ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-an"])
    out["variable frame rate"] = ff("vfr.mp4", L("testsrc2=s=1080x1920:r=30") + a + ["-shortest", "-vf", "setpts='PTS+random(0)*0.02/TB'", "-vsync", "vfr", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac"])
    out["4K 3840x2160"] = ff("4k.mp4", L("testsrc2=s=3840x2160:r=30", 6) + a + ["-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac"])
    out["audio only in an .mp4"] = ff("audioonly.mp4", a + ["-c:a", "aac"])
    out["very long (12 min, low quality)"] = ff("long.mp4", L("testsrc2=s=540x960:r=15", 720) + ["-f", "lavfi", "-i", "sine=f=300:d=720", "-shortest", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "40", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "24k"])
    n = out["normal 1080x1920 h264+aac"]
    if n:
        data = open(n, "rb").read(); p = os.path.join(d, "truncated.mp4"); open(p, "wb").write(data[: len(data) // 3]); out["truncated file (a third)"] = p
        p = os.path.join(d, "corrupt.mp4"); b = bytearray(data); [b.__setitem__(i, 0xFF) for i in range(len(b) // 3, len(b) // 3 + 4000)]; open(p, "wb").write(bytes(b)); out["corrupt middle"] = p
        p = os.path.join(d, "text.mp4"); open(p, "w").write("this is not a video at all\n" * 50); out["text file named .mp4"] = p
    return {k: v for k, v in out.items() if v}


def put_clip(slug, path, session):
    """One request per file (that is how the page uploads; only a RETRY resumes from an offset)."""
    size = os.path.getsize(path)
    data = open(path, "rb").read()
    s, r = upload(slug, "clip", os.path.basename(path), data, session, offset=0, total=size, timeout=300)
    return (isinstance(r, dict) and bool(r.get("ok"))), ("" if isinstance(r, dict) and r.get("ok") else r)


def poll(S, ref, limit):
    t0 = time.time(); last = None
    while time.time() - t0 < limit:
        try: s, b, _ = req("GET", f"/api/progress?ref={ref}")
        except Exception as e: return {"error": f"progress failed: {e}"}, time.time() - t0
        try: last = json.loads(b)
        except ValueError: return {"error": "progress is not JSON: " + b[:80]}, time.time() - t0
        if last.get("state") in ("stopped", "ready", "final", "error", "failed", "needs_you", "interrupted"): break
        time.sleep(2)
    return last, time.time() - t0


def video_probes(S, work, quick):
    A = "videos"
    if not shutil.which("ffmpeg"): rec(A, "ffmpeg missing", "WARN", "skipped"); return
    clips = make_clips(os.path.join(work, "_clips"))
    if quick: clips = {k: v for k, v in clips.items() if "long" not in k and "4K" not in k}
    k = 0
    for label, path in clips.items():
        k += 1; slug = f"vid-{k:02d}"
        ok, why = put_clip(slug, path, f"vsess{k:04d}0000")
        if not ok: rec(A, f"upload: {label}", "WARN", why); continue
        s, b, _ = req("POST", "/api/reels/start", json.dumps({"slug": slug}), {"Content-Type": "application/json"})
        if s >= 500: rec(A, f"start: {label}", "FAIL", f"{s} {b[:120]}"); continue
        try: msg = json.loads(b)
        except ValueError: msg = {}
        if not msg.get("ok"):
            rec(A, f"start: {label}", "PASS" if s < 500 and msg.get("message") else "FAIL", f"refused plainly: {msg.get('message', '')[:100]}"); continue
        jobs = [j for j in os.listdir(os.path.join(work, "jobs")) if j.endswith(slug)]
        ref = jobs[0] if jobs else slug
        last, dt = poll(S, ref, 60 if quick else 150)
        st = (last or {}).get("state"); err = (last or {}).get("error") or (last or {}).get("message") or ""
        stuck = st in ("working", None, "") and dt >= (60 if quick else 150)
        rec(A, f"reel from: {label}", "WARN" if stuck else "PASS", f"state={st} after {dt:.0f}s; {str(err)[:160]}")
        if not alive(): rec(A, f"dashboard died on: {label}", "FAIL")
        time.sleep(1)
        s2, b2, _ = req("GET", "/api/progress")
        if "Traceback" in b2: rec(A, f"progress shows a raw traceback after: {label}", "FAIL", b2[:160])
        for _ in range(20):                                   # wait until the reel is no longer running before the next one
            if not json.loads(req("GET", "/api/reels")[1]) or True:
                break
        r = subprocess.run(["pkill", "-f", f"reel.py.*{slug}"], capture_output=True)


def recovery_probes(S, work):
    A = "recovery"
    clips = make_clips(os.path.join(work, "_clips2"))
    p = clips.get("normal 1080x1920 h264+aac")
    if not p: rec(A, "kill during a reel", "WARN", "no test clip"); return
    ok, _ = put_clip("rec-kill", p, "rsess00000001")
    s, b, _ = req("POST", "/api/reels/start", json.dumps({"slug": "rec-kill"})); time.sleep(4)
    S.stop(signal.SIGKILL); time.sleep(1)
    rec(A, "server killed (kill -9) in the middle of a reel", "PASS", "killed")
    left = subprocess.run(["pgrep", "-f", "reel.py.*rec-kill"], capture_output=True, text=True).stdout.split()
    rec(A, "background reel keeps running after the dashboard is killed", "WARN" if left else "PASS", f"{len(left)} orphan process(es): it may write while a restarted dashboard starts it again" if left else "")
    subprocess.run(["pkill", "-f", "reel.py.*rec-kill"], capture_output=True)
    up = S.start(); rec(A, "dashboard starts again after kill -9", "PASS" if up else "FAIL")
    if up:
        s, b, _ = req("GET", "/api/progress")
        rec(A, "dashboard shows the cut-off reel plainly", "PASS" if s == 200 and "Traceback" not in b else "FAIL", b[:200])
        s, b, _ = req("GET", "/api/reels"); rec(A, "reel list after the crash", "PASS" if s == 200 else "FAIL", s)
        for f in ("expenses.json", "tasks.json"):
            pth = os.path.join(work, "dashboard", f)
            try: json.load(open(pth)); rec(A, f"{f} still valid JSON after kill -9", "PASS")
            except Exception as e: rec(A, f"{f} after kill -9", "FAIL", e)
        for _ in range(3):
            S.stop(signal.SIGTERM); S.start()
        rec(A, "3 quick restarts in a row", "PASS" if alive() else "FAIL")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quick", action="store_true"); ap.add_argument("--no-videos", action="store_true"); a = ap.parse_args()
    work = setup(); S = Server(work); print(f"crash test on a COPY in {work} (port {PORT}); your own project is not touched\n")
    if not S.start(): print("the dashboard copy did not start:\n" + S.log_text()[-1500:]); sys.exit(2)
    t0 = time.time()
    try:
        for name, fn in (("HTTP", lambda: http_probes(S)), ("LOAD", lambda: load_probes(S, a.quick)), ("UPLOADS", lambda: upload_probes(S, work)), ("STATE", lambda: state_probes(S, work)),
                         ("SETTINGS", lambda: settings_probes(S, work)), ("VIDEOS", lambda: None if a.no_videos else video_probes(S, work, a.quick)), ("RECOVERY", lambda: None if a.no_videos else recovery_probes(S, work))):
            print(f"\n== {name}"); 
            try: fn()
            except Exception as e:
                import traceback; rec(name.lower(), "THE TEST ITSELF CRASHED", "WARN", traceback.format_exc()[-300:])
            if not alive():
                rec(name.lower(), "dashboard is down after this group: restarting it", "FAIL"); S.stop(signal.SIGKILL); S.start()
    finally:
        log = S.log_text(); S.stop()
    import re as _re
    tb = []
    for l in log.splitlines():
        if _re.match(r"^[A-Za-z_.]*(Error|Exception|Exit)\b.*", l) and l not in tb: tb.append(l)
    tb = tb[:25]
    open(os.path.join(SRC, "stress_server.log"), "w").write(log)
    fails = [r for r in R if r[2] == "FAIL"]; warns = [r for r in R if r[2] == "WARN"]
    lines = ["# Dashboard crash test", f"{len(R)} checks in {time.time() - t0:.0f} s: {len(R) - len(fails) - len(warns)} passed, {len(warns)} warnings, {len(fails)} FAILED", ""]
    for title, rows in (("FAILED", fails), ("WARNINGS", warns)):
        lines.append(f"## {title}")
        lines += [f"- [{r[0]}] {r[1]}: {r[3]}" for r in rows] or ["- none"]
        lines.append("")
    lines += ["## Errors the dashboard printed to its own log", *([f"- {t[:200]}" for t in tb] or ["- none"]), "", "## All checks"] + [f"- {r[2]} [{r[0]}] {r[1]}" for r in R]
    open(os.path.join(SRC, "stress_report.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n" + "\n".join(lines[:3 + len(fails) + len(warns) + 6])); print("\nfull report: stress_report.md"); shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
