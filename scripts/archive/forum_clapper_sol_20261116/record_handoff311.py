from pathlib import Path
import hashlib, json, datetime
B=Path('C:/ssbot/data/m2_play/clapper_plan')
A=B/'analysis/over_evade311_20261109'
def read(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def write(p,obj):
    t=p.with_suffix(p.suffix+'.tmp')
    t.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    t.replace(p)
mail=(B/'sol/TO_OPUS.md').read_bytes()
digest=hashlib.sha256(mail).hexdigest()
state=read(B/'opus/watch/state.json')
wake=read(B/'sol/OPUS_WAKE.json')
heartbeat=read(B/'opus/watch/heartbeat.json')
log=(B/'opus/watch/watch.log').read_text(encoding='utf-8-sig')
line=[s for s in log.splitlines() if 'SOL_WAKE seq=316 ' in s]
assert wake['seq']==316 and state['tasks_seen']==digest and line
now=datetime.datetime.now(datetime.timezone.utc).isoformat()
r={'at':now,'package':'seq311','written':True,'wake_seq':316,'wake':wake,'mail_sha256':digest,'listener_log':line[-1],'listener_tasks_seen_matches':True,'listener_state':state,'heartbeat':heartbeat,'implementation_started_verified':False,'formal_delivery_received':False,'new_live_released':False,'note':'Receipt establishes dispatch and listener acknowledgement only; actual implementation and formal delivery are separate.'}
write(A/'HANDOFF311.json',r)
s=read(B/'sol/STATUS.json')
s.update(at=now,phase='OVER_EVADE311_WAIT_DELIVERY',source_review_pending=True,current_package='seq311',package_root=str(A),seq311_handoff=str(A/'HANDOFF311.json'),live_or_budget_running=False,own_offline_jobs=[],own_live_session=None)
write(B/'sol/STATUS.json',s)
print(json.dumps({k:r[k] for k in ['at','package','wake_seq','mail_sha256','listener_tasks_seen_matches','implementation_started_verified','formal_delivery_received']},ensure_ascii=False))
