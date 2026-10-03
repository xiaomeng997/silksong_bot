# 1.0.30000 Forum（High Halls 竞技场连战，`Hang_04`）事实记录（M2 W8 上半）

来源：反编译源码 `C:\ssbot\decomp\1.0.30000\Assembly-CSharp`（下称"反编译"）、训练副本场景包（UnityPy 读 `hang_04.bundle`、`hang_04_boss.bundle`、`hang_06.bundle`，脚本在会话临时目录 `fo/`：`scene_tree.py`、`waves.py`、`fsm_dump2.py`、`colliders.py`、`scan_all.py`）、社区 savestate `p7_s3`（`C:\ssbot\sandbox\savestates\community\0557f703fa25\p7_s3.json`）、autosplit 源码（`C:\ssbot\ref\silksong-autosplit-wasm`）。实测部分注明运行目录。未核实的说法标【未核实】。

## 1. 场景结构

- 房间 = `Hang_04`（主场景）+ `Hang_04_boss`（加法加载的子场景，社区存档的 `loadedScenes` 两个都有）。`Hang_04` 的 `Boss Loader`（SceneAdditiveLoadConditional）加载子场景。出口：`left1`（x −0.5，到 `Hang_12`，即去 Conductor 的方向）、`right1`（x 71.5，到 `Hang_06`，路线从这里进来）。autosplit：进 Forum = `Hang_06 → Hang_04`，出 Forum = `Hang_04 → Hang_12`。
- 连战 = `Hang_04_boss` 根对象 `Battle Scene` 上的一个 `BattleScene` 组件（反编译 `BattleScene.cs`），不是 boss FSM。字段：14 个 `BattleWave`，`setPDBoolOnEnd = "hang04Battle"`，`battleStartEventRegister = "FORUM BATTLE START"`，`battleEndEventRegister = "FORUM BATTLE END"`，`battleStartPause 0.75`，`battleEndPause 2.0`，`openGatesOnEnd = 0`（门由吊灯 FSM 打开，见 §3）。
- 开战触发：`Battle Scene/Start Range`（触发盒 x 12.04–32.75、y 0.95–25.04；FSM `Control`）。主角从右边走进盒子 → `Roar Lock`（锁相机、吼叫音效、`ROAR ENTER`，1 s）→ `Wake Threads`（等丝线动画事件）→ `Pull Quake`（主角被拉、`Collect Normal` 动画、0.75 s 后调 `StartBattle`）→ `Hero Rise` → `Wake`（再调一次 `StartBattle`，第二次无效）。`Start Range` 带 PersistentBoolItem：已激活过的存档直接走 `Woken` → `StartBattle`。`Battle Scene` 自己的触发盒（x 20.43–33.57）在场景包里是禁用的。
- `StartBattle` → 关门（`BG CLOSE`）、锁相机，0.75 s 后 `StartWave(0)`。
- 门（`Battle Scene/Gates`，TERRAIN 层，碰撞盒 + 上方 `Wall Collider`）：左门 x 10.54–14.01、y 2.96–9.07，上段 x 10.57–14.01、y 8.98–15.08；右门 x 48.99–53.17、y 2.94–9.05，上段 x 48.99–53.27、y 8.93–15.04。所以关门后场地内侧 x 14.01–48.99（约 35 u）。
- 相机锁：`CameraLockArea` 相机中心 x 27.1–36.2、y 9.6；`CameraLockArea (1)`（多边形，y 15.4–33.05 的高处）y 9.6–16.1。
- 社区存档出生点 x 53.24、y 4.5677（右门外侧，面朝左的方向待实测），离触发盒右边 21 u。
- 地面高度、平台、左墙顶的可贴墙位置：见 §8（TERRAIN 实测）。

## 2. 波次（场景包 `Battle Scene.waves`，按顺序）

`BattleScene` 规则（反编译）：`StartWave(i)` 激活第 i 波、发 `WAVE QUEUED`，等 `startDelay` 后 `WaveStarted`（把这一波带 HealthManager 的子物体计入 `currentEnemies`，发 `BATTLE START`），1 s 后按子物体数检查一次；`HealthManager.Die` 调 `DecrementEnemy`（`bigEnemyDeath` 的晚 1 s；本场所有敌人 `bigEnemyDeath = 0`）；`currentEnemies ≤ remainingEnemyToEnd` 时下一波开始，最后一波结束调 `EndBattle`。`remainingEnemyToEnd > 0` 的波（索引 2、4、9）在本波敌人没死完时就放下一波，波次会重叠。

