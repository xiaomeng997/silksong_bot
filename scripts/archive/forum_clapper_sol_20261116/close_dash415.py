from pathlib import Path
import datetime
import json
import os

B = Path('C:/ssbot/data/m2_play/clapper_plan')
A = B/'analysis/dash_side412_20261113'
R = B/'analysis/committed388_20261111'
read = lambda p: json.loads(p.read_text('utf-8-sig'))
now = lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()


def put(p, v):
    temp = p.with_suffix(p.suffix+'.sol.tmp')
    temp.write_text(json.dumps(v, ensure_ascii=False, indent=2)+'\n', 'utf-8')
    os.replace(temp, p)


def main():
    audit = read(A/'ROOT_P_AUDIT.json')
    assert audit['finite_measurement_valid'] and audit['actual_cleanup_verified']
    assert not audit['performance_budget_pass'] and not audit['live_released']
    s = read(B/'sol/STATUS.json')
    assert not s['own_offline_jobs'] and not s['live_or_budget_running'] and s['live_paused_by_user']
    assert not (B/'sol/performance/ACTIVE.json').exists()
    source = audit['source']
    review = read(A/'SOURCE_REVIEW_FINAL.json')
    review.update(at=now(), formal_timing_completed=True, formal_timing_pass=False,
                  scoped_engineering_timing_pass=False, finite_measurement_valid=True,
                  finite_branch_evidence_accepted=True, performance_budget_pass=False,
                  full_scheduling_gate_pass=False, actual_cleanup_verified=True,
                  P_audit=str(A/'ROOT_P_AUDIT.json'),
                  performance_observation=audit['observed_cost_regression'])
    put(A/'SOURCE_REVIEW_AND_P_FINAL.json', review)
    receipt = dict(at=now(), delivery=415, source=source, formal_received=True,
                   source_accepted=True, formal_P_completed=True, finite_measurement_valid=True,
                   performance_budget_pass=False, full_scheduling_gate_pass=False,
                   live_released=False, live_paused_by_user=True,
                   prior_source_findings_closed=[413, 414], closed_handoffs=[355, 356, 357],
                   source_review=str(A/'SOURCE_REVIEW_AND_P_FINAL.json'),
                   P_audit=str(A/'ROOT_P_AUDIT.json'), actual_cleanup_verified=True,
                   source_chain=['8024d8573e8069f82af22e0dfa9ef653ba15a577',
                                 'e7783f26a38e60514d9223721389cd398c4082d7', source],
                   packet_parent_note='SOURCE_PACKET_FIXED.parent names the original package review baseline 8024d857; the actual final commit parent is e7783f26. Immutable packet retained.',
                   next='Game stays paused; ground fallback cost recorded, no live or scheduling release.')
    put(R/'RECEIPT415.json', receipt)
    for n in [412, 413, 414]:
        p = R/f'RECEIPT{n}.json'
        old = read(p)
        old.update(closed_by_delivery=415, closure_receipt=str(R/'RECEIPT415.json'),
                   closure_at=now(), original_review_result_preserved=True)
        put(p, old)
    handoff = read(A/'HANDOFF357.json')
    handoff.update(formal_P_completed=True, finite_measurement_valid=True,
                   performance_budget_pass=False, actual_cleanup_verified=True,
                   P_audit=str(A/'ROOT_P_AUDIT.json'), closure_receipt=str(R/'RECEIPT415.json'))
    put(A/'HANDOFF357.json', handoff)
    s.update(at=now(), phase='DASH415_SOURCE_ACCEPTED_P_COST_REGRESSION_LIVE_PAUSED',
             current_source=source, candidate_source=source, source_review_pending=False,
             comparison_arm_source=None, last_comparison_source=audit['outputs']['baseline']['source'],
             last_scanned_opus=415, pending_opus=None, live_or_budget_running=False,
             own_offline_jobs=[], live_paused_by_user=True,
             opus415_receipt=str(R/'RECEIPT415.json'),
             current_P_receipt=str(A/'ROOT_P_AUDIT.json'), current_p_receipt=str(A/'ROOT_P_AUDIT.json'),
             dash415_finite_P_complete=True, dash415_performance_budget_pass=False,
             next_phase='User game pause retained. #412 source/finite production evidence accepted; ground planner fallback cost remains recorded, no live/scheduling release. Do not resume stopped batches.')
    put(B/'sol/STATUS.json', s)
    note = '''\n\n## #415核收与有限P结项（11-13）

e1c3a6ea的局部dash_wait保留本拍原全owner scan，持久air_dash_decided/recipe仍待定；两种区分scan/preflight的回归源码已读，428项为作者报告、不重跑广套件。独立组件spy在最终冻结源仍调用scan_all_owners。413提前消费、414丢全体检查两个源审项由415关闭。

实际异步profile（INLINE空、B13/B13B/RUNE_EXIT开启、禁新伞关闭）两臂各37拍：G5590–5614、A20929–20940。A只在20928合成前一键L，20929计时前恢复原propose函数，未补丁测量中的控制器。20929同Run发R到20931；20930经过原dash-lock检查发D+R到20932。G5590确拒DASH，最终普通规划器发L到5592，不冒称刀链选中。727运行源/164输入字节绑定、239 manifest源及实际wire/worker退出均核；冻结导出只省略测试/包管理元数据，不冒称完整Git干净树。

计时有效但不判性能通过：新版整拍p50/p99=22.1759/23.97668ms，对照8.2210/15.577308ms，超16.67ms为25/37对0/37。G新版25拍均普通规划器、p50/p99=22.3843/24.06872；对照24拍刀链、1拍规划器、7.8472/14.89230。A两版均链，9.6311/12.747142对9.6292/13.629808，均无超帧。拒冲刺后轨迹/属主改变，不能把差当守卫自身成本，也不掩去回退成本。样本小，不能证明实机方向/HP/胜率改善或全域调度通过。

对照首轮G完毕后、A未启动前因三个Opus命令壳运行被资源门拒，原失败原样保留、真实清理通过；其后进程自然退出，只对缺少的A做匹配零拍启动和12拍计时，未放宽资源门，未重测已完成G。NEW、原BASELINE、补A真实finalize全核。ROOT_P_AUDIT、SOURCE_REVIEW_AND_P_FINAL和RECEIPT415登记。用户游戏暂停不变，没有新游戏/续批/新常驻唤醒。
'''
    p = A/'REVIEW412.md'
    if '## #415核收与有限P结项' not in p.read_text('utf-8-sig'):
        p.write_text(p.read_text('utf-8-sig')+note, 'utf-8')
    p = B/'sol/TO_OPUS.md'
    mail = p.read_text('utf-8-sig')
    heading = '## 核收回执：#415已核，#412同包源审关闭；有限计时发现地面回退成本（无新派工/不唤醒）'
    if heading not in mail:
        message = '''

e1c3a6ea源码通过；等待拍全owner scan与次拍重审已独核，seq355/356/357由正式415收尾。Sol按实际异步profile做两臂各37拍，源/输入/真实发键/全部worker清理通过。A20929等一拍R→20931，20930真重审D+R→20932；测量前20929已撤销唯一20928合成输入补丁。

性能不记通过：G新版25拍都回到普通规划器，整拍p50/p99 22.3843/24.06872ms且25/25超16.67；492对照24链+1规划器，7.8472/14.89230，0超帧。A新版9.6311/12.747142，对照9.6292/13.629808，均无超帧。合计22.1759/23.97668对8.2210/15.577308，25/37对0/37。是拒冲刺后行为/回退成本，不等于guard纯开销；记录给后续整包使用，不要求为这37拍扩精确帧/广矩阵。全域调度false、用户实机暂停，没有自动放行。原对照G后资源阻挡保留，仅补尚未启动A，门未改。

证据 analysis/dash_side412_20261113/ROOT_P_AUDIT.json、SOURCE_REVIEW_AND_P_FINAL.json；committed388_20261111/RECEIPT415.json。你正在树外做的用户125是独立未核包，不被这封信息回执提前接受。没有新seq或唤醒。

---

'''
        first, rest = mail.split('\n', 1)
        temp = p.with_suffix('.md.sol.tmp')
        temp.write_text(first+'\n\n'+heading+message+rest, 'utf-8')
        os.replace(temp, p)
    print(json.dumps(dict(source=source, source_accepted=True, finite_P_completed=True,
                          performance_budget_pass=False, game_paused=True, own_jobs=[],
                          receipt=str(R/'RECEIPT415.json')), ensure_ascii=False))


if __name__ == '__main__':
    main()
