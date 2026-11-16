from pathlib import Path
import contextlib,importlib.util,io,json,sys,time
B=Path('C:/ssbot/data/m2_play/clapper_plan');G=B/'analysis/w13_50_air_catch429_display_20261114';D=B/'sol/demos'/G.name
if '--ready' in sys.argv:
 end=time.monotonic()+45
 while not all((D/'launch'/n).exists() for n in ['WATCH_READY.json','CAPTURE_READY.json']):
  if (G/'COORDINATOR_END.json').exists() or (D/'FAILED.json').exists() or time.monotonic()>end:break
  time.sleep(2)
else:time.sleep(float(sys.argv[1]) if len(sys.argv)>1 else 0)
spec=importlib.util.spec_from_file_location('live429watch',G/'root_live_watch.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
with contextlib.redirect_stdout(io.StringIO()):out=m.snapshot()
p=D/'run/attempts_i0.jsonl';attempts=[json.loads(l) for l in p.read_text(encoding='utf-8').splitlines() if l.strip()] if p.exists() else []
print(json.dumps(dict(at=out['at'],phase=out['phase'],owned_seen=out['owned_seen'],markers=list(out['markers']),
 completed_records=len(attempts),last_outcome=attempts[-1]['outcome'] if attempts else None,
 last_reason=attempts[-1].get('reason') if attempts else None,
 display_holder_closed=(G/'DISPLAY_HOLD_CLOSED.json').exists()),ensure_ascii=False),flush=True)
