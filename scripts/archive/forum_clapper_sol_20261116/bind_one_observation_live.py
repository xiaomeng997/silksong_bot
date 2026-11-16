"""Bind the prepared ONE-bout lifecycle after the final scoped source/metadata review. Never launches a game."""
from pathlib import Path
import sys,json,os,datetime,hashlib,subprocess,importlib.util
B=Path('C:/ssbot/data/m2_play/clapper_plan');D=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot')
R=Path(sys.argv[1]);P=B/'analysis/task179_observe311_20261105';OLD=B/'analysis/w13_guard179L3_20261106T012400Z_5df8711e'
G='C:/Users/Meng/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe';PY=Path('C:/modeling/silksong_bot/brain/.venv/Scripts/python.exe')
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,d):
 assert not p.exists(),p
 p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def git(*a):return subprocess.check_output([G,'-C',str(D),*a],text=True,encoding='utf-8').strip()
st=read(B/'sol/STATUS.json');assert not st['live_or_budget_running'] and not st.get('own_offline_jobs')
sr=read(R/'SOURCE_REVIEW.json');packet=read(R/'SOURCE_PACKET.json');S=sr['source']
assert sr['accepted'] and packet['source']==S and git('rev-parse','HEAD')==S
assert not git('diff','HEAD','--','brain/ssbot','knowledge')
assert all(sha(D/n)==h for n,h in packet['raw_runtime_files_sha256'].items())
assert read(P/'p/FINALIZED.json')['cleanup_verified'] and read(P/'ROOT_P_AUDIT.json')['formal_ticks']==85
meta=Path(sr['metadata_positive_receipt']);assert read(meta)['configuration_complete'] is True
binding=read(B/'analysis/task179_observe310_20261105/LIVE_DRAFT_BINDING.json');A=Path(binding['analysis']);T=Path(binding['trial'])
assert not T.exists() and not (A/'ENGINEERING_GATE.json').exists()
d=read(A/'TRIAL_CONFIG_DRAFT.json');d['source_pending']=S
assert d['arguments'][d['arguments'].index('--episodes')+1]=='1'
assert all(d['environment'].get(k)==v for k,v in sr['required_environment'].items())
sys.path.insert(0,str(D/'brain'));sys.dont_write_bytecode=True
from ssbot.tools.launcher import PrefsGuard,current_prefs,read_reg_file,prefs_diff,running_game_pids
g=PrefsGuard.default();reg=g.status();assert reg.get('instances')==[] and reg.get('live')==[] and reg.get('restore_pending') is False
assert not running_game_pids() and g.verify_golden()=='fc41b9c5427b4e23ec60af1f16808a6b497507eded5704b90c9224b056ea0469'
assert not prefs_diff(current_prefs(g.store),read_reg_file(g.golden))
demo=Path('C:/ssbot/sandbox/DEMO_SOON')
assert sha(demo)=='0455dd550525b4b11ed62eccb47cdfeb802a3ba0a8b0c08d30f8cc961c53cb81' and demo.stat().st_mtime_ns==1791523123325081300
assert not any((demo.parent/n).exists() for n in ['STOP_AGENTS','HUMAN_PRACTICE'])
assert sha(Path('C:/ssbot/game/train/BepInEx/plugins/SsOracle/SsOracle.dll'))=='ca7673dbeb8f3a061deca742aa0972f585c5284dd5328e8d2378d064509930ac'
processed=sorted(set(st['accepted_opus_numbers'])|set(sr['processed_opus_numbers']))
spec=importlib.util.spec_from_file_location('live_helpers',A/'engineering_helpers.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
assert not h.new_blockers(processed),'new/unprocessed review blocker'
put(A/'ROOT_PREFLIGHT_STATIC.json',dict(at=now(),source=S,head=git('rev-parse','HEAD'),runtime_files=len(packet['raw_runtime_files_sha256']),registry=reg,games=[],golden_ok=True,prefs_diff=[],old_demo_sha256=sha(demo),old_demo_mtime_ns=demo.stat().st_mtime_ns,new_worker_input_receipt_required=True,no_game_started=True))
(A/'TRIAL_CONFIG_DRAFT.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
put(A/'ACCEPTANCE.json',dict(at=now(),scope='ONE watched observation, not no-hit/survival acceptance',source=S,max_bouts=1,game_limit_s=45,seed=314169,start_hp=7,retreat_widths=2.5,ordinary_damage_continues=True,lethal_veto_continues=True,unblocked_death_or_guard_input_log_resource_fault_stops=True,no_auto_next_bout=True))
put(A/'ENGINEERING_DISPOSITION.json',dict(at=now(),source=S,authority='Human requested one bout, damage continues, death blocked, prepare then open; no new permission question',p_source='05b8caeaf86fad46790172f9bd84691e27439bda',p_audit=str(P/'ROOT_P_AUDIT.json'),p_reuse=sr['p_reuse'],scope_limits='actual observed injuries and vetoes do not certify normal mortality; no simulator/live equivalence or future timing guarantee',source_frozen_until_actual_cleanup=True))
evidence=[R/'SOURCE_REVIEW.json',R/'SOURCE_PACKET.json',meta,P/'ROOT_P_AUDIT.json',P/'p/FINALIZED.json',P/'CHECK_RECEIPT.json',B/'analysis/task179_observe310_20261105/CHECK_RECEIPT.json',A/'ACCEPTANCE.json',A/'ENGINEERING_DISPOSITION.json',A/'ROOT_PREFLIGHT_STATIC.json',A/'SCRIPT_PORT_RECEIPT.json',A/'run_unattended.py',A/'RESOURCE_BACKGROUND_APPROVAL.json',A/'resource_background.py']
put(A/'ENGINEERING_GATE.json',dict(at=now(),scope='ONE_W13_OBSERVATION_ENGINEERING',ready=True,user_authorized=True,source=S,execution_head=git('rev-parse','HEAD'),source_packet=str(R/'SOURCE_PACKET.json'),source_review_pass=True,source_review=str(R/'SOURCE_REVIEW.json'),standalone_transport_gate=True,worker_input_gate=True,actual_new_worker_receipt_required=True,input_scope='old input gate is component provenance; actual NEW worker own bootstrap stats must be0/HF2/2/pending0',accepted_opus_numbers=processed,review_applicability=sr['review_applicability'],evidence={str(p):sha(p) for p in evidence},authorization='current human requests ONE watched observation, no HP stop, prevent death',p_scope=str(P/'ROOT_P_AUDIT.json'),budget_scope='one actual bout only; no automatic next/replacement',scope_limits=['FACE_HOOK0','BOUNCE_TABLE0','OBSERVE_BOUT1','REMAINING_HP_QUIT0','45 game seconds','no no-hit/survival claim'],resource_revision='verified-core-background-v1'))
subprocess.run([str(PY),'-X','utf8','-B',str(A/'trial.py')],cwd=D,check=True)
st=read(B/'sol/STATUS.json');assert not st['live_or_budget_running'] and not st.get('own_offline_jobs')
st.update(at=now(),phase='ONE_OBSERVATION_READY',current_source=S,source_review_pending=False,source_review_file=str(R/'SOURCE_REVIEW.json'),next_watch_user_authorized=True,observation_one_bout=dict(analysis=str(A),trial=str(T),source=S,max_bouts=1,damage_stop=False,prevent_death=True,source_ready=True,gate_ready=True))
q=B/'sol/STATUS.live_ready.tmp';q.write_text(json.dumps(st,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(q,B/'sol/STATUS.json')
put(A/'LAUNCH_REQUEST.json',dict(at=now(),source=S,root_preflight_pass=True,one_attempt_only=True,launcher=str(A/'run_unattended.py'),trial=str(T),source_frozen_until_actual_cleanup=True))
print(json.dumps(dict(ready=True,analysis=str(A),trial=str(T),source=S,game_started=False)))
