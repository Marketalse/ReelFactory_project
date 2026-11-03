#!/usr/bin/env python3
"""Test a HUGE pile of icons/pictures in one go (made for 20,000+ files). Free, offline, no AI. Never changes or deletes your files.

  python3 scripts/asset_batch.py ~/Downloads/icons.zip          (a zip, a folder, or several of them)
  python3 scripts/asset_batch.py ~/Downloads/icons.zip --out library/assets --workers 6

For every SVG/PNG it runs the safe-zone asset check (scripts/lib/asset_check.py), on all CPU cores at once. It then
  - copies each file that PASSES (plus its <name>.placement.json) into  <out>/ok/
  - writes <out>/_reports/<time>/report.csv (every file: PASS/FAIL/DUPLICATE, reason, size, zones) and summary.txt (counts per reason)
Failed files are NOT copied (only listed with the reason). Duplicates (same bytes) are counted once.
Safe to stop (Ctrl+C) and start again: files already checked are remembered in <out>/ok/.checked and skipped, and the report
is written as it goes. Zip members are read one by one (never unpacked wholesale); unsafe paths and files over 1.2 MB are refused.
"""
import argparse, csv, hashlib, json, multiprocessing as mp, os, re, shutil, sys, tempfile, time, zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import asset_check as ac        # noqa: E402

