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
import json, os, re

from . import config as cfg
from .hfbuild import REGISTRY, check_values, BuildError

FULL_SCREEN = {"text_card", "flash"}          # the face is hidden: captions pause
DIRECTOR_BLOCKS = ["text_card", "split", "flash", "logo_card"]   # what the Director may place as moments
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


def numbered_transcript(words, per_line=12):
    out, line = [], []
    for i, w in enumerate(words):
        if not line:
            line_t = w["start"]
        line.append(f"({i}){w['text']}")
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
REEL LENGTH: {dur:.1f} s. CTA occupies the last {cta_dur} s automatically.
BRIEF FROM HESHAM: {brief}
LOGO FILES AVAILABLE (logo_card may only use these): {logos}
NUMBERS ACTUALLY SPOKEN (split.value / flash.word may only use these): {numbers}

BLOCKS YOU CAN PLACE AS MOMENTS (* = required value):
{catalogue}
Also: punch_ins = a quick zoom on the face at a key word (scale 1.1-1.5), the cheapest visual change. Use them often.

RULES:
- Everything on screen comes from what he said: same words, his spelling, Western digits. Never invent numbers, names or claims.
- hook.line1 (max 28 chars) + hook.line2 (max 22 chars, the punchiest words) come from his own words in the first sentences.
- keyword_ids: 1 keyword per 2-4 seconds of speech, the words that carry the meaning.
- flash: at most {flash_max}, only on a payoff or a spoken number. text_card: at least {tc_gap} s apart; one every {chapter} s on long reels.
- Never two full-screen moments (text_card, flash) back to back; never a moment inside the last {cta_dur} s.
- cta.type "follow" unless the brief gives a comment keyword. cta.line/promise in his Iraqi dialect, short.
- values must fit the max lengths exactly.

TRANSCRIPT (reel time, (word number)word):
{transcript}

Return ONLY JSON:
{{"hook":{{"line1":"","line2":""}},"keyword_ids":[],"moments":[{{"block":"","at_word":0,"duration":0,"values":{{}}}}],
"punch_ins":[{{"at_word":0,"scale":1.25}}],"cta":{{"type":"follow","line":"","promise":"","keyword":""}}}}"""


def build_prompt(words, dur, brief="", logos=(), feedback=""):
    r = cfg.RULES
    c = cfg.BRAND["colors"]
    p = PROMPT.format(
        hold=r["max_still_hold_s"], brand=f'bg {c["bg"]}, lime {c["accent"]}, violet {c["secondary"]}, font Readex Pro',
        dur=dur, cta_dur=CTA_DUR, brief=brief.strip() or "none", logos=", ".join(logos) or "none",
        numbers=", ".join(spoken_numbers(words)) or "none", catalogue=catalogue(),
        flash_max=r["moments"]["flash"]["max_per_reel"], tc_gap=r["moments"]["text_card"]["min_gap_s"],
        chapter="-".join(str(x) for x in r["chapter_card_every_s"]), transcript=numbered_transcript(words))
    if feedback:
        p += f"\n\nHESHAM'S FEEDBACK ON THE LAST VERSION (apply it, change nothing else):\n{feedback}"
    return p


CTA_DUR = 3.5
HOOK_DUR = 2.6


def resolve(plan, edl_words, duration, *, logos=(), platform_handle="@handle"):
    """Turn a plan into an exact timeline. Returns (timeline, errors, warnings).
    timeline = {"duration", "scenes": [...], "frames": [(t, scale, y)], "keyword_ids", "caption_gaps": [(a,b)]}"""
    err, warn = [], []
    n = len(edl_words)
    r = cfg.RULES
    scenes, frames = [], []
    cta_t = max(0.0, duration - CTA_DUR)

    def at(w, where):
        if not isinstance(w, int) or not 0 <= w < n:
            err.append(f"{where}: at_word {w!r} is not a word number 0-{n - 1}")
            return None
        return max(0.0, edl_words[w]["start"] - 0.05)

    h = plan.get("hook") or {}
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
            err.append(f"{where}: ends at {t + d:.1f}s, inside the CTA (from {cta_t:.1f}s)")
        if b == "split" and vals.get("value") and DIGITS.search(vals["value"]) and DIGITS.search(vals["value"]).group(0).rstrip(".,") not in spoken:
            err.append(f"{where}: value {vals['value']!r} is not a number he said ({', '.join(sorted(spoken)) or 'none spoken'})")
        if b == "flash" and DIGITS.search(vals.get("word", "")) and DIGITS.search(vals["word"]).group(0).rstrip(".,") not in spoken:
            err.append(f"{where}: word {vals['word']!r} is a number he did not say")
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

    # overlaps between moments (all moment blocks occupy the screen)
    ms = sorted([s for s in scenes if s["block"] in DIRECTOR_BLOCKS], key=lambda s: s["t_in"])
    for a, b in zip(ms, ms[1:]):
        if b["t_in"] < a["t_out"] - 0.01:
            err.append(f"{b['id']} ({b['block']}) starts at {b['t_in']:.1f}s before {a['id']} ({a['block']}) ends at {a['t_out']:.1f}s")
        elif a["block"] in FULL_SCREEN and b["block"] in FULL_SCREEN and b["t_in"] - a["t_out"] < 1.0:
            err.append(f"{a['id']} and {b['id']}: two full-screen moments back to back; put face time between them")

    for k, p in enumerate(plan.get("punch_ins") or []):
        t = at(p.get("at_word"), f"punch_ins[{k}]")
        sc = p.get("scale", 1.25)
        if not isinstance(sc, (int, float)) or not 1.1 <= sc <= 1.5:
            err.append(f"punch_ins[{k}]: scale {sc!r} must be 1.1-1.5"); continue
        if t is not None:
            frames.append((round(t, 3), float(sc)))

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


def check_rhythm(timeline, cuts):
    d, a, b = longest_still(timeline, cuts)
    lim = cfg.RULES["max_still_hold_s"]
    if d > lim + 0.05:
        return [f"nothing changes on screen from {a:.1f}s to {b:.1f}s ({d:.1f}s > {lim}s): add a punch_in or a moment there"]
    return []
