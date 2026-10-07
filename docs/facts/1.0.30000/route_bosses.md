# 路线 boss（Forum 之外）：存档、触发、Control FSM（2026-10-06）

来源：社区存档（vichisuki BellRoute-LP，固定提交 0557f703fa25，`C:\ssbot\sandbox\savestates\community\0557f703fa25\manifest.json`；副本 `vs_p6_*` / `vs_p7_*`），探针 `brain/ssbot/probes/route_bosses.py`（scout：fsmtap all + fsm.graph；save：游戏写出的训练存档），输出 `C:\ssbot\sandbox\route_bosses\*_scout.json`（含完整的 Control 静态图）。训练副本、oracle 视图、存档写入关闭。

## 1. 哪些 boss 有现成存档

| 路线 | boss | 社区存档 | 场景 | 状态 |
|---|---|---|---|---|
| S07 | Lace 1 | p6_s3 = vs_p6_s3 | Bone_East_12 | **已接入**（`rb_lace1`） |
| S08 | Fourth Chorus | 无 boss 存档（社区路线跳过它：p8_s5 / p8_s6 "Fourth Chorus Skip"，Bone_East_08 x 98） | Bone_East_08 | 未做：要从跳过存档走到竞技场再存 |
| S13 | Widow | p6_s7 = vs_p6_s7 | Belltown_Shrine | **已接入**（第 2 轮，`rb_widow`）：不需要对话，**挑衅（taunt 键）**即开打（§7）。第 1 轮"要先对话"的结论是错的 |
| S17 | Last Judge | p6_s8 = vs_p6_s8 | Coral_Judge_Arena | **已接入**（`rb_lastjudge`） |
| S19 | Cogwork Dancers | p6_s9 = vs_p6_s9 | Cog_Dancers | 未做：两个 boss（"Dancer A" / "Dancer B" 各 190 HP），走 5.4 s 后醒；单 boss 的表格构建器不适用 |
| S22 | Trobbio | p7_s1 = vs_p7_s1 | Library_13 | **已接入**（`rb_trobbio`） |
| S26 | Lace 2 | p7_s4 = vs_p7_s4 | Cog_Dancers（战斗在 Song_Tower_01） | 未做：存档在 Cog_Dancers（Dancers 已打完，x 39.93），Lace 2 在 `Song_Tower_01`，要坐旋律升降梯（`UnlockedMelodyLift`，第一次要演奏 Threefold Melody，benches.md §1）换场景才到；scout 自动左右走 24 s 没有 boss、还掉进了尖刺。要先做一个 Song_Tower_01 里的训练存档（§9） |
| S27 | Grand Mother Silk | p7_s5 = vs_p7_s5 | Cradle_03 | **已接入**（第 2 轮，`rb_gms`）：同样挑衅开打（§8） |

## 2. 三个已接入的 boss

| | Lace 1 | Last Judge | Trobbio |
|---|---|---|---|
| type_key / FSM | "Lace Boss1" / Control | "Last Judge" / Control | "Trobbio" / Control |
| HP（ents） | 250 | 720 | 700 |
| 训练存档 | `rb_lace1`：vs_p6_s3 向左走到 x 83.50，`encounteredLace1` 设为真 | `rb_lastjudge`：vs_p6_s8 原样（x 33.54, y 24.57） | `rb_trobbio`：vs_p7_s1 原样（x 57.73, y 14.57） |
| 触发 | 向右走，英雄 x ≈ 88.2：Dormant → Refight（社区原位 x 89.94 离触发太近：载入后在 tap 复位前就开打，没有醒来帧） | 向右走约 0.8 s：Dormant → Intro Fall Antic Q（存档里已见过审判者 = REFIGHT 路径） | 向右走，英雄 x ≈ 61.7：Wait Refight → Start Pause → Quick Entrance 1 |
| 首次相遇（路线上） | Encountered? → MEET：Take Control、Convo 1/2/4 三段对话 | Dormant → INTRO FALL：Intro Fall Antic（长版） | State → MEET：Wait → Take Control → Intro Jet → Convo 1 |
| 死亡 | Control 里没有死亡状态（没有 ZERO HP 全局转移）：以 boss 的第一次 dead "hit" 事件为击杀（`Encounter.death_on_kill`），不管 hp_before。全局 LAVA DAMAGE 用 FSM 的 SubtractHP 扣血（没有 hit 事件），可以把 HP 扣到 ≤ 0 而她继续打；下一次命中（hp_before 已为负，如 −30 → −35）才开始 BossDeathSlow，即击杀 | 全局 ZERO HP → Death | 全局 ZERO HP → Death Hit（之后是一长段假死表演） |
| 按 HP 分支 | CrossSlash?（CompareHP）→ 十字斩 | Flame Up Check / Rage Check（CompareHP）→ Flame Roar / Rage Roar | Choice / Pose Idle 送 TO P2 → Phase Roar |
| 场地（冒烟战斗） | 待测（有 "Lava Box" 危险物，冒烟第一场被它打中 1 次、第二场 3 次） | 英雄 x 7.56–52.41，boss 8.05–53.73，地面 y 24.568 | 英雄 x 59.28–88.72，boss 59.61–88.41，地面 y 14.568 |

