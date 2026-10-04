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
- 伤害（DamageHero.damageDealt，全部 hazardType 1 = ENEMY）：Song Heavy Sentry 本体与 `Slam Collider 1/2` = **2**；Song Handmaiden `Spear` = **2**，其余 1；Song Reed / Song Pilgrim 01 / Song Pilgrim 03 / Pilgrim 03 Song / Song Administrator / Song Pilgrim Maestro 全部 1（Song Pilgrim 03 的 `Whip Hit 1–6` 和 Song Reed 的 `ParrySlash Hit`、Administrator 的 `Slash Collider` 为 0）。research.json 的 "Choir Clapper：锤、接触、丝砸全为 2，丝内爆 1"：锤、接触 = 2 与场景包一致；丝砸、丝内爆是生成的投射物，场景包里看不到；实测（§9.2、§10）：Bomb Cast 的 `rune bomb small` 伤 1（= 丝内爆），Jump Cast 落地后的 `rune slam` 伤 2（= 丝砸）。
- 内部名与游戏名：已由游戏图鉴核实，见 §9.1（Song Pilgrim 03 = Choristor，Song Pilgrim 01 = Envoy，Pilgrim 03 Song = Choir Bellbearer）。上面"为 0"的 `Whip Hit 1–6`、`ParrySlash Hit`、`Slash Collider` 是多段攻击，实际每下扣 1 血（§9.2）。
- 各类型 FSM：Song Heavy Sentry `Control`（`Slam Antic`、`Jump Antic → Jump Aim → Jump → Air → Charged? → Slam`、`Spell Antic → Cast 1/2`（`Bomb Cast` FSM 放丝弹）、`Cast Slam Antic`、`Evade Scuttle`、`Avoid Type`（`AVOID BUDDY`：两只互相让））；其余类型的状态表在 `fo/fsm_enemy_*.txt`（场景包导出），行为表从采集录像生成。

## 3. 怎么结束

- `EndBattle`：`completed = true`，`FreezeMoment(EnemyBattleEndSlow)`（oracle "freeze" 事件 type `EnemyBattleEndSlow`，除非 `noEndSlomo`），1 s 后播结束音，再等 `battleEndPause` 2 s 后写 PlayerData `hang04Battle = true`（autosplit 的 "High Halls Arena" 分段就看这个），发 `FORUM BATTLE END`。
- 门不由 BattleScene 开（`openGatesOnEnd = 0`）：`Hang_04` 的 `Hang Battle Drop Lamp`（FSM `Drop Control`）收到 `FORUM BATTLE END` → 吊灯掉下 → `End Arena` 2 s 后发 `DISABLE CAMLOCKS`、`BG OPEN`。吊灯在两次 `HEAVY WAVE` 后各下降一截（Heavy Sentry 落地时），只是表演；吊灯本体只有 r 3.75 的圆形碰撞体，没有 DamageHero。
- `hang04Battle` 之后：`EnteredNewMapZone` / `FixUpSaveState` 置 `leftTheGrandForum`；`Hang_06` 的助战 NPC 不再出现。
- 奖励：Conductor's Melody 在 Forum 之后的房间（研究资料：High Halls 1 连战奖励是 Conductor's Melody，wiki）【未核实位置】。
- 本仓库的判定（`ssbot.train.gauntlet.GauntletTap`）：CLEAR = STATE `room.battles` 的 `completed`（新 oracle）；旧 oracle 用 `EnemyBattleEndSlow` 冻结或按击杀重放波次规则（`WaveSim`：每次死亡的 `DecrementEnemy` + 每波激活 1 s 后的敌人数检查）走完最后一波。
- **最后一击之后还没完**（反编译 `GameManager.cs:5132`、`BattleScene.cs:444`）：`EnemyBattleEndSlow` = 0.1 s 降到 0.25 倍速、按真实时间保持 1 s、0.75 s 升回 1 倍（约 1.85 s 真实时间里只走 0.78 s 游戏时间），之后 `EndBattle` 再等 1 s + `battleEndPause` 2 s 游戏时间才写 `hang04Battle`、发 `FORUM BATTLE END`：**最后一击后约 4.1 s（≈ 245 帧）**。这段时间里垂死的 Clapper 本体、rune slam、炸弹照样伤人（录像：`20261002_223640` ep0 冻结后 13 帧、`20261002_230325` ep0 冻结后 2 帧都有 Clapper 本体接触，当时主角无敌，是 damage_blocked）。本关 `skipSaveIfPlayerIsDead = 0`（死了也写 `hang04Battle`），但 Steel Soul 里死就是结束。所以从 6a38ba3 起 `run_episode`：Forum 的收尾窗口 `post_clear_s = 4.5`（之前是击杀后 60 帧），窗口里策略继续操作；eval 模式下击杀同一 STATE 或窗口内的致命伤 = WOULD_DIE（"lethal hit at/after the kill"）；data 模式计入 `AttemptRecord.lethal_after_clear`。Forum 默认时间盒改为 1500 s。

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
- **左墙顶的贴墙点**：墙面 14.01 + 主角物理碰撞体半宽 0.25 → 贴墙 x = 14.27（实测 14.268–14.272）。最高点实测见下；**是什么限制了这个高度未核实**：pos y 13.60 时物理框顶约 13.92，墙边穹顶下沿（x 14.0–14.5）在 y 14.24–14.50，框顶离穹顶还有 0.32 u，所以不是框顶碰到穹顶；可能是贴墙检测射线碰到 NON_SLIDER 的穹顶角，也可能只是蹬墙跳回到墙上时的高度（实测最高静止贴墙都来自蹬墙跳后的重新抓墙）【推测，要用定点探针核对】。`20261002_221727` i2 ep0 最高 `Wall Cling` 帧 pos (14.273, 13.452)、STATE hero.box x 14.023–14.523、y 11.693–13.772；`forum_setup` 贴墙测试最高静止贴墙 y 13.60。**注意 STATE hero.box 是 `HeroController.Bounds`（物理碰撞体外框 0.5 × 2.08），不是受伤判定**：受伤判定是 `HeroBox` 子物体的盒子（反编译 `HeroBox.cs`，运动学链也用这个）。贴左墙时 `HeroController`（8470 行）调 `FaceLeft()`（`localScale.x = +1`）并 `heroBox.HeroBoxWallSlide()`：盒子 0.8757 × 1.2805、中心在主角 transform 的 (+0.2101, −0.2755)。所以**口袋（贴墙最高点的受伤判定）= x 14.04–14.92、y 12.53–13.97**（pos y 13.45–13.60），比物理外框向右多出 0.4 u、下沿高 0.8 u。另有 `HeroBoxWallScramble`（同样 0.8757 × 1.2805，中心 (+0.2101, +0.4)，由 PlayMaker 动作 `HeroBoxControl` 在爬墙翻越时切换）：若在墙顶触发，受伤盒会高出 0.68 u（y 13.36–14.64）；口袋数字没有包括这种情况（穹顶下没有可翻越的墙沿，应当不会触发【未核实】）。贴墙时 STATE facing = −1（1029 帧里 960 帧，与 FaceLeft 一致）。
- 相机：`CameraLockArea (5)`（启用）x_min 14.6、x_max 56.4、y 9.1–16.8；STATE cam 模式 FROZEN（场景 71 × 26）。
- `zone battles`：`Battle Scene`（启用，14 波，`set_pd_bool` hang04Battle，门 id 即上面 4 个门碰撞体）和 `Battle Scene Act3`（关闭，1 波，`no_end_slomo`）。

### 8.2 场景包（`Hang_04` TileMap 的 EdgeCollider 和 `terrain collider` 盒子，`Hang_04_boss` 的门；已由 8.1 核对）
- 地面：y = 3.0（tilemap 边 x 5–71）。社区存档站立时主角 y 4.5677。
- 左墙：门 x ≤ 14.01（y 2.96–15.08），门上方是 tilemap 墙 x = 14（y 9–15）；再往上是向场地中间升高的台阶状天花板：`terrain collider (7)` x 11.92–14.88、底 y 15.15；`(6)` x 13.92–16.88、底 16.15；`(5)` x 16.92–19.88、底 17.15；`(4)` x 18.92–21.88、底 18.15。这些盒子都在 `Roof Collider_Basic (2)` 穹顶之上，实际挡住贴墙高度的是穹顶（8.1）。
- 右墙对称：门 x ≥ 48.99，天花板 `terrain collider` x 47.12–49.12 底 15.15、`(1)` 45.12–47.12 底 16.15、`(2)` 42.12–45.08 底 17.15、`(3)` 40.12–43.08 底 18.15。
- 场地中间上方开阔到 y ≈ 33（相机锁 (1) 多边形）；`Normal World` 下还有 `Roof Collider_Basic (1)/(2)` 两个大多边形（y 14.2 起，左上 x 10.25–37.74、右上 x 30.11–54.21）。
- `Teleplane`（触发盒 x 17.42–45.94、y 7.35–13.26）：会瞬移的敌人（Handmaiden 的 `Tele`）的落点范围【推测】。

## 9. oracle 导出核对（实例 2，fo_A，数据策略；运行 `20261002_221727`（2 场，见下"假 CLEAR"）、`20261002_223640`（2 场，完整打到 hang04 结束）；工具 `ssbot.tools.behaviour_build --encounter Forum`、`forum_counts`、`forum_pocket`）

### 9.1 游戏名对照（游戏自己的图鉴：场景包里每个敌人的 `EnemyDeathEffects.journalRecord` → `EnemyJournalRecord.displayName` → 解密的 `EN_Journal` / `ZH_Journal`（`resources.assets` TextAsset，`StringEncrypt` AES-ECB，密钥见反编译 `StringEncrypt.cs`））

