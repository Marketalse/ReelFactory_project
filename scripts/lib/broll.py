"""B-roll library: your logos and screenshots in library/broll/, attached to a reel when you say their name.

Drop files in library/broll/ and name them after what they show: `instagram.svg`, `whatsapp.png`, `meta-ads.jpg`.
For Arabic names add library/broll/tags.json:  {"whatsapp.png": ["واتساب", "وتساب"]}.
When a reel's transcript contains one of a file's tags, the file is COPIED into that reel's assets/ folder (the only place
logos may come from). Nothing in the library is ever changed or deleted, and nothing is invented: no match = no file."""
import json, os, re, shutil

from . import config as cfg

EXT = (".svg", ".png", ".jpg", ".jpeg", ".webp")
MAX_ATTACH = 6


def _norm(s):
    return re.sub(r"[ً-ٰٟـ]", "", str(s or "")).lower().strip(" ،,.!?؟:;\"'()[]")


def lib_dir(root=None):
    return os.path.join(root or cfg.ROOT, "library", "broll")


def index(root=None):
    """[{file, tags}] for every image in the library."""
    d = lib_dir(root)
    if not os.path.isdir(d):
        return []
    try:
        extra = json.load(open(os.path.join(d, "tags.json"), encoding="utf-8"))
    except (OSError, ValueError):
        extra = {}
    out = []
    for f in sorted(os.listdir(d)):
        if not f.lower().endswith(EXT) or f.startswith("."):
            continue
        stem = os.path.splitext(f)[0]
        tags = {_norm(t) for t in re.split(r"[-_ ]+", stem)} | {_norm(stem)} | {_norm(t) for t in extra.get(f, [])}
        out.append({"file": f, "tags": sorted(t for t in tags if len(t) >= 3)})
    return out


def match(words, idx):
    """Library files whose tag he actually said. words: transcript words ({text})."""
    spoken = [_norm(w.get("text")) for w in words]
    hit = []
    for item in idx:
        if any(t == s or (len(t) >= 4 and t in s) for t in item["tags"] for s in spoken):
            hit.append(item["file"])
    return hit


def attach(job, words, root=None):
    """Copy the matching files into jobs/<job>/assets/. Returns the names attached (never overwrites an existing file)."""
    files = match(words, index(root))[:MAX_ATTACH]
    if not files:
        return []
    dst = os.path.join(job, "assets")
    os.makedirs(dst, exist_ok=True)
    done = []
    for f in files:
        if not os.path.exists(os.path.join(dst, f)):
            shutil.copy(os.path.join(lib_dir(root), f), os.path.join(dst, f))
        done.append(f)
    return done
