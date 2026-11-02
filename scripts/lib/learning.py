"""Self-learning from posted-reel results (T76). Free, local, no AI.

Hesham types the numbers from Instagram/TikTok Insights (dashboard "How did it do?"). With at least MIN_REELS reels that have results,
this compares his better-held reels (top half by share of the video watched) with the weaker half on facts about the edit (length,
cards and zooms per minute, title length, ready-to-post score) and keeps at most 3 plain lessons where the difference is large.
These are patterns in a SMALL sample, not proof: the lessons say so, they only nudge the director (one line in its brief) and never
override a comment from Hesham. Stored outside the project (~/.reelfactory/learned.json, or RF_LEARNED) so updates never clash.
Switch off or edit: set "enabled": false in that file.
"""
import json, math, os, time

MIN_REELS = 10
EFFECT = 0.8                       # how clear the difference must be (in standard deviations) before it becomes a lesson
FEATURES = {"length_s": ("length", "seconds"), "moments_per_min": ("cards and graphics per minute", ""), "zooms_per_min": ("zooms per minute", ""),
            "hook_chars": ("opening title length", "characters"), "ready_score": ("ready-to-post score", "")}


def path():
    return os.environ.get("RF_LEARNED") or os.path.expanduser("~/.reelfactory/learned.json")


def _load():
    try:
        with open(path(), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _score(entries):
    """Share of the video watched (%), from the latest check (30d > 7d > 2d)."""
    for w in ("30d", "7d", "48h"):
        for e in entries:
            if e.get("when") == w and e.get("watch_pct") is not None:
                return float(e["watch_pct"])
    return None


def _features(f):
    L = f.get("length_s") or 0
    out = {"length_s": L, "hook_chars": f.get("hook_chars"), "ready_score": f.get("ready_score")}
    if L:
        out["moments_per_min"] = round((f.get("moments") or 0) / L * 60, 2)
        out["zooms_per_min"] = round((f.get("zooms") or 0) / L * 60, 2)
    return out


def _mean(x):
    return sum(x) / len(x)


def _sd(x):
    m = _mean(x)
    return math.sqrt(sum((v - m) ** 2 for v in x) / max(1, len(x) - 1))


def analyze(perf, min_reels=MIN_REELS):
    """perf = reels_api.performance() rows. -> {"n", "lessons": [...], "details": {...}} (lessons empty when the sample is too small)."""
    rows = []
    for r in perf or []:
        s = _score(r.get("entries") or [])
        if s is not None:
            rows.append((s, _features(r.get("facts") or {})))
    out = {"n": len(rows), "lessons": [], "details": {}}
    if len(rows) < min_reels:
        out["note"] = f"needs {min_reels} reels with results (have {len(rows)})"
        return out
    rows.sort(key=lambda x: -x[0])
    half = len(rows) // 2
    top, bot = rows[:half], rows[-half:]
    found = []
    for k, (label, unit) in FEATURES.items():
        a = [f[k] for _, f in top if f.get(k) is not None]; b = [f[k] for _, f in bot if f.get(k) is not None]
        if len(a) < 3 or len(b) < 3:
            continue
        sd = math.sqrt((_sd(a) ** 2 + _sd(b) ** 2) / 2) or 1e-9
        d = (_mean(a) - _mean(b)) / sd
        out["details"][k] = {"better_reels": round(_mean(a), 2), "weaker_reels": round(_mean(b), 2), "effect": round(d, 2)}
        if abs(d) >= EFFECT:
            found.append((abs(d), f"Your better-held reels had {'higher' if d > 0 else 'lower'} {label}: about {_mean(a):.1f}{' ' + unit if unit else ''} "
                                  f"vs {_mean(b):.1f} in the weaker ones (from {len(rows)} reels; a pattern, not proof)."))
    out["lessons"] = [t for _, t in sorted(found, reverse=True)[:3]]
    return out


def update(perf):
    """Re-learn from all results and save. Returns the analysis. Keeps the user's 'enabled' switch."""
    res = analyze(perf)
    d = _load()
    d.update({"enabled": d.get("enabled", True), "updated": time.strftime("%Y-%m-%d %H:%M"), **res})
    os.makedirs(os.path.dirname(path()), exist_ok=True)
    tmp = path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path())
    return res


def hint():
    """One short line for the director's brief, or ''."""
    d = _load()
    if d.get("enabled") is False or not d.get("lessons"):
        return ""
    return "LEARNED FROM HIS POSTED REELS (small sample, only a nudge; his comments always win): " + " ".join(d["lessons"])