| 内部类型 | 英文 | 中文 | HP | 控制 FSM | 波次 |
|---|---|---|---|---|---|
| Song Pilgrim 03 | Choristor | 圣咏使徒 | 55 | `Attack` | 0, 1(×2), 9 |
| Song Pilgrim 01 | Envoy | 圣咏特使 | 38 | `Attack` | 0 |
| Pilgrim 03 Song | Choir Bellbearer | 圣咏钟卫 | 35 | `Control` | 2, 8, 9(×2), 11 |
| Song Reed | Reed | 簧片战士 | 55 | `Control` | 0, 2, 8(×2), 12 |
| Song Handmaiden | Clawmaiden | 丝偶侍女 | 48 | `Control`（另有 `Silk Suck`、`Lock Control`） | 3, 5, 10 |
| Song Administrator | Minister | 圣咏大臣 | 60 | `Control` | 4(×2), 11(×2) |
| Song Pilgrim Maestro | Maestro | 圣咏指挥 | 65 | `Control` | 6(×2), 12 |
| Song Heavy Sentry | Choir Clapper | 圣咏槌手 | 230 | `Control`（另有 `Bomb Cast`） | 7, 13(×2) |
| Song Automaton Tiny | （Maestro 的召唤物，对象池克隆，不在波次表） | — | 28 | `Control` | 每只 Maestro 3 只 |

之前 §2 的推断（Song Pilgrim 01/03 与 Choristor/Envoy 的对应）由此更正：**Choristor = Song Pilgrim 03，Envoy = Song Pilgrim 01**。

### 9.2 每类敌人的导出（"ents"）

全部波次敌人都在 "ents"：HealthManager（src 位 1）+ DamageHero（2）；Reed、Choristor、Minister 还有 multi_wounder（8）。实体 iid 稳定，"fsm" 事件的 `ent` 和 "hit" 事件的 `ent` 就是 ents[].iid（行为表按 iid 分流）。parry 位：4 = 只有 counter；5 = clash + counter（可拼刀）。gravity_scale 实测：Choir Clapper 1.4（Air 中每物理步 dvy −1.68 → g_eff 84）、Choristor 1.1、Envoy 1.0、Throwing Bell 1.0，其余都是飞行敌人（0）。

| 类型 | 伤害碰撞体（名字：形状，伤害，parry） | 敌人自己放出的危险物 |
|---|---|---|
| Choir Clapper | 本体 "Song Heavy Sentry"（终局是 "(2)"/"(3)"）盒 2/4；`Slam Collider 1`、`Slam Collider 2` 多边形 2/4（另有不伤主角的 `… Ally`、`Tile Smasher`） | 共用名 "damager" 的圆（type_key 一样，按半径区分，伤害事件来源给出父物体名）：Bomb Cast 的 `rune bomb small` r 2.166、伤 1；Jump Cast 的 `rune slam` r 7.187、伤 2 |
| Clawmaiden | 本体盒 1（有些帧 0）/4；`Slash Collider 1–4` 多边形 1/5 | `Spear`（多边形 2/4，FSM `Control`：Init→Idle→Get Antic Angle→Fire L→Antic Pause→Antic→Fire→Explode→Deactivate）；矛的爆炸 `handmaiden_spear_silk_explosion` = "damager" 圆 r 3.553、伤 2 |
| Minister | 根盒 "Song Administrator" 1/4；`Colliders` 子物体下 `Collider Fly`/`AttackAntic`/`ParryAntic`/`ParryStance`/`Evade` 盒 1/4（随状态换）；`Slash Collider` 多边形（多段，导出伤害 0）；`ParrySlash Hit 1–4` 1/5 | — |
| Maestro | 本体盒 1/4；`Slash Hit 1/2` 多边形 1/5 | 召唤 3 只 Song Automaton Tiny |
| Song Automaton Tiny | 本体盒 1/4 | — |
| Reed | 本体盒 1/4；`Stab Hit 1–3` 1/5；`ParrySlash Hit`（多段，导出 0） | `Song Reed Pin Projectile`（盒 1/5：可拼刀；FSM `Javelin Control`：Init→Throw Effect→Fly→Stick（插墙，碰撞体关）或 Dealt Damage→Deactivate→Recycle） |
| Envoy | 本体盒 1/4；`Charge Damager`、`P1 Damager`（盒）、`P2 Damager`、`JumpSlash Damager 1/2`（多边形）1/5 | — |
| Choristor | `Body Damager` 盒 1/4；`Slash Hit 1–3`、`Spin Hit`、`Spin Slash Hit` 1/5；`Whip Hit 1–6`（多段，导出 dealt 0、eff 2） | — |
| Choir Bellbearer | 本体盒 1/4 | `Throwing Bell`（圆 r 0.425，伤 1，有些帧 0；重力 1.0；FSM：Init→Air→Ground/Wall L/Wall R/Roof→Bounce→Air…，被钉子打中 Tink L/R/U→Nail Hit→Air（改向），Break→Deactivate→Recycle；另有子碰撞体 `Enemy Damager` 打敌人） |

- **多段攻击**：Choristor `Whip Hit 1–6`、Reed `ParrySlash Hit`、Minister `Slash Collider` 导出的伤害是 0（Whip Hit eff 2），但连上之后由 `hornet_multi_wounder` FSM 继续扣血，后续命中时碰撞体已不在导出里（例：`20261002_221727` ep0 f690811 `Whip Hit 2` 启用，f690833 Multiwhip 中 "Song Pilgrim 03/Whip Hit 2" 扣 1 血时它已关闭）。行为表把这类"已连上的多段攻击的后续命中"单列（`multi_hit_follow_ups`，碰撞体 90 帧内出现过），不拿去对支撑；规划器应当把第一下接触当作整套命中。
- **伤害事件的来源路径**（damage / damage_blocked 的 source）：本体是 "Wave N/<GameObject>"（"Wave 8 - Heavy Sentry/Song Heavy Sentry"），子碰撞体是 "<GameObject>/<子物体>"；**Minister 的身体盒只给 "Colliders/Collider ParryStance"**（不含敌人名，只能按"谁在导出这个名字的碰撞体"认）；Tiny 是 "Song Automaton Tiny(Clone)" 或 "EmptyObjectFromNull/Song Automaton Tiny(Clone)"（最多 6 只同名，只能按位置认）；三种 "damager" 由父物体名区分。等待中的同名敌人（波 12 的 "Song Reed" 开场就在 `Fly In Ready`）也在 ents。`damage_blocked` 在一段无敌接触结束时才报，且一段可能跨同名的几只 Tiny：行为表按帧回溯归属。
- **助战与 Cogfly 不在 ents**（部署 `allies` 导出之前）。击杀来源（hit.src，Generic 伤害 = 助战/Cogfly）：最早的 4 场（`20261002_221727` ep0–1、`20261002_223640` ep0–1）共 **129** 次击杀（28 + 28 + 36 + 37，旧计数；此前写的"149"有误）：Garmond = `WildSlash Enemy Damager` 30、`Stomp Damager` 5、`Stomp Splash Damager` 4、`Charge Damager` 3（Generic，5 伤）；Cogfly = `Damager` 8（Generic 3，偶尔 4）；Hornet = `Slash` 29、`UpSlash` 19、`DownSlash New` 10、`AltSlash` 5、`WallSlash` 4（Nail 9，Reaper）、`Needle Damage` 10（Heavy 27 = Silk Spear）；`Enemy Damager` 2（Generic 9）= 被钉子打回的 Throwing Bell 砸到别的敌人。**13 场完整连战**（`20261002_223640` 2、`230325` 1、`231917` 10；用 379e33e 的 GauntletTap 在录像事件上重放，池化 Tiny 的重复死亡也算）：541 次死亡 = 364 波次敌人（每场 28）+ 177 Tiny（每场 9–19）；Hornet 钉子 270（Slash 125、UpSlash 88、DownSlash New 30、AltSlash 20、WallSlash 7）、丝矛 45，Garmond 201（WildSlash 111、Stomp 47、Charge 29、Stomp Splash 14），Cogfly 17，钟 8。
- **击杀去重（379e33e 修正）**：旧 tap 按实体 iid 去重 "hit" dead，Maestro 的 Tiny 是对象池，复用同一个负 iid（`20261002_231917` ep0：-693612 死 4 次、-693690 死 3 次，间隔 ≥ 907 帧），所以只记到 9 次 Tiny 死亡而实际 19 次。所有录像里每个 dead 的 hit 都有 hp_before > 0（没有对已死敌人的重复报告）；现在按"从 hp > 0 打死、同一实体 60 帧内不重复"计。波次模拟不受影响（Tiny 不算波次成员）。下文和旧 AttemptRecord 里的击杀数（kills.n、by_type、by_src）在这之前都少算了 Tiny。
- **假 CLEAR（已修 7eb12de）**：Tiny 也报 "hit" dead，旧 GauntletTap 把它们算进 DecrementEnemy 重放，`20261002_221727` ep0 在终局开打前就判 CLEAR（28 次击杀里 6 次是 Tiny，Clapper 只死了 1 只，没有 EnemyBattleEndSlow 冻结）。修后只数波次类型；`20261002_223640` ep0 41 次死亡（28 + 13 Tiny，旧计数 36）、终局 761 s 开始、848 s 两只 Clapper 都死。**完整连战**（13 场）用了 **714–990 s** 游戏时间（中位 848 s）；之前写的 "550–850 s / 550–990 s" 把 `221727` 的两场假 CLEAR（543、586 s，终局前就结束）算进去了。超过 900 s 的有 3 场，所以数据跑用 `--timebox 1500`，c86979f 之后 Forum 默认也是 1500 s。
- **data 模式的 CLEAR 不等于活下来**：LethalBlock 把主角保在 1 血，随机策略每场被判"会死"173–251 次（`20261002_231917` 的 AttemptRecord.would_die），CLEAR 只说明连战走完了（采集用）。
- **波次时间（379e33e 修正）**：旧 `WaveSim` 在索引 2（2 个敌人、remainingEnemyToEnd 2）开始的同一刻就开索引 3，记录的波次时间提前约 2 s、顺序颠倒（`20261002_231917` ep0：波 2 58.03 s、波 3 57.53 s，实际 Clawmaiden 59.77 s 才出现）。游戏里是开波 1 s 后 `DoCheckEnemies`（数子物体）才发现 2 ≤ 2 而结束这一波；修后 sim 在每波激活 1 s 后做这次检查，并忽略下一波 startDelay 期间的重复 WaveEnd（游戏会再跑一次 StartWave，但按子物体数敌人只算一次）。13 场重放：结束帧全部等于 EnemyBattleEndSlow 冻结帧；索引 3 / 5 / 10 的 Clawmaiden 都在 sim 波次时间之后 0.02–0.47 s 内出现。
- **行为表核对**：见 §11（13 场重建：28,029 次接触里 19 次不同的接触失败，其中 5 次是敌人被打死那一帧的身体接触；留出核对九类都没到 ≈ 0，支撑还不能当保守的用）。首版这里写的"Clapper `Slam Collider 2` 在 Slam Recover"等描述有误，以 §11 为准。导出空洞（有伤害却 colliders == []）0。

