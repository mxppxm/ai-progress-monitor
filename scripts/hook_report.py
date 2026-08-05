#!/usr/bin/env python3
"""hook_report — 把各 AI 工作台的原生 hook 事件翻译成进度上报。

Hooks 由工作台运行时**自动触发**，无需 AI 自觉调 MCP 工具，上报更确定。
本脚本复用 server/db.py 的同一套 SQLite 数据层，与 MCP 方式写入同一张表。

语义（与看板三态对齐）：
  - 开始/继续对话 → running；重启时标题改为本轮用户提示词
  - 停止输出（stop）→ done；若末条回复含拍板用语 → pending（黄灯）
  - 再发消息 → 同一 task 重启为 running，标题跟新提示词

支持两种调用方式：

  1. Claude Code 风格（推荐）—— 直接作为命令 hook，从 stdin 读 JSON：
        你的 CLI 配置里 command 指向本脚本，args 传 --agent <工作台名>，
        脚本会解析 stdin 里的 hook_event_name 以及 hook 附带字段，自动决定上报动作。

  2. 通用 CLI —— 手动/其它工作台调用：
        python hook_report.py --agent codex --event SessionStart --task_id codex-001 --name 我的任务
        python hook_report.py --agent claude --event Stop --message 收尾说明
"""
import argparse
import json
import sys
from pathlib import Path

# 让脚本能 import server 下的 db（无论从哪个目录调用）
REPO = Path(__file__).resolve().parent.parent
SERVER_DIR = REPO / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import db  # noqa: E402
import notify  # noqa: E402

# 新建空会话时注入：提醒模型用拍板用语触发黄灯（hooks 路径无需 MCP 规则）
_CHOICE_HINT = (
    "【进度看板】若需要用户拍板/二选一，请在回复里明确写上「需要你选择」或「你来决定」，"
    "看板会亮黄灯；停止输出即视为本轮结束，用户继续对话会自动重启任务。"
)


# ── 事件 → 上报动作 ──────────────────────────────────────────────
def _task_id_for(agent: str, event: dict) -> str:
    """尽量从 hook 上下文里抽一个稳定的任务 ID。"""
    explicit = event.get("task_id")
    if explicit:
        return explicit
    sid = event.get("session_id")
    if sid:
        return f"{agent}-{sid[:8]}"
    import time
    return f"{agent}-{int(time.time())}"


def _user_prompt(event: dict) -> str:
    """各工作台用户提示词字段兼容（Cursor prompt / Codex UserPromptSubmit 等）。"""
    for key in ("prompt", "user_prompt", "content"):
        val = event.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    # CLI / 显式 name 也算「本轮标题」
    name = event.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return ""


def _title_from_prompt(prompt: str, limit: int = 100) -> str:
    """用提示词首行做看板标题，过长截断。"""
    one = prompt.splitlines()[0].strip() or prompt.strip()
    one = " ".join(one.split())  # 压空白，看板更清晰
    if len(one) > limit:
        return one[: limit - 1] + "…"
    return one


def _task_name_for(agent: str, event: dict, task_id: str) -> str:
    """从 hook 上下文抽一个人类可读的任务名（优先本轮用户提示词）。"""
    prompt = _user_prompt(event)
    if prompt:
        return _title_from_prompt(prompt)
    title = event.get("session_title")
    if isinstance(title, str) and title.strip():
        return title.strip()[:100]
    cwd = event.get("cwd") or ""
    proj = Path(cwd).name if cwd else ""
    if proj:
        return f"{agent}: {proj}"
    return f"{agent} 会话任务"


def _assistant_text(event: dict) -> str:
    """各工作台末条助手文案字段兼容。"""
    for key in ("last_assistant_message", "text", "message", "agent_message"):
        val = event.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _notify_after_log(task_id: str, node_type: str, message: str) -> None:
    task = db.get_task(task_id)
    if not task:
        return
    if db.is_choice_message(message):
        notify.notify_choice(task["agent"], task["name"], message)
    else:
        notify.notify_node(task["agent"], task["name"], node_type, message)


def _ensure_task(agent: str, event: dict) -> tuple[str, dict | None]:
    """保证任务存在；不把已有状态强行改成 running（结束/黄灯路径用）。"""
    task_id = _task_id_for(agent, event)
    name = _task_name_for(agent, event, task_id)
    existing = db.get_task(task_id)
    if existing is None:
        db.record_task(task_id, agent, name)
        existing = db.get_task(task_id)
    return task_id, existing


