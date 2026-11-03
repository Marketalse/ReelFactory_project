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
        tags = {_norm(t) for t in re.split(r"[-_ ]+", stem) if t.lower() != "icon"} | {_norm(stem)} | {_norm(t) for t in extra.get(f, [])}
        out.append({"file": f, "tags": sorted(t for t in tags if len(t) >= 3)})
    return out


PREFIXES = ("وال", "بال", "كال", "فال", "لل", "ال", "و", "ب", "ل", "ف", "ك")


def _strip(s):
    """Arabic attached words: 'بالانستغرام' -> 'انستغرام' (and with the article: 'الانستغرام' -> 'انستغرام')."""
    for p in PREFIXES:
        if s.startswith(p) and len(s) - len(p) >= 4:
            return s[len(p):]
    return s


def _close(a, b):
    """One letter different (typo or a spelling variant), only for words of 5+ letters."""
    if len(a) < 5 or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) <= 1
    short, long_ = (a, b) if len(a) < len(b) else (b, a)
    return any(long_[:i] + long_[i + 1:] == short for i in range(len(long_)))


def _kind(tag, spoken):
    """How a spoken word matches a library tag: exact | contains | prefix (Arabic attached letters) | close (one letter off) | None."""
    if tag == spoken:
        return "exact"
    if len(tag) >= 4 and tag in spoken:
        return "contains"
    st = _strip(spoken)
    if st != spoken and (tag == st or _strip(tag) == st):
        return "prefix"
    if _strip(tag) == st and _strip(tag) != tag:
        return "prefix"
    if _close(tag, spoken) or _close(tag, st):
        return "close"
    return None


def suggest(words, idx):
    """Library files that fit what he said, with the first time they fit and how sure we are: [{file, t, word, kind}]."""
    out = []
    for item in idx:
        best = None
        for w in words:
            sp = _norm(w.get("text"))
            for t in item["tags"]:
                k = _kind(t, sp)
                if k and (best is None or ("exact contains prefix close".split().index(k) < "exact contains prefix close".split().index(best["kind"]))):
                    best = {"file": item["file"], "t": round(w.get("start", 0), 2), "word": w.get("text"), "kind": k}
        if best:
            out.append(best)
    return out


def match(words, idx):
    """Library files that fit what he said (exact name, attached Arabic letters, or one letter off). words: transcript words ({text})."""
    return [h["file"] for h in suggest(words, idx)]


def attach(job, words, root=None):
    """Copy the matching files into jobs/<job>/assets/. Returns the names attached (never overwrites an existing file)."""
    files = sorted(match(words, index(root)), key=lambda f: f.startswith("icon-"))[:MAX_ATTACH]        # his own logos first, bundled icons after
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
