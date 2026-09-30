# Launch the training copy in a small window without leaving any trace in the user's game settings.
# Unity writes the launch resolution back to PlayerPrefs (HKCU) on exit, and PlayerPrefs are shared by
# every copy of the game, so we snapshot the key before launch and restore it exactly after exit.
# Superseded for training by `python -m ssbot.tools.launcher -n N` (brain/ssbot/tools/launcher.py): per-instance
# ports/logs/sandboxes, window tiling, and one golden-snapshot restore shared by concurrent launchers. This script
# refuses to run while that launcher has live instances or still owes a golden restore (its instances.json): its own
# before/after snapshot would capture their settings or undo the launcher's restore. The launcher in turn refuses to
# start while a game process it did not register (e.g. one started here) is running.
param(
    [int]$Width = 1280,
    [int]$Height = 720,
    [string]$GameDir = 'C:\ssbot\game\train',
    [string]$PrefsDir = 'C:\ssbot\sandbox\prefs'
)

$ErrorActionPreference = 'Stop'
$key = 'HKCU\Software\Team Cherry\Hollow Knight Silksong'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$snapDir = $PrefsDir

# Live launcher instances: the pid is alive with the recorded creation time (epoch seconds, as psutil gives it).
$registry = Join-Path $snapDir 'instances.json'
if (Test-Path $registry) {
    $state = Get-Content -Raw $registry | ConvertFrom-Json
    $live = @($state.instances | Where-Object {
        $p = Get-Process -Id $_.pid -ErrorAction SilentlyContinue
        if (-not $p) { return $false }
        if ($null -eq $_.created) { return $true }
        try { $started = ([DateTimeOffset]$p.StartTime).ToUnixTimeMilliseconds() / 1000.0 } catch { return $true }
        [math]::Abs($started - [double]$_.created) -le 1.0
    })
    if ($live.Count -gt 0) {
        throw "refusing: $($live.Count) instance(s) of ssbot.tools.launcher are running (pids $(($live | ForEach-Object { $_.pid }) -join ', ')); wait for them or stop them first"
    }
    if ($state.restore_pending) {
        throw "refusing: the launcher still owes a golden PlayerPrefs restore; run 'python -m ssbot.tools.launcher --restore' first"
    }
}

New-Item -ItemType Directory -Force $snapDir | Out-Null
$snapshot = Join-Path $snapDir "before_$stamp.reg"

cmd /c "reg export `"$key`" `"$snapshot`" /y >nul 2>&1"
if ($LASTEXITCODE -ne 0) { throw "could not snapshot $key" }

$exe = Join-Path $GameDir 'Hollow Knight Silksong.exe'
$args = @('-screen-fullscreen', '0', '-screen-width', "$Width", '-screen-height', "$Height")
$proc = Start-Process -FilePath $exe -WorkingDirectory $GameDir -ArgumentList $args -PassThru
Write-Host "started pid $($proc.Id) at ${Width}x${Height}; settings snapshot $snapshot"

try {
    $proc.WaitForExit()
}
finally {
    # reg.exe prints its success message on stderr, which Windows PowerShell 5.1 turns into an error record; go through cmd.
    cmd /c "reg export `"$key`" `"$(Join-Path $snapDir "after_$stamp.reg")`" /y >nul 2>&1"
    cmd /c "reg delete `"$key`" /f >nul 2>&1"
    cmd /c "reg import `"$snapshot`" >nul 2>&1"
    if ($LASTEXITCODE -ne 0) { throw "RESTORE FAILED - import $snapshot manually" }
    Write-Host 'game exited; settings restored'
}
