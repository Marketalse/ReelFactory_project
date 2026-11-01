#!/usr/bin/env python3
"""Reel Factory one-command pipeline (SHAK-292). Stdlib only (runs on any python3).

  python3 scripts/reel.py <raw_clip | jobs/<job_dir>> [--slug name] [--select A|B|C|auto] [--stop-after STAGE]
                          [--budget 1.00] [--width 540] [--every 3] [--effort low|medium|high] [--force STAGE,...]
                          [--asr-model large-v3-turbo]

Models, prices, caps and the ASR model come from config/project.json; brand from config/brand.json;
story length from config/rules.json. Every run is also written to <job>/run.log.

Stages (each caches its output file in the job folder; re-runs skip finished stages unless --force):
  ingest      raw clip -> proxy.mp4, audio16k.wav (scripts/ingest.sh; skipped for an existing job)
  transcribe  hyperframes whisper -> transcript_asr.json (word timestamps, local, $0)
  fix         Claude Haiku 5.5 corrects word TEXT only, never timestamps -> transcript.json
  selects     story model (config models.selects) proposes 3 stories from the transcript; GATE 1: stops unless --select given / already chosen in job.json
  keyframes   <=40 resized stills of the CHOSEN range only (scripts/keyframes.py) -> keyframes/, keyframes.json
  shotlog     Claude Sonnet 5.5, ONE batched call over the stills -> shot_log.json (face box, eyes, energy, usable moments)
  plan        Director (config models.director; one retry with models.director_fallback) -> scene_plan.json (every beat names a real media source)
  validate    deterministic rules (no LLM); one automatic repair call if it fails -> validation.json
  report      pipeline_report.md with measured tokens, cost, time per stage

Money: every paid call is logged to <job>/cost.json from the provider's own usage.cost; a call is refused when
spent + worst-case estimate would exceed --budget (default: config budget_usd.per_reel_stop), or when this
month's ledger total would pass budget_usd.monthly_stop. The job total is appended to dashboard/expenses.json. Only text and resized stills leave the Mac, never audio/video.
"""
import argparse, base64, glob, json, os, re, subprocess, sys, time, urllib.request, urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import config as cfg   # noqa: E402  (all settings live in config/*.json)

ROOT = cfg.ROOT
FF, FFDIR = cfg.find_ffmpeg()
ENV = dict(os.environ, PATH=os.environ.get("PATH", "") + ":" + FFDIR)
M_FIX = cfg.MODELS["transcript_fix"]
M_VIS = cfg.MODELS["vision"]
M_SEL = cfg.MODELS["selects"]
M_DIR = cfg.MODELS["director"]
M_DIR_FALLBACK = cfg.MODELS.get("director_fallback")
LEN_MIN, LEN_MAX = cfg.RULES["reel_length_s"]["min"], cfg.RULES["reel_length_s"]["max"]
STAGES = ["ingest", "transcribe", "fix", "selects", "keyframes", "shotlog", "plan", "validate", "report"]

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

    def llm(self, stage, model, content, max_tokens, effort="low", est_in_tokens=None):
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
        try:
            d = json.load(urllib.request.urlopen(req, timeout=600))
        except urllib.error.HTTPError as e:
            raise Stop(f"{stage}: provider error HTTP {e.code} {e.read()[:200]!r}")
        dt = time.time() - t0
        u = d["usage"]
        rec = {"stage": stage, "model": model, "in": u["prompt_tokens"], "out": u["completion_tokens"],
               "reasoning": (u.get("completion_tokens_details") or {}).get("reasoning_tokens"),
               "cost": u.get("cost", 0.0), "seconds": round(dt, 1), "finish": d["choices"][0].get("finish_reason")}
        self.cost["calls"].append(rec); jsave(self.cost_path, self.cost)
        print(f"   [{stage}] {model.split('/')[1]} in={rec['in']} out={rec['out']} think={rec['reasoning']} ${rec['cost']:.4f} {dt:.0f}s")
        if rec["finish"] == "length":
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
def st_ingest(c):
    if os.path.exists(os.path.join(c.job, "proxy.mp4")): return "cached"
    raise Stop("job has no proxy.mp4; pass a raw clip path (+ --slug) or run scripts/ingest.sh")

