from pathlib import Path
import datetime,hashlib,json,sys
import numpy as np
import psutil

B=Path('C:/ssbot/data/m2_play/clapper_plan');A=B/'analysis/b13_399_20261112'
read=lambda p:json.loads(Path(p).read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()
def put(p,d):Path(p).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def dead(q):
    try:return abs(psutil.Process(q['pid']).create_time()-q['created'])>.01
    except psutil.NoSuchProcess:return True
def source_inputs():
    sp=read(A/'SOURCE_PACKET.json')
    assert all(sha(A/'source'/n)==h for n,h in {**sp['raw_runtime_files_sha256'],**sp['support_sha256']}.items())
    assert all(sha(p)==h for p,h in read(A/'REPLAY_INPUT_BINDING.json')['files'].items())
    return sp
def window(p,q,value,formal):
    r=read(p/'RESULT.json');pe=r['p_entry'];assert r['exception'] is None and not r['foreign'] and pe['formal']==formal
    m=read(p/'CONFIGURATION_MANIFEST.json');assert not m['unknown_environment_switches']
    assert set(m['unresolved'])=={'SSBOT_FORUM_CHAIN_BLOCK','SSBOT_FORUM_CHAIN_ORDER','SSBOT_FORUM_CHAIN_SCHEDULE','SSBOT_WORKER_BOOST','SSBOT_WORKER_CPUS'}
    sw=m['switches']['SSBOT_FORUM_CHAIN_B13'];assert sw['raw']==str(value) and sw['bindings']=={'ssbot.combat.knife_chain_transfer.B13':bool(value)}
    assert all(sha(A/'source/brain/ssbot'/n)==h for n,h in r['source_sha256'].items()),'result source drift'
    rr=[json.loads(l) for l in (p/'measurement_trace.jsonl').read_text().splitlines()];ts=[x for x in rr if x['kind']=='tick'];ac=[x for x in rr if x['kind']=='action'];fo=rr[-1]
    assert fo['complete'] and fo['overflow']==0 and fo['records']==len(rr)-2
    di=fo['diagnostics'];assert di['complete'] and not di['events_overwritten'] and not di['callback_errors']
    assert not [e for e in di['events'] if e['kind']!='gc']
    assert len(ts)==len(ac)==pe['ticks']==q['last']-q['from']+1
    assert all(t['actions']==1 and not t['error'] and t['send_done_ns']>=t['tick_start_ns'] for t in ts)
    acts={x['f']:x for x in ac}
    assert all(acts[t['f']]['target_frame']==t['f']+2 and acts[t['f']]['send_done_ns']==t['send_done_ns'] and acts[t['f']]['policy_mask_matches_wire'] and acts[t['f']]['policy_flags_match_wire'] for t in ts)
    for n in ['BUDGET_LIFECYCLE.json','DECISION_LOG_LIFECYCLE.json','WORKER_LIFECYCLE.json']:assert read(p/n)['complete'],n
    budget=read(p/'BUDGET_LIFECYCLE.json');assert budget['journal_fd_after'] is None and budget['audit_after']['clean'] and not budget['audit_after']['unmerged']
    logs=read(p/'DECISION_LOG_LIFECYCLE.json');assert all(logs['after_drain'][k]==0 for k in ['held_bytes','held_chunks','pending_rows'])
    w=read(p/'WORKER_LIFECYCLE.json');assert set(w['workers'])=={'field','plan'} and not w['errors']
    assert all(x['closed'] and x['exitcode']==0 and dead(x['identity']) for x in w['workers'].values())
    if formal:
        tim=pe['timing'];rt=tim['runtime'];assert tim['signatures_before']==r['signatures_after']
        assert rt['cpu_affinity']==list(range(16)) and rt['priority']==128 and not rt['power_throttling']['execution_speed_throttled'] and not rt['query_errors']
    es=[json.loads(l) for l in (p/'decisions_i0.chain.jsonl').read_text().splitlines()]
    notes=[x for x in es if x.get('event')=='transfer_b13_guard' and x.get('frame') in acts]
    selected={x['frame']:x for x in es if x.get('event')=='b2_selected' and x.get('frame') in acts}
    branches=[]
    for n in notes:
        f=n['frame'];s=selected.get(f);a=acts[f]
        row=dict(f=f,kind=n['kind'],state=n.get('state'),opening=n.get('opening'),steer=n.get('steer'),proposal_mask=n['mask'],actual_mask=a['mask'],actual_owner=a['owner'],selected=s is not None,actual_chain=a['owner']=='chain')
        if n['kind']=='strike':
            press=n['press_F'];pa=next((x for x in ac if x['target_frame']==press),None)
            row.update(press_F=press,contact_F=n['contact_F'],actual_down_attack_sent=bool(pa and pa['owner']=='chain' and pa['mask']&2 and pa['mask']&(1<<19)))
        branches.append(row)
    vals=[x['total_tick_ms'] for x in ts]
    return dict(ticks=len(vals),frames=[t['f'] for t in ts],tick_p50_ms=float(np.percentile(vals,50)),tick_p99_ms=float(np.percentile(vals,99)),tick_max_ms=max(vals),over_16_67ms=sum(v>1000/60 for v in vals),branches=branches,model_hits=r.get('model_hits'),configuration_unresolved=m['unresolved'],source_files=len(r['source_sha256'])),vals

def main():
    sp=source_inputs();mode=sys.argv[1]
    if mode=='engineering':
        root=A/sys.argv[2];e=read(root/'ENGINEERING.json');assert e['error'] is None and not e['children_left'] and dead(e)
        c=read(A/'CASE_NEW.json');out={}
        for q in c['contexts']:out[q['name']]=window(root/q['name'],q,1,False)[0]
        put(A/'PRODUCTION_EXECUTION_EVIDENCE.json',dict(at=now(),source=sp['source'],source_inputs_unchanged=True,formal=False,actual_workers_exited=True,windows=out,scope='Existing production policy/planner/geometry/before_send/sent; hero synthetic after SYN, recorded enemy future. Model hits are not live hits.'))
        print(json.dumps({k:dict(ticks=v['ticks'],branches=v['branches']) for k,v in out.items()},ensure_ascii=False))
    else:
        out={};frames={};receipts=[]
        for side,value in [('new',1),('baseline',0)]:
            c=read(A/('CASE_'+side.upper()+'.json'));windows={};values=[]
            formal_root=A/(sys.argv[2] if side=='new' and len(sys.argv)>2 else 'formal_'+side)
            for prefix in ['startup','formal']:
                p=(A/(prefix+'_'+side) if prefix=='startup' else formal_root)/'FINALIZED.json';f=read(p);assert f['execution_ok'] and f['cleanup_verified'] and all(dead(x) for x in [f,*f['workers']]);receipts.append(str(p))
            for q in c['contexts']:
                d,v=window(formal_root/q['name'],q,value,True);windows[q['name']]=d;values+=v;frames[side,q['name']]=d['frames']
            out[side]=dict(ticks=len(values),tick_p50_ms=float(np.percentile(values,50)),tick_p99_ms=float(np.percentile(values,99)),over_16_67ms=sum(v>1000/60 for v in values),windows=windows)
        assert all(frames['new',q['name']]==frames['baseline',q['name']] for q in c['contexts'])
        audit=dict(at=now(),source=sp['source'],source_and_inputs_unchanged=True,matching_frame_sets=True,outputs=out,receipt_files=receipts,scope='Four affected finite windows, same final source with B13 on/off, real async plan/field, actual wire sends; descriptive cost only.',full_scheduling_gate_pass=not any(x['over_16_67ms'] for x in out.values()),limitations=['Known five configuration descriptors unresolved, no unknown environment switches; actual B13 binding checked.','Recorded enemies do not respond to new hero actions; no live safety or win-rate proof.','Check actual branch coverage before assigning scoped pass.'])
        put(A/'ROOT_P_AUDIT.json',audit);print(json.dumps({k:{n:x[n] for n in ['ticks','tick_p50_ms','tick_p99_ms','over_16_67ms']} for k,x in out.items()}))

if __name__=='__main__':main()
