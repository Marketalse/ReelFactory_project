"""Creative brief (T100): what the reel is FOR, set by Hesham before editing. Free, local.

Fields (all optional; nothing chosen = the old behaviour):
  goal      educate | sell | followers | entertain
  style     educational | fast | storytelling          (matches the story step's styles)
  length    short (30-45 s) | standard (40-90 s) | long (60-90 s)
  audience  short free text
  action    what viewers should do (free text), e.g. comment "store"
Saved as jobs/<job>/brief.json; the same facts are written into brief.md in plain words so the story step and the director read them.
The end card stays controlled by config/brand.json (cta.enabled): "action" is a hint for the words, not a new card.
"""
import json, os, re

GOALS = {"educate": "teach something useful", "sell": "sell a product or service", "followers": "win new followers", "entertain": "entertain and be shared"}
STYLES = {"educational": "clear and explained step by step, calmer pace", "fast": "fast and energetic, quick cuts, short beats",
          "storytelling": "a story with a beginning, a turn and an ending, emotional pace"}
LENGTHS = {"short": (30, 45), "standard": (40, 90), "long": (60, 90)}
MARK = "<!-- creative brief -->"


def clean(raw):
    """Keep only valid values; never raises. -> dict (empty when nothing valid was given)."""
    raw = raw if isinstance(raw, dict) else {}
    out = {}
    if raw.get("goal") in GOALS:
        out["goal"] = raw["goal"]
    if raw.get("style") in STYLES:
        out["style"] = raw["style"]
    if raw.get("length") in LENGTHS:
        out["length"] = raw["length"]
    from . import themes
    if raw.get("theme") in themes.names():
        out["theme"] = raw["theme"]
    for k, n in (("audience", 120), ("action", 160)):
        v = re.sub(r"\s+", " ", str(raw.get(k) or "")).strip()[:n]
        if v:
            out[k] = v
    return out


def length_range(brief, default):
    """(min, max) seconds: the brief's choice, else the project's rule."""
    return LENGTHS.get((brief or {}).get("length"), default)


def to_text(brief):
    """Plain sentences for the AI. '' when there is nothing."""
    b = clean(brief)
    if not b:
        return ""
    L = ["CREATIVE BRIEF (set by Hesham before editing; follow it, but use only his own words):"]
    if "goal" in b:
        L.append(f"- Goal: {GOALS[b['goal']]}.")
    if "audience" in b:
        L.append(f"- Audience: {b['audience']}.")
    if "style" in b:
        L.append(f"- Style: {b['style']}: {STYLES[b['style']]}.")
    if "length" in b:
        lo, hi = LENGTHS[b["length"]]
        L.append(f"- Length: {lo}-{hi} seconds.")
    if "action" in b:
        L.append(f"- Action wanted from viewers: {b['action']}. (Only if he actually says it; never invent words.)")
    return "\n".join(L) if len(L) > 1 else ""


def save(folder, brief, notes=""):
    """Write brief.json and brief.md into an inbox folder (or a job folder). The notes he typed stay, the brief text goes after them."""
    b = clean(brief)
    os.makedirs(folder, exist_ok=True)
    if b:
        with open(os.path.join(folder, "brief.json"), "w", encoding="utf-8") as f:
            json.dump(b, f, ensure_ascii=False, indent=1)
    body = (notes or "").strip()
    text = to_text(b)
    if text:
        body = (body + "\n\n" if body else "") + MARK + "\n" + text
    if body or os.path.exists(os.path.join(folder, "brief.md")):
        with open(os.path.join(folder, "brief.md"), "w", encoding="utf-8") as f:
            f.write(body + "\n")
    return b


def load(job):
    try:
        with open(os.path.join(job, "brief.json"), encoding="utf-8") as f:
            return clean(json.load(f))
    except (OSError, ValueError):
        return {}
