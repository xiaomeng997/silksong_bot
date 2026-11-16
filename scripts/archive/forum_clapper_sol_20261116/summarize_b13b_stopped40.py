"""Finalize source/configuration, descriptive costs and wire actions of observed exposure."""
from pathlib import Path
import collections,datetime,hashlib,json,psutil
import numpy as np
B=Path('C:/ssbot/data/m2_play/clapper_plan');G=B/'analysis/w13_50_b13b404_20261113';D=B/'sol/demos'/G.name;A=B/'analysis/b13b_402_20261113';S=A/'source'
read=lambda p:json.loads(Path(p).read_text(encoding='utf-8-sig'))
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()
def put(p,x):
 with Path(p).open('x',encoding='utf-8') as f:json.dump(x,f,ensure_ascii=False,indent=2);f.write('\n')
def main():
 me=psutil.Process();me.cpu_affinity(list(range(24,32)));me.nice(psutil.IDLE_PRIORITY_CLASS)
 packet=read(A/'SOURCE_PACKET.json');contract=read(D/'contract.json');result=read(G/'ROOT_PARTIAL_RESULT.json')
 assert all(sha(S/n)==h for n,h in packet['raw_runtime_files_sha256'].items())
 assert all(sha(p)==h for p,h in contract['prerequisites'].items())
 versions=[];rss=[]
 for ep in range(40):
  m=read(D/f'run/measurement_manifest_i0_e{ep}.json')
  assert m['configuration_complete'] and not m['unknown_environment_switches'] and not m['unresolved']
  assert m['code']['head_revision']==contract['source']
  actual=m['code']['files_sha256'];expected=packet['raw_runtime_files_sha256']
  assert all(n in expected and expected[n]==h for n,h in actual.items()),('source snapshot mismatch',ep)
  for key,binding,value,raw in [('SSBOT_FORUM_CHAIN_B13','ssbot.combat.knife_chain_transfer.B13',True,'1'),('SSBOT_FORUM_CHAIN_B13B','ssbot.combat.knife_chain_transfer.B13B',True,'1'),('SSBOT_FORUM_SLAM_NO_NEW_GLIDE','ssbot.combat.forum_planner.SLAM_NO_NEW_GLIDE',False,'0')]:
   sw=m['switches'][key];assert sw['raw']==raw and sw['bindings']=={binding:value}
  rt=m['runtime_before'];assert rt['cpu_affinity']==list(range(16)) and rt['priority']==128 and rt['numba_threads']==4
  assert m['seed']==contract['seed'] or m['seed']==read(G/'CONTINUOUS_PLAN.json')['seeds'][ep]
  rss.append(dict(bout=ep+1,before=rt['rss'],after=m['runtime_after'].get('rss')))
  versions.append(dict(bout=ep+1,source=m['code']['head_revision'],files_verified=len(actual),configuration_complete=True,actual_B13=True,actual_B13B=True,extra_no_new_glide=False))
 put(G/'ACTUAL_VERSION_AUDIT.json',dict(at=now(),source=contract['source'],exposed_bouts=40,mixed_source=False,runtime_files_unchanged=len(expected),prerequisites_unchanged=len(contract['prerequisites']),all_runtime_bindings_verified=True,rows=versions,RSS=rss))
 notes={};selected=set()
 with (D/'run/decisions_i0.chain.jsonl').open('rb') as f:
  for line in f:
   if line.startswith((b'{"event":"transfer_b13_guard"',b'{"event":"transfer_b13b_sprint_jump"')):
    x=json.loads(line);notes.setdefault((x['episode'],x['frame']),[]).append(x)
   elif line.startswith(b'{"event":"b2_selected"'):
    x=json.loads(line);selected.add((x['episode'],x['frame']))
 counters=collections.Counter();wire=collections.Counter();owners=collections.defaultdict(list);age=[];ticks=0
 for ep,r in enumerate(result['rows']):
  with (D/f'run/measurement_i0_e{ep}.jsonl').open(encoding='utf-8') as f:
   for line in f:
    x=json.loads(line);fr=x.get('f');key=(ep,fr)
    if x.get('kind')=='action' and key in notes:
     for n in notes[key]:
      label=n['event']+':'+n['kind'];counters[label]+=1
      if key in selected and x.get('owner')=='chain' and x['mask']==n['mask']:wire[label]+=1
    if ep<39 and x.get('kind')=='tick' and isinstance(fr,int) and r['wake_f']<=fr<=r['end_f'] and not x.get('error'):
     ticks+=1;owners[x.get('owner') or 'none'].append(x['total_tick_ms'])
     if x.get('recv_ns') is not None:age.append((x['tick_start_ns']-x['recv_ns'])/1e6)
 costs={k:dict(n=len(v),p50_ms=float(np.percentile(v,50)),p99_ms=float(np.percentile(v,99)),max_ms=max(v),over_frame=sum(x>1000/60 for x in v)) for k,v in owners.items()}
 allcost=[v for vs in owners.values() for v in vs]
 events=dict(at=now(),source=contract['source'],scope='39 complete bouts costs, 40 observed bouts wire events; model/counterfactual saved HP not inferred.',guard_proposals=dict(counters),selected_matching_actual_chain_wire=dict(wire),
  completed39_tick_cost_by_actual_owner=costs,total_ticks=ticks,total_tick_p50_ms=float(np.percentile(allcost,50)),total_tick_p99_ms=float(np.percentile(allcost,99)),
  before_tick_STATE_age_ms=dict(p50=float(np.percentile(age,50)),p99=float(np.percentile(age,99)),max=max(age)),
  limitations=['Tick cost excludes wait before tick_start; GC68ms before tick123311 appears in STATE age, not its13ms tick cost.','Wire sends and selected proposals do not establish hero action success, protection or saved HP.','The batch remains stopped at40; no full50 statistics.'])
 put(G/'EVENT_SUMMARY.json',events)
 print(json.dumps(dict(versions=40,mixed=False,ticks=ticks,guard_proposals=dict(counters),actual_chain_wire=dict(wire),tick_p50=events['total_tick_p50_ms'],tick_p99=events['total_tick_p99_ms'],rss_start=rss[0]['before'],rss_end=rss[-1]['after']),ensure_ascii=False))

if __name__=='__main__':main()
