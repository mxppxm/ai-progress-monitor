#!/bin/bash
# Cursor hooks 入口：把 stdin JSON 转给 hook_report.py（agent=cursor）
# 用法：在 ~/.cursor/hooks.json 里 command 指向本脚本（把 <repo_root> 换成真实路径）
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/.." && pwd)"
PY="$REPO/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3.12 || command -v python3)"
fi
exec "$PY" "$REPO/scripts/hook_report.py" --agent cursor
