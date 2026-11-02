"""Stage 3 speech intelligence. Free, local, no AI, no internet: stdlib only.

Reads what Stage 2 and the transcript steps already made and writes jobs/<job>/speech_intel.json:
  - which languages are in the speech (Arabic / English / Kurdish letters) and which glossary words appear,
  - fillers, repeated words, pauses, speaking speed, sentences that seem unfinished,
  - how loud each word was (emphasis) from the real audio,
  - SEPARATE scores, each with its own meaning (never one mystery number): transcription confidence, timestamp reliability,
    audio quality, delivery energy. They are rough guides for decisions, not proof that a word is right or wrong.

The RAW transcript (transcript_asr.json) is never touched. Corrections are listed next to it, not instead of it.
Not done here (needs a model): who is speaking (speaker labels) and what is important in meaning (the story step does that).
"""
import array, json, math, os, re, wave

from lib import transcript as tr

ARABIC = re.compile(r"[؀-ۿ]")
LATIN = re.compile(r"[A-Za-z]")
KURDISH = re.compile(r"[ڕڵێۆەڤ]")           # letters Sorani uses that Iraqi Arabic does not
CONNECTORS = {"و", "بس", "لان", "لأن", "اللي", "ان", "أن", "لما", "اذا", "إذا", "او", "أو", "مثل", "يعني", "بين", "على", "من", "في", "لكن"}
HEDGES = {"يعني", "شوف", "هسه", "اكو"}
STOP = CONNECTORS | HEDGES | {"هذا", "هذي", "هاي", "ذاك", "انت", "انا", "هو", "هي", "شي", "كل", "ما", "لا", "هل", "كان", "اللى", "الى", "إلى", "عن"}
FRAME = 0.05


def _norm(t):
    return re.sub(r"[^\w؀-ۿ]", "", str(t)).lower()


def _jload(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p * (len(xs) - 1)))] if xs else 0.0


def _db(rms):
    return 20 * math.log10(rms / 32768.0) if rms > 0 else -90.0


# ----------------------------------------------------------------------------- step 1: language and vocabulary
def languages(words, configured="ar"):
    counts = {"arabic": 0, "english": 0, "kurdish": 0, "other": 0}
    for w in words:
        t = str(w.get("text", ""))
        if KURDISH.search(t):
            counts["kurdish"] += 1
        elif ARABIC.search(t):
            counts["arabic"] += 1
        elif LATIN.search(t):
            counts["english"] += 1
        else:
            counts["other"] += 1
    n = max(1, sum(counts.values()) - counts["other"])
    share = {k: round(v / n, 3) for k, v in counts.items() if k != "other"}
    if share["kurdish"] >= 0.08:
        main = "kurdish (Sorani)"
    elif share["english"] >= 0.7:
        main = "english"
    elif share["english"] >= 0.1:
        main = "arabic + english mixed"
    else:
        main = "arabic"
    note = ""
    if share["kurdish"] >= 0.08 and configured == "ar":
        note = "Kurdish letters found but the transcriber is set to Arabic: Kurdish speech will be heard badly. Check the words carefully."
    elif share["english"] >= 0.7 and configured == "ar":
        note = "Mostly English but the transcriber is set to Arabic."
    return {"main": main, "share": share, "configured": configured, "note": note}


def vocabulary(words, glossary_terms):
    """Glossary words: how many times the preferred spelling appears, and spoken forms still left unfixed."""
    texts = [_norm(w.get("text", "")) for w in words]
    hits, unfixed = {}, []
    for t in glossary_terms or []:
        want, spoken = _norm(t.get("write", "")), _norm(t.get("spoken", ""))
        if want and want in texts:
            hits[t["write"]] = texts.count(want)
        if spoken and want and spoken != want:
            for i, x in enumerate(texts):
                if x == spoken:
                    unfixed.append({"i": i, "text": words[i]["text"], "should_be": t["write"]})
    return {"used": hits, "unfixed_spellings": unfixed[:30]}