def st_transcribe(c):
    out = os.path.join(c.job, "transcript_asr.json")
    if os.path.exists(out): return "cached"
    legacy = os.path.join(c.job, "transcript.json")
    if os.path.exists(legacy) and not os.path.exists(os.path.join(c.job, "transcript_asr.json")) \
            and not c.a.retranscribe:
        json.dump(json.load(open(legacy)), open(out, "w"), ensure_ascii=False)   # reuse existing local ASR output (words+timestamps)
        return "reused existing local ASR transcript"
    r = subprocess.run(["npx", "hyperframes", "transcribe", os.path.join(c.job, "audio16k.wav"), "-l", "ar", "-m", c.a.asr_model,
                        "--json", "--dir", c.job], capture_output=True, text=True, env=ENV, cwd=ROOT)
    p = os.path.join(c.job, "transcript.json")
    if not os.path.exists(p): raise Stop("transcribe failed: " + r.stderr[-300:])
    os.replace(p, out); return f"whisper {c.a.asr_model}"

FIX_PROMPT = """You correct an automatic Arabic speech transcript. The speaker is an Iraqi (Erbil) marketer-entrepreneur talking to camera about business, online stores, Meta ads and customer service. Dialect: Iraqi Arabic mixed with English terms. The ASR output below is word-by-word, numbered; many words are mis-heard (wrong dialect spelling, garbled phrases, English words written in Arabic letters, brand names).

Rules:
- Return ONLY JSON: {"fixes":[{"i":<word index>,"text":"<corrected word>"}],"notes":"<=20 words"}.
- ONE-TO-ONE replacement per word index: never merge, split, add or delete words (timestamps depend on it).
- Keep Iraqi dialect; do NOT convert to formal Arabic. Keep English terms (customer service, ads, store) in Latin letters.
- Only change a word when you are confident from context. Leave uncertain words unchanged.
- Fix obvious garbles (a nonsense word that fits no dialect reading) to the most likely intended word.

WORDS:
"""

def st_fix(c):
    out = os.path.join(c.job, "transcript.json")
    asr = jload(os.path.join(c.job, "transcript_asr.json"))
    if os.path.exists(out) and jload(os.path.join(c.job, "transcript_fix_meta.json")): return "cached"
    prompt = FIX_PROMPT + "\n".join(f"{i}:{w['text']}" for i, w in enumerate(asr))
    txt = c.llm("fix", M_FIX, [{"type": "text", "text": prompt}], 2500, "low")
    fx = parse_json(txt)
    words = [dict(w) for w in asr]; applied = []
    for f in fx.get("fixes", []):
        i, t = f.get("i"), (f.get("text") or "").strip()
        if isinstance(i, int) and 0 <= i < len(words) and t and " " not in t and t != words[i]["text"]:
            applied.append({"i": i, "from": words[i]["text"], "to": t}); words[i]["text"] = t
    jsave(out, words)
    jsave(os.path.join(c.job, "transcript_fix_meta.json"), {"model": M_FIX, "n_words": len(words), "n_changed": len(applied), "changes": applied, "notes": fx.get("notes")})
    return f"{len(applied)}/{len(words)} words corrected"

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
    log = parse_json(c.llm("shotlog", M_VIS, content, 6000, "low"))
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
    if not os.path.exists(sp):
        dur = proxy_duration(c.job)
        res = parse_json(c.llm("selects", M_SEL, [{"type": "text", "text": SELECTS_PROMPT.format(dur=dur, lines=lines, lmin=LEN_MIN, lmax=LEN_MAX)}], 3000, c.a.effort))
        jsave(sp, res)
    sel = jload(sp)["selects"]
    pick = c.a.select; from_job = None
    if not pick:
        chosen = [s for s in job.get("selects", []) if s.get("chosen")]
        if chosen and not c.a.fresh_selects:   # Hesham's earlier pick in job.json wins: use ITS range, not the new candidate with the same letter
            from_job = chosen[0]; pick = chosen[0]["id"]
    if not pick:
        print("\n   GATE 1 - Hesham picks the story. Candidates:")
        for s in sel: print(f"     {s['id']}  {s['range'][0]:.0f}-{s['range'][1]:.0f}s  {s['label']}  | {s['hook_line']}")
        print(f"   Re-run with --select A|B|C (or --select auto to take #1, only if you accept skipping the gate).")
        raise Stop("GATE 1 reached (not an error)")
    if from_job:
        s = {"id": from_job["id"], "range": from_job["range"], "label": from_job["label"], "hook_line": ""}; by = "hesham (job.json)"
    else:
        s = sel[0] if pick == "auto" else next((x for x in sel if x["id"] == pick), None); by = "auto (gate skipped)" if pick == "auto" else "hesham (--select)"
    if not s: raise Stop(f"unknown select {pick}")
    jsave(os.path.join(c.job, "chosen_select.json"), dict(s, picked_by=by))
    return f"select {s['id']} {s['range']}"

