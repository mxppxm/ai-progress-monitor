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
| `sessionStart` | 注入黄灯用语提示（不建任务） |
| `beforeSubmitPrompt` | 用户点发送 → `record_task` / 重启为 running，标题改为本轮提示词 |
| `postToolUse`（Shell/Write/…） | 仅给**已有** running 任务打心跳；不新建卡（避免 Task 子代理孤儿任务） |
| `afterAgentResponse` | 末条含「需要你选择 / 你来决定」等 → 黄灯 pending |
| `stop` / `subagentStop` | 停止输出 → `success`（已结束）；已黄灯则保持 pending |
| `sessionEnd` | 仍 running 则结束；已结束/待选择不变 |

核心命令：`<repo_root>/scripts/hook_report.py --agent cursor`（由 `cursor-hook.sh` 包装）。

也可复制 README 短话术：

```
请根据 <repo>/install/hooks.md，安装 hooks。
```

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