# ----------------------------------------------------------------------------- audio: loudness per word
def read_audio(path):
    """-> (samples as array('h'), sample_rate) or (None, 0)."""
    try:
        with wave.open(path, "rb") as w:
            if w.getsampwidth() != 2 or w.getnchannels() != 1:
                return None, 0
            return array.array("h", w.readframes(w.getnframes())), w.getframerate()
    except (OSError, wave.Error, EOFError):
        return None, 0


def frame_levels(samples, sr):
    """RMS in dB for every 50 ms frame."""
    n = max(1, int(sr * FRAME))
    out = []
    for i in range(0, len(samples) - n + 1, n):
        seg = samples[i:i + n]
        out.append(_db(math.sqrt(sum(s * s for s in seg) / n)))
    return out


def word_levels(words, levels):
    out = []
    for w in words:
        a, b = int(w["start"] / FRAME), max(int(w["start"] / FRAME) + 1, int(w["end"] / FRAME))
        seg = levels[a:b] or [min(levels) if levels else -90.0]
        out.append(round(max(seg), 1))
    return out


# ----------------------------------------------------------------------------- step 2: delivery
def delivery(words, wl, silence_gap=0.6):
    fillers, repeats, pauses = [], [], []
    for i, w in enumerate(words):
        n = _norm(w["text"])
        if w["text"] in tr.FILLERS or n in {_norm(x) for x in tr.FILLERS}:
            fillers.append({"i": i, "text": w["text"], "t": round(w["start"], 2)})
        if i and n and n == _norm(words[i - 1]["text"]) and n not in ("لا",):
            repeats.append({"i": i, "text": w["text"], "t": round(w["start"], 2), "kind": "word said twice"})
        if i >= 3 and n and (n, _norm(words[i - 1]["text"])) == (_norm(words[i - 2]["text"]), _norm(words[i - 3]["text"])):
            repeats.append({"i": i, "text": words[i - 1]["text"] + " " + w["text"], "t": round(w["start"], 2), "kind": "phrase restarted"})
        if i:
            gap = w["start"] - words[i - 1]["end"]
            if gap >= silence_gap:
                pauses.append({"after": i - 1, "t": round(words[i - 1]["end"], 2), "seconds": round(gap, 2), "long": gap >= 1.2})
    phr = tr.phrases(words, gap=silence_gap, max_words=60)
    speed, unfinished = [], []
    talk = sum(w["end"] - w["start"] for w in words) or 1.0
    for ph in phr:
        a, b = words[ph[0]]["start"], words[ph[-1]]["end"]
        wpm = len(ph) / max((b - a) / 60.0, 1e-3)
        speed.append({"from": ph[0], "to": ph[-1], "t": round(a, 2), "words_per_min": round(wpm)})
        last = _norm(words[ph[-1]]["text"])
        nxt_gap = (words[ph[-1] + 1]["start"] - words[ph[-1]]["end"]) if ph[-1] + 1 < len(words) else 9.0
        if last in {_norm(c) for c in CONNECTORS} and nxt_gap >= 0.8 and len(ph) >= 2:
            unfinished.append({"i": ph[-1], "t": round(words[ph[-1]]["end"], 2), "text": " ".join(words[i]["text"] for i in ph[-6:])})
    wpms = [s["words_per_min"] for s in speed if s["to"] - s["from"] >= 3]
    # emphasis: words clearly louder than the speaker's usual level
    med = _pct(wl, 0.5) if wl else 0.0
    emph = [{"i": i, "text": words[i]["text"], "t": round(words[i]["start"], 2), "db_above_usual": round(wl[i] - med, 1)}
            for i in range(len(words)) if wl and wl[i] - med >= 4.0 and len(_norm(words[i]["text"])) >= 3]
    return {"fillers": fillers, "repeats": repeats, "pauses": pauses[:60], "long_pauses": sum(p["long"] for p in pauses),
            "unfinished_sentences": unfinished[:20], "emphasis_words": sorted(emph, key=lambda e: -e["db_above_usual"])[:25],
            "speed": {"median_words_per_min": round(_pct(wpms, 0.5)) if wpms else 0,
                      "fast_phrases": [s for s in speed if s["words_per_min"] >= 230 and s["to"] - s["from"] >= 3][:10],
                      "slow_phrases": [s for s in speed if 0 < s["words_per_min"] <= 80 and s["to"] - s["from"] >= 3][:10]},
            "talk_seconds": round(talk, 1)}


