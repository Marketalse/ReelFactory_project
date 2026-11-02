"""Director plan v2: the AI picks blocks and anchors each one to a spoken word (by its number);
code turns that into exact times, checks every rule, and hands back named errors for one repair.

Plan JSON the Director returns:
{
  "hook": {"line1": "...", "line2": "..."},
  "keyword_ids": [12, 40],                       # words that turn lime in the captions
  "moments": [{"block": "text_card", "at_word": 34, "duration": 2.5, "values": {...}}],
  "punch_ins": [{"at_word": 20, "scale": 1.25}],
  "cta": {"type": "follow" | "comment", "line": "...", "promise": "...", "keyword": ""}
}
"""
import glob, json, os, re

from . import config as cfg
from .hfbuild import REGISTRY, check_values, BuildError

FULL_SCREEN = {"text_card", "flash", "number_graph", "before_after", "tier_list", "pixel_scene"}          # the face is hidden: captions pause
DIRECTOR_BLOCKS = ["text_card", "split", "flash", "logo_card", "name_tag", "info_card", "number_graph", "before_after", "tier_list", "ui_card", "doc_card", "pixel_scene", "text_behind"]   # what the Director may place as moments
DIGITS = re.compile(r"[0-9][0-9,.]*")


def catalogue():
    lines = []
    for name in DIRECTOR_BLOCKS:
        b = REGISTRY["blocks"][name]
        ins = ", ".join(f'{k}{"*" if v.get("required") else ""}({v["type"]}{", max " + str(v["maxLength"]) if v.get("maxLength") else ""})'
                        for k, v in b["inputs"].items())
        d = b["duration_s"]
        rules = "; ".join(b.get("rules", []))
        lines.append(f'- {name}: {b["purpose"]} values: {ins}. duration {d["min"]}-{d["max"]} s.{" Rules: " + rules + "." if rules else ""}')
    return "\n".join(lines)


def numbered_transcript(words, per_line=12, marks=()):
    marks = set(marks or ())
    out, line = [], []
    for i, w in enumerate(words):
        if not line:
            line_t = w["start"]
        line.append(f"({i}){w['text']}{'!' if i in marks else ''}")
        if len(line) >= per_line or i == len(words) - 1 or words[i + 1]["start"] - w["end"] > 0.3:
            out.append(f"[{line_t:5.1f}s] " + " ".join(line)); line = []
    return "\n".join(out)


def spoken_numbers(words):
    return sorted({DIGITS.search(w["text"]).group(0).rstrip(".,") for w in words if DIGITS.search(w["text"])})