## 10. Choir Clapper 的跳跃与左墙顶口袋（你的打法核验；工具 `ssbot.tools.forum_pocket`）

### 10.1 跳跃（反编译 FSM `Control` + 录像）

- 状态链：`Jump Antic`（面向主角、vx 0）→ `Jump Aim`（面向主角；Target X = 主角 x + 5；`SendEventByScale`：scale x > 0 即**面朝左**时直接结束，否则再 −10 → 主角 x − 5）→ `Jump`（Jump X = clamp(Target − 自己 x, −12, 12)；SetVelocity(Jump X, **38**)）→ `Air`（直到底部碰撞 LAND）→ `Charged?`（Jump Cast 时放 rune）→ `Slam Effects?` → `Slam 2`（`Slam Collider 2`）→ `Slam Recover` → `Idle`。
- 实测瞄准（`20261002_221727` ep0，9 次跳）：落点 = 主角 x + 5.00（±0.14，面朝左）或 − 5.00（面朝右），即**总落在主角前 5 u、自己这一侧**。
- 重力：gravity_scale **1.4**，g_eff **84 u/s²**（Air 中每个 0.02 s 物理步 dvy −1.68）；vy0 38 → 理论最高 +8.6 u，实测 pos y 7.45 → 15.67（本体框顶 15.86），到顶 0.43–0.48 s，空中约 0.9 s。这是**多数**跳的顶点，不是定值：13 场 413 次跳里 348 次框顶 15.86，36 次更高（最高 16.60，例：`20261002_230325` 一次从 x 24.56 起跳、主角在墙上，pos 顶点 16.15），其余被穹顶截低。瞄准有个注意点：`FaceObjectV2` 的 pauseBetweenTurns 0.5 s，所以 Jump Aim 用的朝向可能是半秒前的（主角刚绕到它背后时，目标会落在错的一侧）【未在录像里逐次核对】。靠近右墙（x 44.8–46.7）的跳被穹顶截到 14.47–14.78。
- 本体框相对 pos：站立面朝左 x −2.25…+1.34、y −4.43…−0.53（地面 pos y 7.45 → 框 y 3.02–6.92，Spell Antic 最高 7.78）；Air 中 y −3.59…+0.19；`Jump Antic` 姿势 x −1.92…+1.65。面朝右左右镜像。所以贴紧左墙时 pos = 16.26（面朝左）/ 15.35（面朝右）/ 15.93（Jump Antic 面朝左）。
- 其他招：`Slam 0`/`Slam 1` 各 SetVelocityByScale −30（向前冲 3.0–4.3 u，0.12–0.32 s），`Slam Collider 1` 前 −1.91…+6.24、y −3.19…+3.13（地面时顶 10.58），`Slam Collider 2` 前 0.67…7.76、y −4.99…+2.65（顶 10.10）；`Evade Scuttle` 0.35 s 内以 15 u/s **向后**（背离主角）退，背后 6 u 内有墙则 `Escape Jump` → Jump Slam / Jump Cast；Bomb Cast：`First Bomb` 后 9 对、每 0.15 s 一对、间距 4.2（最远 ±37.8，穿墙），每颗 `rune bomb small` r 2.17、中心 y 3.67、亮 5–7 帧（偶尔 16–17）；Jump Cast 落地后约 2 s 在落点出现 `rune slam`，再 1.28 s 爆：圆 r 7.19、中心 y ≈ 3.34（顶 ≈ 10.5），亮 7–19 帧。

### 10.2 主角在口袋里时 Clapper 怎么选

- `Slam Range`（AlertRange = 主角碰撞体进入触发盒，反编译 `AlertRange.cs`）是 pos ±8.05 × (pos − 4.46 … pos + 3.37)，站地时世界 y ≤ 10.82。口袋里主角的物理碰撞体下沿 ≥ 11.69、受伤盒下沿 ≥ 12.53，都在盒子上方 → "In Slam Range" 为假：`Walk` 的 CLOSE、`Idle` 的 EVADE 都不会触发，只走 `Far Range`：JUMP SLAM 0.5 / CAST 0.25 / JUMP CAST 0.25（SendRandomEventV4，eventMax 2/1/1，missedMax 1/2/2）；`Walk` 的 DistanceWalk 把自己保持在离主角 7 ± 1.5 u（x ≈ 19.8–22.8）。贴墙高度的门槛：Slam Range 顶 10.82，主角贴墙时物理碰撞体下沿 = pos − 1.76、`HeroBoxWallSlide` 下沿 = pos − 0.92，所以 pos y 高于约 12.6（按物理碰撞体）/ 11.7（按 HeroBox）就出了 Slam Range；低于这个高度贴墙，Clapper 照样会冲锤（锤顶 10.58）和后撤。`TrackTriggerObjects` 认的是与触发盒层相碰、没被 `ignoreLayers` / 标签过滤掉的任何碰撞体（`AlertRange.isHeroInRange` 其实是"里面有任何东西"）。**层矩阵已查**（`globalgamemanagers` 的 Physics2DSettings + TagManager，UnityPy；脚本在会话临时目录 `fx2/`：`layers.py`、`cogfly_layer.py`、`hero_layer.py`）：三只 Clapper 的 `Slam Range` 在第 13 层 `Hero Detector`，`ignoreLayers` 0、无标签过滤、lineOfSight = Parent；第 13 层**只和第 9 层 `Player` 相碰**。第 9 层上带碰撞体的只有主角根物体 `Hero_Hornet` 的 BoxCollider2D（`heroloading_assets_all.bundle`，即 STATE hero.box 那个物理碰撞体）；Garmond Fighter 的碰撞体在 14（根）/ 17（攻击）/ 22 / 24 / 15 / 13 层，Cogfly（`Clockwork Hatchling`，`herodynamic_assets_all.bundle`）在 14 / 15 / 17 / 18 / 19 层，Clapper 本体在 11 层（`Slam Collider … Ally` 在 24 层）：**助战、Cogfly、另一只 Clapper 都不会让 Slam Range 变真**，门槛就是按物理碰撞体算的 pos y ≈ 12.6（不只是"保守值"）。
- 这时跳的目标 = 14.27 + 5 = 19.27：从 19.8–22.8 起跳只向左移 0.5–3.5 u，本体左沿始终 ≥ 17.3。
- 实测（运行 `20261002_231917`，e589c0b 的数据策略加了口袋模式：只剩 Clapper 时选到 CLING 的概率 0.5，但 CLING 段平均 300 帧、其他段 55 帧，**按帧约 85% 的时间在左墙**（不是此前写的"一半时间"；ccb85d1 起这个比例由 `POCKET_CLING_SHARE = 0.85` 按帧直接设定，行为不变）；ep0 的 40 次跳）：起跳时主角在左墙（x 14.27–14.6）的 17 次，起跳点 x 22.1–28.8（中位 ≈ 25），本体顶过 12.53 时左沿最小 17.87–19.37，即离口袋右沿 ≥ 2.95 u；主角在口袋里时 Clapper 的 x：p5 18.6、中位 23.7。两次危险的起跳（x 15.36、15.59，面朝右）都发生在主角在它右边（x 16.5、18.6）时：本体贴墙升到 14.31–14.36（被穹顶挡住），覆盖口袋的高度。

### 10.3 各招离口袋最近的距离（`forum_pocket` 在 9a14574 上重跑：运行 `20261002_223640` 2 场、`230325` 1 场、`231917` 10 场 = 13 场完整连战，241,841 帧 Clapper、413 次跳；输出 `fx2/pocket_new.json`（会话临时目录）。口袋 = 贴墙最高点的 `HeroBoxWallSlide` x 14.04–14.92、y 12.53–13.97；碰撞体到盒子的精确距离。此前的版本用的是 4 个运行 10 场 / 264 次跳，含 `221727` 的两场假 CLEAR，数字见 git 历史）