存档的 PlayerData 是社区路线的，不是我们的路线：三份都是 5 面具、9 丝、Hunter 纹章；Last Judge / Trobbio 的 `nailUpgrades` 1，Lace 1 为 0。我们的路线在 Trobbio 前计划 7 面具（DESIGN §3.6.4 面具算术），这里没有改。

## 3. 动作族（BehaviourSpec，`brain/ssbot/knowledge/behaviour_tables.py`）

由 Control 静态图读出：决策状态分支进去的那个状态是动作的开始，进入任一决策状态即结束；两次动作之间是 `<前缀>_IDLE` 族（身体接触），醒来链是 `<前缀>_INTRO`。全部按 flipX 定向（精灵在 flipX 假时朝 −x，与 Forum 敌人相同，未单独核对）。

- Lace 1（L1_）：INTRO、EVADE（Evade / Evade 2）、HOP（三个 Hop To *）、CHARGE、JSLASH（含 Downstab、Wallcling、Kickoff）、COMBO（ComboSlash 1–5）、COUNTER（含 RapidSlash 与多段连击）、CROSS（CrossSlash Antic 起）、SING、STUN、LAVA（全局 Lava Damage → Lava Hop → Lava Tele Out → Set Tele Pos X → Tele In → Lava End → Idle，掉进熔岩后跳起并传送回场地）。
  - 十字斩前的 CrossSlash Aim、CS Evade、CS Evade Cancel 是零时长的逻辑状态（前 12 场 Lace 里 96 / 61 / 18 次退出，t_in_prev 全是 0.0），按决策状态处理。Aim 之后 61/96 次走 EVADE：CS Evade → Evade → Evade Recover → Evade Move → CROSS SLASH → 再 Aim（43 次，就是普通的 Evade 状态，算 EVADE 族，ctx 的来源状态 "CS Evade" 可以区分）；闪避次数用完时 CS Evade → END → CS Evade Cancel（转身）→ CrossSlash Antic（18 次）；直接 FINISHED → CrossSlash Antic 35 次。原来以 CrossSlash Aim 作为 CROSS 的开始，一半的 CROSS 实例只有 Aim（被接着的 Evade 以 chain 结束）。
- Last Judge（LJ_）：INTRO、THROW（Throw Face Hero / Throw Antic，含 Censer Slam 与 Pull）、JUMP（Jump Antic / OJump Antic）、SPIN（含 Flame Spin、Rerage）、DASH、EVADE、CHARGE、STOMP、FLAME_ROAR、RAGE_ROAR、STUN、SING。
- Trobbio（TR_）：INTRO、FLASH、TORNADO、THROW、JUMP（含空中投掷、Flash Start Air）、EVADE（Tornado Evade）、EXIT（退场再入场）、FLURRY（Move Dir 2 起的炸弹连射）、COLUMNS（BC Pause 起）、SPIN、PHASE（Phase Roar）、STUN、SING。

Trobbio 的炸弹、龙卷风物体名以 "Trobbio " 开头且各有自己的 "Control" FSM：`FightTap` 原来按前缀匹配 boss，会把它们的状态记成 boss 的（冒烟第一场的 attacks 里有 Fling / Air / Explode）；已改成与表格构建器相同的精确匹配。

## 4. 冒烟（数据策略，1x）

