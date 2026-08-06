"""把看板点击映射到本机工作台 App（macOS `open -a`）。"""
from __future__ import annotations

import subprocess

# 按优先级尝试；Claude Code 多为终端，故回退到常见终端 App
AGENT_APPS: dict[str, tuple[str, ...]] = {
    "cursor": ("Cursor",),
    "codex": ("Codex",),
    "clacky": ("OpenClacky", "Clacky"),
    "opencode": ("FreeCode", "OpenCode"),
    "claude": ("Claude", "Ghostty", "Terminal"),
}


def focus_agent(agent: str) -> dict:
    """尝试把对应工作台拉到前台。返回 {ok, app?} 或 {ok:False, error}。"""
    key = (agent or "").strip().lower()
    apps = AGENT_APPS.get(key)
    if not apps:
        return {"ok": False, "error": f"未知工作台: {agent!r}"}

    tried: list[str] = []
    for app in apps:
        tried.append(app)
        try:
            r = subprocess.run(
                ["open", "-a", app],
                check=False,
                timeout=5,
                capture_output=True,
            )
        except Exception as e:
            return {"ok": False, "error": str(e), "tried": tried}
        if r.returncode == 0:
            return {"ok": True, "app": app, "agent": key}

    return {
        "ok": False,
        "error": f"未能打开 {key}（已尝试: {', '.join(tried)}）",
        "tried": tried,
    }
