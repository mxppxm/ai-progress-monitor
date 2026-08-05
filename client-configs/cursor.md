# Cursor 接入 ai-progress-monitor

Cursor 通过 `.cursor/mcp.json` 配置 stdio MCP server。

## 配置
在你的项目根目录创建 `.cursor/mcp.json`：
```json
{
  "mcpServers": {
    "ai-progress-monitor": {
      "command": "/path/to/ai-progress-monitor/.venv/bin/python",
      "args": ["/path/to/ai-progress-monitor/server/mcp_server.py"]
    }
  }
}
```

或者全局配置（对所有项目生效）：
- Cursor 设置 → Features → MCP → 添加
- Command: `/path/to/ai-progress-monitor/.venv/bin/python`
- Args: `/path/to/ai-progress-monitor/server/mcp_server.py`

配置后重启 Cursor，Tools 面板里会出现 `ai-progress-monitor` 的 4 个工具。

## 在 Cursor 中使用
先在对话里让 Cursor 了解上报约定（也可放进 `.cursor/rules` 让长期生效）：

> 你每次完成阶段性工作时，用 ai-progress-monitor 的 `record_task`/`update_progress`/`log_node` 上报进度到看板。

把路径换成实际仓库路径。