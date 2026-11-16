from pathlib import Path
import collections, datetime, hashlib, json
import numpy as np

B=Path('C:/ssbot/data/m2_play/clapper_plan');A=B/'analysis/rune_exit411_20261113'
read=lambda p:json.loads(p.read_text('utf-8-sig'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n','utf-8')
def stats(v):return dict(ticks=len(v),tick_p50_ms=float(np.percentile(v,50)),tick_p99_ms=float(np.percentile(v,99)),tick_max_ms=max(v),over_16_67ms=sum(x>1000/60 for x in v))

def main():
 packet=read(A/'SOURCE_PACKET.json');S=Path(packet['source_root']);head=packet['source']
 assert all(sha(S/n)==h for n,h in packet['raw_runtime_files_sha256'].items())
 normalized={n:hashlib.sha256((S/n).read_bytes().replace(b'\r\n',b'\n')).hexdigest() for n in packet['raw_runtime_files_sha256']}
 assert all(sha(Path(n))==h for n,h in read(A/'REPLAY_INPUT_BINDING.json')['files'].items())
 outputs={};wires={}
 allowed_unresolved={'SSBOT_FORUM_CHAIN_BLOCK','SSBOT_FORUM_CHAIN_ORDER','SSBOT_FORUM_CHAIN_SCHEDULE','SSBOT_WORKER_BOOST','SSBOT_WORKER_CPUS'}
 for label,suffix,enabled in [('new','NEW',True),('baseline','BASELINE',False)]:
  final=read(A/('P_'+suffix)/'FINALIZED.json');assert final['execution_ok'] and final['cleanup_verified']
  out={};costs=[];wires[label]={}
  for q in ['E','W']:
   p=A/('P_'+suffix)/q;r=read(p/'RESULT.json');m=read(p/'CONFIGURATION_MANIFEST.json')
   assert r['exception'] is None and not r['foreign'] and r['p_entry']['formal'] and r['knife_head']==head
   assert not m['unknown_environment_switches'] and set(m['unresolved'])<=allowed_unresolved
   # Replay manifests use package-relative source_sha256; live manifests use code.files_sha256.
   assert all(h==normalized.get('brain/ssbot/'+n) for n,h in m['source_sha256'].items())
   switch=m['switches']['SSBOT_FORUM_RUNE_EXIT_FINAL'];assert switch['bindings']=={'ssbot.combat.tactics.clapper_priority.RUNE_EXIT_FINAL':enabled}
   rt=r['p_entry']['timing']['runtime'];assert rt['cpu_affinity']==list(range(16)) and rt['priority']==128 and not rt['power_throttling']['execution_speed_throttled']
   ticks=[];actions={}
   for l in (p/'measurement_trace.jsonl').open(encoding='utf-8'):
    z=json.loads(l)
    if z.get('kind')=='tick':ticks.append(z)
    if z.get('kind')=='action':
     assert z['policy_mask_matches_wire'] and z['policy_flags_match_wire'] and not z['target_already_observed']
     actions[z['f']]={k:z[k] for k in ['mask','owner','target_frame']}
   assert len(ticks)==r['p_entry']['ticks'] and len(actions)==len(ticks)
   vals=[t['total_tick_ms'] for t in ticks];costs+=vals;frames=[t['f'] for t in ticks]
   logs=[json.loads(l) for l in (p/'decisions_i0.jsonl').read_text('utf-8').splitlines() if l.strip()]
   notes=[]
   for row in logs:
    if row['f'] not in actions:continue
    rec=row.get('clapper_rune_exit')
    if rec is not None:
     notes.append(dict(f=row['f'],logged_stance=row.get('stance'),final_stance=rec['stance'],withdraw=rec['withdraw'],wire=actions[row['f']]))
   if enabled:assert notes
   else:assert not notes
   out[q]=dict(**stats(vals),frames=frames,rune_exit_decisions=notes,actual_switch=switch,configuration_unresolved=m['unresolved'],source_files=len(m['source_sha256']))
   wires[label][q]=actions
  outputs[label]=dict(**stats(costs),windows=out)
 assert outputs['new']['ticks']==outputs['baseline']['ticks']==83
 changes={q:[dict(f=f,new=w,baseline=wires['baseline'][q][f]) for f,w in wires['new'][q].items() if w!=wires['baseline'][q][f]] for q in ['E','W']}
 assert all(outputs['new']['windows'][q]['frames']==outputs['baseline']['windows'][q]['frames'] for q in ['E','W'])
 assert changes['E']
 assert any(n['final_stance'] is not None and n['final_stance']['exit'] is not None for n in outputs['new']['windows']['E']['rune_exit_decisions'])
 assert any(n['withdraw'] is not None and n['withdraw']['exit'] is not None for n in outputs['new']['windows']['W']['rune_exit_decisions'])
 out=dict(at=now(),source=head,source_and_inputs_unchanged=True,matching_frame_sets=True,actual_cleanup_verified=True,scoped_engineering_timing_pass=True,full_scheduling_gate_pass=False,live_released=False,
  scope='Two finite E/W contexts, same source/profile with only RUNE_EXIT_FINAL toggled. Actual async plan/field and before_send/sent. Model hero with recorded enemy motion.',
  outputs=outputs,actual_wire_differences=changes,measured_delta_ms={k:outputs['new'][k]-outputs['baseline'][k] for k in ['tick_p50_ms','tick_p99_ms']},
  limitations=['Model evidence, not live avoided HP or full-world enemy reaction.','W includes actual withdrawn-target calculation; chain kept its action on that sampled tick, so successful rejection/withdraw consumption not claimed.','Same first/last frames but differing actions and later trajectories; delta is not isolated helper cost.','Five operational environment keys remain unresolved in this replay adapter as in prior accepted P; runtime CPU/priority/boost separately read back. No unknown switch.','Full scheduling and complete escape-route safety remain unpassed.'])
 put(A/'ROOT_P_AUDIT.json',out)
 sr=read(A/'SOURCE_REVIEW.json');sr.update(at=now(),scoped_engineering_timing_pass=True,full_scheduling_gate_pass=False,P_audit=str(A/'ROOT_P_AUDIT.json'),actual_cleanup_verified=True);put(A/'SOURCE_REVIEW_FINAL.json',sr)
 print(json.dumps(dict(source=head,source_inputs_stable=True,new={k:v for k,v in outputs['new'].items() if k!='windows'},baseline={k:v for k,v in outputs['baseline'].items() if k!='windows'},delta=out['measured_delta_ms'],wire_differences={q:len(v) for q,v in changes.items()},withdraw_calculation_seen=True,actual_cleanup=True),ensure_ascii=False))

if __name__=='__main__':main()
