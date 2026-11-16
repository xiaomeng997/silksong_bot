"""Audit actual completed finite P, source/input/config/wire/lifecycle binding."""
from pathlib import Path
from collections import Counter
import datetime,hashlib,json
import numpy as np

B=Path('C:/ssbot/data/m2_play/clapper_plan');A=B/'analysis/landing_exit423_20261114'
read=lambda p:json.loads(p.read_text('utf-8-sig'));sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def stats(v):return dict(ticks=len(v),tick_p50_ms=float(np.percentile(v,50)),tick_p99_ms=float(np.percentile(v,99)),tick_max_ms=max(v),over_16_67ms=sum(x>1000/60 for x in v))

binding=read(A/'REPLAY_INPUT_BINDING.json');assert all(sha(Path(p))==h for p,h in binding['files'].items())
packet=read(A/'SOURCE_PACKET_FIXED.json');S=Path(packet['source_root']);assert all(sha(S/n)==h for n,h in {**packet['raw_runtime_files_sha256'],**packet['support_sha256']}.items())
norm={n:hashlib.sha256((S/n).read_bytes().replace(b'\r\n',b'\n')).hexdigest() for n in packet['raw_runtime_files_sha256']}
allowed={'SSBOT_FORUM_CHAIN_BLOCK','SSBOT_FORUM_CHAIN_ORDER','SSBOT_FORUM_CHAIN_SCHEDULE','SSBOT_WORKER_BOOST','SSBOT_WORKER_CPUS'}
outputs,profiles,wires,events,starts,decisions={},{},{},{},{},{}
for label,enabled in [('ON',True),('OFF',False)]:
 c=read(A/f'CASE_{label}.json');out=A/f'P_{label}';p=out/'EXIT';final=read(out/'FINALIZED.json');assert final['execution_ok'] and final['cleanup_verified']
 check=read(A/f'CHECK_{label}'/'FINALIZED.json');assert check['execution_ok'] and check['cleanup_verified']
 assert c['source']==packet['source'] and sha(Path(c['entry_file']))==c['entry_sha256']
 r=read(p/'RESULT.json');m=read(p/'CONFIGURATION_MANIFEST.json');fixture=read(p/'RECORDED_INPUT_FIXTURE.json')
 assert r['knife_head']==c['source'] and r['exception'] is None and not r['foreign'] and r['p_entry']['formal']
 assert r['synthetic_from']==42144 and r['seed']==428636 and not any(z['f']>=42144 for z in r['forced_planner_ticks'])
 assert fixture['through']==fixture['maximum_loaded_frame']==42143 and fixture['released_before_frame']==42144 and fixture['remaining_forced_keys']==0
 assert sha(Path(fixture['path'])/'decisions_i0.chain.jsonl')==fixture['sha256']
 assert all(h==norm.get('brain/ssbot/'+n) for n,h in m['source_sha256'].items())
 assert not m['unknown_environment_switches'] and set(m['unresolved'])<=allowed
 omission=r['knife_brain_dirty'].splitlines();assert all(z.strip().startswith('D brain/tests/') or z.strip() in {'D brain/.python-version','D brain/pyproject.toml','D brain/uv.lock','D brain/uv.toml'} for z in omission)
 switch=m['switches']['SSBOT_FORUM_LANDING_EXIT'];assert switch['bindings']=={'ssbot.combat.tactics.clapper_priority.LANDING_EXIT':enabled}
 for k,x in [('SSBOT_FORUM_TWO_PLAN_INLINE',''),('SSBOT_FORUM_CHAIN_B13',True),('SSBOT_FORUM_CHAIN_B13B',True),('SSBOT_FORUM_RUNE_EXIT_FINAL',True),('SSBOT_FORUM_SLAM_NO_NEW_GLIDE',False)]:assert list(m['switches'][k]['bindings'].values())==[x]
 profiles[label]={k:dict(raw=v['raw'],present=v['present'],bindings=v['bindings']) for k,v in m['switches'].items() if k not in {'SSBOT_FORUM_CHAIN_PROBE','SSBOT_FORUM_CHAIN_BATCH','SSBOT_FORUM_CHAIN_BUDGET','SSBOT_FORUM_LANDING_EXIT'}}
 rt=r['p_entry']['timing']['runtime'];assert rt['cpu_affinity']==list(range(16)) and rt['priority']==128 and not rt['query_errors'] and not rt['power_throttling']['execution_speed_throttled']
 life=read(p/'WORKER_LIFECYCLE.json');assert life['complete'] and life['ready'] and not life['errors'] and set(life['workers'])=={'field','plan'}
 assert all(z['ready'] and z['closed'] and z['exitcode']==0 for z in life['workers'].values())
 rows=[json.loads(l) for l in (p/'measurement_trace.jsonl').open(encoding='utf-8')];ticks=[z for z in rows if z.get('kind')=='tick'];actions=[z for z in rows if z.get('kind')=='action']
 assert len(ticks)==len(actions)==r['p_entry']['ticks']==77 and [z['f'] for z in ticks]==list(range(42145,42222))
 assert all(z['policy_mask_matches_wire'] and z['policy_flags_match_wire'] and not z['target_already_observed'] for z in actions)
 footer=next(z for z in rows if z.get('kind')=='footer');assert footer['complete'] and footer['overflow']==0 and footer['diagnostics']['complete'] and not footer['diagnostics']['events_overwritten'] and not footer['diagnostics']['callback_errors']
 chain=[json.loads(l) for l in (p/'decisions_i0.chain.jsonl').open(encoding='utf-8')];events[label]=chain
 wires[label]={z['frame']:{k:z[k] for k in ['mask','owner','target']} for z in chain if z['event']=='transport_sent' and 42145<=z.get('frame',-1)<=42221};assert len(wires[label])==77
 start=next(z for z in r['rows'] if z['f']==42144);starts[label]={k:start[k] for k in ['f','hero_x','hero_y','hero_vx','hero_vy','mode','ground','clip']}
 decisions[label]={z['f']:z for z in [json.loads(l) for l in (p/'decisions_i0.jsonl').open(encoding='utf-8')] if 42145<=z.get('f',-1)<=42221}
 outputs[label]=dict(**stats([z['total_tick_ms'] for z in ticks]),source=c['source'],switch=switch,source_files=len(m['source_sha256']),artifact=str(p),actual_owners=dict(Counter(z['owner'] for z in ticks)),fixture=fixture,seed=r['seed'],operational_unresolved=m['unresolved'],diagnostic_events=footer['diagnostics']['events'],model_hurts_within_timing=[z for z in r['model_hurts'] if 42145<=z['f']<=42221],model_hits_within_timing=[z for z in r['model_hits'] if 42145<=z['f']<=42221])
