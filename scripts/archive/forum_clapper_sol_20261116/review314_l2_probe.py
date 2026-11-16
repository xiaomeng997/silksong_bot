"""Independently repeat only the two affected L2 lifecycle cases on the #314 source."""
from pathlib import Path
import sys,json,datetime,os,hashlib,psutil,traceback
B=Path('C:/ssbot/data/m2_play/clapper_plan');A=B/'analysis/task179_return314_20261106';D=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot');S='e137055c14294f1580bc69ad680decd786c90388'
sys.path.insert(0,str(D/'brain'));sys.dont_write_bytecode=True
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,d):
    assert not p.exists(),str(p)
    p.write_text(json.dumps(d,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
def status(d):
    p=B/'sol/STATUS.return314.tmp';p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(p,B/'sol/STATUS.json')
me=psutil.Process();me.cpu_affinity(list(range(24,32)));me.nice(psutil.IDLE_PRIORITY_CLASS)
st=read(B/'sol/STATUS.json');assert not st['live_or_budget_running'] and not st.get('own_offline_jobs');A.mkdir(exist_ok=False)
job=dict(pid=me.pid,created=me.create_time(),phase='independent two L2 lifecycle cases plus real landing completion',affinity=me.cpu_affinity(),priority=me.nice(),at=now())
put(A/'ROOT_JOB.json',job);st.update(at=now(),phase='RETURN314_INCREMENTAL_REVIEW',candidate_source=S,source_review_pending=True,own_offline_jobs=[job]);status(st)
error=None
try:
    old=read(B/'analysis/task179_return313_20261105/SOURCE_PACKET.json')['raw_runtime_files_sha256'];current={n:sha(D/n) for n in old}
    changed=[n for n,h in old.items() if current[n]!=h]
    assert changed==['brain/ssbot/combat/tactics/clapper_priority.py'],changed
    put(A/'SOURCE_PACKET.json',dict(source=S,base='830cc00951fbaf9b39fcb2b50c6451b8bd1a53d4',runtime_files=len(current),changed=changed,raw_runtime_files_sha256=current,new_test_sha256=sha(D/'brain/tests/test_middle_return313.py')))
    import pytest
    from tests.test_clapper_priority import manual,scene,step,change
    from tests.test_middle_return313 import move,near_attack
    from ssbot.core.worldstate import E
    mp=pytest.MonkeyPatch();manual.__wrapped__(mp)
    def hero(ws,x,y,contact):
        ws.hero.pos=E((x,y));ws.hero.contact=E(contact)
        ws.hero.hurtbox=[(x-.25,y-1.6),(x+.25,y-1.6),(x+.25,y+.4),(x-.25,y+.4)]
    def view(tac,out):
        return dict(scene=tac.last.get('clapper_scene'),back=tac.last.get('clapper_back'),end=tac.last.get('clapper_back_end'),stance=out.stance_x,target=out.target,hit_kw=out.hit_kw)
    tac,ws,fc=scene(xs=(20.,21.5),hx=20.75);hero(ws,20.75,9.,'AIR');step(tac,ws,fc)
    a=view(tac,near_attack(tac,ws,fc));assert a['back']['posture']=='air' and a['stance']==20.75 and a['target']==8
    tac,ws,fc=scene(xs=(20.,23.),hx=15.);step(tac,ws,fc);near_attack(tac,ws,fc)
    hero(ws,21.5,9.,'AIR');step(tac,ws,fc);move(ws,fc,8,28.)
    opening=view(tac,step(tac,ws,fc));assert opening['back']['posture']=='ground' and opening['end'] is None
    move(ws,fc,8,23.);closing=view(tac,step(tac,ws,fc));assert closing['back']['posture']=='air' and closing['stance']==22. and closing['hit_kw'][8][:3]==(0.,0.,0.)
    move(ws,fc,8,28.);hero(ws,24.,5.6,None);unknown=view(tac,step(tac,ws,fc));assert unknown['back'] is not None and unknown['end'] is None
    hero(ws,24.,5.6,'GROUND');landed=view(tac,step(tac,ws,fc));assert landed['back'] is None and landed['end']['end']=='landed in the standing gap'
    foreign=[]
    for name,mod in list(sys.modules.items()):
        p=getattr(mod,'__file__',None)
        if p and (name=='ssbot' or name.startswith('ssbot.')) and str(D/'brain').replace('\\','/').lower() not in p.replace('\\','/').lower():foreign.append(p)
    assert not foreign and all(sha(D/n)==h for n,h in current.items())
    result=dict(at=now(),source=S,component_pass=True,first_tight_near_end=a,air_gap_open=opening,reclosed_before_landing=closing,unknown_contact=unknown,actual_ground_contact=landed,foreign_modules=foreign,source_unchanged=True,scope='real L2 synthetic fixture only; no full policy/path, timing or live claim',job=job)
    put(A/'ROOT_L2_REPRO.json',result);mp.undo();print(json.dumps(result,ensure_ascii=False))
except BaseException as exc:
    error=repr(exc);put(A/'ROOT_ERROR.json',dict(at=now(),error=error,traceback=traceback.format_exc()));raise
finally:
    put(A/'ROOT_JOB_END.json',dict(at=now(),job=job,error=error,workers_started=False,formal_P_ticks=0,games_started=0))
    st=read(B/'sol/STATUS.json');st.update(at=now(),phase='RETURN314_REVIEW_PENDING',own_offline_jobs=[]);status(st)
