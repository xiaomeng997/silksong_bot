# 路线 boss（Forum 之外）：存档、触发、Control FSM（2026-10-06）

来源：社区存档（vichisuki BellRoute-LP，固定提交 0557f703fa25，`C:\ssbot\sandbox\savestates\community\0557f703fa25\manifest.json`；副本 `vs_p6_*` / `vs_p7_*`），探针 `brain/ssbot/probes/route_bosses.py`（scout：fsmtap all + fsm.graph；save：游戏写出的训练存档），输出 `C:\ssbot\sandbox\route_bosses\*_scout.json`（含完整的 Control 静态图）。训练副本、oracle 视图、存档写入关闭。

## 1. 哪些 boss 有现成存档

| 路线 | boss | 社区存档 | 场景 | 状态 |
|---|---|---|---|---|
| S07 | Lace 1 | p6_s3 = vs_p6_s3 | Bone_East_12 | **已接入**（`rb_lace1`） |
| S08 | Fourth Chorus | 无 boss 存档（社区路线跳过它：p8_s5 / p8_s6 "Fourth Chorus Skip"，Bone_East_08 x 98） | Bone_East_08 | 未做：要从跳过存档走到竞技场再存 |
| S13 | Widow | p6_s7 = vs_p6_s7 | Belltown_Shrine | 未做：boss 名 "Spinner Boss"，Control 停在 Dormant；"Boss Scene" Control 走 Unencountered → Speak Pause → Speak Ready，要先对话（交互区 "Speak Region"），向右 / 向左走 18 s 都没触发 |
| S17 | Last Judge | p6_s8 = vs_p6_s8 | Coral_Judge_Arena | **已接入**（`rb_lastjudge`） |
| S19 | Cogwork Dancers | p6_s9 = vs_p6_s9 | Cog_Dancers | 未做：两个 boss（"Dancer A" / "Dancer B" 各 190 HP），走 5.4 s 后醒；单 boss 的表格构建器不适用 |
| S22 | Trobbio | p7_s1 = vs_p7_s1 | Library_13 | **已接入**（`rb_trobbio`） |
| S26 | Lace 2 | p7_s4 = vs_p7_s4 | Cog_Dancers | 未做（预算） |
| S27 | Grand Mother Silk | p7_s5 = vs_p7_s5 | Cradle_03 | 未做（预算） |

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
