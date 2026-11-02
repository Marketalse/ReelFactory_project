"""Quick re-render (T98), drafts only. Free, local.

A draft is made as whole-second PIECES of 6 s. The first render is one whole render with a keyframe every 2 s, cut into pieces
without re-encoding. After an edit, only the pieces whose content changed are rendered again (HyperFrames --start/--end);
the rest come from jobs/<job>/render_cache/. Pieces are joined picture-copy + exactly-trimmed sound, so nothing drifts.
Each piece has a fingerprint of everything that can change it: the clips and cards overlapping its time, their template files,
the captions shown in it, the footage and the render recipe. Anything not understood changes ALL fingerprints (= whole render),
so the cache can only cost time, never show an old picture. The final video is always a whole render. Nothing is deleted.
"""
import hashlib, json, os, re, subprocess

PIECE_S = 6
RATE = 48000
TAG = re.compile(r'<(?:div|video|audio)\b[^>]*\bclass="clip[^"]*"[^>]*>')
GROUP = re.compile(r'^\s*<div id="[a-z0-9_]+-g\d+" class="clip [a-z0-9_]+-g" data-start="([0-9.]+)" data-duration="([0-9.]+)".*$', re.M)


def _h(*parts):
    h = hashlib.sha256()
    for p in parts:
        h.update(p if isinstance(p, bytes) else str(p).encode("utf-8")); h.update(b"\x00")
    return h.hexdigest()[:20]


def _attr(tag, name):
    m = re.search(rf'\b{name}="([^"]*)"', tag)
    return m.group(1) if m else None


def grid(duration, size=PIECE_S):
    """[(a, b)] whole-second pieces; the last one ends at the reel's end (a tail under 1.5 s joins the piece before it)."""
    cuts = list(range(0, int(duration), size))
    if len(cuts) > 1 and duration - cuts[-1] < 1.5:
        cuts.pop()
    return [(a, (cuts[i + 1] if i + 1 < len(cuts) else duration)) for i, a in enumerate(cuts)]


def _file_print(path):
    try:
        st = os.stat(path)
        with open(path, "rb") as f:
            head = f.read(1 << 20); f.seek(max(0, st.st_size - (1 << 20))); tail = f.read(1 << 20)
        return _h(st.st_size, head, tail)
    except OSError:
        return "missing"


def piece_keys(project, pieces, recipe=""):
    """One fingerprint per piece. See the module note for what goes in."""
    index = open(os.path.join(project, "index.html"), encoding="utf-8").read()
    tags = []
    for m in TAG.finditer(index):
        t = m.group(0)
        try:
            a = float(_attr(t, "data-start") or 0); d = float(_attr(t, "data-duration") or 0)
        except ValueError:
            a, d = 0.0, 1e9
        tags.append((a, a + d, t))
    frame = _h(TAG.sub("", index), recipe)                               # everything around the clips: changes -> all pieces change
    assets = []
    for root, _, files in sorted(os.walk(os.path.join(project, "assets"))):
        for f in sorted(files):
            p = os.path.join(root, f)
            assets.append((os.path.relpath(p, project), _file_print(p)))
    assets_h = _h(json.dumps(assets))
    comp_cache = {}

    def comp(path):
        if path not in comp_cache:
            try:
                comp_cache[path] = open(os.path.join(project, path), encoding="utf-8").read()
            except OSError:
                comp_cache[path] = "missing:" + path
        return comp_cache[path]

    keys = []
    for a, b in pieces:
        parts = [frame, assets_h, a, b]
        for s, e, t in tags:
            if s < b and e > a:
                parts.append(t)
                src = _attr(t, "data-composition-src")
                if src:
                    text = comp(src)
                    groups = list(GROUP.finditer(text))
                    if groups:                                          # captions: only the groups shown in this piece
                        parts.append(GROUP.sub("", text))
                        parts += [g.group(0) for g in groups if float(g.group(1)) < b and float(g.group(1)) + float(g.group(2)) > a]
                    else:
                        parts.append(text)
        keys.append(_h(*parts))
    return keys


