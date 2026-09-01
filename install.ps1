[ERROR] - (starship::print): Under a 'dumb' terminal (TERM=dumb).

param([switch]$Apply)
$argsList = @("-3", (Join-Path $PSScriptRoot "install.py"))
if ($Apply) { $argsList += "--apply" }
$py = Get-Command py -ErrorAction SilentlyContinue
if ($py) { & $py.Source @argsList; exit $LASTEXITCODE }
$python = Get-Command python -ErrorAction SilentlyContinue
if ($python) { & $python.Source (Join-Path $PSScriptRoot "install.py") $(if ($Apply) { "--apply" }); exit $LASTEXITCODE }
Write-Error "Python launcher not found"
exit 1
