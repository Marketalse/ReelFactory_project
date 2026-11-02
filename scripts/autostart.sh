#!/bin/bash
# Started by macOS at login (see "Turn on auto-start.command"). Gets the latest version, then runs the dashboard.
cd "$(dirname "$0")/.." || exit 1
export GIT_TERMINAL_PROMPT=0
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then git pull --ff-only --quiet 2>/dev/null; fi
P="$(cat "$HOME/.reelfactory/port" 2>/dev/null)"; case "$P" in ""|*[!0-9]*) P=8766;; esac
[ "$P" -lt 8766 ] || [ "$P" -gt 8789 ] && P=8766
export RF_DASH_PORT="$P"            # address chosen by the start buttons (never 8765, Content Workshop's)
exec python3 dashboard/serve.py
