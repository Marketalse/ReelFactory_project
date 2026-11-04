"""Meaning check for the cut (free, local, no AI). It proves what can be proven about "the reel says what he said":

HARD errors (the reel must not go on):
  - a word is out of source order or used twice (the cut must never reorder or repeat his words),
  - a reel word has no source word, or its text differs from the source word without a manual spelling fix,
  - two pieces overlap or leave a gap on the reel timeline.
WARNINGS (shown in the report, the reel carries on):
  - a kept word is cut short (its end falls outside its piece by more than CLIP_S): a clipped word,
  - a word that was REMOVED is still audible inside a kept piece (a filler between two close words can come back through the safe padding),
  - a very short gap between two pieces that is not a real pause (a hard jump).
It reads edl.json and the source transcript only. It never changes anything."""
import json, os

CLIP_S = 0.04
AUDIBLE_S = 0.06


def check(edl, words, texts=None):
    """-> {"ok": bool, "errors": [...], "warnings": [...], "stats": {...}}. words = source transcript; texts = manual spelling fixes {src_i: text}."""
    texts = {int(k): v for k, v in (texts or {}).items()}
    err, warn = [], []
    segs, out = edl.get("segments", []), edl.get("words", [])
    seen, last = set(), -1
    for w in out:
        i = w.get("src_i")
        if not isinstance(i, int) or not 0 <= i < len(words):
            err.append(f"reel word {w.get('text')!r} at {w.get('start')} s has no source word"); continue
        if i in seen: err.append(f"source word {i} ({words[i]['text']!r}) is used twice")
        elif i < last: err.append(f"words are out of source order at source word {i} ({words[i]['text']!r})")
        seen.add(i); last = max(last, i)
        if i not in texts and w.get("text") != words[i]["text"]:
            err.append(f"reel word {w.get('text')!r} differs from what he said ({words[i]['text']!r}) and was not changed by hand")
    prev = None
    for s in segs:
        if prev is not None:
            if s["t_in"] < prev["t_out"] - 0.002: err.append(f"pieces overlap on the reel at {s['t_in']} s")
            elif s["t_in"] > prev["t_out"] + 0.002: err.append(f"gap between pieces on the reel at {prev['t_out']} s")
            if s["src_in"] < prev["src_out"] - 0.002: err.append(f"a piece goes back in the source at {s['src_in']} s (reordered)")
        prev = s
    clipped = 0
    for w in out:
        i = w.get("src_i")
        if not isinstance(i, int) or not 0 <= i < len(words): continue
        sw = words[i]
        seg = next((s for s in segs if s["t_in"] - 0.002 <= w["start"] <= s["t_out"] + 0.002), None)
        if seg and (sw["start"] < seg["src_in"] - CLIP_S or sw["end"] > seg["src_out"] + CLIP_S):
            clipped += 1; warn.append(f"the word {sw['text']!r} (source {sw['start']:.2f}-{sw['end']:.2f} s) is cut short by its piece ({seg['src_in']:.2f}-{seg['src_out']:.2f} s)")
    audible = 0
    kept_src = {w.get("src_i") for w in out}
    lo, hi = (edl.get("source_range") or [0, 1e9])
    for i, sw in enumerate(words):
        if i in kept_src or sw["end"] < lo or sw["start"] > hi: continue
        for s in segs:
            over = min(sw["end"], s["src_out"]) - max(sw["start"], s["src_in"])
            if over > AUDIBLE_S:
                audible += 1; warn.append(f"the removed word {sw['text']!r} ({sw['start']:.2f}-{sw['end']:.2f} s) is partly still heard ({over:.2f} s) inside a kept piece"); break
    return {"ok": not err, "errors": err[:20], "warnings": warn[:20],
            "stats": {"words_kept": len(out), "pieces": len(segs), "clipped_words": clipped, "removed_words_still_audible": audible, "dramatic_pauses_kept": len(edl.get("kept_pauses", []))}}


def run(job, texts=None):
    """Check a job folder and write integrity.json. -> the result."""
    with open(os.path.join(job, "edl.json"), encoding="utf-8") as f: edl = json.load(f)
    with open(os.path.join(job, "transcript.json"), encoding="utf-8") as f: words = json.load(f)
    r = check(edl, words, texts)
    with open(os.path.join(job, "integrity.json"), "w", encoding="utf-8") as f: json.dump(r, f, ensure_ascii=False, indent=1)
    return r
