# 路线 boss（Forum 之外）：存档、触发、Control FSM（2026-10-06）

来源：社区存档（vichisuki BellRoute-LP，固定提交 0557f703fa25，`C:\ssbot\sandbox\savestates\community\0557f703fa25\manifest.json`；副本 `vs_p6_*` / `vs_p7_*`），探针 `brain/ssbot/probes/route_bosses.py`（scout：fsmtap all + fsm.graph；save：游戏写出的训练存档），输出 `C:\ssbot\sandbox\route_bosses\*_scout.json`（含完整的 Control 静态图）。训练副本、oracle 视图、存档写入关闭。

## 1. 哪些 boss 有现成存档

| 路线 | boss | 社区存档 | 场景 | 状态 |
|---|---|---|---|---|
| S07 | Lace 1 | p6_s3 = vs_p6_s3 | Bone_East_12 | **已接入**（`rb_lace1`） |
| S08 | Fourth Chorus | 无 boss 存档（社区路线跳过它：p8_s5 / p8_s6 "Fourth Chorus Skip"，Bone_East_08 x 98） | Bone_East_08 | 未做：要从跳过存档走到竞技场再存 |
| S13 | Widow | p6_s7 = vs_p6_s7 | Belltown_Shrine | **已接入**（第 2 轮，`rb_widow`）：不需要对话，**挑衅（taunt 键）**即开打（§6）。第 1 轮"要先对话"的结论是错的 |
| S17 | Last Judge | p6_s8 = vs_p6_s8 | Coral_Judge_Arena | **已接入**（`rb_lastjudge`） |
| S19 | Cogwork Dancers | p6_s9 = vs_p6_s9 | Cog_Dancers | 未做：两个 boss（"Dancer A" / "Dancer B" 各 190 HP），走 5.4 s 后醒；单 boss 的表格构建器不适用 |
| S22 | Trobbio | p7_s1 = vs_p7_s1 | Library_13 | **已接入**（`rb_trobbio`） |
| S26 | Lace 2 | p7_s4 = vs_p7_s4 | Cog_Dancers（战斗在 Song_Tower_01） | 未做：存档在 Cog_Dancers（Dancers 已打完，x 39.93），Lace 2 在 `Song_Tower_01`，要坐旋律升降梯（`UnlockedMelodyLift`，第一次要演奏 Threefold Melody，benches.md §1）换场景才到；scout 自动左右走 24 s 没有 boss、还掉进了尖刺。要先做一个 Song_Tower_01 里的训练存档（§8） |
| S27 | Grand Mother Silk | p7_s5 = vs_p7_s5 | Cradle_03 | **已接入**（第 2 轮，`rb_gms`）：同样挑衅开打（§7） |

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

## 6. Widow（第 2 轮，2026-10-06 晚）

- **开打方式：挑衅**（人 2026-10-06："黑寡妇可以直接挑衅"）。场景里有 "Challenge Region"（FSM "Challenge"：Init → Idle →（ENTER）In Region；In Region 的转移是 INTERACT → Hornet Voice、EXIT → Exit、SPECIAL CHALLENGE → Take Control）。英雄站在区域内（scout 中 x ≈ 45.8–63.2，y 8.57；社区原位 x 51.97 在区内，载入即 In Region）按 taunt 键（游戏动作 HeroActions.Taunt，键盘默认 V；我们的 ACTION 位 "taunt"），实测：In Region → Take Control → Facing → Face R → Challenge 1；"Speak Region" Dialogue Idle → Challenge → Look →（1.8 s）Challenge End；"Boss Scene" Control Speak Ready → Spinner Tele Out → Spinner Away → Battle Start；"Spinner Boss" Control Dormant → Set Intro Pos（挑衅后 171 帧 ≈ 2.85 s）→ Intro In → Scream Start → Intro Scream → Start Fight → Idle。不需要对话。第 1 轮看到 Boss Scene 停在 Speak Ready，以为要在 "Speak Region" 对话，是错的。
- 训练存档 `rb_widow` = vs_p6_s7 原样（x 51.97，y 8.57，5 面具，1 丝）。遭遇 `Widow`：`taunt_intro`（按 taunt 6 帧，然后不输入，等 Control 离开 Dormant），type_key "Spinner Boss"，HP 360。
- 死亡：全局 ZERO HP → Death Stagger（之后是剧本：Hornet Dash → Hornet Connect → Can Bind 等英雄按 BIND → Bind / Bind Burst …，路线上要按绑定，训练回合在击杀后就结束）。假死：另一个 FSM "Fake Death"（TOOK DAMAGE → Check（CompareHP）→ Send Event）发 FAKE DEATH → Death Stagger F → Fake Death End → Tele Out，之后是 P3（狂暴）；第一次进 Rage Start 1 时 SetHP 改她的血量（不是命中造成的 HP 变化）。
- 阶段：Phase Check（CompareHP）→ Move Choice P1 / P2 / P3。动作族（WI_）：INTRO、TELE_OUT（Tele Out → Away）、TELE_IN、SLAM（Start Spinning 起的 SlamString）、STRUM（Strum Start 1 / 2）、CHARGE（Charge / Rage Charge 1）、SCREAM（P2 起，Scream Antic + 线砸 L/R/Mid/Outer）、DASH（Dash Slash Dir → DashSlash → DashCharge，可接 Multihit Slash）、CHASE、EVADE、FAKE_DEATH、RAGE（Rage Scream 2，只第一次进 Rage Start 1 时走；Rage Start 1 本身每次 P3 出招都会进（冒烟第一场 23 次），按决策状态处理）、RAGE_SCREAM、RAGE_STRUM、RAGE_DASH（Rage Scuttle Antic）、STUN、SING。Random Pos / Retry Pos 是零时长的取位循环（一帧里来回几十次），算决策状态。
- 冒烟 `C:\ssbot\data\runs\m2\20261006_202750_Widow_data`（i0、i1，各 2 场，数据策略，1x，代码 7ac8e36）：4/4 CLEAR，游戏时间 289.6 / 244.0 / 236.7 / 317.8 s，每场都有醒来帧、Death Stagger、P1–P3 全部走到（Fake Death 1 次 / 场）。命中来源：Spinner AtkBell(Clone)（铃铛弹）、Spike Collider（场地尖刺组 set1/2/4）、NewCharge Hit、DashSlash Hit、boss 身体。
- 两场的报表构建（只报告，`--fsm-graph C:\ssbot\sandbox\route_bosses\graph_Widow.json`）：扫描干净（17,376 / 14,204 帧）；验证 1,714 个接触，没覆盖 2、无法解释 0、攻击之外 0（只因 2 个没覆盖而 FAILED，2 场的正常情况）。每场的稀有族：WI_INTRO、WI_FAKE_DEATH、WI_RAGE 各 1，WI_STUN 2，WI_SCREAM 6，WI_CHASE 5；WI_SING 0（数据策略不唱）。要 200 次就要约 200–250 场。