def _handle_session_start(agent: str, event: dict) -> dict:
    """用户点发送 / 会话开始：建任务或重启为 running；有新提示词则改标题。"""
    task_id = _task_id_for(agent, event)
    name = _task_name_for(agent, event, task_id)
    # 仅当本轮带了真实提示词才改标题，避免无 prompt 的兜底名覆盖旧标题
    update_name = bool(_user_prompt(event))
    task = db.record_task(task_id, agent, name, update_name=update_name)
    db.bump_version()
    return {"ok": True, "task_id": task_id, "action": "record_task", "task": task}


def _handle_inject_hint(agent: str, event: dict) -> dict:
    """空会话开始：只注入黄灯用语提示，不建任务（Cursor sessionStart / Codex SessionStart）。"""
    ev = event.get("hook_event_name") or "SessionStart"
    return {
        "ok": True,
        "action": "inject_hint",
        # Cursor
        "additional_context": _CHOICE_HINT,
        # Codex SessionStart
        "hookSpecificOutput": {
            "hookEventName": ev if ev not in ("sessionStart",) else "SessionStart",
            "additionalContext": _CHOICE_HINT,
        },
    }


def _handle_post_tool_use(agent: str, event: dict) -> dict:
    """工具用完后：记一个 step 心跳节点。"""
    task_id = _task_id_for(agent, event)
    name = _task_name_for(agent, event, task_id)
    # 心跳不改标题（无用户提示词时兜底名会污染看板）
    db.record_task(task_id, agent, name, update_name=False)
    tool = event.get("tool_name") or "tool"
    msg = f"执行了 {tool}"
    log = db.log_node(task_id, "step", msg, {"tool": tool})
    db.bump_version()
    if log is None:
        return {"ok": False, "error": "task 不存在"}
    return {"ok": True, "task_id": task_id, "action": "log_node", "node_type": "step"}


def _handle_after_agent_response(agent: str, event: dict) -> dict:
    """助手一条消息写完：若含拍板用语 → 黄灯 pending（stop 时会保留）。"""
    text = _assistant_text(event)
    if not text or not db.is_choice_message(text):
        return {"ok": True, "action": "skip", "reason": "no choice keywords"}
    task_id, _ = _ensure_task(agent, event)
    msg = text[:200]
    log = db.log_node(task_id, "step", msg, {"hook": "AfterAgentResponse"})
    db.bump_version()
    if log is None:
        return {"ok": False, "error": "task 不存在"}
    _notify_after_log(task_id, "step", msg)
    return {"ok": True, "task_id": task_id, "action": "pending", "node_type": "step"}


def _handle_stop(agent: str, event: dict) -> dict:
    """停止输出＝本轮结束：默认 success/done；末条含拍板用语或已 pending → 黄灯。"""
    task_id, existing = _ensure_task(agent, event)
    text = _assistant_text(event)
    hook_status = (event.get("status") or "").lower()
    was_pending = bool(existing and existing.get("status") == "pending")

    # 已因 afterAgentResponse 亮黄灯，或本条 stop 自带拍板文案 → 保持/设为 pending
    if was_pending or db.is_choice_message(text):
        msg = (text[:200] if text else None) or "等待你选择"
        log = db.log_node(task_id, "step", msg, {"hook": "Stop", "choice": True})
        db.bump_version()
        if log is None:
            return {"ok": False, "error": "task 不存在"}
        if not was_pending:
            _notify_after_log(task_id, "step", msg)
        return {"ok": True, "task_id": task_id, "action": "pending", "node_type": "step"}

    if hook_status == "error":
        msg = (text[:200] if text else None) or "本轮出错结束"
        log = db.log_node(task_id, "fail", msg, {"hook": "Stop", "status": hook_status})
        db.bump_version()
        if log is None:
            return {"ok": False, "error": "task 不存在"}
        _notify_after_log(task_id, "fail", msg)
        return {"ok": True, "task_id": task_id, "action": "log_node", "node_type": "fail"}

    msg = (text[:200] if text else None) or "本轮结束"
    if hook_status == "aborted":
        msg = (text[:200] if text else None) or "本轮已中止"
    log = db.log_node(task_id, "success", msg, {"hook": "Stop", "status": hook_status or "completed"})
    db.bump_version()
    if log is None:
        return {"ok": False, "error": "task 不存在"}
    _notify_after_log(task_id, "success", msg)
    return {"ok": True, "task_id": task_id, "action": "log_node", "node_type": "success"}


