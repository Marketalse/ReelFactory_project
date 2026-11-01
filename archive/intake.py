#!/usr/bin/env python3
"""intake.py - local landing for raw phone footage.
Zero dependencies (stdlib only). Run: python3 intake.py
Serves http://localhost:8007 and stores accepted files under ../inbox/.
Logs every decision to ../inbox/scripts/intake.log
"""
import hashlib
import logging
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # ~/Desktop/Reel-Factory
INBOX = ROOT / "inbox"
LOG = ROOT / "inbox" / "scripts" / "intake.log"
MAX_BYTES = 150 * 1024 * 1024                          # phone clips are big; 150 MB cap
BAD_NAME = re.compile(r"\.(py|sh|exe|app|bin|run|command)$", re.I)

INBOX.mkdir(parents=True, exist_ok=True)
LOG.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(filename=LOG, level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")


def digest(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()[:10]


class H(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _reply(self, code, body=b""):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._reply(200, b'{"ok":true,"note":"intake local server","url":"http://localhost:8007"}')

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BYTES:
                return self._reply(413, b'{"error":"too large"}')
            form = self.rfile.read(n)
            if b"filename" not in form:
                return self._reply(400, b'{"error":"no file"}')
            m = re.search(rb'filename="([^"]+)"', form)
            name = m.group(1).decode("utf-8", "replace") if m else "file"
            if BAD_NAME.search(name) or not name.strip():
                return self._reply(400, b'{"error":"blocked name"}')
            data = self.rfile.read(n - form.index(b"filename"))
            stamp = time.strftime("%Y-%m-%d-%H%M%S")
            out = INBOX / f"{stamp}__{name}"
            with open(out, "wb") as f:
                f.write(data)
            logging.info("accepted %s (%d bytes) sha=%s", out.name, len(data), digest(out))
            self._reply(200, ('{"ok":true,"saved":"%s"}' % out.name).encode())
        except Exception as e:
            logging.exception("intake error")
            self._reply(500, ('{"error":"%s"}' % e).encode())


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", 8007), H)
    print("intake listening on http://localhost:8007 ->", INBOX)
    srv.serve_forever()
