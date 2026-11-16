from pathlib import Path

p=Path('C:/modeling/silksong_bot/docs/plans/forum_clapper_plan.md')
s=p.read_text(encoding='utf-8')
title='#### 用户改为单局观察：成团后撤引导再钻回平砍；掉血不停、保命拦死亡（11-05，进度7.179）'
assert title not in s
text='''

#### 用户改为单局观察：成团后撤引导再钻回平砍；掉血不停、保命拦死亡（11-05，进度7.179）

用户最新指示取代本次实验原首损停止口径：先只打一盘观看，避免多局混淆；后撤约2.5个怪本体宽（实际身体宽与u距离记日志，受墙边身体空间限制），确认一只实际起跳锁定后，回冲站着怪的面前并立即平砍。不自动开下一盘，不在同局悄悄调整距离。只适用于英雄在两只成团怪的外侧；夹中原三选一保持。回程遇新出招/当前危险仍用既有防御或交还，不硬撞，不将未执行动作记为成功。

Root已完成用户先前要求的离线统计，analysis/cluster_bait_space_20261105/保留REPORT、RESULT、逐事件与复算脚本/hash。35个既有TRAIN（23近期w13、12已用于行为表的旧录像/107个终局范围），1664个起始同伴Idle/Walk的跳跃；初始真Idle旧样本瞄准期经验p99普通3.84u(n433)、跳大符文7.20u(n382)，到落地9.60(n433)/12.00u(n378)。中位几乎不动但尾部积极追赶；旧策略/同局相关、初始姿态/距离组成及回钻会改变DistanceWalk，均不能签新打法99%安全。必要几何算式也不是完整路线验收。用户随后要求停止扩这些离线推演，优先用有界实机看实际闭环，不以99分位或新空间模型作为整局准入的新门。

本次明确为观察模式，不是正常无伤/生存性能验收：普通或链相关掉血均只记录，不因首损、B累计2HP而中止；用户又要求拦截死亡、只掉血不死。优先复用部署Oracle TRAIN的LethalBlock=block，不开全程无敌、不改部署DLL。实际扣血和健康guard拦下的would_die分别记，后者不能当安全或实机成功。保命后的过程继续观察；真实死亡/guard失效、期望键不符/回执越界、关键日志缺失、资源违规、用户STOP/练习标记仍停止。原golden/Prefs/旧DEMO/自有进程/registry全清理后才STATUSfalse的门不变，不碰Windows核心进程。上限单局45s游戏时间或自然结束，原7HP起点和其余起步条件保持；不复用或重开L1/L2/L3旧停止目录。

Root查明必须闭合的现成接口接缝：B2的LOW_HP_POLICY即使环境退出HP设0，仍给监督器剩余2HP退出；episode data语义可记would_die继续，但直接切data会带HP1..5/其他随机起步变化；MeasurementWindow协议2会把catastrophe/would_die封口成lethal，不能只放开episode外层。仅为本次显式观察配置复用这些接口，保持正常eval和原统计语义；输入/资源/完整性fatal保留，原始STATE/trace/measurement完整且明确观察标签。

Opus #309固定源码21b1d9846ec72d775059d209df29f36ed973c2b4已轻扫并读新交付，Root已审此次可能执行的共用增量和新入口关闭隔离，记录sol/work_packages/task179/ROOT_309_SINGLE_BOUT_PREVIEW.json，尚未完整接受源/P/游戏gate。309只补夹中才takeoff换怪，报告明确尚未做前摇后撤→起跳回冲闭环；不能冒称本次已经就绪。连续表虽接线但真实几何闭环接触落空、随后模型受伤，保持BOUNCE_TABLE=0；脸钩正例只有钩中/交还，未完成翻越。本次FACE_HOOK=0，Slam0逐帧body与扩翻越动作表两项延后，不拖住当前不使用它们的观察局，也不全球关闭既有普通冲锤防御。

同Task179以seq230一次合并用户新范围/源审反馈，OBSERVATION_ONE_BOUT_DRAFT.json及Sol信箱已落盘；Opus仍唯一运行源码实现owner，先交稳定最小候选和必要生产正例/受影响测试，不重跑无关大套件或新网格。Sol负责增量源审、必要受影响成本/生命周期检查及唯一游戏，门齐后直接开，不再问用户例行许可。当前在途/排队不算通过：STATUS live_or_budget_running=false，无自有E/P/游戏；来源仍pending，未写新ENGINEERING_GATE、未启动任何新局。用户明确的本次伤害继续/保命要求优先于旧heartbeat中的首损/死亡口径，但不放宽其它实际动作、源审、记录、资源和清理门。
'''
p.write_text(s.rstrip()+text+'\n',encoding='utf-8')
print('main plan 7.179 saved; no runtime change')
