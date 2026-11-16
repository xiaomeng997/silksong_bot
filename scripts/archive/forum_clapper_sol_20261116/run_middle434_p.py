"""Bounded sequential use of the unchanged executor; finalize even a failed run."""
from pathlib import Path
from datetime import datetime, timezone
import json
import subprocess
import sys
import psutil

sys.stdout.reconfigure(encoding='utf-8')
A=Path('C:/ssbot/data/m2_play/clapper_plan/analysis/middle_handoff434_20261114')
EX='C:/ssbot/data/m2_play/clapper_plan/sol/performance/executor_v2.py'
PY='C:/modeling/silksong_bot/brain/.venv/Scripts/python.exe'
me=psutil.Process();me.cpu_affinity(list(range(24,32)));me.nice(psutil.IDLE_PRIORITY_CLASS)
now=lambda:datetime.now(timezone.utc).isoformat()
record=dict(at=now(),pid=me.pid,created=me.create_time(),bounded=True,steps=[],complete=False,error=None)
def save():(A/'ORCHESTRATION.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def call(mode,arm,out,pre=None):
    cmd=[PY,'-B',EX,mode,'--case',str(A/f'CASE_{arm}.json'),'--output',str(out)]
    if pre:cmd+=['--preflight',str(pre)]
    step=dict(mode=mode,arm=arm,output=str(out),start=now());record['steps'].append(step);save()
    print(json.dumps({'starting':mode,'arm':arm,'output':str(out)},ensure_ascii=False),flush=True)
    r=subprocess.run(cmd,capture_output=True,text=True,encoding='utf-8',errors='replace')
    step.update(end=now(),returncode=r.returncode,stdout=r.stdout,stderr=r.stderr);save()
    print(json.dumps({'finished':mode,'arm':arm,'returncode':r.returncode,'stdout':r.stdout[-700:],'stderr':r.stderr[-700:]},ensure_ascii=False),flush=True)
    return r.returncode
save()
try:
    for arm in ['ON','OFF']:
        check=A/f'CHECK_{arm}';out=A/f'P_{arm}'
        for mode,dest,pre in [('check',check,None),('measure',out,check)]:
            assert not dest.exists(),str(dest)
            code=call(mode,arm,dest,pre)
            if (dest/'EXECUTION.json').exists():
                fin=call('finalize',arm,dest)
                assert fin==0,f'{mode}/{arm} finalize failed'
            else:
                raise RuntimeError(f'{mode}/{arm} produced no execution receipt; inspect preserved output')
            assert code==0,f'{mode}/{arm} failed; finalized and stopped'
    record.update(complete=True,ended=now());save()
    print('ALL_BOUNDED_P_STEPS_COMPLETED',flush=True)
except BaseException as exc:
    record.update(error={'type':type(exc).__name__,'message':str(exc)},ended=now());save()
    raise
