#!/bin/bash
# Double-click this file in Finder to open the Reel Factory dashboard.
cd "$(dirname "$0")" || exit 1
git pull --quiet 2>/dev/null || true
if ! curl -s -o /dev/null http://127.0.0.1:8765/api/reels; then
  nohup python3 dashboard/serve.py > dashboard/server.log 2>&1 &
  sleep 1.5
fi
open http://127.0.0.1:8765
