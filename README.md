# AI 工作台进度监控平台 (ai-progress-monitor)

> 🙋 **拷贝话术**：想接入新工作台时，把下方「话术」直接粘贴给那个 AI 即可；想接入的 AI 是 Codex/Claude/Clacky，可改用「自动配置」。详见文末「一键接入」。

统一监控多个 AI 工作台（Codex / Cursor / Claude Code / OpenCode 等）的任务进度。
各工作台通过 **MCP 协议**上报任务与关键节点，你在一个**网页看板**上实时查看，
关键节点（里程碑/成功/失败）自动弹出 **macOS 系统通知**横幅。

```
Codex ──┐
Cursor ─┤─ MCP (record_task / update_progress / log_node)
Claude ─┼──────────────────────────►  mcp_server.py  ─►  SQLite
OpenCode┘                                                  │
                                                      ┌─────▼─────┐
                                                   FastAPI + SSE │
                                                      ┌──────────┴────────┐
                                                      │  网页看板          │
                                                      │  localhost:8777   │
                                                      └───────────────────┘
```

## 🪄 直接粘贴的话术

> 用在**任意 AI 工作台**（Codex / Cursor / Claude / OpenCode / Clacky …）。只要那个工作台已挂载本 MCP（工具：`record_task`、`update_progress`、`log_node`、`list_tasks`），把下面这段整段粘贴给它即可，它会从此**每个会话自动上报**：

```
从现在起，请在每个会话中自动通过 ai-progress-monitor MCP 上报你的任务进度，
无需我每次提醒。规则如下：
1. 会话开始、或接手一个长任务时：调用 record_task
   （task_id=你所属工作台名-短序号，agent=你所属工作台名，name=任务名，stage=starting）
2. 推进到新阶段或进度变化时：调用 update_progress（progress=0-100，stage=coding/testing/deploying 等）
3. 到达重要节点时：调用 log_node（node_type=step 或 milestone，message=简短中文描述）
4. 任务完成：调用 log_node（node_type=success）；失败：调用 log_node（node_type=failed）
   注：milestone / success / fail 会自动触发系统通知并更新任务状态。
判断标准：不要等我要求才上报，做了实质工作就自动上报。
若 MCP 工具暂时不可用，静默跳过，不要阻塞主任务。
```

---

## 功能
- **MCP 上报**：`record_task` / `update_progress` / `log_node` / `list_tasks` 四个工具
- **实时看板**：SSE 秒级刷新（带心跳保活），断线自动切前端兜底轮询，无需手动刷新
- **一键接入**：`setup_agents.py` 自动给各工作台配好 MCP
- **开机自启**：LaunchAgent 开机拉起 + 崩溃自愈
- **节点时间线**：点击任务卡片查看其完整执行节点记录
- **系统通知**：`milestone` / `success` / `fail` 节点触发 macOS 横幅通知

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
```bash
cp scripts/com.mxppxm.ai-progress-monitor.plist ~/Library/LaunchAgents/
launchctl load -w ~/Library/LaunchAgents/com.mxppxm.ai-progress-monitor.plist
```
启动即托；`KeepAlive` 让服务崩溃后自动拉起。`scripts/run_dashboard.sh`
负责杀掉旧进程并重启。

### 5. 接入工作台
见 `client-configs/` 下各文件的截图式配置，替换其中 `/path/to/ai-progress-monitor` 为你的实际路径。

## 工作台上报约定（写给 AI 的通用指令）
让任何接入的 AI 遵守：
> 长任务开始调用 `record_task`（task_id=工作台名-序号, agent=工作台名, name=任务名）
> 阶段切换调用 `update_progress`（progress=0-100, stage=coding/testing/deploying）
> 重要节点调用 `log_node`（step/milestone/success/fail，milestone 与 success/fail 会触发系统通知）

## 目录结构
```
server/
  db.py            SQLite 数据层
  mcp_server.py    MCP stdio 上报服务
  dashboard.py     FastAPI 看板后端 + SSE
  notify.py        macOS 系统通知
dashboard/
  index.html      看板页面
  styles.css
  app.js          实时逻辑（SSE + 兜底轮询）
client-configs/   Codex/Cursor/Claude/OpenCode 接入说明
scripts/
  setup_agents.py           一键自动配置各工作台 MCP
  run_dashboard.sh          看板启动辅助脚本
  com.mxppxm...plist        macOS launchd 自启配置模板
  sse_live_test.py          SSE 实时推送端到端验证脚本
data/             SQLite 数据库（自动生成）
```

## Roadmap（二期可选）
- 桌面浮动栏
- 手机推送
- 任务聚合统计图