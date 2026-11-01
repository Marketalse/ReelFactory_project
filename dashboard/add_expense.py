#!/usr/bin/env python3
"""add_expense.py — add one row to the dashboard ledger.
Usage:
  python3 add_expense.py --video 2026-10-31-haiku-launch --category LLM API --amount 0.04 --note "Haiku 5.5 Director pass, 3 revisions"
  python3 add_expense.py --video template-captions --category Template design --amount 4.20 --note "Sonnet 5.5 session, 2 rounds"
Writes expenses.json next to this script. Prints the new partial total.
"""
import json, sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
LEDGER = HERE / "expenses.json"

def load():
    try: return json.loads(LEDGER.read_text())
    except Exception: return {"rows": [], "categories": {}, "created": "2026-10-29"}

def save(d):
    LEDGER.write_text(json.dumps(d, indent=2, ensure_ascii=False))

def main():
    import argparse
    if len(sys.argv) < 2 or "--help" in sys.argv:
        print(__doc__); sys.exit(0)
    ap = argparse.ArgumentParser()
    ap.add_argument("--video"); ap.add_argument("--category", nargs="+"); ap.add_argument("--amount"); ap.add_argument("--note", default="")
    ns, _ = ap.parse_known_args()
    video = ns.video or ""; category = " ".join(ns.category or []); amount = ns.amount or ""; note = ns.note
    if not (video and category and amount):
        print("missing one of --video / --category / --amount"); sys.exit(1)
    try: value = float(amount)
    except ValueError:
        print("amount must be a number"); sys.exit(1)
    d = load()
    d["rows"].append({"date": date.today().isoformat(), "video": video, "category": category,
                      "amount": round(value, 4), "note": note})
    d["rows"] = d["rows"][-200:]
    save(d)
    print(f"ok: {video} | {category} | {value:.4f}")
    print(f"total: {sum(r['amount'] for r in d['rows']):.4f}")

if __name__ == "__main__":
    main()