# ----------------------------------------------------------------------------- step 3: scores
def word_confidence(words, wl, floor_db, changed):
    """0-1 per word from evidence we can check (a rough guide: whisper gives no confidence of its own here)."""
    out, why = [], []
    for i, w in enumerate(words):
        c, r = 1.0, []
        d = w["end"] - w["start"]
        n = _norm(w["text"])
        if d < 0.08 or (d > 1.4 and len(n) < 8):
            c -= 0.25; r.append("odd length in time")
        if i in changed:
            c -= 0.2; r.append("the spelling fixer changed it")
        if wl and wl[i] <= floor_db + 3:
            c -= 0.2; r.append("barely louder than background")
        if len(n) == 1 and n not in ("و", "ا", "a", "i"):
            c -= 0.15; r.append("single letter")
        out.append(round(max(0.0, c), 2)); why.append(", ".join(r))
    return out, why


def timestamp_reliability(words, dropped_count):
    bad = 0
    for i, w in enumerate(words):
        if w["end"] <= w["start"] or (i and w["start"] < words[i - 1]["end"] - 0.02):
            bad += 1
        elif w["end"] - w["start"] > 1.6:
            bad += 1
    share = bad / max(1, len(words))
    inv = dropped_count / max(1, len(words) + dropped_count)
    return round(max(0.0, 1 - share * 3 - inv * 2) * 100), {"odd_timestamps": bad, "dropped_as_invented": dropped_count}


def audio_quality(levels, samples, lufs):
    if not levels:
        return None, {}
    floor, loud = _pct(levels, 0.1), _pct(levels, 0.9)
    snr = loud - floor
    clip = sum(1 for s in samples if abs(s) >= 32000) / max(1, len(samples)) if samples else 0.0
    score = min(70.0, max(0.0, snr / 30.0 * 70)) + (15 if clip < 0.001 else 0) + (15 if lufs is not None and -30 <= lufs <= -10 else 0)
    return round(min(100.0, score)), {"speech_vs_background_db": round(snr, 1), "background_db": round(floor, 1),
                                      "clipping_share": round(clip, 5), "lufs": lufs}


def delivery_energy(wl, wpm):
    if not wl:
        return None
    dyn = _pct(wl, 0.9) - _pct(wl, 0.5)
    return round(min(100.0, dyn * 12 + max(0, wpm - 130) / 2))


def key_terms(words, top=8):
    cnt = {}
    for w in words:
        n = _norm(w["text"])
        if len(n) >= 3 and n not in {_norm(x) for x in STOP} and not n.isdigit():
            cnt[n] = cnt.get(n, 0) + 1
    return [{"word": k, "times": v} for k, v in sorted(cnt.items(), key=lambda kv: -kv[1])[:top] if v >= 3]


def _lufs(job):
    try:
        m = re.search(r"(-?[0-9.]+)\s*LUFS", open(os.path.join(job, "loudness.txt")).read())
        return float(m[1]) if m else None
    except OSError:
        return None