| 招 / 碰撞体 | 最近距离 u | 说明 |
|---|---|---|
| Jump、Jump Cast 本体（Air） | **0.00** | 413 次跳中 9 次本体在 y ≥ 12.53 时左沿进了 14.92：全部从**贴紧左墙**起跳（x 15.36–15.95，面朝右，即主角在它右边 x 16.4–22.6；这样的起跳共 12 次，另 3 次主角远在右边 x 27.7–37.0，左沿停在 15.8–16.1），沿墙升到穹顶（顶 14.25–14.88）。**口袋里 Clapper 的接触只有 1 次，且是无敌帧里的 damage_blocked，不是命中**：`20261002_231917` ep3 f1106796（终局 "(2)"，主角 pos (14.31, 13.69)）。此前写的"在口袋里打到主角 2 次"不对：两次都是 damage_blocked（另一次 `20261002_221727` ep1 f744405 在旧运行里，主角在它左边往下劈后爬回墙顶）。**起跳时主角就在左墙（x ≤ 14.7）的 105 次跳**（其中主角 x ≤ 14.57 的 92 次）：起跳点中位 26.9，本体升过 12.53 时左沿中位 19.22（离口袋 4.3 u）；最近的一次是 `20261002_231917` ep5 f1214665：起跳点 17.77、面朝左，左沿到 15.79，**离口袋只有 0.87 u**（此前写的"≥ 1.82 u"是 10 场的结果，13 场里出现了更近的） |
| Slam 1 锤（`Slam Collider 1`） | 2.04 | 冲刺可冲到墙边，但顶 ≤ 10.58 |
| Slam 2（地面锤第二下 / Jump Cast 落地 / Jump 落地，`Slam Collider 2`） | 2.42 / 2.61 / 2.64 | 顶 ≤ 10.10（此前表里的"2.73"重跑得不到：10 场时是 2.61 / 2.67） |
| rune slam（Jump Cast，伤 2） | 2.00 | 该次 rune 正落在口袋下方（x 14.38）；顶 ≈ 10.5 |
| Bomb Cast 炸弹（伤 1） | 6.67 | 只在地面 |
| 终局 Drop In（x 21.03 / 42.03 从 y 23.7 落下） | 4.15 | |
| Cast / Jump Antic / Slam 0 / Evade / Idle / Walk 本体 | ≥ 4.73 | |

（其他波次的敌人会进口袋：Reed 本体、Tiny、Minister `Slash Collider` 和 `Colliders/…` 身体盒、Clawmaiden 矛爆炸 0.00 u；13 场里口袋内 12 次接触，2 次是命中（Tiny、Minister `Slash Collider`），其余是 damage_blocked。口袋只用于终局。）

主角在口袋里（transform x < 14.57、y ≥ 13.2，13 场共 2343 帧）时 Clapper 进入的状态：Idle 13、Walk 13、Slam 2 7（多为跳砸落地）、Air 5、Cast 2 5、Cast Slam Antic 2 5、Jump 4、Slam Recover 4、Spell Antic 3、Cast Slam Antic 3、Cast 1 2、Evade Scuttle 2、Jump Antic 2、Slam 1 2；**没有 Slam Antic（地面锤的开始）**，与 10.2 一致（Slam Range 只认主角的物理碰撞体）。两次 `Slam 1` 和两次 Evade 是主角刚爬进口袋时已经开始的招（Slam 1 跟在 Slam Antic 后面；Evade 可能是两只互相让的 Avoid Type）【未逐帧核对】。Clapper 当时的 x：最小 15.63、p5 18.47、中位 23.2。

### 10.4 结论

- **你的打法基本成立**：主角贴在左墙最高点时，Clapper 的锤、跳砸落地、丝砸（rune slam）、丝内爆（炸弹）、入场、本体都够不着，余量 ≥ 2.0 u（锤 2.04、rune 2.00）；它们也不会选锤和后撤（主角不在 Slam Range 里），只会跳 / 施法，而跳总落在主角前 5 u（x ≈ 19.3）；13 场里起跳时主角在墙上的 105 次跳，本体离口袋中位 4.3 u，最近 0.87 u（起跳点 17.77，见下一条）。余量没有 Bell Beast 那样宽，所以下面两条规则是打法的一部分。
- **唯一的漏洞是贴墙起跳**：Clapper 的本体贴着左墙（左沿在墙面 0.5 u 以内，pos ≤ ≈ 16.8 面朝左）时起跳，跳向 19.27 的路上本体先沿墙升起，约 0.16 s 时顶过 12.53、左沿还在 14.9 以内（模型：top = 7.64 + 38t − 42t²，左沿 = pos − 2.25 + (19.27 − pos)·t → pos ≤ 16.78 就重叠；余量 < 1 u 一直到 pos ≈ 17.96：实测起跳点 17.77 面朝左、主角在墙上时左沿到 15.79，离口袋 0.87 u）；13 场里贴墙起跳 12 次（都面朝右，主角在它右边），9 次本体进了口袋的范围；口袋里来自 Clapper 的接触只有 1 次，是无敌帧里的 damage_blocked。Clapper 多半在主角离开口袋时才到墙边（主角在 Slam Range 里时朝墙冲锤，或主角在它右边时向后 Evade 到墙），但主角在口袋里时也见过 Clapper 在 x 15.63（13 场 2343 帧里的最小值），而 Slam Range 只认主角（10.2 层矩阵），助战和另一只 Clapper 不会把它引到墙边。**规则：(1) 回到口袋之前，确认没有 Clapper 贴在左墙边（本体左沿 ≤ 14.6）；有就等它离开或先别上去。(2) 人在口袋里时，任何面朝左、pos ≤ ≈ 18 的 Clapper 都按威胁算（它这时起跳，本体会擦到口袋 1 u 以内或进入口袋）：准备在它起跳时下墙或在最高点出刀，而不是以为口袋里永远安全。** 规划器靠 CC_JUMP / CC_JUMP_CAST 的行为表（按起跳点锚定）应当自动得到这一点（前提是支撑覆盖了这些少见的近墙起跳，见 §11 留出核对），剧本里再写两条。
- **墙上出刀够得着跳到高处的 Clapper 吗**：录像里从左墙（x 14.27）出的 Reaper `WallSlash` 打中 Clapper 7 次（3 个运行）：站地的 Clapper 本体左沿到 16.3–18.6，空中的一次（`20261002_231917` f969433，主角贴墙 y 9.88，Clapper `Air` pos (20.53, 12.43)，本体左沿 18.28）。所以贴墙横斩**至少**够到 x ≈ 18.3–18.6（离主角中心约 4.0–4.3 u）：这是 7 次命中给出的下界，不是量出来的最远距离（真正的够距要用 Reaper `Attacks/Scythe/WallSlash` 伤害多边形相对主角的位置：P17 的 `crests.json` 有这个多边形（世界坐标，宽 3.79 u），但没记当时的主角位置【未核实】）。`20261002_231917` ep0（口袋模式那一场）里主角在墙上时的跳，本体升过 12.53 时左沿 17.87–19.37，大约一半在 18.6 以内：**"在最高点砍一下"至少对较近的一半跳可行**，较远的要等够距实测（规划器按行为表和攻击多边形逐次判断）。Clapper 的伤害绝大部分来自 Garmond（3 个运行里 Clapper 受到的命中：`WildSlash Enemy Damager` 185、`Charge Damager` 48、`Stomp*` 37，Hornet 的钉子 / 丝矛 106）。
- 还要测的：主角长时间待在口袋里时 Clapper 的选择。e589c0b 起数据策略在只剩 Clapper 时按帧约 85% 的时间去左墙爬口袋，但爬上去的少（`20261002_231917` ep0：贴墙 5621 帧里只有 145 帧在 y ≥ 13.3；13 场合计口袋 2343 帧），需要按运动学链的蹬墙跳模型写一个可靠的爬墙动作；以及在墙顶出刀打跳到最高点的 Clapper 的命中实测。

## 11. 行为表（`ssbot.tools.behaviour_build --encounter Forum`，重建于 9a14574（13 场），输出 `knowledge/1.0.30000/enemies/forum/<敌人>.json`（+ `_hitboxes.npz`，未提交，用命令可重建）和 `coverage.json`；首版（1045010，8 场）的数字见 git 历史）

