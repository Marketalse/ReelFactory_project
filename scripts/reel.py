#!/usr/bin/env python3
"""Reel Factory one-command pipeline. Stdlib only (runs on any python3).

  python3 scripts/reel.py inbox/<slug> --slug <slug>        start a reel from an inbox folder (or one clip)
  python3 scripts/reel.py jobs/<job>                         continue (each stage is cached; nothing is paid twice)
  python3 scripts/reel.py jobs/<job> --select B              Gate 1: pick story B
  python3 scripts/reel.py jobs/<job> --approve               Gate 2: the final video + cover suggestion
  python3 scripts/reel.py jobs/<job> --fix "captions bigger, hook shorter"   Gate 2: re-plan with feedback

Stages: ingest -> transcribe (local whisper) -> fix (Haiku) -> review [GATE 0: you fix words] -> selects (Sonnet)
[GATE 1: you pick] -> edl (cut pauses/fillers/retakes) -> keyframes + shotlog (Sonnet) -> plan (Director, Haiku;
Sonnet fallback repair) -> compile (templates only) -> draft (check, contact sheet, 540p draft, edit package)
[GATE 2: you approve or send fixes] -> final (one high-quality video) -> cover suggestion.

Models, prices, caps, ASR and gates come from config/*.json. Every run is written to <job>/run.log.
Money: a paid call is refused when this job's spend + its worst case would pass --budget (default
budget_usd.per_reel_stop), or when the month would pass budget_usd.monthly_stop. Only text and small stills leave
the Mac, never audio or video.
"""
import argparse, base64, glob, json, os, re, shutil, subprocess, sys, time, urllib.request, urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import config as cfg   # noqa: E402  (all settings live in config/*.json)
from lib import transcript as tr, edl as edlmod, director   # noqa: E402
from lib.hfbuild import BuildError   # noqa: E402

ROOT = cfg.ROOT
FF, FFDIR = cfg.find_ffmpeg()
ENV = dict(os.environ, PATH=os.environ.get("PATH", "") + ":" + FFDIR)
M_FIX = cfg.MODELS["transcript_fix"]
M_VIS = cfg.MODELS["vision"]
M_SEL = cfg.MODELS["selects"]
M_DIR = cfg.MODELS["director"]
M_DIR_FALLBACK = cfg.MODELS.get("director_fallback")
LEN_MIN, LEN_MAX = cfg.RULES["reel_length_s"]["min"], cfg.RULES["reel_length_s"]["max"]
STAGES = ["ingest", "transcribe", "fix", "review", "selects", "edl", "keyframes", "shotlog", "plan", "compile", "draft", "report"]
STATUS_AFTER = {"ingest": "ingested", "transcribe": "transcribed", "fix": "transcript_fixed", "review": "transcript_reviewed",
                "selects": "story_picked", "edl": "cut", "plan": "planned", "compile": "built", "draft": "preview_ready"}

class Stop(Exception):
    pass

# ----------------------------------------------------------------------------- helpers
def jload(p, default=None):
    try: return json.load(open(p))
    except Exception: return default

def jsave(p, d):
    json.dump(d, open(p, "w"), indent=1, ensure_ascii=False)

def nous():
    return cfg.auth()


RETRY_CODES = (408, 429, 500, 502, 503, 504, 529)


def explain_http(stage, code, body):
    """Provider errors in plain words, with what to do. The raw reply is kept short at the end."""
    raw = body[:160].decode("utf-8", "replace") if isinstance(body, bytes) else str(body)[:160]
    src = cfg.key_source()
    if code in (401, 403):
        why = (f"the AI service refused the API key ({src}): it is wrong, expired or the account is out of credit. "
               "Check credit at portal.nousresearch.com; to replace the key, click Settings on the Reel Factory page. Then click Try again.")
    elif code == 402:
        why = "the AI service account is out of credit. Top up at portal.nousresearch.com, then click Try again."
    elif code == 404:
        why = "the AI model name was not found. Tell Claude: the model in config/project.json may have been renamed."
    elif code == 400:
        why = "the AI service rejected the request. Send this message to Claude."
    elif code in RETRY_CODES:
        why = "the AI service is busy or having problems right now (already retried). Wait a few minutes, then click Try again."
    else:
        why = "the AI service returned an unexpected error. Send this message to Claude."
    return f"{stage}: {why} [HTTP {code}: {raw}]"


def post_with_retry(req, stage, tries=2, wait=20, timeout=600, sleep=time.sleep):
    """One retry for temporary problems (rate limit, overload, network). Failed calls are not charged."""
    for n in range(1, tries + 1):
        try:
            return json.load(urllib.request.urlopen(req, timeout=timeout))
        except urllib.error.HTTPError as e:
            body = e.read()
            if e.code in RETRY_CODES and n < tries:
                ra = e.headers.get("Retry-After") if e.headers else None
                w = min(60, int(ra)) if ra and ra.isdigit() else wait
                print(f"   [{stage}] AI service busy (HTTP {e.code}); retrying in {w}s"); sleep(w); continue
            raise Stop(explain_http(stage, e.code, body))
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if n < tries:
                print(f"   [{stage}] no answer from the AI service ({e}); retrying in {wait}s"); sleep(wait); continue
            raise Stop(f"{stage}: could not reach the AI service (internet down?). Check the connection, then click Try again. [{e}]")


class Tee:
    """Copy everything printed during a run into <job>/run.log, so a stop is never unexplained."""
    def __init__(self, path, out):
        self.f = open(path, "a", encoding="utf-8"); self.out = out
    def write(self, s):
        self.out.write(s); self.f.write(s); self.f.flush()
    def flush(self):
        self.out.flush(); self.f.flush()

