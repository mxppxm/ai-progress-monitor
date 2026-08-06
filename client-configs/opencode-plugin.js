const PY = "/Users/mico/clacky_workspace/ai-progress-monitor/.venv/bin/python"
const SCRIPT = "/Users/mico/clacky_workspace/ai-progress-monitor/scripts/hook_report.py"
const LOG = "/Users/mico/Library/Logs/ai-progress-monitor/opencode-plugin.log"

const CHOICE_RE =
  /需要选择|请你选择|请选择|需要你选|需要你决定|你来决定|你来定|请你决定|请你拍板|你来拍板|二选一|待选择|得你定|等你决定|等你的选择|选\s*[aab]|a\s*还是\s*b/i

const CHOICE_HINT =
  "【进度看板】若需要用户拍板/二选一，请在回复里明确写上「需要你选择」或「你来决定」，看板会亮黄灯；停止输出即视为本轮结束，用户继续对话会自动重启任务。"

/** OpenCode / FreeCode 进度上报插件（对齐现行 Plugin Hooks API） */
export const AiProgressReport = async (ctx) => {
  const fs = await import("node:fs/promises")
  const { spawn } = await import("node:child_process")

  const log = async (line) => {
    try {
      await fs.mkdir("/Users/mico/Library/Logs/ai-progress-monitor", { recursive: true })
      await fs.appendFile(LOG, `[${new Date().toISOString()}] ${line}\n`)
    } catch {}
  }

  const run = (args) =>
    new Promise((resolve) => {
      const child = spawn(args[0], args.slice(1), {
        stdio: ["ignore", "pipe", "pipe"],
        env: process.env,
      })
      let stderr = ""
      child.stderr?.on("data", (d) => { stderr += String(d) })
      const timer = setTimeout(() => {
        try { child.kill() } catch {}
        resolve({ code: -1, stderr: "timeout" })
      }, 10_000)
      child.on("error", (e) => {
        clearTimeout(timer)
        resolve({ code: -1, stderr: e?.message || String(e) })
      })
      child.on("close", (code) => {
        clearTimeout(timer)
        resolve({ code: code ?? -1, stderr })
      })
    })

  const report = async (event, sessionID, name, message) => {
    const args = [PY, SCRIPT, "--agent", "opencode", "--event", event]
    if (sessionID) args.push("--task_id", `opencode-${String(sessionID).slice(0, 8)}`)
    if (name) args.push("--name", name)
    if (message) args.push("--message", message)
    const r = await run(args)
    if (r.code !== 0) await log(`report fail event=${event} code=${r.code} ${r.stderr}`.trim())
    else await log(`report ok event=${event} sid=${sessionID || "-"} msg=${message ? Math.min(message.length, 80) : 0}`)
  }

  const textFromParts = (parts) => {
    if (!Array.isArray(parts)) return ""
    return parts
      .filter((p) => p && p.type === "text" && p.text && !p.ignored && !p.synthetic)
      .map((p) => String(p.text))
      .join("\n")
      .trim()
  }

  const seenUserMessages = new Map()
  const idleFired = new Set()
  const lastAssistant = new Map() // sessionID -> 末条助手文案
  const deltaBuf = new Map() // sessionID -> 流式拼接中的正文

  const rememberAssistant = (sessionID, text) => {
    const t = (text || "").trim()
    if (sessionID && t) lastAssistant.set(sessionID, t.slice(0, 2000))
  }

  const assistantOf = (sessionID) =>
    (lastAssistant.get(sessionID) || deltaBuf.get(sessionID) || "").trim()

  /** idle 时兜底：从本机 session API 拉末条助手（delta/text.complete 都丢了时） */
  const pullAssistant = async (sessionID) => {
    const cached = assistantOf(sessionID)
    if (cached) return cached
    const client = ctx?.client?.session
    if (!client?.messages || !sessionID) return ""
    const tries = [
      { path: { id: sessionID }, query: { limit: 30 } },
      { path: { id: sessionID } },
      { id: sessionID, limit: 30 },
      { sessionID, limit: 30 },
    ]
    for (const opts of tries) {
      try {
        const res = await client.messages(opts)
        const raw = res?.data ?? res
        const list = Array.isArray(raw) ? raw : (raw?.messages || raw?.data || [])
        if (!Array.isArray(list) || !list.length) continue
        for (let i = list.length - 1; i >= 0; i--) {
          const item = list[i]
          const info = item?.info || item
          const role = info?.role
          if (role && role !== "assistant") continue
          const text = textFromParts(item?.parts) || textFromParts(info?.parts) || ""
          if (text) {
            rememberAssistant(sessionID, text)
            return text.slice(0, 2000)
          }
        }
      } catch (e) {
        await log(`pullAssistant try fail: ${e?.message || e}`)
      }
    }
    return ""
  }

  const endTurn = async (sessionID) => {
    if (!sessionID || idleFired.has(sessionID)) return
    idleFired.add(sessionID)
    let text = assistantOf(sessionID)
    if (!text) text = await pullAssistant(sessionID)
    // 先 AfterAgentResponse：有拍板用语会立刻黄灯；再 Stop 保持 pending / 否则 done
    if (text) await report("AfterAgentResponse", sessionID, null, text.slice(0, 800))
    await report("Stop", sessionID, null, text.slice(0, 800))
    deltaBuf.delete(sessionID)
  }

  await log("plugin loaded (child_process + delta/pull)")

  return {
    "experimental.chat.system.transform": async (_input, output) => {
      try {
        if (!output) return
        if (typeof output.system === "string") {
          if (!output.system.includes("进度看板")) output.system = `${output.system}\n\n${CHOICE_HINT}`
        } else if (Array.isArray(output.system)) {
          if (!output.system.some((s) => String(s).includes("进度看板"))) output.system.push(CHOICE_HINT)
        }
      } catch {}
    },

    "chat.message": async (input, output) => {
      const msg = output?.message ?? input?.message ?? {}
      if (msg.role && msg.role !== "user") return
      const sessionID = input?.sessionID || msg.sessionID
      const messageID = input?.messageID || msg.id
      const text = textFromParts(output?.parts) || textFromParts(msg.parts) || ""
      if (!text) return
      if (seenUserMessages.get(messageID) === text) return
      seenUserMessages.set(messageID, text)
      if (sessionID) {
        idleFired.delete(sessionID)
        deltaBuf.delete(sessionID)
        lastAssistant.delete(sessionID)
      }
      await report("SessionStart", sessionID, text.slice(0, 100))
    },

    "tool.execute.after": async (input) => {
      const sessionID = input?.sessionID
      if (!sessionID) return
      await report("PostToolUse", sessionID)
    },

    // 文本块结束：权威全文（plugin.trigger 会 await）
    "experimental.text.complete": async (input, output) => {
      const sessionID = input?.sessionID || output?.sessionID
      const text = output?.text || input?.text || ""
      rememberAssistant(sessionID, text)
      if (sessionID) deltaBuf.set(sessionID, text)
      // 正文里已有拍板用语 → 立刻黄灯，不等 idle
      if (sessionID && text && CHOICE_RE.test(text)) {
        await report("AfterAgentResponse", sessionID, null, text.slice(0, 800))
      }
    },

    event: async ({ event }) => {
      if (!event?.type) return
      const props = event.properties ?? event
      const sessionID = props.sessionID || props.part?.sessionID

      // bus 上有 message.part.delta（part.updated 是 sync 事件，插件 event 钩子收不到）
      if (event.type === "message.part.delta") {
        if (props.field === "text" && props.delta && sessionID) {
          const next = (deltaBuf.get(sessionID) || "") + String(props.delta)
          deltaBuf.set(sessionID, next)
          rememberAssistant(sessionID, next)
        }
        return
      }

      if (event.type === "message.updated") {
        const info = props.info || props.message || props
        if (info?.role === "assistant") {
          const text = textFromParts(info.parts) || info.content || ""
          rememberAssistant(sessionID, text)
        }
        return
      }

      if (event.type === "session.status") {
        const st = props.status
        const kind = typeof st === "string" ? st : st?.type
        if (kind === "busy" && sessionID) {
          idleFired.delete(sessionID)
        } else if (kind === "idle" && sessionID) {
          await endTurn(sessionID)
        }
        return
      }

      if (event.type === "session.idle" && sessionID) {
        await endTurn(sessionID)
        return
      }

      if (event.type === "session.deleted" && sessionID) {
        idleFired.delete(sessionID)
        lastAssistant.delete(sessionID)
        deltaBuf.delete(sessionID)
        await report("SessionEnd", sessionID)
      }
    },
  }
}
