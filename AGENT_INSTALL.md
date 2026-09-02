# Agent 安装入口

当用户只提供一句“请根据 GitHub 仓库地址安装 TDAI Standard Hook”并附上
本仓库地址时，Agent 应先读取本文件，再执行安装。用户提示词不需要重复
下面的步骤。

## 执行顺序

1. 从用户消息取得 GitHub 仓库地址，确认它是本套件仓库；读取
   `README.md`、`docs/MEMORY_INTERACTION.md`、`protocol/tdai-hook-v1.md`、
   `adapters/README.md` 和当前系统对应的 `docs/platforms/*.md`。
2. 识别宿主操作系统：Windows 使用 `bootstrap.ps1`，Ubuntu 和 macOS 使用
   `bootstrap.sh`。按对应平台文档执行；默认安装目录分别是
   `%USERPROFILE%\\.tdai-hook` 或 `$HOME/.tdai-hook`。已有安装目录有未提交修改时，
   不覆盖也不强制更新。
3. 如果脚本创建了用户私有的 `config.json` 模板，停止安装并向用户索取缺失的
   endpoint、user_key、team_id、agent_id 等值；不要猜测，不要把密钥写回仓库。
   `user_id` 由安装器通过 user_key 实际认证并校正，同时校验该 user 是所选
   Agent 的 owner。不要根据显示名手工填写 user_id。
4. 配置完成后，让 `TDAI_CONFIG` 指向用户私有配置。启动标准核心时优先在命令中
   传入 `--client <agent-name>`；它同时选择同名 profile 并写入日志归因。只有宿主
   无法传 argv 时才使用 `TDAI_PROFILE` / `TDAI_CLIENT`。没有现成 profile 时，只
   添加客户端标识，不复制 Memory 业务逻辑。
5. 阅读当前 Agent 自己的 Hook 文档，生成它自己的原生 Hook。原生 Hook 只做
   事件字段映射、调用 `tdai-hook.py` 和响应格式映射；交互时序见
   `docs/MEMORY_INTERACTION.md`，核心标准见 `protocol/tdai-hook-v1.md`。
6. 合并原生配置时保留已有 Hook；能备份就先备份。不要修改模型 endpoint、模型
   选择或无关权限配置。
7. 按当前平台文档运行 `tdai-hook.py --status` 和仓库测试；再用一个普通 Prompt、
   一次 `/tdai-recall <query>` 和一次正常 Stop 验证召回与写回。若宿主提供 Hook
   列表命令，也检查该 Hook 已加载。Windows command hook 必须使用宿主支持的
   argv 或规范化绝对路径，例如 `py -3 C:/.../tdai-hook.py --client zcode`；不能把
   环境变量和多重引号嵌套进 JSON command。
8. 最后报告实际写入的配置路径、生成的原生 Hook 路径、验证结果和仍需用户
   配置的项目。任何异常都应 fail-open，不能阻塞宿主 Agent。

## 身份字段的唯一含义

安装和更新时必须按下面的语义处理身份字段，不能根据显示名或 Team Owner 猜测：

| 字段 | 准确含义 | 是否可写入 `config.user_id` |
| --- | --- | --- |
| 用户名/显示名 | 给人看的名称，可能重名，也可能对应多把密钥 | 否 |
| 认证 `user_id` | `user_key` 调用 `/v3/meta/auth/verify` 得到的内部用户 ID | 是，且这是唯一来源 |
| `team.owner_user_id` | Team 的创建者/Owner；可以与当前用户和 Agent Owner 不同 | 否 |
| `agent.owner_user_id` | 所选 Agent 及其 Chat-Memory 资产的数据 Owner | 只用于与认证 `user_id` 比对 |
| `task_id` | Agent 下的任务隔离维度，不代表用户或资产所有权 | 否 |

必须满足：

```text
config.user_id = auth/verify(user_key).user.user_id = agent.owner_user_id
```

`team.owner_user_id` 不参与 Hook 的 `user_id` 配置。Chat-Memory 的页面块 ID 虽然
由 Team + Agent 组成，但 L0/L1 数据面仍按 user_id 隔离；填入 Team Owner 会导致
接口返回 accepted ID，而页面读取不到这批数据。

## 平台文档

- Windows：`docs/platforms/windows.md`
- Ubuntu：`docs/platforms/ubuntu.md`
- macOS：`docs/platforms/macos.md`

## 禁止事项

- 不上传或输出 `user_key`、token、密码、个人配置和运行日志；
- 不把 Memory endpoint 当成模型 endpoint；
- 不从用户提示词覆盖 `team_id`、`agent_id` 或 `user_id`；
- 不把 `team.owner_user_id` 当成认证用户或 Agent Owner；
- 不伪造 `last_assistant_message`；
- 不把某个 Agent 的原生适配逻辑复制到标准核心。
