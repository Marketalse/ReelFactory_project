"""B-roll matching by what is IN the picture (T123). Vision AI, cost-gated, cached.

Each picture in library/broll/ is described ONCE by a vision model (a short description, tags in English and Arabic, and what kind of
picture it is). The description is stored in library/broll/ai_index.json next to a fingerprint of the file, so it is only paid for again
when the file changes. For every reel, ONE small text call then matches the reel's transcript against those descriptions and picks the
few library files that really fit what is said; those are copied into the reel's assets/ (the only place the director may take pictures
from) and listed in the director's brief. Nothing is invented: the AI only chooses from files you put in the library, and a file that
doesn't fit is not used. SVG logos are matched by file name only (a vision model cannot read SVG). Costs are tiny (cents) and every call
goes through the normal money guard in scripts/reel.py.
"""
import base64, hashlib, json, os, re, subprocess

from . import broll

PIC_EXT = (".png", ".jpg", ".jpeg", ".webp")
MAX_IMAGES_PER_CALL = 8
KINDS = ("screenshot", "logo", "photo", "chart", "document", "other")


def index_path(root=None):
    return os.path.join(broll.lib_dir(root), "ai_index.json")


def _load(root=None):
    try:
        with open(index_path(root), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) and isinstance(d.get("items"), dict) else {"version": 1, "items": {}}
    except (OSError, ValueError):
        return {"version": 1, "items": {}}


def fingerprint(path):
    h = hashlib.sha256()
    h.update(str(os.path.getsize(path)).encode())
    with open(path, "rb") as f:
        h.update(f.read(1 << 20))
    return h.hexdigest()[:16]


def pending(root=None, limit=MAX_IMAGES_PER_CALL):
    """Library pictures that still need a description (new or changed files), at most `limit`."""
    d, items = broll.lib_dir(root), _load(root)["items"]
    out = []
    for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if f.lower().endswith(PIC_EXT) and not f.startswith("."):
            fp = fingerprint(os.path.join(d, f))
            if items.get(f, {}).get("sha") != fp:
                out.append(f)
    return out[:limit]


def thumb_b64(path, width=512):
    """A small JPEG of the picture for the vision model (smaller = cheaper), as base64. None if it can't be read."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vf", f"scale='min({width},iw)':-2", "-frames:v", "1", "-q:v", "4", "-f", "image2pipe", "-vcodec", "mjpeg", "-"],
                       capture_output=True)
    return base64.b64encode(r.stdout).decode() if r.returncode == 0 and r.stdout else None


DESCRIBE_PROMPT = """You describe pictures for a video editor's B-roll library (an Iraqi marketing creator makes reels about business, online stores, ads, customer service).
Below are {n} pictures, each preceded by its file name. For EACH picture return an object. Return ONLY a JSON array, same order:
{{"file":"<file name>","desc":"<=25 words English: what is visible and what topic it could illustrate","tags":["3-8 short tags: English and Arabic words someone might SAY when this picture fits"],"kind":"screenshot|logo|photo|chart|document|other"}}
Describe only what you see. Do not guess brands you cannot read."""


def describe_content(root, files):
    """The vision request: [{"type": "text"...}, ...]. Pictures that cannot be read are left out (returned list of files actually sent)."""
    sent, content = [], [{"type": "text", "text": ""}]
    for f in files:
        b = thumb_b64(os.path.join(broll.lib_dir(root), f))
        if not b:
            continue
        content.append({"type": "text", "text": "file: " + f})
        content.append({"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b}})
        sent.append(f)
    content[0]["text"] = DESCRIBE_PROMPT.format(n=len(sent))
    return content, sent


def clean_descriptions(rows, sent):
    """Keep only valid rows for files we really sent; short plain text, a known kind."""
    out = {}
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict) or r.get("file") not in sent:
            continue
        desc = re.sub(r"\s+", " ", str(r.get("desc") or "")).strip()[:200]
        tags = [re.sub(r"\s+", " ", str(t)).strip()[:30] for t in (r.get("tags") or []) if str(t).strip()][:8]
        if desc:
            out[r["file"]] = {"desc": desc, "tags": tags, "kind": r.get("kind") if r.get("kind") in KINDS else "other"}
    return out


def save(root, new):
    d = _load(root)
    for f, row in new.items():
        d["items"][f] = dict(row, sha=fingerprint(os.path.join(broll.lib_dir(root), f)))
    os.makedirs(broll.lib_dir(root), exist_ok=True)
    tmp = index_path(root) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, index_path(root))


def catalog(root=None):
    """[{file, desc, tags, kind}] for every described picture that still exists in the library."""
    d, items = broll.lib_dir(root), _load(root)["items"]
    return [dict(file=f, **{k: v[k] for k in ("desc", "tags", "kind")}) for f, v in sorted(items.items()) if os.path.exists(os.path.join(d, f))]


PICK_PROMPT = """You choose B-roll pictures for ONE reel. The speaker talks (Iraqi Arabic) about the topics in the transcript below.
LIBRARY (file: description [tags]):
{catalog}

TRANSCRIPT (time text):
{lines}

Pick at most {n} library files that clearly illustrate something he actually says. Skip a file if it does not clearly fit: picking nothing is fine.
Return ONLY JSON: {{"picks":[{{"file":"<exact file name from the library>","why":"<=15 words: what he says that it illustrates"}}]}}"""


def pick_prompt(lines, cat, n=6):
    cl = "\n".join(f"{c['file']}: {c['desc']} [{', '.join(c['tags'])}]" for c in cat)
    return PICK_PROMPT.format(catalog=cl, lines=lines[:6000], n=n)


def clean_picks(answer, cat, n=6):
    """The AI may only choose files that are in the library. -> [{file, why}]."""
    have = {c["file"] for c in cat}
    out, seen = [], set()
    for p in (answer or {}).get("picks", []) if isinstance(answer, dict) else []:
        f = p.get("file") if isinstance(p, dict) else None
        if f in have and f not in seen:
            seen.add(f); out.append({"file": f, "why": re.sub(r"\s+", " ", str(p.get("why") or "")).strip()[:120]})
    return out[:n]


def brief_note(picks, cat):
    desc = {c["file"]: c["desc"] for c in cat}
    if not picks:
        return ""
    return ("LIBRARY PICTURES matched to this reel by the picture editor (they are in assets/; use one as ui_card.image or logo_card when he talks about it): "
            + "; ".join(f"{p['file']} = {desc.get(p['file'], '')} (fits: {p['why']})" for p in picks))
