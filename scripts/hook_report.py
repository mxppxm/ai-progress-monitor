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
import re
import sys
from pathlib import Path

# 让脚本能 import server 下的 db（无论从哪个目录调用）
REPO = Path(__file__).resolve().parent.parent
SERVER_DIR = REPO / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import db  # noqa: E402
import notify  # noqa: E402

# 新建空会话时注入：提醒模型用拍板用语 / ask 工具触发黄灯（hooks 路径无需 MCP 规则）
_CHOICE_HINT = (
    "【进度看板】若需要用户拍板/二选一，请优先调用 ask 工具让用户点选；"
    "或在回复里明确写上「需要你选择」或「你来决定」。看板会亮黄灯；"
    "停止输出即视为本轮结束，用户继续对话会自动重启任务。"
)


# ── 事件 → 上报动作 ──────────────────────────────────────────────
def _session_suffix(sid: str) -> str:
    """从 session id 抽出够用的短后缀。

    Cursor/Codex 的 UUID 取前 8 位即可。
    Reasonix BranchID 形如 `20260806-094200.479088000-fxb-deepseek-v4-flash`：
    保留到小数秒 `YYYYMMDD-HHMMSS.fffffffff`，同一会话稳定且同秒不撞车。
    """
    s = str(sid).strip()
    m = re.match(r"^(\d{8}-\d{6}\.\d+)", s)
    if m:
        return m.group(1)
    m = re.match(r"^(\d{8}-\d{6})", s)
    if m:
        return m.group(1)
    return s[:8]


def _reasonix_fallback_task_id(event: dict) -> str | None:
    """hooks 偶发缺 sessionId 时，复用最近活跃的 reasonix 任务，避免每轮新卡。"""
    try:
        for t in db.list_tasks(limit=50):
            if t.get("agent") != "reasonix":
                continue
            if t.get("status") not in ("running", "pending"):
                continue
            return t["task_id"]
    except Exception:
        return None
    return None


def _task_id_for(agent: str, event: dict) -> str:
    """尽量从 hook 上下文里抽一个稳定的任务 ID。"""
    explicit = event.get("task_id")
    if explicit:
        return explicit
    sid = event.get("session_id")
    if sid:
        suffix = _session_suffix(sid)
        tid = f"{agent}-{suffix}"
        # Reasonix：兼容旧卡（只有到秒、无小数段）
        if agent == "reasonix" and "." in suffix:
            short = f"{agent}-{suffix.split('.', 1)[0]}"
            if db.get_task(short) and not db.get_task(tid):
                return short
        return tid
    if agent == "reasonix":
        fb = _reasonix_fallback_task_id(event)
        if fb:
            return fb
    import time
    return f"{agent}-{int(time.time())}"


def _resume_task(agent: str, task_id: str, existing: dict | None) -> dict:
    """把 pending 收回为 running（ask 已答）。"""
    name = (existing or {}).get("name") or f"{agent} 会话任务"
    db.record_task(task_id, agent, name, update_name=False)
    db.bump_version()
    return {"ok": True, "task_id": task_id, "action": "resume"}


def _user_prompt(event: dict) -> str:
    """各工作台用户提示词字段兼容（Cursor prompt / Codex UserPromptSubmit 等）。"""
    for key in ("prompt", "user_prompt", "content"):
        val = event.get(key)
        if isinstance(val, str) and val.strip():
            return _strip_hook_context(val)
    # CLI / 显式 name 也算「本轮标题」
    name = event.get("name")
    if isinstance(name, str) and name.strip():
        return _strip_hook_context(name)
    return ""


_REASONIX_META_TAGS = (
    "hook-context",
    "reasoning-language",
    "response-language",
)

# Reasonix 会把 SessionStart / 语言偏好等包进 <tag>...</tag>，再拼到用户原文前面
_REASONIX_META_BLOCK_RE = re.compile(
    r"<(" + "|".join(re.escape(t) for t in _REASONIX_META_TAGS) + r")\b[^>]*>.*?</\1>",
    re.DOTALL | re.IGNORECASE,
)
_REASONIX_META_LINE_RE = re.compile(
    r"^\s*</?(?:" + "|".join(re.escape(t) for t in _REASONIX_META_TAGS) + r")\b[^>]*>\s*$",
    re.IGNORECASE,
)


