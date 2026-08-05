# AI 工作台进度监控平台 (ai-progress-monitor)

> 🙋 **两种接入方式**：想接入新工作台时，优先用「方式一·Hooks」——由工作台运行时**自动**上报，无需 AI 自觉；工作台不支持 hooks 或用不上，再退回「方式二·MCP」。两种方式共用同一套看板与数据库。

统一监控多个 AI 工作台（Claude Code / Codex / Cursor / OpenCode 等）的任务进度。
各工作台通过 **原生 Hooks 或 MCP 协议**上报任务与关键节点，你在一个**网页看板**上实时查看，
关键节点（里程碑/成功/失败）自动弹出 **macOS 系统通知**横幅。

```
Claude Code ─┐
Codex ───────┤─ Hooks (自动触发)  ─┐
Cursor ──────┤─────────────────────┼──►  hook_report.py ─┐
             │                     │                       ├──►  SQLite ──► FastAPI + SSE ──► 网页看板
OpenCode ────┘── MCP (兜底) ───────┴──►  mcp_server.py ────┘           (localhost:8777)
```

---

## 方式一 · Hooks（推荐，自动上报）

Hooks 由工作台**运行时自动触发**，不需要 AI 在每个会话里「自觉」记着上报。
核心是 `scripts/hook_report.py`：它读取工作台传进来的 hook JSON（stdin/参数），
把它翻译成 `record_task` / `update_progress` / `log_node` 落下 SQLite。

| Hook 事件 | 上报动作 |
| :-------- | :------- |
| `SessionStart` | 自动 `record_task`（会话一开始就有任务在跑） |
| `PostToolUse`  | 自动心跳：更新进度/阶段、记一个 `step` 节点 |
| `Stop`         | 自动记一个 `node`，把 Claude 的收尾消息带上看板 |
| `SessionEnd`   | 自动把任务置为 `paused` / `done` |

> 想给某个工作台配 hooks，看 `client-configs/` 里对应的说明文件，
> 把其中的 `<repo_root>` 换成你的实际仓库路径即可。

各工作台 hooks 支持一览：

| 工作台 | 支持 | 说明 |
| :----- | :--- | :--- |
| Claude Code | ✅ | `~/.claude/settings.json` 的 `hooks` 字段，见 `client-configs/claude.md` |
| Codex | ✅ | `~/.codex/config.toml` 的 `hooks` 字段（managed hooks） |
| Cursor | ⚠️ | 支持有限，建议仍用 MCP |
| OpenCode | ⚠️ | 支持有限，建议仍用 MCP |

---

## 方式二 · MCP（兜底）

各工作台通过 **MCP 协议**调用四个工具上报，适合没有成熟 hooks 的工作台：

```
请帮我把 ai-progress-monitor 这个 MCP server 安装/挂载到你当前所在的工作台，
配置完成后确认 record_task / update_progress / log_node / list_tasks 四个工具已加载。

仓库根目录：<repo_root>   （把 <repo_root> 换成你的实际路径）
MCP（stdio）启动方式：
  command = <repo_root>/.venv/bin/python
  args    = ["<repo_root>/server/mcp_server.py"]
  description = "AI 工作台进度监控 — record_task/update_progress/log_node/list_tasks"

请根据你所在的工作台选择对应的配置方式：
- Codex：执行  codex mcp add ai-progress-monitor -- <command> <args...>
- Cursor：往  ~/.cursor/mcp.json 的 mcpServers 里写入 ai-progress-monitor 条目
- Claude Code：执行  claude mcp add ai-progress-monitor --scope user -- <command> <args...>
- OpenCode：往  opencode.json 的 mcp 里写入 ai-progress-monitor 条目
如果该工作台有官方的一键配置机制，也可以改用仓库里的 scripts/setup_agents.py 自动完成。
若配置已存在，不要重复添加；完成后告诉我工具是否已可用。
```

### MCP 上报规则

> 用在支持 MCP 的任意工作台。只要那个工作台已挂载本 MCP（工具：`record_task`、`update_progress`、`log_node`、`list_tasks`），把下面这段整段粘贴给它即可，它会从此**每个会话自动上报**：

```
从现在起，请在每个会话中自动通过 ai-progress-monitor MCP 上报你的任务进度，
无需我每次提醒。规则如下：
1. 会话开始、或接手一个长任务时：调用 record_task
   （task_id=你所属工作台名-短序号，agent=你所属工作台名，name=任务名）
2. 推进到新阶段时：调用 update_progress（stage=coding/testing/deploying 等阶段名）
3. 到达重要节点时：调用 log_node（node_type=step 或 milestone，message=简短中文描述）
4. 任务遇到需要我拍板/选择的决策点（比如"方案 A 还是 B"）时：调用 log_node，
   message 里带上"需要选择 / 请你选 / 你来决定"等字样，
   任务会自动标为「待选择」→ 看板亮黄灯提醒我去选。
5. 任务完成：调用 log_node（node_type=success）；失败：调用 log_node（node_type=failed）
   注：milestone / success / fail 会自动触发系统通知并更新任务状态；
       一旦 success，之前的「待选择」黄灯自动熄灭。
判断标准：不要等我要求才上报，做了实质工作就自动上报。
若 MCP 工具暂时不可用，静默跳过，不要阻塞主任务。
```

