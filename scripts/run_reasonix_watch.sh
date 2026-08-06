#!/bin/bash
# 启动或重启 Reasonix 会话监听（ask → 黄灯兜底）
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$HOME/Library/Logs/ai-progress-monitor"
mkdir -p "$LOG_DIR"

pkill -f "$REPO/scripts/reasonix_session_watch.py" 2>/dev/null || true
sleep 0.5

cd "$REPO"
exec "$REPO/.venv/bin/python" "$REPO/scripts/reasonix_session_watch.py" \
  >> "$LOG_DIR/reasonix-watch.log" 2>&1
