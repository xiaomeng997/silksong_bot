from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json

B = Path('C:/ssbot/data/m2_play/clapper_plan')
R = B / 'analysis/committed388_20261111'
WT = Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot')
H = 'b74140e0d627fac263606a642461fde27fd44b77'
BASE = 'e097f60e42c518eb962782e71c0680ba543016a9'
now = datetime.now(timezone.utc).isoformat()
sha = lambda p: hashlib.sha256(Path(p).read_bytes().replace(b'\r\n', b'\n')).hexdigest()
hashes = {f: sha(WT/f) for f in ['brain/ssbot/combat/rune_hook_exit.py', 'brain/tests/test_rune_hook_exit.py',
                               'brain/ssbot/combat/knife_chain_empty_needle.py', 'brain/ssbot/train/forum_planner_policy.py']}
assert hashes['brain/ssbot/combat/rune_hook_exit.py'] == '559e26d59ca5e8f1f13c7f20624b90194e3ae9ccd4f77cb3d7eb5025c0d28ca3'
assert hashes['brain/tests/test_rune_hook_exit.py'] == 'ca5936505312e47b08e981369ed0dc2e4bf77740fb31e2a1976888eb6800f333'
proof = dict(at=now, source=H, source_LF_sha256=hashes, WT_commit_P13_bound=True,
    root_review='Incremental two-file diff, existing contact_body_witness hull API/domain, targeted test source and author output; no broad rerun',
    prior_false_edges_rechecked=[dict(case='sup overrides CHAIN candidate then plan', old_h1=True, new_h1=False),
                                dict(case='first-known target already Evade', old_h2=True, new_h2=False, status='unknown: no previous state')],
    existing_output_comparison=dict(pair=['f11_off','f13_rec'], decisions=[1359,1359], same_frame_keys=True,
        differences=0, journal=[4077,4077], journal_equal=True, keys_equal=True,
        decision_SHA256=['013a20c96f8ddd080064e9516c84310603729ff8389efab4f6af85f9e05de991',
                         'f661285feebee3e583828aaf05b506468ea55e84a19bfa71e1bc26c6b0661267'],
        rhx_entries=3, rhx_intersections=0, rhx_H2=5),
    analysis_only_allgate=dict(tree='P14, declared read-only extra diagnostic call, production file unchanged',
        common_gate_ticks=18, admissible=0, frame104247='body route unknown for 3877546 (Slam Recover)',
        frame104251='body route unknown for 3877546 (Slam Recover)', frame104260='body route unknown for 3877546 (Idle)'),
    author_tests_read=45, root_repeated_author_tests=False, formal_P=False, new_game=False)
