from pathlib import Path
import ast,datetime as dt,hashlib,json,os,subprocess
M=Path('C:/modeling/silksong_bot');W=Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot');TV=Path('C:/Users/Meng/.codex/worktrees/forum-tv-prep/silksong_bot')
B=Path('C:/ssbot/data/m2_play/clapper_plan');R=B/'analysis/task179_5df8711e_20261105';OLD=B/'analysis/task179_1263e9e3_20261105'
O=B/'opus/review179/l1_305';S='5df8711ea04accff8c03e87560d31b53b2e87a09';GIT='C:/Users/Meng/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe';REL='docs/plans/forum_clapper_plan.md'
now=dt.datetime.now(dt.timezone.utc).isoformat()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def git(root,*args):return subprocess.check_output([GIT,'-C',str(root),*args],text=True,encoding='utf-8').strip()
def put(p,d):
 assert not p.exists(),p
 p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def atomic(p,data):
 t=p.with_name(p.name+'.sol305.tmp');t.write_bytes(data);os.replace(t,p)
status=read(B/'sol/STATUS.json');assert not status['live_or_budget_running'] and not status.get('own_offline_jobs')
assert read(R/'ROOT_CHECK_JOB.json')['exit_code']==0
assert git(W,'rev-parse','HEAD')==S and not git(W,'status','--porcelain','--untracked-files=no')
diff=subprocess.check_output([GIT,'-C',str(W),'diff',S+'^',S,'--','brain/ssbot'])
assert hashlib.sha256(diff).hexdigest()[:16]=='44342b621a61353b'
functional={}
for name,div in [('l1_after',2679),('l2_after',2761)]:
 d=read(O/name/'RESULT.json')
 assert d['knife_diff_sha256_16']=='44342b621a61353b' and d['divergence_tick']==div
 assert d['forced_planner_ticks']==[] and d['exception'] is None and d['foreign']==[]
 assert all(sha(W/'brain/ssbot'/n)==h for n,h in d['source_sha256'].items())
 functional[name]={'divergence':div,'model_hurt':d['first_model_hurt'],'source11_match':True,'forced':[]}
review={'at':now,'source':S,'reviewer':'Sol ordinary complete increment and production artifact audit','accepted':True,
 'changed_files':['brain/ssbot/combat/knife_chain_transfer.py','brain/ssbot/combat/knife_chain_air_v01.json'],
 'diff_sha256_16':'44342b621a61353b','checks':'9 direct incident tests passed1.32s; Opus820 not redundantly rerun','functional':functional,
 'scope':'existing optional dash selector and early-abandon navigation guard, no new action/safety exemption; actual hit/exit remains unverified',
 'limits':['earliest lunge uses existing47/60 clock, not future NPC guarantee','generous geometric union/any-poly applies only to listed approach rolls; it does not enumerate every future downslash timing or prove no other chain possible',
 'unknowns retain old current-step behavior; False never licenses safety','L2 correct result is checked dash refusal and ordinary withdrawal, not successful target attack','L1 modelhurt/nohit retained; earlier handoff does not certify real strike'],
 'air_direct_decision':'Do not expand bounce-animation domain in this iteration; preserve narrow existing window and original guards. Current withdrawal fix is not a new offensive capability.',
 'performance':'pending current-source full affected continuousP; no live gate'}
put(R/'SOURCE_REVIEW.json',review)
packet=read(OLD/'SOURCE_PACKET.json');previous=packet['raw_runtime_files_sha256'];current={n:sha(W/n) for n in previous}
changed=[n for n in current if current[n]!=previous[n]]
assert changed==['brain/ssbot/combat/knife_chain_air_v01.json','brain/ssbot/combat/knife_chain_transfer.py'],changed
put(R/'SOURCE_PACKET.json',{'at':now,'source':S,'source_root':str(W),'raw_runtime_files_sha256':current,'changed_vs1263':changed,'scope':'current710; existing model files unchanged; two guard/selector files'})
inputs=dict(read(OLD/'ACTIVE_INPUT_BINDING.json')['files'])
l2=B/'sol/demos/w13_walk179L2_20261106T000950Z_1263e9e3'
for p in l2.rglob('*'):
 if p.is_file() and p.name not in ('launcher_console.execute.log','worker.log'):
  inputs[str(p)]=sha(p)
