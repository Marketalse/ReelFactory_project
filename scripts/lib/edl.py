"""Edit decision list: turn the chosen source range into the cut that the reel actually uses.

Removes pauses longer than rules.cut.remove_pauses_over_s, filler sounds, and retakes (a phrase said twice:
the last take wins). Words are re-timed onto the reel timeline. No AI, no spend.

DRAMATIC PAUSES (rules.cut.dramatic_pause): a long pause right after a spoken number, or right before a word he said louder than usual, is not
dead air: it lets the point land. Such a pause is shortened to dramatic_pause.keep_s instead of being removed (at most max_per_10s of them, so
the reel never drags). Every other pause over the limit is still removed.

CUT LOG: every removal (filler, retake, pause, the AI editor's cut, a manual cut) is written to edl["cut_log"] with the words, the source time,
the reel time where it happens and a plain reason; kept pauses are in edl["kept_pauses"]. Nothing here decides meaning: it only records.
"""
import re
from . import config as cfg
from .transcript import FILLERS

PAD = 0.08          # keep a little air around speech so cuts don't clip syllables
MIN_SEG = 0.3       # shorter kept pieces are merged into their neighbour


NUMBER_WORDS = {"ألف", "الف", "آلاف", "الاف", "مليون", "ملايين", "مئة", "مية", "ميه", "مائة"}      # whole words only ("الفكرة" is not a number)


def _is_number(t):
    t = (t or "").strip(".,!?؟،:;\"'()")
    return bool(re.search(r"[0-9٠-٩]", t)) or t in NUMBER_WORDS


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


def _runs(idx_set):
    """Consecutive numbers -> [(first, last)]."""
    out = []
    for i in sorted(idx_set):
        if out and i == out[-1][1] + 1: out[-1][1] = i
        else: out.append([i, i])
    return out