def _strip_hook_context(text: str) -> str:
    """去掉 Reasonix 注入的 meta 标签，只留真实用户话。"""
    cleaned = _REASONIX_META_BLOCK_RE.sub("", text)
    lines = []
    for line in cleaned.splitlines():
        if _REASONIX_META_LINE_RE.match(line):
            continue
        # 其它纯标签行（如残缺开标签）也不当标题
        s = line.strip()
        if s.startswith("<") and s.endswith(">") and " " not in s[1:-1].replace("-", ""):
            # 形如 <foo> / </foo> / <foo-bar>
            inner = s.strip("<>/")
            if re.fullmatch(r"[A-Za-z][\w-]*", inner or ""):
                continue
        if not s:
            if lines and lines[-1] != "":
                lines.append("")
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _title_from_prompt(prompt: str, limit: int = 100) -> str:
    """用提示词首行做看板标题，过长截断。"""
    prompt = _strip_hook_context(prompt)
    if not prompt:
        return ""
    # 跳过仍像标签的行，取第一句真人话
    one = ""
    for line in prompt.splitlines():
        s = line.strip()
        if not s or s.startswith("<"):
            continue
        one = s
        break
    if not one:
        one = prompt.strip()
    one = " ".join(one.split())  # 压空白，看板更清晰
    if len(one) > limit:
        return one[: limit - 1] + "…"
    return one


def _task_name_for(agent: str, event: dict, task_id: str) -> str:
    """从 hook 上下文抽一个人类可读的任务名（优先本轮用户提示词）。"""
    prompt = _user_prompt(event)
    if prompt:
        title = _title_from_prompt(prompt)
        if title:
            return title
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
    for key in (
        "last_assistant_message",
        "lastAssistantText",  # Reasonix
        "text",
        "message",
        "agent_message",
    ):
        val = event.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _notify_after_log(task_id: str, node_type: str, message: str) -> None:
    task = db.get_task(task_id)
    if not task:
        return
    if db.is_choice_message(message):
        notify.notify_choice(task["agent"], task["name"], message, task_id=task_id)
    else:
        notify.notify_node(task["agent"], task["name"], node_type, message, task_id=task_id)


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
    ev = event.get("hook_event_name") or event.get("event") or "SessionStart"
    if ev in ("sessionStart",):
        ev = "SessionStart"
    return {
        "ok": True,
        "action": "inject_hint",
        # Cursor
        "additional_context": _CHOICE_HINT,
        # Codex / Reasonix SessionStart：stdout 需带 hookSpecificOutput
        "hookSpecificOutput": {
            "hookEventName": ev,
            "additionalContext": _CHOICE_HINT,
        },
    }


def _tool_name(event: dict) -> str:
    return str(event.get("tool_name") or event.get("toolName") or "").strip()


def _tool_args(event: dict) -> dict:
    raw = event.get("tool_args")
    if raw is None:
        raw = event.get("toolArgs")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _ask_summary(event: dict) -> str:
    """从 Reasonix ask 工具参数抽出可读的待选摘要。"""
    args = _tool_args(event)
    questions = args.get("questions") or []
    parts: list[str] = []
    if isinstance(questions, list):
        for q in questions[:3]:
            if not isinstance(q, dict):
                continue
            prompt = str(q.get("question") or q.get("header") or "").strip()
            opts = q.get("options") or []
            labels = []
            if isinstance(opts, list):
                for o in opts[:4]:
                    if isinstance(o, dict) and o.get("label"):
                        labels.append(str(o["label"]).strip())
                    elif isinstance(o, str) and o.strip():
                        labels.append(o.strip())
            if prompt and labels:
                parts.append(f"{prompt}（{' / '.join(labels)}）")
            elif prompt:
                parts.append(prompt)
    if parts:
        return "需要你选择：" + "；".join(parts)
    return "需要你选择"


def _handle_pre_tool_use(agent: str, event: dict) -> dict:
    """工具执行前：Reasonix ask 弹选择卡 → 立刻黄灯。"""
    tool = _tool_name(event).lower()
    if tool != "ask":
        return {"ok": True, "action": "skip", "reason": "not_ask"}
    task_id = _task_id_for(agent, event)
    existing = db.get_task(task_id)
    if existing is None:
        # ask 出现时通常已有会话；没有则建一张兜底卡
        name = _task_name_for(agent, event, task_id)
        db.record_task(task_id, agent, name)
    msg = _ask_summary(event)[:500]
    log = db.log_node(task_id, "step", msg, {"hook": "PreToolUse", "tool": "ask", "choice": True})
    db.bump_version()
    if log is None:
        return {"ok": False, "error": "task 不存在"}
    _notify_after_log(task_id, "step", msg)
    return {"ok": True, "task_id": task_id, "action": "pending", "node_type": "step"}