| 索引 | BattleWave | startDelay s | remainingEnemyToEnd | 敌人（GameObject 名，出生点 x, y，HP） |
|---|---|---|---|---|
| 0 | Wave 1 | 0.0 | 0 | Song Reed (30.73, 12.53) 55；Song Pilgrim 01 (44.92, 5.13) 38；Song Pilgrim 03 (19.41, 4.53) 55 |
| 1 | Wave 2 - Call Ally | 1.0 | 0 | Song Pilgrim 03 (2) (22.75, 4.53) 55；Song Pilgrim 03 (3) (39.97, 4.53) 55；本波开始 4 s 后叫助战（§4） |
| 2 | Wave 3 | 1.0 | 2 | Pilgrim 03 Song (39.25, 10.96) 35；Song Reed (1) (21.37, 10.53) 55 |
| 3 | Wave 4 | 0.5 | 0 | Song Handmaiden (1.67, 46.23) 48 |
| 4 | Wave 5 - Song Admins | 1.0 | 1 | Song Administrator (40.68, 11.34) 60；Song Administrator (1) (20.6, 11.34) 60 |
| 5 | Wave 6 | 0.0 | 0 | Song Handmaiden (1.67, 46.23) 48 |
| 6 | Wave 7 - Maestro x 2 | 1.0 | 0 | Song Pilgrim Maestro (20.51, 10.87) 65；Song Pilgrim Maestro (1) (42.51, 10.87) 65 |
| 7 | Wave 8 - Heavy Sentry | 1.5 | 0 | Song Heavy Sentry (31.03, 25.73) 230（波开始发 `HEAVY WAVE`） |
| 8 | Wave 9 | 3.0 | 0 | Song Reed (2) (40.34, 11.16) 55；Song Reed (3) (21.44, 11.16) 55；Pilgrim 03 Song (31.05, 10.96) 35 |
| 9 | Wave 10 | 1.0 | 2 | Song Pilgrim 03 (2) (30.85, 4.95) 55；Pilgrim 03 Song (21.34, 10.96) 35；Pilgrim 03 Song (1) (39.25, 10.96) 35 |
| 10 | Wave 11 | 0.5 | 0 | Song Handmaiden (1.67, 46.23) 48 |
| 11 | Wave 12 | 1.0 | 0 | Pilgrim 03 Song (1) (31.35, 12.43) 35；Song Administrator (40.68, 11.34) 60；Song Administrator (1) (20.6, 11.34) 60 |
| 12 | Wave 13 - Maestro | 2.0 | 0 | Song Pilgrim Maestro (24.42, 10.87) 65；Song Reed (39.64, 10.9) 55 |
| 13 | Wave 14 - Finale | 2.0 | 0 | Song Heavy Sentry (2) (21.03, 23.73) 230；Song Heavy Sentry (3) (42.03, 23.73) 230（`HEAVY WAVE`） |

- 共 28 个敌人。出生点是场景包里的初始位置；Handmaiden 在 (1.67, 46.23)（场地左上远处，飞进来），Heavy Sentry 从 y 23–26 落下（`Rest` → `Drop Antic` → `Drop In` → `Enter Land`）。
- `activateEnemiesOnStart = 0` 的是索引 1、6、12（敌人一直在场景里，FSM 等 `BATTLE START`），其余开波时才激活。
- 研究资料说 "13 波"（research.json，wiki 原文），游戏数据是 14 个 BattleWave；差别大概来自索引 2（2 个敌人、remainingEnemyToEnd 2：开波 1 s 后的子物体检查就会放下一波，所以和索引 3 连成一波）【推测，用 room.battles 实测核对】。
- 伤害（DamageHero.damageDealt，全部 hazardType 1 = ENEMY）：Song Heavy Sentry 本体与 `Slam Collider 1/2` = **2**；Song Handmaiden `Spear` = **2**，其余 1；Song Reed / Song Pilgrim 01 / Song Pilgrim 03 / Pilgrim 03 Song / Song Administrator / Song Pilgrim Maestro 全部 1（Song Pilgrim 03 的 `Whip Hit 1–6` 和 Song Reed 的 `ParrySlash Hit`、Administrator 的 `Slash Collider` 为 0）。research.json 的 "Choir Clapper：锤、接触、丝砸全为 2，丝内爆 1"：锤、接触 = 2 与场景包一致；丝砸、丝内爆是 `Bomb Cast` 生成的投射物，场景包里看不到，待实测。
- 内部名与社区名【未核实，按 HP 和招式推断】：Song Heavy Sentry = Choir Clapper（230 HP、末波 2 只，研究资料一致）；Song Handmaiden = Clawmaiden（有 `Silk Suck` FSM，偷丝）；Song Administrator = Minister；Song Pilgrim Maestro = Maestro；Song Reed = Reed；Song Pilgrim 01 / Song Pilgrim 03 / Pilgrim 03 Song 对应 Choristor / Envoy / Choir Bellbearer 中的哪一个待查（Pilgrim 03 Song 会飞、35 HP）。
- 各类型 FSM：Song Heavy Sentry `Control`（`Slam Antic`、`Jump Antic → Jump Aim → Jump → Air → Charged? → Slam`、`Spell Antic → Cast 1/2`（`Bomb Cast` FSM 放丝弹）、`Cast Slam Antic`、`Evade Scuttle`、`Avoid Type`（`AVOID BUDDY`：两只互相让））；其余类型的状态表在 `fo/fsm_enemy_*.txt`（场景包导出），行为表从采集录像生成。

