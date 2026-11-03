#!/usr/bin/env python3
"""Build the ASSET PACK (the big icon library + its Arabic tags + the licences) as ONE zip other people can install. Free, offline.

  python3 scripts/make_asset_pack.py "<folder with the original icon sets>"  [--out ~/Desktop/reelfactory-assets.zip]

Reads what scripts/asset_batch.py already made in library/assets/ (ok/ icons, _reports/*/report.csv = which set each icon came from) and
library/assets/icon_index.json (the Arabic tags from reel.py --tag-icons). The zip contains:
  icons/<file>.svg   only icons from sets that have a LICENSE file next to them (a set without one is LEFT OUT and listed in EXCLUDED.txt)
  LICENSES/<set>.txt  each set's own licence text, copied unchanged (the licences ask you to keep it with the icons)
  icon_index.json     the Arabic tags;   MANIFEST.json  file -> set + sha256;   README.txt
"""
import argparse, csv, glob, hashlib, json, os, sys, zipfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def provenance(assets_dir):
    """{saved_as: set name} from every asset_batch report (the first folder of the original path is the set)."""
    out = {}
    for rep in sorted(glob.glob(os.path.join(assets_dir, "_reports", "*", "report.csv"))):
        for r in csv.DictReader(open(rep, encoding="utf-8")):
            if r.get("result") == "PASS" and r.get("saved_as"):
                parts = r["file"].replace("\\", "/").split("/")
                out[r["saved_as"]] = parts[0] if len(parts) > 1 else "(loose)"
    return out


def licences(src):
    """{set: licence file path} for each top-level folder of the original library that has a LICENSE/COPYING file."""
    out = {}
    for d in sorted(os.listdir(src)):
        p = os.path.join(src, d)
        if not os.path.isdir(p): continue
        for f in sorted(os.listdir(p)):
            if f.upper().startswith(("LICENSE", "LICENCE", "COPYING")) and os.path.isfile(os.path.join(p, f)):
                out[d] = os.path.join(p, f); break
    return out


def add_motion(z, assets_dir, motion_src):
    """Lottie files that PASSED the motion check (library/assets/motion/) go in motion/, with the pack's own licence text (from its index.json).
    A motion folder with no licence text in its index.json is LEFT OUT, the same rule as for icons."""
    try:
        lic = json.load(open(os.path.join(motion_src, "index.json"), encoding="utf-8")).get("license") or {}
    except (OSError, ValueError):
        lic = {}
    text = lic.get("license_text") if isinstance(lic, dict) else None
    mdir = os.path.join(assets_dir, "motion")
    if not text or not os.path.isdir(mdir): return {}
    name = "motion-" + "".join(c if c.isalnum() else "-" for c in str(lic.get("name", "licence")).lower()).strip("-")
    z.writestr(f"LICENSES/{name}.txt", text)
    out = {}
    for f in sorted(os.listdir(mdir)):
        if f.endswith(".json") and not f.endswith(".placement.json"):
            data = open(os.path.join(mdir, f), "rb").read()
            z.writestr("motion/" + f, data); out[f] = {"licence": name, "sha256": hashlib.sha256(data).hexdigest()}
    return out


def build(src, assets_dir, out_zip, motion_src=None):
    ok = os.path.join(assets_dir, "ok")
    prov, lic = provenance(assets_dir), licences(src)
    files = sorted(f for f in os.listdir(ok) if f.lower().endswith(".svg"))
    manifest, excluded = {}, {}
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            s = prov.get(f)
            if s not in lic:
                excluded.setdefault(s or "(unknown set)", 0); excluded[s or "(unknown set)"] += 1; continue
            data = open(os.path.join(ok, f), "rb").read()
            z.writestr("icons/" + f, data)
            manifest[f] = {"set": s, "sha256": hashlib.sha256(data).hexdigest()}
        for s in sorted({m["set"] for m in manifest.values()}):
            z.write(lic[s], f"LICENSES/{s}.txt")
        for rd in ("README.md", "README.txt", "README"):                                   # the collection's own readme (credits) travels with the licences
            if os.path.isfile(os.path.join(src, rd)): z.write(os.path.join(src, rd), "LICENSES/_collection_" + rd); break
        idx = os.path.join(assets_dir, "icon_index.json")
        if os.path.exists(idx): z.write(idx, "icon_index.json")
        motion = add_motion(z, assets_dir, motion_src) if motion_src else {}
        mi = os.path.join(assets_dir, "motion_index.json")
        if motion and os.path.exists(mi): z.write(mi, "motion_index.json")                  # the Arabic tags of the motion files
        z.writestr("MANIFEST.json", json.dumps({"icons": manifest, "motion": motion, "sets": sorted({m["set"] for m in manifest.values()})}, ensure_ascii=False, indent=1))
        z.writestr("EXCLUDED.txt", "Icons left out because their set has no LICENSE file next to it:\n" + "".join(f"  {s}: {n} icons\n" for s, n in sorted(excluded.items())) if excluded else "Nothing left out.\n")
        z.writestr("README.txt", "Reel Factory asset pack: icons with their original licences (LICENSES/), Arabic tags (icon_index.json) and a checksum list (MANIFEST.json).\n"
                   "Install: python3 scripts/install_assets.py <this zip or its web address>. Keep the LICENSES folder with the icons if you share them.\n")
    return len(manifest), excluded


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="the folder with the original icon sets (the one that holds the LICENSE files)")
    ap.add_argument("--out", default=os.path.expanduser("~/Desktop/reelfactory-assets.zip"))
    ap.add_argument("--motion", default=None, help="the folder of the motion pack (has index.json with the licence text); adds the checked Lottie files")
    ap.add_argument("--assets", default=os.path.join(ROOT, "library", "assets"))
    a = ap.parse_args()
    n, ex = build(os.path.expanduser(a.source), a.assets, os.path.expanduser(a.out), os.path.expanduser(a.motion) if a.motion else None)
    print(f"asset pack: {n} icons -> {a.out}")
    for s, c in sorted(ex.items()): print(f"  LEFT OUT (no licence file): {s}: {c} icons")
    print("Upload this zip as a release file on GitHub, then put its web address in config/project.json -> assets_pack.url")
