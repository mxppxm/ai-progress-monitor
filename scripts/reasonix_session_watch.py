#!/usr/bin/env python3
"""Reasonix → 看板：监听 sessions + 桌面页签，兜底黄灯与会话结束。

Reasonix hooks 在会话构建时加载；长会话在补上 PreToolUse(ask) 之前建好的，
之后弹 ask 也不会走 hook。本监听兜底：

1. events.jsonl 里 tool_calls.name=ask → pending；对应 tool 结果 → running
2. Desktop 关掉/切走页签时常不发 SessionEnd → 对照 desktop-tabs.json，
   不在打开页签里的 running/pending 任务，防抖后上报 SessionEnd
3. Reasonix 进程退出后，同样把仍挂着的任务收尾

用法：
  .venv/bin/python scripts/reasonix_session_watch.py
LaunchAgent：com.mxppxm.ai-progress-reasonix-watch
"""
from __future__ import annotations

import json
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PY = REPO / ".venv" / "bin" / "python"
SCRIPT = REPO / "scripts" / "hook_report.py"
DB_PATH = REPO / "data" / "progress.db"
PROJECTS = Path.home() / ".reasonix" / "projects"
TABS_PATH = Path.home() / ".reasonix" / "desktop-tabs.json"
STATE_PATH = REPO / "data" / "reasonix_watch_state.json"
LOG_PATH = Path.home() / "Library" / "Logs" / "ai-progress-monitor" / "reasonix-watch.log"

POLL_SEC = 1.0
# 页签短暂切换 / 新建会话写 tabs 有竞态，给几秒缓冲
ABSENT_SEC = 4.0
APP_GONE_SEC = 5.0
_SID_RE = re.compile(r"^(\d{8}-\d{6}\.\d+)")
_SID_SHORT_RE = re.compile(r"^(\d{8}-\d{6})")


def log(msg: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n"
    try:
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"files": {}}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE_PATH)


def session_id_from_path(path: Path) -> str:
    # 20260806-094200.479088000-fxb-deepseek-v4-flash.events.jsonl
    name = path.name
    if name.endswith(".events.jsonl"):
        return name[: -len(".events.jsonl")]
    return path.stem


def session_suffix(sid: str) -> str:
    """与 hook_report._session_suffix 对齐：保留到小数秒。"""
    s = str(sid).strip()
    m = _SID_RE.match(s)
    if m:
        return m.group(1)
    m = _SID_SHORT_RE.match(s)
    if m:
        return m.group(1)
    return s[:8]


