$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$cmdPath = Join-Path $scriptDir 'supervisor.cmd'

if (-not (Test-Path $cmdPath)) {
    throw "supervisor.cmd not found: $cmdPath"
}

& $cmdPath @args
exit $LASTEXITCODE