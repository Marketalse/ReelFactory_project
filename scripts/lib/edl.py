"""Edit decision list: turn the chosen source range into the cut that the reel actually uses.

Removes pauses longer than rules.cut.remove_pauses_over_s, filler sounds, and retakes (a phrase said twice:
the last take wins). Words are re-timed onto the reel timeline. No AI, no spend.
"""
from . import config as cfg
from .transcript import FILLERS

PAD = 0.08          # keep a little air around speech so cuts don't clip syllables
MIN_SEG = 0.3       # shorter kept pieces are merged into their neighbour


def _norm(t):
    return t.strip(".,!?؟،:;\"'()").lower()


def find_retakes(words, n=3, window=6.0, max_drop=6.0):
    """A false start is restarted quickly: the same 3 words again within 6 s. Deliberate repetition usually comes later."""
    # indices to drop: from the first attempt up to the restart (last take wins)
    drop = set()
    toks = [_norm(w["text"]) for w in words]
    i = 0
    while i + n <= len(toks):
        gram = toks[i:i + n]
        hit = None
        for j in range(i + n, len(toks) - n + 1):
            if words[j]["start"] - words[i]["start"] > window:
                break
            if toks[j:j + n] == gram:
                hit = j
                break
        if hit is not None and words[hit]["start"] - words[i]["start"] <= max_drop:
            drop.update(range(i, hit))
            i = hit
        else:
            i += 1
    return drop


def build(words, s0, s1, *, pause=None, drop_fillers=True, retakes=True, drop=(), keep=(), texts=None):
    """words: full transcript (source time). Returns dict(segments=[{src_in,src_out,t_in,t_out}],
    words=[reel-time words with 'src_i'], removed={...}, duration).
    Manual edits from the dashboard editor (source word numbers): drop = cut these words, keep = bring these back even
    if they were removed automatically (filler / retake), texts = {src_i: new spelling}."""
    pause = cfg.RULES["cut"]["remove_pauses_over_s"] if pause is None else pause
    drop, keep, texts = set(drop), set(keep), {int(k): v for k, v in (texts or {}).items()}
    idx = [i for i, w in enumerate(words) if w["start"] >= s0 - 0.05 and w["end"] <= s1 + 0.05]
    removed = {"fillers": [], "retakes": [], "pauses": 0, "manual": []}
    if drop_fillers:
        kept = [i for i in idx if _norm(words[i]["text"]) not in FILLERS or i in keep]
        removed["fillers"] = [words[i]["text"] for i in idx if i not in kept]
        idx = kept
    if retakes:
        local = [words[i] for i in idx]
        d = {k for k in find_retakes(local) if idx[k] not in keep}
        removed["retakes"] = [local[k]["text"] for k in sorted(d)]
        idx = [i for k, i in enumerate(idx) if k not in d]
    if drop:
        removed["manual"] = [words[i]["text"] for i in idx if i in drop]
        idx = [i for i in idx if i not in drop]
    if not idx:
        raise ValueError("no words left in the chosen range")

    # spans of speech in source time, split where the pause is long or words were removed in between
    spans = []
    for k, i in enumerate(idx):
        a, b = max(s0, words[i]["start"] - PAD), min(s1, words[i]["end"] + PAD)
        if spans:
            prev_i = idx[k - 1]
            gap = words[i]["start"] - words[prev_i]["end"]
            if gap <= pause and i == prev_i + 1:
                spans[-1][1] = b; spans[-1][2].append(i); continue
            if gap > pause:
                removed["pauses"] += 1
        spans.append([a, b, [i]])
    # a piece shorter than MIN_SEG is widened into the silence around it (never into other words);
    # pieces that then touch or overlap are joined. Long pauses are never brought back.
    for k, sp in enumerate(spans):
        need = MIN_SEG - (sp[1] - sp[0])
        if need <= 0:
            continue
        after = (spans[k + 1][0] if k + 1 < len(spans) else s1) - sp[1]
        grow = min(need, max(0.0, after)); sp[1] += grow; need -= grow
        before = sp[0] - (spans[k - 1][1] if k else s0)
        grow = min(need, max(0.0, before)); sp[0] -= grow
    merged = []
    for sp in spans:
        if merged and sp[0] <= merged[-1][1] + 1e-6:
            merged[-1][1] = max(merged[-1][1], sp[1]); merged[-1][2] += sp[2]
        else:
            merged.append(sp)
    # still too short (no silence around it at all): join the nearest neighbour
    k = 0
    while k < len(merged) and len(merged) > 1:
        a, b, ws = merged[k]
        if b - a >= MIN_SEG - 1e-6:
            k += 1; continue
        if k + 1 < len(merged):
            nxt = merged.pop(k + 1); merged[k] = [a, nxt[1], ws + nxt[2]]
        else:
            prv = merged.pop(k - 1); merged[k - 1] = [prv[0], b, prv[2] + ws]; k -= 1

    segments, out_words, t = [], [], 0.0
    for a, b, ws in merged:
        segments.append({"src_in": round(a, 3), "src_out": round(b, 3), "t_in": round(t, 3), "t_out": round(t + b - a, 3)})
        for i in ws:
            w = words[i]
            out_words.append({"text": texts.get(i, w["text"]), "start": round(t + w["start"] - a, 3), "end": round(t + min(w["end"], b) - a, 3), "src_i": i})
        t += b - a
    return {"segments": segments, "words": out_words, "removed": removed, "duration": round(t, 3),
            "source_range": [s0, s1], "source_seconds": round(s1 - s0, 3)}
