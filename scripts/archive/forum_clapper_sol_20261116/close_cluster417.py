from pathlib import Path
import datetime,json,os
B=Path('C:/ssbot/data/m2_play/clapper_plan');A=B/'analysis/cluster_back416_20261113';R=B/'analysis/committed388_20261111'
read=lambda p:json.loads(p.read_text('utf-8-sig'));now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()
def put(p,v):
 q=p.with_suffix(p.suffix+'.sol.tmp');q.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n','utf-8');os.replace(q,p)

def main():
 audit=read(A/'ROOT_P_AUDIT.json');s=read(B/'sol/STATUS.json')
 assert audit['finite_branch_evidence_accepted'] and audit['actual_cleanup_verified'] and not audit['live_released']
 assert not s['own_offline_jobs'] and not s['live_or_budget_running'] and s['live_paused_by_user'] and not (B/'sol/performance/ACTIVE.json').exists()
 source=audit['source'];review=read(A/'SOURCE_REVIEW_FINAL.json')
 review.update(at=now(),formal_timing_completed=True,formal_timing_pass=False,finite_measurement_valid=True,finite_branch_evidence_accepted=True,performance_budget_pass=False,actual_cleanup_verified=True,P_audit=str(A/'ROOT_P_AUDIT.json'),existing_G_cost_still_open=True)
 put(A/'SOURCE_REVIEW_AND_P_FINAL.json',review)
 receipt=read(R/'RECEIPT417.json');receipt.update(at=now(),source_accepted=True,source_review_pending=False,formal_P_completed=True,finite_measurement_valid=True,finite_branch_evidence_accepted=True,performance_budget_pass=False,actual_cleanup_verified=True,source_review=str(A/'SOURCE_REVIEW_AND_P_FINAL.json'),P_audit=str(A/'ROOT_P_AUDIT.json'),live_paused_by_user=True,live_released=False)
 put(R/'RECEIPT417.json',receipt)
 h=read(A/'HANDOFF358.json');h.update(formal_P_completed=True,finite_branch_evidence_accepted=True,actual_cleanup_verified=True,P_audit=str(A/'ROOT_P_AUDIT.json'),closure_receipt=str(R/'RECEIPT417.json'));put(A/'HANDOFF358.json',h)
 old=read(R/'RECEIPT416.json');old.update(closure_receipt=str(R/'RECEIPT417.json'));put(R/'RECEIPT416.json',old)
 s.update(at=now(),phase='CLUSTER417_SOURCE_AND_FINITE_P_CLOSED_LIVE_PAUSED',current_source=source,candidate_source=source,comparison_arm_source=None,last_comparison_source=audit['outputs']['BASELINE']['source'],last_scanned_opus=417,pending_opus=None,source_review_pending=False,live_or_budget_running=False,own_offline_jobs=[],live_paused_by_user=True,current_P_receipt=str(A/'ROOT_P_AUDIT.json'),current_p_receipt=str(A/'ROOT_P_AUDIT.json'),opus417_receipt=str(R/'RECEIPT417.json'),cluster417_finite_P_complete=True,cluster417_performance_budget_pass=False,next_phase='User game pause remains. #416/#417 source and finite return-to-side-slash evidence accepted; no live/scheduling approval. Prior #415 G fallback cost remains recorded. User124/126 implementation timing undecided; no automatic dispatch or game restart.')
 put(B/'sol/STATUS.json',s)
 text='''

## #417修正核收及有限P结项（11-13）

fbf0a388只在cluster场景的BACK_PHASES调用另一只已落地跳的例外；lure及其它阶段恢复原other_move与公共回中。独立同一反例在最终冻结源恢复invalid/other_move、不写skip、生成iid8 back，SCOPE_PROBE_FIXED已存。新增两个分支回归源码已核，295为作者受影响报告、不重跑广套件。更正416：所谓16项含外文件1项，文件本身15项；修后文件17项。p2d的239源码LF指纹与最终源匹配，作者117帧同键/属主/模型/计划等价证据核到。

Sol实际异步INLINE空的BACK窗口9486–9502，两臂各17拍，9484起合成主角且不强制按键，无控制器补丁。新源保持attack_back_other，9498 in_reach，9499 two:idle实际发A+R到9501、9500续到9502，没有公共回中；父e1c实见other_move失效并走中缝链。727运行源、154输入绑定、239 manifest源、最终wire及两个实际worker真实退出均核；五个适配器运维键仍未解析，CPU/High/P0–15/不节流另实读，非未知控制开关。完整导出省略测试/包管理文件，未冒称Git全树干净。

新整拍p50/p99=13.6561/18.088252ms，最大18.4039，1/17超16.67；父版本9.4401/16.1869，最大16.4293，0/17超帧。新6拍planner+11拍two:idle，旧4拍planner+13拍链，13拍实际键/属主不同；不是同动作helper纯开销。有限计时有效和目标分支成立不等于性能/全域调度或实机改善通过；415的G回退成本未重测或修复。两边模型无伤仅为模型，平砍实际命中仍无实机证据。

全部check/measure/finalize真实清理已核，current_source恢复fbf0。ROOT_P_AUDIT、SOURCE_REVIEW_AND_P_FINAL及RECEIPT417已登记，seq358已完成写信/一次信号/监听16:20:40实收/16:21后开工/正式417/源审/有限P，未把任一步入队当完成。用户实机暂停，不续旧批、不增游戏/常驻唤醒；124和126仅设计，何时实现仍待用户定。
'''
 p=A/'REVIEW416.md';oldtext=p.read_text('utf-8-sig').replace('作者16新测试源码','作者原报16项（实际文件15项加外文件1项）测试源码')
 if '## #417修正核收及有限P结项' not in oldtext:p.write_text(oldtext+text,'utf-8')
 p=B/'sol/TO_OPUS.md';mail=p.read_text('utf-8-sig');heading='## 核收回执：#417源审与有限P已完成，seq358关闭（不唤醒）'
 if heading not in mail:
  first,rest=mail.split('\n',1)
  note='''

fbf0a388范围修复通过：独立lure反例恢复原other_move和公共back；17项新文件/295作者受影响报告已核，不重跑广套件。Sol实际异步profile INLINE空、同窗9486–9502两臂各17拍：新版回程9498 in_reach，9499 two:idle A+R→9501、9500续→9502，无公共回中。父e1c实见other_move失效。727源/154输入/239 manifest源/wire与实际worker清理核实。

新整拍p50/p99 13.6561/18.088252ms、1/17超16.67；父9.4401/16.1869、0/17。动作/属主不同，不能当helper纯成本；有限证据接受，性能/全域调度不记通过，415既存G回退成本继续保留，不为这17拍扩精确帧/矩阵。模型无伤不代表实机改善，工具不计平砍命中，真命中仍待实机。

证据analysis/cluster_back416_20261113/ROOT_P_AUDIT.json、SOURCE_REVIEW_AND_P_FINAL.json；committed388_20261111/RECEIPT417.json。用户游戏暂停，无新批/续跑授权；124、126仍仅设计，何时做待用户定。没有新派工或seq，不另唤醒。

---
'''
  q=p.with_suffix('.md.sol.tmp');q.write_text(first+'\n\n'+heading+note+rest,'utf-8');os.replace(q,p)
 print(json.dumps(dict(source=source,source_accepted=True,finite_P_complete=True,performance_budget_pass=False,user_game_paused=True,own_jobs=[],receipt=str(R/'RECEIPT417.json')),ensure_ascii=False))

if __name__=='__main__':main()
