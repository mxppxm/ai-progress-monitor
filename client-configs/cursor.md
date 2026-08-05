# Cursor 接入 ai-progress-monitor

**推荐用 Hooks**（运行时自动上报，无需 AI 自觉调 MCP）。

## 方式一：Hooks（推荐）

1. 确保本仓库依赖已装（`.venv`），看板可跑。
2. 把 `client-configs/cursor-hooks.json` 合并进 **用户级** `~/.cursor/hooks.json`
   （或项目级 `.cursor/hooks.json`），并把其中的 `<repo_root>` 换成真实路径。
3. 保证 `client-configs/cursor-hook.sh` 可执行：
   ```bash
   chmod +x <repo_root>/client-configs/cursor-hook.sh
   ```
4. 在 Cursor **Settings → Hooks** 确认已加载；必要时重启 Cursor。

| Cursor 事件 | 上报动作 |
| :---------- | :------- |
| `sessionStart` | `record_task` |
| `postToolUse`（Shell/Write/…） | 心跳 `step` |
| `stop` | `milestone` |
| `sessionEnd` | 任务置为 `paused` |

核心命令：`<repo_root>/scripts/hook_report.py --agent cursor`（由 `cursor-hook.sh` 包装）。

## 方式二：MCP（兜底）

不适合 hooks 时再用。写入 `~/.cursor/mcp.json`：

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

或跑：`<repo_root>/.venv/bin/python <repo_root>/scripts/setup_agents.py --cursor`

MCP 方式还需把上报规则写进 Cursor rules（见 README / AGENTS.md）。Hooks 方式**不需要** rules。

---
把 `<repo_root>` 换成你的实际仓库路径。
