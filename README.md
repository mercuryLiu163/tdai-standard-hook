# TDAI Standard Hook

跨 Agent 的 Tencent Agent Memory Hook 标准实现（`tdai-hook/v1`）。核心脚本不
依赖任何 Agent SDK，只读 stdin JSON、向 stdout 输出标准 JSON，因此同一份代码
可以被 Codex、Claude Code、ZCode、Grok、agy、DeepSeek Harness 等复用；OpenCode
通过 `adapters/opencode-plugin.ts` 调用同一核心。

## 目录

- `tdai-hook.py`：标准核心，包含 Session/Task 绑定、条件召回、L0 capture、原子状态、日志和 fail-open。
- `manifest.json`：协议版本、事件和适配器清单。
- `tdai-memory.example.json`：不含密钥的配置模板。
- `adapters/README.md`：统一事件协议和各 Agent 接入方式。
- `adapters/opencode-plugin.ts`：OpenCode v2 进程内插件。
- `install.py` / `install.ps1`：默认 dry-run；显式 `--apply` 才合并配置并留下备份。
- `tests/test_protocol.py`：无网络协议回归测试。

## 快速接入

```text
py -3 C:\Users\<user>\.tdai-hook\tdai-hook.py
```

设置 `TDAI_CONFIG` 指向已有 Memory 配置；未设置时依次尝试
`%USERPROFILE%\\.tdai\\config.json`、`%USERPROFILE%\\.tdai\\tdai-memory.json`。
可用 `TDAI_PROFILE` 选择同一配置
中的客户端 profile。标准入口不修改模型地址，也不把 Memory endpoint 当作模型
代理。

```powershell
py -3 C:\Users\mercuryliu\.tdai-hook\tdai-hook.py --status
py -3 C:\Users\mercuryliu\.tdai-hook\install.py       # 只检查，不写配置
py -3 C:\Users\mercuryliu\.tdai-hook\install.py --apply
```

## 稳定契约

输入事件支持 `SessionStart`、`UserPromptSubmit`、`Stop`，同时接受 camelCase 和
snake_case 字段。Hook 失败、后端不可用、JSON 或状态异常都退出 0 且不向模型
注入错误文本；错误只记到 `hook.log` / `hook.jsonl`。状态文件采用临时文件 +
原子替换，按 `session_id` 隔离；每次 API 请求都显式带 team/agent/user，Task
请求再带 task_id。

普通提示不会自动召回；只有配置的历史关键词或 `/tdai-recall <query>` 才召回。
`injected_chars` 日志保留 binding、memory、capability、total 字段，方便验证
缓存和 token 成本。默认只输出 `hookSpecificOutput.additionalContext`；旧宿主可
设置 `TDAI_OUTPUT_MODE=all` 同时输出顶层别名。

## 当前机器已切换

安装器已把现有 Codex、Claude Code 配置切到此标准入口，并为每个配置留下
`*.bak-tdai-YYYYMMDD-HHMMSS` 备份；同时创建了 ZCode 全局
`%USERPROFILE%\\.zcode\\hooks\\hooks.json`。OpenCode、Grok、agy、DeepSeek
Harness 需要按 `adapters/README.md` 加载原生插件或 command hook；未知宿主不要
直接猜字段，只做统一事件映射。
