"""Audit completed39 plus censored fault40 without reopening or completing the batch."""
from pathlib import Path
from datetime import datetime,timezone
import collections,hashlib,importlib.util,json,os,psutil,subprocess,sys
B=Path('C:/ssbot/data/m2_play/clapper_plan');G=B/'analysis/w13_50_b13b404_20261113';D=B/'sol/demos'/G.name
S=B/'analysis/b13b_402_20261113/source'
read=lambda p:json.loads(Path(p).read_text(encoding='utf-8-sig'))
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
now=lambda:datetime.now(timezone.utc).isoformat()
def put(p,v):
    with Path(p).open('x',encoding='utf-8') as f:json.dump(v,f,ensure_ascii=False,indent=2);f.write('\n')
def main():
    assert read(G/'ROOT_CLEANUP.json')['physical_cleanup_complete']
    st=read(B/'sol/STATUS.json');assert not st['live_or_budget_running'] and not st.get('own_offline_jobs')
    me=psutil.Process();me.cpu_affinity(list(range(24,32)));me.nice(psutil.IDLE_PRIORITY_CLASS)
    proc=dict(at=now(),pid=me.pid,created=me.create_time(),kind='stopped40 independent raw audit',cpus=me.cpu_affinity(),priority=int(me.nice()))
    put(G/'PARTIAL_AUDIT_PROCESS.json',proc);st.update(at=now(),own_offline_jobs=[proc],phase='B13B404_STOPPED40_RAW_AUDIT')
    (B/'sol/STATUS.json').write_text(json.dumps(st,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    spec=importlib.util.spec_from_file_location('prior_audit_helpers',G/'audit_repeat50.py');helpers=importlib.util.module_from_spec(spec);spec.loader.exec_module(helpers)
    sys.path.insert(0,str(S/'brain'));env=os.environ.copy();env.update(PYTHONPATH=str(S/'brain'),PYTHONDONTWRITEBYTECODE='1',NUMBA_DISABLE_JIT='1')
    rows=[json.loads(l) for l in (D/'run/attempts_i0.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
    assert len(rows)==40 and [r['episode'] for r in rows]==list(range(40))
    plan=read(G/'CONTINUOUS_PLAN.json');assert [r['seed'] for r in rows]==plan['seeds'][:40]
    assert rows[-1]['outcome']=='HARNESS_FAIL' and all(r['outcome'] in ['CLEAR','QUIT'] for r in rows[:-1])
    gate=read(G/'ENGINEERING_GATE.json');outdir=G/'audits';outdir.mkdir(exist_ok=False)
    audited=[];damage=collections.Counter();events=collections.Counter()
    for ep,r in enumerate(rows):
        out=outdir/f'MEASUREMENT_e{ep}.json';log=outdir/f'MEASUREMENT_e{ep}.log'
        with log.open('x',encoding='utf-8') as f:
            p=subprocess.run([sys.executable,'-B','-X','utf8','-m','ssbot.tools.forum_measure_audit','--run',str(D/'run'),'--instance','0','--episode',str(ep),'--out',str(out),'--protocol-version','2'],env=env,stdout=f,stderr=subprocess.STDOUT)
        au=read(out);exited=helpers.real_exit(r);q1=helpers.real_q1(r)
        if not au['complete'] and r['outcome']=='CLEAR' and exited:
            au=helpers.finish_real_quit_tail(r,out,outdir/f'MEASUREMENT_e{ep}_REAL_QUIT_TAIL.json')
        m=r['measurement'];assert r['rand']['hp']==7 and not r['would_die'] and r['time_scale_game']==1
        assert r['code_rev'].removesuffix('+dirty') in [gate['source'],gate['source'][:8]]
        assert m['configuration_complete'] and m['trace_complete'] and not m['unresolved'] and m['overflow']==0
        if ep<39:
            assert au['complete'] and m['complete'],ep
            assert q1 or r['outcome']=='CLEAR'
        else:
            assert not au['complete'] and not m['complete']
        tail=(au.get('tail') or {}).get('metrics') or {};loss=au['metrics']['L']+tail.get('L',0)
        assert loss==r['hp_lost'],(ep,loss,r['hp_lost'])
        if ep<39:
            for hit in au['metrics']['losses']+tail.get('losses',[]):damage[hit['source']]+=hit['amount'];events[hit['source']]+=1
        audited.append(dict(bout=ep+1,episode=ep,seed=r['seed'],source=gate['source'],outcome=r['outcome'],protected_quit=exited,q1=q1,
            criterion_pass=ep<39 and r['outcome']=='CLEAR' and not exited and loss<5,loss_hp_observed=loss,
            raw_audit_complete=au['complete'],T_observed=au['metrics']['T'],recording=r['recording'],wake_f=r['f_wake'],end_f=r['f_end'],initial_CLI_returncode=p.returncode))
        print(json.dumps(dict(audited=ep+1,total_exposed=40,complete=au['complete'])),flush=True)
    valid=audited[:-1];old=read(B/'analysis/w13_50_slamstart398_20261112_r1/ROOT_50_RESULT.json')['rows'][:39]
    assert [r['seed'] for r in valid]==[r['seed'] for r in old]
    result=dict(at=now(),batch=G.name,source=gate['source'],planned_bouts=50,attempted=40,completed_bouts=39,censored_fault_bouts=[40],unstarted_bouts=list(range(41,51)),
        batch_complete=False,criterion_pass=False,stopped_batch_no_retry=True,source_mixed=False,
        pass_bouts=sum(r['criterion_pass'] for r in valid),protected_quit_bouts=sum(r['protected_quit'] for r in valid),
        hitless_bouts=[r['bout'] for r in valid if r['criterion_pass'] and not r['loss_hp_observed']],real_deaths=0,
        completed_loss_HP=sum(r['loss_hp_observed'] for r in valid),fault_observed_HP=audited[-1]['loss_hp_observed'],
        fault_unknown_interval_retained=True,HP_by_damage_source=dict(damage),real_damage_events_by_source=dict(events),
        matched_first39=dict(same_seed_order=True,new_pass=sum(r['criterion_pass'] for r in valid),baseline_pass=sum(r['criterion_pass'] for r in old),
            new_HP=sum(r['loss_hp_observed'] for r in valid),baseline_HP=sum(r['loss_hp'] for r in old),
            baseline_hitless=sum(r['criterion_pass'] and r['loss_hp']==0 for r in old),scope='Descriptive same-seed39 prefix only; no filled-in final11 bouts, isolated causality or full50 result.'),
        cleanup_receipt=str(G/'ROOT_CLEANUP.json'),rows=audited)
    put(G/'ROOT_PARTIAL_RESULT.json',result)
    put(G/'RAW_AUDIT_COMPLETION.json',dict(at=now(),complete_for_observed_exposure=True,all50_complete=False,completed39_audits=True,fault40_incomplete_preserved=True,process=proc))
    print(json.dumps({k:v for k,v in result.items() if k not in ['rows','HP_by_damage_source','real_damage_events_by_source']},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
