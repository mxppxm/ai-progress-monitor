"""MCP 进度上报服务 — 供各 AI 工作台接入。

各工作台通过 MCP client 调用以下工具，上报任务进度与关键节点：
  - record_task     注册/复用一个任务
  - update_progress 更新进度/阶段/状态
  - log_node        上报关键节点（里程碑/成功/失败，会触发系统通知）
  - list_tasks      查询当前任务（供看板/调试）

启动方式：
    uv run server/mcp_server.py
  或将本文件注册为 stdio MCP server（见 client-configs/）。
"""
from mcp.server.fastmcp import FastMCP

import db
import notify

mcp = FastMCP("ai-progress-monitor")

db.init_db()


@mcp.tool()
def record_task(task_id: str, agent: str, name: str) -> dict:
    """注册一个新的监控任务（或复用已存在的同名 task_id）。

    Args:
        task_id: 任务唯一 ID（建议用 工作台名-序号 或 简短 slug）
        agent:   工作台名称，如 codex / cursor / claude / opencode
        name:    任务的人类可读名称
    """
    result = db.record_task(task_id, agent, name)
    db.bump_version()
    return {"ok": True, "task": result}


@mcp.tool()
def update_progress(task_id: str, progress: int | None = None, stage: str | None = None,
                    status: str | None = None, detail: str | None = None) -> dict:
    """更新任务的进度 / 阶段 / 状态。

    Args:
        task_id:  目标任务 ID
        progress: 0-100 的整数进度百分比（可选）
        stage:    当前阶段，如 'coding' / 'testing' / 'deploying'（可选）
        status:   运行状态：running / paused（可选）
        detail:   补充说明文字（可选）
    """
    result = db.update_progress(task_id, progress, stage, status, detail)
    db.bump_version()
    if result is None:
        return {"ok": False, "error": f"task {task_id!r} 不存在，请先 record_task"}
    return {"ok": True, "task": result}


@mcp.tool()
def log_node(task_id: str, node_type: str, message: str, meta: dict | None = None) -> dict:
    """上报一个关键节点（里程碑）。milestone / success / fail 会触发系统通知横幅。

    message 若包含「需要选择 / 请你选 / 选 A 或 B / 你来决定」等决策意图，
    任务会自动标为「待选择」(pending)，看板亮黄灯提醒你去拍板，并弹黄灯横幅通知。

    Args:
        task_id:   目标任务 ID
        node_type: step / milestone / success / fail
        message:   节点描述，如 '构建通过' / '方案 A 还是 B，需要你选择'
        meta:      额外 JSON 信息（可选），如 {"commit": "abc123"}
    """
    result = db.log_node(task_id, node_type, message, meta or {})
    db.bump_version()
    if result is None:
        return {"ok": False, "error": f"task {task_id!r} 不存在，请先 record_task"}

    task = db.get_task(task_id)
    # 命中「需要用户选择」→ 任务进待选择(黄灯)，发黄灯提醒通知
    if db.is_choice_message(message):
        notify.notify_choice(task["agent"], task["name"], message)
    else:
        notify.notify_node(task["agent"], task["name"], node_type, message)
    return {"ok": True, "task": result, "node_type": node_type}


@mcp.tool()
def list_tasks(limit: int = 50) -> dict:
    """查询当前所有监控中的任务（按最近更新排序）。"""
    tasks = db.list_tasks(limit)
    return {"ok": True, "tasks": tasks}


if __name__ == "__main__":
    mcp.run(transport="stdio")