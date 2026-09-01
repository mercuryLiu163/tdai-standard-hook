param(
    [Parameter(Mandatory = $true)]
    [string]$Repository,
    [string]$InstallRoot = (Join-Path $env:USERPROFILE ".tdai-hook"),
    [switch]$Update,
    [switch]$Apply
)

$ErrorActionPreference = "Stop"
$git = Get-Command git -ErrorAction SilentlyContinue
if (-not $git) { throw "git 未找到，请先安装 Git for Windows" }

$root = [IO.Path]::GetFullPath($InstallRoot)
$gitDir = Join-Path $root ".git"
if (Test-Path -LiteralPath $gitDir) {
    if ($Update) {
        $dirty = @(git -C $root status --porcelain)
        if ($dirty.Count -gt 0) { throw "安装目录有未提交修改，拒绝自动更新：$root" }
        git -C $root pull --ff-only
    }
} elseif (Test-Path -LiteralPath $root) {
    throw "安装目录已存在但不是 Git 仓库：$root"
} else {
    git clone --depth 1 $Repository $root
}

$config = if ($env:TDAI_CONFIG) {
    [IO.Path]::GetFullPath($env:TDAI_CONFIG)
} else {
    Join-Path $env:USERPROFILE ".tdai\config.json"
}
$configDir = Split-Path -Parent $config
if (-not (Test-Path -LiteralPath $config)) {
    New-Item -ItemType Directory -Path $configDir -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $root "tdai-memory.example.json") -Destination $config
    Write-Host "已创建配置模板：$config"
    Write-Host "请先编辑 endpoint、user_key、user_id、team_id、agent_id，再重新运行本脚本。"
    exit 2
}

$py = Get-Command py -ErrorAction SilentlyContinue
if (-not $py) { $py = Get-Command python -ErrorAction SilentlyContinue }
if (-not $py) { throw "Python 3 未找到" }
$install = Join-Path $root "install.py"
$argsList = @("-3", $install, "--config", $config)
if ($Apply) { $argsList += "--apply" }
& $py.Source @argsList
exit $LASTEXITCODE
