"""Run existing reviewed entry without --formal; retain actual named worker receipts."""
from pathlib import Path
import datetime,importlib.util,json,os,sys,traceback
import psutil

B=Path('C:/ssbot/data/m2_play/clapper_plan');A=B/'analysis/b13b_402_20261113'
read=lambda p:json.loads(Path(p).read_text(encoding='utf-8'))
now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()
def put(p,d):
    p=Path(p);q=p.with_name(p.name+'.tmp');q.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(q,p)
def alive(d):
    try:return abs(psutil.Process(d['pid']).create_time()-d['created'])<.01
    except psutil.NoSuchProcess:return False

def main():
    c=read(A/'CASE_NEW.json');out=A/(sys.argv[1] if len(sys.argv)>1 else 'engineering_new');assert not out.exists();out.mkdir()
    s=read(B/'sol/STATUS.json');assert not s['live_or_budget_running'] and not s.get('own_offline_jobs')
    assert not (B/'sol/performance/ACTIVE.json').exists()
    me=psutil.Process();me.cpu_affinity(list(range(24,32)));me.nice(psutil.IDLE_PRIORITY_CLASS)
    ident=dict(pid=me.pid,created=me.create_time());s.update(at=now(),phase='B13B_ENGINEERING_PRODUCTION_CHECK',own_offline_jobs=[dict(pid=me.pid,create_time=me.create_time(),phase='engineering',timing=False,directory=str(out))]);put(B/'sol/STATUS.json',s)
    os.environ.update(OPUS_KNIFE=c['source_root'],OPUS_NUMBA=c['cache'],PYTHONDONTWRITEBYTECODE='1',NUMBA_NUM_THREADS='4')
    os.environ['PATH']=c['git_directory']+os.pathsep+os.environ.get('PATH','')
    result=dict(at=now(),**ident,source=c['source'],formal=False,contexts=[],error=None)
    try:
        for q in c['contexts']:
            dest=out/q['name'];assert not dest.exists()
            sys.argv=[c['entry_file'],q['trial'],str(q['last']),str(dest),'--p-from='+str(q['from']),'--engineering',*q['flags']]
            spec=importlib.util.spec_from_file_location('b13_existing_entry_'+q['name'],c['entry_file']);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
            with (out/(q['name']+'.log')).open('x',encoding='utf-8',buffering=1) as log:
                oldout,olderr=sys.stdout,sys.stderr;sys.stdout=sys.stderr=log
                try:m.main()
                finally:sys.stdout,sys.stderr=oldout,olderr
            r=read(dest/'RESULT.json');w=read(dest/'WORKER_LIFECYCLE.json')
            assert r['exception'] is None and not r['foreign'] and not r['p_entry']['formal']
            assert w['complete'] and not w['errors'] and set(w['workers'])=={'field','plan'}
            assert all(x['closed'] and x['exitcode']==0 and not alive(x['identity']) for x in w['workers'].values())
            result['contexts'].append(dict(name=q['name'],directory=str(dest),workers=w['workers'],ticks=r['p_entry']['ticks']))
    except BaseException:
        result['error']=traceback.format_exc();raise
    finally:
        result['children_left']=[dict(pid=p.pid,created=p.create_time()) for p in me.children(recursive=True)]
        put(out/'ENGINEERING.json',result)
    print(json.dumps(dict(engineering_complete=True,contexts=[x['name'] for x in result['contexts']],requires_actual_exit_check=True)))

if __name__=='__main__':main()
