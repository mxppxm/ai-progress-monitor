# AGENTS.md — AI 接入说明

> 人类说「接入进度监控」或给出 `install/*.md` 链接时：**读对应文档并立刻执行**。
>
> - Hooks（推荐）：[`install/hooks.md`](./install/hooks.md)
> - MCP（兜底）：[`install/mcp.md`](./install/mcp.md)

本仓库路径记为 `REPO`（本文件所在目录的绝对路径）。

**优先 Hooks，MCP 仅作兜底。** Cursor / Claude / Codex 用 Hooks；OpenCode 或 hooks 不可用时再走 MCP。

人类侧短话术（复制即可）：

```
请根据 REPO/install/hooks.md，安装 hooks。
请根据 REPO/install/mcp.md，安装 mcp。
```

或：

```
请根据 https://raw.githubusercontent.com/mxppxm/ai-progress-monitor/main/install/hooks.md，安装 hooks。
请根据 https://raw.githubusercontent.com/mxppxm/ai-progress-monitor/main/install/mcp.md，安装 mcp。
```

装完后一句话告诉人类：用的 Hooks 还是 MCP、改了哪些文件。
