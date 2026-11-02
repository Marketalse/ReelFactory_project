#!/usr/bin/env python3
"""Makes Reel Factory's own sound effects with ffmpeg (tones and noise it generates itself).
No download, no licence to buy, nothing copied from anyone: they belong to the project and are free to use anywhere.

    python3 scripts/make_sfx.py            # writes style/sfx/*.wav and style/sfx/catalog.json
    python3 scripts/make_sfx.py <folder>   # same, into another folder (used by tests)

Audio files are not kept in git (see .gitignore); this script and catalog.json are, so they can always be rebuilt."""
import json, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = "made by scripts/make_sfx.py from ffmpeg tone/noise generators; own work, free to use in any video"

SOUNDS = {
    "whoosh": ("A layout change: a card slides in or out", 0.50,
               "anoisesrc=d=0.5:c=pink:a=0.6,highpass=f=250,lowpass=f=5000,afade=t=in:d=0.18,afade=t=out:st=0.22:d=0.28"),
    "pop":    ("A key word lands (max 1 per 3 s)", 0.10,
               "sine=f=760:d=0.10,afade=t=out:st=0.01:d=0.09,volume=0.9"),
    "ding":   ("A spoken number appears", 0.70,
               "sine=f=1320:d=0.7,afade=t=out:st=0.02:d=0.68,volume=0.6"),
    "click":  ("A small tap on a title or tag", 0.04,
               "anoisesrc=d=0.04:c=white:a=0.5,highpass=f=1800,afade=t=out:st=0.005:d=0.035"),
    "rise":   ("Build-up before a payoff", 0.80,
               "sine=f=300:d=0.8,aeval='val(0)*sin(2*PI*t*(300+900*t))':c=mono,afade=t=in:d=0.4,afade=t=out:st=0.6:d=0.2,volume=0.7"),
}


def make(folder=None):
    folder = folder or os.path.join(ROOT, "style", "sfx")
    os.makedirs(folder, exist_ok=True)
    cat = []
    for name, (use, dur, graph) in SOUNDS.items():
        out = os.path.join(folder, name + ".wav")
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", graph,
                            "-ar", "48000", "-ac", "2", out], capture_output=True, text=True)
        if r.returncode:
            raise SystemExit(f"could not make {name}: {r.stderr.strip()[-300:]}")
        cat.append({"name": name, "file": name + ".wav", "use": use, "seconds": dur, "source": SRC})
    with open(os.path.join(folder, "catalog.json"), "w", encoding="utf-8") as f:
        json.dump({"licence": "Own work made by the project's script. No third-party sound, nothing to credit or pay.", "sounds": cat}, f,
                  ensure_ascii=False, indent=1)
    return cat


if __name__ == "__main__":
    c = make(sys.argv[1] if len(sys.argv) > 1 else None)
    print("made:", ", ".join(x["name"] for x in c))
