# Claude Code 接入 ai-progress-monitor

两种方式，**推荐用 Hooks**（自动触发、无需 AI 自觉），MCP 作兜底。

## 方式一：Hooks（推荐）

Claude Code 原生支持生命周期 hooks，把这些事件自动上报到看板：

| 事件 | 上报动作 |
| :--- | :------- |
| `SessionStart` | 自动 `record_task` / 继续对话时重启为 running |
| `PostToolUse`  | Bash/Write/Edit 每次成功后自动心跳 `step` |
| `Stop` | 停止输出 → `success`（已结束）；末条含拍板用语 → 黄灯 pending |
| `SessionEnd` | 仍 running 则结束；已结束/待选择不变 |

### 配置

把 `client-configs/claude-hooks.json` 里的 `hooks` 合并进 `~/.claude/settings.json`
（全局）或 `.claude/settings.json`（项目级，可入库），并把 `<repo_root>` 换成实际仓库路径。

```bash
# 全局生效
jq '.hooks = (input.hooks)' \
   ~/.claude/settings.json \
   <(sed "s|<repo_root>|$PWD|g" client-configs/claude-hooks.json) \
   > ~/.claude/settings.json.tmp && mv ~/.claude/settings.json.tmp ~/.claude/settings.json
```

或手动把 hooks 段粘贴进 `~/.claude/settings.json`。生效后重启 Claude Code 即可，
无需给它任何「记得上报」的提示——hooks 是运行时自动触发的。

> 原理：hook 命令 `python <repo_root>/scripts/hook_report.py --agent claude`
> 会自动读 stdin 里的 hook JSON（`hook_event_name`/`session_id`/`cwd`…），
> 生成稳定的 task_id 并写入同一个 SQLite 看板。

也可复制 README 短话术：

```
请根据 <repo>/install/hooks.md，安装 hooks。
```

## 方式二：MCP（兜底）

Claude Code 通过 `claude mcp add` 命令注册 stdio MCP server。

```bash
# 用户级（全局生效）
claude mcp add ai-progress-monitor --scope user -- <repo_root>/.venv/bin/python <repo_root>/server/mcp_server.py
```

确认：
```bash
claude mcp list
```

之后 Claude 需在会话里主动上报（它会识别 MCP 工具）。建议把上报约定写进 `~/.claude/CLAUDE.md`。

---
把 `<repo_root>` 换成你的实际仓库路径。