#!/usr/bin/env python3
"""Clacky → 看板自动上报。

优先轮询 OpenClacky HTTP API（进行中会话的消息常只在内存/API，磁盘 JSON 滞后甚至为空）：
  GET http://127.0.0.1:7070/api/sessions
  GET http://127.0.0.1:7070/api/sessions/{id}/messages

映射：
  history_user_message → SessionStart
  tool_call            → PostToolUse
  status 离开 running  → Stop（末条 assistant）
  running + error 字段 → Stop（Clacky 常不改 status）
  assistant 后静默     → Stop
  长时间无事件         → Stop（防僵尸 running）

API 不可用时回退 ~/.clacky/sessions/*.json（只追新消息，不回放历史）。

用法：
  .venv/bin/python scripts/clacky_session_watch.py
LaunchAgent：com.mxppxm.ai-progress-clacky-watch
"""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PY = REPO / ".venv" / "bin" / "python"
SCRIPT = REPO / "scripts" / "hook_report.py"
SESSIONS = Path.home() / ".clacky" / "sessions"
STATE_PATH = REPO / "data" / "clacky_watch_state.json"
LOG_PATH = Path.home() / "Library" / "Logs" / "ai-progress-monitor" / "clacky-watch.log"

DB_PATH = REPO / "data" / "progress.db"
API_BASE = "http://127.0.0.1:7070"
POLL_SEC = 1.2
# 末条 assistant 后静默 → 本轮结束
IDLE_SEC = 5.0
# 任意事件都不再更新 → 视为卡死/僵尸 running（Clacky 出错后常不改 status）
STALE_SEC = 90.0
HTTP_TIMEOUT = 4.0


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
        return {"sessions": {}}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE_PATH)


def report(
    event: str,
    session_id: str,
    name: str | None = None,
    message: str | None = None,
    *,
    status: str | None = None,
) -> None:
    task_id = f"clacky-{session_id[:8]}"
    # 走 stdin JSON，才能带上 status=error（CLI --event 路径不读 stdin）
    payload: dict = {
        "event": event,
        "task_id": task_id,
        "sessionId": session_id,
    }
    if name:
        payload["name"] = name[:100]
    if message:
        payload["message"] = message[:800]
    if status:
        payload["status"] = status
    try:
        r = subprocess.run(
            [str(PY), str(SCRIPT), "--agent", "clacky"],
            input=json.dumps(payload, ensure_ascii=False),
            capture_output=True,
            text=True,
            timeout=12,
        )
        if r.returncode != 0:
            log(f"report fail event={event} sid={task_id} code={r.returncode} {r.stderr.strip()}")
        else:
            log(f"report ok event={event} sid={task_id}")
    except Exception as e:
        log(f"report error event={event} {e}")


def session_error_text(meta: dict) -> str:
    """Clacky 出错后 status 可能仍是 running，但 error 字段已有终态文案。"""
    for key in ("error", "error_code"):
        val = meta.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    if str(meta.get("status") or "").lower() == "error":
        return "会话出错"
    return ""


def list_board_open_clacky() -> list[str]:
    """看板里仍挂着的 clacky 任务 id。"""
    if not DB_PATH.is_file():
        return []
    try:
        con = sqlite3.connect(str(DB_PATH))
        try:
            rows = con.execute(
                "SELECT task_id FROM tasks "
                "WHERE agent='clacky' AND status='running' "
                "AND COALESCE(archived,0)=0"
            ).fetchall()
        finally:
            con.close()
        return [str(r[0]) for r in rows]
    except Exception as e:
        log(f"list board tasks: {e}")
        return []


def reconcile_board(state: dict, alive_sids: set[str] | None = None) -> None:
    """本地已判定结束，或会话已不在 API，但看板仍 running → 补 Stop。"""
    sessions = state.get("sessions") or {}
    for tid in list_board_open_clacky():
        if not tid.startswith("clacky-"):
            continue
        prefix = tid[len("clacky-") :]
        match_sid = None
        st = None
        for sid, row in sessions.items():
            if sid.startswith(prefix) or sid[:8] == prefix[:8]:
                match_sid = sid
                st = row
                break
        if st is None:
            # 完全无水位的老卡：直接收尾
            report("Stop", prefix, message="会话已结束（看板兜底）")
            continue
        if st.get("running"):
            # 仍认为在跑：若 API 活着且会话不在列表，上面 poll 会处理；这里跳过
            if alive_sids is not None and match_sid not in alive_sids and st.get("source") == "api":
                stop_session(match_sid, st, message=st.get("last_assistant") or "会话已离开列表")
            continue
        # 本地已 idle，看板还挂着 → 补一刀
        report(
            "Stop",
            match_sid or prefix,
            message=st.get("last_assistant") or "本轮结束",
        )


