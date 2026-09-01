# Agent 安装入口

当用户只提供一句“请根据 GitHub 仓库地址安装 TDAI Standard Hook”并附上
本仓库地址时，Agent 应先读取本文件，再执行安装。用户提示词不需要重复
下面的步骤。

## 执行顺序

1. 从用户消息取得 GitHub 仓库地址，确认它是本套件仓库；读取
   `README.md`、`protocol/tdai-hook-v1.md` 和 `adapters/README.md`。
2. 在 Windows 上运行 `bootstrap.ps1 -Repository <仓库地址>`，将套件安装到
   `%USERPROFILE%\\.tdai-hook`。已有安装目录有未提交修改时，不覆盖也不强制更新。
3. 如果脚本创建了 `%USERPROFILE%\\.tdai\\config.json` 模板，停止安装并向用户
   索取缺失的 endpoint、user_key、user_id、team_id、agent_id 等值；不要猜测，
   不要把密钥写回仓库。
4. 配置完成后，设置 `TDAI_CONFIG=%USERPROFILE%\\.tdai\\config.json`，并使用
   当前 Agent 对应的 `TDAI_PROFILE`。没有现成 profile 时，只添加客户端标识，
   不复制 Memory 业务逻辑。
5. 阅读当前 Agent 自己的 Hook 文档，生成它自己的原生 Hook。原生 Hook 只做
   事件字段映射、调用 `tdai-hook.py` 和响应格式映射；核心标准见
   `protocol/tdai-hook-v1.md`。不要使用 `.grok` 旧路径。
6. 合并原生配置时保留已有 Hook；能备份就先备份。不要修改模型 endpoint、模型
   选择或无关权限配置。
7. 运行 `py -3 "%USERPROFILE%\\.tdai-hook\\tdai-hook.py" --status`，再运行仓库
   测试。若宿主提供 Hook 列表命令，也检查该 Hook 已加载。
8. 最后报告实际写入的配置路径、生成的原生 Hook 路径、验证结果和仍需用户
   配置的项目。任何异常都应 fail-open，不能阻塞宿主 Agent。

## 其他系统

没有 `bootstrap.ps1` 的系统使用等价的 Git/Python 流程：将仓库克隆到用户
目录，复制 `tdai-memory.example.json` 为用户私有配置，调用
`python3 install.py` 或直接调用 `tdai-hook.py`。原生 Hook 仍由目标 Agent
按同一标准协议生成。

## 禁止事项

- 不上传或输出 `user_key`、token、密码、个人配置和运行日志；
- 不把 Memory endpoint 当成模型 endpoint；
- 不从用户提示词覆盖 `team_id`、`agent_id` 或 `user_id`；
- 不伪造 `last_assistant_message`；
- 不把某个 Agent 的原生适配逻辑复制到标准核心。