## 3. 怎么结束

- `EndBattle`：`completed = true`，`FreezeMoment(EnemyBattleEndSlow)`（oracle "freeze" 事件 type `EnemyBattleEndSlow`，除非 `noEndSlomo`），1 s 后播结束音，再等 `battleEndPause` 2 s 后写 PlayerData `hang04Battle = true`（autosplit 的 "High Halls Arena" 分段就看这个），发 `FORUM BATTLE END`。
- 门不由 BattleScene 开（`openGatesOnEnd = 0`）：`Hang_04` 的 `Hang Battle Drop Lamp`（FSM `Drop Control`）收到 `FORUM BATTLE END` → 吊灯掉下 → `End Arena` 2 s 后发 `DISABLE CAMLOCKS`、`BG OPEN`。吊灯在两次 `HEAVY WAVE` 后各下降一截（Heavy Sentry 落地时），只是表演；吊灯本体只有 r 3.75 的圆形碰撞体，没有 DamageHero。
- `hang04Battle` 之后：`EnteredNewMapZone` / `FixUpSaveState` 置 `leftTheGrandForum`；`Hang_06` 的助战 NPC 不再出现。
- 奖励：Conductor's Melody 在 Forum 之后的房间（研究资料：High Halls 1 连战奖励是 Conductor's Melody，wiki）【未核实位置】。
- 本仓库的判定（`ssbot.train.gauntlet.GauntletTap`）：CLEAR = STATE `room.battles` 的 `completed`（新 oracle）；旧 oracle 用 `EnemyBattleEndSlow` 冻结或按击杀重放 `DecrementEnemy` 走完最后一波。

## 4. 助战（Garmond & Zaza / Shakra）

