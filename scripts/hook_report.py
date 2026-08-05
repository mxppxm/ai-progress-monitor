#!/usr/bin/env python3
"""hook_report — 把各 AI 工作台的原生 hook 事件翻译成进度上报。

Hooks 由工作台运行时**自动触发**，无需 AI 自觉调 MCP 工具，上报更确定。
本脚本复用 server/db.py 的同一套 SQLite 数据层，与 MCP 方式写入同一张表。

支持两种调用方式：

  1. Claude Code 风格（推荐）—— 直接作为命令 hook，从 stdin 读 JSON：
        你的 CLI 配置里 command 指向本脚本，args 传 --agent <工作台名>，
        脚本会解析 stdin 里的 hook_event_name (SessionStart/PostToolUse/Stop/SessionEnd)
        以及 hook 附带字段，自动决定上报动作。

  2. 通用 CLI —— 手动/其它工作台调用：
        python hook_report.py --agent codex --event SessionStart --task_id codex-001 --name 我的任务
        python hook_report.py --agent claude --event Stop --message 收尾说明

用法示例（Claude Code 的 .claude/settings.json hooks 配置）：
    {
      "hooks": {
        "SessionStart": [{ "hooks": [{ "type": "command",
            "command": "python <repo_root>/scripts/hook_report.py --agent claude" }] }],
        "SessionEnd":   [{ "hooks": [{ "type": "command",
            "command": "python <repo_root>/scripts/hook_report.py --agent claude" }] }],
        "PostToolUse":  [{ "matcher": "Bash|Write|Edit",
            "hooks": [{ "type": "command",
            "command": "python <repo_root>/scripts/hook_report.py --agent claude" }] }],
        "Stop":         [{ "hooks": [{ "type": "command",
            "command": "python <repo_root>/scripts/hook_report.py --agent claude" }] }]
      }
    }
"""
import argparse
import json
import os
import sys
from pathlib import Path

# 让脚本能 import server 下的 db（无论从哪个目录调用）
REPO = Path(__file__).resolve().parent.parent
SERVER_DIR = REPO / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import db  # noqa: E402


# ── 事件 → 上报动作 ──────────────────────────────────────────────
def _task_id_for(agent: str, event: dict) -> str:
    """尽量从 hook 上下文里抽一个稳定的任务 ID。"""
    # 优先用户显式指定的 task_id
    explicit = event.get("task_id")
    if explicit:
        return explicit
    # 用会话 ID —— 一个会话对应一个任务，稳定且不重复
    sid = event.get("session_id")
    if sid:
        return f"{agent}-{sid[:8]}"
    # 兜底：按 agent 造一个递增 id
    import time
    return f"{agent}-{int(time.time())}"


def _task_name_for(agent: str, event: dict, task_id: str) -> str:
    """从 hook 上下文抽一个人类可读的任务名。"""
    name = event.get("name")
    if name:
        return name
    title = event.get("session_title")
    if title:
        return title
    cwd = event.get("cwd") or ""
    proj = Path(cwd).name if cwd else ""
    if proj:
        return f"{agent}: {proj}"
    return f"{agent} 会话任务"


def _handle_session_start(agent: str, event: dict) -> dict:
    task_id = _task_id_for(agent, event)
    name = _task_name_for(agent, event, task_id)
    task = db.record_task(task_id, agent, name)
    db.bump_version()
    return {"ok": True, "task_id": task_id, "action": "record_task", "task": task}


def _handle_post_tool_use(agent: str, event: dict) -> dict:
    """工具用完后：记一个 step 心跳节点，顺带把进度顶到可见。"""
    task_id = _task_id_for(agent, event)
    name = _task_name_for(agent, event, task_id)
    db.record_task(task_id, agent, name)  # 幂等：不存在则建
    tool = event.get("tool_name") or "tool"
    msg = f"执行了 {tool}"
    log = db.log_node(task_id, "step", msg, {"tool": tool})
    db.bump_version()
    if log is None:
        return {"ok": False, "error": "task 不存在"}
    return {"ok": True, "task_id": task_id, "action": "log_node", "node_type": "step"}


def _handle_stop(agent: str, event: dict) -> dict:
    """回合结束：把 Claude 的收尾消息记为 milestone 节点。"""
    task_id = _task_id_for(agent, event)
    name = _task_name_for(agent, event, task_id)
    db.record_task(task_id, agent, name)
    msg = event.get("last_assistant_message") or event.get("message") or "本轮结束"
    msg = msg.strip()[:200] or "回合完成为止"
    log = db.log_node(task_id, "milestone", msg, {"hook": "Stop"})
    db.bump_version()
    if log is None:
        return {"ok": False, "error": "task 不存在"}
    return {"ok": True, "task_id": task_id, "action": "log_node", "node_type": "milestone"}


def _handle_session_end(agent: str, event: dict) -> dict:
    """会话结束：把任务置为 paused，避免一直显示「运行中」。"""
    task_id = _task_id_for(agent, event)
    name = _task_name_for(agent, event, task_id)
    db.record_task(task_id, agent, name)
    task = db.update_progress(task_id, status="paused",
                              detail=f"会话结束（{event.get('reason', 'other')}）")
    db.bump_version()
    if task is None:
        return {"ok": False, "error": "task 不存在"}
    return {"ok": True, "task_id": task_id, "action": "pause"}


_HANDLERS = {
    "SessionStart": _handle_session_start,
    "PostToolUse": _handle_post_tool_use,
    "Stop": _handle_stop,
    "SessionEnd": _handle_session_end,
}


def _read_stdin_json() -> dict:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def main() -> int:
    ap = argparse.ArgumentParser(description="AI 工作台进度 hook 上报")
    ap.add_argument("--agent", required=True,
                    help="工作台名：claude / codex / cursor / opencode ...")
    ap.add_argument("--event", default=None,
                    help="强制指定事件：SessionStart/PostToolUse/Stop/SessionEnd"
                         "（缺省时自动从 stdin JSON 的 hook_event_name 解析）")
    ap.add_argument("--task_id", default=None, help="目标任务 ID（可选）")
    ap.add_argument("--name", default=None, help="任务名（可选）")
    ap.add_argument("--message", default=None, help="上报消息文本（可选）")
    args = ap.parse_args()

    db.init_db()

    # 合并 stdin JSON（Claude Code 风格）与显式参数，显式参数优先。
    # 只有当没显式 --event 时才读 stdin（避免交互终端下阻塞）。
    event = {}
    if args.event is None:
        event = _read_stdin_json()
    if args.task_id:
        event["task_id"] = args.task_id
    if args.name:
        event["name"] = args.name
    if args.message:
        event["message"] = args.message

    ev_name = args.event or event.get("hook_event_name")
    if not ev_name:
        # 无事件信息：静默忽略（首轮 SessionStart 之前的空调用不算错误）
        print(json.dumps({"ok": False, "error": "no event specified"}, ensure_ascii=False))
        return 0

    handler = _HANDLERS.get(ev_name)
    if not handler:
        print(json.dumps({"ok": False, "event": ev_name, "error": "unsupported event"},
                         ensure_ascii=False))
        return 0

    result = handler(args.agent, event)
    print(json.dumps(result, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())