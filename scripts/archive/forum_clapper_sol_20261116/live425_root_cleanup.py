import json,psutil,sys,hashlib,datetime
from pathlib import Path
B=Path('C:/ssbot/data/m2_play/clapper_plan');R=B/'analysis/w13_50_landing425_20261114';N=B/'analysis/landing_exit423_20261114';D=B/'sol/demos'/R.name
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'));sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()
sys.path.insert(0,str(N/'source_fixed424/brain'));from ssbot.tools.launcher import RegPrefsStore,current_prefs,read_reg_file,prefs_diff
end=read(R/'COORDINATOR_END.json');cl=read(D/'launch/cleanup.json');assert not cl['errors'] and not cl['prefs_diff']
owned=read(R/'ROOT_OBSERVED_PROCESSES.json')['processes'];alive=[]
for x in owned:
 try:
  p=psutil.Process(x['pid'])
  if p.create_time()==x['created'] and p.is_running():alive.append(x)
 except psutil.NoSuchProcess:pass
assert not alive,alive
games=[p.pid for p in psutil.process_iter(['name']) if 'silksong' in (p.info['name'] or '').lower()];assert not games
registry=read(Path('C:/ssbot/sandbox/prefs/instances.json'));assert registry['instances']==[] and not registry['restore_pending']
golden=Path('C:/ssbot/sandbox/prefs/golden.reg');diff=prefs_diff(current_prefs(RegPrefsStore()),read_reg_file(golden));assert not diff
assert sha(golden)=='fc41b9c5427b4e23ec60af1f16808a6b497507eded5704b90c9224b056ea0469'
demo=Path('C:/ssbot/sandbox/DEMO_SOON');assert sha(demo)=='0455dd550525b4b11ed62eccb47cdfeb802a3ba0a8b0c08d30f8cc961c53cb81' and demo.stat().st_mtime_ns==1791523123325081300
c=read(D/'contract.json');assert all(sha(Path(c['code'])/p)==h for p,h in c['files'].items());assert all(sha(Path(p))==h for p,h in c['prerequisites'].items())
wc=list((D/'run').glob('worker_cleanup_i0_*.json'));assert len(wc)==1;wr=read(wc[0]);assert wr['complete'] and not wr['secondary_errors']
cap=read(D/'launch/CAPTURE_CLOSED.json');assert cap['encoder_returncode']==0 and cap['frames']>0
from ssbot.combat.knife_chain_budget import audit_events
audit=audit_events(D/'learning_budget.json');assert audit['clean'] and not audit['unmerged']
rows=[json.loads(x) for x in (D/'run/attempts_i0.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]
batch_complete=not end['error'] and not cl['failure'] and cl['worker_returncode']==0 and wr['primary_error'] is None and not audit['stop'] and len(rows)==50
foreign={'applied':False,'reason':'No foreign isolation was applied for this new50 batch'}
out={'at':now(),'complete':True,'runtime_batch_complete':batch_complete,'stopped_batch_no_retry':not batch_complete,'acceptance_pending_raw_audit':True,'coordinator_end':end,'launcher_cleanup':cl,'worker_cleanup':str(wc[0]),'actual_owned_processes_exited':owned,'residual_games':games,'registry':registry,'prefs_diff':diff,'golden_sha256':sha(golden),'old_demo_sha256':sha(demo),'old_demo_mtime_ns':demo.stat().st_mtime_ns,'runtime_files_unchanged':len(c['files']),'prerequisites_unchanged':len(c['prerequisites']),'capture_closed':cap,'foreign_isolation_closed':foreign,'raw_audit_pending':True,'budget_journal_audit':audit}
with (R/'ROOT_CLEANUP.json').open('x',encoding='utf-8') as f:json.dump(out,f,ensure_ascii=False,indent=2)
s=read(B/'sol/STATUS.json');s.update(at=now(),phase='SEPARATED31250_ENDED_RAW_AUDIT_PENDING',live_or_budget_running=False,own_live_session=None,new_game_gate=False);s['separated31250_actual_cleanup']=str(R/'ROOT_CLEANUP.json');s.update(next='Audit actual completed and interrupted exposure; never reopen a stopped batch',next_owner='Sol: batch raw audit and next authorized work',next_phase='Audit every actual episode; do not assume 50 completed');(B/'sol/STATUS.json').write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'complete':True,'owned_exited':len(owned),'runtime_unchanged':len(c['files']),'prerequisites':len(c['prerequisites']),'foreign':foreign,'capture':cap},ensure_ascii=False))
