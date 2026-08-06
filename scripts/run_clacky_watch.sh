#!/bin/bash
# 启动或重启 Clacky 会话监听（自动上报看板）
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$HOME/Library/Logs/ai-progress-monitor"
mkdir -p "$LOG_DIR"

pkill -f "$REPO/scripts/clacky_session_watch.py" 2>/dev/null || true
sleep 0.5

cd "$REPO"
exec "$REPO/.venv/bin/python" "$REPO/scripts/clacky_session_watch.py" \
  >> "$LOG_DIR/clacky-watch.log" 2>&1
