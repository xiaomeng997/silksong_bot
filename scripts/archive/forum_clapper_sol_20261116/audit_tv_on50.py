"""Post-cleanup independent audit of the new continuous 50. No game control."""
import collections, json, os, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import psutil
A=Path('C:/ssbot/data/m2_play/clapper_plan/analysis/w13_50_air_catch429_tv_on_20261114')
B=A.parents[1]
D=B/'sol/demos'/A.name
S=B/'analysis/air_catch428_20261114/source_fixed428'
def read(p): return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def write(p,value):
    with Path(p).open('x',encoding='utf-8') as fp:
        json.dump(value,fp,ensure_ascii=False,indent=2); fp.write('\n')
def now(): return datetime.now(timezone.utc).isoformat()
def real_q1(row):
    q='Q1:' in (row.get('reason') or '')
    if q:
        rq=row['policy']['real_quit']
        assert rq['armed'] and rq['main_menu'] and rq['outcome']=='QUIT' and rq['wrong_submits']==0
    return q

def real_exit(row):
    rq=row.get('policy',{}).get('real_quit') or {}
    q=rq.get('outcome')=='QUIT'
    if q:
        assert rq['armed'] and rq['main_menu'] and rq['wrong_submits']==0
        assert row.get('min_hp') is not None and row['min_hp']<=2
    return q

def finish_real_quit_tail(row, original, out):
    """Use original window semantics for CLEAR plus actual verified main-menu quit (Q1 or Q5). Preserve original CLI receipt."""
    assert row['outcome']=='CLEAR' and real_exit(row)
    from ssbot.record import formats
    from ssbot.record.recorder import RecordingReader
    from ssbot.train.forum_measure_window import MeasurementWindow
    from ssbot.tools.forum_measure_audit import audit_window
    wake,last=row['f_wake'],row['f_end']
    win=MeasurementWindow(SimpleNamespace(wake_frame=wake),wave=13,expected_targets=2,game_limit=120,protocol_version=2)
    states=[]
    for _,recv,_,flags,_,payload in RecordingReader(row['recording']).records('state'):
        f=formats.peek(payload,('f',),flags).get('f')
        if not isinstance(f,int) or f<wake-1: continue
        if f>last+2: break
        st=formats.peek(payload,('f','dt','hero','ents','ev','room','game','act'),flags)
        states.append(st)
        if f<=last: win.observe(st,recv)
    before=win.snapshot()
    assert before['end_reason']=='targets_dead' and before['tail_end_f'] is None
    win.finish_at(last,'episode_quit'); measured=win.snapshot()
    audit={'run':str(D/'run'),'instance':0,'episode':row['episode'],'window':measured,
           **audit_window(states,measured,row),'initial_audit':str(original),
           'method':'Actual verified main-menu protected quit finish_at after targets_dead; initial CLI receipt retained; raw/source unchanged.'}
    write(out,audit)
    assert audit['complete'] and audit['tail']['metrics']['real_quit_unload'] is not None
    return audit