EXT = (".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".json", ".ico", ".pdf", ".eps", ".ai")
BIG = ac.MAX_BYTES * 4
_TMP = None


def members(src):
    """Yield (name, bytes-or-None) for every file in a zip or folder, one at a time."""
    if os.path.isdir(src):
        for root, _, files in os.walk(src):
            for f in sorted(files):
                p = os.path.join(root, f)
                if f.startswith("."): continue
                try:
                    yield os.path.relpath(p, src), (open(p, "rb").read() if os.path.getsize(p) <= BIG else None)
                except OSError:
                    yield os.path.relpath(p, src), None
    elif zipfile.is_zipfile(src):
        with zipfile.ZipFile(src) as z:
            for i in z.infolist():
                n = i.filename
                if i.is_dir() or n.startswith("/") or ".." in n.replace("\\", "/").split("/") or "__MACOSX" in n or os.path.basename(n).startswith("."):
                    continue                                                         # unsafe path or Mac junk: skipped silently
                try:
                    yield n, (z.read(i) if i.file_size <= BIG else None)
                except Exception:                                                    # noqa: BLE001 - one broken member never stops the pile
                    yield n, None
    else:
        yield os.path.basename(src), open(src, "rb").read()


def work(job):
    """(index, name, data) -> (index, record or None). Runs in a worker process."""
    global _TMP
    i, name, data = job
    _TMP = _TMP or tempfile.mkdtemp(prefix="assetcheck-")
    try:
        return i, ac.check_bytes(name, data, _TMP)
    except Exception as e:                                                          # noqa: BLE001
        return i, {"ok": False, "problems": [f"could not be checked: {e}"], "may_sit": []}


def safe_name(n, taken):
    base, ext = os.path.splitext(os.path.basename(n))
    base = re.sub(r"[^A-Za-z0-9_-]+", "-", base).strip("-").lower()[:60] or "asset"
    name, k = base + ext.lower(), 2
    while name in taken:
        name = f"{base}-{k}{ext.lower()}"; k += 1
    taken.add(name); return name


def jobs(sources, seen, counters, limit):
    """Feed the workers: skips non-assets, duplicates and files already checked in an earlier run."""
    n = 0
    for src in sources:
        for name, data in members(src):
            if os.path.splitext(name)[1].lower() not in EXT: continue
            n += 1
            if limit and n > limit: return
            if data is None:
                counters["refused"].append(name); continue
            h = hashlib.sha256(data).hexdigest()
            if h in seen:
                counters["dups"].append((name, seen[h])); continue
            seen[h] = name
            yield (h, name, data)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sources", nargs="+")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "library", "assets"))
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--limit", type=int, default=0, help="stop after N files (for a quick try)")
    a = ap.parse_args()
    t0 = time.time(); stamp = time.strftime("%Y%m%d-%H%M%S")
    okdir, repdir = os.path.join(a.out, "ok"), os.path.join(a.out, "_reports", stamp)
    os.makedirs(okdir, exist_ok=True); os.makedirs(repdir, exist_ok=True)
    done_p = os.path.join(okdir, ".checked")
    seen = {}
    if os.path.exists(done_p):                                   # resume: files already checked in an earlier run
        for line in open(done_p, encoding="utf-8"):
            h = line.strip()
            if h: seen[h] = "an earlier run"
    taken = set(os.listdir(okdir)); counters = {"refused": [], "dups": []}
    csvf = open(os.path.join(repdir, "report.csv"), "w", newline="", encoding="utf-8")
    cols = ["file", "result", "reason", "kind", "size", "zones", "saved_as"]
    w = csv.DictWriter(csvf, fieldnames=cols); w.writeheader()
    results = {"PASS": 0, "FAIL": 0, "DUPLICATE": 0, "REFUSED": 0}; reasons = {}
    donef = open(done_p, "a", encoding="utf-8")
    pending = {}                                                 # index -> (hash, name, data kept only until its result is back)

    def feed():
        for i, (h, name, data) in enumerate(jobs(a.sources, seen, counters, a.limit)):
            pending[i] = (h, name, data)
            yield (i, name, data)

    def record(row):
        w.writerow(row); results[row["result"]] += 1
        if row["result"] in ("FAIL", "REFUSED"):
            k = re.sub(r"[\d.]+", "#", row["reason"])[:90]; reasons[k] = reasons.get(k, 0) + 1

    count = 0
    pool = mp.Pool(a.workers)
    try:
        for i, r in pool.imap_unordered(work, feed(), chunksize=16):
            h, name, data = pending.pop(i)
            count += 1
            row = {"file": name, "result": "FAIL", "reason": "", "kind": r.get("kind", ""), "size": f"{r.get('w', '')}x{r.get('h', '')}" if r.get("w") else "", "zones": "", "saved_as": ""}
            if r["ok"]:
                out = safe_name(name, taken)
                with open(os.path.join(okdir, out), "wb") as f: f.write(data)
                r["asset"] = out
                json.dump(r, open(os.path.join(okdir, os.path.splitext(out)[0] + ".placement.json"), "w"), indent=1, ensure_ascii=False)
                row.update(result="PASS", saved_as=out, zones=" ".join(f"{z['zone']}:{z['max_w']}x{z['max_h']}" for z in r["may_sit"] if z["ok"]))
            else:
                row["reason"] = "; ".join(r["problems"]) or "no zone is big enough"
            record(row); donef.write(h + "\n")
            if count % 500 == 0:
                donef.flush(); csvf.flush()
                print(f"  ...{count} checked, {results['PASS']} pass, {results['FAIL']} fail  ({count / (time.time() - t0):.0f} files/s)", flush=True)
    except KeyboardInterrupt:
        print("\nStopped. Run the same command again to carry on where it stopped.")
    finally:
        pool.terminate(); donef.close()
    for name, same in counters["dups"]: record({"file": name, "result": "DUPLICATE", "reason": "same file as " + same, "kind": "", "size": "", "zones": "", "saved_as": ""})
    for name in counters["refused"]: record({"file": name, "result": "REFUSED", "reason": f"over {BIG // 1000} KB or unreadable", "kind": "", "size": "", "zones": "", "saved_as": ""})
    csvf.close()
    lines = [f"Checked {sum(results.values())} files in {time.time() - t0:.0f} s", f"PASS      {results['PASS']}   (copied to {okdir})", f"FAIL      {results['FAIL']}",
             f"DUPLICATE {results['DUPLICATE']}", f"REFUSED   {results['REFUSED']}", "", "Most common reasons for FAIL/REFUSED:"] + [f"  {v:6d}  {k}" for k, v in sorted(reasons.items(), key=lambda x: -x[1])[:15] if k]
    open(os.path.join(repdir, "summary.txt"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines)); print(f"\nFull list: {os.path.join(repdir, 'report.csv')}")


if __name__ == "__main__":
    main()
