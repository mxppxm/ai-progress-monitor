# AI 工作台进度监控 (ai-progress-monitor)

统一看板：多工作台（Cursor / Claude / Codex / OpenCode…）通过 **Hooks**（推荐）或 **MCP** 上报进度，网页实时查看（http://127.0.0.1:8777），关键节点会弹 macOS 通知。

---

## 快速开始（人类）

```bash
# 1. 依赖
uv venv .venv && uv pip install "mcp[cli]" fastmcp fastapi uvicorn
# 或: python3 -m venv .venv && .venv/bin/pip install "mcp[cli]" fastmcp fastapi uvicorn

# 2. 看板
.venv/bin/python server/dashboard.py   # → http://127.0.0.1:8777
```

开机自启（可选）：`scripts/com.local.ai-progress-monitor.plist.template`，替换 `__REPO_ROOT__` / `__HOME__` 后拷到 `~/Library/LaunchAgents/` 并 `launchctl load -w`。

---

## 接入话术（复制发给 AI）

把 `<repo>` 换成仓库绝对路径，或直接用 GitHub raw 链接（无需先打开仓库）。

### Hooks（推荐 · Cursor / Claude / Codex）

```
请根据 <repo>/install/hooks.md，安装 hooks。
```

GitHub：

```
请根据 https://raw.githubusercontent.com/mxppxm/ai-progress-monitor/main/install/hooks.md，安装 hooks。
```

### MCP（兜底 · OpenCode 或 hooks 不可用时）

```
请根据 <repo>/install/mcp.md，安装 mcp。
```

GitHub：

```
请根据 https://raw.githubusercontent.com/mxppxm/ai-progress-monitor/main/install/mcp.md，安装 mcp。
```

> Agent 读对应文档后自行安装；细节见 [`install/hooks.md`](./install/hooks.md) / [`install/mcp.md`](./install/mcp.md)。本地总览也可读 [`AGENTS.md`](./AGENTS.md)。

**Hooks 语义（看板三态）**

| 时机 | 看板 |
| :--- | :--- |
| 用户提交提示词 | 建/重启为「运行中」，**标题＝本轮提示词** |
| 停止输出 | 「已结束」；回复含「需要你选择 / 你来决定」→「待选择」黄灯 |
| 再发消息 | 同一任务重启，标题换成新提示词 |
| 新建空会话 | 不建任务（只注入拍板用语提示） |

---

## 能力摘要

| 能力 | 说明 |
| :--- | :--- |
| Hooks 自动上报 | `scripts/hook_report.py`（Cursor / Claude / Codex） |
| MCP 上报 | `record_task` / `update_progress` / `log_node` / `list_tasks` |
| 三态卡片 | 运行中 · 待选择（黄灯）· 已结束；标题随新提示词更新 |
| 实时看板 | SSE + 断线轮询兜底 |

---

## 目录

```
install/           ← AI 安装入口（hooks.md / mcp.md）
AGENTS.md          ← 本地总览（与 install 对齐）
server/            db · mcp_server · dashboard · notify
scripts/           setup_agents · hook_report · 自启模板
dashboard/         看板前端
client-configs/    各工作台 hooks 模板
data/              SQLite（自动生成）
```