def open_tab_session_suffixes() -> set[str]:
    """当前桌面打开页签对应的会话后缀。"""
    try:
        data = json.loads(TABS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return set()
    tabs = data.get("tabs") if isinstance(data, dict) else None
    if not isinstance(tabs, list):
        return set()
    out: set[str] = set()
    for tab in tabs:
        if not isinstance(tab, dict):
            continue
        for key in ("sessionPath", "session_path"):
            raw = tab.get(key)
            if isinstance(raw, str) and raw.strip():
                out.add(session_suffix(Path(raw).name))
                break
        topic = tab.get("topicId") or tab.get("topic_id")
        if isinstance(topic, str) and topic.startswith("topic_"):
            # topic_20260806-110003_61cd... → 至少到秒；与小数秒卡兼容靠前缀匹配
            body = topic[len("topic_") :]
            out.add(session_suffix(body.split("_", 1)[0]))
    return out


def reasonix_app_running() -> bool:
    try:
        r = subprocess.run(
            ["pgrep", "-f", "Reasonix.app/Contents/MacOS/reasonix-desktop"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return r.returncode == 0 and bool((r.stdout or "").strip())
    except Exception:
        return False


def list_open_reasonix_tasks() -> list[str]:
    if not DB_PATH.is_file():
        return []
    try:
        con = sqlite3.connect(str(DB_PATH))
        try:
            rows = con.execute(
                "SELECT task_id FROM tasks "
                "WHERE agent='reasonix' AND status IN ('running','pending') "
                "AND COALESCE(archived,0)=0"
            ).fetchall()
        finally:
            con.close()
        return [str(r[0]) for r in rows]
    except Exception as e:
        log(f"list tasks error: {e}")
        return []


def task_session_suffix(task_id: str) -> str:
    if task_id.startswith("reasonix-"):
        return session_suffix(task_id[len("reasonix-") :])
    return session_suffix(task_id)


def report_session_end(session_id: str, reason: str) -> None:
    event = {
        "event": "SessionEnd",
        "sessionId": session_id,
        "reason": reason,
    }
    try:
        r = subprocess.run(
            [str(PY), str(SCRIPT), "--agent", "reasonix"],
            input=json.dumps(event, ensure_ascii=False),
            capture_output=True,
            text=True,
            timeout=12,
        )
        out = (r.stdout or "").strip()
        log(
            f"session_end sid={session_id[:40]} reason={reason} "
            f"code={r.returncode} out={out[:200]}"
        )
    except Exception as e:
        log(f"session_end error sid={session_id}: {e}")


def reconcile_closed_sessions(state: dict) -> None:
    """页签关掉或 App 退出时，补发 SessionEnd。"""
    now = time.time()
    absent: dict = state.setdefault("absent_since", {})
    app_gone_since = state.get("app_gone_since")

    running = reasonix_app_running()
    if running:
        state["app_gone_since"] = None
        app_gone_since = None
    else:
        if app_gone_since is None:
            state["app_gone_since"] = now
            app_gone_since = now
        elif now - float(app_gone_since) >= APP_GONE_SEC:
            for tid in list_open_reasonix_tasks():
                sid = task_session_suffix(tid)
                report_session_end(sid, "app_quit")
                absent.pop(tid, None)
            return

    open_exact = open_tab_session_suffixes()

    def still_open(sid: str) -> bool:
        if sid in open_exact:
            return True
        short = sid.split(".", 1)[0]
        for o in open_exact:
            if o.split(".", 1)[0] == short:
                return True
        return False

    live = set(list_open_reasonix_tasks())
    for tid in list(absent.keys()):
        if tid not in live:
            absent.pop(tid, None)

    for tid in live:
        sid = task_session_suffix(tid)
        if still_open(sid):
            absent.pop(tid, None)
            continue
        since = absent.get(tid)
        if since is None:
            absent[tid] = now
            continue
        if now - float(since) < ABSENT_SEC:
            continue
        report_session_end(sid, "tab_closed")
        absent.pop(tid, None)


def report_ask(session_id: str, cwd: str, tool_args: dict, *, answered: bool) -> None:
    event = {
        "event": "PostToolUse" if answered else "PreToolUse",
        "sessionId": session_id,
        "cwd": cwd or str(Path.home()),
        "toolName": "ask",
        "toolArgs": tool_args,
    }
    if answered:
        event["toolResult"] = "answered"
    try:
        r = subprocess.run(
            [str(PY), str(SCRIPT), "--agent", "reasonix"],
            input=json.dumps(event, ensure_ascii=False),
            capture_output=True,
            text=True,
            timeout=12,
        )
        out = (r.stdout or "").strip()
        log(
            f"{'resume' if answered else 'pending'} sid={session_id[:40]} "
            f"code={r.returncode} out={out[:200]}"
        )
    except Exception as e:
        log(f"report error sid={session_id}: {e}")


def extract_asks_from_obj(obj: dict) -> list[tuple[str, dict]]:
    """返回 [(call_id, arguments_dict), ...]"""
    found: list[tuple[str, dict]] = []

    def handle_calls(calls) -> None:
        if not isinstance(calls, list):
            return
        for c in calls:
            if not isinstance(c, dict):
                continue
            if c.get("name") != "ask":
                continue
            cid = str(c.get("id") or "")
            raw = c.get("arguments")
            args: dict = {}
            if isinstance(raw, dict):
                args = raw
            elif isinstance(raw, str) and raw.strip():
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, dict):
                        args = parsed
                except json.JSONDecodeError:
                    args = {}
            found.append((cid or f"anon-{len(found)}", args))

    # events.jsonl: replace/append with messages[].tool_calls
    msgs = obj.get("messages")
    if isinstance(msgs, list):
        for m in msgs:
            if isinstance(m, dict):
                handle_calls(m.get("tool_calls") or m.get("toolCalls"))

    handle_calls(obj.get("tool_calls") or obj.get("toolCalls"))
    return found


def extract_ask_results(obj: dict) -> set[str]:
    """tool 结果消息里带上的 call id（若有）。"""
    ids: set[str] = set()
    msgs = obj.get("messages")
    if not isinstance(msgs, list):
        return ids
    for m in msgs:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        name = m.get("name")
        content = m.get("content")
        # Reasonix：role=tool name=ask，content 含 The user answered
        is_ask_result = (
            role in ("tool", "function")
            and (
                name == "ask"
                or (
                    isinstance(content, str)
                    and "The user answered" in content
                )
            )
        )
        if role not in ("tool", "function") and not is_ask_result:
            continue
        if name == "ask" or (
            isinstance(content, str) and "The user answered" in content
        ):
            for key in ("tool_call_id", "toolCallId", "id"):
                v = m.get(key)
                if v:
                    ids.add(str(v))
                    break
            else:
                # 无 id 时用占位，配合「任意 pending ask」收回
                ids.add("__ask_answered__")
        else:
            for key in ("tool_call_id", "toolCallId", "id"):
                v = m.get(key)
                if v:
                    ids.add(str(v))
    return ids


def infer_cwd(path: Path) -> str:
    # .../projects/-Users-mico-foo/sessions/xxx.events.jsonl
    try:
        proj = path.parents[1].name  # -Users-mico-foo
        if proj.startswith("-"):
            return "/" + proj[1:].replace("-", "/")
    except Exception:
        pass
    return str(Path.home())


def scan_file(path: Path, st: dict) -> None:
    key = str(path)
    files = st.setdefault("files", {})
    meta = files.get(key)
    first_seen = meta is None
    if first_seen:
        meta = {"offset": 0, "asks": {}, "mtime": 0}
        files[key] = meta

    try:
        raw = path.read_bytes()
    except Exception:
        return
    if len(raw) < meta.get("offset", 0):
        meta["offset"] = 0
        meta["asks"] = {}
        first_seen = True

    # 冷启动：整文件扫一遍，只对「尚未有 tool 结果」的 ask 亮黄灯
    if first_seen:
        text = raw.decode("utf-8", errors="replace")
        sid = session_id_from_path(path)
        cwd = infer_cwd(path)
        pending_asks: dict[str, dict] = {}
        answered: set[str] = set()
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue
            for cid, args in extract_asks_from_obj(obj):
                pending_asks[cid] = args
            answered |= extract_ask_results(obj)
        for cid, args in pending_asks.items():
            if cid in answered:
                meta.setdefault("asks", {})[cid] = {
                    "pending": False, "answered": True
                }
                continue
            report_ask(sid, cwd, args, answered=False)
            meta.setdefault("asks", {})[cid] = {
                "pending": True, "answered": False
            }
        meta["offset"] = len(raw)
        return

    chunk = raw[meta["offset"] :]
    if not chunk:
        return
    text = chunk.decode("utf-8", errors="replace")
    # 不完整最后一行留给下次
    if not text.endswith("\n"):
        last_nl = text.rfind("\n")
        if last_nl < 0:
            return
        text = text[: last_nl + 1]
    meta["offset"] += len(text.encode("utf-8"))

    sid = session_id_from_path(path)
    cwd = infer_cwd(path)
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if '"ask"' not in line and "tool_call_id" not in line and "toolCallId" not in line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue

        for cid, args in extract_asks_from_obj(obj):
            asks = meta.setdefault("asks", {})
            prev = asks.get(cid) or {}
            if not prev.get("pending") and not prev.get("answered"):
                report_ask(sid, cwd, args, answered=False)
                asks[cid] = {"pending": True, "answered": False}

        for cid in extract_ask_results(obj):
            asks = meta.setdefault("asks", {})
            if cid == "__ask_answered__":
                # 收回所有仍 pending 的 ask
                for prev in asks.values():
                    if prev.get("pending") and not prev.get("answered"):
                        report_ask(sid, cwd, {}, answered=True)
                        prev["answered"] = True
                        prev["pending"] = False
                continue
            prev = asks.get(cid)
            if prev and prev.get("pending") and not prev.get("answered"):
                report_ask(sid, cwd, {}, answered=True)
                prev["answered"] = True
                prev["pending"] = False
            elif cid and cid not in asks:
                asks[cid] = {"pending": False, "answered": True}

def iter_event_files() -> list[Path]:
    if not PROJECTS.is_dir():
        return []
    return sorted(PROJECTS.glob("*/sessions/*.events.jsonl"), key=lambda p: p.stat().st_mtime)


def main() -> int:
    log("reasonix_session_watch start")
    state = load_state()
    while True:
        try:
            for path in iter_event_files():
                # 只跟最近改动的，避免冷启动全量扫爆
                try:
                    mtime = path.stat().st_mtime
                except OSError:
                    continue
                meta = state.setdefault("files", {}).get(str(path))
                if meta and meta.get("offset") and mtime <= meta.get("mtime", 0):
                    # 仍可能有追加但 mtime 粒度不够；有 offset 时每次都试读尾部更稳
                    pass
                scan_file(path, state)
                state.setdefault("files", {}).setdefault(str(path), {})["mtime"] = mtime
            reconcile_closed_sessions(state)
            save_state(state)
        except Exception as e:
            log(f"loop error: {e}")
        time.sleep(POLL_SEC)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        log("reasonix_session_watch stop")
        sys.exit(0)
