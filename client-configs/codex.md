# Codex 接入 ai-progress-monitor

两种方式，**优先用 Hooks**（自动触发），MCP 作兜底。

## 方式一：Hooks（推荐）

1. 确认本仓库 `.venv` 可用（看板依赖同一套 Python）。
2. 把 `client-configs/codex-hooks.json` 写成用户级 `~/.codex/hooks.json`
   （或项目级 `.codex/hooks.json`），并把其中的 `<repo_root>` 换成真实绝对路径。
3. 在 `~/.codex/config.toml` 确保 hooks 开启：

```toml
[features]
hooks = true
```

4. 在 Codex 里执行 `/hooks`，如提示未信任则 trust 本仓库相关 hooks。
5. 必要时重启 Codex。

| Codex 事件 | 上报动作 |
| :--------- | :------- |
| `SessionStart` | 注入黄灯用语提示（不建任务） |
| `UserPromptSubmit` | 建/重启任务为 running，**标题＝本轮提示词** |
| `PostToolUse` | 心跳 `step`（不改标题） |
| `Stop` | 停止输出 → `success`；末条含「需要你选择 / 你来决定」→ 黄灯 pending |
| `SessionEnd` | 仍 running 则结束；已结束/待选择不变 |

核心命令：`<repo_root>/.venv/bin/python <repo_root>/scripts/hook_report.py --agent codex`

也可直接把 README 里「Codex 一键接入」整段 prompt 粘贴给 Codex，让它自动写好上述文件。

## 方式二：MCP（兜底）

```bash
codex mcp add ai-progress-monitor -- <repo_root>/.venv/bin/python <repo_root>/server/mcp_server.py
```

或编辑 `~/.codex/mcp.json`：

```json
{
  "mcpServers": {
    "ai-progress-monitor": {
      "command": "<repo_root>/.venv/bin/python",
      "args": ["<repo_root>/server/mcp_server.py"],
      "type": "stdio"
    }
  }
}
```

MCP 方式需另写长期规则，让模型自觉调用 `record_task` / `update_progress` / `log_node`（见 README「方式二」）。

---
把 `<repo_root>` 换成你的实际仓库路径。
