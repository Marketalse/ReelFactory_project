"""Unified content intelligence (T102): ONE file that joins everything known about the footage, phrase by phrase. Free, local.

jobs/<job>/content_intel.json holds, for every phrase (words split on pauses over 0.35 s, the same rule the story step reads):
the words and times, the pause after it, speaking speed, how loud it is, emphasis words, fillers/repeats, words to double-check,
scene changes inside it (media index) and where the face is (shot log, when it exists). The story step reads short marks from it
({pause 1.4s}, {emphasis: word}, {fast}, {unsure: word}, {scene change}) so it chooses with the same facts a human editor would see.
Built from files that already exist; missing ones are simply left out. It never changes any of them.
"""
import json, os

PAUSE_MARK = 0.9          # seconds: a pause worth telling the story step about
FAST_WPM = 230
SLOW_WPM = 80


def _jl(p, d=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return d


def phrases(words, gap=0.35):
    out, cur = [], []
    for i, w in enumerate(words):
        if cur and w["start"] - words[cur[-1]]["end"] > gap:
            out.append(cur); cur = []
        cur.append(i)
    if cur:
        out.append(cur)
    return out


def build(job):
    """Write jobs/<job>/content_intel.json. -> dict, or None when there is no transcript yet."""
    words = _jl(os.path.join(job, "transcript.json"))
    if not words:
        return None
    si = _jl(os.path.join(job, "speech_intel.json"), {}) or {}
    idx = _jl(os.path.join(job, "media_index.json"), {}) or {}
    shots = _jl(os.path.join(job, "shot_log.json"), []) or []
    wl = si.get("word_levels_db") or []
    conf = si.get("word_confidence") or []
    d = si.get("delivery", {}) or {}
    emph = {e["i"] for e in d.get("emphasis_words", [])}
    fill = {e["i"] for e in d.get("fillers", [])}
    rep = {e["i"] for e in d.get("repeats", [])}
    cuts = []                                            # scene changes on the joined timeline (proxy time)
    for c in idx.get("clips", []):
        for sc in c.get("scenes", [])[1:]:
            cuts.append(round(c["start"] + sc["start"], 2))
    faces = sorted((r["t"], r["face"]) for r in shots if r.get("face") and "t" in r)
    ph = []
    for g in phrases(words):
        a, b = words[g[0]]["start"], words[g[-1]]["end"]
        nxt = words[g[-1] + 1]["start"] - b if g[-1] + 1 < len(words) else None
        wpm = len(g) / max((b - a) / 60.0, 1e-3) if len(g) >= 3 else None
        face = min(faces, key=lambda f: abs(f[0] - (a + b) / 2))[1] if faces else None
        ph.append({
            "i0": g[0], "i1": g[-1], "t0": round(a, 2), "t1": round(b, 2), "text": " ".join(words[i]["text"] for i in g),
            "pause_after_s": round(nxt, 2) if nxt is not None else None,
            "words_per_min": round(wpm) if wpm else None,
            "level_db": round(sum(wl[i] for i in g) / len(g), 1) if wl and len(wl) > g[-1] else None,
            "emphasis": [words[i]["text"] for i in g if i in emph], "fillers": sum(i in fill for i in g), "repeats": sum(i in rep for i in g),
            "unsure": [words[i]["text"] for i in g if len(conf) > i and conf[i] < 0.6],
            "scene_changes": [c for c in cuts if a <= c <= b], "face": face})
    out = {"version": 1, "words": len(words), "duration": round(words[-1]["end"], 2), "phrases": ph,
           "scores": si.get("scores") and {k: v.get("value") for k, v in si["scores"].items()},
           "language": (si.get("language") or {}).get("main"), "key_terms": si.get("key_terms", []),
           "sources": {"speech_intel": bool(si), "media_index": bool(idx), "shot_log": bool(shots)}}
    tmp = os.path.join(job, "content_intel.json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    os.replace(tmp, os.path.join(job, "content_intel.json"))
    return out


def marks(p):
    """Short marks for one phrase, or ''."""
    m = []
    if p["pause_after_s"] is not None and p["pause_after_s"] >= PAUSE_MARK:
        m.append(f"pause {p['pause_after_s']:.1f}s")
    if p["emphasis"]:
        m.append("emphasis: " + ", ".join(p["emphasis"][:3]))
    if p["words_per_min"] and p["words_per_min"] >= FAST_WPM:
        m.append("fast")
    elif p["words_per_min"] and p["words_per_min"] <= SLOW_WPM:
        m.append("slow")
    if p["fillers"] or p["repeats"]:
        m.append("false start")
    if p["unsure"]:
        m.append("unsure: " + ", ".join(p["unsure"][:2]))
    if p["scene_changes"]:
        m.append("scene change")
    return " {" + "; ".join(m) + "}" if m else ""


LEGEND = ("Marks in braces are measured facts about that line: pause = silence after it; emphasis = louder words; fast/slow = speaking speed; "
          "false start = filler or repeated words; unsure = words the transcript may have wrong; scene change = the picture changes. "
          "Prefer ranges that start after a pause on a clean, confident line and end on a pause; avoid starting on a false start.")


def marked_lines(ci):
    """The story step's transcript lines with the marks added. Same line rule as before (split on pauses over 0.35 s)."""
    return "\n".join(f"[{p['t0']:.1f}-{p['t1']:.1f}] {p['text']}{marks(p)}" for p in ci["phrases"])