## 7. Grand Mother Silk（第 2 轮）

- 开打同样是挑衅：载入后英雄（x 38.26，y 133.57）立刻在 "Challenge Region" 里（In Region），taunt → Take Control → Hornet Voice → Facing → Straight Back? → Face Straight Back → Challenge 2 → Challenge Complete；"Intro Sequence" 的 "First Challenge"：Idle →（CHALLENGE START）Challenge Cam → Wait For Beat End（2.5 s）→ Burst Anim（7.9 s）→ Ready Wait →（2.5 s）Intro Shake → Hero Facing → Silk Enter；"Silk Boss" Control Dormant → Ready（挑衅后约 11.3 s）→ Intro Up → Intro Roar → Title Up → Begin；Attack Control Dormant →（ATTACK）Init Pause 是开打（醒来帧）。
- 三个 FSM：Control（移动：Drift F/B、Dash、Juke，眩晕）、Attack Control（全部攻击）、Phase Control（P1–P6，每次换阶段 AddHP；P3 → P4 是剧本：Stagger Hit → Stagger Fall → Stagger Pause → BG Break Sequence → Rubble M → Rubble Sides → Set P4；HP Check 6 → Death Hit 是击杀）。研究资料里的阶段 HP 是 100 / 192 / 240 / 110 / 242 / 340（共 1,224）；ents 里载入时 HP 100。
- 接入：遭遇 `GMS`（`rb_gms` = vs_p7_s5 原样），`control_fsm` = "Attack Control"，新字段 `phase_fsm` = "Phase Control"：它进入 death_states（Death Hit）也算击杀（`FightTap`），表格构建器从它读阶段标记（Set P2 / Set P3 / Stagger Hit / Set P5 / Set P6）和死亡。换阶段的命中不是击杀（HP 会加回来），所以不能用 death_on_kill。
- 动作族（GM_，来自 Attack Control）：STOMP_SWIPE、CLAW、PINCER（手的组合，Hand Ptn Choice 选；Wait For Hands Ready 是手执行的时间，算在族里）、WEB、RUBBLE、SPIKE、ROAR、SING、DASH（DashAttack Prepare）、HAND_DASH（全局 PREPARE DASH）、CATCH（全局 HORNET CAUGHT：被丝线抓住后的斩击，DamageHeroDirectly，没有碰撞体）、STOP（全局 STUN / ATTACK STOP：眩晕或 P3→P4 的硬直）。她的移动（Control 的 Drift / Dash / Juke）与攻击同时进行，不单独成族。
- 冒烟 `C:\ssbot\data\runs\m2\20261006_202750_GMS_data`（i2、i3、i4 各 1 场）：3/3 CLEAR，游戏时间 519.2 / 596.2 / 510.9 s（时限 720 s），boss_hp_end −9 / −9 / −27。报表构建（只报告，`graph_GMS.json` = Attack Control）：扫描干净（31,154 / 35,774 / 30,655 帧），六个阶段每场都到；每 3 场：STOMP_SWIPE 162、PINCER 73、DASH 70、WEB 48、SPIKE 46（P5 起）、RUBBLE 45（P4 起）、CATCH 39、STOP 21、ROAR 6，**CLAW、HAND_DASH、SING 0**。验证 3,879 个接触：没覆盖 1、无法解释 39（CATCH 的 Slash End 直接伤害，没有导出的碰撞体）、攻击之外 621（待查：大概是 Control 移动时的身体接触或手 / 丝线在攻击结束后还在动）。
- 场地 arena_x (20, 60)、floor_y 133.5677 是暂定值（没量）。

## 8. Lace 2（未接入）

社区存档 p7_s4（"Boss - Lace 2"）在 `Cog_Dancers`（x 39.93，y 4.60，Dancers 已打败：Boss Scene "Sequence" 走 Check → Defeated → Gates Opened → Door Entry → Idle Unlocked），Lace 2 本身在 `Song_Tower_01`：要用旋律升降梯（第一次要在 Cog_Dancers 演奏 Threefold Melody，之后 `UnlockedMelodyLift`，benches.md §1）。scout 自动左右走 24 s 没有找到 boss（ents 里没有 Lace，英雄还掉进尖刺）。要接入得先到 Song_Tower_01（例如 pdset UnlockedMelodyLift 后坐升降梯，或者找一个 Song_Tower_01 的存档），在触发前存训练存档。研究资料：Lace 2 800 HP。
