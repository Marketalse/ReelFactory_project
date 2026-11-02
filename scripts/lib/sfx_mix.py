"""Sound design (T127): the sound effects the registry promises, placed on the timeline. Free, local.

Before this, the effects were made but never used. Now every moment plays its registry sound when it starts (whoosh for a card, hit for the
title and the flash, pop for a name tag or a key word, ding for a spoken number), key words get a soft pop at most every 3 s, and a
punch-in gets a very quiet pop. Quiet by design (brand.json -> sfx.volume, default 0.45 of the voice): the final loudness step levels
the whole mix, so the voice stays on top. Switch off with brand.json -> sfx.enabled false. The sounds are our own (scripts/make_sfx.py).
"""
import json, os, shutil, subprocess

from . import config as cfg

LOUD = {"hit": 1.5, "ding": 1.0, "whoosh": 1.0, "pop": 1.0, "click": 1.0, "rise": 1.0}      # relative weight per sound
QUIET_GAP = 0.25                                                                             # never two effects closer than this (seconds)


def settings():
    s = dict(cfg.BRAND.get("sfx") or {})
    return {"enabled": s.get("enabled", True), "volume": float(s.get("volume", 0.45)), "key_words": s.get("key_words", True),
            "punch_ins": s.get("punch_ins", True)}


def sfx_dir():
    return os.path.join(cfg.ROOT, "style", "sfx")


def ensure_files():
    """The wavs are not kept in git: make them (ffmpeg, a second) when missing. -> catalog {name: seconds} or {} if impossible."""
    cat = os.path.join(sfx_dir(), "catalog.json")
    try:
        have = json.load(open(cat, encoding="utf-8")).get("sounds", [])
    except (OSError, ValueError):
        have = []
    if not have or any(not os.path.exists(os.path.join(sfx_dir(), s["file"])) for s in have):
        try:
            import sys
            sys.path.insert(0, os.path.join(cfg.ROOT, "scripts"))
            import make_sfx
            make_sfx.make()
            have = json.load(open(cat, encoding="utf-8")).get("sounds", [])
        except (SystemExit, Exception):                              # noqa: BLE001 - no sound effects is better than no reel
            return {}
    return {s["name"]: float(s.get("seconds", 0.5)) for s in have if os.path.exists(os.path.join(sfx_dir(), s["file"]))}


def plan(timeline, registry, caption_words=(), keyword_ids=()):
    """[{name, t}] sorted by time, from the timeline (reel time). Pure: no files are touched."""
    st = settings()
    if not st["enabled"]:
        return []
    ev = []
    for s in timeline.get("scenes", []):
        spec = (registry.get(s["block"]) or {}).get("sfx") or {}
        if spec.get("in") and s["block"] != "captions":
            ev.append({"name": spec["in"], "t": max(0.0, s["t_in"] + (0.12 if s["block"] == "hook_two_tone" else 0.0))})
        if spec.get("value") and s["block"] == "split":
            ev.append({"name": spec["value"], "t": s["t_in"] + 0.8})
    if st["key_words"]:
        gap = ((registry.get("captions") or {}).get("sfx") or {}).get("min_gap_s", 3)
        last = -99.0
        for k in sorted(keyword_ids):
            if 0 <= k < len(caption_words) and caption_words[k]["start"] - last >= gap:
                ev.append({"name": (registry["captions"]["sfx"] or {}).get("keyword", "pop"), "t": caption_words[k]["start"], "kind": "keyword"}); last = caption_words[k]["start"]
    if st["punch_ins"]:
        for t, _sc in timeline.get("punch_ins", []):
            ev.append({"name": "pop", "t": t, "quiet": True})
    ev.sort(key=lambda e: e["t"])
    out, last_t = [], -99.0
    for e in ev:                                                     # keep it clean: never a pile-up of effects
        if e["t"] - last_t >= QUIET_GAP:
            out.append(e); last_t = e["t"]
    return out


def project_audio(events, duration, out_dir):
    """Copy the used sounds into the project and return the audio list for hfbuild.build_project ([] when sounds are unavailable)."""
    cat = ensure_files()
    if not events or not cat:
        return []
    os.makedirs(os.path.join(out_dir, "assets", "sfx"), exist_ok=True)
    base, audio = settings()["volume"], []
    for n, e in enumerate(events):
        if e["name"] not in cat or e["t"] >= duration - 0.2:
            continue
        shutil.copy(os.path.join(sfx_dir(), e["name"] + ".wav"), os.path.join(out_dir, "assets", "sfx", e["name"] + ".wav"))
        vol = base * LOUD.get(e["name"], 1.0) * (0.5 if e.get("quiet") else 1.0)
        audio.append({"id": f"sfx{n}", "src": f"assets/sfx/{e['name']}.wav", "t_in": round(e["t"], 3), "dur": round(min(cat[e["name"]] + 0.03, duration - e["t"]), 3),
                      "volume": round(min(1.0, vol), 3)})
    return audio
