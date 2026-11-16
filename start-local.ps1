$ErrorActionPreference = 'Stop'
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Missing .venv. Follow README.md first.' }
& $python (Join-Path $PSScriptRoot 'scripts\dev.py')
exit $LASTEXITCODE
