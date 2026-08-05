# AI 工作台进度监控平台 (ai-progress-monitor)

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

## 功能
- **MCP 上报**：`record_task` / `update_progress` / `log_node` / `list_tasks` 四个工具
- **实时看板**：SSE 秒级刷新，按状态筛选，卡片展示进度条
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

### 3. 接入工作台
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
  app.js          实时逻辑
client-configs/   Codex/Cursor/Claude/OpenCode 接入说明
data/             SQLite 数据库（自动生成）
```

## Roadmap（二期可选）
- 桌面浮动栏
- 手机推送
- 任务聚合统计图