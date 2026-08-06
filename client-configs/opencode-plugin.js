const PY = "/Users/mico/clacky_workspace/ai-progress-monitor/.venv/bin/python"
const SCRIPT = "/Users/mico/clacky_workspace/ai-progress-monitor/scripts/hook_report.py"

const HEARTBEAT_TOOLS = new Set(["bash", "write", "edit", "task", "delete", "create", "patch"])

export const AiProgressReport = async ({ $ }) => {
  const report = async (event, sessionID, name, message) => {
    const args = [PY, SCRIPT, "--agent", "opencode", "--event", event]
    if (sessionID) args.push("--task_id", `opencode-${String(sessionID).slice(0, 8)}`)
    if (name) args.push("--name", name)
    if (message) args.push("--message", message)
    try {
      await $`${args}`.quiet().nothrow().timeout(10_000)
    } catch {}
  }

  const seenUserMessages = new Map()
  let idleFired = false

  return {
    "message.updated": async ({ sessionID, messageID, info }) => {
      const msg = info?.info ?? info ?? {}
      if (msg.role !== "user") return
      let text = ""
      const content = msg.content
      if (typeof content === "string") {
        text = content.trim()
      } else if (Array.isArray(content)) {
        text = content
          .map((part) => (typeof part === "string" ? part : part?.text || part?.content || ""))
          .join(" ")
          .trim()
      }
      if (!text) return
      if (seenUserMessages.get(messageID) === text) return
      seenUserMessages.set(messageID, text)
      idleFired = false
      await report("SessionStart", sessionID, text.slice(0, 100))
    },
    "tool.execute.after": async (input) => {
      const tool = input?.tool ?? ""
      if (HEARTBEAT_TOOLS.has(tool)) {
        await report("PostToolUse", input?.sessionID)
      }
    },
    "session.status": async (input) => {
      if (input?.status === "idle" && !idleFired) {
        idleFired = true
        await report("Stop", input?.sessionID)
      } else if (input?.status === "busy") {
        idleFired = false
      }
    },
    "session.deleted": async (input) => {
      await report("SessionEnd", input?.sessionID)
    },
  }
}
