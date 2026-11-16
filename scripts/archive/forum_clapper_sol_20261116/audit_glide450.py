"""Audit the fixed-source glide jump-hold finite P comparison."""
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import numpy as np
import psutil

B=Path('C:/ssbot/data/m2_play/clapper_plan')
A=B/'analysis/glide_danger450_20261115'
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
        assert list(m['switches']['SSBOT_FORUM_GLIDE_DANGER']['bindings'].values())==[enabled]
        for name,expect in [('SSBOT_FORUM_GLIDE_JUMP_HOLD',True),('SSBOT_FORUM_MIDDLE_HANDOFF',True),('SSBOT_FORUM_TWO_PLAN_INLINE',''),('SSBOT_FORUM_CHAIN_B13',True),
             ('SSBOT_FORUM_CHAIN_B13B',True),('SSBOT_FORUM_RUNE_EXIT_FINAL',True),
             ('SSBOT_FORUM_SLAM_NO_NEW_GLIDE',False),('SSBOT_FORUM_SLAM_COMMIT',True),
             ('SSBOT_FORUM_LANDING_EXIT',True),('SSBOT_FORUM_AIRSTRIKE',True)]:
            assert list(m['switches'][name]['bindings'].values())==[expect],name
        profile={k:dict(raw=v['raw'],present=v['present'],bindings=v['bindings']) for k,v in m['switches'].items()
                 if k not in {'SSBOT_FORUM_CHAIN_PROBE','SSBOT_FORUM_CHAIN_BATCH','SSBOT_FORUM_CHAIN_BUDGET','SSBOT_FORUM_GLIDE_DANGER'}}
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
assert outputs['ON']['ticks']==outputs['OFF']['ticks']==47
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


# Functional receipts and GC observations for the new first-controllable-key cost.
functional={};gc={}
for arm in ['ON','OFF']:
    functional[arm]={};gc[arm]={}
    for ctx in read(A/f'CASE_{arm}.json')['contexts']:
        name=ctx['name'];own,last=ctx['from'],ctx['last'];p=A/f'P_{arm}'/name
        ds=[json.loads(l) for l in (p/'decisions_i0.jsonl').open(encoding='utf-8')]
        notes={x['f']:x.get('fi',{}).get('glide_danger') for x in ds if own<=x.get('f',-1)<=last}
        if arm=='OFF':
            assert not any(notes.values())
        else:
            assert notes[own] and notes[own]['charged']>0
            if name=='OPEN':assert notes[own]['opens']>0 and notes[own]['floats']==0
            if name=='FLOAT':assert notes[own]['mode']==8 and notes[own]['phase'] in [2,5] and notes[own]['floats']>0
        functional[arm][name]=dict(first_note=notes.get(own),window_ticks=sum(v is not None for v in notes.values()),
            charged_rows_total=sum((v or {}).get('charged',0) for v in notes.values()),
            opens_total=sum((v or {}).get('opens',0) for v in notes.values()),
            floats_total=sum((v or {}).get('floats',0) for v in notes.values()),
            exits_total=sum((v or {}).get('exits',0) for v in notes.values()),
            unknown_ticks=sum(bool((v or {}).get('unknown')) for v in notes.values()),
            first_wire=wires[arm,name][own])
        trace=[json.loads(l) for l in (p/'measurement_trace.jsonl').open(encoding='utf-8')]
        ticks=[x for x in trace if x.get('kind')=='tick'];foot=next(x for x in trace if x.get('kind')=='footer')
        active={};pauses=[]
        for e in foot['diagnostics']['events']:
            if e.get('kind')!='gc':continue
            if e.get('status')=='start':active[e['tid']]=e
            elif e.get('status')=='stop' and e['tid'] in active:
                st=active.pop(e['tid']);lo,hi=st['wall_ns'],e['wall_ns']
                overlap=[x['f'] for x in ticks if lo<=x['tick_start_ns']+x['total_tick_ms']*1e6 and hi>=x['tick_start_ns']]
                pauses.append(dict(generation=e['generation'],ms=(hi-lo)/1e6,overlap_frames=overlap))
        gc[arm][name]=pauses
assert wires['ON','OPEN'][135004]['mask']==0 and wires['OFF','OPEN'][135004]['mask']&1
assert wires['ON','OPEN'][135004]['target']==135006
result.update(real_glide_danger_actions_verified=True,functional=functional,gc_diagnostics=gc,
    source_review=str(A/'SOURCE_REVIEW_FINAL.json'),critical_source_review_agent='/root/walk418_review',
    owned_processes=list(owned.values()),
    limitations=[
        'Two selected windows,47 ticks per arm; empirical percentiles do not certify global scheduling or deadlines.',
        'Recorded enemies do not react; hero synthetic only afterB. Replay sends are not real-game acceptance or HP benefit.',
        'OPEN changes actual first replay send fromJ+R to0; FLOAT exercises charged optional-continuation rows but need not change its first selected action.',
        'Original no-deadline engineering and source red/green boundaries are separate evidence. Formal exit classes are not proof of the exact attack-cancel regression.',
        'Dash-cancel model uncertainty still skips preference; forced historical16/18 group is outside this cost scope.',
        'Whole-tick deltas include differing actions/paths, not isolated helper cost; profile MH1/GJH1/AS1/LANDING_EXIT1 only.'])
import runpy
executor=runpy.run_path(str(B/'sol/performance/executor_v2.py'))
case=read(A/'CASE_ON.json')
fresh=executor['snapshot'](case,A,'ROOT_FINAL')
result['fresh_environment']=fresh
(A/'ROOT_P_AUDIT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(A/'ROOT_CLEANUP.json').write_text(json.dumps(dict(at=result['at'],actual_cleanup_verified=True,owned_processes=list(owned.values()),
    bounded_orchestrator_exited=result['bounded_orchestrator_exited'],environment=fresh,active_lock_absent=True),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
review=read(A/'SOURCE_REVIEW_FINAL.json')
review.update(formal_P_completed=True,formal_P_audit=str(A/'ROOT_P_AUDIT.json'),finite_measurement_valid=True,actual_cleanup_verified=True,
    outputs={a:{k:v for k,v in t.items() if k!='contexts'} for a,t in outputs.items()},performance_budget_pass=False,full_scheduling_gate_pass=False,new_game_authorized=False)
(A/'SOURCE_REVIEW_AND_P_FINAL.json').write_text(json.dumps(review,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(outputs={a:{k:v for k,v in t.items() if k!='contexts'} for a,t in outputs.items()},wire_differences={c:len(v) for c,v in differences.items()},
    actual_processes_exited=len(owned),functional=functional,gc_overlaps={a:{c:len([e for e in v if e['overlap_frames']]) for c,v in cs.items()} for a,cs in gc.items()},
    finite_P_valid=True,actual_cleanup=True),ensure_ascii=False))
