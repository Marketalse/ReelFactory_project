"""AI tagging of the big icon library (T149). The 20,000+ icons in library/assets/ok/ (checked by scripts/asset_batch.py) have English file names;
a reel is spoken in Arabic, so ONE cheap pass (Haiku, through the money guard in scripts/reel.py --tag-icons) writes Arabic words a person might SAY
next to each distinct icon name. After that the Format Pack finds icons by what he says. Everything else here is free and local.
Index file: library/assets/icon_index.json  {"concepts": {name: [arabic tags]}, "files": {file: name}}."""
import json, os, re

from . import broll, config as cfg

STYLE = {"fill", "filled", "outline", "outlined", "solid", "line", "lines", "thin", "bold", "light", "regular", "duotone", "stroke", "small", "large", "icon", "icons",
         "rounded", "sharp", "round", "square", "two", "tone", "alt", "new", "old", "v1", "v2", "sm", "md", "lg", "xs", "xl"}
BATCH = 220


def ok_dir(root=None): return os.path.join(root or cfg.ROOT, "library", "assets", "ok")
def index_path(root=None): return os.path.join(root or cfg.ROOT, "library", "assets", "icon_index.json")


def concept(filename):
    """'Truck-Delivery_fill-24.svg' -> 'delivery truck' style key: lowercase words, no digits, no style words, sorted-stable."""
    stem = os.path.splitext(os.path.basename(filename))[0].lower()
    words = [w for w in re.split(r"[^a-z]+", re.sub(r"(?<=[a-z])(?=\d)|(?<=\d)(?=[a-z])", " ", stem)) if len(w) >= 2 and w not in STYLE]
    return " ".join(words)


def scan(root=None):
    """{concept: [files]} for every svg in the checked library."""
    out = {}
    d = ok_dir(root)
    for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if f.lower().endswith(".svg"):
            c = concept(f)
            if c: out.setdefault(c, []).append(f)
    return out


def load(root=None):
    try:
        return json.load(open(index_path(root), encoding="utf-8"))
    except (OSError, ValueError):
        return {"concepts": {}, "files": {}}


def pending(root=None, limit=0):
    """Concepts that still need tags (new library files), at most `limit` (0 = all)."""
    have = load(root)["concepts"]
    todo = [c for c in scan(root) if c not in have]
    return todo[:limit] if limit else todo


def estimate(n):
    """USD for tagging n concepts with the word_fix-class model (about 14 tokens in and 30 out per name, plus the prompt per batch)."""
    pin, pout = cfg.price(cfg.role("icon_tags")[0])
    batches = -(-n // BATCH)
    return round((n * 14 + batches * 450) * pin / 1e6 + (n * 30) * pout / 1e6, 3)


PROMPT = """You tag icons for an Iraqi marketing creator's video editor. His reels are spoken in Iraqi Arabic about business, online stores, ads, delivery, customer service, money and social media.
Below are icon NAMES (English). For each name give up to 4 Arabic words or short phrases (1-2 words each) that he might actually SAY when this icon would illustrate it
(everyday Iraqi/Arabic words, no diacritics). Give an empty list [] for names that are only abstract UI shapes (arrows, chevrons, bars, dots) or brand logos.
Return ONLY JSON: {{"<name exactly as given>": ["كلمة", "كلمة"], ...}}  -- one entry per name, same spelling.
NAMES:
{names}"""


def clean(ans, sent):
    """Validate an answer: only names we sent, up to 4 tags of 3-24 characters each."""
    out = {}
    if not isinstance(ans, dict): return out
    for k, v in ans.items():
        if k not in sent or not isinstance(v, list): continue
        tags, seen = [], set()
        for t in v:
            t = re.sub(r"\s+", " ", str(t)).strip(" ،,.!؟?")
            if 3 <= len(t) <= 24 and t not in seen:
                seen.add(t); tags.append(t)
        out[k] = tags[:4]
    return out


def save(new, root=None):
    d = load(root)
    files = scan(root)
    d["concepts"].update(new)
    d["files"] = {f: c for c, fs in files.items() for f in fs if c in d["concepts"]}
    os.makedirs(os.path.dirname(index_path(root)), exist_ok=True)
    tmp = index_path(root) + ".tmp"
    json.dump(d, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
    os.replace(tmp, index_path(root))
    return d


_CACHE = {}


def _inverted(root=None):
    p = index_path(root)
    m = os.path.getmtime(p) if os.path.exists(p) else 0
    if _CACHE.get("k") != (p, m):
        inv, d = {}, load(root)
        by_concept = {}
        for f, c in d["files"].items(): by_concept.setdefault(c, []).append(f)
        for c, tags in d["concepts"].items():
            fs = sorted(by_concept.get(c, []), key=lambda f: (len(f), f))
            if not fs: continue
            for t in tags:
                inv.setdefault(broll._norm(t), []).append(fs[0])
        _CACHE.update(k=(p, m), inv=inv)
    return _CACHE["inv"]


def match(words, exclude=(), root=None):
    """The best big-library icon for the spoken words of one section: exact or attached-letter match on an Arabic tag. -> file or None. Fast (dictionary)."""
    inv = _inverted(root)
    best = None
    for w in words:
        sp = broll._norm(w.get("text"))
        for key, rank in ((sp, 0), (broll._strip(sp), 1)):
            for f in inv.get(key, []):
                if f not in exclude and (best is None or rank < best[0]):
                    best = (rank, f)
                    break
    return best[1] if best else None
