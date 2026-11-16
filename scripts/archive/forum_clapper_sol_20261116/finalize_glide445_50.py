"""Register a completed, audited one-batch authorization; never start another game."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, psutil

ROOT=Path('C:/modeling/silksong_bot')
B=Path('C:/ssbot/data/m2_play/clapper_plan')
G=B/'analysis/w13_50_glide_hold445_20261115'
A=B/'analysis/glide_jump_hold445_20261115'
R=B/'analysis/committed388_20261111'
D=B/'sol/demos'/G.name
PREV=B/'analysis/w13_50_middle_handoff434_20261114'
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
now=datetime.now(timezone.utc).isoformat()

def put(p,x):
    p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

result=read(G/'ROOT_50_RESULT.json')
clean=read(G/'ROOT_CLEANUP.json')
ver=read(G/'ACTUAL_VERSION_AUDIT.json')
gc=read(G/'RUNTIME_GC_AUDIT.json')
video=read(G/'VIDEO_RECEIPT.json')
base=read(PREV/'ROOT_50_RESULT.json')
assert clean['complete'] and clean['runtime_batch_complete'] and result['complete']
assert not result['mixed_source'] and ver['all_actual_switches_verified']
assert all(x['glide_jump_hold'] and x['middle_handoff'] and not x['extra_no_new_glide'] for x in ver['rows'])
assert gc['actual_quiet_collections']==50 and gc['generation2_in_combat']==0
hold=read(G/'DISPLAY_HOLD_CLOSED.json')
assert hold['released'] and not hold['error']
assert video['ffprobe_verified'] and video['encoder_returncode']==0
assert not (B/'sol/performance/ACTIVE.json').exists()
assert not any('silksong' in (x.info['name'] or '').lower() for x in psutil.process_iter(['name']))
for name in ['AUDIT_PROCESS.json','AUDIT_PROCESS_ROOT.json','AUDIT_PROCESS_ROOT2.json','SUMMARY_PROCESS.json']:
    identity=read(G/name)
    try:
        assert abs(psutil.Process(identity['pid']).create_time()-identity['created'])>.01, name
    except psutil.NoSuchProcess:
        pass
s=read(B/'sol/STATUS.json')
assert not s['live_or_budget_running'] and not s['own_live_session'] and not s['own_offline_jobs']
assert [x['seed'] for x in result['rows']]==[x['seed'] for x in base['rows']]
paired=[dict(bout=n['bout'],seed=n['seed'],old_pass=o['criterion_pass'],new_pass=n['criterion_pass'],old_HP=o['loss_hp'],new_HP=n['loss_hp']) for o,n in zip(base['rows'],result['rows'])]
comparison=dict(at=now,same_seeds=True,old_source=base['current_source'],new_source=result['current_source'],
    old_pass=base['pass_bouts'],new_pass=result['pass_bouts'],old_protect=base['protected_quit_bouts'],new_protect=result['protected_quit_bouts'],
    old_hitless=len(base['hitless_whole_bouts']),new_hitless=len(result['hitless_whole_bouts']),old_HP=base['loss_HP_total'],new_HP=result['loss_HP_total'],
    pass_delta=result['pass_bouts']-base['pass_bouts'],HP_delta=result['loss_HP_total']-base['loss_HP_total'],
    HP_reduction_fraction=1-result['loss_HP_total']/base['loss_HP_total'],
    gained_bouts=[x['bout'] for x in paired if x['new_pass'] and not x['old_pass']],lost_bouts=[x['bout'] for x in paired if x['old_pass'] and not x['new_pass']],
    rows=paired,limitation='One same-seed descriptive batch. Only GJH was newly enabled, but timing/closed-loop divergence is not controlled; stable or individually causal HP benefit is not established.')
put(G/'PAIRED_MH434_COMPARISON.json',comparison)
ready=read(D/'launch/WATCH_READY.json');go=read(D/'launch/WATCH_GO.json')
delay=(datetime.fromisoformat(go['at'])-datetime.fromisoformat(ready['at'])).total_seconds()
put(G/'START_RELEASE_DELAY.json',dict(at=now,ready_at=ready['at'],go_at=go['at'],ready_to_GO_seconds=delay,
    wrapper='C:/modeling/silksong_bot/tmp/launch_then_release.ps1',wrapper_runtime_verified=True,
    gates_repeated_or_removed=False,actual_source_input_capture_resource_and_FPS_gates_passed=True,
    startup_average_fps=read(G/'STARTUP_CADENCE_GATE.json')['fps']))
evidence=[G/n for n in ['ROOT_50_RESULT.json','ROOT_CLEANUP.json','ACTUAL_VERSION_AUDIT.json','RAW_AUDIT_COMPLETION.json','RUNTIME_GC_AUDIT.json','VIDEO_RECEIPT.json','SEGMENT_RESULT.json','PAIRED_MH434_COMPARISON.json','START_RELEASE_DELAY.json','POSTPROCESS_FAILURE_1.json','POSTPROCESS_FAILURE_2.json']]
summary=dict(at=now,batch=G.name,source=result['current_source'],authorized_attempts=50,actual_attempts=50,completed_bouts=50,
    authorization_consumed=True,another_batch_authorized=False,production_default_GJH=False,batch_GJH=True,production_default_MH=False,batch_MH=True,
    old_no_new_glide=False,criterion_pass=result['criterion_pass'],pass_bouts=result['pass_bouts'],pass_rate=result['pass_bouts']/50,
    both_killed=result['both_killed'],protected_quit_bouts=result['protected_quit_bouts'],postkill_protected_bouts=result['postkill_protected_quit_bouts'],
    hitless_bouts=result['hitless_whole_bouts'],HP=result['loss_HP_total'],deaths=result['real_deaths'],runtime_faults=0,
    all_source_and_switches_verified=True,actual_cleanup=True,video=video,comparison=comparison,
    postprocessing_repairs=['Git abbreviation validation now uses full source manifest plus actual file hashes; contract-bound original scripts unchanged.',
                           'One actual pre-bout Time.timeScale RPC value 0.9999990463256836 is within the existing runtime 1e-3 gate; inherited exact-equality assertion corrected in independent postprocessor.'],
    next_owner='Sol reports results; next repair scope and any new game require their own applicable authorization.',evidence={str(p):sha(p) for p in evidence})
put(G/'BATCH_FINAL.json',summary)
put(R/'RECEIPT445_GJH50.json',summary)
x=read(G/'BATCH_SPEC.json');x.update(at=now,state='COMPLETED50_AUDITED_TARGET_NOT_MET',ready=False,started=True,completed=True,
    criterion_pass=False,pass_bouts=result['pass_bouts'],protected_quit_bouts=result['protected_quit_bouts'],loss_HP_total=result['loss_HP_total'],authorization_consumed=True,
    display_request_released=True);put(G/'BATCH_SPEC.json',x)
x=read(A/'NEW50_PROPOSAL.json');x.update(at=now,state='COMPLETED50_AUTHORIZATION_CONSUMED',game_started=True,completed=True,authorization_consumed=True,
    final_result=str(G/'BATCH_FINAL.json'));put(A/'NEW50_PROPOSAL.json',x)
auth=read(G/'USER_NEW50_AUTHORIZATION.json');auth.update(started=True,completed=True,actual_attempts=50,authorization_consumed=True,completed_at=now)
put(G/'USER_AUTHORIZATION_CONSUMPTION.json',auth)
x=read(R/'REVIEW445.json');x.update(at=now,live50_completed=True,live50_receipt=str(R/'RECEIPT445_GJH50.json'),
    live50_target_passed=False,pass_bouts=result['pass_bouts'],protected_quit_bouts=result['protected_quit_bouts'],game_authorized=False,
    stage='Source/P/cleanup and one fresh50 completed; authorization consumed; all50-no-protection criterion not met. Default remains off.')
put(R/'REVIEW445.json',x)
s.update(at=now,phase='GLIDE445_50_COMPLETE_AUDITED_TARGET_NOT_MET',live_or_budget_running=False,own_live_session=None,own_offline_jobs=[],
    pending_user=None,pending_opus=None,authorized_batch=None,authorized_bouts=0,new50_authorized=False,new_game_gate=False,
    live_pause_released_only_for_batch=None,glide445_authorization_consumed=True,current_batch=G.name,current_demo=str(D),
    last_game_runtime=result['current_source'],glide445_final_receipt=str(R/'RECEIPT445_GJH50.json'),
    next_phase='Completed new50 results and original video for user review; no additional live authority; defaults unchanged.',
    active_implementation=None,next_owner='Sol: report completed50; then next scope per current user/project plan')
put(B/'sol/STATUS.json',s)
put(G/'POSTPROCESSING_PATH_BINDING.json',dict(at=now,contract_bound_scripts_unchanged=True,
    raw_originals_unchanged=True,audit_script=str(ROOT/'tmp/audit_glide50.py'),audit_sha256=sha(ROOT/'tmp/audit_glide50.py'),
    summary_script=str(G/'summarize_current50.py'),summary_sha256=sha(G/'summarize_current50.py'),
    metadata_assertion_failures_preserved=[str(G/'POSTPROCESS_FAILURE_1.json'),str(G/'POSTPROCESS_FAILURE_2.json')]))
msg=f'''## #445新50完整核收：38达标/40双杀/12保护/127HP，授权已耗尽；信息，无新派工/不唤醒

实际用户call_49b2fc217d5f486aab285ac17dccf204授权已执行完50盘。固定d6a36644、GJH1，MH1/AS1/LANDING_EXIT1及旧禁伞0同上一MH50，同50种子同序；同一游戏全程录像。GO {go['at']}，正常结束{read(G/'COORDINATOR_END.json')['at']}，死亡/运行故障0。

50逐盘原始审计和实际版本/开关核验完成：**38/50达标（76%），40双杀，12真实保护退出，其中第16、45盘是双杀后Q5退出；15无伤，总127HP**。主窗+尾窗损血与原始attempts逐例相符，不能把40 CLEAR当达标。前30=25达标/5保护/67HP，后20=13达标/7保护/60HP，源/关键开关全50一致。原判据“全50不触发剩余2HP退出”仍未过。

相邻MH434批：36达标/37双杀/14保护/8无伤/162HP；本批多2达标、少2保护、多7无伤、少35HP（约21.6%）。这是同种子单批描述，不证明稳定/单例因果收益，别把所有变化算GJH可救。PAIRED_MH434_COMPARISON、BATCH_FINAL、RECEIPT445_GJH50存证。默认GJH0/MH0及旧禁伞0保持，不封版、不自动新50、不扩模型/不落地等另包。

728运行文件/40先决未变；18自有进程真实退出，Prefs/golden/旧DEMO恢复，registry空，常亮已释放，无外来进程隔离/设置。50quietGC、战斗处理窗gen2=0；整拍110122拍p50/p99=13.24175/22.99314ms、max63.4488，仍非全域预算通过。录像58959帧/24fps，encoder0/ffprobe核同，{video['duration_display']}，{video['video']}。ready→GO实际{delay:.3f}s，launch→release包装本批真实验证，不再有上批漏release的327秒等待。

后处理两处继承断言已纠正，收据保留：实际Git短号是7位d6a3664，改用完整manifest HEAD+文件hash核；第8盘RPC timeScale=0.9999990463在既有运行门1e-3内，原审计的==1过严。只是独立后处理修正，合同脚本/控制器/原记录未改、不重打，先前完整审计按hash接续。当前50权限耗尽，下一步展示结果/用户看录像后按计划定下一包；无新的实现任务/唤醒。

---

'''
mail=B/'sol/TO_OPUS.md';t=mail.read_text(encoding='utf-8-sig');heading='# Sol → Opus 留言队列'
assert t.startswith(heading) and '#445新50完整核收：' not in t
mail.write_text(heading+'\n\n'+msg+t[len(heading):].lstrip(),encoding='utf-8')
section=f'''
### 7.384 #445伞内跳保持新50完成：38达标/40双杀/12保护，原全50目标未过（11-15）

实际用户call_49b2fc217d5f486aab285ac17dccf204授权一次新50，固定d6a36644/GJH1，其余MH1/AS1/LANDING_EXIT1及旧禁伞0同上MH434批，同种子同序、同一游戏全程录像。启动平均41.3239FPS过门，实际warm/input/worker/capture/资源收据齐；GO {go['at']}，正常结束{read(G/'COORDINATOR_END.json')['at']}，50实做/无死亡/无运行故障。ready至GO {delay:.3f}秒，launch→release包装实际成功，不再重复上批漏release等待。

逐盘原始审计含主窗+尾窗：38/50达标（76%）、40双杀、12真实保护退出；第16/45盘双杀后Q5保护，均未达标，不能按40CLEAR报告胜场；15无伤，127HP。前30=25达标/5保护/67HP，后20=13达标/7保护/60HP，全50源/实际关键开关一致。相邻MH434=36达标/14保护/8无伤/162HP；本批多2达标、少35HP约21.6%，仅同种子单批描述，未证稳定/单例因果收益。用户原“50盘不触发剩余2HP退出”目标仍未过。

728文件/40先决hash未变，18自有进程全退出，Prefs/golden/旧DEMO恢复、registry空、常亮释放，无外来隔离；50quietGC、战斗处理窗gen2=0。110122拍整拍p50/p99=13.24175/22.99314ms、max63.4488，非全域预算通过。原录像58959帧/24fps、40:56.6、ffprobe/encoder0核同，未裁剪/重写。BATCH_FINAL/RECEIPT445_GJH50/ACTUAL_VERSION_AUDIT/PAIRED_MH434_COMPARISON等登记。

两处后处理继承断言失败保留POSTPROCESS_FAILURE_1/2：Git7位短号被原8位限定拒绝，独立后处理改用完整HEAD+文件hash；第8盘RPC timeScale0.9999990463在既有运行门1e-3内，原==1过严。复用完整审计按hash接续，非控制/运行失败，不动合同脚本/原记录/旧冻结或AA。源码GJH/MH默认仍关、旧禁伞0；本次50授权耗尽，不自动续局或开新批。给Opus完整结果信息，无新派工/唤醒；当前下一步展示录像/按用户和主计划决定下一修复包。
'''
for root in [ROOT,Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot')]:
    f=root/'docs/plans/forum_clapper_plan.md'
    assert '### 7.384 ' not in f.read_text(encoding='utf-8-sig')
    with f.open('a',encoding='utf-8') as out:out.write(section)
(G/'RESULTS_FOR_USER.md').write_text(f'50盘完成：38盘达标（76%），12保护退出，15无伤，127HP；40双杀含第16/45盘双杀后保护，不计达标。\n\n上一批36达标/14保护/8无伤/162HP；本批多2达标，少35HP约21.6%。单批比较，稳定收益未确认；全50不保护目标未过。\n\n全50版本/开关一致，0死亡/运行故障，清理已核。录像：{video["video"]}（{video["duration_display"]}）。\n',encoding='utf-8')
print(json.dumps(dict(complete=True,pass_bouts=result['pass_bouts'],protects=result['protected_quit_bouts'],HP=result['loss_HP_total'],hitless=len(result['hitless_whole_bouts']),
    video=video['duration_display'],ready_to_GO_s=delay,new50_authorized=False,Opus_info_written=True,wake_sent=False),ensure_ascii=False))
