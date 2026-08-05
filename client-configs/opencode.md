# OpenCode 接入 ai-progress-monitor

OpenCode 的 hooks 支持相对有限，**建议用 MCP 方式**接入。

## 方式一：Hooks（可选）
如你的 OpenCode 版本支持 hooks，可把 `python <repo_root>/scripts/hook_report.py --agent opencode` 挂到
会话生命周期事件上（事件名以你 OpenCode 版本的 hooks 配置为准）。

## 方式二：MCP（推荐）

OpenCode 通过项目根目录的 `opencode.json` 配置 MCP servers。

### 配置文件
创建 `opencode.json`（项目根目录）：
```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "ai-progress-monitor": {
      "type": "stdio",
      "command": "<repo_root>/.venv/bin/python",
      "args": ["<repo_root>/server/mcp_server.py"]
    }
  }
}
```

或用 CLI 添加：
```bash
opencode mcp add ai-progress-monitor -- python <repo_root>/server/mcp_server.py
```

## 在会话中使用（MCP 方式）
`opencode` 列表查看可用工具。让 OpenCode 在项目指令里定期上报进度。

---
把 `<repo_root>` 换成你的实际仓库路径。