def _handle_post_tool_use(agent: str, event: dict) -> dict:
    """工具心跳：只更新已有 running/pending 任务，绝不新建。

    Cursor 的 Task 子代理会带自己的 conversation_id 打 postToolUse，
    若这里建任务，子代理又常常不走 stop，就会留下「只有开始没有结束」的孤儿卡。
    """
    task_id = _task_id_for(agent, event)
    existing = db.get_task(task_id)
    if existing is None:
        return {"ok": True, "action": "skip", "reason": "no_task"}
    if existing.get("status") not in ("running", "pending"):
        return {"ok": True, "action": "skip", "reason": "not_active"}
    tool = _tool_name(event) or "tool"
    # Reasonix：用户答完 ask → 黄灯收回为运行中
    if tool.lower() == "ask":
        if existing.get("status") == "pending":
            return _resume_task(agent, task_id, existing)
        return {"ok": True, "task_id": task_id, "action": "skip", "reason": "ask_done"}
    msg = f"执行了 {tool}"
    log = db.log_node(task_id, "step", msg, {"tool": tool, "heartbeat": True})
    if log is None:
        return {"ok": False, "error": "task 不存在"}
    # 心跳不 bump：避免 SSE 高频整板重绘
    return {"ok": True, "task_id": task_id, "action": "log_node", "node_type": "step"}


def _handle_notification(agent: str, event: dict) -> dict:
    """Reasonix Notification：仅当文案本身是拍板意图时亮黄灯。

    工具审批（approval needed: bash …）不算用户二选一，避免误黄灯。
    """
    msg = str(event.get("message") or "").strip()
    if not msg:
        return {"ok": True, "action": "skip", "reason": "empty"}
    task_id = _task_id_for(agent, event)
    existing = db.get_task(task_id)
    if existing is None:
        return {"ok": True, "action": "skip", "reason": "no_task"}
    if not db.is_choice_message(msg):
        # 审批类通知只刷新 detail，不改状态
        db.update_progress(task_id, detail=msg[:500])
        db.bump_version()
        return {"ok": True, "task_id": task_id, "action": "detail"}
    log = db.log_node(
        task_id, "step", msg[:500],
        {"hook": "Notification", "choice": True},
    )
    db.bump_version()
    if log is None:
        return {"ok": False, "error": "task 不存在"}
    _notify_after_log(task_id, "step", msg[:500])
    return {"ok": True, "task_id": task_id, "action": "pending", "node_type": "step"}


def _handle_after_agent_response(agent: str, event: dict) -> dict:
    """助手一条消息写完：始终写入 detail（供看板展示末条）；含拍板用语 → 黄灯。"""
    text = _assistant_text(event)
    if not text:
        return {"ok": True, "action": "skip", "reason": "empty"}
    task_id = _task_id_for(agent, event)
    if db.get_task(task_id) is None:
        # 无主会话（常见于 subagent）不建卡
        return {"ok": True, "action": "skip", "reason": "no_task"}
    msg = text[:500]
    if db.is_choice_message(text):
        log = db.log_node(task_id, "step", msg, {"hook": "AfterAgentResponse", "choice": True})
        db.bump_version()
        if log is None:
            return {"ok": False, "error": "task 不存在"}
        _notify_after_log(task_id, "step", msg)
        return {"ok": True, "task_id": task_id, "action": "pending", "node_type": "step"}

    # 非拍板：只更新 detail，不刷节点、不改状态
    updated = db.update_progress(task_id, detail=msg)
    db.bump_version()
    if updated is None:
        return {"ok": False, "error": "task 不存在"}
    return {"ok": True, "task_id": task_id, "action": "detail", "detail": msg}


def _stop_display_text(event: dict, existing: dict | None) -> str:
    """Stop 载荷往往没有助手正文；优先用真实 text，否则沿用已有 detail。"""
    text = _assistant_text(event).strip()
    if text and not text.startswith("本轮结束"):
        return text[:500]
    prev = ((existing or {}).get("detail") or "").strip()
    if prev and not prev.startswith("本轮结束"):
        return prev[:500]
    return ""


