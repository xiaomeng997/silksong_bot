from pathlib import Path
import json
B=Path('C:/ssbot/data/m2_play/clapper_plan')
for group,names in [('l1_320',['a4ref_cs','a4skip','n1late','n1lateoff','n1p99','n1offp99','n1late_rt','n1ref_rt']),('l1_319',['a4ref','a4skip','n1late','n1p99','n1offp99'])]:
 for name in names:
  p=B/'opus/review179'/group/name/'RESULT.json'
  if not p.exists(): print('MISSING',str(p));continue
  r=json.loads(p.read_text(encoding='utf-8-sig'))
  print(json.dumps(dict(name=group+'/'+name,keys=list(r) if name=='a4ref_cs' else None,head=r.get('knife_head'),dirty=r.get('knife_brain_dirty'),synthetic_from=r.get('synthetic_from'),rows_info={k:(len(v) if isinstance(v,list) else type(v).__name__) for k,v in r.items() if isinstance(v,list)},hits=r.get('model_hits'),hurts=r.get('model_hurts'),notes=r.get('notes'),tool=r.get('tool'),trial=r.get('trial')),ensure_ascii=False))
print('recordfiles',[(str(p),p.stat().st_size) for p in (B/'sol/demos/w13_observe_bait_20261106T055356Z/run/rec').glob('*/TRAIN/*/*')][:18])
