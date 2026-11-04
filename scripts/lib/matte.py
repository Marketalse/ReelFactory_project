"""Person cutout for "text behind the head" (T119). Local AI model, free (no API cost), cached.

HyperFrames ships an on-device person-segmentation model (`hyperframes remove-background`, u2net human segmentation). For every
text_behind moment we build the exact picture the face video shows during that moment (the EDL pieces, so jump cuts are right),
cut the person out of it (a transparent WebM) and the block puts that cutout ABOVE the big word and the face video BELOW it, so the
word appears behind the head. Drafts use half size (the draft is shown at 540 px anyway), finals full size. The cutout is cached by a
fingerprint of the footage + the exact pieces + size, so changing a caption or title never repeats the slow part.
If the model or ffmpeg fails, MatteError is raised and compile drops that one moment (the reel is never stopped for it).
Speed: roughly 2 frames per second on a plain CPU at full size (about 45 s for a 3 s moment); faster on a Mac with its neural engine.
"""
import hashlib, json, os, subprocess, sys

from . import config as cfg

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import setup_matte  # noqa: E402  (where the extra engines live: ~/.reelfactory/matte)

MODEL = "u2net_human_seg"


class MatteError(Exception):
    pass


def slices(segments, a, b):
    """The proxy time ranges that make up reel time a-b: [(src_in, src_out)], from the EDL segments."""
    out = []
    for s in segments:
        ta, tb = max(a, s["t_in"]), min(b, s["t_out"])
        if tb - ta > 1e-3:
            out.append((round(s["src_in"] + (ta - s["t_in"]), 3), round(s["src_in"] + (tb - s["t_in"]), 3)))
    return out


def _fingerprint(path):
    st = os.stat(path)
    h = hashlib.sha256(str(st.st_size).encode())
    with open(path, "rb") as f:
        h.update(f.read(1 << 20)); f.seek(max(0, st.st_size - (1 << 20))); h.update(f.read(1 << 20))
    return h.hexdigest()


def engine_name():
    """The engine to use now: config matte.engine (hyperframes | rvm | mp_selfie | auto). Anything not installed falls back to hyperframes."""
    want = cfg.PROJECT.get("matte", {}).get("engine", "hyperframes")
    ready = setup_matte.status()
    if want == "auto":
        return "rvm" if ready.get("rvm") else "hyperframes"
    return want if want in ready and ready[want] else "hyperframes"


def key(proxy, sl, width, engine="hyperframes"):
    parts = [_fingerprint(proxy), sl, width, MODEL] + ([] if engine == "hyperframes" else [engine])     # old caches stay valid
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()[:20]


def window_command(proxy, sl, width, out):
    """ffmpeg: join the slices of the proxy into one silent 30 fps video of `width` px (9:16)."""
    h = round(width * 16 / 9)
    parts = [f"[0:v]trim=start={a}:end={b},setpts=PTS-STARTPTS,fps=30,scale={width}:{h},format=yuv420p[v{n}]" for n, (a, b) in enumerate(sl)]
    parts.append("".join(f"[v{n}]" for n in range(len(sl))) + f"concat=n={len(sl)}:v=1:a=0[o]")
    return ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", proxy, "-filter_complex", ";".join(parts), "-map", "[o]",
            "-c:v", "libx264", "-crf", "14", "-preset", "veryfast", "-pix_fmt", "yuv420p", out]


def cutout(job, edl, a, b, final, say=print, runner=subprocess.run):
    """-> path of the transparent WebM for reel time a-b (cached in jobs/<job>/matte_cache/). Raises MatteError."""
    proxy = os.path.join(job, "proxy.mp4")
    if not os.path.exists(proxy):
        raise MatteError("proxy.mp4 is missing")
    sl = slices(edl["segments"], a, b)
    if not sl:
        raise MatteError("no footage in that time range")
    width = 1080 if final else 540
    cache = os.path.join(job, "matte_cache")
    os.makedirs(cache, exist_ok=True)
    eng = engine_name()
    k = key(proxy, sl, width, eng)
    out = os.path.join(cache, k + ".webm")
    if os.path.exists(out) and os.path.getsize(out) > 0:
        return out
    tmp = os.path.join(cache, k + ".window.mp4")
    r = runner(window_command(proxy, sl, width, tmp), capture_output=True, text=True)
    if r.returncode or not os.path.exists(tmp):
        raise MatteError("could not prepare the footage for the cutout: " + (r.stderr or "").strip()[-120:])
    if eng != "hyperframes":
        say(f"   cutting the person out with {eng} ({b - a:.1f} s, {width}px)…")
        r = runner([setup_matte.python(), os.path.join(os.path.dirname(setup_matte.__file__), "matte_worker.py"), eng, tmp, out + ".part.webm", (cfg.find_ffmpeg() or ("ffmpeg",))[0]],
                   capture_output=True, text=True, timeout=3600)
        if r.returncode == 0 and os.path.exists(out + ".part.webm") and os.path.getsize(out + ".part.webm") > 0:
            os.replace(out + ".part.webm", out)
            return out
        say(f"   {eng} failed ({((r.stderr or '').strip().splitlines() or ['no message'])[-1][:120]}); using the original cut-out instead")
    ver = cfg.PROJECT.get("tools", {}).get("hyperframes", "0.8.226")
    say(f"   text behind the head: cutting the person out of {b - a:.1f} s of footage ({width}px), this takes a while the first time…")
    r = runner(["npx", "--yes", f"hyperframes@{ver}", "remove-background", tmp, "-o", out + ".part.webm", "--quality", "balanced" if final else "fast"],
               capture_output=True, text=True, timeout=3600)
    if r.returncode or not os.path.exists(out + ".part.webm") or os.path.getsize(out + ".part.webm") == 0:
        raise MatteError("the person cutout failed: " + ((r.stderr or r.stdout or "").strip().splitlines() or ["no message"])[-1][:140])
    os.replace(out + ".part.webm", out)
    return out


def face_ok(shots, lo=0.28, hi=0.72):
    """The face must be in the middle of the frame for the effect (from the shot log). True when unknown (no shot log)."""
    xs = sorted(r["face"]["x"] + r["face"]["w"] / 2 for r in (shots or []) if r.get("face"))
    return True if not xs else lo <= xs[len(xs) // 2] <= hi
