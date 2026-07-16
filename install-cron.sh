#!/usr/bin/env bash
# install-cron.sh — 一鍵安裝 jira-architect 定時 polling cron job（每 2 小時執行）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
POLL_SCRIPT="${SCRIPT_DIR}/scripts/poll.py"
LOG_FILE="\$HOME/.hermes/jira-architect/poll.log"
PYTHON="$(command -v python3)"

CRON_LINE="0 */2 * * * ${PYTHON} ${POLL_SCRIPT} >> ${LOG_FILE} 2>&1"

# Check if already installed
if crontab -l 2>/dev/null | grep -qF "jira-architect/scripts/poll.py"; then
    echo "✅ Cron job is already installed:"
    crontab -l | grep "poll.py"
    echo ""
    echo "To view logs : tail -f ~/.hermes/jira-architect/poll.log"
    echo "To remove    : crontab -e  (delete the jira-architect line)"
    exit 0
fi

# Append to existing crontab
( crontab -l 2>/dev/null; echo "${CRON_LINE}" ) | crontab -

echo "✅ Cron job installed (runs every 2 hours):"
echo "   ${CRON_LINE}"
echo ""
echo "Verify   : crontab -l | grep poll"
echo "View logs: tail -f ~/.hermes/jira-architect/poll.log"
echo "Test run : ${PYTHON} ${POLL_SCRIPT} --once --verbose"
echo ""
echo "To remove: crontab -e  (delete the jira-architect line)"
