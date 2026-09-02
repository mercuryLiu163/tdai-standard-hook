# Windows 安装

## 前置条件

- Git for Windows
- Python 3（推荐通过 `py -3` 调用）
- 目标 Agent 已安装并能加载 command hook

## 安装

在下载或克隆出的仓库目录运行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
& .\bootstrap.ps1 -Repository "https://github.com/<org>/<repo>.git"
```

首次运行会在 `%USERPROFILE%\.tdai\config.json` 创建模板并停止。只在本机编辑
该文件，填入真实的 `endpoint`、`user_key`、`team_id`、`agent_id`。`user_id` 会在
安装时按 user_key 自动认证并校正。不要提交或发送它。

配置完成后运行：

```powershell
& "$env:USERPROFILE\.tdai-hook\bootstrap.ps1" `
  -Repository "https://github.com/<org>/<repo>.git" -Apply
```

省略 `-Apply` 时只检查，不修改 Agent 配置。更新已有安装时加 `-Update`；安装
目录有未提交修改时脚本会拒绝覆盖。

## Command Hook 路径

如果宿主的 Hook 配置只接受一个 Windows command 字符串，使用安装后的实际绝对
路径和正斜杠：

```text
py -3 C:/Users/<user>/.tdai-hook/adapters/<agent>-hook.py
```

不要把 `"%USERPROFILE%\\..."` 再嵌套进 JSON command；宿主支持 argv 时，优先
传递 `py`、`-3`、脚本路径三个参数。适配器内部应按自身文件位置查找标准核心。

如果宿主可直接把标准事件 JSON 传给核心，不需要额外适配器，请在普通命令参数中
显式指定客户端：

```text
py -3 C:/Users/<user>/.tdai-hook/tdai-hook.py --client zcode
```

`--client zcode` 会选择配置中的 `profiles.zcode`，并让绑定提示及日志显示
`client=zcode`。它不是环境变量赋值，可以安全写入只接受 command 字符串的
`hooks.json`。不要为此设置 Windows 用户级 `TDAI_PROFILE`，因为该全局变量会影响
同一用户启动的其他 Agent。只有无法传递命令参数时才把环境变量作为兼容方案。

## 验证

```powershell
py -3 "$env:USERPROFILE\.tdai-hook\tdai-hook.py" --status
py -3 "$env:USERPROFILE\.tdai-hook\install.py"
py -3 -m unittest discover -s "$env:USERPROFILE\.tdai-hook\tests" -v
```

随后让目标 Agent 根据自己的 Hook 文档生成薄适配器，只负责事件字段映射、调用
标准核心和响应格式映射；不要把 Agent 专用路径或密钥写进标准仓库。