- Last Judge `20261006_065020_LastJudge_data` ep0：CLEAR，游戏时间 235.9 s，Flame Roar 1、Rage Roar 1 都出现了；命中来源有 Swing Attack（Flame）、Censer Throw、Flame Wave、Charge Bomb、Roar Glow。
- Trobbio `20261006_065020_Trobbio_data` ep0：CLEAR，233.7 s，Phase Roar 出现；来源有 dazzle flash、Tornado Damager、Bomb、Tornado、Blast。
- Lace 1 `20261006_065020_Lace1_data`：2 场 CLEAR（约 96 s 实时），但没有醒来帧（存档离触发太近，见上），已作废；改存档后 `20261006_065722_Lace1_data` 2 场 CLEAR（112.9 / 78.2 s，有醒来帧）。另有一次 "paused unasked"（醒来后 0.9 s，原因未查明，只出现一次）。
- 三个 boss 轮换（同一个 worker，`20261006_065605_Lace1_mix_data`）：CLEAR 85.5 / 169.0 / 365.6 s。
- 每场的稀有动作：LJ_INTRO、LJ_FLAME_ROAR、TR_INTRO、TR_PHASE 约 1 次，LJ_RAGE_ROAR 约 1.5 次；每族 ≥ 200 次就要约 200 场。
- 两场的报表构建（只报告）：录像与 AttemptRecord 都能扫描；验证有少量接触没覆盖（Flame Wave、Roar Glow 没有导出碰撞体、Trobbio 的 dazzle flash），留待全量数据后处理。

## 5. 低血量起点

`enemy.hp`（oracle RPC，`oracle/src/Train/EnemyHpRpc.cs`，仅训练配置）：按 type_key 直接写 HealthManager.hp（hp 或 frac）。遭遇 `<名>_low` 在醒来后把 boss HP 乘以 0.25–0.6 的随机数。**未部署**，部署前 `_low` 遭遇会以 HARNESS_FAIL 结束。冒烟显示数据策略在时限内就能打死三个 boss、走到所有按 HP 的阶段，所以低血量起点只是加速后期阶段的数据，不是必需。

## 6. 全量构建与留出召回（2026-10-06 晚）

数据：`20261006_070641_Lace1_mix_data`（32 场，重标后全 CLEAR）+ `20261006_072930_Lace1_mix_data`（10 h，实例 0-4 轮换，代码 3039044）：Lace 341 场、Last Judge 337 场、Trobbio 335 场（含 2 场 STUCK）。构建 = `behaviour_build --encounter <名> --fsm-graph C:\ssbot\sandbox\route_bosses\graph_<名>.json` 的同一流程（按 unit 过滤；脚本扫描一次、存 builder、写表，允许验证失败），冻结检出 `C:\ssbot\live_bb_<rev>`，低于正常优先级。输出 `C:\ssbot\data\route_bosses\b*`（表、npz、builder pickle：Trobbio 全量 9.4 GB、LJ 每片 4.3 GB，可删）。

**留出召回的做法**：构建器自己的两折留出（按录像分折，录像里是整场战斗：每折的模板只来自本折的战斗，另一折的接触对它测距）。召回 = 留出的 anchor 集接触落在全量支撑半径内（±4 bin 时间余量）的比例，另列超过 R_FAIL 0.5 u 的个数。两种都报：严格 = 全量半径 + 规划器的配对（f-1 / f 的英雄框各 ±1 bin），t4 = 再加 ±4 bin（67 ms）时间余量；表里不另注的是 t4。没有留出接触的族（L1_INTRO、LJ_INTRO、LJ_DASH）是**没测**，不是 100 %。Bell Beast 的认证（`support_recall`，Forecaster，L 2–4）这三个 boss 还做不了：没有 BossSpec / Forecaster；这里是模板层面的同一种留出。全量 LJ / TR 的表格阶段很慢（TR 全量 6,432 s；LJ 单进程约 20 s/场），修复后的 LJ / TR 按场分 4 片（第 k 片 = 每 4 场取第 k 场，约 84 场一片）各自构建：实例数相加；片内两折各只用约 42 场训练，召回比全量更苛刻（同一份 Trobbio 代码，全量与分片的 TR_PHASE 留出 97.4 % 对 89.4 %）。

### 6.1 每族实例数（200 规则）与留出召回

| Lace 1（全量，36f99ef） | 实例 | 留出 anchor 召回 |
|---|---|---|
| L1_INTRO | 341 | 无接触 |
| L1_EVADE | 3,530 | 310 / 310 |
| L1_HOP | 3,190 | 18 / 18 |
| L1_CHARGE | 3,445 | 12,664 / 12,664 |
| L1_JSLASH | 1,606 | 4,133 / 4,141（严格 4,132；7 个超 0.5 u） |
| L1_COMBO | 3,571 | 11,475 / 11,475 |
| L1_COUNTER | 2,154 | 2,671 / 2,671 |
| L1_CROSS | 1,429 | 968 / 968（**严格只有 682 / 968 = 70.5 %**：时间抖动，±4 bin 内全中） |
| L1_STUN | 943 | 1,121 / 1,128（0 个超 0.5 u） |
| L1_LAVA | 234 | 40 / 40 |
| L1_IDLE | 18,608 | 8,142 / 8,142 |
| L1_SING | 0 | 要织针（数据策略不唱） |

