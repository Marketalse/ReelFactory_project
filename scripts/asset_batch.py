#!/usr/bin/env python3
"""Test a HUGE pile of icons/pictures in one go (Hesham 2026-11-03). Free, offline, no AI. Never changes or deletes your files.

  python3 scripts/asset_batch.py ~/Downloads/icons.zip          (a zip, a folder, or several of them)
  python3 scripts/asset_batch.py ~/Downloads/icons.zip --out library/assets

For every SVG/PNG it runs the safe-zone asset check (scripts/lib/asset_check.py). It then
  - copies each file that PASSES (plus its <name>.placement.json) into  <out>/ok/
  - writes <out>/_reports/<time>/report.csv (every file: PASS/FAIL, reason, size, zones) and summary.txt (counts per reason)
Failed files are NOT copied (only listed with the reason). Duplicates (same bytes) are counted once. Zip members are read one by one
(never unpacked to disk wholesale), unsafe paths and files over 300 KB are refused, so a huge or hostile zip cannot fill the disk.
"""
import argparse, csv, hashlib, json, os, re, shutil, sys, tempfile, time, zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import asset_check as ac        # noqa: E402

EXT = (".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".json", ".ico", ".pdf", ".eps", ".ai")


def members(src):
    """Yield (name, reader) for every file in a zip or folder. reader() -> bytes (None if refused)."""
    if os.path.isdir(src):
        for root, _, files in os.walk(src):
            for f in sorted(files):
                p = os.path.join(root, f)
                yield os.path.relpath(p, src), (lambda p=p: open(p, "rb").read() if os.path.getsize(p) <= ac.MAX_BYTES * 4 else None)
    elif zipfile.is_zipfile(src):
        z = zipfile.ZipFile(src)
        for i in z.infolist():
            if i.is_dir(): continue
            n = i.filename
            if n.startswith("/") or ".." in n.replace("\\", "/").split("/") or "__MACOSX" in n or os.path.basename(n).startswith("."):
                continue                                                         # unsafe path or Mac junk: skipped silently
            yield n, (lambda i=i, z=z: z.read(i) if i.file_size <= ac.MAX_BYTES * 4 else None)
    else:
        yield os.path.basename(src), (lambda: open(src, "rb").read())


def safe_name(n, taken):
    base, ext = os.path.splitext(os.path.basename(n))
    base = re.sub(r"[^A-Za-z0-9_-]+", "-", base).strip("-").lower()[:60] or "asset"
    name, k = base + ext.lower(), 2
    while name in taken:
        name = f"{base}-{k}{ext.lower()}"; k += 1
    taken.add(name); return name


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sources", nargs="+"); ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "library", "assets"))
    ap.add_argument("--limit", type=int, default=0, help="stop after N files (for a quick try)")
    a = ap.parse_args()
    t0 = time.time(); stamp = time.strftime("%Y%m%d-%H%M%S")
    okdir, repdir = os.path.join(a.out, "ok"), os.path.join(a.out, "_reports", stamp)
    os.makedirs(okdir, exist_ok=True); os.makedirs(repdir, exist_ok=True)
    taken = set(os.listdir(okdir)); seen = {}; rows = []; reasons = {}; tmp = tempfile.mkdtemp(prefix="assetcheck-")
    n = 0
    for src in a.sources:
        for name, read in members(src):
            ext = os.path.splitext(name)[1].lower()
            if ext not in EXT: continue
            n += 1
            if a.limit and n > a.limit: break
            row = {"file": name, "result": "FAIL", "reason": "", "kind": "", "size": "", "zones": "", "saved_as": ""}
            data = read()
            if data is None:
                row["reason"] = f"over {ac.MAX_BYTES * 4 // 1000} KB: refused"
            else:
                h = hashlib.sha256(data).hexdigest()
                if h in seen:
                    row["result"], row["reason"] = "DUPLICATE", "same file as " + seen[h]
                else:
                    seen[h] = name
                    p = os.path.join(tmp, "f" + ext)
                    open(p, "wb").write(data)
                    r = ac.check(p)
                    row["kind"] = r.get("kind", ""); row["size"] = f"{r.get('w', '')}x{r.get('h', '')}" if r.get("w") else ""
                    if r["ok"]:
                        out = safe_name(name, taken)
                        shutil.copy(p, os.path.join(okdir, out))
                        r["asset"] = out
                        json.dump(r, open(os.path.join(okdir, os.path.splitext(out)[0] + ".placement.json"), "w"), indent=1, ensure_ascii=False)
                        row.update(result="PASS", saved_as=out, zones=" ".join(f"{z['zone']}:{z['max_w']}x{z['max_h']}" for z in r["may_sit"] if z["ok"]))
                    else:
                        row["reason"] = "; ".join(r["problems"]) or "no zone is big enough"
            rows.append(row)
            if row["result"] != "PASS": reasons[re.sub(r"[\d.]+", "#", row["reason"])[:90]] = reasons.get(re.sub(r"[\d.]+", "#", row["reason"])[:90], 0) + 1
            if n % 200 == 0: print(f"  ...{n} files checked ({sum(r['result'] == 'PASS' for r in rows)} pass)", flush=True)
        if a.limit and n > a.limit: break
    shutil.rmtree(tmp, ignore_errors=True)
    with open(os.path.join(repdir, "report.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["file"]); w.writeheader(); w.writerows(rows)
    cnt = lambda k: sum(r["result"] == k for r in rows)
    lines = [f"Checked {len(rows)} files in {time.time() - t0:.0f} s", f"PASS      {cnt('PASS')}   (copied to {okdir})", f"FAIL      {cnt('FAIL')}", f"DUPLICATE {cnt('DUPLICATE')}",
             "", "Most common reasons for FAIL:"] + [f"  {v:5d}  {k}" for k, v in sorted(reasons.items(), key=lambda x: -x[1])[:15] if k]
    open(os.path.join(repdir, "summary.txt"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines)); print(f"\nFull list: {os.path.join(repdir, 'report.csv')}")


if __name__ == "__main__":
    main()
