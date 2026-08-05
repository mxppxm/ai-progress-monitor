# AI 工作台进度监控 (ai-progress-monitor)

统一看板：多工作台（Cursor / Claude / Codex / OpenCode…）通过 **MCP** 或 **Hooks** 上报进度，网页实时查看（http://127.0.0.1:8777），关键节点会弹 macOS 通知。

> **给 AI**：也可直接读并执行 [`AGENTS.md`](./AGENTS.md)。下面 prompt 可整段复制发给对应工作台。

**Hooks 语义（看板三态）**

| 时机 | 看板 |
| :--- | :--- |
| 用户提交提示词 | 建/重启任务为「运行中」，**标题＝本轮提示词** |
| 停止输出 | 「已结束」；若回复含「需要你选择 / 你来决定」→「待选择」黄灯 |
| 再发一条消息 | 同一任务重启，标题换成新提示词 |
| 新建空会话 | 不建任务（只注入拍板用语提示） |

---

## 快速开始（人类）

```bash
# 1. 依赖
uv venv .venv && uv pip install "mcp[cli]" fastmcp fastapi uvicorn
# 或: python3 -m venv .venv && .venv/bin/pip install "mcp[cli]" fastmcp fastapi uvicorn

# 2. 看板
.venv/bin/python server/dashboard.py   # → http://127.0.0.1:8777

# 3. 一键挂 MCP（探测本机已装工作台；Hooks 优先时可不跑）
.venv/bin/python scripts/setup_agents.py
```

开机自启（可选）：用 `scripts/com.local.ai-progress-monitor.plist.template`，替换 `__REPO_ROOT__` / `__HOME__` 后拷到 `~/Library/LaunchAgents/` 并 `launchctl load -w`。

各工作台细节：`client-configs/`（把 `<repo_root>` 换成实际路径）。

---

## 接入 Prompt（整段复制发给 AI）

把下面各段里的 `<repo_root>` 换成本仓库**绝对路径**后再粘贴（若已在本仓库打开，可让 AI 自行 `pwd` 解析）。

### Codex 一键接入（推荐 · 整段复制到 Codex）

```
请立刻把 ai-progress-monitor 用 Hooks 接到当前 Codex，装好即可用，不要只给说明。

仓库根目录 REPO=<repo_root>
（若你已在该仓库里，用当前 workspace 绝对路径作为 REPO。）

请按顺序执行（已存在且正确则跳过，不要重复堆叠）：

1. 确认依赖
   - 若 REPO/.venv 不存在：python3 -m venv REPO/.venv && REPO/.venv/bin/pip install "mcp[cli]" fastmcp fastapi uvicorn
   - 用 REPO/.venv/bin/python 作为 hook 解释器

2. 写入 ~/.codex/hooks.json
   - 以 REPO/client-configs/codex-hooks.json 为模板
   - 把其中所有 <repo_root> 替换成 REPO 的绝对路径
   - 若 ~/.codex/hooks.json 已有其他 hooks：合并 hooks 对象，保留其它条目，仅覆盖/写入 ai-progress-monitor 这几组事件
   - 必须挂上：SessionStart / UserPromptSubmit / PostToolUse / Stop / SessionEnd
   - 命令形态：REPO/.venv/bin/python REPO/scripts/hook_report.py --agent codex

3. 确保 ~/.codex/config.toml 开启 hooks：
   [features]
   hooks = true

4. 语义（与看板对齐，无需再写 MCP 自觉上报规则）：
   - SessionStart → 只注入黄灯提示，空会话不建任务
   - UserPromptSubmit → 建/重启任务，标题＝本轮用户提示词
   - PostToolUse → 心跳 step（不改标题）
   - Stop → 停止输出＝已结束；末条含「需要你选择 / 你来决定」＝黄灯待选择
   - SessionEnd → 仍 running 则结束；已结束/待选择保持

5. 完成后告诉我：改了哪些文件；提醒我在 Codex 执行 /hooks 信任新 hooks，必要时重启 Codex。
   hooks 生效后不要再安装 MCP 上报规则。
```

### Cursor / Claude 等 · Hooks

```
请帮我把 ai-progress-monitor 用 Hooks 接到你当前所在的工作台。

仓库根目录：<repo_root>
核心命令：<repo_root>/.venv/bin/python <repo_root>/scripts/hook_report.py --agent <你的工作台名>

请按你所在工作台完成配置（已存在则跳过，不要重复写）：
- Claude Code：把 <repo_root>/client-configs/claude-hooks.json 合并进 ~/.claude/settings.json
  （替换 <repo_root>）。挂上 SessionStart / PostToolUse / Stop / SessionEnd。
- Cursor：把 <repo_root>/client-configs/cursor-hooks.json 合并进 ~/.cursor/hooks.json
  （替换 <repo_root>），chmod +x <repo_root>/client-configs/cursor-hook.sh。
  挂上 sessionStart / beforeSubmitPrompt / postToolUse / afterAgentResponse / stop / sessionEnd。
- Codex：请改用上面「Codex 一键接入」那段（写 ~/.codex/hooks.json，见 client-configs/codex-hooks.json）。
- OpenCode：hooks 支持有限，请改用下面「方式二 · MCP」。

语义：用户提交提示词 → 建/重启（标题＝提示词）；停输出 → 结束；
回复含「需要你选择 / 你来决定」→ 黄灯；空会话不建任务。

配置完成后告诉我：改了哪些文件、是否需要重启工作台。
hooks 生效后无需再粘贴上报规则。
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
   （task_id=你所属工作台名-短序号，agent=你所属工作台名，name=本轮用户提示词摘要）
2. 同一会话用户又发新提示词、任务重启时：再次 record_task，name 改为新提示词
3. 推进到新阶段时：调用 update_progress（stage=coding/testing/deploying 等阶段名）
4. 到达重要节点时：调用 log_node（node_type=step 或 milestone，message=简短中文描述）
5. 任务遇到需要我拍板/选择的决策点时：调用 log_node，
   message 里带上「需要选择 / 请你选 / 你来决定」等字样 → 看板亮黄灯
6. 任务完成：log_node（node_type=success）；失败：log_node（node_type=fail）
判断标准：不要等我要求才上报，做了实质工作就自动上报。
若 MCP 工具暂时不可用，静默跳过，不要阻塞主任务。
```

---

## 能力摘要

| 能力 | 说明 |
| :--- | :--- |
| MCP 上报 | `record_task` / `update_progress` / `log_node` / `list_tasks` |
| Hooks 自动上报 | `scripts/hook_report.py`（Cursor / Claude / Codex） |
| 三态卡片 | 运行中 · 待选择（黄灯）· 已结束；标题随新提示词更新；可手动「结束」 |
| 实时看板 | SSE + 断线轮询兜底 |

---

## 目录

```
AGENTS.md          ← AI 接入入口（安装 + 上报规则）
server/            db · mcp_server · dashboard · notify
scripts/           setup_agents · hook_report · 自启模板
dashboard/         看板前端
client-configs/    各工作台 hooks 模板与说明（含 codex-hooks.json）
data/              SQLite（自动生成）
```