---

## 功能
- **自动上报（Hooks）**：`hook_report.py` 把工作台原生 hook 事件翻译成任务/进度/节点
- **MCP 上报（兜底）**：`record_task` / `update_progress` / `log_node` / `list_tasks` 四个工具
- **三态看板**：每张任务卡按**运行中(绿)·待选择(黄灯)·已结束(灰)** 三色显示；
  AI 上报带"需要选择/你来决定"等决策意图的节点时，任务自动亮**黄灯**提醒你去拍板，
  success 后黄灯自然熄灭
- **实时看板**：SSE 秒级刷新（带心跳保活），断线自动切前端兜底轮询，无需手动刷新
- **一键接入（MCP）**：`setup_agents.py` 自动给各工作台配好 MCP
- **开机自启**：LaunchAgent 开机拉起 + 崩溃自愈
- **节点时间线**：点击任务卡片查看其完整执行节点记录
- **系统通知**：`milestone` / `success` / `fail` 节点触发 macOS 横幅通知，`待选择` 另有黄灯提醒

## 快速开始

### 1. 安装依赖（推荐 uv）
```bash
uv venv .venv
uv pip install "mcp[cli]" fastmcp fastapi uvicorn
```
或用 pip：
```bash
python -m venv .venv
source .venv/bin/activate
pip install "mcp[cli]" fastmcp fastapi uvicorn
```

### 2. 启动看板
```bash
cd ai-progress-monitor
.venv/bin/python server/dashboard.py
```
浏览器打开 http://127.0.0.1:8777

### 3. 一键自动配置各工作台 MCP
```bash
.venv/bin/python scripts/setup_agents.py     # 探测并配置所有已安装工作台
.venv/bin/python scripts/setup_agents.py --report   # 只查看安装/配置状态
.venv/bin/python scripts/setup_agents.py --codex --cursor --claude  # 只配指定的工作台
```
自动识别 **codex / cursor / claude / opencode**，逐个写入对应 MCP 配置
（`.codex/mcp.json`、`.cursor/mcp.json`、`claude mcp add`、`opencode.json`），
幂等执行、不重复写入。

### 4. macOS 开机自启（可选）
plist 是模板，先替换占位符再拷贝：
```bash
# 1. 把模板里的 __REPO_ROOT__ ↔ 你的仓库绝对路径、__HOME__ ↔ 你的家目录
sed -e "s|__REPO_ROOT__|$PWD|g" -e "s|__HOME__|$HOME|g" \
    scripts/com.local.ai-progress-monitor.plist.template \
    > ~/Library/LaunchAgents/com.local.ai-progress-monitor.plist

# 2. 加载
launchctl load -w ~/Library/LaunchAgents/com.local.ai-progress-monitor.plist
```
启动即托；`KeepAlive` 让服务崩溃后自动拉起。`scripts/run_dashboard.sh`
负责杀掉旧进程并重启（脚本会自动从自身位置推导仓库根目录，无需改路径）。

### 5. 接入工作台
见 `client-configs/` 下各文件的接入说明，替换其中 `<repo_root>` 为你的实际路径。

## 工作台上报约定（写给 AI 的通用指令，MCP 方式）
让任何接入的 AI 遵守：
> 长任务开始调用 `record_task`（task_id=工作台名-序号, agent=工作台名, name=任务名）
> 阶段切换调用 `update_progress`（stage=coding/testing/deploying）
> 重要节点调用 `log_node`（step/milestone/success/fail，milestone 与 success/fail 会触发系统通知）
> 需要我拍板/选择时调用 `log_node`（message 带"需要选择/你来决定/选 A 或 B"等字样，任务自动亮黄灯进入「待选择」，我处理后 success 即熄灭）

## 目录结构
```
server/
  db.py            SQLite 数据层
  mcp_server.py    MCP stdio 上报服务（兜底）
  dashboard.py     FastAPI 看板后端 + SSE
  notify.py        macOS 系统通知
scripts/
  hook_report.py       把工作台 hook 事件翻译成进度上报（hooks 主入口）
  setup_agents.py       一键自动配置各工作台 MCP
  run_dashboard.sh      看板启动辅助脚本
  com.local.ai-progress-monitor.plist.template   macOS launchd 自启模板（占位符 __REPO_ROOT__/__HOME__）
  sse_live_test.py      SSE 实时推送端到端验证脚本
dashboard/
  index.html      看板页面
  styles.css
  app.js          实时逻辑（SSE + 兜底轮询）
client-configs/   Claude/Codex/Cursor/OpenCode 接入说明（Hooks + MCP）
  claude-hooks.json  Claude Code hooks 配置样例（合并进 ~/.claude/settings.json）
data/             SQLite 数据库（自动生成）
```

## Roadmap（二期可选）
- 桌面浮动栏
- 手机推送
- 任务聚合统计图