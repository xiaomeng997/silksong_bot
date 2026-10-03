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
- Cogfly：`Hang_09`（High Halls）的 `Craft Pickup`（FSM `FSM`，检视文本 `COG_FLIER`）：检视 → `DialogueYesNoItemV3` 消耗 1 个所需物品（场景包里是资源引用，按 DESIGN 是 1 块工艺金属）→ 主角走到桌前、转身做工约 7.5 s（`Hero Face Table` 1.5 s + `Craft` 4.5 s + `Turn Back` 1.5 s）→ 得到物品。这段时间 `disablePause = 1`（`Wait` 置 1，`Get Item` 置 0）：**约 8 s 不能暂停**，路线和 quit map 要登记（房间里没有威胁时无妨）。与 DESIGN §3.6.4 S25 "High Halls → ✚ Cogfly" 一致。

## 7. savestate 组装与验证（实例 2，2026-10-02 20:52–21:05，`ssbot.probes.forum_setup`，结果 JSON 在 `C:\ssbot\sandbox\forum_setup\`）

- 组装：`fo_pre_help7` / `fo_pre_nohelp7` = p7_s3 + 7 面具（health / maxHealth / maxHealthBase 7）+ 助战标志（help：`garmondAidForumBattle`、`garmondWillAidInForumBattle`、`garmondLibraryDefeatedHornet`、`metGarmond` 为真；nohelp：与 p7_s3 相同，全假）。游戏内 `crest.equip`（unlock）+ `abilities.grant {set: movement, tools}`（不带 combat 组，免得给 Needle Strike 和全部丝技）→ 存 `fo_X_raw` → 离线把 grant 多给的 `hasDoubleJump`、`hasSuperJump` 改回假（**路线在 Forum 时没有二段跳和 Silk Soar**），并把 Silkspear 放进新纹章空的 Skill 槽（第一次装备的纹章没有存档的装备，Silkspear 留在 Hunter）→ 读回 → 游戏再存成 `fo_X`。
- 读回核对（abilities.list + crest.dump + PROGRESS PlayerData）：
  - **fo_A**：Reaper；槽 0 Skill/Neutral = Silk Spear，槽 1 Red/Up = Cogwork Flier（4 次），槽 6 Yellow = Wallcling；7 面具、丝 1；冲刺 / Cling Grip / 披风 / Clawline 有，二段跳 / Silk Soar / Needle Strike 无；`garmondAidForumBattle` 真。纹章配置 `can_double_jump` 为真，但 PlayerData 没有 Faydown，所以没有二段跳。
  - **fo_A5**：同 fo_A，5 面具。
  - **fo_B**：Hunter_v2（Silkspear 原样在槽 3 Skill/Neutral，Hunter_v2 继承了 Hunter 的装备），槽 0 Red/Up = Cogwork Flier；7 面具；助战真。
  - **fo_C**：同 fo_B，助战标志全假。
- **DebugMod 读 savestate 不清助战标志**（读回后 `garmondAidForumBattle` 仍为真；只有从主菜单读档的 `LoadedFromMenu` 会清）。
- 进场（`forum_intro`）：从 x 53.24 向左走，到 x ≈ 33.0（触发盒右沿）吼叫过场接管控制，约 4.7 s 后第 0 波敌人出现（三次 33.0 / 33.07 / 33.03）。开战前右门开、左门关（room.gates：`Battle Gate` enabled、`Battle Gate (1)` disabled）。
- 助战实测（`check`，GauntletDataPolicy 130–150 s，fsmtap all）：A 与 B 里 `Garmond Fighter` 在按击杀重放的第 1 波开始后 4.3 / 4.4 s 进场（`Jump In → Enter Fall → Enter Land → Roar → Chase/Wildslash/Stomp`），击杀来源里有 `Stomp Damager`、`WildSlash Enemy Damager`；C 里 Garmond 一直 `Dormant`。Shakra 三组都只到 `Away`。130–150 s 内打到第 3–4 波（随机策略，受击 26–52 次，LethalBlock 保命）。
- 开战前就在 "ents" 里、但还没参战的敌人：后面波次的 Song Pilgrim Maestro 和 Song Reed（`Fly In Ready`），Maestro 的 3 个 "Song Automaton Tiny"（hp 28，`Die`，在 Maestro 位置待命：**Maestro 会放小机械，波次表外的第 9 种敌人**），第 1 波的 Song Pilgrim 03（`Attack` FSM 被禁用，状态 None）。数据策略已排除这些等待状态（`gauntlet.WAITING_STATES`）。
- **贴墙（Ascendant's Grip，fo_A，左墙）**：40 s 里 1046 帧 `wallClinging`，其中 741 帧竖直速度为 0；贴墙 x = 14.27（墙面 14.01）；**静止贴墙最高点 y = 13.60**（主角中心；墙顶上方 y 15.15 是天花板台阶），蹬墙跳最高到 y 14.95。按住朝墙方向就一直不滑（静止段最长 42 帧，被探针自己随机蹬墙打断）。

## 8. 场地几何

### 8.1 TERRAIN 实测（实例 2，`forum_setup check`，`C:\ssbot\sandbox\forum_setup\terrain_A.bin`，Hang_04 进场时的 TERRAIN，29 个实体碰撞体、20 个启用、0 个危险物）