assert all(sha(Path(n))==h for n,h in inputs.items())
put(R/'ACTIVE_INPUT_BINDING.json',{'at':now,'source':S,'actual_recorded_behavior_sources':['8f9e9629','1263e9e3'],'files':inputs,'scope':'immutable oldL1 and actualL2 inputs, new per-context offline budget only'})
entry0=B/'sol/performance/adapters/task179_1263e9e3_v2.py'
entry=B/'sol/performance/adapters/task179_5df8711e.py'
text=entry0.read_text(encoding='utf-8-sig')
anchor='    EXPECTED_SLAM_REENTRY = "--expect-slam-reentry" in flags\n'
assert text.count(anchor)==1
text=text.replace(anchor,anchor+'    EXPECTED_305 = next((v.split("=",1)[1] for v in flags if v.startswith("--expect305=")), None)\n')
end='    (DEST / "RESULT.json").write_text(json.dumps(out, indent=1, default=str) + "\\n", encoding="utf-8")\n'
assert text.count(end)==1
check='''    if EXPECTED_305:
        assert EXPECTED_305 in ("l1", "l2")
        div = 2679 if EXPECTED_305 == "l1" else 2761
        by_f = {r["f"]: r for r in rows}
        forced_after = [q for q in forced if q.get("f", -1) >= div]
        if EXPECTED_305 == "l1":
            expected = [(2679, "slam", "R"), (2699, "slam", "J"), (2720, "slam", "A+D")]
            actual = [(f, by_f.get(f,{}).get("owner"), by_f.get(f,{}).get("keys")) for f,_,_ in expected]
            passed = actual == expected
        else:
            expected = "new dash choice is geometrically refused at2761; final owner plan and moving left"
            actual = {"owner": by_f.get(2761,{}).get("owner"), "keys": by_f.get(2761,{}).get("keys"),
                      "dash_refused": any(q.get("event")=="rune_transfer_dash_refused" and q.get("frame")==2761 for q in out["chain_events"])}
            passed = actual["owner"] == "plan" and "L" in actual["keys"].split("+") and actual["dash_refused"]
        check305 = {"context":EXPECTED_305,"expected":expected,"actual":actual,"divergence":out["divergence_tick"],
                    "forced_after":forced_after,"scope":"actual functional route mandatory; no hit/safety certificate"}
        check305["passed"] = passed and out["divergence_tick"] == div and not forced_after
        (DEST/"FUNCTIONAL_VALIDATION.json").write_text(json.dumps(check305,indent=2)+"\\n",encoding="utf-8")
        assert check305["passed"], "305 changed branch did not execute; measurement inadmissible"
        out["functional_validation"] = check305
'''
text=text.replace(end,check+end);ast.parse(text)
assert not entry.exists();entry.write_text(text,encoding='utf-8')
def fn_ast(src,name):
 tree=ast.parse(src)
 return next(ast.dump(n,include_attributes=False) for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name==name)
assert fn_ast(text,'act')==fn_ast(entry0.read_text(encoding='utf-8-sig'),'act')
put(R/'ADAPTER_REVIEW.json',{'at':now,'entry':str(entry),'entry_sha256':sha(entry),'base':str(entry0),'act_forcing_ast_identical':True,'changes':'two optional per-context mandatory final branch assertions; no forcing/source/scenario/measurement/lifecycle changes','guarded_main':True})
case=read(B/'sol/performance/cases/task179_1263e9e3_v2.json')
accepted=sorted(set(status['accepted_opus_numbers'])|{305})
case.update(case_id='task179-antic-deadline305-5df8711e',source=S,entry_file=str(entry),entry_sha256=sha(entry),
 source_review_file=str(R/'SOURCE_REVIEW.json'),source_packet_file=str(R/'SOURCE_PACKET.json'),source_packet_sha256=sha(R/'SOURCE_PACKET.json'),
 input_binding_file=str(R/'ACTIVE_INPUT_BINDING.json'),input_binding_sha256=sha(R/'ACTIVE_INPUT_BINDING.json'),accepted_reviews=accepted,
 contexts=[{'name':'l1_early_handoff','trial':str(B/'sol/demos/w13_walk179_20261105T222716Z_8f9e9629'),'from':2673,'last':2735,'flags':['--expect305=l1']},
 {'name':'l2_antic_approach','trial':str(l2),'from':2759,'last':2830,'flags':['--expect305=l2']}],
 scope='sameprofile serial fullP on both actually changed continuous windows; include first newSlam guard, geometric dash refusal, early recovery/ordinary and legacy J/D. Pure model continuation is not live action safety.')