验证通过（43,660 个接触，0 未覆盖 / 0 无法解释 / 0 攻击之外），`support_conservative` 真；熔岩 1,553 个接触全部在静态支撑内（留出 1,553 / 1,553）；543 个多段后续命中不检查（见 6.2）。

| Last Judge（4 片，979cc57） | 实例 | 留出 anchor 召回 |
|---|---|---|
| LJ_INTRO | 337 | 无接触 |
| LJ_THROW | 2,271 | 17,594 / 17,596（0 超） |
| LJ_JUMP | 1,392 | 5,216 / 5,216 |
| LJ_SPIN | 4,453 | 340,822 / 340,833（0 超） |
| LJ_DASH | 1,732 | 无 anchor 接触 |
| LJ_EVADE | 5,180 | 4,943 / 4,943 |
| LJ_CHARGE | 3,056 | 46,943 / 46,995（36 超，Charge End） |
| LJ_STOMP | 4,785 | 77,275 / 77,294（11 超） |
| LJ_FLAME_ROAR | 425 | 6,303 / 6,303（含光环） |
| LJ_RAGE_ROAR | 409 | 1,549 / 1,549 |
| LJ_STUN | 931 | 20,826 / 20,958（严格 20,780；177 超，Stun Air / Stun Start / Stunned） |
| LJ_IDLE | 21,733 | 26,231 / 26,231 |
| LJ_SING | 0 | 要织针 |

验证未过：549,425 个接触里 588 个未覆盖（接触 × 模板集的对；不同的接触 447 个）、0 无法解释、1,398 攻击之外（修复前 4,370）。

| Trobbio（4 片，b26cf2c；括号 = 最终代码 edcbd36 的全量构建 b5，约 167 场一折） | 实例 | 留出 anchor 召回 |
|---|---|---|
| TR_INTRO | 335 | 2,987 / 2,993（2,993 / 2,993） |
| TR_FLASH | 4,760 | 15,190 / 15,229（15,229 / 15,229） |
| TR_TORNADO | 7,853 | 17,067 / 17,099（17,094 / 17,099） |
| TR_THROW | 3,975 | 8,987 / 9,033（9,023 / 9,033） |
| TR_JUMP | 5,405 | 20,051 / 20,131（20,116 / 20,131） |
| TR_EVADE | 11,978 | 210 / 262（235 / 262） |
| TR_EXIT | 7,937 | 13,835 / 14,006（13,973 / 14,006） |
| TR_FLURRY | 1,637 | 10,159 / 10,425（10,392 / 10,425） |
| TR_COLUMNS | 2,650 | 30,499 / 30,595（30,567 / 30,595） |
| TR_SPIN | 3,372 | 2,663 / 2,671（2,667 / 2,671） |
| TR_PHASE | 335 | 1,186 / 1,326（1,291 / 1,326） |
| TR_STUN | 1,184 | 6,418 / 6,594（6,558 / 6,594） |
| TR_IDLE | 36,745 | 11,085 / 11,112（11,097 / 11,112） |
| TR_SING | 0 | 要织针 |

验证未过：141,480 个接触里 792 个未覆盖对（不同的接触 618 个）、0 无法解释、0 攻击之外（修复前 2,148 / 8,697 / 2,174）。括号里是最终代码的全量构建 b5（edcbd36，验证 700 个未覆盖对 / 597 个不同接触、0 无法解释、0 攻击之外）。早先这里引的是修复前代码的全量 b0：除 TR_INTRO（b0 1,026 / 1,026）和 TR_FLASH（b0 15,022 / 15,022）外与 b5 一字不差。分片里 TR_FLURRY 97.4 %、TR_STUN 97.3 %、TR_EXIT 98.8 % 是折小（每折约 42 场）造成的，全量里是 99.7 / 99.5 / 99.8 %。严格召回（全量 b5）：TR_EVADE 222 / 262（84.7 %）、TR_PHASE 1,258 / 1,326（94.9 %），其余族 ≥ 99.0 %。

### 6.2 验证缺口（HANDOFF 未决 2）

