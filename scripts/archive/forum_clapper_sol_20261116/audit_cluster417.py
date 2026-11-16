from pathlib import Path
from collections import Counter
import datetime,hashlib,json
import numpy as np

B=Path('C:/ssbot/data/m2_play/clapper_plan');A=B/'analysis/cluster_back416_20261113'
read=lambda p:json.loads(p.read_text('utf-8-sig'));sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def stats(v):return dict(ticks=len(v),tick_p50_ms=float(np.percentile(v,50)),tick_p99_ms=float(np.percentile(v,99)),tick_max_ms=max(v),over_16_67ms=sum(x>1000/60 for x in v))

def main():
 assert all(sha(Path(p))==h for p,h in read(A/'REPLAY_INPUT_BINDING.json')['files'].items())
 outputs,profiles,actions,plans={},{},{},{}
 allowed={'SSBOT_FORUM_CHAIN_BLOCK','SSBOT_FORUM_CHAIN_ORDER','SSBOT_FORUM_CHAIN_SCHEDULE','SSBOT_WORKER_BOOST','SSBOT_WORKER_CPUS'}
 for label in ['NEW','BASELINE']:
  case=read(A/f'CASE_{label}.json');out=A/f'P_{label}';p=out/'BACK';final=read(out/'FINALIZED.json');assert final['execution_ok'] and final['cleanup_verified']
  packet=read(Path(case['source_packet_file']));source=Path(case['source_root'])
  assert sha(Path(case['source_packet_file']))==case['source_packet_sha256']
  assert all(sha(source/n)==h for n,h in {**packet['raw_runtime_files_sha256'],**packet['support_sha256']}.items())
  norm={n:hashlib.sha256((source/n).read_bytes().replace(b'\r\n',b'\n')).hexdigest() for n in packet['raw_runtime_files_sha256']}
  r=read(p/'RESULT.json');m=read(p/'CONFIGURATION_MANIFEST.json')
  assert r['knife_head']==case['source'] and r['exception'] is None and not r['foreign'] and r['p_entry']['formal'] and r['synthetic_from']==9484
  assert not any(z['f']>=9484 for z in r['forced_planner_ticks'])
  assert all(h==norm.get('brain/ssbot/'+n) for n,h in m['source_sha256'].items())
  assert not m['unknown_environment_switches'] and set(m['unresolved'])<=allowed
  omissions=r['knife_brain_dirty'].splitlines()
  assert all(z.strip().startswith('D brain/tests/') or z.strip() in {'D brain/.python-version','D brain/pyproject.toml','D brain/uv.lock','D brain/uv.toml'} for z in omissions)
  profiles[label]={k:dict(raw=v['raw'],present=v['present'],bindings={n:x.replace(str(source),'<SOURCE>') if isinstance(x,str) else x for n,x in v['bindings'].items()}) for k,v in m['switches'].items() if k not in {'SSBOT_FORUM_CHAIN_PROBE','SSBOT_FORUM_CHAIN_BATCH','SSBOT_FORUM_CHAIN_BUDGET'}}
  for k,x in [('SSBOT_FORUM_TWO_PLAN_INLINE',''),('SSBOT_FORUM_CHAIN_B13',True),('SSBOT_FORUM_CHAIN_B13B',True),('SSBOT_FORUM_RUNE_EXIT_FINAL',True),('SSBOT_FORUM_SLAM_NO_NEW_GLIDE',False)]:assert list(m['switches'][k]['bindings'].values())==[x]
  rt=r['p_entry']['timing']['runtime'];assert rt['cpu_affinity']==list(range(16)) and rt['priority']==128 and not rt['query_errors'] and not rt['power_throttling']['execution_speed_throttled']
  life=read(p/'WORKER_LIFECYCLE.json');assert life['complete'] and life['ready'] and not life['errors']
  assert set(life['workers'])=={'field','plan'}
  assert all(z['ready'] and z['closed'] and z['exitcode']==0 for z in life['workers'].values())
  trace=[json.loads(l) for l in (p/'measurement_trace.jsonl').open(encoding='utf-8')];ticks=[z for z in trace if z.get('kind')=='tick'];sent=[z for z in trace if z.get('kind')=='action']
  assert len(ticks)==len(sent)==r['p_entry']['ticks']==17 and [z['f'] for z in ticks]==list(range(9486,9503))
  assert all(z['policy_mask_matches_wire'] and z['policy_flags_match_wire'] and not z['target_already_observed'] for z in sent)
  chain=[json.loads(l) for l in (p/'decisions_i0.chain.jsonl').open(encoding='utf-8')]
  actions[label]={z['frame']:z for z in chain if z['event']=='transport_sent' and 9486<=z.get('frame',-1)<=9502}
  decisions=[json.loads(l) for l in (p/'decisions_i0.jsonl').open(encoding='utf-8')]
  plans[label]={z['f']:dict(target=z.get('tgt'),scene=z.get('clapper_scene'),back=z.get('clapper_back'),plan=z.get('clapper_plan')) for z in decisions if 9486<=z.get('f',-1)<=9502}
  assert len(actions[label])==17
  outputs[label]=dict(**stats([z['total_tick_ms'] for z in ticks]),source=case['source'],artifact=str(p),actual_owners=dict(Counter(z['owner'] for z in ticks)),source_files=len(m['source_sha256']),operational_unresolved=m['unresolved'],model_hurts=r['model_hurts'])
 assert profiles['NEW']==profiles['BASELINE']
 active=[f for f,z in plans['NEW'].items() if (z['plan'] or {}).get('phase')=='attack_back_other']
 arrived=[f for f,z in plans['NEW'].items() if (z['plan'] or {}).get('status')=='complete' and (z['plan'] or {}).get('reason')=='in_reach']
 presses=[z for f,z in actions['NEW'].items() if z['owner']=='two:idle' and z['mask']&2]
 assert active and arrived and presses and any(z['frame']>=min(arrived) and z['target']==z['frame']+2 for z in presses)
 assert any((z['plan'] or {}).get('reason')=='other_move' for z in plans['BASELINE'].values())
 assert all(z['back'] is None for z in plans['NEW'].values())
 differences=[dict(frame=f,new={k:z[k] for k in ['mask','owner','target']},baseline={k:actions['BASELINE'][f][k] for k in ['mask','owner','target']}) for f,z in actions['NEW'].items() if any(z[k]!=actions['BASELINE'][f][k] for k in ['mask','owner','target'])]
 assert differences
 result=dict(at=datetime.datetime.now(datetime.timezone.utc).isoformat(),source=outputs['NEW']['source'],source_and_inputs_unchanged=True,matching_frames_and_control_profiles=True,actual_cleanup_verified=True,finite_measurement_valid=True,finite_branch_evidence_accepted=True,formal_timing_completed=True,performance_budget_pass=False,full_scheduling_gate_pass=False,live_released=False,user_live_pause_retained=True,outputs=outputs,actual_wire_differences=differences,production_evidence=dict(active_return_frames=active,in_reach_frames=arrived,side_slash_sends=presses,new_public_middle_return_absent=True,baseline_other_move_invalidation_observed=True),measured_delta_ms={k:outputs['NEW'][k]-outputs['BASELINE'][k] for k in ['tick_p50_ms','tick_p99_ms']},limitations=['17 frames per arm, finite descriptive timing only; not full scheduling or live performance approval.','Synthetic hero since9484, recorded enemies do not respond to changed actions. No forced keys or controller input patch from9484.','Side slash was really sent to model input, not proof of live accepted hit; harness does not score side-slash damage.','Actions/trajectories differ; measured delta is not isolated helper overhead.','Five operational keys unresolved by adapter; actual runtime CPU/priority/throttling separately verified.','#415 ground fallback cost remains an existing limitation, not remeasured or fixed by this package.'])
 (A/'ROOT_P_AUDIT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
 print(json.dumps(dict(outputs=outputs,delta=result['measured_delta_ms'],arrived=arrived,press_frames=[z['frame'] for z in presses],wire_differences=len(differences),cleanup=True,game_paused=True),ensure_ascii=False))

if __name__=='__main__':main()
