"""Transcript helpers: clean the ASR output and run Gate 0 (Hesham fixes words in a plain text file).

Gate 0 file format (transcript_review.txt), one phrase per line:
    12 | 4.20-6.85 | يعني لما انت حاط بيج
Hesham edits only the words after the second bar. Timings stay: if a line keeps its word count, each word keeps
its own time; if he adds or removes words, the line's time is shared out by word length.
"""
import re

FILLERS = {"آه", "اه", "ااه", "امم", "اممم", "ممم", "مم", "ام", "uh", "um", "uhm", "erm", "eh", "ah"}
HALLUCINATIONS = {"شكرا", "شكراً", "thank", "thanks", "you.", "اشتركوا", "ترجمة"}


def silences(path):
    """[(start, end)] from ffmpeg silencedetect output."""
    try:
        txt = open(path, encoding="utf-8").read()
    except OSError:
        return []
    starts = [float(x) for x in re.findall(r"silence_start: ([0-9.]+)", txt)]
    ends = [float(x) for x in re.findall(r"silence_end: ([0-9.]+)", txt)]
    return list(zip(starts, ends + [float("inf")] * (len(starts) - len(ends))))


def clean_asr(words, sil, duration):
    """Drop words whisper invents over silence: anything starting inside a long silence (>= 0.6 s),
    and known filler hallucinations in the final silent tail. Returns (kept, dropped)."""
    kept, dropped = [], []
    long_sil = [(s, e) for s, e in sil if min(e, duration) - s >= 0.6]
    for w in words:
        text = str(w.get("text", "")).strip()
        if not text or text in ("♪", "�"):
            dropped.append(w); continue
        inside = any(s + 0.05 <= w["start"] and w["end"] <= e - 0.05 for s, e in long_sil)
        tail = long_sil and w["start"] >= long_sil[-1][0] and long_sil[-1][1] >= duration - 0.2
        if inside or (tail and text.strip(".!؟?").lower() in HALLUCINATIONS):
            dropped.append(w); continue
        kept.append(dict(w, text=text))
    return kept, dropped


def phrases(words, gap=0.35, max_words=14):
    """Group word indices into phrases split on pauses (for the review file and prompts)."""
    out, cur = [], []
    for i, w in enumerate(words):
        if cur and (w["start"] - words[cur[-1]]["end"] > gap or len(cur) >= max_words):
            out.append(cur); cur = []
        cur.append(i)
    if cur:
        out.append(cur)
    return out


HEADER = """# Gate 0 — check the words. Fix only the text after the second |, keep the numbers.
# English words you said in English: write them in Latin letters (customer service).
# When you're done, change the next line to:  STATUS: reviewed   and run the same command again.
STATUS: waiting
"""


def write_review(path, words):
    lines = [HEADER]
    for n, ph in enumerate(phrases(words)):
        a, b = words[ph[0]]["start"], words[ph[-1]]["end"]
        lines.append(f"{n:03d} | {a:.2f}-{b:.2f} | " + " ".join(words[i]["text"] for i in ph))
    open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")


def review_done(path):
    try:
        return any(l.strip().lower().replace(" ", "") == "status:reviewed" for l in open(path, encoding="utf-8"))
    except OSError:
        return False


def apply_review(path, words):
    """Return (new_words, stats). Raises ValueError naming the line if the file was damaged."""
    groups = phrases(words)
    edited = {}
    for raw in open(path, encoding="utf-8"):
        line = raw.rstrip("\n")
        if not line.strip() or line.lstrip().startswith("#") or line.upper().startswith("STATUS"):
            continue
        parts = line.split("|", 2)
        if len(parts) != 3 or not parts[0].strip().isdigit():
            raise ValueError(f"transcript_review.txt: can't read this line (keep the 'NNN | a-b | words' shape): {line[:80]}")
        edited[int(parts[0])] = parts[2].split()
    if set(edited) != set(range(len(groups))):
        missing = sorted(set(range(len(groups))) - set(edited))
        raise ValueError(f"transcript_review.txt: lines missing or added: {missing[:10]} (don't delete or add numbered lines)")
    out, changed, total = [], 0, 0
    for n, ph in enumerate(groups):
        old = [words[i] for i in ph]; new = edited[n]; total += len(old)
        if len(new) == len(old):
            for w, t in zip(old, new):
                changed += t != w["text"]
                out.append(dict(w, text=t))
        else:
            changed += max(len(new), len(old))
            a, b = old[0]["start"], old[-1]["end"]
            weights = [max(1, len(t)) for t in new] or [1]
            span, t0 = b - a, a
            for t, wt in zip(new, weights):
                d = span * wt / sum(weights)
                out.append({"text": t, "start": round(t0, 3), "end": round(t0 + d * 0.92, 3), "edited": True})
                t0 += d
    return out, {"words_before": total, "words_after": len(out), "changed": changed,
                 "error_rate": round(changed / total, 3) if total else 0.0}
