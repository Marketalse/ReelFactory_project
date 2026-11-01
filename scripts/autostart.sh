#!/bin/bash
# Started by macOS at login (see "Turn on auto-start.command"). Gets the latest version, then runs the dashboard.
cd "$(dirname "$0")/.." || exit 1
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then git pull --ff-only --quiet 2>/dev/null; fi
exec python3 dashboard/serve.py
