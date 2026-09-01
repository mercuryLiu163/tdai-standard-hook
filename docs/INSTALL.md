# TDAI Standard Hook：GitHub 分发与跨平台安装

本页是安装索引。Agent 自动安装时先读取根目录的 `AGENT_INSTALL.md`，再按操作
系统进入对应平台文档：

- [Windows](platforms/windows.md)
- [Ubuntu](platforms/ubuntu.md)
- [macOS](platforms/macos.md)

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
的 `user_key`、`user_id`、`team_id`、`agent_id`。模型仍走各 Agent 原来的登录和
模型配置；后端不可达时 Hook fail-open，不阻塞 Agent。
