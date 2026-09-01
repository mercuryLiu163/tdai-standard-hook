import { Plugin } from "@opencode-ai/plugin/v2"
import { spawn } from "node:child_process"
import { fileURLToPath } from "node:url"
import path from "node:path"

type HookOutput = {
  hookSpecificOutput?: { additionalContext?: string }
  additionalContext?: string
  additional_context?: string
}

const root = path.dirname(fileURLToPath(import.meta.url))
const script = path.resolve(root, "..", "tdai-hook.py")

function runCore(event: Record<string, unknown>): Promise<HookOutput> {
  const configured = process.env.TDAI_PYTHON
  const command = configured || (process.platform === "win32" ? "py" : "python3")
  const args = configured ? [script] : process.platform === "win32" ? ["-3", script] : [script]
  return new Promise((resolve) => {
    const child = spawn(command, args, { stdio: ["pipe", "pipe", "ignore"] })
    let stdout = ""
    const timer = setTimeout(() => {
      child.kill()
      resolve({})
    }, Number(process.env.TDAI_OPENCODE_TIMEOUT_MS || 8000))
    child.stdout.on("data", (chunk) => { stdout += chunk.toString() })
    child.on("error", () => { clearTimeout(timer); resolve({}) })
    child.on("close", () => {
      clearTimeout(timer)
      try { resolve(JSON.parse(stdout) as HookOutput) } catch { resolve({}) }
    })
    child.stdin.end(JSON.stringify(event))
  })
}

function contextOf(output: HookOutput): string {
  return output.hookSpecificOutput?.additionalContext || output.additionalContext || output.additional_context || ""
}

export default Plugin.define({
  id: "tdai.memory",
  async setup(ctx) {
    await ctx.session.hook("prompt", async (event) => {
      const output = await runCore({
        hook_event_name: "UserPromptSubmit",
        session_id: event.sessionID,
        prompt: event.prompt.text,
        client: "opencode",
      })
      const context = contextOf(output)
      if (context) event.prompt.text = `${event.prompt.text}\n\n${context}`
    })
  },
})