- `Hang_04_boss` 里 `Battle Scene` 下一直有 `Garmond Fighter`（(43.6, 7.5)）和 `Shakra Fighter`（(33.0, 5.55)），两者都没有 HealthManager。
- 叫助战：`Wave 2 - Call Ally` 的 FSM `Call Ally` 在 `WAVE START` 时给 `Call Ally` 对象发 `CALL ALLY`；`Call Ally` FSM `Control`：等 4 s → `Call?`：PlayerData `garmondAidForumBattle` 为真 → 给 `Garmond Fighter` 发 `ENTER FORUM`；否则 `shakraAidForumBattle` 为真 → `Shakra Fighter`；都不真就自毁。所以助战在索引 1 那波开始 4 s 后才进场（Garmond 优先）。
- 标志从哪来：`Hang_06`（Forum 右边的房间）的 `Aid NPC Control`：`hang04Battle` 为真 → 不出现；Shakra 的任务（Trail's End 许愿，`CheckQuestStateV2`）完成 → 出 Shakra 助战 NPC 并把 `garmondAidForumBattle` 置假；否则 `garmondWillAidInForumBattle` 为真 → 出 `Garmond Aid NPC`。和他说话选"是"（`REQUEST_AID`）→ `garmondAidForumBattle = true`（FSM `Behaviour` 的 `Accept`）。`garmondWillAidInForumBattle` 在 `Library_09`（Whispering Vaults 屋顶的切磋房间）被 `Scene Control`（PlayerDataTestResponse）和 `Garmond Fighter`（FSM 变量覆盖）引用，推断是切磋赢了之后置真【未核实写入点】；`Song_01/02/13/17` 的 `Garmond Fight Scene` 也测试它。
- `GameManager.LoadedFromMenu`（从主菜单读档）把 `garmondAidForumBattle`、`shakraAidForumBattle` 清零：**真实路线里不能在 Hang_06 招募后退出再读档**，否则助战丢失（退出 = 紧急流程的后果之一，路线和恢复表要知道）。DebugMod 读 savestate 是否也清零：见 §7 实测。
- Garmond 在 Forum 的 FSM（`Control`）：`ENTER FORUM` → `Jump In` → `Enter Fall` → `Enter Land` → `Roar` → `Idle` / `Chase Target`（`Wildslash`、`Jump`/`Stomp`、`Charge`、`Hop`），攻击只启用 `WildSlash Enemy Damager`、`Stomp Damager`、`Charge Damager`（DamageEnemies，打敌人）；会伤主角的 `WildSlash Hero Damager 1–5`（DamageHero 1）只在 `Wildslash VsHero*` 状态启用，这些状态只从 `HERO BATTLE` 事件进入（切磋）。他还有 `Friend Bind`（Bind 回应）、`Heavy Sentry Roar`、`Battle End Antic → Goto Battle End Point`（`Ally Battle End Point` (37.0, 6.39)）。所以在 Forum 里 Garmond 的攻击不是威胁，符合 DESIGN §3.5.7。
- oracle 导出：两个 Fighter 都不在 "ents"（无 HealthManager，DamageHero 子物体不启用）。新增 STATE `allies`（`Entities.AllyWatch`，提交 cd215cc，未部署）导出 BattleScene 下名字以 " Fighter" 结尾、无 HealthManager 的子物体（位置、速度、`Control` 状态、碰撞盒）和所有 Cogfly。

## 5. 工具与纹章 id

- Cogfly = ToolItem **"Cogwork Flier"**（autosplit `has_tool("Cogwork Flier")`）；放出的虫子是 `ClockworkHatchling`（反编译 `ClockworkHatchling.cs`：状态 Follow/Aggro/Tele/Attack/…，有自己的 hp）。不在 "ents"（不伤主角），新 `allies` 导出。
- Ascendant's Grip = ToolItem **"Wallcling"**（autosplit；代码里是 `Gameplay.WallClingTool`，`HeroController.cs` 2230 行：装备时滑墙中按住朝墙方向 → `cState.wallClinging`、关闭重力）。
- 纹章 id：`Hunter`、`Hunter_v2`、`Hunter_v3`、`Reaper`、`Wanderer`（m0.md、P17 crests）。
- 社区存档 p7_s3：`CurrentCrestID = Hunter`（未进化），只解锁了 Hunter；`ToolEquips` 只有 Hunter 一项，7 个槽里只装了 `Silk Spear`；`Tools` 为空（没有任何红/蓝/黄工具，没有 Cogfly、没有 Grip）；5 面具、丝 1、Needle 1（nailUpgrades 1）、念珠 332、壳片 44；能力：冲刺、Cling Grip、Drifter's Cloak、Clawline、Needolin 有，**Faydown（二段跳）无、Silk Soar 无**、Needle Strike 无；助战标志全假。

## 6. 取得地点（路线输入）

- Reaper 纹章：场景包里 `Greymoor_20c` 有 `Crest Get Shrine`（FSM 引用 `completedMemory_reaper`）和 `chapel_candle_control`，`Greymoor_20b` 有 `Chapel Door Control`（`chapelClosed_reaper`）和满屋的蜡烛开关 → Reaper 的礼拜堂在 Greymoor（`Greymoor_20b` 进门、`Greymoor_20c` 取纹章，取得 = `completedMemory_reaper`，autosplit "Reaper Crest"）。礼拜堂门的开启条件、记忆场景的内容和绕路时间【未核实】。
- Ascendant's Grip：场景包字符串里找不到拾取点（拾取物引用的是资源，不是名字；只有 Lace 1 / Lace 2 / Lost Lace 的 FSM 提到 "Wallcling"）。社区说法：Dancers 和 Forum 末波都靠它贴墙（research.json）。取得地点【未知，需要查商店清单或拾取物资源】。
- Cogfly：DESIGN §3.6.4 路线 S25 写在 High Halls（✚ Cogfly，用 1 块工艺金属合成）【未核实合成地点】。

## 7. savestate 组装与验证

（实测后补，见下次更新）

## 8. 场地几何（TERRAIN 实测）

（实测后补）

## 9. oracle 导出核对

（实测后补）
