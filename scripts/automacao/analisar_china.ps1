# uv prepara o ambiente isolado do monitor; argumentos seguem para o motor.
$ErrorActionPreference = 'Stop'
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw 'uv não encontrado no PATH.'
}
& uv run --no-project --with psutil==7.2.2 python -u (Join-Path $PSScriptRoot 'lote.py') --country CN @args
exit $LASTEXITCODE