def is_system_user_msg(content) -> bool:
    """Clacky 注入的伪 user 消息（环境上下文 / 压缩摘要），不是真实提问。"""
    text = content if isinstance(content, str) else ""
    t = text.strip()
    if not t:
        return True
    return t.startswith("[Session context:") or t.startswith("[Compressed")


def title_from(name: str | None, content: str | None) -> str:
    text = (content or "").strip()
    if text and not is_system_user_msg(text):
        return " ".join(text.splitlines()[0].split())[:100]
    n = (name or "").strip()
    return (n or "clacky 会话")[:100]


def http_json(url: str):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_sessions():
    # 最近会话（含 running）通常在首页；limit 最大约 50
    data = http_json(f"{API_BASE}/api/sessions?limit=50")
    sessions = data.get("sessions") if isinstance(data, dict) else None
    return sessions if isinstance(sessions, list) else []


def fetch_session(sid: str) -> dict | None:
    data = http_json(f"{API_BASE}/api/sessions/{sid}")
    if isinstance(data, dict):
        s = data.get("session")
        if isinstance(s, dict):
            return s
        if data.get("id"):
            return data
    return None


def fetch_events(sid: str) -> list:
    data = http_json(f"{API_BASE}/api/sessions/{sid}/messages")
    events = data.get("events") if isinstance(data, dict) else None
    return events if isinstance(events, list) else []


def ensure_st(state: dict, sid: str) -> dict:
    sessions = state.setdefault("sessions", {})
    return sessions.setdefault(
        sid,
        {
            "source": None,
            "status": None,
            "updated_at": None,
            "event_len": 0,
            "msg_len": 0,
            "mtime": 0.0,
            "running": False,
            "idle_since": None,
            "last_activity": None,
            "last_assistant": "",
            "name": "",
        },
    )


def mark_activity(st: dict, now: float, *, quiet_candidate: bool = False) -> None:
    st["last_activity"] = now
    if quiet_candidate:
        st["idle_since"] = now
    else:
        st["idle_since"] = None


def stop_session(sid: str, st: dict, message: str = "", *, status: str | None = None) -> None:
    report("Stop", sid, message=message or st.get("last_assistant") or "", status=status)
    st["running"] = False
    st["idle_since"] = None


def apply_new_events(sid: str, st: dict, events: list, session_name: str, now: float, start: int) -> None:
    for ev in events[start:]:
        if not isinstance(ev, dict):
            continue
        et = ev.get("type")
        if et == "history_user_message":
            content = ev.get("content")
            if is_system_user_msg(content):
                continue
            report("SessionStart", sid, name=title_from(session_name, content if isinstance(content, str) else None))
            st["running"] = True
            mark_activity(st, now)
        elif et == "tool_call":
            if st.get("running"):
                report("PostToolUse", sid)
            mark_activity(st, now)
        elif et == "assistant_message":
            c = ev.get("content")
            text = c.strip() if isinstance(c, str) else ""
            if text:
                st["last_assistant"] = text
            mark_activity(st, now, quiet_candidate=True)
        elif et in ("tool_result", "token_usage"):
            # 心跳类事件：刷新活跃时间，避免长工具误判 stale，但不清 idle 候选
            st["last_activity"] = now
    st["event_len"] = len(events)


def maybe_stop_idle(sid: str, st: dict, now: float) -> None:
    if not st.get("running"):
        return
    idle_since = st.get("idle_since")
    if idle_since and (now - float(idle_since)) >= IDLE_SEC:
        stop_session(sid, st)
        return
    last_act = st.get("last_activity")
    if last_act is None:
        # 迁状态/无水位：先打戳，下一轮再判 stale，避免一上来误杀
        st["last_activity"] = now
        return
    if (now - float(last_act)) >= STALE_SEC:
        stop_session(sid, st, message=st.get("last_assistant") or "本轮超时无进展")


