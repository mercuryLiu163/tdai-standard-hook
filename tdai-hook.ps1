param(
    [string]$Profile = ""
)

# Thin Windows launcher. It deliberately does not modify any agent config.
if ($Profile) { $env:TDAI_PROFILE = $Profile }
$script = Join-Path $PSScriptRoot "tdai-hook.py"
$py = Get-Command py -ErrorAction SilentlyContinue
if ($py) {
    & $py.Source -3 $script
} else {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) { exit 0 }
    & $python.Source $script
}
exit $LASTEXITCODE