_C = cfg.BRAND["colors"]
BRAND = {"bg": _C["bg"], "accent_lime": _C["accent"], "secondary_violet": _C["secondary"],
         "negative_coral": _C["negative"] + " (loss/warning only)", "font": cfg.BRAND["font"]["family"], "canvas": "1080x1920 30fps"}
MOVES = """1 word-pop captions (1-3 words, pop on spoken word; keyword turns lime) [every beat has these]
2 mixed-weight words (Readex wght 200<->700)
3 text-behind-subject (big word/number behind head; needs matte, status NOT proven yet -> avoid unless essential)
4 concept B-roll cutaway (needs a real asset; no library exists yet -> set media.type="needs_asset" with a search query, never invent a file)
5 solid lime flash + 1 word (payoff only, MAX 2 per reel)
6 whip-blur zoom into screen recording (no screen recording exists in this take -> do not use)
7 punch-in zoom on face (crop of the same take, ~1s on a key word)
10 kinetic type card (condensed glowing headline on dark; chapter/key claim)
11 icon row on beat (3 icons, one per word; list moments)
14 before/after compare slider (needs two states; avoid unless story has them)
15 two-tone bold caption (white line + lime line) for the hook in first 3 s"""

PLAN_PROMPT = """You are the DIRECTOR of an automated reel factory for an Iraqi marketer (Hesham). Produce the scene plan for ONE reel as strict JSON. The renderer is a deterministic HTML/GSAP compositor; it only understands the fields below, so be precise and complete. Quality bar: a Gen-Z/Gen-Alpha viewer must see a visual change at least every 3 s and never be bored; the reel must be built from REAL media that exists.

BRAND: {brand}
CHOSEN STORY: id {sid}, source range {s0:.1f}-{s1:.1f}s of proxy.mp4 ("{label}"). Reel time 0 = source {s0:.1f}s. Total reel duration = {dur:.1f}s.
CTA INPUT: {cta}
MOVES AVAILABLE (catalogue number, name, constraint):
{moves}
RHYTHM RULES (validator enforces): beats contiguous from 0 to {dur:.1f}; hook beat <=3.0s and must use move 15 or 7 plus a caption; a visual change every <=3.5s (a beat is a visual change only if its media/move differs from the previous beat); never the same signature move (3,5,10,14) in two consecutive beats; lime flash (5) at most 2 and only on a real payoff; counter only if a number is actually spoken (spoken numbers in range: {numbers}); CTA only in the LAST beat, handle appears only there; captions cover EVERY spoken word (the renderer builds them from the transcript - you only choose keyword indices); no beat shorter than 0.8s.
MEDIA SOURCES allowed per beat (media.type): "proxy_cut" (a source time range of proxy.mp4, may be punched-in via crop.scale 1.0-1.6 and crop.cx/cy 0-1), "keyframe_still" (ref = a file from KEYFRAMES; a Ken-Burns push-in), "text_card" (generated kinetic card, no media needed), "flash" (solid lime), "needs_asset" (B-roll that must be found: give query; renderer substitutes a placeholder and the report flags it). Every beat MUST name one. Use speaker face box / headroom from the shot log to choose crops and to keep captions off the face (caption_zone: "top|middle|bottom").
Return ONLY JSON:
{{"hook":{{"line":"<=8 words Arabic, from speaker's words or a tight rewrite","keyword":"1 word"}},
"beats":[{{"id":"b1","t_in":0.0,"t_out":2.8,"src_in":{s0:.1f},"src_out":<source seconds>,"layout":"face_full|face_punch|card|broll|flash|cta","move":<catalogue # or null>,"media":{{"type":"proxy_cut|keyframe_still|text_card|flash|needs_asset","ref":"<keyframes/... or empty>","crop":{{"scale":1.0,"cx":0.5,"cy":0.4}},"query":"<only for needs_asset>"}},"caption":{{"style":"word_pop|two_tone|none","zone":"top|middle|bottom","keyword_word_indices":[<global word indices from the transcript>]}},"text_card":{{"headline":"","sub":""}},"fx_in":"cut|whip_blur|flash|none","why":"<=15 words"}}],
"counter":null,"cta":{{"words":"{cta_words}","promise":"{cta_promise}","handle":""}},
"risks":["<=3 items: what could look bad"],"assets_needed":["<=5 queries"]}}
Within a proxy_cut, src_out-src_in must equal t_out-t_in (no speed change) and lie inside {s0:.1f}-{s1:.1f}; beats with proxy_cut should follow the spoken line order (audio is the source audio, uncut), so src_in = s0 + t_in whenever audio continues. Use cutaways (keyframe_still/text_card/needs_asset) only as picture-over-voice: audio keeps playing, so still set src_in = s0 + t_in for timing.

SHOT LOG (t, face box, eyes, energy, usable):
{shots}

SILENCES in range (cut candidates): {sil}

TRANSCRIPT in range [t_start-t_end] (global word index first) text:
{lines}
"""

