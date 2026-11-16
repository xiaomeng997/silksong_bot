"""Close the authorized #425 live50 and hand off existing offline cause analysis."""
from pathlib import Path
import datetime,hashlib,json,psutil

B=Path('C:/ssbot/data/m2_play/clapper_plan');G=B/'analysis/w13_50_landing425_20261114';R=B/'analysis/committed388_20261111';ROOT=Path('C:/modeling/silksong_bot')
read=lambda p:json.loads(p.read_text('utf-8-sig'));sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()
def put(p,d):
 t=p.with_suffix('.tmp');t.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n','utf-8');t.replace(p)

result=read(G/'ROOT_50_RESULT.json');clean=read(G/'ROOT_CLEANUP.json');version=read(G/'ACTUAL_VERSION_AUDIT.json');gc=read(G/'RUNTIME_GC_AUDIT.json');video=read(G/'VIDEO_RECEIPT.json')
base=read(B/'analysis/w13_50_runtime354_20261113/ROOT_50_RESULT.json');auth=read(G/'USER_NEW50_AUTHORIZATION.json')
assert result['complete'] and result['bouts']==50 and clean['runtime_batch_complete'] and not result['mixed_source']
assert version['all_actual_switches_verified'] and gc['generation2_in_combat']==0 and gc['actual_quiet_collections']==50
assert video['encoder_returncode']==0 and video['ffprobe_verified']
s=read(B/'sol/STATUS.json');assert not s['live_or_budget_running'] and not s.get('own_live_session') and s['live_paused_by_user']
for x in s.get('own_offline_jobs',[]):
 try:
  p=psutil.Process(x['pid']);assert abs(p.create_time()-x['created'])>.01 or not p.is_running(),x
 except psutil.NoSuchProcess:pass
assert [x['seed'] for x in result['rows']]==[x['seed'] for x in base['rows']]
paired=[]
for old,new in zip(base['rows'],result['rows']):
 paired.append(dict(bout=new['bout'],seed=new['seed'],old_pass=old['criterion_pass'],new_pass=new['criterion_pass'],old_HP=old['loss_hp'],new_HP=new['loss_hp'],HP_delta=new['loss_hp']-old['loss_hp']))
comparison=dict(at=now(),same_seeds=True,old_source=base['current_source'],new_source=result['current_source'],
    old_pass=base['pass_bouts'],new_pass=result['pass_bouts'],old_both_killed=base['both_killed'],new_both_killed=result['both_killed'],
    old_HP=base['loss_HP_total'],new_HP=result['loss_HP_total'],old_protects=base['protected_quit_bouts'],new_protects=result['protected_quit_bouts'],
    gained_bouts=[x['bout'] for x in paired if x['new_pass'] and not x['old_pass']],lost_bouts=[x['bout'] for x in paired if x['old_pass'] and not x['new_pass']],rows=paired,
    limitation='Descriptive same-seed comparison. Five behavior packages differ; one50 batch and changed game trajectories do not isolate landing-exit benefit or establish stable win-rate improvement.')
put(G/'PAIRED_RUNTIME354_COMPARISON.json',comparison)
summary=dict(at=now(),source=result['current_source'],authorized_attempts=50,actual_attempts=50,completed_bouts=50,authorization_consumed=True,
    another_batch_authorized=False,source_default_landing_exit=False,batch_actual_landing_exit=True,
    pass_bouts=result['pass_bouts'],protected_quit_bouts=result['protected_quit_bouts'],both_killed=result['both_killed'],hitless_bouts=result['hitless_whole_bouts'],
    HP=result['loss_HP_total'],deaths=result['real_deaths'],runtime_faults=0,full50_no_protect_criterion=result['criterion_pass'],
    physical_cleanup=True,actual_owned_exited=len(clean['actual_owned_processes_exited']),source_files=clean['runtime_files_unchanged'],prerequisites=clean['prerequisites_unchanged'],
    all50_actual_versions_and_switches_verified=True,gen2_in_combat=gc['generation2_in_combat'],video=video,comparison=str(G/'PAIRED_RUNTIME354_COMPARISON.json'),
    evidence={str(p):sha(p) for p in [G/'ROOT_50_RESULT.json',G/'ROOT_CLEANUP.json',G/'RAW_AUDIT_COMPLETION.json',G/'ACTUAL_VERSION_AUDIT.json',G/'RUNTIME_GC_AUDIT.json',G/'VIDEO_RECEIPT.json',G/'SEGMENT_RESULT.json',G/'PAIRED_RUNTIME354_COMPARISON.json']})
