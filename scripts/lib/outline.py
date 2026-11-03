"""OUTLINE step (T130): one strong-model call turns the cut talk into a STRUCTURE before any visuals are planned:
hook, sections (steps / points / proof), the recap, and the format that fits. The director then builds the visuals around it.
Every title on screen is built by CODE from his own spoken words (the AI only points at word numbers), so nothing is invented."""
import re

FORMATS = ("explainer", "tips", "story", "opinion")
KINDS = ("step", "point", "proof", "turn")
MAX_SECTIONS = 7
TITLE_WORDS = 4

PROMPT = """You are the story architect for Hesham's Iraqi short-form channel. The reel is ALREADY CUT. Below is its transcript; each word has a number like (12)word.
Find the STRUCTURE of what he says, using ONLY his words (never invent). Return ONLY JSON:
{{"format":"explainer|tips|story|opinion",
 "hook_word":<number of the word where the hook line starts>,
 "sections":[{{"from_word":<n>,"to_word":<n>,"kind":"step|point|proof|turn","title_from":<n>,"title_to":<n>}}],
 "concept":{{"from_word":<n>,"to_word":<n>}} or null}}
Rules:
- explainer = a process or chain in order (steps); tips = separate pieces of advice; story = events then a lesson; opinion = a claim then reasons.
- 2 to {max_sections} sections, in time order, not overlapping, together covering the body of the talk (the hook line may come before the first one).
- title_from..title_to = a short phrase of at most {tw} words that he actually says inside that section and that names it. It will be shown on screen.
- concept = ONLY if he states one central idea or comparison in a few words (e.g. a named effect); else null.
- If the talk has no real structure, return format "opinion" with 2 sections. Never pad.
No commentary outside the JSON.

TRANSCRIPT:
{transcript}"""


def _int(v, lo, hi):
    try:
        v = int(v)
    except (TypeError, ValueError):
        return None
    return v if lo <= v <= hi else None


def clean(ans, words):
    """Validate the AI answer against the real words. Returns the outline dict (titles built from his words) or raises ValueError."""
    if not isinstance(ans, dict):
        raise ValueError("the outline answer is not an object")
    n = len(words)
    fmt = ans.get("format") if ans.get("format") in FORMATS else "opinion"
    hook = _int(ans.get("hook_word"), 0, n - 1)
    secs, last_end = [], -1
    for s in (ans.get("sections") or [])[:MAX_SECTIONS]:
        if not isinstance(s, dict): continue
        a, b = _int(s.get("from_word"), 0, n - 1), _int(s.get("to_word"), 0, n - 1)
        ta, tb = _int(s.get("title_from"), 0, n - 1), _int(s.get("title_to"), 0, n - 1)
        if None in (a, b, ta, tb) or b < a or a <= last_end: continue
        if not (a <= ta <= tb <= b) or tb - ta + 1 > TITLE_WORDS: continue          # the title must be his words, inside the section
        secs.append({"from_word": a, "to_word": b, "kind": s.get("kind") if s.get("kind") in KINDS else "point",
                     "title": " ".join(w["text"] for w in words[ta:tb + 1]).strip(" ،,.!؟?"), "title_from": ta, "title_to": tb,
                     "t_in": round(words[a]["start"], 2), "t_out": round(words[b]["end"], 2)})
        last_end = b
    if len(secs) < 2:
        raise ValueError("fewer than 2 usable sections")
    concept = None
    c = ans.get("concept")
    if isinstance(c, dict):
        ca, cb = _int(c.get("from_word"), 0, n - 1), _int(c.get("to_word"), 0, n - 1)
        if ca is not None and cb is not None and 0 <= cb - ca < 6:
            concept = {"from_word": ca, "to_word": cb, "text": " ".join(w["text"] for w in words[ca:cb + 1]).strip(" ،,.!؟?")}
    return {"format": fmt, "hook_word": hook if hook is not None else secs[0]["from_word"], "sections": secs, "concept": concept,
            "recap": [s["title"] for s in secs]}


def brief_note(o):
    """The text added to the director's brief."""
    lines = [f"STORY STRUCTURE (from the outline step; build the visuals around it, one clear visual change per section): format = {o['format']}."]
    for i, s in enumerate(o["sections"], 1):
        lines.append(f"  section {i} ({s['kind']}) words {s['from_word']}-{s['to_word']} ({s['t_in']}-{s['t_out']}s): title \"{s['title']}\" (his words {s['title_from']}-{s['title_to']})")
    if o.get("concept"):
        lines.append(f"  central idea in his words: \"{o['concept']['text']}\" (words {o['concept']['from_word']}-{o['concept']['to_word']})")
    lines.append("  Show section titles only as his own words; a recap near the end may list the titles in order.")
    return "\n".join(lines)
