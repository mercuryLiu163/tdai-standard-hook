# 适配器与统一协议

本目录只定义适配边界，不把任何厂商的配置路径写死到 Memory 核心中。
每个 Agent 应根据自己的原生 Hook 协议生成一个很薄的适配器；适配器负责
“原生事件 → 标准 JSON → 标准核心 → 原生响应”，核心只负责记忆、Task、隔离、
日志和 fail-open。

## 统一 JSON Hook 协议

所有 stdin 适配器都向 `tdai-hook.py` 发送一个 JSON 对象，每次一行或一整个
JSON 文档均可。字段采用 Claude Code/ZCode 兼容的 camelCase 与 snake_case
别名：

```json
{
  "hook_event_name": "UserPromptSubmit",
  "session_id": "session-123",
  "prompt": "用户原始提示",
  "last_assistant_message": "上一轮助手回复",
  "cwd": "C:\\work\\repo",
  "client": "zcode"
}
```

事件只使用三个稳定生命周期：`SessionStart`、`UserPromptSubmit`、`Stop`。
Hook 成功时返回：

```json
{
  "hookSpecificOutput": {
    "hookEventName": "UserPromptSubmit",
    "additionalContext": "<tdai-binding>...</tdai-binding>"
  }
}
```

空 stdout、退出码 0 都表示“无额外上下文”；任何异常都 fail-open，不阻塞宿主。
需要兼容只识别顶层字段的旧宿主时设置 `TDAI_OUTPUT_MODE=all`。

## 标准核心调用

如果 Agent 原生支持 JSON stdin/stdout command hook，按平台调用：

```text
# Windows
py -3 %USERPROFILE%\\.tdai-hook\\tdai-hook.py

# Ubuntu/macOS
python3 $HOME/.tdai-hook/tdai-hook.py
```

调用前设置 `TDAI_CONFIG`（或使用平台默认的 Windows
`%USERPROFILE%\\.tdai\\config.json`、Ubuntu/macOS `$HOME/.tdai/config.json`），
并可设置 `TDAI_PROFILE=codex|claude-code|zcode|grok|agy|deepseek|harness`。
适配器至少要完成以下字段映射：`event`、`session_id`、`prompt`、
`last_assistant_message`、`cwd`、`client`。标准输出中的
`hookSpecificOutput.additionalContext`（或顶层 `additionalContext`）是要注入
回模型的上下文。

如果 Agent 的事件名或输出协议不同（例如 agy 的 `PreInvocation`/`Stop`、
OpenCode 的进程内插件），Agent 自己生成原生适配器；本仓库不把该适配器当作
核心实现。适配器可以读取宿主的 transcript，再组装标准事件，但不能把厂商
配置、模型地址或密钥写进核心。

## 适配器伪代码

```text
native_event = read_native_event()
standard_event = {
  "hook_event_name": map_event(native_event),
  "session_id": map_session(native_event),
  "prompt": map_prompt_or_transcript(native_event),
  "last_assistant_message": map_reply_or_transcript(native_event),
  "cwd": map_cwd(native_event),
  "client": "<agent-name>"
}
core_output = run("tdai-hook.py", standard_event)
return map_core_output_to_native(core_output)
```

ZCode 的 `hooks/hooks.json` 可直接使用该命令；Claude Code 与 Codex 的
`UserPromptSubmit`/`Stop` 也使用同样的 JSON 输出。不要把 Memory endpoint
改成模型 endpoint，Hook 是旁路调用。

## OpenCode

OpenCode 是进程内 TypeScript 插件，不是 stdin command hook。仓库中的
`opencode-plugin.ts` 仅作为适配器参考样例；正式使用时由 OpenCode 自己或其
安装流程按本协议生成插件。插件只负责调用标准核心并把 additionalContext
追加到 prompt，不能复制记忆业务逻辑。

## 宿主身份与隔离

身份来自配置或 profile，不信任用户 prompt 覆盖。每条 Memory API 请求都带
`team_id`、`agent_id`、`user_id`，Task 绑定时再带 `task_id`，会话状态按
`session_id` 原子写入 `state_dir`。多 Agent 想共用同一套记忆就共用 agent_id；
想分开记忆就为 profile 配不同 agent_id。

## 安装原则

Windows 的 `install.ps1` 与 Ubuntu/macOS 的 `install.py` 默认只打印方案
（dry-run），只有显式 `-Apply` / `--apply` 才会备份并合并 Claude Code、Codex、
ZCode 已存在的 JSON 配置；不会覆盖其他字段、不会触碰 OpenCode 配置，也不会把
密钥写入脚本。
