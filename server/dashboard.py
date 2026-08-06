"""看板后端 — FastAPI + SSE。

提供：
  GET /           看板前端页面
  GET /api/tasks  拉取当前任务列表（JSON，含已注册 agents）
  GET /api/tasks/{id}/nodes  拉取某个任务的节点时间线
  POST /api/tasks/{id}/end   手动结束任务
  POST /api/tasks/clear      一键清空（永久删除全部任务）
  POST /api/focus/{agent}    聚焦到对应工作台 App
  GET /api/stream SSE 实时推送：任务数据变更时自动 push

启动：
    uv run server/dashboard.py   # 默认 http://127.0.0.1:8777
"""
import asyncio
import json
import time
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

import db
import focus

app = FastAPI(title="AI Progress Monitor")

ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_DIR = ROOT / "dashboard"

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)
app.mount("/static", StaticFiles(directory=str(DASHBOARD_DIR)), name="static")

db.init_db()

# SSE 订阅者集合
_subscribers: set[asyncio.Queue] = set()


def _snapshot() -> str:
    return json.dumps(
        {"tasks": db.list_tasks(), "agents": focus.registered_agents()},
        ensure_ascii=False,
    )


def _publish():
    data = _snapshot()
    for q in list(_subscribers):
        try:
            q.put_nowait(data)
        except asyncio.QueueFull:
            pass


@app.get("/")
def index():
    return FileResponse(str(DASHBOARD_DIR / "index.html"))


@app.get("/api/tasks")
def tasks_api():
    return {"tasks": db.list_tasks(), "agents": focus.registered_agents()}


@app.post("/api/tasks/{task_id}/end")
def end_api(task_id: str):
    """手动结束任务（看板卡片「结束」按钮）。"""
    t = db.end_task(task_id)
    if t is None:
        raise HTTPException(status_code=404, detail="task not found")
    db.bump_version()
    _publish()
    return {"ok": True, "task": t}


@app.post("/api/tasks/clear")
def clear_api():
    """一键清空：永久删除全部任务与节点。"""
    deleted = db.clear_all_tasks()
    db.bump_version()
    _publish()
    return {"ok": True, "deleted": deleted}


@app.post("/api/tasks/{task_id}/archive")
def archive_api(task_id: str):
    t = db.archive_task(task_id)
    if t is None:
        raise HTTPException(status_code=404, detail="task not found")
    _publish()
    return {"ok": True, "task": t}


@app.post("/api/tasks/{task_id}/unarchive")
def unarchive_api(task_id: str):
    t = db.unarchive_task(task_id)
    if t is None:
        raise HTTPException(status_code=404, detail="task not found")
    _publish()
    return {"ok": True, "task": t}


@app.get("/api/tasks/{task_id}/nodes")
def task_nodes(task_id: str, limit: int = 100):
    return {"nodes": db.list_nodes(task_id, limit)}


@app.api_route("/api/focus/{agent}", methods=["GET", "POST"])
def focus_api(agent: str, task_id: str | None = None):
    """点击看板/通知：聚焦对应工作台（Clacky 打开 Chrome 会话标签）。"""
    result = focus.focus_agent(agent, task_id=task_id)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error") or "focus failed")
    return result


@app.get("/api/stream")
async def stream():
    """SSE 实时推送。连接后先发一次全量，之后推增量。"""
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    _subscribers.add(queue)

    async def gen():
        try:
            # 首次全量
            initial = _snapshot()
            yield f"data: {initial}\n\n"
            idle = 0
            while True:
                try:
                    data = queue.get_nowait()
                    idle = 0
                    yield f"data: {data}\n\n"
                except asyncio.QueueEmpty:
                    await asyncio.sleep(3)
                    idle += 3
                    # 心跳注释，保持连接活跃并让前端知道还连着
                    yield ": ping\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            _subscribers.discard(queue)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
        },
    )


def startup_watch():
    """每 0.8s 检查数据版本，有变化就推送广播。"""
    last = db.get_version()

    async def loop():
        nonlocal last
        while True:
            await asyncio.sleep(0.8)
            cur = db.get_version()
            if cur != last:
                last = cur
                _publish()

    asyncio.create_task(loop())


@app.on_event("startup")
async def _startup():
    startup_watch()


if __name__ == "__main__":
    uvicorn.run("dashboard:app", host="127.0.0.1", port=8777, reload=False)