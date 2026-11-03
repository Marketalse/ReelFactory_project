#!/usr/bin/env python3
"""LEARN FROM A REFERENCE VIDEO (T135). Free, offline, no AI (paid AI calls only happen inside scripts/reel.py).
  python3 scripts/ref_learn.py ~/Downloads/reference.mp4 [--name explainer-a] [--apply]
It measures a video you like and writes library/formats/<name>.json plus a contact sheet you can look at:
  structure : length, size, frame rate, loudness, number of picture changes per minute, pauses
  palette   : background, accent, surface and text colours (from the frames)
  layout    : which part of the 1080x1920 frame moves (the footage window) and which bands stay still (header, panel)
--apply  puts the palette into config/project.json as the Format Pack's 'custom' theme (format_pack.theme = custom).
Nothing is copied from the video except these numbers and colours."""
import argparse, json, os, re, subprocess, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W, H = 1080, 1920


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def probe(path):
    r = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path])
    d = json.loads(r.stdout or "{}"); v = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), {})
    num, den = (v.get("r_frame_rate") or "0/1").split("/")
    return {"duration_s": round(float(d.get("format", {}).get("duration", 0)), 2), "width": v.get("width"), "height": v.get("height"),
            "fps": round(float(num) / float(den), 2) if float(den) else None, "codec": v.get("codec_name"),
            "encoder": (d.get("format", {}).get("tags") or {}).get("encoder")}


def loudness(path):
    r = run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af", "ebur128=peak=true", "-f", "null", "-"])
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)
    return float(m[-1]) if m else None


def changes_and_pauses(path, dur):
    r = run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-vf", "select='gt(scene,0.25)',metadata=print:file=-", "-an", "-f", "null", "-"])
    cuts = len(re.findall(r"pts_time:", r.stdout + r.stderr))
    s = run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af", "silencedetect=noise=-38dB:d=0.4", "-f", "null", "-"])
    pauses = [float(x) for x in re.findall(r"silence_duration: ([\d.]+)", s.stderr)]
    return cuts, pauses


def frames(path, dur, n=12):
    """n frames evenly spread, scaled to 1080x1920 raw RGB -> list of PIL images (small, 270x480)."""
    from PIL import Image
    out = []
    for k in range(n):
        t = dur * (k + 0.5) / n
        r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", path, "-frames:v", "1", "-vf", "scale=270:480", "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True)
        if r.stdout:
            import io
            out.append(Image.open(io.BytesIO(r.stdout)).convert("RGB"))
    return out


def hexc(c): return "#%02X%02X%02X" % tuple(c)


def palette(imgs):
    """Most common colours over all frames (quantized), then roles: bg = most common, accent = most saturated frequent, surface = common colour next to bg in brightness, text = brightest frequent."""
    from PIL import Image
    big = Image.new("RGB", (len(imgs) * 90, 160))
    for i, im in enumerate(imgs): big.paste(im.resize((90, 160)), (i * 90, 0))
    q = big.quantize(colors=10, method=Image.Quantize.MEDIANCUT).convert("RGB")
    cnt = sorted(q.getcolors(), reverse=True)
    cols = [c for _, c in cnt]
    lum = lambda c: 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    sat = lambda c: (max(c) - min(c)) / (max(c) or 1)
    bg = cols[0]
    accent = max(cols[:8], key=lambda c: sat(c) * (1 if sum(abs(a - b) for a, b in zip(c, bg)) > 90 else 0.2))
    text = max(cols[:8], key=lum)
    rest = [c for c in cols[:8] if c not in (bg, accent, text)]
    surface = min(rest or [bg], key=lambda c: abs(lum(c) - lum(bg) - 12))
    on = bg if lum(accent) > 110 else text
    return {"bg": hexc(bg), "accent": hexc(accent), "surface": hexc(surface), "text": hexc(text), "on": hexc(on), "all": [hexc(c) for c in cols]}


