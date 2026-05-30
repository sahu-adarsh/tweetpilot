#!/usr/bin/env bash
# Sets up two daily cron windows for the tweet agent.
# Morning: 8:00-9:30 AM IST  |  Evening: 7:00-8:30 PM IST
# Each window has a 25% skip rate → ~10-11 posts/week (range 8-12).
# Run once: bash setup_cron.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_PATH="$SCRIPT_DIR/agent.py"
LOG_FILE="$SCRIPT_DIR/tweet_agent.log"

# Find the Python interpreter (prefer venv if active)
if [[ -n "${VIRTUAL_ENV:-}" ]]; then
    PYTHON_PATH="$VIRTUAL_ENV/bin/python"
elif command -v python3 &>/dev/null; then
    PYTHON_PATH="$(command -v python3)"
else
    echo "ERROR: python3 not found. Install Python 3 first."
    exit 1
fi

echo "Using Python: $PYTHON_PATH"
echo "Agent path:   $AGENT_PATH"
echo "Log file:     $LOG_FILE"
echo ""

CRON_CMD="$PYTHON_PATH $AGENT_PATH >> $LOG_FILE 2>&1"
# 8:00 AM IST = 02:30 UTC  |  7:00 PM IST = 13:30 UTC
MORNING_ENTRY="30 2 * * * $CRON_CMD"
EVENING_ENTRY="30 13 * * * $CRON_CMD"

if crontab -l 2>/dev/null | grep -qF "agent.py"; then
    echo "Existing tweet agent cron entries found:"
    crontab -l | grep "agent.py"
    echo ""
    read -rp "Replace them? (y/N): " confirm
    if [[ "${confirm,,}" != "y" ]]; then
        echo "Aborted. No changes made."
        exit 0
    fi
    (crontab -l 2>/dev/null | grep -vF "agent.py") | crontab -
    echo "Removed existing entries."
fi

(crontab -l 2>/dev/null; echo "$MORNING_ENTRY"; echo "$EVENING_ENTRY") | crontab -

echo ""
echo "Two cron windows installed:"
echo "  Morning: 8:00-9:30 AM IST"
echo "  Evening: 7:00-8:30 PM IST"
echo "  Target:  ~10 tweets/week (range 8-12)"
echo ""
echo "Verify with:  crontab -l"
echo "Watch logs:   tail -f $LOG_FILE"
echo "Remove:       crontab -e  (delete both agent.py lines)"
echo ""
echo "NOTE: On macOS, cron requires Full Disk Access."
echo "  System Settings → Privacy & Security → Full Disk Access → enable 'cron'"
