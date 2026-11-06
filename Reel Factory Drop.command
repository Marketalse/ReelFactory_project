#!/bin/bash
# Double-click: starts the Drop folder. Put clips in "Reel Factory Drop" on your Desktop, drafts appear in its Ready folder.
cd "$(dirname "$0")" || exit 1
if ! command -v python3 >/dev/null 2>&1; then echo "PROBLEM: Python is missing. Send Claude a screenshot of this window."; exit 1; fi
. scripts/rf_port.sh 2>/dev/null
open "$(pwd -P)/Reel Factory.command"          # starts the dashboard, opens the browser, prints the links
echo ""
echo "Drop folder: ~/Desktop/Reel Factory Drop   (drafts appear in its Ready folder)"
echo "Dashboard:   http://reelfactory.localhost:${RF_PORT:-8766}   Control: http://reelfactory.localhost:${RF_PORT:-8766}/index.html   (backup http://127.0.0.1:${RF_PORT:-8766})"
echo "Leave this window open while you work. Close it to stop."
echo ""
open "$HOME/Desktop/Reel Factory Drop" 2>/dev/null || { mkdir -p "$HOME/Desktop/Reel Factory Drop"; open "$HOME/Desktop/Reel Factory Drop"; }
exec python3 -u scripts/watch_folder.py
