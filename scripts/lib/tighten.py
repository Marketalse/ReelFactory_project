"""AI tightening of the cut (T124). The AI decides WHAT to cut; code checks every decision.

The old cut only removed pauses, filler sounds and exact retakes by rule. This adds a real editing judgement: after the story range is
chosen, an AI editor reads it line by line (a line = one stretch of speech between pauses) and removes the lines that weaken it: false
starts, the same point said twice (the better take stays), side stories, a long intro before the point, a weak ending. It may also move
the start or end of the range. Code then enforces the rules the AI cannot be trusted with:
  - only WHOLE lines are removed (never half a sentence), the AI cannot invent, reorder or reword anything;
  - the first line of the reel (the hook) is never removed;
  - at most MAX_SHARE of the speech may go, and the reel must not fall below the target length;
  - every cut is saved with its reason in tighten.json; the Edit page shows each one so he can restore it.
"""
import json, os, re

MAX_SHARE = 0.45
MIN_LINE_S = 0.4

PROMPT = """You are the film editor of Hesham's reels (Iraqi Arabic, business and marketing, Instagram/TikTok). A story range has been chosen. Make it TIGHTER and STRONGER by removing whole lines that weaken it.
MAIN MESSAGE: {main}   AUDIENCE: {aud}   STYLE: {style}
TARGET: the finished reel should be {lmin}-{lmax} seconds. The range is {length:.0f} s now; pauses and fillers are cut automatically afterwards (about 15% shorter).

How to edit:
- Keep the hook (the first strong line) and ONE clear flow: problem, explanation, result. Keep the strongest example.
- REMOVE: false starts and restarts, a point said twice (keep the better take), side stories that do not support the main message, a long intro before the point, filler explanations, weak or unfinished lines, a weak ending after the natural close.
- You may move the start and the end of the range (start/end = line numbers) to skip a slow intro or a weak outro.
- Only whole lines, never half a sentence. Never reorder, reword or invent. If it is already tight, remove nothing.
- Marks in braces are measured facts: pause = silence after the line, emphasis = louder words, false start = filler or repeated words, unsure = words the transcript may have wrong.
Return ONLY JSON: {{"start":<first line to keep>,"end":<last line to keep>,"drops":[{{"id":<line>,"why":"<=12 words English"}}],"summary":"<=25 words English"}}

LINES (number [from-to s] text):
{lines}"""


def units(ci, s0, s1):
    """The lines inside the range: [{id, i0, i1, t0, t1, text, marks}]. id = position in the content-intel phrase list."""
    from lib import content_intel
    out = []
    for n, p in enumerate(ci["phrases"]):
        if p["t0"] >= s0 - 0.25 and p["t1"] <= s1 + 0.25:
            out.append(dict(id=n, i0=p["i0"], i1=p["i1"], t0=p["t0"], t1=p["t1"], text=p["text"], marks=content_intel.marks(p)))
    return out


def build_prompt(us, main, aud, style, lmin, lmax):
    lines = "\n".join(f"{u['id']} [{u['t0']:.1f}-{u['t1']:.1f}] {u['text']}{u['marks']}" for u in us)
    return PROMPT.format(main=main or "(not stated)", aud=aud or "(not stated)", style=style or "(not stated)", lmin=lmin, lmax=lmax,
                         length=(us[-1]["t1"] - us[0]["t0"]) if us else 0, lines=lines)


def decide(answer, us, lmin):
    """Check the AI's answer. -> {"start_id","end_id","drops":[{id,why}], "removed_s","kept_s","notes":[...]} (always safe to apply)."""
    notes = []
    ids = {u["id"]: u for u in us}
    first, last = us[0]["id"], us[-1]["id"]
    ans = answer if isinstance(answer, dict) else {}

    def pick(v, default):
        return v if isinstance(v, int) and v in ids else default
    start, end = pick(ans.get("start"), first), pick(ans.get("end"), last)
    if start > end:
        start, end = first, last; notes.append("the AI's start/end were upside down: ignored")
    inside = [u for u in us if start <= u["id"] <= end]
    speech = sum(u["t1"] - u["t0"] for u in inside)
    floor = lmin * 0.8                              # after pauses are cut a reel is shorter than its range: never go below this
    drops, removed = [], 0.0
    for d in ans.get("drops", []) if isinstance(ans.get("drops"), list) else []:
        i = d.get("id") if isinstance(d, dict) else None
        if i not in ids or not (start <= i <= end) or i == start or any(x["id"] == i for x in drops):
            continue                                            # unknown line, outside the range, the hook, or repeated
        dur = ids[i]["t1"] - ids[i]["t0"]
        if dur < MIN_LINE_S:
            continue
        if removed + dur > MAX_SHARE * speech:
            notes.append("stopped cutting: the AI wanted to remove more than 45% of the speech"); break
        if speech - removed - dur < floor:
            notes.append("stopped cutting: the reel would get too short"); break
        removed += dur
        drops.append({"id": i, "why": re.sub(r"\s+", " ", str(d.get("why") or "")).strip()[:100]})
    return {"start_id": start, "end_id": end, "drops": drops, "removed_s": round(removed, 1), "kept_s": round(speech - removed, 1),
            "summary": re.sub(r"\s+", " ", str(ans.get("summary") or "")).strip()[:200], "notes": notes}


def apply(us, decision):
    """-> (new range [s, e], drops with word numbers). The range moves to the kept lines; drops are whole lines."""
    ids = {u["id"]: u for u in us}
    s, e = ids[decision["start_id"]]["t0"], ids[decision["end_id"]]["t1"]
    rows = []
    for d in decision["drops"]:
        u = ids[d["id"]]
        rows.append({"line": u["id"], "i0": u["i0"], "i1": u["i1"], "t0": u["t0"], "t1": u["t1"], "text": u["text"], "why": d["why"]})
    return [round(s, 2), round(e, 2)], rows


def drop_words(path):
    """Source word numbers cut by the AI for this reel (from tighten.json), for edl.build(drop=...)."""
    try:
        with open(path, encoding="utf-8") as f:
            t = json.load(f)
    except (OSError, ValueError):
        return []
    return sorted({i for r in t.get("drops", []) for i in range(r["i0"], r["i1"] + 1)})


def cut_reasons(path):
    """{source word number: reason} for the Edit page."""
    try:
        with open(path, encoding="utf-8") as f:
            t = json.load(f)
    except (OSError, ValueError):
        return {}
    return {i: r.get("why") or "weak or repeated" for r in t.get("drops", []) for i in range(r["i0"], r["i1"] + 1)}