def st_plan(c):
    out = os.path.join(c.job, "scene_plan.json")
    if os.path.exists(out) and not c.a.replan: return "cached"
    sel = jload(os.path.join(c.job, "chosen_select.json")); s0, s1 = sel["range"]
    words = jload(os.path.join(c.job, "transcript.json"))
    shots = jload(os.path.join(c.job, "shot_log.json")); man = jload(os.path.join(c.job, "keyframes.json"))
    job = jload(os.path.join(c.job, "job.json"), {})
    inrange = [(a, b, t, i) for a, b, t, i in lines_from_words(words) if b > s0 and a < s1]
    lines = "\n".join(f"[{a:.1f}-{b:.1f}] ({i}) {t}" for a, b, t, i in inrange)
    sh = "\n".join("t=%.1f face=%s eyes=%s e=%s use=%s %s" % (r["t"], r.get("face") and [round(r["face"][k], 2) for k in "xywh"], r.get("eyes"), r.get("energy"), ",".join(r.get("usable", [])), r.get("note", ""))
                   for r in shots if s0 - 1 <= r["t"] <= s1 + 1)
    kf = ", ".join(f["file"] for f in man["frames"] if s0 - 1 <= f["t"] <= s1 + 1)
    sil = ""
    try:
        sil = "; ".join(re.findall(r"silence_start: ([0-9.]+)", open(os.path.join(c.job, "silences.txt")).read())[:30])
    except Exception: pass
    cta = (job.get("plan") or {}).get("cta") or {"text": "", "promise": ""}
    nums = [(i, t) for i, t in numbers_spoken(words) if s0 <= words[i]["start"] <= s1]
    prompt = PLAN_PROMPT.format(brand=json.dumps(BRAND), sid=sel["id"], s0=s0, s1=s1, label=sel["label"], dur=s1 - s0,
                                cta=json.dumps(cta, ensure_ascii=False), moves=MOVES, numbers=nums or "none", cta_words=cta.get("text", ""),
                                cta_promise=cta.get("promise", ""), shots=sh, sil=sil or "n/a", lines=lines) + "\nKEYFRAMES available: " + kf
    plan = parse_json(c.llm("plan", M_DIR, [{"type": "text", "text": prompt}], 9000, c.a.effort))
    plan.update({"job_id": os.path.basename(c.job), "select": sel["id"], "select_range": [s0, s1], "total_duration": s1 - s0, "director": M_DIR})
    jsave(out, plan); return f"{len(plan.get('beats', []))} beats"

