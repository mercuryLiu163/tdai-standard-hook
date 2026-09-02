# TDAI Hook Protocol v1

这是各 Agent 适配器与 Memory 核心之间的稳定边界。核心不依赖任何 Agent
的配置路径、模型地址或 UI 协议。

## 标准输入

适配器向 `tdai-hook.py` 的 stdin 发送一个 JSON 对象：

```json
{
  "hook_event_name": "UserPromptSubmit",
  "session_id": "session-123",
  "prompt": "用户原始提示",
  "last_assistant_message": "上一轮助手回复",
  "cwd": "C:\\work\\repo",
  "client": "agy"
}
```

稳定事件只有：`SessionStart`、`UserPromptSubmit`、`Stop`。字段同时接受
camelCase 别名。宿主没有直接提供 prompt 或 assistant message 时，适配器
可以从宿主 transcript 取最近一条对应消息。

启动器也可以用 `tdai-hook.py --client <agent-name>` 固定客户端。该参数既用于日志
归因，也选择配置中同名的 `profiles.<agent-name>`；事件里的 `client` 仍是协议字段，
适合能够生成完整标准 JSON 的适配器。环境变量 `TDAI_CLIENT` / `TDAI_PROFILE` 仅作
兼容，不是 Windows command hook 的首选配置方式。

## 标准输出

核心默认返回：

```json
{
  "hookSpecificOutput": {
    "hookEventName": "UserPromptSubmit",
    "additionalContext": "<tdai-memory>...</tdai-memory>"
  }
}
```

适配器只需提取 `additionalContext` 并转换成宿主要求的注入格式。设置
`TDAI_OUTPUT_MODE=all` 时，核心还会输出顶层 `additionalContext` 和
`additional_context`，便于不认识嵌套字段的宿主读取。

空输出或退出码 0 表示没有额外上下文；异常必须 fail-open，不能阻塞宿主。

## 适配器职责

每个 Agent 自己生成并维护原生 Hook。适配器只负责：

1. 把原生事件名转换成三个标准事件之一；
2. 把会话 ID、提示词、上一轮回复和工作目录映射到标准字段；
3. 调用标准核心并把上下文转换回原生响应；
4. 为 `Stop` 传入真实的 assistant message，不能伪造回复；
5. 宿主字段不完整时，从 transcript 倒序提取最近真实用户消息和最终模型文本，
   再使用标准字段别名回退；不要把工具日志或 Hook 输出当成 assistant message；
6. 任何解析、网络或核心错误都 fail-open。

核心之外的实现可以是 shell、PowerShell、Python、TypeScript 或 Agent 自己
生成的插件，但不得复制记忆业务逻辑。
