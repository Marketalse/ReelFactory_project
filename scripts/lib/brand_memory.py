"""Brand memory: what Hesham APPROVED, remembered so new reels feel like his best ones. Free, local, no AI.

The brand profile itself (colours, font, caption rules, logo rules) is config/brand.json and always wins. This file only
remembers the LOOK of reels he approved (how busy they were) and turns it into a short hint for the director and a
"busier/calmer than usual" note in the visual plan. It needs at least MIN_REELS approved reels before it says anything.

Stored OUTSIDE the project (~/.reelfactory/brand_memory.json, or RF_BRAND_MEMORY) so an update can never clash with it.
Override or switch off: set "enabled": false, or put fixed numbers under "overrides" (they replace the learned averages).
"""
import json, os, time

MIN_REELS = 2
KEEP = 30
KEYS = ("moments_per_min", "punch_ins_per_min", "caption_words_per_min", "text_screen_share")


def path():
    return os.environ.get("RF_BRAND_MEMORY") or os.path.expanduser("~/.reelfactory/brand_memory.json")


def _load():
    try:
        with open(path(), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(d):
    os.makedirs(os.path.dirname(path()), exist_ok=True)
    tmp = path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path())


def record(job_name, intensity, blocks=None):
    """Remember one approved reel. Same reel approved twice is stored once (newest wins)."""
    d = _load()
    d.setdefault("enabled", True); d.setdefault("overrides", {})
    rows = [r for r in d.get("approved", []) if r.get("job") != job_name]
    rows.append({"job": job_name, "time": time.strftime("%Y-%m-%d %H:%M"),
                 "intensity": {k: intensity.get(k) for k in KEYS if intensity.get(k) is not None}, "blocks": blocks or {}})
    d["approved"] = rows[-KEEP:]
    _save(d)
    return len(d["approved"])


def profile():
    """-> {"n", "intensity": {...}, "blocks": {...}} or None (off, or too few approved reels)."""
    d = _load()
    if d.get("enabled") is False:
        return None
    rows = d.get("approved", [])
    if len(rows) < MIN_REELS:
        return None
    avg = {}
    for k in KEYS:
        v = [r["intensity"][k] for r in rows if k in r.get("intensity", {})]
        if v:
            avg[k] = round(sum(v) / len(v), 2)
    for k, v in (d.get("overrides") or {}).items():
        if k in KEYS and isinstance(v, (int, float)):
            avg[k] = v
    blocks = {}
    for r in rows:
        for b, n in (r.get("blocks") or {}).items():
            blocks[b] = blocks.get(b, 0) + n
    return {"n": len(rows), "intensity": avg, "blocks": blocks}


def hint():
    """One short line for the director's brief, or ''."""
    p = profile()
    if not p:
        return ""
    i = p["intensity"]
    fav = ", ".join(b for b, _ in sorted(p["blocks"].items(), key=lambda kv: -kv[1])[:3])
    return (f"Look of the {p['n']} reels he approved: about {i.get('moments_per_min', '?')} cards/graphics and {i.get('punch_ins_per_min', '?')} zooms per minute"
            + (f"; most used: {fav}" if fav else "") + ". Aim for the same feel (his own choice always wins).")


def compare(intensity):
    """Plain notes when this reel is clearly busier or calmer than his approved ones."""
    p = profile()
    if not p:
        return []
    notes = []
    names = {"moments_per_min": "cards and graphics", "punch_ins_per_min": "zooms", "caption_words_per_min": "caption words", "text_screen_share": "time with text on screen"}
    for k, label in names.items():
        mine, usual = intensity.get(k), p["intensity"].get(k)
        if mine is None or not usual:
            continue
        r = mine / usual
        if r >= 1.5:
            notes.append(f"busier than your approved reels: {label} {mine:g} vs usual {usual:g}")
        elif r <= 0.5:
            notes.append(f"calmer than your approved reels: {label} {mine:g} vs usual {usual:g}")
    return notes
