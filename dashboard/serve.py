#!/usr/bin/env python3
"""Reel Factory control dashboard — local server (Python standard library only).

    python3 dashboard/serve.py            then open http://127.0.0.1:8765

Serves index.html and keeps tasks.json as the single task list for Hesham, Claude and Hermes.
Every save makes a backup in dashboard/.backups/ (last 50 kept). A save is refused if someone
else (e.g. Hermes) changed the file since you loaded it, so nobody's edit is lost silently.
Listens on 127.0.0.1 only: nothing is reachable from other machines.
"""
import json, os, shutil, sys, threading, time
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import unquote, urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reels_api  # noqa: E402
import settings_api  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
TASKS = os.path.join(HERE, "tasks.json")
EXPENSES = os.path.join(HERE, "expenses.json")
BACKUPS = os.path.join(HERE, ".backups")
STATUSES = {"todo", "in_progress", "review", "blocked", "done"}
PORT = int(os.environ.get("RF_DASH_PORT", "8765"))


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def check(d):
    if not isinstance(d, dict) or not isinstance(d.get("tasks"), list):
        return "tasks.json must be an object with a 'tasks' list"
    ids = set()
    for t in d["tasks"]:
        for k in ("id", "phase", "title", "owner", "status"):
            if not t.get(k):
                return f"task {t.get('id', '?')} is missing '{k}'"
        if t["status"] not in STATUSES:
            return f"task {t['id']}: unknown status '{t['status']}'"
        if t["id"] in ids:
            return f"duplicate task id {t['id']}"
        ids.add(t["id"])
    return None


def save(d):
    os.makedirs(BACKUPS, exist_ok=True)
    if os.path.exists(TASKS):
        shutil.copy2(TASKS, os.path.join(BACKUPS, time.strftime("tasks-%Y%m%d-%H%M%S.json")))
        old = sorted(os.listdir(BACKUPS))
        for f in old[:-50]:
            os.remove(os.path.join(BACKUPS, f))
    tmp = TASKS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1, ensure_ascii=False)
    os.replace(tmp, TASKS)