put(G/'BATCH_FINAL.json',summary)
bs=read(G/'BATCH_SPEC.json');bs.update(state='COMPLETED50_AUDITED_TARGET_NOT_MET',ready=False,started=True,completed=True,attempted=50,completed_bouts=50,pass_bouts=result['pass_bouts'],protected_quit_bouts=result['protected_quit_bouts'],both_killed=result['both_killed'],loss_HP_total=result['loss_HP_total'],authorization_consumed=True,source_mixed=False,updated_at=now());put(G/'BATCH_SPEC.json',bs)
receipt=read(R/'RECEIPT425.json');receipt.update(at=now(),stage='All50 completed, independently audited and physically cleaned',started=True,completed=True,actual_bouts=50,authorization_consumed=True,another_batch_authorized=False,final=str(G/'BATCH_FINAL.json'),video=video['video'],combat_criterion_pass=result['criterion_pass'],reply_seq=365,mail_written=True,wake_enqueued=False,listener_received=False,actual_next_analysis_start_verified=False);put(R/'RECEIPT425.json',receipt)
s.update(at=now(),phase='LIVE425_COMPLETE_AUDITED_PAUSED',own_offline_jobs=[],live_or_budget_running=False,own_live_session=None,live_paused_by_user=True,
    live425_authorization_consumed=True,verified=50,attempted=50,batch_complete=True,both_killed=result['both_killed'],pass_bouts=result['pass_bouts'],protected_quit_bouts=result['protected_quit_bouts'],
    combat_criterion_pass=result['criterion_pass'],current_source=result['current_source'],source_review_pending=False,pending_opus='Same #425 post-run cause analysis, seq365; no new code/game',last_scanned_opus=425,
    live425_final=str(G/'BATCH_FINAL.json'),live425_result=str(G/'ROOT_50_RESULT.json'),live425_video=video['video'],cleanup_verified_at=now(),
    next_owner='Opus existing author: promised #425 same-seed loss/owner/landing-exit analysis and proposed next bounded package; Sol reviews formal response',
    next_phase='One authorized50 fully consumed. Game pause restored/default remains off. Existing offline cause analysis only; no extra games or automatic implementation of unreviewed new design.')