# ----------------------------------------------------------------------------- everything together
def analyze(raw, words, glossary_terms=None, changed=(), dropped=0, wav=None, lufs=None, configured="ar"):
    """raw = the untouched ASR words, words = the corrected words (same count, same timing)."""
    samples, sr = read_audio(wav) if wav else (None, 0)
    levels = frame_levels(samples, sr) if samples else []
    wl = word_levels(words, levels) if levels else []
    floor = _pct(levels, 0.1) if levels else -60.0
    conf, why = word_confidence(words, wl, floor, set(changed))
    dl = delivery(words, wl)
    ts, ts_detail = timestamp_reliability(words, dropped)
    aq, aq_detail = audio_quality(levels, samples, lufs)
    low = [{"i": i, "text": words[i]["text"], "raw_text": raw[i]["text"] if i < len(raw) else words[i]["text"],
            "t": round(words[i]["start"], 2), "confidence": conf[i], "why": why[i]}
           for i in range(len(words)) if conf[i] < 0.6]
    emph = dl["emphasis_words"]
    return {
        "version": 1,
        "language": languages(words, configured),
        "speakers": {"count": 1, "assumed": True, "note": "Speaker labels need a speaking-person model; not built yet. One speaker is assumed."},
        "vocabulary": vocabulary(words, glossary_terms),
        "transcript": {"words": len(words), "raw_file": "transcript_asr.json", "corrected_file": "transcript.json",
                       "corrections": len(list(changed)), "note": "Literal words are kept in the raw file; corrections are listed, never replace it."},
        "delivery": dl,
        "key_terms": key_terms(words),
        "scores": {
            "transcription_confidence": {"value": round(sum(conf) / max(1, len(conf)) * 100), "low_confidence_words": len(low),
                                         "means": "How likely the words were heard right (rough guide from timing, loudness and spelling fixes)."},
            "timestamp_reliability": {"value": ts, **ts_detail, "means": "How trustworthy the word timings are for cutting."},
            "audio_quality": {"value": aq, **aq_detail, "means": "Background noise, clipping and loudness of the voice."},
            "delivery_energy": {"value": delivery_energy(wl, dl["speed"]["median_words_per_min"]), "emphasis_words": len(emph),
                                "means": "How much the voice rises and how fast it goes."},
            "semantic_importance": {"value": None, "means": "Meaning-based importance comes from the story step (AI), not from here."},
        },
        "low_confidence_words": low[:60],
        "word_levels_db": wl,
        "word_confidence": conf,
    }


def build(job, configured="ar", glossary_terms=None):
    """Reads the job folder, writes speech_intel.json. Returns the dict, or None when there is no transcript yet."""
    raw = _jload(os.path.join(job, "transcript_asr.json"))
    words = _jload(os.path.join(job, "transcript.json")) or raw
    if not words:
        return None
    meta = _jload(os.path.join(job, "transcript_fix_meta.json"), {}) or {}
    changed = [c["i"] for c in meta.get("changes", []) if isinstance(c.get("i"), int)]
    dropped = len(_jload(os.path.join(job, "transcript_asr_dropped.json"), []) or [])
    wav = os.path.join(job, "audio16k.wav")
    out = analyze(raw or words, words, glossary_terms, changed, dropped, wav if os.path.exists(wav) else None, _lufs(job), configured)
    tmp = os.path.join(job, "speech_intel.json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    os.replace(tmp, os.path.join(job, "speech_intel.json"))
    return out


def summary_lines(si):
    """A few plain lines for the run log and the report."""
    s, d = si["scores"], si["delivery"]
    lines = [f"language: {si['language']['main']}" + (f" ({si['language']['note']})" if si["language"]["note"] else ""),
             f"scores (rough guides): words heard right {s['transcription_confidence']['value']}/100, timings {s['timestamp_reliability']['value']}/100, "
             f"audio {s['audio_quality']['value']}/100, delivery energy {s['delivery_energy']['value']}/100",
             f"delivery: {len(d['fillers'])} fillers, {len(d['repeats'])} repeats, {d['long_pauses']} long pauses, "
             f"{d['speed']['median_words_per_min']} words/min, {len(d['unfinished_sentences'])} maybe-unfinished sentences"]
    if si["low_confidence_words"]:
        lines.append("check these words: " + ", ".join(f"{w['text']} ({w['t']}s)" for w in si["low_confidence_words"][:8]))
    return lines