- **2026-10-04：表已用 107 场重建，本节的实例数和留出比例是 13 场时的，新数字见 §12.1。**
- 做法（`ssbot/knowledge/gauntlet_tables.py`）：Forum 同时有最多 6 个、4 类敌人，同类常有 2–9 只（Tiny），单 Boss 的 BehaviourBuilder 把别的伤害实体都当成 Boss 的危险物。现在每个敌人实体（HealthManager 根的 iid）一条流：它自己的实体和它放出的危险物（按 spawns 表：Clapper 的 rune bomb small / rune slam、Clawmaiden 的 Spear / 矛爆炸、Reed 的 Pin、Bellbearer 的 Throwing Bell；危险物在"放它的那招结束后 4 s 内"武装也归那招），它的 fsm / hit 事件，以及归到它名下的主角接触（按来源路径里最深的敌人名；只给子碰撞体名的按"谁在导出这个名字的碰撞体"；同名的按"哪只的伤害碰撞体碰到主角框"，再按 transform 距离；`damage_blocked` 逐帧归属）。每类一个 BehaviourBuilder；家族 = 该类的攻击开始状态（表见代码 FORUM_SPECS，从场景包 FSM 和录像整理），另加 `<P>_IDLE`（两招之间走 / 飞时本体也伤人）和 `<P>_ENTRY`（入场）；被打死（hit dead）即死亡；多段攻击的后续命中单列。
- 输入：13 场完整的连战（`20261002_223640` 2 场、`20261002_230325` 1 场、`20261002_231917` 10 场；fo_A，数据策略，实例 2），3.07 h 战斗时间（单实例墙钟与战斗时间几乎相同：run `20261002_231917` 10 场用了 2 h 23 min 墙钟、2 h 22 min 战斗时间，重置 + 开场约 9 s / 场），每类敌人的实例数：Choir Clapper 39、Clawmaiden 39、Minister 52、Maestro 39、Song Automaton Tiny 117、Reed 65、Envoy 13、Choristor 52、Choir Bellbearer 65（Tiny 是对象池，按 iid 计）。**留出折按场交替**（9a14574 起；之前按录像分折，一个录像有 5 场，8 场里 7 场落在同一折，留出核对等于拿 1 场去验 7 场）。
- 样本内核对：28,029 次接触（2,648 次命中 + 25,381 帧无敌接触）里 **19 次**（不同的接触，不是 (接触, 模板集) 对）不在支撑内、无法解释或在攻击实例之外：Choir Clapper 4、Clawmaiden 2、Minister 6、Maestro 1、Reed 4、Choir Bellbearer 2；Tiny、Envoy、Choristor 全部通过。无人认领的接触 0（9a14574 起：只给子碰撞体名的接触往回找 2 帧导出（这次找回 21 次，都是 Minister 的 `Colliders/…`），再找不到就算到该类最近的活实体上记作无法解释；仍然没人认领的列在 coverage.json `validation.unattributed`、按失败计）。导出空洞 0。多段后续命中（不拿去对支撑）：Minister 105、Reed 32、Choristor 50。
- 这 19 次里 **5 次是敌人被打死那一帧的身体接触**（Reed `20261002_231917` ep0 f912516、终局 Clapper ep0 f969668（`ZERO HP` 全局转移进 `Start Battle?`）、Clawmaiden ep1 f1004990 / ep2 f1051728、Maestro ep4 f1132417）：击杀先结束了实例，同帧的接触落在实例外或没有模板的死亡状态里。这不是支撑的洞，是"死的那一帧（终局 Clapper 还要多十几帧，§3）身体照样伤人"：规划器要把刚被打死的敌人的最后一个身体框再算几帧。其余：Clapper 3 次 `rune bomb small` 无敌接触（2 次当时没有导出炸弹碰撞体、1 次没有归属的攻击）、Minister 6 次 `Colliders/Collider Fly` / `ParryStance` 在 Chase / Retreat? / Parry Stance 里超出支撑、Reed 2 次 Pin 投射物 + 1 次 Defend Start 本体（0.59 u）、Bellbearer 2 次钟。此前写的"Clapper 失败是 Slam Collider 2 在 Slam Recover"不对。
- **留出核对（看没见过的实例会不会落在支撑外）**：另一折的记录里离支撑 > 0.5 u 的接触（anchor 集）：Choir Clapper 41/10828（0.4%）、Clawmaiden 66/1258（5.2%）、Minister 26/2636（1.0%）、Maestro 3/498（0.6%）、Song Automaton Tiny 80/5076（1.6%）、Reed 92/3104（3.0%）、Envoy 6/994（0.6%）、Choristor 8/2417（0.3%）、Choir Bellbearer 8/944（0.9%）。Bell Beast 同样的核对是 0 / 184,521。按场分折后比首版（9.5–18%）好很多，但**九类都没到 ≈ 0**：每个表的 `validation.support_conservative` 都是 false（判据：样本内全过、且留出 anchor / self 超出 0.5 u 的不超过 0.1%），`support_note` 写了原因；`BossModel.load` 读到这种表会发警告（`support_ok` false）。**在留出核对接近 0 之前，这些支撑不能当作保守的用**：规划器要么不用、要么加大余量。最差的是 Clawmaiden（5.2%，瞬移落点和矛爆炸）、Reed（3.0%）、Tiny（1.6%）；要的是更多场次（每场每类只有 1–9 个实例）。
- 决策条件（似然比 + 留出对数损失，只影响概率；首版的观察，重建后未逐条复核）：与 Bell Beast 不同，**这里很多选择依赖距离**（dist_visible）：Clapper 的 Walk / Idle / Dmg Attack / After Scuttle / Evade Scuttle（Slam Range），Choristor 的 Attack Choice / Hop / Slash Check，Minister 的 Chase / Attack，Reed 的 Alert，Bellbearer 的 In Range，Tiny 的 Fire / Brake / Pull Up；Clapper 的 Far Range、Maestro 的 Attack Choice、Clawmaiden 的 Spin Antic 跟随 SendRandomEventV4 的计数器（last_choice / miss_*）。

每招的实例数、每小时战斗时间的速率、到 200 还要几小时（同一实例上继续跑同样的数据策略；单实例墙钟 ≈ 战斗时间）：

| 敌人 | 家族 | 实例 | 每小时 | 到 200 还要 h |
|---|---|---|---|---|
| Choir Clapper | CC_SLAM | 393 | 128.0 | 已够 |
| Choir Clapper | CC_JUMP | 220 | 71.7 | 已够 |
| Choir Clapper | CC_CAST | 390 | 127.0 | 已够 |
| Choir Clapper | CC_JUMP_CAST | 202 | 65.8 | 已够 |
| Choir Clapper | CC_EVADE | 843 | 274.6 | 已够 |
| Choir Clapper | CC_ENTRY | 39 | 12.7 | 12.7 |
| Clawmaiden | CM_SLASH | 296 | 96.4 | 已够 |
| Clawmaiden | CM_SPIN | 356 | 116.0 | 已够 |
| Clawmaiden | CM_TELE | 78 | 25.4 | 4.8 |
| Clawmaiden | CM_ENTRY | 39 | 12.7 | 12.7 |
| Minister | MI_CHARGE | 334 | 108.8 | 已够 |
| Minister | MI_PARRY | 334 | 108.8 | 已够 |
| Minister | MI_EVADE | 219 | 71.3 | 已够 |
| Minister | MI_ENTRY | 52 | 16.9 | 8.7 |
| Maestro | MA_SLASH | 989 | 322.1 | 已够 |
| Maestro | MA_SUMMON | 177 | 57.7 | 0.4 |
| Maestro | MA_DEFEND | 417 | 135.8 | 已够 |
| Maestro | MA_POINT | 0 | 0.0 | 没出现过 |
| Maestro | MA_ENTRY | 39 | 12.7 | 12.7 |
| Song Automaton Tiny | AT_FIRE | 988 | 321.8 | 已够 |
| Song Automaton Tiny | AT_DEFEND | 1178 | 383.7 | 已够 |
| Song Automaton Tiny | AT_ENTRY | 282 | 91.9 | 已够 |
| Song Automaton Tiny | AT_LEAVE | 107 | 34.9 | 2.7 |
| Reed | RE_STAB | 281 | 91.5 | 已够 |
| Reed | RE_THROW | 268 | 87.3 | 已够 |
| Reed | RE_DEFEND | 230 | 74.9 | 已够 |
| Reed | RE_EVADE | 202 | 65.8 | 已够 |
| Reed | RE_ENTRY | 65 | 21.2 | 6.4 |
| Envoy | EN_SLASH | 95 | 30.9 | 3.4 |
| Envoy | EN_JUMPSLASH | 34 | 11.1 | 15.0 |
| Envoy | EN_CHARGE | 44 | 14.3 | 10.9 |
| Envoy | EN_HOPSLASH | 0 | 0.0 | 没出现过 |
| Envoy | EN_AMBUSH | 13 | 4.2 | 44.2 |
| Envoy | EN_ENTRY | 0 | 0.0 | 没出现过 |
| Choristor | CH_SLASH | 177 | 57.7 | 0.4 |
| Choristor | CH_WHIP | 170 | 55.4 | 0.5 |
| Choristor | CH_JUMP | 112 | 36.5 | 2.4 |
| Choristor | CH_ENTRY | 52 | 16.9 | 8.7 |
| Choir Bellbearer | CB_THROW | 1057 | 344.3 | 已够 |
| Choir Bellbearer | CB_EVADE | 395 | 128.7 | 已够 |
| Choir Bellbearer | CB_ENTRY | 65 | 21.2 | 6.4 |

- **结论**：除 Envoy 和各类入场外，还没到 200 的是 Clawmaiden CM_TELE 4.8 h、Song Automaton Tiny AT_LEAVE 2.7 h、Choristor CH_JUMP 2.4 h、Choristor CH_WHIP 0.5 h、Maestro MA_SUMMON 0.4 h、Choristor CH_SLASH 0.4 h（战斗时间，单实例墙钟大致相同）。首版写的"再跑约 2 h 就几乎全够"不对（首版表里就有 CM_TELE 6.6 h、AT_LEAVE 3.9 h、CH_JUMP 3.9 h）：按现在 13 场的速率还要约 4.8 h 才能让除 Envoy 和入场外的全部招到 200（四个实例并行约 1.2 h）。**Envoy 只在第 0 波出现一只**（38 HP，几秒就死）：普通斩 / 跳斩 / 冲锋 / 伏击分别还要 3.4 / 15.0 / 10.9 / 44.2 h，HopSlash 从没出现（`Hop Up?` 要主角在它上方）；各类入场每场 1–5 次（6.4–12.7 h）。这些要么另做定点采集（只打 Envoy 的 savestate、让它多活），要么按"每场一次的固定开场"处理、不要求 200。MA_POINT（`Point Start` 的下一个状态是空）在 Forum 不出现。
- 完整连战每场 714–990 s 游戏时间（11.9–16.5 min，中位 848 s；`--timebox 1500`；第 7 波两只 Maestro 是最慢的一段），一个实例一小时约 4 场。

## 12. R0：全部完整连战的表、留出召回、数据产品（2026-10-04，forum_planner_plan.md §5 R0；离线，没有连接游戏）

代码在分支 `worktree-wf_198518ec-9ba-1`。大文件不进仓库：每场缓存 `C:\ssbot\data\m2_forum_r0\cache`（728 MB，`forum_extract`）、按折支撑与接触 `C:\ssbot\data\m2_forum_r0\build_all\extra`（43 MB，`behaviour_build --extra`）、`*_hitboxes.npz`。下面的数字都来自这些输出，复现命令见 §12.7。

### 12.1 输入与表的重建

