#!/bin/bash
# 启动或重启 ai-progress-monitor 看板服务
# 供 LaunchAgent 开机自启 / 手动重启使用
set -e
REPO="/Users/mico/clacky_workspace/ai-progress-monitor"
LOG_DIR="$HOME/Library/Logs/ai-progress-monitor"
mkdir -p "$LOG_DIR"

# 清理占用端口的旧进程
lsof -ti tcp:8777 | xargs kill -9 2>/dev/null || true
sleep 1

cd "$REPO"
exec "$REPO/.venv/bin/python" "$REPO/server/dashboard.py" \
  >> "$LOG_DIR/dashboard.log" 2>&1