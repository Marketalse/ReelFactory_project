#!/usr/bin/env python3
"""Check the Nous model list and prices against config/project.json. Free (no AI call is made).

    python3 scripts/models_refresh.py            report: are our models still offered, and at what price
    python3 scripts/models_refresh.py --write    also update prices_per_mtok for the models we use

Never switches models: that needs Hesham's approval in docs/DECISIONS.md (AGENTS.md section 6).
"""
import argparse, json, os, sys, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import config as cfg  # noqa: E402

PROJECT_JSON = os.path.join(cfg.ROOT, "config", "project.json")


def per_mtok(pricing):
    """Prices as $ per million tokens from either per-token strings (OpenRouter style) or per-million numbers."""
    if not isinstance(pricing, dict):
        return None
    def num(*keys):
        for k in keys:
            if pricing.get(k) not in (None, ""):
                try:
                    return float(pricing[k])
                except (TypeError, ValueError):
                    pass
        return None
    i, o = num("prompt", "input", "in"), num("completion", "output", "out")
    if i is None or o is None:
        return None
    if i < 0.01 and o < 0.01:          # per token -> per million
        i, o = i * 1e6, o * 1e6
    return {"in": round(i, 4), "out": round(o, 4)}


def fetch(opener=urllib.request.urlopen):
    base, key = cfg.auth()
    req = urllib.request.Request(base.rstrip("/") + "/models", headers={"Authorization": "Bearer " + key})
    with opener(req, timeout=30) as r:
        d = json.loads(r.read().decode("utf-8"))
    return {m.get("id"): m for m in (d.get("data") or d.get("models") or []) if isinstance(m, dict) and m.get("id")}


def compare(catalog, project):
    used = sorted(set(project["models"].values()))
    rows, new_prices = [], {}
    for m in used:
        have = project.get("prices_per_mtok", {}).get(m)
        if m not in catalog:
            rows.append((m, "NOT OFFERED any more: tell Claude", have, None)); continue
        live = per_mtok(catalog[m].get("pricing"))
        if live and have and (abs(live["in"] - have["in"]) > 1e-6 or abs(live["out"] - have["out"]) > 1e-6):
            rows.append((m, "price changed", have, live)); new_prices[m] = live
        elif live and not have:
            rows.append((m, "price added", None, live)); new_prices[m] = live
        else:
            rows.append((m, "ok", have, live))
    return rows, new_prices


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    try:
        catalog = fetch()
    except SystemExit as e:
        sys.exit(str(e))
    except Exception as e:
        sys.exit(f"Couldn't read the model list: {e}")
    project = json.load(open(PROJECT_JSON, encoding="utf-8"))
    rows, new_prices = compare(catalog, project)
    print(f"{len(catalog)} models offered. Ours:")
    for m, state, have, live in rows:
        print(f"  {m:40s} {state:40s} config={have} live={live}")
    if new_prices and a.write:
        project.setdefault("prices_per_mtok", {}).update(new_prices)
        json.dump(project, open(PROJECT_JSON, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
        open(PROJECT_JSON, "a").write("\n")
        print(f"Updated prices for {len(new_prices)} model(s) in config/project.json.")
    elif new_prices:
        print("Run again with --write to update the prices.")


if __name__ == "__main__":
    main()
