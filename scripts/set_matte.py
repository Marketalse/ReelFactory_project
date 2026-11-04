#!/usr/bin/env python3
"""Choose the cut-out engine for new reels. Free.
    python3 scripts/set_matte.py            show the choices and the current one
    python3 scripts/set_matte.py hyperframes   the original (slow, safe)
    python3 scripts/set_matte.py rvm           Robust Video Matting (fast; needs scripts/setup_matte.py once)
    python3 scripts/set_matte.py mp_selfie     MediaPipe selfie (fastest, rougher edges)
    python3 scripts/set_matte.py auto          rvm when installed, else the original
If the chosen engine is not installed or fails, the original cut-out is used and the report says so."""
import json, os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import setup_matte   # noqa: E402

CHOICES = ["hyperframes", "rvm", "mp_selfie", "auto"]
p = os.path.join(ROOT, "config", "project.json"); txt = open(p, encoding="utf-8").read()
cur = json.loads(txt).get("matte", {}).get("engine", "hyperframes")
if len(sys.argv) < 2:
    print("current:", cur)
    for k, v in setup_matte.status().items(): print(f" - {k}: {'ready' if v else 'not installed (run: python3 scripts/setup_matte.py)'}")
    print(" - hyperframes: always available\n - auto: rvm when ready, else hyperframes"); sys.exit(0)
new = sys.argv[1]
if new not in CHOICES: sys.exit(f"unknown engine {new!r}; choose one of: {', '.join(CHOICES)}")
out, n = re.subn(r'("matte":\s*\{\s*"engine":\s*")[^"]*(")', rf'\g<1>{new}\g<2>', txt, count=1)
if n != 1: sys.exit("could not find matte.engine in config/project.json")
open(p, "w", encoding="utf-8").write(out); print(f"cut-out engine is now: {new} (was {cur})")
