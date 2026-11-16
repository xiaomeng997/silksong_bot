param(
    [Parameter(Mandatory = $true)][string]$LaunchScript,
    [Parameter(Mandatory = $true)][string]$BatchRoot
)
$ErrorActionPreference = 'Stop'
$taskPython = 'C:/modeling/silksong_bot/brain/.venv/Scripts/python.exe'
$taskLaunch = (Resolve-Path -LiteralPath $LaunchScript).Path
$taskBatch = (Resolve-Path -LiteralPath $BatchRoot).Path
$taskRelease = Join-Path $taskBatch 'release.py'
if (-not (Test-Path -LiteralPath $taskRelease)) { throw 'Missing reviewed release script' }
if (Test-Path -LiteralPath (Join-Path $taskBatch 'LAUNCH_CLAIM.json')) { throw 'Batch already launched; do not relaunch' }
if (Test-Path -LiteralPath (Join-Path $taskBatch 'COORDINATOR_END.json')) { throw 'Batch already ended; do not reopen' }
# The reviewed launcher binds the actual user authorization and contract.
& $taskLaunch
if ($LASTEXITCODE -ne 0) { throw 'Launch failed; inspect the existing process, never retry automatically' }
# The reviewed release waits at most120s for actual readiness, checks input,
# capture, source, resource, startup FPS and authorization, then atomically GO.
& $taskPython -B -X utf8 $taskRelease
if ($LASTEXITCODE -ne 0) { throw 'Release refused; retain cancellation/cleanup evidence and do not retry' }
