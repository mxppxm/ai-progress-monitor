"""系统通知 — 关键节点触发 macOS 横幅。

当上报的节点类型为 milestone/success/fail 时弹出系统通知，
让用户不用盯看板也能收到重要消息。
"""
import shutil
import subprocess

# 只在需要弹横幅的节点类型上触发
NOTIFY_TYPES = ("milestone", "success", "fail")

_ICONS = {"milestone": "🔥", "success": "✅", "fail": "❌"}


def _best_notifier():
    """优先 terminal-notifier，否则用 osascript 原生通知。"""
    if shutil.which("terminal-notifier"):
        return "terminal-notifier"
    return "osascript"


def notify_node(agent: str, task_name: str, node_type: str, message: str) -> None:
    """根据节点类型发送系统通知横幅。no-op if 不是关键节点。"""
    if node_type not in NOTIFY_TYPES:
        return
    icon = _ICONS.get(node_type, "")
    title = f"{icon} {agent} · {task_name}"
    notifier = _best_notifier()
    try:
        if notifier == "terminal-notifier":
            subprocess.run(
                ["terminal-notifier", "-title", title, "-message", message,
                 "-sound", "default"],
                check=False, timeout=5, capture_output=True,
            )
        else:
            # macOS 原生 AppleScript 通知
            script = f'display notification "{_safe(message)}" with title "{_safe(title)}"'
            subprocess.run(["osascript", "-e", script], check=False, timeout=5, capture_output=True)
    except Exception:
        # 通知失败不影响主流程，静默吞掉
        pass


def _safe(s: str) -> str:
    return s.replace('\\', '\\\\').replace('"', '\\"')[:80]