def validate_plan(plan, words, keyframes):
    err, warn = [], []
    s0, s1 = plan["select_range"]; dur = s1 - s0; beats = plan.get("beats", [])
    if not beats: return ["no beats"], []
    prev_end = 0.0
    kfs = {f["file"] for f in keyframes["frames"]}
    signature = {3, 5, 10, 14}
    flashes = 0; last_sig = None; last_key = None; hold_start = 0.0
    for k, b in enumerate(beats):
        bid = b.get("id", k)
        if abs(b["t_in"] - prev_end) > 0.05: err.append(f"{bid}: gap/overlap at {prev_end:.2f}->{b['t_in']:.2f}")
        if b["t_out"] - b["t_in"] < 0.8: err.append(f"{bid}: shorter than 0.8s")
        prev_end = b["t_out"]
        m = b.get("media") or {}; mt = m.get("type")
        if mt not in ("proxy_cut", "keyframe_still", "text_card", "flash", "needs_asset"): err.append(f"{bid}: invalid media.type {mt}")
        if mt == "proxy_cut":
            if abs((b["src_out"] - b["src_in"]) - (b["t_out"] - b["t_in"])) > 0.1: err.append(f"{bid}: proxy_cut length != beat length")
            if b["src_in"] < s0 - 0.05 or b["src_out"] > s1 + 0.05: err.append(f"{bid}: source range outside select")
            sc = (m.get("crop") or {}).get("scale", 1.0)
            if not 1.0 <= sc <= 1.6: err.append(f"{bid}: crop.scale {sc} outside 1.0-1.6")
        if mt == "keyframe_still" and m.get("ref") not in kfs: err.append(f"{bid}: keyframe ref {m.get('ref')} does not exist")
        if mt == "needs_asset": warn.append(f"{bid}: needs asset: {m.get('query')}")
        mv = b.get("move")
        if mv == 5 or mt == "flash": flashes += 1
        if mv in signature and mv == last_sig: err.append(f"{bid}: signature move {mv} twice in a row")
        last_sig = mv if mv in signature else None
        if mv in (3, 6, 14): warn.append(f"{bid}: move {mv} depends on an unavailable asset/prototype")
        key = (mt, m.get("ref"), mv, round((m.get("crop") or {}).get("scale", 1.0), 1))
        if key != last_key: hold_start = b["t_in"]; last_key = key
        if b["t_out"] - hold_start > 3.5: err.append(f"{bid}: no visual change for {b['t_out'] - hold_start:.1f}s (>3.5)")
        if b.get("layout") == "cta" and k != len(beats) - 1: err.append(f"{bid}: CTA before the last beat")
    if abs(prev_end - dur) > 0.15: err.append(f"beats end at {prev_end:.2f}, reel is {dur:.2f}")
    if flashes > 2: err.append(f"{flashes} flashes (max 2)")
    h = beats[0]
    if h["t_out"] > 3.05: err.append("hook beat longer than 3s")
    if h.get("move") not in (15, 7): err.append("hook beat must use move 15 or 7")
    if (h.get("caption") or {}).get("style") in (None, "none"): err.append("hook beat has no caption")
    if beats[-1].get("layout") != "cta": err.append("last beat is not the CTA")
    if (plan.get("cta") or {}).get("handle") and beats[-1].get("layout") != "cta": err.append("handle outside CTA")
    spoken = [t for _, t in numbers_spoken([w for w in words if s0 <= w["start"] <= s1])]
    if plan.get("counter") and not spoken: err.append("counter used but no number is spoken in range")
    n = len(words)
    for b in beats:
        for i in (b.get("caption") or {}).get("keyword_word_indices", []) or []:
            if not (isinstance(i, int) and 0 <= i < n): err.append(f"{b.get('id')}: keyword index {i} invalid")
            elif not (s0 - 0.01 <= words[i]["start"] <= s1 + 0.01): warn.append(f"{b.get('id')}: keyword index {i} outside select range")
    return err, warn

