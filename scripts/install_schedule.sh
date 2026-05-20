#!/bin/bash
# Install the Balboa morning briefing as a daily 7am launchd job.
# Run once: bash scripts/install_schedule.sh

PLIST="com.balboa.morning-briefing.plist"
SRC="$(cd "$(dirname "$0")" && pwd)/$PLIST"
DEST="$HOME/Library/LaunchAgents/$PLIST"

# Unload if already installed
launchctl unload "$DEST" 2>/dev/null

cp "$SRC" "$DEST"
launchctl load "$DEST"

echo "Scheduled. Balboa will send a morning briefing at 7:00am daily."
echo "To test now:  .venv/bin/python scripts/morning_briefing.py"
echo "To uninstall: launchctl unload ~/Library/LaunchAgents/$PLIST"
echo "Logs:         tail -f /tmp/balboa-briefing.log"