- **地面**：tilemap EdgeCollider `Chunk 0 0/1/2`，y = 3.0 从 x 5 到 71（x 0–5 是 y 5 的台阶，在左门外）。场地内（门之间 x 14.01–48.99）没有平台、没有危险物（TERRAIN hazards 0）。
- **左墙**：`Battle Gate` x 10.54–14.01、y 2.96–9.07，上面 `Wall Collider` x 10.57–14.01、y 8.98–15.08（进场时左门已关、右门 `Battle Gate (1)` 和它的 `Wall Collider` 关闭；开战 `BG CLOSE` 后两边都关）；tilemap 墙面 x = 14（y 9–15）。**墙面 x = 14.01**。右墙对称：门 x ≥ 48.99，tilemap 墙 x = 49（y 9–15）。
- **天花板是一个穹顶**，真正的下沿是两块启用的 `Roof Collider_Basic (2)`、`(1)` 多边形（flags 1 = NON_SLIDER：实体、不能贴墙/滑墙），比 tilemap 台阶和 `terrain collider (n)` 盒子都低：左半下沿 (10.72, 14.41) (13.93, 14.19) (15.44, 14.99) (16.74, 16.14) (17.58, 16.24) (19.68, 17.32) (20.38, 17.75) (21.53, 17.87) (22.46, 19.00) (23.89, 20.36) (25.82, 21.77) (27.87, 22.66) (29.52, 23.02) (31.19, 23.15) (31.89, 23.31)；右半 (31.16, 23.23) (33.53, 22.95) (36.41, 21.81) (38.73, 20.23) (39.96, 18.69) (40.60, 17.85) (42.42, 17.10) (43.41, 16.95) (44.31, 16.51) (46.43, 15.86) (46.91, 15.05) (49.67, 14.28)。即**墙边 y ≈ 14.2，往中间升高，中央 x ≈ 31.5 处 y ≈ 23.3**。其上的 tilemap 台阶（左：x 14–15 y 15、15–17 y 16、17–20 y 17、20–22 y 18、22–23 y 22、23–24 y 23、24–32 y 24；右对称，中心 x ≈ 31.5）和 `terrain collider`/`(1)`–`(7)` 盒子（底 y 15.15–18.15）都在穹顶之上，碰不到。`Roof Collider_Basic (3)`/`(4)`（另一套略低的穹顶）和 `Black Thread Battle Gate`（Act 3 的 `Battle Scene Act3`）都是关闭的。
- 左门外走廊的天花板 `Roof Collider_Basic` x −3.78–13.52、y 9.09–15.05（门外，场地内用不到）。
- **左墙顶的贴墙点**：墙面 14.01 + 主角半宽 0.25 → 贴墙 x = 14.27（实测 14.268–14.272）。最高点被穹顶限制：贴墙时（`Wall Cling` 动画）主角受击框相对位置 y −1.76…+0.32（实测：`20261002_221727` i2 ep0 最高贴墙帧 pos (14.273, 13.452)，受击框 x 14.023–14.523、y 11.693–13.772）；`forum_setup` 贴墙测试最高静止贴墙 y 13.60（受击框顶约 13.92），框顶顶到穹顶下沿（x 14.0–14.5 处 y 14.23–14.46，算上主角物理碰撞体比受击框高）。所以**口袋 = 受击框 x 14.02–14.52、y ≈ 11.7–13.9**。
- 相机：`CameraLockArea (5)`（启用）x_min 14.6、x_max 56.4、y 9.1–16.8；STATE cam 模式 FROZEN（场景 71 × 26）。
- `zone battles`：`Battle Scene`（启用，14 波，`set_pd_bool` hang04Battle，门 id 即上面 4 个门碰撞体）和 `Battle Scene Act3`（关闭，1 波，`no_end_slomo`）。

### 8.2 场景包（`Hang_04` TileMap 的 EdgeCollider 和 `terrain collider` 盒子，`Hang_04_boss` 的门；已由 8.1 核对）
- 地面：y = 3.0（tilemap 边 x 5–71）。社区存档站立时主角 y 4.5677。
- 左墙：门 x ≤ 14.01（y 2.96–15.08），门上方是 tilemap 墙 x = 14（y 9–15）；再往上是向场地中间升高的台阶状天花板：`terrain collider (7)` x 11.92–14.88、底 y 15.15；`(6)` x 13.92–16.88、底 16.15；`(5)` x 16.92–19.88、底 17.15；`(4)` x 18.92–21.88、底 18.15。这些盒子都在 `Roof Collider_Basic (2)` 穹顶之上，实际挡住贴墙高度的是穹顶（8.1）。
- 右墙对称：门 x ≥ 48.99，天花板 `terrain collider` x 47.12–49.12 底 15.15、`(1)` 45.12–47.12 底 16.15、`(2)` 42.12–45.08 底 17.15、`(3)` 40.12–43.08 底 18.15。
- 场地中间上方开阔到 y ≈ 33（相机锁 (1) 多边形）；`Normal World` 下还有 `Roof Collider_Basic (1)/(2)` 两个大多边形（y 14.2 起，左上 x 10.25–37.74、右上 x 30.11–54.21）。
- `Teleplane`（触发盒 x 17.42–45.94、y 7.35–13.26）：会瞬移的敌人（Handmaiden 的 `Tele`）的落点范围【推测】。

## 9. oracle 导出核对

（实测后补）
