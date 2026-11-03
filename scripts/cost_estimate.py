#!/usr/bin/env python3
"""Cost of ONE reel, worked out from the real prompt sizes and the prices in config/project.json. Free, offline.
   python3 scripts/cost_estimate.py [--raw 150] [--json]      (raw = seconds of raw footage)
It is an ESTIMATE. After a real reel, compare with jobs/<job>/cost.json (the provider's real numbers):
   python3 scripts/cost_estimate.py --real jobs/<job>/cost.json
"""
import argparse, json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from lib import director, tighten, transcript as tr          # noqa: E402

CFG = json.load(open(os.path.join(ROOT, "config", "project.json")))
P = CFG["prices_per_mtok"]
H, S, O = "anthropic/claude-haiku-5.5", "anthropic/claude-sonnet-5.5", "anthropic/claude-opus-5.5"
IMG = 800            # tokens per 540 px still (same number the money guard uses)
THINK = {"low": 1500, "medium": 5000, "high": 12000}      # typical thinking tokens added to the answer, by effort


def call(model, tin, tout, effort="low"):
    t = tout + THINK[effort]
    return tin * P[model]["in"] / 1e6 + t * P[model]["out"] / 1e6


def tok(chars): return chars / 2.6          # the pipeline's own rule of thumb


def scenario(raw_s, story_s, name):
    words_raw = raw_s * 2.4                 # about 145 words a minute
    words_story = story_s * 2.4
    tr_raw, tr_story = tok(words_raw * 7), tok(words_story * 7)     # 6 letters + space; numbered lines add a bit
    frames = 24                             # after "same picture" filtering (cap is 40)
    rows = []
    add = lambda stage, model, c, note: rows.append((stage, model.split("/")[1], round(c, 4), note))
    # ---- steps both versions have
    add("word fix", H, call(H, tr_raw + 500, tr_raw * 0.15, "low"), "fixes mistakes in the raw words")
    add("proofread", H, call(H, tr_raw + 400, 600, "low"), "second check of the words")
    add("shot log (look at frames)", S, call(S, frames * IMG + 600, frames * 90, "low"), f"{frames} pictures")
    if name == "today":
        add("story pick + hooks", S, call(S, tr_raw + 900, 1200, "low"), "3 stories, hooks")
        add("tighten", S, call(S, tr_story + 500, 500, "low"), "cuts weak lines")
        add("B-roll match (AI)", S, call(S, 1500 + 6 * IMG, 700, "low"), "only when new pictures exist")
        add("director (plan)", H, call(H, tok(len(director.PROMPT)) + tr_story + 1500, 2500, "low"), "chooses visuals")
        add("director repair (30% of reels)", S, 0.3 * call(S, tok(len(director.PROMPT)) + tr_story + 2500, 2500, "low"), "fixes rule breaks")
        add("cover words", H, 0.003, "in the director call")
    else:
        add("story pick + hooks", S, call(S, tr_raw + 900, 1500, "medium"), "strong model, thinks longer")
        add("tighten", S, call(S, tr_story + 500, 600, "medium"), "cuts weak lines")
        add("OUTLINE (new): hook, steps, recap", S, call(S, tr_story + 1800, 1800, "high"), "turns the talk into a structure and a concept")
        add("B-roll match (AI)", S, call(S, 1500 + 6 * IMG, 700, "low"), "when new pictures exist")
        add("director (plan)", S, call(S, tok(len(director.PROMPT)) + tr_story + 3500, 3500, "medium"), "step by step layout + highlights")
        add("LOOK at the result (new, QA) x2 rounds", H, 2 * call(H, 10 * IMG + 1500, 700, "low"), "10 pictures of the draft, scored")
        add("revision after the look (new)", S, call(S, tok(len(director.PROMPT)) + tr_story + 5000, 3000, "medium"), "one fix round")
        add("cover design (new)", S, call(S, 3 * IMG + 1200, 700, "low"), "picks the best face frame + layout")
    return rows


def show(rows, title):
    tot = sum(r[2] for r in rows)
    print(f"\n{title}")
    for st, m, c, n in rows: print(f"  {st:<38}{m:<12}${c:>7.3f}   {n}")
    print(f"  {'TOTAL (estimate)':<50}${tot:>7.3f}")
    return tot


def real(path):
    d = json.load(open(path)); by = {}
    for c in d["calls"]: by[c["stage"]] = by.get(c["stage"], 0) + c["cost"]
    for k, v in sorted(by.items(), key=lambda x: -x[1]): print(f"  {k:<20}${v:.4f}")
    print(f"  {'TOTAL (real)':<20}${sum(by.values()):.4f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--raw", type=float, default=150); ap.add_argument("--story", type=float, default=65)
    ap.add_argument("--real"); ap.add_argument("--json", action="store_true"); a = ap.parse_args()
    if a.real: real(a.real); sys.exit()
    t = show(scenario(a.raw, a.story, "today"), f"TODAY: {a.raw:.0f} s raw, {a.story:.0f} s reel")
    n = show(scenario(a.raw, a.story, "pack"), "FORMAT PACK (same look as the Higgsfield reels)")
    print(f"\n  x{n / t:.1f} per reel.  100 reels a month: today ${t * 100:.0f}, pack ${n * 100:.0f}   (the monthly stop is ${CFG['budget_usd']['monthly_stop']:.0f})")
