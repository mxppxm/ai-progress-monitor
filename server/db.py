"""SQLite 数据层 — AI 工作台进度监控平台

存储所有工作台上报的任务、进度、关键节点。
线程安全：每条 MCP connection 可能在不同线程，用 check_same_thread=False + 锁保护。
"""
import json
import os
import sqlite3
import threading
import time
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "progress.db"

_LOCK = threading.Lock()

# 关键节点类型枚举（用于触发系统通知）
NODE_TYPES = ("step", "milestone", "success", "fail")

# 「待选择」＝黄灯：任务上报节点时，若 message 命中这些关键词，则把任务标为
# 待选择(pending)，提醒用户有一个决策点需要过去选择/拍板。任务后续结束(success)后黄灯自然熄灭。
CHOICE_KEYWORDS = (
    "需要选择", "请你选择", "请选择", "需要你选", "需要你决定",
    "你来决定", "你来定", "请你决定", "请你拍板", "你来拍板",
    "选 a", "选 b", "选择 a", "选择 b", "a 还是 b", "a或b",
    "二选一", "待选择", "得你定", "等你决定", "等你的选择",
)


def is_choice_message(message: str) -> bool:
    """判断节点 message 是否包含'需要用户选择'的决策意图（忽略大小写）。"""
    m = (message or "").lower()
    return any(kw in m for kw in CHOICE_KEYWORDS)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """初始化表结构（幂等）。"""
    with _LOCK, _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                task_id    TEXT PRIMARY KEY,
                agent      TEXT NOT NULL,          -- 工作台名称: codex/cursor/claude/opencode/...
                name       TEXT NOT NULL,          -- 任务名称
                status     TEXT NOT NULL DEFAULT 'running',  -- running/done/failed/paused
                progress   INTEGER NOT NULL DEFAULT 0,       -- 0-100
                stage      TEXT NOT NULL DEFAULT 'started',  -- 当前阶段
                detail     TEXT DEFAULT '',                  -- 补充描述
                archived   INTEGER NOT NULL DEFAULT 0,        -- 1=已存档（从运行列表隐藏）
                started_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS nodes (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id   TEXT NOT NULL REFERENCES tasks(task_id),
                node_type TEXT NOT NULL,            -- step/milestone/success/fail
                message   TEXT NOT NULL,
                meta      TEXT DEFAULT '{}',        -- JSON 扩展信息
                ts        REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_nodes_task ON nodes(task_id, ts);
            """
        )
        # 迁移：老库补 archived 列
        cols = [r[1] for r in conn.execute("PRAGMA table_info(tasks)").fetchall()]
        if "archived" not in cols:
            conn.execute("ALTER TABLE tasks ADD COLUMN archived INTEGER NOT NULL DEFAULT 0")


def record_task(task_id: str, agent: str, name: str) -> dict:
    """注册或复用一条任务。若已存在则视为复用；新上报自动取消存档。"""
    now = time.time()
    with _LOCK, _connect() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO tasks (task_id, agent, name, status, progress, stage, detail, archived, started_at, updated_at)
               VALUES (?, ?, ?, 'running', 0, 'started', '', 0, ?, ?)""",
            (task_id, agent, name, now, now),
        )
        # 复用已存在（含已存档）任务 → 新上报自动取消存档，重新显示
        conn.execute(
            "UPDATE tasks SET archived=0, updated_at=? WHERE task_id=?",
            (now, task_id),
        )
        row = conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        return dict(row)


def update_progress(task_id: str, progress: int | None = None, stage: str | None = None,
                    status: str | None = None, detail: str | None = None) -> dict | None:
    """更新任务进度/阶段/状态。返回更新后的任务 dict，若 task 不存在返回 None。"""
    updates, params = [], []
    if progress is not None:
        updates.append("progress=?")
        params.append(max(0, min(100, int(progress))))
    if stage is not None:
        updates.append("stage=?")
        params.append(stage)
    if status is not None:
        updates.append("status=?")
        params.append(status)
    if detail is not None:
        updates.append("detail=?")
        params.append(detail)
    if not updates:
        return get_task(task_id)

    now = time.time()
    updates.append("updated_at=?")
    params.append(now)
    # 新上报自动取消存档，重新出现在运行列表（常量，无占位符）
    updates.append("archived=0")
    params.append(task_id)

    with _LOCK, _connect() as conn:
        cur = conn.execute(f"UPDATE tasks SET {', '.join(updates)} WHERE task_id=?", params)
        if cur.rowcount == 0:
            return None
        row = conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        return dict(row)


