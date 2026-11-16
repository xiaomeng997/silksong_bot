"""Prepare reviewed #318 source and fixed-executor cases; no P/game is started here."""
from pathlib import Path
import ast,datetime,hashlib,json,os,shutil,psutil,subprocess
B=Path('C:/ssbot/data/m2_play/clapper_plan');A=B/'analysis/task179_return318_20261106';D=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot');M=Path('C:/modeling/silksong_bot')
S='0b1481774f04838a610e5d31a70acbfcdef623df';G='C:/Users/Meng/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe'
T=B/'sol/demos/w13_observe_bait_20261106T055356Z';old=B/'sol/performance/adapters/task179_5df8711e.py';producer=B/'opus/review179/l1_308/replay308.py'
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,d):
 assert not p.exists(),str(p)
 p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def atom(p,d):
 t=p.with_name(p.name+'.return318.tmp');t.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(t,p)
st=read(B/'sol/STATUS.json');assert not st['live_or_budget_running'] and not st.get('own_offline_jobs')
assert not (B/'sol/performance/ACTIVE.json').exists()
assert read(B/'sol/OPUS_WAKE.json')['seq']==241
assert subprocess.check_output([G,'-C',str(D),'rev-parse','HEAD'],text=True).strip()==S
j=read(A/'ROOT_JOB.json')
try:alive=abs(psutil.Process(j['pid']).create_time()-j['created'])<.01
except psutil.NoSuchProcess:alive=False
assert not alive and read(A/'CHECK_RECEIPT.json')['pytest_rc']==0
put(A/'ROOT_CHECK_CLEANUP.json',dict(at=now(),job=j,identity_exited=True,formal_P_ticks=0,games_started=0))
pkt=read(A/'SOURCE_PACKET.json');assert all(sha(D/n)==h for n,h in pkt['raw_runtime_files_sha256'].items())
put(A/'SOURCE_REVIEW.json',dict(at=now(),source=S,accepted=True,scope='ONLY four affected offline P windows on current318; BODY/AIR on A/N/W and off D in distinct actual executor processes; no game/continuous-downslash certification',processed_opus_number=318,previous317_P2_closed=True,independent_changed_checks=11,checks_seconds=1.57,source_delta='one native Idle observer: explicit current-frame Control->Idle, gaps revoke extension, same-frame death unknown, later hit revokes old instance',retained='317 finite air-only legal recovery and per-target contact grouping; 315/316 lock boundaries retained',limits=['A4 is recorded-reaction conditional legal recovery/landing/slash, not natural NPC response or repeated downslash','W3 is synthetic ground command positive, no side-hit model','Old input/deadline/scheduling limits retained, this P sample is not a future latency guarantee'],full_behavior_live_accepted=False,new_game_gate=False,checks=str(A/'CHECK_RECEIPT.json'),artifact_receipt=str(A/'ROOT_ARTIFACT_RECEIPT.json')))

src=producer.read_text(encoding='utf-8');known=old.read_text(encoding='utf-8');edits=[]
def replace(a,b):
 global src
 assert src.count(a)==1,(a[:80],src.count(a));src=src.replace(a,b);edits.append((a,b))
