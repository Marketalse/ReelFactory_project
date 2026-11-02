#!/bin/bash
# Double-click this file in Finder to open Reel Factory in your browser.
# If it can't start, it says why in this window (send Claude a screenshot).
cd "$(dirname "$0")" || exit 1
HERE="$(pwd -P)"
URL="http://127.0.0.1:8790"
LOG="$HERE/dashboard/server.log"
export GIT_TERMINAL_PROMPT=0            # never stop and ask for a GitHub password
echo "Reel Factory: $HERE"

if ! command -v python3 >/dev/null 2>&1; then
  echo ""
  echo "PROBLEM: Python is missing on this Mac, so the dashboard can't run."
  echo "Send Claude a screenshot of this window."
  exit 1
fi

# 1. Get the latest version (gives up after 20 seconds, never asks for a password)
UPDATED=""
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  BEFORE="$(git rev-parse HEAD 2>/dev/null)"
  git pull --ff-only --quiet >/dev/null 2>&1 &
  PULL=$!
  for i in $(seq 1 20); do kill -0 $PULL 2>/dev/null || break; sleep 1; done
  if kill -0 $PULL 2>/dev/null; then kill $PULL 2>/dev/null; echo "Update check took too long. Using this version."
  elif wait $PULL; then
    if [ "$BEFORE" != "$(git rev-parse HEAD 2>/dev/null)" ]; then UPDATED=1; echo "Updated to the latest version."; else echo "Already up to date."; fi
  else
    echo "Couldn't check for updates (offline, or a file was changed by hand). Using this version."
  fi
else
  echo "Note: this copy isn't linked to GitHub (a ZIP download?), so it never updates."
fi

up() { [ "$(curl -s --max-time 2 -o /dev/null -w '%{http_code}' "$URL/api/reels" 2>/dev/null)" = "200" ]; }
wait_up() { for i in $(seq 1 "$1"); do up && return 0; sleep 1; done; return 1; }
start_here() {
  up && { lsof -ti tcp:8790 -sTCP:LISTEN 2>/dev/null | xargs kill 2>/dev/null; sleep 1; }   # only stops Reel Factory itself
  nohup python3 dashboard/serve.py > "$LOG" 2>&1 &
}

AGENT="gui/$(id -u)/com.reelfactory.dashboard"
if launchctl print "$AGENT" >/dev/null 2>&1; then AUTO=1; else AUTO=""; fi

# 2. If a dashboard is already running, make sure it is this folder's, up to date
if up; then
  RUNNING="$(curl -s --max-time 2 "$URL/api/root" 2>/dev/null | python3 -c 'import sys,json; print(json.load(sys.stdin)["root"])' 2>/dev/null)"
  WHY=""
  if [ -z "$RUNNING" ]; then WHY="An older dashboard is running. Restarting it with the new version."
  elif [ "$RUNNING" != "$HERE" ]; then WHY="Another copy was running from $RUNNING. Switching to this one."
  elif [ -n "$UPDATED" ]; then WHY="Restarting the dashboard with the update."
  fi
  if [ -n "$WHY" ]; then
    if curl -s --max-time 2 "$URL/api/reels" | grep -q '"busy": \[\]'; then
      echo "$WHY"
      if [ -n "$AUTO" ] && [ "$RUNNING" = "$HERE" ]; then launchctl kickstart -k "$AGENT" 2>/dev/null; sleep 2
      else start_here; fi
    else
      echo "A reel is being made right now, so the dashboard keeps running. Double-click again when it's finished to load the update."
    fi
  fi
fi

# 3. Not running: start it (auto-start first, then directly from this folder)
if ! up; then
  echo "Starting the dashboard..."
  if [ -n "$AUTO" ]; then launchctl kickstart "$AGENT" 2>/dev/null; fi
  if ! wait_up 8; then
    if [ -n "$AUTO" ]; then
      echo "Auto-start didn't bring it up, so it's starting from this folder instead (it works, but stops when the Mac restarts)."
      echo "To fix auto-start: System Settings > General > Login Items, allow 'bash' (Reel Factory) in the background,"
      echo "then double-click 'Turn on auto-start.command' again. If that shows PROBLEM, send Claude a screenshot."
      launchctl print "$AGENT" 2>&1 | grep -E "state =|last exit|working directory" | head -3 | sed 's/^/   auto-start: /'
    fi
    start_here
    wait_up 20
  fi
fi

# 4. Open it, or say clearly what went wrong
if up; then
  open -a "Google Chrome" "http://reelfactory.localhost:8790/" 2>/dev/null || open "$URL/"
  echo ""
  echo "=============================================="
  echo "  Reel Factory is open in your browser."
  echo "  Make a reel:  http://reelfactory.localhost:8790"
  echo "  Control:      http://reelfactory.localhost:8790/index.html"
  echo "  (backup link: http://127.0.0.1:8790)"
  echo "  (Hold Cmd and click a link to open it)"
  echo "=============================================="
  echo "You can close this window."
else
  echo ""
  echo "PROBLEM: the dashboard didn't start. Send Claude a screenshot of this window."
  echo "------ what the dashboard said ------"
  tail -n 15 "$LOG" 2>/dev/null
  [ -f "$HOME/.reelfactory/dashboard.log" ] && { echo "------ auto-start log ------"; tail -n 8 "$HOME/.reelfactory/dashboard.log"; }
  echo "------ what is using port 8790 ------"
  lsof -nP -i tcp:8790 -sTCP:LISTEN 2>/dev/null || echo "(nothing)"
  open "$URL/"
  echo ""
  echo "Dashboard link (try it after fixing the problem): $URL"
fi
