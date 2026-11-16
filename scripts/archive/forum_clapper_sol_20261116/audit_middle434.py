"""Audit the completed, fixed-source three-window middle-handoff P comparison."""
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import numpy as np
import psutil

B=Path('C:/ssbot/data/m2_play/clapper_plan')
A=B/'analysis/middle_handoff434_20261114'
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
packet=read(A/'SOURCE_PACKET_FIXED.json')
S=Path(packet['source_root'])
assert all(sha(S/n)==h for n,h in {**packet['raw_runtime_files_sha256'],**packet['support_sha256']}.items())
assert all(sha(Path(n))==h for n,h in read(A/'REPLAY_INPUT_BINDING.json')['files'].items())
assert not (B/'sol/performance/ACTIVE.json').exists()
norm={n:hashlib.sha256((S/n).read_bytes().replace(b'\r\n',b'\n')).hexdigest() for n in packet['raw_runtime_files_sha256']}
allowed={'SSBOT_FORUM_CHAIN_BLOCK','SSBOT_FORUM_CHAIN_ORDER','SSBOT_FORUM_CHAIN_SCHEDULE','SSBOT_WORKER_BOOST','SSBOT_WORKER_CPUS'}

def stats(v):
    return dict(ticks=len(v),tick_p50_ms=float(np.percentile(v,50)),tick_p99_ms=float(np.percentile(v,99)),
                tick_max_ms=max(v),over_16_67ms=sum(x>1000/60 for x in v))

def alive(identity):
    try:return abs(psutil.Process(identity['pid']).create_time()-identity['created'])<.01
    except psutil.NoSuchProcess:return False

outputs={};profiles=[];starts={};wires={};all_owners={};owned={};signature_changes=[]
for label,enabled in [('ON',True),('OFF',False)]:
    case=read(A/f'CASE_{label}.json')
    for name in [f'CHECK_{label}',f'P_{label}']:
        final=read(A/name/'FINALIZED.json')
        assert final['execution_ok'] and final['cleanup_verified']
        for ident in [dict(pid=final['pid'],created=final['created']),*final['workers']]:
            assert not alive(ident)
            owned[(ident['pid'],ident['created'])]=ident
    assert sha(Path(case['entry_file']))==case['entry_sha256']
    per_context={};values=[];arm_owners=Counter()
    for ctx in case['contexts']:
        p=A/f'P_{label}'/ctx['name'];r=read(p/'RESULT.json');m=read(p/'CONFIGURATION_MANIFEST.json')
        own,last=ctx['from'],ctx['last'];count=last-own+1
        fixture=read(p/'RECORDED_INPUT_FIXTURE.json')
        assert r['knife_head']==case['source']==packet['source'] and r['exception'] is None and not r['foreign']
        assert r['p_entry']['formal'] and r['p_entry']['timing']['start']==own and r['p_entry']['ticks']==count
        assert r['synthetic_from']==own+1 and not any(v['f']>=own for v in r['forced_planner_ticks'])
        assert fixture['through']==fixture['maximum_loaded_frame']==own-1
        assert fixture['own_controls_from']==fixture['measurement_from']==fixture['released_before_frame']==own
        assert fixture['synthetic_from']==own+1 and fixture['remaining_forced_keys']==0
        assert sha(Path(fixture['path'])/'decisions_i0.chain.jsonl')==fixture['sha256']
        assert all(h==norm['brain/ssbot/'+n] for n,h in m['source_sha256'].items())
        assert not m['unknown_environment_switches'] and set(m['unresolved'])<=allowed
        assert list(m['switches']['SSBOT_FORUM_MIDDLE_HANDOFF']['bindings'].values())==[enabled]
        for name,expect in [('SSBOT_FORUM_TWO_PLAN_INLINE',''),('SSBOT_FORUM_CHAIN_B13',True),
             ('SSBOT_FORUM_CHAIN_B13B',True),('SSBOT_FORUM_RUNE_EXIT_FINAL',True),
             ('SSBOT_FORUM_SLAM_NO_NEW_GLIDE',False),('SSBOT_FORUM_SLAM_COMMIT',True),
             ('SSBOT_FORUM_LANDING_EXIT',True),('SSBOT_FORUM_AIRSTRIKE',True)]:
            assert list(m['switches'][name]['bindings'].values())==[expect],name
        profile={k:dict(raw=v['raw'],present=v['present'],bindings=v['bindings']) for k,v in m['switches'].items()
                 if k not in {'SSBOT_FORUM_CHAIN_PROBE','SSBOT_FORUM_CHAIN_BATCH','SSBOT_FORUM_CHAIN_BUDGET','SSBOT_FORUM_MIDDLE_HANDOFF'}}
        profiles.append(profile)
        rt=r['p_entry']['timing']['runtime']
        assert rt['cpu_affinity']==list(range(16)) and rt['priority']==128 and not rt['query_errors']
        assert not rt['power_throttling']['execution_speed_throttled']
        life=read(p/'WORKER_LIFECYCLE.json')
        assert life['complete'] and life['ready'] and not life['errors'] and set(life['workers'])=={'field','plan'}
        assert all(x['ready'] and x['closed'] and x['exitcode']==0 for x in life['workers'].values())
        trace=[json.loads(l) for l in (p/'measurement_trace.jsonl').open(encoding='utf-8')]
        ticks=[x for x in trace if x.get('kind')=='tick'];actions=[x for x in trace if x.get('kind')=='action']
        assert len(ticks)==len(actions)==count and [x['f'] for x in ticks]==list(range(own,last+1))
        assert all(x['policy_mask_matches_wire'] and x['policy_flags_match_wire'] and not x['target_already_observed'] for x in actions)
        foot=next(x for x in trace if x.get('kind')=='footer')
        assert foot['complete'] and foot['overflow']==0 and foot['diagnostics']['complete']
        assert not foot['diagnostics']['events_overwritten'] and not foot['diagnostics']['callback_errors']
        chain=[json.loads(l) for l in (p/'decisions_i0.chain.jsonl').open(encoding='utf-8')]
        sent={x['frame']:{k:x[k] for k in ['mask','owner','target']} for x in chain
              if x.get('event')=='transport_sent' and own<=x.get('frame',-1)<=last}
        assert list(sorted(sent))==list(range(own,last+1)) and sent[own]['target']==own+2
        wires[label,ctx['name']]=sent
        row=next(x for x in r['rows'] if x['f']==own)
        starts[label,ctx['name']]={k:row[k] for k in ['hero_x','hero_y','hero_vx','hero_vy','mode','ground','clip']}
        before=r['p_entry']['timing']['signatures_before'];after=r['signatures_after']
        changed={k:dict(before=before.get(k),after=v) for k,v in after.items() if v!=before.get(k)}
        if changed:signature_changes.append(dict(arm=label,context=ctx['name'],changes=changed))
        times=[x['total_tick_ms'] for x in ticks];values.extend(times)
        owners=Counter(x['owner'] for x in ticks);arm_owners.update(owners)
        per_context[ctx['name']]=dict(**stats(times),artifact=str(p),seed=r['seed'],own_from=own,synthetic_from=own+1,
            actual_owners=dict(owners),first_wire=sent[own],source_files=len(m['source_sha256']),fixture=fixture,
            first_model_hurt=r['first_model_hurt'],model_hits=r['model_hits'],model_hurt_contacts=len(r['model_hurts']))
    outputs[label]=dict(**stats(values),actual_owners=dict(arm_owners),contexts=per_context)
