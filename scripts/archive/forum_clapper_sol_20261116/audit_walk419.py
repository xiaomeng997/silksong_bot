from pathlib import Path
from collections import Counter
import datetime,hashlib,json
import numpy as np
B=Path('C:/ssbot/data/m2_play/clapper_plan');A=B/'analysis/walk_rule418_20261113'
read=lambda p:json.loads(p.read_text('utf-8-sig'));sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def stats(v):return dict(ticks=len(v),tick_p50_ms=float(np.percentile(v,50)),tick_p99_ms=float(np.percentile(v,99)),tick_max_ms=max(v),over_16_67ms=sum(x>1000/60 for x in v))

def main():
 binding=read(A/'REPLAY_INPUT_BINDING_V3.json');assert all(sha(Path(p))==h for p,h in binding['files'].items())
 packet=read(A/'SOURCE_PACKET_FIXED.json');S=Path(packet['source_root']);assert all(sha(S/n)==h for n,h in {**packet['raw_runtime_files_sha256'],**packet['support_sha256']}.items())
 norm={n:hashlib.sha256((S/n).read_bytes().replace(b'\r\n',b'\n')).hexdigest() for n in packet['raw_runtime_files_sha256']}
 allowed={'SSBOT_FORUM_CHAIN_BLOCK','SSBOT_FORUM_CHAIN_ORDER','SSBOT_FORUM_CHAIN_SCHEDULE','SSBOT_WORKER_BOOST','SSBOT_WORKER_CPUS'}
 outputs,profiles,wires,events,starts={},{},{},{},{}
 for label,enabled in [('ON',True),('OFF',False)]:
  c=read(A/f'CASE_{label}_V3.json');out=A/f'P_{label}';p=out/'RETURN';final=read(out/'FINALIZED.json');assert final['execution_ok'] and final['cleanup_verified']
  assert c['source']==packet['source'] and sha(Path(c['entry_file']))==c['entry_sha256']
  r=read(p/'RESULT.json');m=read(p/'CONFIGURATION_MANIFEST.json');fixture=read(p/'RECORDED_INPUT_FIXTURE.json')
  assert r['knife_head']==c['source'] and r['exception'] is None and not r['foreign'] and r['p_entry']['formal']
  assert r['synthetic_from']==10012 and not any(z['f']>=10012 for z in r['forced_planner_ticks'])
  assert fixture['through']==fixture['maximum_loaded_frame']==10011 and fixture['released_before_frame']==10012 and fixture['remaining_forced_keys']==0
  assert sha(Path(fixture['path'])/'decisions_i0.chain.jsonl')==fixture['sha256']
  assert all(h==norm.get('brain/ssbot/'+n) for n,h in m['source_sha256'].items())
  assert not m['unknown_environment_switches'] and set(m['unresolved'])<=allowed
  omission=r['knife_brain_dirty'].splitlines();assert all(z.strip().startswith('D brain/tests/') or z.strip() in {'D brain/.python-version','D brain/pyproject.toml','D brain/uv.lock','D brain/uv.toml'} for z in omission)
  switch=m['switches']['SSBOT_FORUM_TWO_WALK_RULE'];assert switch['bindings']=={'ssbot.combat.walk_rule.ENABLED':enabled}
  for k,x in [('SSBOT_FORUM_TWO_PLAN_INLINE',''),('SSBOT_FORUM_CHAIN_B13',True),('SSBOT_FORUM_CHAIN_B13B',True),('SSBOT_FORUM_RUNE_EXIT_FINAL',True),('SSBOT_FORUM_SLAM_NO_NEW_GLIDE',False)]:assert list(m['switches'][k]['bindings'].values())==[x]
  profiles[label]={k:dict(raw=v['raw'],present=v['present'],bindings=v['bindings']) for k,v in m['switches'].items() if k not in {'SSBOT_FORUM_CHAIN_PROBE','SSBOT_FORUM_CHAIN_BATCH','SSBOT_FORUM_CHAIN_BUDGET','SSBOT_FORUM_TWO_WALK_RULE'}}
  rt=r['p_entry']['timing']['runtime'];assert rt['cpu_affinity']==list(range(16)) and rt['priority']==128 and not rt['query_errors'] and not rt['power_throttling']['execution_speed_throttled']
  life=read(p/'WORKER_LIFECYCLE.json');assert life['complete'] and life['ready'] and not life['errors'] and set(life['workers'])=={'field','plan'}
  assert all(z['ready'] and z['closed'] and z['exitcode']==0 for z in life['workers'].values())
  rows=[json.loads(l) for l in (p/'measurement_trace.jsonl').open(encoding='utf-8')];ticks=[z for z in rows if z.get('kind')=='tick'];actions=[z for z in rows if z.get('kind')=='action']
  assert len(ticks)==len(actions)==r['p_entry']['ticks']==59 and [z['f'] for z in ticks]==list(range(10054,10113))
  assert all(z['policy_mask_matches_wire'] and z['policy_flags_match_wire'] and not z['target_already_observed'] for z in actions)
  footer=next(z for z in rows if z.get('kind')=='footer');assert footer['complete'] and footer['overflow']==0 and footer['diagnostics']['complete'] and not footer['diagnostics']['events_overwritten'] and not footer['diagnostics']['callback_errors']
  chain=[json.loads(l) for l in (p/'decisions_i0.chain.jsonl').open(encoding='utf-8')];events[label]=chain
  wires[label]={z['frame']:{k:z[k] for k in ['mask','owner','target']} for z in chain if z['event']=='transport_sent' and 10054<=z.get('frame',-1)<=10112};assert len(wires[label])==59
  start=next(z for z in r['rows'] if z['f']==10012);starts[label]={k:start[k] for k in ['f','hero_x','hero_y','hero_vx','hero_vy','mode','ground','clip']}
  outputs[label]=dict(**stats([z['total_tick_ms'] for z in ticks]),source=c['source'],switch=switch,source_files=len(m['source_sha256']),artifact=str(p),actual_owners=dict(Counter(z['owner'] for z in ticks)),fixture=fixture,seed=r['seed'],operational_unresolved=m['unresolved'],diagnostic_events=footer['diagnostics']['events'],model_hurts_within_timing=[z for z in r['model_hurts'] if 10054<=z['f']<=10112])
 assert profiles['ON']==profiles['OFF'] and starts['ON']==starts['OFF'] and outputs['ON']['seed']==outputs['OFF']['seed']
 on=next(z for z in events['ON'] if z['event']=='transfer_follow_middle' and z['frame']==10062)
 off=next(z for z in events['OFF'] if z['event']=='transfer_follow_middle_blocked' and z['frame']==10062)
 landed=next(z for z in events['ON'] if z['event']=='transfer_follow_landed' and z['frame']==10110)
 assert wires['ON'][10062]==dict(mask=1048576,owner='knife_chain:rune_transfer.middle',target=10064)
 assert wires['OFF'][10062]==dict(mask=2097152,owner='knife_chain:rune_transfer.air',target=10064)
 assert on['land_f']==10110 and off['candidates']==21
 diffs=[dict(frame=f,on=w,off=wires['OFF'][f]) for f,w in wires['ON'].items() if w!=wires['OFF'][f]];assert diffs
 result=dict(at=datetime.datetime.now(datetime.timezone.utc).isoformat(),source=packet['source'],source_and_inputs_unchanged=True,same_source_switch_comparison=True,same_seed=True,same_synthetic_start=starts['ON'],matching_frames_and_other_control_profiles=True,actual_cleanup_verified=True,finite_measurement_valid=True,finite_branch_evidence_accepted=True,formal_timing_completed=True,performance_budget_pass=False,full_scheduling_gate_pass=False,live_released=False,user_live_pause_retained=True,outputs=outputs,actual_wire_differences=diffs,measured_delta_ms={k:outputs['ON'][k]-outputs['OFF'][k] for k in ['tick_p50_ms','tick_p99_ms']},production_evidence=dict(on_acceptance=on,off_rejection_summary={k:v for k,v in off.items() if k!='scanned'},on_model_landing=landed),entry_lifecycle=dict(initial_zero_tick_failure_preserved=str(A/'ENTRY_FAILURE_V1.json'),initial_failure_cleanup=True,measured_entry=str(A/'entry_v3.py'),entry_review=str(A/'ENTRY_REVIEW_V3.json'),fixture_cleared_at=10012,measurement_begins=10054),limitations=['59 frames per arm; descriptive timing only, no full scheduling or live approval.','Synthetic hero since10012, recorded enemies do not react to changed actions.','Recording own sends used only through10011; same pre-synthetic fixture, cleared before timing; no measured forced keys/selection/source gating.','This return window has no walker offset>0 route; offset fix is covered by independent component and actual call-site review, not claimed dynamically exercised here.','Different actions and trajectories after10062; delta is not isolated helper cost.','Both model damage and model landing are not live HP improvement or a win-rate claim.','Original void author pair and failed zero-tick entry preserved; no old run rewritten as a pass.','Five operational keys unresolved in adapter; actual CPU/priority/throttling separately read back.'])
 (A/'ROOT_P_AUDIT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
 print(json.dumps(dict(on={k:v for k,v in outputs['ON'].items() if k in ['ticks','tick_p50_ms','tick_p99_ms','tick_max_ms','over_16_67ms','actual_owners']},off={k:v for k,v in outputs['OFF'].items() if k in ['ticks','tick_p50_ms','tick_p99_ms','tick_max_ms','over_16_67ms','actual_owners']},delta=result['measured_delta_ms'],wire_differences=len(diffs),fixture_cleared_at=10012,model_landed=10110,actual_cleanup=True,game_paused=True),ensure_ascii=False))

if __name__=='__main__':main()
