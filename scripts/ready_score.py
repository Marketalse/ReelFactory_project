#!/usr/bin/env python3
"""Ready-to-post score (0-100): how well a reel follows what keeps people watching short videos.
NOT a prediction of views. Free and local: it only reads the reel's own files (timeline, cut, QA results, cover).

    python3 scripts/ready_score.py jobs/<job> [--final]

Each check gives points and, when it falls short, one concrete tip. Written to jobs/<job>/ready_score.json
(the dashboard shows it on the draft and final pages; the Results page puts it next to the real numbers,
so later we can see which checks matter for Hesham's audience)."""
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import config as cfg, director  # noqa: E402

CONTENT = {"text_card", "split", "flash", "logo_card", "info_card", "number_graph", "before_after", "tier_list", "ui_card", "doc_card", "pixel_scene"}


def _j(p, default=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _band(value, steps):
    """steps: [(limit, points)], first limit the value fits under wins."""
    for lim, pts in steps:
        if value <= lim:
            return pts
    return 0


def score(job, final=False):
    tl = _j(os.path.join(job, "timeline.json"))
    edl = _j(os.path.join(job, "edl.json"))
    if not tl or not edl:
        return None
    qa = _j(os.path.join(job, "qa_final.json" if final else "qa.json")) or _j(os.path.join(job, "qa.json")) or {}
    m = qa.get("metrics", {})
    dur = float(m.get("duration") or tl.get("duration") or 0)
    words = edl.get("words") or []
    scenes = tl.get("scenes") or []
    checks = []

    def add(key, label, pts, mx, tip, value=""):
        checks.append({"key": key, "label": label, "points": int(round(pts)), "max": mx, "ok": pts >= mx, "value": value,
                       "tip": "" if pts >= mx else tip})

    # 1. Hook speed: the first word, the first second decides the swipe
    first = float(words[0]["start"]) if words else 99.0
    add("hook_speed", "You start talking straight away", _band(first, [(0.5, 20), (1.0, 15), (2.0, 8)]), 20,
        f"Your first word comes at {first:.1f} s. Start speaking in the first half second (cut the silence or the breath before it).",
        f"first word at {first:.1f} s")

    # 2. Hook title on screen from the first frame
    hook = next((s for s in scenes if s.get("block") == "hook_two_tone"), None)
    ok_hook = bool(hook and float(hook.get("t_in", 1)) <= 0.05 and (hook.get("values") or {}).get("line1"))
    add("hook_title", "A title is on screen from the first frame", 10 if ok_hook else 0, 10,
        "Add a short title in the first frame: people decide with the sound off.", (hook or {}).get("values", {}).get("line1", ""))

    # 3. Length: 40-60 s keeps most people to the end
    try:                                              # a length chosen in the creative brief counts as the target
        import sys as _s
        _s.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from lib import creative_brief as _cb
        _b = _cb.load(job)
        _lo, _hi = _cb.length_range(_b, (0, 0)) if _b.get("length") else (0, 0)
    except Exception:                                 # noqa: BLE001
        _lo = _hi = 0
    if _hi and dur >= 15:
        add("length", "Good length", 15 if _lo - 2 <= dur <= _hi + 2 else 8, 15,
            f"You asked for {_lo}-{_hi} s in the brief: this reel is {dur:.0f} s.", f"{dur:.0f} s (asked {_lo}-{_hi})")
    else:
        add("length", "Good length", _band(dur, [(39.9, 10), (60, 15), (75, 11), (90, 7)]) if dur >= 15 else 3, 15,
            "Shorter keeps more people to the end: aim for 40-60 s (cut the weakest example or the long intro)." if dur > 60 else
            "Very short reels can feel unfinished: 40-60 s is the sweet spot.", f"{dur:.0f} s")

    # 4. Rhythm: something changes on screen every few seconds
    try:
        cuts = director.face_cuts(tl, edl.get("segments") or [])
        still, a, b = director.longest_still(tl, cuts)
    except Exception:                       # noqa: BLE001 - a plan we can't read gives no rhythm points, never a crash
        still, a, b = 99.0, 0, 0
    add("rhythm", "Something changes on screen every few seconds", _band(still, [(2.6, 15), (3.6, 10), (5.0, 5)]), 15,
        f"Nothing changes from {a:.1f} s to {b:.1f} s ({still:.1f} s). Ask for a zoom or a card there (\"zoom at …\").",
        f"longest still {still:.1f} s")

    # 5. Key words highlighted in the captions
    kw = len(tl.get("keyword_ids") or [])
    want = max(1, int(dur / 4))
    add("keywords", "Key words stand out in the captions", 5 if kw >= want else (3 if kw >= want / 2 else 0), 5,
        "Highlight more key words (about one every 3-4 seconds), e.g. \"make the important words green\".", f"{kw} highlighted")

    # 6. Captions match every spoken word
    cw, sw = m.get("caption_words"), m.get("spoken_words_shown")
    cap_ok = cw is not None and cw == sw
    add("captions", "Captions show every word you say", 10 if cap_ok else (0 if cw is not None else 5), 10,
        "Some words are missing from the captions: send \"check the captions\" as a change." if cw is not None else
        "Captions not checked yet.", f"{cw}/{sw} words" if cw is not None else "")

    # 7. Sound level
    lufs, peak = m.get("lufs"), m.get("true_peak")
    if lufs is None:
        snd, val = 0, "no sound measured"
    else:
        target = cfg.PROJECT.get("sound", {}).get("lufs", -14)
        snd = 10 if abs(lufs - target) <= 1.5 else (6 if abs(lufs - target) <= 3 else 2)
        if peak is not None and peak > -0.5:
            snd = min(snd, 6)
        val = f"{lufs:.1f} LUFS"
    add("sound", "Voice is loud and clear", snd, 10, "The voice level is off: re-record closer to the phone or in a quieter room.", val)

    # 8. Clean picture: no black or frozen frames
    bad = len(m.get("black") or []) + len(m.get("frozen") or [])
    add("clean", "No black or frozen picture", 5 if bad == 0 else 0, 5, "There is a black or frozen moment: send \"remove the frozen part\".",
        "clean" if bad == 0 else f"{bad} problem(s)")

    # 9. Variety: at least one card/flash plus zooms
    moments = sum(1 for s in scenes if s.get("block") in CONTENT)
    zooms = len(tl.get("punch_ins") or [])
    var = (3 if moments >= 1 else 0) + (2 if zooms >= max(1, int(dur / 10)) else 0)
    add("variety", "Cards and zooms keep it moving", var, 5, "Add a card on your main point and a few zooms on strong words.",
        f"{moments} card{'s' if moments != 1 else ''}, {zooms} zoom{'s' if zooms != 1 else ''}")

    # 10. Cover ready
    has_cover = os.path.exists(os.path.join(job, "review", "cover.jpg"))
    if final:
        add("cover", "Cover image ready", 5 if has_cover else 0, 5, "No cover yet: click \"Back to automatic\" or upload your own.",
            "ready" if has_cover else "missing")
    else:                                   # drafts get their cover after Approve; no penalty
        add("cover", "Cover image ready", 5, 5, "", "ready" if has_cover else "made after you approve")

    total = sum(c["points"] for c in checks)
    grade = "ready" if total >= 85 else ("good" if total >= 70 else "fix")
    words_ = {"ready": "Ready to post", "good": "Good: a few tips below", "fix": "Fix the tips below before posting"}
    tips = [c for c in sorted(checks, key=lambda c: c["points"] - c["max"]) if c["tip"]][:3]
    out = {"score": total, "grade": grade, "verdict": words_[grade], "checks": checks, "top_tips": [c["tip"] for c in tips],
           "final": final, "note": "Checks what keeps people watching. Not a prediction of views."}
    with open(os.path.join(job, "ready_score.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    r = score(os.path.abspath(sys.argv[1]), final="--final" in sys.argv)
    if not r:
        sys.exit("no timeline/edl in this job yet")
    print(f"{r['score']}/100 · {r['verdict']}")
    for c in r["checks"]:
        print(f"  {'✓' if c['ok'] else '·'} {c['label']}: {c['points']}/{c['max']}  {c['value']}")
    for t in r["top_tips"]:
        print("  tip:", t)
