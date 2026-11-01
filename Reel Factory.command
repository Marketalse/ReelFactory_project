#!/bin/bash
# Double-click this file in Finder to open Reel Factory in your browser.
cd "$(dirname "$0")" || exit 1
HERE="$(pwd -P)"
echo "Reel Factory: $HERE"
UPDATED=""
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  BEFORE="$(git rev-parse HEAD 2>/dev/null)"
  if git pull --quiet 2>/dev/null; then
    if [ "$BEFORE" != "$(git rev-parse HEAD 2>/dev/null)" ]; then UPDATED=1; echo "Updated to the latest version."; else echo "Already up to date."; fi
  else
    echo "Couldn't check for updates (offline?). Using this version."
  fi
else
  echo "Note: this copy isn't linked to GitHub (a ZIP download?), so it never updates. Use your cloned project folder instead."
fi
AGENT="gui/$(id -u)/com.reelfactory.dashboard"
if launchctl print "$AGENT" >/dev/null 2>&1; then AUTO=1; else AUTO=""; fi
RUNNING="$(curl -s --max-time 2 http://127.0.0.1:8765/api/root 2>/dev/null | python3 -c 'import sys,json; print(json.load(sys.stdin)["root"])' 2>/dev/null)"
UP="$(curl -s --max-time 2 -o /dev/null -w '%{http_code}' http://127.0.0.1:8765/api/reels 2>/dev/null)"
RESTART=""
if [ "$UP" = "200" ]; then
  if [ -z "$RUNNING" ]; then RESTART="An older dashboard is running. Restarting it with the new version."
  elif [ "$RUNNING" != "$HERE" ]; then RESTART="Another copy was running from $RUNNING. Switching to this one."
  elif [ -n "$UPDATED" ]; then RESTART="Restarting the dashboard with the update."
  fi
fi
if [ -n "$RESTART" ]; then
  if curl -s --max-time 2 http://127.0.0.1:8765/api/reels | grep -q '"busy": \[\]'; then
    echo "$RESTART"
    if [ -n "$AUTO" ]; then launchctl kickstart -k "$AGENT"; sleep 2; else
      lsof -ti tcp:8765 -sTCP:LISTEN | xargs kill 2>/dev/null; sleep 1
      UP=""
    fi
  else
    echo "A reel is being made right now, so the dashboard keeps running. Double-click again when it's finished to load the update."
  fi
fi
if [ "$UP" != "200" ] && [ -n "$AUTO" ]; then
  launchctl kickstart "$AGENT" 2>/dev/null; sleep 2
elif [ "$UP" != "200" ]; then
  nohup python3 dashboard/serve.py > dashboard/server.log 2>&1 &
  sleep 1.5
fi
open http://127.0.0.1:8765/
echo "Opened in your browser. You can close this window."