class Ctx:
    def __init__(self, job, a):
        self.job, self.a = job, a
        self.cost_path = os.path.join(job, "cost.json")
        self.cost = jload(self.cost_path, {"calls": []})
        self.timing = jload(os.path.join(job, "timing.json"), {})

    def spent(self): return sum(c["cost"] for c in self.cost["calls"])

    def llm(self, stage, model, content, max_tokens, effort="low", est_in_tokens=None, _retry=False):
        """One paid call. Returns text. Enforces the budget BEFORE calling."""
        chars = sum(len(p.get("text", "")) for p in content if p["type"] == "text")
        imgs = sum(1 for p in content if p["type"] == "image_url")
        est_in = est_in_tokens or int(chars / 2.6 + imgs * (self.a.img_tok))
        pin, pout = cfg.price(model)
        worst = est_in * pin / 1e6 + max_tokens * pout / 1e6
        if self.spent() + worst > self.a.budget:
            raise Stop(f"BUDGET GUARD: {stage} worst case ${worst:.3f} + spent ${self.spent():.3f} > budget ${self.a.budget:.2f}. "
                       f"Raise --budget only with Hesham's approval.")
        month = cfg.month_spent() + (self.spent() - self.cost.get("logged", 0.0))
        if month + worst > cfg.BUDGET["monthly_stop"]:
            raise Stop(f"MONTHLY CAP: this month ${month:.2f} + worst case ${worst:.3f} > ${cfg.BUDGET['monthly_stop']:.2f}. "
                       f"Change budget_usd.monthly_stop in config/project.json only with Hesham's approval.")
        if self.spent() + worst > cfg.BUDGET["per_reel_warn"] and not getattr(self, "_warned", False):
            self._warned = True
            print(f"   WARNING: this job may pass the ${cfg.BUDGET['per_reel_warn']:.2f} per-reel warning level")
        base, key = nous()
        body = {"model": model, "max_tokens": max_tokens, "reasoning": {"effort": effort},
                "messages": [{"role": "user", "content": content}]}
        req = urllib.request.Request(base + "/chat/completions", data=json.dumps(body).encode(),
                                     headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
        t0 = time.time()
        d = post_with_retry(req, stage)
        dt = time.time() - t0
        u = d["usage"]
        rec = {"stage": stage, "model": model, "in": u["prompt_tokens"], "out": u["completion_tokens"],
               "reasoning": (u.get("completion_tokens_details") or {}).get("reasoning_tokens"),
               "cost": u.get("cost", 0.0), "seconds": round(dt, 1), "finish": d["choices"][0].get("finish_reason")}
        self.cost["calls"].append(rec); jsave(self.cost_path, self.cost)
        print(f"   [{stage}] {model.split('/')[1]} in={rec['in']} out={rec['out']} think={rec['reasoning']} ${rec['cost']:.4f} {dt:.0f}s")
        if rec["finish"] == "length":
            if not _retry and max_tokens < 24000:      # answer was cut off: try once more with double room (budget guard still applies)
                print(f"   [{stage}] answer was cut off at {max_tokens}; trying once more with {max_tokens * 2}")
                return self.llm(stage, model, content, max_tokens * 2, effort, est_in_tokens, _retry=True)
            raise Stop(f"{stage}: output hit max_tokens={max_tokens} (truncated JSON). Raise the limit or lower effort.")
        return d["choices"][0]["message"]["content"]

def parse_json(txt):
    t = txt.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
    if m: t = m.group(1).strip()
    i = min([x for x in (t.find("{"), t.find("[")) if x >= 0] or [0])
    return json.loads(t[i:])

def lines_from_words(words, gap=0.35):
    """[(t0,t1,text,first_index)] phrases, split on pauses."""
    out, cur = [], []
    for i, w in enumerate(words):
        if cur and w["start"] - words[cur[-1]]["end"] > gap:
            out.append(cur); cur = []
        cur.append(i)
    if cur: out.append(cur)
    return [(words[c[0]]["start"], words[c[-1]]["end"], " ".join(words[i]["text"] for i in c), c[0]) for c in out]

def numbers_spoken(words):
    return [(i, w["text"]) for i, w in enumerate(words) if re.search(r"\d|ألف|الف|مليون", w["text"])]

# ----------------------------------------------------------------------------- stages
def set_status(c, stage):
    jp = os.path.join(c.job, "job.json"); j = jload(jp, {})
    if stage in STATUS_AFTER:
        j["status"] = STATUS_AFTER[stage]; jsave(jp, j)


def st_ingest(c):
    if os.path.exists(os.path.join(c.job, "proxy.mp4")): return "cached"
    raise Stop("job has no proxy.mp4; start from an inbox folder: python3 scripts/reel.py inbox/<slug> --slug <slug>")

def st_transcribe(c):
    out = os.path.join(c.job, "transcript_asr.json")
    if os.path.exists(out): return "cached"
    asr = cfg.PROJECT["asr"]; model = c.a.asr_model or asr["model"]
    tmp = os.path.join(c.job, "_asr"); os.makedirs(tmp, exist_ok=True)
    r = subprocess.run(["npx", "--yes", f"hyperframes@{cfg.PROJECT.get('tools', {}).get('hyperframes', '0.8.226')}", "transcribe",
                        os.path.join(c.job, "audio16k.wav"), "--engine", asr.get("engine", "whisper"), "--model", model,
                        "--language", asr["language"], "--json", "--dir", tmp], capture_output=True, text=True, env=ENV, cwd=ROOT)
    found = [os.path.join(dp, f) for dp, _, fs in os.walk(tmp) for f in fs if f == "transcript.json"]
    if not found: raise Stop(f"transcribe failed (model {model}): " + (r.stderr or r.stdout)[-400:])
    words = json.load(open(found[0], encoding="utf-8"))
    words = words.get("words", words) if isinstance(words, dict) else words
    kept, dropped = tr.clean_asr(words, tr.silences(os.path.join(c.job, "silences.txt")), proxy_duration(c.job))
    jsave(out, kept); jsave(os.path.join(c.job, "transcript_asr_dropped.json"), dropped)
    return f"whisper {model}: {len(kept)} words ({len(dropped)} invented-over-silence dropped)"

FIX_PROMPT = """You correct an automatic Arabic speech transcript. The speaker is an Iraqi (Erbil) marketer-entrepreneur talking to camera about business, online stores, Meta ads and customer service. Dialect: Iraqi Arabic mixed with English terms. The ASR output below is word-by-word, numbered; many words are mis-heard (wrong dialect spelling, garbled phrases, English words written in Arabic letters, brand names).

Rules:
- Return ONLY JSON: {"fixes":[{"i":<word index>,"text":"<corrected word>"}],"notes":"<=20 words"}.
- ONE-TO-ONE replacement per word index: never merge, split, add or delete words (timestamps depend on it).
- Keep Iraqi dialect; do NOT convert to formal Arabic. Keep English terms (customer service, ads, store) in Latin letters.
- Only change a word when you are confident from context. Leave uncertain words unchanged.
- Use these exact spellings when the word is meant: {glossary}
- Fix obvious garbles (a nonsense word that fits no dialect reading) to the most likely intended word.

WORDS:
"""

def st_fix(c):
    out = os.path.join(c.job, "transcript.json")
    asr = jload(os.path.join(c.job, "transcript_asr.json"))
    if os.path.exists(out) and jload(os.path.join(c.job, "transcript_fix_meta.json")): return "cached"
    prompt = FIX_PROMPT.replace("{glossary}", glossary_text()) + "\n".join(f"{i}:{w['text']}" for i, w in enumerate(asr))
    txt = c.llm("fix", M_FIX, [{"type": "text", "text": prompt}], 4000, "low")   # longer clip = longer answer
    fx = parse_json(txt)
    words = [dict(w) for w in asr]; applied = []
    for f in fx.get("fixes", []):
        i, t = f.get("i"), (f.get("text") or "").strip()
        if isinstance(i, int) and 0 <= i < len(words) and t and " " not in t and t != words[i]["text"]:
            applied.append({"i": i, "from": words[i]["text"], "to": t}); words[i]["text"] = t
    jsave(out, words)
    jsave(os.path.join(c.job, "transcript_fix_meta.json"), {"model": M_FIX, "n_words": len(words), "n_changed": len(applied), "changes": applied, "notes": fx.get("notes")})
    return f"{len(applied)}/{len(words)} words corrected"

def glossary_text():
    terms = [t for t in cfg.GLOSSARY.get("terms", []) if t.get("confirmed")]
    return "; ".join(f'{t["spoken"]} -> {t["write"]}' for t in terms) or "none yet"


def st_review(c):
    """GATE 0: Hesham fixes words in transcript_review.txt; timings are kept."""
    path = os.path.join(c.job, "transcript_review.txt"); meta = os.path.join(c.job, "transcript_review_meta.json")
    if os.path.exists(meta): return "cached"
    words = jload(os.path.join(c.job, "transcript.json"))
    if c.a.skip_review or not cfg.PROJECT["gates"].get("transcript_review", True):
        jsave(meta, {"skipped": True}); return "skipped (no Gate 0)"
    if not os.path.exists(path):
        tr.write_review(path, words)
        raise Stop(f"GATE 0 (not an error): fix the words in {path}, set 'STATUS: reviewed', run again")
    if not tr.review_done(path):
        raise Stop(f"GATE 0 waiting: {path} still says STATUS: waiting")
    try:
        new, stats = tr.apply_review(path, words)
    except ValueError as e:
        raise Stop(str(e))
    jsave(os.path.join(c.job, "transcript_before_review.json"), words)
    jsave(os.path.join(c.job, "transcript.json"), new); jsave(meta, stats)
    return f"{stats['changed']} of {stats['words_before']} words changed by Hesham (error rate {stats['error_rate']:.0%})"

def st_keyframes(c):
    s0, s1 = jload(os.path.join(c.job, "chosen_select.json"))["range"]
    s0, s1 = max(0.0, s0 - 0.5), min(proxy_duration(c.job), s1 + 0.5)
    cur = jload(os.path.join(c.job, "keyframes.json"))
    if cur and not c.a.rekey and cur.get("range") == [s0, s1] and cur.get("width") == c.a.width: return "cached"
    sp = os.path.join(c.job, "shot_log.json")
    if os.path.exists(sp): os.remove(sp)   # shot log is tied to the frame set
    cmd = [sys.executable, os.path.join(ROOT, "scripts", "keyframes.py"), c.job, "--width", str(c.a.width), "--every", str(c.a.every), "--cap", "40",
           "--start", str(s0), "--end", str(s1)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode: raise Stop("keyframes failed: " + r.stderr[-300:])
    m = jload(os.path.join(c.job, "keyframes.json")); m["range"] = [s0, s1]; jsave(os.path.join(c.job, "keyframes.json"), m)
    return f"{m['count']} frames in {s0:.1f}-{s1:.1f}s"

SHOT_PROMPT = """You are the shot-logger for a short-form video editor. Below are {n} still frames from ONE vertical phone video (talking head), each preceded by its timestamp in seconds. For EACH frame return an object. Return ONLY a JSON array, one object per frame, same order:
{{"t":<seconds>,"face":{{"x":<0-1 left edge>,"y":<0-1 top edge>,"w":<0-1>,"h":<0-1>}}|null,"eyes":"open|closed|away","energy":<1 flat - 5 animated>,"gesture":"none|hand|point|nod|other","headroom":"ok|tight","bg":"low|med|high clutter","text":"any readable on-screen text or empty","usable":["hook","punch_in","cut","avoid"],"note":"<=10 words"}}
face = bounding box of the speaker's face as fractions of the frame (approximate is fine). usable = what an editor could use this moment for: hook (strong first frame), punch_in (good moment for a zoom), cut (clean place to cut/transition), avoid (blink, half-closed eyes, awkward mid-word face, motion blur). Be honest: if frames are near-identical, say so in note. No commentary outside the JSON."""

def st_shotlog(c):
    out = os.path.join(c.job, "shot_log.json")
    if os.path.exists(out): return "cached"
    man = jload(os.path.join(c.job, "keyframes.json"))
    content = [{"type": "text", "text": SHOT_PROMPT.format(n=man["count"])}]
    for f in man["frames"]:
        content.append({"type": "text", "text": "t=%.2f" % f["t"]})
        b = base64.b64encode(open(os.path.join(c.job, f["file"]), "rb").read()).decode()
        content.append({"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b}})
    log = parse_json(c.llm("shotlog", M_VIS, content, 9000, "low"))
    if len(log) != man["count"]: raise Stop(f"shot log returned {len(log)} rows for {man['count']} frames")
    jsave(out, log); return f"{len(log)} rows"

SELECTS_PROMPT = """You are the story editor of an Iraqi short-form (Reels) channel run by Hesham, a marketer-entrepreneur in Erbil. From this transcript of ONE raw take, propose exactly 3 candidate stories, each a continuous source range of {lmin}-{lmax} seconds that could stand alone as a reel. Each must start on a strong spoken hook taken from the speaker's OWN words, hold one idea, and end on a natural close. Prefer ranges that begin/end at pauses. Do not invent content.
Return ONLY JSON: {{"selects":[{{"id":"A","range":[start_s,end_s],"label":"<=12 words English","hook_line":"verbatim Arabic from transcript","why":"<=25 words","score":1-10}},...]}} sorted best first.
Take length: {dur:.1f}s.
TRANSCRIPT (time_start-time_end text):
{lines}"""

def proxy_duration(job):
    err = subprocess.run([FF, "-hide_banner", "-i", os.path.join(job, "proxy.mp4")], capture_output=True, text=True).stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err)
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])

def transcript_lines(c):
    words = jload(os.path.join(c.job, "transcript.json"))
    return words, "\n".join(f"[{a:.1f}-{b:.1f}] {t}" for a, b, t, _ in lines_from_words(words))

def st_selects(c):
    jp = os.path.join(c.job, "job.json"); job = jload(jp, {})
    words, lines = transcript_lines(c)
    sp = os.path.join(c.job, "selects.json")
    if not os.path.exists(sp) and proxy_duration(c.job) <= LEN_MAX + 5:
        jsave(sp, {"selects": [{"id": "A", "range": [0.0, proxy_duration(c.job)], "label": "the whole take", "hook_line": "", "why": "take is already reel length", "score": 0}]})
    if not os.path.exists(sp):
        dur = proxy_duration(c.job)
        res = parse_json(c.llm("selects", M_SEL, [{"type": "text", "text": SELECTS_PROMPT.format(dur=dur, lines=lines, lmin=LEN_MIN, lmax=LEN_MAX)}], 5000, c.a.effort))
        jsave(sp, res)
    sel = jload(sp)["selects"]
    pick = c.a.select; from_job = None
    if not pick:
        chosen = [s for s in job.get("selects", []) if s.get("chosen")]
        if chosen and not c.a.fresh_selects:   # Hesham's earlier pick in job.json wins: use ITS range, not the new candidate with the same letter
            from_job = chosen[0]; pick = chosen[0]["id"]
    if not pick and len(sel) == 1 and sel[0].get("label") == "the whole take":
        pick = "A"
    if not pick and cfg.PROJECT["gates"].get("story_pick", "ask") == "auto":
        pick = "auto"
    if not pick:
        print("\n   GATE 1 - Hesham picks the story. Candidates:")
        for s in sel: print(f"     {s['id']}  {s['range'][0]:.0f}-{s['range'][1]:.0f}s  {s['label']}  | {s['hook_line']}")
        print(f"   Re-run with --select A|B|C (or --select auto to take #1, only if you accept skipping the gate).")
        raise Stop("GATE 1 reached (not an error)")
    if from_job:
        s = {"id": from_job["id"], "range": from_job["range"], "label": from_job["label"], "hook_line": ""}; by = "hesham (job.json)"
    else:
        s = max(sel, key=lambda x: x.get("score", 0)) if pick == "auto" else next((x for x in sel if x["id"] == pick), None); by = "auto (best score)" if pick == "auto" else "hesham (--select)"
    if not s: raise Stop(f"unknown select {pick}")
    jsave(os.path.join(c.job, "chosen_select.json"), dict(s, picked_by=by))
    return f"select {s['id']} {s['range']}"

def st_edl(c):
    out = os.path.join(c.job, "edl.json")
    if os.path.exists(out) and not c.a.replan: return "cached"
    s0, s1 = jload(os.path.join(c.job, "chosen_select.json"))["range"]
    man = jload(os.path.join(c.job, "manual_edit.json"), {}) or {}          # cuts/restores/spellings from the Edit page
    e = edlmod.build(jload(os.path.join(c.job, "transcript.json")), s0, s1,
                     drop=man.get("drop", []), keep=man.get("keep", []), texts=man.get("texts", {}))
    jsave(out, e)
    r = e["removed"]
    return f"{e['source_seconds']:.1f}s -> {e['duration']:.1f}s ({r['pauses']} pauses, {len(r['fillers'])} fillers, {len(r['retakes'])} retake words removed)"


def job_logos(c):
    d = os.path.join(c.job, "assets")
    return sorted(f for f in os.listdir(d) if f.lower().endswith((".svg", ".png", ".jpg", ".jpeg", ".webp"))) if os.path.isdir(d) else []


def st_plan(c):
    """Director (Haiku) -> plan; code resolves word anchors to exact times and checks every rule;
    one repair with the Director, then one with the fallback model; still failing -> stop."""
    out = os.path.join(c.job, "timeline.json")
    if os.path.exists(out) and not c.a.replan: return "cached"
    e = jload(os.path.join(c.job, "edl.json")); words = e["words"]
    try:                                            # logos/screenshots from library/broll whose name he said
        from lib import broll
        got = broll.attach(c.job, words)
        if got: print("   b-roll attached from library/broll:", ", ".join(got))
    except Exception as ex:                         # noqa: BLE001 - the library is a bonus, never a reason to stop a reel
        print("   b-roll library skipped:", ex)
    brief = open(os.path.join(c.job, "brief.md"), encoding="utf-8").read() if os.path.exists(os.path.join(c.job, "brief.md")) else ""
    job = jload(os.path.join(c.job, "job.json"), {})
    feedback = c.a.fix or ""
    prompt = director.build_prompt(words, e["duration"], brief, job_logos(c), feedback, director.taste())
    if feedback and os.path.exists(os.path.join(c.job, "scene_plan.json")):
        prompt += "\n\nPREVIOUS PLAN:\n" + json.dumps(jload(os.path.join(c.job, "scene_plan.json")), ensure_ascii=False)
    plan = parse_json(c.llm("plan", M_DIR, [{"type": "text", "text": prompt}], 9000, c.a.effort))
    attempts = [(M_DIR, plan)]

    def resolve(p):
        tl, err, warn = director.resolve(p, words, e["duration"], logos=job_logos(c))
        if not err:
            err = director.check_rhythm(tl, director.face_cuts(tl, e["segments"]))
        return tl, err, warn

    tl, err, warn = resolve(plan)
    if err and all(director.STILL_ERR.search(x) for x in err):        # only "nothing changes on screen": fix it for free, no AI
        plan, tl, err, warn, added = director.fix_rhythm(plan, words, resolve)
        print(f"   rhythm: added {added} zoom(s) automatically (free)")
    for model in [m for m in (M_DIR, M_DIR_FALLBACK) if m] if not c.a.no_repair else []:
        if not err: break
        print(f"   plan errors -> repair with {model.split('/')[1]}:", *err[:8], sep="\n     - ")
        plan = parse_json(c.llm("repair", model, [{"type": "text", "text":
            "Fix this reel plan JSON so every error below is solved. Change only what is needed, keep the schema, "
            "return ONLY the full JSON.\n\nERRORS:\n" + "\n".join(err) + "\n\nPLAN:\n" + json.dumps(plan, ensure_ascii=False)
            + "\n\nTRANSCRIPT:\n" + director.numbered_transcript(words)}], 9000, c.a.effort))
        attempts.append((model, plan)); tl, err, warn = resolve(plan)
        if err and all(director.STILL_ERR.search(x) for x in err):
            plan, tl, err, warn, added = director.fix_rhythm(plan, words, resolve)
            print(f"   rhythm: added {added} zoom(s) automatically (free)")
    jsave(os.path.join(c.job, "scene_plan.json"), plan)
    jsave(os.path.join(c.job, "validation.json"), {"errors": err, "warnings": warn, "attempts": [m for m, _ in attempts]})
    if err: raise Stop("plan still breaks the rules after repair: " + "; ".join(err[:4]))
    shots = jload(os.path.join(c.job, "shot_log.json")) or []
    faces = sorted(r["face"]["y"] + r["face"]["h"] * 0.45 for r in shots if r.get("face"))
    tl["face_cy"] = round(faces[len(faces) // 2], 3) if faces else 0.36
    tl["director"] = attempts[-1][0]; tl["feedback"] = feedback
    jsave(out, tl)
    n = sum(1 for s in tl["scenes"] if s["block"] not in ("hook_two_tone", "cta_card"))
    return f"{n} moments, {len(tl['punch_ins'])} punch-ins, {len(tl['keyword_ids'])} keywords ({len(warn)} warnings)"


def st_compile(c):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from compile import compile_job
    try:
        p = compile_job(c.job)
    except BuildError as e:
        raise Stop(f"compile refused the plan: {e}")
    return os.path.relpath(p, c.job)


def st_draft(c):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import render
    if os.path.exists(os.path.join(c.job, "review", "draft_540p.mp4")) and not c.a.replan:
        res = jload(os.path.join(c.job, "review", "draft.json"), {})
    else:
        try:
            res = render.draft(c.job)
        except render.RenderError as e:
            raise Stop(str(e))
        jsave(os.path.join(c.job, "review", "draft.json"), res)
    c.gate2 = res
    qa = res.get("qa") or {}
    if qa.get("errors"):
        raise Stop("QA found problems before Gate 2 (draft kept for inspection): " + "; ".join(qa["errors"][:5]))
    return f"draft ready: QA passed ({len(qa.get('warnings', []))} QA warnings, {len(res.get('check_warnings', []))} check warnings)"


def st_report(c):
    cost = c.cost["calls"]; tot = sum(x["cost"] for x in cost)
    e = jload(os.path.join(c.job, "edl.json"), {}); tl = jload(os.path.join(c.job, "timeline.json"), {})
    val = jload(os.path.join(c.job, "validation.json"), {}); rv = jload(os.path.join(c.job, "transcript_review_meta.json"), {})
    dr = jload(os.path.join(c.job, "review", "draft.json"), {})
    L = [f"# Reel report - {os.path.basename(c.job)}", "",
         f"**Status:** preview ready - watch `review/draft_540p.mp4`, then reply with `--approve` or `--fix \"...\"`.", "",
         f"Spend this job: **${tot:.4f}** (stop at ${c.a.budget:.2f})", "",
         "| stage | model | in tok | out tok | cost | s |", "|---|---|---|---|---|---|"]
    for x in cost:
        L.append(f"| {x['stage']} | {x['model'].split('/')[1]} | {x['in']} | {x['out']} | ${x['cost']:.4f} | {x['seconds']} |")
    L += ["", f"Transcript: {rv.get('changed', 0)} words fixed by you at Gate 0 (error rate {rv.get('error_rate', 0):.0%}).",
          f"Cut: {e.get('source_seconds', 0):.1f}s of the take -> {e.get('duration', 0):.1f}s reel; removed {e.get('removed', {}).get('pauses', 0)} pauses, "
          f"{len(e.get('removed', {}).get('fillers', []))} fillers, {len(e.get('removed', {}).get('retakes', []))} retake words.",
          f"Plan: {len(tl.get('scenes', []))} scenes, {len(tl.get('punch_ins', []))} punch-ins; director {str(tl.get('director', '')).split('/')[-1]}; "
          f"repairs: {max(0, len(val.get('attempts', [])) - 1)}.", "", "Warnings:"]
    qa = dr.get("qa") or {}
    qm = qa.get("metrics", {})
    L += [f"QA: length {qm.get('duration')}s, loudness {qm.get('lufs')} LUFS, captions {qm.get('caption_words')}/{qm.get('spoken_words_shown')} words, "
          f"errors {len(qa.get('errors', []))}.", ""]
    L += [f"- {w}" for w in val.get("warnings", []) + qa.get("warnings", []) + dr.get("check_warnings", [])] or ["- none"]
    L += ["", "Files: `review/draft_540p.mp4`, `review/contact_sheet.jpg`, `edit_package/` (clean_cut.mp4, captions_ar.srt, hyperframes/)."]
    open(os.path.join(c.job, "report.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    return "report.md"


WORD_FIX = re.compile(r"^\s*(.+?)\s*(?:=>|->|→)\s*(.+?)\s*$")


def apply_word_fixes(job, comment):
    """Comment lines like 'رخنه => رقم' or 'kastomer => customer' replace those words everywhere in the transcript
    (word count may change; timings are shared out within the replaced words)."""
    pairs = [m.groups() for m in (WORD_FIX.match(l) for l in comment.splitlines()) if m]
    if not pairs:
        return 0
    changed = 0
    for name in ("transcript.json", "edl.json"):
        p = os.path.join(job, name); d = jload(p)
        if d is None: continue
        words = d["words"] if isinstance(d, dict) else d
        out, i = [], 0
        while i < len(words):
            hit = None
            for old, new in pairs:
                ow = old.split()
                if [w["text"] for w in words[i:i + len(ow)]] == ow:
                    hit = (ow, new.split()); break
            if not hit:
                out.append(words[i]); i += 1; continue
            ow, nw = hit; span = words[i:i + len(ow)]
            a0, b0 = span[0]["start"], span[-1]["end"]; step = (b0 - a0) / max(1, len(nw))
            for k, t in enumerate(nw):
                w = dict(span[min(k, len(span) - 1)]); w.update(text=t, start=round(a0 + k * step, 3), end=round(a0 + (k + 1) * step - 0.02, 3))
                out.append(w)
            changed += len(ow); i += len(ow)
        if isinstance(d, dict): d["words"] = out
        else: d = out
        jsave(p, d)
    return changed // 2 if os.path.exists(os.path.join(job, "edl.json")) else changed


def dashboard_watching(job):
    """True when an open dashboard tab is following this reel and can show its own notification
    (clicking a browser notification opens the reel; a Mac notification would open Script Editor)."""
    port = os.environ.get("RF_DASH_PORT", "8766")
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/watching?ref={os.path.basename(job)}", timeout=2) as r:
            return bool(json.load(r).get("watching"))
    except Exception:
        return False


def notify(msg, job=None):
    """Mac notification, unless a dashboard tab will show a clickable one (silently skipped off macOS)."""
    if job and dashboard_watching(job):
        return
    try:
        subprocess.run(["osascript", "-e", f'display notification "{msg}" with title "Reel Factory"'], capture_output=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        pass


def bakeoff(job, models, a):
    """T59: run the three AI steps (word fix, story pick, director) with the current models and with each candidate on THIS
    reel's real data, in scratch folders (jobs/_bakeoff/...). Your reel is never touched. Writes report.md: cost + result per model.
    Costs cents; every call still goes through the budget guard. It never changes config/project.json: choosing is up to Hesham (T60)."""
    global M_FIX, M_SEL, M_DIR
    base = os.path.basename(job); out = os.path.join(ROOT, "jobs", "_bakeoff", base); os.makedirs(out, exist_ok=True)
    cur = {"fix": M_FIX, "selects": M_SEL, "plan": M_DIR}
    keep_a = (a.select, a.fresh_selects, a.replan); a.select, a.fresh_selects, a.replan = "auto", True, False
    rows = []
    try:
        for label, pick in [("current", cur)] + [(m, {"fix": m, "selects": m, "plan": m}) for m in models]:
            d = os.path.join(out, re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")); os.makedirs(d, exist_ok=True)
            for f in ("job.json", "brief.md", "transcript_asr.json", "transcript.json", "edl.json", "shot_log.json", "chosen_select.json"):
                if os.path.exists(os.path.join(job, f)): shutil.copy(os.path.join(job, f), os.path.join(d, f))
            for f in ("selects.json", "timeline.json", "scene_plan.json", "transcript_fix_meta.json", "cost.json", "proxy.mp4"):
                if os.path.lexists(os.path.join(d, f)): os.remove(os.path.join(d, f))
            if os.path.exists(os.path.join(job, "proxy.mp4")): os.symlink(os.path.join(job, "proxy.mp4"), os.path.join(d, "proxy.mp4"))
            if os.path.isdir(os.path.join(job, "assets")) and not os.path.exists(os.path.join(d, "assets")):
                shutil.copytree(os.path.join(job, "assets"), os.path.join(d, "assets"))
            res = {"model": label, "steps": {}}
            for step, fn_ in (("fix", st_fix), ("selects", st_selects), ("plan", st_plan)):
                M_FIX, M_SEL, M_DIR = pick["fix"], pick["selects"], pick["plan"]
                c = Ctx(d, a); before = c.spent(); t0 = time.time()
                real = os.path.join(job, "transcript.json")
                try:
                    msg = fn_(c); ok = True
                except Stop as e:
                    msg = "STOP: " + str(e); ok = False
                except Exception as e:                      # noqa: BLE001 - one model failing must not end the comparison
                    msg = f"ERROR: {e}"; ok = False
                if step == "fix" and os.path.exists(real):   # later steps use the REAL fixed transcript: one step = one model
                    shutil.copy(real, os.path.join(d, "transcript.json"))
                res["steps"][step] = {"ok": ok, "cost": round(c.spent() - before, 4), "seconds": round(time.time() - t0, 1), "result": msg}
                print(f"   bakeoff {label[:34]:34s} {step:8s} {'ok ' if ok else 'BAD'} ${c.spent() - before:.4f}  {msg[:90]}")
            rows.append(res)
    finally:
        M_FIX, M_SEL, M_DIR = cur["fix"], cur["selects"], cur["plan"]
        a.select, a.fresh_selects, a.replan = keep_a
    lines = [f"# Model bake-off: {base}", "", "Same real reel, each model on its own copy. Nothing in your reel changed.", "",
             "| Model | Word fix | Story pick | Director plan | Total cost |", "|---|---|---|---|---|"]
    for r in rows:
        cell = lambda k: (("ok " if r["steps"][k]["ok"] else "FAILED ") + f"${r['steps'][k]['cost']:.4f} · " + r["steps"][k]["result"])[:120]
        lines.append(f"| {r['model']} | {cell('fix')} | {cell('selects')} | {cell('plan')} | ${sum(x['cost'] for x in r['steps'].values()):.4f} |")
    lines += ["", "Pick per step in docs/DECISIONS.md (T60). Rule: never a cheaper model if quality drops."]
    with open(os.path.join(out, "report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    jsave(os.path.join(out, "report.json"), rows)
    return os.path.join(out, "report.md")


FUNCS = {"ingest": st_ingest, "transcribe": st_transcribe, "fix": st_fix, "review": st_review, "selects": st_selects,
         "edl": st_edl, "keyframes": st_keyframes, "shotlog": st_shotlog, "plan": st_plan, "compile": st_compile,
         "draft": st_draft, "report": st_report}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input"); ap.add_argument("--slug"); ap.add_argument("--select"); ap.add_argument("--stop-after", choices=STAGES)
    ap.add_argument("--budget", type=float, default=cfg.BUDGET["per_reel_stop"]); ap.add_argument("--width", type=int, default=540)
    ap.add_argument("--every", type=float, default=2.0); ap.add_argument("--effort", default="low", choices=["low", "medium", "high"])
    ap.add_argument("--force", default=""); ap.add_argument("--asr-model", default=None); ap.add_argument("--retranscribe", action="store_true")
    ap.add_argument("--fresh-selects", action="store_true"); ap.add_argument("--no-repair", action="store_true")
    ap.add_argument("--skip-review", action="store_true", help="skip Gate 0 for this reel")
    ap.add_argument("--approve", action="store_true", help="Gate 2: render the final video and the cover suggestion")
    ap.add_argument("--fix", help="Gate 2: re-plan with this feedback")
    ap.add_argument("--bakeoff", help="T59: compare these models (comma separated) with the current ones on this reel; costs cents")
    ap.add_argument("--rebuild", action="store_true", help="new draft from the manual edit (Edit page); no AI, no spend")
    a = ap.parse_args()
    a.img_tok = {1080: 2800, 720: 1300, 540: 800, 384: 420}.get(a.width, 800)
    a.rekey = False; a.replan = bool(a.fix)
    inp = a.input
    if not os.path.isdir(os.path.join(inp, "")) or not os.path.exists(os.path.join(inp, "job.json")):
        if not a.slug: sys.exit("a new reel needs --slug <name>")
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "ingest_folder.py"), inp, "--slug", a.slug], env=ENV)
        if r.returncode: sys.exit("ingest failed")
        inp = sorted(glob.glob(os.path.join(ROOT, "jobs", "*-" + a.slug)))[-1]
    job = os.path.abspath(inp)
    sys.stdout = Tee(os.path.join(job, "run.log"), sys.stdout)
    print(f"\n===== run {time.strftime('%Y-%m-%d %H:%M:%S')} | {' '.join(sys.argv[1:])}")
    c = Ctx(job, a)
    force = set(filter(None, a.force.split(",")))
    files = {"transcribe": ["transcript_asr.json"], "fix": ["transcript_fix_meta.json"], "review": ["transcript_review_meta.json"],
             "keyframes": ["keyframes.json"], "shotlog": ["shot_log.json"], "selects": ["selects.json", "chosen_select.json"],
             "edl": ["edl.json"], "plan": ["timeline.json"], "draft": ["review/draft_540p.mp4"]}
    for s in force:
        for f in files.get(s, []):
            if os.path.exists(os.path.join(job, f)): os.remove(os.path.join(job, f))
    if "keyframes" in force: a.rekey = True
    if a.fix:
        j = jload(os.path.join(job, "job.json"), {}); j.setdefault("feedback_history", []).append({"time": time.strftime("%Y-%m-%d %H:%M"), "fix": a.fix})
        jsave(os.path.join(job, "job.json"), j)
        n = apply_word_fixes(job, a.fix)
        if n: print(f"   word fixes from your comment: {n} word(s) changed in the transcript")
    print(f"JOB {os.path.basename(job)} | budget ${a.budget:.2f} | spent so far ${c.spent():.4f}")
    t_all = time.time(); status = "ok"
    try:
        if a.bakeoff:
            if not os.path.exists(os.path.join(job, "edl.json")):
                raise Stop("bake-off needs a finished reel (with edl.json): make a draft first")
            print("REPORT:", bakeoff(job, [m.strip() for m in a.bakeoff.split(",") if m.strip()], a))
        elif a.rebuild:
            if not os.path.exists(os.path.join(job, "timeline.json")):
                raise Stop("nothing to rebuild yet: make a draft first")
            a.replan = True                                  # re-render the draft
            j = jload(os.path.join(job, "job.json"), {})
            j.setdefault("feedback_history", []).append({"time": time.strftime("%Y-%m-%d %H:%M"), "fix": "(manual edit in the editor)"})
            jsave(os.path.join(job, "job.json"), j)
            print(f"{'plan':11s} ok    0.0s  +$0.0000  your manual edit")
            for s in ("compile", "draft", "report"):
                t0 = time.time()
                msg = FUNCS[s](c)
                set_status(c, s)
                print(f"{s:11s} ok  {time.time() - t0:5.1f}s  +$0.0000  {msg}")
        elif a.approve:
            import render
            if not os.path.exists(os.path.join(job, "review", "draft_540p.mp4")):
                raise Stop("nothing to approve yet: no draft in review/")
            try:
                outs = render.final(job, cfg.PROJECT["review"]["platforms"])
            except render.RenderError as e:
                raise Stop(str(e))
            j = jload(os.path.join(job, "job.json"), {}); j["status"] = "rendered"; j["output"] = [os.path.relpath(o, job) for o in outs]
            jsave(os.path.join(job, "job.json"), j)
            print("FINAL:", *outs, sep="\n  ")
        else:
            for s in STAGES:
                t0 = time.time(); before = c.spent()
                msg = FUNCS[s](c)
                c.timing[s] = round(time.time() - t0, 1); jsave(os.path.join(job, "timing.json"), c.timing)
                set_status(c, s)
                print(f"{s:11s} ok  {time.time() - t0:5.1f}s  +${c.spent() - before:.4f}  {msg}")
                if a.stop_after == s: break
            else:
                print(f"\nGATE 2: watch {os.path.join(job, 'review', 'draft_540p.mp4')}\n"
                      f"  approve:  python3 scripts/reel.py {os.path.relpath(job, ROOT)} --approve\n"
                      f"  or fix:   python3 scripts/reel.py {os.path.relpath(job, ROOT)} --fix \"what to change\"")
    except Stop as e:
        status = "stopped"; print("STOP:", e)
    except Exception:
        import traceback
        status = "crashed"; print("CRASH (full error below, also in run.log):"); traceback.print_exc(file=sys.stdout)
        raise
    finally:
        logged = c.cost.get("logged", 0.0); new = c.spent() - logged
        if new > 0.00005:
            subprocess.run([sys.executable, os.path.join(ROOT, "dashboard", "add_expense.py"), "--video", os.path.basename(job), "--category", "LLM", "API",
                            "--amount", f"{new:.4f}", "--note", f"reel.py run ({status}); measured provider usage.cost"], capture_output=True)
            c.cost["logged"] = c.spent(); jsave(c.cost_path, c.cost)
        print(f"TOTAL this job ${c.spent():.4f} | wall {time.time() - t_all:.0f}s")
        st = jload(os.path.join(job, "job.json"), {}).get("status", "")
        notify({"preview_ready": "Draft ready: open the dashboard to watch it", "rendered": "Final videos ready"}.get(st)
               or (f"Stopped: see run.log ({os.path.basename(job)})" if status != "ok" else f"{os.path.basename(job)}: {st}"), job)

if __name__ == "__main__":
    main()
