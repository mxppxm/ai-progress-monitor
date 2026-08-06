# 安装 ai-progress-monitor Hooks

> Agent：读完本文档后**立刻执行**，不要只给说明。已存在且正确的配置跳过，勿重复堆叠。

## 概述

用工作台原生 Hooks 自动上报进度到看板（http://127.0.0.1:8777）。**优先 Hooks，不要再装 MCP 自觉上报规则。**

## 一、解析仓库路径 REPO

按顺序取第一个可用的：

1. 当前 workspace / cwd 已是本仓库（存在 `scripts/hook_report.py`）→ 用其绝对路径
2. 用户消息里写了路径 → 用该路径
3. 默认常见路径：`~/clacky_workspace/ai-progress-monitor`（若存在）
4. 仍找不到 → 询问用户 REPO 绝对路径，**不要猜测乱写**

## 二、确认依赖

```bash
cd "$REPO"
# 若无 .venv：
python3 -m venv .venv
.venv/bin/pip install "mcp[cli]" fastmcp fastapi uvicorn
```

Hook 解释器一律用：`$REPO/.venv/bin/python`（不存在则先建 venv）。

看板（可选，人类查看用）：

```bash
$REPO/.venv/bin/python $REPO/server/dashboard.py   # → http://127.0.0.1:8777
```

## 三、按当前工作台写入 Hooks

识别你所在工作台，只配当前这一个。模板在 `$REPO/client-configs/`，把其中 `<repo_root>` 全部换成 `$REPO` 绝对路径。

### Cursor

1. 合并 `$REPO/client-configs/cursor-hooks.json` → `~/.cursor/hooks.json`
2. `chmod +x $REPO/client-configs/cursor-hook.sh`
3. 若本机曾用 MCP：从 `~/.cursor/mcp.json` 去掉 `ai-progress-monitor`；删除要求自觉调 `record_task` 的 Cursor rule（如 `~/.cursor/rules/ai-progress-monitor.mdc`）
4. 提醒用户：Settings → Hooks 确认已加载；必要时重启 Cursor

事件：`sessionStart` / `beforeSubmitPrompt` / `postToolUse` / `afterAgentResponse` / `stop` / `sessionEnd`

### Claude Code

合并 `$REPO/client-configs/claude-hooks.json` → `~/.claude/settings.json`（或项目 `.claude/settings.json`）。

事件：`SessionStart` / `PostToolUse` / `Stop` / `SessionEnd`

### Codex

1. 以 `$REPO/client-configs/codex-hooks.json` 为模板写入 `~/.codex/hooks.json`（已有其它 hooks 则合并，保留其它条目）
2. `~/.codex/config.toml` 确保：

```toml
[features]
hooks = true
```

3. 提醒用户：在 Codex 执行 `/hooks` 信任新 hooks；必要时重启

事件：`SessionStart` / `UserPromptSubmit` / `PostToolUse` / `Stop` / `SessionEnd`

### OpenCode

OpenCode 无 `hook` 配置字段，事件挂钩走 **插件系统**：把 `$REPO/client-configs/opencode-plugin.js`
复制为 `~/.config/opencode/plugins/ai-progress-report.js`（插件内部调用 `hook_report.py --agent opencode`）。

```bash
mkdir -p ~/.config/opencode/plugins
cp "$REPO/client-configs/opencode-plugin.js" ~/.config/opencode/plugins/ai-progress-report.js
```

生效：**重启 OpenCode**（插件在启动时加载）。已运行的旧会话不回补历史，下次会话自动上报。

事件映射：`chat.message` → SessionStart（建/重启+改标题）；`event:session.status(idle)` → Stop；
`tool.execute.after` → PostToolUse 心跳；`event:session.deleted` → SessionEnd。
排障日志：`~/Library/Logs/ai-progress-monitor/opencode-plugin.log`。

### Clacky

Clacky **无原生会话生命周期 hooks**。推荐用**会话文件监听**自动上报（不依赖模型自觉调 MCP）：

```bash
# 已提供 LaunchAgent（本机）：com.mxppxm.ai-progress-clacky-watch
# 或手动：
bash "$REPO/scripts/run_clacky_watch.sh"
```

监听 `~/.clacky/sessions/*.json` → 调用 `hook_report.py --agent clacky`：
新 user 消息 → SessionStart；tool / 工具调用 → PostToolUse；assistant 收尾静默约 5s → Stop。

排障日志：`~/Library/Logs/ai-progress-monitor/clacky-watch.log`。

MCP（`~/.clacky/mcp.json`）与长期记忆清单仍可作兜底，但有 watcher 后不必再依赖自觉上报。

模板契约：`$REPO/client-configs/clacky-hooks.json`。

## 四、语义（写入后自动生效，无需再写规则）

| 时机 | 看板 |
| :--- | :--- |
| 用户提交提示词 | 建/重启为「运行中」，**标题＝本轮提示词** |
| 停止输出 | 「已结束」；回复含「需要你选择 / 你来决定」→「待选择」黄灯 |
| 再发消息 | 同一任务重启，标题换成新提示词 |
| 新建空会话 | 不建任务（只注入拍板用语提示） |

核心命令：`$REPO/.venv/bin/python $REPO/scripts/hook_report.py --agent <工作台名>`

## 五、完成回执

一句话告诉用户：改了哪些文件、是否需要重启 / `/hooks` 信任。不要再安装 MCP 上报规则。