startup=known[known.index('    if "--startup-only" in flags:'):known.index('    policy.warmup()\n    policy.reset')]
# The fixed executor's startup check stays on E24-31 (the scene's normal engineering default is E16-23).
startup=startup.replace('        # Lifecycle only:', '        me.cpu_affinity(list(range(24,32)))\n        # Lifecycle only:',1)
replace('    print("warming policy", flush=True)\n    policy.warmup()', '    print("warming policy", flush=True)\n'+startup+'    policy.warmup()')
line='    assert policy.params.hero2 == 16383 and chain is not None'
replace(line,line+'\n    chain.require_send_clock = False  # deterministic recorded prehistory; actual clock required at measured T')
measure=known[known.index('        chain.require_send_clock = True'):known.index('        runtime = None',known.index('        chain.require_send_clock = True'))]
replace('        runtime = None\n        if FORMAL:',measure+'        runtime = None\n        if FORMAL:')
replace('        "runtime_before": timing.get("runtime") or {}}})','        "boost_result": (timing.get("runtime") or {}).get("boost_result"),\n        "runtime_before": timing.get("runtime") or {}}})')
extra=known[known.index('    from ssbot.combat.knife_chain_nominal import compiled_signatures\n    out["signatures_after"]'):known.index('    out["configuration_complete"] = manifest["configuration_complete"]')]
replace('    out["configuration_complete"] = manifest["configuration_complete"]',extra+'    out["configuration_complete"] = manifest["configuration_complete"]')
inverse=src
for a,b in reversed(edits):assert inverse.count(b)==1;inverse=inverse.replace(b,a)
assert inverse==producer.read_text(encoding='utf-8');ast.parse(src)
entry=A/'timing_entry318.py';entry.write_text(src,encoding='utf-8')
put(A/'ADAPTER_REVIEW.json',dict(at=now(),base=str(producer),base_sha256=sha(producer),known_lifecycle_adapter=str(old),known_sha256=sha(old),entry_sha256=sha(entry),inverse_exact=True,edits=['exact previously validated startup warmup/close branch; E24-31 startup only','deterministic prehistory clock off; true clock guard at measured T','actual field identity, signatures, boost_result and child/module diagnostics'],control_geometry_and_synthetic_model_unchanged=True,guarded_main=True))
H=B/'analysis/w13_guard179L3_20261106T012400Z_5df8711e'
for n in ['engineering_helpers.py','resource_background.py','RESOURCE_BACKGROUND_APPROVAL.json']:shutil.copyfile(H/n,A/n)
files=[T/'contract.json',T/'run/decisions_i0.chain.jsonl',T/'run/b2_input_path_i0.json',producer]
files.extend(p for p in (T/'run/rec').rglob('*') if p.is_file())
put(A/'P_INPUT_BINDING.json',dict(at=now(),scope='closed completed observation inputs and recorded-reaction conditional scene; no new live input stats',files={str(p):sha(p) for p in files}))
accepted=sorted(set(st['accepted_opus_numbers'])|set(range(308,319)))
put(A/'REVIEW_APPLICABILITY.json',dict(at=now(),processed_for_this_P=accepted,not_global_accepted_set=True,scope='308/309 disabled FACE_HOOK/BOUNCE_TABLE; 310..312 completed OBS1 source; 313..318 return delta and fixes now incrementally reviewed for on/off offline P only',full_live_accepted=False))
common=dict(source=S,source_root=str(D),source_review_file=str(A/'SOURCE_REVIEW.json'),entry_file=str(entry),entry_sha256=sha(entry),source_packet_file=str(A/'SOURCE_PACKET.json'),source_packet_sha256=sha(A/'SOURCE_PACKET.json'),input_binding_file=str(A/'P_INPUT_BINDING.json'),input_binding_sha256=sha(A/'P_INPUT_BINDING.json'),resource_helper_file=str(A/'engineering_helpers.py'),resource_helper_sha256=sha(A/'engineering_helpers.py'),git_directory=str(Path(G).parent),cache=str(B/'analysis/critical214_20261103/p_prepared_ce81b62c/numba_cache'),baseline=dict(golden_sha256='fc41b9c5427b4e23ec60af1f16808a6b497507eded5704b90c9224b056ea0469',old_demo_sha256='0455dd550525b4b11ed62eccb47cdfeb802a3ba0a8b0c08d30f8cc961c53cb81',old_demo_mtime_ns=1791523123325081300),accepted_reviews=accepted,expected_field_worker=True)
on=['--env=SSBOT_FORUM_TWO_RETURN_BODY=1','--env=SSBOT_FORUM_TWO_RETURN_AIR=1','--no-force-from=2760']
def q(name,first,last,flags):return dict(name=name,trial=str(T),last=last,flags=flags,**{'from':first})
contexts=[q('A',2785,2900,on+['--shift-ent=335470:2760:-2.5','--splice-raw=335470:2790:2733:-2.5','--splice-ent=335476:2836:2766:0','--react-raw=335470:3339:mirror','--down-release-ok']),q('N',2810,2830,on),q('W',2860,2900,on+['--shift-ent=335470:2760:1.5','--delay-ent=335470:2800:120','--splice-ent=335476:2836:2766:0'])]
put(A/'P_CASE_ON.json',dict(common,contexts=contexts,scope='178 affected measured ticks: A116/N21/W41, explicit BODY/AIR on only'))
put(A/'P_CASE_OFF.json',dict(common,contexts=[q('D',2600,2640,['--no-force-from=2760','--env=SSBOT_FORUM_TWO_RETURN_BODY=0','--env=SSBOT_FORUM_TWO_RETURN_AIR=0'])],scope='41 measured ticks default-off D in a separate actual process'))
assert sha(B/'sol/performance/executor_v1.py')=='58ddebd9cae93764d37b9fb4efa75ea7a2484bb6f4337895a245886e86062ffc'
mail='''## seq242 / 同Task179：318事件绑定回修核收；仅四窗P冻结源码，暂不实现新改动

Root审单源完整增量，11直接检查1.57s通过、foreign0/714全同、E24764真实退出。FSM入口替代scaled时钟推算、断档撤延长、同帧死亡未知回39、明确新Idle重绑关闭317的P2；乙/分组未重改。五组原工件各682个最终tuple逐位不变，原producer f57d+dirty记录保持。SOURCE_REVIEW现仅限以下P范围accepted=true，不是整包/实机通过；见analysis/task179_return318_20261106/。

现在源0b148177与刀口docs HEAD冻结到Root实际P完整退出清理；请暂停计算/改源，STATUS true时只读。Root复用固定executor_v1，已把原Sol核过startup/close和真实clock/worker/signature收据段接到你replay308的Sol副本，逆替换逐字节还原，未动场景/控制/几何；先做非计时最小启动退出检查，再分别真实进程跑ON A/N/W及OFF D，合计219拍，不重跑其他窗。A末帧2900不冒充覆盖2903。入口/源码/输入都绑SHA，原资源门与Windows进程不动。

P运行中不并跑重计算；普通确认不必新编号唤醒。当前没有新局许可，旧观察与STOP不重开；连续下劈/自然响应等未覆盖仍按原限制保留。Root核完P与真实清理再给一次结果反馈。

'''
mp=B/'sol/TO_OPUS.md';mp.write_text(mail+mp.read_text(encoding='utf-8-sig'),encoding='utf-8')
st.update(at=now(),phase='RETURN318_READY_FIXED_STARTUP',candidate_source=S,current_source=S,source_review_pending=False,source_review_file=str(A/'SOURCE_REVIEW.json'),source_review_scope='four offline P windows only, no live gate',opus318_review=str(A/'SOURCE_REVIEW.json'),active_blocker=None,source_frozen_for_P=True,next_watch_user_authorized=False)
atom(B/'sol/STATUS.json',st);atom(B/'sol/OPUS_WAKE.json',dict(seq=242,task=179,at=now(),note='318 P2 fixed, finite four-window P review accepted. Freeze runtime/docs and pause compute until actual P cleanup; no game.'))
print(json.dumps(dict(source_review=True,cases=[str(A/'P_CASE_ON.json'),str(A/'P_CASE_OFF.json')],executor_unchanged=True,input_files=len(files))))
