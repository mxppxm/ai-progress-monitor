#!/usr/bin/env python3
"""自动配置各 AI 工作台的 MCP — 一键接入 ai-progress-monitor。

探测已安装的 Agent 并写入对应 MCP 配置，让它们启动会话时自动挂载
record_task / update_progress / log_node / list_tasks 四个工具。

用法：
    python3 setup_agents.py            # 自动探测并配置已安装的工作台
    python3 setup_agents.py --report   # 只报告，不改动
    python3 setup_agents.py --codex --cursor --claude   # 只配置指定工作台

支持：codex / cursor / claude / opencode
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MCP_RUN = str(REPO / ".venv" / "bin" / "python")
MCP_ARGS = [str(REPO / "server" / "mcp_server.py")]
DESC = "AI 工作台进度监控 — record_task/update_progress/log_node/list_tasks"

HOME = Path.home()


# ── 各工作台工具实现 ─────────────────────────────────────────────
def _merge_json(path: Path, key: str, entry: dict) -> bool:
    """把 entry 合并进 path 的 json[key] 字典，幂等（已存在则跳过）。"""
    if not path.exists():
        data = {}
    else:
        try:
            data = json.loads(path.read_text())
        except Exception:
            print(f"  ⚠️  {path} 不是合法 JSON，跳过。")
            return False
    servers = data.setdefault(key, {})
    if entry["name"] in servers:
        print(f"  ✓ {path} 已配置 {entry['name']}，跳过")
        return True
    cmd = {"type": "stdio", "command": entry["command"], "args": entry["args"],
           "description": DESC}
    servers[entry["name"]] = cmd
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(f"  ✓ 已写入 {path}")
    return True


def setup_codex():
    print("[Codex]")
    if not shutil.which("codex"):
        print("  未安装，跳过")
        return
    path = HOME / ".codex" / "mcp.json"
    _merge_json(path, "mcpServers",
                {"name": "ai-progress-monitor", "command": MCP_RUN, "args": MCP_ARGS})


def setup_cursor():
    print("[Cursor]")
    if not shutil.which("cursor"):
        print("  未安装，跳过")
        return
    path = HOME / ".cursor" / "mcp.json"
    _merge_json(path, "mcpServers",
                {"name": "ai-progress-monitor", "command": MCP_RUN, "args": MCP_ARGS})


def setup_claude():
    print("[Claude Code]")
    if not shutil.which("claude"):
        print("  未安装，跳过")
        return
    # 优先用官方 CLI（最可靠）
    try:
        r = subprocess.run(
            ["claude", "mcp", "add", "ai-progress-monitor", "--scope", "user",
             "--", MCP_RUN, *MCP_ARGS],
            capture_output=True, text=True, timeout=60)
        if r.returncode == 0 or "already" in (r.stdout + r.stderr).lower():
            print("  ✓ claude mcp add 成功")
        else:
            print(f"  ⚠️ claude mcp add 异常:\n  {(r.stdout+r.stderr).strip()}")
            _merge_json(HOME / ".claude.json", "mcpServers",
                        {"name": "ai-progress-monitor", "command": MCP_RUN, "args": MCP_ARGS})
    except Exception as e:
        print(f"  ⚠️ claude 命令执行失败: {e}")


def setup_opencode():
    print("[OpenCode]")
    if not shutil.which("opencode"):
        print("  未安装，跳过")
        return
    path = REPO / "opencode.json"
    _merge_json(path, "mcp",
                {"name": "ai-progress-monitor", "command": MCP_RUN, "args": MCP_ARGS})


AGENTS = {"codex": setup_codex, "cursor": setup_cursor,
          "claude": setup_claude, "opencode": setup_opencode}


def report():
    print("安装状态报告：")
    for name in AGENTS:
        found = shutil.which(name)
        print(f"  {name:10} {'✓ ' + str(found) if found else '✗ 未安装'}")
    # 展示已配置项
    for name, path in [("codex", HOME / ".codex/mcp.json"),
                       ("cursor", HOME / ".cursor/mcp.json"),
                       ("claude", HOME / ".claude.json"),
                       ("opencode", REPO / "opencode.json")]:
        has = False
        try:
            if path.exists():
                data = json.loads(path.read_text())
                has = "ai-progress-monitor" in json.dumps(data)
        except Exception:
            pass
        print(f"  → {name} 的配置{'已含' if has else '未含'} ai-progress-monitor")


def main():
    ap = argparse.ArgumentParser(description=DESC)
    ap.add_argument("--report", action="store_true", help="只报告配置状态")
    for n in AGENTS:
        ap.add_argument(f"--{n}", action="store_true", dest=f"do_{n}")
    args = ap.parse_args()

    if args.report:
        report()
        return

    wanted = [n for n in AGENTS if getattr(args, f"do_{n}")]
    if not wanted:
        wanted = list(AGENTS)  # 默认全部

    print(f"开始配置: {', '.join(wanted)}\n")
    for n in wanted:
        AGENTS[n]()
        print()
    print("完成！重启各工作台后即可使用。")


if __name__ == "__main__":
    main()