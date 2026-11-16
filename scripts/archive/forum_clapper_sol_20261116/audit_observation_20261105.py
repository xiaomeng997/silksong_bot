"""Audit one finished observation, retaining the unchanged mortality audit separately."""
from pathlib import Path
from types import SimpleNamespace
import sys,json,datetime,os,shutil,hashlib,collections,psutil
B=Path('C:/ssbot/data/m2_play/clapper_plan');A=B/'analysis/w13_observe_bait_20261106T055356Z';T=B/'sol/demos/w13_observe_bait_20261106T055356Z'
D=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot');sys.path.insert(0,str(D/'brain'));sys.dont_write_bytecode=True
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def put(p,d):
    assert not p.exists(),str(p)
    p.write_text(json.dumps(d,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
def status(d):
    p=B/'sol/STATUS.observation_audit.tmp';p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(p,B/'sol/STATUS.json')
me=psutil.Process();me.cpu_affinity(list(range(24,32)));me.nice(psutil.IDLE_PRIORITY_CLASS)
st=read(B/'sol/STATUS.json');assert not st['live_or_budget_running'] and not st.get('own_offline_jobs')
st.update(at=now(),phase='ONE_OBSERVATION_OFFLINE_AUDIT',own_offline_jobs=[dict(pid=me.pid,created=me.create_time(),phase='read finished raw only')]);status(st)
try:
    from ssbot.tools.forum_aa_v2 import verify_episode,cheat_scan
    from ssbot.tools.forum_measure_audit import audit_window
    from ssbot.train.forum_measure_window import MeasurementWindow
    from ssbot.train.measurement import validate_trace
    from ssbot.train.aa_v2 import runtime_errors
    from ssbot.record.recorder import RecordingReader
    from ssbot.record import formats
    run=T/'run';attempt=json.loads((run/'attempts_i0.jsonl').read_text().splitlines()[0]);m=attempt['measurement']
    v=A/'normal_mortality_audit';v.mkdir();shutil.copy2(run/'attempts_i0.jsonl',v/'attempts_i0.jsonl')
    ordinary=verify_episode(v,0,production=False,context={'observation_profile':True,'scope':'Unchanged normal mortality audit retained; not survival acceptance'})
    reader=RecordingReader(attempt['recording']);states=[]
    w=MeasurementWindow(SimpleNamespace(wake_frame=attempt['f_wake']),wave=13,expected_targets=2,game_limit=45,protocol_version=2,observe_lethal=True)
    for _,received,_,flags,_,payload in reader.records('state'):
        f=formats.peek(payload,('f',),flags).get('f')
        if not isinstance(f,int) or f<attempt['f_wake']-1:continue
        if f>attempt['f_end']+2:break
        s=formats.peek(payload,('f','fc','dt','hero','ents','ev','room','game','act'),flags);states.append(s)
        if f<=attempt['f_end']:w.observe(s,received)
    window=w.snapshot();audit=audit_window(states,window,attempt)
    mismatch={k:[m['window'].get(k),window.get(k)] for k in ('wake_f','end_f','T','target_ids','tail_end_f','tail_end_reason','lethal_vetoes') if m['window'].get(k)!=window.get(k)}
    manifest=read(Path(m['manifest']));errors=runtime_errors(manifest);trace=validate_trace(Path(m['path']))
    cheat,unloaded=cheat_scan((s for s in states if window['wake_f']<=s['f']<=window['tail_end_f']),audit['metrics'])
    if mismatch:errors.append('observation online/offline mismatch')
    if cheat:errors.append(cheat)
    if not audit['complete'] or not trace['complete'] or not ordinary['continuity']['ok']:errors.append('incomplete observation/raw/trace')
    if not m['configuration_complete'] or m['unresolved'] or m['overflow']:errors.append('configuration/overflow')
    verification=dict(at=now(),complete=not errors,errors=errors,scope='protected one-bout behavior observation only; not survival/no-hit acceptance',normal_audit_errors=ordinary['errors'],observation_window=window,window_mismatch=mismatch,observation_audit=audit,trace=trace,continuity=ordinary['continuity'],configuration_complete=m['configuration_complete'],unresolved=m['unresolved'],overflow=m['overflow'],normal_no_cheat_error=cheat,real_quit_unloaded_frames=unloaded)
    put(A/'ROOT_OBSERVATION_VERIFICATION.json',verification)
    ds=[json.loads(l) for l in (run/'decisions_i0.jsonl').read_text().splitlines() if l]
    byf={s['f']:s for s in states};events=[];seen=set()
    for s in states:
        for e in s.get('ev') or []:
            key=json.dumps(e,sort_keys=True)
            if key not in seen:seen.add(key);events.append(dict(record_f=s['f'],event=e))
    put(A/'ROOT_RAW_EVENTS.json',events)
    def pos(p):
        if isinstance(p,dict):return p.get('x'),p.get('y')
        return tuple(p[:2]) if isinstance(p,(list,tuple)) else (None,None)
    def snap(f):
        s=byf.get(f) or {};h=s.get('hero') or {};es=[]
        for e in s.get('ents') or []:
            if e.get('type_key')=='Song Heavy Sentry':es.append({k:e.get(k) for k in ('id','iid','pos','hp','fsms','vel')})
        return dict(f=f,fc=s.get('fc'),hero={k:h.get(k) for k in ('pos','vel','health','cstate','can','input','atk')},enemies=es)
    groups={}
    for d in ds:
        c=d.get('clapper_cluster')
        if not c:continue
        key=json.dumps(c['move'])
        if key not in groups:groups[key]=dict(start=d['f'],last=d['f'],route=c,first=snap(d['f']),transitions=[],rows=[])
        g=groups[key];g['last']=d['f'];g['rows'].append(dict(f=d['f'],mask=d.get('mask'),tgt=d.get('tgt'),entry=d.get('entry_attack'),plan=d.get('plan'),goal=d.get('goal'),end=d.get('clapper_cluster_end')))
        if not g['transitions'] or g['transitions'][-1]['phase']!=c['phase']:g['transitions'].append(dict(phase=c['phase'],f=d['f'],route=c,snapshot=snap(d['f'])))
    damages=[e for e in events if e['event'].get('k') in ('hp','damage','catastrophe','would_die','hero_dead','die')]
    clusters=[]
    for g in groups.values():
        g['last_snapshot']=snap(g['last']);g['phase_counts']=dict(collections.Counter('return' if 'return' in (r.get('goal') or '') else 'other' for r in g['rows']))
        # Keep all actual decisions for independent causal reading; no predicted hit is called an actual hit.
        clusters.append(g)
    result=dict(at=now(),source=attempt['code_rev'],seed=attempt['seed'],outcome=attempt['outcome'],protected_observation=True,T=window['T'],actual_hp_loss=audit['metrics']['L'],losses=audit['metrics'].get('losses'),tail=audit.get('tail'),lethal_vetoes=attempt['observation']['lethal_vetoes'],actual_unblocked_lethal=attempt['observation']['unblocked_lethal'],cluster_routes=clusters,damage_events=damages,policy_hit_log=attempt['policy'].get('hit_log'),live_ticks=attempt['policy'].get('ticks'),tick_ms_p50=attempt['policy'].get('tick_ms_p50'),tick_ms_p99=attempt['policy'].get('tick_ms_p99'),verification_complete=not errors,no_second_bout=True)
    put(A/'ROOT_BEHAVIOR_AUDIT.json',result)
    print(json.dumps(dict(verification_complete=not errors,errors=errors,normal_audit_errors=ordinary['errors'],T=window['T'],losses=result['losses'],vetoes=result['lethal_vetoes'],clusters=[{k:v for k,v in g.items() if k!='rows'} for g in clusters],damage_events=damages),ensure_ascii=False))
finally:
    st=read(B/'sol/STATUS.json');st.update(at=now(),phase='ONE_OBSERVATION_AUDIT_ENDED',own_offline_jobs=[]);status(st)