PROMPT = """You are the DIRECTOR of an automated reel factory for Hesham, an Iraqi marketer in Erbil. The reel is ALREADY CUT
(pauses and retakes removed). You decide what appears on screen and when, by anchoring each visual to a spoken word
number. A deterministic renderer builds the video from fixed templates; it only understands the JSON below.

AUDIENCE: Iraqi Gen-Z / young business owners on Instagram and TikTok. Something must change on screen at least every
{hold} s. Frame 0 is the thumbnail: the hook title is on screen from 0 s.
BRAND: {brand}
REEL LENGTH: {dur:.1f} s. {cta_note}
BRIEF FROM HESHAM: {brief}
LOGO FILES AVAILABLE (logo_card may only use these): {logos}
NUMBERS ACTUALLY SPOKEN (split.value / number_graph.value+percent / flash.word may only use these): {numbers}

BLOCKS YOU CAN PLACE AS MOMENTS (* = required value):
{catalogue}
Also: punch_ins = a quick zoom on the face at a key word (scale 1.1-1.5), the cheapest visual change. Use them often.
A word followed by ! in the transcript was SAID WITH EMPHASIS (louder): prefer those words for punch_ins and keyword_ids.

RULES:
- Everything on screen comes from what he said: same words, his spelling, Western digits. Never invent numbers, names or claims.
- hook.line1 (max 28 chars) + hook.line2 (max 22 chars, the punchiest words) come from his own words in the first sentences.
- keyword_ids: 1 keyword per 2-4 seconds of speech, the words that carry the meaning.
- flash: at most {flash_max}, only on a payoff or a spoken number. text_card: at least {tc_gap} s apart; one every {chapter} s on long reels.
- Never two full-screen moments (text_card, flash, number_graph, before_after, tier_list, pixel_scene) back to back.
- BE VISUALLY AMBITIOUS, never basic: a new visual (card, graphic or zoom) every 2.5-3 s, and VARIETY: in a 60 s reel use at least 4 different block types and never the same block twice in a row. Match the visual to what he says: text_behind for the ONE most important keyword (once per reel), pixel_scene when he describes a team, a person or a place, ui_card or doc_card when he mentions a tool, dashboard, document or plan (ui_card.image only from the LIBRARY PICTURES in the brief), number_graph/split when he says a number, before_after/tier_list when he compares or ranks, info_card for one explained point.
- name_tag only when he says a name out loud; before_after and tier_list only when he really compares or ranks; info_card to explain one point.{cta_rules}
- values must fit the max lengths exactly.
- cover = the reel's cover image (thumbnail). Its big title is the hook. Add, only if it fits what he said:
  tag (max 16 chars, a short topic label in English capitals from a term he used, e.g. "STOCK TIPS"),
  sticker (max 18 chars, a short question or phrase he said, English terms in Latin letters),
  card_label (max 24 chars) + card_value (max 26 chars): a formula or result he actually said, spoken numbers only (e.g. "1,200 × 3 = 3,600").
  Leave any of them "" when there is nothing real for it.

TRANSCRIPT (reel time, (word number)word):
{transcript}

Return ONLY JSON:
{{"hook":{{"line1":"","line2":""}},"keyword_ids":[],"moments":[{{"block":"","at_word":0,"duration":0,"values":{{}}}}],
"punch_ins":[{{"at_word":0,"scale":1.25}}],{cta_json}
"cover":{{"tag":"","sticker":"","card_label":"","card_value":""}}}}"""


TASTE_MAX = 1800


def taste(root=None, skip_job=None, limit=12):
    """Hesham's standing preferences: the 'Hesham's taste' lessons plus his recent editing comments on earlier reels
    (newest first, word fixes and plain retries left out). Short, so it costs little."""
    root = root or cfg.ROOT
    out = []
    try:
        txt = open(os.path.join(root, ".reel-agent", "lessons.md"), encoding="utf-8").read()
        sec = txt.split("## Hesham's taste", 1)[1].split("\n## ", 1)[0]
        out += [l.strip()[2:] for l in sec.splitlines() if l.strip().startswith("- ")]
    except (OSError, IndexError):
        pass
    notes = []
    for jp in glob.glob(os.path.join(root, "jobs", "*", "job.json")):
        job = os.path.basename(os.path.dirname(jp))
        if job == skip_job:
            continue
        try:
            hist = json.load(open(jp, encoding="utf-8")).get("feedback_history") or []
        except (OSError, ValueError):
            continue
        for h in hist:
            if h.get("rejected"):                      # he went back to an earlier draft: the change he asked for did not work for him
                notes.append((h.get("time", ""), f"He did not like the result of: \"{str(h['rejected'])[:120]}\" (he went back to an earlier draft)"))
            for line in str(h.get("fix", "")).splitlines():
                line = line.strip()
                if line and "=>" not in line and not line.startswith("(") and len(line) > 3:
                    notes.append((h.get("time", ""), line))
    seen = set()
    for _, line in sorted(notes, reverse=True):
        if line.lower() not in seen:
            seen.add(line.lower()); out.append(f"{line} (his comment on an earlier reel)")
        if len(seen) >= limit:
            break
    text = "\n".join("- " + l for l in out)
    return text[:TASTE_MAX]


