from pathlib import Path
import json,hashlib,datetime
B=Path('C:/ssbot/data/m2_play/clapper_plan');A=B/'analysis/over_evade311_20261109';repo=Path('C:/modeling/silksong_bot')
now=datetime.datetime.now(datetime.timezone.utc).isoformat();A.mkdir(exist_ok=True)
task='''## seq311：用户已授权——仅中间原选over，走路怪闪身就压第一只，再选站中间/翻第二只

用户最新原话：“那就按这个方案交给opus修：只限两怪中间、原本选翻走路怪的分支，走路怪闪身就直接压第一只，压住再判断站中间还是翻第二只。修完再打50盘，开打前给我准备框。”这是正式实现包，不是只写建议。Opus负责设计/代码/离线验证，Sol独审、必要正式P和新50。基线7b088d7824256cee0867d4bac0c127f9411f0bbf，工程树forum-knife-rows刚实核相同，原docs脏项及五aim_zones文件保留。请直接开始，在本包内完成后正式交付，不等一次已读。

### 行为与范围（以用户最终顺序为准）

四项入口同时成立：英雄处于两只活怪之间的既有middle父场景；第一只仍在跳大符文瞄准前摇、尚未锁定/起跳；另一只是走路怪；本次方案原已选over翻走路怪。仅从该分支触发，不能扩成所有双怪/所有闪身的全局禁追。原本选钻大符文、压大符文留中间、外侧/成团/重叠/双怪已同时起跳不套此入口。

走路怪未闪身时维持既有准备攻击；它一进闪身，停止追它，直接朝第一只正在瞄准的施法怪压位置。不要先比较“要不要压”，也不要默认原地等。计算已有压点/执行输入不等于重新竞选是否压。压是面前一侧引导第一只落点，不是提前钻背；所有实际属主（ordinary/追击移动与冲刺/钩/刀链）需尊重同一阶段意图，不能只拦CLAW，chase继续追远。

压住第一只之后，才根据最新局面决定后手：站中间，或翻第二只。原选over是触发条件，不绑定最终后手；向第一只压也不等于已选留中间。第二只闪完可能转近招，也可能远程（近/远表都有小符文，远表另有跳锤/跳大符文），它不保证继续待机。保存两怪各自实例/时钟/活符文，按压完后的间隙、落点及可执行后继选择，不能沿用第二只Idle假设或预设钻第二只。继承既有动作合法交还、已发前缀/hold、危险/真实发键门；到达/阶段推进按可核实际状态，不能无限追过已锁定的第一只、重开旧事件或以长期hold当成功。无需新造全局战术语言、精确边界长扫描或重写所有跳招。

唯一完整设计：主仓库docs/plans/forum_clapper_l2_tactics.md“原选翻过走路怪时，闪身触发先压第一只、再选后手”。先核实际代码该意图的所有权/交还，再选择局部实现。用户现在授权的是这一行为；低侧撞身、回中段拖过新冲锤窗口、一般翻越失败恢复、圈外多余跳/禁伞均不并修。必要接口调整留本包，遇不可分依赖给具体最小证据。

### 已有原始证据，优先复用

新50基线analysis/w13_50_rune310_20261109_r4已完整审计/清理：36通过/14Q1、2无伤、185HP。原始run在sol/demos/w13_50_rune310_20261109_r4/run，e15（用户16局）recording为rec/2026-11-09/TRAIN/i0_015；analysis/.../user_review310/REPORT.md、USER_CASE_WITNESS.json、OWNER_SUMMARIES.json、EVADE_RANGE_NOTE.json及e15.pkl是派生入口。正式重放仍绑定原始STATE/actual sent及冻结源analysis/rune_allpaths310_20261109/source。

第16局53372左怪1435118大符文前摇；53403右怪1435112闪身，chase发R+DASH（53405/06第一次攻击尚锁、53412/13重发），53412实际Dash。英雄53404–53426从x28.80追到34.16。53424/25记录middle/over/aim_attack；53427左怪Jump、53428 Air，53430才发翻越J、53431英雄离地、53452下劈右怪。53557大符文损2。此段确证是“瞄准期追远，之后翻”，不是提前钩/下劈；不能承诺该2HP必可避免。

第45局另有两只先后大符文：133451第一只前摇，另一只133471闪身/133493 Idle；第一只133505 Jump，第二只133509大符文前摇、133564 Jump。这是新招/独立时钟的邻接入口，是否满足本包原over条件要核，不强行当正例。正常闪身约0.35s/5.4u；地面近程中心距约8.3，原来砍得到不意味着闪后仍近程。只作已核事实，不硬写全局选招假设。

### 必要验证与交付

1. 真实生产输入复现原追远，候选需见实际朝第一只压的policy→before_send→sent（方向/owner/绝对帧），并见压住后站中间和翻第二只两种后继各有可执行正例；缺实录可补明确标注的有界生产形状场景，不能只靠helper变target或永久拒键。
2. 查走路怪闪身转近招/大符文、第一只已锁定/起跳、原动作仍有不可取消前缀、旧事件重复/失效交还等真正受影响边界。场景外、原选under/留中间、第二只未闪、原正常接刀保留对照。别为本包全扫全部50或重跑大量无关文件；固定证据可引用，新增反例限本行为。
3. 共同有效模型起点比较；分歧后不强喂旧英雄冒充闭环。完整到达/后继与真实owner、send、模型接触分清，已接触后的模型轨迹不当真实HP。保留两只动态危险与既有A符文门，不靠删安全检查得到正例。
4. 固定可审commit、相关测试/必要变异、原件绑定、明确覆盖/未覆盖、短行为差异和已跑通的受影响整拍P入口正式交付。Sol只补独立缺口和必要P，不重复同组测试；无需工程再全50普查或全局性能优化。

### 执行与下一50

当前无Sol游戏/P/离线作业。工程重计算沿现有E16–23 Idle约定登记实际PID/create及退出，正式P/游戏期间让出重计算、只读收信。不得改股票项目或其他代理配置，不动冻结AA/原始录制/旧停止批。实机权限仍只由Sol调度。

通过源审/必要P后，Sol用同一最终源准备独立新50，同游戏连续；每局真实2HP保护退出继续收满，死亡/运行/输入/关键日志/恢复/资源/清理故障停批。开打准备框必须在游戏/控制器/录像预热和开打前检查完成后发，用户实际新回复后快速检查并GO，旧回复不复用。新50的整个流程已由用户授权，第一局释放仍等该准备回复。

本包seq311，不再续seq310修旧A。正式交付TO_SOL新编号并用既有一次性wake_sol回当前聊天；Sol继续盯交付、源审、必要P和准备框，不创建周期任务。写信、唤醒、监听收到、实际开工、正式完成分别核实。

---

'''
p=B/'sol/TO_OPUS.md';old=p.read_text(encoding='utf-8-sig');assert '## seq311：' not in old;p.write_text(task+old,encoding='utf-8')
auth={'at':now,'seq':311,'source':'7b088d7824256cee0867d4bac0c127f9411f0bbf','user_instruction':'只限两怪中间、原本选翻走路怪的分支，走路怪闪身就直接压第一只，压住再判断站中间还是翻第二只。交给Opus修，修完新50，开打前准备框。','implementation_owner':'Opus','review_P_live_owner':'Sol','fresh_ready_required':True,'same_game_continuous50':True,'q1_continue':True,'runtime_fault_stop':True,'mail_sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
(A/'USER_AUTHORIZATION.json').write_text(json.dumps(auth,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');(A/'TASK311.md').write_text(task,encoding='utf-8')
p=B/'sol/STATUS.json';s=json.loads(p.read_text(encoding='utf-8-sig'));assert not s['live_or_budget_running'] and not s['own_offline_jobs'];s.update(at=now,phase='OVER_EVADE311_DISPATCHED',pending_opus='seq311 implement middle over evade -> press first -> choose middle or vault second',next_phase='Watch formal Opus delivery, independent source review and affected P, then prewarm fresh50 and ask ready before first fight.',current_package='seq311',package_root=str(A),live50_preparation_authorized=True,live_release_requires_fresh_ready=True);p.write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(auth,ensure_ascii=False))
