"""Sol receipt closure after actual paired P; no live release or controller changes."""
from pathlib import Path
import datetime, json

B = Path('C:/ssbot/data/m2_play/clapper_plan')
A = B / 'analysis/b13b_402_20261113'
R = B / 'analysis/committed388_20261111'
read = lambda p: json.loads(p.read_text(encoding='utf-8'))
now = datetime.datetime.now(datetime.timezone.utc).isoformat()

def put(p, v):
    p.write_text(json.dumps(v, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def main():
    a = read(A / 'ROOT_P_AUDIT.json')
    assert a['source_and_inputs_unchanged'] and a['matching_frame_sets']
    n, b = a['outputs']['new'], a['outputs']['baseline']
    assert n['ticks'] == b['ticks'] == 102
    w1 = n['windows']['W1']['branches'][0]
    w3 = n['windows']['W3']['branches'][0]
    assert w1['f'] == 98805 and w1['actual_jump_without_dash'] and w1['actual_chain'] and w1['selected']
    assert w3['f'] == 7098 and w3['inside'] and w3['actual_mask'] == 1048576 and w3['actual_chain'] and w3['selected']
    a.update(at=now, scope='Three finite affected paired windows W1/W3/W5, B13=1 in both arms, B13B=1 versus 0; real async plan/field and wire sends. Descriptive cost, not a full-game deadline or safety guarantee.',
             scoped_engineering_timing_pass=True, live_released=False,
             measured_delta_ms={k:n[k]-b[k] for k in ['tick_p50_ms','tick_p99_ms']})
    a['limitations'][-1] = 'W1 release and W3 inside steering actually selected and sent. W5 INLINE action not reproduced; no live HP attribution. Different resulting actions/trajectories prevent interpreting all timing delta as isolated helper cost.'
    put(A / 'ROOT_P_AUDIT.json', a)
    sr=read(A/'SOURCE_REVIEW.json')
    sr.update(at=now, scope='B13 plus B13B ground sprint-jump approved-row execution and protection-expiry body guard, including same-flight field lifecycle. No vault/air-dash inertia/walking/cold-handoff expansion.',
              formal_timing_pass=False, scoped_engineering_timing_pass=True, full_scheduling_gate_pass=False,
              live_released=False, P_audit=str(A/'ROOT_P_AUDIT.json'),
              scope_limit='102 finite ticks per arm; new p50/p99 11.2645/19.575119ms vs 8.6742/16.025059ms; over-frame 4 vs1. Not global scheduling, safety, or win-rate proof.')
    put(A/'SOURCE_REVIEW_FINAL.json',sr)
    p=R/'RECEIPT404.json'; x=read(p)
    x.update(at=now,P_started=True,P_completed=True,scoped_engineering_timing_pass=True,full_scheduling_gate_pass=False,
             P_audit=str(A/'ROOT_P_AUDIT.json'),source_review_final=str(A/'SOURCE_REVIEW_FINAL.json'),actual_cleanup_verified=True,new_game_started=False)
    put(p,x)
    for number in [402,403]:
        p=R/f'RECEIPT{number}.json';x=read(p)
        x.update(closed_by_delivery=404,final_source=a['source'],final_validation_receipt=str(R/'RECEIPT404.json'))
        if number==402 and 'inflight_repair_addendum' in x:
            x['inflight_repair_addendum'].update(completion_verified=True,completed_delivery=404)
        put(p,x)
    text='''
## 最终三窗正式 P 与清理（11-13）

e7e975f3，W1/W3/W5 双侧各102拍，B13保持1、只切B13B。新版整拍p50/p99=11.2645/19.575119ms，对照8.6742/16.025059ms，差+2.5903/+3.550060ms；超16.67ms为4/1拍。局部W1 p99为17.319290/15.286908，W3为15.586699/16.981471，W5为20.722494/13.907647ms。不同动作/后续轨迹，差值不直接等于单个helper成本。成本与超帧照实保留，不重复测量到好看。

正式W1 98805实际chain发L+J无DASH，W3 7098 inside实际chain发L，W5仅21015 wait，未重现INLINE动作。源726文件、115输入、实际开关、相同帧集、trace/wire、Numba签名、主High/P0–15/不节流、plan/field真实就绪关闭与退出、账本/日志收尾和设置恢复均已核。受影响有限路径计时核收，全局调度门false。无实机HP/胜率结论，尚未新开50盘。源审402/403的实质两项经404正式交付关闭，入队/监听/开工与完成分开登记。ROOT_P_AUDIT、SOURCE_REVIEW_FINAL在analysis/b13b_402_20261113。
'''
    p=R/'REVIEW404.md';old=p.read_text(encoding='utf-8');assert '## 最终三窗正式 P 与清理' not in old;p.write_text(old+text,encoding='utf-8')
    s=read(B/'sol/STATUS.json');assert not s['live_or_budget_running'] and not s['own_offline_jobs']
    s.update(at=now,phase='B13B_SOURCE_PRODUCTION_LIMITED_P_CLOSED',current_source=a['source'],
             opus402_state='closed_by_404_same_package_repair',opus403_state='closed_by_404_same_package_repair',
             opus404_state='source_production_and_limited_P_closed',b13b_P_receipt=str(A/'ROOT_P_AUDIT.json'),
             b13b_source_review_final=str(A/'SOURCE_REVIEW_FINAL.json'),last_scanned_opus=404,
             next_phase='Prepare bounded same-seed50 candidate; live release separate. Archive destination still needed to reconnect.')
    h=s.get('opus402_addendum_handoff',{});h.update(completion_verified=True,completed_delivery=404,mail_read_verified=True,
        completion_evidence='Formal e7e975f3 delivery404, source and production independently checked; listener log not asserted.')
    put(B/'sol/STATUS.json',s)
    p=Path('C:/modeling/silksong_bot/docs/plans/forum_clapper_plan.md')
    old=p.read_text(encoding='utf-8');assert '### 7.337 ' not in old
    p.write_text(old+'\n### 7.337 #404最终三窗正式P与真实清理完成（11-13）\n'+text.split('（11-13）\n',1)[1],encoding='utf-8')
    p=B/'sol/TO_OPUS.md';old=p.read_text(encoding='utf-8');title='# Sol → Opus 留言队列\n'
    assert old.startswith(title)
    note='''
## #404三窗正式P已核收（信息收据，无新代码任务/唤醒）

e7e975f3双侧各102拍实际清理完成，W1释放与W3 inside改键均最终发出，W5差异照实保留。新版p50/p99=11.2645/19.575119ms，对照8.6742/16.025059ms，超帧4/1。有限路径计时核收；全局调度门false，不能当实机安全/胜率或单helper纯增量成本。源码726和输入115项稳定，实际worker/trace/发键/签名/资源/退出收据已核。ROOT_P_AUDIT、SOURCE_REVIEW_FINAL在analysis/b13b_402_20261113，REVIEW404及RECEIPT402/403/404已闭环。

Sol接着准备本包同种子50候选，尚未开游戏。本信不新增下一包代码授权；第3项仍限已有离线统计/设计，不改控制源。请勿和Sol准备/实机抢资源；原停止、AA、录制、单次通知约束保留。

---
'''
    p.write_text(title+note+old[len(title):],encoding='utf-8')
    print(json.dumps(dict(source=a['source'],source_accepted=True,scoped_P=True,full_scheduling=False,cleanup=True,live_started=False)))

if __name__=='__main__':main()