def build_prompt(words, dur, brief="", logos=(), feedback="", prefs="", marks=()):
    r = cfg.RULES
    c = cfg.BRAND["colors"]
    p = PROMPT.format(
        hold=r["max_still_hold_s"], brand=f'bg {c["bg"]}, lime {c["accent"]}, violet {c["secondary"]}, font Readex Pro',
        dur=dur, cta_note=(f"CTA occupies the last {CTA_DUR} s automatically." if cta_on() else
                           "No end card, no follow ask, no handle: the reel stays clean and ends on his face."),
        cta_rules=(f' Never a moment inside the last {CTA_DUR} s.\n- cta.type "follow" unless the brief gives a comment keyword. '
                   "cta.line/promise in his Iraqi dialect, short." if cta_on() else ""),
        cta_json=('"cta":{"type":"follow","line":"","promise":"","keyword":""},' if cta_on() else ""), brief=brief.strip() or "none", logos=", ".join(logos) or "none",
        numbers=", ".join(spoken_numbers(words)) or "none", catalogue=catalogue(),
        flash_max=r["moments"]["flash"]["max_per_reel"], tc_gap=r["moments"]["text_card"]["min_gap_s"],
        chapter="-".join(str(x) for x in r["chapter_card_every_s"]), transcript=numbered_transcript(words, marks=marks))
    if prefs:
        p += ("\n\nHESHAM'S STANDING PREFERENCES (from his earlier comments; follow them unless his notes for this reel say otherwise):\n" + prefs)
    if feedback:
        p += f"\n\nHESHAM'S FEEDBACK ON THE LAST VERSION (apply it, change nothing else):\n{feedback}"
    return p


HOOK_MAX = (28, 22)


def _fit(words, limit):
    """Longest run of whole words (from the start) that fits in `limit` characters."""
    out = []
    for w in words:
        if len(" ".join(out + [w])) > limit:
            break
        out.append(w)
    return out


