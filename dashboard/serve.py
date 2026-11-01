#!/usr/bin/env python3
"""Reel Factory control dashboard — local server (Python standard library only).

    python3 dashboard/serve.py            then open http://127.0.0.1:8765

Serves index.html and keeps tasks.json as the single task list for Hesham, Claude and Hermes.
Every save makes a backup in dashboard/.backups/ (last 50 kept). A save is refused if someone
else (e.g. Hermes) changed the file since you loaded it, so nobody's edit is lost silently.
Listens on 127.0.0.1 only: nothing is reachable from other machines.
"""
import json, os, shutil, sys, time
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

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

    def do_GET(self):
        if self.path.startswith("/api/tasks"):
            return self.send_json(200, load(TASKS, {"tasks": [], "version": 0}))
        if self.path.startswith("/api/expenses"):
            return self.send_json(200, load(EXPENSES, {"rows": []}))
        if self.path in ("/", ""):
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):
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


if __name__ == "__main__":
    if not os.path.exists(TASKS):
        sys.exit(f"missing {TASKS}")
    print(f"Reel Factory dashboard: http://127.0.0.1:{PORT}  (Ctrl+C to stop)")
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