def main():
    assert read(A/'ROOT_CLEANUP.json')['complete']
    status=read(B/'sol/STATUS.json')
    assert not status['live_or_budget_running'] and not status.get('own_offline_jobs')
    assert not any((p.info['name'] or '').lower().find('silksong')>=0 for p in psutil.process_iter(['name']))
    gate=read(A/'ENGINEERING_GATE.json'); plan=read(A/'CONTINUOUS_PLAN.json')
    with (D/'run/attempts_i0.jsonl').open(encoding='utf-8') as fp:
        rows=[json.loads(line) for line in fp if line.strip()]
    assert len(rows)==50 and [r['episode'] for r in rows]==list(range(50))
    assert [r['seed'] for r in rows]==plan['seeds'] and len(set(plan['seeds']))==50
    me=psutil.Process(); me.cpu_affinity(list(range(24,32))); me.nice(psutil.IDLE_PRIORITY_CLASS)
    receipt={'at':now(),'pid':me.pid,'created':me.create_time(),'cpus':me.cpu_affinity(),'priority':int(me.nice()),'kind':'new50 independent raw audit'}
    write(A/'AUDIT_PROCESS.json',receipt)
    status.update(at=now(),own_offline_jobs=[receipt],phase='SEPARATED31250_RAW_AUDIT')
    temp=(B/'sol/STATUS.json').with_suffix('.tmp'); temp.write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); temp.replace(B/'sol/STATUS.json')
    os.environ['NUMBA_DISABLE_JIT']='1'
    sys.path.insert(0,str(S/'brain'))
    env=os.environ.copy(); env.update(PYTHONPATH=str(S/'brain'),PYTHONDONTWRITEBYTECODE='1',NUMBA_DISABLE_JIT='1')
    audir=A/'audits'; audir.mkdir(exist_ok=True)
    raw=[]; sources=collections.Counter(); events=collections.Counter(); cli=[]
    for ep,row in enumerate(rows):
        out=audir/f'MEASUREMENT_e{ep}.json'; log=audir/f'MEASUREMENT_e{ep}.log'
        assert not out.exists()
        with log.open('x',encoding='utf-8') as fp:
            proc=subprocess.run([sys.executable,'-X','utf8','-B','-m','ssbot.tools.forum_measure_audit','--run',str(D/'run'),'--instance','0','--episode',str(ep),'--out',str(out),'--protocol-version','2'],env=env,stdout=fp,stderr=subprocess.STDOUT)
        au=read(out); cli.append({'episode':ep,'returncode':proc.returncode,'complete':au['complete'],'out':str(out)})
        q1=real_q1(row); exited=real_exit(row)
        if not au['complete'] and row['outcome']=='CLEAR' and exited:
            au=finish_real_quit_tail(row,out,audir/f'MEASUREMENT_e{ep}_REAL_QUIT_TAIL.json')
        assert au['complete'],ep
        m=row['measurement']; assert m['complete'] and m['configuration_complete'] and m['trace_complete'] and not m['unresolved'] and m['overflow']==0,ep
        assert row['rand']['hp']==7 and row['would_die']==0 and row['time_scale_game']==1,ep
        assert row['code_rev'].removesuffix('+dirty') in (gate['source'],gate['source'][:8]),(ep,row['code_rev'],gate['source'])
        if not q1: assert row['outcome']=='CLEAR',ep
        tail=(au.get('tail') or {}).get('metrics') or {}
        loss=au['metrics']['L']+tail.get('L',0); assert loss==row['hp_lost'],ep
        for x in au['metrics']['losses']+tail.get('losses',[]):
            sources[x['source']]+=x['amount']; events[x['source']]+=1
        raw.append({'bout':ep+1,'episode':ep,'seed':row['seed'],'source':gate['source'],'reported_code_rev':row['code_rev'],'outcome':row['outcome'],'kills':row.get('gauntlet',{}).get('kills',{}).get('n'),'q1':q1,'q5':'Q5:' in row.get('reason',''),'protected_quit':exited,'criterion_pass':row['outcome']=='CLEAR' and not exited and loss<5,'start_hp':7,'loss_hp':loss,'min_hp_observed':row.get('min_hp'),'final_hp_by_loss':7-loss,'main_L':au['metrics']['L'],'tail_L':tail.get('L',0),'T':au['metrics']['T'],'wake_f':row['f_wake'],'end_f':row['f_end'],'kill_f':row.get('f_kill'),'recording':row['recording'],'raw_audit_complete':True})
        print(f'audit repeat {ep+1}/50 complete; Q1={q1}; actual_quit={exited}',flush=True)
    for x in raw:x['batch']=A.name
    assert len(raw)==50 and [x['bout'] for x in raw]==list(range(1,51))
    baseline=read(B/'analysis/w13_50_landing425_20261114/ROOT_50_RESULT.json')
    assert [r['seed'] for r in raw]==[r['seed'] for r in baseline['rows']]
    result={'at':now(),'complete':True,'criterion':'All50 without remaining-HP<=2 actual protected quit including postkill tail; Q1 and Q5 recorded separately','criterion_pass':all(r['criterion_pass'] for r in raw),'bouts':50,'both_killed':sum(r['outcome']=='CLEAR' for r in raw),'pass_bouts':sum(r['criterion_pass'] for r in raw),'Q1_bouts':sum(r['q1'] for r in raw),'protected_quit_bouts':sum(r['protected_quit'] for r in raw),'postkill_protected_quit_bouts':[r['bout'] for r in raw if r['outcome']=='CLEAR' and r['protected_quit']],'postkill_Q1_bouts':[r['bout'] for r in raw if r['outcome']=='CLEAR' and r['q1']],'hitless_whole_bouts':[r['bout'] for r in raw if r['criterion_pass'] and r['loss_hp']==0],'real_deaths':0,'loss_HP_total':sum(r['loss_hp'] for r in raw),'HP_by_damage_source':dict(sources),'real_damage_events_by_source':dict(events),'sources':sorted({x['source'] for x in raw}),'current_source':gate['source'],'mixed_source':len({x['source'] for x in raw})>1,'cleanup_receipt':str(A/'ROOT_CLEANUP.json'),'initial_CLI_audits':cli,'rows':raw,'comparison':{'same_seeds':True,'baseline_source':baseline['sources'],'baseline_pass':baseline['pass_bouts'],'baseline_Q1':baseline['Q1_bouts'],'baseline_hitless':len(baseline['hitless_whole_bouts']),'baseline_loss_HP_total':baseline['loss_HP_total'],'scope':'Same50 seeds; one source per version. Descriptive before/after only; no isolated causal or stability claim.'}}
    write(A/'ROOT_50_RESULT.json',result)
    write(A/'RAW_AUDIT_COMPLETION.json',{'at':now(),'complete':True,'bouts':50,'process':receipt})
    print(json.dumps({k:v for k,v in result.items() if k not in ('rows','initial_CLI_audits','HP_by_damage_source','real_damage_events_by_source')},ensure_ascii=False),flush=True)
if __name__=='__main__': main()
