# OpenCode 接入 ai-progress-monitor

OpenCode 通过项目根目录的 `opencode.json` 配置 MCP servers。

## 配置
创建 `opencode.json`（项目根目录）：
```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "ai-progress-monitor": {
      "type": "stdio",
      "command": "/path/to/ai-progress-monitor/.venv/bin/python",
      "args": ["/path/to/ai-progress-monitor/server/mcp_server.py"]
    }
  }
}
```

或用 CLI 添加：
```bash
opencode mcp add ai-progress-monitor -- python /path/to/ai-progress-monitor/server/mcp_server.py
```

## 在会话中使用
`opencode` 列表查看可用工具。让 OpenCode 在项目文件 `.opencode/agents/` 或全局指令里定期上报进度。

把路径换成实际仓库路径。