def layout(imgs):
    """Rows/columns that change between frames = footage; still ones = frame furniture. -> window box (1080x1920 px) + still bands."""
    import statistics
    w, h = imgs[0].size
    px = [im.load() for im in imgs]
    var = [[0.0] * w for _ in range(h)]
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            vals = [sum(p[x, y]) / 3 for p in px]
            var[y][x] = statistics.pstdev(vals)
    moving = lambda y, x: var[y][x] > 12
    rows = [sum(moving(y, x) for x in range(0, w, 2)) / (w / 2) for y in range(0, h, 2)]
    ys = [i * 2 for i, r in enumerate(rows) if r > 0.35]
    if not ys: return {"window": None, "note": "no moving footage found"}
    y0, y1 = min(ys), max(ys)
    cols = [sum(moving(y, x) for y in range(y0, y1, 2)) / max(1, (y1 - y0) / 2) for x in range(0, w, 2)]
    xs = [i * 2 for i, c in enumerate(cols) if c > 0.35]
    x0, x1 = (min(xs), max(xs)) if xs else (0, w)
    k = W / w
    return {"window": {"x0": round(x0 * k), "y0": round(y0 * k), "x1": round(x1 * k), "y1": round(y1 * k)},
            "still_top_px": round(y0 * k), "still_bottom_px": round(H - y1 * k), "full_frame": (y1 - y0) > 0.9 * h and (x1 - x0) > 0.9 * w}


def contact(imgs, out):
    from PIL import Image
    cols = 6; rows = (len(imgs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * 270, rows * 480))
    for i, im in enumerate(imgs): sheet.paste(im, ((i % cols) * 270, (i // cols) * 480))
    sheet.save(out, quality=82)


def analyse(path, name):
    info = probe(path); dur = info["duration_s"]
    cuts, pauses = changes_and_pauses(path, dur)
    imgs = frames(path, dur)
    if not imgs: raise SystemExit("could not read frames from this video")
    spec = {"name": name, "source": os.path.basename(path), "video": info, "loudness_lufs": loudness(path),
            "picture_changes": cuts, "picture_changes_per_min": round(cuts / dur * 60, 1) if dur else None,
            "pauses": {"count": len(pauses), "avg_s": round(sum(pauses) / len(pauses), 2) if pauses else 0, "max_s": round(max(pauses), 2) if pauses else 0},
            "palette": palette(imgs), "layout": layout(imgs)}
    return spec, imgs


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video"); ap.add_argument("--name"); ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    name = re.sub(r"[^a-z0-9-]+", "-", (a.name or os.path.splitext(os.path.basename(a.video))[0]).lower()).strip("-") or "reference"
    spec, imgs = analyse(a.video, name)
    d = os.path.join(ROOT, "library", "formats"); os.makedirs(d, exist_ok=True)
    json.dump(spec, open(os.path.join(d, name + ".json"), "w"), indent=1, ensure_ascii=False)
    contact(imgs, os.path.join(d, name + "_frames.jpg"))
    p, L, pa = spec["palette"], spec["layout"], spec["pauses"]
    print(f"Learned '{name}' from {os.path.basename(a.video)}  ->  library/formats/{name}.json  (+ {name}_frames.jpg to look at)")
    print(f"  {spec['video']['width']}x{spec['video']['height']}, {spec['video']['duration_s']} s, {spec['video']['fps']} fps, loudness {spec['loudness_lufs']} LUFS")
    print(f"  picture changes: {spec['picture_changes']} ({spec['picture_changes_per_min']} per minute); pauses: {pa['count']} (avg {pa['avg_s']} s, longest {pa['max_s']} s)")
    print(f"  colours: background {p['bg']}  accent {p['accent']}  surface {p['surface']}  text {p['text']}")
    print("  layout: " + (f"footage window x {L['window']['x0']}-{L['window']['x1']}, y {L['window']['y0']}-{L['window']['y1']} (still {L['still_top_px']} px at the top, {L['still_bottom_px']} px at the bottom)" if L.get("window") and not L.get("full_frame") else "the footage fills the whole frame"))
    if a.apply:
        cp = os.path.join(ROOT, "config", "project.json"); c = json.load(open(cp, encoding="utf-8"))
        c.setdefault("format_pack", {}).update({"theme": "custom", "colors": {k: p[k] for k in ("bg", "accent", "surface", "text", "on")}, "learned_from": name})
        json.dump(c, open(cp, "w"), indent=2, ensure_ascii=False)
        print("  applied: the Format Pack now uses these colours (format_pack.theme = custom). Undo: set format_pack.theme back to dark or violet.")


if __name__ == "__main__":
    main()
