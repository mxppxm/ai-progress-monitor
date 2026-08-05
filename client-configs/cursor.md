# Cursor 接入 ai-progress-monitor

Cursor 的 hooks 支持相对有限，**建议用 MCP 方式**接入（稳定可靠）。

## 方式一：Hooks（可选）
如你的 Cursor 版本支持 hooks，可把 `python <repo_root>/scripts/hook_report.py --agent cursor` 挂到
会话开始 / 工具结束事件上（事件名以你 Cursor 版本的 hooks 配置为准）。

## 方式二：MCP（推荐）

Cursor 通过 `.cursor/mcp.json` 配置 stdio MCP server。

### 项目级配置
在你的项目根目录创建 `.cursor/mcp.json`：
```json
{
  "mcpServers": {
    "ai-progress-monitor": {
      "command": "<repo_root>/.venv/bin/python",
      "args": ["<repo_root>/server/mcp_server.py"]
    }
  }
}
```

### 全局配置
- Cursor 设置 → Features → MCP → 添加
- Command: `<repo_root>/.venv/bin/python`
- Args: `<repo_root>/server/mcp_server.py`

配置后重启 Cursor，Tools 面板里会出现 `ai-progress-monitor` 的 4 个工具。

## 在 Cursor 中使用（MCP 方式）
先在对话里让 Cursor 了解上报约定（也可放进 `.cursor/rules` 让长期生效）：

> 你每次完成阶段性工作时，用 ai-progress-monitor 的 `record_task`/`update_progress`/`log_node` 上报进度到看板。

---
把 `<repo_root>` 换成你的实际仓库路径。