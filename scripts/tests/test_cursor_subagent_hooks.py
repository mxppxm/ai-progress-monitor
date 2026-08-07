#!/usr/bin/env python3
"""Cursor 子代理 hooks：不得把父任务标成 ended，且应回写进度文案。"""
from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PY = REPO / ".venv" / "bin" / "python"
SCRIPT = REPO / "scripts" / "hook_report.py"
sys.path.insert(0, str(REPO / "server"))
import db  # noqa: E402


def _run(event: dict) -> dict:
    p = subprocess.run(
        [str(PY), str(SCRIPT), "--agent", "cursor"],
        input=json.dumps(event).encode(),
        capture_output=True,
        check=False,
    )
    out = (p.stdout or b"").decode().strip()
    assert p.returncode == 0, p.stderr.decode()
    return json.loads(out.splitlines()[-1])


def test_subagent_stop_does_not_end_parent():
    cid = f"subagent-fix-{uuid.uuid4()}"
    tid = f"cursor-{cid[:8]}"

    assert _run({
        "hook_event_name": "beforeSubmitPrompt",
        "conversation_id": cid,
        "prompt": "parent with subagent",
    })["action"] == "record_task"

    start = _run({
        "hook_event_name": "subagentStart",
        "conversation_id": cid,
        "parent_conversation_id": cid,
        "subagent_type": "explore",
        "task": "dig into hooks",
        "subagent_id": "tool_abc",
    })
    assert start.get("action") in ("log_node", "detail", "subagent"), start
    task = db.get_task(tid)
    assert task and task["status"] == "running", task
    assert "子任务" in (task.get("detail") or ""), task

    stop = _run({
        "hook_event_name": "subagentStop",
        "conversation_id": cid,
        "parent_conversation_id": cid,
        "subagent_type": "explore",
        "status": "completed",
        "task": "dig into hooks",
        "summary": "found root cause",
        "description": "explore",
    })
    assert stop.get("action") != "log_node" or stop.get("node_type") != "success", stop
    task = db.get_task(tid)
    assert task and task["status"] == "running", task
    assert "found root cause" in (task.get("detail") or "") or "子任务" in (task.get("detail") or ""), task

    # 父会话继续跑工具时仍应记心跳
    hb = _run({
        "hook_event_name": "postToolUse",
        "conversation_id": cid,
        "tool_name": "Shell",
    })
    assert hb.get("action") == "log_node", hb
    assert hb.get("reason") != "not_active", hb


def test_child_post_tool_still_skips_orphan_card():
    """子代理自己的 conversation_id 仍不建卡（避免孤儿）。"""
    child = f"child-only-{uuid.uuid4()}"
    r = _run({
        "hook_event_name": "postToolUse",
        "conversation_id": child,
        "tool_name": "Shell",
    })
    assert r.get("action") == "skip"
    assert r.get("reason") == "no_task"
    assert db.get_task(f"cursor-{child[:8]}") is None


if __name__ == "__main__":
    db.init_db()
    test_subagent_stop_does_not_end_parent()
    test_child_post_tool_still_skips_orphan_card()
    print("ok")
