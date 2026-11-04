#!/usr/bin/env python3
"""Choose the reel structure (layout) used for new reels. Free.
    python3 scripts/set_layout.py            show the available layouts and the current one
    python3 scripts/set_layout.py stage      use the 'stage' layout (animation on top, caption band, you as a cut-out at the bottom)
    python3 scripts/set_layout.py panel      use the Format Pack frame (you in the middle, step panel at the bottom)
Only the setting format_pack.layout in config/project.json changes. Reels already made keep their look until you make them again."""
import json, os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from lib import layouts   # noqa: E402

p = os.path.join(ROOT, "config", "project.json")
txt = open(p, encoding="utf-8").read(); cur = json.loads(txt)["format_pack"].get("layout", "panel")
have = ["panel"] + layouts.names()
if len(sys.argv) < 2:
    print("current:", cur)
    for n in have: print(" -", n, "(Format Pack frame)" if n == "panel" else "(" + layouts.load(n)["label"] + ")")
    sys.exit(0)
new = sys.argv[1]
if new not in have: sys.exit(f"unknown layout {new!r}; choose one of: {', '.join(have)}")
if new != "panel":
    probs = layouts.problems(layouts.load(new))
    if probs: sys.exit("this layout breaks the safe zone: " + "; ".join(probs))
out, n = re.subn(r'("format_pack":\s*\{\s*"layout":\s*")[^"]*(")', rf'\g<1>{new}\g<2>', txt, count=1)
if n != 1: sys.exit("could not find format_pack.layout in config/project.json")
open(p, "w", encoding="utf-8").write(out); print(f"layout is now: {new} (was {cur})")
