#!/usr/bin/env python3
"""Pre-UAT end-to-end harness. Runs the REAL pipeline (real ffmpeg, real HyperFrames render, real code) against a COPY of the project, with a
local MOCK of the AI service (no paid call is ever made) and a pre-seeded Whisper transcript (the speech model is not available offline here).
Everything that touches AI is therefore MOCK coverage; everything else is verified live."""
import argparse, json, os, random, re, resource, shutil, signal, subprocess, sys, tempfile, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SRC = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MOCK_PORT = 8791
NASTY = {"on": False, "repairs": 0}      # "nasty director": a plan like a real AI writes it (a card running past the end, an unknown block) and a repair answer that is a sentence
STATE = {"mode": "ok", "calls": 0, "by_stage": {}, "lock": threading.Lock(), "delay": 0.0, "fail_every": 0}
VOC = "يعني لما انت حاط بيج و تبيع بيه ما رقم تواصل وياك شنو تتصور الزبون راح يخسر طلب لان شغلك كله خدمة زبائن اعلان نتيجة مبيعات متجر توصيل شحن".split()


def words_for(dur, seed=1):
    r = random.Random(seed); t, out = 0.4, []
    while t < dur - 1.0:
        d = r.choice([0.22, 0.3, 0.38]); out.append({"text": r.choice(VOC), "start": round(t, 2), "end": round(t + d, 2)}); t += d + r.choice([0.06, 0.1, 0.14, 0.9 if r.random() < .06 else 0.1])
    return out