put(B/'sol/performance/cases/task179_5df8711e.json',case)
raw=(M/REL).read_bytes();assert all((r/REL).read_bytes()==raw for r in (W,TV))
lines=raw.decode('utf-8').splitlines();assert '当前进度（11-05，7.171）' in lines[2]
lines[2]='2026-10-27 起草（历史审阅与阶段规格保留）。**当前进度（11-05，7.172）：305运行源5df8711e的接近时限/提前交还已有限源审，Sol9项直接事故回归通过；L2模型改为真实扫描拒绝冲刺后撤离，不能称已接刀成功；L1提前交还旧Slam脚本，modelhurt仍保留。Sol接两个受影响连续窗口P，旧P不重绑；暂不扩大air_direct弹起动画入口，当前无新game gate。179翻越/moving stomp与同iid第二锤现场仍未覆盖，178原有限验收保留。**'
section='''

#### #305接近时限/提前交还有限源审，Sol接两个受影响连续窗口P（11-05，进度7.172）

5df8711e仅改transfer.py、air表和9项直接事故测试；Root核完整增量及相邻规则、实际当前源hash，工作副本diff44342b621a61353b与提交运行增量同。Sol E24–31/Idle独跑9项1.32s通过；Opus820相关不重复。新时限复用已有CL_SLAM最早前冲47/60时钟及观测/拟合姿态并集，沿固定朝向/松键/可用一次dash的现有接近行，检查是否仍可能碰静止前摇身体。只影响是否花已有dash或提前放弃，不能把任一多边形碰撞当真实hit/安全。该“宽松”仅相对所列接近行/几何，不穷举未来所有D/A时序，非其它链都无解证书；未知沿旧当前步检查，不给False附加安全许可。原下劈行和facehook先尝试，新guard后排；Slam0/1不再新开无静止出刀域的接近。持有run恢复走原B2责任窗，未增动作/免伤豁免/放宽余量。

原L2片段首差异2761，3个实际成功前缀同、0强制/异常/外来，当前11hash匹配。dash选择分支确实进入原全owner锁定扫描，但遭几何否决，最终2761/2763普通L、2765普通DASH+L；2795不再向Slam0新开转移。后续到2830无modelhurt只是条件模型，不是已向右怪出刀或现场安全。原L1首差异2679（原2683），guard恢复由旧Slam接手R，2699J/2720A+D保持原绝对时钟；严格无hit/2729modelhurt保留。两条实际生产policy/planner/B2/最终before_send/sent路径有限核收，不强造不存在的成功dash放行。主179走路翻越/移动踩头及新同iid第二Slam现场均未覆盖，不被上述模型替代。

air_direct当前动画门不含DownSpikeBounce且活动转移持键期间不再询问，是既有能力边界。本次不扩大它：实际攻击冷却到2770才解除、旧入口k<=24只剩2770/71窄窗，且现有dash路径已被扫描否决；直接放开动画不是当前撤离修正的必要项，也不能据此宣称可接。后续如证据要求扩大，须另按现有入口语义/全危险/时序支持核，不偷偷改开关或加新动作池。

analysis/task179_5df8711e_20261105保存SOURCE_REVIEW、SOURCE_PACKET（710项/仅两运行与表文件变化、261模型不变）、ACTIVE_INPUT_BINDING、CHECKS及ADAPTER_REVIEW。固定executor不改，新adapter只加两上下文最终路由断言，act强制范围AST与已核v2相同；L1必须2679slam/R、2699J、2720A+D，L2必须2761真实dash拒绝且最终plan向左，防止P测回旧路径。case只测L12673..2735（含2675首次目标Slam守卫）和L22759..2830（含2761准入/否决/后继），同profile串行；不重测旧212/113/109或无关场景。新源入口先startup/finalize再独占P/finalize，原资源/5s静止/30s pulse/实际High4线程EcoQoS/真实清理门保持。当前没有新game gate，原L1/L2停止原件/NO_RETRY不动；Opus源码静止等SolP，不新增实现任务或ACK。
'''
new=('\n'.join(lines).rstrip()+section).encode('utf-8');atomic(M/REL,new);git(M,'add','--',REL);git(M,'commit','-m','docs: review approach deadline and prepare affected performance windows')
heads={str(M):git(M,'rev-parse','HEAD')}
for root in (W,TV):
 assert not git(root,'status','--porcelain','--untracked-files=no')
 atomic(root/REL,new);git(root,'add','--',REL);git(root,'commit','-m','docs: sync approach deadline review and performance scope');heads[str(root)]=git(root,'rev-parse','HEAD')
