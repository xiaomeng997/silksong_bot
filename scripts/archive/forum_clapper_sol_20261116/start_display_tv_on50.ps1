$ErrorActionPreference = 'Stop'
$taskRoot = 'C:/ssbot/data/m2_play/clapper_plan/analysis/w13_50_air_catch429_tv_on_20261114'
$taskCommand = '"C:\modeling\silksong_bot\brain\.venv\Scripts\python.exe" -B -X utf8 "C:\ssbot\data\m2_play\clapper_plan\analysis\w13_50_air_catch429_tv_on_20261114\display_hold429.py" "C:\ssbot\data\m2_play\clapper_plan\analysis\w13_50_air_catch429_tv_on_20261114"'
$taskClaim = Join-Path $taskRoot 'DISPLAY_HOLD_CLAIM.json'
$taskStream = [IO.File]::Open($taskClaim,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
$taskWriter = [IO.StreamWriter]::new($taskStream,[Text.UTF8Encoding]::new($false))
try { $taskWriter.Write('{"one_holder_for_this_authorized_batch":true}') } finally { $taskWriter.Dispose() }
$taskStartup = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ShowWindow=[UInt16]0}
$taskResult = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine=$taskCommand;CurrentDirectory=$taskRoot;ProcessStartupInformation=$taskStartup}
if ($taskResult.ReturnValue -ne 0) { throw "Display helper launch failed: $($taskResult.ReturnValue); do not retry automatically" }
@'
import datetime,json,psutil,sys,time
from pathlib import Path
g=Path('C:/ssbot/data/m2_play/clapper_plan/analysis/w13_50_air_catch429_tv_on_20261114')
p=psutil.Process(int(sys.argv[1]));deadline=time.monotonic()+10
while not (g/'DISPLAY_HOLD_READY.json').exists():
 if (g/'DISPLAY_HOLD_CLOSED.json').exists() or not p.is_running() or time.monotonic()>deadline:raise RuntimeError('display request not ready; no game launch')
 time.sleep(.1)
r=json.loads((g/'DISPLAY_HOLD_READY.json').read_text(encoding='utf-8'));actual=psutil.Process(r['pid']);assert abs(r['created']-actual.create_time())<.01 and (actual.pid==p.pid or actual.ppid()==p.pid) and 'display_hold429.py' in ' '.join(actual.cmdline())
owned=[dict(pid=x.pid,created=x.create_time(),name=x.name(),cmdline=x.cmdline(),ppid=x.ppid()) for x in {p.pid:p,actual.pid:actual}.values()]
with (g/'ROOT_OBSERVED_PROCESSES.json').open('x',encoding='utf-8') as f:json.dump(dict(at=datetime.datetime.now(datetime.timezone.utc).isoformat(),processes=owned),f)
print(json.dumps(dict(display_request_active=True,pid=actual.pid,created=actual.create_time(),physical_TV_power_not_verified=True)))
'@ | & 'C:/modeling/silksong_bot/brain/.venv/Scripts/python.exe' -B -X utf8 - $taskResult.ProcessId
if ($LASTEXITCODE -ne 0) { throw 'Display helper receipt failed; inspect/stop it, do not launch game' }
