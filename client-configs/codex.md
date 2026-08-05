# Codex 接入 ai-progress-monitor

Codex (OpenAI) 通过 stdio MCP server 方式接入。先确认 Python + mcp 包就绪：

```bash
pip install "mcp[cli]" fastmcp 2>/dev/null  # 安装 MCP 运行时
```

## 方式一：命令注册（推荐）
```bash
codex mcp add ai-progress-monitor -- /path/to/ai-progress-monitor/.venv/bin/python /path/to/ai-progress-monitor/server/mcp_server.py
```

## 方式二：配置文件
编辑 `~/.codex/mcp.json`：
```json
{
  "mcpServers": {
    "ai-progress-monitor": {
      "command": "/path/to/ai-progress-monitor/.venv/bin/python",
      "args": ["/path/to/ai-progress-monitor/server/mcp_server.py"],
      "type": "stdio"
    }
  }
}
```

## 在 Codex 会话中使用
对话里直接让 Codex 上报进度，例如：

> 任务开始：调用 `record_task` task_id=codex-001 agent=codex name="重构登录模块"
> 写代码中：`update_progress` progress=50 stage=coding
> 完成：`log_node` node_type=milestone message="登录重构完成，测试通过"

把路径换成你的实际仓库路径即可。