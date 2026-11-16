from pathlib import Path
import ast,datetime,hashlib,json,shutil
B=Path('C:/ssbot/data/m2_play/clapper_plan');R=B/'analysis/task179_observe310_20261105'
OLD=B/'analysis/w13_guard179L3_20261106T012400Z_5df8711e'
tag='w13_observe_bait_'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
A=B/'analysis'/tag;T=B/'sol/demos'/tag;A.mkdir()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def put(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for n in ['engineering_helpers.py','resource_background.py','RESOURCE_BACKGROUND_APPROVAL.json']:shutil.copyfile(OLD/n,A/n)
src=(OLD/'trial.py').read_text(encoding='utf-8-sig');code=src.replace(OLD.name,tag)
code=code.replace('"ONE_W13_AIR_ENGINEERING"','"ONE_W13_OBSERVATION_ENGINEERING"')
code=code.replace('"SSBOT_FORUM_REMAINING_HP_QUIT":"6"','"SSBOT_FORUM_REMAINING_HP_QUIT":"0","SSBOT_FORUM_OBSERVE_BOUT":"1","SSBOT_FORUM_CHAIN_FACE_HOOK":"0","SSBOT_FORUM_CHAIN_BOUNCE_TABLE":"0"')
old='   link.rpc("profile.set",name="TRAIN",timeout_s=15);link.close()'
new='''   try:
    train=link.rpc("profile.set",name="TRAIN",timeout_s=15);write(TRIAL/"launch/train_preflight.json",train)
    guards=link.rpc("guards.get",timeout_s=15);write(TRIAL/"launch/lethal_guard_preflight.json",guards)
    assert guards.get("profile")=="TRAIN" and guards.get("lethal_block")=="block" and not guards.get("refused"),"observation requires TRAIN lethal block"
    assert guards.get("healthy",{}).get("lethal_block") is True and guards.get("healthy",{}).get("session_gate") is True,"lethal/session guard unhealthy"
   finally:link.close()'''
assert code.count(old)==1;code=code.replace(old,new);ast.parse(code);(A/'trial.py').write_text(code,encoding='utf-8')
co=(OLD/'run_unattended.py').read_text(encoding='utf-8-sig')
old="assert d['current_source']=='5df8711ea04accff8c03e87560d31b53b2e87a09' and not d['source_review_pending']"
new="assert d['current_source']==json.loads((HERE/'ENGINEERING_GATE.json').read_text())['source'] and not d['source_review_pending']"
assert co.count(old)==1;co=co.replace(old,new).replace('UNATTENDED_WALK179_L3_LIVE','OBSERVE_BAIT_ONE_LIVE');ast.parse(co);(A/'run_unattended.py').write_text(co,encoding='utf-8')
d=read(OLD/'TRIAL_CONFIG_DRAFT.json');d=json.loads(json.dumps(d).replace(OLD.name,tag));d['environment'].update(SSBOT_FORUM_OBSERVE_BOUT='1',SSBOT_FORUM_REMAINING_HP_QUIT='0',SSBOT_FORUM_CHAIN_FACE_HOOK='0',SSBOT_FORUM_CHAIN_BOUNCE_TABLE='0')
a=d['arguments'];a[a.index('--seed')+1]='314169';a+=['--timebox','45'];assert a[a.index('--episodes')+1]=='1' and '--measure' in a
d.update(scope='ONE_W13_OBSERVATION_ENGINEERING',source_pending=None,purpose='ONE watched cluster bait then return ground side-swing observation; HP losses and healthy lethal veto continue; not a survival/no-hit result',user_present_request='先打一盘吧，我不容易记混',coverage_target='record actual initial layout, fixed2.5bodywidth retreat/wall cap, observed takeoff, ground return/swing; all other injuries recorded separately',user_authorized=True,authorization='current user explicitly requests one bout, damage continues, death blocked; no automatic next bout',stopping='45 game seconds/natural end; guard/input/log/resource/control faults stop; no ordinary HP or healthy lethal-veto stop')
put(A/'TRIAL_CONFIG_DRAFT.json',d)
put(A/'SCRIPT_PORT_RECEIPT.json',dict(origin=str(OLD),trial_changes=['fresh namespace','observation scope/profile assertions','readonly TRAIN/healthy lethal guard receipt on same game process before worker; original worker input.stats bootstrap remains unchanged'],coordinator_changes=['source equals separately reviewed game gate','phase name'],owned_spawn_worker_launcher_cleanup_unchanged=True,old_demo_handling='original approved park-and-restore lifecycle retained, exact old hash/mtime verified; STOP/PRACTICE remain hard stop',new_game_gate=False))
put(R/'LIVE_DRAFT_BINDING.json',dict(tag=tag,analysis=str(A),trial=str(T),source_pending=True,gate_exists=False,trial_root_created=False,max_bouts=1))
assert not (A/'ENGINEERING_GATE.json').exists() and not T.exists()
print(json.dumps(dict(tag=tag,analysis=str(A),trial=str(T),draft_only=True,no_game_started=True)))
