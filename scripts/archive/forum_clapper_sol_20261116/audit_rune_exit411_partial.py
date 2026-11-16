"""Audit the recorded10 after the user paused and manually closed the game."""
from pathlib import Path
import datetime, importlib.util, json, os, psutil, subprocess, sys

B=Path('C:/ssbot/data/m2_play/clapper_plan');G=B/'analysis/w13_50_rune_exit411_20261113';A=B/'analysis/rune_exit411_20261113';D=B/'sol/demos'/G.name
read=lambda p:json.loads(p.read_text('utf-8-sig'))
now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n','utf-8')

def main():
 assert read(G/'ROOT_CLEANUP.json')['physical_cleanup_complete']
 state=read(B/'sol/STATUS.json');assert not state['live_or_budget_running'] and not state.get('own_offline_jobs')
 me=psutil.Process();me.cpu_affinity(list(range(24,32)));me.nice(psutil.IDLE_PRIORITY_CLASS)
 job=dict(pid=me.pid,created=me.create_time(),kind='User-paused10 raw audit',cpus=me.cpu_affinity())
 state.update(at=now(),own_offline_jobs=[job]);put(B/'sol/STATUS.json',state)
 spec=importlib.util.spec_from_file_location('partial_audit_helpers',G/'audit_repeat50.py');helpers=importlib.util.module_from_spec(spec);spec.loader.exec_module(helpers)
 sys.path.insert(0,str(A/'source/brain'));os.environ['NUMBA_DISABLE_JIT']='1'
 env=os.environ.copy();env.update(PYTHONPATH=str(A/'source/brain'),NUMBA_DISABLE_JIT='1',PYTHONDONTWRITEBYTECODE='1')
 rows=[json.loads(l) for l in (D/'run/attempts_i0.jsonl').read_text('utf-8').splitlines() if l.strip()]
 assert len(rows)==10 and [r['episode'] for r in rows]==list(range(10))
 assert len(read(D/'learning_budget.json')['attempts'])==10
 assert [r['seed'] for r in rows]==read(G/'CONTINUOUS_PLAN.json')['seeds'][:10]
 auditdir=G/'audits';auditdir.mkdir(exist_ok=False);out=[]
 for ep,r in enumerate(rows):
  ap=auditdir/f'MEASUREMENT_e{ep}.json'
  with (auditdir/f'MEASUREMENT_e{ep}.log').open('x',encoding='utf-8') as log:
   p=subprocess.run([sys.executable,'-B','-X','utf8','-m','ssbot.tools.forum_measure_audit','--run',str(D/'run'),'--instance','0','--episode',str(ep),'--out',str(ap),'--protocol-version','2'],env=env,stdout=log,stderr=subprocess.STDOUT)
  au=read(ap);exited=helpers.real_exit(r)
  if not au['complete'] and r['outcome']=='CLEAR' and exited:au=helpers.finish_real_quit_tail(r,ap,auditdir/f'MEASUREMENT_e{ep}_REAL_QUIT_TAIL.json')
  assert au['complete'] and r['measurement']['complete'] and r['measurement']['trace_complete'] and r['measurement']['configuration_complete'] and not r['measurement']['unresolved']
  tail=(au.get('tail') or {}).get('metrics') or {};loss=au['metrics']['L']+tail.get('L',0);assert loss==r['hp_lost']
  assert r['outcome']=='CLEAR' or helpers.real_q1(r)
  manifest=read(D/f'run/measurement_manifest_i0_e{ep}.json');assert manifest['code']['head_revision']==read(A/'SOURCE_PACKET.json')['source']
  sw=manifest['switches']['SSBOT_FORUM_RUNE_EXIT_FINAL'];assert sw['bindings']=={'ssbot.combat.tactics.clapper_priority.RUNE_EXIT_FINAL':True}
  assert not manifest['unknown_environment_switches'] and not manifest['unresolved']
  out.append(dict(bout=ep+1,episode=ep,seed=r['seed'],outcome=r['outcome'],protected_quit=exited,criterion_pass=r['outcome']=='CLEAR' and not exited and loss<5,loss_HP=loss,raw_audit_complete=True))
  print(f'user-paused raw audit {ep+1}/10 complete',flush=True)
 parent=read(B/'analysis/w13_50_runtime354_20261113/ROOT_50_RESULT.json')['rows'][:10]
 result=dict(at=now(),source=read(A/'SOURCE_PACKET.json')['source'],planned=50,completed=10,unstarted=list(range(11,51)),batch_complete=False,user_requested_pause=True,user_reported_manual_close=True,
  stop_not_prompt=True,no_auto_resume=True,normal_stop_at_requested_bout_not_achieved=True,
  pass_bouts=sum(r['criterion_pass'] for r in out),both_killed=sum(r['outcome']=='CLEAR' for r in out),protected_quits=sum(r['protected_quit'] for r in out),
  hitless=[r['bout'] for r in out if r['criterion_pass'] and not r['loss_HP']],loss_HP=sum(r['loss_HP'] for r in out),
  close_related_primary_error=read(Path(read(G/'ROOT_CLEANUP.json')['worker_cleanup']))['primary_error'],physical_cleanup_verified=True,
  matched_parent_first10=dict(same_seeds=[r['seed'] for r in out]==[r['seed'] for r in parent],pass_bouts=sum(r['criterion_pass'] for r in parent),loss_HP=sum(r['loss_hp'] for r in parent),scope='Ten-bout descriptive prefix only; not a complete50 or causal comparison.'),rows=out)
 put(G/'ROOT_PARTIAL_RESULT.json',result)
 put(G/'RAW_AUDIT_COMPLETION.json',dict(at=now(),complete_for_observed_exposure=True,completed10_audited=True,full50_complete=False,process=job))
 print(json.dumps({k:v for k,v in result.items() if k not in ['rows','unstarted']},ensure_ascii=False))

if __name__=='__main__':main()