- **Lace 1 多段斩**（修了）：反击的 RapidSlash Charge 撞到英雄（HERO COLLIDE）→ Collide To Multihit → Hero Facing → Multihitting → Multihit Slash，Multihit Slash 用 PlayMaker 的 DamageHeroDirectly 扣血：英雄被抓住后在哪里都挨打（离她的碰撞体 0.5–6 u），173 个"未覆盖"全是它。`BehaviourSpec.direct_damage_states`（Lace：Multihit Slash、Finish Multihit、Bind Bell Damage，图里带 DamageHeroDirectly 的三个状态）：这些状态里 boss 的接触算多段后续命中（不检查、单独计数），钩子（MultiHit 碰撞体）照常检查。复核后收窄（edcbd36）：只有来源是 boss 本身（"Boss Scene/Lace Boss1"，DamageHeroDirectly 的事件就这么写）的接触才算后续命中，这些状态里 boss 碰撞体子物体的命中照常检查；341 场的 543 个后续命中来源全是 boss 本身，集合不变（验证 JSON 里另按导出与否分列）。
- **Lace 1 "Lava Box"**（不是缺口）：一个静态危险物（x 70.7–119.4，y −3.33–2.41，开场就武装），构建器按环境危险物处理，1,553 个熔岩接触全部在静态支撑内。
- **Lace 1 场地**（测了，改了）：341 场里地面 y 7.568 上英雄 x 82.0–106.0（0.5 u 分箱，每箱都有着地帧）；两侧是熔岩坑：英雄 x 77.4–81.5 与 106.5–110.4，坑底 y 约 2.2–2.5，熔岩接触时英雄 x 78–82 / 106–110；boss x 78.2–109.7（她也会掉进坑）。`LACE_1.arena_x` 由暂定的 (80, 115) 改为 (82.0, 106.0)（数据策略的走位范围）。
- **Last Judge "Roar Glow/Damager"**（修了）：光环并没有漏导出，它就是 boss 自己导出的 "Damager" 圆（r 4.04，dealt 1，咆哮期间），只是伤害事件的来源路径不带 boss 名，`match_source` 认不出。`BehaviourSpec.boss_parts`（LJ："Roar Glow"）：这类来源算 boss 的。攻击之外 4,370 → 1,398，LJ_FLAME_ROAR 的留出接触 3,331 → 6,303，全部覆盖。
- **Last Judge 剩下的**（没修）：攻击之外的 1,398 个是 "censer sphere/hero_damager"（香炉链球；那一帧 boss 只导出 Censer Slam 圆，没有 hero_damager：真的漏导出，要改 oracle 导出）；588 个未覆盖：Stun Air / Stun Start 一开始的身体接触（boss 身体框在硕直里 dealt 0，接触其实是上一个攻击的身体，归到了 STUN 的第 0 帧）、Stunned 里的 Swing Attack Flame/Hit Circle、Flame Wave(Clone) 的 Dmg 5/6/7 自身模板（无穷远残差）。
- **Trobbio 炫光**（部分修了）：Flash Burst 里炫光是 boss 自己导出的 "Damager" 圆（r 3.77，dealt 1），来源路径 "Trobbio_dazzle_flash/Damager"；但炫光在 Flash Burst 之后还会停留，这时它有时作为单独的实体导出、有时根本不导出。boss 导出该碰撞体时（近 LAG_F 帧内）算 boss 的，否则按原来的匹配。先试的"总算 boss 的"把无法解释从 8,697 推到 25,570（停留的炫光那时 boss 没导出它），已改正。复核发现只比名字不够：boss 还导出别的 "Damager"（Trobbio 的 poly11 在 TR_FLURRY、poly7 在 TR_COLUMNS，LJ 的 poly6 在 Charge End），edcbd36 起 `boss_parts` 是（部件根名，boss 导出它用的碰撞体 "名字:形状"）对：LJ ("Roar Glow", "Damager:circle")、TR ("Trobbio_dazzle_flash", "Damager:circle")，只在 boss 导出这个圆时算 boss 的。b26cf2c（4 片）：未覆盖 2,148 → 792、无法解释 8,697 → 0、攻击之外 2,174 → 0。剩下的未覆盖主要是 Blast/Damager（炸弹爆炸：BC Attack 与空闲尾巴里自身模板残差无穷远）和 TR_EXIT 等状态里停留的炫光。

### 6.3 Trobbio 的两场 STUCK（i3 ep110 剩 52 HP，i4 ep101 剩 7 HP）

