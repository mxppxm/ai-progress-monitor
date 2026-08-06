# OpenCode 接入 ai-progress-monitor

OpenCode 没有 `hook` 配置字段，事件挂钩走**插件系统**（启动时加载 `~/.config/opencode/plugins/` 下的 .js/.ts）。

## 方式一：插件（推荐 · 自动上报）

把 `client-configs/opencode-plugin.js` 复制为 `~/.config/opencode/plugins/ai-progress-report.js`：

```bash
mkdir -p ~/.config/opencode/plugins
cp <repo_root>/client-configs/opencode-plugin.js ~/.config/opencode/plugins/ai-progress-report.js
```

插件订阅 opencode 事件并调用 `scripts/hook_report.py --agent opencode`，语义与 hooks 一致：

| opencode 事件 | hook_report 事件 | 看板动作 |
| :--- | :--- | :--- |
| `message.updated`（role=user） | `SessionStart` | 建/重启任务，标题=提示词 |
| `tool.execute.after`（实质工具） | `PostToolUse` | step 心跳 |
| `session.status` = idle | `Stop` | 结束/黄灯 |
| `session.deleted` | `SessionEnd` | 收尾 |

**重启 OpenCode 后生效**；已运行会话不回补历史，下次会话自动上报。

插件内硬编码了仓库绝对路径，换机器/换路径需同步改插件里的 `PY` / `SCRIPT` 常量。

## 方式二：MCP（兜底 · 自觉上报）

OpenCode 通过 `opencode.json` 的 `mcp` 字段配置 MCP servers（已配好则跳过）。

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "ai-progress-monitor": {
      "type": "local",
      "enabled": true,
      "command": [
        "<repo_root>/.venv/bin/python",
        "<repo_root>/server/mcp_server.py"
      ]
    }
  }
}
```

或用 CLI 添加：

```bash
opencode mcp add ai-progress-monitor -- python <repo_root>/server/mcp_server.py
```

MCP 方式依赖项目指令（AGENTS.md）里的自觉上报规则，不保证每个会话必然上报；
**插件方式由运行时自动触发，是 OpenCode 的推荐接入。**