- **107 场完整连战**（不是计划写的约 128 场：开始重建时只有已关闭的录像能读，`074533` 和 `074719` 各有一个还在写的录像，各 13–14 场没进来；冻结的清单 `build_all\fights.json`）：`223640` 2、`230325` 1、`231917` 10、`014254` 25、`030413` 19、`074533` 25（i2_000）、`074719` 25（i3_000），fo_A，数据策略；**25.4 h 战斗时间**，229,792 次接触（帧）。按场交替分两折（54 / 53 场）。重建用了 6.6 h（扫描 3.8 h、9 类验证 2.2 h、按折支撑 0.6 h）。
- 实例数：除 Envoy 外每个家族都 ≥ 200（Clapper 跳 2,116、跳施法 1,978；Clawmaiden 瞬移 660；Choristor 跳 914、鞭 1,309；Maestro 召唤 1,386；Tiny 离场 828）。Envoy 只在第 0 波有一只：普通斩 692、跳斩 241、冲锋 385 也够了，**伏击 107（按现速率还要 22 h）**；HopSlash、Envoy 入场、Maestro `Point` 仍然一次都没出现。
- 样本内：Envoy 0 失败；其余每类 1–41 个"(接触, 模板集)"超出 0.5 u，无法归属 0。留出（另一折的家族级 anchor 模板，0.5 u 外的比例）：Envoy 0 / 9,145、Choristor 0.01 %、Clapper 0.08 %、Tiny 0.09 %、Minister 0.12 %、Maestro 0.17 %、Bellbearer 0.18 %、Reed 0.31 %、Clawmaiden 0.61 %（13 场时是 0.3–5.2 %）。投射物的 self 模板留出：Clapper 4 / 13,963、Clawmaiden 6 / 1,586、Reed 3 / 867、Bellbearer 19 / 4,750。`support_conservative` 仍全是 false（判据是 ≤ 0.1 %），所以认证靠 §12.2 的召回和余量。
- 新增导出（`behaviour_build --extra`）：每类每折单独的支撑（只用这一折的实例和这一折自己的接触残差膨胀）、每次接触的归属与样本内 / 留出残差（`contacts.jsonl.gz`；按状态的留出残差搜索到 3 u，`R_MARGIN_SEARCH_U`）、每折的停留区间和后继（`build.json` 的 `walk`）。
- **样本内验证没有通过**（`coverage.json` 的 `validation.ok = false`，构建用了 `--allow-failed-validation`）：样本内 55 次接触离本类的记录占据 > 0.5 u（Minister 16、Bellbearer 14、Clapper 12、Reed 7、Tiny 4、Choristor 2），19 次的来源在接触前后没有导出伤害碰撞体（Clapper 14、Reed 3、Tiny 1、Bellbearer 1），56 次不在任何攻击实例里；无法归属 0。支撑模板按样本内残差膨胀（≤ 0.5 u 的部分），这些超出的接触由 §12.2 的余量和结构项负责。
- **代码出处**：这次构建在分离的后台进程里跑，`git_info` 返回了空（`sha: null`）。表和 `coverage.json` 的 `code` 已补上 `7d09798`（构建 17:19 开始、该提交 17:20 记录的工作区；构建器代码 `behaviour_tables` / `gauntlet_tables` / `hitbox_tables` 从 7d09798 到修复轮只改了 `contact_rows(residuals)`，不影响表），并注明是事后补的。之后 `git_info` 在 git 进程失败时直接读 `.git` 文件，`behaviour_build` 对多敌人场地读不到版本就退出（`--allow-no-sha` 才继续）。

### 12.2 留出召回（认证；`support_recall --encounter Forum`，`ssbot.knowledge.forum_support`）

做法：每一折的场次用**另一折单独建的表**；每次接触对它被归属的那个敌人做预测（不是对所有敌人的并集），起点 c − L（L = 2 / 3 / 4 帧），配对同 Bell Beast（c 帧的主角框在 t_c，或 c − 1 帧的框在 t_c−1）。预测 = 规划器的做法搬到每个敌人上：当前状态的按状态模板（锚点 = 本次攻击第一个导出帧的 transform，镜像按 flipX）+ 训练折记录过的后继（停留区间各放宽 1 帧；当前状态已超过记录的最长停留时，后继可以从下一帧到视野末任意时刻开始）+ 攻击可能结束时的尾巴 + 已结束攻击的尾巴（6 s）。Forum 的锚点不固定：视野内才开始的攻击，锚点放在敌人当前位置沿导出速度每帧外推一个、两种镜像。查询用规划器的 `SupportQuery`（9 类全部模板一次打包，主角受伤框半宽 + 余量）。多段攻击的后续命中（构建器的 `follow`）不检查。

结构性补充（每一项的覆盖数在输出里单独计）：
1. **投射物按自身模板**：每个已武装的投射物（钟、Reed 的针、Clawmaiden 的矛和爆炸、Clapper 的炸弹和 rune）从它武装的位置和时刻放它的 self 模板（构建器早就有，留出 99.6–99.97 %）。钟的弹跳路径依赖投掷时主角的位置，投掷者的按状态模板只能以并集包住它，这正是计划 §4.2 说的"确定路径投射物"的前身；R2 里应换成真正的路径。
2. **同名候选**：构建器按 GameObject 名归属接触，第 12 波开场就在场上等待（`Fly In Ready`）的 "Song Reed" / "Song Pilgrim Maestro" 与第 0 / 6 波的同名敌人重名，来源路径的 "Wave 1/…" 父物体其实能区分（构建器没用它，R2 修）。召回里同名的敌人都算候选。
3. **当前伤害框管**：**导出在击杀那一帧就把敌人去掉**（它离开 HealthManager 列表），但垂死的身体还会伤人（§12.3 死亡尾巴）；等待中的敌人、停放的 Tiny 也有启用的身体框。对**不在任何攻击实例里**的敌人，用它最后一次导出的伤害框，按该类的最高速度（训练折每帧位移的 p99.99：31–56 u/s，去掉 hit-stop 小步长和单帧 > 1.2 u 的瞬移）向外长到查询时刻，最多用 0.5 s 前的框。
4. **家族并集**（可选 `--family-wide`）：当前攻击再放一份家族级模板（所有状态的并集，时间从攻击开始算），给"Multihit Clashed"（Reed 的连刺被拼刀弹开）这类少见分支兜底。

余量：每个家族一个，取**训练折**接触的按状态留出残差（对测试折的模板）的分位数（`--margin-q`，1.0 = 最大），投射物的余量取它们 self 模板的留出残差；**校准用的接触永远不是被检验的接触**（两折互换）。生产用的余量（两折全部接触的最大值）写进 `knowledge/1.0.30000/enemies/forum/support_margins.json`。

结果（每个滞后 228,333 次接触 = 两折全部非后续命中的接触；`C:\ssbot\data\m2_forum_r0\recall_*.json`）：

| 设置 | L2 | L3 | L4 |
|---|---|---|---|
| 只有按状态模板 + 尾巴，没有余量（`--margins none`，早期走法，无结构性补充） | 99.897 % | 99.899 % | 99.902 % |
| + 每家族留出余量（最大值） | 99.964 % | 99.964 % | 99.965 % |
| + 投射物自身模板、同名候选、伤害框管（余量 p99.9） | 99.998 % | 99.998 % | 99.998 % |
| 全部结构性补充但不要家族并集，余量 p99.9 | 99.9996 % | 99.9991 % | 99.9987 % |
| **+ 家族并集、未武装投射物、入场世界并集、身体外形管、投射物管（余量最大值）** | **100 %** | **100 %** | **100 %** |

（p99.9 那一行漏的 3 次：Minister 格挡姿态身体框、Reed 第 5 刺的 `Stab Hit 3`（只在 L4）、Clawmaiden 第 5 斩（L3 / L4）；它的面积代价中位 ×1.0、最大 ×3.9，≥ 0.5 u 的家族只剩 Tiny 冲撞 0.62、Clawmaiden 旋转 2.62、Envoy 冲锋 2.66、Maestro 防御 0.73、Reed 防御 1.84 / 待机 0.97 / 刺 0.68 和三种投射物。）

- **认证通过（最后一行，`support_margins.json` 的 `certified: true`）**：两折互换、余量只在训练折上校准，每个滞后 0 漏。不是靠按状态模板覆盖的接触单独计数（L2 / L3 / L4）：同名候选 47 / 45 / 46（第 12 波等待中的同名敌人，见上）、伤害框管（在攻击里的敌人身体超出家族余量）9 / 10 / 10、投射物管（被钉子打过、碰撞体短暂关闭的钟）1 / 1 / 0。没有一次接触是靠"攻击外"的管覆盖的（垂死和等待的身体都被别的项覆盖了）。
- 被这几项补上的漏网都是具体的机制，不是随机误差：钟被打中后改向（自身模板以武装点为原点，包不住改向后的路）、rune 在武装前就出现在落点（武装前用当前位置放它的模板）、Choristor 从场外跳入时身体框在落下那一帧才启用（用身体外形 + 速度）、Reed 的反击被拼开后"Multihit Clashed"把身体弹开（家族并集）、终局 Clapper 死后 rune 还会炸。
- 每类最高速度（伤害框管的增长速度，训练折每帧位移的 p99.99）：Maestro 25–28 u/s，Envoy 37–40，Clawmaiden 43–48，Choristor 45–48，Bellbearer 47–55，Reed 48–51，Clapper 49–54，Tiny 51，Minister 54–55。
- **余量和代价**（生产用 = 两折全部接触的最大留出残差；`support_margins.json` 的 `by_family` / `by_type`；面积 = 按状态 anchor 模板每个占用时间格的平均面积，不含主角半宽）：46 个家族里 26 个 < 0.5 u（面积 ×1.0–1.4）；≥ 0.5 u 的：Minister 待机 / 格挡、Tiny 冲撞 / 待机、投射物（针、矛、钟、炸弹）**3.0 u（搜索上限，即少数接触离留出模板 > 3 u）**，Envoy 冲锋 2.96、Clawmaiden 旋转 2.76、Reed 防御 2.62、Clapper 跳 2.11、Choristor 跳 1.61、Reed 刺 1.37、Reed 待机 1.29、Tiny 防御 0.98、Maestro 防御 0.76、Clawmaiden 斩 0.70、Choristor 入场 0.55、Maestro 斩 0.54。支撑面积中位 ×1.16，最大 ×4.3（Envoy 冲锋），×2 以上的 12 个家族（Clapper 跳、Clawmaiden 旋转、Minister 待机 / 格挡、Tiny 冲撞 / 待机、Reed 防御 / 待机 / 刺、Envoy 冲锋、Choristor 入场 / 跳）。这些大余量来自每个家族里个位数的离群接触（p99.9 时多数 ≤ 0.7 u，见上表第三行）：认证是在"最大值余量 + 结构性补充"下做的，规划器真正用哪一组余量要和视野内 FORCED_RISK 一起权衡（R2 / R5），换成更小的余量需要再跑一次召回认证。

