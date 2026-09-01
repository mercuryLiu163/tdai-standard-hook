# TDAI Standard Hook

跨 Agent 的 Tencent Agent Memory Hook 标准实现（`tdai-hook/v1`）。核心脚本不
依赖任何 Agent SDK，只读 stdin JSON、向 stdout 输出标准 JSON，因此同一份代码
可以被 Codex、Claude Code、ZCode、Grok、agy、DeepSeek Harness 等复用；OpenCode
通过 `adapters/opencode-plugin.ts` 调用同一核心。

## Agent 一句话安装

用户可以只发送“请根据 GitHub 仓库地址安装 TDAI Standard Hook”并附上本仓库
地址。Agent 克隆仓库后，先读取根目录的 `AGENT_INSTALL.md`，再按其中流程
安装、生成自己的原生 Hook 并验证。完整人工安装说明见 `docs/INSTALL.md`。

## 目录

```text
tdai-hook.py                  # 标准核心
manifest.json                 # 协议、事件和适配器清单
AGENT_INSTALL.md              # Agent 自行安装入口
tdai-memory.example.json      # 不含密钥的配置模板
bootstrap.ps1                 # Windows 安装引导
bootstrap.sh                  # Ubuntu/macOS 安装引导
install.py / install.ps1      # 配置检查与最小合并
protocol/                     # tdai-hook/v1 标准协议
adapters/                    # 各 Agent 的薄适配器说明和示例
docs/platforms/              # Windows、Ubuntu、macOS 平台说明
tests/                        # 无网络协议回归测试
```

## 平台支持

| 平台 | 安装引导 | 默认安装目录 | Python |
| --- | --- | --- | --- |
| Windows | `bootstrap.ps1` | `%USERPROFILE%\\.tdai-hook` | `py -3` |
| Ubuntu | `bootstrap.sh` | `$HOME/.tdai-hook` | `python3` |
| macOS | `bootstrap.sh` | `$HOME/.tdai-hook` | `python3` |

完整步骤见 [`docs/INSTALL.md`](docs/INSTALL.md) 及对应平台文档。

## 快速接入

Windows：

```powershell
py -3 "$env:USERPROFILE\\.tdai-hook\\tdai-hook.py" --status
py -3 "$env:USERPROFILE\\.tdai-hook\\install.py"       # 只检查，不写配置
```

Ubuntu/macOS：

```sh
python3 "$HOME/.tdai-hook/tdai-hook.py" --status
python3 "$HOME/.tdai-hook/install.py"                    # 只检查，不写配置
```

设置 `TDAI_CONFIG` 指向用户私有的 Memory 配置；未设置时使用平台默认的
`$HOME/.tdai/config.json`（Windows 为 `%USERPROFILE%\\.tdai\\config.json`）。
可用 `TDAI_PROFILE` 选择同一配置中的客户端 profile。标准入口不修改模型地址，
也不把 Memory endpoint 当作模型代理。

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
