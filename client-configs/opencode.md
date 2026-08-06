# OpenCode 接入 ai-progress-monitor

OpenCode 没有 `hook` 配置字段，事件挂钩走**插件系统**（启动时加载 `~/.config/opencode/plugins/` 下的 .js/.ts）。

## 方式一：插件（推荐 · 自动上报）

把 `client-configs/opencode-plugin.js` 写入插件目录，并把模板里的 `<repo_root>` 换成真实绝对路径：

```bash
REPO="<repo_root>"   # 换成仓库绝对路径
mkdir -p ~/.config/opencode/plugins
sed "s|<repo_root>|$REPO|g" "$REPO/client-configs/opencode-plugin.js" \
  > ~/.config/opencode/plugins/ai-progress-report.js
```

插件订阅 opencode 事件并调用 `scripts/hook_report.py --agent opencode`，语义与 hooks 一致：

| 插件钩子 | hook_report 事件 | 看板动作 |
| :--- | :--- | :--- |
| `chat.message`（用户提示词） | `SessionStart` | 建/重启任务，标题=提示词 |
| `tool.execute.after` | `PostToolUse` | step 心跳 |
| `experimental.text.complete` / `message.part.delta` | 缓存助手正文 | 供拍板用语检测 |
| 正文含「需要你选择」等 | `AfterAgentResponse` | 立即黄灯 |
| `event` → `session.status` idle / `session.idle` | `Stop`（带末条正文） | 结束；有拍板用语则保持黄灯 |
| `event` → `session.deleted` | `SessionEnd` | 收尾 |

> 注意：`message.updated` / `session.*` 属于 **Event**，必须挂在统一的 `event` 钩子上；
> 旧版把它们写成顶层 Hooks key 会被静默忽略（FreeCode 报不上来的常见原因）。

**重启 OpenCode / FreeCode 后生效**；已运行会话不回补历史，下次会话自动上报。

排障：看 `~/Library/Logs/ai-progress-monitor/opencode-plugin.log`（插件加载与每次上报会写一行）。

模板用 `<repo_root>` 占位；安装时必须替换成绝对路径。换机器/换路径后重新跑上面的 `sed`。

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
