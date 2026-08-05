# AI 工作台进度监控 (ai-progress-monitor)

统一看板：多工作台（Cursor / Claude / Codex / OpenCode…）通过 **MCP** 或 **Hooks** 上报进度，网页实时查看（http://127.0.0.1:8777），关键节点会弹 macOS 通知。

> **给 AI**：也可直接读并执行 [`AGENTS.md`](./AGENTS.md)。下面两段 prompt 可整段复制发给任意工作台。

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

各工作台细节：`client-configs/`（把 `<repo_root>` 换成实际路径）。

---

## 接入 Prompt（整段复制发给 AI）

把 `<repo_root>` 换成本仓库绝对路径后再粘贴。

### 方式一 · Hooks（推荐 · Claude / Codex）

运行时自动上报，无需 AI「自觉」记着调用工具。

```
请帮我把 ai-progress-monitor 用 Hooks 接到你当前所在的工作台。

仓库根目录：<repo_root>
核心命令：python <repo_root>/scripts/hook_report.py --agent <你的工作台名>

请按你所在工作台完成配置（已存在则跳过，不要重复写）：
- Claude Code：把 <repo_root>/client-configs/claude-hooks.json 里的 hooks
  合并进 ~/.claude/settings.json（或项目 .claude/settings.json），
  并把其中的 <repo_root> 全部替换成真实路径。挂上 SessionStart / PostToolUse / Stop / SessionEnd。
- Codex：对照当前版本 hooks 文档，在 ~/.codex/config.toml（或项目 config.toml）
  挂上等价生命周期钩子，命令同上，--agent codex。可参考 <repo_root>/client-configs/codex.md。
- Cursor：把 <repo_root>/client-configs/cursor-hooks.json 合并进 ~/.cursor/hooks.json
  （或项目 .cursor/hooks.json），替换 <repo_root>，chmod +x <repo_root>/client-configs/cursor-hook.sh。
  挂上 sessionStart / beforeSubmitPrompt / postToolUse / afterAgentResponse / stop / sessionEnd
  （新建空会话不建任务；点发送才建/重启；停输出即结束；拍板用语亮黄灯）。
- OpenCode：hooks 支持有限，请改用下面「方式二 · MCP」。

配置完成后告诉我：改了哪些文件、是否需要重启工作台。
hooks 生效后无需再粘贴上报规则——运行时会自动 record_task / 心跳 / 收尾。
```

### 方式二 · MCP（兜底 · 全工作台可用）

```
请帮我把 ai-progress-monitor 这个 MCP server 安装/挂载到你当前所在的工作台，
配置完成后确认 record_task / update_progress / log_node / list_tasks 四个工具已加载。

仓库根目录：<repo_root>
MCP（stdio）启动方式：
  command = <repo_root>/.venv/bin/python
  args    = ["<repo_root>/server/mcp_server.py"]

请根据你所在的工作台选择对应的配置方式：
- Codex：执行  codex mcp add ai-progress-monitor -- <command> <args...>
- Cursor：往  ~/.cursor/mcp.json 的 mcpServers 里写入 ai-progress-monitor 条目
- Claude Code：执行  claude mcp add ai-progress-monitor --scope user -- <command> <args...>
- OpenCode：往  opencode.json 的 mcp 里写入 ai-progress-monitor 条目
也可以直接跑：<repo_root>/.venv/bin/python <repo_root>/scripts/setup_agents.py
若配置已存在，不要重复添加；完成后告诉我工具是否已可用。

同时请把下面「上报规则」写入你的长期规则文件（Cursor rules / CLAUDE.md / AGENTS.md 等），每个会话自动遵守。
```

**MCP 上报规则**（可单独复制，或跟上面那段一起发）：

```
从现在起，请在每个会话中自动通过 ai-progress-monitor MCP 上报你的任务进度，
无需我每次提醒。规则如下：
1. 会话开始、或接手一个长任务时：调用 record_task
   （task_id=你所属工作台名-短序号，agent=你所属工作台名，name=任务名）
2. 推进到新阶段时：调用 update_progress（stage=coding/testing/deploying 等阶段名）
3. 到达重要节点时：调用 log_node（node_type=step 或 milestone，message=简短中文描述）
4. 任务遇到需要我拍板/选择的决策点时：调用 log_node，
   message 里带上「需要选择 / 请你选 / 你来决定」等字样 → 看板亮黄灯
5. 任务完成：log_node（node_type=success）；失败：log_node（node_type=fail）
判断标准：不要等我要求才上报，做了实质工作就自动上报。
若 MCP 工具暂时不可用，静默跳过，不要阻塞主任务。
```

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
