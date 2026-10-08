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
- 各类型 FSM：Song Heavy Sentry `Control`（`Slam Antic`、`Jump Antic → Jump Aim → Jump → Air → Charged? → Slam`、`Spell Antic → Cast 1/2`（`Bomb Cast` FSM 放丝弹）、`Cast Slam Antic`、`Evade Scuttle`、`Avoid Type`（`AVOID BUDDY`：两只互相让））；**抽丝怪可以整场不出现**（2026-10-05，你给的截图：圣城那里推车、长廊尽头上天花板、打掉里面的机关）：Forum 三只 Clawmaiden（第 4 / 6 / 11 波）的 `Control` 在 `Battle Ready` 后进 `Burned?`：`PlayerDataBoolTest marionettesBurned` 为真 → `Burn Death`（移到 y −100、`InstaDeath`），开波即死；这个开关由 `Hang_14` 的 `break_thread_core`（FSM 变量 PD Bool = marionettesBurned）和 `Handmaiden Scene` 设置（场景包，`find_pd.py`）。Forum 场景里只有 Clawmaiden 读它；别的场景里 Maestro、Reed、Envoy、Choristor 也读（作用没查）。到 `Hang_14` 机关的路线要求（你说要二段跳）、绕路时间没查。；**下劈"拼"冲锤**（2026-10-05，你：Clapper 的冲锤可以用下劈拼刀，不用跑；你 16:04 的半速练习 `20261005_160435`，Wanderer，脚本 `scratchpad/clapper_ds.py`）：22 次在 Clapper `Slam Antic` / `Slam 0–1` / 跳砸时下劈它，**0 次 NailClashEffect**（不是拼刀，和 canClashTink = 0 一致），但 **15 / 22 次没掉血**：下劈先打中它本体（`hit DownSlash`），之后几帧的锤 / 本体接触被下劈命中的无敌（`DOWNSPIKE_INVULNERABILITY_STEPS` 8 步 0.16 s，长版 16 步）挡掉、人也弹起；7 次掉 2 格：锤先到（下劈还没打中）或下劈打中得太早（命中后 12–19 帧锤才到，无敌已过）。所以是"下劈命中无敌 + 弹起"，要在锤生效前不到 0.16 s 内打中它头。**两只不同时出招**（2026-10-04 读 FSM）：`Close Range` 和 `Far Range` 选招前先读另一只（`Buddy`）`Control` FSM 的 `Is Attacking`，为真就 CANCEL 回 `Idle`；所以最后一波一只在出招时另一只只会走 / 待机（身体照样伤人），不会两只同时抡锤；另外每个起手状态（Slam / Jump / Spell / Cast Slam Antic、Jump Aim、Evade Scuttle）第一件事是 `FaceObjectV2` 面向主角（两次转身至少隔 0.5 s）；其余类型的状态表在 `fo/fsm_enemy_*.txt`（场景包导出），行为表从采集录像生成。

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

全部波次敌人都在 "ents"：HealthManager（src 位 1）+ DamageHero（2）；Reed、Choristor、Minister 还有 multi_wounder（8）。实体 iid 稳定，"fsm" 事件的 `ent` 和 "hit" 事件的 `ent` 就是 ents[].iid（行为表按 iid 分流）。parry 位：4 = 只有 counter；5 = clash + counter（可拼刀）。**核对（2026-10-04，你问 Clapper 能否拼刀、Skarrgard 能拼）**：parry 的 clash 位就是 `DamageHero.canClashTink`（拼刀只走 `DamageHero.TryClashTinkCollider`，反编译里没有别的 NailClash 路径）；场景包直接读（`C:\ssbot\sandbox\forum_tools_scripts\clash_bits.py <scene>`）：Forum 两只 Clapper 的本体和 `Slam Collider 1/2`（都是 2 伤）canClashTink = 0，Clawmaiden 的 `Spear`（2 伤）也是 0；Hunter's March 守门竞技场（`ant_02`）的 Skarrgard（斯卡尔守卫，`Bone Hunter Throw`）本体 2 伤 = 0、斩击 `JSlash1/2`、`Slash1`、`Slash2`（含 3 个副本）2 伤 = 1。所以能否拼刀是逐个碰撞体设的，和伤害无关：Skarrgard 的斩能拼，Clapper 的砸不能。**拼刀的效果（2026-10-04，你问"有无敌吗、是不是只抵消那一刀、最小间隔、下劈能不能拼"；反编译 `DamageHero.cs:347-498`、`HeroController.cs:5060-5098, 5391`）**：主角 `NailParry` → `parryInvulnTimer` = INVUL_TIME_PARRY **0.15 s（实测，probes.md），期间所有 ENEMY 类伤害都不进**（不只是被拼的那一下；尖刺等危险物不算）；另有 `NailClashEffect` 冻结（实时 0.25 s，速度 0；连续拼刀在 0.15 s 内不再冻结）；后坐：横拼向反方向退（`RecoilLeft/Right`），上挑拼刀止住上升（`RecoilDown`），**下劈拼刀弹起**（`DownspikeBounce`，同 pogo）；这一刀对那只敌人不造成伤害（`PreventDamage`）；0.1 s 后 `NailParryRecover` 把攻击冷却清零，马上能再砍。**敌人的招不一定被抵消**：只给被拼的碰撞体和它的父物体发 `PARRIED`，要它自己的 FSM 处理；Forum 的主控制 FSM 里只有 Envoy 冲锋（`Charge`/`Reset` → `Deflect`）和 Reed 防御反击（`Parry Slash` → `Multihit Clashed`）接这个事件，其余（Minister 冲刺、Clawmaiden 斩、Choristor、Maestro……）**招照常打完**，0.15 s 后还站在判定里就会挨打（碰撞体自己的 FSM 是否另有处理没查）。最小间隔：同一个敌人碰撞体拼完要等 0.1 s + 1 帧（`nailClashRoutine`）才能再拼；主角这边 0.1 s 后就能再出刀。能拼的刀：所有纹章的横砍、上挑、**下劈**（Hunter `DownSlash`、Reaper `DownSlash New`、Wanderer `DownSlash`）、冲刺斩、贴墙砍的 `canHitSpikes` 都是 1（`nail_clash_attacks.py`）；只有开局没披风时的 `Cloakless` 踢（canHitSpikes 0）拼到会改成主角挨 1 下。**后坐只看出刀方向，不看朝向和形状**：`HeroController.cs:4196-4222` 给横砍设 0 / 180（贴墙时反过来）、所有纹章的上挑一律 90、下劈 270，拼刀分支按它走（横 → `RecoilLeft/Right` 3.75 u/s × 8 步 ≈ 0.6 u，负重环带 4 步 ≈ 0.3 u；上 → `RecoilDown` 只截断上升；下 → 弹起）。所以**收割者背对敌人用上挑拼刀可以，而且不被推开**：Reaper 上挑的伤害多边形按朝向坐标是 x −2.12…+0.81、y −0.63…+3.77（相对主角 transform，有效 0.083–0.25 s；`attacks/reaper.json` shapes.up），即身后 2.1 u 内、腰部以上到头顶 3.8 u；低于腰线的招（贴地横扫）和敌人身体碰不到它。gravity_scale 实测：Choir Clapper 1.4（Air 中每物理步 dvy −1.68 → g_eff 84）、Choristor 1.1、Envoy 1.0、Throwing Bell 1.0，其余都是飞行敌人（0）。

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
- 其他招：`Slam 0`/`Slam 1` 各 SetVelocityByScale −30（向前冲 3.0–4.3 u，0.12–0.32 s），`Slam Collider 1` 前 −1.91…+6.24、y −3.19…+3.13（地面时顶 10.58），`Slam Collider 2` 前 0.67…7.76、y −4.99…+2.65（顶 10.10）；`Evade Scuttle` 0.35 s 内以 15 u/s **向后**（背离主角）退，背后 6 u 内有墙则 `Escape Jump` → Jump Slam / Jump Cast；Bomb Cast：`First Bomb` 后 9 对、每 0.15 s 一对、间距 4.2（最远 ±37.8，穿墙），每颗 `rune bomb small` r 2.17、中心 y 3.67、亮 5–7 帧（偶尔 16–17）；Jump Cast 落地后约 2 s 在落点出现 `rune slam`，再 1.28 s 爆：圆 r 7.19、中心 y ≈ 3.34（顶 ≈ 10.5），亮 7–19 帧。**大符文在它前方**（2026-10-04，你说"大符文放在怪前边，贴着后背炸不到"；场景包）：`rune slam` 从子物体 `Rune Slam Point` 生成（FSM `SpawnObjectFromGlobalPool spawnPoint=$Rune Slam Point`），它在本体 transform 的锤子一侧（和 `Pt Slam` 同侧）**6.62 u**（Finale 两只：本体 x 21.03 / 42.03，点 14.415 / 35.415；Wave 8 同样 6.615）。r 7.19 的圆因此覆盖本体中心后方约 0.6 u 到前方约 13.8 u；本体半宽约 2.6–2.8 u（Antic 本体盒 x −2.78…+2.59），所以**贴着后背站在圆外**，你说的成立。注意圆按生成那一刻的位置和朝向固定在世界里，炸之前（约 3.3 s）它转身或走开，圆不跟着动。

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

### 12.2 留出召回与认证（`support_recall --encounter Forum`，`ssbot.knowledge.forum_support`；修复轮 2026-10-04 重做）

做法（不变的部分）：每次接触对它被归属的那个敌人做预测（不是对所有敌人的并集），起点 c − L（L = 2 / 3 / 4 帧），配对同 Bell Beast（c 帧的主角框在 t_c，或 c − 1 帧的框在 t_c−1）。预测 = 规划器的做法搬到每个敌人上：当前状态的按状态模板（锚点 = 本次攻击第一个导出帧的 transform，镜像按 flipX）+ 训练表记录过的后继（停留区间各放宽 1 帧；当前状态已超过记录的最长停留时，后继可以从下一帧到视野末任意时刻开始）+ 攻击可能结束时的尾巴 + 已结束攻击的尾巴（6 s）。Forum 的锚点不固定：视野内才开始的攻击，锚点放在敌人当前位置沿导出速度每帧外推一个、两种镜像。查询用规划器的 `SupportQuery`（9 类全部模板一次打包，主角受伤框半宽 + 余量）。多段攻击的后续命中（构建器的 `follow`）不检查。结构项（每一项的覆盖数单独计）：投射物按自身模板（已武装的从武装点 / 时刻放；在导出里还没武装的可以从下一帧起在原地武装）、家族并集（`--family-wide`：当前攻击再放一份所有状态的并集，给"Multihit Clashed"这类少见分支兜底）、入场家族的世界坐标并集、同名候选、当前伤害框管 / 身体外形管 / 投射物管（只在预测失败后试，单独计）。

**第一版的"认证"不成立（复核结论，确认）**：(1) 认证折 k 的余量来自训练折接触的留出残差，而这个残差是对**折 k 自己的占据**算的（`behaviour_tables.validate` 的留出 = "对另一折"），等于用被检验折的模板定余量；结构项也是看着这 107 场的漏网逐个加的（`recall_final` 8 行漏 → 6be2b89 加四项 → `recall_cert` 0 漏）。(2) 待机家族的按状态模板锚在**待机开始处**，Minister 追人几秒、Tiny 到处飞，模板盖住大半个场地，100 % 对它们接近空话（下面"代价"一段的场地覆盖率）。(3) 构建之后才关闭的 35 场上，折 0 的表 + 每折余量漏 1 次（Clawmaiden 斩 `074533` i2/ep30 f1590148）。修复：

1. **三份不相交**（`--split 3way`，默认）：认证折 k 的场次用折 1−k 建的表；折 k 的场按顺序交替分两半，每一半用**另一半**接触的留出残差定余量（这些残差正是对折 1−k、即所用表的占据算的）。表、余量、被检验的接触来自三组互不相交的场次。旧做法留作 `--split 2way`（注明有泄漏）。
2. **待机身体管**（idle body tube）代替待机家族的按状态模板：敌人在待机家族里时，不放当前待机实例的模板，改用它最后一次被看到时的伤害框（没有伤害框时用该类的身体外形），沿导出速度平移，再按"离看到时的游戏时间"（1/60 s 一格，5 % 容差向上取格）长出 g[格]。g 在训练场上标定（`IdleTubeCalibration`）：同一待机实例里 i 帧和 i+n 帧（n ≤ 40）都可见时，i+n 帧的伤害框超出"i 帧的框按 i 帧速度外推"的最大距离，每类每格取最大值、单调化。按游戏时间而不是帧分格：`074533` i2/ep2 有一次 4 帧跨了 0.48 s 的卡顿，按帧分格会把 Clapper 4 帧的增长算成 7.9 u（按时间分格是 1.5 u）。待机里可能开始的攻击照常在外推锚点上放（敌人下一帧就可能出手，那一帧的身体也在攻击模板里），待机实例只在视野内**新进入**时（攻击结束后，锚点 = 那时的位置，只用模板前几帧）才放模板。待机家族不再有余量。107 场的生产值（4 帧 ≈ L4）：Maestro 1.33 u、Clapper 1.53、Envoy 1.80、Reed 1.89、Tiny 1.92、Clawmaiden 1.92、Bellbearer 2.08、Minister 2.21、Choristor 2.52（Choristor 的 Hop Back 在待机里瞬间后跳；导出速度为 0 的移动全进了 g）。注意 g 随时间长得快（20 格 3.0–8.8 u、40 格 3.6–14.9 u）：它只适合几帧的视野，规划器 0.8 s 的视野要另想办法（R2）。
3. **来源没写敌人名字的接触**：`damage_blocked` 的来源有时只有碰撞体子物体（`Colliders/Collider Fly`），构建器在同类里挑了一个导出这个碰撞体的敌人（`contacts.jsonl.gz` 的 `src` 写的是它挑的名字），不一定是碰到主角的那只（例：`223640` i2/ep0 f767636 归给了 7 u 外的那只 Minister；第一版里它的 Chase 模板盖住整个场地，所以"覆盖"了）。现在按 oracle 事件自己的来源判断，这类接触同类的每个敌人都是候选（"unnamed-source candidate"，单独计）。
4. **在新数据上认证一次**：配置冻结在 `da1cd41` 之后，对构建之后才关闭的 35 场（`074533` i2 ep25–41、`074719` i3 ep25–42；`behaviour_build --contacts-only --exclude-fights`，在 8d12c86 扫描，74,613 次接触、74,120 次非后续）只跑了一次：两折的表各测一遍，余量 = 107 场全部接触的最大留出残差（生产余量，待机家族除外），管和身体管的参数也来自 107 场。这才是认证。

结果（`C:\ssbot\data\m2_forum_r0\recall_*.json`）：

| 设置 | 场次 / 每个滞后的接触 | L2 | L3 | L4 | 不是靠预测本身覆盖的（每个滞后） |
|---|---|---|---|---|---|
| 第一版，早期代码（6be2b89 之前），无余量 | 107 / 228,333 | 99.897 % | 99.899 % | 99.902 % | — |
| 第一版，早期代码，每折余量（泄漏） | 107 / 228,333 | 99.964 % | 99.964 % | 99.965 % | — |
| 第一版"认证"（每折余量有泄漏、结构项按这 107 场的漏网加） | 107 / 228,333 | 100 % | 100 % | 100 % | 同名 45–47、伤害框管 9–10、投射物管 0–1 |
| **开发：三份不相交 + 待机身体管**（`recall_dev3.json`，da1cd41） | 107 / 228,333 | **100 %** | **99.9996 %** | **99.9996 %** | 同名 46–47、无名来源候选 15–18、伤害框管（攻击中）21–23、投射物管 0–1 |
| 开发，同上但不要余量（`recall_dev_nomargin.json`） | 107 / 228,333 | 100 % | 99.9996 % | 99.9991 % | 同名 48–50、无名来源候选 22–23、伤害框管（攻击中）48–49、投射物管 5–6（漏的 3 次：上面那次 Clawmaiden 斩 L3 / L4、Reed 第 5 刺 L4） |
| **认证：35 场新数据，折 0 的表 + 生产余量**（`recall_fresh.json`） | 35 / 74,120 | **100 %** | **100 %** | **100 %** | 同名 9、无名来源候选 4；管 0 |
| **认证：35 场新数据，折 1 的表 + 生产余量** | 35 / 74,120 | **100 %** | **100 %** | **100 %** | 同名 9、无名来源候选 4；管 0 |

（前两行是第一版用早期走法跑的，不是对最终代码的对照消融，只作历史记录。待机身体管算在预测里，单独计数：开发每个滞后 474–495 次、认证 133–147 次；其余待机接触被它下一帧可能开始的攻击（外推锚点上的模板前几格）、刚结束攻击的尾巴或它的投射物盖住。）

- **开发集漏的 1 次**（L3、L4 各 1）：Clawmaiden 斩 `074719` i3/ep5 f281119，构建器记它在 `Slash 5` 第 0 帧，起点时在 `Slash 3`；对另一折 `Slash 5` 模板的留出残差 0.068 u，而它所在那一半拿到的 CM_SLASH 余量是 0.0（另一半的 CM_SLASH 接触全在表里）。它不是结构漏洞，是"半折余量没见过这个尾巴"：生产余量（0.7048 u，来自 107 场的最大值）盖得住它。没有为它改任何东西（之后的认证配置就是跑开发集的那一份）。
- **余量本身的作用很小**：同一套结构不要余量（`--margins none`）在开发集上是 100 / 99.9996 / 99.9991 %（3 次），只是伤害框管和投射物管多盖了 48–49 / 5–6 次；召回主要靠结构项（待机身体管、投射物自身模板、家族并集、管、候选），不是靠余量。
- **认证通过**：冻结的配置在 35 场新数据上两折的表都是 0 漏（`support_margins.json`：`certified: true`、`certification: "fresh"`，开发集的数在 `development` 里）。**通过的是生产余量**（107 场全部接触的最大值），不是每折 / 每半的余量：复核时用每折余量，折 0 的表在这 35 场上漏了上面那次 Clawmaiden 斩（需要 0.4–0.5 u，每折余量 0.257）；生产余量 0.7048 u。新数据上没有一次接触要靠管（第一版每个滞后 9–10 次"攻击中的伤害框管"、开发集 21–23 次，都在 107 场里）。
- 每类最高速度（伤害框管，训练场每帧位移的 p99.99）：Maestro 25–28 u/s，Envoy 37–40，Clawmaiden 43–48，Choristor 45–48，Bellbearer 47–55，Reed 48–52，Clapper 49–54，Tiny 51，Minister 54–55。
- **余量**（生产 = 107 场全部接触的最大留出残差，待机家族不再有；`support_margins.json` 的 `by_family` / `by_type`）：38 个（29 个敌人家族 + 投射物 6 个 + 入场 3 个）里 21 个 < 0.5 u；≥ 0.5 u 的：**3.0 u（搜索上限）**：Minister 格挡、Tiny 冲撞、Reed 的针、Clawmaiden 的矛、钟、rune bomb；Envoy 冲锋 2.96、Clawmaiden 旋转 2.76、Reed 防御 2.62、Clapper 跳 2.11、Choristor 跳 1.61、Reed 刺 1.37、Tiny 防御 0.98、Maestro 防御 0.76、Clawmaiden 斩 0.70、Choristor 入场 0.55、Maestro 斩 0.54。
- **代价**（`support_area`；面积 = 按状态 anchor 模板（投射物：self 模板）每个占用时间格的平均面积，不含主角半宽；**场地覆盖率** = 模板锚在场地带 x 14.01–48.99、y 3–18 的中心、加主角半宽（和余量）后占场地带的比例，每个模板取占用格的中位数，家族取中位数 / 最大格）。面积比：48 个（42 个敌人家族 + 6 个投射物）中位 ×1.13，**最大 ×7.4（Reed 的针），×2 以上 12 个**：投射物 4 个（针 ×7.4、rune bomb ×6.0、矛 ×4.1、钟 ×2.7）+ 敌人家族 8 个（Envoy 冲锋 ×4.3、Reed 防御 ×2.8、Clawmaiden 旋转 ×2.6、Tiny 冲撞 ×2.5、Choristor 跳 ×2.4、Clapper 跳 ×2.3、Minister 格挡 ×2.3、Choristor 入场 ×2.3）；只看敌人家族中位 ×1.12、最大 ×4.3。（第一版报的"最大 ×4.3、12 个家族 ×2 以上"漏了投射物的 self 模板，又把 Reed 待机 ×1.70、刺 ×1.64 算进了 ×2 以上；那时 ×2 以上的敌人家族是 10 个。）
- **场地覆盖率**（无余量 → 生产余量，中位格）：待机模板（现已不放）Tiny 93 %、Clawmaiden 63 %、Bellbearer 62 %、Minister 55 %（最大格 96 %）、Clapper 36 %；**待机身体管在 4 帧时只占 6–20 %**（Maestro 6 %、Tiny 7 %、Envoy 8 %、Bellbearer 9 %、Clawmaiden 9 %、Choristor 11 %、Reed 12 %、Minister 17 %、Clapper 20 %：身体外形 + 主角半宽 + g）。**但几个会移动的攻击家族的模板本身也很宽**：Clawmaiden 旋转 74 % → 99 %、Tiny 防御 75 → 79 %、Reed 刺 66 → 77 %、Minister 格挡 52 → 76 %、Tiny 冲撞 30 → 64 %（最大格 100 %）、钟 34 → 65 %、Reed 防御 26 → 50 %、Clawmaiden 斩 46 → 54 %、Clapper 跳施法 48 %、施法 44 %。这些家族的召回同样有一部分是"模板大"换来的：锚在攻击开始处的按状态模板对边飞边打的招（旋转、冲撞、防御里的移动）天然就宽，R2 要给它们像待机一样按当前位置重新锚定（或按路径条件化），再认证一次。

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
  - **两个分支之后的冷却（2026-10-04，你问"被打触发反击和没被打的两个分支 CD 可能不同，要分别统计"；场景包 FSM 静态读，`Control` FSM）**：
    - Minister：两个分支都汇到 `Evade?`（SendRandomEventV4 FINISHED / EVADE 各 0.5，eventMax 2 / 2、missedMax 2 / 2；EVADE 只在主角在 `Evade Range` 里时发）→ `Retreat?` → `Set Attack Time`（`Attack Time` = 随机 0.5–1.5 s）→ `Chase`：`Chase` 里 `Attack Time` 每秒减 1，到 0 置 `Attack Ready`，`Attack Ready && In Attack Range` → `Attack Choice`（冲刺 / 格挡）。所以**冷却本身两支相同**（重新抽 0.5–1.5 s），差别只在反击这一支多花的时间（Block + 4 段斩）。**被打会缩短冷却**：`Chase` 里 TOOK DAMAGE → `Range Check` 把 `Attack Time` 夹到 ≤ 0.5 s；`ReAlert` 直接设 0.5 s。
    - Reed：`Defend Start` 置 `Just Did Defend` = 1，只有 `Stab Antic` 和 `Throw Antic` 把它清 0；`Alert` 里每次进入抽 `Will Defend`（RandomBool），`Will Defend && In Defend Range && !Just Did Defend` → DEFEND。所以**防御过一次（不管被没被打、反没反击），刺或扔之前不会再防御**；两支都回 `Alert`，反击这一支晚回来。
    - 结论：这两类的"反击会不会重置冷却"是**不会**（两支冷却相同），但两支用时不同，主角的命中也会改冷却（Minister）。行为表的历史条件目前按家族记（MI_PARRY、RE_DEFEND 两支同一个家族），要把**上一招的分支**（防御被打 → 反击 / 姿态自然结束）和**最近被主角打中**分开作候选条件（R5 冷却项），并按分支分别统计到下一次出招的时间。
