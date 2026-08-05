# Codex 接入 ai-progress-monitor

两种方式，**优先用 Hooks**（自动触发），MCP 作兜底。

## 方式一：Hooks（推荐）

Codex CLI 支持生命周期 hooks。核心命令仍是
`python <repo_root>/scripts/hook_report.py --agent codex`，
它会把 session 上下文翻译成 `record_task`/`update_progress`/`log_node`。
把你的 hooks 挂到 `~/.codex/config.toml` 或项目 `config.toml`：

```toml
# ~/.codex/config.toml 或 <project-root>/config.toml
[hooks]
# 会话开始时自动 record_task
# 会话结束时自动把任务置为 paused
# （event 名 / 字段以你当前版本的 Codex hooks 文档为准）
# "startup"      = "python <repo_root>/scripts/hook_report.py --agent codex --event SessionStart"
# "session_end"  = "python <repo_root>/scripts/hook_report.py --agent codex --event SessionEnd"
```

把 `<repo_root>` 换成你的实际仓库路径。
> 说明：Codex 的 hooks 事件名与 managed hooks 机制会随版本演进，配置前请对照
> 你当前版本 Codex 的 hooks 文档核对事件名。`hook_report.py` 对事件是幂等的，
> 拿不准时先手动跑一次 `--report` 之类验证。

## 方式二：MCP（兜底）

Codex 通过 stdio MCP server 接入。先确认 Python + mcp 包就绪：

```bash
pip install "mcp[cli]" fastmcp 2>/dev/null
```

### 命令注册（推荐）
```bash
codex mcp add ai-progress-monitor -- <repo_root>/.venv/bin/python <repo_root>/server/mcp_server.py
```

### 配置文件
编辑 `~/.codex/mcp.json`：
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

### 在 Codex 会话中使用（MCP 方式）
对话里让 Codex 上报进度，例如：

> 任务开始：调用 `record_task` task_id=codex-001 agent=codex name="重构登录模块"
> 写代码中：`update_progress` stage=coding
> 需拍板：`log_node` node_type=step message="登录方案 A 还是 B，需要你选择"（自动亮黄灯）
> 完成：`log_node` node_type=milestone message="登录重构完成，测试通过"

---
把 `<repo_root>` 换成你的实际仓库路径。