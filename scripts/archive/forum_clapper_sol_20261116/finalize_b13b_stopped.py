from pathlib import Path
import datetime,json
B=Path('C:/ssbot/data/m2_play/clapper_plan');G=B/'analysis/w13_50_b13b404_20261113';D=B/'sol/demos'/G.name;R=B/'analysis/committed388_20261111'
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
stamp=datetime.datetime.now(datetime.timezone.utc).isoformat()
def put(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def main():
 h=read(G/'FAULT_HANDOFF.json');h.update(work_started_verified=True,work_started_evidence='Actual Opus gc404_scan/tid.py and .txt after seq353 inspect current GC/TID/receive timings. Not formal completion.');put(G/'FAULT_HANDOFF.json',h)
 r=read(G/'ROOT_PARTIAL_RESULT.json');r.update(real_deaths_scope='Zero in completed39 only; no zero-death claim about interrupted40 post-stop tail.',post_stop_tail=dict(user_reported_death=True,source='User via TO_SOL407',video_independently_checked=True,HUD_health_minus8_seconds=3,HUD_health_minus3_seconds=1,HUD_health_final_frame=1,death_frame_independently_seen=False,observed_additional_HP_after_fault_at_least=2,raw_measurement_not_extended_or_filled=True));put(G/'ROOT_PARTIAL_RESULT.json',r)
 put(G/'VIDEO_RECEIPT.json',dict(at=stamp,video=str(D/'w13.mp4'),bytes=941447158,duration_seconds=2045.5,duration_display='34:05.5',fps=24,frames=49092,width=960,height=562,codec='h264',encoder_returncode=0,ffprobe_verified=True,raw_video_unmodified=True,includes_warm_hold_and_post_stop_tail=True,tail_frame_checks=[str(G/n) for n in ['poststop_minus8.png','poststop_minus3.png','poststop_final.png']]))
 bs=read(G/'BATCH_SPEC.json');bs.update(state='STOPPED_HARNESS_FAIL_NO_RETRY',ready=False,started=True,completed=False,attempted=40,completed_bouts=39,pass_bouts=29,protected_quit_bouts=10,unstarted_bouts=10,HP_completed39=128,HP_fault40_observed_in_raw=4,post_stop_damage_outside_measurement=True,source_mixed=False,updated_at=stamp);put(G/'BATCH_SPEC.json',bs)
 put(G/'STOPPED_NO_RETRY.json',dict(at=stamp,source=r['source'],batch=G.name,first_fault_bout=40,first_fault_episode=39,stop_frame=123318,reason='missing critical application receipt beyond four-frame upper bound',batch_may_not_reopen=True,unstarted_bouts=list(range(41,51)),next_game_requires_new_bounded_authorization=True,raw_fault_retained=True))
 put(R/'RECEIPT406.json',dict(at=stamp,delivery=406,authorization_accepted=True,current_chat_direct_reply_received=True,same_batch_not_extra50=True,batch=G.name,source=r['source'],game_started=True,strict_stop_at_bout=40,complete50=False,partial_result=str(G/'ROOT_PARTIAL_RESULT.json'),physical_cleanup_verified=True))
 put(R/'RECEIPT407.json',dict(at=stamp,delivery=407,report_read=True,post_stop_damage_independently_seen=True,user_reported_death=True,death_frame_independently_seen=False,guard_stop_preserved=True,GC_fault_investigation_seq=353,source_code_changed=False,review='Physical cleanup verified; game remained unpaused during shutdown and tail censored. Safe-stop behavior needed before new live release.'))
 put(R/'RECEIPT408.json',dict(at=stamp,delivery=408,user_scope_record_received=True,next_behavior_priority='Migrate separated F-behind-N response to new chain before cold-handoff3; preserve branches first, tactics afterward.',implementation_owner='Opus own worktree under user scope',current_frozen_source_unchanged=True,no_new_live_authorization=True,design_review_pending=True))
 (G/'RESULTS_FOR_USER.md').write_text('''# B13+B13B：第40盘故障停批

完整39盘：29胜、10次保护退出、7盘无伤，掉血128。第40盘关键输入回执超时严格停批；故障前观察到4HP，测量不完整；41–50盘未开。

同种子前39盘旧版27胜、130HP、6无伤；本版29胜、128HP、7无伤。只是39个种子的描述比较，不是完整50或B13单独因果证明。

实际40盘均e7e975f3，B13/B13B=1、额外禁开伞=0；726源文件/57先决未变，14受控进程真退，设置及原DEMO恢复。录像34:05.5正常封尾。

同窗68.481ms gen2自动GC，123311状态在GC后才进入控制；发送123313时最新已123315，随后超过原四帧回执上界。seq353已实际收信/开工，正式结论尚待；不放宽门、不重开停止批。

录像末尾可见3HP变1HP。用户报告之后被打死，最后提取帧仍1HP，未独立看到死亡帧；未知尾段不计0伤。#407安全停机缺口已记；#408用户下步为隔怪接招先迁新刀链、再改打法，排冷启动之前。

[34分05秒原录像](C:/ssbot/data/m2_play/clapper_plan/sol/demos/w13_50_b13b404_20261113/w13.mp4)
''',encoding='utf-8')
 s=read(B/'sol/STATUS.json');assert not s['live_or_budget_running'] and not s.get('own_offline_jobs') and not s.get('own_live_session')
 s.update(at=stamp,phase='B13B404_STOPPED40_RESULTS_REGISTERED',last_scanned_opus=408,last_scanned_opus_number=408,pending_opus=dict(seq=353,state='listener_received_and_actual_work_verified_completion_pending',task='Bounded receipt/GC fault investigation, no guard relaxation/retry'),b13b50_result=str(G/'ROOT_PARTIAL_RESULT.json'),b13b50_video=str(D/'w13.mp4'),b13b50_complete=False,opus407_state='post_stop_damage_seen_safe_stop_gap_recorded',opus408_state='user_next_behavior_scope_received_design_review_pending',next_phase='Review seq353 formal cause/proposal; stopped batch closed. Next behavior: separated response migration before cold handoff.');put(B/'sol/STATUS.json',s)
 p=Path('C:/modeling/silksong_bot/docs/plans/forum_clapper_plan.md');t=p.read_text(encoding='utf-8');assert '### 7.340 ' not in t
 p.write_text(t+'''
### 7.340 #407停机尾段受击及#408用户下步顺序已收，40盘源/动作/录像登记（11-13）

40盘manifest逐盘核e7e975f3、B13/B13B=1、额外禁伞=0、主High/P0–15/Numba4，无混版/未知或未解析配置；源726/先决57稳定。完成39盘88954拍整拍p50/p99=13.0026/22.550105ms，STATE入队等待不含在本拍成本。40盘真实proposal/selected/wire核到B13 strike38、steer2、B13B release1/guard5；发键不当命中/救回HP。ACTUAL_VERSION_AUDIT/EVENT_SUMMARY已写。

录像ffprobe核34:05.5、49092帧/24fps、960×562/h264、941447158字节，encoder0，原件未改。#407用户报告停后被打死；Sol独提末尾8秒/3秒/末帧见HUD3→1，最后仍1，未独见死亡帧。原始故障前4HP与停后可见至少2HP分开；未知尾窗不填0，0死只限完成39盘。物理清理通过不等于及时冻结，安全停机缺口保留。

seq353监听7:51:09实际收到、mail marked seen，gc404_scan/tid.py及结果实际写出，正式结论尚待，不以收信/开工替完成。#408用户原话112–116：N隔着F时先迁新刀链再改打法，排冷启动第3项之前；Opus设计/自己树，不改本冻结源；方案待独审，没有新实机授权。RECEIPT406/407/408、RESULTS_FOR_USER、VIDEO_RECEIPT已登记；停止批不重开。登记辅助脚本首次因时间字段str被调用而退出，修正后完成，不是运行/原始审计失败。
''',encoding='utf-8')
 print(json.dumps(dict(complete39=39,wins=29,protected=10,hitless=7,full50=False,video='34:05.5',version_verified=40,handoff_actual_work=True,formal_reply_pending=True)))

if __name__=='__main__':main()
