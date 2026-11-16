from pathlib import Path
import ast,datetime,hashlib,json,shutil
B=Path('C:/ssbot/data/m2_play/clapper_plan');OLD=B/'analysis/w13_50_air_catch429_display_20261114';G=B/'analysis/w13_50_air_catch429_tv_on_20261114';D=B/'sol/demos'/G.name
A=B/'analysis/air_catch428_20261114';H='d7cbe1a59cbee1d8fa8d40c53fc57b3ed1bd2b19';ROOT=Path('C:/modeling/silksong_bot')
read=lambda p:json.loads(Path(p).read_text(encoding='utf-8-sig'));sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()
def put(p,d):Path(p).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def rewrite(t):return t.replace(OLD.name,G.name).replace('AIR_CATCH429_DISPLAY50_W13_HP2_CONTINUOUS','AIR_CATCH429_TV_ON50_W13_HP2_CONTINUOUS')
assert not G.exists() and not D.exists()
s=read(B/'sol/STATUS.json');assert s['current_source']==H and not s['source_review_pending'] and not s['live_or_budget_running'] and not s['own_offline_jobs'] and not s['own_live_session']
assert read(OLD/'ROOT_CLEANUP.json')['complete'] and not (B/'sol/performance/ACTIVE.json').exists()
packet=read(A/'SOURCE_PACKET_FIXED.json');S=Path(packet['source_root']);assert all(sha(S/n)==h for n,h in {**packet['raw_runtime_files_sha256'],**packet['support_sha256']}.items())
assert read(A/'SOURCE_REVIEW_AND_P_FINAL.json')['accepted'] and read(A/'ROOT_P_AUDIT.json')['finite_measurement_valid']
G.mkdir()
for p in OLD.glob('*.py'):
 text=rewrite(p.read_text(encoding='utf-8-sig'));(G/p.name).write_text(text,encoding='utf-8')
 assert ast.dump(ast.parse(text),include_attributes=False)==ast.dump(ast.parse((G/p.name).read_text(encoding='utf-8')),include_attributes=False)
for name in ['RESOURCE_BACKGROUND_APPROVAL.json','RESOURCE_BACKGROUND_CLASSIFICATION_CHECKS.json','RUNTIME354_REUSE.json']:shutil.copy2(OLD/name,G/name)
auth=read(OLD/'USER_NEW50_AUTHORIZATION.json');auth.update(at=now(),source=H,batch_id=G.name,user_text='电视打开了 继续',
 question_item_id='direct current-chat user message: 电视打开了 继续',started=False,
 provenance={'kind':'Actual direct current Codex chat message','observed_at':now(),'user_text':'电视打开了 继续',
 'scope':'Fresh50 after physical TV on, same reviewed source/config/seeds, existing temporary awake-display preference retained'},
 physical_tv_on_confirmed_by_user=True)
put(G/'USER_NEW50_AUTHORIZATION.json',auth)
for name in ['CONTINUOUS_PLAN.json','TRIAL_CONFIG_DRAFT.json','CANDIDATE_SPEC.json','VALIDATION_PLAN.json','START_GATE_CHECKS.json']:
 x=json.loads(rewrite(json.dumps(read(OLD/name),ensure_ascii=False)));x['at']=now()
 if 'authorization' in x:x['authorization']=auth['user_text']
 if name=='VALIDATION_PLAN.json':x['next_candidate']=G.name
 if name=='CONTINUOUS_PLAN.json':x['notes']='TV physically on confirmed by user; one fresh50, same source/seeds, temporary awake request; >=30 startup fps required; old batches closed.'
 put(G/name,x)
for p in G.glob('*.py'):compile(p.read_text(encoding='utf-8'),str(p),'exec')
review=read(OLD/'LIFECYCLE_REVIEW.json');review.update(at=now(),files={p.name:sha(p) for p in G.glob('*.py')},previous_review=str(OLD/'LIFECYCLE_REVIEW.json'),changes='Same reviewed code/guards with fresh batch labels and actual user TV-on/continue authorization. All execute/input/stops/capture/cleanup logic unchanged.');put(G/'LIFECYCLE_REVIEW.json',review)
put(G/'BATCH_SPEC.json',dict(at=now(),batch=G.name,source=H,planned_bouts=50,state='AUTHORIZED_STAGED_PREPARE_PENDING',ready=False,started=False,authorization=str(G/'USER_NEW50_AUTHORIZATION.json'),display_awake=True,physical_tv_on_user_confirmed=True,minimum_launch_fps=30,airstrike=True,landing_exit=True,prior_paused_batch_reopened=False))
s.update(at=now(),phase='TV_ON50_AUTH_VERIFIED_STAGING',live_paused_by_user=False,authorized_batch=G.name,authorized_bouts=50,live_pause_released_only_for_batch=G.name,live_tv_on50_authorization_consumed=False,pending_user=None,next_phase='Fresh50 after TV on; prepare, bounded display request, actual startup>=30fps then original GO; no extra confirmation.')
put(B/'sol/STATUS.json',s)
launch=(ROOT/'tmp/launch_live429.ps1').read_text(encoding='utf-8');(ROOT/'tmp/launch_tv_on50.ps1').write_text(rewrite(launch),encoding='utf-8')
start=(ROOT/'tmp/start_display429.ps1').read_text(encoding='utf-8')
old="r=json.loads((g/'DISPLAY_HOLD_READY.json').read_text(encoding='utf-8'));assert r['pid']==p.pid and abs(r['created']-p.create_time())<.01"
new="r=json.loads((g/'DISPLAY_HOLD_READY.json').read_text(encoding='utf-8'));actual=psutil.Process(r['pid']);assert abs(r['created']-actual.create_time())<.01 and (actual.pid==p.pid or actual.ppid()==p.pid) and 'display_hold429.py' in ' '.join(actual.cmdline())"
assert old in start;start=start.replace(old,new)
old="owned=dict(pid=p.pid,created=p.create_time(),name=p.name(),cmdline=p.cmdline(),ppid=p.ppid())"
new="owned=[dict(pid=x.pid,created=x.create_time(),name=x.name(),cmdline=x.cmdline(),ppid=x.ppid()) for x in {p.pid:p,actual.pid:actual}.values()]"
assert old in start;start=start.replace(old,new).replace('processes=[owned]','processes=owned').replace('pid=p.pid,created=p.create_time(),physical_TV_power_not_verified=True','pid=actual.pid,created=actual.create_time(),physical_TV_power_not_verified=True')
(ROOT/'tmp/start_display_tv_on50.ps1').write_text(rewrite(start),encoding='utf-8')
watch=(ROOT/'tmp/watch_live429_once.py').read_text(encoding='utf-8');(ROOT/'tmp/watch_tv_on50_once.py').write_text(rewrite(watch),encoding='utf-8')
print(json.dumps(dict(batch=G.name,authorized50=True,user_confirmed_TV_on=True,source=H,game_started=False)))
