#!/usr/bin/env bash
# Sets up a daily cron job to run the tweet agent at 9:00 AM IST (3:30 AM UTC).
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

# 9:00 AM IST = 03:30 AM UTC
CRON_SCHEDULE="30 3 * * *"
CRON_CMD="$PYTHON_PATH $AGENT_PATH >> $LOG_FILE 2>&1"
CRON_ENTRY="$CRON_SCHEDULE $CRON_CMD"

if crontab -l 2>/dev/null | grep -qF "agent.py"; then
    echo "A tweet agent cron job already exists:"
    crontab -l | grep "agent.py"
    echo ""
    read -rp "Replace it? (y/N): " confirm
    if [[ "${confirm,,}" != "y" ]]; then
        echo "Aborted. No changes made."
        exit 0
    fi
    (crontab -l 2>/dev/null | grep -vF "agent.py") | crontab -
    echo "Removed existing entry."
fi

(crontab -l 2>/dev/null; echo "$CRON_ENTRY") | crontab -

echo ""
echo "Cron job installed! Tweet will post daily at 9:00 AM IST."
echo ""
echo "Verify with:  crontab -l"
echo "Watch logs:   tail -f $LOG_FILE"
echo "Remove:       crontab -e  (then delete the agent.py line)"
echo ""
echo "NOTE: On macOS, cron requires Full Disk Access."
echo "  System Settings → Privacy & Security → Full Disk Access → enable 'cron'"
