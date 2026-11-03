#!/usr/bin/env python3
"""Reel Factory control dashboard — local server (Python standard library only).

    python3 dashboard/serve.py            then open http://127.0.0.1:8766

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
import backup_api  # noqa: E402
import it_agent  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
TASKS = os.path.join(HERE, "tasks.json")
EXPENSES = os.path.join(HERE, "expenses.json")
BACKUPS = os.path.join(HERE, ".backups")
STATUSES = {"todo", "in_progress", "review", "blocked", "done"}
PORT = int(os.environ.get("RF_DASH_PORT", "8766"))


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
    tmp = f"{TASKS}.{os.getpid()}.{threading.get_ident()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1, ensure_ascii=False)
    os.replace(tmp, TASKS)


PAGES = {"/make.html", "/index.html", "/edit.html", "/timeline.html"}      # the only static files served: no source code, ledger or backups
_board_lock = threading.Lock()                                                 # one board save at a time (check version, then write)


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        if isinstance(sys.exc_info()[1], (BrokenPipeError, ConnectionResetError, TimeoutError)):
            return                                                             # a browser tab closed mid-answer: not an error
        super().handle_error(request, client_address)


class H(SimpleHTTPRequestHandler):
    timeout = 120                  # a connection that sends nothing for 2 minutes is dropped (idle or half-open sockets must not pile up forever)

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
        try:
            self._get()
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            self.close_connection = True
        except Exception as e:                                               # noqa: BLE001 - the page gets a plain message, never a dropped connection
            print("GET error:", self.path[:120], type(e).__name__, e, flush=True)
            self.close_connection = True
            try: self.send_json(500, {"ok": False, "message": "something went wrong on this page; try again, and tell Claude if it repeats"})
            except Exception: pass                                           # noqa: BLE001

    def do_POST(self):
        try:
            self._post()
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            self.close_connection = True
        except Exception as e:                                               # noqa: BLE001
            print("POST error:", self.path[:120], type(e).__name__, e, flush=True)
            self.close_connection = True
            try: self.send_json(500, {"ok": False, "message": "something went wrong; nothing was changed. Try again, and tell Claude if it repeats"})
            except Exception: pass                                           # noqa: BLE001

    def _get(self):
        q = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
        if self.path.startswith("/api/upload/status"):
            return self.send_json(200, reels_api.upload_status(q.get("slug"), q.get("kind"), unquote(q.get("name", "")), q.get("session"),
                                                               int(q.get("order") or 0) if str(q.get("order") or "0").isdigit() else 0))
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
            v = settings_api.version()
            if q.get("check") == "1":
                v["update_ready"] = settings_api.update_ready()
            return self.send_json(200, v)
        if self.path.startswith("/api/health"):
            return self.send_json(200, settings_api.health())
        if self.path.startswith("/api/timeline"):
            ok, data = reels_api.timeline(q.get("job", ""))
            return self.send_json(200 if ok else 409, data if ok else {"ok": False, "message": data})
        if self.path.startswith("/api/editor"):
            ok, data = reels_api.editor(q.get("job", ""))
            return self.send_json(200 if ok else 409, data if ok else {"ok": False, "message": data})
        if self.path.startswith("/api/backup"):
            return self.send_json(200, backup_api.status())
        if self.path.startswith("/api/it"):
            return self.send_json(200, it_agent.status())
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
        if urlparse(self.path).path not in PAGES:
            return self.send_json(404, {"error": "not found"})
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
        return o in (None, f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}", f"http://reelfactory.localhost:{PORT}")

    def _post(self):
        if not self.same_origin():
            self.close_connection = True
            return self.send_json(403, {"ok": False, "message": "not allowed"})
        if self.path.startswith("/api/settings/"):
            try:
                n = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(min(n, 4096)).decode("utf-8") or "{}")
                if not isinstance(body, dict): raise ValueError("not an object")
            except Exception:
                return self.send_json(400, {"ok": False, "message": "bad request"})
            action = self.path.split("/")[3].split("?")[0]
            if action == "key":
                ok, msg = settings_api.save_key(body.get("key"))
            elif action == "test":
                ok, msg = settings_api.test_key()
            elif action == "backup":
                ok, msg = backup_api.run(reels_api.ROOT, body.get("target") or None)
            elif action == "it_agent":
                ok, msg = it_agent.set_on(bool(body.get("on", True)))
            elif action == "backup_auto":
                ok, msg = backup_api.set_auto(body.get("on", True))
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
                offset = int(h.get("X-Offset", 0) or 0); total = int(h.get("X-Total", 0) or 0) or None
            except ValueError:
                return self.send_json(400, {"ok": False, "message": "bad upload headers"})
            ok, msg = reels_api.upload(h.get("X-Slug"), h.get("X-Kind"), unquote(h.get("X-Name", "")), h.get("X-Session"), n, self.rfile, order, offset, total)
            if not ok:
                self.close_connection = True               # the unread body must not be parsed as the next request
            return self.send_json(200 if ok else 409, {"ok": ok, "message": msg})
        if self.path.startswith("/api/timeline/"):
            try:
                n = int(self.headers.get("Content-Length", 0))
                if n > 2_000_000:
                    raise ValueError("too big")
                body = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
                if not isinstance(body, dict): raise ValueError("not an object")
            except Exception:
                return self.send_json(400, {"ok": False, "message": "bad request"})
            action = self.path.split("/")[3].split("?")[0]
            job, seq = body.get("job"), body.get("sequence")
            if action == "save":
                ok, msg, clean = reels_api.timeline_save(job, seq)
                return self.send_json(200 if ok else 409, {"ok": ok, "message": msg, "sequence": clean})
            if action == "check":
                ok, data = reels_api.timeline_check(job, seq)
                return self.send_json(200 if ok else 409, {"ok": ok, "markers": data} if ok else {"ok": False, "message": data})
            if action == "apply":
                ok, msg = reels_api.timeline_apply(job, seq)
                return self.send_json(200 if ok else 409, {"ok": ok, "message": msg})
            if action == "undo":
                ok, msg = reels_api.timeline_undo(job)
                return self.send_json(200 if ok else 409, {"ok": ok, "message": msg})
            return self.send_json(404, {"ok": False, "message": "unknown action"})
        if self.path.startswith("/api/editor/"):
            try:
                n = int(self.headers.get("Content-Length", 0))
                if n > 2_000_000:
                    raise ValueError("too big")
                body = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
                if not isinstance(body, dict): raise ValueError("not an object")
            except Exception:
                return self.send_json(400, {"ok": False, "message": "bad request"})
            action = self.path.split("/")[3].split("?")[0]
            if action == "preview":
                ok, data = reels_api.editor(body.get("job"), body.get("edit") or {})
                return self.send_json(200 if ok else 409, data if ok else {"ok": False, "message": data})
            if action == "save":
                ok, msg, notes = reels_api.editor_save(body.get("job"), body.get("edit") or {})
                return self.send_json(200 if ok else 409, {"ok": ok, "message": msg, "notes": notes})
            if action == "rebuild":
                ok, msg = reels_api.rebuild(body.get("job"))
                return self.send_json(200 if ok else 409, {"ok": ok, "message": msg})
            return self.send_json(404, {"ok": False, "message": "unknown action"})
        if self.path.startswith("/api/reels/"):
            try:
                n = int(self.headers.get("Content-Length", 0))
                if not 0 <= n <= 1_000_000: raise ValueError("too big")
                body = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
                if not isinstance(body, dict): raise ValueError("not an object")
            except Exception:
                return self.send_json(400, {"error": "bad JSON"})
            action = self.path.split("/")[3].split("?")[0]
            T = lambda k: body.get(k) if isinstance(body.get(k), str) else ""            # text fields: anything else counts as empty
            data = body.get("data") if isinstance(body.get("data"), dict) else {}
            fn = {"start": lambda: reels_api.start(T("slug")), "resume": lambda: reels_api.resume(T("job")),
                  "fix": lambda: reels_api.fix(T("job"), T("text")), "approve": lambda: reels_api.approve(T("job")),
                  "reveal": lambda: reels_api.reveal(T("job")),
                  "use_version": lambda: reels_api.use_version(T("job"), body.get("n")),
                  "use_hook": lambda: reels_api.use_hook(T("job"), body.get("n")),
                  "ask_doctor": lambda: reels_api.ask_doctor(T("job")),
                  "variation": lambda: reels_api.make_variation(T("job"), T("id")),
                  "cover_reset": lambda: reels_api.cover_reset(T("job")),
                  "performance": lambda: reels_api.save_performance(T("job"), data),
                  "posted": lambda: reels_api.save_posted(T("job"), T("platform")),
                  "check": lambda: reels_api.check_name(T("slug"), T("session")),
                  "notes": lambda: reels_api.save_notes(T("slug"), T("session"), T("text"), body.get("brief") if isinstance(body.get("brief"), dict) else None)}.get(action)
            if not fn:
                return self.send_json(404, {"error": "unknown action"})
            ok, msg = fn()
            return self.send_json(200 if ok else 409, {"ok": ok, "message": msg})
        if not self.path.startswith("/api/tasks"):
            return self.send_json(404, {"error": "not found"})
        try:
            n = int(self.headers.get("Content-Length", 0))
            if not 0 <= n <= 8_000_000: raise ValueError("too big")
            d = json.loads(self.rfile.read(n).decode("utf-8"))
            if not isinstance(d, dict): raise ValueError("not an object")
        except Exception as e:
            return self.send_json(400, {"error": f"bad JSON: {e}"})
        with _board_lock:                                                    # check the version and write as ONE step: two saves can never both win
            cur = load(TASKS, {"version": 0})
            if not isinstance(cur, dict): cur = {"version": 0}
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


def daily_backup():
    """Once a day while the dashboard runs: back up results and comments (Settings → Backup). Never stops the server."""
    time.sleep(60)
    while True:
        try:
            if backup_api.due() and backup_api.targets():
                ok, msg = backup_api.run(reels_api.ROOT)
                print("backup:", msg, flush=True)
        except Exception as e:          # noqa: BLE001
            print("backup skipped:", e, flush=True)
        time.sleep(3600)

if __name__ == "__main__":
    if not os.path.exists(TASKS):
        sys.exit(f"missing {TASKS}")
    print(f"Reel Factory dashboard: http://127.0.0.1:{PORT}  (Ctrl+C to stop)")
    Server.allow_reuse_address = True
    SERVER = Server(("127.0.0.1", PORT), H)
    threading.Thread(target=daily_backup, daemon=True).start()
    threading.Thread(target=it_agent.watch, daemon=True).start()
    SERVER.serve_forever()
