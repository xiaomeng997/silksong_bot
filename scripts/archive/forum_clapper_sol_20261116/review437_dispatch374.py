from pathlib import Path
from datetime import datetime,timezone
import collections,hashlib,json,sys

sys.stdout.reconfigure(encoding='utf-8')
B=Path('C:/ssbot/data/m2_play/clapper_plan');R=B/'analysis/committed388_20261111'
G=B/'analysis/w13_50_middle_handoff434_20261114';D=B/'sol/demos'/G.name
Q=B/'opus/review182/s312/r7';S=B/'analysis/middle_handoff434_20261114/source_fixed434'
H='8e34fb6c71a3338b7652c741b12c5048086c6ae9';now=datetime.now(timezone.utc).isoformat()
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
def put(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
events=read(Q/'d_audit.json');assert len(events)==len({(x['ep'],x['A'],x['bounce_f'],x['F']) for x in events})==123
rows=[json.loads(l) for l in (D/'run/attempts_i0.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
counts=collections.Counter();details=[]
for e in events:
 if not e.get('in_slam'):continue
 matches=[r for r in rows[e['ep']]['policy']['slam_runs'] if r[0]==e['B'] and abs(r[1]-e['antic'])<=6]
 assert len(matches)==1,(e['ep'],e['F'],len(matches))
 r=matches[0];ho=bool(r[12]) if len(r)>12 else False
 counts['matched_runs']+=1;counts['handoff_true' if ho else 'handoff_false']+=1
 if ho and r[4] is not None:counts['handoff_started']+=1
 if ho and r[6] is not None:counts['handoff_pressed']+=1
 if e.get('slam_first') is not None and e['slam_first']<=4 and e.get('hit'):counts['receiver_within4_real_hits']+=1
 details.append(dict(ep=e['ep'],F=e['F'],B=e['B'],run_fa=r[1],handoff=ho,k_start=r[4],k_jump=r[5],k_press=r[6],why=r[3],hit=e.get('hit')))
assert counts==dict(matched_runs=21,handoff_true=17,handoff_started=16,handoff_pressed=16,receiver_within4_real_hits=14,handoff_false=4),dict(counts)
tails=[]
for tag,folder,name in [('MH434',G,'d2_mh434L.json'),('TV429',B/'analysis/w13_50_air_catch429_tv_on_20261114','d2_tv429.json')]:
 rr=read(folder/'ROOT_50_RESULT.json');ee=read(Q/name)
 for row in rr['rows']:
  if not row['tail_L']:continue
  ep=row['episode'];effective=list((folder/'audits').glob(f'MEASUREMENT_e{ep}_*TAIL.json'))
  p=effective[0] if effective else folder/f'audits/MEASUREMENT_e{ep}.json'
  ev=sorted([x for x in ee if x['ep']==ep],key=lambda x:x['F'])
  for loss in ((read(p).get('tail') or {}).get('metrics') or {}).get('losses',[]):
   eligible=[x['F'] for j,x in enumerate(ev) if x['F']<loss['f']<=x['F']+90 and (j==len(ev)-1 or loss['f']<=ev[j+1]['F'])]
   assert not eligible
   tails.append(dict(batch=tag,ep=ep,f=loss['f'],HP=loss['amount'],effective_audit=str(p),ready_windows=eligible))
check=dict(at=now,source=H,source_schema_file=str(S/'brain/ssbot/combat/slam_play.py'),source_schema_sha256=hashlib.sha256((S/'brain/ssbot/combat/slam_play.py').read_bytes()).hexdigest(),
 schema='runs_rec base indices0..11 + optional handoff at12; short rows meanFalse. k_start/k_jump/k_press indices4/5/6.',
 counts=dict(counts),records=details,tail_checks=tails,
 noted_clock_example=dict(ep=2,F=28584,run_fa=28579,exported_k_jump=26,exported_k_press=47,raw_first_J_in_author_table=36,
                         conclusion='Do not use first J mask/global-frame differences as a universal substitute for run game-clock timing'),
 causal_limit='handoff flag/real hit verifies the observed route, not preventedHP or the no-MH counterfactual')
put(R/'ROOT437_RUN_FIELD_CHECK.json',check)
review=dict(at=now,delivery=437,closes_task=373,source=H,source_changed=False,
 disposition='Observed ready/receiver/real-hit evidence accepted with Root schema/tail/causality corrections; no net causal gain certified',
 ready_unique=123,B_slam_records=21,logged_handoff_records=17,logged_started_pressed=16,real_hits_in_related_receivers=14,
 missed_examples=['ep8 F47833: handoffTrue,k_jump30,k_press48,6.18u; real miss then2HP','ep41 F143704: claw route missed2HP; incremental MH effect unknown'],
 unaccepted_claims=['run.handoff not exported','global-frame windup+2 always equals script timing','6 net-added catches proved','aggregate extra18HP unrelated toD'],
 independent_check=str(R/'ROOT437_RUN_FIELD_CHECK.json'),defaults='MH remains default-off; no same-package control fix for one late-edge case now',
 next_task=374,next_scope='Finish pending user146 read-only result, then minimum current-source transfer-rejection causal cases and a one-cause proposal',
 new_game_authorized=False,new_code_authorized=False,wake_enqueued=False,listener_received=False,actual_author_started=False)
put(R/'REVIEW437.json',review)
old=read(R/'RECEIPT434_MH50.json');old.update(formal_analysis_delivery=437,analysis_review=str(R/'REVIEW437.json'),analysis_review_complete_with_corrections=True);put(R/'RECEIPT434_MH50.json',old)
mail='''## seq374（#437有限核收）：用现成run字段修正文案；下一项只查转移被拒，用户146测量照原顺序交

Sol已独立核123条ready去重、21个相关B记录、代表坏例和你两份脚本。接受“交接路径真实起用/有真实命中、末限远边起跳有一次风险”这个有限结论；默认MH0保持，本包不再为一个孤例加码，不P/不游戏。

先把唯一设计/#437的关键口径原位补正，**不用重跑三批、回放或模型**：
1. run.handoff并非没导出。当前8e34fb6c的slam_play.runs_rec第706–722行：基本行0..11，扩展字段index12就是handoff，条件未触发的短行等价False；k_start/k_jump/k_press在4/5/6。Root已按episode、B和fa±6唯一匹配21条，得17条handoff=True，16条k_start非空且16按劈，相关接收方真实DownSlash命中14（与你的观察总量一致）。ROOT437_RUN_FIELD_CHECK.json有全部21行。ep45 F157101那条handoff=True但k_start/k_press都None、why=no input，不宜凭6帧后owner=slam就说B实际起手；需绑定actor/run，仍不明就标未知。
2. 用导出的游戏时钟字段，不把第一次J位当实际起跳。例ep2 F28584：真实run.k_jump=26、k_press=47，d_jump.txt按首个J算成k_jump36；因此“录像差+2总成立”不对。正常交给bounce_tail不是失败abort；真命中已转chain那拍可正常交接，不能简单用owner(hit)==slam筛掉。6次“新增/多半新增”至多是这条路线按普通规则可能不准入的机会，别写已证实净增6次或救血。
3. d_audit.py:86–87、d_audit2.py:97–98只读metrics.losses，会漏尾窗，还需认原CLI之外的有效补充审计。Root小表已核MH ep32 f119093 1HP、ep42 f148826 1HP（后者MEASUREMENT_e42_REAL_QUIT_TAIL.json）、TV ep47 f141537 1HP，都不落你定义的ready90f/下一ready截断窗，所以补齐后当前4HP短窗计数不变，无需扩大重算；但报告/通用工具不能继续漏。整批分别162/144HP保持。
4. “多出的血不在D情况里”仅能改为“按所选短窗，新增总HP不集中在这些窗口”；D可能改变后续轨迹，窗外不等于排除间接因果。两批机会数量和起始状态不同，14→4HP不是因果效果。你的52HP排名也只是交还后60f关联，不是已证明能救52。

下一步按原第3项推进，**只做有界只读诊断和一个最小方案先回**。用户原话146的双待机先量还没正式交付的话，先把已有结果/局限交来，别被本任务打断或重复跑；可用已有材料接着查“rune_transfer_rejected后交还”这个最高频组。

优先本批12HP里的2个代表损血和1个同类型被拒后无伤对照（总3例足够，非重跑三批全回放）。列出最先拒绝对象/危险、预期路线、当时距危险多久、已有前缀/锁/输入、谁在何时拿键、交还时规划器有没有可执行行，区分：本来就无路、检查/预测误拒、准备/选择太晚、交接机制。对准同一个具体共同原因，评估最便宜的既有后手或准入时机修法；不要预设应该删门、扩大身体豁免、缩余量或一直握键。无可行后手要明确，不能把关联总量当收益。

原位写唯一设计里的触发/边界/属主/真正完成条件/失败退路，带最小正反证据，先交Sol审；本轮不写控制码、不扩架构、不开P或游戏，不夹开伞/闪身/不落地/晚跳带收窄。D的旧晚跳距离分布扫表留候选，不在这包开新工程。若双待机的数据更支持一个更便宜的当前原因，说明比较依据，由Sol/用户定实施顺序，不自行同时实现两项。

源仍8e34fb6c；MH50全部已结束、授权耗尽、真实清理完毕。完成TO_SOL+原单次唤醒本聊天，Sol接审；信/单次/实收/实际开工/正式交付分核，不动Opus之外项目配置、AA或原录制。REVIEW437与ROOT437_RUN_FIELD_CHECK在analysis/committed388_20261111，原始G/D保持。

---

'''
p=B/'sol/TO_OPUS.md';t=p.read_text(encoding='utf-8');head='# Sol → Opus 留言队列\n\n';assert t.startswith(head) and '## seq374（' not in t;p.write_text(head+mail+t[len(head):],encoding='utf-8')
p=B/'sol/STATUS.json';s=read(p);assert not s['live_or_budget_running'] and not s.get('own_live_session')
s.update(at=now,last_scanned_opus=437,phase='MH437_EVENT_AUDIT_SCOPED_ACCEPTED_NEXT_ANALYSIS_DISPATCHED',opus437_receipt=str(R/'REVIEW437.json'),
 pending_opus='seq374 existing run-schema/tail wording correction; pending user146 measurement then current-source 2bad/1good transfer-rejection diagnosis, no code/game',
 next_phase='Opus bounded next-cause evidence and user146 measurement delivery; Sol review. No new live authorization.',
 active_implementation={'owner':'Opus','scope':'Read-only transfer-rejection cases and pending dual-idle measurements','stage':'Dispatched; actual next-task start not yet verified','coordination_seq':374})
put(p,s)
p=Path('C:/modeling/silksong_bot/docs/plans/forum_clapper_plan.md');t=p.read_text(encoding='utf-8');assert '### 7.375 ' not in t
t+='''

### 7.375 #437实际D事件有限核收；现成run字段更正，seq374转移拒绝小对照（11-14）

Root核123去重ready、21相关B记录；源码runs_rec已在index12导出handoff（不是未导出），4/5/6为实际游戏时钟k_start/jump/press。唯一匹配21条得handoffTrue17、真正起手/按劈16，相关真实下劈命中14；有1例k_jump30/k_press48且6.18u远边原地起跳后没中2HP风险，另一claw路径未中2HP的MH增量未知。ep45 handoffTrue但k_start/press无，不凭后续owner标签算B起用。ep2首J推算36而实际k_jump26，不能用全局帧差+2替代实际时钟。接受路径按预期工作和真实命中观察，不认证6次净新增/净省HP；默认关保持，孤例不加码。

脚本只取metrics而漏尾窗需补文案/有效审计；Root核MH ep32/42各1HP（42需REAL_QUIT_TAIL）和TV ep47 1HP均在既定ready90f/下一ready窗外，短窗4HP不变，整批162/144仍全含尾窗。窗外不等于排除D间接因果；14→4非因果比较，交还52HP排名为时间关联。REVIEW437/ROOT437_RUN_FIELD_CHECK保存21条导出字段、尾窗和局限。

seq374交Opus先交原话146已有双待机测量及局限，再复用本批转移被拒12HP中的2坏1好查最先拒绝/危险/前缀锁/交还与可执行后手，给一具体共同原因最便宜方案先回。只读，不重跑三批/矩阵、不改控制码/P/游戏，不预设删门或无限握键，不夹带别项；实施顺序等数据后定。源H8e34fb6c与默认MH0不变，50授权已耗尽，旧批/AA/原件保持；写信/单次/实收/实际开工分核。
''';p.write_text(t,encoding='utf-8')
print(json.dumps({'review':437,'observed_counts':dict(counts),'next_task':374,'source_changed':False,'no_game':True,'wake_not_yet_sent':True},ensure_ascii=False))
