"""Send fewer pictures to the vision AI (T61). Free, local, ffmpeg only.

A talking-head clip gives dozens of key frames that look almost the same, and every picture costs money. A frame is kept only if it
looks different from the last kept one (a small fingerprint of its brightness pattern), and a frame is ALWAYS kept at least every
MAX_GAP seconds and at least MIN_KEEP frames overall, so the shot log still covers the whole story. The first frame is always kept.
"""
import subprocess

BITS = 4            # fingerprint difference (of 64) at or below which two frames count as "the same"
MIN_KEEP = 8
MAX_GAP = 8.0


def image_hash(path):
    """64-bit difference hash of an image file, or None if it can't be read."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vf", "scale=9:8:flags=area,format=gray", "-f", "rawvideo", "-"], capture_output=True)
    d = r.stdout
    if r.returncode or len(d) != 72:
        return None
    h = 0
    for y in range(8):
        for x in range(8):
            h = (h << 1) | (1 if d[y * 9 + x] > d[y * 9 + x + 1] else 0)
    return h


def distinct(frames, root, hasher=image_hash, bits=BITS, min_keep=MIN_KEEP, max_gap=MAX_GAP):
    """frames: [{"t", "file"}] in time order. -> the frames worth paying for (a sublist, same order)."""
    if len(frames) <= min_keep:
        return list(frames)
    import os
    hs = [hasher(os.path.join(root, f["file"])) for f in frames]
    kept, last_h, last_t = [], None, None
    for f, h in zip(frames, hs):
        if not kept or h is None or last_h is None or bin(h ^ last_h).count("1") > bits or f["t"] - last_t >= max_gap:
            kept.append(f); last_h, last_t = h, f["t"]
    i = 0
    while len(kept) < min_keep and i < len(frames):         # never fewer than min_keep: add evenly spread frames
        if frames[i] not in kept:
            kept.append(frames[i])
        i += max(1, len(frames) // min_keep)
    return sorted(kept, key=lambda f: f["t"])
