#!/bin/bash
# Double-click to stop Reel Factory starting by itself. Use "Reel Factory.command" again to open it.
LABEL="com.reelfactory.dashboard"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
echo "Auto-start is OFF. Double-click Reel Factory.command when you want to use it."
