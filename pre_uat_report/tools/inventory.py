#!/usr/bin/env python3
"""Stage 1: automatic inventory of the repository (modules, sizes, functions, internal imports, tests per module, unused functions, endpoints,
config keys). Reads source only; writes pre_uat_report/evidence/metrics/inventory.json. No network, no AI."""
import ast, json, os, re, subprocess, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC_DIRS = ["scripts", "scripts/lib", "dashboard"]


def py_files(d):
    p = os.path.join(ROOT, d)
    return sorted(os.path.join(d, f) for f in os.listdir(p) if f.endswith(".py")) if os.path.isdir(p) else []


mods, allsrc = {}, {}
for d in SRC_DIRS:
    for f in py_files(d):
        txt = open(os.path.join(ROOT, f), encoding="utf-8").read(); allsrc[f] = txt
        tree = ast.parse(txt)
        funcs = [(n.name, n.lineno, (n.end_lineno or n.lineno)) for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        classes = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        imps = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.ImportFrom) and n.module is not None and n.level >= 1:
                imps.update(a.name for a in n.names) if n.module == "" else imps.add(n.module.split(".")[0])
            elif isinstance(n, ast.ImportFrom) and n.module:
                if n.module == "lib": imps.update(a.name for a in n.names)
                elif n.module.startswith("lib."): imps.add(n.module.split(".")[1])
            elif isinstance(n, ast.Import):
                imps.update(a.name.split(".")[0] for a in n.names)
        mods[f] = {"loc": txt.count("\n") + 1, "functions": len(funcs), "classes": classes, "func_list": funcs, "imports": sorted(imps),
                   "longest": sorted(funcs, key=lambda x: x[2] - x[1], reverse=True)[:3]}
tests = {}
for f in sorted(os.listdir(os.path.join(ROOT, "tests"))):
    if f.startswith("test_") and f.endswith(".py"):
        t = open(os.path.join(ROOT, "tests", f), encoding="utf-8").read()
        tests[f] = t
names = {os.path.splitext(os.path.basename(m))[0]: m for m in mods}
covered = {m: sorted(tf for tf, t in tests.items() if re.search(r"\b" + re.escape(os.path.splitext(os.path.basename(m))[0]) + r"\b", t)) for m in mods}
alltext = "\n".join(allsrc.values()) + "\n".join(tests.values()) + "\n".join(open(os.path.join(ROOT, "dashboard", h), encoding="utf-8").read() for h in os.listdir(os.path.join(ROOT, "dashboard")) if h.endswith(".html"))
unused = []
for m, info in mods.items():
    for name, a, b in info["func_list"]:
        if name.startswith("_") or name in ("main", "do_GET", "do_POST") or name.startswith(("st_", "test_")): continue
        if len(re.findall(r"\b" + re.escape(name) + r"\b", alltext)) <= 1:
            unused.append((m, name, a))
big = sorted(((m, n, a, b - a + 1) for m, i in mods.items() for n, a, b in i["func_list"] if b - a + 1 > 80), key=lambda x: -x[3])
serve = allsrc["dashboard/serve.py"]
endpoints = sorted(set(re.findall(r'startswith\("(/api/[a-z_/\.]*)"', serve) + re.findall(r'path == "(/[a-z/\.]*)"', serve)))
actions = sorted(set(re.findall(r'"([a-z_]+)": lambda: reels_api', serve)))
cfgkeys = list(json.load(open(os.path.join(ROOT, "config", "project.json"))).keys())
unused_cfg = [k for k in cfgkeys if not k.startswith("_") and not re.search(r"""["']""" + re.escape(k) + r"""["']""", "\n".join(allsrc.values()))]
git = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
out = {"commit": git, "modules": {m: {k: v for k, v in i.items() if k not in ("func_list",)} for m, i in mods.items()}, "tests_per_module": covered,
       "modules_without_tests": sorted(m for m, t in covered.items() if not t), "unused_function_candidates": unused, "functions_over_80_lines": big,
       "dashboard_endpoints": endpoints, "reel_actions": actions, "config_keys": cfgkeys, "config_keys_never_read_in_code": unused_cfg,
       "loc_total": sum(i["loc"] for i in mods.values()), "test_files": len(tests)}
json.dump(out, open(os.path.join(ROOT, "pre_uat_report", "evidence", "metrics", "inventory.json"), "w"), indent=1, ensure_ascii=False)
print("commit", git[:10], "| modules", len(mods), "| LOC", out["loc_total"], "| test files", len(tests))
print("modules without a test file naming them:", out["modules_without_tests"])
print("functions > 80 lines:", [(m, n, ln) for m, n, a, ln in big][:12])
print("unused function candidates:", len(unused), [(m.split('/')[-1], n) for m, n, a in unused][:25])
print("config keys never read:", unused_cfg)
print("endpoints:", len(endpoints), "reel actions:", len(actions))
