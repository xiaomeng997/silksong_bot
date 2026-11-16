"""Two bounded real-L2 probes for the new return state; no planner simulation or game."""
from pathlib import Path
import sys,json,datetime,os,hashlib,psutil
B=Path('C:/ssbot/data/m2_play/clapper_plan');A=B/'analysis/task179_return313_20261105';D=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot')
sys.path.insert(0,str(D/'brain'));sys.dont_write_bytecode=True
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def status(s):
    p=B/'sol/STATUS.return313.tmp';p.write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(p,B/'sol/STATUS.json')
def put(p,d):
    assert not p.exists(),str(p)
    p.write_text(json.dumps(d,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
me=psutil.Process();me.cpu_affinity(list(range(24,32)));me.nice(psutil.IDLE_PRIORITY_CLASS)
s=read(B/'sol/STATUS.json');assert not s['live_or_budget_running'] and not s.get('own_offline_jobs')
A.mkdir(exist_ok=True)
s.update(at=now(),phase='RETURN313_INCREMENTAL_REVIEW',source_review_pending=True,candidate_source='830cc00951fbaf9b39fcb2b50c6451b8bd1a53d4',own_offline_jobs=[dict(pid=me.pid,created=me.create_time(),phase='two bounded L2 probes',cpus=me.cpu_affinity(),priority=me.nice())]);status(s)
try:
    base=read(B/'analysis/task179_observe312_20261105/SOURCE_PACKET.json')['raw_runtime_files_sha256']
    current={n:sha(D/n) for n in base};changed=[n for n,h in base.items() if current[n]!=h]
    packet=dict(source=s['candidate_source'],base='b4615f2528edf339d0a8b9e61de21681d5910289',runtime_files=len(current),changed=changed,raw_runtime_files_sha256=current,new_test_sha256=sha(D/'brain/tests/test_middle_return313.py'))
    if (A/'SOURCE_PACKET.json').exists():assert read(A/'SOURCE_PACKET.json')==packet
    else:put(A/'SOURCE_PACKET.json',packet)
    import pytest
    from tests.test_clapper_priority import manual,scene,step,change
    from tests.test_middle_return313 import hero_at,move,near_attack
    from ssbot.combat.tactics import gauntlet as G
    mp=pytest.MonkeyPatch();manual.__wrapped__(mp)
    def view(tac,out):
        return dict(region=tac.last.get('clapper_region'),scene=tac.last.get('clapper_scene'),winner=tac.last.get('clapper_winner'),back=tac.last.get('clapper_back'),back_end=tac.last.get('clapper_back_end'),pending=tac._clapper_priority.get('back'),stance=out.stance_x,target=out.target,hit_kw=out.hit_kw)
    tac,ws,fc=scene(xs=(20.,21.5),hx=20.75);hero_at(ws,20.75,y=9.);step(tac,ws,fc)
    first=view(tac,near_attack(tac,ws,fc))
    tac,ws,fc=scene(xs=(20.,23.),hx=15.);step(tac,ws,fc);near_attack(tac,ws,fc)
    hero_at(ws,21.5,y=9.);step(tac,ws,fc);before=view(tac,step(tac,ws,fc))
    move(ws,fc,8,28.);opening=view(tac,step(tac,ws,fc))
    move(ws,fc,8,23.);closing=view(tac,step(tac,ws,fc))
    result=dict(at=now(),source=s['candidate_source'],scope='real L2 entry with existing synthetic scene fixture; no planner, geometry certificate, timing or live claim',root_between_when_near_attack_ends=first,airborne_gap_opens=dict(hero_y=9.,before=before,opened=opening,reclosed=closing),known_limit='fixture contact fields are not an actual live grounded proof; source itself has no vertical/contact completion gate',foreign_modules=[])
    for name,mod in list(sys.modules.items()):
        p=getattr(mod,'__file__',None)
        if p and (name=='ssbot' or name.startswith('ssbot.')) and str(D/'brain').replace('\\','/').lower() not in p.replace('\\','/').lower():result['foreign_modules'].append(p)
    assert not result['foreign_modules']
    assert all(sha(D/n)==h for n,h in current.items())
    put(A/'ROOT_L2_REPRO.json',result);mp.undo()
    print(json.dumps(result,ensure_ascii=False,default=str))
finally:
    s=read(B/'sol/STATUS.json');s.update(at=now(),phase='RETURN313_REVIEW_PENDING',own_offline_jobs=[]);status(s)
