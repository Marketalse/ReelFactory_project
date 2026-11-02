"""Stage 4 editorial helpers. Free, local. The AI only proposes; this code checks and scores.

  - story score  S = wR*R + wC*C + wD*D + wN*N + wF*F  (weights in config/rules.json -> story_score; proposed starting
    values, not proven predictors). R relevance, C clarity, D delivery, N novelty, F narrative fit, each 1-10 from the AI,
    except D, which is blended with a measured delivery score from the real audio (speech_intel.json) when it exists.
  - hooks must be Hesham's own words: each hook line is looked up in the transcript and given its time.
  - a story range must be a sensible length and start/end between words, not inside one.
  - continuity: cuts that jump inside a sentence, very tight cuts, a first cut that starts on a filler.
  - editorial.json: the decisions as plain instructions (source ranges, alternatives, rationale, confidence flags), written
    next to the timeline. Nothing here touches a video file.
"""
import json, os, re

DEFAULT_WEIGHTS = {"relevance": 0.30, "clarity": 0.25, "delivery": 0.20, "novelty": 0.15, "fit": 0.10}
KEYS = {"relevance": "R", "clarity": "C", "delivery": "D", "novelty": "N", "fit": "F"}
HOOK_TYPES = ("curiosity", "problem", "direct")


def _n(t):
    return re.sub(r"[^\w؀-ۿ ]", "", str(t)).lower().split()


def weights(rules):
    w = dict(DEFAULT_WEIGHTS)
    w.update({k: float(v) for k, v in ((rules or {}).get("story_score", {}).get("weights", {}) or {}).items() if k in w})
    tot = sum(w.values()) or 1.0
    return {k: v / tot for k, v in w.items()}                 # always adds up to 1, even if the file is edited carelessly


def _num(x):
    try:
        return min(10.0, max(1.0, float(x)))
    except (TypeError, ValueError):
        return None


def range_delivery(si, a, b):
    """1-10 measured delivery for a time range from speech_intel.json (fewer fillers/repeats/long pauses, more emphasis = better)."""
    if not si:
        return None
    d = si.get("delivery", {})
    inr = lambda t: a <= t <= b
    n = max(1.0, (b - a) / 10.0)                                # per 10 seconds
    bad = (sum(inr(x["t"]) for x in d.get("fillers", [])) + sum(inr(x["t"]) for x in d.get("repeats", []))
           + 2 * sum(inr(x["t"]) for x in d.get("pauses", []) if x.get("long")) + 2 * sum(inr(x["t"]) for x in d.get("unfinished_sentences", []))) / n
    good = sum(inr(x["t"]) for x in d.get("emphasis_words", [])) / n
    return round(min(10.0, max(1.0, 7.0 - bad * 1.2 + min(good, 3) * 0.8)), 1)


def score_select(sel, w, si=None):
    """Adds sel['parts'] (R,C,D,N,F), sel['ai_score'] and sel['score'] (the formula). Falls back to the AI's own score if it gave no parts."""
    sc = sel.get("scores") or {}
    parts = {k: _num(sc.get(k)) for k in w}
    if all(v is None for v in parts.values()):
        sel["ai_score"] = sel.get("score"); sel["parts"] = {}
        return sel
    fill = next((v for v in parts.values() if v is not None), 5.0)
    parts = {k: (v if v is not None else fill) for k, v in parts.items()}
    meas = range_delivery(si, *sel["range"]) if si and sel.get("range") else None
    if meas is not None:
        parts["delivery"] = round((parts["delivery"] + meas) / 2, 1)
        sel["delivery_measured"] = meas
    sel["parts"] = {KEYS[k]: round(v, 1) for k, v in parts.items()}
    sel["ai_score"] = sel.get("score")
    sel["score"] = round(sum(w[k] * parts[k] for k in w), 2)
    return sel


def check_hook(line, words, near=None):
    """Is this hook really in the transcript? -> {found, t, index}. Looks for the words in order, allowing a missing word or two."""
    toks = _n(line)
    if not toks:
        return {"found": False}
    texts = [" ".join(_n(w["text"])) for w in words]
    for i in range(len(words)):
        j, k = i, 0
        while j < len(words) and k < len(toks) and j - i <= len(toks) + 2:
            if texts[j] == toks[k]:
                k += 1
            j += 1
        if k >= max(1, int(len(toks) * 0.8)) and texts[i] == toks[0]:
            return {"found": True, "t": round(words[i]["start"], 2), "index": i}
    return {"found": False}


def check_hooks(sel, words):
    out = []
    for h in sel.get("hooks") or []:
        if not isinstance(h, dict) or not h.get("line"):
            continue
        r = check_hook(h["line"], words)
        a, b = sel.get("range", [0, 1e9])
        r["inside_range"] = bool(r.get("found") and a - 0.5 <= r["t"] <= b)
        out.append({"type": h.get("type"), "line": h["line"], **r})
    return out


