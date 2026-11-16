"""Light monitor of this one already-running batch; ends with its coordinator."""
from pathlib import Path
import contextlib,importlib.util,io,json,time,psutil
B=Path('C:/ssbot/data/m2_play/clapper_plan');G=B/'analysis/w13_50_middle_handoff434_20261114';D=B/'sol/demos'/G.name
spec=importlib.util.spec_from_file_location('live50watch',G/'root_live_watch.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
seen=G/'ROOT_OBSERVED_PROCESSES.json';r=json.loads(seen.read_text(encoding='utf-8'));me=psutil.Process();owners=[me]
parent=me.parent()
if parent and 'watch_middle434_loop.py' in ' '.join(parent.cmdline()):owners.append(parent)
for p in owners:r['processes'].append(dict(pid=p.pid,created=p.create_time(),name=p.name(),cmdline=p.cmdline(),ppid=p.ppid()))
seen.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
deadline=time.monotonic()+7200
while time.monotonic()<deadline:
 with contextlib.redirect_stdout(io.StringIO()):out=m.snapshot()
 p=D/'run/attempts_i0.jsonl';rows=[json.loads(l) for l in p.read_text(encoding='utf-8').splitlines() if l.strip()] if p.exists() else []
 print(json.dumps(dict(at=out['at'],phase=out['phase'],completed=len(rows),last_outcome=rows[-1]['outcome'] if rows else None,
  ended=(G/'COORDINATOR_END.json').exists(),failed=(D/'FAILED.json').exists(),display_closed=(G/'DISPLAY_HOLD_CLOSED.json').exists())),flush=True)
 if (G/'COORDINATOR_END.json').exists():break
 time.sleep(30)