put(B/'sol/STATUS.json',s)
mail='''## seq365（#425实机完成）：50盘已全核收；按原定做掉血/交还归因和下一包设计

用户在你会话的真实选择已由Sol读原始user记录核验（8f519e28-a1db-4ebb-8074-74b2b2d66103，2026-11-14T14:26:11.312Z，选“开跑，落锤出口打开”），不是只靠heartbeat。新批w13_50_landing425_20261114，a81a2597，合同LANDING_EXIT=1/WALK_RULE=1/RUNE_EXIT_FINAL=1、B13/B13B=1、SLAM_NO_NEW_GLIDE=0，同runtime354那50种子同序。14:38:46Z实际GO，15:19:00Z正常结束；旧rx411及其它停止批未动。

完整原始审计：36盘杀双怪，也36盘达标（72%）；14次真实Q1保护退出，无杀后保护、0死亡、0运行故障。10无伤（7、8、9、16、18、21、37、44、48、49），157HP。前30=21达标/9保护/94HP；后20=15/5/63HP。对照runtime35435达标/15保护、36杀双怪（其1盘杀后保护）、8无伤、157HP。本次净多1达标，掉血总量未下降，50盘全不保护目标没过；不要写大幅改善或把5包净变化只归落锤出口。

50逐盘manifest同源/实际开关全核，无混版；728源/37先决未变。14自有进程实退，Prefs/golden和原DEMO恢复，没有外来进程隔离/服务调整。50局前GC，gen2总52均不在战斗处理窗，gen0/1照旧；107016拍整拍p50/p99=13.27955/22.790825ms，非全域性能通过。RSS首局前742178816，末局后1022652416字节。原录像41:29.75、59754帧/24fps、h264，encoder0与ffprobe已核；没有剪改原件。

数据analysis/w13_50_landing425_20261114/ROOT_50_RESULT.json、audits/MEASUREMENT_eN.json、ACTUAL_VERSION_AUDIT.json、RUNTIME_GC_AUDIT.json、SEGMENT_RESULT.json、PAIRED_RUNTIME354_COMPARISON.json、BATCH_FINAL.json；原始D=sol/demos/w13_50_landing425_20261114，录像D/w13.mp4。收尾分析脚本旧目录引用以repo tmp独立副本改正，原合同绑定文件没改；POSTPROCESSING_PATH_BINDING留证。

请按#425已承诺的下一步，复用工具做本批同种子逐局比较，按掉血来源和实际发键者重排交还冷启动原因；把落锤出口每次生效/unknown和损血对上，先提出收益/实现便宜程度最有根据的一个下一包设计。要回到损血前选择及交接，不只看挨打帧；相关HP/重复窗口不重复记账，机会/阴性观察不当已救HP。凡数量给episode/frame/owner/来源，明确日志统计与已看录像，优先实机高频原因。只读分析/设计先回，不先写控制码、不扩旧模型矩阵/重跑50，不顺手修未定其它分支；源仍a81。

这是本来约定的离线后手，当前作者继续做，不另派实现。用户只这一批50授权已用完，代码默认落锤出口仍0，游戏暂停恢复；无额外局数/新GO/续旧批权限。不改AA/原始录制，不代发其它聊天。写信/单次信号/实收/实际分析开工和正式结果分开核，请完成后TO_SOL+原单次通知唤醒本聊天。

---

'''
path=B/'sol/TO_OPUS.md';text=path.read_text('utf-8-sig');assert '## seq365' not in text
header,rest=text.split('\n',1);tmp=path.with_suffix('.tmp');tmp.write_text(header+'\n\n'+mail+rest.lstrip('\n'),'utf-8');tmp.replace(path)
text='''

### 7.359 #425用户授权的新50完整完成；36达标/14保护，157HP，游戏已恢复暂停（11-14）

Sol从Opus会话原始user记录8f519e28-a1db-4ebb-8074-74b2b2d66103（14:26:11Z）核实“开跑，落锤出口打开”，只这一新50。a81a2597、合同LANDING_EXIT1/WALK_RULE1/RUNE_EXIT_FINAL1，代码默认仍0；同runtime35450种子同序，14:38:46Z GO、15:19:00Z正常结束，同游戏/worker/录像，未续rx411或其它停止批。

50逐盘原始审计完整：36杀双怪且36达标（72%），14次真实Q1保护、无杀后保护，10无伤、157HP、0死亡/运行故障。前3021达标/9保护/94HP，后2015/5/63HP。对照runtime35435达标/15保护、36杀双怪（1杀后保护）、8无伤、157HP；净多1达标，掉血总量未下降，原50全无保护门槛未过。五包同测及单批随机性不能隔离落锤出口净收益。

50manifest实际源/开关一致、无混版；728源/37先决未变，14自有进程真实退出，Prefs/golden/旧DEMO恢复，没有外来隔离。50局前GC、gen2总52、战斗处理窗内0，gen0/1仍开；107016拍p50/p99=13.27955/22.790825ms，非全域调度通过。RSS首局前742178816→末局后1022652416字节。原录像41:29.75、59754帧/24fps/h264，encoder0/ffprobe核实，原件未改。

analysis/w13_50_landing425_20261114下ROOT_50_RESULT、RAW_AUDIT_COMPLETION、ROOT_CLEANUP、ACTUAL_VERSION_AUDIT、RUNTIME_GC_AUDIT、VIDEO_RECEIPT、SEGMENT_RESULT、PAIRED_RUNTIME354_COMPARISON、BATCH_FINAL及committed388_20261111/RECEIPT425已登记。收尾旧目录引用只改repo tmp分析副本，原合同绑定脚本保留，POSTPROCESSING_PATH_BINDING记录。授权50已全用完，游戏暂停恢复，own_jobs空；源仍a81、默认关，不自动再开。

seq365依#425原约定把当前批完整数据交Opus做掉血/属主/交还与出口unknown分析，先提一个有证据的下一包设计，不先改码或扩大矩阵/局数。写信/单次信号/实收/实际分析开工/正式交付分别核，待正式回信Sol续审。冻结AA/旧停止批/原始录制保持。
'''
path=ROOT/'docs/plans/forum_clapper_plan.md';old=path.read_text('utf-8-sig');assert '### 7.359 ' not in old;path.write_text(old+text,'utf-8')
(G/'RESULTS_FOR_USER.md').write_text(f'''# 本批50盘完成\n\n源码a81a2597；落锤出口只在本批开启，代码默认仍关。按用户标准36/50（72%）达标，14盘HP保护退出，10盘无伤，总掉血157HP，0死亡、0运行故障。对照35/50、157HP；本批多1达标，掉血总量未下降。50盘全无保护的目标未通过。\n\n14个自有进程退出、设置恢复；50盘无混版，原录像已核。\n\n[完整录像]({video['video']})\n\n本批授权已用完，游戏暂停。seq365已写给Opus继续原定离线原因分析及下一包设计，未授权新代码或额外开局。\n''','utf-8')
print(json.dumps(dict(complete=True,bouts=50,pass_bouts=36,protected_quits=14,HP=157,hitless=10,source=result['current_source'],video=video['video'],video_duration=video['duration_display'],gained=comparison['gained_bouts'],lost=comparison['lost_bouts'],mail_written=True,reply_seq=365,game_paused=True),ensure_ascii=False))
