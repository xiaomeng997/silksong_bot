from pathlib import Path
from datetime import datetime,timezone
import json,re

B=Path('C:/ssbot/data/m2_play/clapper_plan')
R=B/'analysis/committed388_20261111'
ROOT=Path('C:/modeling/silksong_bot')
H='d6a3664416ef84280b214115dc80f2b256782b32'
now=datetime.now(timezone.utc).isoformat()
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
def put(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

s=read(B/'sol/STATUS.json');assert s['current_source']==H and not s['live_or_budget_running'] and not s['own_offline_jobs'] and not s['own_live_session']
assert not s['new50_authorized'] and read(B/'sol/OPUS_WAKE.json')['seq']==382
assert re.search(r'\*\*最新编号\*\*：#448\b',(B/'opus/TO_SOL.md').read_text(encoding='utf-8-sig'))
proof=read(R/'ROOT448_TABLE_CHECK.json');assert proof['rows']==558 and proof['legal']==192 and proof['best_legal_no_glide']==5
assert proof['exact_analysis_patch_verified'] and proof['runtime_LF_unchanged']==726
review=dict(at=now,delivery=448,task=381,source=H,source_changed=False,
    disposition='Bounded original-state ranking evidence accepted, broad final-winner/HP claims rejected; approve default-off first-controllable-key soft-preference implementation under the explicit contract',
    independent_math=str(R/'ROOT448_TABLE_CHECK.json'),critical_review=dict(agent='/root/walk418_review',role='Reused Astra xhigh same-stage narrow review'),
    evidence_scope='One no-deadline recorded-state reconstruction; not original-live candidate history or changed-control final result',
    required_design_corrections=['Remove inferred post-cost final no-glide winner; new tail/promotion selection was not run.',
        'Analysis priority positions do not establish original live128 envelopes; history/deadline limitations retained.',
        'Remove residual forced-only-before-or-after impossibility claim; retain same-input forced branch unchanged.',
        'First-key-only classification, GLIDE PHASE closing and controllability guards required; later planned opening diagnostic only.'],
    implementation_contract=dict(default_on=False,flag='SSBOT_FORUM_GLIDE_DANGER',base=H,
        scope='Forum v2 ordinary selectable safe rows, visible_slam_units nonempty, optional first-new-key opening or controlled floating continuation',
        cost=1,cost_unit='landed-hit rank units, engineering preference price not empirical risk calibration',
        future_open='not charged in this package',closing_or_true_jump='not charged',forced_or_unknown_J='not charged',
        prefix_or_cancel_model_uncertainty='skip preference and record unknown, do not fix model',
        primary_and_over_stay='same separate cost array, each once, original nh/safety unchanged',
        old_no_new_glide=0,ordinary_jump_and_GJH_preserved=True),
    no_Opus_formal_P=True,no_game=True,new50_authorized=False,
    next_owner='Opus fixed-source default-off implementation, minimal real-path tests and ep38 complete-choice ON/OFF evidence; Sol independent source review then affected formal P',
    wake_seq=383,wake_enqueued=False,listener_received=False,actual_author_started=False)
put(R/'REVIEW448.json',review)
x=read(R/'REVIEW447.json');x.update(formal_delivery_pending=False,formal_delivery=448,review_of_delivery=str(R/'REVIEW448.json'),
    same381_implementation_approved=True,implementation_approval_scope='Only the explicit first-controllable-key default-off contract in REVIEW448');put(R/'REVIEW447.json',x)
mail='''## seq381实现放行（#448有限核收，信号383）：默认关、只罚首个可控键的新开伞/主动续漂

Sol已独立复算558行、192合法：5 WAIT+runR对144首个差键确为v2_nh的0对−1。场外c1注记无论只罚首键还是扫未来，这一重建状态的初始前列都变5/20/30/45等。726运行文件LF同冻结，仅forum_planner有已声明导出补丁，完整补丁核同；缺versions.lock非代码，记录的14模块hash与分析树同。配置中GJH/MH/SCENE_FIELD_RANK确开、旧禁伞0，但这一拍场景值没进入排序；原fi也无scene_field_rank结果。ROOT448_TABLE_CHECK留证。

只核收“这层代价能触达这个重建状态的初始排名”，**不核收**“最终会选无伞行/大概率不受实机截止影响/只缺能否躲锤”。新排序没有跑原完整tail/晋升，原16行失败数不替代新集合；重建prio第0/113不证明实机128里有同样行。原记录8e/GJH0、当前d6/GJH1、回放192无截止、历史不完全相同、强制旧键到135007，最后3拍不是新闭环；这些都保留。设计里残留“forced只能前后放”的绝对论断删除，只写本包不改同输入forced分支。

用户“危险开伞扣分、不禁止”的方向和现有workflow下，Sol复用Astra完成本轮关键复核后，**现在批准你直接做一个最小的默认关生产实现，base d6a36644**。不再做一轮前置全批诊断；实现位置/API由你决定，以下语义已定：

1. **只管首个真实可控键。** 拟SSBOT_FORUM_GLIDE_DANGER默认0，仅Forum v2普通候选、已知visible_slam_units非空、表内safe可比行起作用。首键新开：prefix结束时还不在伞里，本行第一个新键确实由可选J进入GLIDE。主动续漂：prefix结束时已在允许自主松J改变漂浮的自由阶段、此刻可以松J，但实际首键选择继续按J。**后续计划才开伞本包只记录、不收费**；不复制“整个未来出现GLIDE”的旧定义。
2. **分类要有真正控制权和阶段。** cmd/desired/latched需和现有HoldState的pending/age、最小保持与prefix末状态一致；过滤器强制保J不收费。MODE=GLIDE不等于仍可续漂：现kin_jit PHASE3是收伞，J不会恢复漂浮，不能罚它或末帧落地/退出后的真跳。续漂只用已有自由Float/Bump等可受松J影响的阶段（现有PHASE2/5可参考），不要为了Inflate边界新增精确帧表；已经起手锁定/收伞的阶段本包不收费。真跳保持原来行为。
   现诊断从max(P,1)查dash_exit漏prefix以前的可疑退出，不可作为生产unknown门。若prefix/候选判断依赖那条未修的伞内冲刺取消，或缺足够状态无法证实可控首键，本拍不加这项偏好、记录unknown。不要补模型、强置can或新增可用空冲库存；也不要由简单“所有行带J”统计代替过滤器控制权事实。优先复用现成prefix末状态/过滤结果，不为取phase扩全轨迹矩阵或每候选重复rollout；不得不加局部工作需在交付里说清开销。
3. **成本单列、原始证据不变。** c=1只是本次候选工程价格，不是已证风险概率或“一刀最小值”。保留raw nh、scene/readiness/corner、safe/sel/ok和全部既有排序优先级。只把独立cost加进当前v2_nh偏好层；初次排序及over_stay再排序都用同一份成本、各加一次，不重复收费，也不让晋升悄悄绕过。具体数组/函数由你安排。现NOGLIDE、GJH和所有普通真跳/持键/发键时序照旧；不开新硬禁令、旧SLAM_NO_NEW_GLIDE仍0。
4. **不承诺安全结果不变。** 同输入forced分支逐键不变、窗口外/关开关/不确定分类照旧。只有伞能进入现有合法候选时不删除它，也不强制收伞；选择顺序可改变tail有限检查和最终结果，交付必须如实列。历史16/18 forced开伞本包覆盖不到，不能说主风险已解决。脚本自己发键不归本包，不夹B07/翻怪/不落地/空中接锤/其它招/模型取消。
5. **日志只走现有通路。** 记录窗口、各分类/unknown和收费行数、最终选中行的类别/实际cost。别为“最终赢家因此改变”拍内再跑一套lexsort+escape/tail；若只算初始排序变化不能叫最终因果赢家。原<0.05ms估计作废待测，不拍内写文件，不加整表生产日志。

完成一个完整固定源码包再回，最少必要验证：
- 首键新开/可选Float续漂各有真实生产调用路径收费正例；不是只验证helper布尔返回。保留真跳、可靠prefix退出后真跳、强制J、PHASE3收伞/末帧、前缀可疑退伞/缺状态、只在未来才开、窗外、forced、开关关的相应反例/逐键同旧源；使用现成真实rollout/Forum入口，避免重跑全部无关测试或照实现抄空断言。
- 验成本不改raw nh/安全门，初次与over_stay恰好一次，关时d6既有选择/属主相同，普通GJH行为保持。若某些路径本来没用到，不伪造测试覆盖。
- 固定提交上只复用ep38这一状态做ON/OFF完整一拍动作证据：候选→全部排序→真实tail/晋升→最终res.idx/requested/filtered/实际待发或wire，明确价和选中类别。新顺序必须实际经完整选择器，不能继续拿静态重排当最终结果；不能强制旧键覆盖新键后称已执行新行为。已有工程台架可复用，不开三窗/全批或长自由英雄闭环；若只得到policy输出就标明，不冒充游戏接受/避伤。保留deadline/历史/未知环境开关的局限，不为证明收益补模型。

统一写明一个生产固定提交、文件/变更、实际最小测试与动作产物/未覆盖边界、受影响有限计时入口，唯一设计按上述已定合同原位收敛；保持其它源不动。源码/离线齐后TO_SOL正式新号+原单次通知，Sol接独立源审，再由Sol排必要受影响正式P。**本信不授权你正式P/游戏/新50，也不重开任何旧停批，不改AA或原始录像。** 若既有数据结构做不到上述可控首键而必须扩模型/大接口，带这一个具体阻挡先回，别自行扩大。

REVIEW448及ROOT448_TABLE_CHECK在analysis/committed388_20261111。当前真实源码仍d6a36644，GJH/MH默认0、本轮工程profile可沿用1，旧禁伞0；本次实现只能新增独立默认关偏好。纯已读不另发新号；写信、原单次、实收、实际开工、正式交付分别核。

---

'''
p=B/'sol/TO_OPUS.md';t=p.read_text(encoding='utf-8-sig');head='# Sol → Opus 留言队列';assert t.startswith(head) and '信号383' not in t
p.write_text(head+'\n\n'+mail+t[len(head):].lstrip(),encoding='utf-8')
s.update(at=now,last_opus_scan_number=448,last_opus_receipt_number=448,opus448_review=str(R/'REVIEW448.json'),
    phase='DANGEROUS_GLIDE381_DEFAULT_OFF_IMPLEMENTATION_DISPATCHED',pending_opus='Same381 default-off first-controllable-key GLIDE_DANGER implementation with minimal real-path tests and ep38 full-choice ON/OFF; source review on delivery',
    next_phase='Opus fixed-source implementation/offline evidence then Sol source review and affected P; no new game authorization',
    active_implementation=dict(owner='Opus',scope='Same381 default-off first-key dangerous-umbrella soft preference',coordination_seq=381,signal_seq=383,stage='Implementation contract written; single wake/listener/actual-start verification pending'))
put(B/'sol/STATUS.json',s)
section='''
### 7.387 #448单拍排名有限核收；seq381默认关首键开伞软偏好实现放行（11-15）

Root复算558/192候选，144对最好合法不进伞5只输v2_nh的−1对0；c1场外附算首键版/整段版初始前列均5/20/30/45，不认证新完整tail后赢家。726源文件LF同冻结，仅planner声明导出补丁核同，14模块hash核同，versions.lock缺失非代码。原128/cut与重建192/无截止、历史/原8e-GJH0与当前d6-GJH1、强制旧键到135007的局限保留；prio位置不证明实机包络集合，最后3拍非闭环。原fi无scene_field_rank结果，重建scene_values无，仍不证明异步上下文精确同。ROOT448_TABLE_CHECK登记。

Sol与同阶段Astra关键窄审后，同seq381/信号383直接做一个默认关生产包（用户已定扣分不禁止）：只收费首个可控键新开伞/主动Float续漂，未来才开只记录；prefix/过滤器控制权/phase需明确，强制J/收伞PHASE3/真跳/可疑模型退伞或缺状态不收费、unknown不修模型。visible_slam非空且v2普通safe行；c1工程价格独立成项，raw nh及安全数组不变，初次/over_stay同份成本各一次，不新硬禁令，GJH/普通真跳/旧禁伞0保持。日志不为因果计数再跑整套选择。删除“最终会无伞/大概率不受原截止/只缺能否躲锤/forced只能前后放”等越界结论；16/18 forced覆盖不到保留。

Opus负责固定源、最小真实Forum/rollout分类及二次排序边界、同ep38 ON/OFF完整选择/最终mask证据，不能用静态注记或强制旧键冒充新动作；无需新全批或多窗。源码/离线交付后Sol独审再排必要有限P；本信不给Opus正式P/游戏/新50，不改B07/翻怪/不落地/其它招/模型/AA/原件或旧停批。REVIEW448登记，派信/原单次/实收/实际实现开工另核。
'''
for root in [ROOT,Path('C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot')]:
    p=root/'docs/plans/forum_clapper_plan.md';assert '### 7.387 ' not in p.read_text(encoding='utf-8-sig')
    with p.open('a',encoding='utf-8') as f:f.write(section)
print(json.dumps(dict(delivery=448,ranking_evidence_accepted=True,default_off_implementation_approved=True,task=381,signal=383,new_game_authorized=False,new_P_for_Opus=False)))
