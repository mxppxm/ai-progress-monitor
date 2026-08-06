#!/usr/bin/env python3
"""CLI：聚焦工作台。供通知点击 / 手动调用。

  .venv/bin/python scripts/focus_agent.py --agent cursor
  .venv/bin/python scripts/focus_agent.py --agent clacky --task-id clacky-aeade48b
  .venv/bin/python scripts/focus_agent.py --from-pending
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "server"))

import focus  # noqa: E402

PENDING = REPO / "data" / "pending_notify.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", default="")
    ap.add_argument("--task-id", default="")
    ap.add_argument("--from-pending", action="store_true")
    args = ap.parse_args()

    agent = args.agent.strip()
    task_id = args.task_id.strip() or None

    if args.from_pending:
        try:
            data = json.loads(PENDING.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"no pending notify: {e}", file=sys.stderr)
            return 1
        agent = str(data.get("agent") or "").strip()
        tid = data.get("task_id")
        task_id = str(tid).strip() if tid else None

    if not agent:
        print("agent required", file=sys.stderr)
        return 2

    result = focus.focus_agent(agent, task_id=task_id)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