- **飞行怪往斜下打（below.json）**：在空中承诺的攻击里，它自己的碰撞体（加上它扔出的投射物）碰到"站在承诺点正下方地面上的主角"的比例，对比前方 3 u / 6 u：Bellbearer 扔钟 1.7 % vs 10 % / 35 %；Maestro 斩 0 %；Tiny 冲撞 7.1 % vs 34 % / 58 %；Reed 刺 9.9 % vs 17 % / 25 %、扔针 6.4 % vs 15 % / 22 %：**这四类正下方明显更安全，成立**。但 **Minister 冲刺 30 % vs 30 % / 19 %、格挡反击 37 % vs 27 % / 13 %，Clawmaiden 斩 26 % vs 28 % / 12 %、旋转 + 矛 40 % vs 38 % / 32 %**：这两类会俯冲，正下方不比前方安全。
- **偷丝怪的距离与冲刺斩（clawmaiden_distance.json）**：它在两招之间飞的时候（67,383 个样本帧）离主角水平距离 p5 1.9、p50 8.0、p95 14.6 u，高出主角 p50 3.1 u，水平速度 p50 5.0 u/s（它的飞行上限，最大 12）。冲刺斩够距**估计** 7.0 u（冲刺 28 u/s × 0.1 s = 2.8 u + 收割者冲刺斩多边形前沿 4.16 u；冲刺斩自身的位移没建模【未核实，R1 测】）：38.7 % 的时间够得着，站着横砍（3.6 u）只有 10.7 %。它确实保持在比横砍远得多的距离，冲刺斩够得着的时间是横砍的 3.6 倍；中位 8.0 u 比估计的冲刺斩够距略远，"正好控制在冲刺斩距离"要等 R1 实测冲刺斩真实够距再定。
- **小铃铛（bells.json）**：`Throwing Bell` 的伤害框 parry 位在 135,712 帧里**全是 4（只有 counter，没有拼刀位）**：按导出它不会触发 NailClash；被钉子打中走的是自己的 `Nail Hit`（1,391 次），打中后 3 帧速度 p50 27.6 u/s（p95 32.4）：**可以打走，成立**（你说的"拼刀"在游戏里是这个改向，不是 NailClash 的弹反无敌）。下劈：主角在钟上方、下落中打中它 100 次，之后 10 帧内弹起（vy > 5 u/s）只有 8 次：**下劈大概率弹不起来，成立**。
- **Minister 的格挡（你 2026-10-08 问；你的两次练习 + R1 data2 录像）：** ① **格挡时不转身**：你的练习里 83 次 Parry Stance，16 次你绕到它身后，它一次都没转（flipX 不变）。② **格挡姿态里砍不伤它**：约 300 个 data2 录像文件里，它在 Parry Stance 时没有任何一次受伤的 hit；3,276 次 Parry Block 里 3,274 次没有对应的 hit 事件（被挡下）——随机策略各方向都砍过，所以绕后多半也破不了防（你的练习里 42 次格挡全是从前面或正下方砍的，没有身后的样本，未直接验证）。③ **能伤它的窗口**：Parry Stance Antic（0.13–0.15 s）、Parry Stance End（0.25 s）、以及**被挡之后的 Parry Block（0.583 s）**——这段里它照样掉血（同样本：AltSlash 204、Slash 81、UpSlash 46、飞针 271 次），然后才往前冲出反击那一刀。④ 触发反击之后 1.2 s 内主角被它打中：横砍 53 %、交替横砍 68 %、贴墙砍 83 %、上挑 18 %、下劈 0 / 8（反击是水平冲）。
- **Reed（拿针的飞怪）的防御（你：打法和 Minister 一样）：** Defend 1.016 s（p5 1.007、p95 1.032），中途被打 → Block 0.516 s（p5 0.500）→ `Parry Y Aim` → Parry Slash；之后 Multihit（钩住主角）729、Parry Slash End 428、Multihit Clashed（被拼掉）254。和 Minister 不同：**它的反击按主角的高度瞄（Parry Y Aim）**，所以从下面 / 上面触发并不安全（触发后 1.2 s 内被 Reed 打中：横砍 34 / 50、上挑 6 / 13、下劈 3 / 7、无 hit 事件的 841 / 1,358）；拼中一下整套取消（Multihit Clashed）。等防御结束（约 1.0 s）的打法照用。
- **打回去的钟变成主角的攻击（你 2026-10-08 问；R1 v2 的 data2 录像 217 个文件，按每次扔出（Init 起）分段）：** 钟的 Control 被打中走 Air → Tink L / R → Nail Hit → Air（或直接 Break）。7,284 次被打中的扔出里：之后**再也没打到主角** 7,127 次，没看到结束 21 次；记成"打中后打到主角"的 136 次**全部和 Nail Hit 同一帧**（钟碰到主角和刀砍到钟同帧：刀出得太晚，不是被打回去的钟又打人）。敌人身上 src = "Enemy Damager"（attack Generic）的命中 2,190 次，全部在某个钟被打中之后 2 s 内：被打回的钟会伤敌人（你看到的掉血）。所以规划器应该：钟一进 Nail Hit 就从危险区里拿掉（当作主角的投射物），并把"在它碰到身体之前砍中它"当作一种防御（和拼刀一样要早于接触）。
- **出招的距离边界（boundaries.json，给 R1 的诱招探针）**：每个家族被选中时主角的水平距离 p50 / p99 / 最大，以及最大值 ±1 u 内采到的决策数（选了它的 / 超出边界的）：Clawmaiden 斩 3.0 / 4.31 / 4.52（1,133：427 / 432）、旋转 10.7 / 10.9；Clapper 锤 6.7 / 8.46 / 8.76（19,359：1,131 / 3,528）；Envoy 斩 3.2 / 4.9 / 5.7；Choristor 斩 2.7 / 7.7 / 8.1、跳和鞭 p99 12.8；Minister 闪避 2.4 / 5.1 / 5.3、冲刺 p99 7.4（最大 16.8）、格挡 p99 7.4；Reed 闪避 p99 4.3、防御 p99 8.1；Bellbearer 闪避 p99 5.1。Maestro、Tiny 的招 p99 ≈ 29 u：与距离无关。最大值远大于 p99 的（Minister 冲刺、Clapper 跳 / 施法、Reed 各招）是少数远距离情形，诱招时以 p99 为边界。近战家族边界附近的样本已经很多（几千到上万次决策），远程家族边界附近的少（几十到一百）。

### 12.5 forum_simul 复现设计 H 的表 1.2

`forum_simul --run 20261003_074719_Forum_A_data --first 12`（同样的 12 场、609,481 帧）：按帧在场数 0–8 个的比例 2.31 / 22.33 / 32.23 / 19.06 / 12.43 / 2.65 / 0.64 / 2.08 / 6.28 %，与 H 表 1.2 逐项相同；每波在场 p50 / p95 / 最大、≥ 2 的比例、最常见组合、x 跨度、最近两只 < 3 u、6 u 内 ≥ 1 / ≥ 2 也一致（第 13 波 ≥ 2 是 84.7 % 对 H 的 82 %）。不同的三列是定义：每场秒数这里是游戏时间（dt 之和，H 是帧数 / 60，约低 5–8 %）；"两侧都有"这里含 12 u 边界（第 2 波 14.8 % 对 5 %，其余差 1–3 个百分点）；"全待机 / 混合 / 全承诺"这里把入场也算承诺（第 0 波 7 / 49 / 44 % 对 8 / 56 / 36 %）。

### 12.6 planner_bench --encounter Forum（脚手架）

规划器还没有多敌人预测（R2），所以这里只测"支撑阶段"在真实 Forum 走法上的代价：每 tick 把所有敌人的支撑放置（召回同一套走法，视野 0.8 s；视野内才开始的攻击每 0.2 s 一个锚点）装进一个 `SupportQuery`，再查 400 条 × 36 步的弹道候选（主角位置出发的扇形，不是规划器的候选）。`074719` i3 ep0 前 3,000 帧（第 0–1 波），4 线程，训练折 0 的表 + 余量：**每 tick 放置 p50 28,506、p99 38,391；放置 20 ms / 422 ms，查询 133 / 199 ms，整 tick 154 / 574 ms（p50 / p99）**；400 条候选在每一 tick 都全部碰到支撑。也就是说把召回的走法原样搬进规划器，比 R3 的 9 ms 预算慢约 20 倍、而且会永远 FORCED_RISK：R2 需要（1）停留区间宽的状态用"时间上预先膨胀"的模板一次放置（不是每 1/60 s 一个），（2）视野内才开始的攻击用按速度膨胀的锚点模板（不是每帧一个锚点 × 两个镜像），（3）两招之间的身体按当前位置重新锚定（IDLE 家族从待机开始算的模板太宽：`forum_simul` 的预测统计在一场上（单场建的表、样本内、无余量），主角站着不动时 +0 s 就有 76 % 的帧在支撑里）。修复轮加了 `--idle-growth`（待机身体管代替待机模板，同一场同一段）：每 tick 放置 p50 28,172、p99 37,827（几乎没变：大头是视野内才开始的攻击在每 0.2 s 外推锚点 × 两镜像上的放置，不是待机模板），整 tick 100 / 323 ms（p50 / p99；机器负载不同，不可直接比），候选仍然每 tick 全部碰到支撑。所以待机身体管解决的是"支撑空泛"，不是代价；（1）（2）仍是 R2 的主要工作。

### 12.7 复现

