#!/usr/bin/env bash
# One-time import of the existing Reel Factory files into this repo's new structure.
#
#   bash scripts/import_from_old.sh ~/Desktop/Reel-Factory
#
# Copies only (the old folder is never changed). Video, audio and images are not copied into git
# (see .gitignore); reference videos are copied to references/ so they stay usable locally.
# Afterwards: review with `git status`, then commit and push.
set -euo pipefail
OLD="${1:?usage: bash scripts/import_from_old.sh /path/to/old/Reel-Factory}"
OLD="${OLD%/}"
NEW="$(cd "$(dirname "$0")/.." && pwd)"
[ -d "$OLD" ] || { echo "Not a folder: $OLD"; exit 1; }
[ "$(cd "$OLD" && pwd)" != "$NEW" ] || { echo "Old and new folder are the same"; exit 1; }

copied=0; missing=()
cp_one() {  # cp_one <old relative path> <new relative path>
  if [ -e "$OLD/$1" ]; then
    mkdir -p "$NEW/$(dirname "$2")"
    cp -R "$OLD/$1" "$NEW/$2"
    copied=$((copied + 1)); echo "  ok  $1  ->  $2"
  else
    missing+=("$1")
  fi
}

echo "== working code (keeps working; will be refactored) =="
cp_one scripts/reel.py          scripts/reel.py
cp_one scripts/keyframes.py     scripts/keyframes.py
cp_one scripts/ingest.sh        scripts/ingest.sh
cp_one dashboard/add_expense.py dashboard/add_expense.py
cp_one dashboard/expenses.json  dashboard/expenses.json          # git-ignored: your spend stays local
cp_one model/cost_model.py      scripts/cost_model.py
cp_one model/models.json        archive/model/models.json         # replaced by config/project.json
cp_one style/fonts              style/fonts

echo "== knowledge worth keeping =="
cp_one .reel-agent/lessons.md        .reel-agent/lessons.md
cp_one .reel-agent/visual-ledger.json .reel-agent/visual-ledger.json
cp_one model/COST_MODEL.md           docs/COST_MODEL.md
cp_one references/reference_spec.md     references/reference_spec.md
cp_one references/reference_spec_v2.md  references/reference_spec_v2.md
cp_one references/ai-tool-reel-teardown.md references/ai-tool-reel-teardown.md
cp_one references/ai-tool-prompts.md    references/ai-tool-prompts.md
cp_one references/harakah-integration.md references/harakah-integration.md
for f in "$OLD"/references/ref*.mp4; do [ -e "$f" ] && cp_one "references/$(basename "$f")" "references/$(basename "$f")"; done

echo "== archived (replaced by the new structure, kept for history) =="
for f in AGENTS.md SOP.md EXECUTION_PLAN.md REEL_FACTORY_MASTER_INDEX.md REEL_FACTORY_FINAL_INDEX.md \
         REEL_FACTORY_LIVE_QUEUE.md REEL_FACTORY_CONTROL_BOARD.md REEL_FACTORY_TASK_MAP.md \
         REEL_FACTORY_CANONICAL_TASK_MAP.md REEL_FACTORY_EXECUTION_STATUS.md REEL_FACTORY_STATUS_SNAPSHOT.md; do
  cp_one "$f" "archive/$f"
done
cp_one archive/EXECUTION_PLAN_v1.md archive/EXECUTION_PLAN_v1.md
cp_one model/MODELS.md          archive/model/MODELS.md
cp_one model/llm.md             archive/model/llm.md
cp_one style/brand.json         archive/style/brand.json          # replaced by config/brand.json
cp_one templates                archive/templates_v0
cp_one reels/v0-draft           archive/reels_v0-draft
cp_one dashboard/dashboard.html archive/dashboard_old.html
cp_one inbox/scripts/intake.py  archive/intake.py

# never bring tooling or junk across
find "$NEW" -name .DS_Store -delete 2>/dev/null || true
find "$NEW" -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true

echo
echo "Copied $copied item(s). Not found (fine if you never had them): ${#missing[@]}"
for m in "${missing[@]:-}"; do [ -n "$m" ] && echo "  -  $m"; done
echo
echo "Not imported on purpose: jobs/ and assets/raw/ (video stay where they are), spikes/, integrations/harakah (re-added later as a built file), node_modules."
echo "Next:  git status   then   git add -A && git commit -m 'Import existing code' && git push"