### 12.3 数据产品（`forum_products`，107 场缓存；`knowledge/1.0.30000/enemies/forum/<产品>.json`）

- **多段连击（chains.json，修复轮重做）**：第一版按"90 帧内"把主角 Multihit 的 `special_damage` 挂到最近的那条连击上，复核发现这些事件没有来源、离上一次 damage 70–970 帧，"3 下"是时间巧合（例：Minister 斩 + 83 帧后的 Multihit + 104 帧后另一次斩），**作废**。事件里其实能看到机制：多段碰撞体（Minister `Slash Collider`、Choristor `Whip Hit 1–6`、Reed / Minister `ParrySlash Hit`）让主角的 `Roar and Wound States` FSM 走 Multihit：先是 Multihit 的 `TakeQuickDamage`（`special_damage`，无来源，同帧还有一条 `catastrophe` cause=quick 的 LethalBlock 记录），约 20 帧后是 `Final Hit` 的 `DamageHeroDirectly`——一条带来源的 damage 事件（12 场：175 次 tick、174 次 Final Hit，tick → Final Hit 20–21 帧）。现在一条连击 = 一次 Final Hit + 它之前、彼此间隔 ≤ 30 帧且不跨过上一次 Final Hit 的 tick；下数 = tick + 1，伤害 = tick 的量 + Final Hit 的量；其余 damage 都是单下。107 场：**Minister 斩 831 条：2 下 806、1 下 25；Choristor 鞭 401 条：2 下 381、1 下 20；Reed 招架反击 227 条：2 下 203、1 下 24；没有一条超过 2 下（2 格）**；tick 共 1,470 次，80 次后面没有 Final Hit（战斗结束等）。这三种碰撞体的 damage 事件全部是 Final Hit（第一次接触本身不报 damage，只触发 Multihit）。所以按"整链实测最大伤害计 h"：这三招各 2 格。仍要注意：数据模式 LethalBlock 把每一下的掉血挡掉，主角一直在 1 格；tick 次数是否随血量变化不知道【未核实】，R1 关掉 LethalBlock、高血量时再测一次。
- **死亡尾巴（death_tails.json）**：导出在击杀那一帧就把敌人从 ents 里去掉（离开 HealthManager 列表），之后看不到它的碰撞体；所以按"来源路径里有被杀敌人的 GameObject 名"的接触计：Clapper 321 次击杀里 39 次、Reed 52 / 535、Choristor 30 / 428、Envoy 17 / 107、Minister 14 / 428、Clawmaiden 13 / 321、Maestro 8 / 321 在**击杀那一帧**还有接触，**之后 0 帧**（§3 说的终局 Clapper 冻结后十几帧的接触，是在击杀前就开始、击杀后才报告的无敌段）。Tiny 和 Bellbearer 的名字在场上重名（池化克隆、多只同名），统计被别的同类污染（Tiny 997 / 1,426 次击杀后 7 s 内都有同名接触），不可用。规划器的死亡尾巴 = 击杀那一帧它最后的碰撞体（R2 用"最后一次导出的框"实现，召回里的当前伤害框管就是这么做的）。
- **击杀冻结（kill_freeze.json，击杀那一帧或下一帧开始的 freeze 事件；长度取 oracle 结束事件自己的 `frames` / `ms`）**：只有 Clapper 有：`BigEnemyDeathSlow`（down 0.04 / wait 0.06 / up 0.04 s，速度 0）323 次，9–10 帧（p50 165 ms）；最后一只时 `EnemyBattleEndSlow`（down 0.1 / wait 1.0 / up 0.75 s，速度 0.25）108 次：**104 次量到，112–138 帧，p50 114 帧（1.90 s）、p95 135 帧、最长 138 帧（2.47 s）**，其中 9 次的结束在缓存的战斗窗口之后（缓存在 f1 = 冻结开始 + 60 帧处截止；第一版因此丢了这些长的，只报了 112–114 帧），从录像里补读；另 4 次录像在 f1 就停了，没有结束事件（删失，不计）。`EnemyDeath`（0.04 / 0.024 / 0.04）6 次 8 帧。其余 8 类的击杀**没有**冻结（Choristor 409 / 428、Tiny 1,388 / 1,426、Bellbearer 530 / 535……）；和击杀同帧的少数冻结是主角自己的（`NailClashEffect` 0.25 s ≈ 24 帧、受击 `StartRecoil` ≈ 15 帧、`BindBreak` 33 帧）。所以 YELLOW"不打可能致死的一击"只对 Clapper 有冻结代价。
- **出手时间与距离（strikes.json，修复轮）**："承诺"= 进入攻击起始状态；"第一下"= 它自己的攻击碰撞体（不含身体）或它扔出的投射物第一次启用（投射物看到攻击结束后 4 s）。投射物现在按**出现**的那一帧归属（武装前在导出里已经出现的不武装前段的第一帧：rune bomb 出现后约 21 帧才炸，p95 32、最长 97 帧；rune slam 65 帧；Clawmaiden 的矛 80 帧；钟和 Reed 的针出现即武装），不再按武装那一帧：第一版里 Clapper 上一次施法留下、在下一次施法承诺后才炸的 rune bomb 被算给了新的一次（6 场抽查 20 % 的 CC_CAST 实例），CC_CAST 的 p5 因此是 0.067 s。p5 / p50（s）：Envoy 跳斩 0.408 / 0.416、斩 0.491 / 0.508、冲锋 0.491 / 0.508；Minister 冲刺 0.500 / 0.516；Clawmaiden 斩 0.508 / 0.516（旋转的矛 4.87 s 后才扔）；Choristor 斩 0.633 / 0.641、跳 0.767 / 0.783、鞭 0.824 / 0.833；Reed 刺 0.649 / 0.882、扔 0.667 / 0.683；Bellbearer 扔钟 0.658 / 0.666；Maestro 斩 0.699 / 0.716；Clapper 施法（炸弹）**0.400** / 1.18、锤 0.874 / 0.899、跳 1.39 / 1.42、跳施法 1.80 / 1.85。**最小值**仍有几个低于 0.35 s，全是投射物家族：Bellbearer 扔钟 0.0、Reed 扔针 0.1、Clapper 施法 0.117——上一招还在飞的钟 / 针在新一招承诺那一帧被打回或重新武装，出现即武装，按出现归属分不开；以 p5 为准。只用身体打的家族（Tiny 的 Fire 是身体冲撞、Clapper / Minister / Reed / Bellbearer 的 Evade、Clawmaiden 瞬移、Maestro 防御和召唤）没有"第一下"：改量**身体冲撞时间** = 承诺 → 它的伤害框第一次碰到"承诺那一帧主角的框"（主角原地不动；承诺时已经碰着的不计）：**Tiny 冲撞（AT_FIRE）7,963 次里 4,063 次碰到，p5 0.90 s、p50 1.31 s**（3,896 次没碰到：主角不在它冲的路上），最小 0.017 s 是贴身承诺。**所以"每类最快的一招都 ≥ 0.40 s"只按 p5 成立**（9 类：Envoy 跳斩 0.408、Clapper 施法 0.400、Minister 冲刺 0.500、Clawmaiden 斩 0.508、Choristor 斩 0.633、Reed 刺 0.649、Bellbearer 扔钟 0.658、Maestro 斩 0.699、Tiny 冲撞（身体）0.90），长于收割者一刀的 0.35 s（`attacks/reaper.json`：duration 0.35、有效 0.083–0.208 s）：敌人一承诺，主角立刻出的一刀大多能在它的第一下之前收刀，前提是人在它这一招的判定之外（判定的朝向坐标范围在文件里，例：Maestro 斩 x p99 3.65 u、Envoy 斩 4.6 u、Choristor 斩 9.5 u、Minister 冲刺 9.3 u、Clapper 锤 12.1 u、Envoy 冲锋 29 u）；投射物家族的最小值和 Tiny 贴身冲撞是例外。承诺时主角的水平距离 p50：Choristor 斩 2.7 u、Envoy 斩 3.2、Clawmaiden 斩 4.2、Minister 冲刺 5.9、Reed 刺 6.4、Clapper 锤 6.7、Maestro 斩 9.4、Clapper 跳 11.0。
- **惩罚窗口（strikes.json 的 punish，只算敌人自己的碰撞体）**：前摇（承诺 → 第一下）每个家族 100 % ≥ 0.35 s；后摇（最后一下 → 这一招结束）p50：Envoy 斩 0.71 s、Reed 刺 0.62、Envoy 跳斩 0.53、Choristor 跳 0.48 / 斩 0.47、Maestro 斩 0.47、Envoy 冲锋 0.43、Minister 冲刺 / 格挡反击 0.28、Clapper 锤 / 跳 / 跳施法 0.27、Clawmaiden 斩 0.18、Choristor 鞭 0.02。**后摇里放得下一整刀（0.35 s）的比例**：Maestro 斩 99.5 %、Envoy 98 / 96 / 94 %、Choristor 跳 96 %、Reed 刺 95 %、Choristor 斩 66 %、Reed 防御反击 57 %、Minister 冲刺 32 %、Choristor 鞭 32 %，**Clapper 和 Clawmaiden 斩、Minister 格挡 0 %**（它们收招就接下一个动作）：这几招只能在前摇或有效段从判定外打。
- **波间安静段（quiet.json）**：没有在场敌人（离开等待状态）也没有武装投射物的 ≥ 0.25 s 空档：107 场 1,038 段（约 9.7 段 / 场），p50 1.02 s、p95 3.0 s、最长 4.06 s；**≥ 1.52 s（Bind 的 1.37 s + 0.15 s）的只有 37.6 %**。按下一波：Clapper 波前 p50 2.17 s、92 % 够；Maestro + Reed（第 12 波）p50 2.0 s、80 %；Bellbearer + Reed（第 2 / 8 波）p50 1.02 s、48 %；只有 Reed 的 3.0 s、100 %；其余波前都是 1.016 s（BattleWave 的 1 s startDelay），0 % 够。所以"在实测的波间空隙 Bind"（DESIGN §3.5.7）只在第 7、12、13 波前和第 8 波前的一半时间可行。
- **Garmond 选谁（garmond.json，有 allies 导出的 50 场：`074533`、`074719`）**：他进入 Chase Target / Wildslash / Charge / Stomp 等状态后 3 s 内打中的第一个敌人，11,673 次，其中场上 ≥ 2 个候选的 9,302 次：是离 Garmond 最近的 53.0 %、HP 最多的 37.3 %、离主角最近的 36.8 %（可同时成立）。他大体追最近的，但不是确定的。