class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=HERE, **k)

    def log_message(self, *a):
        pass

    def send_json(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def send_file(self, path, ctype):
        size = os.path.getsize(path); rng = self.headers.get("Range")
        start, end = 0, size - 1
        if rng and rng.startswith("bytes="):
            a, _, b = rng[6:].partition("-")
            start = int(a) if a else max(0, size - int(b)); end = int(b) if a and b else end
            self.send_response(206); self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        else:
            self.send_response(200)
        self.send_header("Content-Type", ctype); self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1)); self.send_header("Cache-Control", "no-store"); self.end_headers()
        with open(path, "rb") as f:
            f.seek(start); left = end - start + 1
            while left > 0:
                chunk = f.read(min(1 << 20, left))
                if not chunk: break
                self.wfile.write(chunk); left -= len(chunk)

    def do_GET(self):
        q = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
        if self.path.startswith("/api/watching"):
            return self.send_json(200, {"watching": reels_api.watching(q.get("ref", ""))})
        if self.path.startswith("/api/progress"):
            p = reels_api.progress(q.get("ref", ""))
            if q.get("notify") == "1":
                reels_api.mark_seen(p.get("job"), p.get("slug"), p.get("ref"))
            return self.send_json(200, p)
        if self.path.startswith("/api/events"):
            return self.stream_progress(q.get("ref", ""), notify=q.get("notify") == "1")
        if self.path.startswith("/api/version"):
            return self.send_json(200, settings_api.version())
        if self.path.startswith("/api/health"):
            return self.send_json(200, settings_api.health())
        if self.path.startswith("/api/root"):
            return self.send_json(200, {"root": os.path.realpath(reels_api.ROOT)})
        if self.path.startswith("/api/reels"):
            return self.send_json(200, reels_api.list_reels())
        if self.path.startswith("/media/"):
            p = reels_api.media_path(unquote(self.path[7:].split("?")[0]))
            if not p:
                return self.send_json(404, {"error": "not found"})
            ctype = {".jpg": "image/jpeg", ".mp4": "video/mp4", ".mov": "video/quicktime", ".srt": "text/plain; charset=utf-8"}.get(os.path.splitext(p)[1], "image/jpeg")
            return self.send_file(p, ctype)
        if self.path.startswith("/api/tasks"):
            return self.send_json(200, load(TASKS, {"tasks": [], "version": 0}))
        if self.path.startswith("/api/performance.csv"):
            b = reels_api.performance_csv().encode("utf-8")
            self.send_response(200); self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="reel_results.csv"')
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b); return
        if self.path.startswith("/api/performance"):
            return self.send_json(200, {"reels": reels_api.performance(q.get("job") or None), "fields": {k: v[0] for k, v in reels_api.PERF_FIELDS.items()}})
        if self.path.startswith("/api/spend"):
            return self.send_json(200, reels_api.spend())
        if self.path.startswith("/api/expenses"):
            return self.send_json(200, load(EXPENSES, {"rows": []}))
        if self.path in ("/", ""):
            self.path = "/make.html"
        return super().do_GET()

    def stream_progress(self, ref, every=1.0, limit=4 * 3600, notify=False):
        """Server-Sent Events: one progress object per second until the run ends (or the tab closes)."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream"); self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive"); self.end_headers()
        t0 = time.time()
        try:
            while time.time() - t0 < limit:
                p = reels_api.progress(ref)
                if notify:
                    reels_api.mark_seen(p.get("job"), p.get("slug"), p.get("ref"))
                self.wfile.write(b"data: " + json.dumps(p, ensure_ascii=False).encode() + b"\n\n"); self.wfile.flush()
                if p.get("state") != "running":
                    break
                time.sleep(every)
        except (BrokenPipeError, ConnectionResetError):
            pass
        self.close_connection = True

    def same_origin(self):
        """Only this page may change settings (a website you visit can't post to the dashboard)."""
        o = self.headers.get("Origin")
        return o in (None, f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}")

    def do_POST(self):
        if not self.same_origin():
            self.close_connection = True
            return self.send_json(403, {"ok": False, "message": "not allowed"})
        if self.path.startswith("/api/settings/"):
            try:
                n = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(min(n, 4096)).decode("utf-8") or "{}")
            except Exception:
                return self.send_json(400, {"ok": False, "message": "bad request"})
            action = self.path.split("/")[3].split("?")[0]
            if action == "key":
                ok, msg = settings_api.save_key(body.get("key"))
            elif action == "test":
                ok, msg = settings_api.test_key()
            elif action == "update":
                ok, msg, restart = settings_api.update(reels_api.busy())
                self.send_json(200 if ok else 409, {"ok": ok, "message": msg, "restart": restart})
                if restart:
                    threading.Thread(target=restart_self, daemon=True).start()
                return
            else:
                return self.send_json(404, {"ok": False, "message": "unknown action"})
            return self.send_json(200 if ok else 400, {"ok": ok, "message": msg})
        if self.path.startswith("/api/cover"):
            h = self.headers
            try:
                n = int(h.get("Content-Length", 0))
            except ValueError:
                return self.send_json(400, {"ok": False, "message": "bad upload headers"})
            ok, msg = reels_api.cover_upload(h.get("X-Job"), h.get("X-Kind"), unquote(h.get("X-Name", "")), n, self.rfile)
            if not ok:
                self.close_connection = True
            return self.send_json(200 if ok else 409, {"ok": ok, "message": msg})
        if self.path.startswith("/api/upload"):
            h = self.headers
            try:
                n = int(h.get("Content-Length", 0)); order = int(h.get("X-Order", 0) or 0)
            except ValueError:
                return self.send_json(400, {"ok": False, "message": "bad upload headers"})
            ok, msg = reels_api.upload(h.get("X-Slug"), h.get("X-Kind"), unquote(h.get("X-Name", "")), h.get("X-Session"), n, self.rfile, order)
            if not ok:
                self.close_connection = True               # the unread body must not be parsed as the next request
            return self.send_json(200 if ok else 409, {"ok": ok, "message": msg})
        if self.path.startswith("/api/reels/"):
            try:
                n = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
            except Exception:
                return self.send_json(400, {"error": "bad JSON"})
            action = self.path.split("/")[3].split("?")[0]
            fn = {"start": lambda: reels_api.start(body.get("slug")), "resume": lambda: reels_api.resume(body.get("job")),
                  "fix": lambda: reels_api.fix(body.get("job"), body.get("text")), "approve": lambda: reels_api.approve(body.get("job")),
                  "reveal": lambda: reels_api.reveal(body.get("job")),
                  "cover_reset": lambda: reels_api.cover_reset(body.get("job")),
                  "performance": lambda: reels_api.save_performance(body.get("job"), body.get("data")),
                  "check": lambda: reels_api.check_name(body.get("slug"), body.get("session")),
                  "notes": lambda: reels_api.save_notes(body.get("slug"), body.get("session"), body.get("text"))}.get(action)
            if not fn:
                return self.send_json(404, {"error": "unknown action"})
            ok, msg = fn()
            return self.send_json(200 if ok else 409, {"ok": ok, "message": msg})
        if not self.path.startswith("/api/tasks"):
            return self.send_json(404, {"error": "not found"})
        try:
            n = int(self.headers.get("Content-Length", 0))
            d = json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception as e:
            return self.send_json(400, {"error": f"bad JSON: {e}"})
        cur = load(TASKS, {"version": 0})
        if d.get("version") != cur.get("version"):
            return self.send_json(409, {"error": "tasks.json changed since you loaded it (Hermes or another tab). Reload, then redo your change.",
                                        "current_version": cur.get("version")})
        err = check(d)
        if err:
            return self.send_json(400, {"error": err})
        d["version"] = (cur.get("version") or 0) + 1
        save(d)
        return self.send_json(200, {"ok": True, "version": d["version"]})


def restart_self(delay=1.0):
    """Start again with the new code (same command, same port). Under the auto-start agent launchd would also restart us."""
    time.sleep(delay)
    try:
        SERVER.server_close()
    except Exception:
        pass
    os.execv(sys.executable, [sys.executable, os.path.abspath(__file__)])


SERVER = None

if __name__ == "__main__":
    if not os.path.exists(TASKS):
        sys.exit(f"missing {TASKS}")
    print(f"Reel Factory dashboard: http://127.0.0.1:{PORT}  (Ctrl+C to stop)")
    ThreadingHTTPServer.allow_reuse_address = True
    SERVER = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    SERVER.serve_forever()