# ------------------------------------------------------------------ mock AI
def answer(text, nimg):
    def nums(p): return [int(x) for x in re.findall(p, text)]
    if "shot-logger" in text:
        n = int(re.search(r"Below are (\d+) still", text).group(1))
        return json.dumps([{"face": {"x": .3, "y": .2, "w": .4, "h": .2}, "eyes": "open", "energy": 3, "gesture": "none", "headroom": "ok", "bg": "low", "text": "", "usable": ["punch_in", "cut"], "note": "ok"} for _ in range(n)])
    if "story editor of an Iraqi" in text:
        lines = re.findall(r"^\[([\d.]+)-([\d.]+)\] (.+)$", text, re.M)
        dur = float(re.search(r"Take length: ([\d.]+)s", text).group(1)); hook = lines[0][2] if lines else "x"
        sel = [{"id": k, "range": [0.0, round(dur - 1.0, 1)], "label": f"candidate {k}", "hook_line": hook, "why": "mock", "style": "educational",
                "scores": {"relevance": 7, "clarity": 7, "delivery": 6, "novelty": 6, "fit": 7}, "hooks": [{"type": t, "line": hook} for t in ("curiosity", "problem", "direct")], "score": 7} for k in "ABC"]
        return json.dumps({"main_message": "a mock message", "audience": "business owners", "selects": sel})
    if "film editor of Hesham" in text:
        ids = [int(x) for x in re.findall(r"^(\d+) \[", text, re.M)] or [0]
        return json.dumps({"start": min(ids), "end": max(ids), "drops": [], "summary": "mock: nothing to remove"})
    if "story architect" in text:
        idx = [int(x) for x in re.findall(r"\((\d+)\)", text)] or [0]; n = max(idx) + 1; a = n // 3
        return json.dumps({"format": "explainer", "hook_word": 0, "concept": None, "sections": [
            {"from_word": 0, "to_word": a - 1, "kind": "step", "title_from": 1, "title_to": 2},
            {"from_word": a, "to_word": 2 * a - 1, "kind": "step", "title_from": a + 1, "title_to": a + 2},
            {"from_word": 2 * a, "to_word": n - 1, "kind": "point", "title_from": 2 * a + 1, "title_to": 2 * a + 2}]})
    if NASTY["on"] and "DIRECTOR of an automated reel" in text:
        idx = [int(x) for x in re.findall(r"\((\d+)\)", text)] or [0]; n = max(idx) + 1
        w = {int(i): t for i, t in re.findall(r"\((\d+)\)([^\s(]+)", text)}
        return json.dumps({"hook": {"line1": " ".join(w.get(i, "") for i in (0, 1, 2)).strip(), "line2": ""}, "keyword_ids": [min(n - 1, 5)],
                           "moments": [{"block": "info_card", "at_word": n - 3, "duration": 4.0, "values": {"kicker": "ك", "headline": w.get(n - 3, "x"), "caption": w.get(n - 2, "x")}},
                                       {"block": "not_a_real_block", "at_word": 20, "duration": 2.0, "values": {}}],
                           "punch_ins": [{"at_word": min(n - 1, k), "scale": 1.2} for k in (10, 45)], "cover": {"tag": "", "sticker": "", "card_label": "", "card_value": ""}})
    if NASTY["on"] and "Fix this reel plan JSON" in text:
        NASTY["repairs"] += 1
        if NASTY["repairs"] == 1: return "The reel ends at 43.3s, and moments[1] (not_a_real_block) is not allowed, so I removed it."
    if "DIRECTOR of an automated reel" in text or "Fix this reel plan JSON" in text:
        idx = [int(x) for x in re.findall(r"\((\d+)\)", text)] or [0]; n = max(idx) + 1
        w = {int(i): t for i, t in re.findall(r"\((\d+)\)([^\s(]+)", text)}
        return json.dumps({"hook": {"line1": " ".join(w.get(i, "") for i in (0, 1, 2)).strip(), "line2": ""}, "keyword_ids": [min(n - 1, 5), min(n - 1, 40), min(n - 1, 90)],
                           "moments": [], "punch_ins": [{"at_word": min(n - 1, k), "scale": 1.2} for k in (10, 45, 80)],
                           "cover": {"tag": "", "sticker": "", "card_label": "", "card_value": ""}})
    if "quality reviewer" in text:
        return json.dumps({"scores": {"readable": 8, "layout": 7, "consistency": 8, "variety": 5}, "issues": [{"t": 3.0, "what": "mock: plain frame"}], "verdict": "mock verdict"})
    if "PROOFREADER" in text or "correct an automatic Arabic" in text:
        return json.dumps({"fixes": [], "notes": "mock"})
    if "tag icons" in text or "tags icons" in text:
        names = re.findall(r"^([a-z ]+)$", text.split("NAMES:")[-1], re.M); return json.dumps({n: ["مثال"] for n in names})
    return json.dumps({"ok": True})


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0)); body = json.loads(self.rfile.read(n) or b"{}")
        parts = body["messages"][0]["content"]; text = "\n".join(p.get("text", "") for p in parts if p.get("type") == "text"); nimg = sum(1 for p in parts if p.get("type") == "image_url")
        a = answer(text, nimg)
        with STATE["lock"]:
            STATE["calls"] += 1; stage = a[:14]; STATE["by_stage"][stage] = STATE["by_stage"].get(stage, 0) + 1; k = STATE["calls"]; mode = STATE["mode"]
        if STATE["delay"]: time.sleep(STATE["delay"])
        if STATE["fail_every"] and k % STATE["fail_every"] == 0: mode = "err500"
        if mode == "err500": return self._send(500, {"error": "boom"})
        if mode == "err429": self.send_response(429); self.send_header("Retry-After", "1"); self.send_header("Content-Length", "2"); self.end_headers(); self.wfile.write(b"{}"); return
        if mode == "err401": return self._send(401, {"error": "bad key"})
        if mode == "hang": time.sleep(3600); return
        if mode == "garbage": a = "I'm sorry, here is my answer: not json at all"
        if mode == "empty": a = ""
        if mode == "truncated": a = a[: max(5, len(a) // 2)]
        if mode == "drop": self.connection.close(); return
        self._send(200, {"choices": [{"message": {"content": a}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 1000, "completion_tokens": 300, "cost": 0.001}})
    def _send(self, code, obj):
        b = json.dumps(obj).encode(); self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)


def start_mock():
    class S(ThreadingHTTPServer): daemon_threads = True; allow_reuse_address = True
    srv = S(("127.0.0.1", MOCK_PORT), H); threading.Thread(target=srv.serve_forever, daemon=True).start(); return srv


# ------------------------------------------------------------------ project copy + runs
def make_copy():
    work = tempfile.mkdtemp(prefix="rf-e2e-")
    shutil.copytree(SRC, work, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git", "jobs", "inbox", "node_modules", "__pycache__", "ok", "_reports", ".backups", ".runs", "pre_uat_report", "tests", "*.mp4", "*.mov", "*.webm"))
    for d in ("jobs", "inbox"): os.makedirs(os.path.join(work, d), exist_ok=True)
    p = os.path.join(work, "config", "project.json"); c = json.load(open(p)); c["route"]["base_url"] = f"http://127.0.0.1:{MOCK_PORT}"; json.dump(c, open(p, "w"), indent=1)
    return work


def env_for(work):
    e = dict(os.environ, RF_API_KEY="mock-key", HOME=os.path.join(work, "_home"), PYTHONUNBUFFERED="1"); os.makedirs(e["HOME"], exist_ok=True); return e


def ffclip(path, dur, size="1080x1920", audio=True):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    a = ["-f", "lavfi", "-i", f"sine=f=220:d={dur}"] if audio else []
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=s={size}:r=30:d={dur}"] + a + ["-shortest", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p"] + (["-c:a", "aac"] if audio else ["-an"]) + [path], capture_output=True, text=True)
    return r.returncode == 0


def run(work, args, timeout=900, label=""):
    """Run scripts/reel.py; -> dict(code, seconds, max_rss_mb, tail). Peak memory is the largest child's, from the kernel's own accounting."""
    t0 = time.time()
    p = subprocess.Popen([sys.executable, os.path.join(work, "scripts", "reel.py")] + args, cwd=work, env=env_for(work), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    out = []; th = threading.Thread(target=lambda: out.append(p.stdout.read())); th.start()
    try:
        _, st, ru = os.wait4(p.pid, 0) if False else (None, None, None)
    except Exception:
        pass
    try:
        p.wait(timeout=timeout); code = p.returncode
    except subprocess.TimeoutExpired:
        p.kill(); code = "TIMEOUT"
    th.join(10)
    ru = resource.getrusage(resource.RUSAGE_CHILDREN)
    return {"label": label, "code": code, "seconds": round(time.time() - t0, 1), "max_rss_mb": round(ru.ru_maxrss / 1024), "output": (out[0] if out else "")}


def seed_job(work, slug, dur, seed=1, audio=True, size="1080x1920"):
    """Ingest a synthetic clip, then drop a ready Whisper-style transcript into the job. -> job folder."""
    clip = os.path.join(work, "inbox", slug, "clips", "01-take.mp4"); assert ffclip(clip, dur, size, audio), "ffmpeg could not make the test clip"
    r = run(work, [os.path.join(work, "inbox", slug), "--slug", slug, "--stop-after", "ingest"], 300, f"ingest {slug}")
    jobs = [j for j in os.listdir(os.path.join(work, "jobs")) if j.endswith(slug)]
    if not jobs: return None, r
    jd = os.path.join(work, "jobs", sorted(jobs)[-1]); json.dump(words_for(dur, seed), open(os.path.join(jd, "transcript_asr.json"), "w"), ensure_ascii=False)
    return jd, r