def st_validate(c):
    plan = jload(os.path.join(c.job, "scene_plan.json")); words = jload(os.path.join(c.job, "transcript.json")); man = jload(os.path.join(c.job, "keyframes.json"))
    err, warn = validate_plan(plan, words, man); repaired = False
    if err and not c.a.no_repair:
        print("   validator errors -> one repair call:", *err[:8], sep="\n     - ")
        txt = c.llm("repair", M_DIR, [{"type": "text", "text": "Fix this reel scene plan JSON so it passes every validation error below. Change only what is needed; keep the same schema; return ONLY the full corrected JSON.\n\nERRORS:\n" + "\n".join(err) + "\n\nPLAN:\n" + json.dumps(plan, ensure_ascii=False)}], 9000, c.a.effort)
        fixed = parse_json(txt)
        for k in ("job_id", "select", "select_range", "total_duration", "director"): fixed[k] = plan[k]
        jsave(os.path.join(c.job, "scene_plan_attempt1.json"), plan); jsave(os.path.join(c.job, "scene_plan.json"), fixed)
        plan = fixed; repaired = True; err, warn = validate_plan(plan, words, man)
        if err and M_DIR_FALLBACK and M_DIR_FALLBACK != M_DIR:
            print(f"   still failing -> one repair with the fallback Director {M_DIR_FALLBACK}")
            txt = c.llm("repair_fallback", M_DIR_FALLBACK, [{"type": "text", "text": "Fix this reel scene plan JSON so it passes every validation error below. Change only what is needed; keep the same schema; return ONLY the full corrected JSON.\n\nERRORS:\n" + "\n".join(err) + "\n\nPLAN:\n" + json.dumps(plan, ensure_ascii=False)}], 9000, c.a.effort)
            fixed = parse_json(txt)
            for k in ("job_id", "select", "select_range", "total_duration"): fixed[k] = plan[k]
            fixed["director"] = M_DIR_FALLBACK
            jsave(os.path.join(c.job, "scene_plan_attempt2.json"), plan); jsave(os.path.join(c.job, "scene_plan.json"), fixed)
            plan = fixed; err, warn = validate_plan(plan, words, man)
    jsave(os.path.join(c.job, "validation.json"), {"errors": err, "warnings": warn, "repaired": repaired})
    if err: raise Stop("validation FAILED after repair: " + "; ".join(err[:5]))
    return f"PASS ({len(warn)} warnings{', repaired once' if repaired else ''})"

def st_report(c):
    cost = c.cost["calls"]; tot = sum(x["cost"] for x in cost)
    plan = jload(os.path.join(c.job, "scene_plan.json"), {}); val = jload(os.path.join(c.job, "validation.json"), {})
    fix = jload(os.path.join(c.job, "transcript_fix_meta.json"), {})
    L = [f"# Pipeline report - {os.path.basename(c.job)}", "", f"Total model spend this job: **${tot:.4f}** (budget ${c.a.budget:.2f})", "",
         "| stage | model | in tok | out tok | think tok | cost | s |", "|---|---|---|---|---|---|---|"]
    for x in cost: L.append(f"| {x['stage']} | {x['model'].split('/')[1]} | {x['in']} | {x['out']} | {x['reasoning']} | ${x['cost']:.4f} | {x['seconds']} |")
    L += ["", f"Transcript: {fix.get('n_changed')} of {fix.get('n_words')} words corrected by Haiku (changes in transcript_fix_meta.json).",
          f"Plan: {len(plan.get('beats', []))} beats, validation errors {len(val.get('errors', []))}, warnings {len(val.get('warnings', []))}, repaired once: {val.get('repaired')}.",
          "", "Warnings:"] + [f"- {w}" for w in val.get("warnings", [])] + ["", "Assets needed: " + "; ".join(plan.get("assets_needed", [])), "",
          "NOT done by this pipeline: assemble/render and the visual QA gate. Quality of the final video is judged by Hesham."]
    open(os.path.join(c.job, "pipeline_report.md"), "w").write("\n".join(L))
    return f"${tot:.4f} total"

