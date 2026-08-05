# AGENTS.md — AI 接入说明（请整份执行）

> 人类对你说「接入进度监控」时：**读本文件并立刻执行**，不要再去翻长 README。

本仓库路径记为 `REPO`（本文件所在目录的绝对路径）。

**优先 Hooks，MCP 仅作兜底。** Cursor / Claude / Codex 用 Hooks；OpenCode 或 hooks 不可用时再走 MCP。

---

## A. Hooks 安装（Cursor / Claude / Codex · 立刻做）

### Cursor

1. 把 `REPO/client-configs/cursor-hooks.json` 合并进 `~/.cursor/hooks.json`（替换其中 `<repo_root>` → `REPO`）
2. `chmod +x REPO/client-configs/cursor-hook.sh`
3. **删除**本机对 MCP 的依赖（若有）：
   - 从 `~/.cursor/mcp.json` 去掉 `ai-progress-monitor`
   - 删除要求调用 `record_task` 等的 Cursor rule（如 `~/.cursor/rules/ai-progress-monitor.mdc`）
4. 在 Settings → Hooks 确认已加载；必要时重启 Cursor

语义：点发送建/重启任务；停输出＝结束；回复含「需要你选择 / 你来决定」＝黄灯；空会话不建任务。

### Claude Code

合并 `REPO/client-configs/claude-hooks.json` → `~/.claude/settings.json`（替换 `<repo_root>`）。

### Codex

对照当前 hooks 文档配置 `~/.codex/config.toml`，命令：
`python REPO/scripts/hook_report.py --agent codex`（见 `client-configs/codex.md`）。

Hooks 生效后**不要**再写「请自觉调 MCP」类规则。

---

## B. MCP 安装（兜底 · 立刻做）

```bash
cd REPO
# 若无 .venv：
#   python3 -m venv .venv && .venv/bin/pip install "mcp[cli]" fastmcp fastapi uvicorn
.venv/bin/python scripts/setup_agents.py
```

只配当前工作台时加：`--cursor` / `--codex` / `--claude` / `--opencode`。

确认工具：`record_task` · `update_progress` · `log_node` · `list_tasks`。已存在则跳过。

然后把下面 **「MCP 上报协议」** 写入长期规则（Cursor rules / CLAUDE.md / AGENTS.md），勿重复堆叠。

---

## C. MCP 上报协议（仅 MCP 方式需要）

本会话已挂载 `ai-progress-monitor` MCP。做实质工作就自动上报；工具不可用则静默跳过。

1. **开长任务** → `record_task`（`task_id`=`工作台名-短序号`，`agent`=工作台名，`name`=任务名）
2. **换阶段** → `update_progress`（`stage`=coding/testing/…，`progress`=0–100）
3. **重要节点** → `log_node`（`node_type`=`step`|`milestone`，`message`=中文简述）
4. **需人类拍板** → `log_node`，`message` 含「需要选择 / 请你选 / 你来决定」→ 看板黄灯
5. **完成** → `log_node` `success`；**失败** → `fail`

写完后一句话告诉人类：用的 Hooks 还是 MCP、改了哪些文件。
