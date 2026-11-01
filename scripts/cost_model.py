#!/usr/bin/env python3
"""Reel Factory per-reel operating cost. Prices: provider /v1/models catalog 2026-11-01 (USD per token).
Token counts for images are MEASURED (Sonnet 5.5, frame 1080x1920 source, 2026-11-01); Director/output sizes are ESTIMATES."""
P = {  # input, output, cache_read  ($/MTok)
 "opus5":   (5.0, 25.0, 0.5),
 "sonnet55":(2.0, 10.0, 0.1),
 "haiku55": (0.1,  0.5, 0.01),
}
IMG_TOK = {1080: 2728, 720: 1233, 540: 737, 384: 387}   # measured input tokens per frame at that width
def c(m, tin=0, tout=0, tcache=0):
    i, o, r = P[m]; return (tin*i + tout*o + tcache*r) / 1e6
def frame(width, out_tok): return c("sonnet55", IMG_TOK[width] + 60, out_tok)   # +60 prompt tokens

SCEN = {  # name: dict
 "lean":     dict(shot_frames=12, shot_w=540, shot_out=120, dir_in=12000, dir_cached=0, dir_out=2000, dir_think=2000, passes=1, qa_frames=8, qa_w=720, qa_out=120),
 "expected": dict(shot_frames=30, shot_w=540, shot_out=150, dir_in=20000, dir_cached=0, dir_out=3000, dir_think=5000, passes=3, qa_frames=8, qa_w=720, qa_out=200),
 "heavy":    dict(shot_frames=60, shot_w=720, shot_out=300, dir_in=40000, dir_cached=0, dir_out=4000, dir_think=12000, passes=3, qa_frames=8, qa_w=1080, qa_out=300),
}
def reel(s):
    asr = 0.0
    fix = c("haiku55", 2000, 1200)
    shot = s["shot_frames"] * frame(s["shot_w"], s["shot_out"])
    # pass 1 full prompt; revisions re-read the stable prefix (~70%) from cache
    d1 = c("opus5", s["dir_in"], s["dir_out"] + s["dir_think"])
    rev = c("opus5", s["dir_in"]*0.3, s["dir_out"] + s["dir_think"], s["dir_in"]*0.7)
    director = d1 + (s["passes"]-1) * rev
    qa = s["passes"] * s["qa_frames"] * frame(s["qa_w"], s["qa_out"])
    return dict(asr=asr, transcript_fix=fix, shot_log=shot, director=director, qa=qa, render=0.0), None
if __name__ == "__main__":
    # reproduce the $11.16 figure
    per_1080 = frame(1080, 76)
    print(f"1080-wide frame call: ${per_1080:.4f}; x1800 frames (60 s @30 fps) = ${1800*per_1080:.2f}  (Hesham's shown figure: $11.16)")
    print(f"frames implied by $11.16 at that price: {11.16/per_1080:.0f}")
    for n, s in SCEN.items():
        parts, _ = reel(s); t = sum(parts.values())
        print(f"\n{n}: total ${t:.3f}/reel | 12 reels ${12*t:.2f} | 24 reels ${24*t:.2f}")
        for k, v in parts.items(): print(f"   {k:15s} ${v:.4f}")
