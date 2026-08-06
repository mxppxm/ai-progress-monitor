const PY = "/Users/mico/clacky_workspace/ai-progress-monitor/.venv/bin/python"
const SCRIPT = "/Users/mico/clacky_workspace/ai-progress-monitor/scripts/hook_report.py"
const LOG = "/Users/mico/Library/Logs/ai-progress-monitor/opencode-plugin.log"

/** OpenCode / FreeCode 进度上报插件（对齐现行 Plugin Hooks API） */
export const AiProgressReport = async () => {
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
    else await log(`report ok event=${event} sid=${sessionID || "-"}`)
  }

  const textFromParts = (parts) => {
    if (!Array.isArray(parts)) return ""
    return parts
      .filter((p) => p && p.type === "text" && p.text && !p.ignored)
      .map((p) => String(p.text))
      .join(" ")
      .trim()
  }

  const seenUserMessages = new Map()
  const idleFired = new Set()
  const lastAssistant = new Map() // sessionID -> 末条助手文案

  const rememberAssistant = (sessionID, text) => {
    const t = (text || "").trim()
    if (sessionID && t) lastAssistant.set(sessionID, t.slice(0, 800))
  }

  await log("plugin loaded (child_process)")

  return {
    "chat.message": async (input, output) => {
      const msg = output?.message ?? input?.message ?? {}
      if (msg.role && msg.role !== "user") return
      const sessionID = input?.sessionID || msg.sessionID
      const messageID = input?.messageID || msg.id
      const text = textFromParts(output?.parts) || textFromParts(msg.parts) || ""
      if (!text) return
      if (seenUserMessages.get(messageID) === text) return
      seenUserMessages.set(messageID, text)
      if (sessionID) idleFired.delete(sessionID)
      await report("SessionStart", sessionID, text.slice(0, 100))
    },

    "tool.execute.after": async (input) => {
      const sessionID = input?.sessionID
      if (!sessionID) return
      await report("PostToolUse", sessionID)
    },

    // 部分版本在文本流结束时给完整助手回复
    "experimental.text.complete": async (input, output) => {
      const sessionID = input?.sessionID || output?.sessionID
      const text = output?.text || input?.text || ""
      rememberAssistant(sessionID, text)
    },

    event: async ({ event }) => {
      if (!event?.type) return
      const props = event.properties ?? event
      const sessionID = props.sessionID

      // 缓存助手正文，供 Stop 带回看板 detail
      if (event.type === "message.part.updated") {
        const part = props.part || props
        const role = props.role || props.message?.role || props.info?.role
        if (part?.type === "text" && part.text && role !== "user") {
          rememberAssistant(sessionID, part.text)
        }
        return
      }
      if (event.type === "message.updated") {
        const info = props.info || props.message || {}
        if (info.role === "assistant") {
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
        } else if (kind === "idle" && sessionID && !idleFired.has(sessionID)) {
          idleFired.add(sessionID)
          await report("Stop", sessionID, null, lastAssistant.get(sessionID) || "")
        }
        return
      }

      if (event.type === "session.idle" && sessionID && !idleFired.has(sessionID)) {
        idleFired.add(sessionID)
        await report("Stop", sessionID, null, lastAssistant.get(sessionID) || "")
        return
      }

      if (event.type === "session.deleted" && sessionID) {
        idleFired.delete(sessionID)
        lastAssistant.delete(sessionID)
        await report("SessionEnd", sessionID)
      }
    },
  }
}