不是 tap 的问题：两场都到了 Phase Roar、各 4 次硬直，每 100 s 的 Exit / Tornado Evade / Flash / Jump / Throw / Tornado 次数与 CLEAR 战斗相同（如 Exit 8.3 对中位 8.1、Tornado Evade 11.9 / 12.6 对 12.3），只是数据策略的输出慢：324 场 CLEAR 的游戏时间中位 287 s、p99 392 s、最长 415 s，420 s 的时限正好落在分布的尾巴里。`TROBBIO.timebox_s` 420 → 540 s。（Lace CLEAR 最长 141 s / 时限 300，LJ 最长 227 s / 420，都够。）

### 6.4 结论

- 实例数：三个 boss 每族都 ≥ 200，只有 *_SING 为 0（要织针；数据策略不唱）。按 200 规则**不用再收数据**；SING 要单独的织针策略。
- 召回 100 %：Lace 只差 L1_JSLASH（8 / 4,141）和 L1_STUN（7 / 1,128，都没超 0.5 u），验证已通过、支撑保守：可以停。Last Judge 的缺口是结构性的（漏导出的香炉链球、硬直开头的身体归属、Flame Wave 自身模板），多收数据关不掉，要改导出 / 构建器。Trobbio 的缺口有一部分是数据量：同样的模板做法，片内两折（每折约 42 场）对全量两折（约 167 场），TR_PHASE 89.4 % → 97.4 %、TR_EVADE 80.2 % → 89.7 %，随训练场数上升；其余 TR 族在最终代码的全量 b5 里 ≥ 99.4 %（严格 ≥ 99.0 %）。TR_PHASE 每场只有一次（335 个实例、1,326 个留出接触），要接近 100 % 粗估还要 2–3 倍的场数（再 350–700 场 Trobbio，每场约 5.4 分钟墙钟，5 个实例约 6–13 h）；更省的是部署 enemy.hp 后跑 Trobbio_low（醒来就降到 25–60 % 血，相位咆哮在下一次决策就出现）。TR_EVADE 的接触少（11,978 个实例里只有 262 个留出接触），也随数据改善。剩下的 Blast 自身模板是结构问题。

### 6.5 复核后的修正（edcbd36，构建 b5）

- `boss_parts` 按名字 + 形状匹配，`direct_damage_states` 只认 boss 本身的事件（见 6.2）。最终代码的构建 `C:\ssbot\data\route_bosses\b5`：Lace 全量、LJ 4 片、**Trobbio 全量**（单进程，约 2 h，留出两折各约 167 场：给出最终代码的全量召回，取代上面的 b0 对照），冻结检出 `C:\ssbot\live_bb_edcbd36`。汇总：`python <scratchpad>\rb_summary.py <目录[,目录...]> <boss>`（报 t4 与严格召回、未覆盖的对与不同接触、无留出接触的族标 UNMEASURED）。
- 结果（b5）：Lace 全量与 b1 完全一致（1,461 s）：543 个后续命中全部来自 boss 本身，而且全部算"已导出"（她的身体框就叫 Lace Boss1），所以"只排除未导出的接触"那种改法会把 173 个未覆盖放回来，按来源收窄才对。LJ 4 片与 b2 完全一致（588 对 / 447 个、0、1,398，各族留出不变）。Trobbio 全量（5,899 s）：各族留出接触数与 b26cf2c 的分片相同（名字 + 形状的收窄在这批数据里没有改动任何归属），验证 700 对 / 597 个未覆盖、0、0，留出见 6.1 括号。

## 7. Widow（第 2 轮，2026-10-06 晚）