assert all(p==profiles[0] for p in profiles)
assert not signature_changes,signature_changes
assert outputs['ON']['ticks']==outputs['OFF']['ticks']==185
assert all(starts['ON',c]==starts['OFF',c] for c in outputs['ON']['contexts'])
differences={c:[dict(frame=f,on=v,off=wires['OFF',c][f]) for f,v in wires['ON',c].items()
               if v!=wires['OFF',c][f]] for c in outputs['ON']['contexts']}
result=dict(at=datetime.now(timezone.utc).isoformat(),source=packet['source'],
    source_and_inputs_unchanged=True,same_source_switch_comparison=True,formal_timing_completed=True,
    finite_measurement_valid=True,actual_cleanup_verified=True,actual_owned_processes_exited=len(owned),
    source_files=728,inherited_unchanged_entry_guard_checks=36,own_B_synthetic_Bplus1_verified=True,
    no_measured_forcing=True,no_new_JIT_signatures=True,outputs=outputs,
    wire_differences= differences,default_switch_remains_off=True,live_released=False,
    performance_budget_pass=False,full_scheduling_gate_pass=False,
    limitations=['Three chosen windows, 185 frames per arm, not a full scheduling or live win-rate result.',
      'Recorded enemies do not react to changed hero actions; model hits/hurts are not actual HP.',
      'ep0 remains unhandled; ep22 catch does not establish prevented damage; post-hit model hurt unreliable.',
      'Actions and ownership differ between arms: p50/p99 delta is not isolated handoff helper cost.',
      'Profile AS1/LANDING_EXIT1, same source; no claim about all other switch combinations.'])
orch=read(A/'ORCHESTRATION.json')
assert orch['complete'] and orch['error'] is None and not alive(orch)
assert all(z['returncode']==0 for z in orch['steps'])
result['bounded_orchestrator_exited']=dict(pid=orch['pid'],created=orch['created'])
result['resource_gate_all_contexts_clear']=True
for arm in ['ON','OFF']:
    for c in outputs[arm]['contexts']:
        assert not read(A/f'P_{arm}'/f'RESOURCE_{c}.json')['blockers']
for c,actor in [('E0',335470),('E22',2501982),('E30',2712110)]:
    own=outputs['ON']['contexts'][c]['own_from']
    for arm in ['ON','OFF']:
        rows=[json.loads(l) for l in (A/f'P_{arm}'/c/'decisions_i0.chain.jsonl').open(encoding='utf-8')]
        ev=[x for x in rows if x.get('event')=='middle_handoff_ready' and x.get('frame')==own]
        assert (len(ev)==1 and ev[0]['caster']==actor) if arm=='ON' else not ev
assert not differences['E0'] and not differences['E30']
assert differences['E22'] and wires['ON','E22'][71299]['owner']=='slam'
assert wires['OFF','E22'][71299]['owner']=='plan'
assert any(h['target']==2501988 for h in outputs['ON']['contexts']['E22']['model_hits'])
result['completion_and_actual_handoff_actions_verified']=True

put=A/'ROOT_P_AUDIT.json';put.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:{f:v for f,v in out.items() if f!='contexts'} for k,out in outputs.items()},ensure_ascii=False))
print(json.dumps(dict(wire_differences={k:len(v) for k,v in differences.items()},actual_processes_exited=len(owned),
    model_hits={arm:{c:len(x['model_hits']) for c,x in out['contexts'].items()} for arm,out in outputs.items()})))