FUNCS = {"ingest": st_ingest, "transcribe": st_transcribe, "fix": st_fix, "keyframes": st_keyframes, "shotlog": st_shotlog,
         "selects": st_selects, "plan": st_plan, "validate": st_validate, "report": st_report}

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input"); ap.add_argument("--slug"); ap.add_argument("--select"); ap.add_argument("--stop-after", choices=STAGES)
    ap.add_argument("--budget", type=float, default=cfg.BUDGET["per_reel_stop"]); ap.add_argument("--width", type=int, default=540); ap.add_argument("--every", type=float, default=2.0)
    ap.add_argument("--effort", default="low", choices=["low", "medium", "high"]); ap.add_argument("--force", default="")
    ap.add_argument("--asr-model", default=cfg.PROJECT["asr"]["model"]); ap.add_argument("--retranscribe", action="store_true")
    ap.add_argument("--fresh-selects", action="store_true"); ap.add_argument("--no-repair", action="store_true")
    a = ap.parse_args()
    a.img_tok = {1080: 2800, 720: 1300, 540: 800, 384: 420}.get(a.width, 800)
    a.rekey = a.replan = False
    inp = a.input
    if os.path.isfile(inp):
        if not a.slug: sys.exit("raw clip needs --slug")
        subprocess.run(["bash", os.path.join(ROOT, "scripts", "ingest.sh"), inp, a.slug], cwd=ROOT, env=ENV, check=True)
        inp = sorted(glob.glob(os.path.join(ROOT, "jobs", "*-" + a.slug)))[-1]
    job = os.path.abspath(inp)
    if not os.path.isdir(job): sys.exit(f"not a job folder: {job}")
    sys.stdout = Tee(os.path.join(job, "run.log"), sys.stdout)
    print(f"\n===== run {time.strftime('%Y-%m-%d %H:%M:%S')} | {' '.join(sys.argv[1:])}")
    c = Ctx(job, a)
    force = set(filter(None, a.force.split(",")))
    for s in force:
        for f in {"transcribe": ["transcript_asr.json"], "fix": ["transcript_fix_meta.json"], "keyframes": ["keyframes.json"], "shotlog": ["shot_log.json"],
                  "selects": ["selects.json", "chosen_select.json"], "plan": ["scene_plan.json"]}.get(s, []):
            if os.path.exists(os.path.join(job, f)): os.remove(os.path.join(job, f))
    if "keyframes" in force: a.rekey = True
    print(f"JOB {os.path.basename(job)} | budget ${a.budget:.2f} | spent so far ${c.spent():.4f}")
    t_all = time.time(); status = "ok"
    try:
        for s in STAGES:
            t0 = time.time(); before = c.spent()
            msg = FUNCS[s](c)
            c.timing[s] = round(time.time() - t0, 1); jsave(os.path.join(job, "timing.json"), c.timing)
            print(f"{s:11s} ok  {time.time() - t0:5.1f}s  +${c.spent() - before:.4f}  {msg}")
            if a.stop_after == s: break
    except Stop as e:
        status = "stopped"; print("STOP:", e)
    except Exception:
        import traceback
        status = "crashed"; print("CRASH (full error below, also in run.log):"); traceback.print_exc(file=sys.stdout)
        raise
    finally:
        # ledger: log only NEW spend of this run
        logged = c.cost.get("logged", 0.0); new = c.spent() - logged
        if new > 0.00005:
            subprocess.run([sys.executable, os.path.join(ROOT, "dashboard", "add_expense.py"), "--video", os.path.basename(job), "--category", "LLM", "API",
                            "--amount", f"{new:.4f}", "--note", f"reel.py run ({status}); measured provider usage.cost"], capture_output=True)
            c.cost["logged"] = c.spent(); jsave(c.cost_path, c.cost)
        print(f"TOTAL this job ${c.spent():.4f} | wall {time.time() - t_all:.0f}s")

if __name__ == "__main__":
    main()