def log_node(task_id: str, node_type: str, message: str, meta: dict | None = None) -> dict | None:
    """记录一个关键节点。若任务不存在返回 None。"""
    if node_type not in NODE_TYPES:
        node_type = "step"
    now = time.time()
    with _LOCK, _connect() as conn:
        # 确保任务存在
        t = conn.execute("SELECT task_id FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        if t is None:
            return None
        conn.execute(
            "INSERT INTO nodes (task_id, node_type, message, meta, ts) VALUES (?,?,?,?,?)",
            (task_id, node_type, message, json.dumps(meta or {}, ensure_ascii=False), now),
        )
        # success/fail 自动终结任务状态（同时熄灭之前的「待选择」黄灯）
        if node_type in ("success", "fail"):
            st = "done" if node_type == "success" else "failed"
            conn.execute(
                "UPDATE tasks SET status=?, updated_at=?, progress=? WHERE task_id=?",
                (st, now, 100 if st == "done" else 0, task_id),
            )
        # 节点带「需要用户选择」意图 → 标为待选择(黄灯)；仅在非终结节点上生效
        elif is_choice_message(message):
            conn.execute(
                "UPDATE tasks SET status='pending', updated_at=? WHERE task_id=?",
                (now, task_id),
            )
        # 新上报节点自动取消存档，重新出现在运行列表
        conn.execute(
            "UPDATE tasks SET archived=0 WHERE task_id=?",
            (task_id,),
        )
    return get_task(task_id)


def archive_task(task_id: str) -> dict | None:
    """把任务标记为已存档，从运行/默认列表隐藏（保留历史）。"""
    now = time.time()
    with _LOCK, _connect() as conn:
        cur = conn.execute(
            "UPDATE tasks SET archived=1, updated_at=? WHERE task_id=?",
            (now, task_id),
        )
        if cur.rowcount == 0:
            return None
        row = conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        return dict(row)


def unarchive_task(task_id: str) -> dict | None:
    """取消存档，让它重新显示。"""
    now = time.time()
    with _LOCK, _connect() as conn:
        cur = conn.execute(
            "UPDATE tasks SET archived=0, updated_at=? WHERE task_id=?",
            (now, task_id),
        )
        if cur.rowcount == 0:
            return None
        row = conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        return dict(row)


def get_task(task_id: str) -> dict | None:
    with _LOCK, _connect() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        return dict(row) if row else None


def list_tasks(limit: int = 200) -> list[dict]:
    """按更新时间倒序返回最近 N 天内的未归档任务（默认 3 天）。"""
    cutoff = time.time() - 3 * 86400
    with _LOCK, _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE archived=0 AND updated_at>=? ORDER BY updated_at DESC LIMIT ?",
            (cutoff, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def list_agents() -> list[str]:
    """返回最近3天内有任务的工作台列表（用于泳道）。"""
    cutoff = time.time() - 3 * 86400
    with _LOCK, _connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT agent FROM tasks WHERE archived=0 AND updated_at>=? ORDER BY agent",
            (cutoff,),
        ).fetchall()
    return [r["agent"] for r in rows]


def count_archived() -> int:
    """已存档任务数（用于前端显示）。"""
    with _LOCK, _connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM tasks WHERE archived=1").fetchone()
        return row["c"] if row else 0


def list_nodes(task_id: str, limit: int = 100) -> list[dict]:
    with _LOCK, _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM nodes WHERE task_id=? ORDER BY ts DESC LIMIT ?", (task_id, limit)
        ).fetchall()
    return [dict(r) for r in rows]


# 全局数据版本号，用于 SSE 增量推送
_VERSION = 0


def bump_version() -> int:
    global _VERSION
    with _LOCK:
        _VERSION += 1
        return _VERSION


def get_version() -> int:
    return _VERSION