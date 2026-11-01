"""Backup: copy the small, irreplaceable files (results, comments, plans, transcripts, settings, lessons, task board)
into Google Drive or iCloud Drive on this Mac, as one ZIP per backup. Never videos, images, audio or keys.

Google Drive for desktop and iCloud Drive sync these folders to the cloud by themselves; nothing is uploaded from here.
Settings live in ~/.reelfactory/backup.json. Runs from the Settings button, and automatically once a day while the
dashboard is open (serve.py)."""
import glob, json, os, re, time, zipfile

HOME = os.path.expanduser("~")
STATE = os.path.join(HOME, ".reelfactory", "backup.json")
FOLDER = "Reel Factory backup"
KEEP = 30                                         # newest backups kept in the folder
TEXT = (".json", ".md", ".txt", ".srt", ".log", ".csv")
SKIP_DIRS = re.compile(r"^(hyperframes.*|hf|_frames|node_modules|assets|proxy.*)$")
MAX_FILE = 5 * 1024 * 1024
NAME = re.compile(r"^reelfactory-backup-\d{4}-\d{2}-\d{2}-\d{4}\.zip$")
DAY = 24 * 3600


def targets(home=HOME):
    """Cloud folders found on this Mac: [{key, label, path}]. Google Drive first."""
    out = []
    for p in sorted(glob.glob(os.path.join(home, "Library", "CloudStorage", "GoogleDrive-*"))):
        for sub in ("My Drive", "Mon Drive", "Meine Ablage"):
            if os.path.isdir(os.path.join(p, sub)):
                acct = os.path.basename(p)[len("GoogleDrive-"):]
                out.append({"key": "gdrive:" + acct, "label": f"Google Drive ({acct})", "path": os.path.join(p, sub)})
                break
    ic = os.path.join(home, "Library", "Mobile Documents", "com~apple~CloudDocs")
    if os.path.isdir(ic):
        out.append({"key": "icloud", "label": "iCloud Drive", "path": ic})
    return out


def _load():
    try:
        return json.load(open(STATE, encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save(st):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    tmp = STATE + ".tmp"
    json.dump(st, open(tmp, "w", encoding="utf-8"), indent=1)
    os.replace(tmp, STATE)


def _chosen(st, found):
    return next((t for t in found if t["key"] == st.get("target")), found[0] if found else None)


def status(home=HOME):
    st, found = _load(), targets(home)
    t = _chosen(st, found)
    return {"targets": [{"key": x["key"], "label": x["label"]} for x in found], "target": t["key"] if t else None,
            "last": st.get("last"), "last_file": st.get("last_file"), "last_count": st.get("last_count"),
            "error": st.get("error"), "auto": st.get("auto", True)}


def files_to_save(root):
    """(path on disk, path inside the ZIP) for every small text file worth keeping."""
    out = []
    for rel in ("config", ".reel-agent"):
        for dp, dn, fn in os.walk(os.path.join(root, rel)):
            out += [(os.path.join(dp, f), os.path.relpath(os.path.join(dp, f), root)) for f in fn if f.endswith(TEXT)]
    for rel in ("dashboard/tasks.json", "dashboard/expenses.json"):
        if os.path.isfile(os.path.join(root, rel)):
            out.append((os.path.join(root, rel), rel))
    for d in ("jobs", "inbox"):
        base = os.path.join(root, d)
        for dp, dn, fn in os.walk(base):
            dn[:] = [x for x in dn if not SKIP_DIRS.match(x) and not x.startswith(".")]
            for f in fn:
                p = os.path.join(dp, f)
                if f.endswith(TEXT) and os.path.getsize(p) <= MAX_FILE:
                    out.append((p, os.path.relpath(p, root)))
    return out


def run(root, target=None, home=HOME, now=None):
    """Make one backup ZIP. Returns (ok, message)."""
    st, found = _load(), targets(home)
    if target:
        if target not in [t["key"] for t in found]:
            return False, "That backup place isn't on this Mac any more."
        st["target"] = target
    t = _chosen(st, found)
    if not t:
        return False, "No Google Drive or iCloud Drive folder found on this Mac. Install Google Drive for desktop or turn on iCloud Drive, then try again."
    dest = os.path.join(t["path"], FOLDER)
    stamp = time.strftime("%Y-%m-%d-%H%M", time.localtime(now or time.time()))
    name = f"reelfactory-backup-{stamp}.zip"
    try:
        os.makedirs(dest, exist_ok=True)
        files = files_to_save(root)
        tmp = os.path.join(dest, "." + name + ".part")
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            for src, arc in files:
                try:
                    z.write(src, arc)
                except OSError:
                    pass
            z.writestr("README.txt", "Reel Factory backup: your results, comments, plans, transcripts, settings and lessons.\n"
                       "No videos or keys. To restore, unzip into the Reel Factory project folder (ask Claude to help).\n")
        os.replace(tmp, os.path.join(dest, name))
        old = sorted(f for f in os.listdir(dest) if NAME.match(f))
        for f in old[:-KEEP]:
            os.remove(os.path.join(dest, f))
    except OSError as e:
        st["error"] = str(e)[:200]; _save(st)
        return False, f"Backup failed: {e.strerror or e}. Check that {t['label']} is running."
    st.update(last=time.strftime("%Y-%m-%d %H:%M", time.localtime(now or time.time())), last_ts=now or time.time(),
              last_file=f"{t['label']} → {FOLDER}/{name}", last_count=len(files), error=None)
    _save(st)
    return True, f"Backed up {len(files)} files to {t['label']} → {FOLDER}."


def due(now=None):
    st = _load()
    return st.get("auto", True) and (now or time.time()) - float(st.get("last_ts") or 0) >= DAY


def set_auto(on):
    st = _load(); st["auto"] = bool(on); _save(st)
    return True, "Daily backup is on." if on else "Daily backup is off."
