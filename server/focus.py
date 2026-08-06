"""把看板点击映射到本机工作台 App / URL（macOS）。"""
from __future__ import annotations

import json
import subprocess
import urllib.request
from pathlib import Path

# 键顺序 = 看板默认泳道顺序（「已注册工作台」）
AGENT_APPS: dict[str, tuple[str, ...]] = {
    "cursor": ("Cursor",),
    "codex": ("Codex",),
    "reasonix": ("Reasonix",),
    # clacky 走 Chrome，不在此列
}

CLACKY_BASE = "http://127.0.0.1:7070"
CLACKY_SESSIONS = Path.home() / ".clacky" / "sessions"


def registered_agents() -> list[str]:
    """返回已注册、可聚焦的工作台 ID 列表（固定顺序）。"""
    return ["cursor", "codex", "reasonix", "clacky"]


def _open_app(app: str) -> bool:
    r = subprocess.run(
        ["open", "-a", app],
        check=False,
        timeout=5,
        capture_output=True,
    )
    return r.returncode == 0


def _resolve_clacky_session_id(task_id: str | None) -> str | None:
    """从 task_id=clacky-XXXXXXXX 解析完整 session_id；无则取最近会话。"""
    prefix = ""
    if task_id and task_id.startswith("clacky-"):
        prefix = task_id[len("clacky-") :].strip()

    # 优先打本机 API（与 UI 一致）
    try:
        with urllib.request.urlopen(f"{CLACKY_BASE}/api/sessions", timeout=2) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        sessions = data.get("sessions") or []
        if prefix:
            for s in sessions:
                sid = str(s.get("id") or "")
                if sid.startswith(prefix):
                    return sid
        if sessions:
            return str(sessions[0].get("id") or "") or None
    except Exception:
        pass

    # 兜底：扫本地 sessions 目录
    if not CLACKY_SESSIONS.is_dir():
        return None
    files = sorted(CLACKY_SESSIONS.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in files:
        try:
            sid = str(json.loads(path.read_text(encoding="utf-8")).get("session_id") or "")
        except Exception:
            continue
        if not sid:
            continue
        if prefix and sid.startswith(prefix):
            return sid
        if not prefix:
            return sid
    return None


def _focus_clacky_chrome(url: str) -> dict:
    """在 Google Chrome 中打开/激活 Clacky 标签页（优先复用已有 7070 标签）。"""
    # AppleScript：找到已有 127.0.0.1:7070 标签则激活并跳到目标 URL，否则新开
    script = f'''
tell application "Google Chrome"
  activate
  set targetURL to "{url}"
  set found to false
  repeat with w in windows
    set tabIndex to 0
    repeat with t in tabs of w
      set tabIndex to tabIndex + 1
      set u to URL of t
      if u starts with "{CLACKY_BASE}" then
        set URL of t to targetURL
        set active tab index of w to tabIndex
        set index of w to 1
        set found to true
        exit repeat
      end if
    end repeat
    if found then exit repeat
  end repeat
  if not found then
    open location targetURL
  end if
end tell
'''
    try:
        r = subprocess.run(
            ["osascript", "-e", script],
            check=False,
            timeout=8,
            capture_output=True,
            text=True,
        )
        if r.returncode == 0:
            return {"ok": True, "app": "Google Chrome", "agent": "clacky", "url": url}
    except Exception as e:
        return {"ok": False, "error": str(e), "url": url}

    # Chrome / osascript 失败时退回系统 open
    try:
        r = subprocess.run(
            ["open", "-a", "Google Chrome", url],
            check=False,
            timeout=5,
            capture_output=True,
        )
        if r.returncode == 0:
            return {"ok": True, "app": "Google Chrome", "agent": "clacky", "url": url}
    except Exception as e:
        return {"ok": False, "error": str(e), "url": url}

    return {"ok": False, "error": "无法打开 Google Chrome", "url": url}


def focus_agent(agent: str, task_id: str | None = None) -> dict:
    """尝试把对应工作台拉到前台。返回 {ok, app?} 或 {ok:False, error}。"""
    key = (agent or "").strip().lower()

    if key == "clacky":
        sid = _resolve_clacky_session_id(task_id)
        url = f"{CLACKY_BASE}/#session/{sid}" if sid else f"{CLACKY_BASE}/"
        return _focus_clacky_chrome(url)

    apps = AGENT_APPS.get(key)
    if not apps:
        return {"ok": False, "error": f"未知工作台: {agent!r}"}

    tried: list[str] = []
    for app in apps:
        tried.append(app)
        try:
            if _open_app(app):
                return {"ok": True, "app": app, "agent": key}
        except Exception as e:
            return {"ok": False, "error": str(e), "tried": tried}

    return {
        "ok": False,
        "error": f"未能打开 {key}（已尝试: {', '.join(tried)}）",
        "tried": tried,
    }
