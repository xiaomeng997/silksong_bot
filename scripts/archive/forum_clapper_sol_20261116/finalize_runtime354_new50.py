from pathlib import Path
import datetime, hashlib, json, os, psutil

B=Path('C:/ssbot/data/m2_play/clapper_plan')
G=B/'analysis/w13_50_runtime354_20261113'
A=B/'analysis/runtime354_20261113'
D=B/'sol/demos'/G.name
R=B/'analysis/committed388_20261111'
read=lambda p:json.loads(p.read_text('utf-8-sig'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()
def put(p,d):
    q=p.with_suffix('.tmp');q.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n','utf-8');os.replace(q,p)

def main():
    result=read(G/'ROOT_50_RESULT.json');cleanup=read(G/'ROOT_CLEANUP.json')
    gc=read(G/'RUNTIME_GC_AUDIT.json');video=read(G/'VIDEO_RECEIPT.json');probe=read(A/'REAL_RUNTIME_PROBE_AUDIT.json')
    assert result['complete'] and result['bouts']==50 and cleanup['runtime_batch_complete']
    assert probe['passed'] and gc['generation2_in_combat']==0 and gc['actual_quiet_collections']==50
    assert not result['mixed_source'] and read(G/'ACTUAL_VERSION_AUDIT.json')['all_actual_switches_verified']
    s=read(B/'sol/STATUS.json');assert not s['live_or_budget_running'] and not s.get('own_live_session')
    for x in s.get('own_offline_jobs',[]):
        try:
            p=psutil.Process(x['pid'])
            assert p.create_time()!=x['created'] or not p.is_running(),x
        except psutil.NoSuchProcess:pass
    summary=dict(at=now(),source=result['current_source'],authorized_max_attempts=51,actual_probe_attempts=1,actual_fresh_batch_attempts=50,
        actual_runtime_probe_pass=True,actual_new50_runtime_complete=True,physical_cleanup_verified=True,
        quiet_GC_bouts=50,generation2_in_combat=0,combat_criterion_pass=result['criterion_pass'],both_killed=result['both_killed'],
        pass_bouts=result['pass_bouts'],protected_quit_bouts=result['protected_quit_bouts'],postkill_protected_quit_bouts=result['postkill_protected_quit_bouts'],
        hitless_bouts=result['hitless_whole_bouts'],loss_HP_total=result['loss_HP_total'],real_deaths=result['real_deaths'],
        full_scheduling_gate_pass=False,new_replay_P_pass_claimed=False,
        validation_scope='Actual worker lifecycle probe and one continuous50. No global safety/stability or isolated win-rate causality claim.',
        evidence={str(p):sha(p) for p in [A/'REAL_RUNTIME_PROBE_AUDIT.json',G/'ROOT_50_RESULT.json',G/'RAW_AUDIT_COMPLETION.json',G/'ROOT_CLEANUP.json',G/'ACTUAL_VERSION_AUDIT.json',G/'RUNTIME_GC_AUDIT.json',G/'VIDEO_RECEIPT.json',G/'SEGMENT_RESULT.json']})
    put(A/'RUNTIME_VALIDATION_FINAL.json',summary)
    put(R/'RECEIPT410_RUNTIME.json',dict(**summary,delivery=410,seq354_runtime_repair_closed=True,implementation_source_review_already_closed=True,new_live_authorization_consumed=True,another_batch_authorized=False))
    bs=read(G/'BATCH_SPEC.json');bs.update(state='COMPLETED50_AUDITED_RUNTIME_PASS_COMBAT_TARGET_NOT_MET',ready=False,started=True,completed=True,attempted=50,completed_bouts=50,both_killed=36,pass_bouts=35,protected_quit_bouts=15,postkill_protected_quit_bouts=[11],loss_HP_total=157,source_mixed=False,updated_at=now());put(G/'BATCH_SPEC.json',bs)
    (G/'RESULTS_FOR_USER.md').write_text('''# runtime354：短故障验证及新50盘完成

c3a55b78。短验证1次：160ms注入实际执行，LearningStop后松键/冻结19.028ms，读回timeScale=0.0001；随后保持冻结清理。预期HARNESS_FAIL和不完整测量原样保留，不当战斗通过。14个自有进程全退。

新50同一游戏连续完成、逐盘原始审计齐全：36盘击杀双怪；按“击杀且不触发2HP保护”标准35盘达标（70%），15次实际保护退出，其中第11盘为击杀后保护退出。8盘无伤（2、4、8、12、16、25、33、37），157HP，0死亡、0运行故障。前30达标21，后20达标14，均70%。原定50盘全不触发保护的目标未通过。

逐盘版本及B13/B13B=1、额外冲锤禁开伞=0核实，无混版。50次局前回收，最终累计诊断52次gen2均在战斗处理窗口外；战斗窗口内gen2为0。gen0/1仍开启。实际整拍p50/p99为13.2934/22.585888ms，不是全局调度通过或新回放P结论。RSS首局前740917248字节，末局后1024155648字节；不据一批证明全域无增长。

727运行文件/36先决在关局清理时未变，14个自有进程全部退出，Prefs及原DEMO恢复。录像h264、960×562、24fps、60631帧，42:06.3，1144495146字节，encoder0，原件未改。

[完整原录像](C:/ssbot/data/m2_play/clapper_plan/sol/demos/w13_50_runtime354_20261113/w13.mp4)

下一行为方向仍是#408用户所定：被N隔着F的接招先移入新刀链、保留原分支，再改打法，排冷交还第3项之前。无额外局数授权；旧40停止批与原录像未动。
''','utf-8')
    s.update(at=now(),phase='RUNTIME354_PROBE_AND_NEW50_COMPLETED_AUDITED',own_offline_jobs=[],live_or_budget_running=False,own_live_session=None,
        verified=50,attempted=50,batch_complete=True,both_killed=36,pass_bouts=35,protected_quit_bouts=15,combat_criterion_pass=False,
        current_source=result['current_source'],source_review_pending=False,pending_opus=None,last_scanned_opus=410,last_scanned_opus_number=410,
        runtime354_final=str(A/'RUNTIME_VALIDATION_FINAL.json'),runtime354_result=str(G/'ROOT_50_RESULT.json'),runtime354_video=video['video'],
        runtime354_cleanup=str(G/'ROOT_CLEANUP.json'),cleanup_verified_at=now(),next_owner='Opus: existing separated-response chain migration design; Sol: source/design review on actual delivery',
        next_phase='User-authorized1probe+50 fully consumed. Await video feedback or new design delivery; no further game started. Existing #408 behavior priority preserved.');put(B/'sol/STATUS.json',s)
    p=B/'sol/TO_OPUS.md';old=p.read_text('utf-8-sig');header='''## #410运行实机验证与新50已完成（信息收据，无新任务/唤醒）

当前聊天明确授权1次短验证+通过后新50，已全部实际执行。c3a55b78探针160ms已触发，松键/真实冻结19.028ms，readback0.0001，kept_frozen清理14进程全退；预期HARNESS_FAIL/不完整测量保留。新50正常完整结束，无运行故障；50次局前GC，累计52次gen2都不落在实战处理窗口内。源727/先决36关局时未变，50逐盘开关/实际源全核。

36盘杀双怪，其中11盘号击杀后Q1退出；按用户标准35达标/15实际保护（含该1局），8无伤/157HP/0死。前30达标21、后20达标14，各70%。全批不触发保护未达标，不把36与35混说。全程录像42:06.3。资料analysis/runtime354_20261113/RUNTIME_VALIDATION_FINAL.json及analysis/w13_50_runtime354_20261113/ROOT_50_RESULT.json、RUNTIME_GC_AUDIT.json、RESULTS_FOR_USER.md。源/组件/实际生命周期这包关闭，无新回放P/全域调度声明；旧40不动。本次最多1+50授权已消费，无额外开局。#408隔怪接招先迁新链再改的用户优先级继续，不另派代码任务，不另发唤醒。

---

'''
    old=old.replace('# Sol → Opus 留言队列\n\n','# Sol → Opus 留言队列\n\n'+header,1);q=p.with_suffix('.tmp');q.write_text(old,'utf-8');os.replace(q,p)
    p=Path('C:/modeling/silksong_bot/docs/plans/forum_clapper_plan.md');t=p.read_text('utf-8');assert '### 7.343 ' not in t
    t+='''
### 7.343 #410实际故障探针通过，新50完整收齐：运行修复通过、战斗目标未过（11-13）

用户当前聊天call_805feb3b回复“验证通过后连打新50盘（推荐）”，最多1+50局，本次全消费。c3a55b78短探针实际GO17:36:35 UTC，tick200注入160ms后触发原四帧LearningStop，松键与timeScale0.0001真实读回共19.028ms；kept_frozen清理。预期HARNESS_FAIL及measurement不完整保留，不冒称完整战斗/测量通过。独立物理核14进程全退、设置恢复及源不变。REAL_RUNTIME_PROBE_AUDIT已写后才准备新50。

新50实际GO17:40:38 UTC，18:22结束，原50种子同序、同一游戏/worker，无运行故障。独立原始50审计完整：36盘杀双怪，第11盘杀后Q1，按原“无实际2HP保护退出”标准35达标/15保护（含该1盘），8无伤、157HP、0死。前30为21达标/9保护/90HP，后20为14达标/6保护/67HP，两段各70%。全50不触发保护未过，暂记36胜/14QUIT的初始口径已由杀怪与实际保护两维更正；不重复计局。

50实际manifest同源、B13/B13B=1、额外冲锤禁开伞=0、High/P0–15/Numba4，无未知/未解析开关。727运行文件/36先决关局时未变，14自有进程全退，Prefs/原DEMO恢复。50次局前回收阈值[2000,10,10000]开启GC；最终累计诊断gen2共52，按实际处理首末拍墙钟的战斗窗内0，gen0/1仍开启；不泛化全域不可能触发。111897拍p50/p99=13.2934/22.585888ms，非新回放P或全局调度门通过。RSS首局前740917248→末局后1024155648字节，增长照记。

原录像42:06.3、60631帧/24fps、960×562/h264、1144495146字节，encoder0/ffprobe核实，未改原件。analysis/runtime354_20261113/RUNTIME_VALIDATION_FINAL、w13_50_runtime354_20261113的ROOT_50_RESULT/ACTUAL_VERSION_AUDIT/RUNTIME_GC_AUDIT/VIDEO_RECEIPT/SEGMENT_RESULT已登记。#410源组件及实际运行修复关闭，保留全域门false；停止40不重开，原AA/录制不变，无额外游戏授权。#408下步仍为隔怪接招先迁新刀链、再改打法，先于冷交还第3项；Opus仅信息收据无新唤醒。
''';p.write_text(t,'utf-8')
    print(json.dumps(dict(complete=True,bouts=50,pass_bouts=35,protected_quits=15,both_killed=36,hitless=8,HP=157,gen2_in_combat=0,video=video['video'],minutes=video['duration_display']),ensure_ascii=False))

if __name__=='__main__':main()
