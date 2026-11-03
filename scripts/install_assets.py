#!/usr/bin/env python3
"""Install the asset pack (big icon library + Arabic tags + licences) into this project. Free.
  python3 scripts/install_assets.py                    (downloads the address in config/project.json -> assets_pack.url)
  python3 scripts/install_assets.py <zip file or web address>
Checks every icon against the pack's checksum list, refuses unsafe paths, never overwrites an icon that differs from the pack, and
puts the licences in library/assets/LICENSES/. Safe to run again."""
import hashlib, json, os, shutil, sys, tempfile, urllib.request, zipfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def install(src, root=ROOT):
    tmp = None
    if src.startswith(("http://", "https://")):
        tmp = tempfile.mktemp(suffix=".zip"); print("downloading ...")
        urllib.request.urlretrieve(src, tmp); src = tmp
    try:
        try:
            z = zipfile.ZipFile(src)
        except zipfile.BadZipFile:
            sys.exit("This is not a zip file (wrong link, or the download failed). Use the link to reelfactory-assets.zip.")
        if "MANIFEST.json" not in z.namelist():
            sys.exit("This zip is not the Reel Factory asset pack (it has no MANIFEST.json). It looks like a plain folder of files. "
                     "Upload reelfactory-assets.zip (made by scripts/make_asset_pack.py) and use that link.")
        man = json.loads(z.read("MANIFEST.json"))["icons"]
        ok = os.path.join(root, "library", "assets", "ok"); lic = os.path.join(root, "library", "assets", "LICENSES")
        os.makedirs(ok, exist_ok=True); os.makedirs(lic, exist_ok=True)
        new = same = bad = clash = 0
        for name, info in man.items():
            if "/" in name or "\\" in name or name.startswith("."): bad += 1; continue          # unsafe name: skipped
            data = z.read("icons/" + name)
            if hashlib.sha256(data).hexdigest() != info["sha256"]: bad += 1; continue             # damaged: skipped
            p = os.path.join(ok, name)
            if os.path.exists(p):
                if open(p, "rb").read() == data: same += 1
                else: clash += 1                                                                  # his own different file: kept
                continue
            open(p, "wb").write(data); new += 1
        for n in z.namelist():
            if n.startswith("LICENSES/") and n.endswith(".txt") and ".." not in n:
                open(os.path.join(lic, os.path.basename(n)), "wb").write(z.read(n))
        if "icon_index.json" in z.namelist():
            ip = os.path.join(root, "library", "assets", "icon_index.json")
            if not os.path.exists(ip): open(ip, "wb").write(z.read("icon_index.json"))            # never replaces tags he made himself
        mnew = mbad = 0
        mot = os.path.join(root, "library", "assets", "motion"); mman = json.loads(z.read("MANIFEST.json")).get("motion", {})
        if mman:
            os.makedirs(mot, exist_ok=True)
            from lib import motion_check                                                          # the same safety check, run again on this computer
            for name, info in mman.items():
                if "/" in name or "\\" in name or name.startswith("."): mbad += 1; continue
                data = z.read("motion/" + name)
                p = os.path.join(mot, name)
                if hashlib.sha256(data).hexdigest() != info["sha256"]: mbad += 1; continue
                if not os.path.exists(p): open(p, "wb").write(data); mnew += 1
                rec = motion_check.check(p)
                if not rec["ok"]: os.remove(p); mbad += 1; mnew -= 1; continue                    # unsafe here: removed
                json.dump(rec, open(os.path.join(mot, os.path.splitext(name)[0] + ".placement.json"), "w"), indent=1, ensure_ascii=False)
            if "motion_index.json" in z.namelist():
                mp_ = os.path.join(root, "library", "assets", "motion_index.json")
                if not os.path.exists(mp_): open(mp_, "wb").write(z.read("motion_index.json"))      # never replaces tags he made himself
            print(f"motion: {mnew} new Lottie files, {len(mman) - mnew - mbad} already there, {mbad} skipped (damaged or unsafe).")
        print(f"installed: {new} new icons, {same} already there, {clash} kept (different from the pack), {bad} skipped (damaged or unsafe).")
        return new, same, clash, bad
    finally:
        if tmp and os.path.exists(tmp): os.remove(tmp)


if __name__ == "__main__":
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    src = sys.argv[1] if len(sys.argv) > 1 else json.load(open(os.path.join(ROOT, "config", "project.json"))).get("assets_pack", {}).get("url", "")
    if not src: sys.exit("no pack given: pass a zip file or a web address, or set config/project.json -> assets_pack.url")
    install(src)