def _handle_session_end(agent: str, event: dict) -> dict:
    """关会话：已结束/待选择保持；仍在 running 则标 done（等同停输出）。"""
    task_id = _task_id_for(agent, event)
    existing = db.get_task(task_id)
    if existing is None:
        return {"ok": True, "action": "skip", "reason": "no task"}
    st = existing.get("status")
    if st in ("done", "failed", "pending"):
        return {"ok": True, "task_id": task_id, "action": "keep", "status": st}

    reason = event.get("reason") or "other"
    msg = f"会话结束（{reason}）"
    log = db.log_node(task_id, "success", msg, {"hook": "SessionEnd", "reason": reason})
    db.bump_version()
    if log is None:
        return {"ok": False, "error": "task 不存在"}
    _notify_after_log(task_id, "success", msg)
    return {"ok": True, "task_id": task_id, "action": "log_node", "node_type": "success"}


_HANDLERS = {
    "SessionStart": _handle_session_start,
    "InjectHint": _handle_inject_hint,
    "PostToolUse": _handle_post_tool_use,
    "AfterAgentResponse": _handle_after_agent_response,
    "Stop": _handle_stop,
    "SessionEnd": _handle_session_end,
}

# 各工作台事件名 → 本脚本统一名
_EVENT_ALIASES = {
    # Cursor（camelCase）
    "sessionStart": "InjectHint",             # 空会话只注入提示，不建任务
    "beforeSubmitPrompt": "SessionStart",     # 用户点发送才建/重启任务
    "sessionEnd": "SessionEnd",
    "postToolUse": "PostToolUse",
    "afterAgentResponse": "AfterAgentResponse",
    "stop": "Stop",
    # Codex / Claude 风格
    "UserPromptSubmit": "SessionStart",       # 用户提交提示词 → 建/重启 + 改标题
}


def _resolve_event(agent: str, raw_ev: str) -> str:
    """解析事件；Codex 的 SessionStart 只注入提示（建任务改走 UserPromptSubmit）。"""
    if agent == "codex" and raw_ev == "SessionStart":
        return "InjectHint"
    return _EVENT_ALIASES.get(raw_ev, raw_ev)


def _normalize_event(event: dict) -> dict:
    """兼容 Cursor / Claude 等不同工作台的 hook 字段。"""
    out = dict(event)
    # Cursor: conversation_id ≈ session_id
    if not out.get("session_id") and out.get("conversation_id"):
        out["session_id"] = out["conversation_id"]
    # Cursor: workspace_roots[0] 可当 cwd
    if not out.get("cwd"):
        roots = out.get("workspace_roots") or []
        if roots:
            out["cwd"] = roots[0]
    # Cursor stop: status → message 兜底（无正文时）
    if not out.get("message") and out.get("status") and not out.get("text"):
        out["message"] = f"本轮结束（{out['status']}）"
    return out


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
                    help="强制指定事件：SessionStart/PostToolUse/Stop/SessionEnd/…"
                         "（缺省时自动从 stdin JSON 的 hook_event_name 解析）")
    ap.add_argument("--task_id", default=None, help="目标任务 ID（可选）")
    ap.add_argument("--name", default=None, help="任务名（可选）")
    ap.add_argument("--message", default=None, help="上报消息文本（可选）")
    args = ap.parse_args()

    db.init_db()

    # 合并 stdin JSON（Claude / Cursor 风格）与显式参数，显式参数优先。
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

    event = _normalize_event(event)

    raw_ev = args.event or event.get("hook_event_name")
    if not raw_ev:
        print(json.dumps({"ok": False, "error": "no event specified"}, ensure_ascii=False))
        return 0

    ev_name = _resolve_event(args.agent, raw_ev)
    handler = _HANDLERS.get(ev_name)
    if not handler:
        print(json.dumps({"ok": False, "event": raw_ev, "error": "unsupported event"},
                         ensure_ascii=False))
        return 0

    result = handler(args.agent, event)
    print(json.dumps(result, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
