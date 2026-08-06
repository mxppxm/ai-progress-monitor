# AI 工作台进度监控

本机多 AI 工作台（Cursor / Claude Code / Codex / OpenCode…）的统一进度看板：会话开始、工具调用、停输出、需要你拍板，都会反映到网页卡片上；关键节点可弹 macOS 通知。

看板地址：[http://127.0.0.1:8777](http://127.0.0.1:8777)

**别人能不能用？** 能——前提是 **macOS + 本机跑这些工作台**。核心链路（看板 + Hooks 上报）已可 clone 即用；通知点击聚焦、开机自启、Clacky 监听等偏本机集成。更细的判断见文末「适用与局限」。

---

## 环境要求

| 项 | 说明 |
| :--- | :--- |
| 系统 | **macOS**（通知 / `open -a` 聚焦 / LaunchAgent 日志路径均按 macOS 写） |
| Python | 3.10+（建议用仓库内 `.venv`） |
| 工作台 | 至少装一个：Cursor / Claude Code / Codex / OpenCode（或 Clacky） |

Linux / Windows：看板服务本身可起，但通知与「点卡片跳回 App」目前不可用。

---

## 快速开始（人类）

```bash
git clone https://github.com/mxppxm/ai-progress-monitor.git
cd ai-progress-monitor

python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
# 或: uv venv .venv && uv pip install -r requirements.txt

.venv/bin/python server/dashboard.py   # → http://127.0.0.1:8777
```

开机自启（可选）：复制 `scripts/com.local.ai-progress-monitor.plist.template`，把 `__REPO_ROOT__` / `__HOME__` 换成真实路径，放到 `~/Library/LaunchAgents/` 后 `launchctl load -w`。也可直接跑 `scripts/run_dashboard.sh`。

---

## 接入工作台（复制发给 AI）

把仓库 clone 到本机后，在对应工作台里发下面一句话（把 `<repo>` 换成**绝对路径**）。Agent 会读 `install/*.md` 并改配置。

### Hooks（推荐 · Cursor / Claude / Codex / OpenCode）

```
请根据 <repo>/install/hooks.md，安装 hooks。
```

未打开本仓库时，也可用 GitHub raw：

```
请根据 https://raw.githubusercontent.com/mxppxm/ai-progress-monitor/main/install/hooks.md，安装 hooks。
```

### MCP（兜底 · Hooks 不可用或你明确要求时）

```
请根据 <repo>/install/mcp.md，安装 mcp。
```

```
请根据 https://raw.githubusercontent.com/mxppxm/ai-progress-monitor/main/install/mcp.md，安装 mcp。
```

细节：[`install/hooks.md`](./install/hooks.md) · [`install/mcp.md`](./install/mcp.md) · 本地总览 [`AGENTS.md`](./AGENTS.md)

### 各工作台怎么接

| 工作台 | 推荐方式 | 配置位置（摘要） |
| :--- | :--- | :--- |
| Cursor | Hooks | `~/.cursor/hooks.json` + `cursor-hook.sh` |
| Claude Code | Hooks | `~/.claude/settings.json`（或项目 `.claude/`） |
| Codex | Hooks | `~/.codex/hooks.json`，并开启 `features.hooks` |
| OpenCode | 插件 | `~/.config/opencode/plugins/ai-progress-report.js`（`<repo_root>` 需替换） |
| Clacky | 会话监听 | `scripts/run_clacky_watch.sh`（可选） |

模板都在 `client-configs/`，占位符一律是 `<repo_root>`，安装时换成绝对路径。

---

## 看板语义（三态）

| 时机 | 看板 |
| :--- | :--- |
| 用户提交提示词 | 建/重启为「运行中」，**标题＝本轮提示词** |
| 停止输出 | 「已结束」；回复含「需要你选择 / 你来决定」→「待选择」黄灯 |
| 再发消息 | 同一任务重启，标题换成新提示词 |
| 新建空会话 | 不建任务（只注入拍板用语提示） |

---

## 能力摘要

| 能力 | 说明 |
| :--- | :--- |
| Hooks / 插件自动上报 | `scripts/hook_report.py`，无需模型自觉调工具 |
| MCP 上报 | `record_task` / `update_progress` / `log_node` / `list_tasks` |
| 实时看板 | SSE + 断线轮询；点卡片可聚焦对应 App（macOS） |
| 系统通知 | 里程碑 / 成功 / 失败 → macOS 横幅（terminal-notifier） |

---

## 目录

```
install/           AI 安装入口（hooks.md / mcp.md）
AGENTS.md          本地总览（与 install 对齐）
server/            db · mcp_server · dashboard · notify · focus
scripts/           hook_report · setup_agents · 自启 / Clacky watch
dashboard/         看板前端
client-configs/    各工作台 hooks / 插件模板（含 <repo_root>）
data/              SQLite 等（运行时生成，已 gitignore）
```

---

## 适用与局限

**适合分享给：** 同在 macOS 上同时开多个 AI Coding 工作台、想一眼看谁在跑、谁卡在等你拍板的人。clone → 起看板 → 让 Agent 按 `install/hooks.md` 装一遍，通常就能用。

**目前还不像「成品开源产品」的地方：**

1. **绑定 macOS** — 通知与 App 聚焦依赖 `osascript` / `open -a` / `~/Library/Logs`
2. **本机单用户** — 看板只听 `127.0.0.1`，没有账号、多机、远程
3. **无 LICENSE** — 仓库暂未声明开源协议，转载/商用前请先跟作者确认
4. **Clacky 是可选私货** — 会话 API / watcher 对多数人无关，可忽略
5. **安装偏「让 AI 执行文档」** — 人类最短路径是起看板；接工作台仍建议用上面的接入话术，而不是手改 JSON

排障：看板进程是否在跑、hooks 是否已信任/重启、OpenCode 插件里 `<repo_root>` 是否已替换、日志目录 `~/Library/Logs/ai-progress-monitor/`。