def build(words, s0, s1, *, pause=None, drop_fillers=True, retakes=True, drop=(), keep=(), texts=None, ai_drop=(), reasons=None, emphasis=None):
    """words: full transcript (source time). Returns dict(segments=[{src_in,src_out,t_in,t_out}],
    words=[reel-time words with 'src_i'], removed={...}, duration).
    Manual edits from the dashboard editor (source word numbers): drop = cut these words, keep = bring these back even
    if they were removed automatically (filler / retake), texts = {src_i: new spelling}.
    ai_drop = words the AI editor cut (kept apart from `drop` only so the cut log can say who cut them); reasons = {src_i: why} for those;
    emphasis = source word numbers he said louder than usual (from speech_intel), used for dramatic pauses."""
    pause = cfg.RULES["cut"]["remove_pauses_over_s"] if pause is None else pause
    ai_drop = set(ai_drop)
    drop, keep, texts = set(drop) | ai_drop, set(keep), {int(k): v for k, v in (texts or {}).items()}
    reasons = {int(k): v for k, v in (reasons or {}).items()}
    dp = dict(cfg.RULES["cut"].get("dramatic_pause") or {})
    emphasis = set(emphasis or ())
    why_removed = {}                                                  # source word number -> (kind, reason)
    idx = [i for i, w in enumerate(words) if w["start"] >= s0 - 0.05 and w["end"] <= s1 + 0.05]
    removed = {"fillers": [], "retakes": [], "pauses": 0, "manual": []}
    if drop_fillers:
        kept = [i for i in idx if _norm(words[i]["text"]) not in FILLERS or i in keep]
        removed["fillers"] = [words[i]["text"] for i in idx if i not in kept]
        for i in idx:
            if i not in kept: why_removed[i] = ("filler", "a filler sound (hesitation), not part of what he means")
        idx = kept
    if retakes:
        local = [words[i] for i in idx]
        d = {k for k in find_retakes(local) if idx[k] not in keep}
        removed["retakes"] = [local[k]["text"] for k in sorted(d)]
        for k in d: why_removed[idx[k]] = ("retake", "the same words were said again a moment later: the last take stays")
        idx = [i for k, i in enumerate(idx) if k not in d]
    if drop:
        removed["manual"] = [words[i]["text"] for i in idx if i in drop]
        for i in idx:
            if i in drop:
                why_removed[i] = ("ai", reasons.get(i) or "cut by the AI editor") if i in ai_drop else ("manual", "cut by you on the Edit page")
        idx = [i for i in idx if i not in drop]
    if not idx:
        raise ValueError("no words left in the chosen range")

    # spans of speech in source time, split where the pause is long or words were removed in between
    spans, pause_cuts, kept_pauses = [], [], []
    dp_budget = max(1, int(((s1 - s0) / 10.0) * float(dp.get("max_per_10s", 1)) + 0.5)) if dp.get("enabled") else 0
    for k, i in enumerate(idx):
        a, b = max(s0, words[i]["start"] - PAD), min(s1, words[i]["end"] + PAD)
        if spans:
            prev_i = idx[k - 1]
            gap = words[i]["start"] - words[prev_i]["end"]
            if gap <= pause and i == prev_i + 1:
                spans[-1][1] = b; spans[-1][2].append(i); continue
            if gap > pause:
                removed["pauses"] += 1
                why = None
                if i == prev_i + 1 and len(kept_pauses) < dp_budget and gap >= float(dp.get("min_gap_s", 0.6)):
                    if _is_number(words[prev_i]["text"]): why = "a pause after a number lets it land"
                    elif i in emphasis: why = "a pause before a word he said louder: it builds the point"
                if why:                                                 # dramatic: keep keep_s of silence (never more than there was) instead of cutting it all
                    keep_s = min(gap, float(dp.get("keep_s", 0.5)))
                    extra = max(0.0, (keep_s - 2 * PAD) / 2)
                    spans[-1][1] = min(s1, spans[-1][1] + extra); a = max(s0, words[i]["start"] - PAD - extra)
                    kept_pauses.append({"src_i": i, "src_from": round(words[prev_i]["end"], 3), "src_to": round(words[i]["start"], 3), "pause_s": round(gap, 2),
                                        "kept_s": round(keep_s, 2), "why": why})
                else:
                    pause_cuts.append({"src_i": i, "src_from": round(words[prev_i]["end"], 3), "src_to": round(words[i]["start"], 3), "pause_s": round(gap, 2)})
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
    def reel_time_before(src_i):
        """Where on the reel a cut before source word src_i falls (the start of the first kept word after it)."""
        nxt = next((w for w in out_words if w["src_i"] > src_i), None)
        return round(nxt["start"], 2) if nxt else round(t, 2)

    cut_log = []
    for kind_runs in _runs(why_removed):
        a_i, b_i = kind_runs
        for kind in dict.fromkeys(why_removed[i][0] for i in range(a_i, b_i + 1) if i in why_removed):            # one entry per kind inside a run
            ids = [i for i in range(a_i, b_i + 1) if i in why_removed and why_removed[i][0] == kind]
            why = next((why_removed[i][1] for i in ids if why_removed[i][1]), "")
            cut_log.append({"kind": kind, "words": [words[i]["text"] for i in ids], "src_i": [ids[0], ids[-1]], "src_from": round(words[ids[0]]["start"], 3),
                            "src_to": round(words[ids[-1]]["end"], 3), "reel_t": reel_time_before(ids[-1]), "why": why})
    for pc in pause_cuts:
        cut_log.append({"kind": "pause", "words": [], "src_i": [pc["src_i"], pc["src_i"]], "src_from": pc["src_from"], "src_to": pc["src_to"],
                        "reel_t": reel_time_before(pc["src_i"] - 1), "why": f"a pause of {pc['pause_s']} s, over the {pause} s limit"})
    cut_log.sort(key=lambda e: e["src_from"])
    return {"segments": segments, "words": out_words, "removed": removed, "duration": round(t, 3),
            "source_range": [s0, s1], "source_seconds": round(s1 - s0, 3), "cut_log": cut_log, "kept_pauses": kept_pauses}