### 12.4 你的回答的核对（M2.md "Forum 打法问答"）

- **防御姿态与固定反击（stances.json）**：
  - Minister 格挡（MI_PARRY）2,621 次，姿态里被打中 627 次，之后有反击的 241 次：FSM 是 `Parry Stance → Parry Block → Parry Slash 1 → 2 → 3 → 4`（591 次；没被打中的 1,977 次是 `Parry Stance → Parry Stance End`）。被打到 → 第一个反击框 p50 0.27 s（p95 1.17 s），每段有效约 0.2 s，碰撞体 `ParrySlash Hit 1–4`，**parry 位全是 5（拼刀 + counter）：可拼刀**；反击是一段冲刺斩，朝向坐标 x −12.8…+15.9 u、y −7…+9.4 u。
  - Reed 防御（RE_DEFEND）1,899 次，被打中 511 次，反击 175 次：`Defend → Block → Parry Y Aim → Parry Slash →`（`Multihit → Multihit End` 227、`Parry Slash End` 225、**`Multihit Clashed` 82：数据策略的乱砍已经把它的反击拼掉了 82 次**）。被打到 → 反击框 p50 0.20 s，有效 p50 0.28 s（多段时到 0.75 s），`ParrySlash Hit` parry 位 5，可拼刀；朝向坐标 x −11.2…+11.3 u。
  - Maestro 防御（MA_DEFEND）3,359 次、Tiny 防御（AT_DEFEND）9,464 次：被打中 734 / 1,666 次，**没有反击碰撞体**（Maestro 是 `Defending → Defend End → Slash Recover F`）。
  - 结论：你说的"防御姿态被打中后有固定反击、可以拼刀"对 Minister 和 Reed 成立（反击由被打触发、FSM 固定、parry 位可拼，录像里已有 82 次实际拼开）；"跑出反击范围"要跑出 11–16 u 的冲刺距离，靠跑不现实，正确做法是不打它的姿态或拼它的反击（R8）。
- **飞行怪往斜下打（below.json）**：在空中承诺的攻击里，它自己的碰撞体（加上它扔出的投射物）碰到"站在承诺点正下方地面上的主角"的比例，对比前方 3 u / 6 u：Bellbearer 扔钟 1.7 % vs 10 % / 35 %；Maestro 斩 0 %；Tiny 冲撞 7.1 % vs 34 % / 58 %；Reed 刺 9.9 % vs 17 % / 25 %、扔针 6.4 % vs 15 % / 22 %：**这四类正下方明显更安全，成立**。但 **Minister 冲刺 30 % vs 30 % / 19 %、格挡反击 37 % vs 27 % / 13 %，Clawmaiden 斩 26 % vs 28 % / 12 %、旋转 + 矛 40 % vs 38 % / 32 %**：这两类会俯冲，正下方不比前方安全。
- **偷丝怪的距离与冲刺斩（clawmaiden_distance.json）**：它在两招之间飞的时候（67,383 个样本帧）离主角水平距离 p5 1.9、p50 8.0、p95 14.6 u，高出主角 p50 3.1 u，水平速度 p50 5.0 u/s（它的飞行上限，最大 12）。冲刺斩够距**估计** 7.0 u（冲刺 28 u/s × 0.1 s = 2.8 u + 收割者冲刺斩多边形前沿 4.16 u；冲刺斩自身的位移没建模【未核实，R1 测】）：38.7 % 的时间够得着，站着横砍（3.6 u）只有 10.7 %。它确实保持在比横砍远得多的距离，冲刺斩够得着的时间是横砍的 3.6 倍；中位 8.0 u 比估计的冲刺斩够距略远，"正好控制在冲刺斩距离"要等 R1 实测冲刺斩真实够距再定。
- **小铃铛（bells.json）**：`Throwing Bell` 的伤害框 parry 位在 135,712 帧里**全是 4（只有 counter，没有拼刀位）**：按导出它不会触发 NailClash；被钉子打中走的是自己的 `Nail Hit`（1,391 次），打中后 3 帧速度 p50 27.6 u/s（p95 32.4）：**可以打走，成立**（你说的"拼刀"在游戏里是这个改向，不是 NailClash 的弹反无敌）。下劈：主角在钟上方、下落中打中它 100 次，之后 10 帧内弹起（vy > 5 u/s）只有 8 次：**下劈大概率弹不起来，成立**。
- **出招的距离边界（boundaries.json，给 R1 的诱招探针）**：每个家族被选中时主角的水平距离 p50 / p99 / 最大，以及最大值 ±1 u 内采到的决策数（选了它的 / 超出边界的）：Clawmaiden 斩 3.0 / 4.31 / 4.52（1,133：427 / 432）、旋转 10.7 / 10.9；Clapper 锤 6.7 / 8.46 / 8.76（19,359：1,131 / 3,528）；Envoy 斩 3.2 / 4.9 / 5.7；Choristor 斩 2.7 / 7.7 / 8.1、跳和鞭 p99 12.8；Minister 闪避 2.4 / 5.1 / 5.3、冲刺 p99 7.4（最大 16.8）、格挡 p99 7.4；Reed 闪避 p99 4.3、防御 p99 8.1；Bellbearer 闪避 p99 5.1。Maestro、Tiny 的招 p99 ≈ 29 u：与距离无关。最大值远大于 p99 的（Minister 冲刺、Clapper 跳 / 施法、Reed 各招）是少数远距离情形，诱招时以 p99 为边界。近战家族边界附近的样本已经很多（几千到上万次决策），远程家族边界附近的少（几十到一百）。

### 12.5 forum_simul 复现设计 H 的表 1.2

`forum_simul --run 20261003_074719_Forum_A_data --first 12`（同样的 12 场、609,481 帧）：按帧在场数 0–8 个的比例 2.31 / 22.33 / 32.23 / 19.06 / 12.43 / 2.65 / 0.64 / 2.08 / 6.28 %，与 H 表 1.2 逐项相同；每波在场 p50 / p95 / 最大、≥ 2 的比例、最常见组合、x 跨度、最近两只 < 3 u、6 u 内 ≥ 1 / ≥ 2 也一致（第 13 波 ≥ 2 是 84.7 % 对 H 的 82 %）。不同的三列是定义：每场秒数这里是游戏时间（dt 之和，H 是帧数 / 60，约低 5–8 %）；"两侧都有"这里含 12 u 边界（第 2 波 14.8 % 对 5 %，其余差 1–3 个百分点）；"全待机 / 混合 / 全承诺"这里把入场也算承诺（第 0 波 7 / 49 / 44 % 对 8 / 56 / 36 %）。

### 12.6 planner_bench --encounter Forum（脚手架）

规划器还没有多敌人预测（R2），所以这里只测"支撑阶段"在真实 Forum 走法上的代价：每 tick 把所有敌人的支撑放置（召回同一套走法，视野 0.8 s；视野内才开始的攻击每 0.2 s 一个锚点）装进一个 `SupportQuery`，再查 400 条 × 36 步的弹道候选（主角位置出发的扇形，不是规划器的候选）。`074719` i3 ep0 前 3,000 帧（第 0–1 波），4 线程，训练折 0 的表 + 余量：**每 tick 放置 p50 28,506、p99 38,391；放置 20 ms / 422 ms，查询 133 / 199 ms，整 tick 154 / 574 ms（p50 / p99）**；400 条候选在每一 tick 都全部碰到支撑。也就是说把召回的走法原样搬进规划器，比 R3 的 9 ms 预算慢约 20 倍、而且会永远 FORCED_RISK：R2 需要（1）停留区间宽的状态用"时间上预先膨胀"的模板一次放置（不是每 1/60 s 一个），（2）视野内才开始的攻击用按速度膨胀的锚点模板（不是每帧一个锚点 × 两个镜像），（3）两招之间的身体按当前位置重新锚定（IDLE 家族从待机开始算的模板太宽：`forum_simul` 的预测统计在一场上（单场建的表、样本内、无余量），主角站着不动时 +0 s 就有 76 % 的帧在支撑里）。

### 12.7 复现

```
cd brain   # 低优先级、NUMBA_NUM_THREADS=4，一次一个
..\scripts\uv.cmd run python -m ssbot.tools.behaviour_build <7 个运行> --encounter Forum --allow-failed-validation --extra C:\ssbot\data\m2_forum_r0\build_all\extra --fights-list C:\ssbot\data\m2_forum_r0\build_all\fights.json
..\scripts\uv.cmd run python -m ssbot.tools.forum_extract --fights-list C:\ssbot\data\m2_forum_r0\build_all\fights.json --out C:\ssbot\data\m2_forum_r0\cache
..\scripts\uv.cmd run python -m ssbot.tools.support_recall --encounter Forum --extra C:\ssbot\data\m2_forum_r0\build_all\extra --cache C:\ssbot\data\m2_forum_r0\cache --margins heldout --margin-q 1.0 --family-wide --area --write-margins <json> --json <json>
..\scripts\uv.cmd run python -m ssbot.tools.forum_products --cache C:\ssbot\data\m2_forum_r0\cache
..\scripts\uv.cmd run python -m ssbot.tools.forum_simul --cache C:\ssbot\data\m2_forum_r0\cache --run 20261003_074719_Forum_A_data --first 12
```