def fix_hook(h, edl_words=()):
    """The hook always needs two lines. If the AI gave one (or none), split his own words into two lines:
    line 2 gets the last, punchiest words. Never adds words he didn't say; trims at word boundaries to fit."""
    l1 = " ".join(str(h.get("line1") or "").split()); l2 = " ".join(str(h.get("line2") or "").split())
    if not l1 or not l2:
        words = (l1 or l2).split()
        if len(words) < 2:                                  # nothing usable: his first spoken words
            words = [w["text"] for w in list(edl_words)[:8]] or words
        if len(words) >= 2:
            k = max(1, len(words) // 2)
            l1, l2 = " ".join(words[:k]), " ".join(words[k:])
    if len(l1) > HOOK_MAX[0]:
        l1 = " ".join(_fit(l1.split(), HOOK_MAX[0])) or l1[:HOOK_MAX[0]]
    if len(l2) > HOOK_MAX[1]:
        l2 = " ".join(_fit(l2.split(), HOOK_MAX[1])) or l2[:HOOK_MAX[1]]
    return dict(h, line1=l1, line2=l2)


CTA_DUR = 3.5


def cta_on():
    """End card (follow ask + handle) on or off: config/brand.json -> cta.enabled. Off = the reel ends on his face."""
    return bool(cfg.BRAND.get("cta", {}).get("enabled", True))


def cta_dur():
    return CTA_DUR if cta_on() else 0.0
HOOK_DUR = 2.6


def resolve(plan, edl_words, duration, *, logos=(), platform_handle="@handle", relaxed=False):
    """Turn a plan into an exact timeline. Returns (timeline, errors, warnings).
    timeline = {"duration", "scenes": [...], "frames": [(t, scale, y)], "keyword_ids", "caption_gaps": [(a,b)]}"""
    err, warn = [], []
    n = len(edl_words)
    r = cfg.RULES
    scenes, frames = [], []
    cta_t = max(0.0, duration - cta_dur())

    def at(w, where):
        if not isinstance(w, int) or not 0 <= w < n:
            err.append(f"{where}: at_word {w!r} is not a word number 0-{n - 1}")
            return None
        return max(0.0, edl_words[w]["start"] - 0.05)

    h = fix_hook(plan.get("hook") or {}, edl_words)
    plan["hook"] = h
    try:
        check_values("hook_two_tone", {"line1": h.get("line1", ""), "line2": h.get("line2", "")}, "hook")
    except BuildError as e:
        err.append(str(e))
    scenes.append({"id": "hook", "block": "hook_two_tone", "t_in": 0.0, "t_out": min(HOOK_DUR, cta_t),
                   "values": {"line1": h.get("line1", ""), "line2": h.get("line2", "")}})

    spoken = set(spoken_numbers(edl_words))
    counts, last_t = {}, {}
    for k, m in enumerate(plan.get("moments") or []):
        where = f"moments[{k}] ({m.get('block')})"
        b = m.get("block")
        if b not in DIRECTOR_BLOCKS:
            err.append(f"{where}: block must be one of {DIRECTOR_BLOCKS}"); continue
        t = at(m.get("at_word"), where)
        if t is None:
            continue
        spec = REGISTRY["blocks"][b]["duration_s"]
        if relaxed:                              # Edit page: you may stretch or shrink a clip well beyond the AI's usual range
            spec = {"min": 0.5, "max": max(spec["max"] * 3, 8.0)}
        d = float(m.get("duration") or spec["min"])
        if not spec["min"] <= d <= spec["max"]:
            warn.append(f"{where}: duration {d} clamped to {spec['min']}-{spec['max']} s")
            d = min(max(d, spec["min"]), spec["max"])
        vals = dict(m.get("values") or {})
        try:
            check_values(b, vals, where)
        except BuildError as e:
            err.append(str(e)); continue
        if t < HOOK_DUR - 0.05:
            err.append(f"{where}: starts at {t:.1f}s, inside the hook (first {HOOK_DUR} s)")
        if t + d > cta_t + 0.01:
            err.append(f"{where}: ends at {t + d:.1f}s, inside the CTA (from {cta_t:.1f}s)" if cta_on()
                       else f"{where}: ends at {t + d:.1f}s, after the reel ends ({duration:.1f}s)")
        if b == "split" and vals.get("value") and DIGITS.search(vals["value"]) and DIGITS.search(vals["value"]).group(0).rstrip(".,") not in spoken:
            err.append(f"{where}: value {vals['value']!r} is not a number he said ({', '.join(sorted(spoken)) or 'none spoken'})")
        if b == "number_graph":
            for key in ("value", "percent"):
                mm = DIGITS.search(vals.get(key, "") or "")
                if mm and mm.group(0).rstrip(".,") not in spoken:
                    err.append(f"{where}: {key} {vals[key]!r} is not a number he said ({', '.join(sorted(spoken)) or 'none spoken'})")
        if b == "flash" and DIGITS.search(vals.get("word", "")) and DIGITS.search(vals["word"]).group(0).rstrip(".,") not in spoken:
            err.append(f"{where}: word {vals['word']!r} is a number he did not say")
        if b == "ui_card" and vals.get("image"):
            f = vals["image"]
            if os.path.basename(f) not in logos:
                err.append(f"{where}: image {f!r} is not in the reel's assets/ (have: {', '.join(logos) or 'none'})")
            else:
                vals["image"] = "assets/logos/" + os.path.basename(f)
        if b == "logo_card":
            for key in ("logo_a", "logo_b"):
                f = vals.get(key)
                if f and os.path.basename(f) not in logos:
                    err.append(f"{where}: {key} {f!r} is not in the reel's assets/ (have: {', '.join(logos) or 'none'})")
                elif f:
                    vals[key] = "assets/logos/" + os.path.basename(f)
        gap = r["moments"].get(b, {}).get("min_gap_s")
        if gap and b in last_t and t - last_t[b] < gap:
            err.append(f"{where}: only {t - last_t[b]:.1f}s after the previous {b}; minimum {gap} s")
        last_t[b] = t
        counts[b] = counts.get(b, 0) + 1
        scenes.append({"id": f"m{k}", "block": b, "t_in": round(t, 3), "t_out": round(t + d, 3), "values": vals})
    fmax = r["moments"]["flash"]["max_per_reel"]
    if counts.get("flash", 0) > fmax:
        err.append(f"{counts['flash']} flashes; maximum {fmax}")
    for bk, n_ in counts.items():                                 # any other block with a per-reel maximum (e.g. text_behind)
        mx = r["moments"].get(bk, {}).get("max_per_reel")
        if bk != "flash" and mx and n_ > mx:
            err.append(f"{n_} {bk} moments; maximum {mx} per reel")

    # overlaps between moments (all moment blocks occupy the screen)
    ms = sorted([s for s in scenes if s["block"] in DIRECTOR_BLOCKS], key=lambda s: s["t_in"])
    for a, b in zip(ms, ms[1:]):
        if b["t_in"] < a["t_out"] - 0.01:
            err.append(f"{b['id']} ({b['block']}) starts at {b['t_in']:.1f}s before {a['id']} ({a['block']}) ends at {a['t_out']:.1f}s")
        elif a["block"] in FULL_SCREEN and b["block"] in FULL_SCREEN and b["t_in"] - a["t_out"] < 1.0:
            err.append(f"{a['id']} and {b['id']}: two full-screen moments back to back; put face time between them")

    for k, p in enumerate(plan.get("punch_ins") or []):
        if "at_word" not in p and "at_time" in p:                  # a zoom placed by time (the automatic rhythm fix uses it where no word helps)
            t = p.get("at_time")
            if not isinstance(t, (int, float)) or not HOOK_DUR <= t <= duration - 0.4:
                err.append(f"punch_ins[{k}]: at_time {t!r} is outside the reel"); continue
            t = float(t)
        else:
            t = at(p.get("at_word"), f"punch_ins[{k}]")
        sc = p.get("scale", 1.25)
        if not isinstance(sc, (int, float)) or not 1.1 <= sc <= 1.5:
            err.append(f"punch_ins[{k}]: scale {sc!r} must be 1.1-1.5"); continue
        if t is not None:
            frames.append((round(t, 3), float(sc)))

    if cta_on():
        c = plan.get("cta") or {}
        cta_vals = {"line": c.get("line", ""), "promise": c.get("promise", ""), "keyword": c.get("keyword", "") if c.get("type") == "comment" else "",
                    "handle": platform_handle}
        try:
            check_values("cta_card", cta_vals, "cta")
        except BuildError as e:
            err.append(str(e))
        scenes.append({"id": "cta", "block": "cta_card", "t_in": round(cta_t, 3), "t_out": round(duration, 3), "values": cta_vals})

    kw = [i for i in (plan.get("keyword_ids") or []) if isinstance(i, int) and 0 <= i < n]
    if len(kw) != len(plan.get("keyword_ids") or []):
        warn.append("some keyword_ids were not valid word numbers and were ignored")
    gaps = [(s["t_in"], s["t_out"]) for s in scenes if s["block"] in FULL_SCREEN or s["block"] == "cta_card"]
    return {"duration": round(duration, 3), "scenes": scenes, "punch_ins": sorted(frames), "keyword_ids": kw,
            "caption_gaps": gaps}, err, warn


def face_cuts(timeline, segments):
    """Face video pieces: one per EDL segment, split again at punch-ins and around split cards.
    Successive EDL pieces alternate 1.0 / 1.08 zoom so jump cuts read as deliberate."""
    cuts_at = {0.0, timeline["duration"]}
    for s in segments:
        cuts_at.update((s["t_in"], s["t_out"]))
    punch = timeline["punch_ins"]
    for t, _ in punch:
        cuts_at.update((t, min(t + 1.6, timeline["duration"])))
    splits = [(s["t_in"], s["t_out"]) for s in timeline["scenes"] if s["block"] == "split"]
    for a, b in splits:
        cuts_at.update((a, b))
    behind = [(s["t_in"], s["t_out"]) for s in timeline["scenes"] if s["block"] == "text_behind"]     # the cutout needs the plain, unzoomed picture
    for a, b in behind:
        cuts_at.update((a, b))
    pts = sorted(t for t in cuts_at if 0 <= t <= timeline["duration"])
    out = []
    for a, b in zip(pts, pts[1:]):
        if b - a < 1e-4:
            continue                      # same instant; any real sliver is kept here and folded in by absorb_short
        seg_i = next(i for i, s in enumerate(segments) if s["t_in"] - 1e-6 <= a < s["t_out"] - 1e-6) if any(
            s["t_in"] - 1e-6 <= a < s["t_out"] - 1e-6 for s in segments) else len(segments) - 1
        seg = segments[seg_i]
        scale = 1.08 if seg_i % 2 else 1.0
        for t, sc in punch:
            if t <= a + 1e-6 < t + 1.6:
                scale = sc
        if any(x <= a + 1e-6 < y2 for x, y2 in behind):
            scale = 1.0
        y = 480 if any(x <= a + 1e-6 < y2 for x, y2 in splits) else 0
        out.append({"id": f"seg{len(out)}", "t_in": round(a, 3), "t_out": round(b, 3),
                    "src_in": round(seg["src_in"] + (a - seg["t_in"]), 3), "scale": scale,
                    "cy": timeline.get("face_cy", 0.36), "y": y})
    # merge neighbours that are the same continuous shot with the same framing
    merged = []
    for f in out:
        p = merged[-1] if merged else None
        if p and p["scale"] == f["scale"] and p["y"] == f["y"] and abs(p["src_in"] + (p["t_out"] - p["t_in"]) - f["src_in"]) < 0.02:
            p["t_out"] = f["t_out"]
        else:
            merged.append(f)
    merged = absorb_short(merged)
    for i, f in enumerate(merged):
        f["id"] = f"seg{i}"
    return merged


MIN_CUT = 0.3     # the renderer refuses shorter face pieces; slivers come from a zoom/card starting just after a cut


def absorb_short(cuts, min_d=MIN_CUT):
    """Fold pieces shorter than min_d into a neighbour. Prefer the neighbour that continues the same
    footage (then nothing visible changes but the zoom); otherwise the previous piece runs on, or the
    next piece starts earlier (a sliver of under 0.3 s, too short to notice)."""
    cuts = [dict(c) for c in cuts]
    dur = lambda c: c["t_out"] - c["t_in"]
    cont = lambda a, b: abs(a["src_in"] + dur(a) - b["src_in"]) < 0.02      # b continues a's footage
    while len(cuts) > 1:
        i = next((k for k, c in enumerate(cuts) if dur(c) < min_d - 1e-6), None)
        if i is None:
            break
        f = cuts[i]; p = cuts[i - 1] if i > 0 else None; n = cuts[i + 1] if i + 1 < len(cuts) else None
        if p and cont(p, f):
            p["t_out"] = f["t_out"]
        elif n and cont(f, n):
            n["t_in"], n["src_in"] = f["t_in"], f["src_in"]
        elif p:
            p["t_out"] = f["t_out"]
        else:
            n["src_in"] = round(n["src_in"] - dur(f), 3); n["t_in"] = f["t_in"]
        del cuts[i]
    return cuts


def longest_still(timeline, cuts):
    """Longest stretch with no visual change (cut, zoom change, or a scene starting/ending)."""
    ch = {0.0, timeline["duration"]}
    for f in cuts:
        ch.update((f["t_in"], f["t_out"]))
    for s in timeline["scenes"]:
        ch.update((s["t_in"], s["t_out"]))
    pts = sorted(ch)
    best = max(((b - a, a, b) for a, b in zip(pts, pts[1:])), default=(0, 0, 0))
    return best


STILL_ERR = re.compile(r"nothing changes on screen from ([\d.]+)s to ([\d.]+)s")


PUNCH_LEN = 1.6          # a punch-in zooms for this long, then returns (face_cuts uses the same number)


def _gap(err):
    m = STILL_ERR.search(err[0]) if err else None
    return (float(m.group(1)), float(m.group(2))) if m else None


def fix_rhythm(plan, words, resolve, max_add=None):
    """FREE, no AI. While the only problem left is 'nothing changes on screen for too long', add a quick zoom (punch-in) in that stretch.
    A zoom on a word changes the picture when it starts AND when it ends 1.6 s later, so any word whose start or end lands inside the
    stretch helps (nearest the middle first). A stretch with no useful word (speech the transcriber missed, a silent part) gets a zoom
    anchored by TIME in its middle. A try that changes nothing is undone and another spot is tried. Bounded: at most about one zoom
    per 3 s of reel. resolve(plan) -> (timeline, errors, warnings). Returns (plan, timeline, errors, warnings, added)."""
    plan = json.loads(json.dumps(plan))
    if max_add is None:                                         # about one zoom per 3 s of reel at the very most
        max_add = 4 + int((words[-1].get("end", words[-1].get("start", 0)) if words else 0) / 3)
    added, stuck, tried = 0, 0, set()
    tl, err, warn = resolve(plan)
    while err and added < max_add and stuck < 12 and all(STILL_ERR.search(x) for x in err):
        a, b = _gap(err)
        mid = (a + b) / 2
        starts = []                                             # where the zooms already in the plan begin
        for p in plan.get("punch_ins") or []:
            if "at_word" in p and isinstance(p["at_word"], int) and 0 <= p["at_word"] < len(words):
                starts.append(max(0.0, words[p["at_word"]]["start"] - 0.05))
            elif "at_time" in p:
                starts.append(float(p["at_time"]))
        free = lambda t0: all(t0 >= s0 + PUNCH_LEN + 0.35 or t0 + PUNCH_LEN + 0.35 <= s0 for s0 in starts)   # zooms that touch merge into one: no visible change
        have = {p.get("at_word") for p in plan.get("punch_ins") or [] if "at_word" in p}
        cands = []
        for i, w in enumerate(words):
            if i in have or ("w", i) in tried:
                continue
            t0 = max(0.0, w["start"] - 0.05)
            hits = [abs(x - mid) for x in (t0, t0 + PUNCH_LEN) if a + 0.4 <= x <= b - 0.4]
            if hits and free(t0):
                cands.append((min(hits), i))
        if cands:
            k = min(cands)[1]; new, key = {"at_word": k, "scale": 1.25}, ("w", k)
        else:                                                   # no word helps here: anchor the zoom by time in the middle of the stretch
            t0 = next((round(mid - PUNCH_LEN / 2 + d, 2) for d in (0, -0.5, 0.5, -1.0, 1.0, -1.5, 1.5)
                       if a + 0.3 <= mid - PUNCH_LEN / 2 + d and mid + PUNCH_LEN / 2 + d <= b - 0.3 and free(mid - PUNCH_LEN / 2 + d)), None)
            if t0 is None or ("t", t0) in tried:
                break
            key, new = ("t", t0), {"at_time": t0, "scale": 1.25}
        plan.setdefault("punch_ins", []).append(new)
        tl2, err2, warn2 = resolve(plan)
        g2 = _gap(err2) if err2 and all(STILL_ERR.search(x) for x in err2) else None
        tried.add(key)
        if g2 and abs(g2[0] - a) < 0.05 and abs(g2[1] - b) < 0.05:      # nothing changed: undo it and try another spot
            plan["punch_ins"].pop(); stuck += 1
            continue
        added += 1; tl, err, warn = tl2, err2, warn2
    return plan, tl, err, warn, added


OVERLAP_ERR = re.compile(r"m(\d+) \((\w+)\) starts at ([\d.]+)s before m(\d+) \((\w+)\) ends at ([\d.]+)s")


def fix_overlaps(plan, resolve, max_fix=12):
    """FREE, no AI. While the only problem left is 'two moments on screen at once': make the earlier one end a little sooner
    (if it stays long enough), otherwise drop the later one. Bounded by max_fix. Returns (plan, timeline, errors, warnings, fixed)."""
    plan = json.loads(json.dumps(plan))
    fixed = 0
    tl, err, warn = resolve(plan)
    while err and fixed < max_fix and all(OVERLAP_ERR.search(x) for x in err):
        m = OVERLAP_ERR.search(err[0])
        kb, ka = int(m.group(1)), int(m.group(4))
        xs, ye = float(m.group(3)), float(m.group(6))
        moms = plan.get("moments") or []
        if not (0 <= ka < len(moms) and 0 <= kb < len(moms)):
            break
        a = moms[ka]
        spec = REGISTRY["blocks"][a["block"]]["duration_s"]
        d = float(a.get("duration") or spec["min"])
        new_d = round(d - (ye - xs) - 0.1, 2)
        if new_d >= spec["min"]:
            a["duration"] = new_d
        else:
            moms.pop(kb)
        fixed += 1
        tl, err, warn = resolve(plan)
    return plan, tl, err, warn, fixed


def check_rhythm(timeline, cuts):
    d, a, b = longest_still(timeline, cuts)
    lim = cfg.RULES["max_still_hold_s"]
    if d > lim + 0.05:
        return [f"nothing changes on screen from {a:.1f}s to {b:.1f}s ({d:.1f}s > {lim}s): add a punch_in or a moment there"]
    return []