def process_api_session(meta: dict, state: dict, now: float, force_events: bool) -> None:
    sid = str(meta.get("id") or "")
    if not sid:
        return
    status = str(meta.get("status") or "idle").lower()
    updated_at = str(meta.get("updated_at") or "")
    name = str(meta.get("name") or "").strip()
    err_text = session_error_text(meta)

    sessions = state.setdefault("sessions", {})
    known = sid in sessions
    st = ensure_st(state, sid)
    st["name"] = name or st.get("name") or ""

    prev_status = st.get("status")
    prev_updated = st.get("updated_at")
    was_running = bool(st.get("running"))
    # 尚未用 API 水位同步过（含从 file 状态迁过来）
    api_fresh = st.get("source") != "api" or prev_status is None

    def seed_running(events: list) -> None:
        seed_title = name
        last_as = ""
        for ev in events:
            if not isinstance(ev, dict):
                continue
            if ev.get("type") == "history_user_message" and not is_system_user_msg(ev.get("content")):
                c = ev.get("content")
                if isinstance(c, str) and c.strip():
                    seed_title = title_from(name, c)
            elif ev.get("type") == "assistant_message":
                c = ev.get("content")
                if isinstance(c, str) and c.strip():
                    last_as = c.strip()
        report("SessionStart", sid, name=seed_title or "clacky 会话")
        st["running"] = True
        st["last_assistant"] = last_as
        mark_activity(st, now)
        st["event_len"] = len(events)

    def end_if_needed(msg: str = "", *, fail: bool = False) -> None:
        if was_running or st.get("running"):
            stop_session(
                sid,
                st,
                message=msg or err_text or st.get("last_assistant") or "",
                status="error" if fail else None,
            )
        else:
            st["running"] = False
            st["idle_since"] = None

    # 首次 / 迁到 API：只对齐水位；真正在跑且无终态错误才建任务
    if not known or api_fresh:
        st["source"] = "api"
        st["status"] = status
        st["updated_at"] = updated_at
        if status == "running" and not err_text:
            try:
                events = fetch_events(sid)
            except Exception as e:
                log(f"api events bootstrap fail {sid[:8]}: {e}")
                events = []
            seed_running(events)
        else:
            # idle / error / running+error：对齐水位，必要时补 Stop（file 回退曾误拉回）
            try:
                events = fetch_events(sid)
                st["event_len"] = len(events)
                for ev in reversed(events):
                    if isinstance(ev, dict) and ev.get("type") == "assistant_message":
                        c = ev.get("content")
                        if isinstance(c, str) and c.strip():
                            st["last_assistant"] = c.strip()
                            break
            except Exception:
                st["event_len"] = -1
            end_if_needed(fail=bool(err_text) or status == "error")
            if st.get("event_len") is None or st.get("event_len") == 0:
                st["event_len"] = -1
        return

    st["source"] = "api"
    changed = status != prev_status or updated_at != prev_updated
    need_events = force_events or changed or was_running or status == "running" or st.get("idle_since")
    if not need_events and not err_text:
        maybe_stop_idle(sid, st, now)
        return

    st["status"] = status
    st["updated_at"] = updated_at

    # running 但已有终态 error：立刻收尾（Clacky 常不把 status 改成 error）
    if err_text and (was_running or st.get("running") or status == "running"):
        try:
            events = fetch_events(sid)
            if len(events) > int(st.get("event_len") or 0):
                apply_new_events(sid, st, events, name, now, int(st.get("event_len") or 0))
        except Exception:
            pass
        end_if_needed(err_text, fail=True)
        return

    try:
        events = fetch_events(sid)
    except Exception as e:
        log(f"api events fail {sid[:8]}: {e}")
        maybe_stop_idle(sid, st, now)
        return

    prev_len = int(st.get("event_len") if st.get("event_len") is not None else 0)
    if prev_len < 0:
        # 首次对齐：不回放；若此刻已 running，只从最后一条真实 user 起追
        if status == "running":
            start = len(events)
            for i, ev in enumerate(events):
                if isinstance(ev, dict) and ev.get("type") == "history_user_message" and not is_system_user_msg(ev.get("content")):
                    start = i
            apply_new_events(sid, st, events, name, now, start)
        else:
            st["event_len"] = len(events)
            return
    else:
        if len(events) < prev_len:
            prev_len = 0
        apply_new_events(sid, st, events, name, now, prev_len)

    # API 标记已结束 → 立刻 Stop
    if was_running and status in ("idle", "error", "done", "success") and status != "running":
        if st.get("running"):
            stop_session(
                sid,
                st,
                message=st.get("last_assistant") or "",
                status="error" if status == "error" else None,
            )
        return

    # 进入 running 但没吃到 user 事件 → 用会话名兜底
    if status == "running" and not st.get("running") and not err_text:
        report("SessionStart", sid, name=title_from(name, None))
        st["running"] = True
        mark_activity(st, now)

    maybe_stop_idle(sid, st, now)


