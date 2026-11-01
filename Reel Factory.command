#!/bin/bash
# Double-click this file in Finder to open Reel Factory in your browser.
cd "$(dirname "$0")" || exit 1
HERE="$(pwd -P)"
echo "Reel Factory: $HERE"
if [ -d .git ]; then
  git pull --quiet 2>/dev/null && echo "Updated to the latest version." || echo "Couldn't check for updates (offline?). Using this version."
else
  echo "Note: this copy isn't linked to GitHub (a ZIP download?), so it never updates. Use your cloned project folder instead."
fi
RUNNING="$(curl -s --max-time 2 http://127.0.0.1:8765/api/root 2>/dev/null | python3 -c 'import sys,json; print(json.load(sys.stdin)["root"])' 2>/dev/null)"
if [ -n "$RUNNING" ] && [ "$RUNNING" != "$HERE" ]; then
  echo "Another copy was running from $RUNNING. Switching to this one."
  lsof -ti tcp:8765 -sTCP:LISTEN | xargs kill 2>/dev/null; sleep 1
  RUNNING=""
fi
if [ -z "$RUNNING" ] && ! curl -s --max-time 2 -o /dev/null http://127.0.0.1:8765/api/reels; then
  nohup python3 dashboard/serve.py > dashboard/server.log 2>&1 &
  sleep 1.5
fi
open http://127.0.0.1:8765/
echo "Opened in your browser. You can close this window."