(R/'ROOT455_CLOSURE_CHECK.json').write_text(json.dumps(proof, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
review = dict(at=now, delivery=455, task=382, source=H, parent='906f87d7c5f6276f160a574ce2d2d3f05b960405',
    accepted=True, accepted_scope='Narrowed grounded-still-body pure admission plus default-off/record-only source; NOT active executor or live readiness',
    source_review_pending=False, prior_P2_groups_closed=3, source_LF_sha256=hashes,
    closure=dict(A='Both physical/rendered lanes scan body regions, occupied, runes and sideways exit; outer physical-only ram regression read',
                 B='CV targets removed; existing fitted safety hull witness used, full route unavailable -> unknown reject; domain explicitly narrowed',
                 C='Actual owner and known same-iid previous state required; event identities kept; two root counterexamples now false'),
    actual_key_owner_changed=False, active_mode_1_refused=True, author_tests_read=45,
    root_proof=str(R/'ROOT455_CLOSURE_CHECK.json'),
    engineering_cost_ms=dict(Forum_p50=43.32, Forum_max=64.37, one_still_body_p50=53.85),
    formal_P_started=False, performance_budget_pass=False, full_scheduling_gate_pass=False,
    live_ready=False, game_authorized=False, active_trigger_approved=False,
    original_b35_application_not_supported=True, old_P12_C1_admissible_claim_invalidated=True,
    next_owner='Opus same-task382 bounded existing-body-support feasibility/design proposal only',
    wake_seq_expected=389, wake_enqueued=False, listener_received=False, actual_author_started=False)
(R/'REVIEW455.json').write_text(json.dumps(review, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
p = R/'REVIEW454.json'; d = json.loads(p.read_text(encoding='utf-8'))
d.update(repair_closed_by_delivery=455, repair_closed_by_source=H, prior_P2_groups_closed=True,
         formal_repair_completion_verified=True, original_906_source_accepted=False)
p.write_text(json.dumps(d, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

title = '## seq382回#455：三组回修按收窄域核收；下一步仅查现有身体预报可用性（信号389），不写新策略'
body = '''
Sol已独立增量核b74140e0（父906）两文件差分、contact_body_witness(hull=True)的真实域、45受影响测试源码/两份通过记录与commit/WT/P13绑定；未重跑原45。**三组P2闭合，核收限定为纯准入+default0/record2源码，不等于完整空钩、活跃触发、实际可用或成本通过。**针模块/policy未变，已核的其它材料按源有限续用。

两路的动态体/ray/ram/伤害/大小符文/横向出圈接线已读，物理ram外层反例有意义；恒速targets已去，现有拟合安全hull提供全段、不够就unknown，明确只适用于足够长的落地静止状态；H1实际最终占键、H2已观测同iid前态、事件自身身份字段成立。Sol上一轮两个隔离反例在新源均为false，未调用准入/回放。真实b35失败事件target3877540保留，不用当前焦点补身份。两次记录gap至多3帧的语义是记录间的变化，别把它称精确游戏帧边沿。

Sol独立只解析现有f11_off/f13_rec结果：1359决策、4077最终及发送记录0差、keys同，rhx entry3/交集0/H2 5；原历史强制口径和tool未解析调度限制保持，不能当真实worker/准时/游戏接受或HP证据。也核P13→P14只有显式分析调用，在18个共同门拍全部body route unknown；247/251是左怪Slam Recover，260是Idle。旧P12在247–251可准入依赖恒速框，按新口径作废，C1也没有真实准入正例。收窄域是当前正确拒绝，不为凑正例放开未知。

工程全查Forum中位43.32/max64.37ms、带一只静止路线怪53.85ms已读。现在不用排正式P去重证明显昂贵，也不把record2放进实机；发键/执行器/C1均未获实现批准。本聊天全部50权限耗尽，没有新游戏/50。当前已实机源仍e097，b741登记为离线限定源核收，不偷偷切换游戏配置。

**同一包下一步只做一个有界可用性/设计答复，暂不改生产代码、不先做异步或性能大迁移：**
1. 用已经有的b35最高点单窗，重点247–251以及首次交还241。查现有V2/RangeSupport/刀链接口能否给Evade、收招→Idle这类怪提供同拍、带身份和未知界限的身体路线/支持集。列真实接口、已覆盖时段、先在哪一格变未知及原因；区别整段确实有支持、只有恒速框、只有英雄中心occupied这三种。不得把后两种换名当已解决，别读录像未来冒充本拍预测。
2. 如果没有整段路线，现有已审数据是否足以证明某个未知时段根本够不到空钩的身体/针/ram区域？只能引用已有可核的速度/位置/姿态界限，缺证据就说缺，不能先发明新模型/余量。按当前物理+渲染准入口径，只有现成材料能支持时才在这个窗口做最少离线几何确认；不扫三批、不重跑173、不先广跑成本。若可用支持接口本就足够，给最小接线方案/缺项；若不够，明确缺什么证据和最小下一步，而非马上造通用预测。
3. 最后把“空钩如何在原案例接上”的最小完整方案放回唯一4.10：需要什么身体支持、触发证据及其作用范围、能否用现有共享计算避免重复工作。C1仍只作候选，不实施，也不为正例改inside或自动延长边沿；不要求这一轮就量误用率。先确认值得推进的实际适用面，再决定性能和执行器，不能只剩合成静止正例却宣称能打。

一次正式新编号答复即可；这不是新的实现任务或正式计时，不为回执再发一个仅已读的包。源码保持本固定源，允许只读本窗分析和设计文档原位更新。原始录像/AA/旧停批不动；有实机/P时只读收信。本次用户无需再授权同范围的只读分析；若下一步确实要扩新模型或改变战术范围，由Sol拿具体方案再判断。'''
p = B/'sol/TO_OPUS.md'; raw = p.read_bytes(); header = '# Sol → Opus 留言队列'.encode()
assert raw.startswith(header) and title.encode() not in raw
p.write_bytes(header+('\n\n'+title+'\n'+body+'\n\n---\n\n').encode('utf-8')+raw[len(header):].lstrip(b'\r\n'))

p = B/'sol/STATUS.json'; s = json.loads(p.read_text(encoding='utf-8-sig'))
assert s['current_source']==BASE and not s['live_or_budget_running'] and not s.get('own_offline_jobs')
s.update(at=now, phase='RHX455_OFFLINE_SCOPED_SOURCE_ACCEPTED_APPLICABILITY_PENDING382',
    candidate_source=H, offline_accepted_source=H, source_review_pending=False,
    last_opus_scan_number=455, last_opus_receipt_number=455, opus455_receipt=str(R/'REVIEW455.json'),
    pending_opus='seq382 bounded existing-body-support applicability/design proposal, same b35 window only; source fixed, no code/P/game',
    rhx455_live_ready=False, rhx455_performance_budget_pass=False, rhx454_P2_closed=True,
    next_owner='Opus same-task382 read-only applicability/design proposal',
    next_phase='Existing-support feasibility in original case, then concrete minimum design; no real-action or new50 permission.')
p.write_text(json.dumps(s, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
add = '''
### 7.397 #455三组P2按收窄域闭合；离线限定源码核收，原案例仍不可准入（11-15）

固定b74140e0父906、仅rune_hook_exit/tests两文件，commit/WT/P13绑定，needle/policy未变。Sol增量读源码/既有contact_body_witness安全hull域及45测试两份通过材料，不重跑45：两路动态检查/物理ram外层反例成立；去CV targets，以拟合hull全段、无定义拒绝，域限足够长落地静止状态；实际最终owner/同iid已知前态/原事件身份修正，Root两旧语义反例新源都false。当前限定源码无剩余这三组P2，不代表完整空钩可用或全域身体证书。ROOT455_CLOSURE_CHECK/REVIEW455留证。

只解析f11_off/f13_rec：1359决策/4077最终发送0差、keys同；entry3、交集0、H2 5。tool限制/历史前缀仍在，非真实worker或准时/HP证据。P14仅额外分析调用18共同门拍，全部body route unknown；b35 247–251原C1分析正例依赖旧恒速框已作废。工程全查Forum p50 43.32/max64.37ms、带静止体53.85ms，未过实时成本，不排P重证明显昂贵/不把record2上实机，active1仍拒绝。已实机源保持e097，b741仅离线限定核收，所有50权限余0。

信号389同包下一步只查b35短窗的现有V2/RangeSupport/刀链身体支持接口及未知时段是否已有可核不可达界限，必要最少离线确认；区别可靠支持、CV框和中心occupied，不造新模型/余量，不扫三批173/广测成本，不先异步迁移或写C1/执行器。给原案例能接上的最小完整方案与缺证据，唯一4.10原位更新，再定适用域、触发和性能，不能只靠合成静止正例宣称能打。新固定源保持；下一步归Opus只读可用性/设计，本通知不增加实机权限。
'''
for root in [Path('C:/modeling/silksong_bot'), WT]:
    p = root/'docs/plans/forum_clapper_plan.md'; assert b'### 7.397 ' not in p.read_bytes()
    with p.open('ab') as f: f.write(('\n'+add+'\n').encode('utf-8'))
print(json.dumps(dict(delivery=455, three_P2_closed=True, offline_only_source_accepted=True,
                     active_feature_ready=False, formal_P=False, game_authorized=False)))
