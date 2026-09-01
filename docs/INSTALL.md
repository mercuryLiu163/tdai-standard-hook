# TDAI Standard Hook：GitHub 分发与跨平台安装

本页是安装索引。Agent 自动安装时先读取根目录的 `AGENT_INSTALL.md`，再按操作
系统进入对应平台文档：

- [Windows](platforms/windows.md)
- [Ubuntu](platforms/ubuntu.md)
- [macOS](platforms/macos.md)
- [交互流程、数据流和提示词](MEMORY_INTERACTION.md)

## 仓库结构

```text
tdai-hook.py                  # 标准核心
bootstrap.ps1                 # Windows 安装引导
bootstrap.sh                  # Ubuntu/macOS 安装引导
install.py / install.ps1      # 配置检查与最小合并
tdai-memory.example.json      # 不含密钥的配置模板
protocol/                     # tdai-hook/v1 标准协议
adapters/                    # 各 Agent 薄适配器说明和示例
docs/platforms/              # 平台安装说明
tests/                        # 无网络协议回归测试
```

仓库只放标准套件源码和模板，不放实际 `user_key`、用户 `config.json`、状态目录、
日志或会话文件。发布前在仓库根目录运行：

```text
python -m py_compile tdai-hook.py install.py
python -m unittest discover -s tests -v
```

Windows 使用 `py -3` 替代 `python`；Ubuntu/macOS 使用 `python3`。发布到 GitHub
后，用户或 Agent 只需提供仓库地址，平台安装文档会完成其余步骤。

安装完成后不要跳过 [Agent 与 Memory 交互说明](MEMORY_INTERACTION.md)；目标 Agent
必须按其中的事件映射和验证提示词确认 UserPromptSubmit 的召回以及 Stop 的写回。

## `user_id`、Team Owner 与 Agent Owner

这几个字段不是同一个概念：

| 名称 | 含义 |
| --- | --- |
| 用户名/显示名 | 人类可读名称，不作为数据隔离依据 |
| 认证 `user_id` | `user_key` 经 `/v3/meta/auth/verify` 返回的内部身份 |
| `team.owner_user_id` | Team Owner，可能是另一个内部用户 |
| `agent.owner_user_id` | Agent 以及 `chat_memory-{team_id}-{agent_id}` 资产的 Owner |
| `task_id` | Agent 内的任务隔离维度，与用户所有权无关 |

标准 Hook 的配置必须满足：

```text
config.user_id = 认证 user_id = agent.owner_user_id
```

不要把 `team.owner_user_id` 写入 `config.user_id`。Hub 页面按 Chat-Memory 资产 Owner
读取 L0；即使 Team、Agent、Task 都正确，错误的 user_id 仍会把原文写入页面不可见
的身份桶。安装器会自动完成认证、Owner 校验和旧 user_id 纠正。

## 各 Agent 接入

标准核心接收 `SessionStart`、`UserPromptSubmit`、`Stop` 三类事件，输出标准 JSON。
目标 Agent 先阅读 `adapters/README.md` 和 `protocol/tdai-hook-v1.md`，再依据自己
的原生 Hook 文档生成薄适配器：

```text
原生事件 → 标准 JSON → tdai-hook.py → 标准上下文 → 原生响应
```

适配器只负责字段映射、调用和响应格式转换；不要把宿主专用配置路径、模型地址或
密钥写进标准核心。OpenCode 的进程内插件示例位于 `adapters/opencode-plugin.ts`，
它仍需按正在运行的 OpenCode 版本调整。

## 更新、回滚与服务器要求

各平台安装脚本的 `--update` / `-Update` 会在安装目录有未提交修改时拒绝覆盖；
显式 `--apply` / `-Apply` 才会合并 Agent 配置，并尽量留下备份。标准套件本身可
通过 Git tag 回到已发布版本。

每台电脑只需能访问 Memory API endpoint（默认 `/v3` 路径），并由用户私下提供有效
的 `user_key`、`team_id`、`agent_id`。`user_id` 由安装器根据 user_key 自动认证并
与 Agent owner 校验，避免相同显示名或旧配置把 L0 写入错误身份桶。模型仍走各 Agent 原来的登录和
模型配置；后端不可达时 Hook fail-open，不阻塞 Agent。
