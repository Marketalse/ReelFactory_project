"""Keeps YOUR task-board changes (done marks, notes) when an update changes the same board file.
Three-way merge of dashboard/tasks.json by task and field:
  base = the board as it was when you last updated, mine = your board now, theirs = the new board from GitHub.
  A field you changed (and GitHub did not) stays yours. If both changed it, GitHub's wins, except 'done' which is always kept.
  Tasks you added are kept. Nothing else in the file is touched."""
import json, os, subprocess, sys


def merge3(base, mine, theirs):
    b = {t["id"]: t for t in (base or {}).get("tasks", [])}
    m = {t["id"]: t for t in (mine or {}).get("tasks", [])}
    out = json.loads(json.dumps(theirs))
    have = {t["id"]: t for t in out.get("tasks", [])}
    for tid, mt in m.items():
        bt, tt = b.get(tid), have.get(tid)
        if tt is None:
            if bt is None:                       # a task only you added
                out["tasks"].append(mt)
            continue                             # removed upstream: stay removed
        for k, v in mt.items():
            if bt is not None and bt.get(k) == v:
                continue                         # you didn't change this field
            if bt is None or tt.get(k) == bt.get(k) or (k == "status" and v == "done"):
                tt[k] = v                        # only you changed it (or you marked it done)
    mine_log = (mine or {}).get("log", []); seen = {json.dumps(x, sort_keys=True) for x in out.get("log", [])}
    out.setdefault("log", []).extend(x for x in mine_log if json.dumps(x, sort_keys=True) not in seen and x not in (base or {}).get("log", []))
    return out


def _git(root, *a):
    return subprocess.run(["git", "-C", root, *a], capture_output=True, text=True)


def load_file(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_file(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2); f.write("\n")
    os.replace(tmp, path)


def from_stash(root):
    """After `git stash` + `git pull`: put your board changes from the stash back on top of the new board."""
    rel = "dashboard/tasks.json"
    mine = _git(root, "show", f"stash@{{0}}:{rel}"); base = _git(root, "show", f"stash@{{0}}^:{rel}")
    if mine.returncode or base.returncode:
        return False, "nothing to restore"
    path = os.path.join(root, rel)
    save_file(path, merge3(json.loads(base.stdout), json.loads(mine.stdout), load_file(path)))
    return True, "your board changes were restored"


if __name__ == "__main__":
    ok, msg = from_stash(sys.argv[1] if len(sys.argv) > 1 else os.getcwd())
    print(msg)
