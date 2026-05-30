#!/usr/bin/env bash
# Installs a launchd agent to run the tweet agent twice daily.
# Unlike cron, launchd queues missed jobs and runs them when the Mac wakes from sleep.
# Run once: bash setup_launchd.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_PATH="$SCRIPT_DIR/agent.py"
LOG_FILE="$SCRIPT_DIR/tweet_agent.log"
PLIST_LABEL="com.tweetpilot"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_LABEL.plist"

# Use the Python that has the packages installed
PYTHON_PATH="/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"
if [ ! -f "$PYTHON_PATH" ]; then
    PYTHON_PATH="$(command -v python3)"
fi

echo "Python:   $PYTHON_PATH"
echo "Agent:    $AGENT_PATH"
echo "Plist:    $PLIST_PATH"
echo "Log:      $LOG_FILE"
echo ""

# Unload existing plist if already installed
if launchctl list | grep -q "$PLIST_LABEL" 2>/dev/null; then
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
    echo "Unloaded existing launchd agent."
fi

mkdir -p "$HOME/Library/LaunchAgents"

# Write the plist — launchd uses LOCAL time (IST), no UTC conversion needed
cat > "$PLIST_PATH" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$PLIST_LABEL</string>

    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON_PATH</string>
        <string>$AGENT_PATH</string>
    </array>

    <key>StartCalendarInterval</key>
    <array>
        <dict>
            <key>Hour</key><integer>8</integer>
            <key>Minute</key><integer>30</integer>
        </dict>
        <dict>
            <key>Hour</key><integer>19</integer>
            <key>Minute</key><integer>0</integer>
        </dict>
    </array>

    <key>StandardOutPath</key>
    <string>$LOG_FILE</string>
    <key>StandardErrorPath</key>
    <string>$LOG_FILE</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
        <key>HOME</key>
        <string>$HOME</string>
    </dict>
</dict>
</plist>
EOF

launchctl load "$PLIST_PATH"

# Remove old cron entries now that launchd takes over
if crontab -l 2>/dev/null | grep -qF "agent.py"; then
    (crontab -l 2>/dev/null | grep -vF "agent.py") | crontab -
    echo "Removed old cron entries."
fi

echo ""
echo "launchd agent installed!"
echo ""
echo "Schedule (IST, local time):"
echo "  Morning: 8:30 AM"
echo "  Evening: 7:00 PM"
echo "  Missed jobs fire on next wake — no tweets lost to sleep."
echo ""
echo "Useful commands:"
echo "  Status:  launchctl list | grep tweetpilot"
echo "  Logs:    tail -f $LOG_FILE"
echo "  Unload:  launchctl unload $PLIST_PATH"
echo "  Reload:  launchctl unload $PLIST_PATH && launchctl load $PLIST_PATH"