assert profiles['ON']==profiles['OFF'] and starts['ON']==starts['OFF']
assert wires['ON'][42145]==dict(mask=2097152,owner='plan',target=42147)
assert wires['OFF'][42145]==dict(mask=0,owner='plan',target=42147)
on=decisions['ON'][42145];off=decisions['OFF'][42145]
assert on['tgt']==off['tgt']==1577066 and 'landing exit' in on['goal_why']
assert abs(on['stance']-34.89)<.02 and abs(off['stance']-32.48)<.02
exit_frames=[f for f,z in decisions['ON'].items() if ((z.get('clapper_landing_exit') or {}).get('stance') or {}).get('exit') is not None]
unknown_frames=[f for f,z in decisions['ON'].items() if (z.get('clapper_landing_exit') or {}).get('unknown')]
targets={k:sorted({z['tgt'] for z in v.values()}) for k,v in decisions.items()};assert targets['ON']==targets['OFF']==[1577066]
diffs=[dict(frame=f,on=z,off=wires['OFF'][f]) for f,z in wires['ON'].items() if z!=wires['OFF'][f]]
result=dict(at=datetime.datetime.now(datetime.timezone.utc).isoformat(),source=packet['source'],source_and_inputs_unchanged=True,same_source_switch_comparison=True,same_seed=True,same_synthetic_start=starts['ON'],matching_frames_and_other_control_profiles=True,actual_cleanup_verified=True,finite_measurement_valid=True,finite_branch_evidence_accepted=True,formal_timing_completed=True,performance_budget_pass=False,full_scheduling_gate_pass=False,live_released=False,default_switch_remains_off=True,user_live_pause_retained=True,outputs=outputs,actual_wire_differences=diffs,measured_delta_ms={k:outputs['ON'][k]-outputs['OFF'][k] for k in ['tick_p50_ms','tick_p99_ms']},production_evidence=dict(first_branch_frame=42145,first_target_frame=42147,on_stance=on['stance'],off_stance=off['stance'],exit_frames=exit_frames,unknown_frames=unknown_frames,target_ids=targets),entry_lifecycle=dict(measured_entry=str(A/'entry_v3.py'),unchanged_entry_review=str(B/'analysis/walk_rule418_20261113/ENTRY_REVIEW_V3.json'),fixture_cleared_at=42144,measurement_begins=42145,preparation_metadata_error=str(A/'PREPARATION_NOTE.json'),no_runtime_failure=True),limitations=['77frames per arm descriptive timing only; no full scheduling or live approval.','Synthetic hero from42144; recorded enemies do not react to changed actions.','Own recording sends only through42143, fixture cleared before timing; no measured forcing/source gating.','Different actions and owner trajectories: delta is not isolated helper cost.','Model hurts/hits are not live HP or win-rate evidence.','Known open/no-wall-correction domain only; unknown inputs skip; active chain/waypoint/entry and route-under-landing not solved.','Five operational keys unresolved; actual CPU/priority/throttling independently read.'])
(A/'ROOT_P_AUDIT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
print(json.dumps(dict(on={k:v for k,v in outputs['ON'].items() if k in ['ticks','tick_p50_ms','tick_p99_ms','tick_max_ms','over_16_67ms','actual_owners']},off={k:v for k,v in outputs['OFF'].items() if k in ['ticks','tick_p50_ms','tick_p99_ms','tick_max_ms','over_16_67ms','actual_owners']},delta=result['measured_delta_ms'],wire_differences=len(diffs),exit_frames=len(exit_frames),unknown_frames=unknown_frames,model_hurts={k:len(v['model_hurts_within_timing']) for k,v in outputs.items()},actual_cleanup=True,game_paused=True),ensure_ascii=False))