def range_flags(sel, words, lmin, lmax):
    """Plain-words confidence flags for a story range."""
    a, b = sel["range"]
    flags = []
    if b - a < lmin - 3 or b - a > lmax + 3:
        flags.append(f"length {b - a:.0f}s is outside the {lmin}-{lmax}s target")
    for i, w in enumerate(words):
        if w["start"] < a < w["end"] - 0.05:
            flags.append(f"starts inside a word at {a:.1f}s"); break
    for i, w in enumerate(words):
        if w["start"] + 0.05 < b < w["end"]:
            flags.append(f"ends inside a word at {b:.1f}s"); break
    inside = [w for w in words if a <= w["start"] and w["end"] <= b]
    if inside and inside[0]["start"] - a > 1.5:
        flags.append("a long silence before the first word")
    return flags


def continuity(edl, words_src=None):
    """Checks on the cuts the EDL made: [] means nothing suspicious."""
    seg = edl.get("segments", [])
    w = edl.get("words", [])
    flags = []
    for p, q in zip(seg, seg[1:]):
        gap = q["src_in"] - p["src_out"]
        if gap < 0.12:
            flags.append(f"very tight cut at {q['t_in']:.1f}s (only {gap:.2f}s of source removed): may feel like a jump")
        # cut lands in the middle of a spoken flow: both neighbouring words are close in time in the SOURCE
        before = [x for x in w if x["end"] <= q["t_in"] + 0.02]
        after = [x for x in w if x["start"] >= q["t_in"] - 0.02]
        if before and after and gap < 0.25 and before[-1].get("src_i") is not None and after[0].get("src_i") is not None \
                and after[0]["src_i"] - before[-1]["src_i"] == 1:
            flags.append(f"cut at {q['t_in']:.1f}s falls between two words spoken back to back")
    if w and edl.get("duration") and w[0]["start"] > 0.6:
        flags.append(f"the reel starts with {w[0]['start']:.1f}s before the first word")
    return flags


def build(job, rules=None, lmin=40, lmax=90):
    """Write jobs/<job>/editorial.json from selects.json, chosen_select.json, edl.json, timeline.json, speech_intel.json."""
    j = lambda n, d=None: _jl(os.path.join(job, n), d)
    sel, chosen, edl = j("selects.json", {}) or {}, j("chosen_select.json"), j("edl.json")
    if not chosen or not edl:
        return None
    tl = j("timeline.json", {}) or {}
    si = j("speech_intel.json")
    words = j("transcript.json", []) or []
    alts = [{"id": s.get("id"), "range": s.get("range"), "label": s.get("label"), "score": s.get("score"), "parts": s.get("parts"),
             "style": s.get("style"), "why": s.get("why"), "chosen": s.get("id") == chosen.get("id")} for s in sel.get("selects", [])]
    hooks = check_hooks(chosen, words) if words else []
    flags = []
    if chosen.get("range") and words:
        flags += range_flags(chosen, words, lmin, lmax)
    flags += continuity(edl)
    flags += [f"hook '{h['line'][:40]}' is not word for word in the transcript" for h in hooks if not h["found"]]
    hook_card = next((s for s in tl.get("scenes", []) if s.get("block") == "hook_two_tone"), None)
    out = {
        "version": 1,
        "main_message": sel.get("main_message"), "audience": sel.get("audience"),
        "chosen": {k: chosen.get(k) for k in ("id", "range", "label", "why", "score", "parts", "style", "picked_by")},
        "alternative_stories": alts,
        "hooks": hooks,
        "hook_on_screen": (hook_card or {}).get("values"),
        "timeline_instructions": {"source_ranges": [{"src_in": s["src_in"], "src_out": s["src_out"], "t_in": s["t_in"], "t_out": s["t_out"]}
                                                    for s in edl.get("segments", [])],
                                  "removed": {k: (len(v) if isinstance(v, list) else v) for k, v in (edl.get("removed") or {}).items()},
                                  "note": "These are instructions, not a new video: change them and rebuild; originals are never touched."},
        "rationale": chosen.get("why"),
        "confidence_flags": flags,
        "weights": weights(rules),
    }
    tmp = os.path.join(job, "editorial.json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    os.replace(tmp, os.path.join(job, "editorial.json"))
    return out


def _jl(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def summary_lines(ed):
    c = ed["chosen"]
    L = [f"message: {ed.get('main_message') or '(not stated)'} | audience: {ed.get('audience') or '(not stated)'}",
         f"story {c.get('id')} {c.get('range')} score {c.get('score')}" + (f" (R/C/D/N/F {c['parts']})" if c.get("parts") else "")]
    L += [f"hook ({h['type']}): {h['line']}" + ("" if h["found"] else "  <- not word for word") for h in ed["hooks"]]
    L += [f"check: {f}" for f in ed["confidence_flags"][:6]]
    return L
