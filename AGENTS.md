# AGENTS.md — AI 接入说明（请整份执行）

> 人类对你说「接入进度监控 / 安装这个 MCP」时：**读本文件并立刻执行**，不要再去翻 README。

本仓库路径记为 `REPO`（本文件所在目录的绝对路径）。

---

## 1. 安装 MCP（立刻做）

```bash
cd REPO
# 若无 .venv：
#   python3 -m venv .venv && .venv/bin/pip install "mcp[cli]" fastmcp fastapi uvicorn
.venv/bin/python scripts/setup_agents.py
```

只配当前工作台时加对应 flag：`--cursor` / `--codex` / `--claude` / `--opencode`。

完成后确认工具可用：`record_task` · `update_progress` · `log_node` · `list_tasks`。已存在则跳过，不要重复添加。

---

## 2. 写入上报规则（立刻做）

把下面 **「上报协议」** 整段写入当前工作台的长期规则（已存在同类规则则合并/更新，勿重复堆叠）：

| 工作台 | 写入位置 |
| :----- | :------- |
| Cursor | 用户规则或项目 `.cursor/rules/`（建议 alwaysApply） |
| Claude Code | `~/.claude/CLAUDE.md` 或项目 `CLAUDE.md` |
| Codex | `~/.codex/AGENTS.md` 或项目 `AGENTS.md` |
| 其他 | 该工作台的全局/项目 instruction 文件 |

写完后用一句话告诉人类：MCP 是否已挂上、规则写到了哪里。

---

## 3. 上报协议（每个会话自动遵守）

本会话已挂载 `ai-progress-monitor` MCP。做实质工作就自动上报，无需人类提醒；工具不可用则静默跳过。

1. **开长任务** → `record_task`（`task_id`=`工作台名-短序号`，`agent`=工作台名，`name`=任务名）
2. **换阶段** → `update_progress`（`stage`=coding/testing/…，`progress`=0–100）
3. **重要节点** → `log_node`（`node_type`=`step`|`milestone`，`message`=中文简述）
4. **需人类拍板** → `log_node`，`message` 含「需要选择 / 请你选 / 你来决定」→ 看板黄灯
5. **完成** → `log_node` `success`；**失败** → `fail`（会通知并改状态）