def _handle_stop(agent: str, event: dict) -> dict:
    """停止输出＝本轮结束。

    Reasonix 一个会话一张卡：Stop 只更新 detail / 保持黄灯，不标 done；
    真正结束交给 SessionEnd。其它工作台仍是 Stop → done。
    """
    task_id = _task_id_for(agent, event)
    existing = db.get_task(task_id)
    if existing is None:
        return {"ok": True, "action": "skip", "reason": "no_task"}
    hook_status = (event.get("status") or "").lower()
    was_pending = bool(existing.get("status") == "pending")
    snippet = _stop_display_text(event, existing)

    # 已因 afterAgentResponse 亮黄灯，或本条 stop 自带拍板文案 → 保持/设为 pending
    if was_pending or db.is_choice_message(snippet):
        msg = snippet or "等待你选择"
        log = db.log_node(task_id, "step", msg, {"hook": "Stop", "choice": True})
        db.bump_version()
        if log is None:
            return {"ok": False, "error": "task 不存在"}
        if not was_pending:
            _notify_after_log(task_id, "step", msg)
        return {"ok": True, "task_id": task_id, "action": "pending", "node_type": "step"}

    # Reasonix：回合结束但会话还在 → 保持 running，只刷新末条
    if agent == "reasonix":
        if hook_status == "error":
            msg = snippet or "本轮出错"
            log = db.log_node(task_id, "fail", msg, {"hook": "Stop", "status": hook_status})
            db.bump_version()
            if log is None:
                return {"ok": False, "error": "task 不存在"}
            _notify_after_log(task_id, "fail", msg)
            return {"ok": True, "task_id": task_id, "action": "log_node", "node_type": "fail"}
        if snippet:
            db.update_progress(task_id, detail=snippet)
            if existing.get("status") != "running":
                db.record_task(
                    task_id, agent, existing.get("name") or "reasonix 会话",
                    update_name=False,
                )
            db.bump_version()
        return {"ok": True, "task_id": task_id, "action": "turn_idle", "detail": snippet}

    if hook_status == "error":
        msg = snippet or "本轮出错结束"
        log = db.log_node(task_id, "fail", msg, {"hook": "Stop", "status": hook_status})
        db.bump_version()
        if log is None:
            return {"ok": False, "error": "task 不存在"}
        _notify_after_log(task_id, "fail", msg)
        return {"ok": True, "task_id": task_id, "action": "log_node", "node_type": "fail"}

    msg = snippet or ("本轮已中止" if hook_status == "aborted" else "本轮结束")
    log = db.log_node(task_id, "success", msg, {"hook": "Stop", "status": hook_status or "completed"})
    db.bump_version()
    if log is None:
        return {"ok": False, "error": "task 不存在"}
    _notify_after_log(task_id, "success", msg)
    return {"ok": True, "task_id": task_id, "action": "log_node", "node_type": "success"}


def _handle_session_end(agent: str, event: dict) -> dict:
    """关会话：已结束保持；pending/running 都标 done（会话真正关掉）。"""
    task_id = _task_id_for(agent, event)
    existing = db.get_task(task_id)
    if existing is None:
        return {"ok": True, "action": "skip", "reason": "no task"}
    st = existing.get("status")
    if st in ("done", "failed"):
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
    "PreToolUse": _handle_pre_tool_use,
    "PostToolUse": _handle_post_tool_use,
    "AfterAgentResponse": _handle_after_agent_response,
    "Stop": _handle_stop,
    "SessionEnd": _handle_session_end,
    "Notification": _handle_notification,
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
    "subagentStop": "Stop",  # 子代理结束；若曾误建卡则收尾，无卡则 skip
    # Codex / Claude / Reasonix 风格
    "UserPromptSubmit": "SessionStart",       # 用户提交提示词 → 建/重启 + 改标题
    "SubagentStop": "Stop",
}


def _resolve_event(agent: str, raw_ev: str) -> str:
    """解析事件；Codex / Reasonix 的 SessionStart 只注入提示（建任务改走 UserPromptSubmit）。"""
    if agent in ("codex", "reasonix") and raw_ev == "SessionStart":
        return "InjectHint"
    return _EVENT_ALIASES.get(raw_ev, raw_ev)


def _normalize_event(event: dict) -> dict:
    """兼容 Cursor / Claude / Reasonix 等不同工作台的 hook 字段。"""
    out = dict(event)
    # Reasonix: event ≈ hook_event_name
    if not out.get("hook_event_name") and out.get("event"):
        out["hook_event_name"] = out["event"]
    # Cursor: conversation_id ≈ session_id；Reasonix: sessionId
    if not out.get("session_id"):
        if out.get("conversation_id"):
            out["session_id"] = out["conversation_id"]
        elif out.get("sessionId"):
            out["session_id"] = out["sessionId"]
    # Reasonix camelCase 工具字段
    if not out.get("tool_name") and out.get("toolName"):
        out["tool_name"] = out["toolName"]
    if out.get("tool_args") is None and out.get("toolArgs") is not None:
        out["tool_args"] = out["toolArgs"]
    # Cursor: workspace_roots[0] 可当 cwd
    if not out.get("cwd"):
        roots = out.get("workspace_roots") or []
        if roots:
            out["cwd"] = roots[0]
    # 注意：Cursor stop 只有 status、没有助手正文；不要把 status 伪造成 message，
    # 否则会盖掉 afterAgentResponse 已写入的末条回复。
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
    # Reasonix SessionStart 只认 stdout 里的 hookSpecificOutput / 纯文本；
    # 整包 {ok,action,...} 会被当成上下文，下一轮标题就变成 <hook-context>。
    if (
        args.agent == "reasonix"
        and isinstance(result, dict)
        and result.get("action") == "inject_hint"
        and isinstance(result.get("hookSpecificOutput"), dict)
    ):
        print(json.dumps({"hookSpecificOutput": result["hookSpecificOutput"]},
                         ensure_ascii=False))
    else:
        print(json.dumps(result, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
