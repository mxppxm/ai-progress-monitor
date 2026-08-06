"""系统通知 — 关键节点触发 macOS 横幅；点击横幅聚焦对应工作台。

使用 data/terminal-notifier.app（缺失则从 GitHub 拉取），-execute 调用 focus_agent。
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

NOTIFY_TYPES = ("milestone", "success", "fail")
_ICONS = {"milestone": "🔥", "success": "✅", "fail": "❌"}

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data"
PENDING = DATA / "pending_notify.json"
TN_APP = DATA / "terminal-notifier.app"
TN_BIN = TN_APP / "Contents" / "MacOS" / "terminal-notifier"
TN_ZIP_URL = (
    "https://github.com/julienXX/terminal-notifier/releases/download/"
    "2.0.0/terminal-notifier-2.0.0.zip"
)
PY = REPO / ".venv" / "bin" / "python"
FOCUS_CLI = REPO / "scripts" / "focus_agent.py"


def _safe(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')[:80]


def _shell_quote(s: str) -> str:
    return "'" + s.replace("'", "'\"'\"'") + "'"


def _py() -> str:
    return str(PY if PY.exists() else Path(sys.executable))


def _write_pending(agent: str, task_id: str | None, title: str, message: str) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    PENDING.write_text(
        json.dumps(
            {
                "agent": agent,
                "task_id": task_id or "",
                "title": title,
                "message": message,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _focus_shell(agent: str, task_id: str | None) -> str:
    cmd = [_py(), str(FOCUS_CLI), "--agent", agent]
    if task_id:
        cmd += ["--task-id", task_id]
    return " ".join(_shell_quote(c) for c in cmd)


def _ensure_terminal_notifier() -> Path | None:
    """PATH / 已下载 / 现拉 GitHub release。"""
    which = shutil.which("terminal-notifier")
    if which:
        return Path(which)
    if TN_BIN.exists():
        return TN_BIN

    DATA.mkdir(parents=True, exist_ok=True)
    zip_path = DATA / "terminal-notifier.zip"
    try:
        urllib.request.urlretrieve(TN_ZIP_URL, zip_path)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(DATA)
        zip_path.unlink(missing_ok=True)
        # zip 内可能是顶层 terminal-notifier.app
        if not TN_BIN.exists():
            for p in DATA.rglob("terminal-notifier"):
                if p.name == "terminal-notifier" and p.parent.name == "MacOS":
                    # 已在子目录，挪到 DATA/terminal-notifier.app
                    app = p.parents[2]
                    if app != TN_APP and app.name.endswith(".app"):
                        if TN_APP.exists():
                            shutil.rmtree(TN_APP)
                        shutil.move(str(app), str(TN_APP))
                    break
        if TN_BIN.exists():
            TN_BIN.chmod(TN_BIN.stat().st_mode | 0o111)
            return TN_BIN
    except Exception:
        try:
            zip_path.unlink(missing_ok=True)
        except Exception:
            pass
    return None


def _notify_via_tn(bin_path: Path, agent: str, task_id: str | None, title: str, message: str) -> None:
    _write_pending(agent, task_id, title, message)
    subprocess.run(
        [
            str(bin_path),
            "-title", title,
            "-message", message,
            "-sound", "default",
            "-execute", _focus_shell(agent, task_id),
        ],
        check=False,
        timeout=8,
        capture_output=True,
    )


def _notify_via_osascript(title: str, message: str) -> None:
    # 无点击聚焦能力（点开常进 Script Editor）；仅兜底
    script = f'display notification "{_safe(message)}" with title "{_safe(title)}"'
    subprocess.run(["osascript", "-e", script], check=False, timeout=5, capture_output=True)


def _send(agent: str, task_id: str | None, title: str, message: str) -> None:
    body = (message or "").strip() or " "
    title = (title or "AI Progress").strip()
    try:
        tn = _ensure_terminal_notifier()
        if tn:
            _notify_via_tn(tn, agent, task_id, title, body)
            return
        _notify_via_osascript(title, body)
    except Exception:
        pass


def notify_node(
    agent: str,
    task_name: str,
    node_type: str,
    message: str,
    task_id: str | None = None,
) -> None:
    if node_type not in NOTIFY_TYPES:
        return
    icon = _ICONS.get(node_type, "")
    title = f"{icon} {agent} · {task_name}"
    _send(agent, task_id, title, message)


def notify_choice(
    agent: str,
    task_name: str,
    message: str,
    task_id: str | None = None,
) -> None:
    title = f"🟡 {agent} · 待选择：{task_name}"
    body = (message or "有一个决策点需要你过去选择").strip()[:80]
    _send(agent, task_id, title, body)
