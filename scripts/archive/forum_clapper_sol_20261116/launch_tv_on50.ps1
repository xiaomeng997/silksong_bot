$ErrorActionPreference = 'Stop'
$taskRoot = 'C:/ssbot/data/m2_play/clapper_plan/analysis/w13_50_air_catch429_tv_on_20261114'
$taskSource = 'd7cbe1a59cbee1d8fa8d40c53fc57b3ed1bd2b19'
$taskPython = 'C:/modeling/silksong_bot/brain/.venv/Scripts/python.exe'
$taskContract = 'C:/ssbot/data/m2_play/clapper_plan/sol/demos/w13_50_air_catch429_tv_on_20261114/contract.json'
$taskAuth = Join-Path $taskRoot 'USER_NEW50_AUTHORIZATION.json'
$taskClaimPath = Join-Path $taskRoot 'LAUNCH_CLAIM.json'
$taskClaim = @{
    at = [DateTimeOffset]::UtcNow.ToString('o')
    batch_id = 'w13_50_air_catch429_tv_on_20261114'
    source = $taskSource
    user_authorization_sha256 = (Get-FileHash -LiteralPath $taskAuth -Algorithm SHA256).Hash.ToLowerInvariant()
    contract_sha256 = (Get-FileHash -LiteralPath $taskContract -Algorithm SHA256).Hash.ToLowerInvariant()
}
$taskStream = [IO.File]::Open($taskClaimPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
$taskWriter = [IO.StreamWriter]::new($taskStream, [Text.UTF8Encoding]::new($false))
try { $taskWriter.Write(($taskClaim | ConvertTo-Json -Depth 8)) } finally { $taskWriter.Dispose() }
$taskCommand = '"C:\modeling\silksong_bot\brain\.venv\Scripts\python.exe" -B -X utf8 "C:\ssbot\data\m2_play\clapper_plan\analysis\w13_50_air_catch429_tv_on_20261114\run_unattended.py"'
$taskStartup = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ShowWindow = [UInt16]0}
$taskResult = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
    CommandLine = $taskCommand
    CurrentDirectory = 'C:\ssbot\data\m2_play\clapper_plan\analysis\air_catch428_20261114\source_fixed428'
    ProcessStartupInformation = $taskStartup
}
if ($taskResult.ReturnValue -ne 0) { throw "WMI launch failed: $($taskResult.ReturnValue); claim retained, no automatic retry" }
@'
import datetime,hashlib,json,psutil,sys
from pathlib import Path
g=Path('C:/ssbot/data/m2_play/clapper_plan/analysis/w13_50_air_catch429_tv_on_20261114')
claim=json.loads((g/'LAUNCH_CLAIM.json').read_text(encoding='utf-8-sig'))
p=psutil.Process(int(sys.argv[1]))
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
receipt={**claim,'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'pid':p.pid,'created':p.create_time(),'command':p.cmdline(),'coordinator_script_sha256':sha(g/'run_unattended.py'),'claim_sha256':sha(g/'LAUNCH_CLAIM.json')}
with (g/'ROOT_LAUNCH_RECEIPT.json').open('x',encoding='utf-8') as f:json.dump(receipt,f,ensure_ascii=False,indent=2)
print(json.dumps({'launched':True,'pid':p.pid,'created':p.create_time(),'batch':claim['batch_id'],'source':claim['source'],'authorization_verified':True}))
'@ | & $taskPython -B -X utf8 - $taskResult.ProcessId
if ($LASTEXITCODE -ne 0) { throw 'Launch receipt failed; inspect existing process, do not launch again' }
