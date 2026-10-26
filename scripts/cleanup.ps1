# Destinado ao Agendador de Tarefas do Windows; utiliza caminhos absolutos.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
& "$projectRoot\.venv\Scripts\python.exe" "$projectRoot\scripts\cleanup_logs.py"
exit $LASTEXITCODE