# ----------------------------------------------------------------------------- cache folder
def _idx(cache):
    try:
        return json.load(open(os.path.join(cache, "pieces.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def have(cache, keys):
    return [os.path.exists(os.path.join(cache, k + ".mp4")) and os.path.getsize(os.path.join(cache, k + ".mp4")) > 0 for k in keys]


def save_index(cache, pieces, keys, duration, recipe):
    os.makedirs(cache, exist_ok=True)
    tmp = os.path.join(cache, "pieces.json.tmp")
    with open(tmp, "w") as f:
        json.dump({"piece_s": PIECE_S, "duration": duration, "recipe": recipe, "pieces": [{"a": a, "b": b, "key": k} for (a, b), k in zip(pieces, keys)]}, f, indent=1)
    os.replace(tmp, os.path.join(cache, "pieces.json"))


def cut_pieces(full, pieces, keys, cache):
    """Seed the cache from a whole render that has a keyframe at every piece start: copy, no re-encode. -> list of problems."""
    os.makedirs(cache, exist_ok=True)
    bad = []
    for (a, b), k in zip(pieces, keys):
        out = os.path.join(cache, k + ".mp4")
        if os.path.exists(out) and os.path.getsize(out) > 0:
            continue
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(a), "-i", full, "-t", f"{b - a:.3f}", "-c", "copy", "-avoid_negative_ts", "make_zero", out],
                           capture_output=True, text=True)
        if r.returncode or not os.path.exists(out) or os.path.getsize(out) == 0:
            bad.append(f"could not cut piece {a}-{b}s: {(r.stderr or '').strip()[:80]}")
    return bad


def join(files, lengths, out):
    """Pieces -> one video: picture copied (frame exact), sound of each piece trimmed/padded to its exact length. -> error text or ''."""
    tmp_v = out + ".v.mp4"; tmp_a = out + ".a.m4a"; raw = out + ".h264"
    # picture: every piece is a copy that starts on a keyframe; join the raw H.264 and give it fresh, even 30 fps timestamps
    # (the mp4 'concat' route kept odd offsets from the cut pieces and produced a 70 s timeline for a 21 s reel)
    with open(raw, "wb") as w:
        for f in files:
            r = subprocess.run(["ffmpeg", "-v", "error", "-i", f, "-an", "-c:v", "copy", "-bsf:v", "h264_mp4toannexb", "-f", "h264", "-"], capture_output=True)
            if r.returncode or not r.stdout:
                return "reading a piece failed: " + (r.stderr or b"").decode("utf-8", "replace").strip()[:100]
            w.write(r.stdout)
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", "30", "-f", "h264", "-i", raw, "-c:v", "copy", tmp_v], capture_output=True, text=True)
    if r.returncode:
        return "joining the picture failed: " + (r.stderr or "").strip()[:120]
    want = round(sum(lengths) * 30)
    r = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", tmp_v],
                       capture_output=True, text=True)
    got = int(r.stdout.strip() or 0) if r.stdout.strip().isdigit() else 0
    if abs(got - want) > 1:                                          # never ship a draft with lost or doubled frames: caller makes a whole render
        return f"the joined picture has {got} frames, expected {want}"
    cmd = ["ffmpeg", "-v", "error", "-y"]
    for f in files:
        cmd += ["-i", f]
    parts = "".join(f"[{i}:a]aresample={RATE},atrim=end={L:.4f},asetpts=N/{RATE}/TB,apad=whole_dur={L:.4f}[a{i}];" for i, L in enumerate(lengths))
    cmd += ["-filter_complex", parts + "".join(f"[a{i}]" for i in range(len(files))) + f"concat=n={len(files)}:v=0:a=1[a]",
            "-map", "[a]", "-c:a", "aac", "-b:a", "192k", tmp_a]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        return "joining the sound failed: " + (r.stderr or "").strip()[:120]
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", tmp_v, "-i", tmp_a, "-map", "0:v", "-map", "1:a", "-c", "copy", "-movflags", "+faststart", out],
                       capture_output=True, text=True)
    for f in (tmp_v, tmp_a, raw):
        try:
            os.remove(f)                                              # temporary helper files made just now, not user data
        except OSError:
            pass
    return "joining failed: " + (r.stderr or "").strip()[:120] if r.returncode else ""
