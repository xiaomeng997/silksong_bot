# Launch the training copy in a small window without leaving any trace in the user's game settings.
# Unity writes the launch resolution back to PlayerPrefs (HKCU) on exit, and PlayerPrefs are shared by
# every copy of the game, so we snapshot the key before launch and restore it exactly after exit.
param(
    [int]$Width = 1280,
    [int]$Height = 720,
    [string]$GameDir = 'C:\ssbot\game\train'
)

$ErrorActionPreference = 'Stop'
$key = 'HKCU\Software\Team Cherry\Hollow Knight Silksong'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$snapDir = 'C:\ssbot\sandbox\prefs'
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
