# Claude Code 接入 ai-progress-monitor

Claude Code 通过 `claude mcp add` 命令注册 stdio MCP server。

## 注册
```bash
# 项目级
claude mcp add ai-progress-monitor --scope project -- /path/to/ai-progress-monitor/.venv/bin/python /path/to/ai-progress-monitor/server/mcp_server.py

# 用户级（全局生效）
claude mcp add ai-progress-monitor --scope user -- /path/to/ai-progress-monitor/.venv/bin/python /path/to/ai-progress-monitor/server/mcp_server.py
```

确认：
```bash
claude mcp list
```

## 在会话中使用
Claude 会自动识别 MCP 工具。你可以让它主动上报，甚至可以要求：

> 请在任何长任务中，通过 ai-progress-monitor 的 `record_task` 建立任务、`update_progress` 报告进度、`log_node` 标注关键节点。

建议把它写进 `~/.claude/CLAUDE.md` 作为长期指令，这样每次会话都会记得上报。

把路径换成实际仓库路径。