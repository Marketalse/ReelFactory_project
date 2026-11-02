"""Manual editing from the dashboard's Edit page (text-based editing + timeline, like Premiere's transcript editing).

Hesham cuts or restores words, fixes spellings, moves / resizes / adds / removes cards and zooms, edits the title.
Everything is stored in SOURCE word numbers (src_i) so a cut never shifts a card onto the wrong word.
`preview()` recomputes the cut and the timeline without saving (the page calls it after every change);
`save()` checks the same rules as the AI plan, keeps a backup of the previous version, and writes:
  manual_edit.json (cuts/restores/spellings), edl.json, scene_plan.json, timeline.json.
Then `reel.py --rebuild` makes a new draft from them. No AI, no spend."""
import json, os, shutil, subprocess, time
from array import array

from . import config as cfg, director, edl as edlmod
from .hfbuild import REGISTRY

EDITABLE = list(director.DIRECTOR_BLOCKS)


def _j(p, default=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _w(p, data):
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


class EditError(Exception):
    pass


def _inputs(job):
    tr = _j(os.path.join(job, "transcript.json"))
    sel = _j(os.path.join(job, "chosen_select.json"))
    if not tr or not sel:
        raise EditError("this reel has no transcript or chosen story yet")
    return tr, sel["range"][0], sel["range"][1]


def logos(job):
    d = os.path.join(job, "assets")
    return sorted(f for f in os.listdir(d) if f.lower().endswith((".svg", ".png", ".jpg", ".jpeg", ".webp"))) if os.path.isdir(d) else []


def current(job):
    """The reel as it is now, in source word numbers (what the page edits)."""
    tr, s0, s1 = _inputs(job)
    e = _j(os.path.join(job, "edl.json")) or {}
    plan = _j(os.path.join(job, "scene_plan.json")) or {}
    man = _j(os.path.join(job, "manual_edit.json")) or {}
    ew = e.get("words") or []
    src = lambda k: ew[k]["src_i"] if isinstance(k, int) and 0 <= k < len(ew) else None
    moments = [{"block": m.get("block"), "at_src": src(m.get("at_word")), "duration": m.get("duration"), "values": m.get("values") or {}}
               for m in plan.get("moments") or [] if src(m.get("at_word")) is not None]
    return {"drop": man.get("drop", []), "keep": man.get("keep", []), "texts": man.get("texts", {}),
            "hook": plan.get("hook") or {}, "moments": moments,
            "punch_ins": [{"at_src": src(p.get("at_word")), "scale": p.get("scale", 1.25)} for p in plan.get("punch_ins") or []
                          if src(p.get("at_word")) is not None],
            "keyword_src": [src(k) for k in plan.get("keyword_ids") or [] if src(k) is not None]}


def compute(job, edit):
    """edit (source word numbers) -> (edl, plan, timeline, errors, warnings). Nothing is written."""
    tr, s0, s1 = _inputs(job)
    texts = {int(k): str(v).strip() for k, v in (edit.get("texts") or {}).items() if str(v).strip()}
    try:
        e = edlmod.build(tr, s0, s1, drop=[int(x) for x in edit.get("drop") or []], keep=[int(x) for x in edit.get("keep") or []],
                         texts=texts)
    except ValueError as ex:
        raise EditError(str(ex))
    kept = [w["src_i"] for w in e["words"]]
    pos = {s: k for k, s in enumerate(kept)}

    def idx(s):
        """A card on a word that was cut moves to the next word still in the reel."""
        if s is None:
            return None
        s = int(s)
        if s in pos:
            return pos[s]
        nxt = [k for k, x in enumerate(kept) if x > s]
        return nxt[0] if nxt else len(kept) - 1

    old = _j(os.path.join(job, "scene_plan.json")) or {}
    plan = {"hook": edit.get("hook") or old.get("hook") or {},
            "keyword_ids": sorted({idx(s) for s in edit.get("keyword_src") or [] if int(s) in pos}),
            "moments": [{"block": m.get("block"), "at_word": idx(m.get("at_src")), "duration": float(m.get("duration") or 0),
                         "values": dict(m.get("values") or {})} for m in edit.get("moments") or []],
            "punch_ins": [{"at_word": idx(p.get("at_src")), "scale": float(p.get("scale") or 1.25)} for p in edit.get("punch_ins") or []],
            "cta": old.get("cta") or {}, "cover": old.get("cover") or {}}
    tl, err, warn = director.resolve(plan, e["words"], e["duration"], logos=logos(job), relaxed=True)
    try:
        warn += director.check_rhythm(tl, director.face_cuts(tl, e["segments"]))
    except Exception as ex:                    # noqa: BLE001
        err.append(f"cut problem: {ex}")
    oldtl = _j(os.path.join(job, "timeline.json")) or {}
    tl["face_cy"] = oldtl.get("face_cy", 0.36)
    tl["director"] = "manual edit"; tl["feedback"] = "(manual edit in the editor)"
    return e, plan, tl, err, warn


def state(job, edit=None):
    """Everything the Edit page draws. With `edit`, shows that (unsaved) version instead of the saved one."""
    tr, s0, s1 = _inputs(job)
    edit = edit if edit is not None else current(job)
    e, plan, tl, err, warn = compute(job, edit)
    kept = {w["src_i"]: w for w in e["words"]}
    texts = {int(k): v for k, v in (edit.get("texts") or {}).items()}
    words = []
    for i, w in enumerate(tr):
        if w["start"] < s0 - 0.05 or w["end"] > s1 + 0.05:
            continue
        k = kept.get(i)
        words.append({"i": i, "text": texts.get(i, w["text"]), "src_start": w["start"], "src_end": w["end"], "kept": k is not None,
                      "t": k["start"] if k else None, "t_end": k["end"] if k else None,
                      "why": None if k else ("you cut it" if i in set(map(int, edit.get("drop") or [])) else
                                             ("filler" if edlmod._norm(w["text"]) in edlmod.FILLERS else "retake or pause"))})
    blocks = {b: {"label": REGISTRY["blocks"][b].get("label", b), "inputs": REGISTRY["blocks"][b]["inputs"],
                  "duration_s": REGISTRY["blocks"][b]["duration_s"]} for b in EDITABLE + ["hook_two_tone"]}
    return {"edit": edit, "words": words, "segments": e["segments"], "duration": e["duration"],
            "scenes": tl["scenes"], "punch_ins": tl["punch_ins"], "keyword_ids": tl["keyword_ids"],
            "errors": err, "warnings": warn, "blocks": blocks, "logos": logos(job), "source_range": [s0, s1],
            "saved_at": (_j(os.path.join(job, "manual_edit.json")) or {}).get("saved_at")}


def save(job, edit):
    """Check, back up the previous version, write. Returns (ok, message, errors)."""
    e, plan, tl, err, warn = compute(job, edit)
    if err:
        return False, "Not saved: fix the red items first.", err
    stamp = time.strftime("%Y%m%d-%H%M%S")
    bk = os.path.join(job, "edits", stamp)
    os.makedirs(bk, exist_ok=True)
    for f in ("edl.json", "scene_plan.json", "timeline.json", "manual_edit.json"):
        if os.path.exists(os.path.join(job, f)):
            shutil.copy2(os.path.join(job, f), os.path.join(bk, f))
    _w(os.path.join(job, "manual_edit.json"), {"drop": sorted({int(x) for x in edit.get("drop") or []}),
                                               "keep": sorted({int(x) for x in edit.get("keep") or []}),
                                               "texts": {str(k): v for k, v in (edit.get("texts") or {}).items() if str(v).strip()},
                                               "saved_at": time.strftime("%Y-%m-%d %H:%M")})
    _w(os.path.join(job, "edl.json"), e)
    _w(os.path.join(job, "scene_plan.json"), plan)
    _w(os.path.join(job, "timeline.json"), tl)
    return True, f"Saved ({len(warn)} tip{'s' if len(warn) != 1 else ''}). Previous version kept in edits/{stamp}.", warn


def waveform(job, per_s=20):
    """Loudness peaks of the source video (0-100, `per_s` per second), cached in waveform.json."""
    out = os.path.join(job, "waveform.json")
    src = os.path.join(job, "proxy.mp4")
    if os.path.exists(out) and os.path.exists(src) and os.path.getmtime(out) >= os.path.getmtime(src):
        return _j(out)
    if not os.path.exists(src):
        return {"per_s": per_s, "peaks": []}
    rate = per_s * 100
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", src, "-vn", "-ac", "1", "-ar", str(rate), "-f", "s16le", "-"],
                       capture_output=True, timeout=300)
    a = array("h"); a.frombytes(r.stdout[: len(r.stdout) // 2 * 2])
    peaks = [max((abs(x) for x in a[k:k + 100]), default=0) for k in range(0, len(a), 100)]
    top = max(peaks or [1]) or 1
    data = {"per_s": per_s, "peaks": [round(100 * p / top) for p in peaks]}
    _w(out, data)
    return data