```
cd brain   # 低优先级、NUMBA_NUM_THREADS=4，一次一个
..\scripts\uv.cmd run python -m ssbot.tools.behaviour_build <7 个运行> --encounter Forum --allow-failed-validation --extra C:\ssbot\data\m2_forum_r0\build_all\extra --fights-list C:\ssbot\data\m2_forum_r0\build_all\fights.json
..\scripts\uv.cmd run python -m ssbot.tools.forum_extract --fights-list C:\ssbot\data\m2_forum_r0\build_all\fights.json --out C:\ssbot\data\m2_forum_r0\cache
# 开发（三份不相交 + 待机身体管；--margins none 是不要余量的对照）
..\scripts\uv.cmd run python -m ssbot.tools.support_recall --encounter Forum --extra C:\ssbot\data\m2_forum_r0\build_all\extra --cache C:\ssbot\data\m2_forum_r0\cache --margins heldout --margin-q 1.0 --family-wide --split 3way --json C:\ssbot\data\m2_forum_r0\recall_dev3.json
# 新数据：构建之后关闭的场（不在 fights.json 里的）→ 只扫接触 → 缓存 → 认证（配置先冻结）
..\scripts\uv.cmd run python -m ssbot.tools.behaviour_build C:\ssbot\data\runs\m2\20261003_074533_Forum_A_data C:\ssbot\data\runs\m2\20261003_074719_Forum_A_data --encounter Forum --report-only --exclude-fights C:\ssbot\data\m2_forum_r0\build_all\fights.json --fights-list C:\ssbot\data\m2_forum_r0\fresh\fights.json --contacts-only C:\ssbot\data\m2_forum_r0\fresh
..\scripts\uv.cmd run python -m ssbot.tools.forum_extract --fights-list C:\ssbot\data\m2_forum_r0\fresh\fights.json --out C:\ssbot\data\m2_forum_r0\cache_fresh
..\scripts\uv.cmd run python -m ssbot.tools.support_recall --encounter Forum --extra C:\ssbot\data\m2_forum_r0\build_all\extra --cache C:\ssbot\data\m2_forum_r0\cache --margins heldout --margin-q 1.0 --family-wide --fresh C:\ssbot\data\m2_forum_r0\fresh --fresh-cache C:\ssbot\data\m2_forum_r0\cache_fresh --area --write-margins ..\knowledge\1.0.30000\enemies\forum\support_margins.json --dev-json C:\ssbot\data\m2_forum_r0\recall_dev3.json --json C:\ssbot\data\m2_forum_r0\recall_fresh.json
..\scripts\uv.cmd run python -m ssbot.tools.forum_products --cache C:\ssbot\data\m2_forum_r0\cache
..\scripts\uv.cmd run python -m ssbot.tools.planner_bench --encounter Forum --cache C:\ssbot\data\m2_forum_r0\cache --extra C:\ssbot\data\m2_forum_r0\build_all\extra --fight 20261003_074719_Forum_A_data/i3/ep0 --frames 3000 --idle-growth ..\knowledge\1.0.30000\enemies\forum\support_margins.json
..\scripts\uv.cmd run python -m ssbot.tools.forum_simul --cache C:\ssbot\data\m2_forum_r0\cache --run 20261003_074719_Forum_A_data --first 12

## 13. R1：波次起点、定点采集 v2、爬墙、加速检查（2026-10-04，forum_planner_plan.md §5 R1；实例 2、3，fo_A，oracle）

代码在分支 `worktree-wf_6dcc3810-3d5-1`（首轮 35737e8，修复轮 8a03afb / 505987c）。探针结果 JSON 在 `C:\ssbot\sandbox\forum_r1\`（`ssbot.probes.forum_r1`）。下面的运行：首轮冻结代码 1c374f8 的 `20261004_111158_Forum_A_w0_data2_envoy`（Envoy 专场 106 局，1.56 h 战斗时间）和 `20261004_111158_Forum_A_w2_mix_data2`（波次起点 36 局，1.71 h），修复轮 13:00 把它们停下（为了改代码）；修复轮的长跑见 13.4。

### 13.1 从第 i 波开始（R1 ①）

- **DebugMod 战斗中存档可以用**（计划 §1 第 12 条以为读档会回到开战前）。DebugMod 存档时如果房间里有已开始的 BattleScene，会写 `roomSpecificOptions = "BattleScene|Battle Scene|<currentWave>"`（`REF\Silksong.DebugMod\SaveStates\RoomSpecific.cs`）；读档时先把 `currentWave` 设回去再调 `StartBattle`，并用 Harmony 转译把 `DoStartBattle` 里的 `StartWave(0)` 改成 `StartWave(currentWave)`。`Start Range` 的 PersistentBoolItem 已触发，所以读档后没有吼叫过场。
- 存档 `fo_r1_w0` … `fo_r1_w13`（`C:\ssbot\sandbox\savestates\`）：w1–w13 由一次从 fo_A 开始的策略跳波顺路存下（`wave_start.make_wave_states`：每到新的一波先把 PlayerData 改回、松开按键再存；14 个存档核对 nailUpgrades 1、isInvincible False、7 面具、丝 1）；w0 是开战 2 s 后存的。读档核对（`forum_r1 check`，11:01 和修复轮 13:03）：每个存档都从第 i 波重开，这一波的成员全部出现。
- **"第 i 波开始"要分两个时刻**：读档返回后约 1.2 s（`battleStartPause` 0.75 s 加读档）room.battles 就报告"已开始、第 i 波"（DebugMod 在 StartBattle 之前设了 currentWave），这时 `currentEnemies` 还是 0、成员还没激活；成员在 `StartWave` 的 `startDelay(i)` 之后才激活（`BattleWave.WaveStarted` 把它们数进 currentEnemies）。实测激活比"开始"晚：w1 1.0 s、w2 1.017 s、w4 1.017 s、w8 3.017 s（13:03 check）。修复轮起，波次起点的开场（`encounters.forum_wave_intro`）等到 currentEnemies > 0 的第一帧，把 tap 的开战帧（AttemptRecord `f_wake`、`gauntlet.waves[0]`）移到那里（`GauntletTap.rebase_start`），开场记录里有 `battle_start_f`、`active_f`、`activation_s`；所以修复轮的波次时间和完整连战同义。**首轮的 R1 记录（1c374f8）里波次时间从"开始"算，比激活早 0–3 s。**
- **助战**：w1 读档后 Garmond 照样进场（第 1 波自己的 WAVE START 发 `CALL ALLY`，§4；13:03 check 结束时 Garmond 在 `Skid`，首轮核对里是 `Intro Roar`）；w2–w13 读档 12 / 12 次 Garmond 一直 `Dormant`，所以从第 2 波起是"无助战"的起点。（首轮写的"从第 1 波起 13 / 13 不来"是错的。）
- **前面几波没跑过的成员还挂在波次物体下面（"幽灵子物体"）**：读档后第 0…i−1 波从没开始，它们的成员仍是各自 BattleWave 的子物体。`BattleScene.DoCheckEnemiesNew` 按第 0…currentWave 波的 `transform.childCount` 之和判断是否进下一波，所以整场都偏大：
  - 重叠波次（remainingEnemyToEnd > 0）不会按 1 s 计数进下一波。第 2 波（Bellbearer + Reed，to_next 2）自然连战里 1.6 s 后第 3 波就开始（策略跳波实测）；**从 w2 读档，第 3 波要等到第 2 波死一个才开始**：13:03 check 看了 10 s 一直 enemies 2 / to_next 2；首轮运行里 3 局 w2 分别在 59.7、75.05、65.95 s 才开始第 3 波（有人被杀，DecrementEnemy 2→1 ≤ 2）。这段时间是自然连战里没有的 Bellbearer + Reed 单独组合。首轮写的"要自然组合就从前一波读（w2 → 1.5 s 后第 3 波）"是错的；w4、w9 读档的"第一个击杀后进下一波"与自然的一致（核对者）。
  - 潜在的卡死：重叠波次里两只成员在下一波的 startDelay 之内先后死掉时，`WaveEnd` 会把下一波 `StartWave` 两次（w1 存档里 2 个成员 currentEnemies 是 4），自然连战靠计数检查纠正；读档后幽灵子物体挡住纠正，可能一直卡到 180 s 时间盒。首轮 23 局（核对者）没见到。
  - 修复：oracle 新 RPC **`battle.prune`**（8a03afb，`-p:Deploy=false` 构建，**未部署**）：在波次起点读档后、第 i 波还没有人死之前，把第 0…i−1 波里带 HealthManager 的子物体先脱离父物体再销毁，计数检查就和自然连战在第 i 波时一样（HealthManager 只在 Die 时通知 BattleScene，销毁不会触发 DecrementEnemy）。开场在激活前调用；部署的 oracle 回 `unknown rpc`，记录里写 `ghosts: "unpruned"`。部署后核对：w2 读档后第 3 波应在约 1.5 s 后开始（HANDOFF R1 Next）。
  - 在部署前：w2 移出轮换；首轮 3 局 w2 的清单在 `C:\ssbot\data\runs\m2\20261004_111158_Forum_A_w2_mix_data2\exclude_w2_ghosts.json`（`behaviour_build --exclude-fights`）。其他波次起点：从 w3 读档只有 Clawmaiden（自然的第 3 波开始时通常还有 Bellbearer + Reed），第 4、9 波同理，重叠的组合要等 battle.prune 部署后从前一波读。
- 敌人的 HP、位置都是新生成的；主角位置是存档时的位置（w11–w13 在右墙边 x 48.7），HP / 丝在数据模式下由 randomize_start 重新随机。
- **策略跳波**（部署的 oracle 就能用）：通过 debug line server 把 `isInvincible` 置真、`nailUpgrades` 4（钉子伤害 21）、丝保持 9（丝矛），`WaveSkipPolicy` 去砍在场的波次成员，BattleScene 按自己的规则推进（助战照常进场）。实测一次跳到第 13 波：第 0–5 波共 37 s 游戏时间，**两只 Maestro 的第 6 波 353 s**，第 7 波 13 s，第 12 波（Maestro + Reed）181 s，总计 716 s（飞着的 Maestro 打不到）。所以只在前几波有用；实际采集用存档。
- **oracle RPC `battle.wave {wave}`**（06a7c2b，未部署）：对第 0…currentWave 波的活成员调 `HealthManager.Die`（Generic，和 DebugMod 的 kill all 同一调用），BattleScene 按自己的规则推进（startDelay、1 s 数子物体、第 1 波的 Call Ally 照常），到 `currentWave == wave` 时回复。部署后要核对（HANDOFF R1 Next）。
- 用法：Encounter `Forum_A_w<i>`（开场见上；时间盒 180 s），`combat_run --encounter` 接受逗号分隔的列表、按局轮换。**只用于采集和以后的课程；门槛仍是完整连战。**

### 13.2 三招从没出现：结构上不可达（R1 ③）

PlayMaker 的 `SendEvent`（delay < 0.001、目标 Self）在 OnEnter 里直接 `Fsm.Event` → `ProcessEvent`，状态一切换，`FsmState.ActivateActions` 就返回，这个状态后面的动作不再执行（反编译 PlayMaker `FsmState.cs` 293 行、`Fsm.cs` 2425 行，`HutongGames.PlayMaker.Actions/SendEvent.cs`）。场景包里每个动作的启用位（`actionEnabled`，UnityPy 读 `hang_04_boss.bundle`）：

- **Envoy `HopSlash Antic`**：`Hop Up?` 的动作依次是 CheckHeroPerformanceRegion、StopWalker、SetVelocity2d、**SendEvent FINISHED（启用）**、FaceObjectV2、RayCast2dV2（TERRAIN，前方 3 u，命中发 `HOP UP`）。FINISHED 先到 → `Slash Antic`；射线永远不跑。**不可达**。
- **Bellbearer `Throw Antic Quick`**：`Rethrow?` 的动作是 **SendEvent FINISHED（启用）**、SendRandomEventV4（FINISHED 0.7 / ATTACK 0.3）。永远回 `In Range`。**不可达**。
- **Maestro `Point Start`**：`Attack Choice` 里的 `SendEvent POINT` 是**禁用**的（actionEnabled false），别的分支只有 FIRE / DEFEND / SING；`Point Start` 自己也没有出边。**不可达**。
- **Envoy 入场（EN_ENTRY：Wake Pause / Wake / Black Thread Wake）**：Forum 的 Envoy 默认动画片段是 `Ambush`，`Init` → `Ambush Ready` →（BATTLE START）`Ambush Antic`：它的入场就是伏击（EN_AMBUSH，每场一次）。Wake 系列属于睡眠变体，Forum 里不出现。
- 实测（首轮两个运行，修复轮的审计）：Envoy `Hop Up?` 2407 次，下一状态 2407 次都是 `Slash Antic`（其中 294 次 Envoy 离主角一侧的墙不到 3 u），停留 0.0 s；Bellbearer `Rethrow?` 910 次全部回 `In Range`；Maestro `Attack Choice` 794 次：Fire 556、Defend 238、Point 0。
- 所以这三招和 Envoy 的 Wake 入场不需要采集；行为表应把它们当作结构上不存在（不影响支撑）。

### 13.3 爬墙到左墙顶（Wall Scramble，你的方法）

- 控制器 `ssbot.train.climb.WallClimber`：跑向左墙，离墙面 2.6 u 内跳；一贴上墙（wallSliding / wallClinging）就一直按住左，按住冲刺约 0.25 s 爬一次（按住冲刺爬得更高），松开再按；到 y ≥ 13.3 且贴住就停在那里（口袋），低于 13.15 再爬一次（撞顶后 Detach 有时在 12.9 重新抓墙）。
- 探针（`forum_r1 climb`，第 0 波实战中）：**27 / 27 到顶**（无敌 12 次、不无敌 15 次，后者每次挨 0–3 下），每次 2–6 次冲刺（中位 3），到顶 1.6–5.5 s 游戏时间（中位约 2.9 s），最后贴墙高度 y 13.20–13.66（口袋 13.45–13.60）。之前的蹬墙跳方法 5621 帧贴墙里只有 145 帧到顶（§10.3）。
- 数据策略的 CLIMB 段（首轮波次运行 36 局）：220 段里 61 段开始时主角**已经贴在顶上**（上一段 CLIMB 刚到顶就又抽到 CLIMB），不算爬墙；**真正的爬墙 159 次，144 次到顶（91 %）**，到顶 p50 2.39 s、p95 5.3 s 游戏时间；另 15 次到段结束还没到顶。（首轮写的 101 / 106、p50 1.5 s 把已在顶上的段也算进去了。）修复轮起每段记 `start_top`，审计的 `climbs_real` 按它（旧记录按到顶 < 0.2 s）去掉。

### 13.4 定点采集策略 v2 与长跑（R1 ②⑤）

- 策略 `ssbot.train.forum_policy.ForumDataPolicyV2`（combat_run `--policy data2`；`data2_envoy` 不打 HP ≤ 20 的 Envoy）：每段选一个战术：PRESS、KEEP（3–10 u）、**BAIT**（目标类型某个与距离有关的家族的选择边界：R0 boundaries.json 的最大选择距离或 p99，±1.2 u，偶尔跨过边界）、**DASH_IN**（3–9 u 外冲刺、冲刺中出刀）、**CLAW_IN**（同高度 3–12 u 放飞针）、**UNDER**（站在飞行怪正下方，偶尔上砍）、**JUMP_OVER**（跳过地面怪，在上方偶尔下劈）、**WALL_BAIT**（背靠墙等地面怪过来）、**CLASH**（在出刀距离等着，可拼刀的伤害框或 Throwing Bell 进入横砍框时出刀；有铃时先打铃）、**CLIMB**（13.3 的爬墙器，到顶后贴住，偶尔贴墙横斩）、EVADE。审计 `ssbot.tools.forum_r1_audit`。
- 修复轮的改动（8a03afb）：
  - **保护漏了**：首轮 Envoy 专场 106 局里，HP ≤ 20 的 Envoy 被主角打中 69 次（49 局，39 次 / 小时；下劈 52、横斩 17），5 局被打死（第 8、19、36、63、64 局；第 64 局因此进了第 1 波、Garmond 进场）。原因：保护只看当前位置，冲刺（28 u/s）或下落中按下的刀落在 5 u 外判断"安全"，冲过去 / 掉下去才打中；下劈时主角在 Envoy 上方 3.5 u 以外也算安全。现在按主角速度把接下来 0.35 s 的路径都算进去（2 帧动作延迟 + 出刀），下劈时路径下方 3 u 内有受保护的怪就不劈。**核对**（修复轮专场 `20261004_131323_Forum_A_w0_data2_envoy`，23 局 0.38 h，加冒烟 4 局）：Envoy 每局都被打两下到 20 HP（46 次），之后 **0 次**再被打中、0 次被打死；首轮同口径是 106 局里 49 局有、共 69 次（按首轮的速率 0.38 h 应有约 15 次）。
  - 每帧的随机按"每游戏秒的风险"折算（`_chance`：60 Hz 下写的概率 p 在每个 STATE 用 1−(1−p)^(dt·60)），按键后的休息时间也按游戏秒；所以策略每游戏秒的决策不随倍速变（仍会变的只有动作延迟：2 帧在 1x 是 1/30 s、在 2x 是 1/15 s，见 13.5）。
  - 只剩 Clapper 时贴墙的份额从 0.85 降到 0.5（首轮 w7 / w13 有 62 % / 60 % 的时间在口袋里，Clapper 在地面的决策反而少：13.8）。
  - 每段记 `[帧, 战术, 目标类型, 口袋, 保护中]`（AttemptRecord `policy.segments`），`policy.protect_hp`；`IdlePolicy`（`--policy idle`，完全不按键，13.5 用）。
- **与 R0 同口径的边界附近取样**（审计 `boundary_r0`：只数决策状态的出边，主角 x 到敌人 transform x，R0 boundaries.json 的 boundary_u ±1 u；R0 = 107 场 25.4 h）。首轮写的"3–47 倍"把任何进入攻击开始状态的都算了（Clawmaiden 斩 234 次里 155 次不是从决策状态来的），也没按决策算比例，作废。同口径：

| 家族（R0 边界） | R1 运行 | 边界 ±1 u 内的决策 / h（R0） | 其中选中 / h（R0） | 选中比例（R0） |
|---|---|---|---|---|
| Envoy 普通斩（5.68 u） | Envoy 专场 | 1011（25.2） | 233（5.75） | 0.23（0.228） |
| Choristor 斩（8.05 u） | Envoy 专场 | 4369（445） | 34.7（3.46） | 0.008（0.008） |
| Choristor 鞭（13.03 u） | Envoy 专场 | 867（157） | 20.5（3.43） | 0.024（0.022） |
| Choristor 跳（13.1 u） | Envoy 专场 | 850（157） | 4.5（1.77） | 0.005（0.011） |
| Clawmaiden 斩（4.52 u） | 波次 | 77（44.6） | 24.6（16.8） | 0.32（0.38） |
| Clawmaiden 旋转（10.92 u） | 波次 | 25.8（32.4） | 15.3（15.3） | 0.59（0.47） |
| Minister 闪避（5.33 u） | 波次 | 408（186） | 12.9（5.1） | 0.032（0.028） |
| Clapper 锤（8.76 u） | 波次 | 521（762） | 16.4（44.5） | 0.032（0.058） |

  - 选中比例和 R0 一样（这是敌人的性质）；每小时的增益来自**专场把 Envoy 一直留着**、BAIT 把主角放在边界附近（Envoy 普通斩的 BAIT 样本 43,059 帧），和波次起点把时间集中在少数敌人上：Envoy / Choristor 6–40 倍，Clawmaiden 斩 1.5 倍、Minister 闪避 2.5 倍，Clapper 锤反而只有 R0 的 0.37 倍（口袋）。远距离家族（边界 > 15 u）在 R1 里很少碰到边界（Bellbearer、Maestro、Tiny 每小时与 R0 相近）。
- 家族计数（首轮两个运行）：Envoy 专场 EN_SLASH 2407、EN_JUMPSLASH 946、EN_CHARGE 327、**EN_AMBUSH 106（每局一次）**；Choristor 斩 / 鞭 / 跳 1166 / 704 / 476；Reed 刺 / 扔 / 防御 / 闪避 1212 / 1412 / 713 / 615。波次 36 局：Clawmaiden 斩 / 旋转 / 瞬移 312 / 287 / 23；Minister 冲刺 / 格挡 / 闪避 383 / 800 / 307；Clapper 施法 / 跳 / 锤 / 后撤 / 跳施法 209 / 172 / 107 / 339 / 169；Bellbearer 扔 / 闪避 919 / 318；Maestro 斩 / 防御 / 召唤 556 / 238 / 33；Tiny 防御 / 开火 711 / 555。Envoy 的每个家族都已 ≥ 200（伏击 R0 107 + 106 = 213）；HopSlash 和 Wake 入场不可达（13.2）。
- 长跑：修复轮 13:13 起（冻结代码 `C:\ssbot\live_fo_r1f_8a03afb`；实例 2 先跑 40 局受保护的 Envoy 专场核对保护，再跑波次起点；实例 3 波次起点；轮换 w4、w6、w7、w8、w9、w11、w12、w13、w3、w5、w10，每局 180 s），13:36 `DEMO_SOON`（你要 0.5x 练 Forum）后两个运行各在当前一局后停下：实例 2 专场 23 局、实例 3 波次 8 局（`20261004_131323_Forum_A_w4_mix_data2`）。演示后用 `C:\ssbot\sandboxo_r1f_run.cmd i2w` / `i3` 重新开始（HANDOFF R1）。

### 13.5 加速检查（R1 ④）：**没有跑成，2x 不采用**

- 部署的 `time.scale` 不能加速：`TimeManager.UpdateTimeScale` 在 `CheatManager.IsCheatsEnabled`（发行版里是常量 false，`CheatManager.cs` 215 行）时把所有控制的乘积截到 1。实测：scale 2 → `Time.timeScale` 1（0.5 正常）。DebugMod 的加速之所以能用，是它自己在 UpdateTimeScale 前后 Harmony 补丁了 IsCheatsEnabled，并用 IL 钩子让 `FreezeMoment` / `SetTimeScale` 协程的实时等待按倍速缩短（`REF\Silksong.DebugMod\MonoBehaviours\TimeScale.cs`）。修正在 06a7c2b（未部署）：`time.scale` > 1 走 DebugMod 的 `TimeScale.CustomTimeScale`。
- **首轮的比较工具会把逻辑完全相同的 2x 判成不同**（核对者）：停留时间按帧计（1x 1/60 s、2x 1/30 s），只把 1x 的样本粗化到 1/30 s 就有 155 / 270 个键 p < 0.05（KS 到 1.0）；每帧速度在两种帧长下对 0.02 s 物理步的混叠不同；判据"p < 0.05 的键占比 ≤ 10 %"对 9 个家族键在 1x 对 1x 时就判不同，又放过只影响少数键的真差别。
- 修复轮的 `ssbot.tools.forum_speed_check`（505987c）：
  - **停留时间放到两臂中较粗的帧格上，按整数格比较**：n = round(t / 本臂名义帧)（STATE dt 在 0.01665–0.01668 s 抖动，名义帧取 1/60 s × 倍速），格 = ceil(n / k)（ceil(ceil(x)/k) = ceil(x/k)：D 秒的计时器在两臂落在同一格；用浮点值会差一个 ulp，KS 仍是 1）。
  - **速度按 0.2 s 游戏时间的窗口**（同一状态内），两臂的实体都按较粗一臂的帧读（细的一臂每 k 个 STATE 读一次）：窗口从状态内第一帧开始，帧长不同时短而不匀的动作（闪避）会被截到不同部分（不这样做时模拟 2x 的每个 Evade 键都是 p 0.0002）。
  - **选择按（类型, 主角 |dx| 段 0/3/6/10 u）**，不再按类型无条件比较。
  - **判据**：每个键按场置换（两臂的场混在一起重分），p < 0.05 的键再扩到 max(5000, 2 × 键数 / 0.05) 次置换；一个指标"一致"要求 Holm（族错误率 0.05）下没有显著键，且 p < 0.05 的键数不超过 Binomial(键数, 0.05) 的 99 % 分位（270 键 22、9 键 2）；最小可达 p 大于 0.05 / 键数时标 underpowered（至少 8 + 8 场）。伤害框外沿仍按"两半之间的噪声"比较（超过 2 倍噪声且 > 0.1 u 的键 ≤ 5 %）。
  - `--simulate-b K`：把 B 臂当作 K 倍速录的（每 K 个 STATE 读一次、停留时间放到 K 帧格上），用来校准检查本身。
- 校准（074533 对 074719 两个旧 1x 数据运行，各 8 场）：

| 比较 | 停留（270 键） | 速度 | 选择 | 伤害框外沿 | Holm 显著 |
|---|---|---|---|---|---|
| 1x 对 1x，只看事件 | 7 / 270 | — | 1 / 9（按类型） | — | 0 |
| 1x 对模拟 2x，只看事件 | 10 / 270（不放帧格：136；核对者用首轮工具：155） | — | 1 / 9 | — | 0 |
| 1x 对 1x，含实体 | 7 / 270 | 6 / 114 | 0 / 37 | 0.4 % of 256 | 0 |
| 1x 对模拟 2x，含实体 | 10 / 270 | 5 / 112（各臂按自己帧读：60 / 112，Holm 36） | 0 / 39 | 0.4 % of 241 | 0 |

  Clapper 跳的高度中位 8.219 u、滞空 0.917 s（1x 对 1x）和 8.219 u、0.933 s（模拟 2x，两臂都按 1/30 s 读）都是两边相同。所以修复后的工具对"逻辑相同、帧长不同"判一致，对 1x 对 1x 也判一致；单元测试里一个键平移 0.6 s 时 Holm 只抓到那一个键。
- 2x 的检查要在部署后跑（HANDOFF R1 Next）：先用 `--policy idle`（不按键，排除动作延迟这个混杂），再用 data2；同一组种子（`--same-seeds`）一个实例 2x、另一个 1x，各至少 8 场。即使通过，2x 每个实例只落在一半的 1/60 s 状态时间格上，支撑模板要另外核对。

### 13.6 你的几条说法的核对（R1 数据，首轮两个运行）

- **飞针（Clawline）撞上怪不伤主角：不完全成立**。波次运行 203 次飞针，75 次 `Harpoon` 打中怪；其中 **5 次在打中后 0.5 s 内被同一类怪打中**；按"离主角最近的那只同类怪是不是被钩中的那只"匹配，5 次都是被钩中的那只（不算停放的 Tiny）。飞针冲刺中主角不是无敌的，拉到怪身上时身体接触照样算；你的录像 34 次飞针、437 次受击里 0 次发生在 Harpoon 动画里：人多半在怪不出招、身体可以穿的时候用。规划器要把飞针终点当作"贴在怪身体上"做支撑检查。
- **飞行怪往斜下打，站正下方安全**（主角站地、在它正下方 |dx| < 0.75 u 对 1.5–6 u 的附近；只算该类的命中；期望值 = 附近的命中率 × 正下方的时间，P = Poisson P(X ≤ 实际)）：**Bellbearer 正下方 51.8 s 0 次，期望 4.08，P = 0.017：成立**；Minister 36.7 s 0 次，期望 0.85，P = 0.43：没有证据；Reed 两个运行合计正下方 132 s 6 次，期望约 6.9：**不更安全**（**2026-10-05 更正**：这里"只算该类的命中"是按类型算的，两只 Reed 同时在场时另一只的命中也算进来了，所以不能说明头顶那只；按个体、只算它自己的判定的 R0 回放（上面 below.json 那条）是 Reed 刺正下方 9.9 % 对前方 3 u / 6 u 的 17 % / 25 %、扔针 6.4 % 对 15 % / 22 %：**站在头顶那只 Reed 正下方对它本身更安全**，另一只要单独躲）；Tiny 218 s 44 次，期望 50.8，P = 0.19：差不多；Maestro 两边都是 0。
- **小铃铛可以打走**：策略对着铃出刀 289 次（CLASH 段的计数）；铃的 FSM 进 `Nail Hit`（改向）109 次、`Tink L/R/U` 105 次——这两组数来自不同的出刀（Nail Hit 里也有别的战术的刀），首轮写的"171 次出刀 61 次改向"把两者相除，作废。修复轮的记录有 CLASH 段的帧，可以按段算改向率。
- **拼刀**（按对方的招，NailClashEffect）：Envoy 专场 Envoy 普通斩 95、Choristor 跳 51、Envoy 冲锋 42、Choristor 斩 41、Envoy 跳斩 20、Reed 防御反击 18、Reed 刺 17、Choristor 鞭 15；波次：**Minister 冲刺 76**、Minister 格挡反击 11、Clawmaiden 斩 11、Reed 刺 6、Reed 防御反击 5。
- **口袋（只剩 Clapper 时贴在左墙顶）**：w7 / w13 在口袋 1232 s；这期间 Clapper 开始的招：跳 127、跳施法 121、施法 117、后撤 117，**锤 0**（与 §10.2 一致）；**口袋里来自 Clapper 的受击 0**（口袋里的 46 次受击全来自别的波次的怪）。

### 13.7 复现

```
cd brain
..\scripts\uv.cmd run python -m ssbot.probes.forum_r1 states --instance 2            # fo_r1_w1..w13
..\scripts\uv.cmd run python -m ssbot.probes.forum_r1 check --instance 2 --waves 1,2,4,8 --seconds 10
..\scripts\uv.cmd run python -m ssbot.probes.forum_r1 climb --instance 3 --repeat 15 --timeout 10
..\scripts\uv.cmd run python -m ssbot.probes.forum_r1 fsmgraph --instance 2 --savestate fo_r1_w0    # w0, w2, w3, w4, w7
..\scripts\uv.cmd run python -m ssbot.tools.forum_r1_audit <run dir> --json <out>
..\scripts\uv.cmd run python -m ssbot.tools.forum_speed_check --a <1x runs> --b <2x runs> --json <out>
..\scripts\uv.cmd run python -m ssbot.tools.forum_speed_check --a C:\ssbot\data\runs\m2\20261003_074533_Forum_A_data --b C:\ssbot\data\runs\m2\20261003_074719_Forum_A_data --max-fights 8 --simulate-b 2
```

### 13.8 R1 数据进行为表之前（核对者的高优先级意见）

R1 的记录里有策略造出来的条件，R0 的协变量（|dx| 段、左右、主角 x 三段、历史）分不出来：

- **口袋改变 Clapper 的决策**（首轮波次运行，审计 `clapper_dec`，主角在口袋 / 地面 / 空中 × |dx| 段）：`Idle` 在 3–10 u：口袋 494 次里 Evade Scuttle 0、Dmg Attack 0（只有 Walk / Avoid Type），地面 237 次里 Evade 78、Dmg Attack 5；`Avoid Type` 在 6–10 u：口袋 Evade 90 / 130，地面 19 / 53；`Walk` 在口袋里总是去 `Far Range`，地面 3–10 u 大多 `Close Range`。（Dmg Attack 是 Idle 的 TOOK DAMAGE 出边，口袋里主角很少打到它，所以一部分是"没挨打"。）R0 的表把这些行算进主角 x 西三分之一的地面格子。
- 修复（8a03afb）：
  - Forum 的规格加了候选协变量 **`hero_height`**（主角离地高度段：< 1 u、1–5 u、≥ 5 u；左墙顶口袋在最高段），和别的协变量一样做 Holm 检验和留出对数损失；Bell Beast 不加（表不变）。在首轮 9 场 Clapper 波次起点上试建：Clapper 的 `Idle`（和距离一起）、`Walk` 都把它选为条件。
  - **受保护的类型**：`knowledge/1.0.30000/enemies/forum/hero_caused.json`（13:02 在实例 2 上用 fsm.graph 读的 9 类控制 FSM）列出每类有"主角打中才走"的出边的状态（TOOK DAMAGE、BLOCKED HIT、CANCEL MULTI HIT；Envoy：Walker → Leader?、Charge → Reset、Sleep、Wake、Start Praying）。AttemptRecord `policy.protect` 里列出的类型，在那一场里 HP ≤ `protect_hp` 时从这些状态出去的决策、以及这些状态的停留时间都不进表（GauntletBuilder 计数器 `protected <type>: ... dropped`）。首轮的 Envoy 专场记录有 `protect`，默认 protect_hp 20。
  - 出处：`run_fights` 的 Fight.info 带 `unit`、`protect`、`protect_hp`、`segments`（修复轮起每段的战术），以后可以按战术分层或去掉。
  - w2 的 3 局见 13.1 的排除清单。
- 首轮 Envoy 专场在 R1 里占 Envoy 数据的绝大多数（普通斩 2407 次 / 1.56 h，R0 692 次 / 25.4 h）；重建表时应保留 R1 来源，能做"去掉 R1"的消融。

### 13.9 R1 收尾：部署后的核对（2026-10-04 14:45–15:05，实例 2、3；oracle = main 56845a9，`SsOracle.dll` md5 11E34633…，训练副本 14:37 部署）

代码在分支 `worktree-wf_5031b357-209-2`（收尾轮）。探针结果 JSON 在 `C:\ssbot\sandbox\forum_r1\`（`hello_i2_144523`、`hello_i3_144532`、`check_i2_144745` / `144950`、`skip_i2_145059` / `145135`）。

- **HELLO**（新探针 `forum_r1 hello`）：两个实例都报 plugin 0.1.0、game 1.0.30000、schema 1，RPC 表里有 `battle.prune`、`battle.wave`、`time.scale`、`fsm.graph`。
- **`time.scale` 2**：回复 `time_scale` 2.0、`via` debugmod；之后 90 个 STATE 的 dt 中位 0.0333 s（2 × 0.01665），回 1 后 dt 中位 0.01668 s。两个实例相同。（换场景读档的那一帧 dt 为 0。）
- **`battle.prune`**（`forum_r1 check --waves 2,3,4,9,10`）：每个存档读回后剪掉前面各波没跑过的成员：w2 5 个（子物体数 [3, 2, 2] → [0, 0, 2]）、w3 7、w4 8、w9 17、w10 20，`kept` 都是空的。**w2 读档后第 3 波在激活后约 1.5 s 开始**（探针 4 次读档按"帧数 / 60"记为 1.533、1.533、1.517、1.517 s：读档后头一两秒的帧 dt 偏大（下一条），所以这几个数偏小、不是游戏时间；按 STATE dt 之和量的只有下面长跑第一局，1.565 s 游戏时间），和自然连战（1 s 计数检查 + 第 3 波 0.5 s startDelay）一样；修复前要等第 2 波死一个（59.7–75 s）。w4（enemies 2 / to_next 1）、w9（3 / 2）在 10 s 内没人死就一直停在本波，是重叠波"死一只才放下一波"的规则；w3、w10 只有 Clawmaiden，和 13.1 一致。
- **读档后的头几帧 dt 很大**：长跑第一局（`20261004_155649_Forum_A_w2_mix_data2` ep0）从"开始"到激活 31 帧、游戏时间 1.032 s，激活到第 3 波 47 帧、1.565 s；按"帧数 / 60"记的波次时间（AttemptRecord `gauntlet.waves[].t`、开场的 `activation_s`）在读档后第一两秒偏小，要按 STATE dt 之和算。
- **`battle.wave`**（`forum_r1 skip --method oracle`，从 fo_A 开战）：**跳到第 6 波（两只 Maestro）5.06 s 实时、跳到第 13 波 16.73 s**（策略跳波：第 6 波 353 s、到第 13 波 716 s）。Garmond：跳到第 6 波时还是 `Dormant`（第 1 波开始后 4 s 才叫他，跳得比这快），之后 1 s 内 `Enter Fall` → `Intro Roar` → `Idle` → `Chase Target`，第 8 s 已在 `Wildslash Antic`；跳到第 13 波时他已在场（`No Target Idle`，(34.0, 5.72)）。所以 oracle 跳波保留第 1 波的叫助战，只是时间压缩了。**注意**：跳过的战斗里 BattleScene 自己的 `currentEnemies` 偏大（第 6 波 2 → 10，第 13 波 26；自然连战第 6 波 4、第 13 波 4），因为 `Die` 杀掉的成员和召唤物的计数方式与自然死亡不同【未核实机制】；波次推进靠子物体数检查，不受影响，但终局能否按时结束没有在跳波后测过。跳波只用于探针和造存档，采集用存档。
- 之后 `Forum_A_w2` 回到波次起点的轮换（`C:\ssbot\sandbox\r1c_collect.cmd`：w2、w4、w6、w7、w8、w9、w11、w12、w13、w3、w5、w10）。

### 13.10 2x 加速检查（R1 ④，部署后；**没有通过，2x 不采用**）

运行（全部 1x 和 2x 同一组种子 131500–131515、同一轮换 w7、w13、w4、w6，各 16 局波次起点，每局 180 s 游戏时间；冻结代码 `C:\ssbot\live_r1c_28a9417`）：

| 策略 | 1x（实例 3） | 2x（实例 2） |
|---|---|---|
| `idle`（不按键） | `20261004_144623_Forum_A_w7_mix_data_idle_oracle`，2678.9 s 游戏时间 | `20261004_150500_..._idle_oracle_x2`，2614.4 s |
| `data2` | `20261004_153511_Forum_A_w7_mix_data2` | `20261004_153211_Forum_A_w7_mix_data2_x2` |

（第一次 2x idle `20261004_145235` 在第 4 局开始前停了：设 2x 后马上读到的 `Time.timeScale` 是 0.0（局间读档 / 冻结），`set_time_scale` 当成失败；28a9417 起改为 5 s 内再读几次。它的 4 局不用。时间盒原来按"帧数 / 60"算，2x 时一局会是 360 s 游戏时间；414fb1a 起 `combat_run` 把时间盒除以倍速，两臂的游戏时间因此相同。）

检查工具 `forum_speed_check` v2（13.5 的判据不变）加了 `--inject`（往 B 臂注入已知的差别：停留时间加减 / 缩放、某类某招的选择份额挪走一部分、速度乘一个系数）和 `--a-slice` / `--b-slice`（同一臂分两半）。结果（`C:\ssbot\data\m2_forum_r1c\speed\<idle|data>\*.json`；格式：p < 0.05 的键 / 键数（二项上限），Holm 显著键数）：

| 比较 | idle：停留 | 速度 | 选择 | data2：停留 | 速度 | 选择 |
|---|---|---|---|---|---|---|
| **1x 对 2x（真实）** | **18/67（8），Holm 7** | **19/42（6），Holm 4** | 1/13，0 | **20/115（12），Holm 4** | **9/65（8），Holm 1** | 0/24，0 |
| 1x 前 8 局对后 8 局（噪声） | 0/61，0 | 2/38，0 | 0/13，0 | 0/64，0 | 0/41，0 | 0/15，0 |
| 1x 前 8 局对后 8 局模拟 2x（只粗化） | 0/61，0 | 0/38，0 | 0/13，0 | 0/64，0 | 0/41，0 | 0/15，0 |
| 同一批 16 局对它自己模拟 2x | 0/67 | 0/42 | 0/14 | 0/120 | 0/66 | 0/24 |
| 真实 2x + 全部停留 +1/30 s | 62/67，Holm 21 | | | 72/115，Holm 24 | | |
| 真实 2x + Clapper 停留 +1/30 s | 32/67，Holm 21 | | | 37/115，Holm 21 | | |
| 模拟 2x（前对后）+ 全部停留 +1/30 s | 22/61（8），Holm 0 → 不一致 | | | 23/64（8），Holm 0 → 不一致 | | |
| 真实 2x + Clapper 速度 ×1.1 | | Holm 6（不注入 4） | | | Holm 7（不注入 1） | |
| 模拟 2x（前对后）+ Clapper 速度 ×1.1 | | 5/38（6）→ 没查出 | | | 5/41（6）→ 没查出 | |
| 真实 2x + Clapper 闪避 → 锤 挪 12 % / 25 % / 50 %（−5 / −10.5 / −21 个百分点） | | | 1/13、2/13 没查出；3/13 Holm 1 查出 | | | 0/24、1/24 没查出；Holm 2 查出 |

- **只粗化不会触发它**：同一批局粗化到 1/30 s（同一局）全 0；独立的两半一半粗化，三项都在上限内、Holm 0；1x 对 1x 也一样。（按交替局分两半不能当对照：4 波轮换下单号局是 w7 + w4、双号局是 w13 + w6，两半的敌人不同；idle 的交替对照因此"不一致"。前 8 局 / 后 8 局每半各有每波 2 局。伤害框外沿的比较在 idle 只有 1 个键、data2 17 个键、0 个超出：16 局 180 s 的波次起点太少，伤害框基本没有被检验。）
- **它能查出的**：停留时间整体或只一类偏 1/30 s（两个 1x 帧，超过模板 ±1 时间格的膨胀）：16 + 16 局 Holm 21–24 个键，8 + 8 局靠二项上限（22–23 个键 > 8）。**8 + 8 局时单键 Holm 根本不可能成立**（核对者）：4 波轮换下每类敌人只在自己那几波的局里，Clapper 是 4 + 4 局，按局置换的最小 p 是 1 / C(8, 4) = 1/70 ≈ 0.014，远大于 0.05 / 61；v2 的 `underpowered` 按全部 16 局算（1 / C(16, 8)），所以写的是 false。8 + 8 的这些对照只检验了二项上限那一项（v3 按键算，见 13.15）。**查不出的**：Clapper 的选择份额偏 5–10 个百分点（偏 20 个百分点才查出）；8 + 8 局时 Clapper 速度 ×1.1。所以"选择一致"只能说明差别小于约 20 个百分点。
- **真实的 2x 不一致，两种策略都是同样几个 Clapper 键；另外 Tiny 的 `Ready` 也变了很多，v2 的检查没有查出来**（核对者；不是"只有几个 Clapper 状态差一个 2x 帧"，见 13.15）。Clapper `Air`、`Spell Antic`、`Slam 0`、`Slam 1`（idle 还有 `Jump Antic`、`Slam Recover`、`Cast Slam Antic 2`）的停留在 2x 时短（或长）**一个 2x 帧**：`Air` 1x 绝大多数 53 帧（0.8825 s，粗格 27），2x 是 26 格（0.8667 s）（idle 198 / 213 对 185 / 203；data2 160 / 190 对 162 / 195）；`Slam 0` 1x 多是 3 格（126 / 175），2x 是 2 格（158 / 163）；`Slam 1` 1x 全是 2 格，2x 35 / 163 是 1 格；`Jump Antic`（idle）1x 107 / 107 是 15 格，2x 43 / 104 是 14 格。这些键的平均停留差都不到一个 1x 帧（−21 … +11 ms）。Clapper 跳的高度一样（8.219 u；v2 按隔帧读的实体状态找起跳，1x 漏了只有 1 帧的 `Jump`，n 111 / 203，滞空的 KS 0.58；v3 按 FSM 事件找起跳重算，idle 213 / 203 次，高度中位都是 8.219 u、KS 0.02）；滞空（`Jump` + `Air`，放到 1/30 s 格上）1x 165 / 213 是 27 格、39 是 28 格，2x 184 / 203 是 27 格、13 是 26 格（data2 同样：28 格 38 / 190 对 26 格 16 / 195）：差的正是 `Air` 在哪个 2x 帧结束，同一批局只粗化时完全一样。物理没变，变的是**状态在哪一帧结束**。速度的显著键是短状态的 0.2 s 窗口（Clapper `Evade Scuttle`、`Spell Antic`、`Walk`、`Slam Recover`，data2 是 Tiny `Swoop In`）。
- 原因（推断）：工具把两臂放到同一个 1/30 s 格上用的是"计时器"的取整（状态在 `t ≥ D` 的那次 Update 结束：1x 的 n 帧对应 ceil(n / 2) 格）。由物理事件（落地、碰撞触发器）结束、在 FixedUpdate 里切换的状态，状态时间只累计了已完成的 Update，对应的是 floor(n / 2)：1x 53 帧 → 26 格，正是 2x 测到的。13.5 的校准（把 1x 录像每隔一帧读）复现不了这种取整，所以它通过了、真实的 2x 没通过。另一部分不是测量取整能解释的：`Jump Antic` 在 1x 是 29 帧 26 / 107 次（24 %）、30 帧 81 次，按 floor 取整 29 帧也落到 14 格，所以单是取整应给出约 24 % 的 14 格，2x 实测 43 / 104（41 %），差别显著（按样本 z ≈ 2.6，不是按局的检验）（原来写的"29 帧以下只有 4 %"比错了对象，核对者）：2x 时一帧 1/30 s，游戏自己的计时器和事件检查也只在这些时刻发生，状态实际就提前或推后最多一个 2x 帧【未核实，是对现象最简单的解释】。
- **结论**：按事先定好的判据（任何 Holm 显著键即不一致）2x 不通过，**不采用**；长跑全部 1x（13.13）。差别的大小（一个 2x 帧，1/30 s）正是行为表要用到的尺度：支撑走法的停留区间只放宽 1 帧、模板只膨胀 ±1 个 1/60 s 时间格。**2x 的数据不进任何表**：伤害框 / 支撑模板不行（只填每隔一个 1/60 s 格，状态进出时刻差一个 2x 帧）；行为表的停留和速度也不行（上面这些键），Tiny `Ready` 的自循环按真实时间走、2x 时按游戏时间少了六成（访问次数、后继份额，13.15）；选择份额没看出差别，但检查只能看出约 20 个百分点以上的差，单独用它也要先有自己的、事先定好容差的检查和更多的局。三个 2x 运行（`145235`、`150500`、`153211`）不进任何构建。**更正（修复轮）**：实例 2 的"1x"长跑 `20261004_155649` 其实整场都是 2x（`153211` 设的 2x 一直留在游戏里，`combat_run` 在 1x 时不设倍速，记录里写的是 `time_scale` 1.0），它的 72 局进了 13.13 的新数据认证集；见 13.15。以后要再试，应当事先登记一个按"差别不超过一个 1x 帧"的等价判据（而不是看了这次的数据再改判据），并用完整连战或更长的局检验伤害框。

### 13.11 停放的 Tiny 不算在场（`gauntlet.WAITING_STATES` 加 "Dead"，59e02a1）

- Maestro 的池化召唤物 `Song Automaton Tiny`（hp 28）在没被召唤时停在 `Control` 的 `Dead` 状态（`Die` 只是进 `Dead` 的一步），位置在三只 Maestro 的出生点（20.5 / 24.4 / 42.5, 10.9），碰撞体全关。读任何一个波次存档都能看到 9 只（13.9 的 check 里每一行都有）。旧的 `WAITING_STATES` 只有 `Die`，所以 `live_enemies` 把它们算在场。
- 核对：074719 的 3 场完整连战 + 两个 R1 运行的各 3 局（217,145 帧）里，活着、不隐藏的实体上出现 `Dead` / `Die` 的只有 Tiny 的 `Control`（974,814 / 909 个实体帧），这些帧上伤害碰撞体一次都没启用。所以加 "Dead" 只影响停放的 Tiny。
- 用 `live_enemies` / `in_play` / `WAITING_STATES` 的地方逐个核对：
  - **变了的**：v1 数据策略 `GauntletDataPolicy`（目标不再是停放的 Tiny；"只剩 Clapper"的口袋判断不再被停放的 Tiny 挡掉）；`GauntletBuilder._attribute` 最后一步"同名候选里离得最近、在场的那只"不再选停放的 Tiny（前面"碰到 / 贴身"的两步照旧，垂死的召唤物仍能被选中）；`forum_r1` 探针的 watch 行。
  - **没变的**：`WaveSkipPolicy`（只打波次成员，Tiny 不是）；v2 策略和 `verify_wave_start`（`wave_start.fighting` 本来就去掉 `Dead`，现在是空过滤）；`forum_demo`（`_active` 已用 Tiny 规格的 dormant）；`forum_simul`、`forum_r1_audit`、`forum_products`（各自去掉 `Dead`）。
  - 所以 R0 / R1 以来用 v1 策略采的完整连战，在场里有停放 Tiny 的帧上策略会去追它们（这些数据仍然有效：是策略的行为，不是敌人的）；表的接触归属在这次重建里用新规则（13.13）。
  - **这也改了 v1 策略本身**（核对者）：有 Tiny 停放时"只剩 Clapper"的口袋判断以前不成立，现在成立，所以 Clapper 波次里 59e02a1 之后的 v1 完整连战会进口袋，R0 的 v1 完整连战进不了；主角的位置分布、Clapper 对主角的选择（口袋会改变 Clapper 的选择）都跟着变。对留出召回的认证没有影响（13.13），但凡是"和策略有关"的比较（位置、对主角的选择、R0 对 R1），59e02a1 前后的 v1 局要当成两个策略版本。`GauntletDataPolicy.REVISION` = 2（e2b0873 起写进 AttemptRecord 的 `policy.rev`）；之前的记录没有这一项：`code_rev` 是 59e02a1 的后代的（13.13 的 38 场新完整连战 `154609` / `154612`，代码 28a9417）算版本 2，其余（R0 的 107 + 35 场）是版本 1。
- 测试：`test_gauntlet.py`（停放 / 召唤中的 Tiny、v1 的目标）、`test_forum_r1.py`（构建器的最后一步归属）。

### 13.12 结构上不存在的招在表里标出（abad048）

`BehaviourSpec.absent`（招族或 Control 状态 → 理由，理由引用 13.2）：Envoy `EN_HOPSLASH` / `HopSlash Antic`、`EN_ENTRY` / `Wake Pause` / `Wake` / `Black Thread Wake`；Maestro `MA_POINT` / `Point Start`；Bellbearer `Throw Antic Quick`（不是出招起点，是 `Rethrow?` 的永远走不到的分支）。表里多一项 `structurally_absent`，`coverage.families` 里这些招族 `missing` 为 0、带 `absent`；`coverage.json` 的行带 `absent`、`hours_to_target` 0，`behaviour_build` 打印"structurally absent"。这次重建在加这一项之前就开始了，所以用 `behaviour_build --stamp-absent <表目录>` 事后补标（只改这几项，模板和决策不动；表里记 `absent_stamped_by`）。Bell Beast 的表没有这一项。

### 13.13 R0 + R1 重建与认证（R1 ⑤ 的收尾；**认证没有通过，新表不提交，仓库里仍是 R0 的表**）

输出都在 `C:\ssbot\data\m2_forum_r1c\`（不进仓库）：候选表 `tables\forum`、按折支撑与接触 `build_all\extra`、冻结的输入 `build_all\fights.json`、缓存 `cache`（R0 的 107 场是硬链接）、新数据 `fresh\` + `cache_fresh\`、召回 `recall_*.json`、比较 `table_ablation.json`。代码冻结在 `C:\ssbot\live_r1c_off_59e02a1`（构建、扫描、认证同一份；`support_recall` 的配置和 R0 认证时 da1cd41 相同）。

- **输入**：R0 的 107 场完整连战 + R1 的 181 局 1x（`111158` Envoy 专场 106 局、波次 33 局（去掉 3 局 w2 幽灵）、`130403` 4 + 3、`131323` 23 + 8、`143803` 2 + 2；首轮 06a7c2b 的冒烟运行不进）；R0 认证用过的 35 场不进（两边的差只在 R1）；排除清单 `exclude.json`。288 场，30.07 h 战斗时间（R0 25.4 h），341,436 次接触；构建 6.8 h。`hero_height` 被选进不少决策（Clapper `Idle` / `Walk` / `Dmg Attack` / `After Scuttle`，Choristor `Attack Choice` / `Hop Antic` / `Whip 1/2/4`，Minister `Attack` / `Parry Stance`，Reed `Check Pos` / `Lock R High` / `Parry Slash` / `Throwing Up?`，Envoy `Charge`，Tiny `Defend Ready`）；受保护的 Envoy 去掉了 2,779 个决策、3,867 段停留（`protected Song Pilgrim 01: ...`，HP ≤ 20 时从"主角打中才走"的状态出去的，13.8）。Envoy 实例：普通斩 692 → 3,742、跳斩 241 → 1,440、冲锋 385 → 796、**伏击 107 → 240（≥ 200）**；Choristor 斩 / 鞭 / 跳 1,377 / 1,309 / 914 → 2,920 / 2,217 / 1,530；Reed 各招 +40–60 %；其余 +5–20 %。样本内验证仍不通过（R0 也是，`--allow-failed-validation`）：未覆盖 71、来源没导出 24、攻击外 59 次；留出超 R_FAIL 的比例 0–0.54 %（Clawmaiden 最高）。
- **新数据（认证用）**：不在构建输入里、19:58 冻结时已关闭的 1x 局：实例 0 / 1 的完整连战 38 场（fo_A，v1 策略，`154609` / `154612`，15:46 起）、实例 2 / 3 的波次起点 132 局（含 w2，`155649` / `162411`，15:56 起）、2x 检查的 1x 两臂 32 局（`144623` 14:46 起，比构建开始的 15:03 还早，但构建的运行清单是事先定好的、不含它；`153511` 15:35 起）；202 场、175,437 次接触（每个滞后 173,908 次非后续）。原来写"2x 的局一律不进"，**不对**：`155649`（实例 2）整场是 2x（13.15），202 场里它占 72 场、59,289 次接触（58,733 次非后续）；真正 1x 的新数据是 130 场、116,148 次接触（115,175 次非后续）。唯一的漏网在 `162411`（实例 3，1x），所以"不通过"的结论不变，折 0 在 1x 子集上也是 100 %；但这批认证数据里有三分之一不是 1x。那 38 场 v1 完整连战是 v1 的版本 2（59e02a1 之后，13.11），和 R0 的 v1 完整连战不是同一个策略：对召回认证没有影响，和策略有关的比较里要分开。
- **开发（三份不相交，288 场）**：每个滞后 339,537 次，L2 100 %、L3 / L4 99.9997 %（各 1 次：R0 开发集里就漏的那次 Clawmaiden `Slash 5`，`074719` i3/ep5 f281119）。
- **认证（新数据，生产余量）**：折 0 的表 L2 / L3 / L4 全 100 %；**折 1 的表 L3、L4 各漏 1 次**（99.9994 %）：`20261004_162411` i3/ep9（w3 读档，只有一只 Clawmaiden）f482061，`damage_blocked`（无敌帧里的碰撞），来源 `Slash Collider 1`，发生在 `Slash 2` 的第 0 帧；起点（f − 3 / f − 4）在 `Slash Antic` 0.475–0.492 s。`Slash 1` 只有 2 帧（482059–482060），`Slash Collider 1` 在这两帧启用，482061 时导出里已换成 `Slash Collider 2`，游戏在 482061 报告了碰到 `Slash Collider 1`。这两帧里 Clawmaiden 前冲了 0.66 u（x 29.34 → 28.68），主角在它前方 4.4 u 左右、向左退。停留区间都在表里（`Slash Antic` [0.500, 0.517] s、`Slash 1` [0.025, 0.055] s），所以是**空间上**没盖住：按状态的模板 + CM_SLASH 余量 0.7048 u + 家族并集（锚在攻击开始处）在折 1 的表里到不了这个位置。
- **结论**：按 R0 的协议（三份不相交、新数据、L = 2 / 3 / 4 留出召回 100 %）**没有通过**，新表不提交，`knowledge/1.0.30000/enemies/forum/` 仍是 R0 的表和 `support_margins.json`（只补了 13.12 的结构性标记）。
- **消融（同一批 202 场新数据，R0 的表 + R0 的生产余量）**：**R0 的表漏的是同一次**（折 1，L3 / L4），折 0 全 100 %。所以 R0 在 35 场上的"认证"被这批新数据推翻了（`support_margins.json` 里 `certified: true` 只是那 35 场的结果；Forum 的 `known` 不能据此置真）。加了 R1 之后：要靠预测以外的结构项覆盖的接触变少（攻击中的伤害框管每个滞后 38–41 → 25–26 次，无名来源候选 29 / 26 / 25 → 25 / 21 / 17，同名候选 54–58 不变，待机身体管 506–535 → 484–528）；生产余量变化：**Minister 冲刺 0.19 → 3.0 u（搜索上限）**、Envoy 冲锋 2.96 → 3.0、Tiny 防御 0.98 → 0.76、Maestro 斩 0.54 → 0.39、Reed 闪避 0.14 → 0.02、Envoy 跳斩 0.07 → 0。召回一样，R1 的数据让结构项少用了一些；Minister 冲刺的余量撞到上限**不是 R1 的数据本身，是一次接触归属错了**（核对者指出原来写的"R1 的冲刺近身 / 拼刀"没有核实；修复轮查明如下）。
- **MI_CHARGE 的 3.0 u 是一次归错的接触**：上限只来自一次接触，`20261004_111158_Forum_A_w2_mix_data2` i3/ep10（首轮 battle.prune 之前的 w3 读档，一直打到第 5 波"Wave 5 - Song Admins"的两只 Minister）f400125，`damage_blocked`，来源只有子物体名 `Colliders/Collider AttackAntic`（Minister 的碰撞体不带敌人名，9.2）。这段无敌接触报告为 first_f 400115 – last_f 400125。主角在左墙上（x 14.28，y 9.9，向上 3.75 u/s）；贴着它的是 Minister 799114（x 15.2，`Attack Antic`，它的 `Collider AttackAntic` 一直启用到 400124、挨着主角），400125 它进 `Attack`、这个碰撞体关掉；同一帧另一只 Minister 799128（`Song Administrator (1)`，x 22.3，**离主角 8 u**）在 400120 进了 `Attack Antic`，它的同名碰撞体正启用。构建器把无敌段拆成逐帧，每帧找"这一帧导出这个名字的碰撞体的敌人"：400125 只有 799128，于是这一帧归给了它（`src` 写成 `Song Administrator (1)/...`），它的模板 3 u 内当然没有残差。其余 R1 的 838 次 MI_CHARGE 接触留出残差最大 0.286 u。幽灵子物体和这次无关（那一帧的实体里没有前几波的成员，只有正常等待的后面波次成员和停放的 Tiny）。
- 修复（eeb550e，`GauntletBuilder._attribute`）：只给子物体名的来源，这一帧导出它的敌人都没有贴着主角（TOUCH_U 0.3 u）时，先找导出延迟（LAG_F 2 帧）之内这个名字的碰撞体贴着主角的那只；都没有才照旧。用新代码重扫这一局：400115–400125 全归 799114（400125 是它的 `Attack` 第 0 帧），计数器"touching up to LAG_F before; this frame's exporters far"在这一局 1 次。整个构建里还有几次要等下一次构建的计数器（Minister 的 `Collider ParryStance` 也走这条路）。**所以 13.13 的候选表里 MI_CHARGE 的 3.0 u 余量是假象**，下一次构建应回到 R0 的量级【预期，要等下一次构建核实】。
- 首轮 battle.prune 之前的其他波次起点（w3 及以后，w2 已排除）留在构建里：幽灵子物体不导出、不参与接触，它们只改变波次推进（重叠波要等一个击杀才进下一波，13.1），也就是敌人的组合和时间，不改变单个敌人的行为表；用到组合 / 波次时间的产品（forum_products 之类）要按 `code_rev`（1c374f8，14:37 部署之前）把它们分开。
- 下一步是 R2 的事，不是数据量：Clawmaiden 斩是边冲边砍的招（R0 已指出会移动的攻击家族要按当前位置重新锚定，12.2），这次的漏网正是前冲两帧里的第一段碰撞体；改了预测结构之后要再找一批没见过的数据认证（这 202 场现在也"见过"了）。

### 13.14 复现（收尾轮）

```
cd brain
..\scripts\uv.cmd run python -m ssbot.probes.forum_r1 hello --instance 2
..\scripts\uv.cmd run python -m ssbot.probes.forum_r1 check --instance 2 --waves 2,3,4,9,10 --seconds 10
..\scripts\uv.cmd run python -m ssbot.probes.forum_r1 skip --instance 2 --method oracle --wave 13 --seconds 8
# 2x 检查：C:\ssbot\sandbox\r1c_speed.cmd idle1 | idle2 | data1 | data2，然后
powershell -File C:\ssbot\data\m2_forum_r1c\speed\run_checks.ps1 -Pol idle -A <1x 运行> -B <2x 运行>     # 以及 run_checks2.ps1
..\scripts\uv.cmd run python -m ssbot.tools.forum_speed_check --a <1x> --a-slice 0:8 --b <1x> --b-slice 8:16 --simulate-b 2 --inject dwell:*:*:+0.033333
# 表与认证：C:\ssbot\data\m2_forum_r1c\pipeline_build.ps1、pipeline_cert.ps1、ablation_early.ps1（命令在脚本里）
..\scripts\uv.cmd run python -m ssbot.tools.behaviour_build --encounter Forum --stamp-absent ..\knowledge\1.0.30000\enemies\forum
# 修复轮（13.15）：v3 检查，独立的 1x 对照（-IndOnly），实例 2 的 1x 长跑
powershell -File C:\ssbot\data\m2_forum_r1c\speed\run_checks3.ps1 -Pol data -A <153511> -B <153211>
powershell -File C:\ssbot\data\m2_forum_r1c\speed\run_checks3.ps1 -Pol data_ind -IndOnly -A <153511> -B <153211> -Ind <162411>
C:\ssbot\sandbox\r1cfix_collect.cmd i2
```

### 13.15 修复轮（核对者意见之后，2026-10-04 23:00 起；同一分支，代码 04b6228 … ed65873）

**实例 2 的"1x"长跑其实是 2x。** `20261004_155649_Forum_A_w2_mix_data2`（实例 2，15:56 起，配置和每条记录都写 `time_scale` 1.0）每一局 10,802 帧里约 9,800 帧 dt = 2/60，180 s 时间盒（按帧数 / 60）里是 323–332 s 游戏时间。原因：`time.scale` 设的是 `Time.timeScale`，跑完一个运行它还留在游戏里；实例 2 前一个运行是 2x 臂 `153211`，而 `combat_run.set_time_scale` 在 1x 时直接返回、什么也不设。其他运行逐个按 STATE dt 核对过（每个运行抽 2–6 局：`111158` 两个、`130403` 两个、`131323` 两个、`143803` 两个、`144623`、`154609`、`154612`、`162411`、`195019`、`195800`），都是 1x；2x 只有三个 2x 臂和 `155649`。影响：13.13 的新数据认证集里 72 / 202 场是它（已在 13.13 更正，结论不变）；构建的输入不受影响（都在第一个 2x 运行 14:52 之前）。处理：23:38 用 `combat_run stop` 让它在当前一局后停下（155 局：STUCK 145、CLEAR 9、HARNESS_FAIL 1，全部 2x，不能当 1x 用），实例 2 从 ed65873 的冻结代码重新开 1x（`20261004_233950_Forum_A_w2_mix_data2`，`time.scale 1.0` 读回 1.0，第一局 dt 1/60）。修复（ed65873）：`set_time_scale` 在 1x 时也设并读回（没有这个 RPC 的 oracle 只能是 1x），每条记录多一项 `time_scale_game`（开局前读回的 Time.timeScale），倍速不是 1 的运行结束时把实例设回 1；Forum 的构建器（`GauntletBuilder.scan`）先读一局前 600 帧的 dt，不是 1x 的局不进表（计数器 "fights left out: game speed"，`behaviour_build` 打印警告并从小时数里去掉）。`155649` 可以当作另一组种子的 2x 臂（下面"独立的 2x"）。

**Tiny 的 `Ready`（被推翻的说法）。** 13.10 原来说 2x 的差别只在几个 Clapper 状态、差一个 2x 帧，不对。`Song Automaton Tiny` 的 `Control` `Ready` 会自己转回自己（`Ready → Ready`），这个自循环**按真实时间（或帧数）走，不按游戏时间**【机制未核实】：

| | idle 1x | idle 2x | data2 1x | data2 2x |
|---|---|---|---|---|
| `Ready` 的访问（离开次数） | 1,605 | 1,003 | 1,597 | 1,082 |
| `Ready → Ready` | 953 | 356 | 953 | 387 |
| `Ready → Fire Ready` / `Defend Ready` | 311 / 341 | 308 / 339 | 320 / 321 | 350 / 342 |
| `Ready → Ready` 停留，游戏时间均值 | 1.80 s | 3.23 s | 1.77 s | 3.34 s |
| 同上，真实时间均值（事件的 `rt_in_prev`） | 1.92 s | 1.75 s | 1.88 s | 1.82 s |
| `Ready` 的总时间 | 2,373 s | 2,312 s | 2,344 s | 2,511 s |

出去攻击 / 防御的次数（Maestro 叫的）和在 `Ready` 里的总时间都不变，只有自循环在游戏时间里少了六成，`Ready` 的停留中位从 1.49 s 变成 1.98 s。v2 的检查没有这一项（停留只看分布，idle 的 p ≥ 0.05；data2 p 0.0016 够不着 Holm 的 0.00043），选择只数攻击起点。1x 的局 dt 固定 1/60（真实时间比游戏时间慢约 6 %：这批局的 `rt_in_prev` / `t_in_prev` ≈ 1.06），所以如果这个循环按墙上时间走，1x 时它的游戏时间节奏也会随机器负载变几个百分点；按帧数走就不会。两者现在分不开（2x 时被 Maestro 打断的循环更多，完整循环的均值偏短）【未核实】。

**`forum_speed_check` v3**（04b6228）：加两项按局置换检验的指标，`visits`（每类每个状态的访问次数 / 这类的 FSM 总秒数）和 `next`（每个状态的后继份额，含自循环；只有一个后继的状态不算）；每个键按"含这个键的局"算最小可达 p（1 / C(n_a + n_b, n_a)），报告 `underpowered_keys`（单键 Holm 第一步就不可能成立的键）；Clapper 起跳按 FSM 事件（进 `Jump` 到离开 `Air`），滞空放到共同的格上；`--inject trans:类:从:到:倍数`（改某个转移的次数）；`--a-units` / `--b-units`（按 AttemptRecord 的 unit 挑局）。驱动 `C:\ssbot\data\m2_forum_r1c\speed\run_checks3.ps1`，结果 `speed\v3\<idle|data|data_ind>\*.json`。格式：p < 0.05 的键 / 键数，Holm 显著键数；"弱"是 Holm 不可能单独成立的键数。

| 比较 | 停留 | 速度 | 选择 | visits | next |
|---|---|---|---|---|---|
| idle 1x 对 2x（16 + 16） | 18/67，Holm 7（弱 44） | 19/42，Holm 4 | 1/13，0 | 6/67，0（Tiny `Ready` p 0.0096，4 + 4 局，可达 ≥ 0.014） | 1/16，0（同上） |
| data2 1x 对 2x（16 + 16） | 20/115，Holm 4（弱 90） | 9/65，Holm 1 | 0/24，0 | 1/115，0（Tiny `Ready` p 0.0012，5 + 7 局，可达 0.0013 > 0.05/115） | 2/43，**Holm 1：Tiny `Ready`** |
| 独立的 2x：`153511` 对 `155649` 的 16 局同样四波（别的种子） | 36/120，Holm 10 | 22/66，Holm 9 | 0/24 | 6/120，**Holm 1：Tiny `Ready`**（5 + 8 局） | 3/51，Holm 1（Clapper `Slam Antic`） |
| **独立的 1x 对 1x**：`153511` 对 `162411` 的 16 局同样四波 | 1/118，0 | 0/66，0 | 0/24，0 | 7/118，0 | 0/50，0 |
| 同上，B 模拟 2x（只粗化） | 1/118，0 | 0/66，0 | 0/24，0 | 7/118，0 | 0/50，0 |
| 同上 + 全部停留 +1/30 s | 103/118，Holm 33 | | | | |
| 同上 + Clapper 停留 +1/30 s | 26/118，Holm 23 | | | | |
| 同上 + Clapper 速度 ×1.1 | | 5/66，Holm 5 | | | |
| 同上 + Clapper 闪避 → 锤 挪 25 %（约 −10 个百分点） | | | 1/24，0 → 没查出 | | |
| 同上 + Tiny `Ready → Ready` ×0.37（2x 实测的大小） | | | | 8/118，0（p 0.001，弱） | 1/50，**Holm 1** |
| 同上 + ×0.6 / ×0.8 | | | | 8/118，Holm 0 | 1/50，Holm 0 → 没查出 |
| 8 + 8 对照（前 8 局对后 8 局，含模拟 2x、注入 ×0.37 / ×0.6） | 0，弱 61–64 / 61–64 | 0–2 | 0 | 0，全弱 | 0，全弱 |

- 结论：2x 仍然不采用（理由多了 Tiny `Ready`）。v3 用独立的 1x 对 1x（16 + 16，同样四波，别的种子）证实：只粗化不触发任何一项；停留 +1/30 s、Clapper 速度 ×1.1 在 16 + 16 局都查得出（8 + 8 时速度查不出）；Tiny 自循环少六成只有 `next` 刚好查出（`visits` 的键太多，Tiny 只在 5 + 7 局里，Holm 够不着）；自循环少两成到四成、选择挪 10 个百分点都查不出。
- **功效是按类算的**：4 波轮换（w7、w13、w4、w6）下 16 + 16 局里停留键有 44 / 67（idle）、90 / 115（data2）个单独不可能过 Holm，Tiny 只在 4–5 + 4–8 局。以后要再试 2x（或任何"同一行为"的检查），每类敌人每臂至少 8 局（C(16, 8) = 12,870），比如只轮换两波、或 32 + 32 局，并事先登记等价判据（13.10）。
- 13.10 的 v2 结果（`speed\idle`、`speed\data`）不变；它们的 8 + 8 对照只检验了二项上限（13.10 已注明）。
## 14. R2：多敌人预报（MultiForecast）（2026-10-04，forum_planner_plan.md §5 R2；离线，没有连接游戏）

代码：`combat/enemy_tracker.py`（EnemyTracker，一个敌人实例；BossTracker 不动）、`combat/enemy_tables.py`（9 类共用一个模板库）、`combat/multi_forecast.py`（MultiForecaster / MultiForecast）、`combat/projectiles.py`（投掷物的确定路径）、`combat/wave_tracker.py`（WaveTracker）、`core/forum.py`（静态事实，与 `knowledge.gauntlet_tables.FORUM_SPECS`、`train.encounters` 有一致性测试）；工具 `multi_recall`、`projectile_audit`、`consistency_audit`、`planner_bench --encounter Forum --multi`；测试 `tests/test_multi_forecast.py`（20 个；复核后 25 个，14.7）。

### 14.1 预报怎么组成

- **接口**：`occupied`、`occupied_without`（击杀：去掉它的尾巴、管和它可能开始的招；它扔出的投掷物留下）、`prob`（只用于打分）、`t_min`、`committed`、`support_set`（每个实例一个事件；多段招 hits > 1、伤害 = 实测最大连段 chains.json）、`targets`、`known`；另有 `forecast_if_killed`（假设这几只现在死：一致性审计和以后的击杀价值用）和 `bell_redirected`（主角现在打铃）。Bell Beast 用 `MultiForecaster(boss=Forecaster)` 包起来，所有查询转给 Forecaster 自己的 Forecast：逐位相同（`multi_recall bellbeast`；测试用夹具窗口）。包装是代理（14.7）：别的属性读写都落在 boss 的 Forecast 上（`_occ` 也是它的），包装时不重置被包的 Forecaster。
- **comfort**：多敌人路径还没有 comfort 模板（R3）：`occupied(..., comfort=True)` 用普通支撑回答，并在 `MultiForecaster.comfort_requests` 里计数；14.5 的内存和"今天的规划器"的数字都不含 comfort（规划器的 comfort 检查拿到的是没有余量的支撑；forum_planner_plan §1 第 8 条估计 comfort 模板约让内存翻倍）。
- **行走**：R0 的支撑行走（Control FSM、日志里的停留区间和后继，±1 帧松弛），每个状态一个进入时间的凸包；区间一直在长的节点直接取到上限（hi → 6 s、lo → min(lo, 0)），概率变大不重走（只影响打分）。按（类型、状态、当前实例、死亡、超时）缓存；`warm()` 在战前把 9 类所有起点的行走、家族行走模板、时间金字塔和盒表建好（2245 个，约 50–80 s）。缓存的行走从状态进入时刻算、截到 6 s（WALK_CAP_S）：当前状态的年龄 + H + 1 帧超过 6 s 时按"超时"从原点走（下一帧起随时可能结束；Minister Chase 最长 5.9 s、死掉的 Tiny 10.6 s，不这样它们的后继的开始窗口会被截成 [1 帧, 1 帧]；复核发现）。
- **放置**：当前招（锚点已知）的每个状态：进入时间不超过 3 帧的用细模板逐帧放，更宽的用一个"窗口放置"（粗化 5×5 = 0.25 u 的模板的时间 OR 金字塔，一次查询覆盖整个进入区间）；以后才开始的实例（攻击、待机）用"家族行走模板"（这个起点能到的所有状态和尾巴、各自按进入区间时间膨胀后的每帧外包盒）× 锚点盒（变换按速度外推、加上该类型的待机增长；视觉视角再加偏移散布），两种朝向，按起始时间分段（离原点越近越细：0.4 s 内 6 帧、1 s 内 12 帧、再往后 24 帧）；锚点盒宽于 24 u 的直接放全场盒。
- **管**：待机族里的敌人 = 待机身体管（最近看到的伤害框按速度移动、按待机增长变大）；头 5 帧（反应延迟）还有当前碰撞体管（按该类型最高速度长）和投掷物管（40 u/s）。
- **死亡**：被杀的敌人留最后的伤害框 3 帧（§12.3 的死亡尾巴：导出在击杀那一帧就把它去掉，之后 0 帧接触）；被死亡打断的那一招**不放尾巴**（一致性审计发现的错，见 14.4）；它已经做完的招的尾巴留着：扔出去的东西比它活得久（Clapper 跳跃施法落地后死了，rune slam 照样炸；视觉视角里只有这条尾巴盖它，见 14.3）。Tiny 是池化的：只要还有 Maestro 在场，死后继续走（召唤会把它叫回来，HP 回满）。
- **等待中的敌人**：只有它马上可能进场时才走（它的波次已排队，或 Maestro 在场时停着的 Tiny）；波次成员**最早在它的波次激活时才离开等待状态**（WaveTracker 的最早激活时间；之前不放碰撞体管）。
- **波次**：WaveTracker 只用看到的东西（成员类型的击杀事件、在场成员的出现）和静态波次表（BattleScene 的规则：startDelay、remainingEnemyToEnd、激活后 1 s 的检查），**不读 room.battles**（只当测试真值，测试与 WaveSim 逐帧对照）；下一波还没导出的成员用入场族的世界坐标模板放在它的出生点。只有"新进场"的成员才算激活（不是正在跑的波次里还活着的成员，也不是看到被杀的尸体；BattleScene 会跨波次重用同一个 GameObject，离场过的被杀成员再进场算新的）；视觉视角漏看一次击杀时（画面外）计数会多一、下一波永远不排队，所以在激活 2 s 之后看到下一波类型的新成员进场就重新同步（14.7）。视觉视角里"unknown"/"hidden"相位不算在场。
- **Tiny 成组**：≥ 3 只 Tiny 时，同一个 4 u 网格格子里的成一簇（固定网格：杀掉一只不会把另外两只连成一簇，见 14.4），每簇每个家族行走、每个时间段只放一行（锚点盒覆盖所有成员）；是逐只放置的超集（测试），行数更少。成组的行代表整簇：`occupied_without(某只)` 只要簇里还有别的 Tiny 就保留它，`occupied_only` / `t_min(subject)` 对簇里每只都算它，`support_set` 给簇里每只一个事件（14.7）。
- **结构上不可达的招**（§13.2：Envoy HopSlash / Wake 入场、Bellbearer Throw Antic Quick、Maestro Point）在类型表里删掉，生产表里没有它们的模板（测试）。
- **视觉合法**：HP 只按看到的命中扣（oracle 用事件的 amount，视觉视角按攻击的价格表，方差累加），不读 ents.hp；运行时不读 room.battles、不读格挡位；视觉视角的分支只来自相位（PhasePost），位置 = 检测位置减去该类型的身体偏移（行为表 body_offset 的盒心，按朝向镜像）。AST 测试检查运行时模块不读这些字段。

### 14.2 投掷物的确定路径（`projectile_audit`，每 2 帧一个原点，到 0.8 s）

下面的数字先是 R0 的 10 场构建缓存（样本内，初版）；复核后的模型（铃的侧弹分支、穹顶带 1.1 u）在**留出的 35 场新数据缓存**（`cache_fresh`）和 10 场构建缓存上重测，见本节末尾。

- **物理时钟**：Rigidbody2D 50 Hz，一帧（1/60 s）里有 0 或 1 步；导出的位置只在有步的帧变。用"移动中的投掷物这帧没动 = 这帧没有步"把步的相位（模 0.02 s）收窄到 0.1 ms 网格；一局里相位基本不变（例：18.25 ms、0.45 ms，偶尔漂 0.2–1.5 ms 后重新收窄）。收窄之前（每局开头第一只铃）按半步猜，误差大（p99 0.67 u，只占 0.2 % 样本）。
- **Throwing Bell**（Bellbearer，圆 r 0.425，伤 1）：g 60，半隐式欧拉；落地那一步 vy 停 0，下一步 Bounce vy 20（x 速度不变，第一步抬高 0.1 u）；侧墙那一步 vx 停 0，下一步以 10 u/s 弹回；碰穹顶（§8.1，提前 0.5 u）之后不确定 → 管（40 u/s）；钉击（Nail Hit，9 帧，碰撞体关）把速度设为 30 u/s 沿打击方向，期间碰地 / 墙先滑、Nail Hit 结束再弹。中心误差 p99：≤ 0.1 s 0.0005 u、≤ 0.2 s 0.0006 u、≤ 0.4 s 0.20 u、≤ 0.8 s **0.246 u**（n 1,076,583；最大 7.47 u：没有建模的接触）；记录的伤害框落在支撑形（±1 步、0.1 u 皮）内 1,022,636 / 1,022,951。
- **Song Reed Pin Projectile**（Reed 的标枪，盒约 2.0 × 0.1）：31 u/s 直线，盒碰到侧墙或地面 → Stick（碰撞体关）。p99 **0.050 u**（n 33,443），支撑内 33,443 / 33,443。
- **rune bomb small**（Clapper 的 Bomb Cast，圆 r 2.166、y 3.67、伤 1）：出现时就导出（碰撞体未启用，按半径认出别名），出现后 0.335–0.36 s 点亮，最多 18 帧。一排：第一颗在 x0，之后每步一对 x0 ± 4.2 k（最多 9 对）；**一步是 9 或 10 帧**（FSM 等 0.15 s，按帧取整：实测 0.150 / 0.167 s 交替），所以以后的对从这一排最近看到的那一步起算，每步 9–10 帧。炸弹对象是池化的（一局里约 20 个 iid 循环使用）：两排重叠时池子不够，一侧会晚出或不出（一侧的排）——这些在出现时才被跟踪（出现到点亮还有 0.335 s）。预报：在出现前 0.1–1.5 s 做的预测里 2020 / 2098 颗的点亮帧落在预测窗口内（其余是池子推迟的一侧或别的排在同一 x 的预测），x 误差 p99 **0.025 u**；预测了但没出现的 3142 / 6060（超集：池子没给的一侧）。
- **rune slam**（Jump Cast，圆 r 7.187、y 3.34、伤 2）：出现后 1.06–1.11 s 点亮，亮 20 帧以内。
- 主角打铃（`bell_redirected`）：打中的下一步起 30 u/s（左、右、上、下），碰撞体关 0.15 s，然后自由飞。
- **复核后（e516f22）**：留出的 12 场新数据缓存上初版的铃有 1,581 / 1,157,991 个记录框落在支撑外（最大中心误差 12.3 u，0.1 s 内就有 1.68 u）。查 142 份缓存（107 构建 + 35 新数据）里铃的每次 Bounce：(1) **落地反弹后的侧弹**：8,813 次落地反弹里 384 次在下一步又来一次侧向 Bounce，vx 变成 ±10 u/s（378 次 +10），x 移 0.1 u、y 和 vy 不变；其中 60 次离侧墙很远（x 21–48，没有墙；Box2D 在地面接缝或躺在地上的碎铃处的幽灵接触）。模型改为：路径上每次落地反弹，从下一步起加两条分支（vx = +10、−10；只分一层），`HazardPath` 的铃是 [B, n]，分支 0 是原来的飞行。(2) **穹顶**：703 次离墙的空中接触里，铃顶到穹顶线的间隙 p99 0.83 u、最大 1.01 u（穹顶线在 x 20–23、39–40 附近偏高约 1 u），提前量从 0.5 u 改为 **1.1 u**。另有一次铃落在地上另一只铃上（y 3.9），没有建模。结果（中心误差按分支 0 算，支撑按所有分支）：

| 缓存 | 铃：中心误差 p99（≤ 0.1 / 0.2 / 0.4 / 0.8 s） | 铃：记录框在支撑内 | 标枪 p99、支撑内 | 炸弹排 x 误差 p99、点亮落在窗口内 |
|---|---|---|---|---|
| 留出 35 场（`cache_fresh`） | 0.0005 / 0.0007 / 0.185 / **0.233 u**（n 3,681,504；最大 14.8 u：真实走的是侧弹分支） | **3,469,352 / 3,469,352** | 0.050 u、108,459 / 108,459 | 0.148 u、8,093 / 8,391 |
| 构建 10 场 | 0.0005 / 0.0006 / 0.184 / **0.229 u**（n 1,054,310；最大 0.99 u） | **1,001,308 / 1,001,308** | 0.050 u、33,443 / 33,443 | 0.025 u、2,020 / 2,098 |

  穹顶带变宽后，更多铃在穹顶附近变成管（留出 35 场被审计跳过的"dome tube"样本 3,314 个）。炸弹排点亮在窗口外的（298 / 8,391）是池子推迟的一侧：出现后（点亮前 0.335 s）才按它自己的静态路径跟踪。

### 14.3 留出召回（`multi_recall`，R0 协议：接触在 c、预报在 c − L 帧，L = 2/3/4；union 覆盖 + 按类型）

全部在 5332426 上（冻结检出，低优先级）：

| 组 | 场 | 视角 | L2 / L3 / L4 覆盖 | 按类型（own） |
|---|---|---|---|---|
| dev：R0 的 107 场，三分（第 k 折对 1 − k 折的表，每半用另一半标定的余量） | 107 | oracle | 228,333 / 228,333（三个滞后都是） | 100 %，9 类每类 100 % |
| fresh：R0 的 35 场新数据 | 35 × 2 份表 | oracle | 74,120 / 74,120（两份表都是） | 100 % |
| fresh：R1 的 187 场（w2 的 3 局幽灵已排除） | 187 × 2 份表 | oracle | 112,949 / 112,949（两份表都是） | 100 % |
| ve：R0 的 35 场新数据，视觉视角（占位相位表：恒等映射；位置减去行为表的身体偏移） | 35（fold 0 的表） | ve | 74,120 / 74,120 | 100 % |

- 9 类每类在每组、每个滞后都是 100 %（union 和按类型都是）。盖住它们的：预报本身（放置、投掷物路径、死亡框）≥ 99.4 %，其余是待机身体管（dev 每个滞后约 1,290 次、fresh 约 840 次、ve 约 335 次）；视觉视角另有 26 次靠当前碰撞体管（反应延迟那几帧）。
- **复核：上表漏了多段招的第一次接触。** 连段的后续命中（Final Hit，`follow`）不检查，理由是"连段的第一次接触代表它"；但第一次接触（钩：敌人的 Control / Attack FSM 进入 Multihit / Multiwhip，主角挨的是没有来源的快速伤害）不在 contacts.jsonl.gz 里，所以约 91 % 的连段根本没被检查。`multi_recall` 现在为每条连段补一个钩接触（Final Hit 之前 ≤ 70 帧里最近一次进入连段状态的帧，主角盒取该帧和前一帧），计入 n 并单列。e516f22 重跑（冻结检出 `C:\ssbot\live_r2fix_e516f22`）：

| 组 | 场 | 视角 | L2 / L3 / L4 覆盖（含钩） | 钩（覆盖 / 个数） | 按类型 |
|---|---|---|---|---|---|
| dev 三分 | 107 | oracle | 229,711 / 229,711 | 1,378 / 1,378 | 100 % |
| fresh R0 | 35 × 2 份表 | oracle | 74,585 / 74,585（每份表） | 465 / 465 | 100 % |
| fresh R1（w2 幽灵已排除） | 187 × 2 份表 | oracle | 113,385 / 113,385（每份表） | 436 / 436 | 100 % |
| ve（占位相位表） | 35（fold 0） | ve | 74,585 / 74,585 | 465 / 465 | 100 % |

  每条 Final Hit 都找到了钩（dev 1,459 行 → 1,378 条连段，fresh 1,872 行 → 1,802 条，没找到的 0）；钩按类型（fresh R0）：Song Administrator 243、Song Pilgrim 03（Choristor）161、Song Reed 61。9 类、三个滞后、union 和按类型都是 100 %。`recall_{dev,fresh,ve}_e516f22.json`。
- Bell Beast 包装（`multi_recall bellbeast`，20261003_144536 i4_000，4001 帧，eb5d221；之后的改动不碰 boss 路径）：放置、occupied、prob、support_set、committed、战术、规划器决策 **0 差**；夹具窗口上的逐位测试和 Bell Beast 的测试在 5332426 上都通过。**复核：**这些检查只比了查询，没有比实战策略的 `bell_hit_monitor.zone`：它会改写 `f.det` 并清空路径缓存、调用 `f._occ(placements, ...)`，在包装上 100 % 抛 AttributeError（`det` 只读、`_occ` 被多敌人路径同名覆盖）。改为代理之后（e516f22）：i4_000 4001 帧 + 892 次铃区检查、20261004_095304 i0_001 4001 帧 + 1,333 次铃区检查，八项全部 **0 差**（`bellbeast_wrap_*_e516f22.json`）；测试另查了在窗口中途包装一个已经有状态的 Forecaster。

### 14.4 一致性（forum_planner_plan §4.4 第 6 条：击杀、打铃之后主角周围 1 s 的危险区不得变大；`consistency_audit`）

方法：R0 的 35 场新数据，回放到每 30 帧，主角位置周围 ±2 u（"近"，步长 0.25 u）和 ±6 u（"宽"，0.5 u）× 之后 1 s（每帧）的格子：模拟击杀 = 每只在场敌人 `forecast_if_killed` 对 `forecast`；记录的击杀 = 击杀前一帧的同样比较，以及击杀后的预报对击杀前的预报（同一绝对时间，只看死者和入场）；模拟打铃 = 主角 4 u 内每只在路径上的铃，往远离主角的方向打（侧打；在主角下方加下劈、上方加上挑）；记录的打铃 = 记录到的 Nail Hit 前一帧，按它实际飞走的方向。

发现并修掉的模型错误：

1. **被杀的敌人给被打断的招放尾巴**（Song Pilgrim 03：杀在招中途，招的 `_tail` 模板放在击杀时刻，比它自然结束早，盖到原来没有的格子；第一场前 8000 帧 17 / 512 次模拟击杀违反）。按 §12.3 的死亡尾巴，被打断的招不放尾巴。（中间一版连已做完的招的尾巴也清掉了：视觉视角的召回里 Clapper 的接触有 12 次（每个滞后）只被别的敌人的支撑碰巧盖住——都是 Clapper 死后才炸的 rune slam（跳跃施法的尾巴，6 次）和 rune bomb small（Bomb Cast 的尾巴，6 次），于是改回保留已做完的招的尾巴。）
2. **结束一波的击杀把下一波停着的成员立刻放到主角身上**（例：20261003_074533 i2 ep26 f 1414290–1414380，第 12 波最后一只 Song Administrator：第 13 波（startDelay 2 s）一排队，停在场上 Fly In Ready 的 Reed 就开始走，还带着当前碰撞体管，0.017 s 起就盖到它下方 5 u 的主角；违反的只有 Song Administrator 和 Song Pilgrim 03 的击杀）。改为：等待中的波次成员最早在波次激活时（WaveTracker 的最早时间，startDelay 之后）才离开等待状态，之前不放碰撞体管。修之前（69e9b36，35 场里 26 场有效）：近区 76 / 128,512 次模拟击杀、2 / 1,067 次记录击杀违反，全部属于这一类。
3. **同一进程里的第二个预报器用错家族行走表**（宽区 20 次，都出在杀 Leave 状态的 Tiny 上，t = 0 起盖住宽区一大片；单独重跑那一场 0 次）：模板库按键登记粗基底，同一个键第二次登记时拿到了下一个新键的 id，于是同一进程、同一份表上的下一场，家族行走用到了别的行走的盒表。修好（已登记的键沿用原 id），加了测试。召回的工作进程一个进程跑多场，修之前的召回都受影响（数字仍是 100 %）；14.3 的召回是修好之后的。追查时还改了两处 Tiny 的规则（单独没有测出违反，按游戏规则保留）：死掉的 Tiny 只在有 Maestro 在场时按"会被召回"继续走；成簇改为固定 4 u 网格的格子（去掉一只不会把两边连成一条长链、锚点盒宽过 24 u 变成全场盒）。

结果（5332426，35 场全部有效）：

- **击杀：0 违反**。模拟 172,839 次（Tiny 70,266、Maestro 25,191、Clapper 24,332、Bellbearer 15,853、Reed 11,252、Minister 10,868、Choristor 6,805、Clawmaiden 6,659、Envoy 1,613），记录的 1,429 次（击杀前一帧的假设，和击杀前后两份预报的比较），近区、宽区都是 0。
- **打铃**：记录的 474 次 0 违反。模拟 2,854 次里近区 9 次变大，都是物理，不是模型错误：下劈的铃碰地后要等 Nail Hit 结束才弹起，弹回主角附近（2）；上挑的铃升到顶再落回来（4，0.85–0.98 s）；侧打打向近墙，铃以 10 u/s 弹回（2）；上挑碰到穹顶，之后路径不确定成管（1，这是模型的保守）。宽区 18 次（另有 3 次是铃被打走时穿过主角 6 u 内的远侧格子）。规划器以后算"打铃"的价值时要用 `bell_redirected`，不能假设打走就安全。
- **复核：`occupied_without` 没被审计。** 上面的击杀比较用的是 `forecast_if_killed`（重新成组），而 §4.3 给规划器的击杀查询是 `occupied_without(iid)`：它按行的 owner 过滤，Tiny 成组的行只记在一只（owner）名下，杀 owner 会把同格其他 Tiny 以后可能开始的招一起去掉（合成例子：92,276 格里丢 17,870；`occupied_only(某成员)` 也漏组行，`t_min(subject)` 偏小）。改为组行代表整簇（14.1）后，审计加了一项：`occupied_without(死者)` 必须盖住击杀后其余敌人的支撑（`forecast_if_killed` 去掉死者、入场和等待中的成员）。568d873（冻结检出 `C:\ssbot\live_r2fix_568d873`，35 场）：**击杀 0 违反**（模拟 172,839 次、记录 1,429 次的假设和前后比较，近区宽区都是 0），**`occupied_without` 0 违反**（同样的 172,839 + 1,429 次）。打铃：记录的 474 次 0；模拟 2,854 次里近区 14 次——上面的 9 类物理（落地反弹 2、上挑落回 4、近墙弹回 2、穹顶管 1）加 5 次只由侧弹分支造成（14.2：落地反弹后 4.4 % 的侧弹是真实物理，模型保守地两边都放）。`consistency_568d873.json`。

### 14.5 算力与内存（第 6 波回放：20261003_074719 i3 ep0，5951 帧，6–8 只敌人在场，生产表，4 线程）

5332426，整机同时跑着 4 个召回进程和 5 个游戏实例（整机 CPU p50 53–60 %）：

- **forecast(2 s)：p50 0.91 ms、p99 2.75 ms**（最大 10.0 ms，一次）；update p50 0.06 / p99 0.27 ms。每帧放置：细 3（p99 11）、窗口 9（p99 28）、外包盒 179（p99 238）。（同一回放带规划器时 forecast p50 1.4 / p99 3.4 ms；整机满载 CPU p50 98 % 时（9835ced）p50 2.0 / p99 4.2 ms。）
- **内存**：读表 25 s、warm 55 s；表（模板库）696 MB；进程 RSS 读完表 + warm 938 MB，回放结束 1,012 MB，**峰值工作集 1,109 MB**（带规划器 1,184 MB）。之前峰值 1.94 GB 来自粗化时一次展开整段模板的布尔数组（改成分块）。
- **今天的规划器 + MultiForecast**（没有 Forum 战术：原地 HOLD、风险图来自 MultiForecast）：tick p50 21.6 ms、p99 37.9 ms；其中 support 6.5 / 16.5 ms、prob_bind 6.4 / 14.7 ms、rollout 3.0 / 4.3 ms；**92 % 的 tick 是 FORCED_RISK**（找不到证明安全的路径）。这是 R3 要做的（Forum 词汇、K 目标打分、查询预算）。注意这是开环回放：主角的位置来自录像里的数据策略，不是规划器自己走出来的，所以 92 % 不能当成闭环实战的 FORCED_RISK 比例。
- **复核：(d) 的 2.75 ms 是一次运气好的跑。** 复核者在同样的负载下重跑同一条命令三次：p99 3.08 / 3.23 / 3.21 ms（CPU p50 53 / 57 / 40 %），都超过 3 ms。慢的 tick 是机器噪声不是结构：同一 tick 连做两次，第一次慢的第二次不慢（重负载下第一次 p99 4.67 ms，两次取小 p99 2.51 ms；没有一次 GC 落在预报里，`gc.freeze()` 也不改变尾巴）。剖析（cProfile）：`groups()` 占约 60 %（numpy 小数组调用的固定开销、按行的 `np.unique(axis=0)`、每 tick 约 160 行死掉的 Tiny（Maestro 在场时按"会被召回"继续走）的全场盒逐行追加），`subject()` 约 25 %（每 tick 24 个跟踪器）。改动（语义不变，除全场盒按 owner 合并成外包时间窗，是超集）：Tiny 簇和组用一维键、每种类型查一次增长表、全场盒每个 owner 一个、家族名用对象数组。同一负载下与 5332426 并排：p99 3.14 → 2.72 ms（CPU p50 49 %）、3.05 → 2.61 ms（43–45 %）。e516f22 上三次（`bench_wave6_fc_e516f22_{1,2,3}.json`，5951 tick，同机 5 个游戏实例 + 25–30 个别的 Python 进程）：

| 跑 | 整机 CPU p50 / p99 | forecast(2 s) p50 | p99 | 最大 |
|---|---|---|---|---|
| 1 | 50 % / 58 % | 0.77 ms | **2.57 ms** | 10.4 ms |
| 2 | 44 % / 53 % | 0.69 ms | **2.49 ms** | 10.0 ms |
| 3 | 36 % / 53 % | 0.64 ms | **2.48 ms** | 9.0 ms |

  结论：**勉强达标**（36–50 % 负载下 p99 2.5–2.7 ms），余量只有约 15 %；整机满载时仍会超过 3 ms。R3 往每个 tick 加活之前要再省：把 `groups()` 的分段 / 锚点盒计算搬进 numba，死掉的 Tiny 直接给全场盒不走分段。
- **复核后的内存与规划器**（e516f22）：峰值工作集 1,109–1,112 MB（带规划器 1,187 MB），模板库 696 MB，读表 26–29 s、warm 49–61 s（不含 comfort 模板，见 14.1）。今天的规划器：tick p50 14.2 ms、p99 25.6 ms（CPU p50 42 %；support 4.1 / 12.0、prob_bind 3.7 / 9.8、rollout 2.4 / 4.0 ms），FORCED_RISK 仍是 **92.0 %**；带规划器时 forecast p99 2.96 ms。`bench_wave6_planner_e516f22.json`。

### 14.6 复现

```
cd brain   # 低优先级、NUMBA_NUM_THREADS ≤ 4
# 召回：dev = R0 的 107 场三分；fresh = R0 的 35 场 + R1 的 187 场（w2 的 3 局幽灵已排除）对两份折的表；ve = 35 场新数据、视觉视角（占位相位表）
..\scripts\uv.cmd run python -m ssbot.tools.multi_recall dev --workers 3 --json <out>
..\scripts\uv.cmd run python -m ssbot.tools.multi_recall fresh --fresh C:\ssbot\data\m2_forum_r0\fresh --fresh C:\ssbot\data\m2_forum_r2\r1 --workers 3 --json <out>
..\scripts\uv.cmd run python -m ssbot.tools.multi_recall fresh --fresh C:\ssbot\data\m2_forum_r0\fresh --tables 0 --view ve --workers 2 --json <out>
..\scripts\uv.cmd run python -m ssbot.tools.multi_recall bellbeast <Bell Beast 录像> --frames 4000
# R1 运行的接触（behaviour_build --contacts-only，命令见 C:\ssbot\data\m2_forum_r2\r1_scan.cmd）
..\scripts\uv.cmd run python -m ssbot.tools.projectile_audit --cache C:\ssbot\data\m2_forum_r0\cache --fights 10 --every 2 --horizon 0.8 --json <out>
..\scripts\uv.cmd run python -m ssbot.tools.projectile_audit --cache C:\ssbot\data\m2_forum_r0\cache_fresh --fights 35 --every 2 --horizon 0.8 --json <out>   # 留出
# 复核这一轮的全部跑：C:\ssbot\data\m2_forum_r2\fix_run.cmd <audit|dev|fresh|ve|proj|bench1..3|benchpl|bb1|bb2> <rev>（冻结检出 C:\ssbot\live_r2fix_<rev>）
..\scripts\uv.cmd run python -m ssbot.tools.consistency_audit --every 30 --workers 2 --json <out>
..\scripts\uv.cmd run python -m ssbot.tools.planner_bench --encounter Forum --multi [--planner] --fight 20261003_074719_Forum_A_data/i3/ep0 --wave 6 --frames 6000 --threads 4 --json <out>
..\scripts\uv.cmd run pytest -q tests/test_multi_forecast.py
```

### 14.7 复核修正（2026-10-04 晚，提交 421176d–568d873；离线）

两位复核者在 f274317 上找到的问题，逐条：

1. **Bell Beast 包装不是代理**（实战会崩）：只转读不转写，`det` 只读、多敌人路径的 `_occ` 覆盖了 Forecast 的同名方法，`bell_hit_monitor.zone` 在包装上 4,965 / 4,965 次抛错。改为代理：包装模式下没被本类回答的读写都落在 boss 的 Forecast 上（多敌人的并集查询改名 `_union_occ`）；`MultiForecaster(boss=...)` 不再重置被包的 Forecaster（以前在 `__init__` 里 `reset()` 会清掉它的跟踪器和铃）。结果见 14.3。
2. **Tiny 组行只算在 owner 名下**（高）：见 14.4；组行带簇号（`bb["gcl"]`），`MultiForecast.clusters` 记每簇的 Tiny；全场盒按簇里每只各放一个。
3. **召回漏了多段招的钩**：见 14.3。
4. **WaveTracker 漏看击杀后不再同步**：视觉视角漏一次击杀（画面外），计数多一，下一波永远不排队，即使它的成员已经进场（合成例子；录像 20261003_074719 i3 ep33 的第 9–13 波估计晚 28–138 s）。改为：只有"新进场"的成员算激活，激活 2 s 之后看到下一波类型的新成员进场就重新同步（计数取 min(计数, remainingEnemyToEnd) 再加新一波的人数）；视觉视角的"unknown"/"hidden"相位不算在场（之前 ep27 里第 1 波两只 Choristor 等待时的相位是 unknown，被当成在场，新成员判断失效，第 1 波晚 8.5 s）。35 场新数据与 room.battles（测试真值）对照：oracle 视角 455 次激活全部在 −0.133 – 0 s（偏早，保守方向），重新同步 0 次；视觉视角同样 455 次全部在 −0.133 – +0.067 s，重新同步 3 次（074533 ep27 第 1 波、ep34 第 4 波、074719 ep33 第 9 波，都是漏看的击杀）；之前晚 28–138 s 的 074719 ep33 现在每波都在 0.05 s 内。
5. **铃的确定路径不是支撑的超集**（留出数据）：见 14.2（侧弹分支、穹顶带 1.1 u；留出 35 场 3,469,352 / 3,469,352 在支撑内，p99 0.233 u）。
6. **(d) 不稳**：见 14.5。
7. **行走截在 6 s**：见 14.1（老状态从原点走）。
8. **comfort 被悄悄忽略**：见 14.1（计数、写明）。
9. **一个 Bell Beast 计时测试在忙机器上必挂**（main 上同样挂：p99 4.0–4.3 ms 对 3 ms）：`test_hitbox_tables.py` 的预算超了且机器忙（有游戏实例在跑或整机 CPU > 20 %）时跳过并写出数字，安静机器上仍然断言。
10. 对用户问题"bot 反应会比我 0.5 倍速快吗"的回答原来把"召回在 2–4 帧前就盖住接触"当成反应速度，不对（见 HANDOFF Task R2 的更正）。

全部测试（`pytest -q`，tests + ssbot/tests，e516f22 时的工作区，整机忙）：1071 passed、2 skipped（其一是上面这条计时测试，按负载跳过）、1 xfailed；`tests/test_multi_forecast.py` 25 个。

## 15. R3：快层（ForumPlanner）（2026-10-05，forum_planner_plan.md §5 R3；离线 + 实例 3 的 Bell Beast 小批）

代码：`combat/forum_planner.py`（ForumPlanner，Planner 的子类；Forum 开关 = 胶水层用哪个类，Bell Beast 的 `Planner` 一行没改）、`combat/candidates.py`（`build_forum`：姿态族 + 核心躲避集）、`combat/tactics/modes.py`（`GoalPrefs`）、`combat/multi_forecast.py`（重新锚定、受击反应预报、三处收紧）、`knowledge/kin_jit.py` / `kinematics.py`（冲刺两处、落地清后摇，只在 Forum 配装下生效）、`safety/supervisor.py`（`forum_supervisor_config`）；工具 `planner_bench --encounter Forum --multi --planner --forum`；测试 `tests/test_forum_planner.py`（14 个）、`tests/test_multi_forecast.py` 新增 2 个。输出（不进仓库）：`C:\ssbot\data\m2_forum_r3\`（驱动 `cert.cmd`、`kin.cmd`、`bench.cmd`、`bb_batch.cmd`、`bb_identity.cmd`、`scan_new.cmd`）。

### 15.1 13.13 的漏网与重新锚定

- **经 MultiForecast 重放这一次接触**（`20261004_162411` i3/ep9 f482061，折 1 的表；R0 的表和 R0+R1 候选表都试了）：L2 / L3 / L4 都盖住。盖住它的是窗口放置和外包盒（当前招 CM_SLASH 的家族并集与后续实例），细模板没有盖住；把主角盒再往 Clawmaiden 冲的方向挪 2 u 仍然盖住。13.13 的漏网是 R0 的 SubjectRecall（逐状态模板 + 余量）的，不是运行时预报的。
- **结构上的原因**：CM_SLASH 从 `Fly To Slash` 开始，锚点是那时的位置 (32.70, 7.53)；到 `Slash Antic` 0.475 s 时 Clawmaiden 已经飞到 (29.40, 6.21)，离锚点 3.3 u。按锚点坐标系的模板只含录像里出现过的飞行距离。
- **改法（重新锚定）**：一个实例进入**同一家族的另一个起始状态**（`Fly To Slash` → `Slash Antic`；表里 CM_SLASH 的 `start_states` 本来就是这两个）时，实例照旧继续，同时把剩下的部分当作"从这个状态开始、锚在那一刻位置的新实例"再放一份（该起点的家族行走模板，外包盒形式）。直接从 `Slash Antic` 开始的实例没有飞行段，所以这一份不管之前飞了多远都对得上。测试：合成 Reed 飞 3 u 后，只有重新锚定的那份盖住刀（`test_an_attack_that_moved_is_re_anchored_at_its_later_start_state`）。
- **重新认证**：15.8。

### 15.2 第 6 波开环 FORCED_RISK 的诊断：预报的三处收紧（都要重新认证）

ForumPlanner 第一版在第 6 波回放（074719 i3 ep0）里阶段 1 通过的行中位数是 0；逐 tick 查主角站位被谁盖住：

1. **行走的下界跑到 −333 s**：Tiny 的 `Ready → Ready` 自环最小停留 0，每走一圈出口区间按 1 帧松弛往前挪一帧；"区间一直在长就直接取边界"对下界取的是 min(lo, 0)，已经是负数就一直往下，直到步数上限 20 000（= −333 s）。于是 Tiny 的待机家族行走模板从实例开始前 333 s 起就有盒子，任何一只 Tiny 的后续实例都成了覆盖整个视野的全场盒。改：根之后的节点进入时间不早于根 1 帧（`walk` 的 `push`：lo ≥ −DWELL_SLACK_S）；测试 `test_a_zero_dwell_loop_never_enters_before_the_root`。不只 Tiny：R2 的代码里 610 次行走（9 类的每个状态 × 是否超时）有 **494 次**跑到 −1 s 以下、一直走到步数上限（8 类，只有 Choristor 没有）；撞上上限的行走在那一刻停下，后面的节点可能没走到。改后 0 次。副作用：召回里每次预报从约 2.4 ms 降到约 0.7 ms；dev 召回里之前每个滞后约 1 290 次只由待机身体管盖住的接触，现在全部由预报本身盖住（推断是行走不再被截断，没有逐次核对）。
2. **全场盒取的是一个 owner 所有窗口的外包区间**：改为模板里**有盒子的那些帧**（`TemplateStore.active_span`），按窗口合并。
3. **死掉 / 停放的 Tiny 随时可能回来**：8 场 R0 完整连战里 105 次 Tiny 离开 `Dead`（全部进 `Set Pos`），**105 次都在某只 Maestro 进入 `Summon` 的同一帧**（间隔 0）。改：它们最早在"在场 Maestro 最早可能进入 `Summon`"时离开 `Dead`（Maestro 的行走：当前实例里的 `Summon` 节点，或含 `Summon` 的家族（MA_SUMMON，`Call` 0.48–0.52 s 之后）的后续实例起点加该家族记录的最早 `Summon` 进入时间，减 1 帧）；没有在场 Maestro 时照旧不走。

这三处之后第 6 波的全场盒从 0.73–0.93 s 才开始（之前从 −332 s 起）。但开环里主角站位本身在第 1 帧就被盖住的 tick 仍占绝大多数（数据策略的主角贴着 Tiny 群和 Maestro），开环 FORCED_RISK 比例几乎不变（15.5）；这三处改的是 0.6 s 视野后段的支撑，闭环里规划器自己保持距离时才看得出。

### 15.3 ForumPlanner（快层）

- **候选**：起始状态的姿态族（`posture_of`：WSIDE 或 CLING → 墙，否则按 GROUND 分地面 / 空中）。核心躲避集 56 行 = {WAIT, MOVE 左右, JUMP 11 / 24 / 48 帧 × 原地 / 左 / 右, DASH 左右} × {idle, 左跑, 右跑, 满跳}，三个族里命令逐位相同、没有攻击键；姿态的攻击首段（地面：横砍 3、上砍 2；空中再加收割者下劈 2；墙上：横砍 3 = 墙砍）× 全部续段（Bell Beast 的续段去掉 4 个，加"冲刺"和"冲刺后第 10 帧横砍"各两向）。行数：地面 399、空中 441、墙 357，加 CONTINUE；没有丝技。失去控制（受击冻结 / 后退、锁）时只用核心行。
- **阶段 1**：所有行只推标称一条，标称碰撞盒中心查支撑（模板按主角受击盒膨胀，这就是标称盒的精确检查）。它是必要条件：阶段 1 接触 ⇒ 包络接触（包络盒含标称盒，包络按子盒的检查偏保守，各条都无敌的帧在标称里也无敌），所以阶段 1 接触的行 S = 1 已定，不用包络。J、Hz、U 都在标称上算。
- **阶段 2（包络，bounds_lo）**：每块 32 行，顺序：通过阶段 1 的核心行（**总是，不受截止时间限制**）、CONTINUE、其余按 (Hz, Hz_soft, U, −J) 的前 K_b = 96 行、前 8 名各自同首段的最多 3 个兄弟（V 要两条同首段的安全路），然后其余。优先部分之后，遇到留下安全行的块就停；优先部分之内，过了截止时间（11 ms）且已有安全行才停；**没有安全行就一直查到底**（慢 tick，计 overrun，不算 FORCED_RISK）。
- **命中效果**：每块里有预测命中、包络安全的行（每 tick 最多 32 行）带着第一下命中的效果重推（横砍 / 墙砍：背向后坐；上砍：RecoilDown；下劈：弹起）并重查；超出上限的、有预测命中的行 S = 1。命中分支还要查**被打敌人的受击反应**：`hero_caused.json` 的 TOOK DAMAGE 出边（Clapper `Idle` → `Dmg Attack`、Reed `Alert` → `Stab Pos`、Minister `Chase` → `Range Check`、Maestro `Fly` → `Summon?`、Envoy `Charge` → `Reset` 等，只用跟踪器所跟 FSM 的出边），`MultiForecaster.forecast_reaction` 从命中那一帧按反应状态单独给这只敌人做一份预报（每 tick 最多 4 份，超出的行 S = 1）。测试：Reed 在 `Alert` 被打，反应预报的刺比平常的支撑早到（平常要等 `Alert` 的最小停留）。
- **打分**：收割者横砍 / 上砍 / 墙砍 / 下劈的多边形（`attacks/reaper.json`，生效帧 5–12 / 5–15 / 5–12；下劈前摇 9 帧、斩 11 帧；墙砍 = 不着地且碰撞盒离竞技场墙 ≤ 0.15 u 时的横砍）对最近 K = 4 个、14 u 内的敌人（MultiForecast.targets：受击框沿速度外推），每个目标按 `GoalPrefs.hit_w[iid]` 加权（默认 1）。测试：横砍打到前上方、上砍只打到正上方和身后（M2.md 你的经验那一条）。冲刺 / 冲刺跑中按攻击的行（游戏里是冲刺斩，模型没有）否决（R_UNMOD）。
- **选择**：只在 S 已知的行里选（包络过的，或阶段 1 就接触的）；选中的 S = 0 计划一定包络过（审计 `EnvelopeAudit`：chosen_safe == chosen_safe_enveloped、core_not_enveloped == 0）。FORCED_RISK：第一次接触最晚的 16 行里先比**接触帧占比**（代替 P：MultiForecast.prob 每个敌人、每种放置、每个概率值各查一次，第 6 波 p50 3.7 ms），再比接触时刻、J；`ForumConfig.exact_p` 打开就用 P。
- **U / I3**：致命一击 = 可能结束整场战斗的那一刀（`forum_kill_hp`：终局波在跑（或波次都完）、没有排队的下一波，剩下成员 hp_est − 3σ 的**最大值**：一刀要结束战斗就得把剩下的全打死）；平常波次的击杀不进 U。R3 没有击杀分支，所以这一刀只在 I3（GREEN、满血、h ≥ 3）下放行。
- **YELLOW 的每敌击杀冻结**：`forum_yellow_kill_hp`：在场、该类型的击杀在 kill_freeze.json 里出现过冻结（`kill_freeze_s`，按类型取最长）的敌人中 hp_est − 3σ 的最小值，给监督器的 kill_prims（接线在 R4）。
- **不在快层里**：视野末的锁定检查（Forum 候选没有丝技；Bind 宏自己查）、按键经济项、击杀分支、comfort（多敌人路径没有 comfort 模板）。
- **属性测试（§4.4 第 2、3 条，`tests/test_forum_planner.py`）**：四种局面（刺的前方、身后、待机、刺中）× 8 组随机 GoalPrefs（权重、站位、风险图、hit_w、max_hits；截止时间 0 / 50 ms 交替）：核心行的 S / Hz / U 逐位相同，有目标时 FORCED_RISK ⇒ 默认目标下也 FORCED_RISK；13 个位置 × 截止时间 0 / 2 / 50 ms（块 16）：选中的 S = 0 计划全部包络过；刺中时 FORCED_RISK 只在通过阶段 1 的行全部包络之后。

### 15.4 监督器的 Forum 设置（`forum_supervisor_config`）

worst_known_damage = 2；Q4 按敌人实例计（同一实例 2 次支撑外命中，或全场 3 次；`SupervisorInput.unpredicted_sources`，胶水层在 R4 填）；负重环带装着时受击后窗口 1.3 s（i-frame ×1.3，probes.md 实测 1.30 s；`WEIGHTED_POST_HIT_WINDOW_S`）。多段事件的 hits / damage 已由 MultiForecast.support_set 按 chains.json 的最大整链给出（R2）。Bell Beast 的默认值不变（测试）。负重环带的运动学（`HeroParams.with_weighted()`）在 bench 里按 `ws.res.equipped` 切换；bot 的录像里没有装过它的，没有用装着它的录像核对过【未核实】。

### 15.5 算力：Forum 开环 bench（R3 验收 (c)）

`planner_bench --encounter Forum --multi --planner [--forum]`，074719 i3 ep0 的三段录像：第 6 波（Wave 7 - Maestro × 2，6–8 只敌人）、第 11 波（Wave 12，混合）、第 13 波（Wave 14 - Finale），每段 3000 帧（前 50 个 tick 不计）；"之前" = 今天的 Planner + MultiForecast（R2 的冻结检出 `live_r2fix_e516f22`，即 14.5 (g) 的配置），"之后" = ForumPlanner + Forum 配装的运动学（`hero_reaper_forum.json`）；同一负载下前后各跑一次 Bell Beast bench（20261003_144536 i4_000，6000 帧）。开环：主角的位置来自录像里的数据策略，FORCED_RISK 比例不是闭环实战的比例。

整机 CPU p50 42–58 %（5 个游戏实例（实例 0、1 空闲）+ 3 个扫描进程），冻结检出 `live_r3_2b8f5c7`（之后）与 `live_r2fix_e516f22`（之前），`bench.cmd ... final`：

| 录像 | 敌人 | 之前 tick p50 / p99（ms） | **之后 tick p50 / p99** | 之后规划器 p50 / p99 | FORCED_RISK 之前 → 之后 |
|---|---|---|---|---|---|
| 第 6 波（Maestro × 2） | 8 | 19.2 / 31.0 | **8.06 / 18.19** | 4.97 / 15.47 | 90.8 % → 85.9 % |
| 第 11 波（混合） | 2 | 14.2 / 24.6 | **6.13 / 16.90** | 3.91 / 14.49 | 88.0 % → 84.4 % |
| 第 13 波（终局） | 2 | 15.3 / 23.9 | **6.31 / 14.52** | 4.45 / 12.19 | 93.7 % → 91.6 % |
| Bell Beast（同负载，前 / 后） | | | 5.71 / 18.20、5.93 / 18.44 | 5.19 / 15.67 | 2.2 % |

- 验收：三段 tick p50 都 ≤ 9 ms；p99 不高于同负载的 Bell Beast bench（第 6 波 18.19 对 18.20 / 18.44 ms：持平，余量在噪声以内）。**审查复测没有复现**（CPU p50 33 %：第 6 波 p99 16.16 ms，前后三次 Bell Beast 13.68 / 15.65 / 13.33 ms），这一条按"未达到"算；修正与复测见 15.11。之后的分项（第 6 波 p50）：阶段 1 推演 1.80 ms、阶段 1 支撑 1.38 ms、打分 0.42 ms、包络 0.10 ms（p99 9.0 ms：通过阶段 1 的行多时）、选择 0.11 ms；预报 1.27 ms；tick 里规划器之外的约 1.8 ms 是 bench 自己的 HOLD 偏好和风险图（L2 的替身）。
- 审计（三段合计 9 003 tick）：选中 S = 0 的 1 173 次全部包络过；core_not_enveloped 0；overrun 0；截止时间截断 182 次；命中分支超出上限置 S = 1 的行 1 862 行（第 11 波最多）；受击反应预报 117 份。
- 高负载对照（`load1`，CPU p50 72–86 %，那时还在跑 6 个召回进程、kin_check 和全套测试）：之后 8.6–11.6 / 19.2–48.4，Bell Beast 6.9–7.5 / 21.1–47.4（同一时段），之前 15.5–22.4 / 28.0–34.6。第 6 波 p50 在 86 % 负载下超过 9 ms。
- FORCED_RISK 仍然很高：这是开环（主角在数据策略的位置，常常第 1–3 帧就在支撑里，"forced_stage1" 占 forced 的 99.9 %），不能当成闭环实战的比例。第 6 波 R2 时 92 %，R3 前 90.8 %（同一负载、R2 的检出）。

### 15.6 运动学：冲刺两处、落地清后摇（只在 Forum 配装（abilities ≠ 0）下生效；Hunter 逐位不变）

- **贴墙的地面冲刺**：冲刺结束进地面 sprint 时，如果面向的墙在接触距离 + 0.05 u 之内，sprint FSM 立刻结束（Dash To Run），不做 Ground Sprint 的 0.05 u Translate。T1 的 6 次贴墙冲刺（之前把碰撞盒推进墙里、再跑出 3 u）全部对上。
- **Sprint Grace 只算地面 sprint 的时间**：空中 sprint 落地进地面 sprint 时计时清零（kin_jit 的 LAND 和估计器 `StateTracker` 两处都改）；阈值从模板的 0.3 s 改为 **0.2583 s**：地面时间 0.233 s 松键没有打滑（T2 f1190122，Dash To Run），0.283 s 打滑（s98200 f774201），取中点。注意这个阈值是从录像拟合的，与模板的 0.3 s 不一致，原因没有从模板核实（hornet_sprint 的 Sprint Timer 动作没读）【未核实】。
- **落地清后摇**（`HeroController.BackOnGround`）：落地时这一刀的斩已经结束（ATK_T ≥ thunk_off：横砍 0.192 s、上砍 0.233 s）→ ATTACKING = 0、WSLASH = 0（攻击冷却不变）。
- **kin_check**（`--params hero_reaper_forum.json --lanes bounds_lo_mix --bounds-events none`，0.5 s 窗口、0.1 u；before = 2a10a0d，after = d9dd529（阈值 0.2333、估计器未改），final = 0d735f4）：

| 集 | 类别 | before | after | final |
|---|---|---|---|---|
| T1 + T2（原留出，本轮用来找错和拟合：开发集） | dash（3 048） | 97.34 % | 98.72 % | **99.67 %** |
| T1 + T2（同上） | 全部计入（49 700） | 99.262 % | 99.346 % | 99.404 % |
| 拟合 + 开发（s98000、A、C、B、D） | dash（3 619） | 100 % | 99.83 % | 100 % |
| 拟合 + 开发 | 全部计入（87 419） | 99.064 % | 99.057 % | 99.064 % |

  其余类别（plain、wall、scramble、glide、reaper_down、contact、slope、locked……）三次完全相同：落地清后摇在这几段激励录像里没有改变任何窗口（落地正好落在斩完到后摇结束之间 0.04–0.11 s 的窗口很少；它的作用要到实战录像里看）。留出 dash 剩下 10 个窗口：T2 f1190519–526（8 个，0.32 u）和 1201973 / 1201979（各 1 个，0.17 u）。T1 / T2 这一轮用来找错（贴墙冲刺）和拟合（Sprint Grace 由 T2 f1190122 定下界），**已经不是留出集**：99.67 % 是开发集上的数，不能当作计划"kin_check dash ≥ 99 %"的留出证据；没碰过的录像上的检查见 15.11。

### 15.7 Bell Beast 回归（R3 验收 (b)）

- **Forum 开关关时逐位相同**：Bell Beast 用的 `Planner`、`Forecaster`、Hunter 运动学一行没改（kin_jit 的新规则都在 `ab != 0` 下）。录像核对（`bb_identity.cmd`：planner_bench 重放，逐 tick 记下选中的索引、名字、S、FORCED_RISK、按键、J、P、整段命令和路径的哈希）：main fe50ef9 对 R3（0d735f4），20261003_144536 i4_000 和 20261004_095304 i0_001 各 4 001 个 tick，**0 差**。
- **50 场 oracle 小批**（实例 3，冻结检出 `live_r3kin_d9dd529`，`combat_run run --instances 3 --encounter BellBeast --mode eval --policy planner --view oracle --threads 4 --real-quit 0.2 --seed 139100 --episodes 50`）：运行 `20261005_013127_BellBeast_eval_planner_oracle`，**50 / 50 CLEAR、0 WOULD_DIE**、0 次支撑外命中、规划 p99 中位 15.3 ms（最大 18.5）。之前一次（seed 139000，`20261005_012618`）在第 3 局"paused unasked"（游戏自己暂停，时间尺度 0）后停下：2 CLEAR + 1 HARNESS_FAIL，不计入。

### 15.8 重新认证（R3 验收 (d)，R0 的协议，经 MultiForecast）

代码 2a10a0d（重新锚定 + 15.2 的三处收紧；之后的提交没有动预报），R0 的生产表和余量，冻结检出 `C:\ssbot\live_r3_2a10a0d`，低优先级：

| 组 | 场 | L2 / L3 / L4 覆盖（含钩） | 钩 | 按类型 |
|---|---|---|---|---|
| dev：R0 的 107 场三分 | 107 | 229 711 / 229 711（三个滞后都是） | 1 378 / 1 378 | 9 类 100 %（own 也是） |
| fresh：R0 的 35 场 | 35 × 2 份表 | 74 585 / 74 585（每份表） | 465 | 100 % |
| fresh：R1 的 187 场（w2 幽灵已排除） | 187 × 2 | 113 385 / 113 385（每份表） | 436 | 100 % |
| fresh：13.13 的新数据去掉 2x 的 155649（130 场，含漏网那一场） | 130 × 2 | 116 102 / 116 102（每份表） | 927 | 100 % |
| 合计 fresh | 352 × 2 | 每份表 304 072 / 304 072 | 每份表 1 828 | 100 % |
| **new：没有任何构建或认证见过的场**（收集运行 `20261004_162411` ep60 起 118 场、`195019` 120 场、`195800` 119 场；全部 1x，构建器的速度保护没有去掉任何一场；`scan3.cmd` 三个并行扫描） | 357 × 2 | 每份表 180 145 / 180 145 | 每份表 1 770 | 8 类 100 %（没有 Envoy：波次起点从第 2 波起） |

**结论：按 R0 的协议（三分开发 + 两批留出 + 一批全新数据，L = 2 / 3 / 4，联合与按类型）全部 100 %，`known = True` 成立。** 记录写进 `support_margins.json` 的 `runtime_certification`：代码里 `known` 仍读该文件的 `certified`（true），它的依据现在是这次经 MultiForecast 的认证，不是 R0 那次 35 场的 SubjectRecall（13.13 推翻了它）。13.13 漏网的那一场在 fresh_r1c_1x 组里，两份表都盖住。

全部由预报本身盖住（"by forecast" = n；之前 dev 每个滞后约 1 290 次要靠待机身体管）。

### 15.9 没做完 / 未核实

- 快层没有接进实战循环（R4）：MultiForecaster + ForumPlanner + forum_supervisor_config + forum_kill_hp / forum_yellow_kill_hp 的胶水（`SupervisorInput.unpredicted_sources`、kill_prims、负重环带按 `ws.res.equipped` 切 HeroParams 和监督器配置）。
- 最后一击没有击杀分支，所以只在 I3 下放行；FORCED_RISK 用接触帧占比代替 P（`exact_p` 可开）；没有 comfort 模板；视野末的锁定检查、按键经济项不在快层里。
- 命中分支上限（32 行 / tick）在第 11 波截掉了 1 464 行有预测命中的行（S = 1）：贴着敌人时多数攻击行拿不到命中分支；要么提高上限（算力）、要么按 J 先排（现在按块的顺序）。
- 包络用 bounds_lo（计划 §4.1），kin_check 验收用的是 bounds_lo_mix（多两条收割者下劈 / 滑翔的混合时序，贵约 1.5 倍）。
- Sprint Grace 0.2583 s 是从录像拟合的，与 hornet_sprint 模板的 0.3 s 不一致，原因没核实；落地清后摇在激励录像里没有改变任何窗口，它的效果要在实战录像里看。
- 负重环带：运动学和受击后窗口都按资产值 / probes.md，bot 录像里从没装过，没有用装着它的录像核对。
- 受击反应只用 `hero_caused.json` 的 TOOK DAMAGE 出边（每 tick 最多 4 份预报）；反应的概率（闪避随被打时刻变）只进 R5 的打分。
- 开环 FORCED_RISK 高（84–92 %），主要是数据策略的主角位置；闭环比例要等 R4 的 A0 实战。

### 15.10 复现

```
cd brain   # 冻结检出（git archive，没有 .git）：behaviour_build 要加 --allow-no-sha；低优先级、NUMBA_NUM_THREADS ≤ 4
# 认证（C:\ssbot\data\m2_forum_r3\cert.cmd <dev|fresh|new> 2a10a0d）
..\scripts\uv.cmd run python -m ssbot.tools.multi_recall dev --workers 3 --json <out>
..\scripts\uv.cmd run python -m ssbot.tools.multi_recall fresh --fresh C:\ssbot\data\m2_forum_r0\fresh --fresh C:\ssbot\data\m2_forum_r2\r1 --fresh C:\ssbot\data\m2_forum_r3\fresh_r1c_1x --workers 3 --json <out>
..\scripts\uv.cmd run python -m ssbot.tools.behaviour_build C:\ssbot\data\runs\m2\<run> --encounter Forum --report-only --exclude-fights C:\ssbot\data\m2_forum_r1c\fresh\fights.json --fights-list <dir>\fights.json --contacts-only <dir> --allow-no-sha   # scan3.cmd
..\scripts\uv.cmd run python -m ssbot.tools.multi_recall fresh --fresh <new_a> --fresh <new_b> --fresh <new_c> --workers 3 --json <out>
# bench（bench.cmd <checkout> <tag>）
..\scripts\uv.cmd run python -m ssbot.tools.planner_bench --encounter Forum --multi --planner --forum --fight 20261003_074719_Forum_A_data/i3/ep0 --wave 6 --frames 3000 --threads 4 --json <out>
..\scripts\uv.cmd run python -m ssbot.tools.planner_bench C:\ssbot\data\runs\m2\20261003_144536_BellBeast_eval_planner_oracle\rec\2026-10-03\TRAIN\i4_000 --frames 6000 --threads 4 --json <out>
# kin_check（kin.cmd <checkout> <tag>）
..\scripts\uv.cmd run python -m ssbot.tools.kin_check <T1> <T2> --params ..\knowledge\1.0.30000\kinematics\hero_reaper_forum.json --lanes bounds_lo_mix --bounds-events none --json <out>
# Bell Beast：逐 tick 决策比较（bb_identity.cmd）与 50 场小批（bb_batch.cmd <checkout> <seed> 50）
..\scripts\uv.cmd run pytest -q tests/test_forum_planner.py tests/test_multi_forecast.py
```

### 15.11 审查之后的修正（fixer 轮，2026-10-05；代码 9a8b05d .. 2b3a467）

审查推翻了 15.5 的"p99 不高于 Bell Beast"（复测时第 6 波 p99 16.16 ms，前后三次 Bell Beast 13.68 / 15.65 / 13.33 ms），另有 3 条中等、7 条轻微。逐条处理：

1. **FORCED_RISK 的排序看不见命中分支的接触**（中）：之前 t_hit 和接触占比只来自不命中分支的包络，命中分支里后坐撞进支撑、或被上限截掉的行在排序里是"没有接触"。改：命中分支的接触帧并进这一行（t_hit 取两者较早的，`_note_hit`）；被上限截掉的行从命中那一帧起算在接触里。测试 `test_note_hit_puts_the_hit_branch_into_the_forced_ranking`、`test_forced_ranking_never_takes_a_row_in_contact_for_contact_free`。
2. **分母混用**（轻）：阶段 1 的行在采样帧、标称上算占比，包络过的行在全部帧、包络上算。改：前 p_k 个候选统一在**阶段 1 的帧、标称一条**上比（标称中心点查支撑，阶段 1 已经对每一行算过）或上命中分支的接触；阶段 1 的首次接触改为下界（上一个没接触的采样帧 + 1）；排序 = 接触帧占比、标称上最晚的首次接触、包络上的首次接触、J。没有另查跳过的帧：那一次支撑查询在第 6 波 p50 要 0.7 ms（试过，第一版复测里 prob_bind p50 0.06 → 0.79 ms）。
3. **受击反应只按当前状态取、锚点**（中）：改为行走在命中时刻可能所处的**所有**状态（当前状态 + 行走里最早进入时间 ≤ 命中时刻的每个状态；`_WalkCache.states`、`MultiForecaster.reaction_states`）的 TOOK DAMAGE 出边，一份预报放下全部（`forecast_reaction` 接受多个状态）。锚点：命中时刻的航位推算位置（命中目标的盒子是同一个航位推算），按待机增长和视野偏差放大，两种朝向（Reed 转身刺）；同家族另一个起始状态的反应（Reed `Stab Pos` → `Stab Antic`）以前对假设的反应**根本不放**重新锚定的那一份（re_anchor 要等下一帧导出），现在放在这个锚点盒。审查说新开始的反应"放在敌人现在的位置"不准确：之前也是航位推算到命中时刻 + 待机增长（与所有后续实例的锚点同一个模型，经过 15.8 的认证；Envoy 0.3 s 的增长 3.6 u）；锚点再按敌人的最高速放大会让 0.3 s 后的盒子宽过 COARSE_MAX_U、变成全场盒，没有这么做。真实预报（`react_box` 为空）逐位不变，认证不受影响。测试 `test_reactions_come_from_every_state_the_walk_allows_at_the_hit`。代价：反应预报从每 3 000 tick 约 37 份变成约 166 份（第 6 波）。
4. **上限决定 FORCED_RISK**（轻）：命中分支的上限（hitfx_k 32、react_k 4）按队列顺序分，队列按 J 排、J 随目标变，所以"目标下 FORCED_RISK ⇒ 默认下 FORCED_RISK"不成立。改：没有安全行时，被上限置 S = 1 的行先**不设上限**地做命中分支再判定（审计 `uncapped_ticks` / `uncapped_rows`）。属性测试 `test_forced_risk_does_not_depend_on_the_caps_order`（hitfx_k = 1、react_k = 0，3 个位置 × 6 组目标）。最坏情况没有界：每个不同的（敌人，命中帧）一份反应预报（约 0.6 ms），只在"包络全部查完仍没有安全行"时发生；开环 bench 里 0 次。
5. **只在最近 4 个目标里找第一下命中**（轻）：14 u 内的所有敌人都参加第一下命中（命中分支、受击反应的对象），只有最近 K_tgt = 4 个计分（其余权重 0：J、hits、waste 不变）。
6. **决策依赖计时**（轻）：`ForumConfig.deadline_ms = inf` 是确定模式（截止时间是唯一与计时有关的规则），`planner_bench --deadline-ms`；审计和逐位比较用它。
7. **p99（被推翻）**：逐 tick 记录（`planner_bench --ticks-json`）显示 p99 的 tick 全是"有安全行"的 tick：阶段 1 之后包络在优先部分里一直查到 11 ms 截止时间（96–160 行 + 32 个命中分支）。改：截止时间 **8 ms**，并且"下一块预计（按上一块的耗时）会超过截止时间就在它之前停"；核心行仍然总是包络。cProfile 找到的两处固定开销：命中分支里反应的支撑查询每行一次（每次约 0.37 ms）→ 每个反应一次；支撑查询里五种盒子（死亡、全场、待机管、碰撞体管、危险管）各自重建数组并各调一次核（每次查询约 0.45 ms）→ 一次构建、一次调用（与分开查的并集逐位相同，测试 `test_occupied_is_the_union_of_its_parts`）。
8. 折行（轻）：kin_jit `forum_fixed` 与 planner_bench 的两处续行恢复。
9. **模板文件**（轻）：生产模板（`*_hitboxes.npz`，157 MB，不进 git）的 sha256 写进 `support_margins.json` 的 `runtime_certification.table_files`；规范副本 `C:\ssbot\tables\forum_r3_2a10a0d`（与认证检出 `live_r3_2a10a0d` 的逐个相同）。新检出要先把它们拷进 `knowledge/1.0.30000/enemies/forum/`。
10. **kin_check 的"留出"**（轻）：15.6 表里 T1 + T2 改标为开发集。没碰过的激励录像（s98400 / s98410 / kn_excite_forum_test s98990）里只有 **1 个** dash 窗口，证明不了什么。换成一段没参与任何拟合的 **Forum 实战录像**（收集运行 `20261004_195019` i0_000，131 328 个窗口，数据策略的主角在竞技场里打）：planner_bounds 的 dash **78.45 %**（4 259 个窗口），R3 之前的运动学（2a10a0d）在同一段上完全相同（78.45 %）。R3 的冲刺修正在实战录像上没有变化；**计划的"kin_check dash ≥ 99 %"在实战录像上远没有达到**，原因没查（敌人、竞技场的斜边、受击打断都可能）【未核实】。输出 `C:\ssbot\data\m2_forum_r3fix\kin_fresh*.json`、`kin_forum_before.json`。

**复测（验收 (c)）**：冻结检出 `C:\ssbot\live_r3fix_1e45c67`（= 1e45c67，之后只加了审计计数），`C:\ssbot\data\m2_forum_r3fix\bench_fix.cmd live_r3fix_1e45c67 fix2`：同一负载下交错跑 Bell Beast、第 6 波、Bell Beast、第 11 波、第 13 波、第 6 波、Bell Beast（整机 CPU p50 29–31 %，实例 2、3 的收集在跑）：

| 录像 | tick p50 / p99（ms） | 规划器 p50 / p99 | FORCED_RISK |
|---|---|---|---|
| Bell Beast（三次） | 4.53 / 15.12、4.69 / 15.37、4.66 / 13.88 | | 2.15 % |
| 第 6 波（两次） | **6.04 / 13.49**、**5.84 / 13.51** | 3.66 / 11.41、3.45 / 11.54 | 85.9 % |
| 第 11 波 | **4.30 / 11.25** | 2.71 / 9.37 | 84.4 % |
| 第 13 波 | **4.96 / 10.88** | 3.44 / 8.57 | 91.6 % |

- 三段 tick p50 ≤ 9 ms；**p99 两次第 6 波都低于三次 Bell Beast 中的每一次**（13.49 / 13.51 对 13.88–15.37）。余量不大（0.4 ms 到最低的那次）。负载更高时没有复测（15.5 的 load1 那种 72–86 %）。
- 对照：同样的代码只差截止时间 11 ms、反应逐行查询、盒子分查（9a8b05d，`w6_base`，CPU 34 %）：第 6 波 6.60 / 16.90；第一版修正（762d90f，8 ms 但还没去掉固定开销，`fix1`）：第 6 波 7.46 / 15.12、8.34 / 17.08，Bell Beast 13.11 / 16.12 / 13.79。
- p99 的 tick（前 1.5 %）现在是：阶段 1 约 2.9–3.1 ms、包络 7.1–7.6 ms（约 64 行：核心 56 行是必查的两块）、选择（尾部检查）1.3–1.6 ms。再往下要靠计划 §4.5 的"推演与支撑融合"。
- FORCED_RISK 与 15.5 相同（开环：主角在数据策略的位置）。审计（三段 9 003 tick）：选中 S = 0 的 1 173 次全部包络过；core_not_enveloped 0；overrun 0；截止时间截断 216 次；命中分支 1 727；反应预报 341；上限截掉 258 行。
- 质量的代价：有安全行的 tick 里大多数（约 340 / 416）本来就只包络核心行和 CONTINUE（57 行），不受影响；p99 的那些 tick 从 96–160 行变成约 64 行：贴着很多敌人时，能被选上的攻击行更少（安全不受影响：S、FORCED_RISK 与截止时间无关）。

**Bell Beast（验收 (b)）**：53513b2 之后 Bell Beast 路径（`Planner`、`Forecaster`、Hunter 运动学、planner_bench 的 Bell Beast 分支）没有改动（kin_jit 只改了一处续行的空白），审查在 53513b2 上的逐 tick 比较（4 001 tick，与 main 逐字节相同）和 15.7 的 50 场小批仍然适用；三次 Bell Beast bench 的 FORCED_RISK 2.15 % 与之前相同。

**测试**：全套 1 107 passed、2 skipped、1 xfailed（tests + ssbot/tests，低优先级，6 分 12 秒）；`tests/test_forum_planner.py` 现在 22 项（含参数化）。

## 16. R4：A0 基线实战（2026-10-05，forum_planner_plan.md §5 R4；实例 0–3，fo_A，oracle）

### 16.1 接线（代码 c86b48e → ffe0e82 → b063cae，分支 worktree-wf_89d18409-0b6-1）

- `train/forum_planner_policy.py` 的 `ForumPlannerPolicy`：`combat_run --policy planner` 遇到连战遭遇（`enc.waves` 非空）时用它；Bell Beast 的 `PlannerPolicy` 一行没改。每个 STATE：`OracleBackend()`（无 boss 规格）→ `StateTracker`（Forum 配装运动学 `hero_reaper_forum.json`；`ws.res.equipped` 有 Weighted Anklet 时 `with_weighted()`，同时监督器受击后窗口 1.3 s——fo_A 没装，这条路径没跑到）→ `MultiForecaster.update`（生产表，WaveTracker 在里面）→ `MultiForecast(2 s)` → `ForumTactics` → `ForumPlanner.tick`（T 36、bounds_lo、截止 8 ms）→ `SupervisedControl.step`（`forum_supervisor_config`：worst_known_damage 2、Q4 按实例、`unpredicted_sources` = 每次未预测命中的 HIT_TAKEN 来源 iid）。`FilterContext.kill_hp = forum_kill_hp`（只在终局：最后一击按 I3）；监督器的 `kill_prims` 用 `forum_yellow_kill_hp`（kill_freeze.json 里会冻结的类型）对主角伤害上界算（初版里这条在 YELLOW、支撑已认证、h ≥ 2 时不起作用，修正轮补上，§16.5）。击杀承诺（Bell Beast 的 kill commit）在 Forum 不用（R3 没有认证击杀）。
- **多段攻击的 Final Hit 按钩子判**（与 R2 召回同口径）：多段链最后那下由主角自己的 `Roar and Wound States` FSM（`Final Hit:DamageHeroDirectly`）打出，伤害事件那一帧敌人的碰撞体可能早已不在支撑里。第一次离线回放（`20261004_154609` i0 ep0）就把 Choristor `Whip Hit 2` 的 Final Hit（钩子之后 20 帧）记成了未预测；改为在来源物体的 Control / Attack FSM 进入当前状态的那一帧（≤ 70 帧前）用 L = 3 / 4 / 2 的预报判（`_hook_of`；预报保留 90 帧）。之后回放 26 次受击（4 次 Final Hit）0 次未预测。
- **`MultiForecast.known` 修正**（ffe0e82）：第 1 波（索引 1）的两只 Choristor 在激活前 `Attack` FSM 被禁用（状态 None，§7），旧规则把"看得见、没状态"的敌人记为 unknown，所以第 0 波每一帧 `known = False`，监督器 Q3 "h = 2 and the support is unknown"。第一次实战（`20261005_044825`，22 场，**作废**）全部这样在 4–14 s 退出。现在只有"有过状态又丢了"的才算 unknown；放置不变，认证照旧有效。
- **WaveTracker**：新增 `current(t)` = BattleScene 正在跑的波（排队那一波到它规则时刻（窗口中点）就算开始；第 0 波激活前算第 0 波，因为 room.battles 从 StartBattle 起就报 wave 0）。预报用的 `wave` / `t_active` 不变（旧的"看到成员或 hi + 0.5 s"）：旧值在第 3、5、7、10、13 波比 room.battles 晚约 30 帧（这些波的成员激活后约 0.5 s 才出等待状态）。波次起点存档（`Forum_A_w<i>`）的 wake 从第 i 波开始（b063cae）。
- `combat/tactics/forum_local.py` + `knowledge/1.0.30000/playbooks/Forum.yaml` v0（LOCAL 战术）：HEAL（Q1a：h ≥ 2 未满血、丝 ≥ 9、原地 Bind 提交测试通过；没有安全点，口袋在贴墙 Bind 核实前不当回血点）、Q6（h ≥ 2 未满血、丝 < 9：钉子命中权重 ×1.5）、LEAVE（口袋规则 (2)：人在口袋、有面朝左且 transform x ≤ 18 的 Clapper → 下墙）、EVADE（主角位置的支撑 t_min < 0.6 s）、ENGAGE（最近的敌人按距离 / 权重；Clawmaiden 在场时只打它；Bellbearer、Maestro 远于 8 u 权重 0.4；Minister `Parry Stance / Parry Block`、Reed `Defend / Block` 的命中权重 −1）、HOLD（无人在场）。口袋规则 (1)（有 Clapper 本体左沿 ≤ 14.6 时，x < 16 的站位加罚）只影响站位（A0 没有爬墙宏）。Cogfly 默认：第 6 波 2 次、终局 2 次，只在地面站定、所选计划 S = 0、主角位置支撑 t_min ≥ 1.0 s 时按 上 + 快速施法 2 帧（投掷硬直不在运动学模型里，规划器的前缀里去掉这两帧的键）。
- 工具：`forum_policy_replay`（开环回放，同时编译冻结检出的 numba 缓存）、`forum_a0_report`（§6.3 指标）。

### 16.2 A0：50 场完整连战（`20261005_045446_Forum_A_eval_planner_oracle`，冻结检出 `C:\ssbot\live_r4_ffe0e82`，种子 150000+，eval、真退出 0.2，实例 0–3 各 13 场 = 52 场；报告 `C:\ssbot\data\m2_forum_r4\a0_report.json`）

| 指标 | A0 |
|---|---|
| 结果 | **QUIT 52 / 52**（全部 Q3：h = 2 且支撑里有多段事件——Reed 49 次、Choristor 3 次）；CLEAR 0、WOULD_DIE 0、STUCK 0、HARNESS_FAIL 0 |
| 到达的波 | 52 场全在第 0 波（Reed + Envoy + Choristor）退出；开战到退出 p50 10.1 s、最长 19.4 s |
| 受击 | 每场 2.42 次（按 damage 事件：126 个），掉血每场 3.0；另有 30 个多段链的 Multihit tick（special_damage / TakeQuickDamage，也是 HIT_TAKEN，但自身没有来源，单独计）。按 damage 事件的来源（修正轮按调用路径解析）：Envoy（Song Pilgrim 01）49、Reed 40（本体 24 + `Song Reed Pin Projectile` 16）、Choristor（Song Pilgrim 03）37，未解析 0。（初版写的"Envoy 49、Choristor 37、Reed 24、未解析 46"数的是 156 个 HIT_TAKEN，46 = 30 个 tick + 16 根针，不是 Final Hit：24 个 Final Hit 都有来源） |
| **支撑外命中** | **0**（未知 0；24 次多段 Final Hit 按钩子判，全在支撑内。30 个 tick 里 7 个后面没有 Final Hit——5 个是 10–16 帧后场次结束，2 个还剩 261 / 385 帧——初版的实战记账只通过 Final Hit 判 tick，这 7 个没判；验证者离线逐帧判了全部 156 个掉血事件（含 30 个 tick），0 个在支撑外。修正轮起 tick 单独判，§16.5） |
| FORCED_RISK | 第 0 波 86.6 % 的 tick（23,461 / 27,090），每分钟 17.5 段；选中 S = 0 的计划 3,629 次，全部做过包络（审计相等，core_not_enveloped 0） |
| 模式 | EVADE 100 %（主角位置的 t_min 一直 < 0.6 s）；监督器 tick 里 YELLOW 83 %、GREEN 13 %、RED 4 % |
| 击杀 | 52 场共 1 次（AltSlash）；Bind 0、Cogfly 0（第 6 波没到） |
| tick | 每场 p50 的中位数 7.4 ms、p99 的中位数 15.4 ms（最大 21.6）；规划 p50 3.1 ms / p99 10.4 ms；> 16.7 ms 的 tick 1.0 %（279 / 28,170） |
| 真退出 | 13 次：13 次暂停、13 次到主菜单、错误确认 0 |
| WaveTracker 对 room.battles | 实战 28,170 / 28,170 帧一致（只有第 0 波）；离线整场回放（`154609` i0 ep0，14 波，43,917 帧）43,900 帧一致（99.96 %）：开战第一帧（回放没有 tap，实战有）、第 3 波早 3 帧、第 5 波早 13 帧——跟踪器在致命一击那一帧计死亡，BattleScene 的 DecrementEnemy 在 HealthManager.Die 里，可能在击杀冻结之后【推测，未逐帧核对】 |

- **结论**：框架、记账、决策日志、真退出都正常，支撑外命中 0；但 A0 打不过第 0 波：三只敌人（Reed 扔针 / 刺 / 多段、Envoy 冲锋、Choristor 鞭）同时在场时 0.6 s 视野里几乎找不到不碰支撑的计划（86.6 % FORCED_RISK，这是闭环数字，与 R3 开环的 85–92 % 一致），按"接触帧占比"挑的计划仍在 10 s 内挨 3 下（7 → 4 HP），h = 2 时 Reed 的多段（2 段）在支撑里 → Q3 退出。战术基本没机会出 ENGAGE（EVADE 一直成立），52 场只打死 1 只。
- 决策日志（`decisions_i<N>.jsonl`）每次受击前 90 tick 都在：典型序列是 CONTINUE / MOVE+跑+出刀 都是 S = 1、`n_safe = 0`（400 行里一行安全的都没有），挨打那一帧才因为无敌帧回到 S = 0。

### 16.3 补充：从波次起点打（`20261005_050427_Forum_A_w2_mix_eval_planner_oracle`，冻结检出 `live_r4_b063cae`，实例 0、1 各 12 场，12 个波次起点轮转，eval、无真退出；报告 `ws_report.json`）

完整连战全停在第 0 波，后面各波的数字从这里来（波次起点没有助战、没有前面波次的残余，见 §13.1）：

| 指标 | 结果 |
|---|---|
| 结果 | QUIT 24 / 24（Q3 14：h = 2 且有多段事件——Minister、Reed、Choristor；Q1 10：h = 1 时受击后窗口里退出） |
| 受击 | 每场 3.04 次（attempt 行共 73 次；策略看到 72 个 damage 事件，差的 1 次在策略最后一个 tick 之后），掉血 4.1；另有 11 个 Multihit tick（第 3 波 1、4 波 4、8 波 1、9 波 3、11 波 2）。按 damage 事件、按真波：3 → 12、4 → 2、5 → 7、6 → 12、7 → 6、8 → 5、9 → 3、10 → 8、11 → 4、12 → 6、13 → 7；来源（按调用路径解析）：Clawmaiden 22（本体 15 + 矛 7，第 3、5、10 波）、Song Automaton Tiny 14、Clapper 13（本体 7 + rune bomb 5 + rune slam 1）、Reed 12（含针 5）、Minister 4、Bellbearer 3（Throwing Bell）、Choristor 2、未解析 2（`Colliders/Collider ParryStance`、`Colliders/Collider Fly`）。（初版的按波数字数的是 83 个 HIT_TAKEN = 72 + 11 个 tick） |
| 支撑外命中 | **0**（多段 Final Hit 6 次按钩子判；验证者离线判了全部 83 个掉血事件，0 个在支撑外） |
| FORCED_RISK（按真波的 tick 占比） | 2: 100 %（只有 149 tick）、3: 92.8 %、4: 95.4 %、5: 94.1 %、6: 87.4 %、7: 68.7 %、8: 84.7 %、9: 90.7 %、10: 94.1 %、11: 90.6 %、12: 93.1 %、13: 65.3 %（终局两只 Clapper，1,107 tick）；范围 65–100 %（初版写的 69–95 % 漏了第 2、13 波） |
| 战术 | EVADE 96 %、HOLD 3 %；目标按 tick：Clawmaiden 17,767、Tiny 3,432、Minister 2,496……；Cogfly 投 2 次、Bind 0、击杀 2 |
| tick | p50 中位数 7.4 ms、p99 中位数 12.9 ms（最大 18.5） |
| WaveTracker | 30,117 / 30,543 帧一致（98.6 %）：不一致全在波次起点的开头 10–113 帧（跟踪器从 wake 起算第 i 波，但 wake 已被 intro 挪到这一波的激活时刻，`start()` 又加了一次 startDelay；完整连战不受影响）和第 3 波起点的前 10–17 帧 |

### 16.4 R5 / R6 要解决的

1. **FORCED_RISK 太多（A0 第 0 波 87 %，波次起点各波 65–100 %，多数 85–95 %）**：几只待机敌人的支撑并集（含 3.0 u 的搜索上限余量：Reed 针、Clawmaiden 矛、Minister 格挡、Tiny 冲撞、钟、rune bomb；Envoy 冲锋 2.96 u，§12.2）在 0.6 s 视野里盖住主角能到的几乎所有地方。R5 的终点价值（E / trapped / H_exp）要把主角提前带出"所有出口都会关上"的位置；余量本身（留出残差 p99.9 代替搜索上限）是更大的杠杆，但要重新认证。
2. **Q3 在 h = 2 时因多段事件退出**（A0 52 / 52，波次起点 14 / 24）：Reed、Choristor、Minister 的多段攻击几乎一直在支撑里，所以 7 面具的主角挨 3 下（7 → 4 HP）就退出。是否放宽 Q3（例如只算主角 t_min 内够得着的多段事件）是 §9 第 2 个决定（你来定）；R5 的 H_exp 项要让主角远离多段源。
3. **挨打的节奏**：每 3–5 s 一下，主要是 Envoy 冲锋、Choristor 鞭、Clawmaiden 本体和矛；按接触帧占比挑出的 FORCED_RISK 计划会边跑边出刀（`MOVE+run+attack`），这类计划在 FORCED_RISK 时应当降权（R5 的 r̂ / P'）。
4. **几乎不出手**（76 场共 3 次击杀）：EVADE 一直成立，ENGAGE 没机会；R6 的 BAIT / FOCUS / SPLIT 和惩罚窗口要在"安全出刀空档"里出刀。
5. WaveTracker：致命一击和 BattleScene 计死亡之间的几帧（§16.2）、波次起点的 startDelay 重复（§16.3）。

### 16.5 R4 修正轮（核查之后）

- **YELLOW 的逐敌击杀冻结规则以前不起作用**（计划 §4.4 第 7 条）：监督器在"支撑已认证且 h ≥ 2"时保留 `kill_prims`，把击杀交给 L0 过滤器认证（Bell Beast 的做法）；但 Forum 给过滤器的 `kill_hp = forum_kill_hp` 在终局之前是 None（过滤器就不查击杀），R3 也没有击杀分支，所以两层都不拦普通击杀——击杀冻结可能吃掉暂停。修正：`SupervisorConfig.kills_certifiable`（默认 True，Bell Beast 不变），`forum_supervisor_config` 设 False → YELLOW / RED 时不管支撑和 h，一律去掉会打死"击杀会冻结"的敌人的伤害原语（`forum_yellow_kill_hp`）。GREEN 不变（终局最后一击仍由过滤器按 I3 拦）。测试：YELLOW、已认证、h = 2、Envoy 5 HP → 侧斩 / 上斩被拿掉。A0 里 `kill_prims` 平时只有 Clawline / 道具（伤害上界无限），钉子要等敌人 HP 估计降到 Reaper 一刀以内才会进来，所以对 A0 这种几乎不出手的基线影响很小。
- **记账**：(1) 来源 iid 按调用路径配对（以前按下标配，被格挡的 damage 事件会错位）；(2) 多段链的钩子按实例找（FSM 事件的 `ent`；以前按物体名，两只同名 Reed 会串，`Wave 1/Song Reed/...` 这种嵌套路径找不到钩子），没有 iid 或找不到时按路径里的物体名回退；(3) Multihit tick（special_damage 掉血）在自己那一帧判，不在支撑里就等 70 帧看有没有本链的 Final Hit（有就随链在钩子判），没有或场次先结束就计为支撑外（以前只通过 Final Hit 判，没有 Final Hit 的 tick 根本不判）；(4) Cogfly 第二帧在 FORCED_RISK、暂停待定或监督器接管按键时丢掉（以前照按）。
- **报告**：`forum_a0_report` 按 damage 事件计受击，tick 单独计，类型按调用路径解析（投射物归投掷者：针 → Reed、钟 → Bellbearer、rune bomb / slam → Clapper、矛 → Clawmaiden）；旧记录没有 kind / path，从录像的 events.jsonl 读。修正后的 A0 / 波次起点数字见 §16.2 / §16.3（`C:\ssbot\data\m2_forum_r4\fixer\a0_report_v2.json`、`ws_report_v2.json`）。
- **复测**（波次起点批次重跑一次：`20261005_054233_Forum_A_w2_mix_eval_planner_oracle`，冻结检出 `C:\ssbot\live_r4f_0f517a0`，实例 0、1 各 12 场，种子 170000+，eval、无真退出；报告 `C:\ssbot\data\m2_forum_r4\fixer\ws_report_fix.json`）：QUIT 24 / 24（Q1 12、Q3 12：Reed 6、Minister 4、Choristor 2）；每场 3.33 次受击（80 个 damage 事件）+ 6 个 Multihit tick（全部在自己那一帧就在支撑内）；**支撑外 0、未知 0**（4 个 Final Hit 按钩子判，钩子都找到了，包括 iid 解析不出来的 `Song Reed (1)` / `Song Administrator (1)`，靠物体名回退）；来源 Clawmaiden 27、Tiny 16、Clapper 13、Reed 9、Bellbearer 7、Minister 3、Choristor 3、未解析 2；FORCED_RISK 90.5 %（各波 69–100 %）；EVADE 98 %、HOLD 2 %；YELLOW 下 `kill_prims` 含钉子攻击的 tick 被拿掉攻击（日志里 1,480 个 YELLOW tick）；击杀 0（上一批 2）；Cogfly 2 次；tick p50 中位数 7.4 ms、p99 中位数 14.0 ms（最大 18.9），> 16.7 ms 0.45 %；WaveTracker 29,522 / 29,970（98.5 %，同 §16.3 的波次起点偏移）；包络审计：选中 S = 0 的 2,794 次全部包络，core_not_enveloped 0、overrun 0。结论：修正没有改变基线的样子（还是 EVADE、还是第一波里 3 下左右退出），记账现在每个掉血事件都判。
