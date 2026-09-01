[ERROR] - (starship::print): Under a 'dumb' terminal (TERM=dumb).

# TDAI Standard Hook：GitHub 分发与跨电脑安装

## 1. 发布到 GitHub

仓库只放标准套件源码和模板，不放实际 `user_key`、`config.json`、状态目录、
日志或会话文件。建议仓库至少包含：

```text
tdai-hook.py
tdai-memory.example.json
manifest.json
install.py
install.ps1
bootstrap.ps1
adapters/
tests/
README.md
```

在当前套件目录执行：

```powershell
git init
git add .
git commit -m "release tdai standard hook v1"
git branch -M main
git remote add origin https://github.com/<org>/<repo>.git
git push -u origin main
```

发布前运行：

```powershell
py -3 -m py_compile .\tdai-hook.py .\install.py
py -3 -m unittest discover -s .\tests -v
```

## 2. 其他 Windows 电脑的一键安装

管理员权限不是必需的。首次运行只会 clone 仓库并生成本地配置模板，然后以
退出码 2 停止，避免把占位符当成真实密钥：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
& .\bootstrap.ps1 -Repository "https://github.com/<org>/<repo>.git"
```

编辑生成的 `%USERPROFILE%\\.tdai\\config.json`：

```json
{
  "endpoint": "http://<memory-host>:8420",
  "user_key": "只保存在本机的密钥",
  "user_id": "usr-...",
  "team_id": "team-...",
  "agent_id": "agt-...",
  "team_name": "GIS系统",
  "agent_name": "GIS-toolbox"
}
```

然后执行安装：

```powershell
& "$env:USERPROFILE\\.tdai-hook\\bootstrap.ps1" `
  -Repository "https://github.com/<org>/<repo>.git" -Apply
```

`-Apply` 会对现有 Claude Code、Codex、ZCode JSON 配置做最小合并，并在同一目录
留下 `*.bak-tdai-时间戳`；不修改模型地址，不覆盖无关 Hook。省略 `-Apply` 是
dry-run。验证：

```powershell
py -3 "$env:USERPROFILE\\.tdai-hook\\tdai-hook.py" --status
py -3 "$env:USERPROFILE\\.tdai-hook\\install.py"
```

## 3. 各 Agent 接入

### Claude Code / Codex / ZCode / Grok / agy / DeepSeek Harness

它们若支持 JSON command hook，统一调用：

```text
py -3 %USERPROFILE%\\.tdai-hook\\tdai-hook.py
```

输入 `SessionStart`、`UserPromptSubmit`、`Stop` 事件，输出
`hookSpecificOutput.additionalContext`。同一套配置可通过 `TDAI_PROFILE` 选择
`codex`、`claude-code`、`zcode`、`grok`、`deepseek`、`harness`；是否共用
记忆由 profile 的 `agent_id` 决定。

### 原生协议不同的 Agent（例如 agy、OpenCode）

先读取 `adapters\\README.md` 和 `protocol\\tdai-hook-v1.md`，让目标 Agent
根据自己的 Hook 文档生成薄适配器。适配器只做字段和输出格式转换：

```text
原生事件 → 标准 JSON → tdai-hook.py → 标准上下文 → 原生响应
```

不要把宿主专用配置路径、模型地址或密钥放进标准核心。这样同一份核心可以
被不同 Agent 复用，而每个 Agent 的钩子由它自己遵循本机协议生成。

### OpenCode

OpenCode 使用进程内插件：

```powershell
cd "$env:USERPROFILE\\.tdai-hook\\adapters"
bun install
```

将 `adapters/opencode-plugin.ts` 加到 OpenCode 的全局插件目录或
`opencode.json` 的 `plugins`。它通过 v2 `session.hook("prompt")` 调用标准核心；
具体版本要与正在运行的 OpenCode 匹配，加载后用 `opencode2 api get /api/plugin`
确认。OpenCode v2 插件 API 当前仍可能变化。

## 4. 更新与回滚

更新前确认安装目录没有未提交改动：

```powershell
& "$env:USERPROFILE\\.tdai-hook\\bootstrap.ps1" `
  -Repository "https://github.com/<org>/<repo>.git" -Update -Apply
```

若只需回滚 Agent 配置，从对应 `*.bak-tdai-*` 备份恢复；标准套件本身可用
`git -C "$env:USERPROFILE\\.tdai-hook" checkout <tag>` 回到已发布版本。

## 5. 服务器端要求

每台电脑只需能访问 Memory API endpoint（默认 `/v3` 路径），并为使用者准备
有效的 `user_key`、`user_id`、`team_id`、`agent_id`。Hook 是旁路记忆调用，模型
仍走各 Agent 原来的登录和模型配置；后端不可达时 Hook fail-open，不阻塞 Agent。
