#!/bin/bash
# Double-click once: Reel Factory then starts by itself every time you log in to your Mac.
# It opens Reel Factory and shows its links. Undo with "Turn off auto-start.command".
cd "$(dirname "$0")" || exit 1
HERE="$(pwd -P)"
LABEL="com.reelfactory.dashboard"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
mkdir -p "$HOME/Library/LaunchAgents" "$HOME/.reelfactory"
chmod +x scripts/autostart.sh
. scripts/rf_port.sh                    # Reel Factory's own address (never Content Workshop's)
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
if curl -s --max-time 2 "$URL/api/reels" | grep -q '"busy": \[\]'; then
  lsof -ti tcp:$RF_PORT -sTCP:LISTEN | xargs kill 2>/dev/null; sleep 1
fi
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null
launchctl bootstrap "gui/$(id -u)" "$PLIST" && echo "Auto-start is ON." || { echo "Couldn't turn on auto-start. Send a screenshot of this window to Claude."; exit 1; }
OK=""
for i in $(seq 1 30); do is_rf "$RF_PORT" && { OK=1; break; }; sleep 1; done
if [ -n "$OK" ]; then
  open_browser
  show_links
  echo "It now starts by itself when you log in, and restarts by itself if it ever stops."
  echo "You can close this window."
else
  echo ""
  echo "PROBLEM: auto-start is on, but the dashboard didn't start. Send Claude a screenshot of this window."
  echo "------ auto-start log ------"
  tail -n 15 "$HOME/.reelfactory/dashboard.log" 2>/dev/null
  echo "------ what is using port $RF_PORT ------"
  lsof -nP -i tcp:$RF_PORT -sTCP:LISTEN 2>/dev/null || echo "(nothing)"
  echo "------ auto-start status ------"
  launchctl print "gui/$(id -u)/$LABEL" 2>&1 | grep -E "state|last exit|runs|program|working directory|disabled" | head -8
  echo ""
  echo "Tip: open System Settings > General > Login Items and make sure 'bash' (Reel Factory) is allowed in the background."
  echo ""
  echo "Starting the dashboard from this folder for now, so you can keep working..."
  RF_DASH_PORT=$RF_PORT nohup python3 dashboard/serve.py > dashboard/server.log 2>&1 &
  for i in $(seq 1 20); do is_rf "$RF_PORT" && break; sleep 1; done
  open_browser
  show_links
fi
