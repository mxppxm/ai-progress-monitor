# AI 工作台进度监控 (ai-progress-monitor)

统一看板：多工作台（Cursor / Claude / Codex / OpenCode…）通过 **MCP** 或 **Hooks** 上报进度，网页实时查看（http://127.0.0.1:8777），关键节点会弹 macOS 通知。

> **给 AI**：请阅读并执行 [`AGENTS.md`](./AGENTS.md)（安装 MCP + 写入上报规则）。不要依赖本 README 的长文。

---

## 快速开始（人类）

```bash
# 1. 依赖
uv venv .venv && uv pip install "mcp[cli]" fastmcp fastapi uvicorn
# 或: python3 -m venv .venv && .venv/bin/pip install "mcp[cli]" fastmcp fastapi uvicorn

# 2. 看板
.venv/bin/python server/dashboard.py   # → http://127.0.0.1:8777

# 3. 一键挂 MCP（探测本机已装工作台）
.venv/bin/python scripts/setup_agents.py
```

开机自启（可选）：用 `scripts/com.local.ai-progress-monitor.plist.template`，替换 `__REPO_ROOT__` / `__HOME__` 后拷到 `~/Library/LaunchAgents/` 并 `launchctl load -w`。

各工作台细节：`client-configs/`（把 `<repo_root>` 换成实际路径）。Claude/Codex 也可走 Hooks，见同目录说明。

---

## 能力摘要

| 能力 | 说明 |
| :--- | :--- |
| MCP 上报 | `record_task` / `update_progress` / `log_node` / `list_tasks` |
| Hooks 自动上报 | `scripts/hook_report.py`（Claude/Codex 等原生 hook） |
| 三态卡片 | 运行中 · 待选择（黄灯）· 已结束；可手动点「结束」 |
| 实时看板 | SSE + 断线轮询兜底 |

---

## 目录

```
AGENTS.md          ← AI 接入入口（安装 + 上报规则）
server/            db · mcp_server · dashboard · notify
scripts/           setup_agents · hook_report · 自启模板
dashboard/         看板前端
client-configs/    各工作台手工配置说明
data/              SQLite（自动生成）
```