- **开打方式：挑衅**（人 2026-10-06："黑寡妇可以直接挑衅"）。场景里有 "Challenge Region"（FSM "Challenge"：Init → Idle →（ENTER）In Region；In Region 的转移是 INTERACT → Hornet Voice、EXIT → Exit、SPECIAL CHALLENGE → Take Control）。英雄站在区域内（scout 中 x ≈ 45.8–63.2，y 8.57；社区原位 x 51.97 在区内，载入即 In Region）按 taunt 键（游戏动作 HeroActions.Taunt，键盘默认 V；我们的 ACTION 位 "taunt"），实测：In Region → Take Control → Facing → Face R → Challenge 1；"Speak Region" Dialogue Idle → Challenge → Look →（1.8 s）Challenge End；"Boss Scene" Control Speak Ready → Spinner Tele Out → Spinner Away → Battle Start；"Spinner Boss" Control Dormant → Set Intro Pos（挑衅后 171 帧 ≈ 2.85 s）→ Intro In → Scream Start → Intro Scream → Start Fight → Idle。不需要对话。第 1 轮看到 Boss Scene 停在 Speak Ready，以为要在 "Speak Region" 对话，是错的。
- 训练存档 `rb_widow` = vs_p6_s7 原样（x 51.97，y 8.57，5 面具，1 丝）。遭遇 `Widow`：`taunt_intro`（按 taunt 6 帧，然后不输入，等 Control 离开 Dormant），type_key "Spinner Boss"，HP 360。
- 死亡：全局 ZERO HP → Death Stagger（之后是剧本：Hornet Dash → Hornet Connect → Can Bind 等英雄按 BIND → Bind / Bind Burst …，路线上要按绑定，训练回合在击杀后就结束）。假死：另一个 FSM "Fake Death"（TOOK DAMAGE → Check（CompareHP）→ Send Event）发 FAKE DEATH → Death Stagger F → Fake Death End → Tele Out，之后是 P3（狂暴）；第一次进 Rage Start 1 时 SetHP 改她的血量（不是命中造成的 HP 变化）。
- 阶段：Phase Check（CompareHP）→ Move Choice P1 / P2 / P3。动作族（WI_）：INTRO、TELE_OUT（Tele Out → Away）、TELE_IN、SLAM（Start Spinning 起的 SlamString）、STRUM（Strum Start 1 / 2）、CHARGE（Charge / Rage Charge 1）、SCREAM（P2 起，Scream Antic + 线砸 L/R/Mid/Outer）、DASH（Dash Slash Dir → DashSlash → DashCharge，可接 Multihit Slash）、CHASE、EVADE、FAKE_DEATH、RAGE（Rage Scream 2，只第一次进 Rage Start 1 时走；Rage Start 1 本身每次 P3 出招都会进（冒烟第一场 23 次），按决策状态处理）、RAGE_SCREAM、RAGE_STRUM、RAGE_DASH（Rage Scuttle Antic）、STUN、SING。Random Pos / Retry Pos 是零时长的取位循环（一帧里来回几十次），算决策状态。
- 冒烟 `C:\ssbot\data\runs\m2\20261006_202750_Widow_data`（i0、i1，各 2 场，数据策略，1x，代码 7ac8e36）：4/4 CLEAR，游戏时间 289.6 / 244.0 / 236.7 / 317.8 s，每场都有醒来帧、Death Stagger、P1–P3 全部走到（Fake Death 1 次 / 场）。命中来源：Spinner AtkBell(Clone)（铃铛弹）、Spike Collider（场地尖刺组 set1/2/4）、NewCharge Hit、DashSlash Hit、boss 身体。
- 4 场的报表构建（只报告，修复轮重跑，`--fsm-graph C:\ssbot\sandbox\route_bosses\graph_Widow.json`）：每场都能扫描（17,376 / 14,642 / 14,204 / 19,068 帧），但**验证 FAILED**：3,416 个接触，没覆盖 4（3 个场地 Spike Collider（set1 / set4）的挡下帧，在 WI_CHARGE 的 `_tail` 里 t ≈ 4.05 s，残差 inf：超出自身模板的武装时长；1 个 blade/hero_damager，WI_IDLE `_tail`，0.70 u）、无法解释 0、攻击之外 0。（第一次报的 1,714 / 2 只是 2 场。）尖刺仍按自身模板（不改 world_fixed）：没覆盖的是时间上的尾巴，换成世界坐标也不变；留出验证 1,257 个里 1,254 个在内。计数：Death Stagger 中（击杀之后）boss 的伤害碰撞体还开着 244 帧，另有 1 个 Spinner AtkBell 在攻击之外武装；路线上击杀后到按绑定之前还要继续躲。每场的稀有族：WI_INTRO、WI_FAKE_DEATH、WI_RAGE 各 1，WI_STUN 2，WI_SCREAM 6，WI_CHASE 5；WI_SING 0（数据策略不唱）。要 200 次就要约 200–250 场。

## 8. Grand Mother Silk（第 2 轮）

