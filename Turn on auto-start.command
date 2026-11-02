#!/bin/bash
# Double-click once: Reel Factory then starts by itself every time you log in to your Mac.
# Afterwards just open http://127.0.0.1:8765 (bookmark it). Undo with "Turn off auto-start.command".
cd "$(dirname "$0")" || exit 1
HERE="$(pwd -P)"
LABEL="com.reelfactory.dashboard"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
mkdir -p "$HOME/Library/LaunchAgents" "$HOME/.reelfactory"
chmod +x scripts/autostart.sh
esc() { printf '%s' "$1" | sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g'; }
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$(esc "$HERE/scripts/autostart.sh")</string></array>
  <key>WorkingDirectory</key><string>$(esc "$HERE")</string>
  <key>EnvironmentVariables</key><dict><key>PATH</key><string>$(esc "$PATH")</string></dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$(esc "$HOME/.reelfactory/dashboard.log")</string>
  <key>StandardErrorPath</key><string>$(esc "$HOME/.reelfactory/dashboard.log")</string>
</dict></plist>
PL
# stop a dashboard started the old way (unless a reel is being made)
if curl -s --max-time 2 http://127.0.0.1:8765/api/reels | grep -q '"busy": \[\]'; then
  lsof -ti tcp:8765 -sTCP:LISTEN | xargs kill 2>/dev/null; sleep 1
fi
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null
launchctl bootstrap "gui/$(id -u)" "$PLIST" && echo "Auto-start is ON." || { echo "Couldn't turn on auto-start. Send a screenshot of this window to Claude."; exit 1; }
OK=""
for i in $(seq 1 30); do [ "$(curl -s --max-time 1 -o /dev/null -w '%{http_code}' http://127.0.0.1:8765/api/reels)" = "200" ] && { OK=1; break; }; sleep 1; done
if [ -n "$OK" ]; then
  open http://127.0.0.1:8765/
  echo "Reel Factory now starts by itself when you log in, and restarts by itself if it ever stops."
  echo "Bookmark the page that just opened (Cmd+D). You can close this window."
else
  echo ""
  echo "PROBLEM: auto-start is on, but the dashboard didn't start. Send Claude a screenshot of this window."
  echo "------ auto-start log ------"
  tail -n 15 "$HOME/.reelfactory/dashboard.log" 2>/dev/null
  echo "------ what is using port 8765 ------"
  lsof -nP -i tcp:8765 -sTCP:LISTEN 2>/dev/null || echo "(nothing)"
  echo "------ auto-start status ------"
  launchctl print "gui/$(id -u)/$LABEL" 2>&1 | grep -E "state|last exit|runs|program|working directory|disabled" | head -8
  echo ""
  echo "Tip: open System Settings > General > Login Items and make sure 'bash' (Reel Factory) is allowed in the background."
  echo "Until this is fixed, double-click 'Reel Factory.command' to open the dashboard."
fi
