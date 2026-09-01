# Ubuntu 安装

## 前置条件

```sh
sudo apt-get update
sudo apt-get install -y git python3
```

## 安装

在下载或克隆出的仓库目录运行：

```sh
chmod +x bootstrap.sh
./bootstrap.sh --repository "https://github.com/<org>/<repo>.git"
```

首次运行会在 `$HOME/.tdai/config.json` 创建模板并停止。只在本机编辑该文件，
填入真实的 `endpoint`、`user_key`、`user_id`、`team_id`、`agent_id`，不要提交或
发送它。

配置完成后运行：

```sh
"$HOME/.tdai-hook/bootstrap.sh" \
  --repository "https://github.com/<org>/<repo>.git" --apply
```

也可以设置 `TDAI_CONFIG` 使用其他用户私有配置路径。省略 `--apply` 时只检查，
不修改 Agent 配置；更新已有安装时加 `--update`。

## 验证

```sh
python3 "$HOME/.tdai-hook/tdai-hook.py" --status
python3 "$HOME/.tdai-hook/install.py"
python3 -m unittest discover -s "$HOME/.tdai-hook/tests" -v
```

随后让目标 Agent 根据自己的 Hook 文档生成薄适配器，只负责事件字段映射、调用
标准核心和响应格式映射；不要把 Agent 专用路径或密钥写进标准仓库。