- 开打同样是挑衅：载入后英雄（x 38.26，y 133.57）立刻在 "Challenge Region" 里（In Region），taunt → Take Control → Hornet Voice → Facing → Straight Back? → Face Straight Back → Challenge 2 → Challenge Complete；"Intro Sequence" 的 "First Challenge"：Idle →（CHALLENGE START）Challenge Cam → Wait For Beat End（2.5 s）→ Burst Anim（7.9 s）→ Ready Wait →（2.5 s）Intro Shake → Hero Facing → Silk Enter；"Silk Boss" Control Dormant → Ready（挑衅后约 11.3 s）→ Intro Up → Intro Roar → Title Up → Begin；Attack Control Dormant →（ATTACK）Init Pause 是开打（醒来帧）。
- 三个 FSM：Control（移动：Drift F/B、Dash、Juke，眩晕）、Attack Control（全部攻击）、Phase Control（P1–P6，每次换阶段 AddHP；P3 → P4 是剧本：Stagger Hit → Stagger Fall → Stagger Pause → BG Break Sequence → Rubble M → Rubble Sides → Set P4；HP Check 6 → Death Hit 是击杀）。研究资料里的阶段 HP 是 100 / 192 / 240 / 110 / 242 / 340（共 1,224）；ents 里载入时 HP 100。
- 接入：遭遇 `GMS`（`rb_gms` = vs_p7_s5 原样），`control_fsm` = "Attack Control"，新字段 `phase_fsm` = "Phase Control"：它进入 death_states（Death Hit）也算击杀（`FightTap`），表格构建器从它读阶段标记（Set P2 / Set P3 / Stagger Hit / Set P5 / Set P6）和死亡。换阶段的命中不是击杀（HP 会加回来），所以不能用 death_on_kill。
- 动作族（GM_，来自 Attack Control）：STOMP_SWIPE、CLAW、PINCER（手的组合，Hand Ptn Choice 选；Wait For Hands Ready 是手执行的时间，算在族里）、WEB、RUBBLE、SPIKE、ROAR、SING、DASH（DashAttack Prepare）、HAND_DASH（全局 PREPARE DASH）、CATCH（全局 HORNET CAUGHT：被丝线抓住后的斩击，DamageHeroDirectly，没有碰撞体）、STOP（全局 STUN / ATTACK STOP：眩晕或 P3→P4 的硬直）。她的移动（Control 的 Drift / Dash / Juke）与攻击同时进行，不单独成族。
- 冒烟 `C:\ssbot\data\runs\m2\20261006_202750_GMS_data`（i2、i3、i4 各 1 场）：3/3 CLEAR，游戏时间 519.2 / 596.2 / 510.9 s（时限 720 s），boss_hp_end −9 / −9 / −27。报表构建（只报告，`graph_GMS.json` = Attack Control）：扫描干净（31,154 / 35,774 / 30,655 帧），六个阶段每场都到；每 3 场：STOMP_SWIPE 162、PINCER 73、DASH 70、WEB 48、SPIKE 46（P5 起）、RUBBLE 45（P4 起）、CATCH 39、STOP 21、ROAR 6，**CLAW、HAND_DASH、SING 0**。验证 3,879 个接触：没覆盖 1、无法解释 39（CATCH 的 Slash End 直接伤害，没有导出的碰撞体）、攻击之外 621，**验证 FAILED**。修复轮查明：621 个全是冲刺斩（"DashSlash Effect/SlashHit 1-5"、"DashSlash End Effect/SlashHit 1"）：它们的多边形碰撞体被 oracle 导出在 Silk Boss 实体上（Hitbox Control 的 FSM 事件也带 boss 的 iid），但命中来源路径不经过 "Silk Boss"，所以匹配不到实体。新字段 `BehaviourSpec.boss_parts`（0c73ba7）把这两个根对象算作 boss：攻击之外 0，GM_DASH 905 个接触、残差 0。剩下没覆盖 1（Sprites/Sprite type 2，GM_STOMP_SWIPE，残差 inf）和无法解释 39，验证仍 FAILED（第 1 轮的 boss 也一样），正式构建要 `--allow-failed-validation`，靠留出召回判断。
- 场地 arena_x (20, 60)、floor_y 133.5677 是暂定值（没量）。

## 9. Lace 2（未接入）

社区存档 p7_s4（"Boss - Lace 2"）在 `Cog_Dancers`（x 39.93，y 4.60，Dancers 已打败：Boss Scene "Sequence" 走 Check → Defeated → Gates Opened → Door Entry → Idle Unlocked），Lace 2 本身在 `Song_Tower_01`：要用旋律升降梯（第一次要在 Cog_Dancers 演奏 Threefold Melody，之后 `UnlockedMelodyLift`，benches.md §1）。scout 自动左右走 24 s 没有找到 boss（ents 里没有 Lace，英雄还掉进尖刺）。要接入得先到 Song_Tower_01（例如 pdset UnlockedMelodyLift 后坐升降梯，或者找一个 Song_Tower_01 的存档），在触发前存训练存档。研究资料：Lace 2 800 HP。
