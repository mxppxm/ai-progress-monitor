# 安装 ai-progress-monitor MCP

> Agent：读完本文档后**立刻执行**，不要只给说明。已存在且正确的配置跳过，勿重复堆叠。
>
> **注意**：Cursor / Claude / Codex 优先用 Hooks（见同目录 `hooks.md`）。仅当 hooks 不可用（如 OpenCode），或用户明确要求 MCP 时，才执行本文档。

## 概述

挂载 stdio MCP server，工具：`record_task` · `update_progress` · `log_node` · `list_tasks`。看板：http://127.0.0.1:8777。

## 一、解析仓库路径 REPO

按顺序取第一个可用的：

1. 当前 workspace / cwd 已是本仓库（存在 `server/mcp_server.py`）→ 用其绝对路径
2. 用户消息里写了路径 → 用该路径
3. 默认常见路径：`~/clacky_workspace/ai-progress-monitor`（若存在）
4. 仍找不到 → 询问用户 REPO 绝对路径

## 二、确认依赖

```bash
cd "$REPO"
# 若无 .venv：
python3 -m venv .venv
.venv/bin/pip install "mcp[cli]" fastmcp fastapi uvicorn
```

MCP 启动：

```text
command = $REPO/.venv/bin/python
args    = ["$REPO/server/mcp_server.py"]
```

## 三、挂到当前工作台

只配当前工作台。已存在 `ai-progress-monitor` 则跳过。

### 一键（推荐）

```bash
$REPO/.venv/bin/python $REPO/scripts/setup_agents.py
# 只配当前工作台时加：--cursor / --codex / --claude / --opencode
```

### 或手工

| 工作台 | 做法 |
| :--- | :--- |
| Codex | `codex mcp add ai-progress-monitor -- $REPO/.venv/bin/python $REPO/server/mcp_server.py` |
| Claude Code | `claude mcp add ai-progress-monitor --scope user -- $REPO/.venv/bin/python $REPO/server/mcp_server.py` |
| Cursor | 写入 `~/.cursor/mcp.json` 的 `mcpServers.ai-progress-monitor` |
| OpenCode | 写入 `opencode.json` 的 `mcp` 条目 |

确认四个工具已加载。

## 四、写入 MCP 上报协议（长期规则）

把下面协议写入当前工作台的长期规则（Cursor rules / CLAUDE.md / AGENTS.md 等），**勿与已有同文重复堆叠**。Hooks 已生效的工作台**不要**写这段。

```
本会话已挂载 ai-progress-monitor MCP。做实质工作就自动上报；工具不可用则静默跳过。

1. 开长任务 / 用户新提示词 → record_task
   （task_id=工作台名-短序号，agent=工作台名，name=本轮用户提示词摘要）
2. 同一会话任务重启 → 再次 record_task，name 改为新提示词
3. 换阶段 → update_progress（stage=coding/testing/…，progress=0–100）
4. 重要节点 → log_node（node_type=step|milestone，message=中文简述）
5. 需人类拍板 → log_node，message 含「需要选择 / 请你选 / 你来决定」→ 看板黄灯
6. 完成 → log_node success；失败 → fail
```

## 五、完成回执

一句话告诉用户：用的 MCP、改了哪些文件、工具是否可用。
