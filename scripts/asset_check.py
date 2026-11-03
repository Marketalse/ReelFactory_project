#!/usr/bin/env python3
"""python3 scripts/asset_check.py <file-or-folder>   e.g.  python3 scripts/asset_check.py library/assets
Tests each icon/picture against the safe zone and writes <name>.placement.json (where it may sit, where it may not)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
from lib import asset_check as ac

if __name__ == "__main__":
    if len(sys.argv) < 2: sys.exit(__doc__)
    for r in ac.run(sys.argv[1]):
        print(("PASS  " if r["ok"] else "FAIL  ") + r["asset"])
        for p in r["problems"]: print("      - " + p)
        for z in r.get("may_sit", []):
            print("      " + (f"may sit in '{z['zone']}': up to {z['max_w']}x{z['max_h']} px" if z["ok"] else f"NOT in '{z['zone']}': {z['why']}"))