def poll_api(state: dict, now: float) -> bool:
    """成功走 API 返回 True；连不上返回 False（调用方回退文件）。"""
    try:
        sessions = fetch_sessions()
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
        log(f"api sessions fail: {e}")
        return False

    by_id = {}
    for meta in sessions:
        if isinstance(meta, dict) and meta.get("id"):
            by_id[str(meta["id"])] = meta

    # 本地仍标记 running、但不在首页里的会话，单独补拉
    for sid, st in list(state.get("sessions", {}).items()):
        if not st.get("running") or sid in by_id:
            continue
        try:
            meta = fetch_session(sid)
            if meta:
                by_id[sid] = meta
        except Exception as e:
            log(f"api session refresh {sid[:8]}: {e}")

    for sid, meta in by_id.items():
        status = str(meta.get("status") or "")
        st = state.get("sessions", {}).get(sid) or {}
        force = (
            status == "running"
            or bool(st.get("running"))
            or bool(st.get("idle_since"))
            or bool(session_error_text(meta))
        )
        try:
            process_api_session(meta, state, now, force_events=force)
        except Exception as e:
            log(f"api process {sid[:8]}: {e}")

    alive = set(by_id)
    for sid, st in list(state.get("sessions", {}).items()):
        if st.get("source") != "api":
            continue
        if st.get("running") and sid not in alive:
            stop_session(sid, st)
            st["status"] = "idle"
        else:
            maybe_stop_idle(sid, st, now)
    reconcile_board(state, alive_sids=alive)
    return True


# ── 文件回退（API 不可用）──

def user_title(session: dict, content) -> str:
    return title_from(session.get("name") if isinstance(session.get("name"), str) else None,
                      content if isinstance(content, str) else None)


def process_file(path: Path, state: dict, now: float) -> None:
    if not path.name.endswith(".json"):
        return
    try:
        mtime = path.stat().st_mtime
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        log(f"skip {path.name}: {e}")
        return

    sid = str(data.get("session_id") or path.stem)
    msgs = data.get("messages") or []
    if not isinstance(msgs, list):
        return

    sessions = state.setdefault("sessions", {})
    known = sid in sessions
    st = ensure_st(state, sid)

    # 曾由 API 接管：API 挂了也不回放历史（会把已 Stop 的任务重新 SessionStart）
    if st.get("source") == "api":
        st["source"] = "file"
        st["msg_len"] = len(msgs)
        st["mtime"] = mtime
        if st.get("running"):
            mark_activity(st, now)
        maybe_stop_idle(sid, st, now)
        return

    st["source"] = "file"

    if not known:
        st["msg_len"] = len(msgs)
        st["mtime"] = mtime
        st["running"] = False
        st["idle_since"] = None
        return

    if mtime <= float(st.get("mtime") or 0) and not st.get("idle_since") and not st.get("running"):
        return
    st["mtime"] = mtime

    prev = int(st.get("msg_len") or 0)
    if len(msgs) < prev:
        prev = 0

    for m in msgs[prev:]:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        if role == "user":
            if is_system_user_msg(m.get("content")):
                continue
            report("SessionStart", sid, name=user_title(data, m.get("content")))
            st["running"] = True
            mark_activity(st, now)
        elif role == "tool":
            if st.get("running"):
                report("PostToolUse", sid)
            mark_activity(st, now)
        elif role == "assistant":
            if m.get("tool_calls"):
                if st.get("running"):
                    report("PostToolUse", sid)
                mark_activity(st, now)
            else:
                c = m.get("content")
                st["last_assistant"] = c.strip() if isinstance(c, str) else ""
                mark_activity(st, now, quiet_candidate=True)

    st["msg_len"] = len(msgs)
    maybe_stop_idle(sid, st, now)


def poll_files(state: dict, now: float) -> None:
    if not SESSIONS.is_dir():
        return
    for path in sorted(SESSIONS.glob("*.json")):
        try:
            process_file(path, state, now)
        except Exception as e:
            log(f"error {path.name}: {e}")
    for sid, st in list(state.get("sessions", {}).items()):
        if st.get("source") == "file":
            maybe_stop_idle(sid, st, now)
    reconcile_board(state, alive_sids=None)


def main() -> int:
    if not PY.exists() or not SCRIPT.exists():
        print("missing venv python or hook_report.py", file=sys.stderr)
        return 1
    log("clacky_session_watch started (api+file)")
    state = load_state()
    while True:
        now = time.time()
        ok = poll_api(state, now)
        if not ok:
            poll_files(state, now)
        try:
            save_state(state)
        except Exception as e:
            log(f"save_state: {e}")
        time.sleep(POLL_SEC)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        log("stopped")
        raise SystemExit(0)