status.update(at=now,phase='TASK179_305_SOURCE_ACCEPTED_AWAIT_P',current_plan='7.172',current_head=heads[str(W)],current_plan_head=heads[str(W)],
 current_source=S,candidate_source=S,last_accepted_source=S,source_review_pending=False,source_review=str(R/'SOURCE_REVIEW.json'),
 accepted_opus_numbers=accepted,pending_opus='seq223 source/index static, Root305 affected2contexts P, no implementation task',
 active_blocker='305 source limited accepted; current-source2context continuousP pending; walking-vault and live action unverified. No game gate.',
 next_phase='fixedexecutor matching startup then affected2context formalP',next_watch_ready=False,next_trial=None)
atomic(B/'sol/STATUS.json',(json.dumps(status,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
letter='''## #305有限源审核收，当前不扩大air_direct；源码静止等两个受影响连续P（seq223）

计划7.172已同步，刀口HEAD {head}，runtime5df8711e。Root完整增量/相邻规则/实际工件diff44342b621a61353b已核，9直接事故测试通过1.32s，不重复820。两原点生产路径11hash当前同、无强制/异常/外来；L2核收的是dash真实扫描拒绝→最终ordinary撤离，不能当右怪接刀成功；L1原绝对J/D时钟及模型hurt/nohit照旧保留。SOURCE_REVIEW/SOURCE_PACKET/ACTIVE_INPUT_BINDING/ADAPTER_REVIEW在analysis/task179_5df8711e_20261105。

术语范围请后续报告保持：新guard只比较所列固定接近行，不枚举未来所有D/A时序；观测并集/任一多边形的“宽松”不是证明一切下劈都不可能，只作为提前交还导航判据。False未知沿旧检查，不能当新安全认证。不为这条文案小范围单独改源/交付。air_direct弹起动画本次不扩大；这不是当前撤离修正必需，原点冷却后仅两拍且dash已经被当前scan否决，不能直接放开当可接刀证书。

Sol复用冻结executor，新adapter只加路由断言、act forcing AST与已核v2同；正式P只两个完整连续窗：L12673..2735（含2675首次新Slam守卫、2679恢复、2699J/2720A+D）和L22759..2830（含2761dash拒绝/交还及后继），同profile串行。当前源/入口先matching startup+finalize再measure+finalize；没有新游戏门。现在源码/索引保持静止、不要并跑重算，STATUStrue按原约定只读；无新实现任务、不用ACK或唤醒。实际walking-vault/moving-stomp与同iid第二Slam仍未覆盖，178原有限验收不变，旧L1/L2不重开。

'''.format(head=heads[str(W)])
mail=B/'sol/TO_OPUS.md';atomic(mail,(letter+mail.read_text(encoding='utf-8-sig')).encode('utf-8'))
atomic(B/'sol/OPUS_WAKE.json',(json.dumps({'seq':223,'at':now,'task':179,'note':'305 source limited accepted, no air_direct expansion now; source/index static during Root2context matching startup/formalP. No new task/ACK/game.'},ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
put(R/'PLAN_SYNC_SOURCE_REVIEW.json',{'at':now,'plan':'7.172','heads':heads,'source':S,'seq':223,'new_game_gate':False})
print(json.dumps({'source':S,'plan':'7.172','case':str(B/'sol/performance/cases/task179_5df8711e.json'),'entry_sha256':sha(entry),'heads':heads,'seq':223},ensure_ascii=False))
