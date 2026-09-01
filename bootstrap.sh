#!/usr/bin/env sh
set -eu

usage() {
  cat <<'EOF'
用法：
  ./bootstrap.sh --repository <Git 仓库地址> [--install-root <目录>] [--update] [--apply]

首次运行会复制用户私有配置模板并以退出码 2 停止，填写配置后再次运行。
EOF
}

die() {
  echo "TDAI Standard Hook: $*" >&2
  exit 1
}

repository=""
install_root="${HOME}/.tdai-hook"
update=0
apply=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --repository)
      [ "$#" -ge 2 ] || die "--repository 缺少参数"
      repository="$2"
      shift 2
      ;;
    --install-root)
      [ "$#" -ge 2 ] || die "--install-root 缺少参数"
      install_root="$2"
      shift 2
      ;;
    --update)
      update=1
      shift
      ;;
    --apply)
      apply=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      die "未知参数：$1"
      ;;
  esac
done

[ -n "$repository" ] || { usage >&2; die "必须提供 --repository"; }
command -v git >/dev/null 2>&1 || die "未找到 git"
command -v python3 >/dev/null 2>&1 || die "未找到 python3"

install_root="${install_root%/}"
[ -n "$install_root" ] || die "安装目录不能为空"
mkdir -p "$(dirname "$install_root")"

if [ -d "$install_root/.git" ]; then
  if [ "$update" -eq 1 ]; then
    [ -z "$(git -C "$install_root" status --porcelain)" ] || \
      die "安装目录有未提交修改，拒绝覆盖：$install_root"
    git -C "$install_root" pull --ff-only
  fi
elif [ -e "$install_root" ]; then
  die "安装目录已存在但不是 Git 仓库：$install_root"
else
  git clone --depth 1 "$repository" "$install_root"
fi

config="${TDAI_CONFIG:-$HOME/.tdai/config.json}"
if [ ! -f "$config" ]; then
  mkdir -p "$(dirname "$config")"
  cp "$install_root/tdai-memory.example.json" "$config"
  echo "已创建用户私有配置模板：$config"
  echo "请填写 endpoint、user_key、team_id、agent_id 后再次运行；user_id 将按 user_key 自动校正。"
  exit 2
fi

if [ "$apply" -eq 1 ]; then
  exec python3 "$install_root/install.py" --config "$config" --apply
fi
exec python3 "$install_root/install.py" --config "$config"
