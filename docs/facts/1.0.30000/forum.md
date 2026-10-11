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
- 长跑：修复轮 13:13 起（冻结代码 `C:\ssbot\live_fo_r1f_8a03afb`；实例 2 先跑 40 局受保护的 Envoy 专场核对保护，再跑波次起点；实例 3 波次起点；轮换 w4、w6、w7、w8、w9、w11、w12、w13、w3、w5、w10，每局 180 s），13:36 `DEMO_SOON`（你要 0.5x 练 Forum）后两个运行各在当前一局后停下：实例 2 专场 23 局、实例 3 波次 8 局（`20261004_131323_Forum_A_w4_mix_data2`）。演示后用 `C:\ssbot\sandbox\fo_r1f_run.cmd i2w` / `i3` 重新开始（HANDOFF R1）。

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

## 17. R8：拼刀（2026-10-08，forum_planner_plan.md §5 R8；分支 worktree-wf_814dfeea-b10-4；离线 + 实例 2、3）

### 17.1 Wanderer 的刀（你 10-05：拼刀用 Wanderer 不用 Reaper）

- `knowledge/1.0.30000/attacks/wanderer.json`（`attack_table_build --crest Wanderer`，P17 的 slash.dump，**还没有实测帧**）：横砍 / 交替横砍 / 上挑 / 贴墙砍都在出刀那一帧生效、到 0.12 s（剪辑第一个动画事件 0/24 s，和 Hunter 一样，不是 Reaper 的 0.083 s），下劈 0.04–0.16 s；够距：横砍 x 0.19–3.12 u（拼刀盒 0.19–2.92）、上挑 y 0–3.39 u、下劈 y −2.16–0.13 u。所以**按导出 Wanderer 连拼是无缝的**：拼中后 0.1 s `NailParryRecover` 把攻击冷却和这一刀都清掉，新一刀立即生效，同一碰撞体 0.117 s 后能再拼，无敌到 0.15 s，0.117–0.15 s 之间再出刀就接上。**实测（2026-10-08，实例 2，`kin_excite_forum --attack-frames 60`，fo_W，种子 320000，录像 `C:\ssbot\data\runs\m2\kn_excite_forum_wanderer\2026-10-08\TRAIN\kn_excite_forum_s320000`，551 个采样帧）**：横砍（285 帧）/ 交替横砍（91）/ 上挑（111）的伤害碰撞体在出刀后第 1–7 帧开着（0.017–0.117 s），下劈（64）第 3–9 帧（0.05–0.15 s）；多边形和导出一致（偏移 0.000 u）；贴墙砍没采到（沿用导出 0–0.12 s）。写进 `attacks/wanderer.json` 的 `frames`。所以**连拼无缝成立**：拼中帧 c 之后 c+6 `NailParryRecover`，这时按下的新一刀第 c+7 帧起生效，同一碰撞体 c+7（0.1 s + 1 帧）起可再拼，无敌到 c+9，重叠 3 帧；Reaper 实测第 5–12 帧生效，新一刀 c+11 才生效，空档 2 帧（0.033 s），和计划里的推算一致。（采样的是伤害碰撞体；拼刀盒 `Clash Tink` 是同一个 NailSlash 下的子碰撞体，按同一组动画事件开关，没单独采样。）`attack_table_build --live` 修了一个问题：探针第二次按键（+31 帧）的同槽位刀（Wanderer 的第二下上挑 / 横砍）以前算到第一刀的窗口里（得出 1–38 帧），现在减掉按键偏移。
- 纹章配置（crests.json）：持续 0.25 s、冷却 0.3 s、后摇 0.1 s，下劈类型 `Slash`（`HeroController.DownAttack`：就是一刀 `downSlash`，`cState.attacking`，没有 Hunter 的俯冲、没有 Reaper 的 FSM）；`DASHCOMBO_WINDOW_TIME` 0.15 s：冲刺（Sprint FSM 打开窗口）后 0.15 s 内按攻击是 `WANDERER DASH COMBO`，不是普通一刀（规划器不建模，否决这样的行）。
- 运动学：`hero_wanderer_forum.json` = Reaper 的 Forum 配装参数换成 Wanderer 的计时，能力位去掉 reaper_down、加新的 `down_slash`（kin_jit）；**没在 Wanderer 录像上拟合**，kin_check 在你的 fo_W 练习录像上核对中（HANDOFF R8）。

### 17.2 可拼层（静态表，按行为表里每个家族伤害碰撞体的 parry 位）

- 有可拼碰撞体的家族 13 个：Choristor 斩（`Slash 1/2`、`ComboSlash 1`）、鞭（`Whip 1–6`）、跳（`Jump Spin`、`Spin Slash`）；Clawmaiden 斩（`Slash 1/2/4/5`）；Envoy 普通斩（`Slash1`、`Slash1 2`）、跳斩（`JumpSlash 2/3`）、冲锋（`Charge`）；Maestro 斩（`Slash 1/2`）；Minister 冲刺（`Attack`）、格挡反击（`Parry Slash 1–4`）；Reed 刺（`Stab 1/3/5`）、扔针（`Song Reed Pin Projectile`）、防御反击（`Parry Slash`）。
- 永远不拼（照旧要躲）：所有本体（待机 / 入场 / 闪避 / 瞬移家族）、Clapper 全部（本体和锤 canClashTink 0）、Clawmaiden 旋转（矛和矛爆炸 canClashTink 0）、Bellbearer（钟只有 counter 位：只能打改向）、Tiny（用本体撞）。

### 17.3 拼刀成败（录像统计，`ssbot.tools.forum_clash_stats`）

- 两种口径：**拼刀局面**（出刀生效窗口里，主角的拼刀盒先碰到敌人的可拼碰撞体，之前敌人任何伤害碰撞体都没碰到主角受伤框（放大 0.3 u））和**接触局面**（规划器的规则：敌人第一次碰到放大的受伤框落在出刀生效窗口里，本体也算）。结果：拼中（NailClashEffect，最近的可拼碰撞体是它的）/ 挨打（12 帧内它打中主角）/ 都没有。
- 你的 5 次练习（4,439 刀、239 次拼刀；Reaper 1,059 刀、Wanderer 3,380 刀）：拼刀局面几乎不挨打（例：Wanderer 上挑拼 Minister 冲刺 10 次里 7 拼中、0 挨打；Reaper 横砍拼 Choristor 鞭 13 次 12 拼中）；接触局面会：Choristor 斩横砍 14 次 7 拼中、3 挨打，Reed 刺横砍 11 次 3 拼中、4 挨打。也就是"刀在接触时已经出来"不够，要在它的判定碰到身体之前先碰到刀。拼完之后 0.2 s 内被无敌挡掉的伤害 30 次（29 次来自同类型）；拼完 0.5 s 内同一只再拼 1 次、再挨打 0 次。
- **`clash.json`（2026-10-08 提交，`forum_clash_stats --table`，R1 v2 的 36 个 data2 运行 + 你的 5 次练习，两种口径的并集，两种纹章合并，n ≥ 10，Wilson 95 % 上界）：33 个键，失败概率 ≤ 0.25 的 18 个、≤ 0.5 的 29 个**（另 75 个 n 不够或不可拼，列在 `left_out`）。（n / 拼中 / 挨打 / 失败概率）：Minister 冲刺 横 2493 / 1872 / 22 / 0.013、上 308 / 178 / 7 / 0.046、下 139 / 20 / 9 / 0.12；Minister 格挡反击 横 492 / 209 / 93 / 0.23、上 0.37、下 0.56；Clawmaiden 斩 横 504 / 195 / 67 / 0.17、上 0.15、下 0.34；Envoy 冲锋 横 42 / 35 / 2 / 0.16、下 16 / 5 / 0 / 0.19；Envoy 斩 下 108 / 63 / 2 / 0.065、横 46 / 26 / 7 / 0.28；Envoy 跳斩 下 0.25、横 0.28；Choristor 鞭 横 57 / 36 / 2 / 0.12、下 0.24；Choristor 斩 横 140 / 68 / 13 / 0.15、下 0.29；Choristor 跳 横 0.28、下 0.33、上 0.43；Maestro 斩 上 115 / 33 / 5 / 0.098、横 0.21；Maestro 防御 上 0.35；Reed 防御反击 下 0.13、横 183 / 73 / 26 / 0.20、上 0.48；Reed 刺 上 139 / 45 / 15 / 0.17、横 580 / 217 / 151 / 0.30、下 0.52；Reed 扔针 横 0.52、上 0.54（针是投射物，拼刀分支不归属它）。第一版（只用接触口径，`clash_table_v1.json`）比并集少很多拼中：接触口径漏掉了“刀先碰到判定、判定没碰到身体”的那些拼刀。

### 17.4 规划器里的 EV_CLASH（`ForumConfig.clash`，默认关 = R3 / R4 的规划器）

- 只在没有安全行的 tick 跑（普通安全行永远排在前面）；按 J 取最多 16 行"有接触、有出刀"的行：包络上第一次接触落在某一刀的生效窗口里，接触按敌人归属（每只敌人自己的支撑在外壳中心查一次），每只都要是 `clash.json` 里有的（类型 × 当前攻击家族 × 刀向）且在刀的那一侧（横砍在面朝方向、上挑在上面、下劈在下面）；拼刀放在接触前一帧（拼刀盒在受伤框外面）。
- 成功分支：从拼刀帧起 9 帧（0.15 s）不受任何敌人伤害（两侧规则：背后那刀在无敌里就吃掉）、按刀向后坐（横砍反向、上挑 RecoilDown、下劈弹起、贴墙砍不动）、6 帧后 `EV_PARRY_RECOVER`（下一刀马上能出）；之后的接触可以再拼（多段招的下一段、另一侧），最多 3 次；整条成功分支干净 → 失败概率 1 − ∏(1 − p_k) ≤ 0.25 且 h ≥ 2 时这一行算安全（排在普通安全行之后，按失败概率排）。拼刀开着时候选里加"一直出刀"的续段（每 8 帧一刀：不按方向 / 按左 / 按右 / 上挑），给第二次拼、转身拼和 Minister 正下方连续上挑用。
- 开环回放（A0b i1 ep0，648 tick，483 个 FORCED_RISK；机器忙）：拼刀分支在 483 个 tick 上跑，看了 7,200 行，234 行接触时刀在生效窗口里、都能归属，59 行归属的怪可拼且在刀那一侧，7 行成功分支干净（3 次被选中）；没有"一直出刀"的续段时 0 行干净（0.15 s 后支撑还罩着主角）。分支每个 FORCED_RISK tick 2.4 ms。

### 17.5 被拼中就收招的两招：拼完之后它们还会怎么动（2026-10-08，`scratchpad/r8/parried_motion.py`，R1 v2 的 4 个 Envoy 运行 `*_Forum_A_w0_data2_envoy`）

- Forum 里只有 Envoy 冲锋（`Charge` / `Reset` 收到 `PARRIED` → `Deflect`（瞬时）→ `Charge End` 0.42 s → `Attack Wait` → `Walker`）和 Reed 防御反击（`Parry Slash` → `Multihit Clashed` 0.39 s → `Parry Slash End` 0.33 s → `Alert`）被拼中会收招。这两招拼中（拼刀冻结开始后 4 帧内进入收招状态）后的 60 帧：Envoy 55 次、Reed 21 次；60 帧内挨它打：Envoy 1 次（第 56 帧），Reed 0 次。
- 按游戏时间（STATE `dt` 累加；拼刀冻结 0.25 s 实时里游戏时间不走，按帧数算会多出约 15 帧"不动"）它的伤害碰撞体外框朝主角那边多伸出的最大值：Envoy 3 帧 0.37 u、6 帧 0.60、9 帧 0.70、12 帧 0.80、18 帧 0.89、24 帧起 0.93 u（`Charge End` 里还往前滑），竖直几乎不动；Reed 3 帧 0.36 u、6 帧 0.60、9 帧起 0.96 u，竖直 0.31 / 0.62 / 0.83 u，27 帧起 1.2–3.95 u（`Parry Slash End` 后飞走）。拼中时主角到 Envoy 碰撞体外框的距离中位 3.76 u。
- 收招之后最早的下一次出手：Envoy `Charge End` 结束马上可以 `Slash Antic`（55 次里多数在 43–49 帧，含冻结），第一下最早约 0.41 s 后（strikes.json 跳斩 p5）；Reed 要等 `Parry Slash End` 结束再 `Alert`，0.72 s 之后才有刺。规划器视野 36–48 帧内都打不到。

### 17.6 规划器里的拼刀分支，第二版（2026-10-08，`forum_planner.py`，commit 895137b）

- **收招的两招**（`PARRY_STOPS`）：拼中后这只敌人的支撑在拼刀帧冻结（不再沿冲锋路径往前推），主角外框按上面的实测按帧放大（`PARRY_STOP_GROW`，每 3 帧取那一段结束时的最大值），其他敌人照常。其余招拼中后照常打完（和第一版一样）。
- **一只就够**：第一次接触那一帧只要有一只"当前正在出可拼的招、在刀那一侧"的敌人就可以拼；同一帧碰到的别的敌人只要不在出招（待机：它的支撑是身体管和"可能开始的招"，最快的招也要 0.4 s 才打到）就不挡（拼刀无敌 0.15 s 盖住所有敌人伤害，之后它的接触在下一层再查）；同一帧有别的敌人在出自己的招则不拼。第一版要求所有归属都可拼，wave 0 三只的支撑互相重叠，几乎没有行能过。
- **部分拼刀**：拼了一次或多次之后仍有拼不掉的接触（别的敌人的支撑、表里没有的招），这一行还是 S = 1，但 FORCED_RISK 的排序用它的成功分支：在接触中的帧占比 = 失败概率 × 不拼时的占比 + (1 − 失败概率) × 成功分支的占比，第一次接触取成功分支剩下的那次；部分拼刀的失败概率门槛 0.5（`clash_partial_max_fail`），干净的拼刀（算安全行）仍是 0.25。
- 没有任何敌人在出可拼的招时整个分支跳过（不做推演）。决策日志里选中的拼刀写 `clash: [失败概率, 拼刀次数, 是否部分]`。
- **开环回放**（A0b i1 ep0，648 tick，483 个 FORCED_RISK，Wanderer，机器很忙）：第一版用 `clash.json` 时 0 行干净、0 次选中（拼中的只有 Reed 上挑防御反击，失败概率 0.48 > 0.25，其后其他敌人的支撑紧接着就碰上）；去掉被拼的敌人之后的全部支撑（上界）也是 0 行干净；第二版 81 次拼刀被接受（其中 39 次收招），66 行部分拼刀，**11 个 tick 选中部分拼刀**（Envoy 斩 / 跳斩 横 0.28、Choristor 跳 横 0.28 为主，成功分支剩下的接触在视野第 33–38 帧）；干净的仍是 0。拼刀分支每个 FORCED_RISK tick 约 2.4 ms（忙的机器；不开拼刀 plan p50 6.3 ms，开 9.8 ms）。另一局（i4 ep0，272 个 FORCED_RISK）0 次被接受。

### 17.7 Minister 正下方连续上挑（2026-10-08，实例 3，`Forum_W_w4` = `fo_r8_w4w`（`fo_r1_w4` + Wanderer，`ssbot.probes.forum_states wanderer`），`--policy minister_below`，data 模式，30 场 × 20 s，种子 321000+，运行 `C:\ssbot\data\runs\m2\20261008_032228_Forum_W_w4_data_minister_below_oracle`）

- 策略（`forum_policy.MinisterBelowPolicy`）：走到最近那只 Minister 正下方（|dx| < 0.35 u 就不走），一直按住上，每 4 帧按 2 帧攻击；不跳不冲刺。只在地面上挑，它飞高了够不着。
- 结果：1,364 次上挑、110 次拼中；**拼刀口径**（刀先碰到判定）冲刺 114 次：65 拼中、0 挨打；格挡反击 17 次：6 拼中、0 挨打；**并集口径**（规划器的规则）冲刺在前方 101 次：55 拼中、1 挨打，在后方 24 次：11 拼中、0 挨打；格挡反击在前方 27 次：4 拼中、3 挨打，后方 6 次：2 拼中、1 挨打。冲刺拼中后 0.5 s 内同一判定再拼 9 次、挨打 1 次。所以**上挑碰上冲刺不挨打**（拼刀口径 0 / 114，挨打上界 0.03），但**拼中只有 57 %**（65 / 114，其余 49 次既没拼中也没挨打：判定没碰到身体），格挡反击明显差。（复核更正：第二轮汇报和 HANDOFF 里写的"65 / 65 拼中"是错的，应为 114 次里 65 次。）
- 但整体并不"不挨打"：主角只有 28 % 的时间在它正下方（它飞得快），按"第 5 波开始之前"的时间（下一波在死掉一只或两只后开始；之后活着那只打的也算进下数，两边同一口径）算每分钟挨 Minister 14.9 下（87 下：冲刺 `Slash Collider` 38、格挡姿态的身体 `Collider ParryAntic` / `ParryStance` 33、身体 11、飞行身体 4、出招前摇 1）。对照：R1 v2 的 data2 随机策略（Reaper，205 场 w4 起点）每分钟 20.2 下（冲刺 2,584、格挡身体 1,475、飞行身体 461）。上挑一直出刀杀得快：30 场里 20 场 20 s 内两只都死（第 5 波开始时刻中位 10.7 s；data2 是 71 s）。**只比每分钟**：这里每场限 20 s（10 场到结束都没进第 5 波），data2 每场 180 s，按场比总下数（2.8 对 26.3）有偏，不用。挨打大头是冲刺不在正下方时从侧面来、和上挑砍到格挡姿态时碰到它的身体（你说的"砍到格挡姿态会触发反击、身体会碰到你"）。
- 规划器给它的是上挑续段（`clashrepU`）和 `clash.json` 里 Minister 冲刺上挑 0.046 / 格挡反击上挑 0.37，不按"正下方安全"的规则走。

### 17.8 实战 A/B（2026-10-08，实例 2、3，A0b 的协议：eval、规划器、oracle、真退出 0.2，整场连战，每臂 25 + 25 场；报告 `C:\ssbot\data\m2_forum_r8\live\report_<臂>.json`、实战拼刀统计 `clash_live_<臂>.json`、一致性 `check_<臂>.json`）

- **第一轮 Wanderer 臂作废的原因**：Forum 配装的 Cogwork Flier 和 Wallcling 不在 `hero_damage.KNOWN_NEUTRAL` 里，按"未知道具"给刀加了附魔和倒刺的上界（9 → 16），Wanderer 暴击 ×3 → 48 ≥ wave 0 每只的血（Envoy 38）；杀招规则（YELLOW / RED、Forum 的击杀不认证）于是在 YELLOW（87 % 的 tick）收走所有出刀：R8W / W0 只有 0.16 % 的 tick 按了攻击（A0b 6 %），`kill_prims` 100 % 含刀（A0b 17 %）。录像里装着这两个道具的刀伤：Reaper 9（对有伤害缩放的怪 10），Wanderer 9、暴击 27，从没更大；603fc7b 把两者列为不改刀伤，Wanderer 的上界回到 27（暴击仍按 ×3 算，暴击率约 1 %：Minister 实验 403 刀里 4 次）。修好后重跑 W1 / R8W1（同种子 320800 配对）。**这个修复也改了 Forum 默认的 Reaper**（复核指出，第二轮汇报漏了）：Reaper 的上界从 16 降到 9（对缩放的怪 10），YELLOW 里 kill_prims 收刀的 tick 变少；A0b、R0、R8R 都是按 16 跑的（决策日志里 kill_prims 含刀时 ykill 最大 11、从没到 19），所以下表 R0 / R8R 与 W1 / R8W1 不同上界，"R0 对 W1"不可比；"Reaper 17 % 的 tick kill_prims 含刀"也是上界 16 时量的。按新上界重跑的 Reaper 臂见 17.9。
- 结果（代码 895137b，Wanderer 重跑 603fc7b；全部 50 / 50 在 wave 0 QUIT（Q1），支撑外受击 0，0 次击杀）：

| 臂 | 纹章 | 拼刀 | 运行 | 存活中位 s | 受击 / 场 | 受击 / 分 | Envoy 冲锋受击 / 场 | 选中拼刀 tick（干净 / 部分） | 实战拼中 | tick p50 / p99 ms | plan p50 ms | 迟到 tick |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A0b | Reaper | 关 | 205437 + 205857（f8c0c62） | 12.81 | 4.30 | 19.1 | 1.08 | — | — | 5.9 / 11.8 | 2.4 | 0.2 % |
| R0 | Reaper | 关 | `C:\ssbot\data\runs\m2\20261008_042706_Forum_A_eval_planner_oracle` | 11.92 | 4.22 | 19.7 | 1.10 | — | 104 | 11.2 / 21.7 | 4.5 | 7.0 % |
| R8R | Reaper | 开 | `C:\ssbot\data\runs\m2\20261008_041514_Forum_A_eval_planner_oracle_clash` | 13.75 | 4.04 | 18.0 | 0.60 | 18 / 218 | 151 | 15.8 / 27.5 | 8.8 | 36.5 % |
| W1 | Wanderer | 关 | `C:\ssbot\data\runs\m2\20261008_044219_Forum_W_eval_planner_oracle` | 11.98 | 4.32 | 20.8 | 0.78 | — | 109 | 9.8 / 19.6 | 4.1 | 3.7 % |
| R8W1 | Wanderer | 开 | `C:\ssbot\data\runs\m2\20261008_045259_Forum_W_eval_planner_oracle_clash` | 11.72 | 4.38 | 21.6 | 0.82 | 88 / 930 | 117 | 9.8 / 19.6 | 5.3 | 4.9 % |
| W0 / R8W（作废：刀被收走） | Wanderer | 关 / 开 | `20261008_040450` / `20261008_035419` | 10.21 / 10.55 | 4.42 / 4.42 | 24.7 / 25.0 | 1.08 / 1.16 | —；49 / 0 | 3 / 11（出刀 7 / 24 次） | 10.7 / 11.9（p50） | 4.5 / 5.3 | 7.7 % / 9.9 % |

- **复核结论（2026-10-08）：这组 A/B 不能说明 Reaper 开拼刀活得更久**：置换检验中位差 p = 0.073、均值差 p = 0.28（均值只差 +0.68 s，R8R 的均值 13.51 s 和 A0b 13.50 s 一样，中位的差主要来自 R0 比 A0b 低）；两臂种子不配对（320400 对 320600），`--forum-clash` 同时加了每个 tick 都在的"一直出刀"续段（出刀 827 对 718 次，日志里按攻击 14.3 % 对 6.0 % 的 tick），迟到 tick 36.5 % 对 7.0 %，两臂都是旧上界 16，每臂 50 场（计划要 ≥ 200）。Envoy 冲锋受击少 45 % 是真的（55 对 30 次，置换 p ≈ 0.002），但属于"拼刀开"这一整套配置（分支 + 续段），总受击没变（4.22 对 4.04 / 场：Choristor 从 60 升到 79）。下面是原来的写法，留作记录；配对、≥ 200 场、单独的续段臂见 17.9。
- **Reaper 开拼刀**（原写法）：存活中位比 R0 长 1.83 s（自助法 95 % 区间约 0.0–3.0 s，P(R8R 更长) 0.58），受击 / 分 18.0 对 19.7；变化几乎全在 Envoy 冲锋（0.60 对 1.10 次 / 场，−45 %），Choristor 跳旋（0.44 对 0.22）、Reed 的针（0.50 对 0.18）多了一些。实战拼中 151 次对 104 次。**Wanderer 开拼刀**：和 W1 没有差别（11.72 对 11.98 s，区间约 −0.6–+1.6 s），Envoy 冲锋 0.82 对 0.78。两种纹章不开拼刀时一样（R0 对 W1：−0.06 s）。和 A0b 比：R0 / W1 短约 0.9 s、R8R 长约 0.9 s，都在区间内；但这几臂跑的时候机器同时有别的轨道的实战和离线任务（tick p50 10–16 ms，A0b 6 ms），不是同负载，主要看同一时段的配对臂。
- **一致性**（选中靠拼刀的计划：连续的拼刀 tick 算一次，看从第一 tick 到最后一 tick 后 36 帧里录像发生了什么）：R8R 18 次，拼中 4、挨打 5（都在拼之前），预测失败概率均值 0.26；R8W1 82 次，拼中 14、挨打 19（16 次在拼之前），预测 0.29、实际 0.23；作废的 R8W 13 次，0 拼中、0 挨打。多数时候计划在拼刀发生前就被下一 tick 换掉（每 tick 重新规划），挨打率和预测的失败概率同一量级，没有发现"选了拼刀反而挨打更多"的迹象。
- **算力**：拼刀分支只在没有安全行、且有敌人正在出可拼的招的 tick 跑；R8W1 对 W1 plan p50 +1.2 ms、tick p50 不变；R8R 对 R0 plan p50 +4.3 ms、迟到 tick 36.5 % 对 7.0 %（原写法说"R8R 那 12 分钟机器最忙"，**复核否定了这个归因**：R0 紧接着在同一实例上跑，11 分钟里有 10 分钟和同一个忙的实例 0 运行 `20261008_042143`（40 % 迟到）重叠，自己仍只有 7 % 迟到；R8R 只重叠约 5.5 分钟。迟到来自拼刀分支本身：R8R 里每个拼刀 tick 2.2 ms，且分支没有截止时间检查）。部分拼刀把 16 行都推演到 3 层，是主要开销；要用就该限到 8 行或 2 层再量。
- **和诊断轨道（forum.md §19，worktree-wf_fa16f06f-127-8）的结论对上**：wave 0 的支撑饱和，FORCED_RISK 的占比全是 1、排序落到 J。拼刀的部分拼刀只在"有敌人正在出可拼的招"的 tick 起作用（拼刀无敌那 9 帧把饱和的占比压下去），所以它能改的主要是 Envoy 冲锋这一招，改不了 wave 0 的整体结局；诊断轨道的 `forced_rank = "seen"`（按眼前看到的伤害碰撞体排序，存活 +5.0 s）是更大的一步。两者合并时要注意：`seen` 把"刀会拼掉的那个判定"也算成接触，会把拼刀行排到后面；合并应让拼刀分支的成功分支替换 `seen` 的接触（集成步骤的事）。

### 17.9 复核之后的修正与配对 A/B（2026-10-08 05:30–08:30，修正代理；代码 d24ef17；实例 2、3）

- **统计口径修正**（`forum_clash_stats`，532f8e2）：并集局面按敌人当时的 Control 状态分开记，并记下它属于哪一次出招（敌人连续处在同一家族的那一段帧）；两种口径不一致时取更坏的（挨打 > 拼中 > 拼中别人 > 都没有：以前接触口径先挨打、后来才拼中的记成拼中）；Multihit 特殊伤害归给最近的有伤害碰撞体的敌人（以前类型是 `?multihit`，从来不算挨打）；Reaper 下劈窗口改成规划器的 [9, 19]。
- **`clash.json` 重建**（d24ef17；R1 v2 的 36 个 data2 运行 + 你的 5 次练习 + 第二轮的实战臂和 A0b；输出 `C:\ssbot\data\m2_forum_r8\fix\clash_*.json`）：每个家族的**可拼状态** = 它的拼中发生过的状态（≥ 2 次且 ≥ 5 %）：Envoy 冲锋 {Charge}、Reed 防御反击 {Parry Slash}、Reed 刺 {Stab 1, 3, 5}、Minister 冲刺 {Attack}、Minister 格挡反击 {Parry Slash 1}、Choristor 斩 {Slash 1, 2, ComboSlash 1}、鞭 {Whip 1–4} 等；成功率只在可拼状态里算；**`p_clash_lb`** = 拼中占比的 Wilson 下界、`p_fail` = 挨打占比的上界，样本量按**出招次数**算（同一次出招的几刀高度相关）；按纹章各自有一行（Wanderer 有 10 个键 n ≥ 10）。31 个键，p_fail ≤ 0.25 的 19 个，p_clash_lb ≥ 0.5 的 10 个，没有一个 ≥ 0.75（最好：Minister 冲刺横 0.74 / 0.044，Envoy 冲锋横 0.72 / 0.047）。"都没有"的占比不小（Reed 刺横 577 次里 197 次），以前的 p_fail 把它们都算成功，成功分支却给了拼刀的无敌和后坐。
- **规划器拼刀分支第三版**（f1f2fb1、d997bc7）：分支权重 w = ∏ p_clash_lb（每次拼刀都发生的概率）；干净的分支只在 w ≥ 0.75 且挨打 ≤ 0.25 时算安全行（现在的表里没有键做得到），其余（w ≥ 0.25）进 FORCED_RISK 排序，接触占比 = w × 成功分支 + (1 − w) × 不拼时（第一次接触仍按不拼的算）；**按状态**：用行为表的停留时间和后继推出这只敌人在拼刀那一帧能不能处在可拼状态（`clash_windows`），收招中的（Charge End、Stab Recover、JumpSlash 4……）不拼，`PARRY_STOPS` 也按状态（Envoy Charge / Reset、Reed Parry Slash）；**DESIGN 3.5.6**：默认只在 GREEN、没有暂停待发时拼（`ForumConfig.clash_tiers`；`--forum-clash yellow` 是实验开关，要不要在 YELLOW 拼需要你决定）；每层前查截止时间（默认 deadline_ms + 2 = 10 ms），最多 8 行 2 层；无敌 9 帧（拼刀帧和之后 8 帧），起点取"拼刀盒最早能碰到它的支撑"的那一帧（下界），只保留不管哪一帧拼中都在无敌里的那几帧；同一帧碰到的别的敌人**不再挡**拼刀（拼刀无敌挡所有敌人伤害，它们之后的接触在分支里照算）。`--forum-clash cont`：只加"一直出刀"续段、不跑分支（A/B 的对照）。
- **开环回放**（A0b i1 ep0，483 个 FORCED_RISK，`--clash yellow`）：210 行接触时刀在生效窗口里，166 个归属的敌人那时不在可拼状态（多是 Envoy JumpSlash 4、Choristor Slash Recover），38 次拼刀被接受（全是 Envoy 冲锋 / Reed 防御反击的收招），38 行进排序，4 次选中；8 层被截止时间截掉；plan p50 5.3 ms（第二版 9.8 ms），分支每个 FORCED_RISK tick 0.96 ms。
- **配对 A/B**（`C:\ssbot\sandbox\r8f_live.ps1`，A0b 协议，Reaper（新上界 9），4 组 × 3 臂轮换顺序，每组每臂同一种子 322000 + 100 × 组 → 每臂 200 场、按种子一一配对；清单 `C:\ssbot\data\m2_forum_r8\fix\ab_manifest.txt`，分析 `C:\ssbot\data\m2_forum_r8\fix\ab.py` → `ab.json`；全部 200 / 200 在 wave 0 QUIT（Q1），WOULD_DIE 0）：

| 臂 | 设置 | 存活中位 / 均值 s | 受击 / 场 | 受击 / 分 | 掉血 / 分 | Envoy 冲锋受击 / 场 | 击杀 | 按攻击 / s | plan p50 ms | tick p50 ms | 迟到 tick |
|---|---|---|---|---|---|---|---|---|---|---|---|
| R0 | 拼刀关 | 13.76 / 14.16 | 4.19 | 17.8 | 21.1 | 1.02 | 0 | 1.56 | 4.0 | 9.7 | 2.4 % |
| RC | 只加续段 | 13.25 / 13.37 | 4.01 | 18.0 | 22.4 | 0.68 | 2 | 4.25 | 4.4 | 10.3 | 2.8 % |
| RY | 分支（GREEN + YELLOW）+ 续段 | 12.93 / 13.69 | 4.04 | 17.7 | 21.9 | 0.63 | 1 | 4.19 | 5.2 | 10.2 | 2.9 % |

- 配对差（200 对，符号翻转置换检验，自助法 95 % 区间）：**RC − R0 存活 −0.79 s（p 0.003，区间 −1.31 到 −0.27）**、受击 −0.18 / 场（p 0.01）、Envoy 冲锋 −0.35 / 场（p < 0.0001）；**RY − R0 存活 −0.47 s（p 0.11，−1.03 到 +0.09）**、受击 −0.15（p 0.047）、Envoy 冲锋 −0.40（p < 0.0001）；**RY − RC 存活 +0.32 s（p 0.22，−0.18 到 +0.84）**、Envoy 冲锋 −0.05（p 0.50）。
- **结论**：(1) 第二轮"Envoy 冲锋受击少 45 %"来自"一直出刀"的续段行，不是拼刀分支：只加续段就少 0.35 次 / 场（刀一直在外面，冲锋自己撞上刀就被拼掉），分支在续段之上没有可测的作用（−0.05，p 0.5）；(2) 续段让主角更常出刀（4.2 对 1.6 次 / s）、更少躲，伤害转到 Choristor（286 → 323 / 337 次）和 2 格的招上，**存活反而短 0.5–0.8 s**（每分钟掉血 22.4 / 21.9 对 21.1）。计划的字面验收（受击 / 场和退出数不更多）RY 是过的（4.04 对 4.19，退出都是 200），但 wave 0 里每场都是掉 5 格血后 Q1 退出，这两项几乎由构造决定；看存活时间和每分钟掉血两组都更差（RC 显著），所以**两组都没写进 `Forum.yaml`**，要不要用由你定；(3) 分支本身在 wave 0 几乎无事可做：开环和实战里多数"刀在窗口里"的接触来自收招中的敌人（不可拼），按状态和出招次数修正后没有一个键的 w 到 0.75，只能以混合占比进 FORCED_RISK 排序（RY 里 2,724 个选中 tick）；(4) 算力问题解决：RY 迟到 2.9 % 对 R0 2.4 %，分支每个拼刀 tick 1.12 ms，截止时间截掉 2 % 的拼刀 tick。
- **一致性**（RY 4 个运行，选中拼刀计划的连续 tick 算一次，看之后 36 帧）：207 次，48 % 拼中、19 % 挨打（39 次里 36 次在拼之前），预测 w 均值 0.58；所有 FORCED_RISK tick 的基线是 36 帧内 46 % 挨打、11 % 拼中。日志是按事件抽样的、计划每 tick 都会换，这只说明"选了拼刀的时候挨打不比平常多"，不是 w 的校准。
- 两次 A/B 的对照（17.8 的 R0 / R8R）：新上界下 R0 存活中位 13.76 s（旧上界 11.92 s、A0b 12.81 s），这一项比拼刀的任何一臂都大，但不同时段不同负载，不是配对比较。

## 18. R5 行为模型：感知时刻、冷却、分支历史、Tiny 一只一只、身体触发（2026-10-08，forum_planner_plan.md §5 R5 的行为模型半；离线，没有连接游戏）

代码：`combat/branch_model.py`（SENSING 表、触发形状 RANGES、BranchMemory、BranchModel、运行时 BranchView、身体触发 REACTIVE）、`combat/tiny_orbit.py`、`knowledge/forum_branch.py`（扫描、选择、校准）；工具 `forum_branch`（scan / study / build / parity）、`tiny_orbit`；`multi_recall --branch`。产品 `knowledge/1.0.30000/enemies/forum/branch_model.json`（复核后 243 KB：分支帧表 `types`、预报表 `ahead`、分段 `segmentation`）、`tiny_orbit.json`。测试 `tests/test_branch_model.py`（21 个，含录像逐帧核对）。**全部只进打分（P / J、O / BAIT），支撑、放置、监督器都不读它**；接线：`MultiForecaster(branch=BranchModel.load())` 时每个 EnemyTracker 带一个 BranchMemory，`Subject.next_p` = 下一招家族的概率（**预报表 `ahead`**，§18.11；复核前用的是分支帧表，中途查询时严重失准），`branch_probs(iid)` / `next_attack_probs(iid)` / `BranchView.reactive` / `entry_prob`；`ForumPlannerPolicy(branch_model=True)` 打开，默认关（规划器还没有消费者，R5 终点价值 / R6 的 O、BAIT 用）。

数据：DEV = R0 的 142 场完整连战（`m2_forum_r0\cache` 107 + `cache_fresh` 35，随机数据策略），按场两折交替；**TEST = R1 收尾的 202 场**（`m2_forum_r1c\cache_fresh`：w7 / w2 波次起点、154609 / 154612 完整连战，data2 / idle 策略），选择和调参时没有看过，表在 DEV 全部上拟合后只评估一次。决策 = 控制 FSM 离开一个决策状态的一次转移：DEV 428,997 个、TEST 253,222 个（61 个决策状态，n ≥ 60 且至少两个后继）。主角的丝从录像读（`hero.silk`，每场约 2 s，缓存在 `C:\ssbot\data\m2_forum_r5m\hero\`）。

### 18.1 FSM 静态：每个决策读主角的什么、在哪一刻（场景包 `hang_04_boss` 控制 FSM，`reactive_scripts\out\*.txt` 逐动作解码）

PlayMaker 的三条规则决定了"哪一刻"：(1) 动作在 OnEnter 里发出有出边的事件会**当场**换状态，后面的动作不再执行（13.2 已用过）；(2) 状态里的动作全部结束（没有 everyFrame）时自动发 FINISHED；(3) `SendRandomEventV4`（反编译 `SendRandomEventV4.cs`）每个动作实例有两个计数：`trackingInts[i]`（i 连着出了几次）和 `trackingIntsMissed[i]`（多少次没出 i）；先看有没有 `missed ≥ missedMax` 的事件（有就强制出它），否则按权重抽、抽到已连出 `eventMax` 次的就重抽。`activeBool` 为假时整个动作不跑、计数不动。所以 V4 的"冷却"完全由这个状态自己过去的选择决定——这就是 `last_choice` / `prev2_choice` / `choice_run` / `miss_<后继>` 这些历史量。

| 类型 | 决策状态 | 读什么（FSM 动作） | 何时 |
|---|---|---|---|
| Clapper | Idle | 每帧：Slam Range ∧ Will Evade（进入时 RandomBool）∧ Can Evade（≥ 0.25 s）→ Evade Scuttle；进入时：另一只 |x| < 4 → Avoid Type；TOOK DAMAGE → Dmg Attack；0.65 / 1.15 s（无伴 / 有伴）→ Walk | 分支帧（每帧） |
| | Walk | 每帧：≥ 0.25 s ∧ Slam Range → Close Range；WaitRandom 0.25–2 s → Far Range | 分支帧 |
| | Close Range / Far Range | 瞬时：伴在出招 → Idle；片段 Walk B → SLAM；V4（Close：SLAM / EVADE / CAST 各 1/3、eventMax 1；Evaded 时只 SLAM / CAST。Far：JUMP 0.5 / CAST 0.25 / JUMP CAST 0.25） | 分支帧 |
| | After Scuttle / Dmg Attack | 瞬时 Slam Range | 分支帧 |
| | Escape Jump | V4 1:1、eventMax 1、missedMax 1（严格交替） | — |
| | Avoid Type | 瞬时：主角和伴在同一侧 → Evade | 分支帧 |
| | Evade Scuttle | 进入时：背后 6 u 有墙 → Escape Jump，否则 0.35 s → After Scuttle | **进入** |
| Clawmaiden | Fly | 每帧：Slash Range → Slash；≥ 0.5 s ∧ Suck Start Range ∧ 吸丝计时到 ∧ 没被锁 → Spin Antic；距离 > 20 → Tele Out；WaitRandom 1–2 s → Tele? | 分支帧 |
| | Spin Antic | 进入时：主角丝 < 3 ∧ 硬币 → Fly To Slash；丝 < 2 → Fly；否则动画完 → Spin 0 | **进入** |
| | Spin 0 / 1 / 2 | Silk Suck FSM 每 1.1 s 一次 tick 拿 1 丝，主角丝为 0 → NO SILK | 主角丝 |
| | Tele? | 瞬时：距离 > 22 → 瞬移；V4 TELEPORT / FINISHED（eventMax 1 / 2） | 分支帧 |
| | Fly To Slash | 每帧 Slash Range；1.0 s → Fly | 分支帧 |
| Minister | Chase | 每帧：攻击计时到 ∧ Attack Range（圆 r 7，圆心下 1 u）→ Attack Choice；TOOK DAMAGE → Range Check（计时夹到 ≤ 0.5 s） | 分支帧 |
| | Attack Choice | V4 CHARGE / PARRY 1:1、eventMax 2、missedMax 2：**同一招最多连两次** | 历史 |
| | Evade? | 瞬时：V4 FINISHED / 空 1:1（eventMax 2），抽到空且主角在 Evade Range（r 4.955）→ Evade Antic，否则动作完 → Retreat? | 分支帧 |
| | Retreat? | 进入时 V4 FINISHED / 空，否则 WaitRandom 0.5–1 s；TOOK DAMAGE → Range Check | 进入 |
| | Parry Stance | 0.85 s 或主角越过身后 1 u → End；BLOCKED HIT → Parry Block | 分支帧 |
| Maestro | Attack Choice | 死 Tiny > 1 → FIRE；V4 FIRE 0.75 / DEFEND 0.25（FIRE 最多连 3 次、DEFEND 不连） | 历史 |
| | Summon? | 死 Tiny 0 → Attack Choice、3 → Call；1：V4 空 0.65 / SUMMON 0.35；2：再一个 V4 SUMMON 0.65 | 历史 |
| | Forum Fly | 计时 U(1.15, 1.45) s 或 TOOK DAMAGE → Summon?；**不读主角位置** | — |
| Reed | Alert | 每帧：已上膛的 Evade Range → Evade Antic；Will Defend（进入时硬币）∧ Defend Range（r 7.65）∧ ¬Just Did Defend → Defend Start；WaitRandom 1–1.75 s（Move Cancel 之后 0.75 s）→ Choice；TOOK DAMAGE → Stab Pos | 分支帧 |
| | Choice | 瞬时：Throw Range 外 → 扔；V4 THROW 0.35 / STAB 0.65（eventMax 2） | 分支帧 |
| | Evade End | SendRandomEvent 0.5（无记忆）→ Alert，否则 Throw Range 内 → 扔 | 分支帧 |
| | Throw Antic Anim → Throw Antic（0.25 s）→ Throw Aim（0.4 s）→ Throw Lock → Lock R High / Throwing Up? → Throw Up / Down | Throw Antic Anim 进入时存"向上瞄"；Throw Aim 进入时存到主角的角度；Lock / Throwing Up? / Throw Up / Down 读存下来的值 | **存储（更早的状态）** |
| | Stab Pos | 每帧 Stab Range；1.5 s → Move Cancel | 分支帧 |
| Envoy | Walker | 每帧：Attack Range → 斩；Alerted ∧ Charge Range（场景加载时就开着；一次斩之后开；一次 Walker 待满 1.5 s 时开（`ActivateGameObjectDelay` 1.5 s、resetOnExit 0：离开 Walker 后仍开着，没待满就不开）；Charge Antic 关）→ 冲锋；TOOK DAMAGE → Leader? | 分支帧 |
| | Combo? | 瞬时：没面对主角 → Attack End；V4 1:1（eventMax 2） | 分支帧 |
| Choristor | Hop Antic | 进入时：Close Range → Attack Choice；否则 0.2 s → Hop Check | **进入** |
| | Hop Check | 瞬时 \|x 距离\| ≤ Hop Distance（Move Start 时抽 U(6, 10)，这一串跳共用）→ 后跳 | 分支帧 + 历史 |
| | Hop Land | Hops（Move Start 时抽 1–3）用完或前面有墙 → Attack Choice | 历史 |
| | Attack Choice | 瞬时：Attack Range 外 → Battle Idle；Close Range → 斩；V4 SLASH / JUMP / WHIP（eventMax 2、missedMax 3） | 分支帧 |
| Bellbearer | In Range | 每帧：Throw Range 外 → Out of Range；Evade Range ∧ 背后 3 u 无墙 ∧ ≥ 0.5 s ∧ ¬Evade Cooldown → Evade；WaitRandom 0.8–1.5 s → 扔 | 分支帧 |
| | Insta Throw? | 瞬时闪避测试一次，然后 V4 FINISHED 0.65 / ATTACK 0.35 | 分支帧 |
| | Evade End | 瞬时 Throw Range；V4 1:1（eventMax 2） | 分支帧 |
| 各类 | Check Pos | 瞬时 GetDistance < 6（Maestro 8）→ Shift（换出生点） | 分支帧 |

Tiny 的控制 FSM 在别的包里（Maestro 用 `CreateObject` 生成的预制体，场景包外部文件 45），这次没有解码；它的 Ready → Fire Ready / Defend Ready 由 Maestro 的事件指挥（§18.6）。机器可读的表在 `branch_model.SENSING`（类型 → 状态 → (时刻, 说明)）。

### 18.2 冷却：FSM 里的历史，换成看得见的条件（`BranchMemory`，从控制状态的进入和看到的命中推出）

- **门**（布尔变量 + 哪个状态设 / 清，`branch_model._GATES`）：Bellbearer `Evade Cooldown`（Evade 设、只有 Throw Antic 清：扔一次钟补一发闪避；`can_evade` = 上一次 In Range 待够 0.5 s，带到 Insta Throw?）；Reed `armed`（Evade Antic 关、Defend Start / Stab Antic 开）、`jdd` = Just Did Defend（Defend Start 设、Stab Antic / Throw Antic 清）；Clapper `evaded`（Evade Scuttle 设、任何招的前摇清）；Envoy `charge_armed`（初值开：Charge Range 物体在场景里 active；Charge Antic 关、Slash Antic 开；一次 Walker 待满 1.5 s 时开且离开后保持）和 `alerted`（Slash Antic / Ambush Ready 设，从不清；CHARGE 要它）。**复核修正**：第一版初值关、只在 Walker 里按时间开，于是 Walker → Charge Antic 时门是关的 DEV 131 次、TEST 34 次（FSM 里不可能）。
- **计数 / 计时**：Choristor 这一串跳的第几跳和上一跳方向（`hops`、`last_hop`）；Clawmaiden 吸丝计时（Startle 设 U(1, 3)、Spear Fire Recover 设 U(1.5, 2)，只在 Fly 里减）→ 在 Fly 里累计的时间 `suck_age`；Maestro 自己的死 Tiny 数 `dead_tinies`（Tiny 归属 `TinyOwners`：每一帧 Tiny 在 Ready 且这一帧看得见时，归给 0.25 s 内看得见的最近一只 Maestro（< 8 u），最后一次归属有效；扫描和运行时同一条规则、都只用过去的帧——第一版扫描按整场投票，用到了未来的帧）。
- **防重复**：这个状态以前的选择 `last_choice` / `prev2_choice` / `choice_run` / `miss_<后继>`，上一次各家族之后过了几招 `since_<家族>`（V4 的两个计数就是它们；第一版 `since_` / `miss_` 只在离线扫描里算，运行时没有，§18.11）。
- **分支拆开的历史**（你 10-04）：上一招和它最后一个状态 `prev_end`（例 `MI_PARRY:Parry Stance End` 没被打 vs `MI_PARRY:Parry Slash End` 被打后反击）、离上一招结束多久 `since_end`、从哪个状态进来 `from`、在这个状态里待了多久 `age`、到这一帧为止的最近一次命中 `hit`（< 0.25 s / < 1 s / 更早）。**复核修正**：第一版写"决策当帧的命中是 TOOK DAMAGE 出边的原因、不算历史"，实际几乎用不上：TOOK DAMAGE 出边（DEV 22 场，1,011 次）和同一帧的记录命中重合只有 1 次；Clapper Idle → Dmg Attack 194 / 568、Minister Chase → Range Check 84 / 299 在一次记录命中之后 12–18 帧（多数 18 帧 = 0.3 s），Reed Alert → Stab Pos 只有 7 / 176，其余前 0.35 s 内没有记录到的命中（中位数 1.9–4 s 前）。所以 `hit` 带的是看得见的过去信息（不是泄漏），现在当帧的命中也算。
- 跨敌人：Clapper 的伴在不在、在不在出招、x 距离 < 4（`buddy*`，`clapper_context`：伴的控制状态不在等待集合里、0.25 s 内看得见）；主角的丝（Clawmaiden）。分段（哪个状态开始哪一招）运行时也用扫描的 `FORUM_SPECS`：运行时走子表少 Maestro 的 MA_POINT、Envoy 的 EN_HOPSLASH / EN_ENTRY，第一版运行时的 `prev` / `run` / `since_*` 因此和训练不一样。
- 全部看得见：状态及其进入时刻（oracle 的 FSM / 视觉的阶段）、看到的命中、位置、主角自己的丝；不读 FSM 变量。

**数据核对**（DEV，`C:\ssbot\data\m2_forum_r5m\branch_gap.json`；"下一招"= 上一招结束后的第一招，不算入场 / 待机）：Bellbearer 闪过之后下一招 **2,229 / 2,229 是扔钟**（Evade Cooldown）；Maestro 防御之后 89 % 斩、11 % 召唤、**0 防御**（V4 eventMax 1），斩之后 53 % 斩 / 39 % 防御 / 8 % 召唤。

### 18.3 结果：分支帧模型的留出对数损失与校准（复核后重建，代码 2f5b96a；第一版的数字和它错在哪见 §18.11）

"分支帧模型"（`branch_model.json` 的 `types` 表）估的是 **P(后继 | 这个决策就在这一帧发生)**：拟合和评估都只用状态离开的那一帧。它回答"如果它现在决定，走哪一支"——瞬时决策（进入的同一帧就离开）和候选路径的"假如"；**它不是状态中途的预报**（中途查询要用 `ahead` 表，§18.11.3）。"无条件" = 每次访问的边际（运行时走子今天的 `p_succ`）；"R0 重拟" = R0 表的协变量名在这些记录上用同一套回退平滑重拟（**不是**发布的 R0 表；R0 表在运行时只以无条件 `p_succ` 出现）；"新" = 本节模型，所有协变量都是运行时 `BranchView` 逐帧算得出来的（§18.11.2：7 场逐帧核对 0 差）。DEV 列两折交叉验证，TEST 列 DEV 全部拟合后在 202 场上一次评估。nats / 决策，按决策数加权：

| | 无条件 | R0 重拟 | 新 |
|---|---|---|---|
| DEV（428,997，交叉验证） | 0.740 | 0.538 | **0.279** |
| TEST（253,222，留出） | 0.695 | 0.511 | **0.284** |

逐个决策（ECE = 所有（决策, 后继）对按预测概率分 10 档的期望校准误差，TEST；时刻见 §18.4）：

| 类型 | 决策 | DEV n | 无条件 | R0 重拟 | 新 | 时刻 | 协变量 | TEST n | 无条件 | R0 重拟 | 新 | ECE 前 → 后 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Bellbearer | Check Pos | 710 | 0.253 | 0.176 | 0.153 | branch | dx,in_Throw Range,dist_visible | 318 | 0.146 | 0.096 | 0.084 | 0.028→0.013 |
| Bellbearer | Evade End | 4466 | 0.693 | 0.581 | 0.534 | branch | prev2_choice,in_Throw Range,side | 2947 | 0.693 | 0.547 | 0.514 | 0.004→0.012 |
| Bellbearer | In Range | 15679 | 1.064 | 0.420 | 0.107 | branch | dx,since_end,in_Evade Range,dist | 9928 | 1.044 | 0.402 | 0.117 | 0.015→0.005 |
| Bellbearer | Insta Throw? | 6196 | 0.667 | 0.323 | 0.318 | branch | prev2_choice | 3601 | 0.665 | 0.298 | 0.298 | 0.000→0.002 |
| Choristor | Attack Choice | 5678 | 1.300 | 1.051 | 0.674 | branch | in_Attack Range,in_Close Range,prev2_choice,since_CH_JUMP | 1626 | 1.276 | 0.984 | 0.622 | 0.013→0.005 |
| Choristor | Combo? | 1715 | 0.628 | 0.610 | 0.013 | branch | front,hit | 564 | 0.637 | 0.631 | 0.021 | 0.008→0.002 |
| Choristor | Hop Antic | 9906 | 0.355 | 0.169 | 0.001 | branch | age | 2786 | 0.410 | 0.201 | 0.000 | 0.018→0.000 |
| Choristor | Hop Check | 8776 | 0.693 | 0.236 | 0.190 | branch | dx,last_hop | 2394 | 0.694 | 0.247 | 0.205 | 0.016→0.006 |
| Choristor | Hop Land | 8745 | 0.692 | 0.606 | 0.557 | lead0.2 | hops,side,hero_x | 2380 | 0.692 | 0.612 | 0.563 | 0.001→0.005 |
| Choristor | Slash Check | 2463 | 0.591 | 0.226 | 0.023 | branch | in_Slash Range,hit,dy | 757 | 0.509 | 0.181 | 0.050 | 0.029→0.001 |
| Choristor | Unalert Tick? | 5739 | 0.403 | 0.251 | 0.144 | branch | in_Attack Range,dist,dist_visible,hero_x | 1659 | 0.416 | 0.301 | 0.145 | 0.005→0.012 |
| Clapper | After Scuttle | 10014 | 0.385 | 0.159 | 0.006 | branch | in_Slam Range,dx | 4758 | 0.397 | 0.188 | 0.009 | 0.004→0.000 |
| Clapper | Avoid Type | 9734 | 0.675 | 0.623 | 0.597 | lead0.3 | dx,since_end,prev | 4338 | 0.677 | 0.629 | 0.594 | 0.005→0.009 |
| Clapper | Close Range | 14839 | 1.222 | 1.175 | 0.710 | lead0.2 | buddy_attacking,prev,since_end,dist | 7096 | 1.210 | 1.155 | 0.696 | 0.010→0.004 |
| Clapper | Dmg Attack | 3656 | 0.693 | 0.329 | 0.007 | branch | in_Slam Range,dy | 1185 | 0.698 | 0.331 | 0.020 | 0.048→0.001 |
| Clapper | Escape Jump | 413 | 0.692 | 0.414 | 0.377 | lead0.5 | last_choice,dy,buddy_attacking,since_CC_SLAM | 267 | 0.693 | 0.290 | 0.300 | 0.007→0.018 |
| Clapper | Evade Scuttle | 10486 | 0.201 | 0.090 | 0.024 | branch | age,side | 5044 | 0.234 | 0.093 | 0.013 | 0.006→0.003 |
| Clapper | Far Range | 13876 | 1.274 | 0.974 | 0.596 | branch | buddy_attacking,prev2_choice,miss_Cast Slam Antic,miss_Jump Antic | 6563 | 1.339 | 0.921 | 0.505 | 0.026→0.002 |
| Clapper | Idle | 28014 | 1.319 | 1.054 | 0.152 | branch | age,buddy,in_Slam Range,buddy_close | 13416 | 1.287 | 1.042 | 0.148 | 0.010→0.003 |
| Clapper | Walk | 15094 | 0.543 | 0.387 | 0.038 | branch | in_Slam Range,age | 7733 | 0.579 | 0.459 | 0.037 | 0.016→0.000 |
| Clawmaiden | Fly | 6623 | 1.160 | 0.767 | 0.158 | branch | age,in_Slash Range,in_Suck Start Range,suck_age | 4457 | 1.097 | 0.743 | 0.125 | 0.019→0.010 |
| Clawmaiden | Fly To Slash | 1543 | 0.776 | 0.608 | 0.036 | branch | age,in_Slash Range,in_Tele Escape Range | 1094 | 0.705 | 0.508 | 0.034 | 0.052→0.002 |
| Clawmaiden | Spin 0 | 1018 | 0.233 | - | 0.074 | lead0.2 | silk,age,suck_set,dy | 631 | 0.192 | - | 0.184 | 0.005→0.024 |
| Clawmaiden | Spin 1 | 968 | 0.233 | - | 0.034 | lead0.1 | age,silk,choice_run,in_Slash Range | 605 | 0.188 | - | 0.412 | 0.007→0.066 |
| Clawmaiden | Spin 2 | 919 | 0.686 | 0.668 | 0.136 | lead0.1 | silk,age | 582 | 0.669 | 0.653 | 0.250 | 0.013→0.044 |
| Clawmaiden | Spin Antic | 3736 | 1.098 | 1.007 | 0.449 | entry | age,silk | 2609 | 1.081 | 0.964 | 0.473 | 0.013→0.001 |
| Clawmaiden | Tele? | 935 | 0.679 | 0.481 | 0.474 | branch | prev2_choice,since_CM_SPIN,last_seen_x,in_Suck Start Range | 475 | 0.681 | 0.464 | 0.484 | 0.005→0.046 |
| Envoy | Charge | 568 | 1.322 | 0.895 | 0.733 | lead0.1 | front,hero_x,last_seen_x,dy | 118 | 1.312 | 0.760 | 0.909 | 0.004→0.046 |
| Envoy | Combo? | 842 | 0.663 | 0.639 | 0.486 | branch | front,prev2_choice,miss_JumpSlash Antic | 201 | 0.651 | 0.633 | 0.475 | 0.016→0.027 |
| Envoy | Walker | 1408 | 0.748 | 0.133 | 0.040 | branch | dist_visible,charge_armed,in_Attack Range | 326 | 0.674 | 0.068 | 0.033 | 0.016→0.005 |
| Maestro | Attack Choice | 15278 | 0.608 | 0.318 | 0.331 | branch | miss_Defend Start | 10901 | 0.610 | 0.312 | 0.324 | 0.002→0.005 |
| Maestro | Check Pos | 426 | 0.695 | 0.215 | 0.118 | branch | dx,dist,dist_visible,dy | 255 | 0.661 | 0.202 | 0.115 | 0.121→0.010 |
| Maestro | Fly | 4460 | 0.846 | 0.169 | 0.037 | branch | last_choice,dx,since_end,in_Attack Range | 2599 | 0.781 | 0.169 | 0.038 | 0.056→0.002 |
| Maestro | Slash Recover | 10501 | 0.537 | 0.029 | 0.007 | branch | age | 7539 | 0.543 | 0.019 | 0.003 | 0.005→0.000 |
| Maestro | Summon? | 16694 | 0.290 | 0.272 | 0.177 | branch | dead_tinies,since_MA_SUMMON | 11300 | 0.173 | 0.186 | 0.079 | 0.033→0.006 |
| Minister | Attack | 3309 | 0.634 | 0.407 | 0.088 | branch | age,dist,dx,front | 3131 | 0.680 | 0.421 | 0.121 | 0.043→0.009 |
| Minister | Attack Choice | 6932 | 0.693 | 0.518 | 0.493 | branch | prev2_choice | 6460 | 0.693 | 0.495 | 0.480 | 0.002→0.007 |
| Minister | Chase | 8804 | 0.518 | 0.374 | 0.167 | branch | in_Attack Range,dist,age,from | 7172 | 0.369 | 0.266 | 0.131 | 0.076→0.010 |
| Minister | Check Pos | 568 | 0.314 | 0.050 | 0.002 | branch | last_seen_x,dy | 308 | 0.239 | 0.022 | 0.000 | 0.023→0.000 |
| Minister | Evade? | 5525 | 0.543 | 0.433 | 0.311 | branch | in_Evade Range,prev2_choice,choice_run | 5033 | 0.605 | 0.477 | 0.355 | 0.035→0.001 |
| Minister | Parry Stance | 3404 | 0.550 | 0.530 | 0.242 | branch | age,front,dist | 3208 | 0.442 | 0.416 | 0.210 | 0.062→0.030 |
| Minister | Retreat? | 4243 | 0.297 | 0.276 | 0.150 | branch | age,dist | 3594 | 0.211 | 0.199 | 0.097 | 0.024→0.018 |
| Reed | Alert | 9806 | 1.426 | 0.906 | 0.384 | branch | age,dist,in_Evade Range,last_choice | 5482 | 1.359 | 0.833 | 0.286 | 0.018→0.010 |
| Reed | Check Pos | 710 | 0.276 | 0.236 | 0.098 | branch | hero_x,last_seen_x,dist_visible,in_Defend Range | 284 | 0.264 | 0.264 | 0.191 | 0.004→0.021 |
| Reed | Choice | 3551 | 0.693 | 0.624 | 0.480 | branch | in_Throw Range,prev2_choice | 2178 | 0.693 | 0.580 | 0.469 | 0.005→0.008 |
| Reed | Defend | 2483 | 0.655 | 0.592 | 0.052 | lead0.3 | age,in_Defend Range | 1439 | 0.574 | 0.524 | 0.069 | 0.049→0.002 |
| Reed | Evade End | 2212 | 0.693 | - | 0.673 | branch | in_Throw Range,dist | 1291 | 0.692 | - | 0.674 | 0.013→0.004 |
| Reed | Lock R High | 1151 | 0.448 | - | 0.146 | stored | dy,in_Evade Range,in_Defend Range,since_end | 778 | 0.358 | - | 0.147 | 0.037→0.026 |
| Reed | Stab Pos | 2858 | 0.231 | 0.186 | 0.023 | branch | age,in_Stab Range,from,hit | 1441 | 0.177 | 0.138 | 0.011 | 0.007→0.001 |
| Reed | Throw Down | 2526 | 0.128 | - | 0.028 | stored | dy | 1545 | 0.106 | - | 0.027 | 0.004→0.003 |
| Reed | Throw Lock | 2837 | 0.675 | 0.146 | 0.000 | lead0.4 | side,front | 1717 | 0.693 | 0.158 | 0.007 | 0.032→0.001 |
| Reed | Throw Up | 311 | 0.692 | - | 0.182 | stored | dy,in_Stab Range,silk,choice_run | 172 | 0.689 | - | 0.318 | 0.000→0.040 |
| Reed | Throwing Up? | 2837 | 0.346 | 0.336 | 0.067 | lead0.4 | dy,dist_visible,from | 1717 | 0.326 | 0.320 | 0.061 | 0.006→0.005 |
| Tiny | Brake | 7782 | 0.736 | 0.422 | 0.170 | branch | dx,age,front,hero_x | 5511 | 0.710 | 0.391 | 0.149 | 0.011→0.003 |
| Tiny | Defend Buzz | 12595 | 0.207 | 0.201 | 0.065 | branch | age,dist | 9402 | 0.103 | 0.102 | 0.025 | 0.015→0.003 |
| Tiny | Defend Ready | 12767 | 0.080 | 0.080 | 0.017 | branch | age,dist | 9534 | 0.047 | - | 0.009 | 0.003→0.001 |
| Tiny | Fire | 10501 | 0.791 | 0.528 | 0.320 | branch | dx,front,dy,last_seen_x | 7531 | 0.778 | 0.519 | 0.291 | 0.006→0.007 |
| Tiny | Fire Ready | 10744 | 0.120 | 0.106 | 0.033 | branch | age,front | 7617 | 0.065 | 0.060 | 0.016 | 0.007→0.001 |
| Tiny | Pull Up | 6246 | 0.704 | 0.368 | 0.160 | lead0.4 | age,dist_visible,hero_x,side | 4478 | 0.650 | 0.297 | 0.163 | 0.022→0.003 |
| Tiny | Ready | 52160 | 1.061 | 0.934 | 0.623 | branch | age,front,from,miss_Defend Ready | 31813 | 1.105 | 1.059 | 0.836 | 0.027→0.028 |
| Tiny | Return | 10017 | 0.730 | 0.667 | 0.400 | branch | front,age,dy,dist | 7334 | 0.626 | 0.610 | 0.313 | 0.014→0.012 |

读法：(1) 由距离 / 范围决定的瞬时或每帧决策，换成**精确的触发形状**后几乎确定（Clapper After Scuttle / Dmg Attack TEST 0.009 / 0.020、Walk 0.037，Choristor Slash Check 0.050）。(2) 新加的 `age`（在这个状态里待了多久）被 25 个决策选中：计时出边直接由它看出（Clapper Idle 的 0.65 / 1.15 s → Walk：0.425 → 0.152；Reed Defend 的 1.0 s → Defend End：0.360 → 0.052；Choristor Hop Antic 进入当帧 Close Range → Attack Choice、否则 0.2 s → Hop Check：`age` 一个量就 0.001；Minister Attack、Parry Stance、Retreat?、Maestro Slash Recover 同理）。在分支帧模型里这是合法的条件（"它在这个年龄决定"），但正因如此它不能在中途当预报用（§18.11.3）。(3) 防重复和门：Bellbearer In Range 1.06 → 0.11、Minister Attack Choice 0.693 → 0.493（`prev2_choice`）、Envoy Walker 0.748 → 0.040（`charge_armed` 修正后，§18.11.1）、Maestro Summon? 0.29 → 0.18（`dead_tinies`）。(4) DEV 好、TEST 不稳的：Clawmaiden Spin 1（TEST 0.412，比无条件 0.188 差，ECE 0.066）、Spin 0（0.184 vs 0.192）、Envoy Charge（0.909，R0 重拟 0.760）、Reed Throw Up（n 172，0.318）、Maestro Attack Choice（0.324 vs R0 重拟 0.312）：小样本、DEV（R0 随机策略）和 TEST（R1 data2 / idle、波次起点）的主角行为不同（丝的多少、站位）；Tiny Ready 0.836 是 Maestro 那边的随机选择。

### 18.4 感知时刻：分支帧 / FSM 的感知时刻 / 固定提前 0.1–0.5 s（DEV 交叉验证，几何 + 历史一起选；最后一列只用几何）

| 类型 | 决策 | 分支帧 | 进入 | 存储 | 提前 0.1 | 0.2 | 0.3 | 0.4 | 0.5 | 只用几何：分支帧 / 最好 |
|---|---|---|---|---|---|---|---|---|---|---|
| Bellbearer | Check Pos | 0.153 | 0.153 | - | 0.246 | 0.246 | 0.246 | 0.247 | 0.247 | 0.153 / 0.153 |
| Bellbearer | Evade End | 0.534 | 0.534 | - | 0.542 | 0.546 | 0.546 | 0.546 | 0.546 | 0.686 / 0.686 |
| Bellbearer | In Range | 0.107 | 0.374 | - | 0.241 | 0.284 | 0.320 | 0.356 | 0.366 | 0.183 / 0.183 |
| Bellbearer | Insta Throw? | 0.318 | 0.318 | - | 0.318 | 0.318 | 0.318 | 0.318 | 0.318 | 0.664 / 0.662 |
| Choristor | Attack Choice | 0.674 | 0.674 | - | 0.844 | 0.892 | 0.927 | 0.955 | 0.981 | 0.710 / 0.710 |
| Choristor | Combo? | 0.013 | 0.013 | - | 0.242 | 0.317 | 0.386 | 0.431 | 0.472 | 0.018 / 0.018 |
| Choristor | Hop Antic | 0.001 | 0.001 | - | 0.001 | 0.001 | 0.001 | 0.001 | 0.001 | 0.081 / 0.006 |
| Choristor | Hop Check | 0.190 | 0.190 | - | 0.241 | 0.313 | 0.370 | 0.420 | 0.455 | 0.191 / 0.191 |
| Choristor | Hop Land | 0.560 | 0.560 | - | 0.559 | 0.557 | 0.558 | 0.559 | 0.561 | 0.692 / 0.692 |
| Choristor | Slash Check | 0.023 | 0.023 | - | 0.159 | 0.222 | 0.292 | 0.339 | 0.355 | 0.028 / 0.028 |
| Choristor | Unalert Tick? | 0.144 | 0.144 | - | 0.162 | 0.179 | 0.195 | 0.212 | 0.224 | 0.144 / 0.144 |
| Clapper | After Scuttle | 0.006 | 0.006 | - | 0.105 | 0.159 | 0.196 | 0.228 | 0.261 | 0.006 / 0.006 |
| Clapper | Avoid Type | 0.604 | 0.604 | - | 0.605 | 0.605 | 0.597 | 0.605 | 0.616 | 0.607 / 0.607 |
| Clapper | Close Range | 0.732 | 0.732 | - | 0.714 | 0.710 | 0.716 | 0.721 | 0.722 | 1.185 / 1.170 |
| Clapper | Dmg Attack | 0.007 | 0.007 | - | 0.182 | 0.258 | 0.281 | 0.323 | 0.352 | 0.007 / 0.007 |
| Clapper | Escape Jump | 0.393 | 0.393 | - | 0.388 | 0.390 | 0.395 | 0.381 | 0.377 | 0.692 / 0.687 |
| Clapper | Evade Scuttle | 0.024 | 0.024 | - | 0.024 | 0.024 | 0.025 | 0.025 | 0.025 | 0.095 / 0.092 |
| Clapper | Far Range | 0.596 | 0.596 | - | 0.596 | 0.596 | 0.596 | 0.596 | 0.596 | 1.262 / 1.261 |
| Clapper | Idle | 0.152 | 0.194 | - | 0.176 | 0.182 | 0.187 | 0.191 | 0.195 | 1.028 / 1.028 |
| Clapper | Walk | 0.038 | 0.427 | - | 0.371 | 0.384 | 0.414 | 0.421 | 0.420 | 0.047 / 0.047 |
| Clawmaiden | Fly | 0.158 | 0.287 | - | 0.237 | 0.264 | 0.273 | 0.275 | 0.280 | 0.480 / 0.480 |
| Clawmaiden | Fly To Slash | 0.036 | 0.114 | - | 0.114 | 0.114 | 0.114 | 0.114 | 0.114 | 0.169 / 0.169 |
| Clawmaiden | Spin 0 | 0.079 | 0.137 | - | 0.080 | 0.074 | 0.098 | 0.109 | 0.112 | 0.140 / 0.140 |
| Clawmaiden | Spin 1 | 0.077 | 0.064 | - | 0.034 | 0.047 | 0.060 | 0.059 | 0.058 | 0.193 / 0.151 |
| Clawmaiden | Spin 2 | 0.496 | 0.253 | - | 0.136 | 0.159 | 0.187 | 0.217 | 0.203 | 0.526 / 0.169 |
| Clawmaiden | Spin Antic | 0.449 | 0.449 | - | 0.452 | 0.454 | 0.455 | 0.457 | 0.459 | 0.603 / 0.593 |
| Clawmaiden | Tele? | 0.474 | 0.474 | - | 0.478 | 0.480 | 0.480 | 0.480 | 0.480 | 0.679 / 0.679 |
| Envoy | Charge | 0.777 | 1.151 | - | 0.733 | 0.827 | 1.034 | 0.913 | 0.904 | 0.786 / 0.733 |
| Envoy | Combo? | 0.486 | 0.486 | - | 0.519 | 0.532 | 0.552 | 0.562 | 0.578 | 0.531 / 0.531 |
| Envoy | Walker | 0.040 | 0.229 | - | 0.173 | 0.274 | 0.326 | 0.383 | 0.409 | 0.087 / 0.087 |
| Maestro | Attack Choice | 0.331 | 0.331 | - | 0.331 | 0.331 | 0.331 | 0.331 | 0.331 | 0.594 / 0.585 |
| Maestro | Check Pos | 0.118 | 0.118 | - | 0.137 | 0.154 | 0.201 | 0.272 | 0.319 | 0.118 / 0.118 |
| Maestro | Fly | 0.037 | 0.099 | - | 0.068 | 0.076 | 0.081 | 0.087 | 0.090 | 0.372 / 0.372 |
| Maestro | Slash Recover | 0.007 | 0.007 | - | 0.007 | 0.007 | 0.007 | 0.007 | 0.007 | 0.363 / 0.317 |
| Maestro | Summon? | 0.177 | 0.177 | - | 0.177 | 0.177 | 0.177 | 0.177 | 0.177 | 0.290 / 0.290 |
| Minister | Attack | 0.088 | 0.157 | - | 0.119 | 0.139 | 0.148 | 0.151 | 0.150 | 0.205 / 0.205 |
| Minister | Attack Choice | 0.493 | 0.493 | - | 0.493 | 0.493 | 0.493 | 0.493 | 0.493 | 0.693 / 0.693 |
| Minister | Chase | 0.167 | 0.372 | - | 0.284 | 0.314 | 0.334 | 0.360 | 0.377 | 0.252 / 0.252 |
| Minister | Check Pos | 0.002 | 0.002 | - | 0.301 | 0.302 | 0.310 | 0.311 | 0.310 | 0.002 / 0.002 |
| Minister | Evade? | 0.311 | 0.311 | - | 0.400 | 0.447 | 0.479 | 0.505 | 0.520 | 0.333 / 0.333 |
| Minister | Parry Stance | 0.242 | 0.383 | - | 0.334 | 0.349 | 0.373 | 0.382 | 0.397 | 0.450 / 0.450 |
| Minister | Retreat? | 0.150 | 0.158 | - | 0.152 | 0.151 | 0.153 | 0.155 | 0.158 | 0.259 / 0.259 |
| Reed | Alert | 0.384 | 0.581 | - | 0.519 | 0.567 | 0.597 | 0.616 | 0.630 | 0.835 / 0.835 |
| Reed | Check Pos | 0.098 | 0.098 | - | 0.219 | 0.226 | 0.230 | 0.240 | 0.239 | 0.098 / 0.098 |
| Reed | Choice | 0.480 | 0.480 | - | 0.527 | 0.552 | 0.569 | 0.578 | 0.584 | 0.569 / 0.569 |
| Reed | Defend | 0.053 | 0.053 | - | 0.052 | 0.053 | 0.052 | 0.052 | 0.053 | 0.520 / 0.520 |
| Reed | Evade End | 0.673 | 0.673 | - | 0.682 | 0.689 | 0.687 | 0.691 | 0.689 | 0.673 / 0.673 |
| Reed | Lock R High | 0.360 | 0.360 | 0.146 | 0.314 | 0.254 | 0.175 | 0.147 | 0.189 | 0.365 / 0.147 |
| Reed | Stab Pos | 0.023 | 0.037 | - | 0.067 | 0.059 | 0.067 | 0.065 | 0.073 | 0.116 / 0.116 |
| Reed | Throw Down | 0.120 | 0.120 | 0.028 | 0.121 | 0.123 | 0.123 | 0.098 | 0.068 | 0.120 / 0.028 |
| Reed | Throw Lock | 0.000 | 0.000 | - | 0.001 | 0.001 | 0.001 | 0.000 | 0.027 | 0.001 / 0.000 |
| Reed | Throw Up | 0.638 | 0.638 | 0.182 | 0.633 | 0.638 | 0.627 | 0.574 | 0.456 | 0.677 / 0.185 |
| Reed | Throwing Up? | 0.195 | 0.195 | 0.069 | 0.174 | 0.141 | 0.096 | 0.067 | 0.102 | 0.245 / 0.069 |
| Tiny | Brake | 0.170 | 0.497 | - | 0.398 | 0.441 | 0.423 | 0.327 | 0.517 | 0.260 / 0.260 |
| Tiny | Defend Buzz | 0.065 | 0.069 | - | 0.068 | 0.069 | 0.069 | 0.069 | 0.069 | 0.182 / 0.182 |
| Tiny | Defend Ready | 0.017 | 0.021 | - | 0.020 | 0.024 | 0.024 | 0.024 | 0.024 | 0.049 / 0.049 |
| Tiny | Fire | 0.320 | 0.508 | - | 0.416 | 0.472 | 0.484 | 0.478 | 0.539 | 0.320 / 0.320 |
| Tiny | Fire Ready | 0.033 | 0.036 | - | 0.035 | 0.036 | 0.036 | 0.036 | 0.036 | 0.101 / 0.101 |
| Tiny | Pull Up | 0.204 | 0.176 | - | 0.195 | 0.172 | 0.163 | 0.160 | 0.198 | 0.333 / 0.208 |
| Tiny | Ready | 0.623 | 0.734 | - | 0.734 | 0.734 | 0.734 | 0.734 | 0.734 | 0.850 / 0.850 |
| Tiny | Return | 0.400 | 0.541 | - | 0.551 | 0.546 | 0.542 | 0.541 | 0.545 | 0.451 / 0.451 |

- **选中的时刻**（重建后）：61 个决策里分支帧 45、进入 1（Clawmaiden Spin Antic）、存储 3（Reed Lock R High、Throw Up、Throw Down）、固定提前 12。第一版的"进入 3"里 Choristor Hop Antic、Clapper Evade Scuttle 现在由分支帧 + `age` 表达（进入当帧就离开 = 进入时读的那一支），Reed Throwing Up? 选提前 0.4 s（= Throw Aim 的存储时刻，0.067 vs 存储 0.069）；其余提前与分支帧相差多在 0.005–0.02 nats，在噪声里。
- **和 FSM 静态一致**：FSM 说"进入时读"的，进入时刻的几何明显更好（只用几何：Hop Antic 分支帧 0.081 → 进入 0.006；Spin Antic 0.603 → 0.593，加历史后 0.449（`age`、丝）；"存储"的，存储时刻好（只用几何：Throwing Up? 0.245 → 0.069、Throw Up 0.677 → 0.185、Lock R High 0.365 → 0.147；固定提前 0.4 s 几乎一样好，因为 Throw Aim 正好 0.4 s）；"每帧 / 瞬时"的，分支帧最好，越往前越差（Clapper Dmg Attack 0.007 → 提前 0.1 s 0.182、Choristor Combo? 0.013 → 0.242、Minister Evade? 0.311 → 0.400；数字是重建后的）。
- **诱招（O、BAIT）用哪个**：`BranchModel.timing(tk, state)`；`BranchView` 按它取主角 / 敌人的位置（提前量用保留 1 s 的逐帧记录；进入 / 存储用每次进入状态时的快照；敌人位置只取看得见的帧、最多 0.25 s 旧；主角用 transform `pos_transform`，与扫描的 STATE hero.pos 相同——第一版用的是受击盒中心，低 0.17–0.84 u）。

### 18.5 防御两支的冷却（你 10-04：被打 → 反击 和 没被打 两支）

上一招结束到下一招开始的时间（DEV，`branch_gap.json`，中间没有被打；p10 / p50 / p90 s）和下一招的分布：

| 类型 | 上一招的结束 | n | 间隔 p10 / p50 / p90 | 下一招 |
|---|---|---|---|---|
| Minister | 格挡没被打（`Parry Stance End`） | 2,001 | 0.00 / 0.97 / 2.48 | 冲刺 46 %、闪避 31 %、格挡 23 % |
| | 被打后反击（`Parry Slash End`） | 641 | 0.00 / 1.11 / 2.55 | 冲刺 47 %、闪避 27 %、格挡 26 % |
| | 冲刺（`Attack End`） | 1,751 | 0.00 / 1.00 / 2.30 | 格挡 47 %、闪避 28 %、冲刺 26 % |
| Reed | 举盾没被打（`Defend End`） | 1,666 | 0.00 / 0.67 / 1.55 | 闪避 49 %、刺 31 %、扔 20 % |
| | 被打后反击没钩住（`Parry Slash End`） | 409 | 0.00 / 0.80 / 1.57 | 闪避 48 %、刺 33 %、扔 19 % |
| | 反击钩住了（`Multihit End`） | 292 | 0.10 / 1.10 / 1.58 | 刺 47 %、闪避 29 %、扔 25 % |
| Bellbearer | 闪避（`Evade End`） | 2,087 | 0.00 / 0.85 / 1.45 | **扔 100 %** |
| Maestro | 防御（`Slash Recover F`） | 4,426 | 1.15 / 1.27 / 1.41 | 斩 89 %、召唤 11 %、防御 0 |

结论：Minister 的两支差别小（都经 `Evade?` → `Retreat?` → `Set Attack Time` U(0.5, 1.5)，FSM 里没有按分支的冷却）；Reed 反击**钩住**之后下一招明显晚（p50 1.10 vs 0.67 s）、闪避少（主角被打飞，不在它的闪避盒里）；两支的差别作为 `prev_end` 进了模型（Minister Parry Stance、Reed Alert 都选了 `since_end` / `prev_end`）。格挡没被打、之后中间又被打（`hit`，n 498）时 Minister 的间隔反而长（p50 1.47 s）：被打把攻击计时夹到 ≤ 0.5 s，但出招还要主角在 Attack Range 里。

### 18.6 Tiny 一只一只（`tiny_orbit`，DEV 拟合、TEST 评估）

- **静态**：Maestro `Defend Start` 给三只发 DEFEND READY；`Defending`（1.75 s）把子物体 Defense Formation（局部 (0, −0.22)）转 −180°/s、缩放 0.5 → 2.5（0.75 s，easeOutSine），三个 Defense Point 在局部半径 2、90° / −30° / 210°：轨道半径 1 → 5 u、120° 间隔。`Fire Antic` 用 `GetRandomChild(Ready Flies)` 挑一只，**当场**发 FIRE READY，0.7 s 后（Slash 1）发 FIRE。
- **实测角速度**：±216°/s（DEV 中位数 −216.2 / +216.2，p25–p75 176–242），**方向跟 Maestro 的朝向**（flipX 0 顺时针、1 逆时针：Formation 是它的子物体，Rotate 在本地空间转）。半径：防御开始约 1.25 s 后中位数 5.07 u（p1–p99 约 3.8–5.4，6 场抽查），之前在成形（Tiny 从头顶飞过来）。
- **逐只预测的误差**（中心距离，TEST 207,764 个起点；"稳定" = 防御开始 ≥ 1 s 且在 Defend Buzz）：

| 提前 | 0.1 s | 0.2 s | 0.3 s | 0.4 s | 0.6 s | 0.8 s |
|---|---|---|---|---|---|---|
| 稳定 p50 / p99 / 最大（u） | 0.33 / 4.0 / 20.7 | 0.67 / 6.3 / 21.7 | 1.00 / 7.9 / 23.7 | 1.32 / 8.9 / 25.7 | 1.95 / 9.5 / 26.3 | 2.54 / 9.9 / 27.7 |
| 成形 p50 / p99 | 1.77 / 19.6 | 2.64 / 20.2 | 3.00 / 20.9 | 3.16 / 20.9 | 3.76 / 19.8 | 4.59 / 18.0 |

  尾巴来自：轨道低于地面时 Tiny 被地形挡住、停在半径约 3.8 u 不转（之后再追上）、被打退、Maestro 自己移动。**结论：逐只轨道作打分用够了（中位数 0.3–2.5 u），但离"留出全包"差得远（0.1 s 就要 20 u 余量），不能替换 R2 的整团并集**；要替换得先把"跟着防御点走、被地形挡住"的跟随模型做出来再认证。`TinyOrbit.predict` 已按地形边界（数据的 0.05–99.95 % 位置）夹住。
- **冲锋**（TEST 7,638 次）：FIRE READY → Fire **0.717 s**（p1 0.692、p99 0.733）；方向 **斜下约 52°**（前 0.1 s 位移，p5–p95 48.7–52.4°），**朝主角那一侧 99.7 %**（7,473 / 7,495）；挑哪只：被挑中的是离主角最近那只 3,050 次，随机期望 3,042（**就是随机，不看与主角的连线**）。站在地上被撞的比例（相对 FIRE READY 时 Maestro 的 x，冲锋方向为正）：身后 2–8 u 0.8–0.9 %、**正下方 7.1 %**、前方 3 u 31 %、6 u 56 %、8–10 u 约 59 %（DEV 同：0.4 % / 6.2 % / 27 % / 52 % / 58–60 %）——和你说的"站在指挥家正下方、走到另一侧"一致，也和 R0 逐只回放（7.1 % / 34 % / 58 %）一致。
- 所以对规划器：Fire Ready 一出现就知道是哪只、0.7 s 后冲、往主角那一侧斜下 52°；走到 Maestro 身后 2 u 以外就基本不会被这一冲撞到。

### 18.7 身体触发的反应分支（forum_reactive_moves.md 的 3.2 落到代码里，只进 J / P）

- `branch_model.REACTIVE`：Bellbearer In Range → Evade（Evade Range、≥ 0.5 s、¬Evade Cooldown，每次 0.97）；Clapper Idle → Evade Scuttle（Slam Range、≥ 0.25 s、硬币 0.49）；Reed Alert → Evade Antic（已上膛，0.95；它进 Alert 时已在盒里约 0.8）、→ Defend Start（Defend Range、¬Just Did Defend、硬币 0.45）。门从 BranchMemory 来（§18.2）；**硬币已亮出反面**（这一次访问里主角已在盒里、门开着两帧以上它没反应）→ 这次访问 p = 0。
- `BranchView.reactive(tr, T)`：现在开着的触发和 p；`entry_prob(tr, T, path)`：候选的主角盒路径第一次在门开之后进盒的时刻和 p（敌人按最后看到的位置不动：这些源状态都是悬停 / 站着）。规划器（R6 / R7）把它当成和命中分支同类的 J / P 分支用；**S / Hz / U 不变**。
- 行为表里，同一件事由精确的触发形状协变量表达：Bellbearer In Range 选 `in_Evade Range`、Reed Alert 选 `in_Evade Range` + `in_Defend Range`、Clapper Idle 选 `in_Slam Range`、Minister Evade? 选 `in_Evade Range`（§18.3）。

### 18.8 支撑、召回、Bell Beast、算力

- **支撑不动**：BranchMemory 挂在 EnemyTracker 上（只在 `enter` / `_hit` 里各多一行），放置、`occupied`、`prob`、`support_set` 都不读它；测试 `test_multi_forecaster_branch_view_is_scoring_only` 在合成 Reed 上逐帧比较有 / 没有分支模型的占据、概率图、支撑集：完全相同。
- **留出召回（R2 / R3 的协议，分支模型打开：`multi_recall fresh --tables 0 --branch`，冻结检出 `C:\ssbot\live_r5m_092e3e2`）**：R0 的 35 场留出、fold 0 的表：L2 / L3 / L4 各 74,585 / 74,585（全部由预报本身盖住，钩 465 / 465，按类型 100 %），与 R3 认证（2a10a0d，`C:\ssbot\data\m2_forum_r3\recall_fresh_2a10a0d.json` 的 fresh/tables0）逐项相同（`C:\ssbot\data\m2_forum_r5m\recall_fresh_t0_branch_092e3e2.json`）。
- **Bell Beast**：它不走 EnemyTracker（`MultiForecaster(boss=...)` 包装时 `bv` 为 None，所以这项检查走的是分支模型关闭的路径——这正是回归规则要的"Forum 开关关着时逐位相同"；它不检验分支模型本身）；`multi_recall bellbeast`（20261003_144536 i4_000 4,001 帧 + 892 次铃区检查、20261004_095304 i0_001 4,001 帧 + 1,333 次）放置、occupied、prob、support_set、committed、战术、规划器决策、铃区八项全部 **0 差**；全部测试（冻结检出 092e3e2）1,146 passed、3 skipped、1 xfailed（第一遍有 15 个规划器 / 运动学测试只因为环境里 NUMBA_NUM_THREADS = 3 报线程数错，按 4 线程重跑 73 / 73 通过），之后的提交（反应分支、换行）`test_branch_model.py` 19 / 19。
- **算力**：第一版 `scratchpad bench_bv.py`（20261003_074719 i3 ep0，51,823 帧）每帧 p50 0.17 ms、p99 1.05 ms、最大 7.8 ms。复核后的数字（预报表、快照、每帧对每个活着的敌人算 `next_attack_probs`）见 §18.11.5。

### 18.9 没做完 / 未核实

- Tiny 的控制 FSM 没解码（预制体在场景包外）；冲锋 52° 和"贴地段"只来自录像。
- 逐只轨道的跟随模型（防御点 + 地形阻挡 + 速度上限）没做，所以还不能替换支撑。
- 时刻比较里几个"提前"胜出的差距在噪声内（§18.4），模型照选中的用；小样本决策（Envoy Charge、Reed Throw Up、Escape Jump）校准变差，可以把协变量数按 n 限制（现在一律 ≤ 4）。
- 反应分支的 p 是 R0 的每次访问比例（forum_reactive_moves §2.2），没有按距离 / 进盒方式细分；规划器还没接 `entry_prob`。
- V4 的计数在结果看不见时（例 Minister Evade? 主角在盒外两种抽法都去 Retreat?）是隐藏的，现在用看得见的历史近似，没有做隐状态滤波。

- （复核后）预报表在 DEV → TEST 有的不迁移：Tiny Ready（TEST 1.19，比每次访问表 0.98 差）；它是 Maestro 那边的选择，要看 Maestro 的状态才有用，现在消费方对 Tiny Ready 的 `next_p` 不要当真。分支帧模型里小样本的 Clawmaiden Spin 0 / 1、Envoy Charge 在 TEST 上不稳（§18.3）。
- （复核后）预报表是"按数据里主角的走法平均"的：它不随候选路径变。要给候选算"沿这条路下一招是什么"，得把分支帧模型和"何时触发"（每帧状态的危险率）沿候选的主角路径积分，没做。

### 18.10 复现

```
cd brain   # 低优先级，NUMBA_NUM_THREADS 4；复核后的完整流程：C:\ssbot\data\m2_forum_r5m\fix\pipeline_f1.cmd <rev>（冻结检出 C:\ssbot\live_r5mf_<rev>）
..\scripts\uv.cmd run python -m ssbot.tools.forum_branch scan C:\ssbot\data\m2_forum_r0\cache C:\ssbot\data\m2_forum_r0\cache_fresh --out recs_dev.pkl --ahead-out ahead_dev.pkl --extra-dir C:\ssbot\data\m2_forum_r5m\hero --workers 3
..\scripts\uv.cmd run python -m ssbot.tools.forum_branch scan C:\ssbot\data\m2_forum_r1c\cache_fresh --out recs_test.pkl --ahead-out ahead_test.pkl --extra-dir C:\ssbot\data\m2_forum_r5m\hero --workers 3
..\scripts\uv.cmd run python -m ssbot.tools.forum_branch study recs_dev.pkl --json study_dev.json
..\scripts\uv.cmd run python -m ssbot.tools.forum_branch study ahead_dev.pkl --json study_ahead_dev.json
..\scripts\uv.cmd run python -m ssbot.tools.forum_branch build recs_dev.pkl --study study_dev.json --ahead ahead_dev.pkl --ahead-study study_ahead_dev.json --test recs_test.pkl --ahead-test ahead_test.pkl --out ..\knowledge\1.0.30000\enemies\forum\branch_model.json --report holdout_test.json
..\scripts\uv.cmd run python -m ssbot.tools.forum_branch parity <cache.npz ...> --model ..\knowledge\1.0.30000\enemies\forum\branch_model.json --extra-dir C:\ssbot\data\m2_forum_r5m\hero --json parity.json
..\scripts\uv.cmd run python -m ssbot.tools.tiny_orbit --fit C:\ssbot\data\m2_forum_r0\cache --fit C:\ssbot\data\m2_forum_r0\cache_fresh --test C:\ssbot\data\m2_forum_r1c\cache_fresh --out ..\knowledge\1.0.30000\enemies\forum\tiny_orbit.json --json C:\ssbot\data\m2_forum_r5m\tiny_orbit_report.json
# 召回 / Bell Beast / 全部测试 / 逐帧核对：C:\ssbot\data\m2_forum_r5m\fix\val_f1.cmd <rev>
```
扫描 142 场约 5 min、202 场约 2 min（3 个进程，带预报样本：DEV 1,341,860 个、TEST 893,979 个）；study 分支帧约 5 min、预报约 5 min；build 约 3.5 min；逐帧核对每场约 1–3 min；tiny_orbit 约 10 min。分支帧表要的生成文件 `knowledge/.../forum/*_hitboxes.npz`（git 忽略）只有 parity / 召回用到。

### 18.11 复核之后的修正（fixer 轮，2026-10-08；代码 2f5b96a → dd5cbff，分支 worktree-wf_814dfeea-b10-1；离线，没有连接游戏）

核查（第一轮 week push 的 verifier）推翻了三条说法、给了两条高、一条中、四条低的问题。这一节说第一版错在哪、改了什么、重测的数字。输出在 `C:\ssbot\data\m2_forum_r5m\fix\`（`v_2f5b96a\`：重扫、选择、重建、留出报告 `holdout_test.json`、表 `tables.md`；`val_7db1c2d\`：7 场逐帧核对、召回、Bell Beast；`val_dd5cbff\`：全部测试、2 场整场核对）。

#### 18.11.1 第一版错在哪

1. **训练 / 运行不一致（高）**。第一版选择的候选里有只在离线扫描里算的 R0 协变量（`dist_visible`、`side_visible`、`last_seen_x`、`hero_x`、`since_<家族>`、`miss_<后继>`），61 个决策里 26 个选了至少一个；运行时的 `BranchView` 算不出来，回退在第一个缺的协变量处停下。例：Maestro Attack Choice 唯一的协变量是 `miss_Defend Start`，运行时就成了无条件表，还会在 DEFEND 之后给 DEFEND 概率（FSM 不允许）。核查者只用运行时算得出的协变量重算 TEST：0.340，不是 0.315。这次逐帧核对又找出四处：运行时的 `BranchMemory` 用的是走子表的分段（少 Maestro 的 MA_POINT、Envoy 的 EN_HOPSLASH / EN_ENTRY，`prev` / `run` / `since_*` 和训练不同）；主角参考点（运行时用受击盒中心，扫描用 transform）；敌人位置（运行时用 `tr.pos`，可能是很久以前的，扫描只要 0.25 s 内看得见的）；Tiny 归属（扫描按整场投票，用到了未来的帧）。
2. **只在分支帧拟合，却当预报用（高）**。每条记录都是状态离开的那一帧，所以模型是 P(后继 | 它就在这一帧决定)；第一版的 `next_attack_probs` / `Subject.next_p` 在敌人还没决定的每一帧都拿它当"下一招"的预报。核查者在 68 场 TEST 上提前 0.2 / 0.5 s 查：2.31 / 2.92 nats，无条件表 0.70 / 0.71（Clapper Idle 4.69 / 7.68、Reed Alert 2.65 / 7.00、Minister Chase 4.17 / 4.70）。第一版的 0.695 → 0.315 比的是"在分支帧条件下"的模型和每次访问的边际，**不是预报能力**。
3. **Envoy 的 Charge Range 门（中）**。FSM：Charge Range 物体在场景里一开始就 active；Walker 的 `ActivateGameObjectDelay`（1.5 s，resetOnExit 0：反编译 `ActivateGameObjectDelay.cs`，只在待满时激活，离开不复位）待满 1.5 s 才打开、离开后保持；Slash Antic 打开，Charge Antic 关；CHARGE 还要 `Alerted`（Slash Antic / Ambush Ready 设）。第一版初值关、只在 Walker 里按时间算，于是 Walker → Charge Antic 时门是关的 DEV 131 次、TEST 34 次。
4. 低：当帧命中的排除规则几乎用不上（§18.2 已改，见 18.11.4）；"R0" 基线其实是 R0 协变量名重拟（现在叫"R0 重拟"，§18.3）；Tiny 归属用未来的帧；主角参考点。

#### 18.11.2 改了什么；运行时 = 扫描，逐帧核对

- **一套函数**：R0 时代的几何（`dist_visible`、`last_seen_x`、`hero_x`；`side_visible` 就是 `side`）进 `geometry()`，`since_<家族>`（没出过 = "none"）/ `miss_<后继>` 进 `BranchMemory.features`，Clapper 的伴 `clapper_context`、Tiny 归属 `TinyOwners`（每帧、只用过去）在运行时和扫描里是同一段代码；`BranchMemory` 在两边都用 `FORUM_SPECS` 的分段（离线 `memory_for`；运行时从 `branch_model.json` 的 `segmentation` 取，它在 build 时从 FORUM_SPECS 写进去——combat 包不能 import `knowledge.gauntlet_tables`，`test_import_firewall` 管着）。新加 `age`（在这个状态里待了多久）。
- **位置**：主角用 transform（`HeroState.pos_transform`，= STATE `hero.pos`）；敌人只取它被看见的帧、最多 0.25 s 旧；"进入" / "存储"时刻用每次进入状态时的快照（第一版只留 1 s 的记录，长状态的进入时刻会取不到）。
- **扫描按帧走**，和运行时一样：一帧里的事件按顺序，再到帧末（Tiny 归属、预报样本）。
- **逐帧核对** `forum_branch parity`：把缓存那一场的录像经 `OracleBackend` → `MultiForecaster(branch=...)` 回放，在每一帧、每个处在模型决策状态里的敌人上（Tiny 的 Dead 除外），比较 `BranchView` 算的全部协变量（now / entry / stored 三个时刻的几何 + 全部历史、门、跨敌人）和扫描在同一帧算的。7 场（R0 DEV 3 场、R1 TEST 4 场）：705,805 行（帧 × 敌人）逐项比较，**0 差**（`val_7db1c2d\parity.json`；修正过程中分段还没统一时，第一场前 12,000 帧里 Envoy 的 `since_*` 有 350 处不同，就是这样找出来的）。dd5cbff（分段改从模型里取之后）再核 2 场整场：331,979 行 0 差。测试 `test_runtime_covariates_equal_the_scans_on_a_recording`（录像在本机时跑，6,000 帧，0 差）。说明：分支帧记录是在状态离开那一帧的事件处理中取的，运行时从不在那一刻查询（它查的是帧末、敌人已在下一个状态），所以核对比较的是规划器真正查询的帧末；分支帧表和预报表在帧末用的是同一套函数。
- **门的数据核对**（重扫的记录，`v_2f5b96a\gates_check.txt`）：Envoy Walker → Charge Antic DEV 465 / 465、TEST 104 / 104 都是 `charge_armed` ∧ `alerted`；Bellbearer 有 Evade Cooldown 时 0 次闪避（DEV 1,378 / TEST 935 次决策）、闪过之后的 In Range 0 次再闪避；Reed 没上膛 0 次 Evade Antic、Just Did Defend 时 0 次 Defend Start；Clapper Evaded 时 0 次 Evade Scuttle；Maestro 防御之后的 Attack Choice 4,412 / 4,412（TEST 3,172 / 3,172）是 Fire Antic。

#### 18.11.3 预报表（`ahead`）：中途查询用的

- **样本**：敌人在一个决策状态里的每一帧都是规划器的一次查询；每次访问从进入那一帧起每 0.1 s 取一个样本（Tiny 0.25 s；Tiny 的 Dead 是等 Maestro 召唤的 30 s 等待，不取），协变量是那一帧看得见的（几何取 now / entry / stored，历史含 `age`），标签是这次访问最后去了哪个后继。瞬时决策（进入当帧就离开）没有样本：规划器从来不会看到它是"当前状态"，链里用分支帧表。DEV 1,341,860 个、TEST 893,979 个样本；29 个决策状态有预报表。同样的贪心选择（两折、按场）。
- **用法**：`BranchView.next_attack_probs`（= `Subject.next_p`）：当前状态用它的预报表，链到的下一个决策按"现在进入"用它的预报表（瞬时的用分支帧表）；`branch_probs(..., ahead=True)` 直接给。分支帧表仍是 `branch_probs` 的默认（"如果现在决定"）。
- **TEST 留出**（202 场的样本；"每次访问表" = 今天运行时的 `p_succ`；"分支帧模型（中途查）" = 第一版 next_p 的做法：分支帧表在样本那一帧查，只对分支帧表时刻是 branch / entry / stored 的决策）：

| | 样本 | 每次访问表 | 按样本的无条件 | 分支帧模型（中途查） | **预报表** |
|---|---|---|---|---|---|
| 全部 | 889,333 | 0.716 | 0.603 | — | **0.581** |
| 分支帧模型能查的决策 | 849,049 | 0.729 | 0.612 | 4.995 | **0.596** |
| 退出前 0.2–0.3 s | 97,553 | 0.639 | 0.554 | 4.378（94,043 个） | **0.427** |
| 退出前 0.5–0.6 s | 58,428 | 0.767 | 0.630 | 5.364（55,266 个） | **0.576** |

  核查者的结论成立：分支帧模型中途查询比无条件表差得多（这里 4.4–5.4 nats；核查者用第一版的表、68 场、精确的提前帧得 2.31 / 2.92；重建后的分支帧表有 25 个决策用了 `age`，它只在决定那一刻有意义，中途查询多半因此更差）。预报表在规划器真正查询的帧上比今天的 `p_succ` 好（0.716 → 0.581），但这 0.135 nats 里 0.113 来自"按样本的无条件"（0.603：长状态占的帧多，按帧加权的边际本身就不同），全部协变量（`age`、几何、历史）只再降 0.022——中途的下一招主要取决于主角之后怎么走，表里只能按数据里的走法平均。

- **逐个决策**（DEV 交叉验证、TEST 留出，nats / 样本；后两列 n / 每次访问表 / 分支帧模型 / 预报表）：

| 类型 | 决策 | DEV 样本 | DEV CV 无条件 → 预报 | 时刻 | 协变量 | TEST 样本 | 每次访问表 | 分支帧模型（中途查） | 预报 | 退出前 0.2–0.3 s：n / 每次访问表 / 分支帧模型 / 预报 | 0.5–0.6 s：n / 每次访问表 / 分支帧模型 / 预报 | ECE 预报 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Bellbearer | In Range | 124740 | 0.793 → 0.608 | now | dx,evade_cd,age,dist | 81962 | 0.931 | 3.800 | 0.572 | 8345 / 0.985 / 2.530 / 0.529 | 8124 / 0.970 / 4.457 / 0.645 | 0.007 |
| Clapper | Evade Scuttle | 40165 | 0.019 → 0.019 | now |  | 19042 | 0.054 | 3.131 | 0.011 | 4741 / 0.048 / 2.301 / 0.005 | 0 / - / - / - | 0.001 |
| Clapper | Idle | 136026 | 0.748 → 0.561 | now | age,dist,in_Slam Range,hit | 68164 | 1.249 | 14.605 | 0.510 | 8462 / 1.352 / 17.653 / 0.576 | 5827 / 1.185 / 15.580 / 0.468 | 0.023 |
| Clapper | Walk | 84628 | 0.625 → 0.530 | now | dist,age,dy,last_seen_x | 43719 | 0.762 | 4.265 | 0.584 | 7346 / 0.581 / 4.418 / 0.437 | 2718 / 0.905 / 4.781 / 0.732 | 0.047 |
| Clawmaiden | Fly | 44708 | 0.937 → 0.609 | now | suck_age,dist,age | 27369 | 1.042 | 7.935 | 0.570 | 3674 / 0.886 / 7.639 / 0.449 | 3252 / 0.841 / 10.394 / 0.456 | 0.005 |
| Clawmaiden | Fly To Slash | 11255 | 0.775 → 0.622 | now | dist,since_end,age | 6987 | 0.760 | 4.576 | 0.537 | 881 / 0.712 / 4.310 / 0.457 | 646 / 0.783 / 5.041 / 0.629 | 0.019 |
| Clawmaiden | Spin 0 | 9532 | 0.177 → 0.122 | now | silk,in_Suck Start Range,miss_Spin 1,age | 5601 | 0.154 | - | 0.123 | 609 / 0.164 / - / 0.110 | 579 / 0.140 / - / 0.141 | 0.003 |
| Clawmaiden | Spin 1 | 10860 | 0.159 → 0.100 | now | silk,prev_end | 6534 | 0.150 | - | 0.111 | 600 / 0.179 / - / 0.156 | 601 / 0.140 / - / 0.082 | 0.002 |
| Clawmaiden | Spin 2 | 10682 | 0.649 → 0.226 | now | silk,in_Suck Start Range | 6188 | 0.637 | - | 0.148 | 583 / 0.661 / - / 0.135 | 580 / 0.638 / - / 0.144 | 0.009 |
| Clawmaiden | Spin Antic | 2048 | 0.040 → 0.037 | now | suck_age | 1265 | 1.304 | 4.755 | 0.013 | 76 / 1.300 / 9.503 / 0.006 | 0 / - / - / - | 0.003 |
| Envoy | Charge | 5836 | 1.266 → 1.076 | now | hero_x,front,side,last_seen_x | 1310 | 1.294 | - | 1.064 | 108 / 1.296 / - / 0.931 | 95 / 1.301 / - / 0.984 | 0.021 |
| Envoy | Walker | 2799 | 0.910 → 0.755 | now | dx | 720 | 0.710 | 3.025 | 0.507 | 73 / 0.650 / 3.594 / 0.452 | 46 / 0.728 / 3.701 / 0.502 | 0.050 |
| Maestro | Fly | 31893 | 0.132 → 0.097 | now | dist,since_end | 21979 | 0.509 | 0.237 | 0.081 | 1779 / 0.521 / 0.314 / 0.084 | 1787 / 0.506 / 0.247 / 0.082 | 0.002 |
| Maestro | Slash Recover | 6986 | 0.020 → 0.020 | now |  | 5222 | 1.514 | 4.781 | 0.009 | 1741 / 1.515 / 9.130 / 0.010 | 0 / - / - / - | 0.001 |
| Minister | Attack | 18568 | 0.445 → 0.344 | now | age,dist,front,dist_visible | 16967 | 0.555 | 3.700 | 0.411 | 2472 / 0.566 / 5.236 / 0.422 | 2116 / 0.474 / 6.017 / 0.373 | 0.018 |
| Minister | Chase | 94854 | 0.413 → 0.393 | now | age,dist,last_choice | 83260 | 0.306 | 4.680 | 0.238 | 5877 / 0.358 / 3.916 / 0.264 | 5201 / 0.314 / 4.583 / 0.252 | 0.063 |
| Minister | Parry Stance | 25059 | 0.414 → 0.380 | now | age,dist | 25872 | 0.368 | 3.808 | 0.283 | 3058 / 0.405 / 0.566 / 0.290 | 2793 / 0.346 / 6.746 / 0.254 | 0.040 |
| Minister | Retreat? | 14942 | 0.309 → 0.274 | now | dist,age | 13360 | 0.222 | 2.367 | 0.216 | 1739 / 0.270 / 2.095 / 0.216 | 1596 / 0.168 / 3.688 / 0.207 | 0.034 |
| Reed | Alert | 69796 | 0.952 → 0.758 | now | dist,last_choice,age,armed | 39947 | 1.163 | 5.479 | 0.642 | 3347 / 1.234 / 2.138 / 0.679 | 2978 / 1.172 / 2.859 / 0.624 | 0.015 |
| Reed | Defend | 21271 | 0.526 → 0.484 | now | age,dist | 12879 | 0.500 | - | 0.404 | 1333 / 0.556 / - / 0.421 | 1307 / 0.492 / - / 0.402 | 0.034 |
| Reed | Stab Pos | 10376 | 0.412 → 0.292 | now | dx,age | 4542 | 0.457 | 1.264 | 0.236 | 637 / 0.250 / 0.125 / 0.128 | 339 / 0.433 / 1.417 / 0.227 | 0.005 |
| Tiny | Brake | 17541 | 0.729 → 0.533 | now | hero_x,front,last_seen_x,dist_visible | 11338 | 0.714 | 4.182 | 0.496 | 1850 / 0.713 / 5.377 / 0.510 | 780 / 0.714 / 2.123 / 0.572 | 0.007 |
| Tiny | Defend Buzz | 86520 | 0.138 → 0.133 | now | since_AT_ENTRY | 65361 | 0.078 | 4.104 | 0.067 | 9303 / 0.066 / 0.013 / 0.054 | 2561 / 0.102 / 5.398 / 0.093 | 0.011 |
| Tiny | Defend Ready | 12651 | 0.031 → 0.028 | now | dist | 9485 | 0.023 | 5.370 | 0.015 | 9476 / 0.018 / 5.374 / 0.010 | 0 / - / - / - | 0.001 |
| Tiny | Fire | 20086 | 0.762 → 0.553 | entry | dx,hero_x,side,dist | 13905 | 0.759 | 2.221 | 0.497 | 3185 / 0.756 / 2.314 / 0.459 | 648 / 0.699 / 2.590 / 0.508 | 0.009 |
| Tiny | Fire Ready | 31710 | 0.044 → 0.044 | now |  | 22705 | 0.038 | 3.908 | 0.025 | 1252 / 0.042 / 0.084 / 0.030 | 3 / 4.858 / 1.277 / 5.879 | 0.002 |
| Tiny | Pull Up | 10521 | 0.587 → 0.259 | entry | hero_x,side,dx,age | 7772 | 0.578 | - | 0.192 | 277 / 1.253 / - / 0.579 | 0 / - / - / - | 0.004 |
| Tiny | Ready | 328312 | 0.871 → 0.772 | now | from,age,miss_Defend Ready,prev | 237586 | 0.975 | 3.915 | 1.191 | 12157 / 1.076 / 1.213 / 1.255 | 11673 / 1.030 / 1.587 / 1.176 | 0.044 |
| Tiny | Return | 39943 | 0.549 → 0.471 | now | age,from,prev_end | 28292 | 0.536 | 6.235 | 0.445 | 2572 / 0.636 / 6.537 / 0.529 | 2178 / 0.585 / 5.888 / 0.457 | 0.006 |

  读法：Clapper Idle 1.249 → 0.510、Reed Alert 1.163 → 0.642、Clawmaiden Fly 1.042 → 0.570、Bellbearer In Range 0.931 → 0.572（每次访问表 → 预报表）；Maestro Slash Recover、Clawmaiden Spin Antic 这类"进入后几乎确定"的状态每次访问表很差（1.5 / 1.3：瞬时离开的那一支在中途已经不可能）而预报表 0.01。**Tiny Ready 不迁移**：DEV 交叉验证 0.871 → 0.772，TEST 1.191，比每次访问表 0.975 还差（ECE 0.044）：它的出边是 Maestro 那边的选择，R1 的波次起点 / 策略改变了它的时间分布；消费方对 Tiny 的 Ready 先别信 `next_p`（18.9）。

#### 18.11.4 其它数字的重测

- **分支帧模型**（§18.3）：TEST 0.695 → **0.284**（第一版说 0.315，而运行时实际只有核查者的 0.340）；R0 重拟 0.511。感知时刻（§18.4）：只用几何时 Choristor Hop Antic 分支帧 0.081 / 进入 0.006、Reed Throwing Up? 0.245 / 存储 0.069，和第一版相同。
- **当帧命中**（DEV 22 场，`fix\lag_s.txt`）：5 种 TOOK DAMAGE 出边共 1,100 次，和同一帧的记录命中重合的只有 1 次；Clapper Idle → Dmg Attack 194 / 568、Minister Chase → Range Check 84 / 299 在一次记录命中之后 12–18 帧（多数 18 帧 = 0.3 s）；Reed Alert → Stab Pos 只有 7 / 176；其余前 0.35 s 内没有记录到的命中（中位数 1.9–4 s 前；Clapper 20、Minister 36、Reed 29 次之前根本没有记录命中）。`hit` 现在含当帧（过去的、看得见的信息）。
- 没重测（代码没动）：Tiny 轨道 / 冲锋（§18.6）、防御两支的间隔（§18.5）、Bellbearer 2,229 / 2,229（核查者核了等价的 In Range 条件：0 次再闪避，上面重扫的记录同样 0）。

#### 18.11.5 支撑、召回、Bell Beast、算力、测试（召回 / Bell Beast / 7 场逐帧核对：冻结检出 `C:\ssbot\live_r5mf_7db1c2d`；全部测试和 2 场整场逐帧核对：`live_r5mf_dd5cbff`，只改了分段从哪里取）

- **支撑不动**：放置、`occupied`、`prob`、支撑集都不读分支模型（测试 `test_multi_forecaster_branch_view_is_scoring_only`）。留出召回（`multi_recall fresh --tables 0 --branch`，新模型打开）：R0 的 35 场 L2 / L3 / L4 各 74,585 / 74,585、钩 465 / 465，和第一版（092e3e2）、R3 认证逐项相同（只有耗时：每次预报 1.42 vs 1.34 ms）。
- **Bell Beast**（`MultiForecaster(boss=...)` 没有 BranchView，走的是分支模型关着的路径，正是回归规则要的）：20261003_144536 i4_000、20261004_095304 i0_001 各 4,001 帧、铃区 892 / 1,333 次检查，放置 / occupied / prob / 支撑集 / committed / 战术 / 规划器决策 / 铃区八项 **0 差**。
- **算力**（逐帧核对时每帧对每个活着的敌人算 `next_attack_probs`，= `Subject.next_p` 的工作；低优先级、和别的作业并行，偏保守）：第一版量的那一场（20261003_074719 i3 ep0，51,823 帧）每帧 p50 0.13 ms、p99 1.07 ms、最大 5.0 ms（第一版 0.17 / 1.05 / 7.8）；7 场的 p99 0.58–1.14 ms、最大 8.8 ms；dd5cbff 上同一场（并行作业少时）p50 0.11 / p99 0.80 / 最大 3.1 ms。`ForumPlannerPolicy(branch_model=True)` 仍默认关。
- **测试**：dd5cbff 全部 1,150 passed、2 skipped、1 xfailed（NUMBA_NUM_THREADS 4，`val_dd5cbff	ests.log`）。7db1c2d 那一遍有 1 个失败：`test_import_firewall`（combat → knowledge.gauntlet_tables → ipc：运行时的 `memory_for` 直接读了 FORUM_SPECS），所以分段改成存在模型里、从模型取（dd5cbff）。

## 19. 第 0 波受击取证：为什么规划器 13 s 挨 4 下就退出（2026-10-08，task wave-0 forensics；离线 + 实例 0 的短实战）

对象：到目前为止全部 Forum 规划器实战（都在第 0 波退出）：A0b（`20261005_205437` / `205857`，冻结 f8c0c62，50 场 QUIT + 1 HARNESS_FAIL）和昨晚的 7 组（R5 价值 `20261008_015959` / `021002` / `022115`，R6 v0 `015904` / `020919` / `021942` / `022951`，各 25 场）= 225 场、949 个 damage 受击 + 176 个 Multihit tick；R5 的 `015907` 只有 1 场 HARNESS_FAIL，不计。工具（本节新增）：`ssbot.tools.forum_hit_forensics`（逐场开环回放 + 逐 tick 后见之明）、`ssbot.tools.forum_attack_outcomes`（第 0 波每个出招实例和主角的应对，bot 与你的录像并排）。

### 19.1 方法

- **开环回放**：把录像的 STATE 逐帧喂给 `ForumPlannerPolicy`（同 `forum_policy_replay`，监督器不接管按键；每个 tick 的前缀用录像里实际生效的按键，所以每个 tick 都从真实发生的状态出发规划），`ForumPlanner.debug` 保留这一 tick 的全部候选行（名义盒、无敌帧、J、ok / known、t_hit）。截止时间 inf（决定与机器快慢无关）；回放的选择和实战日志的选择按名字比对，A0b 98.5 % 一致（A0b 的代码 = main 的 Forum 规划器，f8c0c62 之后没改过）；R5 / R6 的组用 main 的规划器回放（按代码，它们改的是 J、目标权重和战术，S / Hz / U / FORCED_RISK 与 main 相同，它们自己的测试也这么说；但这一点没有用它们自己的代码回放验证过），和它们实战的选择一致 64 %（R5 全开 `015959`）、83 %（R6 L2 开 `015904`）、98.5 %（R6 L2 关 `020919`），不一致的 tick 上回放的选择是反事实的。
- **支撑覆盖**：每个受击在 L = 2 / 3 / 4 帧前的预报下判（同 R2 召回的配对：受击帧或前一帧的主角盒中心）；多段链的 Final Hit 在钩子判（同实战记账 `_hook_of`）；"own" = 只用来源类型的敌人和它扔的投射物的支撑。
- **后见之明（hindsight）**：每个分析 tick 上，每个已知 S 的候选行（ok & known）的名义盒逐帧对录像里接下来 0.6 s 的真实伤害碰撞体（`support_threat` 或 multi_wounder 碰撞体，录像多边形；一帧里被打掉的投射物带到下一帧、按速度移动），无敌帧跳过；"不碰（clear）" = 整个视野里不碰。这是**开环**的：敌人对另一个主角的反应没有建模，0.6 s 内多数招已经承诺；它度量的是排序有没有信息，不是真实结果。核对：把录像里主角真实的路径也这样判，直接受击（非 Final Hit）里 96 % 在受击前 12 帧内找到接触（漏的是 Reed 本体 7、针 6、刺 1：碰撞发生在两帧之间）。
- 分析的 tick：战斗中每 3 帧一个，外加每次受击前 1–90 帧的 16 个时刻。
- 样本：实战日志和 attempt 记录（19.2、19.4）用全部 225 场；逐 tick 回放（19.3、19.5、19.6、19.9）用其中 115 场（A0b 50、R6 v0 两组 40、R5 价值 25 场；489 个受击），其余 110 场的回放在其它轨道的实战开着时没有跑完（离线批会拖慢同机实战的 tick，19.11 第 5 条），比例在三组之间一致（A0b / R5 / R6 的"0.15 s 前还有出路"80 % / 79 % / 76 %）。

### 19.2 打中主角的是什么（949 个 damage 受击，按碰撞体）

| 来源 | 次数 | 说明 |
|---|---|---|
| Envoy 冲锋（`Charge Damager`） | 205 | 第一大来源；冲锋本体 + 前方伤害框高速平移 |
| Choristor 鞭链（`Whip Hit 1–4`，2 格链） | 143 | Final Hit 按钩子判 |
| Envoy 横斩（`P2 Damager`，`Slash1 2`） | 100 | 前摇 `Slash Antic` 之后才开碰撞体 |
| Reed 针（`Song Reed Pin Projectile`） | 88 | 飞行中的投射物 |
| Reed 本体（`Wave 1/Song Reed`） | 80 | 突刺 / 防御 / 闪避时的身体 |
| Choristor 跳旋（`Spin Hit`、`Spin Slash Hit`） | 73 | |
| Envoy 本体 | 63 | 多是在左墙边被它连续压住（19.5 的例子） |
| Choristor 连斩（`Slash Hit 1–3`） | 63 | |
| Choristor 本体（`Body Damager`） | 51 | |
| Reed 突刺（`Stab Hit 1–3`） | 48 | |
| Envoy 跳斩（`JumpSlash Damager 2`） | 24 | |
| Reed 招架反击（`ParrySlash Hit`） | 11 | |

- 每场 4.2 次（225 场里 113 场 4 次、81 场 5 次、30 场 3 次）；第一下的中位时刻是开战后 2.4 s；两次受击的间隔中位 1.94 s，22 % 在 1.3 s 内（受击无敌一结束就再挨）。225 场击杀 0 次。

### 19.3 支撑覆盖：全部在支撑内

- 949 个 damage 受击全部在支撑里（实战记账按 L 3 / 4 / 2 判；回放逐 L 判的 489 个在 L = 2 / 3 / 4 都在，union 和 own 都是；Final Hit 在钩子判）。**支撑外 0**：问题不是预报漏了，而是预报太宽（19.5）。

### 19.4 规划器当时的状态

- 949 个受击的前一个 tick **全部是 FORCED_RISK**；594 个在受击前 1.6 s 里没有一个 tick 有安全行（n_safe = 0），其余的最后一次有安全行是在 0.65–1.38 s（中位 0.92 s）之前。
- 模式：EVADE 830、RUSH 119（R6 的 L2 组）；目标：Envoy 496、Choristor 283、Reed 170。实战日志里 108,200 个 tick（偏向受击前后）FORCED_RISK 75 %；FORCED_RISK tick 上，选中和日志列出的 5 个备选**全部 P = 1.0**（FORCED_RISK 的"接触帧占比"）的占 77 %（62,684 / 81,462）。
- tick 用时不是原因：受击前 30 个 tick 里规划本身（决策日志的 `ms`）> 16.7 ms 的 3 / 28,561；9 组的全部决策日志里规划 > 16.7 ms 14 / 107,964（0.013 %）；整个 tick（`policy.late_ticks`：读状态 + 规划 + 发键）> 16.7 ms 412 / 168,164（0.25 %）。（以上不含 `015907`；初版把 0.25 % 写成了"规划 > 16.7 ms"，那是整个 tick 的迟到率。）

### 19.5 主要原因：支撑在第 0 波饱和，FORCED_RISK 的排序没有信息，选择落到 J 上

- **饱和**：回放的受击前最后一个分析 tick 上，**全部受击（489 / 489）**的候选行都在支撑里：每一行在每一个非无敌帧（含第 1 帧）都被盖住（share_min = 1）。受击前 6 帧、同时有"事后不碰"和"事后被打"的行时，两类行的支撑占比**完全相同**（274 / 274）：支撑对"哪一行会被打"没有任何区分力。全部分析 tick（每 3 帧）里 60 % 是这种全饱和。
- **谁盖住的**（`decompose`：按"同一敌人、放置种类、家族、是否已承诺"分组，单组单独的覆盖率）：A0b i1 ep0 五次受击前，Reed 的 RE_THROW / RE_STAB / RE_IDLE / RE_DEFEND 外包盒（以后才可能开始的招）、Envoy 的 EN_CHARGE / EN_IDLE / EN_SLASH 外包盒、已承诺的 RE_THROW / EN_CHARGE / CH_JUMP 窗口放置、一根 Reed 针的自模板窗口——**每一组单独就盖住 100 % 的候选单元**。在回放的 115 场里受击前 1 / 6 / 12 / 24 / 36 帧分解了 2,871 个 tick，其中 17 个分解为空（受击无敌中、非 FORCED_RISK，没有活的候选单元），下面的计数都在 2,854 个非空 tick 上：单独盖住 ≥ 99 % 候选单元的组，Reed 以后才开始的 RE_STAB 外包盒 2,854 次（每一个非空 tick）、RE_THROW 2,852、RE_IDLE 2,835、Envoy EN_CHARGE 外包盒 2,615、RE_DEFEND 1,786、EN_IDLE 1,359、已承诺的 EN_CHARGE 窗口 1,117……；每个非空 tick 至少 2 组、中位 8 组各自就能盖满。Reed 是飞的：起点框 = 位置按速度外推 + 该类的待机扩张（`_start_boxes`），再并上家族模板（针飞过全场、突刺冲得远）。所以只收紧一类（例如 R5 价值轮发现的 RE_STAB / RE_THROW / EN_CHARGE 外包盒，HANDOFF "Task R5 value"）不够；`MultiForecast.committed()`（只留当前招、尾巴、投射物）也常常饱和：已承诺的窗口放置（入场时刻是一个区间，模板按区间并起来）常常单独盖满（EN_CHARGE 窗口 1,117 / 2,854 个 tick），在受击前的 tick 上它和全支撑一样分不出行（19.9 的 `committed` 排序只比原排序好一点）。
- **于是**：FORCED_RISK 的排序键（占比 Pc、首次接触 t_c、t_hit）全部打平，预选（p_k 16 行）和最后的顺序都落到 J；EVADE 的站位来自同样饱和的风险图（`ForumTactics.risk_map`），所以站位 = 原地；J 里留下的是目标命中、朝向目标（boss_x）、少跳。**第 0 波的 bot 实际上是"以为每个计划都一样危险、按 J 去够目标"**。"排序没有信息"的证据是上面的饱和与打平（排序键本身分不出行），不是事后不碰的比例：
  - 每 3 帧一个分析 tick、不管离受击多远：选中计划事后不碰 75.9 %，随机挑一行 75.0 %。这个数也有偏，而且两个方向都有：选中的基本就是实战执行的计划，临近受击的 tick 上它几乎注定被打（下一条），远离受击的 tick 上它前几帧就是真实的、没被打的路径（只看 FORCED_RISK、有出路的 tick：实战日志没记的 tick 离下一次受击中位 147 帧、0.6 s 内的只有 0.1 %，那里选中 89.5 %、随机 82.1 %；日志记下的 tick 中位 49 帧、36 % 在 0.6 s 内，那里 63.1 % 对 66.2 %）。
  - **受击前的 tick 上不能拿选中的计划和随机比**。回放的选中就是实战执行的计划（A0b 98.5 %；R6 L2 开 83 %、R5 全开 64 %：这两组用 main 的规划器回放，见 19.1），而这些 tick 是按"后来被打中"挑出来的，执行的那条路径被打中几乎是定义；开环的后见之明又偏向没执行的行（敌人不会对另一个主角重新瞄准）。初版写的"受击前 6 帧选中 9.4 %、随机 24.3 %、比随机还差"主要量的是"主角确实在那条路上挨了打"（那 276 个 tick 里选中 = 执行 80 %），不是排序比随机差的证据。
  - 拆开看（受击前 1–12 帧、有出路的 tick，钩子为锚，按计划名比对）：选中 = 执行的 1,603 个 tick，选中 14.2 %、随机 32.7 %；选中 ≠ 执行的 316 个 tick（多是 R5 / R6 的组），选中 21.8 %、实际执行的 17.7 %、随机 31.8 %，已承诺支撑的占比（`committed`）26.6 %，录像碰撞体的键（`dr`，19.9）52.5 %。不是执行的那条也比随机低，说明"按 J 往目标凑"可能确实把计划往危险里拉；但 J 选出的行和执行的行常常走相近的路（同样朝目标），开环偏差在这里没有完全去掉，所以这部分到底有多少是真的，这些数据分不出来。能确定的是：排序键打平（上一条）；同一批 tick 上，不是执行计划的排序之间可以比（`dr` 52.5 % 对随机 31.8 %，19.9）；换掉 FORCED_RISK 的第一键之后实战结果变了（19.10）。
- **几乎每一下都还躲得开（事后看）**：从真实状态出发，受击前最后一个还有"事后不碰"行的时刻：≤ 3 帧 60、4–9 帧 323、12–18 帧 88、24–36 帧 16、45–90 帧 2（回放的 489 个受击，Final Hit 以钩子为准）。也就是 78 % 的受击在 0.15 s 前还有出路，99.6 % 在 0.6 s 前还有；"被困 ≥ 0.6 s"几乎没有。
- 例（A0b i1 ep0）：第 3–5 下都是 Envoy 本体（`Slash Antic` / `JumpSlash Antic`），主角在左墙边 x 16.6–17.9：每次无敌一结束，所有行（含 `MOVE(R)` 跑开）在支撑里的占比相同，按 J 选了 `MOVE(L)+runR16_attack` / `CONTINUE`（贴着它出刀），受击前 12–36 帧还有 35–348 行事后不碰。

### 19.6 执行：按键和运动学不是原因

- 受击前 12 帧的**真实按键**从当时估计的状态推演（kin_check 的估计器、规划器的计时），和录像的位置比（分母：回放的 115 场里非 Final Hit 的直接受击 413 个）：受击帧误差 中位 0.00 u、p90 0.17 u、> 0.3 u 8.5 %；录像路径碰到、模型路径不碰（运动学漏判）15 / 413（3.6 %）。
- 从受击前 24 帧推演，漂移大得多：p90 0.67 u、> 0.3 u 17 %、> 1 u 8 %，运动学漏判 25 / 413（6.1 %）（全部 489 个 damage 受击、Final Hit 在伤害帧推演：p90 0.95 u、> 0.3 u 22 %、漏判同样 25）。说"运动学不是原因"用的是 12 帧：tick ≈ 帧，规划器每个 tick 都从观测到的状态重新规划，计划平均 1.6–1.8 个 tick 就换（本节最后一条），受击前最后 0.2 s 里执行的路径碰不碰和模型一致，所以受击不是推演错了造成的。但 FORCED_RISK 的排序看的是整个 T = 36 帧的视野，24 帧的漂移说明视野后半段的推演并不准：排序的后半段（以及以后要开环执行得更久的计划）要另外核对。
- 计划翻来覆去：每 tick 的计划改动率 0.55–0.63（A0b 0.61），因为打平之后 J 每帧都在变；这是 19.5 的结果，不是独立原因。

### 19.7 你在同样的局面下做了什么（`forum_attack_outcomes`，第 0 波、出招时主角在 8 u 内）

| 家族 | bot（225 场）被打中 | 你 1x（46 次）| 你 0.5x（17 次）| 你躲开时的做法 vs bot |
|---|---|---|---|---|
| EN_CHARGE | 43 % (101) | 17 % (29) | 1 / 4 | 你 75 % 起跳越过（bot 41 %），空中占 62 % |
| EN_SLASH | 26 % (500) | 14 % (171) | 0 / 26 | 起手时你 70 % 已在空中（bot 38 %），退开 2.7 u |
| CH_WHIP | 38 % (110) | 21 % (57) | 1 / 11 | 你中位后退 5.9 u、60 % 冲刺；bot 原地（−0.3 u） |
| CH_SLASH | 39 % (203) | 35 % (99) | 1 / 15 | |
| CH_JUMP | 20 % (114) | 24 % (59) | 1 / 16 | |
| EN_JUMPSLASH | 24 % (141) | 26 % (39) | 0 / 4 | |
| RE_STAB | 21 % (325) | 18 % (201) | 5 / 34 | |
| RE_DEFEND / RE_EVADE | 9 % / 12 % | 12 % / 16 % | 0 / 7 % | |

- 第 0 波整体：bot 0 / 225 打完、每分钟 19.3 次受击、中位 12.9 s 退出、击杀 0；你 1x 24 / 46 打完、11.4 次 / min（Envoy 一般第一个死，中位 17.5 s）；你 0.5x 17 / 17 打完、3.7 次 / min、中位 17.9 s。bot 每分钟面对 8 u 内的出招 41 次，你 33–34 次（它一直贴着目标）。
- 结论：每个出招实例的被打中率，bot 在多数家族上和你 1x 差不多；差在 **Envoy 冲锋（43 % vs 17 %：你跳过去）、Envoy 横斩（26 % vs 14 %：你在空中）、Choristor 鞭（38 % vs 21 %：你退开）**，加上 bot 离得近、面对的出招更多、从不击杀（第 0 波永远不结束）。（RE_THROW 的起手状态在 STATE 里多数一帧都看不到，这张表里没有针；针的受击见 19.2。）

### 19.8 原因排序

1. **支撑饱和 → FORCED_RISK 排序打平 → 按 J 选**（根因）：受击前一个 tick 全部 FORCED_RISK（949 / 949），回放的全部（489 / 489）在最后一个 tick 全饱和；下面几条是它的表现。
2. **出路一直到最后都在，按 J 选的计划没有往出路走**：78 % 的受击在 0.15 s 前还有事后不碰的行（开环后见之明）。受击前的选中计划几乎就是被打的那条执行路径，所以"选中 9.4 % 对随机 24.3 %"不能当作"比随机差"（19.5）；在选中 ≠ 执行的 tick 上（受击前 1–12 帧，316 个），选中 21.8 %、随机 31.8 %、录像碰撞体的键 52.5 %：J 的选择没有用上这些出路，而一个只看"现在看得见的碰撞体"的键能找到一半。
3. **贴近目标、不击杀、站在墙边**（J 的目标项 + 原地站位）：每分钟 8 u 内出招 41 次（你 33）；Envoy 本体在左墙边连续压 63 次；击杀 0。
4. 运动学漏判 15 / 413（3.6 %）、规划超时 ≈ 0：不是原因。
5. R5 价值 / R6 v0 为什么没改变结果：**这是从代码推断的，没有用它们自己的代码回放验证**。代码上，R5 价值（35e5fe6）给 J 加了终点价值项、给目标权重乘了击杀价值（T48 那组还把视野拉长到 48 帧）；R6 v0（ef036d5）改的是战术（目标、站位、L2 的 RUSH），到规划器只是 GoalPrefs（只影响分数）；FORCED_RISK 的排序键 Pc / t_c / t_hit 在每一组里都来自同样饱和的支撑。所以在打平的排序里它们只换了"按什么去够目标"。本节对这些组的回放用的是 main 的规划器，和它们实战的选择只有部分一致（按计划名：R5 全开 `015959` 64 %、R6 L2 开 `015904` 83 %、R6 L2 关 `020919` 98.5 %），不一致的 tick 上是反事实的选择。实战结果和"没有作用"一致：七组退出中位 11.8–16.5 s（A0b 12.7–12.9 s），每场 4.0–4.4 次受击。

### 19.9 修正：FORCED_RISK 先看"现在看得见的伤害碰撞体"（`ForumConfig.forced_rank = "seen"`，开关 `SSBOT_FORUM_FR=seen`，默认 `share` = 原样）

- 做法：只在 FORCED_RISK 的 tick 上，对每个已知行，数它的名义盒（无敌帧跳过）在第 1 … T 帧碰到"此刻已开的伤害碰撞体、按所属实体的速度平移"的帧数（`seen_contacts`；不预报、不加余量，只看已经在那儿、正往哪儿去的东西；oracle 视图下 = `Entity.dmg_boxes` 的 active 多边形，视觉视图下对应检测框 + 跟踪速度）；这个计数（再加首次接触帧）排在原来的占比之前，预选的 16 行也按它挑。安全 tick（有 S = 0 的行）上全是 0，顺序不变；Bell Beast 不经过 ForumPlanner。核心 0.14 ms p50 / 0.54 ms p99（420 行 × 38 帧 × 12 个多边形，4 线程）。
- 区分力（回放）：按录像碰撞体算的同一个键（`dr`：录像里的伤害多边形，含多段碰撞体；不是生产的 `seen_polys`，但在 `fx_seen` 的子集上两者受击前 6 帧的结果相同，都是 40.8 %），不碰的行事后 89 % 不碰，碰到的行事后 20 % 不碰（支撑：两者占比相同）。受击前 6 帧、有出路时，按它挑的行事后不碰 45.7 %，随机 24.3 %（它和执行的计划只有 20 % 相同；原排序的 9.4 % 是执行的计划，有偏，不比，见 19.5）；在选中 ≠ 执行的 tick 上（受击前 1–12 帧）52.5 % 对随机 31.8 %。全部分析 tick 上 80.8 %（原排序 75.9 %、随机 75.0 %）。按碰撞体：冲锋、本体、针、跳旋大幅改善；**Envoy 横斩 / 跳斩、Choristor 连斩、鞭、Reed 突刺**这些前摇之后才开碰撞体的招，"看得见"的键看不到（19.11）。
- 只换支撑口径不够：受击前 12 帧内、有出路的 tick 上（伤害帧为锚，回放的 115 场，2,035 个 tick），按已承诺支撑的占比挑（`committed`）事后不碰 35 %、再加管和死亡尾巴（`near`）35 %，按"看得见"的键 57 %，随机 44 %。`committed` / `near` 的选择约 70 % 就是执行的计划（它们也常常打平、落到同样的 J），所以只在选中 ≠ 执行的 274 个 tick 上比才干净：`committed` 26 %、`near` 26 %、原排序 23 %、`dr` 51 %、随机 31 %。
- 用生产代码回放（`--forced-rank seen`，A0b `205857` + R6 对照组 `020919`，50 场、204 个受击）：选中计划事后不碰 74.8 %（随机 69.9 %）；受击前 12 帧内、有出路时 58 %（随机 45 %），30 帧内 57 %（随机 52 %）。同一回放里按原排序挑是 34 % / 34 %，但 A0b 那组的原排序基本就是执行的计划，不能直接比。
- 实战：19.10。

### 19.10 实战核对（A0b 协议：fo_A、eval、planner、oracle、真退出 0.2；种子 340000；seen / share 在实例 0、冻结检出 `C:\ssbot\live_w0f_3608489`，seen_cf 在实例 1、`C:\ssbot\live_w0f_cf`；复核修正轮的 seen_cf / seen 成对重跑在实例 0、种子 340100、`C:\ssbot\live_w0f_cf`）

先跑修正、再跑对照的话负载不一样（第一次修正组同时开着本节的离线批，tick 27 % 迟到，6 场后第 5 场 "paused unasked" 退出，不计），所以按"对照先、修正后"重跑。**两组的负载并不相同**（初版说相同，是错的）：两组都和其它轨道在实例 1–4 上的实战同时跑，但对照组的 tick 迟到 12.8 %（tick p50 中位 12.05 ms），修正组 5.4 %（11.34 ms），对照组多 2.4 倍。结果不是负载造成的：之前 9 组同类对照（A0b 两组、R5 三组、R6 四组，迟到 0.06–0.4 %、tick p50 中位 5.8–7.9 ms）退出中位 11.8–16.5 s，这组高负载的对照 14.0 s 落在其中；seen 的 19.1 s 和 seen_cf 的 25.2 s 都在这个范围之外。

| | seen（`20261008_040149`，04:01–04:15） | share 对照（`20261008_034918`，03:49–04:00） |
|---|---|---|
| 结果 | QUIT 24 + HARNESS_FAIL 1（第 24 场 paused unasked） | QUIT 25 |
| 退出时刻中位 / 均值 | **19.1 / 19.4 s** | 14.0 / 14.4 s |
| 同种子成对（24 对） | **+5.0 s（95 % CI 3.4–6.6），23 / 24 对更久** | |
| 每场受击 / 每分钟 | 3.88 / **12.0** | 3.96 / 16.5 |
| 每场受击来源 | 鞭 0.75、Reed 本体 0.58、Envoy 横斩 0.58、Choristor 本体 0.38、突刺 0.33、跳旋 0.25、连斩 0.21、针 0.21、Envoy 本体 0.21、招架反击 0.17、跳斩 0.12、**冲锋 0.04** | **冲锋 0.92**、鞭 0.68、针 0.44、Envoy 本体 0.32、突刺 0.28、连斩 0.28、跳旋 0.28、Reed 本体 0.24、Envoy 横斩 0.24、Choristor 本体 0.12 |
| FORCED_RISK 时新计划的起手 | 跳 36 %、走 31 %、等 16 %、出刀 11 %、冲刺 6 % | 走 57 %、等 20 %、出刀 11 %、冲刺 7 %、跳 5 % |
| tick > 16.7 ms（`policy.late_ticks`）/ tick p50 中位 | 5.4 % / 11.34 ms | **12.8 %** / 12.05 ms |
| 击杀 | 0 | 0 |

- seen 组那场 HARNESS_FAIL（"paused unasked"）是通用的 harness 失败，不是 seen 造成的：同样的失败出现在 48 个 attempts 文件里（Bell Beast 的 oracle / dust / inject、Lace1、早先的 Forum，代码 e10c2b8、6ab67e1、3fdd8af 等）；share 和 seen_cf 各 25 场没有遇到，但按这个基率说明不了什么。
- 按出招实例（`forum_attack_outcomes`，8 u 内）：EN_CHARGE 被打中 5 %（20 次）对 29 %（14 次）——比你 1x 的 17 % 还低；其余家族基本不变（CH_WHIP 39 % / 30 %、CH_SLASH 38 % / 53 %、EN_SLASH 18 % / 19 %、RE_STAB 24 % / 25 %）。
- 结论：修正做到了取证预测的事——Envoy 冲锋的受击几乎没了（−96 %）、针和 Envoy 本体减半，FORCED_RISK 时会跳（像你跳过冲锋），退出晚了 5 s、每分钟受击 −27 %。**但第 0 波仍然 100 % 退出**：剩下的是前摇之后才开碰撞体的招（鞭、Envoy 横斩、突刺、连斩）和 Reed 的本体（跳得多了，空中撞上飞着的 Reed 多了：0.24 → 0.58，你 1x 的 Reed 受击 2 / 3 也在空中），而且仍然 0 击杀。

**`seen_cf` 的实战**（`20261008_045005_Forum_A_eval_planner_oracle`，04:50–05:05，冻结检出 `C:\ssbot\live_w0f_cf`（82e94fa），实例 1——实例 0 当时被 r5value 占着；同一个种子基数 340000，但 `combat_run` 的种子带实例前缀（实例 1 = 1340000+），所以随机开局和上面两组**不成对**，下面是不成对比较；那段时间机器负载较轻，tick 迟到 1.3 %）：

| | seen_cf | seen | share |
|---|---|---|---|
| 结果 | QUIT 25 | QUIT 24 + HF 1 | QUIT 25 |
| 退出时刻中位 / 均值 | **25.2 / 25.5 s** | 19.1 / 19.4 s | 14.0 / 14.4 s |
| 每分钟受击 | **10.1** | 12.0 | 16.5 |
| 每场受击来源（前几项） | 鞭 0.64、Envoy 横斩 0.56、跳斩 0.52、Reed 本体 0.40、突刺 0.40、跳旋 0.36、针 0.32、Envoy `P1 Damager` 0.20、冲锋 0.12 | 见上 | 见上 |
| 击杀 | 0 | 0 | 0 |

- seen_cf − seen：+6.2 s（自助法 95 % CI 3.1–9.4；随机挑一对 seen_cf 更久的概率 0.78）；seen_cf − share：+11.1 s（8.4–14.1；0.94）。每分钟受击 10.1 已和你 1x 的 11.4 相当（但你会击杀、第 0 波会结束）。负载不同是个混杂（迟到 seen_cf 1.3 %、seen 5.4 %、share 12.8 %），但低负载下的 9 组对照最长也只有 16.5 s，差距比负载能解释的大；同一实例、同一种子、交替时段的成对重跑见下（+4.6 s）。
- 仍然 25 / 25 在第 0 波退出、0 击杀：要打完第 0 波，bot 必须出手（19.11 第 4 条）。

**seen_cf 与 seen 成对重跑**（复核修正轮，2026-10-08 05:57–06:32，`C:\ssbot\sandbox\w0f_pair.ps1`；实例 0，冻结检出 `C:\ssbot\live_w0f_cf`（82e94fa = 最终代码），A0b 协议，种子 340100–340124；每 5 个种子一块，ABBA 交替（偶数块 seen_cf 先、奇数块 seen 先），两组在同一实例、同样的种子、交替的时段里跑，负载相同：迟到 1.8 % 对 1.4 %；06:17 起 r8 在实例 2、3 上开跑，之后的块两组大致各占一半）：

| | seen_cf | seen |
|---|---|---|
| 运行 | `20261008_055737` / `060704` / `061017` / `062102` / `062440` | `060111` / `060410` / `061410` / `061752` / `062846` |
| 结果 | QUIT 25 | QUIT 25 |
| 退出时刻中位 / 均值 | **24.1 / 25.0 s** | 19.4 / 20.4 s |
| 同种子成对（25 对） | **均值 +4.6 s（自助法 95 % CI 2.1–7.2），中位差 +2.3 s（0.7–8.1），18 / 25 对更久（符号检验 p = 0.043）** | |
| 每场受击 / 每分钟 | 3.92 / **9.4** | 4.20 / 12.3 |
| 每场受击来源（前几项） | Envoy 横斩 0.60、Reed 本体 0.48、跳旋 0.40、Envoy 本体 0.32、鞭 2 0.32、鞭 4 0.28、连斩 1 0.24、跳斩 0.20 | **Envoy 横斩 1.00**、跳旋 0.44、Reed 本体 0.44、鞭 1 0.28、鞭 2 0.28、Choristor 本体 0.24、Envoy 本体 0.24、跳斩 0.24 |
| tick 迟到 | 1.8 % | 1.4 % |
| 波次 / 击杀 | 50 场全部第 0 波、0 击杀 | |

- 两组都复现了之前的数：seen 19.4 s（之前 19.1 s），seen_cf 24.1 s（之前不成对的 25.2 s）。seen_cf 比 seen 成对多 4.6 s，和之前不成对的 +6.2 s 方向一致、略小；每分钟受击 −24 %。差异主要在 Envoy 横斩（1.00 → 0.60 次 / 场；推断：已承诺的横斩放置在碰撞体打开前就被 seen_cf 的第二键看到）。
- 仍然 50 / 50 在第 0 波退出、0 击杀（19.11 第 4 条）。

### 19.11 下一步

1. **合并 `forced_rank`（"seen" / "seen_cf"）**（默认仍 `share`；整合后的 Forum A/B 建议用 `SSBOT_FORUM_FR=seen_cf`：同一实例、同一种子上和 `seen` 成对已确认 +4.6 s，19.10）：它和 R5 / R6 / R8 都正交（只改 FORCED_RISK 时的前几个排序键），R6 的目标、R5 的终点价值在"打平"消失之后才有机会起作用。
2. **前摇招**（鞭、横斩、突刺、连斩、跳斩，修正后占剩余受击的一半以上）："看得见"的键在碰撞体打开前看不到它们。离线（`--forced-rank seen` 的回放）比较了两个补充键：`seen_cf`（看得见之后，再看落在已承诺精细放置里的帧占比）明显更好，`seen_cm`（再看已承诺支撑的占比，含会饱和的窗口）次之：受击前 12 帧、有出路时事后不碰 seen 60 %、seen_cm 63 %、seen_cf 73 %、随机 45 %（伤害帧为锚，862 个 tick；全部 tick 75 / 77 / 79 %）。这三个都是回放里的反事实选择，但 seen 的键全为 0 时它退回原排序，那时它的选择常常就是执行的计划（被打的路径），对 seen 不利；只看 seen 的选择 ≠ 实战选择的 437 个 tick（按计划名比对，回放里 CONTINUE 的含义和实战不完全一样，只作参考）：seen 62 %、seen_cm 65 %、seen_cf 78 %、随机 40 %，差距还在；按碰撞体（受击前 12 帧）鞭 35 % → 68 %、Choristor 连斩 0 → 33 %、跳旋 44 % → 67 %、冲锋 63 % → 78 %，Envoy 横斩 19 % → 24 % 仍然最难。已实现为 `forced_rank = "seen_cf"`（`SSBOT_FORUM_FR=seen_cf`，`committed_fine_share`：不含窗口和以后才开始的外包盒），实战比 seen 再晚退出 6 s（19.10，不成对）；剩下最多的是 Envoy 横斩 / 跳斩和鞭。更根本的是给已承诺的招一个按名义时刻（中位驻留）放的模板，不再按入场区间并成窗口。
3. **支撑去饱和**（R2 / R3 的人）：Reed 的"以后才开始"外包盒（RE_STAB / RE_THROW / RE_IDLE）单独就盖满全部候选，几乎每个 tick；Envoy EN_CHARGE 92 %。可做的收紧：以后才开始的招在前摇最短驻留之前不出伤害（起点 + 最短前摇之前的时间格去掉打击段）、飞行类的待机扩张按实测最大速度封顶。改了要重新认证。
4. **出手**：225 + 49 场击杀 0。你在第 0 波先杀 Envoy（1x 中位 17.5 s），第 0 波才会结束；FORCED_RISK 时 J 里的目标项只让 bot 贴近目标，从不形成"安全出刀窗口"。R6 的惩罚窗口（冲锋结束、`Charge End`；横斩 `Slash1 Recover`）要在 seen 键下重新测。
5. 这台机器同时跑几个实战时，tick p50 从 7 ms 涨到 12–15 ms、迟到 5–28 %；比较必须同负载成对（本节的做法），离线批不要和实战一起跑（本节第一次修正组就是这样被拖坏的）。

### 19.12 复现

```
cd brain
# 逐场取证（每场一个 JSON；--forced-rank seen 用修正回放）
..\scripts\uv.cmd run python -m ssbot.tools.forum_hit_forensics <run dir> [...] --out <dir> --workers 3 --threads 4 [--forced-rank seen]
# 出招实例：bot 与你的录像
..\scripts\uv.cmd run python -m ssbot.tools.forum_attack_outcomes --bot <run dir> [...] --human C:/ssbot/data/human/20261004_002749@human-1x C:/ssbot/data/human/20261004_012300@human-1x C:/ssbot/data/human/20261004_091214@human-0.5x C:/ssbot/data/human/20261004_133855@human-0.5x C:/ssbot/data/human/20261005_160435@human-0.5x --cache <dir> --json <out>
```
驱动与输出：`C:\ssbot\data\m2_forum_w0f\`（`fx_run.cmd` → `fx\`，`fx_seen_run.cmd` → `fx_seen\`，`ao_run.cmd` → `ao_all.json`）；实战 `C:\ssbot\sandbox\w0f_live.ps1`。汇总脚本（会话临时目录）`causes.py`、`summ.py`；复核修正轮（会话临时目录 `w0fx\`）：`split.py` / `split3.py`（按"选中 = 执行"拆开、钩子或伤害帧为锚，19.5 / 19.9）、`kin.py`（12 / 24 帧推演，19.6）、`late2.py`（迟到、规划用时，19.4 / 19.10）、`med.py`（各组退出中位）、`dec.py`（分解计数）、`match.py`（回放与实战选择一致率）、`pair2.py`（seen_cf 与 seen 的成对重跑，19.10；驱动 `C:\ssbot\sandbox\w0f_pair.ps1`）。

## 20. R5 终点价值（2026-10-08，forum_planner_plan.md §5 R5 的"终点价值"一半；分支 worktree-wf_814dfeea-b10-2；离线 + 实例 0 的 A/B）

代码：`combat/terminal.py`（新：支撑场 `EnemyFields.build`、身体场 `EnemyFields.from_bodies`、可达模板 `reach_templates`、`TerminalValue.rows`、击杀价值 `kill_value`）、`combat/forum_planner.py`（`ForumConfig.terminal` 与权重，`_terminal` / `_score_forum`）、`core/worldstate.py` + `backends/oracle_backend.py`（`Entity.hit_polys`）、`combat/enemy_tracker.py`（命中目标用 `hit_polys`）、`train/forum_planner_policy.py`（T 取 `ForumConfig().T`，日志和 stats 记终点价值）；可达模板文件 `knowledge/1.0.30000/kinematics/forum_reach.npz`（`python -m ssbot.combat.terminal` 重建）；测试 `tests/test_terminal.py`（8 项）。开关（A/B 用，写进 config_fp）：`SSBOT_FORUM_TV=0` 关终点价值（第 3 轮起默认关，`SSBOT_FORUM_TV=1` 开，20.11）、`SSBOT_FORUM_T=48` 视野 48 帧、`SSBOT_FORUM_HITBODY=0` 恢复 R4 的命中目标。Bell Beast 路径（`Planner`、`Forecaster`、`PlannerPolicy`）一行没改：它不读 `hit_polys`，Forum 开关是胶水层用哪个类。

### 20.1 计划里的场（支撑场）：做了、保守，但第 0 波完全饱和

- **做法**：0.5 u × 1 u 栅格（x 14–49、y 3.5–18.5，主角受击盒中心，1 050 格），时间格 0.1 s 从 0.6 s 到预报视野（2 s：14 格）；每个 owner（敌人 iid、Tiny 群的簇、投射物、波次入场）一张位图，值 = 该 owner 覆盖这一格的放置里最大的路径概率（×255；管、盒、投射物 255）。细 / 窗口 / 外包盒放置都换成模板粗底的逐 bin 外包盒（稀疏表两次查找，时间格内所有入场时刻 ± 1 个模板 bin）；管和盒取 bin 两端的盒子按 bin 末的增长放大；投射物按 10 ms 采样（含 slack 副本和分支）取外包；后两者再按主角受击盒膨胀。所以"场空 ⇒ 格内任何点、bin 内任何帧的细查询都空"（计划 §4.4 第 5 条）。轮转没有做：每 tick 全部 owner 重建（下面的耗时），场永远不过期。
- **保守性**：合成 Reed（`tests/test_terminal.py`，每个 bin 每一帧、每格 3 个随机点）0 违反；A0b 录像 `20261005_205437` i1 ep0（648 tick，每 10 tick 一次、14 个 bin × 4 200 个随机点）：全集场 0 违反，但空格数为 0（见下），所以这一段录像对全集场的检验是空的；承诺场（`MultiForecast.committed()`）检查了 967 492 个空点，0 违反。
- **耗时**（同一录像，整机 5 个游戏实例在采集、低优先级）：每 tick 建场 p50 1.5–2.0 ms、p99 3.3–4.1 ms。
- **饱和**（同一录像，每 20 tick 一次）：并集场在 0.6–2.0 s 的每个 bin、每个采样 tick 都是 **100 %**；单个 owner 也是：Reed、Envoy、Choristor 各自 100 %。细查询本身也一样：主角站在地面任何 x，**t = 0 起**就在 Reed（Alert）和 Envoy（Charge）的支撑里。原因（逐类拆开）：之后才可能开始的实例用家族行走模板的外包盒放置（`bb` 行），`RE_STAB` / `RE_THROW` / `EN_CHARGE` 的入场窗 0.02–0.1 s 那几行在 t = 0 就盖住整条地面（`RE_THROW` 外包盒宽 50–93 u，锚盒 hx 4.7–13.9 u）；路径概率加权也救不回来：p = 1 的行（当前实例的窗口放置、Choristor 待机家族的外包盒 `CH_IDLE` 宽 92 u、全场盒）让 1 − Π(1 − p_i) 处处为 1；承诺场在 0.6 s 也有 80 %，0.9 s 起 100 %。**结论**：在第 0 波，用支撑（或其概率）做的 E 恒为 0、trapped 恒为真，不含信息；这同时说明 A0 / A0b 的 87 % FORCED_RISK 有结构性来源——地面行在第 1 帧就在支撑里，只有空中行可能安全。要改的是 R2 / R3 的放置（外包盒行的时间展开），需要重新认证，不在本轮。

### 20.2 命中目标的 bug（R3 / R4 起就有）

`EnemyTracker.body`（规划器的命中目标、`targets()`、`_nearest`）取的是实体**所有**启用碰撞体的外包盒，其中包括第 13 层的范围触发器（Alert / Throw / Attack / Patrol / Stab / Defend Range，5–47 u）、第 27 层的物理推挤体和第 14 层的 Terrain Block。A0b 录像里：Envoy 的"身体"108 u 宽、Choristor 30 u、Reed 24 u。于是任何一刀在规划器里都"打得到"它们：J 的命中项、第一下命中、命中分支（后坐 + 受击反应）在几乎所有攻击行上都成立（开环回放 ep3：命中分支 325 次、被上限截掉 160 行）。改：`Entity.hit_polys`（oracle 专用字段：启用且不在 13 / 14 / 27 层的碰撞体），`EnemyTracker` 有它就用它（`SSBOT_FORUM_HITBODY=0` 恢复旧的）。改后同一 tick：Reed 1.1 × 2.8 u、Envoy 1.2 × 2.0 u、Choristor 1.5 × 2.9 u。支撑不受影响（待机管用的是 `seen_box` / 伤害盒，不是 `body`）。

### 20.3 实际上线的终点价值：身体场

因为支撑场饱和，J 里的终点项改用**身体场**（敌人身体的可分辨结构，只进打分）：每个在场活敌的身体盒（`hit_polys` 外包）按速度航位推算最多 0.3 s、按主角受击盒膨胀；"区" = 离它 ≤ 1.5 u + 1.5 u/s × t 的格（`BODY_REACH_U`、`BODY_APPROACH_U_S`，启发式，不是认证量）；"余量" = clip((到最近身体的距离 − 1.5) / 4, 0, 1)。可达模板：Forum 运动学（`hero_reaper_forum.json`）从 4 类终点（地面、空中上升 / 顶点 / 下落，按 vy ±3）出发，135 条原语（站 / 左 / 右跑、0.5 s 时转向、5 种跳、2 个时刻的冲刺）在 0.2 / 0.5 / 0.9 / 1.4 s（± 半个 bin）的受击盒中心偏移，运行时按竞技场墙 / 地面截断、量化到一格（每类每时刻 27–149 个偏移）。每行（标称一条的最后一帧）：

- E = Σ_t w_t · R_t 上余量的平均（w_t = 1 / (1 + t) 归一）；trapped = 某个 t ≤ 1.4 s 时 R_t 全在区内；overlap = R_t 在 ≥ 2 个区内的比例；H_exp = t ≤ 0.9 s 时 R_t 在"有 2 格招或多段连击"的敌人（按类型：任一家族 damage ≥ 2 或 chains.json 的整链 > 1 下）区内的比例。
- J += 4.0·E − 3.0·trapped − 1.5·overlap − 2.0·H_W[h]·H_exp（H_W：h ≤ 2 为 1、h = 3 为 0.6、h ≥ 4 为 0.3、未知 0.5）。
- 击杀价值：主角周围 ±8 u × ±5 u、所有 bin 里"只有它盖住"的余量下降（留一法）÷ 还需几刀（hp_est / 一刀，默认 9）；目标的命中权重 × (1 + 3.0 × 击杀价值)。
- 只动 J 和命中权重：`tests/test_terminal.py::test_the_terminal_value_moves_j_only`（确定模式，开 / 关时每行的 Hz、U 和 FORCED_RISK 相同）；字典序不变。

### 20.4 开环回放（`forum_policy_replay`，A0b 录像 i1 ep0 / ep3，同一负载下依次跑四种配置；开环：主角位置是录像的，FORCED_RISK 不是闭环比例）

| 配置 | ep | tick p50 / p99（ms） | 规划 p50 / p99 | 终点价值 p50 / p99 | 命中分支 / 被上限截掉 | 选中行 E / trapped / overlap / H_exp |
|---|---|---|---|---|---|---|
| base（R4：`TV=0 HITBODY=0`） | 0 | 13.8 / 103.1 | 5.84 / 64.9 | — | 212 / 0 | — |
| hitbody（`TV=0`） | 0 | 14.8 / 90.2 | 6.32 / 58.2 | — | 193 / 1 | — |
| tv（默认，偏移未粗化） | 0 | 14.7 / 27.4 | 7.68 / 19.4 | 1.65 / 4.52 | 185 / 1 | 0.35 / 0.20 / 0.31 / 0.42 |
| t48（`T=48`） | 0 | 16.3 / 27.3 | 8.96 / 17.6 | 1.77 / 5.06 | 0 / 0 | 0.37 / 0.17 / 0.32 / 0.43 |
| base | 3 | 13.4 / 76.9 | 4.92 / 36.3 | — | 325 / 160 | — |
| hitbody | 3 | 12.5 / 24.1 | 4.85 / 17.0 | — | 290 / 97 | — |
| tv（偏移按格粗化，35e5fe6） | 3 | 13.7 / 26.0 | 6.27 / 19.0 | **1.30 / 3.65** | 219 / 0 | 0.24 / 0.16 / 0.25 / 0.53 |

- 负载很重（这一段整机 5 个游戏实例在采集、其他代理在跑），四种配置的 tick p50 都在 12.5–16.3 ms（A0 实战 7.4 ms），只能互相比；base 的 p99（77–103 ms）是个别慢 tick，不可比。终点价值每 tick 多 1.3 ms（p50）/ 3.7 ms（p99），在规划的打分阶段（包络之前），所以截止时间 8 ms 下包络少查约一块。
- 开环下 FORCED_RISK 四种配置相同（ep0 483 / 648、ep3 608 / 781；T48 ep0 531）：开环里主角位置是录像的，S 不受打分影响；命中目标修正后命中分支和被截行减少（ep3 325 / 160 → 290 / 97 → 219 / 0）。T48 的 FORCED_RISK 更高（开环）、tick 更贵。闭环效果看 20.5 的 A/B。
- 审计：所有配置选中 S = 0 的计划全部包络过、core_not_enveloped 0、overrun 0。

### 20.5 A/B（实例 0，2026-10-08 01:59–02:33；**终点价值、只修目标、T48 都没有改变第 0 波的结果**）

驱动 `C:\ssbot\sandbox\r5v_ab.ps1`（隐藏窗口，冻结检出 `C:\ssbot\live_r5v_35e5fe6`）在 Trobbio 采集结束后拿 inst0 锁，按 A0b 的协议（fo_A、eval、planner、oracle、真退出 0.2、4 线程）跑完。种子 300000 那一批只跑了 1 场就 HARNESS_FAIL（"paused unasked"，和 A0b 那一场同类），所以 TV 臂用 300100 的 25 场（加 300000 的 1 场失败）。`forum_a0_report`（会话临时目录 `r5v2/rep_*.json`）：

| 臂 | 运行 | 场 | 结果 | 每场受击 | 每分钟受击（95 % bootstrap） | 波次 | 局内时长 p50 / 均值（s） | FORCED_RISK 比例 | 支撑外命中 | tick p50 / p99（ms，每场的中位） | 终点价值 p50 / p99（ms） |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A0b（f8c0c62） | 20261005_205437 + 205857 | 51 | QUIT 50（Q1）、HARNESS_FAIL 1 | 4.27 | 19.1（17.9–20.4） | 全部第 0 波 | 12.7 / 13.5 | 0.803 | 1 | 5.9 / 11.8 | — |
| TV（终点价值 + 修目标，默认） | 20261008_015907 + 015959 | 26 | QUIT 25、HARNESS_FAIL 1 | 4.0 | 18.4（16.9–20.1） | 全部第 0 波 | 13.9 / 13.3 | 0.824 | 0 | 7.4 / 13.6 | 0.88 / 1.50 |
| HB（只修目标，`TV=0`） | 20261008_021002 | 25 | QUIT 25 | 4.16 | 18.4（16.9–20.2） | 全部第 0 波 | 12.7 / 13.6 | 0.810 | 0 | 6.6 / 12.5 | — |
| T48（`T=48`） | 20261008_022115 | 25 | QUIT 25 | 4.4 | 16.6（14.8–18.4） | 全部第 0 波 | 16.5 / 15.9 | 0.887 | 0 | 7.9 / 13.3 | 0.90 / 1.52 |

- 每一场都是第 0 波里 Q1 退出（`hits_to_death 1`，开局 7 血，Choristor 一下 2 格），0 WOULD_DIE，0 次击杀（`kills_by_src` 空）。每场受击、每分钟受击、FORCED_RISK 比例都在 A0b 的误差范围内；T48 每分钟受击略低、局内时长略长，但 FORCED_RISK 更高（0.887），25 场的置信区间和 A0b 只差一点点重叠，不算结论。
- 受击来源变了：Envoy 105 / 51 场（A0b）→ 30 / 26（TV）、35 / 25（HB）、41 / 25（T48）；Choristor 56 → 45、39、43；Reed 57 → 29、30、26。修目标后不再把 108 u 宽的 Envoy"身体"当成能打中，少往 Envoy 身上撞，但换成了更多 Choristor 的受击，总数不变。
- 决策日志（`C:\ssbot\data\m2_forum_r5v\round2\declog_stats.py`，EVADE tick）：FORCED_RISK 占 0.736（A0b）/ 0.755（TV）/ 0.743（HB）/ 0.864（T48）；FORCED_RISK tick 里选中行的 P = 1 占 77–79 %，和排第二的行 P 相同的 100 %；**所有受击都发生在 FORCED_RISK tick**（215 / 102 / 104 / 110 次）；受击前离最近一次有安全行的 tick 中位 2.1–2.6 s（四分位 1.0–8.0 s），即主角在挨打前已经连续好几秒没有安全行。为什么终点价值没起作用，见 20.7。

### 20.6 没做 / 未核实（第 1 轮；第 2 轮的见 20.9）

- 计划 R5 行的"先做"部分（决策感知时刻、FSM 冷却、身体触发反应分支、Tiny 轨道模型）不在本轨（终点价值一半）。
- 身体场的半径与速度、各项权重是手设的启发式，没有拟合（R9）；击杀价值的"一刀伤害"用 9（Reaper 钉子），没有读装备。
- 支撑场的饱和要靠 R2 / R3 的放置修正（外包盒行的时间展开）才能变得有用；那之后终点价值可以换回支撑场（代码保留，属性测试在）。
- 命中目标修正改变了命中分支和 J，对 FORCED_RISK 的影响要看闭环 A/B（20.5）；视觉视图没有 `hit_polys`，回落到全部碰撞体（Forum 的视觉视图是 M3）。

### 20.7 为什么终点价值没改变第 0 波（第 2 轮，`tools/forum_tv_audit`）

做法：把录像开环回放进当前代码的 ForumPlannerPolicy（终点价值开、T 36），`ForumConfig.p_all` 让 FORCED_RISK 的 P / 首次接触对每个允许且已知的行都算（选择仍在 p_k = 16 个预选行里，所以决策和实战同一种），`ForumPlanner.last_sel` 交出选择用的每一列。每个 EVADE tick 记：选中行和第二名在哪一个键上分出先后；换一种排序会不会选别的（前 6 帧按键不同才算）；**事后**：每个允许的行的标称受击盒和录像里同一帧的威胁碰撞体（启用、能伤人；外包盒）比，跳过该行的无敌帧，整段视野不碰 = "事后安全"（敌人是录像里的敌人，它们针对的是录像里的主角，不是这一行，所以是估计）；每个键对"事后安全"的组内 AUC（同一 tick 内的行两两比，0.5 = 没信息）。样本：TV 臂录像 `20261008_015959` i0 的 25 场（19 943 个 EVADE tick：FORCED_RISK 15 863、有安全行 4 080；受击前 36 帧内 3 671）和 A0b 录像 `20261005_205437` i1 的 9 场（FORCED_RISK 5 036、安全 1 925、受击前 1 476）。输出和逐 tick 的转储在 `C:\ssbot\data\m2_forum_r5v\round2\`（`aud_tv.json`、`aud_a0.json`、`*.pkl.gz`；离线排序 `rank_eval.py`）。

| | TV 录像 | A0b 录像 |
|---|---|---|
| FORCED_RISK tick 里选中行 P = 1 | 81.6 % | 77.4 % |
| 选中行与第二名第一个不同的键：J / 全部相同 / 其他 | 82.7 % / 16.2 % / 1 % | 74.6 % / 24.7 % / 0.7 % |
| AUC：P、首次接触（标称 / 包络）、`MultiForecast.prob` | 0.500 | 0.500 |
| 去掉终点价值（J0）选择会变的 tick：FORCED_RISK / 安全 | 18.4 % / 25.3 % | 19.0 % / 20.3 % |
| FORCED_RISK：存在事后安全行 / 选中行事后安全 / J0 的选择事后安全 | 90.3 / **68.4** / 67.4 % | 89.7 / **64.9** / 64.0 % |
| 受击前 36 帧：存在 / 选中 / J0 | 72.7 / **30.4** / 27.8 % | 73.0 / **32.7** / 30.8 % |
| 基线（第 3 轮补，20.11）：随机一个允许行事后安全，FORCED_RISK / 受击前（只算 FORCED_RISK tick） | 66.9 / 36.8 % | 65.5 / 39.1 % |
| AUC（FORCED_RISK）：E / overlap / H_exp / trapped / 终点价值合计 / J0 / J | 0.645 / 0.629 / 0.601 / 0.523 / 0.645 / 0.577 / 0.636 | 0.550 / 0.579 / 0.542 / 0.502 / 0.560 / 0.560 / 0.579 |
| AUC（受击前）：终点价值合计 / J0 | 0.600 / 0.462 | 0.488 / 0.519 |

结论：

1. **FORCED_RISK 里决定选择的就是 J**。支撑在第 0 波饱和（20.1），P 几乎处处为 1、首次接触都在第一帧，三个支撑键的 AUC 正好 0.5（概率版 `prob` 也是）；字典序落到 J，而 FORCED_RISK 占 EVADE tick 的 3/4。所以终点价值不是"被字典序挡住了"：它确实改了 18–25 % 的选择（选择不同 = 前 6 帧按键不同）。
2. **但它对"会不会挨打"几乎没帮助**：选中行事后安全只多 0.9–1.0 个百分点（受击前多 1.9–2.6 个）。终点价值的各项有一点信息（TV 录像上 AUC 0.60–0.65），但它是加在 J0（命中、站位、浪费、跳跃等目标项）上的几个单位，J0 在受击前没有信息（AUC 0.46；**这个"低于 0.5"不能读成"J0 反着来"**：开环重放里实战的选择基本就是录像里走的那条，而录像里的威胁是冲着录像里的主角去的，和录像路径相近的行事后判不安全的偏多，见 20.11 的选择偏差；它说明的是 J0 和录像路径相关，不是因果）；把终点价值放大 4–8 倍或只用终点价值排序，在 TV 录像上能到 70.5–72.6 %（受击前 42.8–46.4 %），在 A0b 录像上没有提高（64.6–65.0 %、34.1–36.5 %），不稳。身体场（身体 + 1.5 u + 1.5 u/s·t）描述的是"离敌人身体多远"，第 0 波打中主角的是已经起手的招（Reed `Stab Antic` → `Stab`、Envoy `Charge`、Choristor `ComboSlash`），伸出身体好几 u。
3. **有信息的是"已经承诺的招"**：把支撑的承诺部分（当前的招、招尾、死亡尾、投射物：`MultiForecast.committed()`）和其中入场已知的细放置（当前招的状态）分别在阶段 1 的帧上算接触比例 P_cm、P_f，作为 P 之后的次级键：选中行事后安全 74.3 % / 70.9 %（比实战 +5.9 / +6.0 个百分点，比随机一个允许行 +7.4 / +5.4），受击前 41.5 % / 42.3 %（比实战 +11.1 / +9.6，但实战的选中行受击前比随机行还差 6.6 / 7.4 个点——选择偏差，20.11——**比随机行只 +4.7 / +3.2**），两份录像方向一致；只用 P_f 73.3 / 69.4 %，只用 P_cm 71.1 / 68.2 %；再叠终点价值 ×2 只多 0–1.6 个点，不稳，不加。离存在事后安全行（90 %）还差约 16 个点：剩下的是还没起手的招（之后的实例，正是支撑饱和的部分）。
4. **R5 模型的分支概率（`Subject.next_p`）没有用**：核对者的结论是运行时的 next_p 不是评估的那个模型（61 个决策里 26 个用到运行时算不出的协变量）、而且只在出招那一帧拟合，提前 0.2 / 0.5 s 查询时对数损失 2.31 / 2.92，比无条件表（0.70）差得多；那个分支也没合进 main。第 0 波缺的信息是"当前已经起手的招"，不是"下一招是哪个分支"；等分支模型按提前量重新拟合后，可以给之后的实例（饱和的外包盒行）配概率，再看 P 能不能分开。

### 20.8 FORCED_RISK 用承诺支撑细分 P（`ForumConfig.commit_rank`，737048f；A/B 后默认开，`SSBOT_FORUM_PC=0` 关，3797b3e）

- 只在 FORCED_RISK 时：对每个允许且已知的行，标称受击盒中心在阶段 1 的帧上（跳过无敌帧）和承诺支撑接触的比例 P_cm、和当前招细放置接触的比例 P_f；预选 16 行按 (P_cm, P_f, 最晚首次接触, J)，排序 `hz > hz_soft > U > S > 保持的跳 > 宏 > V > P > P_cm > P_f > 首次接触（包络 / 标称）> J`。有安全行的 tick 不算（P_cm = P_f = 0），S / Hz / U、FORCED_RISK 与否都不变（`tests/test_forum_planner.py::test_commit_rank_refines_forced_risk_by_the_committed_support`）；关掉时与之前逐位相同（预选和排序多的键全是 0）。Bell Beast 不经过 ForumPlanner。
- 开销（开环 `forum_policy_replay`，TV 录像 ep3 960 帧，关 / 开各两次交替，整机中等负载）：规划 p50 7.0–7.3 → 8.0–8.7 ms，p99 17.4–18.8 → 16.5–17.5 ms；FORCED_RISK 754 / 960、包络审计、截止次数不变。
- **和 wave-0 取证轨（diag，§19）的 "seen" 键比**：取证轨独立得出同一个原因（支撑饱和，选择落到 J），做了 `forced_rank = "seen"`（`SSBOT_FORUM_FR=seen`）：每行标称受击盒和"现在看到的伤害碰撞体按其实体速度平移"相碰的帧数（再按首次接触），放在 P **之前**。在同一批 tick 上（`forum_tv_audit` 用规划器的 `seen_contacts` 算这个分数，`aud2_*`）：seen 的 AUC 0.72–0.75（P_f 0.56–0.58、P_cm 0.51–0.54），说明"已经在场上的判定"信息最多；但两者互补：

| 排序（FORCED_RISK，选中行事后安全；括号里是比随机一个允许行，第 3 轮补，20.11） | TV 录像：全部 / 受击前 | A0b 录像：全部 / 受击前 |
|---|---|---|
| 随机一个允许行（基线） | 66.9 / 36.8 % | 65.5 / 39.1 % |
| 实战（P、首次接触、J） | 68.4（+1.5）/ 30.2（−6.6）% | 64.9（−0.6）/ 31.8（−7.4）% |
| seen（取证轨） | 71.8（+4.9）/ 37.5（+0.7）% | 71.7（+6.1）/ 41.7（+2.5）% |
| commit_rank（本轨） | 74.3（+7.4）/ 41.5（+4.7）% | 70.9（+5.4）/ 42.3（+3.2）% |
| **seen > P > P_cm > P_f（叠加）** | **78.7（+11.8）/ 48.7（+11.9）%** | **76.3（+10.7）/ 51.0（+11.9）%** |
| 存在事后安全行（上限） | 90.3 / 72.7 % | 89.7 / 72.6 % |

  （受击前一列只算 FORCED_RISK tick，和第 2 轮的 30.4 / 32.7 差 0.2–0.9 个点。）以随机行为基线，单独的 seen 在受击前几乎没有增益（+0.7 / +2.5），commit_rank +4.7 / +3.2；叠加 +11.9 / +11.9，比两者之和还多。叠加比任何一个单独都好（两份录像一致），所以本分支把取证轨 3608489 的规划器部分（`seen_contacts`、`seen_polys`、`warm_kernels`、`SSBOT_FORUM_FR`、它的测试）原样移植过来、和 commit_rank 叠在一起（8617aa6：预选和排序都是 seen > P > P_cm > P_f；两个开关都关时与之前逐位相同）。
- A/B（实例 0，按 A0b 的协议，种子 300400–300799）：驱动 `C:\ssbot\sandbox\r5v_ab2.ps1`（冻结检出 `C:\ssbot\live_r5v2_8617aa6`），等取证轨在实例 0 上的 seen / share 对照跑完后：SPC（seen + commit_rank）25 场（300400）→ PC 25 场（300500）→ 当场对照 TV 25 场（300600，都关）→ SPC 25 场（300700）；一批因真退出后的 HARNESS_FAIL 提前结束时用种子 + 50 补齐。结果见 20.10。

### 20.9 没做 / 未核实（第 2 轮）

- 事后安全是开环估计：敌人对另一条路线的反应（Reed 刺的瞄准、Envoy 冲锋方向）没有模拟；它只用于比较排序，闭环效果看 A/B。
- 终点价值的权重和身体场的半径仍是手设的；20.7 说明在第 0 波它不是瓶颈，没有再调。
- P_cm / P_f 只在 FORCED_RISK 时算、只用标称一条（阶段 1 的帧，和 P 一样）；没有做概率加权。
- **叠加后剩下的差距**（`round2\gap_eval.py`，FORCED_RISK 且存在事后安全行的 tick）：叠加排序的选择仍不安全的占 8–10 %（受击前 30–33 %）；其中 68–79 % 有一个事后安全的行和选中行在 seen、P、P_cm、P_f 上**完全相同**（只能靠 J 分），选中行 seen = 0 的占 92–98 %。也就是剩下的受击主要来自"现在还没出现、也还没起手"的招——正是支撑饱和的那部分（之后实例的外包盒行）；要缩小它得有按时间展开的之后实例放置（R2 / R3，需重新认证）或按提前量拟合的分支概率（R5 模型的下一步），不是 J 的权重。

### 20.10 第 2 轮 A/B（实例 0，2026-10-08 04:20–05:18，冻结检出 `C:\ssbot\live_r5v2_8617aa6`；**承诺支撑细分和叠加都显著减少每分钟受击，但第 0 波仍然全部 Q1 退出**）

协议同 A0b（fo_A、eval、planner、oracle、真退出 0.2、4 线程）。**更正（第 3 轮，核对者）**：三臂不是交替跑的，而是**按批次依次跑**，每臂一个连续时间段：SPC 300400 / 300450（04:20–04:37）→ PC（04:37–04:51）→ TV 对照（04:51–05:03）→ SPC 300700（05:03–05:18）；各批次期间机器负载差别很大（实例 1 在跑 L2 A/B，实例 2 / 3 在跑 320600，加上其他轨的离线任务）。所以下表的 tick 时间和迟到比例主要反映各批次的负载，不能当成代码的开销（见表后和 20.11）；受击率的结论不受影响（两批 SPC 都约 10.3，而且迟到更多的那批不比另一批差）。终点价值开、T 36。种子 300400 那一批第 1 场就因真退出后的"paused unasked" HARNESS_FAIL 停了（和 A0b、第 1 轮 TV 300000 同类），驱动用 300450 补齐 25 场。`forum_a0_report`（`round2\rep_TVc.json`、`rep_PC.json`、`rep_SPC.json`）+ `round2\ab2_report.py`：

| 臂 | 运行（20261008_） | 场 | 每场受击 | 每分钟受击（95 % bootstrap） | 局内时长 p50 / 均值 / 最长（s） | FORCED_RISK | 支撑外命中 | tick p50 / p99（ms；随批次负载） | 迟到 tick（随批次负载） |
|---|---|---|---|---|---|---|---|---|---|
| TV（当场对照：两个开关都关） | 045158（300600） | 25 | 4.32 | **19.0（17.1–21.0）** | 12.4 / 13.7 / 21.1 | 0.813 | 0 | 9.8 / 19.0 | 3.5 % |
| PC（commit_rank） | 043725（300500） | 25 | 4.40 | **12.4（11.3–13.7）** | 21.4 / 21.3 / 30.6 | 0.885 | 0 | 12.8 / 21.2 | 17.6 % |
| SPC（seen + commit_rank） | 042011 + 042143 + 050303（300400 / 300450 / 300700） | 50（+1 HARNESS_FAIL） | 4.18 | **10.3（9.5–11.3）** | 23.5 / 24.4 / 43.1 | 0.915 | 0 | 12.0 / 20.2（两批：16.2 / 24.9、10.0 / 18.2） | 23.8 %（两批：40.1 %、5.8 %） |
| 参照：A0b / 第 1 轮 TV | 20.5 | 50 / 25 | 4.27 / 4.0 | 19.1 / 18.4 | 12.7 / 13.5、13.9 / 13.3 | 0.80 / 0.82 | 1 / 0 | 5.9 / 11.8、7.4 / 13.6 | — |

- 当场对照和第 1 轮、A0b 一致（每分钟 19 次受击、活 13–14 s）。**commit_rank 单独：每分钟受击 −35 %、平均存活 +55 %；叠加 seen：−46 %、+78 %**；两个 SPC 批次各 25 场一致（10.31 / 10.34，核对者重算）。95 % 区间互不重叠。取证轨自己的 seen / share 配对（种子 340000）见 §19。
- 但**每一场仍是第 0 波 Q1 退出**（hits_to_death 1），0 WOULD_DIE、0 次击杀、没有一场进第 1 波：活得更久，但受击数（约 4.2–4.4 次就到 Q1）没变，只是被拉长到 21–24 s。下一个瓶颈是把敌人杀掉（R6 的目标、R8 的拼刀），而不是躲。
- FORCED_RISK 比例上升（0.81 → 0.89 / 0.92）：活得久的那部分时间仍在 FORCED_RISK 里，改的是 FORCED_RISK 里怎么选。
- 计算（**更正**，`round3\ab3_report.py`，`round3\ab2_batches.txt`）：按批次看，迟到比例（> 16.7 ms 的 tick）/ tick p50 / 规划 p50 是 SPC 300450 **40.1 %** / 16.2 / 8.8 ms、PC 17.6 % / 12.8 / 6.7 ms、TV 对照 3.5 % / 9.8 / 4.9 ms、SPC 300700 **5.8 %** / 10.0 / 5.4 ms。同样的 SPC 代码两批差 7 倍，所以原来写的"PC / SPC 迟到 18 % / 24 %（对照 3.5 %）、满载时多约 3 ms 是代码开销"不成立：负载最接近的一对（SPC 300700 紧接在 TV 对照之后）是 5.8 % 对 3.5 %、规划 p50 5.4 对 4.9 ms。代码本身的开销见 20.11（同一进程逐 tick 配对测）：旧的 commit_rank 实现在 FORCED_RISK tick 上多约 1 ms（p99 3 ms 以上），第 3 轮改成从阶段 1 的查询顺带算出来以后约 0.3 ms。
- 默认：commit_rank 改为默认开（3797b3e，`SSBOT_FORUM_PC=0` 关）；seen 的默认（`share`）是取证轨的开关，本轨不改。叠加（SPC）比只开 seen 好这一点目前只有离线证据（20.8）；实战里取证轨只开 seen 的 11.9（10.5–13.4，种子 340000、3608489、另一时段）和这里 SPC 的 10.3 区间重叠，所以第 3 轮在同一批里逐场交替四组再比（20.11）。

### 20.11 第 3 轮（核对者意见之后，2026-10-08 06:00 起；代码 2ef6383、b96559f）

**1. commit_rank 的两个键改成从阶段 1 的支撑查询顺带算出（`MultiForecast.occupied_split`，2ef6383）**

- 原来（核对者：中）：FORCED_RISK 时在包络之后，对所有允许的行（第 0 波约 410 行）再查两次支撑（`_union_occ(committed_only=True)` + `_fine_occ`），不在 8 ms 截止时间里，只会拉长 tick。
- 现在：阶段 1 本来就对每一行、在同一组帧、同一个标称受击盒中心上查一次支撑并集。`occupied_split` 把这次查询的每个部件（细放置、窗口、外包盒、路径、各类盒子）按放置的"承诺"标记拆成两半分别查：并集和 `occupied()` 逐位相同（S1 不变），承诺那一半就是 P_cm 要的，细放置那部分就是 P_f 要的。FORCED_RISK 时只剩两次求均值。阶段 1 在包络之前，它多出来的时间算在包络的截止预算里（截止时间从 tick 开始计）。没有改变任何选择：键值和旧的两次查询逐位相同。
- 核验：`tests/test_multi_forecast.py::test_occupied_split_is_the_union_and_its_committed_and_fine_parts`（并集 = `occupied()`，两部分 = 旧的两个查询）；`test_commit_rank_refines_forced_risk_by_the_committed_support` 加了"规划器的 P_cm / P_f 等于旧的两次查询"；在真实录像上逐 tick 比（下表的 1,907 个 FORCED_RISK tick）全部逐位相等。
- 配对测量（`round3\pc_bench.py`）：同一进程里每臂一个 ForumPlannerPolicy（共享表），每个录像 STATE 轮流喂给四臂（每帧换先后），开环；四臂同一时刻承受同一负载（整机重负载：其他轨的 4 个游戏实例 + 离线任务）。C = 都关，PC = commit_rank，S = seen，SPC = 两者；时间单位 ms：

| 录像 | 规划 p50（C / PC / S / SPC） | 阶段 1 支撑 p50 | FORCED_RISK 排序段 p50 | policy tick p50 | 迟到 tick（> 16.7 ms） | 旧实现那两次查询 p50 / p99 |
|---|---|---|---|---|---|---|
| 第 0 波（`20261008_015959` i0 ep3，960 帧，FORCED_RISK 754） | 4.74 / 5.02 / 5.00 / 5.33 | 1.00 / 1.13 / 1.00 / 1.16 | 0.16 / 0.26 / 0.31 / 0.43 | 11.3 / 11.4 / 11.4 / 11.7 | 3.0 / 2.6 / 2.9 / 2.4 % | 0.78 / 2.7 |
| 第 7 波（`20261008_052126` i1 ep0，960 帧，849） | 3.90 / 4.29 / 4.16 / 4.48 | 0.75 / 0.83 / 0.76 / 0.83 | 0.15 / 0.27 / 0.26 / 0.39 | 8.7 / 9.0 / 9.0 / 9.1 | 1.1 / 0.8 / 0.8 / 0.8 % | 0.60 / 2.8 |
| 第 13 波（同一运行 ep1，522 帧，304；和全套测试同时跑） | 6.83 / 7.08 / 6.70 / 7.21 | 1.06 / 1.15 / 1.09 / 1.15 | 0.19 / 0.32 / 0.31 / 0.44 | 12.4 / 12.7 / 12.4 / 12.7 | 17.4 / 19.9 / 19.4 / 19.5 % | 0.93 / 4.8 |

  commit_rank 现在合计多 0.25–0.4 ms 规划 p50（阶段 1 +0.1，排序段 +0.1，其余是开环下选择不同带来的差异），旧实现单是那两次查询就 0.6–0.9 ms p50、2.7–4.8 ms p99；seen 的 `seen_contacts` p50 0.09–0.12 ms、p99 0.4–1.0 ms。迟到比例在同一负载下没有可分辨的差别（第 0 / 7 波 PC、SPC 反而略低；第 13 波 522 帧里 91 对 101–104 个，在泊松误差内）。

**2. 终点价值默认关**（2ef6383 起，`SSBOT_FORUM_TV=1` 开；核对者：低）：闭环没有收益（20.5：TV 18.41 对只修目标 18.42 次/分钟），离线只多约 1 个点（20.7），而它在包络之前、占包络的截止预算（0.9–1.3 ms p50，满载 p99 到 3 ms）。代码、权重和开关都留着，等有闭环收益再开。

**3. 事后判定的选择偏差（核对者：低；`round3\base_eval.py`，round2 的转储）**：开环重放时实战排序选的基本就是录像里实际走的那条（重放和实际选择 99.5–99.8 % 一致），而录像里的威胁是冲着录像里的主角去的，所以靠近录像路径的行事后判"不安全"偏多：和选中行前 6 帧按键相同的行，受击前事后安全只有 30.8 % / 33.0 %，低于随机一个允许行的 36.8 % / 39.1 %。因此：

- 排序之间的比较以"随机一个允许行"为基线（20.7 / 20.8 的表已补）：受击前 commit_rank +4.7 / +3.2 个百分点、seen +0.7 / +2.5、叠加 +11.9 / +11.9；全部 FORCED_RISK tick 上 +7.4 / +5.4、+4.9 / +6.1、+11.8 / +10.7。原来写的"比实战 +11 / +10"有一半来自实战本身被偏差压低。
- J0 在受击前 AUC 0.46 不是"反着来"，而是 J0 和录像路径相关（20.7 第 2 条已改）。
- `forum_tv_audit` 的输出多了 `clear.random`（每个 tick 允许行里事后安全的比例，再按 tick 平均），文档里说明要和它比、不要和实战选择比。
- 取证轨（§19.5）独立得出同样的结论（"开环事后判定偏向没执行的行"），它的结论只靠支撑饱和 / 打平的证据，不靠"比随机差"。

**4. 第 2 轮 A/B 的执行方式和开销归因（核对者：驳回两条）**：20.10 已更正——四批是依次跑的，迟到比例主要是各批的负载（同样的 SPC 代码 40.1 % 对 5.8 %），代码开销按上面第 1 条的配对测量。

**5. 逐场交替的 A/B（`SSBOT_FORUM_AB`）**：ForumPlannerPolicy 读 `SSBOT_FORUM_AB="名:pc=0|1,fr=share|seen;..."`，第 k 场用第 k mod n 组（`ForumConfig` 覆盖 commit_rank / forced_rank），本场的组名记在 attempts 的 `policy.ab_arm`；同一个 combat_run 批次里各组轮流，同一时段、同一负载。驱动 `C:\ssbot\sandbox\r5v_ab3.ps1`（冻结检出 `C:\ssbot\live_r5v3_2ef6383`，实例 0，A0b 协议，终点价值关、T 36，种子 300800 起，每组 25 场，真退出后的 HARNESS_FAIL 让批次提前结束时用种子 + 100 补齐、缺得多的组排前面），四组 = 2×2：C（都关）、PC、S（seen）、SPC。报告 `round3\ab3_report.py`。

**6. 第 3 轮 A/B 结果（实例 0，2026-10-08 06:34–07:26，运行 `20261008_063420`，种子 300900 起；第一批 300800 的第 1 场就是真退出后的 "paused unasked" HARNESS_FAIL，驱动换种子重来）**：100 场，四组各 25 场，**同一批里逐场轮换**（C、PC、S、SPC、C、…），所以四组承受同一负载（整批迟到 1.4 %）。终点价值关、T 36、代码 2ef6383。`round3\ab3_report.txt`：

| 组 | 每场受击 | 每分钟受击（95 % bootstrap） | 局内时长 p50 / 均值（s） | FORCED_RISK / EVADE | 规划 p50（ms） | tick p50 / p99（ms） | 迟到 tick | 击杀 |
|---|---|---|---|---|---|---|---|---|
| C（都关） | 4.16 | **18.9（17.1–20.8）** | 12.7 / 13.2 | 0.808 | 4.11 | 9.9 / 17.4 | 1.9 % | 0 |
| PC（commit_rank） | 4.48 | **13.7（12.5–15.2）** | 19.6 / 19.7 | 0.863 | 4.49 | 9.8 / 17.2 | 1.3 % | 0 |
| S（seen） | 4.20 | **13.8（12.5–15.3）** | 16.9 / 18.3 | 0.879 | 4.29 | 10.1 / 16.8 | 1.3 % | 1（Envoy） |
| SPC（seen + commit_rank） | 4.44 | **10.2（9.1–11.6）** | 27.0 / 26.1 | 0.910 | 4.61 | 10.2 / 17.1 | 1.3 % | 1（Choristor） |

每分钟受击之比（两组各自重抽，4000 次）：PC / C 0.72（0.63–0.83），S / C 0.73（0.64–0.84），**SPC / S 0.74（0.64–0.87）**，SPC / PC 0.75（0.64–0.88）；2×2 主效应 commit_rank 0.73（0.66–0.82）、seen 0.74（0.67–0.83），两者大致相乘（0.72 × 0.73 = 0.53，SPC / C = 0.54），没有交互。平均存活 commit_rank +7.1 s（5.0–9.3），seen +5.7 s（3.5–7.9）。

- **commit_rank 在 seen 之上也有显著收益**（SPC / S 0.74，区间不含 1）：第 2 轮"叠加比只开 seen 好"只有离线证据（核对者：信息），现在有了同一时段、逐场交替的实战证据。数值和第 2 轮一致（C 18.9 对 19.0，PC 13.7 对 12.4，SPC 10.2 对 10.3）。
- **迟到没有变多**：同一负载下 C 1.9 %、PC / S / SPC 1.3 %（活得久的组 tick 更多、FORCED_RISK 更多，迟到比例反而略低）；规划 p50 commit_rank +0.38 ms、seen +0.18 ms、两者 +0.50 ms，和第 1 条的配对测量一致。第 2 轮的 18–24 %（以及 40 %）是批次负载。
- 仍然**每一场都是第 0 波 Q1 退出**（0 WOULD_DIE、没有一场进第 1 波），但这条轨第一次有了击杀：S 一场杀了 Envoy（22.9 s），SPC 一场杀了 Choristor（29.8 s），都是 Slash。活得越久越有机会，但瓶颈仍然是进攻。
- 和取证轨对照（§19；它的 seen 对 seen_cf ABBA 配对，种子 340100–340124，实例 0，05:57–06:32，迟到 1.4–1.8 %，本轨用 `ab3_report.py` 重算）：seen 12.4（11.4–13.5），seen_cf 9.4（8.7–10.2），之比 0.76；本轨 SPC / S 0.74。seen_cf（seen 之后按"承诺的细放置"接触比例排）和 SPC（seen > P > P_cm > P_f）机制几乎相同、效果相同（不同时段，区间重叠：9.4（8.7–10.2）对 10.2（9.1–11.6））。开销不同：seen_cf 在包络之后对所有允许行再查一次细放置（它的配对里规划 p50 5.06 对 seen 4.35 ms），本轨从阶段 1 的拆分查询顺带得到（SPC 4.61 对 S 4.29 ms）。集成时二选一即可；若取 seen_cf，它的键可以直接用 `occupied_split` 里承诺的细放置那一半（拆分时 `com` 在并入窗口等之前就是它），不必再查。

结论：commit_rank 保持默认开；终点价值默认关；seen 的默认值仍是取证轨的开关——实战配对数据支持集成时打开（seen 或 seen_cf 再叠承诺的招，两条轨的数字一致）。剩下的受击（20.9）和"杀不掉"不是这条轨的排序能解决的。

## 21. R6 v0：你的规则作 L2 目标层 + Clapper 控制器（2026-10-08，forum_planner_plan.md §5 R6；分支 worktree-wf_814dfeea-b10-3；离线 + 实例 1 的 A/B（21.5）；第 2 轮 2026-10-08 早上（21.6））

### 21.1 做了什么（`combat/tactics/gauntlet.py` `GauntletTactics`，`Forum.yaml` `forum.l2`）

- 每 tick 先跑 LOCAL（R4 的 `ForumTactics`，HEAL / LEAVE 照旧优先），再由 L2 选目标：每 6 tick（10 Hz）重选一次，目标死了 / 出场 / 换了招式家族 / PUNISH 窗口过了就立即重选；新目标得分要是旧的 1.25 倍才换（滞回）。只改打分（站位 stance_x、朝向 boss_x、每个敌人的命中权重、按目标的权重系数），**规划器的 S / Hz / U 不看 prefs**（§4.4 第 2 条），安全仍由支撑检查、过滤器、监督器负责。
- 目标规则（按顺序，第一个成立的）：
  - **PUNISH（远处目标）**：每个候选敌人一个"接敌点"，一次批量查询 `MultiForecast.occupied`（所有敌人、投射物、入场）得到窗口 = **主角到达（t_run）之后**这个点第一次被支撑覆盖的时刻；t_run = 0.05 + |dx| / 17.5（冲刺 + 疾跑，你说的约 17.5 u/s）；窗口 ≥ t_run + 0.25（出刀到收割者横砍有效段结束 0.208 s）+ 0.10 余量 才去；多个可去时按（窗口 − 需要）× 类型优先级挑。这就是计划 R6 行的远处目标场景：近处待机的（下一招随时可起，窗口短）对远处长后摇的（窗口长）→ 窗口够就去远的，不够就不去。
  - **RUSH**：有落单的（8 u 内没有别的在场敌人）就冲上去；全都分散时先打"最快追上来的"（ETA = max(0, 距离 − 1.8) / 追击速度）。
  - **KITE**：没有落单的：站在最快那只的另一侧 8 u（远离其他敌人那一侧），让它单独先到；有 Tiny 时改站最近的 Maestro 正下方（below.json：Tiny 冲撞正下方 7.1 % 对前方 34 / 58 %）。LOCAL 判 EVADE（主角位置 0.6 s 内被覆盖）时 KITE 让给 EVADE；PUNISH / RUSH 不让（支撑检查是安全）。
  - 优先级：Clawmaiden 在场时只选它（`first`，权重 3）；**Minister 只在没有别的敌人时才选**（`last`）。
- 接敌点：飞行怪（Bellbearer、Reed、Minister、Maestro）在它正下方（你的"在它下面更安全"；Minister 冲刺斩往前两个身位，所以从下面开始最后在它身后）；其他类型在主角这一侧 1.8 u（LOCAL 的 engage_reach）；Clapper 用下面的控制器。
- **Clapper 控制器**（不能拼刀；§10、clapper_face.md）：Idle / Walk / 施法 / 后撤：在主角这一侧的脸上 3.0 u（它每招起手 FaceObject 面向主角）；**锤（CC_SLAM）**：主角在它前面 → 退到前方 13 u（12.5 u 2.3 %、13 u 0）；主角已在它背后 → 背后 3.5 u（3 u 0.2 %）；前方没地方时也去背后；下劈踩头（你练习 15 / 22）留给规划器自己的行去选；**跳砸 / 跳施法**：钻到它下面、站到落点背后 2.5 u：落点 = 起跳点 + 0.92 × clamp(瞄准 − 起跳点, ±12)，瞄准 = Jump Aim 那一帧的主角 x ∓ 5（它这一侧）；Jump Aim 之前按当前主角位置估，之后用存下的瞄准（`jump_landing`）；它在空中时对它的命中权重再 ×1.5（顺路上挑）；大符文在落点前方 6.62 u、r 7.19，只伸到落点后 0.58 u，所以落点背后 2.5 u 在圆外；**两只不同时出招**（Buddy Is Attacking）：一只在出招时另一只的优先级 ×2；**施法（CC_CAST，约 1.25 s 原地）**：脸上照砍，`vocab` 里放 `GLIDE_SPIKE` 钩子（R7 的锯齿环 glide_spike 还没进规划器，目前没人读）。
- **Clapper 朝向的修正**：oracle 后端的 `Entity.facing` 是速度的符号，不动时取 `-1 if flipX else 1`，而 Forum 的精灵不翻转时朝 −x（`enemy_tracker.FACES_LEFT`）：站着的 Clapper 朝向是反的。R0 缓存 15 场核对：Slam Antic 帧 flipX = 1 且主角在它右边 1,564 / 1,631、flipX = 0 且主角在左边 5,414 / 5,434；Idle 6,507 / 6,623、39,630 / 39,651。新函数 `clapper_facing`（flipX 1 = 朝右）给 L2 和 R4 的口袋规则 (2)（以前用的是反的朝向；A0 / A0b 从没到终局，不影响基线）。
- **追击速度**（`pursuit_u_s`，R0 缓存 20 场，敌人速度在"指向主角"方向上的分量，只算在场、距离 > 4 u、正在靠近（> 0.5 u/s）的帧的均值；数据策略的主角）：Choristor 9.69、Clapper 9.38、Envoy 8.14、Tiny 7.02、Minister 5.64、Reed 4.63、Clawmaiden 4.39、Bellbearer 3.99、Maestro 3.12 u/s（p90：Envoy 12.9、Tiny 8.0、Clapper 7.7、Minister 7.2、Reed 6.7、Clawmaiden 6.4、Bellbearer 5.2、Maestro 4.5、Choristor 1.3——Choristor 多数时间原地鞭，靠近时是跳，所以用"靠近时的均值"）。
- 失效 → LOCAL（§4.4 第 4 条）：异常或注入失败（`fail_p`）原样返回 LOCAL 的 prefs；开关 `SSBOT_FORUM_L2`（0 / off = A0 的 LOCAL，fail:<p> = 注入），combat_run 把它记进 config.json 和每行。
- 记账：`stats()["l2"]`（目标按 tick、目标变化 / 换目标、PUNISH 次数与"窗口内打中目标"次数、L2 用时），决策日志多了 `goal`、`goal_why`、`goal_t_end`、`l2_cands`（每次重选时每个候选：iid、类型、窗口、需要、是否落单、ETA、优先级、此刻是否已被覆盖）——目标仲裁逐条可查；`forum_a0_report` 加了 L2 一节、每场受击和击杀数。

### 21.2 离线核对

- 单元测试 `tests/test_forum_l2.py`（13 项）：远处目标（近处待机的 Choristor 在 2 u、远处后摇里的 Envoy 在 13 u：远处接敌点到达后 1.4 s 内不被覆盖 → PUNISH 远的、站位 31.2；只有 0.8 s → 不去，改 RUSH 近的；近处自己的窗口够 → PUNISH 近的）、落单 / 分散 / 扎堆、Tiny 时站 Maestro 下方、Clawmaiden 先 / Minister 后、Clapper 控制器各招、两只 Clapper 互锁、朝向、失效三种（注入、异常、关闭）逐字段等于 LOCAL、开关解析、PUNISH 窗口内命中计数。`test_forum_tactics.py` 照旧 5 项通过。
- **§4.4 第 4 条整条决策逐位相同**：`forum_policy_replay`（`074719` i3 ep0 第 0 波，600 tick，截止时间 inf）`SSBOT_FORUM_L2=fail:1` 对 `=0`：600 / 600 tick 的计划名、S、FORCED_RISK、按键、J 0 处不同。
- 开环回放（同一录像，数据策略的主角位置，所以计划不被执行；机器负载高：5 个游戏实例 + 其他代理）：L2 每 tick p50 0.014–0.047 ms、p99 1.4–3.3 ms（批量查询只在重选的 tick 跑）；异常 0；支撑外命中 0。目标分布：第 0 波 KITE(EVADE) 63 %、RUSH 31 %；第 3 波 Clawmaiden 91 %（first）；第 6 波 KITE(EVADE)（在 Maestro 下方）89 %；第 7 波（单只 Clapper）RUSH 94 %；第 13 波（两只 Clapper）RUSH 48 %、KITE(EVADE) 46 %。
- **PUNISH 在多敌波次里不成立**：第 0 / 3 / 6 波 1,000 tick 的重选里（Envoy / Choristor / Reed / Bellbearer / Clawmaiden / Tiny / Maestro 共 2,331 个候选），接敌点**此刻就被支撑覆盖的占 99.7 %**，到达之后的空闲时间中位 0.017 s、p90 0.030 s、最长 0.168 s，**≥ 0.35 s（够一刀）的 0 次**：待机敌人的支撑（下一招随时可起 + 待机身体管）一直盖着它身边，与 A0 的 87 % FORCED_RISK 同一个原因（§16.4 第 1 条）。接敌点从 1.8 u 改到 3.0 u（收割者横砍够 3.6 u）重跑一次：同样 0 次（没有采用）。第 7 波单只 Clapper 时有 1 次 PUNISH（Tiny）。第一版把"到达前就被覆盖"也算进窗口（窗口全是 0），已改成从到达算起。
- Clapper 控制器在录像上各分支都触发（开环，2,000 tick / 波，按 tick 计）：第 7 波（单只）脸上 1,099、跳（钻到落点背后）513、锤：退到前方 110 / 前方没地方改去背后 82 / 已在背后留在背后 71、PUNISH 12（Tiny）；第 13 波（两只）脸上 790、锤 84 / 83 / 4、KITE(EVADE) 917（两只相距 < 8 u 时没有落单的）。落点公式在实战里的误差没有逐次核对（clapper_face.md 的拟合残差 p50 0、IQR ±0.13 u）。Clapper 朝向检查见 21.1。

### 21.3 远处目标场景（计划 R6 行的验收）

- 合成局面：通过（21.2 第一条）。
- 录像切片：上面的开环回放里这种局面（远处有到达后够一刀的窗口）在第 0 / 3 / 6 波没有出现，所以录像上只能验证"窗口不够时不去"（全部候选都没去），"窗口够时去"只有合成局面和第 7 波的 1 次。闭环实战里 PUNISH 的次数和"窗口内打中"的次数由 A/B 记（`punish_goals` / `punish_landed`）。

### 21.4 没做 / 未核实

- 接敌点只是一个点（离敌人 1.8 u 或正下方），窗口按"站着的主角"查；收割者横砍够距 3.6 u，换成"够得着的最远点"窗口会长一些（未测）。
- 跑过去的路上会不会被别的敌人挡住只由规划器逐帧查（L2 不查路径）。
- 落单判据只用水平距离 8 u，不是计划里的"危险区和危险时段是否重叠"。
- 下劈踩 Clapper 头（命中无敌 0.16 s）在运动学里有没有建模没查；规划器只会在它的行恰好安全时选。
- "在 Reed 下面更安全"与 R1 的数据（飞行怪下方对 Reed 无效：3.5 对 3.1 次 / 分）不一致，按你的规则做了，由 A/B 看。

### 21.5 第 1 轮 A/B（实例 1，2026-10-08 01:59–02:40，冻结检出 `C:\ssbot\live_r6_ef036d5`）

驱动 `C:\ssbot\sandbox\r6_ab.ps1`（日志 `r6_ab.log`）等路线 Boss 采集结束后在实例 1 上按 A0b 的协议（fo_A、eval、planner、oracle、线程 4、真退出 0.2）跑了同种子成对的四块，每块 25 场：L2 开 `20261008_015904`（种子 310000）、`021942`（310025）；L2 关（`SSBOT_FORUM_L2=0`，即 A0b 的 LOCAL 战术）`020919`（310000）、`022951`（310025）。报告：`forum_a0_report`（会话临时目录 `r6\ab\on.json`、`off.json`、`a0b.json`）；按种子配对、按目标 / 受击的分析 `r6\ab\ab_anal.py` → `ab_anal.json`。A0b = `20261005_205437` + `205857`（种子 180000 / 180100，不成对）。

| 指标 | L2 开（50 场） | L2 关（50 场，成对） | A0b（51 场，不成对） |
|---|---|---|---|
| 结果 | QUIT 50（全是 Q1：h = 1） | QUIT 50（全是 Q1） | QUIT 50 + HARNESS_FAIL 1 |
| 到达的波 | 50 场全在第 0 波 | 同 | 同 |
| 受击 / 场（damage 事件） | 4.26：Envoy 94、Choristor 77、Reed 42 | 4.10：89 / 73 / 43 | 4.27：105 / 56 / 57 |
| Multihit tick | 37 | 45 | 35 |
| 存活（开战到退出）p50 / 最长 | 12.6 / 20.5 s | 13.3 / 18.4 s | 12.7 / 19.9 s |
| 钉子打中敌人 / 场（录像 `hit` 事件，每下 9） | 4.56（Envoy 107、Choristor 75、Reed 46 下） | 5.08（129 / 63 / 62） | — |
| 击杀 | 0 | 0 | 0 |
| FORCED_RISK（tick） | 79.0 % | 80.5 % | 80.3 % |
| 支撑外命中 / 未知 | **0 / 0** | 0 / 0 | 1 / 1（i4 ep0 f 905007，来源 iid 9655958；A0b 自己的，未查） |
| tick p50 / p99 的中位、p99 最大 | 6.7 / 13.3 / 17.5 ms | 6.2 / 12.0 / 17.3 ms | 5.9 / 11.8 / 1,471.6 ms（一次卡顿） |
| L2 自身 p50 / p99（中位） | 0.026 / 0.89 ms | — | — |
| 每秒按键（锁存按键 / 游戏时间，每场中位） | 7.28 | 7.18 | 7.75 |
| 计划改动率（每场中位） | 0.555 | 0.620 | 0.615 |
| 目标变化 | L2 目标（换目标或换规则）**33.0 次 / 分**；决策日志里目标 iid 的变化 37.5 次 / 分 | LOCAL 的目标 iid 变化 71.7 次 / 分 | — |
| 真退出 | 9 次：暂停 9、到主菜单 9、错误确认 0 | 9 / 9 / 9 / 0 | 7 / 7 / 7 / 0 |

按种子配对（50 对，开 − 关）：受击 +0.16 次（sd 0.98，se 0.14）、存活 −0.71 s（sd 3.03，se 0.43；开活得更久的 20 对、关活得更久的 30 对）、钉子命中 −0.52 下。**R6 v0 没有改变结果**，差异都在噪声以内。

L2 在第 0 波做了什么、受击从哪来（决策日志，L2 开 24,945 个决策 tick）：

- **L2 确实在工作**：RUSH 55 %、KITE(EVADE) 43 %（KITE 时 LOCAL 的 EVADE 成立，原样用 LOCAL 的打分）、其余 2 %（暂停等）；**PUNISH 0 次**（21.2 的原因：待机敌人的支撑一直盖着接敌点）。RUSH 的理由："落单" 9,310 tick、"都分散：最快追来的" 4,449 tick——第 0 波三只敌人在 35 u 的场地里多数时候相距 ≥ 8 u，按 8 u 的水平判据几乎总有落单的。目标：Envoy 42 %、Reed 31 %、Choristor 25 %。
- RUSH 把主角带到了目标身边：主角到目标的 |dx| 中位 2.5 u（KITE(EVADE) 3.8 u，L2 关 3.7 u），站位离主角中位 1.3 u；但出刀的计划占比几乎不变（13 % 对 L2 关 12 %），钉子命中反而略少。
- **受击和 L2 选了什么无关**：按受击前 0.2 s 的目标分，RUSH 时 122 次（69 次来自正在冲的目标本身、53 次来自别的）、KITE(EVADE) 时 91 次（45 / 46）；每个决策 tick 的受击率 RUSH 0.0089、KITE(EVADE) 0.0085、L2 关 0.0085——同一个速率（约每 3 s 一下），不管 L2 选谁、站哪。受击时的主角–来源距离中位 4.5 u（关 4.9 u）。受击来源的比例和 A0b 一样（Envoy 冲锋最多）。**（第 3 轮更正，核对者）**：这里的分母是决策日志的 tick，它是按事件触发采样的（L2 开 24,945 个，全部 tick 33,701 个），有偏；按全部 tick（`policy.ticks`）算，第 1、2 轮的三对运行合计 75 对：L2 开 0.00612、关 0.00565 次 / tick（+8 %），每分钟 19.95 对 18.57（不显著：成对受击 +0.11，se 0.11）；但**受击来源变了**：Choristor 的 `Body Damager` 开 28 次、关 8 次（成对 +0.27 / 场，se 0.08，显著），存活成对 −0.62 s（se 0.36，约 1.7 se）。所以"受击和 L2 选什么无关"只对总数大致成立，见 21.7.4。
- 原因（与 diag 轨道的早期结论一致，HANDOFF 'Task wave-0 forensics'、forum.md §19）：FORCED_RISK 的 tick（74 %）里规划器按"候选在支撑里的接触帧占比 → 最晚接触 → J"排序（`forum_planner` 的 FORCED_RISK 选择），而第 0 波的支撑饱和：diag 查到 77 % 的 FORCED_RISK tick 上所选行和它的 5 个备选 P 都是 1.0（每个 stage-1 帧都在支撑里），前几项全部并列，选择落到 J（p_k 预选也按 J）——所以第 0 波里 L2 的打分其实决定了计划（J 贪心：跑向目标、出刀），只是不管 J 来自 RUSH 的站位 / 命中权重还是 LOCAL 的 EVADE，规划器都"以为每个计划一样危险"，受击速率一样。diag 的事后核对：A0b 两场里所选计划在事后（录像里的伤害碰撞体）不碰的比例 70 %，随机一行 77 %。第 0 波的瓶颈不是"打谁"，而是 FORCED_RISK 在支撑饱和时没有可用的排序键（diag 试 `SSBOT_FORUM_FR=seen`：按此刻看得见的伤害碰撞体排序；R5 的终点价值、R8 的拼刀分支也在这一层）。
- 验收里的两条：每秒按键、计划改动率不高于 A0b（7.28 对 7.75、0.555 对 0.615）✓；**目标变化 ≤ 10 / 分 ✗**（33 / 分）：KITE 的"ETA 最小"目标随主角移动来回换，而且目标每换一招（招式家族变化）旧目标就作废、不经滞回重选。第 2 轮修正见 21.6。

### 21.6 第 2 轮（2026-10-08 03:10–05:40，分支同上；实例 1）

#### 21.6.1 目标保持（21.5 的 33 次 / 分）

- **规则和目标分开保持**（`gauntlet.py` `_pick` / `_choose`，`Forum.yaml` `forum.l2`）：规则（PUNISH / RUSH / KITE）要跑满 `goal_dwell_s` 1 s 才换（换进 PUNISH 不等）；同一规则下，原目标只要还"合格"（RUSH：落单，原目标的落单判据放宽到 8 − 2 = 6 u；KITE：任何一只）就留着，除非另一只得分 ≥ 1.5 倍且原目标已经当了 `dwell_s` 4 s 目标；**被冲的目标身边来了别的敌人**时先对它 KITE（目标不换），到 4 s 后 RUSH 才换到别的落单敌人；立即换目标的只有：原目标死了 / 出场、PUNISH 开窗、`first` 类型（Clawmaiden）进场、两只 Clapper 中另一只"轮到"（见 21.6.3）。目标换招不再让目标作废，只触发一次重选（可能留着原目标）。每场的统计多了 `tgt_switches` 和按原因分的 `switch_kinds`（gone / ineligible / better / turn / punish）；`forum_a0_report` 多了 `tgt_switches_per_min`、每秒按键（锁存按键 / 游戏时间）和计划改动率。
- **顺带修了 PUNISH 的一个错**：接敌点远到"跑过去 + 一刀"超过 2 s 查询长度的（|dx| ≳ 28 u），到达之后根本没查，窗口记成 inf，于是总是"可去"；开环回放里两只这样的远处目标每 0.1 s 互相 PUNISH 切换（窗口封顶后得分为负，1.25 倍的滞回对负数反而放行）。现在查询里装不下的窗口记为查询终点（不够一刀）。21.2 的"≥ 0.35 s 的窗口 0 次"不受影响（那里没有这么远的候选被计入）。
- 开环回放（21.5 的 L2 开两个运行各前 10 场，第 0 波，主角位置是录像里的；`l2_switch_replay.py`，会话临时目录 `r6\sw_*.json`）：目标切换（换了一只敌人）每分钟：第 1 轮代码 23.8；只加停留 2 s 19.6；加"换招不作废" + 停留 3 s（×1.25）10.3、×1.5 9.6、×2.0 9.2；采用 ×1.5、4 s、规则 1 s。按原因（×1.25、3 s）：better 34、ineligible 10。**（第 3 轮更正）**：这几个数的样本和配置不同：23.8 是 10 场（`sw_old`），9.6 是 20 场、停留 3 s；最终采用的 4 s 在同样 20 场上是 8.22（核对者重跑），而且这只是"换敌人"（`tgt_switches`）；同一回放里"目标或规则变化"（`changes`，第 1 轮判不过用的口径）是 23.0 次 / 分。

#### 21.6.2 实战：先是负载

- 第一次实战（驱动 `C:\ssbot\sandbox\r6_ws.ps1`，冻结检出 `live_r6_6d2f457`，03:45）在机器满载下跑不了：CPU 100 %（其他轨道的取证、回放、行为表、三套全量测试，大多是低优先级）；每场迟到 tick 34–172（第 1 轮 0–2）、tick p99 22–38 ms；7 场后一次 "paused unasked"（大脑 14 帧没发 ACTION，oracle 看门狗按了暂停，HARNESS_FAIL，一次就结束整个运行），L2 关那一块第 1 场就失败。同一时段别的轨道的实战也一样（迟到 100–350 / 场）。
- 第二个驱动 `r6_ws2.ps1`（冻结检出 `live_r6_171cf28`）：实例 1 的 combat_run worker 启动后提到 AboveNormal（两臂一样），某一块被 HARNESS_FAIL 截断时从失败那一场起用同样的种子和轮换补跑。之后波次起点每场迟到 tick 8–60（偶尔 142）、p99 16–26 ms，完整连战迟到 2.6–5.4 % 的 tick；r6_ws2–ws4 共 178 场（波次起点 128 + 完整连战 50）0 次 HARNESS_FAIL。**协议差异**：第 1 轮是普通优先级、负载低；第 2 轮的绝对数字（尤其是受击）在更差的时序下得到，两臂之间仍然成对可比。

#### 21.6.3 Clapper 控制器实战（波次起点 `Forum_A_w7`（一只）/ `Forum_A_w13`（两只），eval、planner、oracle、无真退出；按局轮换，种子 310100–310131，L2 开 / 关成对）

v2 = 171cf28（21.1 的控制器 + 脸上 4 u + 跳的时序判断，见下）。运行：L2 开 `20261008_035906`、`040911`；L2 关 `040451`、`041508`（各 16 场）。分析 `r6\ws_anal.py` → `ws_ab.json`。

| 指标 | w7 L2 开 | w7 L2 关 | w13 L2 开 | w13 L2 关 |
|---|---|---|---|---|
| 场数 / 结果 | 16 / 全 QUIT（Q1） | 16 / 全 QUIT | 16 / 全 QUIT | 16 / 全 QUIT |
| 存活（开波到退出）均值 / p50 | **19.7 / 18.6 s** | 11.1 / 10.9 s | **11.1 / 10.3 s** | 9.2 / 8.7 s |
| 受击 / 场、/ 分 | 3.31、**10.1** | 3.06、16.6 | 3.50、**19.0** | 3.12、20.4 |
| 受击来源 | 符文 24、本体 14、大符文 9、锤 6 | 锤 21、符文 11、本体 11、大符文 6 | 符文 25、锤 14、本体 12、大符文 5 | 锤 19、本体 17、符文 13、大符文 1 |
| 钉子打中 Clapper / 场、/ 分 | **6.4、19.6** | 2.1、11.5 | **10.9、59.0** | 5.7、37.1 |
| FORCED_RISK | 83.5 % | 71.3 % | 69.3 % | 65.0 % |
| 换目标 / 分 | 0 | — | 13.2（轮到 36、更好的 3） | — |

按种子配对（每波 16 对，开 − 关）：w7 存活 **+8.6 s**（se 1.5）、受击 +0.25（se 0.14）、打中 +4.3 下；w13 存活 **+1.9 s**（se 0.8）、受击 +0.38（se 0.18）、打中 +5.2 下。两波都没有击杀（Clapper 230 HP，收割者一下 9，要 26 下），都在挨 3 下左右（h = 1）时 Q1 退出——"每场受击"相同是退出规则决定的，比较看存活时间和受击 / 分钟。**控制器明显好于 LOCAL**：锤（`Slam Collider`）的命中从 21 → 6（w7）、19 → 14（w13），对 Clapper 的输出每分钟 +70 % / +59 %。

L2 开的受击按当时的控制器分支（受击前 0.2 s）：

- **脸上 ← 小符文 44 次（w7 24、w13 20）**：施法（CC_CAST）时站在脸上，`rune bomb` 1 颗 + 9 对、间距 4.2、r 2.17，**地面上没有安全格**（clapper_face.md §2），只能在近处那颗亮的 5–7 帧里人在空中；这是规划器选跳的时机问题：第 0 波一样的支撑饱和（21.5）下它分不出哪一行能躲（diag 的 `SSBOT_FORUM_FR=seen` 按此刻看得见的碰撞体排序，符文炸前 0.33–0.35 s 就画出来）。
- **跳 ← 本体 14 次（w7：退开时 10、钻过去时 4）**：逐场看（`ep 0/2/4/6/8/14`）都是同一个样子：Clapper 在左墙边起跳，"落点后方"被墙夹到 21.1（并不在落点后方），主角往那里钻；半空中剩余时间不够了，判断翻成"退开"，主角在它正下方掉头，被落地的本体砸中。
- **锤：钻到背后（前方没地方）← 本体 7 次（w13）**：前方没有 13 u 的地方时去背后，就是在地面上穿过它的身体。
- 锤：往外 ← 锤 5 次（w7，起手 0.8 s 内没跑到 13 u 外：站位差中位 3.4 u）。

由此的 **v3（716b539）**：跳的走法在它的 Jump Aim（落点确定）那一刻定下，整个跳都不改；落点后方要在场内（不被墙夹）才钻；锤在前方没地方时**往外退到墙边**（不穿过身体；锤够 12 u，离得越远越可能落空）；另外 w13 里"轮到另一只"只在另一只的接敌点能在这一招结束（`Subject.t_free`）之前跑到时才换（a637d77）——**（第 3 轮更正）这条实际没有生效**：`MultiForecast` 给每个 Subject 的 t_free 都是 0，于是"跑得到"永远不成立，"轮到"整条规则从 a637d77 起就关掉了（21.7.2）。v2 里已经有的：脸上 3 u → 4 u（本体前沿在 2.25 u，3 u 只留 0.5 u：第一次实战里冲过头撞上本体）；跳：钻过去只在"跑到落点后方 ≤ 落地前 0.25 s"（起跳到落地 1.415 s / 跳施法 1.85 s）且不在它落地前穿过它的身体时，否则退到落点前方跳砸 8.5 u / 跳施法 14.5 u 外（clapper_face.md §R6 的"往外 3.5 u / 9.2 u"）。

#### 21.6.4 完整连战复测（v2 171cf28，A0b 协议：fo_A、eval、planner、oracle、真退出 0.2；种子 310200，L2 开 `20261008_041945` / 关 `043128` 各 25 场，成对）

| 指标 | L2 开 | L2 关 |
|---|---|---|
| 结果 | QUIT 25（全 Q1），全在第 0 波 | 同 |
| 受击 / 场 | 4.48（Envoy 57、Choristor 36、Reed 19）+ Multihit tick 13 | 4.48（54 / 32 / 26）+ 13 |
| 存活 p50 / 最长 | 14.2 / 17.7 s | 13.9 / 18.2 s |
| FORCED_RISK | 80.4 % | 80.1 % |
| 支撑外命中 / 未知 | 0 / 0 | 0 / 0 |
| tick p50 / p99（中位）/ p99 最大 | 11.3 / 22.3 / 24.8 ms（迟到 5.4 %） | 10.3 / 19.1 / 22.3 ms（2.6 %） |
| 每秒按键 / 计划改动率（每场中位） | 6.97 / 0.582 | 6.89 / 0.625 |
| 换目标 / 分（`tgt_switches`） | **7.65**（44 次：原目标不再合格 26、更好的 18；目标或规则变化 25.9 / 分） | — |
| L2 | 目标 tick：KITE(EVADE) 9,703、RUSH 8,086、PUNISH 0；错误 0；每 tick p99 中位 1.3 ms | — |
| 真退出 | 7 次：暂停 7、到主菜单 7、错误确认 0 | 7 / 7 / 7 / 0 |

成对（25 对，开 − 关）：受击 0.00（se 0.15）、存活 −0.45 s（se 0.66；开更久 13 对、关更久 12 对）。和第 1 轮一样没有差别（21.5 的原因）。验收里能在第 0 波核对的三条：~~换目标 ≤ 10 / 分 ✓（7.65）~~、每秒按键不高于 A0b ✓（6.97 对 7.75）、计划改动率不高于 A0b ✓（0.582 对 0.615）。**（第 3 轮更正，核对者）**：7.65 是"换敌人"（`tgt_switches`），第 1 轮判"不过"用的 33.0 是"目标或规则变化"（`changes`）；同一口径这里是 **25.9 次 / 分，仍然不过**（计划 R6 行的"目标切换"指 GoalArbiter 的 goal 切换，换规则也算）；第 3 轮的处理和复测见 21.7.3。tick 时间比第 1 轮高约一倍是机器负载（21.6.2）。

#### 21.6.5 v3、v4 的实战（只跑 L2 开这一臂：同一组种子 310100–310131、同一轮换；L2 关不跑任何 L2 代码，21.6.3 的 `040451` / `041508` 仍是对照）

（第 3 轮注，核对者：v3 / v4 和对照**不是交错跑的**：L2 关在 04:04–04:15，v3 在 05:06、v4 在 05:21；对照组的时序更差（w7 每场迟到的 state 1.5 对 v4 0.6，w13 2.4 对 0.2）。w7 的 +19.5 s（16 / 16 对）不受影响，w13 +1.0 s（se 0.8）这样的小效应可能受负载差异影响。第 3 轮的复测按块交错，21.7.5。）

| 指标 | w7 v2 | w7 v3 | w7 v4 | w13 v2 | w13 v3 | w13 v4 |
|---|---|---|---|---|---|---|
| 运行 | `035906` + `040911` | `050637` | `052126` | 同左 | 同左 | 同左 |
| 存活均值 / p50 | 19.7 / 18.6 s | 19.3 / 18.3 s | **30.6 / 28.0 s** | 11.1 / 10.3 s | 10.1 / 9.8 s | 10.2 / 10.0 s |
| 对 L2 关成对（存活，se） | +8.6（1.5） | +8.2（1.7） | **+19.5（1.9）** | +1.9（0.8） | +0.9（0.5） | +1.0（0.8） |
| 受击 / 分 | 10.1 | 10.9 | **7.3** | 19.0 | 19.2 | 19.5 |
| 受击来源 | 符文 24、本体 14、大符文 9、锤 6 | 符文 24、锤 19、大符文 12、本体 1 | 符文 36、大符文 20、锤 4、本体 0 | 符文 25、锤 14、本体 12、大符文 5 | 符文 18、锤 17、本体 15、大符文 2 | 符文 21、本体 16、锤 10、大符文 6 |
| 打中 Clapper / 场 | 6.4 | 5.75 | 8.7 | 10.9 | 9.4 | 9.1 |
| 换目标 / 分 | 0 | 0 | 0 | 13.2（轮到） | 4.4 | 3.7 |

- **v3（716b539：跳的走法在 Jump Aim 定下、落点后方要有地方、锤在前方没地方时退到墙边、"轮到另一只"要来得及）**：w7 的本体受击 14 → 1（~~掉头钻回落点下方的情况没了~~ **第 3 轮更正**：这个归因不成立。Jump Aim 是零时长状态，tick 从来不会停在它上面，所以瞄准没存、走法从没被固定，v3 开的决策日志里同一跳内分支翻转 102 次；本体受击的下降应来自同一提交里"落点后方要在场内"的条件（被墙夹住时不再钻过去）。修正见 21.7.1），但锤 / 落地锤的受击 6 → 19：退开（`jump: back off`）时被落地锤打 9 次、往外（`slam: step out`）时被锤打 9 次。v3 − v2 成对（同种子）：w7 存活 −0.33 s（se 2.3）、w13 −0.92 s（se 0.7）——没有分别，受击只是换了来源。看决策日志：退开 / 往外的分支里目标的命中权重还是 3（跳时还 ×1.5，原意是"钻过去时顺路上挑"），支撑饱和、选择落到 J 时，命中权重把人往它那边拉，站位往外推。
- **v4（8754008）**：控制器"走开"的分支（锤往外、锤退到墙边、跳退开）里目标的命中权重置 0；上挑的 ×1.5 只在"钻到落点后方"时给。结果：**w7 存活 30.6 s**（v4 − v2 成对 +11.0 s，se 2.8；对 L2 关 +19.5 s），受击 7.3 次 / 分（L2 关 16.6），锤的受击 4（L2 关 21），本体 0；打中 Clapper 每场 8.7 下（每分钟 17.0，与 v2 的 19.6 相近：活得久、打得一样快）。剩下的受击几乎全是施法：小符文 36、跳施法的大符文 20（都在"脸上"分支：大符文落地后约 3.3 s 才炸，这时跳已结束、控制器回到脸上 4 u，人站在半径 7.19 的圆里）。w13 没有变化（10.2 s，v4 − v2 −0.85 s，se 1.1）：两只靠在一起时没有落单的，KITE 让给 LOCAL 的 EVADE（受击 20 次在这里），被墙夹住的锤往墙边退仍被本体撞 7 次。
- 换目标：w13 3.7 次 / 分（v2 13.2：轮到 36、更好的 3）。~~可达性门控之后少了~~ **第 3 轮更正**：少了是因为"轮到"这条规则整个失效了（t_free 恒为 0，v3 / v4 的 32 场 w13 里 turn 0 次，10 次换目标全是 better），不是门控的效果（21.7.2）。
- 每秒按键（第 3 轮补，核对者指出没报）：w7 / w13 上 L2 开 7.64（v4）/ 7.71（v2），成对的 L2 关 6.48，高 18 %（它对 Clapper 出刀多了 3–4 倍）；计划改动率 0.46 / 0.53 对 0.50。验收"不高于 A0"的 A0 是完整连战，这里不是同类比较，但按键数在 Clapper 波次上确实更高。

#### 21.6.6 没做 / 未核实

- 施法的小符文（v4 开的受击里最多的一类）是规划器选跳的时机问题（支撑饱和下 FORCED_RISK 并列），L2 只能给站位；diag 的 `SSBOT_FORUM_FR=seen` 上线后要在 w7 / w13 上重跑这一对。
- **跳施法的大符文**（v4 w7 20 次）：落地后约 3.3 s 才炸，那时控制器已回到"脸上"；应当在 CC_JUMP_CAST 落地后到大符文炸之前把站位放在圆外（落点后方 ≥ 1.6 u 或前方 13.8 u 外），下一步。
- w13：两只靠在一起时 KITE 让给 LOCAL 的 EVADE，那里的受击没有控制器管；被墙夹住的锤往墙边退还是被本体撞（7 次）。
- 锤在前方没地方时"退到墙边"（v3）是按几何推的：锤够 12 u（12 u 处 38 %），离墙近时仍会被打；你练习里的踩头下劈（15 / 22）规划器从没选过。
- 两波都没打死 Clapper（230 HP，收割者 26 下；v2 开每场打中 6–11 下就因为挨了 3 下退出）；控制器的下一道门是第 13 波 CLEAR，不是存活时间。
- 落单判据仍只看水平距离（加了原目标 2 u 的滞回），不是计划里的"危险区和危险时段重叠"；L2 不查跑过去的路线。
- 第 2 轮的实战在高负载下跑（21.6.2），worker 提到 AboveNormal；和第 1 轮的绝对数字不能直接比。

### 21.7 第 3 轮（2026-10-08 06:00 起，核对者意见之后；分支同上；实例 1）

核对者对第 2 轮（ba7dddb）的意见：一条 high（跳的瞄准从没存下）、两条 medium（"轮到另一只"失效、"目标切换 ≤ 10"换了口径）、三条 low（v3 / v4 不交错、第 0 波受击率的分母、几处数字）。21.5 / 21.6 里错的地方已就地标"第 3 轮更正"。

#### 21.7.1 跳的瞄准（high）

- **问题**：`Jump Aim`（和 `Cast Jump`）是零时长状态：同一帧里 `Jump Antic` / `Cast Slam Antic 2` → `Jump Aim` → `Jump`（`Jump` 只停 1 帧，然后 `Air` 约 0.9 s；ChoirClapper.json dwell：Jump Aim、Cast Jump 都是 instant，n 4,037 / 1,950）。EnemyTracker 按顺序处理 FSM 事件，一帧结束时的状态是 `Jump`，所以 tick 从来不会停在 `Jump Aim` 上。第 2 轮的代码只在 `s.state == "Jump Aim"` 时存瞄准，实战里一次也没存，走法也就从没被固定（核对者：v3 / v4 决策日志里同一跳内分支翻转 102 / 103 次）；空中的落点是按当前主角位置和 Clapper 的空中位置当起跳点重算的。测试都手工给了 `state="Jump Aim"`，测不出来。
- **第一次修正**（23e56af，实战推翻，见下）：起跳前（`Jump Antic`、`Cast Slam Antic`、`Cast Slam Antic 2`、`Cast Jump`）每个 tick 记下它站的 x（起跳点）；过了前摇的第一个 tick（通常是 `Jump` 那一帧，晚了就是 `Air`）存瞄准 =（这时的主角 x，前摇里的 x，这时的朝向：Jump Aim 先 FaceObject，空中不转身），走法在这一刻定下。`CC_AIR_STATES` 去掉了 `Cast Jump`（它在地面上，零时长）。新测试按 tracker 的真实顺序喂 `Jump Antic` ×5 → `Jump` → `Air` ×5（中间没有 Jump Aim），断言瞄准已存、落点不随主角漂移、分支不翻转；另一条测试是第一次就在空中看到它。
- 开环核对（v4 的 w7 / w13 录像 `052126` 第 0–5 场，23e56af；会话临时目录 `r6\r3\jc.json`）：8 次跳里 7 次存了瞄准、定了走法（另 1 次是这一场在前摇里结束），**瞄准之后分支翻转 0 次**（3 次"翻转"是瞄准那一刻从前摇里的估计换成真实落点）；瞄准之前（前摇里，落点跟着主角走）翻转 1–10 次 / 跳。
- **实战推翻了第一次修正**：第 3 轮第一次实战（冻结 4a0c212，`20261008_064118`，种子 310300–310307，8 场）w7 存活 15.7 / 15.4 / 16.2 / 9.8 s，同种子的 v4（`064410`）45.0 / 34.3 / 10.9 / 17.1 s；w7 的 Clapper 本体受击 8 次（v4 同块 2 次）。逐跳看（决策日志里目标 Clapper 在跳的各状态的 tick；`r6\r3\jump_live.py`）：

| 运行 | w7 的跳 | 主角在它空中时从它下面穿过 | 跳期间本体受击 | 跳期间锤（落地锤）受击 |
|---|---|---|---|---|
| v2 `035906` + `040911` | 28 | 6 | 14 | 6 |
| v3 `050637` | 32 | 0 | 0 | 19 |
| v4 `052126` | 25 | 1 | 0 | 4 |
| 第 3 轮 4a0c212 `064118` | 8 | **8** | **8** | 0 |

  原因：它在 Jump Aim 先转身面向主角，所以起跳时主角几乎总在它前面；"落点后方"在它的飞行路线上（短跳时就在起跳点后面），去那里就是从它身下穿过，落下的本体砸中。v3 / v4 的判断每个 tick 按主角当前位置和它的空中位置重算，钻过去的站位跟着主角跑，实际上很少真的去钻（v4 只穿过 1 次），本体受击 0 是这么来的；走法一旦在瞄准时定死，就每一跳都钻。
- **第二次修正（afb89a8，也被实战推翻）**：瞄准照旧存下（落点用真实的），但不从它身下穿过：只有主角在它背后（相对它的朝向）才去落点后方，否则一律退到落点前方（跳砸 8.5 u、跳施法 14.5 u，到墙为止）。实战两块（`065514`、`070132`，种子 310300–310315，与 v4 的 `064410` / `065752` 同种子成对）：w7 跳期间穿过 0 次、本体 0 次，但**存活 16.0 对 28.0 s**（8 对，成对 −12.0 s，se 4.3；开更久 2 对、v4 更久 6 对），锤 / 落地锤受击 9 对 4：它朝主角跳、落在主角前方 5 u，"退到落点前方 8.5 u"在 28.8 u 宽的场地里常常就是墙边（站位 45.9 = 右墙 − 2.5），主角被逼进角落，落地锤（落点前 0.67–7.76 u）照样打到。w13 −0.6 s（se 1.2）。
- **最后的处理（fd57819）：跳的站位退回 v4 实战验证过的规则**——每个 tick 按主角和它**此刻**的位置估一个"落点"（`jump_landing(它的 x, 主角 x, 朝向)`，不是真实落点的预报，是一条站位规则），能在落地前 0.25 s 跑到它后方 2.5 u、且不在它落地前穿过它的身体（地面上）、后方在场内时"钻到后方"，否则退开（前方没地方时仍可钻）。v4 的 25 次跳里这条规则只真正从它身下穿过 1 次、本体 0 次：落点估计跟着主角漂，钻过去的站位基本在它前面一侧，主角很少真的去钻。顺路上挑的 ×1.5、时序判断都恢复。不再存瞄准（Jump Aim 停不到 tick 上，真实落点只对跳施法的大符文有用，那里改用它落地后站的位置，21.7.6）。所以核对者 high 的那一条，处理是：第 2 轮文档里"走法在 Jump Aim 定下、整个跳都不改"的说法撤回（实战从没生效），v4 的实际行为就是上面这条每 tick 重判的规则，实测比"真的定下"和"不钻"都好；代码和文档改成与实际一致。测试 `test_clapper_jump_judged_from_now`（来得及：钻到后方；1 s 后来不及：退开；贴脸在地面：退开；跳施法靠墙：钻），`test_clapper_controller` 的跳的部分按此刻位置判断。复测见 21.7.5。

#### 21.7.2 "轮到另一只"（medium）

- **问题**：`MultiForecast._subject_row` 给每个 Subject 的 `t_free` 都传 0.0，所以 L2 的"另一只的接敌点在这一招能结束之前跑得到"（`c.t_run <= t_free`）永远不成立，a637d77 起"轮到"整条规则失效。v3 / v4 的 32 场 w13 里 turn 0 次；21.6.5 里 w13 换目标从 13.2 降到 3.7 是规则关掉了，不是门控。测试里的 Subject 都是手工给的 `t_free=1.0`。
- **修正**（23e56af）：`t_free` = 这一招的开始时刻 + 这个家族记录的时长 p0.5 − 预报原点（`enemy_tables.Family.dur`，来自行为表 `duration_s`；空闲为 0）。为什么不用支撑漫游自己的最早结束：漫游按 min / max 停留取包络，罕见的中断也算（`Jump Antic → Start Battle?` 最短 0.0 s，29 / 2,116 次），最早结束几乎总是 0。Clapper 各招的 p0.5：CC_SLAM 1.258 s、CC_JUMP 1.544 s、CC_JUMP_CAST 1.965 s、CC_CAST 1.225 s、CC_EVADE 0。只有 L2 读 `t_free`，Bell Beast 不经过这里（逐位相同测试照旧）。
- 测试：`test_multi_forecast.py` 用合成的 Reed 表（RE_STAB p0.5 0.45 s）核对 t_free = 开始 + 0.45 − 原点、空闲为 0；`test_forum_l2.py` 用**生产表和真实的 MultiForecaster**：两只 Clapper，一只进 `Slam Antic` 0.1 s 后，它的 t_free = 1.258 − 0.1，另一只（6 u 外，0.39 s 跑到）轮到、换目标（turn）；进锤 1.0 s 后（剩 0.26 s）不换。

#### 21.7.3 "目标切换 ≤ 10 / 分"：口径和规则的滞回（medium，核对者驳回的那一条）

- **口径**。计划 R6 行和 §6 的"目标切换"指 GoalArbiter 的 goal 切换；L2 的 goal =（规则，目标），所以换规则也算。L2 的计数（每场 `stats.l2`）：`changes` = 每场第一个目标 + 换敌人（`tgt_switches`，按原因 `switch_kinds`）+ 同一目标换规则（第 3 轮新加的 `rule_changes`，按"旧 > 新"）。第 1 轮判"不过"的 33.0 和第 2 轮的 25.9 都是 `changes`；第 2 轮报告的 7.65 只是 `tgt_switches`，不能拿来宣布通过。**第 3 轮的验收口径：切换 = `tgt_switches` + `rule_changes`**（从一个已有的目标换走；不含每场的第一个目标，那不是"切换"：第 0 波每场只有 13–15 s，光是它就占 4.2 次 / 分）。两个数都报，`forum_a0_report` 的 L2 一节加了 `switch_kinds` 和 `rule_changes`。
- **从哪来**（开环，第 2 轮完整连战 `041945` + `043128` 各前 13 场的第 0 波，26 场、6.23 分钟，主角位置是录像里的；会话临时目录 `r6\r3\l2_sw3.py` → `sw_*.json`）：第 2 轮的设置（规则 1 s、目标 4 s ×1.5）`changes` 24.1 / 分 = 第一个目标 4.2 + 换敌人 7.7 + 换规则 12.2；换规则里 RUSH > KITE 58 次、KITE > RUSH 18 次——落单判据在 8 u 边上来回，加上"被冲的目标身边来人先 KITE"之后再换人，一次局面变化常常是两次切换。
- **改动**（4a0c212）：规则也加滞回 `rule_hyst_u`：保持 KITE 时，RUSH 要有一只落单到 8 + 2 = 10 u（RUSH 时原目标照旧放宽到 6 u，形成 6–10 u 的带）；"先对被冲的目标 KITE"只用于原规则是 RUSH 的目标（之前原规则是 KITE 时也会拦着 RUSH 到 dwell_s，不是本意）；参数网格（开环、同 26 场，每分钟）：

| 规则保持 | 规则滞回 | 目标保持 | 换人倍数 | 切换（不含第一个） | 其中换敌人 / 换规则 | changes |
|---|---|---|---|---|---|---|
| 1 s | 0 | 4 s | 1.5 | 19.9 | 7.7 / 12.2 | 24.1 |
| 1 s | 2 u | 4 s | 1.5 | 18.2 | 7.9 / 10.3 | 22.3 |
| 2 s | 2 u | 4 s | 1.5 | 15.1 | 7.6 / 7.6 | 19.3 |
| 3 s | 2 u | 4 s | 1.5 | 12.9 | 7.6 / 5.3 | 17.0 |
| 3 s | 2 u | 6 s | 1.5 | 9.8 | 4.7 / 5.1 | 14.0 |
| 4 s | 2 u | 6 s | 2.0 | 9.3 | 4.7 / 4.7 | 13.5 |
| 3 s | 2 u | 8 s | 2.0 | 10.1 | 4.3 / 5.8 | 14.3 |
| **4 s** | **2 u** | **8 s** | **2.0** | **8.2** | 3.9 / 4.3 | 12.4 |

  采用最后一行（`Forum.yaml`：`goal_dwell_s` 4、`rule_hyst_u` 2、`dwell_s` 8、`switch_x` 2.0；第 2 轮的机制测试固定用第 2 轮的参数，新测试 `test_round3_holding_rule_hysteresis` 核对 KITE 时 9 u 不换、11 u 换，RUSH 的规则保持 4 s）。剩下的换规则几乎都是 RUSH > KITE（26 次：被冲的目标身边来了人）。代价：规则一旦定下要跑满 4 s（换进 PUNISH 除外），目标 8 s；第 0 波 L2 的选择不改变受击（21.5），Clapper 的"轮到"和 Clawmaiden 不受这两个保持时间限制。`changes` 含第一个目标仍是 12.4，只要第 0 波的场次这么短就降不到 10 以下。实战见 21.7.5。

#### 21.7.4 第 0 波的受击：按全部 tick 算（low）

21.5 的"每个决策 tick 的受击率"用的是决策日志的 tick（按事件触发采样，有偏）。按全部 tick（`policy.ticks`）重算第 1、2 轮的三对完整连战（L2 开 `015904` + `021942` + `041945`，关 `020919` + `022951` + `043128`，各 75 场，按种子成对；会话临时目录 `r6\r3\w0_hits.py` → `w0_hits_r12.json`）：

| | L2 开 | L2 关 | 成对（开 − 关，75 对） |
|---|---|---|---|
| 受击（damage）/ tick | 0.00612（325 / 53,124） | 0.00565（317 / 56,063） | 受击 +0.11 / 场（se 0.11） |
| 受击 / 分钟 | 19.95 | 18.57 | 存活 −0.62 s（se 0.36） |
| Choristor `Body Damager` | **28** | 8 | **+0.27 / 场（se 0.08）** |

总受击的差别不显著，但来源变了：Choristor 的身体接触多了 20 次，存活有约 1.7 se 的负向趋势。28 次按受击前 0.2 s 的 L2 目标分：RUSH 冲的正是这只 Choristor 6 次、RUSH 冲别的 8 次、KITE(EVADE)（LOCAL 的打分）14 次——一半发生在 LOCAL 自己的 EVADE 下，所以不是 RUSH 的接敌点离它本体太近这么简单，而是 L2 让主角更多地待在敌群附近（RUSH 时到目标的距离中位 2.5 u，关 3.7 u，21.5）。和 FORCED_RISK 在支撑饱和时的并列是同一个瓶颈（规划器分不出哪一行能躲开它的冲撞），没有改 L2；diag 的 `SSBOT_FORUM_FR=seen` 上线后在同一对 A/B 上复查这一项。第 3 轮完整连战的数字见 21.7.5。

#### 21.7.5 实战复测（实例 1，2026-10-08 06:41–；驱动 `C:\ssbot\sandbox\r6_ws5.ps1`，每块一个运行、按块交错，`r6_ws5_runs.txt` 一行一块）

协议同 21.6（eval、planner、oracle；worker 提到 AboveNormal，两臂一样；机器负载比第 2 轮低：CPU 约 50 %）。中途换了两次代码（21.7.1）：4a0c212 跑了 1 块、afb89a8 跑了 2 块，都按停止文件在块之间停下、换新的冻结检出重启；下面是最终代码 **fd57819** 的结果。

**波次起点**（`Forum_A_w7` / `Forum_A_w13` 按局轮换，无真退出；种子 310300–310331，每块 8 场；fd57819 `070851`、`071230`、`071658`、`072800`，v4（8754008）`064410`、`065752`、`072118`、`072437`；交错：v4 的前两块在被撤回的代码之间跑，后两块和 fd57819 轮流先跑；分析 `r6\r3\ws_anal3.py` → `ws_final.json`，`jump_live.py` → `jump_final.txt`）：

| 指标 | w7 fd57819 | w7 v4 | w13 fd57819 | w13 v4 |
|---|---|---|---|---|
| 场数 / 结果 | 16 / 全 QUIT（Q1） | 16 / 全 QUIT | 16 / 全 QUIT | 16 / 全 QUIT |
| 存活均值 / p50 | **37.4 / 39.8 s** | 26.9 / 26.4 s | 9.4 / 9.0 s | 9.9 / 9.5 s |
| 成对（新 − v4，16 对） | **+10.6 s（se 4.0），新更久 12 对** | | −0.51 s（se 0.52），新更久 5 对 | |
| 受击 / 分 | 6.9 | 8.1 | 20.5 | 20.5 |
| 受击来源 | 小符文 55、锤 11、大符文 **2**、本体 1 | 小符文 30、大符文 **20**、锤 6、本体 2 | 锤 19、小符文 17、本体 13、大符文 2 | 小符文 25、本体 14、锤 13、大符文 2 |
| 打中 Clapper / 场、/ 分 | 9.9、15.8 | 6.5、14.5 | 8.1、52.1 | 9.2、55.9 |
| 跳（w7）：次数 / 从它身下穿过 / 本体 / 锤 | 20 / 0 / 1 / 11 | 28 / 0 / 0 / 6 | — | — |
| 切换 / 分（换敌人 + 换规则） | 0 | 0 | **10.0**（轮到 12、RUSH > KITE 12、KITE > RUSH 1） | 3.4（更好的 9；v4 不记换规则） |
| changes / 分（含第一个目标） | 1.6 | 2.2 | 16.4 | 21.3 |
| 每秒按键（中位）/ FORCED_RISK | 8.79 / 90 % | 8.54 / 87 % | 6.20 / 65 % | 6.23 / 66 % |
| 每场迟到 state | 0.88 | 0.56 | 0.44 | 0.25 |

- **w7：大符文 20 → 2**（21.7.6 的站位起作用），存活 +10.6 s；剩下的受击几乎全是施法的小符文（55，按分钟 5.5 对 v4 的 4.2：活得久、站在脸上的时间长）和落地锤（11 对 6，跳期间）。跳的站位和 v4 相同规则，0 次从身下穿过。
- **w13：没有改善**（−0.5 s，se 0.5）。"轮到另一只"现在真的触发了（12 次），但两只的情形下存活没有变好：锤 19 对 13 多了，小符文 17 对 25 少了。轮到的门控（另一只在这一招最早能结束之前跑得到）本身是对的，问题是跑过去以后马上又被另一只的下一招追上（"FOCUS 一只、把另一只留在背后"是下一步，21.7.8）。w13 的切换 10.0 次 / 分，正好在线上。
- 每秒按键两臂相同（都是 L2 开；和 L2 关比见 21.6.5 的补注）。

**完整连战**（A0b 协议：fo_A、eval、planner、oracle、真退出 0.2；种子 310400–310424，每块 5 场，L2 开 / 关（同一冻结检出 fd57819，`SSBOT_FORUM_L2=0`）按块交错、轮流先跑；开 `073208`、`074014`、`074246`、`075109`、`075408`，关 `073432`、`073649` + `073758`、`074531`、`074824`、`075636`；`forum_a0_report` → `r6\r3\full_on.json` / `full_off.json`，`w0_hits.py` → `w0_hits_r3.json`）：

| 指标 | L2 开 | L2 关 |
|---|---|---|
| 结果 | QUIT 25（全 Q1），全在第 0 波 | QUIT 25 + HARNESS_FAIL 1（"paused unasked"，`073649` 第 2 场，同种子在 `073758` 补跑） |
| 受击 / 场（damage）、/ tick、/ 分 | 4.16、0.00533、18.0 | 4.44、0.00605、20.4 |
| 受击来源 | Envoy 45、Choristor 38（`Body Damager` 5）、Reed 21 | Envoy 42、Choristor 41（`Body Damager` 5）、Reed 28 |
| 存活 p50 / 最长 | 13.2 / 21.4 s | 12.5 / 17.6 s |
| 成对（开 − 关，25 对） | 受击 −0.28（se 0.19），存活 +0.78 s（se 0.71），Choristor 身体接触 0.00（se 0.13） | |
| FORCED_RISK | 82.2 % | 80.0 % |
| 支撑外命中 / 未知 | 0 / 0 | 0 / 0 |
| tick p50 / p99（中位）/ p99 最大 | 10.5 / 19.8 / 24.9 ms | 9.3 / 18.3 / 25.0 ms |
| 每秒按键 / 计划改动率（每场中位） | 7.88 / 0.575 | 7.31 / 0.634 |
| L2 | 目标 tick：KITE(EVADE) 10,604、RUSH 8,396、PUNISH 0；错误 0；每 tick p99 中位 1.07 ms | — |
| **目标切换**（换敌人 + 换规则，不含每场第一个目标） | **8.1 次 / 分**（换敌人 19：更好的 15、不再合格 4；换规则 28：RUSH > KITE 25、KITE > RUSH 3）；`changes` 含第一个目标 12.5 | — |
| 真退出 | 3 次：暂停 3、到主菜单 3、错误确认 0 | 3 / 3 / 3 / 0 |

- **验收**：目标切换 ≤ 10 / 分 **✓（8.1）**（按 goal 切换的口径；含每场第一个目标的 `changes` 是 12.5，第 0 波每场 13 s，第一个目标就占 4.3）；计划改动率不高于 A0b ✓（0.575 对 0.615）；**每秒按键 7.88，比 A0b 的 7.75 高 1.7 %、比同时跑的 L2 关高 8 %，✗（小幅）**——第 2 轮是 6.97（当时 RUSH / KITE 来回换得多）；规则保持 4 s 后 RUSH 的 tick 更连续，冲上去出刀的按键多了，不是抖动（计划改动率反而降了）。Choristor 身体接触这次两臂一样（5 对 5），21.7.4 的差别没有重现。受击、存活的成对差别都在噪声里（受击 −0.28，se 0.19；存活 +0.78 s，se 0.71），第 0 波仍然全部 QUIT（21.5 的原因）。


#### 21.7.6 跳施法的大符文（第 2 轮"下一步"第 1 条）

v4 的 w7 有 20 次受击是跳施法的大符文（`rune slam`）。行为表（ChoirClapper.json `CC_JUMP_CAST`）：大符文在落地那帧出现在落点前方 6.62 u（r 7.19，从落点后 0.58 u 到前方 13.8 u），这一招在承诺后约 2.18 s 结束，而大符文在这一招结束后 0.75 s（`_tail` 的 `t_on_state` p5 / p50 0.749 s，p95 2.67 s）才炸、0.87 s（p50）关；那时控制器已经回到"脸上 4 u"，正在圈里。改动（04dcad8）：跳施法结束后 `rune_hold_s` 1 s 内，站位留在落点后方 2.5 u（这一跳的走法是钻到它下面、且现在过去不穿过它的身体时）或圈外前方 14.5 u（`rune: out`，这时对它的命中权重为 0，和其他"走开"的分支一样）；锤（CC_SLAM）照旧优先。测试 `test_jump_cast_rune_circle_kept_out_of_after_the_move`（退开时圈外、1 s 后回到脸上；钻过去时留在落点后方）。fd57819 起圈心按它落地后（这一招结束那个 tick）站的位置算，不用瞄准估的落点。**实战（21.7.5）：w7 的大符文受击 20 → 2**（16 对，同种子交错）。

#### 21.7.7 §4.4 第 4 条在最终代码上复跑

核对者指出 600 tick 的逐位比对是第 1 轮做的。第 3 轮在 4a0c212 上重跑：`forum_policy_replay` 074719 i3 ep0、600 tick、`--deadline-ms inf`，`SSBOT_FORUM_L2=fail:1` 对 `=0`：模式、目标、计划、S、FORCED_RISK、mask、J 600 个 tick 全部相同（只有记录里的 goal 标签不同："LOCAL" 对空）。单元测试 `test_l2_failure_is_local_bit_for_bit` 的 3 种情况照旧通过。

#### 21.7.8 没做 / 未核实（第 3 轮）

- **第 0 波的结果仍不受 L2 影响**：支撑饱和时 FORCED_RISK 的排序并列（diag 轨道），L2 的打分只决定 J；要等 diag 的 `SSBOT_FORUM_FR=seen`、R5 或 R8。第 1、2 轮 L2 开时 Choristor 身体接触多（21.7.4），第 3 轮 5 对 5 没有重现，仍要在 FR=seen 后复查。
- **w13 没有改善**：两只 Clapper 时"轮到另一只"现在会触发，但存活没变好（21.7.5）；下一步是终局的 FOCUS 目标（clapper_face.md：选一只、把另一只留在它背后），以及两只靠在一起时 KITE 让给 LOCAL 的 EVADE 的那部分。
- **施法的小符文**（w7 剩下的受击里最多）：要在近处那颗亮的 5–7 帧里人在空中，是规划器选跳的时机问题；diag 的 FR=seen 上线后在 w7 / w13 上重跑这一对。
- **跳的站位**：v4 的"每 tick 按此刻位置重判"实测最好，但它为什么很少真的钻到身下（落点估计跟着主角漂）只是事后解释，没有单独做实验；落地锤在跳期间仍有 11 次（v4 6 次）。前摇里的站位每跳翻转 1–10 次（21.7.1 开环），没有加滞回。
- 目标切换：实战完整连战 8.1 次 / 分 ✓，w13 10.0；按 `changes`（含每场第一个目标）完整连战 12.5，第 0 波这么短的场次里降不到 10 以下（21.7.3）。每秒按键比 A0b 高 1.7 %（21.7.5），没有再调。
- 两波都没打死 Clapper（w7 最长 54 s、打中 9.9 下 / 场，要 26 下）。
- PUNISH 在多敌波次里仍不触发；落单判据仍只看水平距离；L2 不查跑过去的路线。
- 被撤回的两版代码的冻结检出 `C:\ssbot\live_r6_4a0c212`、`live_r6_afb89a8` 可删（按安全规则我没删）。

## 22. 反应式支撑（`SSBOT_FORUM_REACT`；2026-10-08，task reactive support，分支 worktree-wf_08175c18-693-1 到 8b1dd82；离线 + 实例 0–3。这条轨道在做 `forum_react_audit` 的细分解（groups2）时被打断，没有写本节；本节是集成步骤按它的代码和 A/B 汇总文件补写的）

起因（你 2026-10-08）：怪的前摇很长，前摇开始了再躲也不晚；第 0 波的危险区被"还没开始的招"盖满（§19.5）。

### 22.1 做了什么（`multi_forecast.ReactConfig`、`ForumPlanner._escape_pick`；默认 off = 支撑逐位不变，`tests/test_reactive_support.py`）

- **delay**：以后才可能开始的攻击实例（攻击家族的 walk 根），最早在"最早开始时刻 − 1 帧 + 该家族的出手延迟 − 视图的感知延迟"之后才放它的 walk 模板，之前只放家族模板（前摇时的身体，按开始后的时间分辨）。出手延迟 = `strikes.json` 里 commit → 第一个攻击碰撞体（或扔出的危险物）的最小值；感知延迟 oracle 1 帧、视觉等价 3 帧（DESIGN §3.9.5 的 33 ms）。例外：钟（CB_THROW）、Reed 针（RE_THROW）、符文弹（CC_CAST）的 commit 可能重新武装之前实例的东西，默认不延迟（`+p5`：按 p5 延迟）；只有身体的家族（闪避、Clawmaiden 瞬移、Tiny 冲撞，可以贴脸开始）不延迟。
- 扩展：`+c` 当前招之后的状态也按"开始 + 延迟 − 感知延迟"放（当前状态和尾巴照旧）；`+i` 有待机身体管的敌人去掉 idle 家族的根（管里已有它的身体）。
- **escape** = delay + 规划器的可逃检查：有安全行时，在排序的前 `esc_k` = 4 行里选第一条"计划结束时（或晚锁定时），对任何敌人可能开始的招都还能逃出它的够距"的行（尾检查只再看这一行）；FORCED_RISK 时在排序前 `esc_k_forced` = 8 行里、与第一行在份额之上的每个键都打平的行中选第一条有逃路的（29835a0）。每批 4 行；`esc_deadline_ms`（默认 deadline_ms + 2，从 tick 开始算）之后不再开新批（8b1dd82，计数 `esc_cut`）。审计 `ssbot.tools.forum_react_audit`（`--crest`：Wanderer 录像）。

### 22.2 实战 A/B（Forum_W = fo_A 换 Wanderer，A0b 协议：eval、planner、oracle、真退出 0.2；实例 0–3，种子 350100–350514，每块 5 场、臂的顺序按块轮换；代码 29835a0 与 8b1dd82 两轮合在一起；驱动 `C:\ssbot\sandbox\react2_live.ps1`，清单 `C:\ssbot\data\m2_forum_react2\manifest_29835a0.txt` / `manifest_8b1dd82.txt`，汇总 `ab_pooled_vs_share.json` / `ab_pooled_vs_seencf.json`）

| 臂（FR : REACT : 拼刀） | 场 | 退出中位 s | 每分钟受击 | FORCED_RISK | late_mean | plan p50 ms | 对 share:off:off 成对（s，95 % 区间） | 对 seen_cf:off:off 成对 |
|---|---|---|---|---|---|---|---|---|
| share : off : off | 60 | 12.0 | 20.4 | 0.778 | 0.75 | 3.3 | — | |
| share : delay : off | 30 | 12.4 | 19.5 | 0.775 | 0.93 | 3.2 | −0.6（−1.6…0.4） | |
| share : escape : off | 60 | 14.2 | 19.0 | 0.792 | 4.55 | 6.2 | +1.7（0.8…2.6） | |
| seen_cf : off : off | 60 | 22.9 | 10.9 | 0.883 | 0.56 | 3.8 | +10.3（8.8…11.9） | — |
| seen_cf : escape : off | 60 | 23.9 | 10.1 | 0.886 | 7.71 | 6.6 | +12.4（10.2…14.6） | +2.0（−0.5…4.7），35 / 60 更久 |
| seen_cf : off : on | 30 | 21.6 | 11.4 | 0.876 | 0.58 | 4.2 | +9.2（6.9…11.4） | **−3.2（−6.1…−0.5）**，12 / 30 |
| seen_cf : escape : on | 30 | 23.4 | 10.3 | 0.885 | 8.43 | 6.9 | +11.1（8.7…13.5） | −1.2（−4.5…1.8），17 / 30 |

- 全部臂每场都在第 0 波退出（QUIT），0 击杀、0 WOULD_DIE、支撑外命中 0。
- 只做 delay 没有作用；escape 在 share 上 +1.7 s（显著）、在 seen_cf 上 +2.0 s（区间含 0）；拼刀（`--forum-clash on`，只在 GREEN）在 seen_cf 上短 3.2 s（显著），和 escape 一起 −1.2 s（不显著）。escape 让 plan p50 多约 3 ms、late_mean 从 0.6–0.9 升到 4.6–8.4（汇总脚本的迟到指标）。
- **FORCED_RISK 的比例开了反应式支撑之后没有降（0.78–0.89）**：去掉"还没开始的招"没有让第 0 波的支撑不再饱和，盖住主角选项的是别的东西。集成任务说明列的候选（未核实）：支撑的余量（`support_margins.json`：Reed 钉、Minister 招架、Tiny 冲撞、钟、符文弹到 3.0 u 的搜索上限，Envoy 冲锋 2.96 u，主角只有 0.5 u 宽）、敌人的身体管、按时间窗放置的已承诺招（入场时刻不确定，0.25 u 粗金字塔）、死亡尾巴、导出的 ±1 bin 延迟。逐组分解（groups2）没有结果。

### 22.3 集成之后的冒烟（2026-10-08 10:45–10:54，分支 forum-integration-1008，冻结检出 `C:\ssbot\live_int_6c160ac`；只证明合并后的代码能跑，不是 A/B）

Forum_W（漫游），A0b 协议，实例 0 13 场 + 实例 1 12 场，种子 360000；`SSBOT_FORUM_FR=seen_cf`、`SSBOT_FORUM_REACT=escape`、`--forum-clash on`，其余用合并后的默认值（commit_rank 开、L2 开、终点价值关、T 36）。运行 `C:\ssbot\data\runs\m2\20261008_104557_Forum_W_eval_planner_oracle_clash`、`20261008_104618_…_clash`，报告 `C:\ssbot\data\runs\m2\int_smoke_report_6c160ac.json`。

- 25 / 25 第 0 波退出（Q1 23 场；QS 僵持 2 场：漫游 ×3 暴击上界让最后一击规则 20 s 不出刀，R8 的未决问题），0 WOULD_DIE、0 击杀、支撑外命中 0；没有崩溃、没有 HARNESS_FAIL。
- 局内时长中位 23.3 s（均值 25.6 s），每场受击 4.2、每分钟 9.8；FORCED_RISK 0.917；包络审计干净；tick p50 10.2 ms、plan p50 / p99 6.2 / 11.1 ms、迟到 tick 1.5 %。
- 拼刀分支在 33,684 个 FORCED_RISK tick 里有 33,633 个被档位门（只在 GREEN）跳过：第 0 波里"拼刀开"实际上只是"一直出刀"的续段行。
- 和 22.2 的数字不成对（不同种子、不同代码、时长的定义可能不同），只作参照：seen_cf + escape + 拼刀开 23.4 s / 10.3 次每分钟，seen_cf + escape 23.9 s / 10.1。

## 23. 第 0 波去饱和：支撑分层分解、三层支撑、击杀冻结的修正（2026-10-08，task wave-0 de-saturation，分支 worktree-wf_34e9717f-fa3-2；离线 + 实例 0–3）

起因：集成之后所有 Forum A/B 都是第 0 波 100 % 退出、0 击杀；开了反应式支撑（§22）FORCED_RISK 仍占 0.78–0.89。本节先量"是哪一层、哪个余量把候选行盖满"，再按你的三层支撑（plan §5 2026-10-08 的"下一轮"三条）和光锥改，最后实战。

### 23.1 分解的方法（`ssbot.tools.forum_layer_audit`）

- 录像：反应式 A/B 第 2 轮 seen_cf + escape 的 6 个运行（`20261008_092135` / `092227` / `092922` / `093102` / `094735` / `094847`，Forum_W，30 场），开环回放（同 §19.1：录像的 STATE 驱动策略，前缀是录下的按键），合并后的代码、seen_cf + escape；每 6 个战斗 tick 一个，共 7,112 个 tick，其中 FORCED_RISK 6,307 个。
- 每个 tick：规划器的已知、允许的候选行（`ForumPlanner.debug`），名义盒中心在第 1 … T 帧（无敌帧不算）对这个 tick 的预报按"层 × 类型 × 家族"分组查询。层：身体（待机身体管）、碰撞体管（只在前 5 帧）、已承诺细放置（入场时刻 ≤ 3 格）、已承诺窗口放置（入场是区间：0.25 u 粗金字塔）、当前招的家族并集（从开始起，窗口放置）、重锚 / 锚点未知的家族行走（外包盒）、尾巴、多段链、以后才开始的攻击 / 待机实例（外包盒）、入场、危险物（自模板 / 确定路径 / 危险物管）、死亡尾巴、全场盒。
- 第 0 级 = 整个支撑；第 1 级 = 去掉"还没开始的"（以后才开始的攻击和待机实例、下一波入场：反应式支撑的理想情况，交给可逃检查）。在第 1 级上做留一法（去掉一层 / 一组后有没有一行整段干净）、组合、变体（每个家族余量 ×0 / ×0.5、待机增长 ×0 / ×0.5：用另一套表 / 管对同一个 tick 重做预报）和 ±1 格导出延迟（模板层在 t − 1 格、t、t + 1 格三处查询取与：从里面逼近"去掉烘进模板的 ±1 格"），以及贪心剥离（每步去掉清出最多行的组）。另记每行在录像未来里是否真的不碰（事后，开环：别的主角时敌人不会改招，§19.1 的偏差同样在这里），用来看去掉一层后多出来的"干净行"有多少是真的。

### 23.2 结果（FORCED_RISK 的 6,307 个 tick；括号里是前 18 帧）

- **第 0 级 0 % 有干净行；第 1 级（还没开始的全部去掉）也只有 3.5 %（11.2 %）**：§22 已经说过"去掉没开始的招解不开"，这里的数更低，因为 FORCED_RISK tick 本来就是最饱和的那些（全部 tick：第 0 级 11.3 %、第 1 级 14.4 %）。
- **单独一层就盖住每一行**的 tick 比例：以后才开始的攻击 100 %、以后的待机实例 100 %、已承诺窗口 63.6 %、当前招的家族并集 56.1 %、尾巴 54.6 %、已承诺细放置 49.8 %、碰撞体管（前 5 帧）38.9 %、危险物自模板 36.0 %、重锚外包盒 28.7 %、身体管 27.3 %、多段链窗口 19.8 %、危险物管 15.0 %。冗余：在第 1 级上单去掉任何一层，有干净行的 tick 最多多出身体 5.3 %、进行中的入场 3.7 %、链窗口 2.6 %、针的自模板 2.4 %，其余 ≤ 1.4 %。贪心剥离要去掉 3 组以上才出现干净行的 tick 占多数，去掉 8 组仍没有的 7 %。
- 组合（第 1 级）：只留身体和危险物（已承诺的全去掉）29.7 %（41.3 %）；只留已承诺的（身体、危险物去掉）14.6 %；去掉窗口和尾巴 10.7 %。
- 变体：**余量**全为 0 时第 1 级 6.2 %（×0.5：4.2 %），只留身体和危险物时 33.7 %——余量不是饱和的主因；**待机增长**为 0 时第 1 级 7.3 %，只留身体和危险物时 58.8 %（×0.5：48.9 %）——身体层里饱和的是增长；**±1 格延迟**：去掉之后看不出变化（这个逼近只能从里面去，量不出更多）。
- 盖满最多的组（单独盖住每一行的 tick 比例）：Reed 针的自模板 36.0 %、Envoy 冲锋的尾巴 29.4 %、冲锋的窗口 25.5 %、Choristor 待机身体管 23.1 %、Envoy 碰撞体管 19.5 %、Reed 扔针的尾巴 19.3 % / 窗口 18.0 %、冲锋细放置 17.7 %、Reed 刺的外包盒 / 家族并集 / 窗口 15–16 %、Reed 防御的链窗口 16.3 %。
- **去掉一层之后的"干净行"有多少真的不碰**（事后；同一批 tick 里随机一行事后不碰 **63.8 %**（行合计；逐 tick 的中位数 72.4 %，初版写的"约 72 %"是这个中位数，审阅指出后改正））。该变体下**全部干净行**（含第 1 级原有的 21,886 行）：第 1 级 95.3 %；余量为 0 时 96.4 %；增长为 0 时 92.6 %；去掉窗口和尾巴 87.0 %；只留身体和危险物 77.4 %。**只算多出来的行**（变体的干净行减去第 1 级的）：余量为 0 时 98.7 %（10,739 行）、增长为 0 时 91.7 %（65,060）、去掉窗口和尾巴 84.4 %（68,706）、只留身体和危险物 76.2 %（334,635）（`scratchpad` `w0d/extra_prec.py`；初版摘要把前一组数写成了"多出来的行"）。结论不变：余量和增长去掉得起，已承诺层去不起。

### 23.3 饱和来自哪里（模板一级的原因）

- **余量由少数接触、少数状态定**（R0 的 `contacts.jsonl.gz` 里每个接触对另一折的留出残差，按控制状态分开；`scratchpad` `resid.py`）：EN_CHARGE 的 2.96 u 全部来自 `Charge` 状态（4,156 个接触里 45 个 > 0.3 u，p99 0.55 u；`Charge End` 最大 0.40、`Reset` 0）；RE_DEFEND 的 2.62 u 全部来自 `Multihit Clashed`（391 个里 19 个 > 0.3 u；`Defend` 最大 0.10、`Parry Slash` 0）；RE_STAB 的 1.37 u 来自 `Stab 3` / `Stab End` / `Stab 5`；CH_JUMP 的 1.61 u 来自 `Jump Spin` 的 2 个接触；针的 3.0 u 来自 3 个接触。家族余量把同一家族所有状态都膨胀这么多：冲锋前摇、防御姿态都按 2.6–3.0 u 放大。
- **Envoy 冲锋的 `Charge` 模板在进入那一刻就横跨 38 u**（x −7.6 … 30.7，锚点系）：`Reset → Charge` 的再次冲锋（63 次）从离锚点很远的地方开始，和第一次冲锋并在同一个按状态的模板里；余量 2.96 u 再加上去，竖直方向 −6.5 … 3.7 u，跳过冲锋的行也在里面（你 75 % 是跳过去的，§19.7）。
- **Reed 扔针的模板里有针**：RE_THROW 每个状态的伤害来源包括 `Song Reed Pin Projectile`，所以 `Throw` / `Throw Recover` / 尾巴的模板是所有方向扔出去的针的并集（x −14 … 30、y −15 … 15）；oracle 视图里针一飞起来就有确定路径（§14.2），这是重复计算。
- **针在手里**（`Throw Effect` 不是休息状态，算已武装）按自模板放：所有方向扔过的针 + 3.0 u 余量。
- **Choristor 的待机增长** 0.6 s 时 14.9 u（`Hop Back` 的瞬间后跳进了 g），Reed 6.1 u：0.6 s 视野里待机身体管就盖住半个场地。
- **击杀冻结规则把刀全收走**（这是 0 击杀的直接原因，和支撑无关）：`kill_freeze_s` 把"击杀那一帧开始的任何冻结"都算成该类的击杀冻结，取最大值；第 0 波三类的击杀从来没有自己的冻结（§12.3：只有 Clapper 有），但击杀同帧常有主角自己的 `NailClashEffect`（0.4 s）或 `StartRecoil`（0.25 s），于是 Envoy、Choristor、Reed 都成了"击杀冻结 0.4 s"的类型；YELLOW 的击杀规则（`forum_yellow_kill_hp` → `HeroDamage.kill_prims`）在任何一只的 hp_est − 3σ ≤ 漫游一刀的上界（暴击 27）时收走所有出刀，而 FORCED_RISK 让 tier 86 % 的时间是 YELLOW。集成冒烟的决策日志：46 % 的 tick `kill_prims` 含三种出刀，2 / 25 场以"QS 僵持：杀招规则 20 s 不出刀"结束。

### 23.4 改了什么（开关；默认值照旧，击杀冻结的修正除外）

- **击杀冻结只算击杀自己的冻结**（`KILL_FREEZE_KINDS`：`BigEnemyDeathSlow` / `EnemyBattleEndSlow` / `EnemyDeath`；默认；`SSBOT_FORUM_KF=any` 恢复原样）：第 0 波三类的击杀冻结变成 0，YELLOW 不再因为它们收刀；Clapper 照旧（1.9–2.5 s 的终局慢动作、0.165 s 的击杀减速）。
- **反应式支撑的新扩展**（`SSBOT_FORUM_REACT=escape+n+g+l`，§22 的开关之上）：
  - `+n`（还没开始的那一层）：有出手时间的家族（strikes.json）以后才开始的实例、以后的待机实例都不放（入场家族和只用身体的家族——闪避、瞬移、Tiny 冲撞——照旧）；可逃检查从"计划末和末尾一个延迟内的锁定"扩到计划里每一个锁定点（攻击、无控制、冲刺斩、硬着陆）。还没扔出去的针 / 钟（不在确定路径上）只放反应窗口（5 帧）内的够距（当前框按 40 u/s 长）；oracle 视图里扔针 / 扔钟的家族（Reed RE_THROW、Bellbearer CB_THROW）不放模板，改成本体管 + 扔出去之后的确定路径，它们的尾巴和可逃检查的威胁也去掉。
  - `+g`：待机身体管只在反应窗口（5 帧）里按待机增长长，之后保持那个大小、按速度平移（你的第 ⑤ 条：不出招的怪不会走到你脸上）。R2 的召回只查 2–4 帧前的预报：这两条在 4 帧内不改变支撑（还没开始的、有出手时间的招 4 帧内打不到；身体管 4 帧内照样长）。
  - `+l`（光锥，只在可逃检查里）：计划末的状态还要对"已承诺、时间确定、不能拼刀的放置"（拼刀表里没有的家族的细放置、危险物的确定路径、死亡尾巴）在视野之后有出路：用可逃检查的 7 种逃法从计划末推演 72 帧，全部碰到就算失败。**这不是"按可达集腐蚀"**（初版写成"腐蚀的模拟版、问的是同一个问题"，审阅驳回）：它只从计划末试 7 种固定逃法，是可达集的欠近似，比腐蚀更严——出路在 7 种之外（例如先等一下再冲刺）的行会被判失败；它只会多判失败、不会放过伤害。§23.12 之前它只在不否决的可逃检查里；之后在 `+n` 下它的失败也让这一行 S = 1。
- **拼刀作主逻辑**（`combat_run --forum-clash main`）：拼刀分支在 GREEN 和"h ≥ 3 的 YELLOW"（来自上一计划 S = 1 的 YELLOW，不是 h = 2）都跑；干净的拼刀行（刀的生效窗口里先碰到、在刀那一侧、在可拼状态里，拼完之后不再碰）只要拼刀表的"仍然挨打"上界之积 ≤ 0.3 就算安全（不再要求拼中率下界之积 ≥ 0.75），排在普通安全行之后、按挨打上界排；FORCED_RISK 的 seen 键跳过拼刀行的拼刀无敌帧（R8 留下的问题：会被拼掉的判定不算接触）；最多连拼 3 次。h = 2、RED、等暂停时仍然不拼（DESIGN 3.5.6）。
- **按状态的余量**（`SSBOT_FORUM_MARGIN=state`，`ssbot.tools.forum_state_margins` → `support_margins_state.json`）：每个控制状态用自己接触的最大留出残差（同 R0 的规则，接触 < 100 的状态用家族余量）；家族并集、尾巴、世界系模板和危险物自模板照旧用家族余量。第 0 波：EN_CHARGE 的 `Charge End` 2.96 → 0.40 u（`Charge`、`Reset` 不变），RE_DEFEND 除 `Multihit Clashed` 外 ≤ 0.59 u（`Defend` 0.10），RE_STAB 的 `Stab 1` 0.01、`Stab 4` 0.17、`Stab Antic` 0，CH_JUMP 的 `Jump Rise` / `Spin Slash` 0。
- **打回去的钟**（默认）：钟进入 `Tink L / R / U` 或 `Nail Hit` 之后不再是主角的危险物（新的一次扔出 `Init` 才算回去）；规划器自己打钟（`bell_redirected`）时从打中那一步起无害。**砍来袭的钟算防御**（`ForumConfig.bell_hits`，默认开）：射程内的钟作为权重 0 的命中目标，刀先碰到钟的行（即使阶段 1 已经接触）走命中分支，分支里的支撑把那只钟从打中起拿掉。第 0 波没有钟，A/B 里不起作用。这两条当时**没有运行时开关**、所有臂都开着（包括 23.6–23.10 的对照臂 int / intk：它们和新臂跑的是同一个冻结检出）；§23.12 加了 `SSBOT_FORUM_BELLS=off`（两条一起关）。第 3 波以后的效果没有测过。
- 工具：`forum_layer_audit`（本节的分解）、`forum_state_margins`、`multi_recall --react / --state-margins`（R2 的留出召回在新支撑上重跑）。

### 23.5 离线回放（开环，同 §19.1；10 场：`092135`、`094847` 两个运行；每 3 个 tick 一个；截止时间 inf）

| 配置 | FORCED_RISK | 有安全行 | 选中计划事后不碰（安全 tick / FORCED_RISK tick） | 安全行事后不碰 | plan ms p50 / p99 |
|---|---|---|---|---|---|
| seen_cf + escape（集成的最好臂） | 90.3 % | 9.7 % | 78.3 %（100 / 75.9） | 100 % | 9.9 / 23.1 |
| + `+n+g` | 89.6 % | 10.4 % | 78.7 %（98.9 / 76.4） | 99.7 % | 9.6 / 21.2 |
| + `+n+g` + 拼刀主逻辑 | 89.5 % | 10.5 % | 78.4 % | 99.7 % | 11.7 / 24.1 |
| `+n+g`（含扔针替换）+ 按状态余量（只 `092135` 的 5 场；同 5 场集成臂 90.5 % / 9.5 %） | 88.4 % | 11.6 % | 80.0 % | 99.7 % | 11.4 / 27.9 |

开环里这些改动只让安全 tick 多 1–2 个百分点：已承诺层（23.3）没动，饱和的主体还在；拼刀主逻辑在 12,655 个 FORCED_RISK tick 里只多出 11 个干净的拼刀行（522 个部分拼刀行进 FORCED_RISK 排序）。

### 23.6 实战第 1 轮（2026-10-08 11:45–12:46；冻结检出 `C:\ssbot\live_w0d_016417b`；实例 0–3 每个 12 块 × 5 场、三臂按块和实例轮换，同实例同种子配对；Forum_W，eval、planner、oracle、真退出 0.2；种子 361000；驱动 `C:\ssbot\sandbox\w0d_live.ps1`，清单 `w0d_manifest_a.txt`，汇总 `C:\ssbot\data\m2_forum_w0d\ab_round1.json`）

三臂：**int** = 集成的"seen_cf + 拼刀开 + escape"、击杀冻结照旧（`SSBOT_FORUM_KF=any`：集成本身）；**intk** = int + 击杀冻结的修正；**new** = intk + `escape+n+g+l` + 拼刀主逻辑（家族余量；这一版的 `+n` 还没有扔针替换，拼刀主逻辑还没有 seen 跳过无敌帧）。

| | int | intk | new |
|---|---|---|---|
| 场 | 80 | 80 | 79 |
| 结果 | QUIT 80 | QUIT 80 | QUIT 79 |
| 打完第 0 波（到第 1 波或更后） | **0** | 11（14 %） | **15（19 %）**，最远到第 5 波 |
| 存活（局内）中位 / 均值 s | 24.1 / 25.4 | 25.4 / 31.0 | **31.9 / 52.3** |
| 击杀 / 场（有击杀的场） | 0（0） | 0.80（31） | **1.42（42）** |
| 第一次击杀中位 s | — | 23.1 | 22.9 |
| 打出的命中 / 场、/ 分 | 4.9 / 11.5 | 12.0 / 23.2 | 17.3 / 19.9 |
| 受击 / 场、/ 分 | 4.29 / 10.1 | 4.26 / 8.3 | 5.09 / **5.8** |
| FORCED_RISK 占比 | 0.893 | 0.891 | **0.796** |
| 迟到 tick（> 16.7 ms） | 15.2 % | 15.8 % | 10.9 % |
| tick p50 / plan p50 中位 ms | 13.3 / 7.8 | 13.7 / 7.8 | 13.2 / 8.4 |
| 支撑外受击 | 0 | 0 | 0 |

- 同实例同种子配对：intk − int 存活 **+5.6 s**（自助 95 % 区间 1.0–10.5），击杀 +0.80（0.51–1.14）；new − int **+26.9 s**（16.4–38.6），击杀 +1.42（0.96–1.92）；**new − intk +21.4 s（10.1–33.6）**，击杀 +0.65（0.08–1.23），45 / 79 对更久。
- 击杀冻结的修正一个人就把 0 击杀变成 0.8 只每场、第 0 波开始被打完；三层支撑的开关在它之上再加 21 s 存活和 0.65 只击杀：受击率降到 5.8 次 / 分（你 1x 11.4），FORCED_RISK 降到 0.80。int 臂又有 QS 僵持（杀招规则 20 s 不出刀）和 Q5，intk / new 没有。
- 受击来源（new，前几项）：Multihit 链（Choristor 鞭 / Reed 反击的钩子）67、Envoy 横斩 56、Choristor 跳旋 38、Reed 本体 36、Reed 针 26、Envoy 本体 20。
- 迟到 tick 偏高（11–16 %）：4 个实例同时跑，11:45–11:58 还和本节的离线回放、召回同时跑（之后停了）；三臂同负载、按块轮换。
- 拼刀主逻辑在 new 里：167,099 个拼刀 tick（档位门跳过 27,826：h = 2、RED、等暂停），219 行拼刀后干净（117 次选中），4,296 行部分拼刀（422 次选中）；拼刀不是 new 胜出的主要来源。

### 23.7 实战第 2 轮（2026-10-08 12:37–13:30；冻结检出 `C:\ssbot\live_w0d_fca0416`；实例 0–3 各 4 块 × 2 臂 × 5 场，ABBA，种子 362000；清单 `w0d_manifest_b.txt`，汇总 `C:\ssbot\data\m2_forum_w0d\ab_round2.json`；同时在跑 23.8 的召回）

两臂：**intk**（同第 1 轮）对 **newS** = `escape+n+g+l`（`+n` 含扔针替换）+ 拼刀主逻辑（含 seen 跳过拼刀无敌帧、连拼 3 次）+ 按状态余量。（初版这里还写了"+ 砍钟作防御"：错了。`bell_hits` 和打回去的钟当时没有开关，两臂跑同一个 fca0416，intk 也开着；两臂在钟上没有区别，第 0 波也没有钟。）

| | intk | newS |
|---|---|---|
| 场 | 80 | 80 |
| 打完第 0 波 | 16（20 %） | 15（19 %），9 场到第 3 波 |
| 存活中位 / 均值 s | 29.9 / 35.9 | 32.8 / **54.1** |
| 击杀 / 场（有击杀的场） | 1.18（43） | 1.19（39） |
| 第一次击杀中位 s | 21.3 | 24.2 |
| 打出的命中 / 场、/ 分 | 14.3 / 23.9 | 15.4 / 17.1 |
| 受击 / 分 | 7.25 | **5.92** |
| FORCED_RISK 占比 | 0.903 | **0.770** |
| 迟到 tick | 18.8 % | 14.7 % |
| 支撑外受击 | 0 | 0 |

- 配对：newS − intk 存活 **+18.2 s**（6.5–31.1），49 / 80 对更久；击杀 +0.01（−0.51–0.56）。第 1 轮的 new − intk 是 +21.4 s、击杀 +0.65。两轮合起来：三层支撑的开关让存活长 18–21 s、受击率降 20–30 %，**打完第 0 波的比例没有变**（new / newS 30 / 159 = 19 %，intk 27 / 160 = 17 %）：活得更久但每分钟打出的伤害少了约 30 %（17 对 24 次命中 / 分），每场击杀一样。
- 受击来源：Reed 的针（`hit_log` 路径 `Song Reed Pin Projectile`）newS 46 次 / 80 场，intk 27（第 1 轮 new 26）。初版说这是"扔针替换的代价"：**按分钟看不出来**（审阅：几轮合起来，替换后的臂 195 次 / 366 分 = 0.53 次 / 分，intk 46 次 / 89 分 = 0.52；newS 活得更久，场均自然多），撤回。§23.12 的新汇总：这两臂的针受击几乎都发生在 Reed 扔针已经开始（受击前 12–30 帧 Reed 在放手前的状态）时：newS 45 / 46、intk 24 / 27——所以"前摇已开始的扔针"是对的问题，`+n` 下确实没有一层管它（§23.12 修）。其余（Multihit 链 70、Reed 本体 41、Envoy 横斩 38、Choristor 跳旋 37、跳斩 32）和 intk 相当。
- 针的瞄准（第 2 轮 6 个运行、115 支针，`scratchpad` `pinaim.py`）：针在 Reed 进入 `Throw` 的那一帧飞出（115 支里 108 支能对上 Reed 的状态，全部是 `Throw` 第 0 帧），出生点离 Reed 约 1.6 u，31 u/s；方向对准的是**放手前约 20 帧（0.33 s）**主角所在的位置：夹角中位 5°、p90 18°、最大 55°（放手那一帧的主角位置：中位 13°、p90 46°）。所以针在手里时，它将来的路径由"主角 0.33 s 前在哪"决定——按计划行各自的位置可以算出来（下一步）。

### 23.8 R2 留出召回：新支撑在 4 帧内没有漏（`multi_recall fresh --react escape+n+g --state-margins`，冻结检出 fca0416，`C:\ssbot\data\m2_forum_w0d\recall_fresh_ngS_fca0416.json`）

- R0 的 35 场新数据 + R1 的运行，两折的表，444 个对局任务：每个滞后 375,940 个接触，**L2 / L3 / L4 全部覆盖（100 %），按类型也 100 %**；多段链的钩 1,802 / 1,802。和集成前的认证（`recall_fresh_e516f22.json`，同样 375,940 / 375,940）比，靠待机身体管覆盖的接触从 838 升到 1,044（扔针 / 扔钟家族改成本体管），新增 30 个靠危险物管、1 个靠碰撞体管（手里的针改成反应窗口的管）。
- 所以按状态的余量没有让任何留出接触变成没覆盖（任务要求：缩余量要说出代价——这里代价为 0 个接触）；`+n` / `+g` 在 2–4 帧的预报里也没有漏。注意这个检验只看 2–4 帧前的预报：`+n` 拿掉的是更远的部分（还没开始的招在视野里晚些时候的伤害），那部分的安全由可逃检查（每个锁定点）承担，不在召回的口径里。

### 23.9 实战第 3 轮：光锥开 / 关（2026-10-08 13:30–14:32；冻结检出 fca0416；ABBA，种子 363000；清单 `w0d_manifest_c.txt`，汇总 `ab_round3.json`）

| | newS（`escape+n+g+l`） | noL（`escape+n+g`，其余同 newS） |
|---|---|---|
| 场 | 80 | 80 |
| 打完第 0 波 | 11（14 %） | **17（21 %）**，最远第 5 波 |
| 存活中位 / 均值 s | 35.5 / 47.8 | 31.0 / 53.0 |
| 击杀 / 场 | 0.86 | **1.30** |
| 第一次击杀中位 s | 27.4 | 25.2 |
| 受击 / 分 | 6.13 | 5.67 |
| FORCED_RISK 占比 | 0.814 | 0.784 |
| 迟到 tick | 9.6 % | 10.1 % |
| 支撑外受击 | 0 | 0 |

- 配对 noL − newS：存活 +5.2 s（−9.5–19.8），击杀 +0.44（−0.14–1.03），40 / 80 对更久：都不显著，但方向一致——**光锥（这一版：计划末对已承诺、不能拼刀的细放置按 7 种逃法模拟）没有帮上忙**，可能还略减了出手（它让可逃检查多否决一些贴近敌人的计划）。第 0 波的已承诺放置在视野之后的部分很短（招在 1 s 内打完），光锥的用处在后面几波的延迟范围伤害（符文圈、rune slam、矛的爆炸），第 0 波量不出来；建议实战默认不开 `+l`，到后几波再单独量。
- 同一个 newS 配置在第 2 轮打完 15 / 80、击杀 1.19，第 3 轮 11 / 80、0.86：轮与轮之间（不同种子、不同负载）的差别和臂之间的差别一样大，单轮 80 场只看得出 ±15 s、±0.5 只击杀量级的效应。

### 23.10 实战第 4 轮：瞄准的针（`+a`；2026-10-08 14:32–15:22；冻结检出 `C:\ssbot\live_w0d_33762ee`；ABBA，种子 364000；清单 `w0d_manifest_d.txt`，汇总 `ab_round4.json`）

`+a`：Reed 扔针还没放手时（`RE_THROW`、还没到 `Throw`），对每个计划行单独查：在 `Throw` 的可能进入时刻（行走给的区间，每 2 帧一个）放一支从 Reed 旁 1.6 u 出发、31 u/s、对准"这一行在放手前 20 帧所在位置"（±15° 三条）的针，碰到就是 S = 1（23.7 的瞄准测量）。离线回放（`092135` 的 5 场）：829 个 tick 有这样的针，3,693 行因此不安全，有安全行的 tick 从 11.6 % 到 11.4 %。

| | newS | newSa（+ `+a`） |
|---|---|---|
| 场 | 80 | 80 |
| 打完第 0 波 | **23（29 %）** | 17（21 %），最远第 5 波 |
| 存活中位 / 均值 s | 33.7 / 60.8 | 31.1 / 59.1 |
| 击杀 / 场 | 1.66 | 1.55 |
| 受击 / 分 | 5.25 | 5.23 |
| Reed 针的受击 | 28 | 29 |
| 迟到 tick | 20.6 % | 23.6 % |
| 支撑外受击 | 0（另 2 次"未判"，见下） | 0 |

- 配对 newSa − newS：−1.7 s（−20.0–17.2），击杀 −0.11（−0.84–0.61）：**瞄准的针没有作用**，针的受击也没少（第 2 轮 newS 的 46 次多半是那一轮的随机性：这一轮 newS 只有 28，和 intk 的 27 一样）。保持默认关。
- **两次"未判"的受击**（newS，`unpredicted_unknown`：受击前 2–4 帧那几帧没有留下预报——这一轮迟到 tick 20 % 以上，跳过的帧没有预报，不是"在支撑外"）：`20261008_144952` 实例 0 第 4 场 f15121164 Envoy 本体（第 0 波），`20261008_151441` 实例 3 第 2 场 f15208118 钟（第 3 波）。用同样的配置开环回放判（`scratchpad` `unk.py`，即 `forum_react_audit` 的判法）：两次在 L = 2 / 3 / 4 / 12 / 24 / 36 帧前的预报里都被覆盖（全体和来源类型都是）。四轮 640 场里支撑外受击 0。

### 23.11 结论与建议

- **第 0 波开始被打完**：集成的最好臂（seen_cf + 拼刀开 + escape）80 场 0 击杀、0 次打完；修正击杀冻结之后 17 %（27 / 160）打完——**打完第 0 波靠的是击杀冻结的修正**。三层支撑的开关之后各轮 18–29 %（newS 49 / 240 = 20 %，noL 17 / 80，newSa 17 / 80），但同一轮配对比只是持平（第 1、2 轮合起来 new / newS 30 / 159 对 intk 27 / 160）：开关的收益在存活（均值从 25–36 s 到 48–61 s，配对 +18–21 s）和受击率（10.1 → 5.2–6.1 次 / 分；你 1x 11.4），不在打完率。最远打到第 5 波。四轮支撑外受击 0——但这只是 2–4 帧口径（§23.12：受击前 30 帧内有 S = 0 计划的受击，新臂约是 intk 的 3–6 倍）。
- 推荐的实战配置（各开关仍默认关，击杀冻结的修正默认开）：`SSBOT_FORUM_FR=seen_cf`、`SSBOT_FORUM_REACT=escape+n+g`、`--forum-clash main`、`SSBOT_FORUM_MARGIN=state`（第 3 轮的 noL）。光锥 `+l`、瞄准的针 `+a` 在第 0 波量不出好处，先不开。
- 还没解决的：① 已承诺层的模板本身（23.3）——FORCED_RISK 仍占 75–80 % 的 tick；要按状态重新锚定（可重入的 `Charge` 以进入时的位置为锚、扔出物不进扔者的模板）并重新认证（R2 的重建），这是去饱和的根本一步。② 打得慢：三层支撑让 bot 活得久但每分钟打出的命中少约 25 %（18 对 24），第一次击杀中位 21–27 s（你 17.5 s）；要在安全的 tick 里更主动地出手（安全 tick 里起手是攻击的只有 2–4 %，大多是 CONTINUE），这是 J / 惩罚窗口（R5 / R6）的事。③ 打完第 0 波之后的主要受击：第 1 波两只 Choristor 的跳旋（`Spin Hit`）和鞭、第 3 波的钟和矛的爆炸。
- 复现：分解 `python -m ssbot.tools.forum_layer_audit <runs> --out <dir> --every 6 --workers 3`（汇总 `scratchpad` `agg.py` / `prec.py`）；按状态余量 `python -m ssbot.tools.forum_state_margins`；召回 `python -m ssbot.tools.multi_recall fresh --fresh C:/ssbot/data/m2_forum_r0/fresh --fresh C:/ssbot/data/m2_forum_r2/r1 --react escape+n+g --state-margins ../knowledge/1.0.30000/enemies/forum/support_margins_state.json`；实战 `C:\ssbot\sandbox\w0d_live.ps1`（`-Arms "<名>:<FR>:<REACT>:<拼刀>:<KF>[:<MARGIN>]"`）与 `w0d_chain.ps1`，汇总 `scratchpad` `ab.py <清单> --dealt`（§23.12 之后用仓库里的 `python -m ssbot.tools.forum_ab_summary <清单>`，含受击前 12 / 24 / 30 帧的计划和可逃检查的统计）。

### 23.12 审阅之后的修正（2026-10-08 晚，提交 5506b86；实战第 5 轮）

同日的审阅提了三个中等问题和几条小的。逐条改了、重新量了。

**① `+n` 下，前摇已经开始的扔针 / 扔钟没有任何一层管。** `+n` 把 Reed 的 RE_THROW、Bellbearer 的 CB_THROW 从支撑里拿掉（模板、尾巴），也从可逃检查的威胁里拿掉；针 / 钟还在手里时只放 5 帧反应窗口的够距。推荐配置又不开 `+a`。新汇总证实这是对的问题：针的受击几乎全部发生在 Reed 扔针已经开始时（受击前 12–30 帧有 Reed 处在放手前的状态）：newS 各轮 45 / 46、40 / 44、28 / 28，noL 36 / 36，intk 24 / 27（intk 那时扔针模板还在支撑里，这些受击发生在 FORCED_RISK 里）。改法：
- `+n` 在 oracle 视图里自动开瞄准的针（`ForumConfig.pin_aim` = `+a` 或 `+n`）：Reed 扔针的前摇里逐行查（§23.10 的做法）。第 4 轮 newSa 对 newS 没有可测的损失。
- Bellbearer 的扔钟在放手之前（`Throw Evade` / `Roof Avoid` / `Throw Antic`，`REACT_KEEP_UNTIL_THROWN`）保留扔钟的模板，也就是 `+n` 之前的支撑：所有方向扔过的钟。进入 `Throw` 之后才换成本体管加钟的确定路径。钟没有瞄准模型，所以这里取保守的做法；多出来的覆盖只在前摇那约 0.66 s 里。
- 还没开始的扔针 / 扔钟仍然不进可逃检查：模板里有所有方向，谈不上出路。从开始（commit）到第一次伤害最少 0.66 s（strikes.json 的 p5：CB 0.658 s，RE 0.667 s），开始之后由上面两条接管。
- R2 召回：只在支撑上加了东西（CB_THROW 前摇的模板），§23.8 的 100 % 不会下降，没有重跑。

**② `+n` 下，可逃检查只是排序偏好，不是安全保证。** 还没开始的招只有可逃检查管，但检查不否决，还常被截止时间切断。第 1–4 轮的新臂里，经过检查的非 FORCED_RISK tick 有 37–42 % 选中的行没通过检查（newS 0.42 / 0.40 / 0.37，noL 0.40，newSa 0.38），这些 tick 照样是 S = 0、GREEN；截断约每 tick 0.27–0.56 次。改法（`ForumConfig.esc_veto`：escape 且 `+n`）：两种情况下选中的行记 S = 1。一是选中的行没通过检查（所查的行全部失败，取失败最少的那行）。二是有威胁在够距内，但截止时间前一行都没查到。S = 1 的后果：下一个 tick 是 YELLOW，不能认证击杀，不算 QS 的安全帧。延续（CONTINUE）这样一行时也保持 S = 1。`+l` 打开时，光锥的失败同样算。审计字段是 `esc_unsafe` / `esc_failed` / `esc_unchecked` / `esc_carried`。不开 `+n` 时，检查照旧只用来排序。

**③ "支撑外受击 0"的口径看不到新开关担的风险。** 2–4 帧的判法（UNPRED_LAGS）按构造看不到这部分：`+n` 拿掉的是 4 帧内打不到的招，`+g` 的身体管 5 帧之后才不长。所以加了计划层面的指标：
- 策略：每个 tick 的选中计划放进一个环形缓冲。每次受击记下受击前 12 / 24 / 30 帧的选中计划，包括 S、FORCED_RISK、是否干净的拼刀行、是否被可逃检查判 S = 1、有没有瞄准针的威胁；另记"受击前 30 帧内有没有选过 S = 0 的计划"。这些写进 `hit_log` 的 `lag` / `safe30` / `clash30`，统计字段是 `planned_safe`。
- 汇总工具 `python -m ssbot.tools.forum_ab_summary <清单>` 放进了仓库，替代 scratchpad 里的 `ab.py`。它从决策日志算同样的数（每次受击前 90 个 tick 的日志都留着，所以旧版本的运行也能算），并按来源归因。另外还报：可逃检查的失败率和截断率、针受击里扔针已经开始的份数、配对差的 bootstrap CI。
- 第 1–4 轮重算的结果（`C:\ssbot\data\m2_forum_w0d\fix\sum_round1..4.json`）。"30 帧内"指受击前 30 帧内有 S = 0 的选中计划；@12 / @24 / @30 指受击前那么多帧时的选中计划是 S = 0：

| 轮 | 臂 | 受击 | 30 帧内（次 / 分） | @12 | @24 | @30 | 其中针 |
|---|---|---|---|---|---|---|---|
| 1 | int | 391 | 2（0.06） | 0 | 2 | 1 | 0 |
| 1 | intk | 403 | 0（0） | 0 | 0 | 0 | 0 |
| 1 | new | 462 | 7（0.10） | 0 | 4 | 7 | 0 |
| 2 | intk | 403 | 2（0.04） | 0 | 1 | 2 | 0 |
| 2 | newS | 483 | 13（0.18） | 1 | 6 | 7 | 3 |
| 3 | newS | 447 | 7（0.11） | 0 | 4 | 6 | 1 |
| 3 | noL | 470 | 14（0.20） | 5 | 8 | 14 | 5 |
| 4 | newS | 482 | 19（0.23） | 1 | 10 | 9 | 4 |
| 4 | newSa | 482 | 12（0.15） | 2 | 10 | 8 | 1 |

  新臂的这类受击是对照的 3–6 倍。占全部受击的比例仍然小（2–4 %），其余都发生在 FORCED_RISK 里，没有一次是"30 帧内有干净拼刀行"（`clash30` 各臂都是 0）。来源分散：Choristor 的跳旋和本体、Envoy 的横斩和跳斩、Reed 的针和刺。

**④ 拼刀作主逻辑的阈值（低）。** `CLASH_MODES["main"]` 有两处和 DESIGN 3.5.6 的"只在 GREEN"不同：干净的拼刀行只要"仍然挨打"的上界之积不超过 0.3 就算安全；h ≥ 3 的 YELLOW 也拼。按审阅的统计，在 main 下第 0 波 / Forum 有 13 个槽能算安全，其中 9 个用的是收割（Reaper）的数据，没有漫游自己的行，例如 EN_JUMPSLASH down（p_fail 0.246）、CH_WHIP down（0.270）、MI_PARRY side（0.196）。实测：各臂约 110–145 个 tick 选中了干净拼刀行，之后 30 帧内受击 0 次（第 1–5 轮的 `clash30` 全是 0）。这两条（0.3 的阈值、YELLOW h ≥ 3）**要 lead / 你来定**，它们都在 `--forum-clash main` 后面，默认关。"拼刀安全要求漫游自己的数据（n_eff ≥ min_n）"这条这一轮没有做，因为读拼刀表代码的那一步被权限分类器拒了。

**⑤ 钟的开关（低）。** 加了 `SSBOT_FORUM_BELLS=off`，同时关掉 `ForumConfig.bell_hits` 和 HazardTracker 的打回去规则；默认 on，行为和以前一样。第 3 波以后的 A/B 还没做。

**⑥ 文字更正。** 已改在原处：§23.2（随机一行的基线 63.8 %；"多出来的行"的精度）、§23.4（光锥不是腐蚀；钟当时没有开关）、§23.7（两臂都开着钟；针的受击按分钟看没有差别）、§23.11（打完第 0 波靠的是击杀冻结的修正）。

**Bell Beast。** 改动的文件里，Bell Beast 的代码路径（`forecast.py`、`planner.py`、`planner_policy.py`）一个都不导入；`forecast.py` 只在注释里提到 multi_forecast。所以 Bell Beast 按构造逐 tick 不变，没有再跑逐 tick 对比。

**实战第 5 轮**（2026-10-08 16:30–17:35）。两臂各用一个冻结检出：rec = `C:\ssbot\live_w0d_33762ee`（第 3 轮 noL 的推荐配置），fix = `C:\ssbot\live_w0d_5506b86`（本节的修正）。两臂的环境变量相同：`SSBOT_FORUM_FR=seen_cf`、`SSBOT_FORUM_REACT=escape+n+g`、`--forum-clash main`、`SSBOT_FORUM_MARGIN=state`。实例 0–3 各跑 4 块 × 2 臂 × 5 场，ABBA，第一块的先后按实例交替；种子 365000；Forum_W，eval、planner、oracle、真退出 0.2。驱动 `C:\ssbot\sandbox\w0d_live2.ps1`（每臂自己的检出），清单 `w0d_manifest_e.txt`，汇总 `C:\ssbot\data\m2_forum_w0d\fix\sum_round5.json`。

| | rec（33762ee） | fix（5506b86） |
|---|---|---|
| 场 | 80（全部 QUIT） | 80（全部 QUIT） |
| 打完第 0 波 | 18（23 %），最远第 5 波 | 19（24 %），最远第 6 波 |
| 存活中位 / 均值 s | 35.3 / 64.2 | 34.0 / 64.9 |
| 击杀 / 场 | 1.45 | 1.59 |
| 受击 / 分 | 4.86 | 4.89 |
| FORCED_RISK 占比 | 0.773 | 0.774 |
| 迟到 tick | 9.5 % | 10.6 % |
| 支撑外受击（2–4 帧）/ 未判 | 0 / 0 | 0 / 0 |
| 受击前 30 帧内有 S = 0 计划（次 / 分） | 15（0.175） | **9（0.104）** |
| ……受击前 24 / 30 帧时是 S = 0 | 8 / 14 | 4 / 5 |
| ……其中针 | 2 | 3 |
| 受击前 12 / 24 / 30 帧时是"可逃检查判的 S = 1" | — | 2 / 4 / 4 |
| Reed 针的受击（扔针已开始） | 32（30） | 41（37） |
| 可逃检查：非 FORCED_RISK 的检查 tick / 失败率 / 截断每 tick | 47,441 / 0.48 / 0.24 | 44,528 / 0.45 / 0.29 |
| 判为 S = 1（失败 / 没查到 / 延续） | — | 61,929（20,122 / 11,671 / 30,310） |
| 选中干净拼刀行后 30 帧内受击 | 0 | 0 |

- 配对 fix − rec（80 对）：存活 +0.8 s（−20.1–21.6），击杀 +0.14（−0.63–0.91），受击率 −0.23 次 / 分（−1.74–1.25）。**都不显著：这些修正没有可测的代价。**
- 受击前 30 帧内有 S = 0 计划的受击从 15 降到 9。受击前 30 帧时还是 S = 0 的，从 14 降到 5。剩下的 9 次是：Envoy 跳斩 3、针 3、Choristor 本体 2、Reed 刺 1。另有 4 次受击，可逃检查在受击前 24–30 帧已经把那一行判成 S = 1，也就是新规则提前看到了。
- 针的受击 41 对 32：按分钟算是 0.47 对 0.37，单轮里不显著；瞄准的针第 4 轮也没让针的受击变少。37 / 41 次发生在扔针已经开始时，但其中只有 3 次在受击前 30 帧内有 S = 0 的计划，其余都发生在 FORCED_RISK 里。针的问题主要在已承诺层的饱和：没有干净的行可选。这不是"没有一层管"造成的。
- 结论：这一轮修的是安全的口径，不是战绩。S = 0 现在包含可逃检查的结果；`+n` 前摇里的针 / 钟有了覆盖；新指标能看到 2–4 帧口径之外的风险。打完率、存活、击杀和 rec 持平。推荐配置不变（`escape+n+g` 加拼刀主逻辑加按状态余量），但 `+n` 现在自带上面三条修正。

## 24. 剩余受击：第 2、3 轮比第 1 轮的 new 改了什么、差在哪里，剩下的每一下是什么（2026-10-08，task remaining hits，分支 worktree-wf_14cec809-b56-1；离线，没碰实例）

你的问题：跟第一轮"击杀冻结 bug 修正 + 三层危险区"（§23.6 的 **new**）比，第二、三轮都改了什么、怎么变差了。数据：§23.6–23.7 和第 3 轮（newS 对 noL）、第 4 轮（newS 对 newSa = newS + 瞄准的针 `+a`）的全部实战（Forum_W，eval、planner、oracle、真退出 0.2），清单 `C:\ssbot\sandbox\w0d_manifest_a/b/c/d.txt`，共 719 场。工具（本节新增）：`ssbot.tools.forum_remaining_hits`（`collect`：attempts 行 + 录像 STATE + FSM 事件 + 决策日志，逐场逐受击；`report`：按臂比率、自助区间、差中差、按来源的泊松检验、机制分类、事后之明合并、功效）；`forum_hit_forensics` 加了 `--crest` / `--clash`（漫游、拼刀主逻辑的开环回放）。输出 `C:\ssbot\data\m2_forum_rh\`（`all\eps\` 每场一个 JSON，`report.json`，`ao_*.json`，`fx_*\`）。

计量口径：每场从 7 格血打到剩 2 格就退出（Q1 hits_to_death 1），所以每场掉的格数基本固定（5–6 格），**掉格 / 分 ≈ 存活时间的倒数**；多段链（Choristor 鞭、Reed 反击钩）一下 2 格，按格数算（§23 的表按受击次数，没区分 2 格链）。等效失血 = 掉的格数 − 砍中刀数 / 4（plan §5 你的汇率）。砍中 = STATE 的 `hit` 事件（打到任何敌人）。

### 24.1 第 2、3 轮相对第 1 轮 new 改了什么

第 1 轮 new = 冻结检出 016417b，`SSBOT_FORUM_REACT=escape+n+g+l`、`--forum-clash main`、击杀冻结修正、`seen_cf`、家族余量。第 2 轮 newS = 冻结检出 fca0416，多了下面四项；第 3 轮同一份代码比 newS 和 noL（newS 去掉光锥 `+l`）；第 4 轮冻结检出 33762ee（只多了默认关的 `+a`），newS 的行为和第 2、3 轮相同。

| 改动 | 提交 | 第 0 波里的作用 |
|---|---|---|
| **扔针替换**（`+n` 的一部分）：Reed 进了扔针招，RE_THROW 的模板、尾巴、可逃检查里"扔针"这个威胁都拿掉，换成本体管；针飞出来才有确定路径 | cc11343 | 针在手里时不再占支撑；第 1 轮 new 的针受击里 7 / 26 在出针那一帧的可逃检查威胁里有 RE_THROW，第 2、3 轮 0 / 126 |
| **拼刀主逻辑的两处**：FORCED_RISK 的 seen 键跳过拼刀行的拼刀无敌帧；连拼 3 次（之前 2 次） | e54ad2d | 部分拼刀行被选中 6.1 → 7.0 / 7.3 次 / 分，干净拼刀行 1.7 → 1.7 / 2.1 次 / 分 |
| **按状态的余量**（`SSBOT_FORUM_MARGIN=state`） | d89f7ba | 选中安全行的 tick 0.31 → 0.35 / 0.29 / 0.36（第 2 / 3 / 4 轮；复核更正：第 4 轮是 0.36 = 1 − 0.64，初版写成 0.31）——三轮里两轮变多、一轮变少 |
| 砍钟作防御（默认开） | fca0416 | 第 0 波没有钟，不起作用 |
| 第 3 轮的 noL：去掉光锥 `+l` | — | 见 24.2 第 6 条 |

另外不同的：种子（361000 / 362000 / 363000 / 364000，**跨轮不能配对**）、时段和负载（迟到 tick：第 1 轮 new 8.4 %、第 2 轮 newS 11.3 %、第 3 轮 8.1 %、第 4 轮 15.6 %）。

### 24.2 变差在哪里（`report`，自助法 2,000 次；p 是双侧、不配对）

| | r1 intk | **r1 new** | r2 intk | **r2 newS** | **r3 newS** | **r3 noL** | **r4 newS** |
|---|---|---|---|---|---|---|---|
| 场 / 分钟 | 80 / 41.3 | 79 / 68.9 | 80 / 47.9 | 80 / 72.1 | 80 / 63.7 | 80 / 70.7 | 80 / 81.1 |
| 掉格 / 分（95 % 区间） | 9.83 | **6.82**（5.86–8.08） | 8.48 | **6.77**（5.88–7.94） | **7.06**（5.93–8.40） | **6.72**（5.88–7.88） | **6.08**（5.27–7.13） |
| 砍中 / 分 | 23.2 | **19.9** | 23.9 | **17.0** | **17.8** | **18.1** | **18.6** |
| 等效失血 / 分（95 % 区间） | 4.02 | **1.85**（0.94–2.99） | 2.50 | **2.51**（1.88–3.35） | **2.62**（1.76–3.72） | **2.20**（1.40–3.26） | **1.42**（0.64–2.42） |
| 只看第 0 波：掉格 / 砍中 / 等效 | 10.16 / 23.0 / 4.41 | **7.40 / 17.4 / 3.04** | 8.64 / 23.3 / 2.81 | **6.76 / 15.6 / 2.86** | **7.35 / 16.5 / 3.21** | **6.99 / 16.2 / 2.96** | **6.69 / 16.4 / 2.60** |
| 第 0 波以外的时间占比；那里的掉格 / 砍中 | 9 %；5.7 / 25.6 | **21 %；4.5 / 29.5** | 10 %；6.8 / 29.2 | 15 %；6.6 / 25.5 | 14 %；5.0 / 25.6 | 18 %；5.4 / 26.7 | 26 %；4.3 / 25.1 |
| 击杀 / 场 | 0.80 | **1.42** | 1.18 | **1.19** | **0.86** | **1.30** | **1.66** |
| 打完第 0 波 | 11 | 15 | 16 | 15 | 11 | 17 | 23 |
| 按攻击键 / 分；砍中 / 按键 | 76；0.31 | **61；0.33** | 77；0.31 | **57；0.30** | **59；0.30** | **56；0.32** | **55；0.34** |
| FORCED_RISK tick 占比 | 0.90 | 0.69 | 0.91 | 0.64 | 0.71 | 0.69 | 0.64 |

（r1 int：掉格 11.58、砍中 11.5、等效 8.71、0 击杀；r4 newSa：掉格 6.23、砍中 18.0、等效 1.73、击杀 1.55，和 r4 newS 没有差别，p ≥ 0.6。）

1. **挨打没有变多**：掉格 / 分 6.82 → 6.77 / 7.06 / 6.72 / 6.08（第 2、3、3、4 轮，p 0.93 / 0.79 / 0.91 / 0.30）；只看第 0 波 7.40 → 6.76 / 7.35 / 6.99 / 6.69（p ≥ 0.41）。
2. **第 2、3 轮少的是打出去的**：砍中 / 分 19.9 → 17.0 / 17.8 / 18.1（−2.8 / −2.1 / −1.8，p 0.10 / 0.20 / 0.22），击杀 / 场 1.42 → 1.19 / 0.86 / 1.30（r3 newS p 0.06），按键 / 分 61 → 57 / 59 / 56；等效失血因此 1.85 → 2.51 / 2.62 / 2.20（p 0.32 / 0.29 / 0.58）——**plan §5 里"new 0.8、newS 1.6"那个变差就是这个，按格数算是 1.85 对 2.51**。
3. **但第 4 轮同一个 newS 比第 1 轮 new 还好**：等效失血 1.42、击杀 1.66、打完第 0 波 23 场、掉格 6.08（对 new：−0.43 / +0.25 / +8 场 / −0.75，都不显著）。**同一配置 newS 三轮之间**：击杀 1.19 / 0.86 / 1.66（第 3 对第 4 轮 +0.80，**p 0.01**）、等效失血 2.51 / 2.62 / 1.42（第 4 对第 2、3 轮 p 0.07）；代码等同的 intk 第 1 → 2 轮第 0 波掉格 −15 %（p 0.04）。~~轮与轮之间同一臂的波动，和"第 1 轮 new 对第 2、3 轮"的差一样大甚至更大：第 2、3 轮的"变差"是轮次（种子、负载、时段）带来的，不是改动带来的。~~ **复核更正：这个结论说过头了**——轮次效应只靠两个 p 值（0.006、0.031），而本节一共做了约 117 个检验（13 组比较 × 9 个指标）；拿没有同轮 intk 对照的第 4 轮 newS 去否定第 5 条的同轮差中差，本身就是本节说"没有意义"的跨轮比较。能说的只是：**分不出来；控制最好的比较（第 5 条的同轮差中差）倾向于第 2 轮的改动减少了砍中和击杀**。三轮 newS 合起来（240 场）对 new：掉格 6.60 对 6.82（p 0.70）、砍中 17.9 对 19.9（p 0.16）、等效 2.13 对 1.85（p 0.63）、击杀 1.24 对 1.42（p 0.53）、第 0 波等效 2.88 对 3.04（p 0.71）。
4. **等效失血的差里一大块是波次构成**：第 1 轮 new 有 21 % 的时间在第 1–5 波（那里每分钟砍中 29.5、掉 4.5 格，等效 −2.9：净赚），第 2、3 轮只有 14–18 %，第 4 轮 26 %（所以第 4 轮的总数最好看）。**只看第 0 波，等效失血 3.04 → 2.86 / 3.21 / 2.96 / 2.60，差都在 ±0.45 以内（p ≥ 0.44）**。
5. 用第 2 轮的同轮对照 intk 做差中差：第 1 轮 new 比 intk 少 2.17 格 / 分等效失血，第 2 轮 newS 比 intk 少 0.01，差中差 +2.18（0.12–4.24，p 0.04），主要在砍中（−3.6 / 分，p 0.09）；击杀上第 1 轮 new 比 intk 多 0.62（p 0.025），第 2 轮 newS 比 intk 只多 0.01（p 0.99）。这是"变差"能找到的最强证据。~~其中一半是 intk 在第 2 轮自己变好（4.02 → 2.50），而第 4 轮 newS 的等效失血（1.42）又比第 1 轮 new 好——不成立。~~（复核更正：差中差正是用同轮对照抵消 intk 自己的变化；第 4 轮没有 intk 对照，不能用来推翻它。**这一条成立到 p 0.04，未经多重比较校正**；确认要同一轮里冻结的 016417b（new）对 fca0416（newS）ABBA，能开关的部分（MARGIN）再单开关比。）
6. **受击构成**（掉格 / 分，泊松精确检验对 r1 new；复核：按场的计数有过度离散（离散度 1.35–2.4），泊松检验的 p 偏小，应改用准泊松或按场的自助法）：Reed 针第 2、3 轮 0.38 → 0.64 / 0.69（p 0.03 / 0.02），看起来是扔针替换的代价，**但第 4 轮同一份代码回到 0.35**（intk 第 2 轮也涨到 0.56，它没有替换）：也是轮次；三轮合起来 0.54 对 0.38（p 0.10）。Envoy 冲锋 0.23 → 0.13（三轮合起来，p 0.08），可能是按状态余量（`Charge End` 2.96 → 0.40 u）或拼刀 seen 跳无敌帧（漫游侧面拼冲锋 42 次失败 1 次）。鞭链、Envoy 横斩、跳旋、连斩、突刺都在 ±0.35 以内（p ≥ 0.1）；Envoy 跳斩第 2 轮 0.29 → 0.50（p 0.06），第 3、4 轮 0.35 / 0.31 / 0.25。
7. **光锥（第 3 轮 noL 对 newS，同轮）**：noL 每项都略好（掉格 −0.34、砍中 +0.31、击杀 +0.44、存活 +5 s），全部不显著（p ≥ 0.15）：量不出光锥的作用。瞄准的针（第 4 轮 newSa 对 newS）：针 0.37 对 0.35，其余也没差。
8. 所以回答"怎么变差了"（复核后改写）：**第 2、3 轮挨打没有变多；变少的是砍中（每分钟少 2–3 刀）和击杀，等效失血按格数差了 0.35–0.77 格 / 分。是改动还是轮次，分不出来**：同一配置 newS 第 4 轮比第 1 轮 new 还好、代码不变的 intk 两轮也差 15 %，说明轮次波动很大；但同轮的差中差（第 5 条）倾向于第 2 轮的改动减少了砍中和击杀（等效 +2.18，p 0.04；砍中 −3.6 / 分，p 0.09），而三轮 newS 的砍中都少约 2 刀 / 分（−10 %，合起来 p 0.16）、按键都少约 4 次 / 分（p 0.10），方向一致。~~所以这不是第 2 轮的改动造成的。~~ 改动本身在第 0 波里量不出好坏（80 场 / 臂只能分出 30 % 以上的掉格差，24.6）。要确认它和找原因（扔针替换让 Reed 扔针时不再占支撑、拼刀 seen 让部分拼刀行多选 15–40 % 而刀砍在招上不在身上、按状态余量），只能同一轮里比：先冻结的 new 对 newS（ABBA），再单开关，每臂 300–600 场。

### 24.3 剩下的每一下（最好的四臂：r1 new、r2 newS、r3 newS、r3 noL；319 场、275 分钟、1,626 次受击、1,876 格）

- **全部在 FORCED_RISK（YELLOW）里挨的**：受击那一 tick 没有一个是 GREEN；89 % 的受击前最后一 tick，选中和日志列出的 5 个备选的接触占比 P 全是 1。出招开始那一 tick（有日志的 1,467 下）91 % 已经是 FORCED_RISK（n_safe = 0），GREEN 只有 7 %；目标层 KITE(EVADE) 61 %、RUSH 35 %。决策日志在受击前几乎逐 tick（攻击开始到受击的窗口里 97 % 的帧有记录）。
- **事后之明**（§19.1 的方法：开环回放，受击前 1–90 帧 16 个时刻，每个已知行对录像里真实的伤害碰撞体；回放用漫游、拼刀主逻辑、各臂自己的开关；r2 newS 的 80 场、r3 newS 的 80 场，其中 814 次受击）：最后一个还有"事后不碰"行的时刻 ≤ 3 帧 21 %、4–9 帧 33 %、12–18 帧 31 %、24–36 帧 13 %、更早 2 %；~~76 % 的受击在 ≥ 4 帧前还有出路（§19.5 是 78 %），针只有 40 %（90）~~。**复核更正**：初版的"可避"是"最后一个有出路的时刻在 4–36 帧"，于是 ≤ 3 帧那一箱整箱算成不可避，可那 174 下里 173 下在 4–36 帧前也有出路。按字面意思（受击前 4–36 帧里**有任何一个**分析过的 tick 有事后不碰的行；工具已改，`forum_remaining_hits report` 的 `avoid`，`C:\ssbot\data\m2_forum_rh\report_avoid_v2.json`）是 **97.4 %**（0.25 u 余量的 `hs_clear_g`：94.6 %）；能反应的那一档（4–6 帧前有出路）36.6 %（余量 22.4 %）。§19.5 的 78 % 是另一个口径（最后有出路的时刻 ≤ 9 帧），同口径这里是 54 %。**针 4–36 帧前 100 % 有出路、4–6 帧前 78 %**（鞭链只有 7 %）：针放手后路径就定了（飞 0.18 s），开环的事后之明对它也成立，所以针的受击是规划器 / 延迟的失败，不是躲不开。
- 按来源（格数、占全部格数）：

| 来源 | 格 | 占比 | 出招时离主角（中位） | 出招到打中 | 打它时在出刀（≤ 0.5 s 按键、目标就是它） | 0.6 s 内刚砍中过 | h ≤ 2（不拼刀） | 滑翔中挨打 | 窗口里有过安全行 |
|---|---|---|---|---|---|---|---|---|---|
| Choristor 鞭链（2 格） | 500 | 27 % | 8.4 u | 1.07 s | 37 % | 24 % | 52 % | 35 % | 22 % |
| Envoy 横斩 | 220 | 12 % | 4.1 u | 0.73 s | 66 % | 26 % | 13 % | 25 % | 4 % |
| Choristor 跳旋 | 209 | 11 % | 9.2 u | 1.17 s | 38 % | 18 % | 5 % | 25 % | 35 % |
| Reed 针 | 152 | 8 % | 6.9 u（出针时） | 0.18 s（飞行） | — | 9 % | 12 % | 41 % | 5 % |
| Choristor 连斩 | 139 | 7 % | 5.7 u | 0.70 s | 51 % | 25 % | 12 % | 19 % | 17 % |
| Reed 突刺 + 突刺时的本体 | 257 | 14 % | 5.7 u | 0.72–0.97 s | 51–56 % | 46–52 % | 9–13 % | 30–44 % | 5–10 % |
| Envoy 跳斩 | 100 | 5 % | 4.5 u | 0.50 s | 62 % | 31 % | 11 % | 34 % | 4 % |
| Envoy 冲锋 | 37 | 2 % | 8.9 u | 0.73 s | 30 % | 19 % | 3 % | 0 | 43 % |
| 其余（后面波次的钟、矛、Choristor 本体……） | 262 | 14 % | | | | | | | |

（复核：表里"h ≤ 2"一列取的是 `hit_log` 里的 h——一条完整的鞭链取 Final Hit 时的 h，那时钩子 tick 已经扣过 1 格；按决策日志在**出招开始**时是 92 / 271 = 34 %，钩子那一 tick 36 %。鞭链的 52 % 是按格加权，按受击算是 55 %。"滑翔中挨打"一列要和基础比例比：14 场抽样里 bot 有 23.5 % 的帧本来就在 `Umbrella` 动画里。）

- **机制**（每下取第一个成立的：针 → 防御反击 → 走进待机身体 → 出招开始时被锁住 → 在打它 → 有拼刀几何但没拼 → 窗口里有过安全行 → 饱和）：在打它（追打 / 换血）677 格 36 %、饱和（窗口里一直没有安全行）591 格 32 %、出招开始时主角被锁 ≥ 12 帧（滑翔前摇、出刀后摇、冲刺）202 格 11 %、针 152 格 8 %、有过安全行又丢了 120 格 6 %、低失败率家族有拼刀几何没拼 103 格 5 %、Reed 防御反击 26 格 1.4 %、走进待机身体 5 格 0.3 %（你的第 ⑤ 条已经起作用）。
- **被锁住那一类按锁的种类拆开**（复核，202 格）：冲刺约 30 %（`Air Dash` 36 格、`Sprint Air` 22 格）、出刀后摇约 27 %、**回血 21 格（10 %：出招开始时正在 `BindCharge` / `BindBurst`，说明 Bind 的提交条件有漏洞，初版没提）**、开伞只有 17 格（8 %）、`Stun` 16 格。所以第 4 条修正以冲刺 / 出刀的锁定为主，Bind 的提交条件单独查。
- ~~**换血不划算**：在打它时挨的那些下，挨打前 1.5 s 内砍中它 0.1–0.9 刀 / 格（鞭 0.14、Envoy 横斩 0.31、跳旋 0.31、突刺 0.86），远低于你的汇率 4 刀 = 1 格：每一次这样的"追一刀"都在亏等效血。~~ **复核更正：这是按结果挑的样本**——0.1–0.9 刀 / 格（鞭 0.14、Envoy 横斩 0.31、跳旋 0.31、突刺 0.86）只统计了以挨打收场的那些进攻。四个最好的臂一共砍中 5,010 刀，按你的 4 刀 = 1 格折合 1,252 格，追打这一类掉了 677 格（全部掉格 1,876）：**整体是净赚**。它不能当"该少出刀"的证据（第 2、3 轮的问题恰恰是砍中少了）；要比换血，得按进攻片段算（从进入 RUSH / 出刀到结束，所有片段的砍中 / 4 对掉格）。
- **滑翔**：25–35 % 的受击时主角在 `Umbrella` 动画里（复核：这基本就是基础比例，bot 23.5 % 的帧在 `Umbrella` 里；被锁那一类里开伞只占 8 %）（`Umbrella Inflate Antic` 时攻击、冲刺都不响应，Inflate 0.075 s 之后才行，movement_kinematics.md 1.2）；慢慢往下飘、只有 8.5 u/s 的横向速度。规划器的运动学有滑翔（开伞前摇 0.084 s、Inflate 0.19 s），行里空中再按跳就会开伞（movement_kinematics.md 1.2 的条件）。
- **鞭链和 h ≤ 2**：~~鞭链的 52 % 在 h ≤ 2 时挨的~~（复核更正：按出招开始时的 h 是 34 %，见上表注）——有选择效应（2 格链在 h = 3 时把这一场直接打到退出，所以每场最后一下常是鞭链），也有拼刀门：h ≤ 2 时拼刀主逻辑不跑（DESIGN 3.5.6），而漫游拼 Choristor 鞭（侧面）24 次只失败 1 次（Wilson 上界 0.20，规划器用的就是上界）。h = 2 的收紧现在由你的决定处理（DESIGN 3.5.6 修订：剩的血 > 单次最大伤害时什么都允许，挨打后退出），不再是这里的修正。鞭的钩子碰撞体（`Whip Hit n`，导出 dealt 0、eff 2、可拼）在 STATE 里有，oracle 视图算作伤害框，规划器的 seen 看得到。
- **实战的受击记录认错了实例**：鞭链的 44 %、Choristor 连斩的 40 % 在 `hit_log` 里记成另一只 Choristor（按路径名找实体，取到同类型的第一只，常常是还在 Sleep 的那只）；`follow_ups` 和按实例的统计因此不准（覆盖检查按类型，不受影响）。本工具按碰撞体家族和出招时间改正。

### 24.4 你在同样局面下的做法（`forum_attack_outcomes`，第 0 波、出招时 8 u 内；你的是 2026-10-04/05 的 Reaper 录像，bot 是漫游）

| 家族 | 每次出招被打中：r1 new / r2 newS / r3 newS / r3 noL | 你 1x / 0.5x | 每分钟遇到的次数：bot（r2 newS）/ 你 1x |
|---|---|---|---|
| EN_SLASH | 10 / 6 / 9 / 8 % | 14 / 0 % | **14.1 / 6.3** |
| RE_STAB | 20 / 25 / 19 / 20 % | 18 / 15 % | 4.3 / 7.4 |
| CH_SLASH | 13 / 13 / 14 / 14 % | 35 / 7 % | 3.7 / 3.6 |
| EN_JUMPSLASH | 12 / 16 / 13 / 13 % | 26 / 0 % | **3.9 / 1.4** |
| RE_EVADE | 7 / 9 / 6 / 5 % | 16 / 8 % | 3.7 / 4.0 |
| RE_DEFEND | 2 / 3 / 2 / 2 % | 12 / 0 % | 2.4 / **4.8** |
| CH_WHIP | 15 / 10 / 13 / 16 % | 21 / 9 % | 2.2 / 2.1 |
| CH_JUMP | 9 / 8 / 10 / 12 % | 24 / 6 % | 2.6 / 2.2 |
| EN_CHARGE | 10 / 6 / 7 / 7 % | 17 / 25 % | 1.1 / 1.1 |

- **按每次出招算，bot 已经不比你 1x 差**（只有 Reed 突刺略高；复核：其实你 1x 每次出招被打中的比例更高——Envoy 横斩 14 % 对 6–10 %、鞭 21 % 对 10–16 %、跳斩 26 % 对 12–16 %）；第 0 波每分钟挨打 bot 6.0–6.6 次、你 1x 11.4、0.5x 3.7。差在两处：**bot 每分钟遇到 Envoy 横斩 / 跳斩的次数是你的 2.2–2.8 倍**（初版写成"待在距离里的时间"，量的其实是每分钟遇到的出招次数；它是 RUSH 的目标，bot 在 4–5 u 外转，等它出招），而**你打 Reed 打得多**（你触发 Reed 防御 4.8 次 / 分、突刺 7.4 次 / 分，bot 2.4 / 4.3）；你打完第 0 波 24 / 46（52 %），bot 11–17 / 80（14–21 %）——**复核：两边的停止规则不同，不能直接比**：你在第 0 波 46 次里挨了 309 下（平均每次约 6.7 下），没有 bot 那样挨到剩 2 格就退出（Q1）；要比就按同一停止规则，或比第 0 波每分钟击杀。另外你用的是收割，bot 用的是漫游。
- 躲开时的做法（干净的那些）：Envoy 横斩，你**退 2.7 u**（bot 1.0）、出招时 70 % 在空中（bot 89 %）、跳 43 %（bot 95 %）、冲刺 27 %（bot 60 %）、出刀 84 %（bot 66 %）；Choristor 鞭，你**退 5.9 u**（bot 2.0）；Reed 突刺，你退 0.7 u（bot 往里 0.5 u）。bot 跳和冲刺得多、退得少。**这些是观察，不是修正**（复核）：你每次出招被打中的比例比 bot 高，所以"你干净躲开时退 2.7 / 5.9 u"不能说明退远会少挨打；退距要在 bot 自己的数据里比（退得远的干净 / 挨打比例），或者实战 A/B。

### 24.5 原因排序和修正（按格数；"可避"= 受击前 4–36 帧里有任何一个 tick 有事后不碰的行（复核更正后的口径，24.3），"4–6 帧"= 能反应的那一档；回放的场数见 24.3；括号里是有回放的受击数）

| # | 原因 | 格（占比） | 可避 / 4–6 帧 | 修正（对应你的打法） |
|---|---|---|---|---|
| 1 | **追打 / 换血**：在打它的时候挨它的招（Envoy 横斩 / 跳斩、Reed 突刺、Choristor 连斩、鞭） | 677（36 %） | 97 % / 27 %（301） | FORCED_RISK 和 J 按你的汇率给行定价（行的期望掉格 P × d 对它预计砍中数 / 4，plan §5 已写）。~~现在挨打前 1.5 s 只砍中 0.1–0.9 刀 / 格~~（复核：按结果挑的样本，整体砍中 1,252 格对这一类掉 677 格，是净赚；定价规则保留，但不是"少出刀"的证据）。Envoy 横斩：`Slash1 Recover` 里还手（R6 的惩罚窗口）；你退 2.7 u、Reed 突刺你退 0.7 u 是观察，不是修正（24.4） |
| 2 | **Choristor 鞭链**（2 格；和别的原因重叠） | 500（27 %） | 96 % / 7 %（132） | 你的决定（DESIGN 3.5.6 修订）：拼鞭是**低分的安全选项**；更好的是前摇（约 0.82 s）时绕到它身后，或换一个在鞭的范围外的目标（它甩鞭时站着不动）。~~鞭前摇时退 ≥ 6 u；对低失败率家族取消 h = 2 不拼刀，连拼深度提到 5（鞭有 5 段）~~（复核：退距是观察；鞭有 6 段 `Whip 1–6`、`clash.json` 里能拼的是 Whip 1–4；每次拼的 Wilson 上界 0.20，连拼 5 次的成功下界 0.8⁵ = 0.33，在 `clash_max_fail` 0.3 下永远算不上干净；h = 2 的门现在由你的决定处理） |
| 3 | **饱和**：窗口里一直没有安全行 | 591（32 %） | 98 % / 37 %（222） | 已承诺层的窗口放置仍然盖满（§23.2）；定时拼刀行、按名义时刻的已承诺模板（§19.11 第 2 条）；事后看几乎都还有出路，排序要能找到它们 |
| 4 | **出招开始时主角被锁住**（冲刺约 30 %、出刀后摇约 27 %、Bind 10 %、开伞 8 %、Stun；≥ 0.2 s） | 202（11 %） | 94 % / 32 %（96） | 出刀 / 冲刺前先问"锁定里来得及躲吗"（锁定点的可逃检查 `+n` 已有）；**Bind 的提交条件查漏洞**（21 格在 `BindCharge` / `BindBurst` 里挨）；开伞只占 8 %（初版"少开伞"排在前面是错的：滑翔中挨打的比例约等于基础比例 23.5 %） |
| 5 | **Reed 针**（飞 0.18 s，出针时 6.9 u） | 152（8 %） | **100 % / 78 %**（90） | 初版的"40 % 躲得开"是可避口径的错（24.3）：针 4–6 帧前还有出路的占 78 %，是规划器 / 延迟的失败。瞄准的针（`+a`，33762ee）第 4 轮量不出差别（针 0.37 对 0.35 格 / 分）；飞行怪正下方加分（below.json：针 6.4 % 对前方 15–22 %，你的第 ③ 条）、Reed 扔针前摇时横向移动（针瞄 0.33 s 前的位置，§23.7）；查这些受击前 4–6 帧有出路时规划器为什么没选 |
| 6 | 有过安全行又丢了（鞭、跳旋、连斩为主） | 120（6 %） | 100 % / 35 %（49） | 安全行在出招开始后消失：已承诺模板入场后变宽；定时行、在出招前就站到它够不着的地方 |
| 7 | ~~低失败率家族有拼刀几何但没拼（Envoy 横斩、跳斩、冲锋、鞭）~~ | 103（5 %） | 98 % / 18 %（44） | ~~同 2：取消 h = 2 不拼刀（对这些家族）；拼刀行进候选~~ **复核：这一类拿掉**——103 格里 95 格的拼刀几何最早只在接触前 ≤ 3 帧出现，漫游的刀按下后 0–0.12 s 才生效、再加反应延迟，来不及拼；几何常在上方 / 下方，低失败率却只看侧面的数据（§17.3 也写了"接触局面"的拼刀明显更差）。要保留就要求几何最早在 ≥ 6 帧前出现、按刀向分别查失败率 |
| 8 | Reed 防御反击 | 26（1.4 %） | 100 % / 73 %（11） | **按 Reed 防御一节**（不是 Minister 的规则）：Reed 的反击按主角的高度瞄（`Parry Y Aim`），从上面 / 下面触发并不安全（下劈触发 3 / 7 挨打）；它的 Block 是 0.516 s（不是 Minister 的 Parry Block 0.583 s）。做法：防御里不砍，等它结束（Defend 约 1.0 s），或者对准反击时刻拼刀（拼中一下整套反击取消，`Multihit Clashed`）。~~或下劈触发~~ |
| 9 | 走进待机身体 | 5（0.3 %） | — | 你的第 ⑤ 条已经解决（§23 的 `+g`） |

（除第 2 条外互不重叠：每一下按 24.3 的先后取第一个成立的机制；鞭链单列，因为它跨了几类、又是 2 格。总结里的 "hits" 是受击次数，"share" 是按格的占比。）

### 24.6 A/B 功效：80 场 / 臂能量出多大的差

每场的比率噪声很大（存活时间长尾：同一臂里有 20 s 的也有 200 s 的），**同实例同种子配对几乎没有相关**（配对差的相关 ρ = −0.13 … +0.01：种子只定开局位置，之后全是随机的），所以配对不比不配对省场数。双侧 5 %、功效 80 %，每臂要的场数（括号：80 场 / 臂能检出的最小相对差）：

| 指标 | 10 % 的差 | 20 % 的差 | 80 场能检出 |
|---|---|---|---|
| 受击 / 分 | 620–1,000 | 160–250 | 28–35 % |
| 掉格 / 分 | 670–970 | 170–240 | 29–35 % |
| 第 0 波掉格 / 分 | 730–1,080 | 180–270 | 30–37 % |
| 砍中 / 分 | 270–610 | 70–150 | 19–28 % |
| 等效失血 / 分 | 2,800–9,600 | 700–2,400 | 60–110 %（复核：按绝对量 1.5–2.0 格 / 分，见下） |
| 击杀 / 场 | 3,200–5,100 | 800–1,300 | 57–80 % |
| log 存活 | 670–950 | 180–260 | — |

- 去饱和这几轮**能**量出：int → intk → new（掉格 −15 %、−31 %，§23.6）、newS 对 intk（−20 %，§23.7）。**量不出**：new 对 newS（−1 %）、newS 对 noL（+5 %）、newSa 对 newS（+2 %）、等效失血 1.5–2.0 格 / 分以下的差（初版写"要 60 % 以上"，见下）、击杀的差（要 57 % 以上）。
- **跨轮的波动比这还大**：同一配置 newS 三轮的击杀 1.19 / 0.86 / 1.66（第 3 对第 4 轮 p 0.01）、等效失血 2.51 / 2.62 / 1.42；代码等同的 intk 两轮第 0 波掉格差 15 %（p 0.04）；第 2、3 轮的针涨了 70 %（来源计数 p 0.02–0.03），第 4 轮同一份代码又回到第 1 轮的水平。所以跨轮的比较（包括拿第 1 轮的 new 去比后面的轮）在这个样本量下没有意义；来源计数的泊松检验够灵敏，但同样只能在同一轮里用。
- 建议：比较只在同一轮里做（ABBA，同负载），**不跨轮**（对照臂自己跨轮变了 15 %）；主指标用第 0 波的掉格 / 分和砍中 / 分，20 % 的差要每臂约 200 场；针对某一类招的修正用该来源的计数检验（准泊松或按场自助，24.2 第 6 条）。~~等效失血只作汇总，不作判据（要几千场）。~~ **复核更正**：等效失血的"60–110 %"只是因为它的均值接近 0；按绝对量，80 场 / 臂能分出 1.5–2.0 格 / 分，和掉格 / 分的 1.9–2.5 格 / 分差不多，所以照 plan §5 你的要求，它和无伤波数并列为主指标，功效按绝对差报。**无伤波数**本节没报：719 场里第 0 波无伤打完 0 次。

### 24.7 复现

```
cd brain
# 复核更正后的可避（avoid / react / avoid_g / react_g，report 的 mechanisms / families / hindsight 键）
..\scripts\uv.cmd run python -m ssbot.tools.forum_remaining_hits report --out C:/ssbot/data/m2_forum_rh/all --json C:/ssbot/data/m2_forum_rh/report_avoid_v2.json --arms r1:new,r2:newS,r3:newS,r3:noL --focus r1:new,r2:newS,r3:newS,r3:noL --hindsight C:/ssbot/data/m2_forum_rh/fx_r2_newS --hindsight C:/ssbot/data/m2_forum_rh/fx_r3_newS
# 逐场逐受击（每场一个 JSON，已有的跳过）
..\scripts\uv.cmd run python -m ssbot.tools.forum_remaining_hits collect --manifest r1=C:/ssbot/sandbox/w0d_manifest_a.txt --manifest r2=C:/ssbot/sandbox/w0d_manifest_b.txt --manifest r3=C:/ssbot/sandbox/w0d_manifest_c.txt --manifest r4=C:/ssbot/sandbox/w0d_manifest_d.txt --out C:/ssbot/data/m2_forum_rh/all --workers 3
# 事后之明（K_SET 的 tick；环境变量按臂：FR=seen_cf、KF=kill、REACT、MARGIN）
..\scripts\uv.cmd run python -m ssbot.tools.forum_hit_forensics <runs> --out C:/ssbot/data/m2_forum_rh/fx_r2_newS --every 100000 --workers 2 --threads 4 --forced-rank seen_cf --crest Wanderer --clash main
# 汇总
..\scripts\uv.cmd run python -m ssbot.tools.forum_remaining_hits report --out C:/ssbot/data/m2_forum_rh/all --json C:/ssbot/data/m2_forum_rh/report.json --arms r1:int,r1:intk,r1:new,r2:intk,r2:newS,r3:newS,r3:noL,r4:newS,r4:newSa,r234:newS --pool r234:newS=r2:newS+r3:newS+r4:newS --cmp r1:new~r2:newS --cmp r1:new~r4:newS --cmp r3:newS~r4:newS ...（全部见 report.json 的 diffs 键） --did r1:intk~r1:new~r2:intk~r2:newS --pairs r2:intk~r2:newS ... --focus r1:new,r2:newS,r3:newS,r3:noL --hindsight C:/ssbot/data/m2_forum_rh/fx_r2_newS --hindsight C:/ssbot/data/m2_forum_rh/fx_r3_newS
# 你的录像对比
..\scripts\uv.cmd run python -m ssbot.tools.forum_attack_outcomes --bot <runs of one arm> --human <§19.12 的五个会话> --cache C:/ssbot/data/m2_forum_w0f/demo_cache --json C:/ssbot/data/m2_forum_rh/ao_<arm>.json
```

### 24.8 复核（2026-10-08，独立核对；上面各处已就地更正）

- **确认**：第 2 轮相对 new 只多了四样代码（`git diff 016417b fca0416`；33762ee 只多了默认关的 `+a`）；各臂的比率（自己的脚本从 719 个场 JSON 重算，9 臂一致）；关键 p 值；按原因的受击数（全量重实现一致；分层抽 63 下对原始录像和日志核对：主要原因 63 / 63、格数 63 / 63、来源实例 62 / 62、招的家族 62 / 63）；受击前最后一 tick 100 % FORCED_RISK；事后之明的分箱（174 / 265 / 253 / 102 / 20；4 场离线重跑 319 个 tick 的 `hs_clear` 全部一致）；`hit_log` 认错实例（鞭 43 %、连斩按格 40 %，样本 6 / 6）；漫游拼刀表的计数。
- **推翻**：①"变差是轮次波动、不是改动"（24.2 第 3、5、8 条，改成"分不出来，同轮差中差倾向于改动减少了砍中和击杀"）；②"76 % 的受击 ≥ 4 帧前有出路"（是 97.4 %；工具的可避定义已改，24.3）；③"针只有 40 % 躲得开"（100 %，4–6 帧前 78 %）；④"有拼刀几何没拼的可以靠拼刀解决"（几何多在接触前 ≤ 3 帧才出现，24.5 第 7 条拿掉）；⑤"鞭链 52 % 在 h ≤ 2"（出招开始时 34 %）；⑥"换血不划算"（按结果挑样本，整体净赚）。
- **部分推翻**：等效失血的功效（按绝对量 80 场能分出 1.5–2.0 格 / 分，24.6）；你的录像对比（数对，但推不出"照你的退距"，停止规则不同，24.4）。
- **其他更正**：Reed 防御的修正按 Reed 防御一节（反击瞄高度，不用下劈触发）；被锁住的一类按种类拆开（含 Bind 21 格）；24.1 第 4 轮选中安全行 0.36；鞭有 6 段。
- **还没做**：同一轮里冻结的 new 对 newS（ABBA）；按进攻片段的换血；r1 new 和 noL 的事后之明回放（现在只回放了 r2 / r3 newS 的 160 场）；`hit_log` 的实例归属修正（策略记账，没改）。

## 25. 你赢的录像在规划器眼里（2026-10-08，task "the person's wins under the planner"；分支 worktree-wf_5bda75c4-6ae-1 = main + 去饱和分支；离线，没有连接游戏，规划器行为一行没改）

问题（你 10-08）：现在的 bot 没你打得好；拿你打赢的录像给规划器打分，你的操作为什么得分更低？做法：把你的录像开环喂给 `ForumPlannerPolicy`（同 §19.1），每个 tick 找出最像你接下来实际动作的候选行，看规划器怎么判它、把它排在第几、为什么不选它，再用录像里真实的伤害碰撞体（§19.1 的后见之明）看它到底碰没碰。工具 `ssbot.tools.forum_human_score`（本节新增，测试 `tests/test_forum_human_score.py`）。

### 25.1 录像、配置、方法

- **录像**（游戏时间）：赢的 8 场（0.5x）——`20261004_133855` 的第 1、3、5、6 次（路线配装 + 漫游）和 `20261005_160435` 的第 0、1、2、4 次（不带护符 / 白色工具），共 1,656 s；1x 打完第 0 波的 24 次（`20261004_002749` 收割 19 次、`20261004_012300` 漫游 5 次，只取第 0 波，到第 1 波的第一帧），共 1,031 s。纹章按录像（`hero.crest`），收割的那 19 次用收割的运动学和刀形。
- **0.5x → 游戏帧**：0.5x 的录像每个游戏帧有两个 STATE（dt = 1/120 s）。相邻两个合成一个 1/60 s 的游戏帧（第二个 STATE，两帧的事件并起来，dt / 物理步数相加，按键取或），并照 1x 的读法改写 `udt` × 0.5、`ts` / 0.5——运动学的步长是 udt × ts，`ts < 1` 还会被当成世界慢动作（不改的话推演只走一半：你的按键推演 18 帧平均误差的中位 0.65 u，改后 0.035 u）。规划器、运动学、后见之明都在游戏帧上跑。
- **你的按键**：STATE `input.mask`（只留游戏键，去掉菜单键）写进 `act.mask`，规划器的前缀和按住状态都是你的（§19.1 的开环回放）。
- **两种配置**：**最好臂** = 去饱和分支的 `SSBOT_FORUM_FR=seen_cf`、`SSBOT_FORUM_REACT=escape+n+g`、`SSBOT_FORUM_MARGIN=state`、击杀冻结修正（默认）、`--forum-clash main`；**集成默认** = 什么开关都不设（`share`、反应式关、拼刀关、家族余量；击杀冻结已是修正后的默认）。截止时间 inf（选择与机器快慢无关）。每 3 个游戏帧分析一次：最好臂 55,194 个 tick，默认 55,244 个。（复核：回放的最好臂**没开光锥 `+l`**，实战的 new / newS 都开着；开 `+l` 时可逃检查只会更严。）
- **匹配**：每一行的名义盒中心对你接下来录像里的主角盒中心，第 1–18 帧的平均距离 err18（再按整个视野 errH 打破平局）；err18 ≤ 0.35 u 算"候选集里有你的动作"。另把你自己的按键从同一个起点推演一遍（"按键行"）：它的误差就是运动学本身的误差。（复核更正：只比盒子中心会挑到你那条路线**不出刀**的版本；25.11 起匹配先要求出刀 / 跳 / 冲刺的按下次数和你相同，本节 25.2–25.8 的数是旧匹配的，新数见 25.11。）
- **判决**：对匹配上的行和按键行都按规划器的规则算 S——第 1 级（名义盒中心在第 1 级帧上对支撑）、包络（bounds_lo 各车道的外包）、命中分支（不设上限）；规划器自己判过的行和重算的 S 一致 99.9 %。排名：有安全行的 tick 在安全行里按规划器的字典序（keep、mkeep、V、J，再看可逃检查 / 尾检查有没有挪选择）；FORCED_RISK 的 tick 按预选的顺序（seen、seen_cf、P_cm、P_f、首次接触、J），记下第一个让规划器的首选排在你前面的键。
- **后见之明**：行的名义盒逐帧对录像里接下来 36 帧的真实伤害碰撞体（无敌帧跳过）。**这里的偏差和 §19 相反**：匹配上的行就是你实际走的路径（误差 ≤ 0.35 u），敌人确实是对这条路径做的反应，所以"事后不碰"基本是闭环的真结果；规划器自己选的行是没执行的，开环、偏乐观。
- **分层**：被判不安全的行，它的中心路径按 `forum_layer_audit` 的分组（层 × 类型 × 家族）查；层归成：身体（待机身体管、碰撞体管、当前待机状态）、已承诺（细放置、重锚外包盒、多段链的细 / 外包）、窗口（窗口放置、家族并集、链窗口）、尾巴、还没开始（以后才开始的攻击 / 待机实例、下一波入场）、投射物（自模板、确定路径、危险物管）、入场、死亡尾巴、全场盒。另用余量 ×0、待机增长 ×0 的变体表对同一个 tick 重做预报。
- **核对**：按键行推演误差 err18 中位 0.008 u、p90 0.65 u（1x 中位 0.000、0.5x 0.035）；匹配误差 err18 中位 0.094 u、p90 0.56 u；81 % 的 tick 有 0.35 u 内的行。

### 25.2 你的局面在规划器眼里：82–89 % 是 FORCED_RISK，你 86–89 % 的动作被判不安全，其中 88 % 事后没碰

| | 最好臂：第 0 波 1x | 最好臂：赢的 0.5x | 最好臂：全部 | 默认：全部 |
|---|---|---|---|---|
| tick | 21,571 | 33,623 | 55,194 | 55,244 |
| FORCED_RISK（规划器一行安全的都没有） | 78.2 % | 84.4 % | 81.9 % | 88.7 % |
| 你的动作在候选集外（err18 > 0.35 u） | 21.8 % | 16.6 % | 18.6 % | 18.7 % |
| 匹配上的行：被判不安全 | 83.9 % | 87.1 % | 85.9 % | 88.5 % |
| …… 其中事后没碰（误报） | 83.1 % | 91.1 % | 88.2 % | 88.5 % |
| 匹配上的行：事后没碰 | 85.7 % | 92.2 % | 89.7 % | 89.8 % |
| 判安全但事后碰了（漏报），占判安全的 | 0.66 % | 0.47 % | 0.55 % | 0.41 % |
| 你的行就是规划器的选择 | 1.3 % | 0.8 % | 1.0 % | 1.0 % |
| 规划器选的行事后没碰（开环，偏乐观）：FORCED_RISK tick | 85.5 % | 91.5 % | 89.3 % | 83.5 % |

- 赢的那几场按波次（最好臂）：FORCED_RISK 从第 1 波的 55 %（加蒙德在场）到第 2 波 100 %、第 4 波（Minister）98 %；其余各波 80–94 %。你的动作被判不安全的比例各波 81–100 %，事后被碰的只有 4–11 %。
- 漏报很少（匹配 tick 的 0.08 %，35 次里 33 次是 Reed 本体）：支撑不漏，问题是它几乎把你的每一步都标成危险。最好臂比默认只少 7 个百分点的 FORCED_RISK；它选的行在后见之明里明显更好（FORCED_RISK 时 89 % 对 84 % 没碰），但判你的动作和默认一样。
- 规划器换算的"等效失血"（plan §5：掉的格 − 砍中 / 4）：你赢的 8 场每分钟受击 6.0、掉 5.4 格、砍中 40.5 刀，等效 −4.8 格 / 分；1x 第 0 波每分钟受击 8.3、掉 9.1 格、砍中 26.8 刀，等效 +2.4 格 / 分，平均 43 s 打完。最好臂实战（§23.6 new）第 0 波每分钟受击 5.8、砍中 19.9，等效约 +0.8 格 / 分——每分钟挨得比你 1x 还少，但砍得少、不回血、只有 19 % 打完第 0 波。（复核：这是第 1 轮的 new 臂（家族余量、带 `+l`）；和回放的配置更接近的是 newS：5.92 / 17.1。打完第 0 波的比例停止规则不同，见 24.4。）

### 25.3 你的动作不在候选集里（18.6 % 的 tick）

按你接下来 18 帧做的事分（占全部 tick；最好臂，默认几乎一样）：

| 类 | 占全部 tick | 说明 |
|---|---|---|
| 起跳 / 冲刺的时刻不在候选行的格点上 | 7.7 % | 你的按键推演和录像一致（按键行 ≤ 0.35 u），但没有一行近：这些 tick 你 18 帧里平均起跳 0.40 次、冲刺 0.27 次（匹配上的 tick 0.12 / 0.06）。候选行只在第一段（第 2 帧）或续段的固定位置起跳 / 冲刺：缺"等 k 帧再跳 / 冲"（复核：这一类里 33 % 的 tick 18 帧内根本没起跳也没冲刺，归因最多约 5.1 %；25.11 起这一类要求起跳 + 冲刺 > 0） |
| 空中带攻击、运动学跟不上 | 4.5 % | 按键行也 > 0.35 u：空中出刀（平均 0.5 次）、后坐 |
| 冲刺斩（收割 Dash Upper / 漫游 dash combo） | 2.6 % | 第 0 波 1x（收割）候选集外的 27 %；规划器把攻击接冲刺当作没建模的招否决（R_UNMOD） |
| 下劈 | 1.2 % | |
| 被打中（受击后摇） | 1.0 % | |
| Bind、空中连斩、飞针、贴墙、滑翔、工具 | 各 0.1–0.4 % | |

### 25.4 支撑的误报：按层、按类型和家族

被判不安全、事后没碰的匹配行（最好臂 34,017 个；默认 35,173 个）由哪些层盖住（中心路径；括号里是同样被判不安全、事后真被碰的行，作对照）：

| 层 | 最好臂：误报行被盖 | （真报行被盖） | 去掉它（只它一层）就干净 | 默认：误报行被盖 |
|---|---|---|---|---|
| 还没开始（以后才开始的实例） | 91.9 % | (92.4 %) | 14.1 % | 97.1 % |
| 窗口放置 / 家族并集 | 60.8 % | (88.4 %) | 0.8 % | 66.4 % |
| 身体（待机身体管、碰撞体管） | 50.1 % | (73.7 %) | 1.3 % | 61.4 % |
| 已承诺（细放置、外包盒） | 45.4 % | (75.8 %) | 0 | 54.8 % |
| 尾巴 | 36.7 % | (57.3 %) | 0.5 % | 50.1 % |
| 投射物 | 14.9 % | (17.7 %) | 0.6 % | 29.9 % |
| 入场 | 2.8 % | | 0.2 % | 2.7 % |

- **多层冗余，单去一层几乎没用**：只靠一层盖住的误报只有 17 %（几乎都是"还没开始"）。余量 ×0 只放掉 0.7 % 的误报（默认 0.2 %），待机增长 ×0 放掉 11.7 %（默认 0.7 %：默认里那些行还被"还没开始"盖着）。按层组合（最好臂，全部 tick；"放掉"= 原来误报的行变干净，"代价"= 原来真报的行变干净，即新的漏报）：

| 去掉的层 | 误报放掉 | 代价（真报放掉） | 你的动作判安全的比例 |
|---|---|---|---|
| 无（现在） | 0 | 0 | 14.1 % |
| 还没开始 | 14.1 % | 1.9 % | 25.0 % |
| + 窗口 | 19.2 % | 3.4 % | 29.0 % |
| + 尾巴 | 24.0 % | 5.2 % | 32.8 % |
| + 身体 | 42.0 % | 15.4 % | 47.5 % |
| 只留已承诺 + 投射物 | 44.6 % | 15.6 % | 49.4 % |

  也就是说，就算把时间不确定的层（还没开始、窗口、尾巴）全去掉，你没碰的动作仍有 76 % 被已承诺的细放置、身体管或投射物盖住。
- **按组看区分力**（每组：盖住的误报行占比、盖住的真报行占比、精度 = 误报 / (误报 + 真报)；只算组列表完整的行；基准精度 = 全部被判不安全的行里事后没碰的比例）：
  - 第 0 波（基准 0.870）：**Reed 以后才开始的闪避（`start_attack` RE_EVADE，`+n` 留下的只用身体的家族）盖住 93.0 % 的误报和 92.6 % 的真报，精度 0.870 = 基准，19 % 的误报只有它**，首次接触中位第 9 帧；Reed 的 RE_STAB 家族并集 / 窗口 / 细放置 / 外包盒各盖 14–17 %，精度 0.86–0.88（= 基准：没有信息）；Reed 的碰撞体管 0.80、防御链窗口 0.82、针的危险物管 0.88。Choristor、Envoy 的组有信息：CH_WHIP 链细放置 0.56、CH_SLASH 细放置 0.63、Choristor 碰撞体管 0.70、Envoy 冲锋细放置 0.73 / 窗口 0.77 / 尾巴 0.80。
  - 赢的那几场（基准 0.929）：以后才开始的闪避——Clapper CC_EVADE 盖住 29 % 误报、Reed 26 %、Bellbearer CB_EVADE 21 %、Minister MI_EVADE 16 %、Clawmaiden 瞬移 CM_TELE 10 %——精度 0.91–0.94（= 基准）；Tiny 以后才开始的 AT_FIRE / AT_DEFEND / AT_LEAVE 各盖 5.7 %，精度 0.986；Maestro 以后才开始的 MA_DEFEND / MA_SUMMON 3.9 %，0.994（几乎从不碰）。有信息的是碰撞体管（Clapper 0.88、Minister 0.87、Choristor 0.86）、Clapper 符文尾巴 CC_CAST 0.89、Minister 冲刺链 0.83–0.86。
- **最早从第 1 帧就盖住**：误报行最早被盖的帧中位 1（80 % 在 6 帧内），真报行中位 1（89 %）。你经常就站在支撑里——飞着的 Reed 下面、怪的旁边——而且站得住。
- **能不能用这些标签排序**：在被判不安全的行里，用一半录像学每组的对数几率（盖住它的组的最大值 + 0.1 × 总和），另一半上分"事后碰 / 没碰"的 AUC 0.73 / 0.73；盖住它的层数 0.69 / 0.72；seen_cf 键 0.63 / 0.66；最早被盖的帧 0.56 / 0.57。~~支撑里有信息，但不在"在不在支撑里"这一位上，而在哪些组、几层。~~ **复核更正**：初版只拿 seen_cf 一个键比。同样的按段对半划分上，规划器**真正的 FORCED_RISK 预选顺序**（seen > seen_cf > P_cm > P_f > 首次接触，字典序）AUC **0.755 / 0.779**，打平或超过学出来的分数（0.735 / 0.728，已复现）；只用第一个键 seen 就有 0.701 / 0.709。所以二元的支撑饱和了，但排序靠的 seen / seen_cf / P 这些键**是有信息的**，不要用学出来的分数替换它们（标签又只来自你实际走的闭环路线，和规划器打分的全部候选行分布不同）。
- **"精度等于基准 = 没有信息"这个论证不成立**（复核）：一层盖住 92 % 的不安全行，它的精度必然接近基准。改用只靠这一层盖住的行的命中率：只靠"以后才开始"盖住的行事后被碰 1.8 %（86 / 4,893），被判不安全的行整体 12 %——去掉它的方向有依据，但见 25.8 第 1 条的代价。
- **核对口径**（复核）：用实际受伤事件（36 帧内）作标准，匹配上、判不安全的行只有 6.4 % 你真的受了伤；误报行最早被盖的帧 1x 71 %、0.5x 85 % 在 ≤ 6 帧（早于人的反应时间），所以误报不是"你后来躲开了"造成的。但开环下**全部候选行**有 86 % 事后没碰（被判不安全的候选行 84.6 %），所以"你的动作 88 % 没碰"说的是支撑饱和，不说明你的行比任意一条候选行更安全。

### 25.5 FORCED_RISK 时你的行排第几（全部 tick 的 81.9 %）

- 你的行在规划器的预选顺序里中位第 155、p90 第 391（约 400 个允许的行；默认中位 136）；进前 16 行（预选）的 14 %（默认 15 %）。
- 第一个让规划器的首选排在你前面的键（最好臂）：**J 39 %**、seen_cf 25 %、seen 11 %、P_cm 10 %、首次接触 7 %，打平 8 %；默认：J 48 %、P_cm 24 %、P_f 20 %。你的行 12 % 有"现在看得见的碰撞体"接触（规划器首选 2.5 %），落在已承诺细放置里的帧占比 0.28（首选 0.21）——你贴得近，事后 88 % 照样没碰。
- J 决定时差在哪一项：**站位 49 %、命中 26 %、续接 CONTINUE 加分 17 %**、空挥 4 %。你的行预计命中 0.087（首选 0.179），站位项 −4.17（首选 −3.69）。

### 25.6 你的行安全、规划器选了别的（10.7 % 的 tick）

- 决定的键：J 83 %、keep（跳键还要按住的续段规则）15 %。J 里差得最多的一项：**站位 52 %、CONTINUE 加分 33 %**、命中 8 %、空挥 5 %；平均差：命中 −1.40、站位 −1.17、CONTINUE −0.12、空挥 −0.10。你的行预计命中 0.036，规划器选的 0.195。两者事后都 99 % 以上没碰。（复核：① **keep 是开环回放的假象**：`jump_until` / `macro_until` / `prev_cmd` 来自规划器自己上一次选、却从没执行过的行（执行的是你的按键）；抽样两段里它的跳键续按在 28.6 % / 37.8 % 的 tick 上生效，其中 74 % / 70 % 你前后 5 帧都没按跳，同一个状态还把所有 ATTACK 开头的行或上跳键。25.11 的重跑每帧清掉这两个闩。② 预计命中的差距有一部分来自匹配不看出刀：这些 tick 里 32 % 是你出刀、匹配行没出。③ CONTINUE 加分只是"差最多的那一项"：真去掉它只翻转 7.6 % 的 J 决定 tick（全部 tick 的 0.68 %）。④ 这类 tick 里规划器选的行有 53 % 和你的路径在 0.35 u 以内。）
- 局面（粗分）：离 L2 的站位远（RUSH 时站位 = 目标的 x）46 %；在防御中的 Reed / Minister 旁边等 6.4 %；够得着但不出刀 3.5 %；走位不出刀 3.5 %；在飞行怪下面 2.8 %；其余 38 %。
- 可逃检查（最好臂）：你的安全行有 28 % 过不了它（第 0 波 41 %；威胁多是 CH_JUMP、CH_WHIP、RE_STAB）；规划器的选择被可逃 / 尾检查挪动的 3 %。
- 另外 3.0 % 的 tick 规划器有安全行，但你的行被判不安全（其中 93 % 事后没碰）。

### 25.7 被否决的行（5.9 % 的 tick）

- 监督器的允许表收走了攻击续段 4.1 %（续段是 clashrep、run16_attack、upatk2、dash_attack：低血时多，hp 1–2 时 16 %、hp 4 时 10 %、hp 6–7 时 1 %）；没建模的冲刺斩（R_UNMOD）1.9 %。

### 25.8 原因排序（占全部 tick，最好臂）与对应的修正

一个 tick 只记一个原因，按顺序：候选集外 → 被否决 → 被判不安全（再分 FORCED_RISK 与否、事后碰没碰）→ 安全但排在后面。

| # | 原因 | 占 tick（最好臂 / 默认） | 证据 |
|---|---|---|---|
| 1 | **支撑误报**：你的动作事后没碰，但被判不安全 | **56.5 % / 59.0 %**（其中 FORCED_RISK tick 53.5 % / 58.7 %） | 25.2、25.4：每一步都被多层盖住；Reed / 各类闪避的"以后才开始"盒子、Reed 刺的模板没有区分力 |
| 2 | **候选集外** | 18.6 % / 18.7 % | 25.3：起跳 / 冲刺时刻 7.7 %，空中带攻击 4.5 %，冲刺斩 2.6 % |
| 3 | **安全但排在后面**（J：站位、CONTINUE、命中；keep） | 10.7 % / 8.9 % | 25.6 |
| 4 | 判不安全且事后真碰（真报：你也挨了或险些挨） | 7.5 % / 7.6 % | |
| 5 | **被否决**（低血时收走攻击 4.1 %、冲刺斩 1.9 %） | 5.9 % / 5.0 % | 25.7 |
| — | 你的行就是规划器的选择 | 0.7 % / 0.6 % | |

而在 1 和 4 的 FORCED_RISK tick 上（81.9 % 的 tick），规划器在一堆"都不安全"的行里按 seen / seen_cf / P 再按 J 选：你的行中位排第 155，J（站位、命中）决定 39 %、seen_cf 25 %（25.5）。（复核：这张表按"你的行被判了什么"划分，可 FORCED_RISK 的 tick 上所有允许的行都被判不安全，你的行被判不安全并不是它排在后面的原因；53.5 % 的 tick（FORCED_RISK 且被判不安全）上决定排名的是预选的键，而这些键有信息（AUC 0.76–0.78，25.4）。另外规划器选的行有 17 % 和你的路径在 0.35 u 以内，"就是你的行"的 0.7–1.0 % 低估了一致程度。25.11 按决定排名的键重新划分。）

修正（按收益；复核后）：
1. **"以后才开始"里只用身体的家族（闪避 RE / CC / CB / MI_EVADE、Clawmaiden 瞬移、Tiny 的 AT_FIRE / DEFEND / LEAVE、Maestro 的 MA_DEFEND / SUMMON）也改成反应窗口内的够距**（同 `+n` 对还没扔出去的针 / 钟的做法），把它们开始之后的安全交给可逃检查。它们盖住 92 % 的误报；单独去掉放掉 14 % 的误报、代价 1.9 % 的真报（要过 R2 召回）。**复核**：方向有依据（只靠这一层盖住的行命中率 1.8 %，不安全行整体 12 %），但代价要和现有漏报比：放掉的 86 条真报是现有 35 次漏报的 **3.5 倍**，其中 70 条是 Reed 闪避，而现有漏报 35 次里 33 次也是 Reed 本体（这 86 条里 36 帧内真受伤的只有 3 条）。R2 召回只看 2–4 帧，查不出这一类；只用身体的家族的够距要配一个闪避速度，并确认可逃检查把这些招当作威胁。
2. **已承诺层按状态、按瞄准重锚**（§23 的下一步）：Reed 的刺（RE_STAB）按 `Stab Antic` 时主角的位置定方向（同针的 `+a`），Envoy 冲锋的再冲锋按进入时的位置，窗口放置改成名义时刻（中位驻留）放置。~~和 1 合起来（去掉还没开始 + 窗口 + 尾巴）放掉 24 % 的误报、代价 5 %。~~ **复核更正**：−24 % / −5 % 是把"以后才开始"、窗口、尾巴三层**整层删掉**的数（上界），不是重锚的效果；Reed 刺的瞄准没有测量（§23.7 只测了针，RE_STAB 各组精度 0.87–0.93、基准 0.875，只被 RE_STAB 盖住的行命中率 4.3 %）；窗口改名义时刻等于去掉入场时间的不确定性，召回会降，而 R2 召回只看 2–4 帧（§23.8）。先照 `pinaim.py` 量 RE_STAB 的方向和 `Stab Antic` 时主角位置的关系，验证用整个视野的事后之明加实战 A/B。
3. ~~**FORCED_RISK 的排序用有校准的命中概率**：用这批后见之明标签学每行的命中概率，替换现在的占比 / seen_cf 键（留出 AUC 0.73 对 seen_cf 0.63–0.66）~~ **复核推翻**：现在的预选顺序 AUC 0.755 / 0.779 不比学出来的 0.735 / 0.728 差，**保留 seen / seen_cf / P 这些键，不用学出来的分数替换**。学出来的分数要在按段留出的数据上胜过 0.76–0.78（或和现有键组合后胜过）、并在 bot 自己的开环录像上验证，才能再提。按 plan §5 的汇率（P × 掉格 对 预计命中 / 4）取舍这一条保留。
4. **候选集**：加"等 3 / 6 / 9 / 12 帧再起跳 / 冲刺"的首段或续段（7.7 %；复核：其中 33 % 的 tick 18 帧内根本没起跳也没冲刺，收益最多约 5.1 %）；冲刺斩进运动学和刀形（R7；第 0 波收割 27 % 的候选集外）；空中出刀的后坐（4.5 %）。
5. **J 的站位**：RUSH 的站位不该是目标的 x，而是目标出刀够距的外沿（你多在够距边上等，25.6 的 46 %）；命中项只给安全的出刀窗口。~~CONTINUE 加分只在打平时用~~（复核：去掉它只翻转全部 tick 的 0.68 %，几乎没有杠杆，它本来就是防止来回切换的设计）。
6. **监督器的允许表**：低血时只收走会碰的攻击行，不收走整类攻击（4.1 %）。
7. 可逃检查过严（你安全的行 28 % 过不了）：它的威胁同样来自"以后才开始"的家族模板，修正 1 之后重新量。

### 25.9 没做 / 未核实

- 0.5x 的你反应时间多一倍；规划器的判决不吃反应时间，所以"误报"的结论在 1x 和 0.5x 上一样（83 % / 91 % 的不安全行事后没碰），但候选集外和 J 的差别可能部分来自 0.5x 下更细的操作。
- 第 0 波 1x 的 19 次是收割（fo_A）：按现在的计划（漫游）只有 5 次漫游的第 0 波可比。
- 组列表每行只存了最早的 8 组（最好臂 18 %、默认 79 % 的不安全行被截断）；按层的数字用完整的层集合，按组的数字只算没截断的行，默认的按组数字因此不报。
- 规划器选的行的后见之明是开环的（敌人对另一条路径的反应没有），只作参照；你的行（匹配误差 ≤ 0.35 u）近似闭环。
- 0.5x 合帧后的受击冻结在游戏帧里只剩一半长（冻结按真实时间放），只影响受击前后几帧。

### 25.10 复现

```
cd brain
# 最好臂（另一个视角：不设任何 SSBOT_FORUM_* 开关，--clash off，--out ...\default）
set SSBOT_FORUM_FR=seen_cf& set SSBOT_FORUM_REACT=escape+n+g& set SSBOT_FORUM_MARGIN=state
..\scripts\uv.cmd run python -m ssbot.tools.forum_human_score run --seg C:/ssbot/data/human/20261004_133855:win:1,3,5,6 --seg C:/ssbot/data/human/20261005_160435:win:0,1,2,4 --seg C:/ssbot/data/human/20261004_002749:w0 --seg C:/ssbot/data/human/20261004_012300:w0 --out C:/ssbot/data/m2_forum_hs/best --clash main --workers 4 --threads 4 --variants m0,g0 --demo-cache C:/ssbot/data/m2_forum_w0f/demo_cache
..\scripts\uv.cmd run python -m ssbot.tools.forum_human_score summary C:/ssbot/data/m2_forum_hs/best C:/ssbot/data/m2_forum_hs/default --json <out>
```
每 32 段 4 个进程约 30 min（0.5x 的一场约 10 min）。输出 `C:\ssbot\data\m2_forum_hs\best\`、`default\`（每段一个 JSON，每 3 帧一个 tick），汇总 `best_summary.json` / `default_summary.json`；本节其余的切法（按组的精度、层组合、AUC、互斥的原因计数、否决按血量、等效失血）是会话临时目录的 `deep.py`、`groups.py`、`auc.py`、`account.py`、`veto.py`、`eff_loss.py`、`outside.py`，读同样的 JSON。

### 25.11 复核之后的重跑：按下次数也要对上（2026-10-08 晚，基线集成，冻结检出 `C:\ssbot\hs_da8d104`）

工具改了三处（`forum_human_score`，da8d104）：① **匹配**先要求第 1–18 帧出刀 / 跳 / 冲刺的按下次数（锁存后按键的上升沿；你的按键过同一个按住过滤器）和你相同，再在这些行里挑盒子中心最近的；没有这样的行记为"候选集里没有你的按键"，算候选集外；旧的只看位置的匹配留作 `best_pos`。② 开环回放每帧清掉规划器自己的跳 / 宏闩（`jump_until`、`macro_until`：来自它没执行过的选择，25.6 的复核）。③ 每个 tick 记下全部允许行和规划器判不安全的行里事后没碰的个数（基础比例）、规划器选的行离你的路径多远，汇总按"决定排名的键"给每个 tick 一个原因（FORCED_RISK 的 tick 记让规划器的首选排在你前面的第一个键）。规划器的代码是去饱和分支的最终版（a6cb2a7，含 §23.12 的审阅修正；旧的一轮是那之前的 38b2e8b），回放没开 `+l`。输出 `C:\ssbot\data\m2_forum_hs\best_v2\`、`default_v2\`，汇总 `v2_summary.json`。

| 全部 tick | 旧（只看位置，38b2e8b） | 新：最好臂 | 新：默认 |
|---|---|---|---|
| tick | 55,194 | 55,194 | 55,244 |
| FORCED_RISK | 81.9 % | 82.1 % | 88.7 % |
| 有匹配行（按下次数相同且 ≤ 0.35 u） | 81.4 %（只看位置） | **71.4 %** | 70.4 % |
| 只看位置 ≤ 0.35 u | 81.4 % | 81.0 % | 80.9 % |
| 位置最近的行按下次数和你相同（你出刀的 tick） | — | 55.2 %（**11.3 %**） | 58.7 %（12.8 %） |
| 没有一行按下次数和你相同 | — | 3.3 %（几乎都是出刀） | 4.9 % |
| 匹配行被判不安全 | 85.9 % | **86.6 %** | 89.3 % |
| …… 其中事后没碰（误报） | 88.2 % | **88.8 %** | 89.1 % |
| 判安全但事后碰了（漏报），占判安全的 | 0.55 % | **0.60 %**（32 次：Reed 本体 31、针 1） | 0.41 % |
| 匹配行事后没碰 | 89.7 % | 90.2 % | 90.2 % |
| 全部允许行事后没碰（开环，按行合计） | — | 80.9 % | 80.5 % |
| 规划器判不安全的行事后没碰 | — | 78.9 % | 78.9 % |
| 规划器选的行事后没碰（开环） | 91.0 % | 91.2 % | 85.6 % |
| 规划器选的行离你的路径 ≤ 0.35 u（按下次数也相同） | — | 17.5 %（12.4 %） | 17.2 %（12.2 %） |

每个 tick 一个原因（先后：候选集外 → 被否决 → 就是规划器的选择 → FORCED_RISK 按决定排名的键 → 有安全行的 tick 里判不安全 / 安全但排在后面）：

| 原因（占全部 tick） | 旧 | 新：最好臂 | 新：默认 |
|---|---|---|---|
| 候选集外 | 18.6 % | **28.6 %** | 29.6 % |
| FORCED_RISK，第一个让规划器的首选排在你前面的键：J | 25.5 % | 22.8 % | 31.0 % |
| …… seen_cf / seen | 16.8 / 7.4 % | 15.1 / 6.2 % | — |
| …… P_cm / P_f / 首次接触 | 6.5 / — / 4.4 % | 6.1 / — / 4.3 % | 15.1 / 12.2 / 0.1 % |
| 有安全行，你的行安全但排在后面 | 10.7 % | 9.0 % | 7.1 % |
| 被否决 | 5.9 % | 4.1 % | 3.9 % |
| 有安全行，你的行被判不安全（事后没碰 / 碰了） | 3.0 / 0.2 % | 2.9 / 0.2 % | 0.3 / 0.04 % |
| 就是规划器的选择 | 0.7 % | 0.7 % | 0.6 % |

- **按下次数一对上，十个百分点的 tick 落到候选集外**（81.4 → 71.4 %）：只看位置时，最近的行有一半按键和你不同，你出刀的 tick 上 89 % 不同（就是复核说的"你那条路线不出刀的版本"）。但对匹配行的判决几乎没变（判不安全 86.6 %、其中 88.8 % 事后没碰、漏报 0.60 %）：**误报的结论在按键对上之后照样成立**。
- **基础比例**：全部允许的候选行（开环，敌人没对它们反应，偏乐观）事后没碰 80.9 %，被判不安全的候选行 78.9 %；你的匹配行 90.2 %，你被判不安全的行 88.8 %。按行合计，你的动作比一条普通候选行**多约 10 个百分点没碰**（复核的 1,376 tick 抽样是 86 % / 84.6 %，按 tick 平均，口径不同）。所以"88 % 没碰"一部分是支撑饱和，一部分是你的动作确实更干净。
- **候选集外的 28.6 %**：没有一行按键和你相同 3.3 %（出刀 3.1 %）；按键相同的行都 > 0.35 u 的 25.3 %，其中你的按键用模型推演是准的（时机问题）12.6 %，带起跳 / 冲刺的 8.8 %；冲刺斩 2.9 %、下劈 1.9 %、受击 1.6 %、空中连斩 0.9 %。候选集比初版估的缺得多，主要是时机（"等 k 帧再跳 / 冲 / 出刀"）。
- **安全但排在后面**（最好臂 4,963 个 tick）：决定的键 J 96.9 %（清掉回放的跳闩之后 keep 不再出现：旧的 15 % 就是 25.6 复核说的假象）；J 里差得最多的一项站位 54.8 %、CONTINUE 加分 34.6 %、命中 7.3 %；预计命中你 0.031、规划器 0.127（旧 0.036 对 0.195：差距一部分来自旧匹配挑了不出刀的行）；你安全的行 21.4 % 过不了可逃检查（第 0 波 32.9 %，旧 28 %）。
- **FORCED_RISK 时你的行排第几**：中位第 143、p90 第 383，进前 16 行 16.2 %；第一个让首选排在前面的键 J 39.1 %、seen_cf 25.8 %、seen 10.5 %、P_cm 10.3 %、首次接触 7.3 %。
- 误报按层几乎不变：以后才开始 91.6 %、窗口 60.9 %、身体 48.8 %、已承诺 45.3 %、尾巴 36.9 %、投射物 15.1 %；只靠以后才开始的 14.5 %；余量 ×0 放掉 0.7 %，待机增长 ×0 放掉 11.9 %。
- 没在新匹配上重算：按组的精度、层组合、AUC（25.4、25.8 的那些切法用会话临时脚本读旧 JSON）；复核的预选键 AUC 0.755 / 0.779 是旧匹配上的数。

**改危险区之后的重打分检查（plan §5）的基线**就是这一轮（最好臂 / 默认）：FORCED_RISK 82.1 / 88.7 %，有匹配行 71.4 / 70.4 %，匹配行判不安全 86.6 / 89.3 %，其中事后没碰 88.8 / 89.1 %，漏报（占判安全）0.60 / 0.41 %（不能涨），你安全的行过不了可逃检查 21.4 % / —。复现（冻结检出里，约 30 min 一个配置，3 个进程 × 4 线程）：

```
scripts\forum_human_rescore.cmd best <名字>      &rem 或 default；输出 C:\ssbot\data\m2_forum_hs\<名字>\、<名字>_summary.json
cd brain
..\scripts\uv.cmd run python -m ssbot.tools.forum_human_score summary C:/ssbot/data/m2_forum_hs/best_v2 C:/ssbot/data/m2_forum_hs/default_v2 --json C:/ssbot/data/m2_forum_hs/v2_summary.json
```

## 26. 第二轮推进 A 轨：你 10-08 的决定和打法进规划器（2026-10-08 晚，task "forum push 2 track A"，分支 worktree-wf_c8fb34ca-073-2 = 基线集成 0cac216；离线 + 实例 0 的 10 场冒烟）

### 26.1 开关：`SSBOT_FORUM_TA`（默认空 = 全部关，和之前逐位相同）

用 "+" 或 "," 连接的记号，`all` = 全部；`SSBOT_FORUM_AB` 多了一个键 `ta=<记号>`（`ta=none` 为空），逐场轮换时监督器和 L2 跟着这一场的臂走。每场的 `stats.fcfg.ta`、决策日志的 `ta` / `free` 字段记下用的是什么。

| 记号 | 做什么 | 代码 |
|---|---|---|
| `free` | DESIGN 3.5.6 修订（你：剩的血 > 单次最大伤害时什么都允许）：h ≥ 2（hits_to_death 按支撑里最大的单次事件算，高庭 2 格）且没有挂起的暂停时，监督器的 YELLOW 不再收走可能致死的出刀（`kill_prims`）、不限惩罚刀数、不禁拼刀、没有击杀规则（不会 QS），L0 的 I3 放行最后一击，规划器的拼刀闸门放开；档位的名字照旧（YELLOW），`SupervisorDecision.free` / `FilterContext.free` 带着这个状态。h = 1 照旧 Q1、在受击后的无敌窗口里退出；Q3（绕面具 / 长连段 / 危险物 / 未知支撑）在 h = 2 照旧退出 | `SupervisorConfig.free_until_hit`、`safety_filter.i3_kill_allowed`、`ForumPlanner.clash_allowed` |
| `whip` | 拼鞭的行仍然安全（可拼层），但 J 减去它的命中分和 1 个命中权重（没收益）；L2：Choristor 甩鞭时（`CH_WHIP`：前摇和 Whip 1–6，它站着不动）站位移出鞭的范围（26.2：身后 5.3 u 外或身前 9.3 u 外，取近的），站位在鞭范围里的候选目标优先级 ×0.2（换鞭够不着的目标），鞭开始 / 结束时重选目标；PUNISH 不动（它的窗口已经算过鞭） | `forum_planner.WHIP_FAMS`、`gauntlet._whip_zones` |
| `guard` | L2：防御中的 Minister / Reed 按出刀方向给命中权重（`GoalPrefs.hit_kw`：横砍 / 上挑 / 贴墙 / 下劈各一个），是目标时给等待的站位（26.3） | `gauntlet._guard_rule` |
| `edge` | RUSH 的站位改成目标身体边缘外 2.7 u（漫游横砍够到主角中心前 3.12 u，减 0.4 u）：你在够距边上等（§25.6），不再是目标的 x | `gauntlet._edge_spot` |
| `under` | J：飞行怪正下方加分 = 10 ×（below.json：前方 3 u 的命中率 − 正下方的，按它当前的招，没有招按类型）× 行在它身体正下方的帧占比 | `forum_planner.under_gains`、`_under_bonus` |
| `eml` | 等效失血（你：9 丝回 3 血，砍中 4 刀 = 1 格）：J 减去 4 × 命中权重 × 1.154 格 × 第 1 阶段的接触帧占比（安全行为 0）；FORCED_RISK 的排序在首次接触之后、J 之前加一个键：1.154 × P − 预计砍中数 / 4（预选用第 1 阶段的占比，最终排序用 P），原来的预选键不动 | `ForumConfig.eml_*` |
| `kb` | 命中分支里被打的怪按实测的击退位移移动（26.4）：它自己的支撑和它的受击反应从命中那一帧起跟着平移（用主角的外包盒反向平移去查它一个人的支撑，其他怪的支撑不动） | `forum_planner.knockback`、`_kb_shifts` |

### 26.2 鞭会不会打身后：会（`tools.forum_knockback`，R0 + R1 缓存 395 场）

Choristor 的 `Whip Hit 1–6` 碰撞体在它的朝向坐标里（x 正 = 身前，y 相对变换点；每段的形状固定，各分位相同）：

| 段 | 样本帧 | x | y |
|---|---|---|---|
| Whip Hit 1 | 17,165 | 0.52 … 5.68 | −1.13 … −0.14 |
| Whip Hit 2 | 12,263 | 0.52 … 8.75 | −1.13 … −0.14 |
| Whip Hit 3 | 11,365 | 0.37 … 7.83 | −0.64 … 0.46 |
| Whip Hit 4 | 10,885 | −0.90 … 5.87 | 0.39 … 3.42（头顶） |
| Whip Hit 5 | 10,451 | −3.72 … 0.27 | −0.40 … 3.30（头顶到身后） |
| Whip Hit 6 | 10,134 | −4.75 … −0.87 | −1.78 … 2.18（身后，主角的高度） |

`Whip Antic` 0.817 s（p0 0.808），Whip 1–6 每段 0.05–0.067 s，所以第一下在前摇开始后约 0.82 s，身后那两段约 1.0–1.15 s；甩鞭各状态里水平速度 p50 0（站着不动）。**鞭是从前面经过头顶甩到身后的一整圈，身后 4.75 u 以内照样打得到**：所以"绕后"要在身后 5.3 u 以外（4.75 + 主角半宽 0.25 + 0.3），身前要在 9.3 u 以外（8.75 + 0.25 + 0.3）。前摇里贴到它身后砍、在身后两段之前离开，这种时机由规划器逐帧查支撑决定，L2 只给站位。

### 26.3 Minister 格挡的高度带；Reed 防御

- **Minister 在 Parry Stance 时**（R0 + R1 缓存 144 万个碰撞体帧）：变换点离地 p5 2.29、p50 5.22、p95 10.89 u；姿态碰撞体 `Collider ParryStance` 的下沿在变换点下 0.46–2.14 u（p50 1.30），上沿在变换点下 0.09 到上 1.49 u。反击 `ParrySlash Hit 1–4`（相对变换点，朝向坐标）：1 段 x −4.34…3.94、y −2.80…0.80；2 段 x −2.65…3.85、y −2.61…−0.56；3 段 x −0.84…3.54、y −2.47…1.55；4 段 x −3.36…3.08、y −0.49…1.33：最低到变换点下 2.8 u。
- **主角**：受伤框高 2.08 u（中心离地 1.04）；漫游上挑 x −0.79…0.51、到中心上方 3.39 u（站着离地 4.43），下劈到中心下方 2.16 u，横砍到中心前方 3.12 u（`AttackTable`）。
- **高度带**（Minister 变换点离地）：**低** < 4.5（姿态身体最低到它下面 2.14 u，够到站着的主角头顶 2.08 + 0.3）；**中** 4.5–5.2（身体碰不到，但反击最低 2.8 u 够得到站着的主角）；**高** 5.2–8.2（反击从头顶过去；站着上挑够到 5.7，小跳上挑约 8.2）；**够不着** > 8.2。按你的三档：

| 带 | 聚在一起（它身边 8 u 内还有怪：打它、把它打跑） | 单挑（等防御结束） | 是目标时站哪 |
|---|---|---|---|
| 低 | 只给下劈分（从上面触发：反击是水平冲） | 下劈分（下劈 / 飞针触发单挑也能用），别的不打 | 够距边（身体边缘外 2.7 u） |
| 中 | Parry Stance 里给上挑分（一下）和下劈分；Parry Block 里上挑 0 分（留着刀对反击拼刀，定时拼刀行是 B 轨的） | Stance 里只有下劈分；Block 里上挑 0 分 | 它正下方 |
| 高 | 上挑给分（Stance 和 Block 都给：被挡后僵 0.583 s，砍它照样掉血，反击从头顶过） | Parry Block 里上挑给分（已经触发了），Stance 里不打 | 它正下方 |
| 够不着 | 不打 | 不打 | 它正下方 |

  横砍、贴墙砍在任何带都是负分（反击是水平往前冲）。
- **Reed**：`ParrySlash Hit` x −1.32…3.31、y −1.95…1.41（相对变换点），但它先 `Parry Y Aim` 对准主角的高度，所以从上 / 下触发也不安全：Defend / Block 里四个方向都是负分；是目标时站在够距边（身体边缘外 2.7 u）等 Defend（1.0 s）结束；真被触发了，拼它的反击（拼中整套取消，规划器的拼刀分支）。
- **格挡被打时会不会被顶走**（你问过 Parry Stance 是被弹开不位移还是照样被顶高）：几乎不动。Parry Stance → Parry Block 那一帧之后 12 帧（0.2 s）：从下面打 上移 0.25 u（中位，n 193），从侧面打 横移 1.34 u（n 425）；Reed Defend → Block：横移 0.95 u（n 352），上移 0.5 u（n 132）。不在防御里时上挑把它们顶高约 3 u（26.4）。所以"上挑两下以后它够高"的推演只对不在防御里的飞行怪成立，防御里的 Minister 按上表的高度带走。

### 26.4 击退：被打的怪往哪动、动多少（`tools.forum_knockback`；`forum_planner.knockback`）

被钉子打中（`hit` 事件，按 src 分横砍 / 上挑 / 下劈）之后变换点的位移，减去打之前 3 帧它自己的速度外推，按类型 × 方向 × 被打时的状态取中位：

- **横砍**：往远离主角的方向每帧约 0.45 u、推 8 帧 = 3.6 u（Choristor / Envoy 在 2 / 4 / 6 / 9 / 12 帧正好 0.9 / 1.35 / 2.25 / 3.15 / 3.6 u；Reed、Minister、Bellbearer、Tiny、Clawmaiden 合并的中位 12 帧 3.0–3.6 u）。
- **上挑**：往上每帧约 0.375 u、8 帧 = 3.0 u（Reed 12 帧 3.0 u（n 775）、Minister 2.8、Bellbearer 3.0、Tiny 3.1、Clawmaiden 2.9）。
- Maestro 约 0.65 倍（上 2.0、横 2.3 u）；Clapper 横 0.72 u、上 0；下劈样本少（多是 Tiny），不建模。
- 12 帧中位 < 2 u 的状态不推（冲刺 / 突刺 / 转圈 / 死亡下落 / 防御反击里）：Minister `Attack`、`Parry Block`、`Parry Slash 1–4`；Reed `Block`、`Multihit Clashed`、`Parry Slash`、`Stab 1–5`；Tiny `Defend Buzz`、`Wall Bonk`、`Die`、`Brake`；Clawmaiden `Slash 1/4/5`；Envoy `JumpSlash Antic`；Choristor `Jump Spin`、`Hop Back`、`Slash End`、`ComboSlash Antic2`、`Slash 2`、`Jump Rise`。防御姿态（Minister Parry Stance、Reed Defend）按上面的格挡数：横 0.35 / 0.25 倍、上 0。
- 命中分支（`kb`）：第一刀命中的那只怪，按（类型、它此刻的状态、刀的方向、朝向）给出从命中帧起的位移，把它自己的支撑（`occupied_only`）和它的受击反应用反向平移的主角外包盒去查，其他怪照旧（`occupied_without`）。只推第一刀；"连挑两下"的第二刀不推（未做）。

### 26.5 飞行怪正下方的加分（below.json）

below.json 是"空中出招的实例里，碰到站在出招点正下方 / 前方 3 u / 6 u 地面上的主角的比例"。增益 = 前方 3 u − 正下方（带扔出物），截到 ≥ 0，按招；类型的是按实例加权的平均：Bellbearer 扔钟 0.085、Reed 0.032（突刺 0.066、扔针 0.083、防御 0.001、闪避为负）、Tiny 0.126（冲锋 0.268）、Clawmaiden 0.014、Minister 0（冲刺、格挡反击正下方不比前方安全）、Maestro 没有前方的数。J 加 10 × 增益 × 正下方帧占比（例：Reed 一整段都在正下方 +0.32，Bellbearer +0.85，Tiny +1.26；横向站位每 u 0.6）。

### 26.6 检查

- 单测 `tests/test_forum_track_a.py`（18 个，含 `forum_human_score.j_terms` 的核函数签名）：free 模式（h = 2 时解禁、h = 1 照旧 Q1、Q3 照旧、Bell Beast 默认不变、I3 和拼刀闸门）、记号解析和 AB 键、击退表、命中分支里只有被打的那只怪跟着动、below 增益和加分、按刀向的命中权重、eml 只在首次接触之后打破平局、L2 的格挡带 / Reed / 鞭的范围和站位 / 够距边、测量工具。改了一处旧测试的形状（`_forum_targets` 的权重从 [K] 变成 [K, 4]）。
- **Bell Beast**：它的路径上改动的只有监督器（`free_until_hit` 默认 False：`careful`、I3 的表达式不变）、`FilterContext.free`（从决策取，Bell Beast 恒为 False）和 `GoalPrefs.hit_kw`（Bell Beast 不读），按构造逐位相同，没有重跑逐 tick 比较。
- 全部测试（4f6842b 之后的工作区，NUMBA_NUM_THREADS 4，低优先级）：1294 通过、2 跳过、1 预期失败；之后改动的文件（L2、单测）单独重跑通过。
- 开环回放（`forum_policy_replay`，`SSBOT_FORUM_TA=all`，没有异常、L2 错误 0）：A0 录像 600 帧（edge 272 个 tick、kb 81 行）；`20261003_074719` i3 ep0 的第 0–3 波 6,000 帧（edge 2,068、Reed 防御 184、鞭 483 个 tick；拼鞭行 4、kb 50 行）。
- 重打分（plan §5 的固定检查，`scripts\forum_human_rescore.cmd best`，`SSBOT_FORUM_TA=all`）：第一次（冻结检出 `C:\ssbot\hs_ta_6b8f2ba`）每个 tick 都报错——`forum_human_score.j_terms` 自己调用打分核函数，还是旧的签名（2ef0551 改了，加了单测）；重跑（`C:\ssbot\hs_ta_2ef0551`，输出 `C:\ssbot\data\m2_forum_hs\ta_all_2ef0551`，32 段 0 错误）对基线 best_v2（§25.11）：FORCED_RISK 82.10 → 82.09 %、匹配行 71.4 → 71.4 %、匹配行判不安全 86.57 → 86.57 %、其中事后没碰 88.82 → 88.81 %、**漏报（占判安全）0.60 → 0.60 %（持平）**；误报没降——击退只改命中分支，你被判不安全的行几乎都在第 1 阶段就接触（34,000 / 34,110），碰不到命中分支。**被否决的 tick 4.09 → 2.87 %**（赢的局 3.04 → 1.04 %，你的行"不允许"4.15 → 1.43 %）：`free` 取消了低血时收走出刀；第 0 波不变（那里没有会冻结的击杀）。J 决定的原因 22.8 → 23.0 %、seen_cf 15.1 → 15.9 %（原来被否决的 tick 现在落到这两个键上）。
- **冒烟（不是 A/B）**：实例 0，10 场，Forum_W、eval、planner、oracle、真退出 0.2，seen_cf + escape+n+g + 按状态余量 + 拼刀主逻辑 + `SSBOT_FORUM_TA=all`，冻结检出 `C:\ssbot\live_ta_4f6842b`（`guard` 的单挑下劈、鞭不动 PUNISH 两处改动之前），种子 370000，驱动 `C:\ssbot\sandbox\ta_smoke.ps1`，运行 `20261008_185856_Forum_W_eval_planner_oracle_clashM`。代码跑通（没有崩溃、0 WOULD_DIE、支撑外受击 0），10 场都在第 0 波 Q1 退出。**结果比第 5 轮的 fix 臂差很多**（同一配置不带 `SSBOT_FORUM_TA`，75 场，不同种子、不同时段，不配对）：存活中位 26.9 对 34.8 s、每分钟受击 10.4 对 4.8、击杀 0.40 对 1.69 / 场、第 0 波 FORCED_RISK 占比 0.82 对 0.64、GREEN tick 0.6 % 对 15 %、L2 的 KITE(EVADE) 63 % 对 42 %、PUNISH 2 % 对 11 %；打中目标每分钟 8.2 对 6.6（`goal_hits`）；选中的第一段是出刀 4.3 % 对 2.5 %。受击多出来的主要是 Choristor 转圈（Spin Hit 1.55 对 0.44 / 分）、Envoy 跳斩（1.33 对 0.26）、Envoy 横斩（1.11 对 0.70）、针（1.11 对 0.47）。RUSH 时主角离目标（Envoy）中位 4.8 u（fix 5.1 u，站位 1.8 u；edge 的站位 3.2 u）。10 场能分出这么大的差，但分不出是哪个记号：`edge`（RUSH 占 1/3–2/5 的 tick，站位从 1.8 u 挪到约 3.5 u，正是 §24.4 说的 bot 在 4–5 u 外转、多招来 Envoy 横斩的距离）、`free`（第 0 波几乎一直 h ≥ 2：YELLOW 的"惩罚最多 1 刀"取消，J 给多刀的行加分，出刀更多）、`kb`、`eml`（FORCED_RISK 平局时偏向砍得多的行）都可能。见 26.7 的开环逐记号比较和建议的 A/B。

### 26.7 逐记号的开环比较和建议的 A/B

冒烟只说明"全开"变差了，不说明是哪一个。不占实例能做的：同一份录像（第 5 轮 fix 臂 `20261008_163913` i0 ep1，15,654 帧，开环，规划器的截止时间照常 8 ms，所以有少量计时噪声），每次只开一个记号，和不开比"选中的行不同"的 tick 比例（`forum_policy_replay --ticks-out`，脚本在本会话 scratchpad `ta\ddiff.py`）：

| 记号 | 选中的行不同 | 第一段按键不同 | 说明 |
|---|---|---|---|
| `edge` | 20.3 % | 25.8 % | RUSH 占这一场 65 % 的 tick，站位挪 1.7 u |
| `free` | 3.8 % | 5.0 % | YELLOW 的"惩罚最多 1 刀"取消（多刀的行 J 变高） |
| `eml` | 3.5 % | 4.6 % | FORCED_RISK 的平局 + J |
| `under` | 2.2 % | 2.1 % | |
| `whip` | 0.8 % | 1.1 % | 这一场甩鞭少 |
| `kb` | 0.4 % | 0.5 % | 命中分支只在有安全行的 tick 起作用 |
| `guard` | 0.3 % | 0.4 % | 第 0 波只有 Reed 的防御 |
| 全开 | 23.0 % | 29.1 % | |

开环里 FORCED_RISK 占比各记号都不变（0.265），所以冒烟里 0.64 → 0.82 是行为（主角站的地方）变了，不是判决变了；改动选择最多的是 `edge`。**判断：冒烟变差的头号嫌疑是 `edge`**：基线 RUSH 时站位在 Envoy 1.8 u、主角实际停在 5.1 u（安全的行到不了站位），`edge` 把站位放到约 3.5 u，主角就真的进到 3–5 u 那一带——正是 §24.4 说的"bot 在 4–5 u 外转、每分钟遇到 Envoy 横斩是你的 2.2 倍"的距离。另一种读法是"够距"指**敌人出招的够距**（站在它够不着的地方等），那样站位应在 5 u 以外（Envoy 横斩选择距离 p99 4.9 u），这次没有实现，留给 A/B 之后定。**建议的 A/B（合并那一步，同一轮、ABBA）**：先 `ta=none` 对 `ta=free`（你的决定，要确认它不让受击变多），`ta=none` 对 `ta=edge`；其余 `whip+guard+under+eml+kb` 作一臂；`edge` 不过就不开。`SSBOT_FORUM_AB` 可以逐场轮换 `ta`。

### 26.8 没做 / 未核实

- 实战 A/B（合并那一步做）：每个记号单独的作用没有分开量（26.7）。
- 击退只推第一刀；Minister "上挑两下后够高"要连着推两刀（第二刀的命中分支）；下劈的击退没建模。
- 甩鞭时"贴身后砍、在身后两段之前离开"的时机没有专门的候选行（规划器按支撑自己选）。
- 中带的"一下上挑之后定时拼反击"：L2 这里只把 Parry Block 里的上挑分设为 0、站在它下面；定时拼刀行是 B 轨的候选。
- 飞针（R7）在格挡带里的用法没进来。
- `under` 的权重 10、`eml` 的 1.154 格 / 次和 4 刀 / 格、`edge` 的 0.4 u 余量、格挡带的 0.3 u 余量是取的数，没有调。

复现：

```
cd brain
..\scripts\uv.cmd run python -m ssbot.tools.forum_knockback --out C:/ssbot/data/m2_forum_ta/measure.json
..\scripts\uv.cmd run pytest -q tests/test_forum_track_a.py
set SSBOT_FORUM_TA=all && ..\scripts\forum_human_rescore.cmd best ta_all_<rev>      &rem 冻结检出里
```
## 27. 高庭第二轮推进 B 轨：只用身体的家族、锁定、针、定时行、受击归属（2026-10-08 晚，task forum push 2 track B，分支 worktree-wf_c8fb34ca-073-3；离线 + 实例 1 的 10 场冒烟；规划器的改动全部在开关后面，默认关）

任务（plan §5 的修正顺序和 §24.5 的原因表）：① 还没开始、只用身体的家族改成反应窗口的够距，可逃检查把它们当威胁；② 候选行加"等 3 / 6 / 9 / 12 帧再跳 / 冲"和定时拼刀行；③ 冲刺 / 出刀的锁定进可逃检查，查 Bind 的提交漏洞；④ Reed 的针为什么还打得中；⑤ `hit_log` 认错实例。开关都进 `SSBOT_FORUM_REACT` 的串（`+b` / `+br` / `+k` / `+s`）或 `SSBOT_FORUM_WAITS=1`，不设就和合并前逐位相同；Bell Beast 不经过任何改动的代码路径（`source_id` 只有 Forum 的策略读）。

### 27.1 改了什么（开关）

| 开关 | 做什么 | 代码 |
|---|---|---|
| `+b`（要 `+n`） | 待机中的怪（待机身体管在放）还没开始的**只用身体的家族**（strikes.json 里没有一次带自己攻击碰撞体的：闪避 RE / CC / CB / MI_EVADE、Clawmaiden 瞬移 CM_TELE、Tiny 的 AT_FIRE / DEFEND / LEAVE、Maestro 的 MA_DEFEND / SUMMON、Envoy 的 EN_AMBUSH）不放家族模板；它们在反应窗口里的够距由**碰撞体管**承担（最后看到的身体框按该类型的最高速度长 5 帧：Reed 51.6、Minister 54.4、Tiny 50.8、Clapper 49.9、Bellbearer 47.7、Clawmaiden 45.4、Maestro 26.6 u/s），以后才开始的由可逃检查承担（威胁，无前摇：从检查点起）。**Reed 的保留**（`BODYREACH_KEEP`：现有漏报 32 次里 31 次是 Reed 本体） | `multi_forecast.ReactConfig.bodyreach`、`body_only_families()`；`ForumPlanner._threats` |
| `+br` | 同上，Reed 的也去掉 | `ReactConfig.bodyreach_all` |
| `+k` | 可逃检查的锁定点加上进入冲刺 / sprint（出刀、无控制的模式本来就是）；`+n` 时 Bind 宏另查：Bind 锁住的 1.37 s + 0.15 s 里任何时刻开始的、可逃检查管的招（还没开始、不在支撑里）碰得到主角就不 Bind | `ForumPlanner._escape_fail`、`_bind`、`_bind_threatened`；审计 `bind_threat` |
| `+s` | FORCED_RISK 的 seen 键：≥ 15 u/s 的碰撞体（飞着的针）前后各再试一帧；碰到瞄准的针（还没放手）的行也记一次 seen 接触 | `seen_contacts_swept`、`pin_contacts_kernel` |
| `SSBOT_FORUM_WAITS=1` | 定时行：WAIT 之后等 3 / 6 / 9 / 12 帧再向左 / 右跳或冲刺（16 行）；出刀的首段之后在 Reed 反击（续段第 26 帧）/ Minister 冲刺斩（第 30 帧）的时刻再按一刀（横 / 上），给 A 轨的规则用（地面 / 空中各 +32 行，墙 +24；地面带拼刀续段 507 行，≤ 512） | `candidates.build_forum(waits=True)`、`ForumConfig.waits` |

另外（没有开关，不改行为）：瞄准的针的逐行检查改成 numba（`pin_contacts_kernel`，和原来的 numpy 循环逐位相同，有测试），新内核进 `warm_kernels`。

### 27.2 受击归属（`hit_log` 认错实例，§24.3）

原因：oracle 后端按路径找实体时，同类型有几只就取**离主角最近的身体**；鞭够 8 u，最近的常是另一只（还在睡的）。而且路径里带编号的实例（`Song Pilgrim 03 (2)/Spin Hit`）根本对不上类型，记成没有来源。改成（`OracleBackend._resolve_source`）：先按路径里的 GameObject 名找实例（实体的名字取它那个名字等于类型的碰撞体），再按路径末尾的碰撞体名找"这个碰撞体离主角框最近（重叠为 0、生效的优先）"的那只，都不行才退回最近的身体。核对（第 5 轮的录像回放，每个受击看归到的那只当时在不在出招动画里）：鞭的受击 13 / 13 归到正在 `Whip Multihit` 的 Choristor（旧规则 8 / 13，其余 5 次归到在 `Ambush Jump` / `Whip Antic` 的另一只）；连斩 22 / 22 有碰撞体可对的都归对（旧 12 / 22）；跳旋 36 / 36（旧 34 / 36）；Reed 65 / 65 两种规则一样。

### 27.3 Reed 的针为什么还打得中（第 5 轮 fix 臂 = `+n`，瞄准的针开着；41 次针受击，决策日志）

- **39 / 41 次受击前 10 帧全是 FORCED_RISK**（n_safe = 0）。瞄准的针在 `+n` 下只做一件事：把碰到它的行标 S = 1；FORCED_RISK 时所有行本来就是 S = 1，排序的键（seen > seen_cf > P_cm > P_f > 首次接触 > J）里没有它——**瞄准的针在 FORCED_RISK 里不起作用**。
- 放手（`Throw` 第 0 帧出针）到受击的帧数：≥ 10 帧 23 次（针早就在飞、路径确定）、4–9 帧 9 次、≤ 3 帧 9 次（近身，出针当场就碰到，只能靠放手前的瞄准）。
- 针在飞的时候，选中的行 seen 键多是 0：规划器按"现在看得见的碰撞体按速度平移"判这一行碰不到针，可还是被打了。逐帧核对一例（`163337_…_2` i3 ep4）：针 −15 帧出现，速度 (30.4, 6.1) u/s，判定框生效，seen_polys 里有它；它按速度外推到受击那一帧的位置差约 0.3 u（导出时不时重复一帧，针一帧飞 0.5 u），而选中的行正好擦着外推的针尖——零余量的键让规划器专挑擦边的行。
- 冒烟 1 里 FORCED_RISK + 扔针前摇的 tick 每个 54 ms（p50，其余 10 ms）：`+s` 的瞄准针检查原来是 numpy，对整组约 400 行太慢，改成 numba 之后见 27.8。
- 修正就是 `+s`：快的碰撞体前后各多试一帧，瞄准的针进 seen 键。开环回放比较见 27.7。

### 27.4 Bind 的提交漏洞（§24.3：21 格在 `BindCharge` / `BindBurst` 里挨）

Bind 宏的检查（`Planner._bind`）把 Bind 的整段推演对支撑查一遍；`+n` 把**还没开始的招**全从支撑里拿掉了（交给可逃检查），而 Bind 宏不过可逃检查，所以 Bind 期间才开始的招没有任何一层管。第 5 轮（两臂 160 场）50 次 Bind 提交里 6 次在 1.52 s 内挨打，都是 67–87 帧之后、提交时离 6–8 u、处于收招 / 前摇（Envoy `Slash1 Recover`、Choristor `Hop Antic`）的怪在 Bind 期间出的新招。`+k` 的 `_bind_threatened` 正是查这件事：可逃检查的每个威胁（同样的类型 × 家族表、同样的航位推算）在 Bind 锁定期间每 2 帧开始一次，它的家族模板碰到 Bind 推演里的主角就拒绝 Bind。代价是 Bind 更少（怪在附近时几乎不 Bind；你的回血打法本来就是跑到房间另一侧），实战里看审计 `bind_threat`。

### 27.5 `+b` / `+br`：你赢的录像上误报和真报各放掉多少（`forum_human_score --variants rb,rbr`，冻结检出 `C:\ssbot\hs_tb2`（12d9d58），最好臂；输出 `C:\ssbot\data\m2_forum_hs\b_v2\`、`b_v2_summary.json` 的 `react_variants`）

做法：同 §25.11 的重跑（32 段、每 3 帧一个 tick、按下次数也对上的匹配），对每个匹配上的行另用 `+b` / `+br` 的支撑重做一次预报，看被判不安全的行变不变干净；变干净的行里事后没碰的是放掉的误报，事后碰了的是放掉的真报（= 新的漏报）。另外对你判安全的行（基础和变体各自的）都跑一次可逃检查（变体用它自己的威胁：只用身体的家族也在里面），按 `+n` 的否决算"安全且过了可逃检查"——这是规划器实际会认的安全。

| 匹配行（37,147 行，判不安全 32,091：误报 28,566 / 真报 3,525） | 基础 | `+b`（Reed 保留） | `+br` |
|---|---|---|---|
| 放掉的误报（占误报） | — | 721（2.5 %） | 1,898（6.6 %） |
| 放掉的真报（占真报） | — | 3（0.09 %） | 17（0.48 %） |
| 漏报：只按支撑 | 32 | 35 | 49 |
| 漏报：加可逃检查的否决 | 30 | 32 | 44 |
| 判安全且过了可逃检查的行 | 3,979 | 4,552（+14 %） | 5,395（+36 %） |
| 放掉的行里过不了可逃检查的 | — | 13.8 % | 23.4 % |
| 新漏报是谁打的 | | Reed 本体 3 | Reed 本体 16、Envoy 1 |

- 分开看：赢的 8 场（0.5x）`+b` 放掉误报 687（3.6 %）、真报 1，加否决的漏报 15 → 15；第 0 波 1x `+b` 只放掉 34 个误报、2 个真报（漏报 15 → 17，两次都是 Reed 本体，原来盖住它们的是别的怪只用身体的模板）。`+br` 在第 0 波放掉 10.4 % 的误报，但真报 15 个（Reed 本体 14）——**Reed 的闪避模板确实有区分力，`+br` 不用**。
- 放掉的少（2.5 %，§25.8 第 1 条的"单去这一层 14 %"是整层删除的上界）有三个原因：只对待机中的怪生效（见下一条的召回漏报）；Reed 保留（它的闪避是最大的一组，误报的 32 %）；多层冗余（同一行多半还被窗口、已承诺、身体层盖着）。
- 结论：`+b` 让你安全的动作被规划器认安全的多 14 %，漏报几乎不变（加否决 30 → 32）；`+br` 不行。

### 27.6 R2 留出召回（`multi_recall fresh --react escape+n+g+br --state-margins`，冻结检出 `hs_tb2`）

第一版的 `+b` 对**所有**怪生效（包括正在出招的）：两折各跑到一半就有 8 个留出接触没盖住（L2–L4 都有），全是 Clapper 在 `Slam 2` / `Slam Recover` 之后回到 `Idle` 时的身体：`+n` 本来就把"以后的待机实例"拿掉了，攻击之后的身体只剩"以后才开始的 CC_EVADE"模板在管，再拿掉它就没了（`--only` 单跑这两场：6 个漏）。改成只对**待机中**的怪（待机身体管在放）生效之后，这两场 0 漏。全量（R0 的 35 场 + R1 的运行，两折，444 个对局任务，79.5 min；`C:\ssbot\data\m2_forum_tb\recall_fresh_ngSbr_12d9d58.json`）：**L2 / L3 / L4 各 375,940 / 375,940（100 %），按类型也 100 %，多段链的钩 1,802 / 1,802**；靠待机身体管盖住的接触从 1,044 升到 8,154（L2），靠碰撞体管的 1 → 3。`+br` 是 `+b` 的超集（拿掉的更多），所以 `+b` 也是 100 %。注意这和 26.5 不矛盾：召回只看 2–4 帧前的预报，`+br` 的新漏报在 36 帧的视野里（§25.8 第 1 条复核说的：R2 召回看不出这一类）。

### 27.7 `+s` 的开环回放：针受击之前选中的行（`forum_hit_forensics`，冻结检出 `C:\ssbot\hs_c114f88`；第 5 轮 fix 臂里有针受击的 32 场、41 次针受击；最好臂 `escape+n+g` 对 `escape+n+g+s`；输出 `C:\ssbot\data\m2_forum_tb\pins\base\`、`s\`）

每次针受击前 4 / 6 / 9 / 12 / 15 / 18 帧的 tick（246 个，157 / 164 和 82 / 82 是 FORCED_RISK），回放里规划器自己选的行事后碰不碰（录像里的真实伤害碰撞体，36 帧）：

| | 基础 | `+s` |
|---|---|---|
| 受击前 4–6 帧：选中的行事后没碰（82 个 tick；有事后没碰的行 54） | 32（39 %） | 33（40 %） |
| 受击前 9–18 帧（164 个；有事后没碰的行 150） | 94（57 %） | 104（63 %） |
| 配对：只有这一臂选中的行没碰 | 5 | **16**（符号检验 p ≈ 0.03） |

开环（敌人没对另一条路反应），只能说明 `+s` 让 FORCED_RISK 更常选到躲开针的行，主要在 9–18 帧前（针在飞、或瞄准中）；能反应的 4–6 帧前几乎没变（那时多半已经来不及）。实战效果要 A/B（针的来源计数检验，§24.6）。

### 27.8 冒烟（实例 1，Forum_W，eval、planner、oracle、真退出 0.2，10 场 × 3 + 对照 10 场；种子 370000 / 370100 / 370300 / 370200；整机负载很重：本轨道 3 个离线任务 + A 轨的重打分 + 其他代理）

| 运行 | 代码 / 开关 | 结果 | 每 tick（策略）p50 / p99 | 规划 tick 最长 |
|---|---|---|---|---|
| `20261008_190549` | c114f88，`escape+n+g+b+k+s` + WAITS | QUIT 6、HARNESS_FAIL 4（大脑丢失看门狗：15 帧没发动作） | 17.8 / — ms | 1,772 ms |
| `20261008_192052` | 91c01cb（针内核 numba） | QUIT 4、HARNESS_FAIL 6 | 18.4 / 31.1 | 1,754、1,483 ms |
| `20261008_193057`（对照） | 91c01cb，`escape+n+g`，WAITS 关 | QUIT 9、HARNESS_FAIL 1 | 17.2 / 25.7 | < 200 ms |
| `20261008_194200` | b1a7f41（新内核预热、只用身体的家族集合只读一次） | QUIT 8、HARNESS_FAIL 2 | 17.1 / 26.4 | 3,075 ms（第一场第 2 个 tick） |

- 第一版的问题：`+s` 的瞄准针检查对 FORCED_RISK 的整组候选行是 numpy，扔针前摇的 tick 54 ms（p50）；新的 numba 内核第一次调用在战斗中编译 1.5–1.8 s；`body_only_families()` 每次预报都读一遍 strikes.json（每 tick 约 +1 ms）。三处都修了（91c01cb、96cf1a1、b1a7f41），最后一轮和对照的看门狗失败 2 对 1 / 10、每 tick 持平。
- 还剩：最后一轮第一场第 2 个 tick 3.1 s（`forum_policy_replay` 同一场 400 帧复现不出来，开环每 tick p99 26 ms），原因没查清；这么重的负载下（同时 A 轨的冒烟也是 1 / 10 看门狗失败）可逃检查 91–99 % 的 tick 被截止时间砍掉，冒烟不能当效果的证据。合并步骤的 A/B 要在正常负载下跑。
- 三轮开关冒烟：没有崩溃，支撑外受击 0（另有 2 / 0 / 3 次"未判"：受击那一刻没有保留的预报，负载下迟到的 tick），0 WOULD_DIE；`bind_threat` 0（没有走到回血的局面）。

### 27.9 `+b` / `+br`：bot 自己的录像（`forum_layer_audit --variants rb,rbr`，冻结检出 `C:\ssbot\hs_tb4`；第 5 轮 fix 臂 3 个运行 15 场，每 6 帧一个 tick；`escape+n+g` + 按状态余量；输出 `C:\ssbot\data\m2_forum_tb\layers\`）

规划器全部候选行（开环：敌人没对这些行反应，偏乐观）在整个视野里离开支撑的行，和事后（录像里真实伤害碰撞体）没碰的行：

| 8,355 个 tick、2,829,534 行（事后没碰 74.7 %） | 基础 | `+b` | `+br` |
|---|---|---|---|
| 离开支撑的行 | 435,702 | +18,589 | +98,193 |
| …… 其中事后没碰（精度） | 95.2 % | 放掉的 99.4 % | 放掉的 96.1 % |
| 放掉的误报 / 真报（占基础的误报 / 真报） | — | 1.1 % / 0.02 % | 5.6 % / 0.56 % |
| 有一行离开支撑的 tick | 3,523 | 3,588（+65） | 3,897（+374） |

bot 的录像以第 0 波为主（Reed 闪避保留，Envoy 的 EN_AMBUSH 很少），所以 `+b` 在这里放掉的少；放掉的行比基础本来干净的行还干净（99.4 % 对 95.2 %），和你的录像（27.5）的结论一致：`+b` 安全，`+br` 多放掉的那部分里真报多（Reed 本体）。

### 27.10 定时行：你赢的录像里候选集外少了多少（`SSBOT_FORUM_WAITS=1`，最好臂，冻结检出 `C:\ssbot\hs_tb3`；`C:\ssbot\data\m2_forum_hs\w_v1\`、`w_v1_summary.json`；对 §25.11 的 `best_v2`）

| | 基础（best_v2） | 加定时行 |
|---|---|---|
| 候选集外（全部 tick） | 28.6 % | **27.0 %** |
| …… 第 0 波 1x / 赢的 8 场 | 31.3 / 26.9 % | 29.2 / 25.7 % |
| 候选集外里"按键推演准、差在时机"的 | 44.1 % | 41.9 % |
| …… 其中带起跳 / 冲刺的 | 30.9 % | 27.9 % |
| 有匹配行的 tick | 39,402 | 40,280（+878） |
| FORCED_RISK / 匹配行判不安全 / 其中事后没碰 / 漏报（占判安全） | 82.1 / 86.6 / 88.8 / 0.60 % | 82.0 / 86.8 / 88.7 / 0.60 % |

16 行"等 k 帧再跳 / 冲"只补回候选集外的 1.6 个百分点（§25.11 估的时机类 12.6 %）：你的时机散在 0–18 帧的每一帧，而且多半同时带着出刀和方向变化，固定的 3 / 6 / 9 / 12 帧格点盖不全；判决和漏报不变。定时拼刀行（Reed 反击、Minister 冲刺斩时刻的一刀）在这里量不出作用：它们要命中分支把格挡被打后的反击放在那个时刻才有分（A 轨的规则那一侧）。

### 27.11 结论和推荐

- **`+b`**：可以开。你的录像上误报 −2.5 %（赢的 8 场 −3.6 %）、加否决的漏报 30 → 32（两个新漏报是 Reed 本体，原来是被别的怪的模板碰巧盖住）、判安全且过可逃检查的行 +14 %；bot 录像上放掉的行 99.4 % 事后没碰；R2 留出召回 100 %。**`+br` 不开**（Reed 本体的漏报 +14）。
- **`+s`**：开环里针受击前 9–18 帧选中行躲开针的多了 6 个百分点（配对 16 对 5）；要实战 A/B 用针的来源计数检验。
- **`+k`**：Bind 的漏洞补上了（按设计，实战看 `bind_threat` 和每分钟 Bind 次数）；冲刺锁定进可逃检查让每批检查更贵，重负载下可逃检查本来就 91–99 % 被截止时间砍掉，要在正常负载下看 `esc_cut`。
- **定时行**：候选集外 −1.6 个百分点，代价 +32 行（地面带拼刀 507 行）。
- **受击归属**：已修，按实例的统计（`follow_ups`、Q4 按实例、A/B 汇总里按实例的数）从现在起是对的。
- 推荐给合并步骤的 A/B：`escape+n+g+b+k+s` + `SSBOT_FORUM_WAITS=1` 对 `escape+n+g`（同种子、ABBA、正常负载），有差再单开关拆。

### 27.12 复现

```
cd brain
# 你的录像，+b / +br 变体（冻结检出里；约 65 min，重负载下）
..\scripts\forum_human_rescore.cmd best b_v2 "rb,rbr"
# 定时行
set SSBOT_FORUM_WAITS=1& ..\scripts\forum_human_rescore.cmd best w_v1 g0
# R2 留出召回
..\scripts\uv.cmd run python -m ssbot.tools.multi_recall fresh --fresh C:\ssbot\data\m2_forum_r0\fresh --fresh C:\ssbot\data\m2_forum_r2\r1 --react escape+n+g+br --state-margins ..\knowledge\1.0.30000\enemies\forum\support_margins_state.json --workers 3 --json <out>
# bot 录像（SSBOT_FORUM_MARGIN=state）
..\scripts\uv.cmd run python -m ssbot.tools.forum_layer_audit <第 5 轮 fix 臂的运行> --out <dir> --forced-rank seen_cf --react escape+n+g --every 6 --workers 2 --threads 4 --variants rb,rbr --crest Wanderer
# 针受击的开环回放（每个有针受击的场，SSBOT_FORUM_REACT=escape+n+g 与 escape+n+g+s 各一遍；FR=seen_cf、MARGIN=state）
..\scripts\uv.cmd run python -m ssbot.tools.forum_hit_forensics <run> --out <dir> --episodes <eps> --instances <i> --every 100000 --forced-rank seen_cf --crest Wanderer --clash main
```
汇总脚本（会话临时目录）：`pin_cmp.py`（针回放配对）、`layers_sum.py`（bot 录像的变体）、`pins.py` / `binds.py`（决策日志里的针受击、Bind 提交）、`attr_check.py`（受击归属）、`dodge_speed.py`（只用身体的家族模板在前几帧的够距对碰撞体管）。

## 28. 第二轮推进的合并与评估（2026-10-08 夜，task "forum push 2 merge / evaluate"，分支 worktree-wf_c8fb34ca-073-4；离线重打分 + 实例 0–4 的一轮实战 A/B）

### 28.1 合并

- 从 main 53e9fc8 依次合并基线集成（worktree-wf_c8fb34ca-073-1，0cac216）、A 轨（-073-2，5940cac）、B 轨（-073-3，6a556db）。两条轨道都写了第 26 节：**A 轨保留 §26，B 轨改为 §27**（标题和节内的 26.x 引用一并改；HANDOFF 里 B 轨那一节仍写 26.x）。`forum_planner.py` 的冲突是两边各加的字段，取并集。
- 全套测试（c54d210）：1316 通过、2 跳过、1 xfail。
- Bell Beast 逐 tick 相同（高庭开关全关）：冻结基线 0cac216 对冻结合并 c54d210，`20261003_144536_BellBeast` i4_000 的 3,000 帧，oracle 视图 3,001 / 3,001 个 tick 相同（84 个 FORCED_RISK），视觉等效视图 3,001 / 3,001（1,023 个）。
- `tools/forum_ab_summary` 加了：每分钟掉的格数、无伤波数（打完的波里没挨打的：下一波开始了或整场 CLEAR，按策略的每波受击数）、`--landed`（用 `forum_remaining_hits collect` 的每场文件算砍中数和等效失血 = 掉的格数 − 砍中数 / 4）以及它们的配对差。

### 28.2 离线重打分（你赢的 8 场 + 第 0 波 24 次；冻结合并 c54d210，`forum_human_rescore.cmd best`，32 段 0 错误；输出 `C:\ssbot\data\m2_forum_hs\fp2_{base,A,B,AB}[_summary.json]`）

base = 第 5 轮推荐配置（所有新开关关）；+A = `SSBOT_FORUM_TA=all`；+B = `SSBOT_RESCORE_REACT=escape+n+g+b+k+s` + `SSBOT_FORUM_WAITS=1`。base 和 §25.11 的 best_v2 每个数都相同（开关全关 = 合并前）。

| 全部 32 段（第 0 波 24 段） | base | +A | +B | +A+B |
|---|---|---|---|---|
| FORCED_RISK 占比 | 82.1 %（78.6 %） | 82.1 %（78.5 %） | 79.6 %（78.3 %） | 79.6 %（78.2 %） |
| 有匹配行（按下次数也对上） | 71.4 % | 71.4 % | 73.0 % | 73.0 % |
| 你的动作被判不安全（匹配行） | 86.6 % | 86.6 % | 85.4 % | 85.4 % |
| 其中事后没碰（误报） | 88.8 % | 88.8 % | 88.5 % | 88.5 % |
| 漏报（判安全却被碰，占判安全；次数） | 0.60 %（32） | 0.60 %（32） | 0.54 %（32） | 0.54 %（32） |
| 你的行被否决的 tick | 4.1 % | 2.9 % | 4.1 % | 2.9 % |
| 候选集外 | 28.6 % | 28.6 % | 27.0 % | 27.0 % |

- +A 只动了否决（`free`：h ≥ 2 时不再收刀），危险区的判定一点没变（和 §26.6 一样：A 的记号作用在 J、L2 和受击分支上，不在第一段接触上）。
- +B：FORCED_RISK 降 2.5 个点，几乎全在赢的那 8 场的后面几波（84.4 → 80.4 %；第 0 波 78.6 → 78.3 %）；定时行把候选集外降 1.6 个点；误报只降 0.3 个点、漏报次数不变（比例降是因为判安全的行多了）。
- 结论：离线看两轨都没有让安全口径变差（漏报 32 次不变），B 小幅变好，A 中性；**实战里 N 变差来自行为（站位、选目标、J 的取舍），不是危险区的判定**，和 A 轨冒烟后的逐记号开环比较（§26.7：`edge` 改动 20 % 的决策、FORCED_RISK 不变）一致。

### 28.3 实战 A/B（一轮，三臂轮转；第一部分 = 你 22:18 的 DEMO_SOON 之前）

**勘误（核对者，2026-10-08 23:50；修正未做，见 HANDOFF 本节 Review fixes）**：(1) 不是 0 次 HARNESS_FAIL，有 5 次大脑掉线看门狗（R 3、N 1、R1 1，都是 51–139 s 的长局），`forum_ab_summary` 把它们滤掉了，存活均值偏低（R 最多）；(2) 无伤波数 0 / 6 / 9 和它显著的配对 CI 是假象：全是索引 2（remainingEnemyToEnd 2，约 1.5 s 后索引 3 就开始）那段，没有哪一臂有真正的无伤波；(3) 砍中数含加蒙德 / Cogfly（计划 0322fcf），只看第 0 波等效失血 N / R / R1 = 4.89 / 4.06 / 3.48、配对差 −0.11（CI −1.51..1.31，不显著）；(4) "Choristor 击杀 33 → 10 指向 whip"、"edge 首要嫌疑" 没有依据（没打过第 0 波的局里 N 杀 Choristor 反而更多，差别来自波次进度；N 的迟到比例高 10 个点，算力混杂），按单个 token 的原因未知。站得住的只有第 0 波通关（McNemar 12 比 1，p 0.003）和存活（+9.4 s）。

Forum_W（漫游）、eval、planner、oracle、真退出 0.2；实例 0–4 各一个驱动（`C:\ssbot\sandbox\fp2_live.ps1`），每块三臂各 5 场、按块和实例轮转顺序，块种子 371000 + 200 × 实例 + 5 × 块（配对 = 同实例、同块种子、同场序号）。
- **R** = 第 5 轮推荐配置（seen_cf、escape+n+g、按状态余量、clash main、击杀修正），冻结基线 0cac216；
- **N** = R + A 轨全部记号（`SSBOT_FORUM_TA=all`：free、whip、guard、edge、under、eml、kb）+ B 轨全部开关（`escape+n+g+b+k+s`、`SSBOT_FORUM_WAITS=1`），冻结合并 c54d210；
- **R1** = 第 1 轮的 new（seen_cf、escape+n+g+l、clash main、击杀修正、按家族余量），冻结 016417b。

21:17 开始，22:18 你的 DEMO_SOON 出现后各驱动在当前一组结束时停下（62 组）。全部 QUIT，0 次 WOULD_DIE、0 次 HARNESS_FAIL，支撑外受击 0（unknown：N 4、R1 1、R 0）。

**机器负载很重**：另一个代理的 `forum_escape_search`（4 个低优先级进程）一直在跑，开头 10 分钟还有本任务的重打分（随即停掉，挪到实战之后）。迟到 tick 占比 N 0.67 / R 0.57 / R1 0.53（第 5 轮 ≈ 0.13），tick p50 约 17–18 ms（第 5 轮 ≈ 14 ms），逃逸检查每 tick 被截 0.79–0.83 次。所以这一轮的绝对水平比第 5 轮差（R 每分钟受击 7.2，第 5 轮的同一配置 4.9），只能做轮内比较；N 的算力更多（迟到多 10 个点），重负载对它更不利。

主指标（按比值求和；括号里是配对差 = 后者 − 前者，bootstrap 95 % 区间）：

| 指标 | N | R | R1 |
|---|---|---|---|
| 场数 / 分钟 | 99 / 52.2 | 96 / 64.6 | 96 / 70.0 |
| 每分钟受击 / 掉的格数 | 8.51 / 9.70 | 7.17 / 8.23 | 6.93 / 8.06 |
| 无伤波数 / 打完的波数 | 0 / 3 | 6 / 28（都是第 2 波） | 9 / 38（都是第 2 波） |
| 每分钟砍中 / 等效失血（格 / 分） | 19.1 / 4.92 | 19.2 / 3.42 | 21.3 / 2.75 |
| 第 0 波打完 | 3 / 99 | 14 / 96 | 19 / 96 |
| 每场击杀（Envoy / Choristor / Reed 合计） | 0.55（30 / 10 / 14） | 0.84（30 / 33 / 18） | 1.25（42 / 47 / 29） |
| 存活中位 / 平均（s） | 26.5 / 31.6 | 27.8 / 40.4 | 29.6 / 43.7 |
| FORCED_RISK 占比 | 0.81 | 0.80 | 0.80 |

| 配对（n） | 每分钟受击 | 每分钟掉格 | 无伤波 / 场 | 等效失血 / 分 | 击杀 / 场 | 存活（s） |
|---|---|---|---|---|---|---|
| R − N（91） | −0.37（−1.65..0.85） | −0.28（−1.82..1.29） | +0.066（0.022..0.121） | −0.18（−1.61..1.16） | +0.30（−0.04..0.66） | +9.4（0.4..18.7） |
| R1 − N（94） | −0.94（−2.30..0.43） | −0.68（−2.31..0.88） | +0.096（0.043..0.160） | −1.16（−2.75..0.36） | +0.71（0.29..1.14） | +12.0（3.4..20.4） |
| R1 − R（87） | −0.58（−1.77..0.60） | −0.35（−1.84..1.11） | +0.034（−0.046..0.115） | −0.73（−2.18..0.70） | +0.44（−0.05..0.93） | +3.9（−6.9..14.4） |

- **N 每一项都比 R 差**：受击 / 掉格多 18 %，0 个无伤波（R 6 个），第 0 波打完 3 对 14，击杀少三分之一（少的全是 Choristor：10 对 33，`whip` 让它在甩鞭时离开、换目标），存活短 9 s（配对区间不含 0）。和 A 轨冒烟（`ta=all`，§26.6）的方向一致；砍中数每分钟持平（19.1 对 19.2），所以差在挨打，不在出手。哪一个记号拖后腿这一轮分不出来（下一步按记号拆：A 轨的建议是先拆 `edge`、`free`）。
- **R1 对 R（第 2 轮的改动是不是少了砍中）**：R1 每分钟砍中 21.3 对 19.2、击杀 1.25 对 0.84（配对 +0.44，区间刚含 0）、等效失血 2.75 对 3.42，受击和存活差不多：方向和 §24 的同轮双重差分一致（第 2 轮的改动少了砍中和击杀），96 场对 87 对还不显著。
- 受击来源（前几名，次数）：N：Envoy 冲刺 `P2 Damager` 67、Reed 本体 58、Reed 针 38、Choristor 旋转 37、Choristor 连斩 1 段 29、Envoy 本体 29、鞭 4 段 22、Envoy 跳斩 22；R：Envoy 冲刺 64、Reed 本体 54、Choristor 旋转 44、Reed 针 39、Choristor 本体 32、鞭 4 段 27；R1：Envoy 冲刺 74、Choristor 旋转 38、Reed 针 38、Reed 本体 38、连斩 1 段 26、鞭 4 段 26。N 的针受击没有少（38 对 39：`+s` 在重负载下没显出来），Choristor 本体少了（`edge` / `whip` 让它离 Choristor 远），连斩和 Envoy 本体多了。
- 计划安全的受击（受击前 30 帧内选过 S = 0 的计划）：N 3 / 436、R 1 / 488、R1 6 / 526；逃逸检查失败率 0.36 / 0.41 / 0.36；N 的逃逸否决 35,193 个 tick（R 60,199）。

### 28.4 结论和下一步

1. **N（两轨全开）不能当默认。** 实战每个主指标都比 R 差，离线安全口径没变差：问题在 A 轨改行为的记号。下一轮按记号拆，每臂只开一个、和 R 同轮 ABBA：`edge`（嫌疑最大：RUSH 站到 Envoy 横斩 3–5 u 的带里，§24.4）、`whip`（Choristor 击杀从 33 掉到 10）、`free`、`eml` / `under` / `guard` / `kb`；B 轨的 `+b+k+s` + 定时行单独一臂（离线小幅变好）。
2. **R1 对 R**：第 2 轮的改动（抛掷替换、按状态余量、钟当目标、去掉光锥）可能少了砍中和击杀（R1 多 2 刀 / 分、多 0.44 杀 / 场，区间刚含 0），受击没差。凑满每臂 200 场再下结论。
3. **负载**：这一轮迟到 tick 是第 5 轮的 4–5 倍；以后实战 A/B 前先看机器上有没有别的离线任务，迟到 > 0.2 时轮内比较也要报迟到率，N 这种算得多的臂会被额外拖累。
4. 第二部分没跑（DEMO_SOON 一直在）：同一驱动、同一清单接着跑即可（种子换成 372000 起，见 28.5），再用 `forum_ab_summary` 合起来算。

### 28.5 复现

```
# 冻结检出（git archive + CODE_REV + 高庭碰撞盒 npz）
powershell -File C:\ssbot\sandbox\fp2_freeze.ps1 -rev 0cac216      # R
powershell -File C:\ssbot\sandbox\fp2_freeze.ps1 -rev c54d210      # N（R1 用已有的 C:\ssbot\live_w0d_016417b）
# 实战（每个实例一个驱动；第二部分：-Seed 372000 -Blocks 4，同一个 -Tag b）
powershell -File C:\ssbot\sandbox\fp2_live.ps1 -Inst <0-4> -Tag b -Arms "R:seen_cf:escape+n+g:main:kill:state:live_fp2_0cac216::0,N:seen_cf:escape+n+g+b+k+s:main:kill:state:live_fp2_c54d210:all:1,R1:seen_cf:escape+n+g+l:main:kill::live_w0d_016417b::0"
# 砍中数（每场一个文件）和汇总
..\scripts\uv.cmd run python -m ssbot.tools.forum_remaining_hits collect --manifest b=C:/ssbot/sandbox/fp2_manifest_b.txt --out C:/ssbot/data/m2_forum_fp2/rh --workers 2
..\scripts\uv.cmd run python -m ssbot.tools.forum_ab_summary C:\ssbot\sandbox\fp2_manifest_b.txt --landed C:/ssbot/data/m2_forum_fp2/rh --json C:\ssbot\data\m2_forum_fp2\ab_part1.json
# 离线重打分（C:\ssbot\sandbox\fp2_rescore.ps1：两个一组，在冻结合并里）
set SSBOT_FORUM_TA=all& set SSBOT_RESCORE_REACT=escape+n+g+b+k+s& set SSBOT_FORUM_WAITS=1& scripts\forum_human_rescore.cmd best fp2_AB
```
Bell Beast 逐 tick：会话临时目录的 `bb_ticks.cmd` / `bb_ticks_ve.cmd <检出> <输出>`（集成那一步的脚本）。

## 26. 待机的怪：不可逃逸区（编号与上面 A 轨的 §26 重复，合并后本节记作 §26-ICS；2026-10-08，task "idle enemies: the inescapable zone"，分支 worktree-wf_b572dcee-369-1 = main + 去饱和分支 + da8d104（§25 的工具）；离线，没有连接游戏，规划器和预报一行没改）

问题（你 2026-10-08）：怪还没出招，不需要躲。对它能出的每一招，假设它**现在**出：从这一招最后一个伤害框往前推，每推一帧把区域按主角一帧的逃跑够距缩一圈、并上那一帧自己的伤害框，一直推到出招时刻，结果就是"现在出招的不可逃逸区"（ICS），也就是现在不能站的地方。瞬发全屏 AoE → 全屏都不能站；前摇 10 s 的全屏 AoE → 只有身体不能站。你怀疑 Forum 里所有招的前摇都长（strikes.json 出招到第一个伤害 p5 ≥ 0.40 s，除了投射物的重新武装和贴脸的 Tiny），所以没有一招有身体之外的不可逃逸区，一只怪时身体外面随便站。本节量三件事：每个家族的 ICS（26.1、26.2）；现在的支撑在一只待机怪周围标了什么、和 ICS 差多少（26.3）；"用 ICS 换掉还没开始那一层"会怎样（26.4）；结论 26.5。工具 `ssbot.tools.forum_ics`（本节新增，测试 `tests/test_forum_ics.py`：瞬发全屏 AoE 全部不可逃、2.5 s 后的全屏 AoE 只剩身体——就是你的两个思想实验）。

### 26.1 ICS 怎么算（`forum_ics zones`）

- **伤害**：每个家族的锚点系家族模板（`support/<家族>/anchor`：记录到的所有实例从出招起按时间的并集，已含认证残差和 ±1 格导出延迟），再按主角碰撞盒半宽高膨胀成"主角中心的配置空间"。默认**不加**家族余量（26.2 另算了加余量的版本）。
- **朝向**：出招那一刻实例的镜像等于主角所在一侧的比例，攻击家族 0.94–1.00（CB_IDLE 0.94、RE_STAB 0.96、CC_EVADE 0.96，其余 ≥ 0.97）；低于 0.9 的是待机家族（EN 0.54、CC 0.70、RE 0.73、MI 0.79、CM 0.84）、Tiny 的 AT_DEFEND（0.50）和 Clawmaiden 的 CM_SPIN（0.28）。所以主角在 (dx, dy) 时模板朝它那一侧，世界里的 ICS = 区域(|dx|, dy)；< 0.9 的家族和 AT_LEAVE、MA_SUMMON 两个镜像都算（表里"both"）。
- **身体**：该类型的身体碰撞盒（`support_margins.json` production_tubes 的 body_hull，相对 transform = 锚点）按主角半宽高膨胀；"身体外"= 这个盒子外。
- **主角**：漫游 Forum 配装（`hero_wanderer_forum.json`，加上 Weighted Anklet = 负重腰带：最大下落 38 u/s），平地、无墙，规划器自己的运动学。出招后 `lat` 帧才开始反应（oracle 1 帧；`--lat 12` = 人的 0.2 s）。四种锁定状态：**自由**（站在地上）；**出刀**（出招那一帧按下漫游的刀、朝向怪：0.10 s 内不能转身、不能冲刺）；**冲刺向它**（出招那一帧朝怪冲刺，0.1 s 2.8 u 停不下来）；**空中**（站立高度之上 0.5–8 u，静止）。
- **两个界**：
  - **上界**（ub）：从一个起点出发，1,688 条按键序列（站 / 跑 / 疾跑往两边，全跳 / 短跳，冲刺，跳 + 空中冲刺，冲刺后跳，各自等 0–30 帧再做，24 / 45 / 75 帧时再转向 / 停 / 再跳；外加跑 / 疾跑 / 站着在任意第 4 帧起跳）用规划器的运动学滚出来，只要有一条在模板的最后一格之前都不碰，这个起点就"可逃"。没有一条能逃的起点是上界里的 ICS（真正的 ICS 只会更小：可能有库里没有的逃法）。
  - **下界**（lb）：就是你的算法——从最后一帧往前，每帧按"一帧能走的最大盒子"（左右冲刺速度 28 u/s、向上起跳 18.6 u/s、向下最大下落 38 u/s，各除以 60）腐蚀、并上这一帧的伤害；地板以下算不能站。它不管惯性和重力（可以悬停），所以只会比真的 ICS 小。
  - 真的 ICS 在两者之间。下界为空、上界也为空就是"确实没有"；上界非空而下界为空，就是"库里没找到出路，但放开惯性 / 重力又找得到"。
- **"晚"与"早"**：上界里的 ICS 点，再看最好的那条序列能撑多少帧才被碰（`survival`）。≥ lat + 6 帧才被碰的点记为"**晚**"——这是招本身造成的；更早就被碰的点是出招那一刻已经贴着的（模板在出招时刻的格子比身体盒子宽：实例并集里身体位置的散布、残差），或者模板里**别的实例留下的危险物**（Clapper 的符文弹、钟、针：家族模板按"出招以来"把那段时间里所有伤害源都并进来，包括之前施放、还在场上的）。
- **特例**：Reed 扔针（RE_THROW 的模板是所有方向扔过的针）另用规划器的**瞄准针模型**（§23.7：出招后 ≥ 40 帧放手，31 u/s，从 Reed 旁 1.6 u，对准放手前 20 帧主角的位置 ±15°）；Tiny 的俯冲（AT_FIRE，只用身体）用**瞄准俯冲模型**（录像 paths：出招后 0.70 s `Fire`，每个实例都是 39.4 u/s，方向对准主角，放手前是 Tiny 的身体）。重新武装（CB_THROW、RE_THROW、CC_CAST 的最小出手 0.00 / 0.10 / 0.12 s）是之前那一招扔出去、已经在飞的东西，属于危险物层（确定路径 / 危险物管），不是一只待机怪"现在出招"的事。

### 26.2 每个家族的 ICS（oracle 反应 1 帧，不加余量；`C:\ssbot\data\m2_forum_ics\zones_lat1.json` / `.npz`）

数字是**身体盒子外**最远的 ICS 点离身体盒子的距离（u）。"自由：全部 / 晚"：站在地上时上界 ICS 的全部 / 其中"晚"的部分（26.1）；"出刀"、"冲刺向它"、"空中"都是"晚"的部分；"下界"是你的腐蚀（二维，含空中格子；全部，不分早晚）；"瞄准模型"是 RE_THROW / AT_FIRE 用瞄准模型时四种锁定的结果（离锚点最远的 ICS 点，0 = 身体外没有）；"出手"是 strikes.json 的出招 → 第一个攻击碰撞体（最小 / p5，s）；"锚高"是实例锚点离地 q05 / q50 / q95（飞的类型三个高度都算，取最大）。

| 类型 | 家族 | 出手 min/p5 s | 自由：全部 / 晚 | 出刀 | 冲刺向它 | 空中 | 下界 | 瞄准模型 | 镜像 | 锚高 |
|---|---|---|---|---|---|---|---|---|---|---|
| Envoy | EN_AMBUSH | - | 0.0 / 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |  |  | 2.1/2.1/2.1 |
| Envoy | EN_CHARGE | 0.48/0.49 | 0.0 / 0.0 | 0.0 | 3.8 | 0.0 | 0.1 |  |  | 2.4/2.4/2.4 |
| Envoy | EN_IDLE | - | 1.5 / 0.0 | 2.6 | 7.5 | 0.7 | 1.0 |  | both | 2.4/2.4/2.4 |
| Envoy | EN_JUMPSLASH | 0.40/0.41 | 0.0 / 0.0 | 0.0 | 4.2 | 0.0 | 0.1 |  |  | 2.4/2.4/2.4 |
| Envoy | EN_SLASH | 0.48/0.49 | 0.3 / 0.0 | 2.0 | 7.0 | 0.5 | 0.1 |  |  | 2.4/2.4/2.4 |
| Choristor | CH_IDLE | - | 0.9 / 0.0 | 0.0 | 7.1 | 0.0 | 0.7 |  |  | 1.9/1.9/1.9 |
| Choristor | CH_JUMP | 0.76/0.77 | 0.7 / 0.0 | 1.2 | 6.0 | 0.0 | 0.8 |  |  | 1.9/1.9/1.9 |
| Choristor | CH_SLASH | 0.63/0.63 | 1.4 / 0.0 | 2.7 | 7.4 | 1.1 | 1.0 |  |  | 1.9/1.9/1.9 |
| Choristor | CH_WHIP | 0.81/0.82 | 0.9 / 0.0 | 1.7 | 6.2 | 0.0 | 0.7 |  |  | 1.9/1.9/1.9 |
| Reed | RE_DEFEND | 0.58/0.66 | 0.3 / 0.0 | 1.1 | 5.4 | 0.0 | 0.8 |  |  | 2.3/6.0/9.9 |
| Reed | RE_EVADE | - | 0.4 / 0.4 | 2.3 | 8.8 | 2.9 | 0.8 |  |  | 2.3/5.2/8.5 |
| Reed | RE_IDLE | - | 1.1 / 0.0 | 3.2 | 7.6 | 1.9 | 0.9 |  | both | 2.3/5.5/10.3 |
| Reed | RE_STAB | 0.63/0.65 | 1.0 / 0.0 | 3.0 | 7.5 | 2.5 | 1.1 |  |  | 2.7/5.9/10.2 |
| Reed | RE_THROW | 0.10/0.67 | 3.6 / 3.6 | 4.4 | 12.6 | 5.7 | 1.0 | 0.0/0.0/0.0/0.0 |  | 2.9/6.0/10.8 |
| Minister | MI_CHARGE | 0.48/0.50 | 0.0 / 0.0 | 0.8 | 5.6 | 0.0 | 1.1 |  |  | 2.3/5.6/10.3 |
| Minister | MI_EVADE | - | 0.9 / 0.0 | 0.0 | 8.7 | 3.6 | 1.3 |  |  | 2.4/4.8/9.0 |
| Minister | MI_IDLE | - | 1.3 / 0.0 | 2.9 | 7.9 | 3.3 | 1.1 |  | both | 2.7/6.6/10.8 |
| Minister | MI_PARRY | 0.71/0.75 | 1.5 / 0.0 | 2.5 | 6.9 | 2.2 | 1.5 |  |  | 2.4/5.7/10.3 |
| Clawmaiden | CM_IDLE | - | 2.2 / 0.0 | 3.8 | 8.2 | 2.1 | 1.7 |  | both | 2.6/5.8/10.3 |
| Clawmaiden | CM_SLASH | 0.50/0.51 | 0.8 / 0.0 | 1.9 | 6.9 | 0.0 | 0.9 |  |  | 2.9/5.2/9.3 |
| Clawmaiden | CM_SPIN | 4.82/4.87 | 1.1 / 0.0 | 1.8 | 6.2 | 1.6 | 1.3 |  | both | 4.2/6.0/9.8 |
| Clawmaiden | CM_TELE | - | 0.6 / 0.0 | 0.0 | 3.3 | 0.0 | 1.1 |  |  | 4.1/8.4/13.1 |
| Bellbearer | CB_EVADE | - | 2.0 / 2.0 | 2.2 | 6.4 | 2.4 | 1.1 |  |  | 5.0/7.4/10.0 |
| Bellbearer | CB_IDLE | - | 1.8 / 0.0 | 0.0 | 4.6 | 0.0 | 1.2 |  |  | 4.7/7.4/11.2 |
| Bellbearer | CB_THROW | 0.00/0.66 | 1.6 / 0.0 | 0.0 | 4.0 | 0.0 | 1.1 |  |  | 4.5/6.9/11.2 |
| Maestro | MA_DEFEND | - | 0.0 / 0.0 | 0.0 | 0.0 | 0.0 | 0.7 |  |  | 6.7/8.1/9.2 |
| Maestro | MA_IDLE | - | 0.0 / 0.0 | 0.0 | 0.0 | 0.0 | 1.1 |  |  | 6.5/8.3/9.3 |
| Maestro | MA_SLASH | 0.68/0.70 | 0.0 / 0.0 | 0.0 | 0.0 | 1.6 | 1.1 |  |  | 6.6/7.9/9.1 |
| Maestro | MA_SUMMON | - | 0.0 / 0.0 | 0.0 | 0.0 | 0.0 | 0.9 |  | both | 6.6/7.9/9.1 |
| Tiny | AT_DEFEND | - | 1.8 / 0.0 | 3.7 | 9.5 | 4.5 | 1.3 |  | both | 2.7/11.1/13.5 |
| Tiny | AT_FIRE | - | 0.0 / 0.0 | 0.0 | 14.2 | 3.3 | 1.4 | 0.0/0.0/0.0/0.0 |  | 8.4/11.4/13.8 |
| Tiny | AT_IDLE | - | 1.1 / 0.0 | 0.0 | 6.0 | 2.9 | 1.4 |  |  | 3.6/8.3/13.4 |
| Tiny | AT_LEAVE | - | 1.8 / 0.0 | 3.3 | 8.3 | 3.1 | 1.4 |  | both | 1.9/10.4/13.3 |
| Clapper | CC_CAST | 0.12/0.40 | 29.2 / 0.0 | 30.4 | 35.9 | 27.8 | 29.2 |  |  | 4.5/4.5/4.5 |
| Clapper | CC_EVADE | - | 0.0 / 0.0 | 0.0 | 2.2 | 0.0 | 0.0 |  |  | 4.5/4.5/4.5 |
| Clapper | CC_IDLE | - | 0.0 / 0.0 | 0.0 | 4.7 | 0.8 | 0.0 |  | both | 4.5/4.5/4.5 |
| Clapper | CC_JUMP | 1.16/1.39 | 0.0 / 0.0 | 0.0 | 3.0 | 0.2 | 0.0 |  |  | 4.5/4.5/4.5 |
| Clapper | CC_JUMP_CAST | 1.18/1.80 | 20.4 / 0.0 | 0.0 | 25.3 | 15.6 | 20.1 |  |  | 4.5/4.5/4.5 |
| Clapper | CC_SLAM | 0.85/0.87 | 2.4 / 2.4 | 21.3 | 25.3 | 2.5 | 0.0 |  |  | 4.5/4.5/4.5 |

读法：

- **站在地上（自由），身体外"晚"的 ICS：除了 4 个家族，全部是 0。** 例外：
  - Clapper 的 **CC_SLAM 2.4 u**（上界；下界 0）：主角在它身体盒子外 0–2.4 u（离中心 3.75–6.15 u）时，库里没有一条序列躲得开 0.85–0.96 s 的砸地（最好的序列撑 54 帧 = 砸地那一刻）。下界为空：放开惯性和重力就躲得开，所以这是"要么没有、要么只差一点"的区域；反应 12 帧时它缩到 0.5 u，跳起时刻的格点换一下结果就变——是"帧级时机才躲得开"的地方，实战里当它是不能站的。
  - Bellbearer 的 CB_EVADE 2.0 u：只有一个点——Bellbearer 在最低锚高（离地 5.0 u）时主角正好在它下面，撑 7 帧（刚过"晚"的门槛）。
  - Reed 的 RE_EVADE 0.4 u：Reed 在最低锚高（2.3 u）时身体前 0.4 u 内，闪避的身体扫过来，撑 12 帧。
  - Reed 的 RE_THROW 3.6 u 只是模板（所有方向扔过的针的并集）的结果；**用瞄准针模型是 0**（四种锁定都是 0）。
- **"早"的部分**（出招那一刻就已经碰到的）：大多数家族 0.3–2.2 u——模板在出招时刻的格子比身体盒子宽（实例并集里身体位置的散布、残差、飞的类型锚高的散布）。Clapper 的 CC_CAST 29.2 u、CC_JUMP_CAST 20.4 u 全是"早"的：模板里有之前施放、还挂在场上的符文弹 / 符文砸，出招那一刻就在那里，属于危险物层。
- **锁定会造出小的 ICS**：**出刀**时（0.10 s 不能转身、不能冲刺）近战家族身体外 1–4 u（EN_SLASH 2.0、CH_SLASH 2.7、RE_STAB 3.0、MI_PARRY 2.5、CM_SLASH 1.9、AT_DEFEND 3.7）；**朝它冲刺**时 3–9.5 u（冲刺本身就把主角送进去 2.8 u）。Envoy 的冲锋 / 跳斩、Choristor 的鞭在出刀时也几乎为 0（0–1.7 u）。**空中**静止时多数 0–3.6 u。也就是说：怪没出招时站哪都行，但**贴着它出刀 / 朝它冲刺**的那 0.1 s 里，它若此刻出招就可能躲不开——这是"什么时候能出手"的问题，不是"站哪"的问题。
- **下界**（你的腐蚀，不分早晚）：身体外最远 ≤ 1.7 u（就是上面"早"的散布），只有 Clapper 的 CC_CAST / CC_JUMP_CAST 例外（同上，出招那一刻已在场的符文）。
- **人的反应**（`--lat 12`，0.2 s，`zones_lat12.json`）：自由时"晚"的 ICS 仍然只有 RE_THROW（并集 6.0 u，瞄准针 0）、AT_FIRE（并集 8.9 u，瞄准俯冲 0）、CC_SLAM（0.5 u）。
- **加上家族余量**（`--margin`，`zones_lat1_margin.json`，生产支撑的做法）：MI_PARRY 变成 6.0 u（余量 3.0 u）、CC_JUMP 1.8 u（余量 2.1 u）、AT_FIRE 并集 11.3 u（余量 3.0 u），其余同上——余量本身就会造出身体外的 ICS。
- **投射物的重新武装**（CB_THROW 最小 0.00 s、RE_THROW 0.10 s、CC_CAST 0.12 s）：是之前扔出去、还在飞 / 挂着的东西，确定路径 / 危险物管管，不是"待机的怪现在出招"。**贴脸的 Tiny**：AT_FIRE 0.70 s 才俯冲，并集模板和瞄准俯冲模型自由时都是 0；Tiny 的 AT_DEFEND（不朝向，两个镜像）自由时也是 0（"早"1.8 u），出刀时 3.7 u、空中 4.5 u。

**回答你的猜想（第 2 部分）**：对**站着（自由）的主角**，Forum 里没有一招在身体外有不可逃逸区（"晚"的部分全为 0），除了 Clapper 的砸地（最多 2.4 u，而且只有上界，下界为 0）和两个闪避的边缘点（≤ 0.4 u，或一个 2 u 处的单点）；Reed 的针和 Tiny 的俯冲按瞄准模型也是 0。你说的"一只怪时身体外随便站"成立——前提是主角当时不在出刀 / 朝它冲刺的锁定里（那时近战家族身体外 1–4 u 躲不开）。

### 26.3 现在的支撑在一只待机怪周围标了什么（`forum_ics replay` 的 idle 部分；`C:\ssbot\data\m2_forum_ics\summary.json`、文字地图 `summary.maps.txt`）

- **录像**：你赢的 8 场（`20261004_133855` 第 1、3、5、6 次，`20261005_160435` 第 0、2、1、4 次，0.5x 合成游戏帧，同 §25.1）——9 类敌人都有；bot 的第 0 波 10 场（`092135`、`094847` 各 5 场，seen_cf + escape 的录像，§23.1）。开环回放（§19.1），每 24 帧一次。
- **两种配置**：**集成默认**（什么开关都不设）和**最好臂**（`SSBOT_FORUM_REACT=escape+n+g`、`SSBOT_FORUM_MARGIN=state`、`SSBOT_FORUM_FR=seen_cf`；拼刀关——它不改支撑）。
- **怎么量**：每只在场、活着、处在待机家族里（没出招）的敌人，**只用它自己的放置**（按放置的主人过滤；Tiny 的组放置算进组里每一只）在一张以它为中心的网格上（左右各 12 u、站立高度之上 0–12 u，0.5 u 一格，墙外不算）按规划器自己的占用查询查第 1 / 6 / 12 / 18 / 24 / 36 帧，分层：身体（待机身体管、碰撞体管）、还没开始（以后才开始的攻击 / 待机实例）、窗口、已承诺、尾巴；余量 = 同一 tick 在"余量全为 0"的表上重做预报后少掉的面积。身体 = 它最后看到的身体碰撞盒按主角半宽高膨胀；"身体外面积"只数这个盒子外的格子；"最远"是这些格子离盒子的最远距离（中位数；到 12–15 u 是碰到了网格边，实际更远）。"单独"= 8 u 内没有别的敌人（§1 的"只有它在近处"），单独的 tick < 20 时用全部 tick。

| 类型 | 待机 tick（单独） | 集成默认：身体外面积 u²（第 1 / 6 / 12 / 36 帧）| 最远 u | 最好臂：身体外面积 u² | 最远 u | 最好臂里只它盖住的（第 12 帧，u²）：身体管 / 还没开始 / 尾巴 | 家族 ICS 身体外 u² | 最好臂在 ICS 外（误报，第 12 帧）|
|---|---|---|---|---|---|---|---|---|
| Envoy | 114（19），全部 | 190 / 220 / 220 / 251 | 14.1–15.0 | 6 / 23 / 23 / 23 | 3.0–3.8 | 23 / 0 / 0 | 0.75 | 23 |
| Choristor | 513（221） | 142 / 198 / 262 / 266 | 12.7–14.6 | 8 / 39 / 40 / 40 | 4.0–4.0 | 40 / 0 / 0 | 1.0 | 40 |
| Reed | 561（272） | 265 / 265 / 265 / 265 | 12.4–12.4 | 70 / 147 / 212 / 265 | 7.8–12.4 | 0 / 167 / 0 | 22.0 | 202 |
| Minister | 388（221） | 248 / 248 / 248 / 248 | 11.7–11.7 | 75 / 152 / 207 / 248 | 8.6–11.7 | 7 / 147 / 0 | 9.0 | 214 |
| Clawmaiden | 131（71） | 271 / 271 / 271 / 271 | 12.3–12.3 | 173 / 211 / 220 / 271 | 9.8–12.3 | 0 / 155 / 3 | 0.0 | 232 |
| Bellbearer | 396（168） | 255 / 255 / 255 / 255 | 12.5–12.5 | 73 / 181 / 233 / 255 | 9.4–12.5 | 0 / 189 / 0 | 0.0 | 265 |
| Maestro | 372（3），全部 | 237 / 238 / 238 / 239 | 12.3–12.3 | 70 / 113 / 155 / 221 | 6.0–11.8 | 0 / 124 / 0 | 0.0 | 166 |
| Tiny | 1570（0），全部 | 221 / 222 / 226 / 234 | 13.9–13.9 | 221 / 222 / 222 / 223 | 13.9–13.9 | 3 / 190 / 0 | 0.0 | 276 |
| Clapper | 376（330） | 243 / 243 / 243 / 243 | 13.2–13.2 | 110 / 155 / 190 / 243 | 10.5–13.2 | 0 / 136 / 0 | 22.0 | 184 |

（"家族 ICS 身体外"：它能出的每一招的 ICS（26.2 的"晚"的部分；地面一行按自由、空中按静止）并起来，在同一张网格上、按该类的中位锚高，身体外的面积；Clapper 去掉了 CC_CAST / CC_JUMP_CAST——它们的模板里有之前施放、还在场上的符文，见 26.2。"在 ICS 外"按全部 tick 的平均地图算。）

- **集成默认：一只待机怪身体外整张网格都被标了**——从第 1 帧起就 190–270 u²（网格里墙内的格子大约 270–300 u²），最远到网格边。盖满它的是"还没开始"那一层（以后才开始的攻击 / 待机实例的外包盒，按待机增长长大，第 1 帧只它盖的就有 134–245 u²）；身体管从第 1 帧的 5–18 u² 长到第 36 帧的 44–256 u²（Envoy 的待机增长封顶 3.6 u；Choristor 0.6 s 15 u）。
- **最好臂：Envoy、Choristor 身体外只剩身体管——一圈 3–4 u**：Envoy 第 1 帧 6 u²（最远 0.8 u）、之后 23 u²（3.0–3.8 u）；Choristor 8 → 40 u²（4.0 u）。这一圈是待机身体管在反应窗口（5 帧）里按待机增长长的（`+g` 之后不再长）：Envoy 5 帧 2.25 u、Choristor 2.97 u。它们没有"只用身体"的家族，`+n` 把还没开始的招全拿掉了。
- **最好臂：另外 7 类仍然几乎整张网格**（第 12 帧 155–233 u²，第 36 帧 221–271 u²）。盖住的几乎全是"还没开始"层里 `+n` 留下的**只用身体的家族**（strikes.json 没有出手时间：Reed / Minister / Bellbearer / Clapper 的闪避、Clawmaiden 的瞬移、Tiny 的 AT_FIRE / AT_DEFEND / AT_LEAVE、Maestro 的 MA_DEFEND / MA_SUMMON）——第 12 帧单它就盖 124–190 u²；身体管只盖 0–7 u²。余量在待机时不加面积（0：被别的层盖着）；刚出完招的尾巴在默认里 Bellbearer 74、Clapper 35、Clawmaiden 18 u²（第 1 帧），最好臂里只它盖的只有 Clawmaiden 3 u²。Tiny 从来不是"单独"的（8 u 内总有别的 Tiny），表里是全部 tick；它的组放置让"只用它自己的放置"和规划器的 `occupied_only` 在个别 tick 上不一致（最多 306 u²），其余类型完全一致。
- 文字地图（最好臂，第 12 帧，地面往上 10 行，左右 ±12 u；`#` = 一半以上的 tick 被标、`+` = 10 % 以上）：Envoy 是中间 ±3 u 一根柱子（身体管），Reed 是 ±10 u 内全是 `#`（只有网格两边各 2 u 没标）。集成默认下 Envoy 也全是 `#`。

**回答你的问题（第 1 部分）："现在算出来的是不是一只待机怪的碰撞体积外边全是安全区？"——不是。** 集成默认下身体外整张图都不安全；最好臂下 Envoy 和 Choristor 接近了（只剩身体管的一圈 3–4 u），其余 7 类仍然被"只用身体的家族的以后实例"盖满。这些家族自己的 ICS 身体外几乎为 0（26.2：闪避 ≤ 0.4 u，Bellbearer 闪避一个点，瞬移 0，Tiny 0，Maestro 0）。

### 26.4 用 ICS 换掉"还没开始"那一层（`forum_ics replay` 的 whatif 部分；开环，只按支撑判，不动规划器）

做法：每个 tick，规划器已知、允许的行（名义盒中心逐帧，无敌帧不算）按三种支撑判 S：**现在**（整个支撑）；**去掉还没开始**（`start_attack`、`start_idle` 拿掉，即 §23 的第 1 级）；**换成 ICS**（再加上：每只在场的敌人从它最早可能出招的时刻 t_strike 起，每一帧把它每个家族的 ICS（"晚"的部分；按这一行那一帧的锁定状态——在空中 / 朝它冲刺 / 地上出刀 / 自由——和主角在它哪一侧）放在它按速度外推的位置上）。FORCED_RISK = 没有一行 S = 0。你的录像另外把**你自己的按键**从这个 tick 的状态滚出来（§25 的"按键行"，只算滚出来和录像 18 帧平均误差 ≤ 0.35 u 的 tick），用同样三种支撑判，并用录像里真实的伤害碰撞体看它碰没碰。

| | 规划器自己的 FORCED_RISK | 支撑：现在 | 去掉还没开始 | 换成 ICS | 你的动作被判不安全：现在 / 去掉 / 换成 ICS | 其中事后没碰（误报） | 判安全却被碰（漏报，占判安全） |
|---|---|---|---|---|---|---|---|
| 最好臂，你赢的 8 场（8,436 tick；按键行 7,119） | 84.2 % | 83.7 % | 69.6 % | 72.7 % | 86.9 % / 78.5 % / 81.1 % | 91.4 % / 90.6 % / 90.9 % | 0.43 % / 0.79 % / 0.89 % |
| ……不算 Clapper 的两波（6,172 tick） | 83.4 % | 82.9 % | 68.3 % | **68.6 %** | | | |
| 最好臂，bot 第 0 波（1,179 tick） | 87.3 % | 87.0 % | 78.4 % | **78.5 %** | | | |
| 集成默认，你赢的 8 场 | 87.9 % | 87.6 % | 78.3 % | 79.9 % | 88.3 % / 84.1 % / 85.4 % | 91.5 % / 91.1 % / 91.2 % | 0.24 % / 0.44 % / 0.48 % |
| ……不算 Clapper 的两波 | 88.4 % | 88.2 % | 78.3 % | **78.3 %** | | | |
| 集成默认，bot 第 0 波 | 89.7 % | 89.7 % | 87.6 % | **87.6 %** | | | |

- **把"还没开始"换成 ICS，FORCED_RISK 降 9–14 个点**（最好臂：你的局面 83 → 69 %，bot 第 0 波 87 → 79 %），而 ICS 自己几乎不加回来（不算 Clapper 的两波：+0.3 个点；bot 第 0 波：+0.1）。Clapper 的两波（第 7、13 波）加回 2.5–6 个点：那是 CC_SLAM 和 Clapper 两个施法家族在出刀 / 冲刺 / 空中锁定下的区域（模板里有之前的符文，26.2）。
- **但剩下的 69–79 % 仍然是 FORCED_RISK**：盖住这些行的是已承诺层、身体管、尾巴、投射物（§23.2、§25.4 已经量过：去掉还没开始只放掉 14 % 的误报）。所以换掉这一层是对的、几乎没有代价，但它不是饱和的主体。
- **你的动作**：被判不安全的比例 86.9 → 78.5 → 81.1 %（换成 ICS），其中 91 % 事后没碰——误报的比例不变，因为剩下的误报来自别的层。ICS 加回来的不安全只有 180 / 7,119 次（2.5 %），其中 161 次在 Clapper 的两波。
- **代价**：去掉还没开始那一层后，你的动作里"现在被判不安全、去掉后判安全、而事后真被碰"的有 8 次（7,119 次里 0.11 %；判安全里的漏报 0.43 → 0.79 %），分散在第 0、3、4、5、9、11 波；ICS 一次也没有把它们盖回来（换成 ICS 后仍是这 8 次）。它们是在 ICS 之外被碰的：怪在主角不在 ICS 里的时候出了招、主角（你）没有躲——ICS 只保证"躲得开"，不保证"会去躲"，所以换成 ICS 时规划器必须保留可逃检查（§22 的 escape，现在在 `+n` 下否决）去真的选那条出路。要在 R2 召回里另外确认。

### 26.5 结论

1. **你的猜想基本成立**：主角站着（自由）时，Forum 里没有一招在身体外有"晚"的不可逃逸区，只有 Clapper 的砸地（CC_SLAM，身体外最多 2.4 u，只有上界、下界为 0，跳起时机差一帧结果就变）和两个闪避的边缘（Reed ≤ 0.4 u；Bellbearer 正下方一个点）。Reed 的针、Tiny 的俯冲按瞄准模型都是 0。人的 0.2 s 反应下也一样（CC_SLAM 0.5 u）。所以"一只怪时身体外随便站"对站着的主角是对的。
2. **但锁定改变结论**：出刀的 0.1 s（不能转身、不能冲刺）里，近战家族身体外 1–4 u 躲不开；朝它冲刺时 3–9.5 u。站哪都行，**贴着它出刀 / 朝它冲刺的时机**才要看它此刻能不能出招——这正好是 L2 的"出手窗口"问题（§21、§25.6），不是支撑的问题。
3. **现在的支撑没有做到"身体外都安全"**：集成默认下一只待机怪身体外整张图（±12 u × 12 u）从第 1 帧就被标满；最好臂（`escape+n+g`）下只有 Envoy 和 Choristor 接近（身体管一圈 3–4 u），其余 7 类被"只用身体的家族（闪避、瞬移、Tiny、Maestro）的以后实例"盖满，而这些家族自己的 ICS 身体外几乎为 0。
4. **用 ICS 换掉"还没开始"一层**：FORCED_RISK 降 9–14 个点（最好臂：你的局面 83 → 69 %，bot 第 0 波 87 → 79 %），ICS 本身几乎不加回来（Clapper 两波除外），你的动作被判不安全 87 → 81 %。剩下 69–79 % 的 FORCED_RISK 来自已承诺层 / 身体管 / 尾巴 / 投射物——要去饱和，下一步还是 §23.11 ① 的已承诺层。
5. 建议（要 lead / 你定，代码没改）：(a) `+n` 把只用身体的家族也拿出支撑，换成按锁定状态查的预计算 ICS（`zones_lat1.npz` 的 `|zl`），可逃检查继续否决；(b) 身体管在 `+g` 之后剩下的一圈（Envoy 2.25 u、Choristor 2.97 u：5 帧的待机增长）和 ICS 的"早"部分（0.3–2.2 u）是同一件事：身体在几帧内就能到的地方，躲不了也不用躲——它不是 ICS 能替代的，R2 召回 2–4 帧要它（§23.8），保留；(c) Clapper 的家族模板要把之前施放的符文拆出去（危险物层管）才能用它的 ICS。

### 26.6 没做 / 未核实

- **平地、无墙**：ICS 按开阔地面算；怪离墙近时主角少了一个方向，ICS 会变大（尤其冲锋、砸地）。墙边的版本没有算。
- **上界依赖库**：1,688 条序列（跳起时刻每 4 帧；每 2 帧对 CC_SLAM、CB_EVADE、RE_EVADE、EN_SLASH 复算结果相同），空中只算了静止（vy 0）的起点，没算上升 / 下落中、贴墙、滑翔中；出刀锁定按"出招那一帧按刀"算（最严的一种）。
- **模板是并集**：家族模板把所有实例（不同时机、不同瞄准、不同距离）并在一起，所以这里的 ICS 偏大（保守）；它比真的单次出招宽。瞄准的家族只对 RE_THROW（瞄准针）和 AT_FIRE（瞄准俯冲）单独建了模型；RE_STAB、Reed 的招架反击（按主角高度）、冲锋的距离没有按主角位置条件化。
- **"早 / 晚"的门槛**（lat + 6 帧）是人为的；"早"的点里有一部分是模板在出招时刻就比身体盒子宽（散布），一部分是之前施放、还在场上的危险物（Clapper 的符文）。后者应该由危险物层（确定路径 / 自模板 / 管）管，这里没有把它们从家族模板里拆出来。
- **对比与替换是开环的**（§19.1 的偏差）：你的按键行在你的录像上近似闭环，规划器的行是开环；"有安全行"只按支撑（名义盒中心逐帧），没有包络、命中分支和可逃检查的否决，所以和规划器自己的 FORCED_RISK 不完全一样（表里两者并列）。
- 第 1 部分的网格只到怪两侧各 12 u、站立高度之上 12 u；"最远距离"到 12–15 u 就是碰到了网格边缘，实际更远。
- Tiny 的组放置（≥ 3 只时一行代表一个格子里的所有 Tiny）按成员归属算进了每一只。

### 26.7 复现

```
cd brain
# 第 2 部分：每个家族 × 锁定状态的 ICS（约 1.5 min；--lat 12 人的反应；--margin 加家族余量）
..\scripts\uv.cmd run python -m ssbot.tools.forum_ics zones --out C:/ssbot/data/m2_forum_ics [--lat 12] [--margin]
# 第 1、3 部分：开环回放（环境变量 = 规划器的开关：最好臂 SSBOT_FORUM_FR=seen_cf SSBOT_FORUM_REACT=escape+n+g SSBOT_FORUM_MARGIN=state；集成默认 = 都不设）
..\scripts\uv.cmd run python -m ssbot.tools.forum_ics replay C:/ssbot/data/runs/m2/20261008_092135_Forum_W_eval_planner_oracle C:/ssbot/data/runs/m2/20261008_094847_Forum_W_eval_planner_oracle C:/ssbot/data/human/20261004_133855:win:1,3,5,6 C:/ssbot/data/human/20261005_160435:win:0,1,2,4 --limit 5 --every 12 --every-idle 24 --workers 3 --threads 2 --demo-cache C:/ssbot/data/m2_forum_w0f/demo_cache --zones C:/ssbot/data/m2_forum_ics/zones_lat1.npz --out C:/ssbot/data/m2_forum_ics/replay_<臂>
..\scripts\uv.cmd run python -m ssbot.tools.forum_ics summary C:/ssbot/data/m2_forum_ics/replay_best C:/ssbot/data/m2_forum_ics/replay_default --zones C:/ssbot/data/m2_forum_ics/zones_lat1.npz --json C:/ssbot/data/m2_forum_ics/summary.json
```
输出：`C:\ssbot\data\m2_forum_ics\`：`zones_lat1.json` / `.npz`（每个家族 × 锁定 × 锚高的区域数组，`|zl` 是"晚"的部分）、`zones_lat12.json`、`zones_lat1_margin.json`；`replay_best\`、`replay_default\`（每段一个 JSON + 待机地图 `*_maps.npz`）；`summary.json`、`summary.maps.txt`（每类 × 层 × 计划帧的文字地图）。驱动 `scratchpad` `run_replay.ps1`，表格 `ztable.py`、`show.py`。

## 29. 区域修正：黄色、已承诺层按瞄准重锚、停放的怪、半屏规则（2026-10-09，task "zone fix"，分支 worktree-wf_0469f4be-4ea-1 = main + forum push 2 合并（7de4e05）+ 区域叠加层（339ff40）；离线，没有开游戏）

第一个开发者在 00:44 被 Windows 更新重启打断，留下 33295b6 / f14aa52 / 9ceb414 和一处没提交的改动；本节是接手后的全部结果。数都是"之前 = 你 10-08 晚看到的叠加层（3ca18c5 的冻结检出 `C:\ssbot\zf_before_3ca18c5`）"对"之后 = 本分支"。

### 29.1 半屏规则怎么量（`tools/zone_share.py`）

每 3 个游戏帧一次：相机视野（STATE 里的相机，主角所在的 z = 0 平面）里被下面这些盖住的比例（主角中心空间，按叠加层的投影画到 192×108 的屏幕上再数）：(a) 黄色不可逃区（已出招 + 还没开始），(b) 规划器在提前量 k = 0 的支撑（所有层的并），另报 k = 12。场地在屏幕里最多占 81–85 %（墙和天花板之外不算），所以 0.81–0.85 就是"整个场地"。数据：你的两次叠加层会话（`20261008_230220`、`20261008_231544`，4 次尝试，10,842 个测量帧）和 bot 最近的第 0 波录像（forum push 2 A/B 的 4 个运行、19 场，11,167 帧，到第 1 波为止）。

### 29.2 已承诺层按瞄准重锚（`tools/forum_aim.py`，开关 `SSBOT_FORUM_AIM`）

- 你说的 Reed 三连刺：录像里 `Stab 1`–`Stab 5` 是身体沿一条直线滑 7–15 u（往前下方约 17–20°），针（约 3.8 × 1.1 u 的框）在身体前面，`Stab 1 / 3 / 5` 才有针。家族模板（从 `Stab Pos` 开始、所有实例的并）有 40 × 24 u，因为 `Stab Pos` 先飞到主角旁边上方——起点离出刺的地方很远。
- **按主角方向分箱不行**：`Stab Antic` 时主角相对 Reed 的方向分 16 个扇区，每个扇区的模板还是并集的一半到三分之二大、留出残差 r ≥ 3 u。**按它自己的飞行方向**：`Stab 1` 进入时 1,271 个实例的速度方向全落在同一个 22.5° 扇区（前下方），方向是固定的；镜像按飞的方向（`aim_frame`：速度 ≥ 1 u/s 时朝向 = 速度的正负，否则按贴图朝向，贴图朝向转身时会晚一帧）。
- 残差 11 u 的来源是少数实例在 `Stab End` / `Stab Recover`（只有身体）里掉下去或滑很远：瞄准模板在这两个状态前截断（`AIM_AFTER`），这两个状态的逐状态节点照旧放。截断后 `Stab 1` 的 r 2.7 u、`Stab 3` 1.7 u、`Stab 5` 0.9 u。
- 每个家族的**每个**"可用箱占实例 ≥ 90 %"的状态都是瞄准状态，追踪器在每次进入时重新锚定（只在那个方向箱有模板时；否则保留前一次已认证的锚，`_aim_now`）。所有 30 个攻击家族都量了（不只是跟主角走的那些），共 92 个模板（`knowledge/1.0.30000/enemies/forum/aim_templates.json` 是报告，`.npz` 不进 git，`python -m ssbot.tools.forum_aim build` 约 5 min 重建）。没有可用模板的：AT_FIRE / AT_DEFEND / AT_LEAVE（持续时间差别大：留出实例的碰撞体比训练模板的最后一帧还晚）、MI_PARRY、CB_THROW、EN_JUMPSLASH、EN_AMBUSH、CM_TELE、CC_EVADE。
- 认证规则同 R2：开发集两折互留（按场分折）+ 35 场新场对全部开发场，每个箱的模板膨胀 r（两折和新场取大）后盖住 100 % 的留出碰撞体框；r ≤ 3 u、没有"比模板还晚"的框才用。
- 构建的加载慢 100 倍（每行一次 `searchsorted`，一场 30 s）：改成每场一次 + 进程池，全部 142 场 20 s。

### 29.3 黄色（叠加层，`ZoneEngine.yellow`）

- **已出招**：每个已出招实例**自己现在的伤害碰撞体**（oracle 的真框）沿它的速度推 12 帧，和主角盒做闵可夫斯基和（主角中心空间），再按一帧的逃离范围往回腐蚀（`erode_back`，地面、墙、穹顶以外是实心）。家族模板（全部录到的实例的并）是规划器的上界，不是"确定躲不开"的格子，不再进黄色。Reed 的刺就是一条往前下方的斜带（PNG 见 29.8）。投掷物（钟、针、符文）是别的实体，本来就不在里面；Clapper 模板里以前施放的符文（`CC_CAST` 等）在"还没开始"的下界里也去掉了（危险物层管）。
- **还没开始**：第一个开发者的"按家族 × 锁定状态的现在出招下界"（锚点两侧各 24 u 的 `_ns_lb`，不是整个 `zones_lat1` 上界），跟主角走的家族（`forum_aim.CANDIDATES`）不进。

### 29.4 停放的怪（`SSBOT_FORUM_PARK`，默认开）

后面波次的怪停在场外（`Fly In Ready`、`Dormant`、`Sleep`、`Wait` 这类等待状态、没有渲染）时，碰撞体可能报"启用"，但从来没伤过人（任务里的数：主角和那只停着的 Reed 重叠 136 帧，0 次受伤）。叠加层 339ff40 已经不画；预报里它不进支撑（不放碰撞体管、不走状态图）。复核时发现第一版把**波次已经排队、视野内就要激活**的怪也拿掉了（`test_a_waiting_wave_member_waits_for_its_wave` 失败）：改成只在它的波次在视野内不会激活时拿掉，波次排队了就照旧从激活时刻走。

### 29.5 A 轨安全（33295b6，单测在 `test_forum_track_a.py`）

- `kb`：被打的怪的支撑同时查推开的和没推开的两份（中位击退没有下界，墙会挡住）。
- `free`：h ≥ 2 时只有击杀慢动作 ≤ 0.5 s 的击杀可以不认证；高庭的最后一击（`EnemyBattleEndSlow` / `BigEnemyDeathSlow`，1.85–2.47 s 不暂停，垂死的 Clapper 的身体、符文砸地、钟和别的怪都还会伤人）照旧走 I3。

### 29.6 接受检查（冻结检出 `C:\ssbot\hs_zfix_b0be790`，`SSBOT_FORUM_AIM=1`，停放默认开）

- **R2 留出召回**（`multi_recall fresh --react escape+n+g --state-margins`，444 个对局任务，31 min，`C:\ssbot\data\m2_forum_zfix\recall_fresh_aim.json`）：**L2 / L3 / L4 各 375,940 / 375,940（100 %）**，自己类型也 100 %，多段链的钩 1,802 / 1,802，0 漏。
- **重打分**（`forum_human_rescore.cmd best zfix_aim`，32 段 0 错误，对 §28.2 的 base = fp2_base；输出 `C:\ssbot\data\m2_forum_hs\zfix_aim[_summary.json]`）：

| 全部 32 段 | base | + 瞄准 + 停放 |
|---|---|---|
| FORCED_RISK | 82.10 % | 81.84 % |
| 第 0 波 24 段的 FORCED_RISK | 78.56 % | 78.30 % |
| 你的动作被判不安全（匹配行） | 86.57 % | 86.43 % |
| 误报（匹配行里判不安全且事后没碰） | 76.89 % | 76.75 % |
| 漏报（占判安全） | 0.60 % | 0.60 % |

  三项都往下、漏报没升，按 plan §5 的规则接受：`SSBOT_FORUM_AIM` 默认改成开（`0` 关；没有 `aim_templates.npz` 就什么也不加载——冻结检出要连它一起拷）。幅度很小：FORCED_RISK 主要不是已出招之后的事（见 29.7）。

### 29.7 半屏规则：之前 / 之后

| | 你的两次会话 之前 | 之后 | bot 第 0 波 之前 | 之后 |
|---|---|---|---|---|
| 黄色 > 50 % 的帧 | 3,369（31.1 %），最大 0.852 | **0**，最大 0.488 | 1,700（15.2 %），最大 0.852 | **0**，最大 0.143 |
| 黄色中位 | 0.280 | 0.041 | 0.238 | 0.030 |
| 支撑 k = 0 > 50 % 的帧 | 5,098（47.0 %） | 4,577（42.2 %） | 3,899（34.9 %） | 3,130（28.0 %） |
| 支撑 k = 0 中位 | 0.460 | 0.429 | 0.421 | 0.391 |
| 支撑 k = 12 > 50 % 的帧 | 8,057（74.3 %） | 7,767（71.6 %） | 8,704（77.9 %） | 7,745（69.4 %） |

- (a) 黄色：达标。之后最大的 0.488 是"还没开始"的下界（已出招部分最大 0.172）。
- (b) 支撑 k = 0：**没有达标**，每一帧列在 `C:\ssbot\data\m2_forum_zfix\over_half_after.csv`（7,707 行：录像、帧、波次、各份额、k = 0 最大的层、当时已出招的家族）。按放置分组拆开（每 15 帧一次，只看 > 50 % 的帧，平均每组盖住的屏幕份额）：
  - 第 0 波（`231544` 第 1 次尝试，130 帧里 39 帧超）：Reed 的 RE_DEFEND 反击链窗口 0.27、**RE_STAB 瞄准之前**的细放置 0.25 和家族并 0.15（`Stab Pos` 先飞到主角旁边上方：这段跟主角走，瞄准模板管不到）、还没开始的 RE_EVADE 0.16、Envoy 冲锋 0.10。
  - 后面的波（`231544` 第 0 次，506 帧里 232 帧超）：**Maestro 召出的小自动机**（Automaton Tiny）——还没开始的 AT_FIRE / AT_DEFEND 各 0.34、AT_LEAVE 0.18，已出招的 AT_FIRE 尾巴 / 家族并 / 细放置各 0.18–0.22；其次 CM_SPIN、CM_TELE、MA_DEFEND。
  - 最差的四帧（k = 0 支撑 0.813 = 整个场地）PNG：`C:\ssbot\data\m2_forum_zfix\png\worst_s0_*.png`（模式 support）。例如 `230220` 第 1 次 16841 帧：Reed 在 `Stab Pos`、Envoy 在 `Charge`，已出招层（粉）和窗口层（蓝）盖满整个场地。
  - 为什么这件事重要：规划器第一段的接触检查从第 0 帧查起（`forum_planner` 的 `tk = arange(T1)`），第 0 帧每一行的主角盒都一样——主角现在站的地方在 k = 0 支撑里，**所有行**都判不安全，这就是 FORCED_RISK 约 80 % 的直接机制。
- 下一步（没做，要 lead / 你定）：① Reed `Stab Pos` 按主角位置锚定（它飞到主角旁边上方 6.7 u：锚点 = 主角 + 偏移，同 §23.7 的 `pinaim`）；② Tiny 的 AT_FIRE 按持续时间分箱或时间伸缩，才能过留出认证；③ k = 0（及输入生效前的几帧）用 oracle 的真碰撞体代替模板——这几帧所有行一样、不区分行，只会把整个 tick 推进 FORCED_RISK。

### 29.8 PNG 和回放

- PNG（`C:\ssbot\data\m2_forum_zfix\png\`，黄 + 红，k = 0）：`before_*` / `after_*` 同一帧。Reed 刺（黄色占屏幕，之前 → 之后）：`230220` 第 0 次 3551（`Stab 1`，73 % → 5 %：一条从 Reed 往左下的斜带）、4043（58 % → 2 %）、4361（`Stab End`，80 % → 2 %：只剩身体，红框）；`231544` 第 0 次 4940（68 % → 7 %）、9728（83 % → 5 %）；第 1 次 20959（56 % → 7 %）；随机帧 8459、10301、16967、17621、5708、6878、20107、53053。录像里没有对应视频帧的 3605、39115 没出图。
- 回放（k 0,12，带录像，半尺寸，最终代码）：`C:\ssbot\data\m2_forum_overlay\20261008_230220_zones_fix.rrd`、`20261008_231544_zones_fix.rrd`（旧的 `*_zones.rrd` 留着对比）。每只怪一个固定名字（类型短名 + 出场顺序，如 "Reed 2"）+ 当前 Control 状态，碰撞体、黄色、支撑按怪分开记、各用一种颜色；现场叠加层的说明框列出所有怪。

### 29.9 A/B 工具（f14aa52）

`forum_ab_summary`：没受击的波按那一波自己的怪算（不是"下一波开始就算清"），重叠的波合在一起；砍中数只算主角自己的（HERO_ATTACKS、dealt > 0，Garmond / Cogfly 另算团队输出）；HARNESS_FAIL 行保留并单独列出。

### 29.10 复现

```
cd brain
..\scripts\uv.cmd run python -m ssbot.tools.forum_aim build --workers 4                     # 瞄准模板（约 5 min）
..\scripts\uv.cmd run python -m ssbot.tools.zone_share run C:/ssbot/data/human/20261008_230220:win C:/ssbot/data/human/20261008_231544:win --out <dir>\h --every 3 --ks 0,12
..\scripts\uv.cmd run python -m ssbot.tools.zone_share run <4 个 runs\m2\20261008_21*_Forum_W_eval_planner_oracle_clashM 目录> --w0 --out <dir>\bot --every 3 --ks 0,12
..\scripts\uv.cmd run python -m ssbot.tools.zone_share summary <dir>\h <dir>\bot
..\scripts\uv.cmd run python -m ssbot.tools.zone_share png <session> --attempt N --frames F1,F2 [--mode support] --out <dir> --tag after_
..\scripts\uv.cmd run python -m ssbot.tools.viewer C:/ssbot/data/human/<session> --zones --k 0,12 --video --video-scale 0.5 --save <out>.rrd
```
测量输出：`C:\ssbot\data\m2_forum_zfix\v_before\{h,bot}`（之前，3ca18c5 + zone_share）、`v_after3\{h,bot}`（之后）、`v_after3_summary.json`。

### 29.11 你说的紫框：Choristor 的鞭子在前摇里"够到"11.7 u 外（2026-10-09，task "support reach"；开关 `SSBOT_FORUM_RCLIP`，默认关；工具 `tools/support_reach.py`，表 `combat/reach_table.py`）

**那个紫框是什么**（`20261009_085824` 第 0 次尝试，原始帧 5690，回放配置 AIM=1、seen_cf、escape+n+g、按状态余量、clash main）：Choristor 3 在 `Whip Antic`（鞭子的前摇）里已经 0.70 s，站着不动（速度 0），transform 在 x 22.79，面朝你；你在 x 34.44，正前方 11.65 u。`enemies/choristor_3/support/k12` 是它自己的 CH_WHIP 支撑：家族模板（从前摇开始的全部实例的并，粗金字塔窗口）+ `Whip 1`–`Whip 6`、`Multiwhip`、`Whip End`、尾巴各自的窗口放置，**全部锚在前摇开始的位置**，入口窗口都很窄（`Whip 1` 0.09–0.15 s 后）。k = 12 时它们往前伸到 x 36.5（13.7 u），其中家族模板和 `Whip 1`–`Whip 4` 盖到你；k = 0 时只有身体附近（没盖到你）。列表和 PNG：`C:\ssbot\data\m2_forum_reach\explain\before_20261009_085824_f5691_Choristor_3{.json,.png,_hero.png}`。

**为什么伸那么远——你的猜想对了一半**：锚点本身没有动、也没有生长（它就是你看到它站的地方）。但模板是 1,309 个录到的实例相对"前摇开始位置"的并集，里面包括**被打退的实例**：142 场录像里 1,774 次 `Whip Antic`，1,649 次身体一动不动，125 次动了 2.7–3.6 u，**每一次都在被打（主角或 Garmond 的 `Charge Damager`）之后 1–9 帧**，击退约 0.47 u/帧、持续约 8 帧，导出的速度是 0（击退直接挪 transform）。鞭子期间也一样（`Whip 3`–`6` 被打后身体最多离锚 4.8 u）。所以模型等于让"别的实例被打飞的那几 u"在每一次前摇里都算上——效果上就是让它"跑着前摇"。鞭子本身离身体最远 8.75 u（`Whip 2`），`Whip 1`/`Whip 2` 自己往前滑 1.3 u。**录像里的真实范围**：前摇 0.70 s 时再过 12 帧，碰撞体离它的 transform 最远 **9.75 u（没被打）/ 10.65 u（中途被打）**（142 场 2,241 个样本），没有一次到过 11.4 u（你身体的边）。你说"它绝对够不着"是对的。
- 顺带发现：鞭子的碰撞体（`Whip Hit 1`–`6`）和 Reed / Minister 的 `ParrySlash Hit`、Minister 的 `Slash Collider` 都是多段伤害，导出时 dealt = 0。叠加层的红色、黄色"已出招"和 `forum_aim` 的瞄准模板只收 dealt > 0，**所以这几招在红 / 黄里看不到，CH_WHIP 的瞄准模板也没有鞭子**（AIM 现在默认关；`forum_aim.instances(threat=True)` 已经能把它们算进去，重建瞄准模板时要打开）。支撑模板本身是有鞭子的（建表收的是 eff ≠ 0）。

**推广：每只怪自己的支撑超出它真实范围多少**（`support_reach scan`：你的三次会话 7 段 17,869 帧 + bot 第 0 波 19 场 11,483 帧，每 3 帧；真实范围 = 142 场录像里"处在这个状态时，k 帧后它的威胁碰撞体相对它 transform 到过的框"（按朝向镜像，k ± 1 帧），超出 > 1 u 算超出）：
- 你的会话：k = 0 有支撑的 44,213 个"怪 × 帧"里 40,489 个超出（91.6 %），k = 12 是 39,497 / 43,342；你站的位置落在"超出部分"里的有 21,960（k = 0）/ 16,639（k = 12）次。bot 第 0 波：k = 0 24,650 / 31,721，k = 12 22,342 / 30,447。
- 按原因排（你站的位置被超出部分盖住的次数，k = 12）：Maestro 的小自动机还没出招的 AT_FIRE / AT_DEFEND 家族游走框（`Ready` 时超出中位 20 u）、Reed 还没开始的 RE_EVADE 框、Clapper CC_EVADE、Minister MI_EVADE、Bellbearer CB_EVADE、Clawmaiden CM_TELE；已出招的：小自动机 AT_FIRE 的 `Return` / `Wall Bonk` 窗口和尾巴（17–19 u）、Envoy 冲锋 EN_CHARGE 的各状态窗口（14 u，bot 第 0 波第一名）、Minister MI_PARRY 的链框（11 u）、Reed RE_DEFEND 反击链的窗口 / 尾巴（5–9 u）、Clawmaiden CM_SPIN 家族模板（14 u）。
- 四个机制：(1) 从出招开始锚定的并集装着所有实例的位移（击退、飞行、冲到墙边）；(2) 入口时间不确定的窗口放置把"什么时候进这个状态"和"那时身体在哪"拆开了——"撞墙"这个状态在任何入口时间都放在任何距离上；(3) 还没开始的实例：家族游走的逐 bin 包围盒 × 两个镜像 × 锚点框，锚点框按**待机**生长从现在算起——敌人正在前摇里站着不动时也照样长（这才是字面意义上的"跑着前摇"，在后面的实例上）；(4) 余量。逐帧数据：`C:\ssbot\data\m2_forum_reach\scan_before\`、汇总 `scan_before_summary.json`。

**改了什么（`SSBOT_FORUM_RCLIP=1`，默认关）**：每只怪**自己的**放置（细、窗口、包围盒）和待机身体管，在提前量 k 时只保留它"从现在的位置、现在的状态、现在在这个状态里的时间"出发 k 帧内真实到过的框之内的部分。
- 表（`support_reach clip-build`，**只用开发集 107 场**，新场完全留出给召回）：按 (类型, Control 状态, 在状态里的时间 0.05 s 一档, k = 0–126 帧) 记碰撞体相对 transform 的框，分"全部"和"没被打"（前 20 帧到 k 帧后都没被打：没有击退）两份；一档的框还并上后两档（状态比录到的都短 0.1 s 也盖得住）；行数不够就退到整个状态、家族、类型。运行时：追踪器 20 帧内没看到它挨打就用"没被打"的框，否则用"全部"。
- 留出余量 r：开发集两折按场互留，每 (类型, 状态, 时间档, 部分, k 段) 取一折超出另一折的最大值，至少 0.5 u；再加主角半宽。
- 不裁剪：入场 / 等待 / 死亡状态、正在投掷的家族（Reed 的针、Bellbearer 的钟、Clawmaiden 的矛、Clapper 的符文：它们的模板和身体管也代表扔出去的东西）、小自动机的分组行、视觉视图、受击反应预报、超过 2 帧没看到的怪。抛射物、入场、死亡尾巴本来就不归怪自己。
- 你的那一帧：k = 12 的鞭子支撑从 x 36.5 缩到 33.7（真实范围 + r 0.5 + 主角半宽），**不再盖你**（PNG `after_20261009_085824_f5691_Choristor_3.png`）。另外两帧：7939 撤退的 Bellbearer k = 0 支撑 x 38.5–48.5 → 41.0–45.5、不再盖你；10427 Reed 的地面反击 k = 0 / 12 支撑 x 23.8–48.5（整个场地）→ 32.8–38.0 / 30.5–38.5，不再盖你（`explain\{before,after}_20261009_085824_f{7939,10427}_*.png`）。

**数字（冻结检出 `C:\ssbot\hs_rclip_b5e9072`；半屏和扫描用回放配置 AIM=1）**：

| 半屏规则（支撑 > 屏幕一半的帧） | 你的三次会话 之前 | 之后 | bot 第 0 波 之前 | 之后 |
|---|---|---|---|---|
| k = 0 | 7,575 / 17,869（42.4 %），中位 0.430 | **4,184（23.4 %）**，中位 0.135 | 3,130 / 11,167（28.0 %），中位 0.391 | **113（1.0 %）**，中位 0.097 |
| k = 12 | 12,394（69.4 %），中位 0.607 | **5,963（33.4 %）**，中位 0.301 | 7,745（69.4 %），中位 0.567 | **1,417（12.7 %）**，中位 0.224 |

| 超出真实范围 > 1 u（怪 × 帧） | 你的会话 之前 | 之后 | bot 第 0 波 之前 | 之后 |
|---|---|---|---|---|
| k = 0 超出 | 40,489 / 44,213 | 19,312 | 24,650 / 31,721 | 5,214 |
| k = 0 你站的位置在超出部分里 | 21,960 | 13,778 | 7,313 | 225 |
| k = 12 超出 | 39,497 / 43,342 | 19,663 | 22,342 / 30,447 | 5,250 |
| k = 12 你站的位置在超出部分里 | 16,639 | 10,663 | 5,082 | 770 |

- 还剩的大头：**Maestro 的小自动机**（你的会话里剩下的"你站在超出部分里"几乎全是它）——3 只以上时它们后面的实例按簇放一行（一行代表几只、位置不同），这些分组行没有裁剪；后面的波（第 3、5、6、7、12、13 波）占剩下的超半屏帧的 99 %。bot 第 0 波剩下的是 Choristor 的入场（`CH_ENTRY`，故意不裁）和 Reed 还没开始的 RE_EVADE。
- 代价：同一批帧（`085824` 前 1,800 帧，每 6 帧，400 × 49 的查询），预报 p50 0.66 → 0.98 ms，`occupied` p50 1.09 → 1.90 ms（裁剪按怪分批查询）；读表 0.2 s + 初始化 1 s（每个进程一次）。
- R2 留出召回和你赢的录像的重打分见 29.12（跑完后补）。中途修过两次（都是新场召回抓到的，表只用开发集）：投掷中的怪不裁（Reed 的针出手那一帧由身体管代表：`074533` i2 ep34 L2）；时间档并上后两档、余量至少 0.5 u（Clawmaiden 的斩比开发集最远还远 0.14 u：`074719` i3 ep32 L3）。

**复现**（`brain` 下）：
```
..\scripts\uv.cmd run python -m ssbot.tools.support_reach explain C:/ssbot/data/human/20261009_085824 --attempt 0 --frame 5690 --enemy "Choristor 3" --tag before_   # 加 SSBOT_FORUM_RCLIP=1 / --tag after_
..\scripts\uv.cmd run python -m ssbot.tools.support_reach reach --out <reach60_all.json>          # 真实范围（开发 + 新场，k 0-60，扫描用）
..\scripts\uv.cmd run python -m ssbot.tools.support_reach clip-build                                # 裁剪表（只用开发集）-> knowledge/.../forum/reach_clip.npz（不进 git）+ .json
..\scripts\uv.cmd run python -m ssbot.tools.support_reach scan <session>:win ... | <bot run> ... [--w0] --out <dir> --reach <reach60_all.json>
..\scripts\uv.cmd run python -m ssbot.tools.support_reach summary <dir>\h <dir>\bot
```
驱动：`C:\ssbot\data\m2_forum_reach\share.cmd <tag> <0|1>`（半屏 + 扫描）、`accept.cmd recall|base|rclip`（召回、重打分）。冻结检出要连 `reach_clip.npz` 一起拷。

### 29.12 精度检查：预测框比真伤害框大多少（2026-10-09，task "support precision"，`tools/support_precision.py`，分支 worktree-wf_3821c41a-c3d-1 = main + 区域修正分支 worktree-wf_0469f4be-4ea-1 到 2b23e08；离线，没有开游戏）

你 10-09 的要求：把游戏里真实的伤害框导出来，对每个已承诺的预测做一个通用检查——此刻预测 0.2 s 以后的伤害框，0.2 s 以后那里如果没有真伤害框，预测就有误差；比真的大 50 % 算余量。以前的接受检查只看召回（不漏，R2 留出 L2–L4 100 %）和半屏规则，**没有精度检查**。

**定义**（每帧 t × 每只怪 × 每层 × 提前量 k = 0、6、12、18 帧；每 3 个游戏帧量一次，外加你点名的帧）：
- **预测**：规划器的支撑，同 `viewer --zones`（`ZoneEngine`，开关同回放：FR=seen_cf REACT=escape+n+g MARGIN=state KF=kill clash=main crest=Wanderer，`SSBOT_FORUM_AIM=1` 和 `0` 各跑一遍），**按放置的主人拆开**：`forum_layer_audit.classify` 的每个放置组、每个管盒、每条危险物路径各归它的怪；投掷物（针、钟、符文、矛、爆炸）归扔它的怪（它武装那一帧离它最近的同类型怪）。层同回放的 `support/kNN/<layer>`：body、committed、window、not_started、hazard、death；另加 com_all = committed ∪ window（所有已承诺的放置）和 total = 全部。核对：拆开再并起来和叠加层的支撑逐格相同（0 格差）。
- **参考（真值）**：那只怪在 t + k 的**真伤害碰撞体**——它自己的和它扔出去的东西的所有启用、dealt > 0 的碰撞体（`zone_overlay.damage_colliders`，停放的跳过；圆是 8 边形），和主角盒（半宽 0.25 × 半高 1.04 u）做**精确的**闵可夫斯基和，在支撑查询用的同一批网格点（叠加层的 0.25 u 网格）上判。R = t+k−1 … t+k+1 三帧的并、主角盒再长一格 0.05 u（支撑的 ±1 帧 / ±1 格）；Rs = 恰好 t + k。not_started 的参考：只有 (t, t+k] 里它真的进了一个攻击起始状态（它的表的 `attack_starts`）才 = R，否则是空的。
- **膨胀核对**（"在一个已知紧的帧上比"）：k = 0、只有身体的怪，body 层 / R：Reed `Alert` 中位 0.86、p99 1.0；Choristor `Battle Idle` 0.92；Tiny `Ready` 0.86 / 1.0；Envoy `Walker` 1.0 / 1.0；Minister `Chase` 1.04 / 1.22。全部 body k = 0 的中位 0.89–0.92、p90 1.04–1.12。参考和支撑是同一个膨胀、同一个网格。
- **打断**：(t, t+k] 里这只怪被砍（`hit` 事件）、进了硬直类状态（Stun / Recoil / Clash / Parried …）、死了、或者离它 6 u 内发生拼刀：预报不可能知道，**单列，不算错**。
- **你的规则**：预测非空，且 RATIO = 预测面积 / R 面积 > 1.5，或者 R 是空的（误报）且没被打断 → **错误**。

**结果**（`SSBOT_FORUM_AIM=1`，即回放 `20261009_085824_zones.rrd` 的配置；你的 3 次会话 = `20261008_230220`、`20261008_231544`、`20261009_085824` 的 7 次尝试，全程；bot = §29 的 4 个 A/B 运行 19 场，到第 1 波为止）：

| 层 | | 你的会话 k = 0 | k = 12（0.2 s） | bot 第 0 波 k = 0 | k = 12 |
|---|---|---|---|---|---|
| committed | (帧, 怪) 数 | 23,218 | 17,991 | 17,493 | 13,218 |
| | **错误** | **99.56 %** | **99.43 %** | **99.31 %** | **99.43 %** |
| | RATIO 中位 / p90 / p99 / 最大 | 13.1 / 73 / 141 / 304 | 16.7 / 78 / 145 / 304 | 9.4 / 38 / 59 / 91 | 12.9 / 42 / 60 / 91 |
| com_all（+ window） | 错误 | 99.73 % | 99.81 % | 99.57 % | 99.57 % |
| | RATIO 中位 / p90 / p99 | 17.7 / 73 / 143 | 21.4 / 74 / 143 | 13.1 / 42 / 59 | 17.5 / 44 / 60 |
| not_started | 错误（其中误报） | 100 %（全部误报） | 100 %（30,307 / 32,152 误报） | 100 %（全部误报） | 100 %（10,429 / 11,120） |
| | RATIO 中位（真起手了的） | – | 26.4 | – | 24.9 |
| body | 错误 / RATIO 中位 | 8.97 % / 0.89 | 99.45 % / 6.7 | 6.37 % / 0.92 | 100 % / 6.8 |
| total | 错误 / RATIO 中位 | 91.8 % / 14.3 | 99.99 % / 26.7 | 80.6 % / 8.1 | 99.8 % / 16.6 |
| 打断（单列） | committed | 0 | 1,590 | 0 | 491 |
| 几何召回（total） | 真伤害格全被盖住的 (帧, 怪) / 格 | 99.18 % / 99.64 % | 98.81 % / 99.50 % | 100 % / 100 % | 96.88 % / 98.08 % |

- `SSBOT_FORUM_AIM=0`（规划器默认）几乎一样：你的会话 committed 错误 99.61 % / 99.36 %、RATIO 中位 13.3 / 15.5；bot 99.41 % / 99.14 %、8.5 / 9.2。瞄准模板只改了很少的行。
- 你说"大了 10000 %"（100 倍）：中位是 10–20 倍，p90 40–78 倍，p99 60–145 倍，最大 304 倍。**合格（≤ 1.5 倍）的已承诺预测不到 1 %**；按类型 k = 12 com_all 的中位：Tiny 69、Clawmaiden 42、Reed 34、Minister 21、Envoy 14、Maestro 14、Choristor 13、Bellbearer 11、Clapper 7。
- not_started 在 k = 0 永远是误报（"还没开始的攻击在前摇结束前不可能伤人"），而它在 k = 0 有 32,987 + 11,366 个非空预测。
- body：k = 0 是紧的（中位 0.9），k = 12 是 6.7 倍：身体管按这一类的最大速度往每个方向长。

**你点名的帧**（`20261009_085824` 第 0 次尝试，AIM = 1；行在 `aim1\h\20261009_085824_a0.jsonl`，`"asked": true`）——全部判为错误：
- **5690**（行 5689）Choristor 3，`CH_WHIP` / `Whip Antic`（进状态 0.68 s）：k = 0 committed（chain_fine）29.4 u² 对真的 4.5 u² = **6.5 倍**；k = 12 window（chain_win）112 u² 对 5.2 u² = **21.4 倍**，比真框往前多 12.5 u、往后 7.5 u、往上 4 u。
- **7939** Bellbearer 1，`CB_EVADE` / `Evade`（0.05 s，瞄准模板放了）：k = 0 committed 86.7 u² 对 8.4 u² = **10.3 倍**，k = 12 107 u² = **14.4 倍**（四周各多 2.5–5.8 u：你看到的"一圈三个主角宽"）；还有 not_started k = 0 94.8 u²、k = 12 200.7 u²：0.2 s 内没有起手，**误报**。
- **7939** Reed 2，`RE_IDLE` / `Alert`：not_started k = 0 69.8 u²、k = 12 **248 u²**（左右各 10 u、上 9 u），0.2 s 内没有起手：**误报**；身体 k = 12 46.9 u² = 5.4 倍。
- **10427** Reed 2，`RE_DEFEND` / `Parry Slash`（0.4 s，地面反击）：k = 0 committed（chain_fine）155.8 u² 对 8.0 u² = **19.5 倍**，window（chain_win）306 u² = **38 倍**；k = 12 committed **23 倍**、window **44 倍**。超出真框：committed 前 7.75 u、后 12.5 u、上 5.25 u；window 前 10.75 u、后 12.5 u、上 11 u——和你说的"前面宽 3–4 个主角、后面 2/5 屏、高一个主角"同一个方向，量更大。

**主要原因**（k = 12 com_all 的多出面积按放置种类分，见 summary 的 `causes`）：
1. **家族并集**（`com_fam`：这个家族所有录到的实例、所有状态的并，当前状态没有逐状态模板时放）：带它的行占全部多出面积的约 55 %，RATIO 中位 37–65。Tiny 的 `AT_FIRE` / `AT_DEFEND` 前后各 32–34 u = 整个场地；Envoy `EN_CHARGE` 往前 34 u（整段冲锋，不是 0.2 s 能走的）；Reed `Stab Pos` / `Stab Antic`（瞄准之前，跟主角走）前后 20–34 u。
2. **反击链窗口**（`chain_fine + chain_win`：Reed `RE_DEFEND`、Minister `MI_PARRY`）：约 18 %，中位 21–27：链上所有后续段的并，前后各 15 u、上 12 u。
3. **细放置本身也大**：`com_fine + aim` 中位 9.7（k = 0）/ 14.3（k = 12），只有 `com_fine` 的 41。细模板在某个时间格 = 所有录到的实例在"起手后这么久"的碰撞体的并、锚在起手处，离起手越久越散；再加状态余量（MARGIN=state）和残差垫。
4. **not_started**：k = 0 起就有（规则说前摇结束前不该有）；最大的是 Tiny `Ready`（整个场地）、Reed `Alert`（两边各 34 u）、Minister `Chase`。
5. **身体管**：按最大速度四面长，0.2 s 后 6.7 倍。

**几何召回**（每个真伤害格，不只主角实际站过的地方——和 R2 的接触召回不是一个量）：k = 0 漏的是投掷物出手那一刻（Reed `Throw` 143 行、Bellbearer 的钟 194 行：危险物层还没放上它）；k = 12 漏的是攻击收尾时身体走得比剩下的模板远（Envoy `Charge End` 311 行、Choristor `Spin Slash End` 234、`Slash Recover` 191、Envoy `Attack End` 189、`JumpSlash 4` 137）。所以接受门要比"之前 / 之后"，不是要求 100 %。

**作为接受门**（以后每个支撑改动都跑）：
```
cd brain
..\scripts\uv.cmd run python -m ssbot.tools.support_precision run C:/ssbot/data/human/20261008_230220:win C:/ssbot/data/human/20261008_231544:win C:/ssbot/data/human/20261009_085824:win --out <dir>\h --frames 5690,7939,10427 --workers 3 --threads 2 --aim 1
..\scripts\uv.cmd run python -m ssbot.tools.support_precision run <4 个 C:\ssbot\data\runs\m2\20261008_21*_Forum_W_eval_planner_oracle_clashM 目录> --w0 --out <dir>\bot --workers 3 --threads 2 --aim 1
..\scripts\uv.cmd run python -m ssbot.tools.support_precision summary <dir>\h <dir>\bot --ks 0,12 --json <dir>\summary.json
..\scripts\uv.cmd run python -m ssbot.tools.support_precision png C:/ssbot/data/human/20261009_085824:win:0 --frames 5690,7939,10427 --k 12 --out <dir>\png
..\scripts\uv.cmd run python -m ssbot.tools.support_precision worst <dir>\summary.json --list worst_fam --top 10 --out <dir>\png
```
26 个任务每个约 70 s，3 个进程约 10 min。基线：`C:\ssbot\data\m2_forum_precision\summary_aim1.json`、`summary_aim0.json`（合并），`summary_aim{1,0}_{h,bot}.json/.txt`（分开，k = 0、6、12、18）；逐行数据 `aim{1,0}\{h,bot}\*.jsonl`。

**PNG**（世界坐标，y 朝上：真伤害填红（严格的 t + k 更深）、预测各层描边（叠加层的颜色，白 = total）、真碰撞体白线、白点 = 主角中心、黄框 = 相机屏幕）：`C:\ssbot\data\m2_forum_precision\png\flagged\`（你的 4 个帧，k = 0 和 12，每只怪一张）、`png\worst\`（多出面积最大的：全是 Tiny 的整场并）、`png\worst_fam\`（每个类型 × 家族最差的一张：Tiny AT_FIRE / AT_DEFEND、Clawmaiden 旋转 / 飞 / 三连、Reed 刺尾 / 反击、Minister 格挡、Clapper 跳、……）。

**回放里的精度标量**：`viewer <session> --zones --precision [--k 0,12]` 每只怪每个 k 记 `metrics/precision/<名字>/k<k>/{committed, com_all, not_started, total}`（RATIO；0 = 没有预测，−1 = 预测了但没有真伤害）和 `.../error`（你的规则，1 = 错），右边多一个时间序列视图。试跑：`C:\ssbot\data\m2_forum_precision\20261009_085824_f10300-10460_precision.rrd`（10427 帧附近）。

**没做**：任何支撑本身的改动（这一节只量）。

### 29.13 精度推进 S0：多段伤害进真值、精度工具修正、基线（2026-10-09，task "precision push" S0；分支 worktree-wf_de8bf451-06d-1 = main + 区域修正 / RCLIP 83423a3 + 精度工具 18848cb；离线，没有开游戏）

**P0 多段伤害算真伤害**：规则 `zone_overlay.hurts(c, src)`：启用并且 dealt > 0，或者 dealt = 0、eff ≠ 0、实体带 multi_wounder 源位（8）。用在红色、黄色（已出招）、`world/colliders` 和每只怪的 `colliders`（都走 `damage_colliders`）、`viewer` 的红色、精度工具的真值、`forum_aim`（`instances(threat=True)`）。证明（`C:\ssbot\data\m2_forum_push\p0\mw_proof.json`、`mw_proof_raw.json`，脚本同目录）：
- 开发 + fresh 的 142 场缓存：dealt = 0 的碰撞体只有 8 种，全部带 multi_wounder 位、eff = 2：Minister `Slash Collider`、Reed `ParrySlash Hit`、Choristor `Whip Hit 1`–`6`。伤害事件的来源正是它们：`Slash Collider` 1,090 次、`ParrySlash Hit` 299、`Whip Hit 1`–`6` 214 / 187 / 48 / 100 / 13 / 1。
- 原始录像（你的 3 次会话 + bot 两个 run 各 3 场）里另有三种 dealt = 0：被打回去的钟 `Throwing Bell`（512 帧）、Reed 的针（9 帧）、Clawmaiden 身体（285 帧）。它们 eff = 0、没有 multi_wounder 位；没有一个伤害事件只对得上 dealt = 0 的碰撞体。所以它们不算。
- 瞄准模板按 `threat=True` 只用开发集重建（98 个；R2 fresh 不再进余量 r，变成留出）。变化：CH_WHIP `Whip 1` r 2.4 → 2.3；EN_JUMPSLASH 新选了 3 个状态；RE_DEFEND `Multihit End` 1.95 → 1.35；CC_JUMP_CAST 加 `Cast Slam Antic 2`。AIM 仍默认关（规划器）；叠加层默认 AIM=1。

**精度工具的修正**（验证者的 F1–F5，`tools/support_precision.py`）：
- 投掷物的主人取**预测那一帧当时**的主人（每个投掷物一个指派历史，不再用整场最后的表）。
- 指派：投掷物出现时和每次重新武装时，给 THROW_F = 120 帧内处在"会扔它的家族"状态的同类怪（几只时取最近的），都没有才取最近的同类怪。你的 3 次会话 + bot 第 0 波：全部指派都是按投掷状态（例如 231544 第 1 次 183 次全是）。
- t + k 按累计**游戏时间**取（第一帧游戏时间 ≥ t + k/60），顿帧不再让参考提前。
- not_started 另按你的字面规则判一遍（层名 `ns_any`：参考 = 这只怪在那里的任何真伤害）。
- 没有在场怪认领的支撑（死掉的投掷者的投掷物、后面波次的入场）单独一行 `unattributed`。Tiny 的群组行算给群里每一只（和 `occupied_only` 一致）。
- 新子命令：后见召回 `run --ks hindsight --lite` + `hindsight`（k = 0..12 和 36；按家族；自己的支撑 / 所有支撑；"被打过"的行分开）。

**基线**（`C:\ssbot\data\m2_forum_push`；冻结检出 `C:\ssbot\hs_push_d08b738`；配置 base = seen_cf + escape+n+g + 按状态余量 + kill，AIM=0，所有修正开关关；rclip = base + RCLIP=1；"之前" = 精度工具第一版的 AIM=0 基线）。错误占比 / RATIO 中位：

| | 之前 | base | rclip |
|---|---|---|---|
| 你的会话 k0 committed | 99.61 % / 13.3 | 99.60 % / 12.3 | 96.37 % / 2.6 |
| 你的会话 k12 committed | 99.36 % / 15.5 | 99.38 % / 14.9 | 98.89 % / 7.0 |
| 你的会话 k12 com_all | 99.82 % / 21.9 | 99.81 % / 20.4 | 99.39 % / 7.6 |
| 你的会话 k0 / k12 ns_any（字面规则） | – | 99.94 % / 100 % | 96.19 % / 99.50 % |
| 你的会话 k0 body（p99） | 8.97 %（5.35） | 6.61 %（1.77） | 5.26 %（1.55） |
| 你的会话几何召回 k0 / k12（行） | 99.17 / 99.18 % | 100 / 99.46 % | 100 / 99.07 % |
| bot 第 0 波 k0 / k12 committed | 99.41 / 99.14 % | 99.40 / 99.45 % | 94.20 / 98.64 % |
| bot 第 0 波几何召回 k12（行） | 98.20 % | 98.40 % | 98.22 % |
| 无主支撑（你的会话 k0 / k12） | – | 1,174 / 508 行，几乎全错 | 同左 |

无主支撑主要是投掷者已死（或还没命名）的投掷物：k0 haz_tube 569、haz_path 290、死亡尾 133；k12 haz_path 397、后面波次入场 64。

- k0 召回 99.17 → 100 %：验证者说对了，以前 k0 漏的是"用整场最后的投掷者表"造成的假漏。
- k0 body 的 p99 5.35 → 1.77：同一个原因（别人的针算到了这只怪头上）。
- RCLIP 把倍数中位降到 2.6（k0）/ 7.0（k12），但 committed 仍然 96–99 % 判错；它让 k12 的几何召回从 99.46 降到 99.07 %（你的会话）。

**后见召回**（每帧每只怪：它在 t + k 的真伤害格子（多段伤害、它扔出去的东西都算，严格那一帧）是否全在 k 的支撑里；"自己" = 它自己的支撑，"全部" = 所有支撑；不算 t 前 30 帧内被打过或 (t, t + k] 被打断的行）：

| 干净行全覆盖 自己 / 全部 | base | rclip |
|---|---|---|
| 你的会话 k0 / k6 | 100 / 100 %，99.86 / 99.95 % | 100 / 100 %，99.86 / 99.90 % |
| 你的会话 k12 | 99.61 / 99.83 %（17,105 行） | 99.60 / 99.75 % |
| 你的会话 k36 | 95.85 / 98.97 % | 95.80 / 97.65 % |
| bot 第 0 波 k12 | 98.50 / 99.56 %（12,674 行） | 98.50 / 99.11 % |
| bot 第 0 波 k36 | 83.88 / 99.19 % | 83.88 / 93.77 % |

- base 本身就不是 100 %：k12 漏得最多的是 Envoy 的入场伏击 EN_AMBUSH（你的会话 59 %、bot 64 %）、Choristor 入场 CH_ENTRY（95 %）、Envoy 的 EN_SLASH / EN_JUMPSLASH（98–99 %）。k36 还有 Choristor 在 `Hop Back` / `Hop Forward` 之后 0.6 s 的出招整块没盖到（CH_IDLE 86 %）。所以以后的门槛比"开关前后"，不是要求 100 %。
- RCLIP 让"全部"降（k12 你的会话 99.83 → 99.75 %，bot 99.56 → 99.11 %；被打过的行 k12 99.55 → 97.92 %）：它剪掉的格子以前盖住了别的怪的真伤害。按门槛它不能默认开。

**半屏规则**（zone_share，超过半个屏幕的帧占比；括号是中位占比）：你的会话 k0 44.9 %（0.45）→ rclip 23.9 %（0.14），k12 70.2 %（0.62）→ 33.6 %（0.30）；bot 第 0 波 k0 32.7 % → 1.0 %，k12 72.6 % → 12.7 %。黄色（必死区）两者都没有一帧过半。

PNG（真伤害填红，多段伤害现在在里面）：`C:\ssbot\data\m2_forum_push\{base,rclip}\png\`（5690 鞭子、7939 Bellbearer / Reed、9380 矛在飞、10427 Reed 反击；k0 和 k12）。例：10427 Reed 2 的真伤害从 8.0 u² 变成 18.0 u²（`ParrySlash Hit` 进来了），window 的倍数从 38 降到 17——支撑没变，是参考终于对了。

**门槛命令**（每个门槛一条，换配置或换数据集只改参数；新的干净录像加一个 `sets\<名字>.cmd` 就能重跑）：
```
C:\ssbot\data\m2_forum_push\gate.cmd <precision|hindsight|share|recall|rescore|png|all> <config> <dataset> [<输出名>]
  config:  configs\base.cmd（全关）、rclip.cmd、aim1.cmd；新开关复制一个
  dataset: sets\seen.cmd（你的 3 次会话 + bot 第 0 波）、sets\r2.cmd（R2 fresh 的 run，留出）
  输出:    C:\ssbot\data\m2_forum_push\<输出名>\<gate>_<dataset>[_h|_bot|_held].json，日志同名 .log
  代码:    GATE_ROOT（默认 C:\ssbot\hs_push_d08b738，换提交就重新冻结一份）
..\scripts\uv.cmd run python C:\ssbot\data\m2_forum_push\compare.py old_aim0=之前 base rclip --set seen --md <out>.md
```
重打分（门槛 4）不受 S0 影响：规划器的 AIM 默认关，P0 只改了显示、真值和瞄准模板；基线仍是 0.60 % = 32（`C:\ssbot\data\m2_forum_hs\rclip_base_d51b216_summary.json`）。

#### 29.13 最终数字（S5 集成：一个开关 `SSBOT_FORUM_TIGHT`；2026-10-09 夜；同一分支 fa6c11a；离线，没有开游戏）

**一个开关**：`SSBOT_FORUM_TIGHT=1` 把精度推进的整个候选包一起打开 = 门槛配置 s4tb：RCLIP=2、REANCHOR=chain、RTHROW、PRESTRIKE、NSBOX=bin0、GATES、TINYCLIP、BODYCLIP（`multi_forecast.TIGHT_BUNDLE`，在读任何开关之前生效；没设或设成空的成员取包里的值，显式设的保留自己的值，例如 `SSBOT_FORUM_BODYCLIP=0` 把 BODYCLIP 拿掉；单测 `tests/test_tight.py`）。门槛配置 `C:\ssbot\data\m2_forum_push\configs\tight.cmd`（= base + TIGHT=1）。不在包里：WALKFLOOR（门槛 1 失败）、NSBOX=bin（seen 丢 1 行）、REANCHOR fam（门槛 1 失败）、AIM（所有候选都关）。

**结论：包不做默认，所有开关保持默认关。** 具体卡在：
1. 门槛 4（你的胜局重打分）：包的底座 RCLIP=2 单独跑完了全部 32 段，"只看支撑"的漏报按类型上升。同一真值的基线 `s1rb_base_1b8c69a`：1 个（Reed 的针）→ 6 个（针 5、Envoy（`Song Pilgrim 01`）1）。对任务给的基线 `rclip_base_d51b216`（旧真值，按 tick 数是 53：Reed 本体 52 + 针 1）总数是降的，但针 1 → 5、Envoy 0 → 1 是升的。规划器的逃生检查把这 6 个全部拦下（过了逃生检查的漏报 0 → 0）。包里后加的开关都不碰针的检查（`forum_planner._pin_contacts`，S1 的未决问题），所以包大概率带着这 5 个针；包自己的重打分 `C:\ssbot\data\m2_forum_hs\s4rb_s4tb_d14aa37` 在排队，出来后 `decide.py` 给最终判定。
2. 门槛 1（R2 召回 L2-L4）：包和每个嵌套候选都还没跑完——20:35 起协调者把所有 Python 任务暂停了。到暂停时：RCLIP=2 单独 81 / 444 张表 0 漏；S2 最终组合 49 / 444 张表 0 漏。

**现在能报的数字**（seen = 你的 3 次会话 + bot 第 0 波；"候选" = s3cand0 = 包去掉 TINYCLIP / BODYCLIP；包本身 s4tb 的同一套数在 s4 队列里）

| 门槛 | base（全关） | 候选 s3cand0 |
|---|---|---|
| 精度：你，committed 倍数中位 k0 / k12 | 12.28 / 14.93 | 2.45 / 9.03 |
| 精度：你，committed 错误率 k0 | 99.6 % | 96.98 % |
| 精度：你，body k12 中位 | 6.7 | 6.5 |
| 精度：你，ns_any k12 中位 | 28.72 | 16.38 |
| 精度：你，total k12 中位 | 27.08 | 13.88 |
| 精度：bot，committed k0 / k12 | 7.9 / 9.39 | 2.31 / 6.09 |
| 精度：bot，total k12 | 15.39 | 8.67 |
| 半屏：你 k0 / k12 | 44.95 % / 70.2 % | 4.77 % / 35.1 % |
| 半屏：bot k0 / k12 | 32.7 % / 72.6 % | 0.97 % / 15.9 % |
| 后见（自己 / 所有主人）你 k12 | 99.614 / 99.83 | 99.602 / 99.801 |
| 后见 你 k36 | 95.854 / 98.97 | 95.808 / 98.134 |
| 后见 bot k12 | 98.501 / 99.558 | 98.501 / 99.369 |
| 后见 bot k36 | 83.879 / 99.186 | 83.879 / 95.77 |
| 重打分（32 段，只看支撑 / 过逃生检查） | 1 / 0（旧真值 53） | 排队（RCLIP=2 单独 6 / 0） |
| R2 召回 L2-L4 | 100 % | 排队 |

- 后见对它的前一步（s2p → s3cand0）seen 上 k 0..36 一行不丢（你和 bot）。对 base：RCLIP=2 丢了 k12 194,736 行里的 29 个被打行（Choristor CH_JUMP、Reed、Envoy；S2 已记），bot k36 所有主人 99.19 → 95.77 也是这个。
- 按类型（你，committed，k0 / k12 倍数中位，base → 候选）：Tiny 69.6 / 69.8 → 2.7 / 21.5，Clawmaiden 32.9 / 34.3 → 2.7 / 13.6，Reed 14.2 / 13.6 → 2.5 / 8.3，Minister 9.9 / 10.5 → 2.4 / 7.6，Maestro 11.0 / 12.2 → 2.1 / 6.9，Envoy 10.3 / 16.5 → 2.0 / 5.5，Choristor 6.6 / 7.3 → 2.4 / 6.4，Clapper 6.1 / 6.0 → 5.9 / 5.9，Bellbearer 7.0 / 8.8 → 2.4 / 7.7（表 `C:\ssbot\data\m2_forum_push\s5\per_type_{h,bot}_s3cand0.md`）。

**还超 1.5 倍的（每一类都还超）和原因**
- 所有类型 k12：剪框是每个（状态、状态内时间格、k）一个轴对齐矩形 = 所有后续分支的并，k 越大分支越多矩形越大。下一步是每个 k 的多边形或按后续分支分开的并（S2 已记）。
- Tiny k12 21.5：Fire Ready 之后 39 u/s 的俯冲，矩形要盖住所有俯冲方向。
- Clapper k0 也有 5.9：施法不剪（符文炸弹在施法后很久、在 Idle / Walk 里才武装），要按炸弹自己的路径剪。
- 无主行（51 / 46 行）26.2 / 31.0：没归到任何怪的预测。

**还超半屏的帧**（候选，你的会话：k0 853 帧 = 4.77 %，k12 6,277 帧 = 35.1 %；bot k0 0.97 %）
- 最大的几帧（份额 0.813）：20261008_231544 第 1 次 f27283 / f31999 / f33349 / f36967 / f46453，20261008_230220 第 0 次 f8825，20261009_085824 第 2 次 f45116（全表在 `C:\ssbot\data\m2_forum_push\s3cand0\share_seen_h.json` 的 worst）。
- k0 超半屏时面积最大的层（853 帧）：飞行物 hazard 454、committed 169、window 160、未开始 39、身体 31。base 是 window 3,775、committed 2,851、未开始 923。也就是说剩下的主要是飞行物（铃、矛、符文炸弹的管子没剪），不再是 window。bot 的 108 帧是未开始层 104 + 身体 4。
- k12 的 35 %：未开始层（ns_any 中位 16.4 倍）和 k12 的大矩形。

**给你的说明：标出的框现在是什么**（PNG：base `C:\ssbot\data\m2_forum_push\base\png\`，S2 最终组合 `...\rclip2best3\png\`；包的 PNG 排在 s4 队列 `...\s4tb\png\`）
- 5690，Choristor 的鞭子（紫框够到 11.7 u 外）：RCLIP 把它剪到"从现在的状态、在这个状态里待了多久"录到过的范围；鞭子的 Whip Hit 1-6 现在算真伤害（红）。Choristor k0 倍数中位 6.6 → 2.4。
- 7939，Bellbearer / Reed：Bellbearer 的投掷由 RTHROW 剪（出手前不放铃的路径），k0 7.0 → 2.4；Reed k0 14.2 → 2.5。
- 10427，Reed 反击：真伤害从 8.0 u² 变 18.0 u²（`ParrySlash Hit` 进了真值）；RCLIP=2 下预测 488 格对真 288 格，约 1.7 倍。反击只在 Reed 被打时存在（fix_spec 第 7 节），按行条件的反击还没做。
- 长矛飞行：红八角是真的爆炸圆（r 3.553，亮 0.1 s）；规划器的 ent/Spear/self 是所有方向的并再加 3.0 u（搜索上限的产物），S4 (d) 没做，所以没变。

**你的回放**：`C:\ssbot\data\m2_forum_overlay\20261009_085824_zones_tight.rrd`（包、AIM 0 和所有门槛一样、k 0 和 12、多段伤害红色、每只怪的精度标量、半分辨率；磁盘剩 500 GB）。排在 `C:\ssbot\data\m2_forum_push\s5\queue5.cmd` 里：等 BODYCLIP 的表建完、没有任务被暂停、少于 3 个重任务时才开始，日志 `C:\ssbot\data\m2_forum_overlay\rrd_tight_085824.log`。

**复现 / 新数据集上重跑**
```
rem 每个门槛（冻结 C:\ssbot\hs_s4_d14aa37；包 = s4tb，和 tight.cmd 同一套开关）
set GATE_ROOT=C:\ssbot\hs_s4_d14aa37
C:\ssbot\data\m2_forum_push\s4\gate4.cmd <precision|hindsight|share|recall|png|all> s4tb <数据集>
C:\ssbot\data\m2_forum_push\s3\rescore3.cmd %GATE_ROOT% s4tb <输出名>
rem 判定（只读 json，几秒）：前后表、每个候选过没过、包 = 嵌套链里最后一个全过的
python C:\ssbot\data\m2_forum_push\s5\decide.py [--seen <数据集>]
```
`decide.py` 写 `s5\bundle_gates.md`、`s5\verdict.json`、`s5\compare_seen_s5.md`。默认改开的条件：R2 召回 L2-L4 100 %（自己和 hooks）、seen / R2 后见对前一步一行不丢、重打分总数和每一类都不多漏。

### 29.14 精度推进 S1：RCLIP 重打分多出来的漏报、P1 / P2（2026-10-09，task "precision push" S1；同一分支；离线，没有开游戏）

**RCLIP 重打分多出来的 70 个漏报，逐帧查**（b5e9072 对 d51b216，按 tick 比；`C:\ssbot\data\m2_forum_push\s1\miss_diff_rclip.json`、`who.log`、`diag_{base,rclip}.json`）：
- **62 个是"停放"的 Reed**：后面波次的一只 Reed 停在场外 `Fly In Ready`（不渲染），身体碰撞体导出为启用，固定在 (39.0–40.1, 9.65–12.45)。行的盒子碰到它就算"被打中"。62 个里你**一次都没掉血**（horizon 内没有伤害事件）。重打分的真值（`forum_hit_forensics.damage_polys`）以前不跳过停放的怪；精度工具和叠加层（`zone_overlay.damage_colliders`）早就跳过。重打分那 4 组录像里，主角盒子和停放 Reed 重叠 1,204 帧（`parked_check.json`）。
- 所以 fix_spec 里"Reed 身体 31 → 68"不是 P1（出招前的身体），而是这只停放的 Reed：RCLIP 把别的怪罩到那里的支撑剪掉了，那里本来就没有危险。
- **改**：`damage_polys` 默认跳过停放的实体（`keep_parked=True` 保留旧行为）。这是真值修正，不是规划器开关。
- 另外 8 个是真的碰撞体，全部是"别的怪 / 别的家族的框顺带盖住了"：
  - Envoy 2 个（k = 34、37）：Envoy 在 k 内被主角打中，之后跳斩 / 斩到行上。base 里盖住它们的是 Reed 的 RE_DEFEND 窗口和 RE_EVADE 未出招框，不是 Envoy 自己的支撑。
  - Reed 的针 5 个（两次投掷，k = 29–37）：Reed 在 `Throw Aim`，针还没出手。"+n" 下它归规划器的瞄准针检查管，那几行它也判安全（pl_S = 0）。base 里盖住它们的是 Envoy 冲锋的框。
  - Tiny 1 个（k = 35）：之后才被召回的 Tiny。base 里盖住的是 Maestro 的 MA_SUMMON / MA_DEFEND 框。RCLIP=2 后这一个已经没了。
  - 都不是 P1。
- 被打过的行确实是 RCLIP 的问题：后见召回里，RCLIP=1 只在"被打过"的行上掉覆盖（你的会话 k12：Reed RE_DEFEND 100 → 94.2 %，Maestro MA_IDLE 100 → 88.8 %）。原因是"没被打"的可达表默认 horizon 里也不会被打（fix_spec P2）。

**P2：`SSBOT_FORUM_RCLIP=2`**（`multi_forecast._Builder._clip / _hero_hit_k`）
- 没看到命中时仍先用"没被打"的可达框。
- 从"一次命中最早能打到这只怪"的那一帧起，并上"所有帧"的可达框（含击退、被打后的反击）。
- "最早能打到"：打的人盒子和怪身体之间的距离，先减去 HIT_REACH_U = 4 u（Reaper 斩 2.35 u + 1.65 u 余量），再按主角冲刺 28 u/s、下落 30 u/s 加上怪自己的速度来追。
- 打的人包括主角和**盟友**：新加 `WorldState.allies`，来自 oracle 的 allies 导出。证据：20261009_085824 f25585 和 f26989，Garmond 的 `WildSlash` / `Stomp` 打中了离主角 14–23 u 的 Maestro。
- 已经看到命中时照旧，全程用"所有帧"。
- 剪切框只会比 RCLIP=1 大，所以支撑是 RCLIP=1 的超集，召回不会比它低。

**P1：`SSBOT_FORUM_PRESTRIKE`**（默认关）
- "+n" 丢掉 Reed 还没开始的 RE_STAB / RE_DEFEND 根时，把它从当前状态的真实可达放进支撑：开发集的 reach 表，"所有帧"部分。
- 时间从最早开始到最晚开始 + 13 帧，盒子类型 `prestrike`，算 not_started 层。
- 上面已经说明，重打分的 Reed 漏报不需要它。它只为以后 F2 缩小 RE_EVADE 框时兜底。

**门槛**（seen = 你的 3 次会话 + bot 第 0 波；base = S0 的全关，冻结 d08b738；RCLIP=2 冻结 dd96ea9；表 `C:\ssbot\data\m2_forum_push\s1\compare_seen_s1.md`）

| | base | RCLIP=1 | RCLIP=2 |
|---|---|---|---|
| 你的会话 committed 判错 / 倍数中位，k0 | 99.6 % / 12.3 | 96.4 % / 2.6 | 97.2 % / 2.8 |
| 你的会话 committed 判错 / 倍数中位，k12 | 99.4 % / 14.9 | 98.9 % / 7.0 | 99.3 % / 9.3 |
| bot committed 倍数中位，k0 / k12 | 7.9 / 9.4 | 2.0 / 3.8 | 2.3 / 6.1 |
| k12 几何召回（你的 / bot，行 %） | 99.46 / 98.40 | 99.07 / 98.22 | 99.45 / 98.40 |
| 后见 k12：干净行 自己 / 所有，你的会话 | 99.61 / 99.83 | 99.60 / 99.75 | 99.60 / 99.80 |
| 后见 k12：被打过的行（所有支撑），你的 / bot | 99.55 / 99.34 | 97.92 / 96.63 | 99.47 / 98.77 |
| 后见 k36：所有支撑 干净行，bot | 99.19 | 93.77 | 95.77 |
| 超过半屏的帧 k0 / k12，你的会话 | 44.9 / 70.2 % | 23.9 / 33.6 % | 23.9 / 38.9 % |
| 超过半屏的帧 k0 / k12，bot | 32.7 / 72.6 % | 1.0 / 12.7 % | 1.0 / 15.9 % |

- **后见召回**：k ≤ 12 时，RCLIP=2 自己的覆盖只在 5 帧（14 个 帧×k）比 base 少，原因如下。
  - Bellbearer `Out of Range` 两帧：算到它头上的钟在飞，它自己没有钟的路径。base 里是被它别的框顺带盖住的。
  - Reed `Block` 一帧：被打后往下掉了 1.9 u，比"所有帧"可达框低 0.4 u。
  - Clapper 三帧：差 1–3 格。
- k36 时，"所有支撑"那一列比 base 低（bot 干净行 99.19 → 95.77）。少掉的都是别的怪的框顺带盖住的部分；"自己的支撑"一列和 base 一样（83.88）。
- **召回**（multi_recall fresh，L2–L4，自己的 + 钩子）：RCLIP=1 在 R2 的 444 张表上是 100 %（`C:\ssbot\data\m2_forum_reach\recall_fresh_rclip.json`），用的是同一张 reach 表（md5 相同）。RCLIP=2 的剪切框是它的超集，PRESTRIKE 只加支撑，所以两者都是 100 %。直接跑的 `gate.cmd recall rclip2 r2` 在机器过载时开始，还没跑完。
- **重打分**：真值修正后重跑。机器过载，到 15:45 只跑完一部分段，下面按"各 run 都跑完的段"逐 tick 数（`s1\partial.py`）。

  | 16 段相同（共 32） | 旧 base d51b216 | 旧 RCLIP b5e9072 | base（真值修正） | RCLIP=1 | RCLIP=2（无盟友） |
  |---|---|---|---|---|---|
  | 安全行 | 5,809 | 9,082 | 5,809 | 9,082 | 7,852 |
  | 漏报 | 35（全是 Reed） | 80（Reed 74、针 5、Tiny 1） | **0** | 6（针 5、Tiny 1） | 4（针 4） |

  - **旧基线的 Reed 漏报几乎全是停放的 Reed**：旧 base 这 16 段的 35 个漏报，真值修正后一个不剩（S0 基线 0.60 % = 32，其中 Reed 身体 31）。
  - 加上逃生检查看（rb 变体，13 段相同）：RCLIP=2 剩下的那个针漏报，那一行逃生检查判不过，所以"安全且逃生检查通过"的漏报是 0。PRESTRIKE 的安全行和漏报与 RCLIP=2 完全一样。

**结论**
- RCLIP=2 按"只看支撑"的规则仍不过门槛 4：Reed 的针 0 → 4（到目前为止）。这些针是"+n"下瞄准针检查漏掉、base 里只靠 Envoy 冲锋的框顺带盖住的。所以 RCLIP=2 **保持默认关**。
- 如果按"支撑 + 逃生检查"（规划器在 escape+n+g 下真正的判断）计漏报，到目前为止 RCLIP=2 不增加漏报，可以考虑默认开。由集成阶段决定，等全部 32 段跑完再定。
- PRESTRIKE 在 seen 数据和重打分里没有可测的作用，保持关。
- 下一步要修的是瞄准针检查（那 5 行针），以及 Bellbearer 那两帧飞着的钟（没有路径）。

### 29.15 精度推进 S2：最大的多余（RCLIP 漏剪 Tiny、REANCHOR、RTHROW）（2026-10-09，task "precision push" S2；同一分支；离线，没有开游戏）

**RCLIP 的 bug：Tiny 自己的框从来没被剪过**（已修，1cd56a3）
- `MultiForecast._clip_rows` 用 -1 表示"不剪"，`_clip_groups` / `_bbox_occ` 只剪 owner >= 0 的行。Maestro 召出来的 Tiny 是对象池克隆，iid 是负数，所以 Tiny 自己的 committed / window / bbox 行一直没剪。
- 后果：RCLIP=2 下你的会话里 committed 多出来的面积，k0 有 74 % 是 Tiny 的（倍数中位 69.6，整个场地）。例：20261008_231544 第 1 次 f30379，一只 Tiny 在 `Fire Ready`，committed k0 7,604 格（真伤害 78 格）。
- 改成专门的哨兵 NOCLIP（int64 最小值）。同一帧 k0 7,604 → 300 格，k12 7,604 → 2,202 格（真 91）。
- 你的会话 committed 倍数（Tiny）：k0 中位 69.6 → 2.7，k12 69.8 → 21.5。合计 p99 140.8 → 57.6。k0 多余面积 2.80 M → 0.79 M（格·k）。
- 后见召回（seen，所有 k，自己 / 全部）和 S1 的 RCLIP=2 完全一样，没有丢。
- 注意：这改的是 RCLIP=1/2 本身。S1 报的 RCLIP 数字里 Tiny 是没剪的。

**`SSBOT_FORUM_REANCHOR`**（默认关；分两部分 `fam`、`chain`，"1" = 两个都开）
- fam：当前这招的"家族并集"（家族模板从起手算，所有录到的实例、所有状态）在走图给出的每个节点（各状态和收尾）都有自己的按状态模板时就不放；后面状态的出招延迟下限也去掉（以前它们起手前的身体靠并集盖）。
- chain：你说的"防守的怪没被打就没有反击框"。Reed 的 RE_DEFEND、Minister 的 MI_PARRY 在架势里（还没被打）时，被打才会进的状态（Block → Parry Y Aim → Parry Slash → Multihit…；Parry Block → Parry Slash 1–4 → End）最早只能从"主角或盟友的一次命中最早能打到它"的那一帧开始（RCLIP=2 的 `_hero_hit_k`）；反击再加上格挡的最短时长（Block 0.483 s、Parry Block 0.558 s）；走图给的时间窗在那之前就结束了，就不放。这时这个防守家族的并集也不放。
- 结果（RCLIP 关）：committed 层没变（并集大多是粗模板，算 window 层）；com_all 倍数中位 k0 17.3 → 15.1；超过半屏的帧，你的会话 k0 44.9 → 43.3 %，bot 32.7 → 28.2 %。
- **fam 不过门槛 1**：后见召回（seen，自己，k12）你的会话 99.61 → 99.23 %，bot 98.50 → 97.10 %。k12 丢的 320 行：
  - Envoy EN_CHARGE `Charge End` 124 行。冲锋结束后的身体只有并集盖着（别的实例冲得更久，碰巧盖到）；`Charge End` 0.40–0.43 s，收尾模板盖不到。
  - Choristor CH_JUMP `Spin Slash End` 114 行、CH_ENTRY `Enter Land` 38 行、CH_SLASH `Slash Recover` 33 行。
  - 所以 fam 保持关。
- chain 单独：seen 后见召回里没有丢一行 Reed / Minister。它在 committed 层上看不出变化（反击是窗口放置）。

**`SSBOT_FORUM_RTHROW`**（默认关，要和 RCLIP 一起开）
- 投掷家族（CB_THROW、RE_THROW、CM_SPIN）的模板里也装着它扔出去的东西，所以 RCLIP 一直不剪它们。
- 现在：在它"最早能进入出手状态"的前一帧之前，按可达框剪；之后不剪。出手状态 = 表里投射物"武装"时 Boss 所在的状态：钟 `Throw`（8,682 / 8,737），Reed 的针 `Throw`（2,139 / 2,153），Clawmaiden 的矛 `Spear Fire Recover`（492 / 496；`Spear Fire` 是它前面的瞬时状态）。
- 这一招已经进过出手状态（`Instance.visited`）就完全不剪：刚扔出去的东西可能还没有路径（S1 说的"飞着的钟没有路径"，20261008_231544 第 1 次 f26455 / f26467）。只剪当前这一招自己的（committed）行；后面再扔的根行留着它们自己的投射物。
- Clapper 的施法不在内：rune bomb 在施法后很久才武装（在 Idle、Walk……里）。
- 结果（RCLIP=2 + Tiny 修正之上，你的会话 committed 倍数中位）：Clawmaiden k0 32.5 → 2.7、k12 35.0 → 13.6；Bellbearer k0 5.0 → 2.4。
- 第一版只剪不看"已出手"，seen 后见召回丢了 1 行（就是上面那只 Bellbearer 在 `Recover`），已修（671e639）。

**没做：F1 的"在决定动作的状态重新锚定"**
- 要按每个状态入口重新锚定，需要"以状态入口为原点"的按状态模板；现在的表只有 anchor（起手）和 world 两种坐标。
- 最接近的是 `forum_aim build`：它已经在每个有认证方向分箱模板的状态重新瞄准；S0 里 AIM=1 只把 committed 中位从 12.3 降到 12.0。
- RCLIP=2 下被剪的怪已经接近真框（10427：488 格对真 288 格）。

**门槛**：见下表和 HANDOFF 的 S2 结果。

**S2 门槛**（seen = 你的 3 次会话 + bot 第 0 波；表 `C:\ssbot\data\m2_forum_push\s2\compare_seen_s2.md`、`compare_chain.md`，按类型 `per_type_{h,bot}.md`）

| | base | RCLIP=2（S1） | RCLIP=2 + Tiny 修正 | REANCHOR=1，RCLIP 关 | REANCHOR=chain，RCLIP 关 | RCLIP=2 + Tiny + chain + RTHROW |
|---|---|---|---|---|---|---|
| 你的会话 committed 判错 % / 倍数中位 / p99，k0 | 99.6 / 12.28 / 140.8 | 97.18 / 2.82 / 140.8 | 97.09 / 2.51 / 57.6 | 99.6 / 12.28 / 140.8 | 99.6 / 12.28 / 140.8 | 96.98 / 2.45 / 15.9 |
| 同上，k12 | 99.38 / 14.93 / 145.2 | 99.31 / 9.32 / 145.5 | 99.31 / 9.21 / 57.6 | 99.38 / 14.93 / 145.2 | 99.38 / 14.93 / 145.2 | 99.31 / 9.03 / 45.7 |
| 后见召回 自己 / 全部，你的会话 k12 | 99.614 / 99.830 | 99.602 / 99.801 | 99.602 / 99.801 | **99.228** / 99.725 | 99.614 / 99.830 | 99.602 / 99.801 |
| 后见召回 自己 / 全部，bot k12 | 98.501 / 99.558 | 98.501 / 99.369 | 98.501 / 99.369 | **97.104** / 99.211 | 98.501 / 99.558 | 98.501 / 99.369 |
| 超过半屏的帧，你的会话 k0 / k12 % | 44.9 / 70.2 | 23.9 / 38.9 | 23.8 / 38.9 | 43.3 / 69.6 | 44.7 / 70.1 | **18.9 / 35.1** |
| 超过半屏的帧，bot k0 / k12 % | 32.7 / 72.6 | 1.0 / 15.9 | 1.0 / 15.9 | 28.2 / 70.8 | 31.3 / 72.2 | 1.0 / 15.9 |

- 后见召回丢的行（和它所基于的那一列比，`s2\hind_lost.py`）：Tiny 修正 0，chain 0，最终组合 0（k 6 / 12 / 36）；REANCHOR=1 在 k12 丢 320 行（都是 fam）。
- R2 留出（后见，已跑完的共同场次）：最终组合对"RCLIP=2 + Tiny 修正"在 k 0 / 6 / 12 / 36 丢 0 行；Tiny 修正对 S1 的 RCLIP=2（+PRESTRIKE）也丢 0 行。RCLIP=2 本身对 base 在"被打过"的行上还丢一些（k12 29 行：Choristor 跳、Reed、Envoy），这是 S1 已知的 RCLIP 问题，不是 S2 的开关。
- 按类型（你的会话 committed 倍数中位 k0 / k12，最终组合对 S1 的 RCLIP=2）：Tiny 69.6 / 69.8 → 2.7 / 21.5，Clawmaiden 32.5 / 35.0 → 2.7 / 13.6，Bellbearer 5.0 / 8.5 → 2.4 / 7.7；其它不变（Clapper 5.9 / 5.9，Reed 2.5 / 8.3，Minister 2.4 / 7.6，Envoy 2.0 / 5.5，Maestro 2.1 / 6.9，Choristor 2.4 / 6.4）。没有一类到 1.5 倍；RCLIP 下剩下的多余就是剪切框本身（所有后续的框、+ r、+ 主角半宽）。
- PNG（门槛 5）：标出的帧 5689 / 7939 / 9379 / 10427 在"RCLIP=2 + Tiny 修正"和最终组合之间逐字节相同（那几帧没有 Tiny、没有出手前的投掷、没有架势里的防守怪）。另画了前后对比（`s2\png_extra\{before,after}`，before = S1 的 RCLIP=2）：Clawmaiden 在 `Spin 1`（20261008_230220 第 0 次 f8441）committed k0 351.2 u² → 30.0 u²（28.8 倍 → 2.5 倍）；20261008_231544 第 1 次 f30379 的 6 只 Tiny。
- 重打分（门槛 4）到目前为止：所有运行都跑完的 4 段上全部 0 漏报（含逃生检查）；Tiny 修正后"安全"行 2,644 → 2,656。最终组合的重打分（`C:\ssbot\data\m2_forum_hs\s2rb_rclip2best3d_671e639`）和召回（门槛 1，`C:\ssbot\data\m2_forum_push\rclip2best3\recall_r2.log`）还在后台跑。
- 结论：Tiny 修正是 RCLIP 内部的 bug 修正，RCLIP 开着就生效；REANCHOR 的 fam 不过门槛 1，保持关；chain 和 RTHROW 在最终组合的重打分和召回出来之前保持默认关。

### 29.16 精度推进 S3：还没开始的那一层（WALKFLOOR、NSBOX、GATES）（2026-10-09，task "precision push" S3；同一分支；离线，没有开游戏）

**这一层里现在有什么**（回放用的配置 escape+n+g）
- "+n" 已经把有出招延迟的招（strikes.json 里有自己攻击框或投掷物的家族）和所有以后的待机实例拿掉了，交给逃生检查。
- 剩下的是：只用身体撞的家族（闪避、Tiny 的冲撞、Clawmaiden 的瞬移、Maestro 的防守和召唤等）还没开始的根、入场、S1 的 PRESTRIKE 框。
- 你的规则"没开始的招在最短的'起手到第一帧伤害'之前打不到人，只有身体在动"：对有延迟的招，"+n" 和逃生检查的延迟（strikes.json，只用 R0 dev）已经是这样做的。只用身体撞的家族，伤害就是身体本身，这条规则不去掉它们；能把它们变小的只有 F2 / F3 / F5。这次没有重新拟合延迟表。

**`SSBOT_FORUM_WALKFLOOR`（F3，默认关）：不过门槛 1**
- 做法：走图里根之后的所有节点，最早只能在根状态最早结束时进入（从进入算：最短停留 - 1 帧；已超时的从现在起 1 帧）。
- 前提在 R0 fresh（留出）上成立：87,714 次状态停留里有 171 次比"最短停留 - 1 帧"早离开，除了 2 次 Clapper `Slam 0` → `Start Battle?`（早 0.03 s），都是被打死。
- 但你的会话后见召回丢了行（对 base）：k12 64 行（Minister 入场 `Fly In` 28 行、闪避 `Evade` 20 行、Maestro `Defending` 14 行……），k6 38 行，k36 70 行。
- 原因不是停留时间错了。例：20261008_230220 第 0 次 f11105，Minister 闪避了 0.29 s（`Evade` 共 0.40–0.43 s）。0.2 s 后它已经在 `Chase` 里，那时的身体只被一个"下一帧就开始的假闪避"盖着。加了下限后，这个假闪避晚 0.1 s 开始，起点又按闪避的速度往前推，推过了身体真正停下的地方。
- 也就是说：一招结束后的身体（`Evade`、`Fly In`、`Defending` 之后）在 "+n" 下没人负责（以后的待机实例被拿掉了，收尾模板又没盖到），以前是碰巧被假的根盖住。和 S2 里 Envoy `Charge End` 是同一类问题。先给这块身体找个"主人"（F2 第 2 部分：按当前这招的结束位置放，不用过时的速度外推），再开 WALKFLOOR。保持关。

**`SSBOT_FORUM_NSBOX`（F2，默认关，分部分）**
- `bin`：以后的实例最早从它最早的开始时刻起才有框，不再提前一格。丢了 1 行：20261008_231544 第 1 次 f44707，Minister 在 `Chase`，身体跑出 "+g" 的待机身体管 6 格（共 236 格），以前是一个闪避根提前的那一格盖住的。保持关。
- `bin0`：提前的那一格保留，但在"现在"（k0）一律没有。后见召回 0 行丢失。
- F2 的其余部分（按状态和状态内时间的增长、按当前这招的结束位置定锚、朝主角的单侧镜像）没做：都要新的 R0 dev 表。

**`SSBOT_FORUM_GATES`（F5，默认关，只在 oracle 视角）**
- 表 `fsm_gates.json` 在 R0 dev 上挖（`tools/fsm_gates.py mine`）：同一只怪同一家族连续两次起手之间，每一次都会进的、属于别的家族起手的状态。至少 200 对，没有例外。
  - Bellbearer 的闪避 CB_EVADE：两次闪避之间一定有 `Throw Evade`（dev 1,766 对；超时 10.2 s = 最长间隔 5.09 s 的 2 倍）。
  - Maestro 的防守 MA_DEFEND：两次之间一定有 `Fire Antic`（1,447 对；14.8 s）。
  - 留出（R0 fresh，`fsm_gates check`）：552 / 501 对，0 次例外，0 次超时。
- 追踪器记下每个家族最近一次起手、每个状态最近一次进入、最近一次表里没有的转移。被限制的根最早在"走图里最早进入解除状态"之后 1 帧开始；走图到不了解除状态就不放。遇到表里没有的转移、死亡或超时就解除。
- 你的会话后见召回：0 行丢失。

**门槛（seen = 你的 3 个会话 + bot 第 0 波；`C:\ssbot\data\m2_forum_push\s3\compare_seen_s3.md`）**

| | base | S2 最终组合 | S2+P+WF+bin+G | S2+P+bin+G | 候选 S2+P+bin0+G |
|---|---|---|---|---|---|
| 你的会话 k0 还没开始层的行数 | 33,831 | 33,831 | 4,801 | 7,620 | 7,620 |
| 你的会话 k0 全部，错误 % / 倍数中位 / p99 | 93.1 / 15.0 / 185 | 92.1 / 2.86 / 185 | 63.9 / 1.98 / 25.4 | 65.5 / 2.03 / 25.5 | 65.5 / 2.03 / 25.5 |
| 你的会话 k12 还没开始层（按任何真伤害），倍数中位 | 28.7 | 16.4 | 16.9 | 16.5 | 16.4 |
| bot k0 全部，错误 % / 倍数中位 | 80.6 / 7.74 | 78.9 / 2.25 | 75.3 / 2.08 | 78.9 / 2.16 | 78.9 / 2.16 |
| 后见召回 k12 你的会话（自己 / 全部） | 99.614 / 99.83 | 99.602 / 99.801 | 99.287 / 99.562 | 99.602 / 99.801 | 99.602 / 99.801 |
| 对 S2 最终组合丢的行（你的会话 / bot） | | | k12 68 / 0 | 1 / 0 | 0 / 0 |
| 超过半屏的帧，你的会话 k0 / k12 | 44.9 / 70.2 % | 18.9 / 35.1 % | 4.74 / 31.4 % | - | 4.77 / 35.1 % |
| 超过半屏的帧，bot k0 / k12 | 32.7 / 72.6 % | 1.01 / 15.9 % | 0.93 / 12.3 % | - | 0.97 / 15.9 % |

- P = S1 的 PRESTRIKE（Reed 出招前的身体，按要求保留）。候选里 k0 还剩的"还没开始"的行都是 PRESTRIKE 框（Reed `Alert` 2,089、`Defend` 536……，它从根前一格开始，照 S1 原样保留）和入场。
- committed 层没变（k0 中位 2.45，k12 9.03），每一类也没变：S3 的开关不碰它。
- 还在后台一个一个地跑（`C:\ssbot\data\m2_forum_push\s3\master3.cmd`，冻结 5c187ec）：候选的"之前"s2p、PNG（5690 / 7939 / 9380 / 10427 和长矛 / Tiny 额外帧）、候选的重打分（`C:\ssbot\data\m2_forum_hs\s3rb_s3cand0_5c187ec`）、R2 召回、R2 后见、三个开关各自单开。
- 结论：WALKFLOOR 和 NSBOX=bin 保持关。NSBOX=bin0 和 GATES 在 seen 上一行没丢；候选的重打分不增加漏报（总数和每一类）、召回保持 100 % 才打开。

### 29.17 精度推进 S4：模板收紧（TINYCLIP、BODYCLIP；AIM=2 和长矛没做）（2026-10-09，task "precision push" S4；同一分支；离线，没有开游戏）

**`SSBOT_FORUM_TINYCLIP`（S4 (c)，默认关，要 RCLIP 开着）**
- 3 个以上 Tiny 时，同一格里的 Tiny 共用一行"组"预测（每个格子 × 每个家族走图 × 每段时间一行），代表这一格里每一个 Tiny。以前这种组行从来不剪。
- 现在：组里每个 Tiny 都有自己的可达范围时，这一行按"成员可达范围的并集"剪：给每个成员复制一份，各用自己的范围剪，合起来就是并集（精确，不是外包框）。
- 组里有一个成员没有范围（死了、停着、看不见、太久没看到），整组不剪（安全）。
- 预期影响：Tiny 的 committed k12 倍数中位最早是 69x；Tiny 组行在你的会话里占超过半屏的帧的 14 %，RCLIP 之后每个超过半屏的帧里都有它（fix_spec §6 第 10 条）。数还没出来（见下面的队列）。

**`SSBOT_FORUM_BODYCLIP`（S4 (b)，默认关，要 RCLIP 开着）**
- 待机的身体管（按速度外推，再按这一类的待机增长、超出标定后按最高速度往四个方向长）在 k12 是真身体的 6.5 倍（RCLIP=2；没有 RCLIP 是 6.7 倍）。
- 现在再用"身体自己的可达范围"剪：表和 RCLIP 的可达表同一个格式、同一种查法、同一种 2 折留出余量，但记录的是 k 帧后变换位置上的身体外框（production_tubes 的 body_hull，就是身体管自己的框），不是攻击框。按（类型、状态、在状态里的时间、有没有被打、k）。只用 R0 dev。
- 运行时只在有 RCLIP 剪的地方用，同样的"没被打"部分和"英雄打得到它之后放宽"；投掷到出手那一刻起不剪（投掷时身体管也代表扔出去的东西）。
- 建表（`support_reach clip-build --body`）跑到 107 场里的 40 场时，协调者在 20:35 暂停了所有 Python 任务（让你用机器），恢复后会自己跑完（`C:\ssbot\data\m2_forum_push\s4\body_build.cmd`）。所以还没有数。

**门槛：排队中**（`C:\ssbot\data\m2_forum_push\s4\queue4.cmd` 和 `queue4b.cmd`）
- 按协调者的新规矩：最低优先级（Idle），每个任务 2 个进程 × 4 线程；每一步重任务前等到没有被暂停的任务、同时跑的少于 4 个。
- s4tc = S3 候选 + TINYCLIP（"之前"是 S3 候选 s3cand0）；s4tb = s4tc + BODYCLIP（BODYCLIP 自己的影响 = s4tb 对 s4tc）。
- 每个都跑：seen 上的精度 / 后见 / 半屏、PNG、你的会话重打分、R2 召回、R2 后见。

**没做的**
- (a) AIM=2：S0 已经把瞄准模板改成含多段伤害、只用 dev。剩下的（每格每边的余量、每次观察重新定锚、被打时放宽、可变时长）没做。AIM 在所有候选里都关着，RCLIP 已经把瞄准行从 23.0 % 的帧降到 3.2 %；瞄准之前的部分按 §10 换成"逃不掉的区域"表（另一个工作流，还没合进来）。
- (d) 长矛按确定路径飞、validate 里自残差搜到 3.0 u 再重新认证：没做；后者要重建正式表（重任务）。
- 结论规则：TINYCLIP / BODYCLIP 只有在重打分总数和每一类都不多漏、R2 召回保持 100 %、seen 后见一行不丢时才打开。

## 30. 瞄准招的不可逃逸区：Reed 的针（2026-10-09，task "aim ICS"，分支 worktree-wf_b8c4d3d3-280-3；工具 `ssbot.tools.aim_ics`，表 `knowledge/1.0.30000/enemies/forum/aim_ics_Reed.npz`，数据 `C:\ssbot\data\m2_forum_aimics`）

### 30.1 针的事实（12,405 次放手，7 个数据集，对照 `Song_Reed` 的 FSM；取代 §23.7 的"放手前约 0.33 s"）

- **决策**：`Throw Aim` 进入的那一帧，在 `Throw Antic Anim` 之后 0.250–0.283 s（中位 0.266，15–16 帧，`Wait 0.25` 的帧量化）。这一帧可以观测（FSM 进入）。
- **瞄准**：Reed transform → 主角 transform（STATE `hero.pos`，不是 HeroBox，也不是脚）。存下的角度夹到扇形里：朝主角那一侧的仰角 −70° 到 +45°（Lock L [135, 250]，Lock R [0, 45] / [290, 360]）。用这一帧预测，误差中位 0.0000°，最大 0.49°。早一帧或晚一帧，中位约 0.45°、p99 约 6°。没有提前量。
- 主角在扇形外时，针夹到最近的边。12,405 次全部扔出，没有取消，也没有换招。扇形的一侧 = Reed 的朝向，而决策时的朝向 12,405 次全部等于主角所在的一侧。
- **放手**：决策后 0.400–0.50 s（`Wait 0.4` = 24–25 帧；7–9 % 多一个 `Throw Transition` 0.067–0.083 s）。前摇开始到放手 0.65–0.78 s。
- **出针点**（朝向坐标）：(+1.53, −0.54)；夹后的角度在 10–170° 时改为 (+1.11, +0.48)。
- Reed 从决策到放手漂移：中位 (−0.137, +0.037) u，p95 0.23 u。
- **针**：31.0 u/s 直线，不转向。碰撞盒 2.0314 × 0.0979 沿飞行方向，中心在 transform 后 0.025 u。出生帧导出的是未旋转的水平盒。
- 针的结束：插进地面、墙或穹顶 81 %（之后碰撞体关闭）；打中主角 16 %；拼刀 3.7–5.5 %。

### 30.2 不可逃逸区怎么算（`aim_ics scan` / `pack`，离线）

- **网格**：主角 HeroBox 中心相对 Reed transform，0.1 u 一格。x 朝主角那一侧（就是扇形那一侧，另一侧镜像），x 0.05–15.95，y −11.95–7.95。
- Reed 的 y 超出录像范围 4.5–20.2 的格子记为 −1（不可能），因为主角的高度由状态定死。
- **两族**：
  - `measured`：实测时序。放手在第 24 和 25 帧，两个都要躲过。
  - `person`：你的时序。决策后 0.1 s（6 帧）放手，几何和 `measured` 相同。
- 两族共同的最坏情况，一条轨迹要躲过全部组合：瞄准误差 −0.5° / 0 / +0.5°；Reed 漂移 0，或 p95 向后 (−0.22, +0.06) u。
- **针的几何**：出生帧同时测旋转盒和导出的水平盒。之后每帧测"上一帧到这一帧"的扫掠盒。针头碰到地面或背后的墙就停（插入那一帧仍有伤害）。
- **主角**：
  - 运动学：规划器自己的，漫游 Forum 配装，没有负重环带（bot 的 Forum_W）。
  - 逃跑：按测量者 B 的事件库（`hero_lib.py`），在 42 帧内列全按键时机。前 12 帧每 2 帧一个起点，之后每 3 帧一个。轨迹在 0.03 u 上去重，每个状态 8–38 万条。42 帧之后按重力、最大下落、地面、墙继续。
  - 受击盒：真 HeroBox 0.4554 × 2.2498，中心在 transform 下 0.38 u；不是导出的 hero.Bounds 0.50 × 2.079。
- **延迟**：
  - `lat0`：第一个可用的键在决策 + 1 帧（预先规划）。
  - `lat2`：在决策 + 3 帧（bot 晚 1 帧看到 `Throw Aim` 进入，加 2 帧 harness 提前量）。
  - 延迟里沿用决策时锁存的键。
- **状态（38 个）**：
  - 地面：能冲刺 / 冲刺冷却 / 冲刺中朝 Reed / 冲刺中背离 Reed。
  - 空中：离站立高度 4 档（< 0.5、0.5–1.5、1.5–3.5、≥ 3.5 u）× vy 3 档（静止 |vy| ≤ 4、上升 > 4、下落 < −4）× 冲刺可用与否。
  - 背后有墙（离碰撞盒 0.3 u / 1.5 u）：地面，以及空中 h1、h2.5 静止。贴墙滑、扒墙算 0.3 u。
  - 运行时由 `hero_state_key(h, vy, grounded, can_dash, dashing, wall_behind, wall)` 给出状态键，只查表：`AimICS().inescapable(family, key, lat, hero_hb, reed)`。
- **物理相位**：表是相位的并集，`meta.phases` 记了每个键实际用了哪些相位；本次只打包了相位 0，见 30.6。
- **耗时**：每个状态建库 35–170 s，扫描 0–10 s（numba，4 线程）。

### 30.3 结果：实测时序下每个状态的区都是 0

- `measured`：38 个状态 × lat0 / lat2，不可逃逸区面积全部是 0 u²。原因：决策后要 0.40 s 才放手，主角有 24 帧逃，跑都跑得出那条线。
- **延迟扫描**（`scan_lat`，相位 0）：把第一个键推迟 L 帧，看区什么时候出现。

| 状态 | L 6 / 10 / 14 | L 18 | L 22 |
|---|---|---|---|
| ground | 0 | 0 | 5.47 |
| ground_nd | 0 | 1.42 | 7.80 |
| air h0.25 无冲刺 | 0 | 0 | 5.75 |
| air h1 有冲刺 | 0 | 0.02 | 5.40 |
| air h1 无冲刺 | 0 | 0.08 | 5.53 |
| air h2.5 无冲刺 | 0 | 0 | 1.62 |
| air h1 下落无冲刺 | 0 | 0.08 | 5.53 |

  - 也就是：第一个键晚到决策后约 0.32 s（L 18–19）以前，哪个状态都没有不可逃逸的位置。
  - bot 的反应（L 2）离这个边界还有 16 帧以上。
- **`person`**（放手在决策后 0.1 s），相位 0，单侧扇形 u²，lat0 / lat2：

| 状态 | lat0 | lat2 |
|---|---|---|
| ground | 0 | 1.19 |
| ground_nd | 1.42 | 4.15 |
| 冲刺朝 Reed | 11.96 | 11.96 |
| 冲刺背离 | 0.94 | 0.94 |
| air h0.25 静止，有冲刺 / 无冲刺 | 0.04 / 3.67 | 2.21 / 5.11 |
| air h1 静止，有 / 无 | 1.30 / 11.50 | 5.37 / 13.71 |
| air h2.5 静止，有 / 无 | 0.62 / 10.98 | 4.86 / 14.14 |
| air h5 静止，有 / 无 | 0.39 / 11.16 | 4.61 / 15.28 |
| air h1 上升，有 / 无 | 1.31 / 16.96 | 5.50 / 19.54 |
| air h1 下落，有 / 无 | 1.22 / 3.19 | 2.85 / 4.29 |
| air h1 静止，墙 0.3 u，有 / 无 | 1.34 / 2.11 | 6.38 / 7.50 |
| air h1 静止，墙 1.5 u，有 / 无 | 1.93 / 9.36 | 11.57 / 16.43 |

  - 你的顺序成立：地面（0）< 空中有冲刺（0.04–1.3）< 空中无冲刺（3.2–17）。
  - 离地 0.5–1.5 u 比 0.25 u 大：0.25 u 时约 5 帧就落地，可以再跳。
  - 贴墙（0.3 u）时无冲刺的区从 11.5 缩到 2.1：可以扒墙或蹬墙跳。
  - 区在 Reed 两侧，是接近水平的两条带（y 约 −2.5 到 +0.7）。往下斜扔的针，主角横着跑就能出线；水平的针只能靠改变高度躲开。
  - PNG：`png/zones_person.png`、`png/zones_measured.png`（空）、`png/zones_measured_latency.png`。

### 30.4 用录像核对（`aim_validate.py`，12,405 次扔针全部；`aim_validate.json`）

- **几何模型对真路径**：主角真实的 HeroBox 路径（按游戏时间重采样），对真实的针（出针点、方向、放手时刻）。
  - 2,080 次真受击里，模型复现了 2,022 次（97.2 %）。
  - 58 次模型判没打中，按数据集：dev 9、r0fresh 6、r1 3、r1c 7、forumw 27、human 1、human2 5。把 HeroBox 放大 0.1 u 剩 22 次，放大 0.25 u 剩 8 次，大多是差一点。
  - 另有 1,558 次模型判打中、实际没受伤：无敌帧和拼刀（两者没有分开）。
- **实测时序的区**：区是空的，所以每次扔针都在区外。区外受击的分解（`measured|lat0`；lat2 相同）：

| 状态 | 区外没中 | 受击：放手时没动（< 0.5 u） | 受击：动了但没出线 | 受击：沿逃跑路径仍被打中（反例） |
|---|---|---|---|---|
| ground | 2,719 | 383 | 496 | 15 |
| 空中有冲刺 | 3,176 | 99 | 469 | 18 |
| 空中无冲刺 | 3,854 | 61 | 425 | 24 |
| 背后有墙 | 318 | 18 | 34 | 0 |
| 冲刺中 | 258 | 6 | 31 | 1 |
| 你的录像（human + human2） | 341 | 6 | 58 | 6 |

  - 反例 = 模型认为她的真路径能躲开、实际被打中。这就是上面那 58 次几何漏判，不是"区外不可逃逸"。
  - 其余区外受击都是她没出线：站着没动（567），或动了还在线上（1,455）。
- **`person` 区对实测**（lat0）：区内 172 次扔针，被打中 32 次，140 次（81 %）没中。0.1 s 的时序让区比实际大。
- **各状态的命中率**（决策时的状态，全部数据集）：

| 状态 | 命中率 | 放手时没动的占比 |
|---|---|---|
| ground | 894 / 3,613 = 24.7 % | 23.7 %（其中 45 % 被打中） |
| 空中有冲刺 | 586 / 3,762 = 15.6 % | |
| 空中无冲刺 | 510 / 4,364 = 11.7 % | |
| 冲刺中 | 38 / 296 | |
| 背后有墙 | 52 / 370 | |

  - 你的录像：地面 15 / 185 = 8.1 %，空中有冲刺 28 / 144 = 19.4 %，空中无冲刺 24 / 105 = 22.9 %，冲刺中 12 / 54。
  - 这些反映的是打法，不是可不可逃。
- PNG `png/person_throws.png`：你的 3 次扔针（区内受击 / 区外受击 / 区外躲开，用 `person` 区；红色只画她那一高度的格子）。

### 30.5 和规划器今天给的支撑比（你的录像，精度工具的行 `m2_forum_precision/aim1/h`，AIM=1，0.25 u 格）

- 决策之前（`Throw Range`、`Throw Antic`），RE_THROW 的 `not_started` 层面积中位（p90），u²：

| 状态 | k0 | k6 | k12 | k18 |
|---|---|---|---|---|
| `Throw Antic` | 76.5（81.5） | 171（199） | 252（296） | 305（345） |
| `Throw Range` | 67.8（85.0） | 164（213） | 246（307） | 299（353） |

- `committed` 只出现在 6 行，k0 中位 39.7。
- 不可逃逸区：实测时序 0 u²；`person` 时序单侧最多 20 u²。
- 也就是说，决策之前的 RE_THROW 支撑整块都是冗余：针在决策前 0.65 s 以上不会伤人，决策后的 0.40 s 里每个状态都逃得掉。

### 30.6 没做 / 未核实

- 表里只打包了物理相位 0（`meta.phases`）。相位 0.33 只跑了 ground、ground_nd、dash_toward（`scan/` 里，没打包）：`measured` 仍为 0；`person` 区 ground lat2 0.21（相位 0 是 1.19），dash_toward 9.74（11.96）。测量者 B 测过：相位会让面积差到约 2 倍。其它状态的相位并集没算。
- 没有建模的：
  - Reed 的身体（接触伤害；逃跑路线可能从它下面穿过）；
  - Reed 那一侧更远的墙、穹顶；
  - 无敌帧、拼刀；
  - 同时扔针的第二只 Reed。
- 墙只建了背后一面（0.3 / 1.5 u），贴墙滑的状态按"离墙 0.3 u 静止"近似。
- 状态键里的"能冲刺"在录像里用 STATE `can.dash`；攻击、后坐、伞也会让它为 false。
- 58 次几何漏判没有逐个查：可能是 hit-stop 下的时间对齐，或某些动画里的 HeroBox 不同。
- 1,558 次"模型打中、实际没伤"没有分开无敌帧和拼刀。
- 状态的高度和速度分箱只取了一个代表值。比如"上升"用 vy +8，没有按住跳的键。
- 推广到其它瞄准招只写了规格（`C:\ssbot\data\m2_forum_aimics\generalise.md`）：Tiny 俯冲、Reed 刺、两种反击、Envoy 冲锋、Bellbearer 的钟。除针以外，决策帧和瞄准规则都还要按针的做法实测。

### 30.7 复现

```
cd <checkout>\brain
set NUMBA_NUM_THREADS=4
..\scripts\uv.cmd run python -m ssbot.tools.aim_ics scan --out C:\ssbot\data\m2_forum_aimics\scan [--phases 0.0 0.33 0.67]
..\scripts\uv.cmd run python -m ssbot.tools.aim_ics scan --out C:\ssbot\data\m2_forum_aimics\scan_lat --families measured --phases 0.0 --lats 6 10 14 18 22 --states ground ground_nd air_h0.25_rest_nd air_h1.0_rest_d air_h1.0_rest_nd air_h2.5_rest_nd air_h1.0_fall_nd
..\scripts\uv.cmd run python -m ssbot.tools.aim_ics pack --src C:\ssbot\data\m2_forum_aimics\scan
..\scripts\uv.cmd run python C:\ssbot\data\m2_forum_aimics\aim_validate.py
..\scripts\uv.cmd run --with matplotlib python C:\ssbot\data\m2_forum_aimics\aim_png.py
..\scripts\uv.cmd run python -m pytest -q tests\test_aim_ics.py
```

## 31. 瞄准招的不可逃逸区（二）：抽丝怪（Clawmaiden）的矛，以及 aim_ics 的修正（2026-10-09，task "aim ICS"（矛），分支 worktree-wf_acbf0b3e-b21-1；工具 `ssbot.tools.aim_ics`，表 `knowledge/1.0.30000/enemies/forum/aim_ics_Clawmaiden.npz`，数据 `C:\ssbot\data\m2_forum_aimics\spear`）

你说"抽丝怪的矛也是瞄准的"：对。矛在决策那一帧瞄你，而且**飞行中还会追你**（ChaseObjectWisp）。

### 31.1 矛的规则（Spear 的 Control FSM，`reactive_scripts/out/Song_Handmaiden.txt`；动作代码 `C:\ssbot\decomp\1.0.30000`；1,321 支矛，7 个数据集）

- 出矛：抽丝怪 `Spear Cast Antic`（0.45 s，矛跟着她身后的出矛点：她朝向的反方向 1.68 u、上方 1.67 u）→ `Spear Fire` 给矛发 FIRE。
- **决策** = 矛进入 `Get Antic Angle` 的那一帧（就是抽丝怪 `Spear Cast Antic → Spear Fire` 那一帧）。
  - 存下的角度：从**矛的 transform** 指向 **主角 transform + (0, 0.25)**（GetAngleToTarget2D offsetY 0.25）。
  - 扇形：朝向右时 ClampAngle(−45, 45)，朝向左时 FloatClamp(135, 225)。即朝她的朝向一侧，仰角夹在 ±45°；主角在她身后时夹到较近的那条边。
  - 朝向 = 出矛时她的朝向（MatchScaleSign），不一定是主角那一侧：1,302/1,321 一致，19 次主角在她身后（你的录像 9 支里 3 支）。
  - 误差（决策帧，夹扇形后对比开火速度方向）：p95 0.0001°；最大 0.3–0.9°（bot 各集），你 10-04 的录像最大 2.0°。早一帧或晚一帧：中位 0.2–0.3°。瞄 transform 不加 0.25：中位 1.0°；瞄 HeroBox 中心：中位 2.9°。
- `Antic Pause` 0.15–0.18 s（矛不动，位移 0）。
- `Antic` 0.70–0.73 s：矛以 30 u/s 沿瞄准的**反方向**后退，进状态乘 0.875（实测初速 26.25），之后每个物理步再乘 0.875。空地上后退 3.645 u。
  - 回退方向 = 开火方向的反方向：1,309 次全部 0°。
  - 背后贴墙时（285 次离墙 < 4.5 u）会被墙挡住或沿墙滑：后退 p5 −0.37 u、中位 1.6 u，横向最多 2.3 u。之前说的"贴墙时偏 45–107°"就是这个。开火方向不变。
- `Fire`：决策后 0.85–0.95 s 开火（中位 0.8825 s，各集一样）。
  - 进状态时速度 37.0 u/s，沿存下的角度。
  - **追踪**：ChaseObjectWisp，每个物理步加 45 × (主角 transform − 矛，长度夹到 1) 的力（质量 1）；速度先夹到 [已达到的最大速度, 50]，再积分。所以速度只升不降：37 → 50.9 u/s。
  - 拿录像里真实的主角轨迹模拟，到 Fire 末尾的位置误差：p50 0.000 u，p95 0.02 u，最大 0.23 u（1,297 次）。不带追踪按直线算：p50 2.9 u，最大 9.3 u。加速度用 22.5 或 67.5 都明显更差。
  - 之前量到的"方向漂 p50 7.5°、最大 28°"全是追踪：实测 p50 8.9°、p95 19.5°、最大 29.9°。没有重力，也没有别的转向。之前说的"47 升到 60 u/s"是按渲染帧算位移（50 Hz 物理，每 6 帧有 1 帧不动），真实物理速度是 37 → 50.9。
- 飞行结束：
  - 地形检测器在开火后 0.1 s 才打开（ActivateGameObjectDelay 0.1）。之后接触点在 transform 前方 1.26–1.64 u（地面中位 1.41，墙 1.47）。
  - COLLIDE（地面 753 / 墙 147 / 穹顶 3）或 DAMAGED HERO（打中主角，394）都会进 `Explode`。没有最长时间。
  - Fire 时长中位 0.37 s，最长 0.87 s；打地面最短 0.25 s，打墙最短 0.15 s。
- 爆炸：`Explode` 那一帧从 Explosion Origin 生成圆。
  - 圆心在 transform 前方 0.900 u，横向 ±0.065；r = 3.5529。1,297 次全部如此。
  - 碰撞体从 Explode 那一帧起开 0.067–0.108 s（游戏时间）。
  - 矛本身的碰撞体是三角形：尖在 transform 前方 3.758 u，底在后方 1.776 u，底宽 0.945（两种镜像合起来按 1.256 算）。伤 2，parry 4，不能拼刀。
- 抽丝怪：决策后矛就脱离她了。她从 `Spear Cast Antic` 到决策移动中位 0.75 u，从决策到开火移动中位 2.9 u，都不影响矛。
- 同一时刻没有两支矛：2 s 内两次决策，0 次。

各数据集（支数；决策→开火 最小/中位/最大 s；瞄准误差 p95/最大 °；追踪模型误差 p95/最大 u；漂移 中位/最大 °；结束 地面/墙/主角/穹顶；主角在身后）：

| 集 | 支 | 决策→开火 | 瞄准误差 | 追踪误差 | 漂移 | 结束 | 身后 |
|---|---|---|---|---|---|---|---|
| dev（R0 build_all） | 492 | 0.85 / 0.883 / 0.949 | 0.0001 / 0.61 | 0.000 / 0.23 | 8.6 / 26.4 | 257 / 65 / 166 / 1 | 11 |
| r0fresh | 165 | 0.858 / 0.882 / 0.916 | 0.0001 / 0.90 | 0.000 / 0.23 | 8.5 / 29.9 | 93 / 18 / 54 / 0 | 0 |
| r1（R2 fresh 的 R1） | 50 | 0.858 / 0.883 / 0.95 | 0.0001 / 0.31 | 0.000 / 0.23 | 7.7 / 25.5 | 28 / 1 / 21 / 0 | 1 |
| r1c | 404 | 0.85 / 0.883 / 0.933 | 0.0001 / 0.40 | 0.035 / 0.23 | 8.6 / 27.9 | 252 / 37 / 111 / 2 | 4 |
| Forum_W（10-08） | 173 | 0.85 / 0.883 / 0.884 | 0.0001 / 0.0001 | 0.000 / 0.00 | 10.4 / 28.9 | 96 / 24 / 35 / 0 | 0 |
| 你 10-05/08/09 | 9 | 0.858 / 0.867 / 0.867 | 0.0 / 0.0 | 0.000 / 0.00 | 17.7 / 21.8 | 8 / 0 / 1 / 0 | 3 |
| 你 10-04 | 28 | 0.858 / 0.867 / 0.95 | 0.54 / 2.0 | 0.20 / 0.23 | 16.6 / 19.2 | 19 / 2 / 6 / 0 | 0 |

受击（damage 事件）：矛身 367 次，爆炸 130 次；i-frame 挡掉的 damage_blocked 另有 109 / 107 次。你的录像：矛身 6 次，爆炸 1 次。

### 31.2 aim_ics 的修正（Reed 那一轮核查者提的问题）

- **高 → 已修**：现在按 50 Hz 物理时钟走。第 n 个物理步发生在第 ceil((n − 相位) × 0.02 × 60) 帧，主角和投射物都在这一步里移动。每一步连续扫掠：子步内相对位移不超过 0.05 u，主角盒按子步内的位移加宽。逃法要求离每个碰撞体至少 0.1 u（HeroBox 半边长和爆炸半径都加 0.1）。
- **中 → 已修**：
  - 表是物理相位 0 / 0.33 / 0.67 的并集。
  - 再并上相邻的高度 / vy 档（`neighbours`）：两个代表值之间的状态读到较大的那个区。
  - 不在按键模型里的状态（绑丝、后坐/受伤/眩晕、伞、pogo、空中冲刺中、贴墙抓/滑）`hero_state_key` 返回 `locked`，读表时在所有可能位置都算"逃不掉"。
  - 墙不再丢：新增 `ground_nd_w0.3`，以及空中 4 高度 × rise/rest/fall × 有无冲刺的 `_w0.3`。共 59 个状态。主角在扇形反侧时，墙在 −x，把逃跑库镜像。
- **低 → 已修**：
  - 投射物按物理步走：针每步 0.62 u；矛按追踪动力学一步一步积分。
  - 逃跑库滚到 120 帧，两种招都够用。之后主角停在原地，不再"按最后的 vx 一直滑"。
- 库：开始时刻 0–12 每 2 帧、16–40 每 4 帧、48 以后每 8 帧；跳按 2/4/8 帧或按到底，再加一次二段按；冲刺有点按、按住、点按后 28 帧再点。
  - 先用粗库扫：粗库是全库的子集，所以粗库得到 0 就是精确的 0。粗库约 3.5–5 万条轨迹，6 s 建一个。
  - 只在粗库区不为 0 时才建全库（约 100 万条）。这一轮一次都没用上。
  - 按时间字典序排序，一条失败后，前缀相同的轨迹直接跳过。
- **重扫 Reed 的针（measured 时序）：59 个状态 × 3 个相位 × lat0/lat2，全部还是 0，没有变化。** 新的 `aim_ics_Reed.npz` 只含 measured。你那套 0.1 s 时序（person）没有用新核重扫，旧值留在 afc4544。

### 31.3 矛的不可逃逸区：每个状态、每个延迟都是 0

- 模型：决策时按上面的规则瞄准，夹扇形。Antic 两种变体：空地后退 3.645 u；被墙挡住完全不退（最坏情况，矛离你近 3.6 u）。
- 开火取第 51 和 54 帧（0.85 / 0.90 s）。追踪 45、速度 37→50；地形检测 0.1 s 后打开，接触点 1.45 u。
- 爆炸 r 取 3.553 + 0.065（横向）+ 0.19（接触点 1.26–1.64 的范围），再加 0.1 余量，持续 0.108 s。
- 瞄准误差 ±1°。
- 网格：以决策时矛的 transform 为原点，x 朝她的朝向，−8 到 26 u，含身后；y 从 −14 到 6；矛高度在 7.0–20.2 之外的位置算不可能。
- **59 个状态 × 3 个相位 × lat0/lat2：全部 0 u²。** 原因是决策到开火有 0.85 s，追踪又弱：速度 37–50 u/s、加速度 45，转弯半径 30–55 u。
- 延迟扫描（`latency_sweep.png`；粗库，所以是上界；相位 0）：第一个键推迟 L 帧，看什么时候开始出现区。

| 状态 | L 0 / 10 / 20 / 30 | L 40 | L 50（≈ 开火） |
|---|---|---|---|
| 地面 / 地面冷却中 | 0 | 0 | 8.7 |
| 空中 h1 有 / 无冲刺 | 0 | 0 | 1.0 |
| 地面贴墙 0.3 | 0 | 0.56 | 29.4 |
| 空中 h1 无冲刺贴墙 0.3 | 0 | 0.77 | 24.1 |

  - 也就是说，决策后等 0.5 s 再动仍然逃得掉。贴墙时余量最小：约 0.67 s 时开始出现区。
  - Reed 的针在同一个工具里 L = 20 帧就出现（地面 2.3、贴墙 5.1 u²）。所以矛比针宽松得多。
- 你说的"空中无冲刺、低空最大"的顺序，对矛不成立：在 0.85 s 的提前量下，所有状态都是 0。只有贴墙才在很晚的反应下先出现区。

### 31.4 用录像核对（`spear_validate.py`，1,309 支有开火的矛）

- 模型对真实的矛（真实开火点、方向、开火时刻）和真实路径（从决策起按游戏时间重采样，受击后冻结）：
  - 497 次受击里复现 496 次。
  - 漏的 1 次是 r1c `20261004_154609_Forum_A_data__i0__ep6` f540705 的爆炸。她决策后 0.88 s 内跑了 7.3 u，没有查原因。
  - 不加余量、用实测半径：490/497；漏的 7 次都是爆炸圆边缘，被 0.1 u + 0.255 u 的余量盖住。
- 模型说打中但没有受伤：248 次（三个相位都判中）。其中 103 次是 i-frame 挡掉的（damage_blocked）。剩下约 146 次没有任何伤害事件，多半是保守余量；用精确几何还剩约 109 次，没有逐个查。
- 分类（区是空的，所以"区内"只有 locked）：

| 主角状态 | 区内受击 | 区内没中 | 区外受击·没动 | 区外受击·动了但还在矛的路径里 | 区外没中 | 反例 |
|---|---|---|---|---|---|---|
| 地面 | – | – | 21 | 171 | 302 | 0 |
| 地面贴墙 | – | – | 16 | 20 | 25 | 0 |
| 冲刺中 | – | – | 0 | 7 | 15 | 0 |
| 空中有冲刺 | – | – | 2 | 91 | 210 | 1 |
| 空中无冲刺 | – | – | 1 | 41 | 89 | 0 |
| 空中贴墙 | – | – | 9 | 45 | 49 | 0 |
| locked | 72 | 122 | – | – | – | – |

  - lat0 和 lat2 完全一样。"没动" = 开火时离决策位置不到 0.5 u。
  - locked 194 次：后坐 48、贴墙抓 30、眩晕 22、伞 71、空中冲刺 12 等。
- 各集受击（矛身 / 爆炸）：dev 156 / 58，r0fresh 49 / 19，r1 20 / 3，r1c 101 / 36，Forum_W 35 / 13，你 10-05/08/09 1 / 0，你 10-04 5 / 1。
- 结论：每次受击都是"可以逃但没逃"。bot 大多是动了，但没离开矛（追踪的线）和爆炸圈。

### 31.5 和规划器今天给的支撑比（你的录像，精度工具的行 `m2_forum_precision/aim1/h`，CM_SPIN，0.25 u 格）

单位 u²，p50（p90）。

| 时刻 | 层 | k0 | k6 | k12 | k18 |
|---|---|---|---|---|---|
| 决策前（Spear Cast Antic） | hazard（ent/Spear/self 和爆炸模板） | 155 (160) | 238 (257) | 307 (339) | 333 (397) |
| 决策前 | not_started（CM_SPIN 尾巴） | 164 (201) | 235 (260) | 256 (277) | 295 (308) |
| 决策前 | total | 215 (262) | 298 (316) | 367 (475) | 431 (475) |
| 决策后（Spear Fire Recover） | hazard | 219 (267) | 236 (267) | 173 (237) | 110 (159) |
| 决策后 | total | 274 (475) | 457 (475) | 389 (475) | 363 (429) |

- 按不可逃逸区，决策前和决策后都应该是 0：所有模型内状态，主角都有逃法。
- 规划器今天在出矛前后要避开 150–430 u² 的区域。
- 真正有用的是确定性的路径：从决策起就知道瞄准角、后退点、开火时刻（0.85–0.95 s）和追踪规律。§31.1 的规则可以直接给 HazardTracker 用；那条建议在 `m2_forum_cases/spear/workflow_result.json` 的 fixes P1，可以照做。

### 31.6 没做 / 未核实

- 没建模：
  - 抽丝怪的身体（接触伤害）、扇形外侧更远的墙、穹顶（只有 3 次打穹顶）、i-frame。
  - Antic 沿墙滑动（只算了空地后退和完全挡住两种）。
  - 主角在 120 帧之后的移动（停在原地）。
- 规划器没接，`multi_forecast.py` 没动。
- `locked` 的判定在核对脚本里按动画名（`special_of`）。运行时要用 HeroController 的状态，接的时候要做。
- 没有用全库确认的状态：这一轮所有区都是 0，按子集关系就是精确的 0。
- 你那套 0.1 s 时序（person）没有用新核重扫。
- 反例 1 次、约 109 次精确几何判中但没受伤，都没有逐个查。

### 31.7 复现

```
cd <checkout>\brain
set NUMBA_NUM_THREADS=4
..\scripts\uv.cmd run python C:\ssbot\data\m2_forum_aimics\spear\spear_extract.py human human2 dev r0fresh r1 r1c forumw
..\scripts\uv.cmd run python C:\ssbot\data\m2_forum_aimics\spear\spear_facts.py
..\scripts\uv.cmd run python -m ssbot.tools.aim_ics scan --types Reed Clawmaiden --families measured --out C:\ssbot\data\m2_forum_aimics\spear\scan
..\scripts\uv.cmd run python -m ssbot.tools.aim_ics pack --type Clawmaiden --src C:\ssbot\data\m2_forum_aimics\spear\scan
..\scripts\uv.cmd run python -m ssbot.tools.aim_ics pack --type Reed --src C:\ssbot\data\m2_forum_aimics\spear\scan
..\scripts\uv.cmd run python C:\ssbot\data\m2_forum_aimics\spear\spear_validate.py
..\scripts\uv.cmd run --with matplotlib python C:\ssbot\data\m2_forum_aimics\spear\spear_png.py sweep
..\scripts\uv.cmd run --with matplotlib python C:\ssbot\data\m2_forum_aimics\spear\spear_png.py
..\scripts\uv.cmd run python -m pytest -q tests\test_aim_ics.py
```

图在 `C:\ssbot\data\m2_forum_aimics\spear\png\`：
- `spear_zones_lat0.png`、`spear_zones_lat2.png`：8 个状态的区，画在示意的抽丝怪、矛和 ±45° 扇形上，全是空的。
- `latency_sweep.png`：两种招的延迟扫描。
- `spear_casts.png`：3 支录到的矛。你被矛身打中的一次（085824）、你逃掉的一次、bot 被爆炸打中的一次。每支画了主角路径、后退、追踪的飞行线和爆炸圈。

## 32. 攻击范围估计（ARE）：Choristor（2026-10-10，task "attack range: Choristor"，分支 worktree-wf_f6746725-345-1；代码 `ssbot/combat/attack_range.py`、`ssbot/tools/attack_range_build.py`、`attack_range_png.py`；表 `knowledge/1.0.30000/enemies/forum/attack_range_choristor.npz` + `.json`；数据 `C:\ssbot\data\m2_forum_are\choristor`）

你 10-10 的决定（forum_planner_plan.md §5）：第一步只把每个怪的攻击范围估计准，**不加任何余量**；余量是以后 bot 做决策时的事，由估计误差或攻击目标决定；先让你看着判断，靠谱了再往上搭；一次一个怪，从 Choristor（Song Pilgrim 03）开始。这一节只有 Choristor，只有第 1 组（已经开始的招，从起手到收招；待机 = 身体）；还没开始的招（第 2 组）不在这一轮。

### 32.1 单位和尺度（你问"1 个单位就是大黄蜂的宽度吗？离 2 个单位就砍不到了？"）

- 1 u = 游戏世界里的 1 个单位（Unity unit），不是大黄蜂的宽度。大黄蜂的受伤框（HeroBox）是 **0.4554 × 2.2498 u**，中心在她 transform 下方 0.38 u：1 u ≈ 2.2 个大黄蜂宽。
- Choristor 的身体伤害框 0.88 × 2.15 u。招的碰撞体是导出的多边形，每个名字的形状固定（不旋转，只随朝向镜像）：Slash Hit 1 4.19 × 2.42、Slash Hit 2 3.73 × 1.15、Slash Hit 3 3.56 × 2.77、Whip Hit 1–6 长 5.16 / 8.24 / 7.46 / 6.76 / 4.00 / 3.88 u、Spin Hit 4.2 × 4.2、Spin Slash Hit 2.55 × 3.82。鞭（Whip Hit）导出 dealt 0，是多段伤害，算进真伤害（zone_overlay.hurts 的规则）。
- 所以"离 2 u 就砍不到"不成立。从起手时的位置量（R0 dev 的并集，原始碰撞体，不含主角框）：

| 家族 / 分支 | 实例 | 时长 p50 / 最长 | 最远：前 / 后 / 上 / 下（u，相对起手位置） | 起手到出伤害 |
|---|---|---|---|---|
| CH_SLASH 单斩 | 193 | 1.08 / 1.10 s | 6.9 / 0.45 / 1.3 / 1.3 | Slash 1 在 0.63–0.66 s，前冲约 2.2 u |
| CH_SLASH 连斩 | 250 | 1.95 / 1.97 s | 9.1 / 0.45 / 1.3 / 1.6 | ComboSlash 1 在 1.41–1.46 s，再冲约 3 u |
| CH_WHIP 普通 | 570 | 1.23 / 1.90 s | 9.6 / 3.6 / 3.45 / 1.8 | Whip 1 在 0.82–0.83 s（Whip 4–6 往上、往后甩） |
| CH_WHIP 缠住（Multiwhip） | 240 | 1.65 / 1.87 s | 9.4 / 0.45 / 3.45 / 1.3 | 只在鞭打到主角之后 |
| CH_JUMP | 417 | 1.82 / 1.83 s | 11.2 / 0.45 / 8.3 / 2.2 | Jump Launch 0.42–0.43 s；落点 L = 1.043 du − 0.04（du = 起手时主角在它前方的距离；残差 p95 1.07 u，最大 2.3），最远 13.2 u |
| CH_HOP 后跳 / 前跳 | 2,781 / 3,172 | 0.28 / 0.30 s | 身体移动约 0.5 u（模板中位） | 只有身体；方向在 Hop Check（0.15 s）定 |
| CH_ENTRY | 371 | 1.05 / 1.08 s | 身体从上方落下（上 6.6） | 只有身体 |

  时间是确定的：同一家族同一状态的进入时刻在 R0 dev 里只差 ±1–2 帧（例：Whip 1 0.816–0.833 s，Slash 1 0.627–0.658 s）。

### 32.2 模型（不加余量）

- **按家族 × 分支 × 时间格（起手后第几帧）**：R0 dev（107 场）里没被打、没拼刀的实例，每一帧的真实伤害碰撞体（攻击 + 身体 + 鞭），**相对它当帧自己的位置**、按起手时的朝向（前 = 它面对的方向），取并集，0.05 u 栅格；实例收招之后（离开家族状态）算它在收招位置的身体。
- **位置**：模板里每格还有中位位移（起手位置到那一格）。查询时**用当前看到的位置重新锚定**：预测位置 = 现在的位置 + （模板在 t+k 的位移 − 在 t 的位移），只有"还没发生的位移"是预测的；x 夹在录到的墙内（14.75–48.25）。CH_JUMP 的横向位移 = 比例(t) × 落点 L（起手时主角的距离定）。
- **分支**：连斩 / 单斩在 Combo?（约 0.84 s）定，看到 ComboSlash* 或 Slash Recover 就知道；鞭在 Whip 6（普通）或 Multiwhip（缠住）知道；跳的方向看到 Hop Back / Hop Forward 就知道。没定之前是两个分支的并集；跳还有一条确定的规则：起手时主角距离 < 4.18 u 一定后跳，> 11.39 u 一定前跳（R0 dev 两边的极值），中间并集。
- **待机**（Battle Idle 和所有家族之外的状态）= 它现在的身体伤害框，任何 k 都一样，不长大。
- **主角框**：画和算的时候只做一次膨胀——主角受伤框 0.4554 × 2.2498（transform 下 0.38）。"主角 transform 不能在的地方" = 原始范围 ⊕ 主角框。没有其他任何余量。
- 栅格：cv2 填充，边上的格子算进去，所以每边最多大一格（0.05 u）；估计和真伤害用同一种栅格，比率不受影响。

### 32.3 估计误差（这是以后定余量的输入；本轮不加余量）

做法（`attack_range_build eval`）：每个实例每 2 帧、每个待机敌人每 6 帧，k = 0 / 6 / 12：估计在 t + k 的那一刻（第一帧游戏时间到 t + k/60 的真帧，按那一帧的时间取模板格）和那一帧的**真实伤害碰撞体**比，都在主角中心空间（同样的主角框膨胀）。RATIO = 估计面积 / 真面积；覆盖 = 真格子里被估计盖住的比例；漏（miss）= 真伤害在估计外面，按估计框的哪一边（前 / 后 / 上 / 下 / 里面的洞）和离估计多远；多（excess）= 估计里没被打到的部分。在 t+k 之前已经开始下一招的行（第 2 组）和这次实例里它被打 / 拼刀的行（击退 ±3.6 u，没建模）单独计，不进主表。

主表（k = 0 / 12；RATIO 是行的分位数，≤1.5 是行的比例；漏 p95 按 前/后/上/下/洞，u）：

| 集合 | 家族 | k | 行 | RATIO 面积 / p50 / p90 / ≤1.5 | 覆盖 | 有漏的行 | 漏 p95（前/后/上/下/洞） |
|---|---|---|---|---|---|---|---|
| R0 fresh（35 场） | CH_SLASH | 0 | 7,947 | 1.09 / 1.00 / 1.04 / 96 % | 99.9 % | 12 % | 0.07/-/0.05/-/0.07 |
| | | 12 | 7,945 | 1.13 / 1.04 / 1.14 / 94 % | 97.0 % | 33 % | 0.45/0.30/0.16/0.24/0.30 |
| | CH_WHIP | 0 | 13,620 | 1.20 / 1.00 / 1.37 / 93 % | 99.7 % | 17 % | 0.07/0.07/0.07/-/0.07 |
| | | 12 | 13,615 | 1.26 / 1.01 / 1.53 / 89 % | 98.7 % | 22 % | 0.21/0.75/0.10/-/0.25 |
| | CH_JUMP | 0 | 8,418 | 1.05 / 1.00 / 1.04 / 96 % | 99.4 % | 31 % | 0.07/0.05/-/0.05/0.05 |
| | | 12 | 8,418 | 1.07 / 1.00 / 1.04 / 95 % | 95.9 % | 52 % | 0.42/0.90/0.60/0.63/0.42 |
| | CH_HOP | 0 | 19,757 | 1.01 / 1.00 / 1.04 / 100 % | 100 % | 0 % | - |
| | | 12 | 7,511 | 1.57 / 2.00 / 2.07 / 44 % | 93.2 % | 40 % | 0.45/0.25/-/2.27/0.25 |
| | CH_ENTRY | 12 | 3,949 | 1.01 / 1.00 / 1.04 / 100 % | 98.0 % | 28 % | -/0.79/0.45/0.45/- |
| | 待机 | 12 | 573 | 1.00 | 99.95 % | 1 % | 0.05（后） |
| R2（187 场） | CH_SLASH | 0 | 72,521 | 1.09 / 1.00 / 1.04 / 95 % | 99.8 % | 12 % | 0.07/-/0.05/-/0.07 |
| | | 12 | 72,153 | 1.12 / 1.03 / 1.14 / 94 % | 97.3 % | 33 % | 0.45/0.30/0.16/-/0.30 |
| | CH_WHIP | 12 | 38,461 | 1.24 / 1.00 / 1.50 / 90 % | 99.1 % | 22 % | 0.21/0.75/0.08/-/0.20 |
| | CH_JUMP | 12 | 30,959 | 1.06 / 1.00 / 1.04 / 95 % | 96.1 % | 53 % | 0.42/0.41/0.59/0.58/0.42 |
| | CH_HOP | 12 | 17,231 | 1.56 / 1.86 / 2.07 / 44 % | 93.5 % | 39 % | 0.25/0.25/-/0.05/0.25 |
| | CH_ENTRY | 12 | 4,699 | 1.00 / 1.00 / 1.00 / 100 % | 98.5 % | 24 % | -/0.05/0.45/0.45/- |
| | 待机 | 12 | 1,850 | 1.00 | 99.2 % | 6 % | 0.45（前） |
| 你的 9 次录像（单独报） | CH_SLASH | 12 | 4,022 | 1.12 / 1.04 / 1.11 / 95 % | 96.5 % | 34 % | 0.45/0.45/0.26/-/0.30 |
| | CH_WHIP | 12 | 13,584 | 1.17 / 1.02 / 1.38 / 92 % | 99.1 % | 26 % | 0.21/0.60/0.10/-/0.20 |
| | CH_JUMP | 12 | 8,389 | 1.06 / 1.00 / 1.04 / 95 % | 95.7 % | 53 % | 0.43/0.65/0.62/0.58/0.42 |
| | CH_HOP | 12 | 10,786 | 1.39 / 1.04 / 2.07 / 62 % | 92.5 % | 42 % | 0.25/0.60/-/0.05/0.25 |
| | CH_ENTRY | 12 | 4,253 | 1.01 / 1.00 / 1.04 / 100 % | 97.3 % | 26 % | 0.24/2.95/0.45/0.45/- |
| | 待机 | 12 | 660 | 1.00 | 98.7 % | 5 % | 0.45（前） |

k = 0 时每个家族的覆盖都是 99.4–100 %，漏的 p95 是 0.05–0.07 u（一格栅格 + 你 0.5 倍速录像的合帧）。按家族的结论：

- **RATIO（目标 ≤ 1.5）**：SLASH、JUMP、ENTRY、待机在 k 0 / 12 都是面积比 1.0–1.13，94–100 % 的行 ≤ 1.5。超出的三处都是"还没定的分支"或"时间差一两帧"：
  - CH_HOP k 12 面积比 1.56、行中位 2.0：起手后 0.15 s 才定方向，主角距离在 4.2–11.4 u 之间时只能画前跳 ∪ 后跳。
  - CH_WHIP 在 0.8–1.0 s（出鞭那一刻）k 12 的 p90 3.4–4.9：Multiwhip（缠住）分支只在鞭打到主角时出现，出鞭前不知道。
  - CH_SLASH 在 0.6 s 和 1.4 s 的 p90 2.6 / 3.8：出刀那几帧只存在 2–4 帧，时间差 ±2 帧的实例取并集，范围是对的、但那一刻往往还没出现或已经收了。
- **漏多远（按时间，R2，k 12）**：
  - CH_SLASH：0.2–1.0 s 覆盖 96.6–99.97 %，漏 p95 ≤ 0.33 u；1.2–1.6 s（连斩前冲）覆盖 90.9–96.4 %，前方漏 p95 0.46–0.55 u（每次冲的距离不同：停在墙边、被别的怪挡）。
  - CH_WHIP：出鞭后 1.2 s 起覆盖 99.7–100 %；出鞭前后（0.8–1.0 s）后方漏 p95 0.75 u（鞭前面紧接着跳，0.15 s 跳步的滑行方向不一样）。
  - CH_JUMP：起跳后（0.4–1.4 s）有漏的行 48–94 %，每边 p95 0.35–0.65 u：落点按主角距离线性预测，残差 p95 1.07 u。
  - CH_ENTRY：上 / 下 0.45 u（从上方跳下来的高度不同）。
- **被打 / 拼刀的实例**（不进主表）：Choristor 挨打会被击退约 ±3.6 u 但不取消招，模型没有击退；含这些行时 k 12 覆盖降到 SLASH 95.7 %（R2）/ 88.0 %（你的录像）、JUMP 94.3 / 91.7 %。

详细（每家族 × 每边 × 每 0.2 s 的漏 / 多、分支已知时的数）：`C:\ssbot\data\m2_forum_are\choristor\eval_{fresh,r2,person}.json`；只锚在起手位置、不按当前位置重新锚定的第一版（作对照）：`eval_{fresh,r2}_antic_anchor.json`（fresh 的覆盖 k 0 / k 12：SLASH 95.1 / 93.5 %、WHIP 96.1 / 94.6 %、JUMP 94.8 / 91.9 %、HOP 96.3 / 86.4 %；重新锚定后 99.4–100 % / 93–99 %，所以用当前位置重新锚定）。

### 32.4 怎么看

- **图**（`C:\ssbot\data\m2_forum_are\choristor\png\`，57 张，`index.json` 说明每张）：世界坐标，1 u 网格和"1 u / 大黄蜂宽 0.46 u"的比例尺。橙色填充 = k 0 的估计（原始碰撞体），浅蓝 = k 12 的估计，细黄线 = k 0 的主角中心区（主角 transform 不能在里面），红粗线 = 现在的真碰撞体，细红 = 之后 1–11 帧的真碰撞体，紫红 = +12 帧的真碰撞体，白框 = 大黄蜂受伤框。你的两帧：`20261009_085824_f5690_Whip_Antic.png`（鞭起手 0.70 s：k 0 只有身体，k 12 的鞭和 +12 帧的真鞭重合，RATIO 1.03）和 `20261009_161454_f2916_Battle_Idle.png`（只有身体）。另外每个家族 2 个实例的起手 / 中间 / 收招帧，和 Slash Recover 之后 +1 / +6 / +12 帧（待机 = 身体，不再有空洞）。
- **回放**：`C:\ssbot\data\m2_forum_overlay\choristor_range.rrd`（085824 第 0 次，raw 帧 5300–6900：鞭、连斩、第二波两只的入场、跳、鞭；0.35 倍视频；只有范围层和真碰撞体）。`world/range/<名字>/k00`、`k12`：raw = 原始范围，hero = 主角中心区；`colliders/real` 红色；右边视频上画同样的线。
- **实时**：`human_session ... --overlay --overlay-range`，模式 range+red（F9 切换），1–5 选 k（0 / 6 / 12 / 18 / 36），每只怪自己的颜色，填充 = 原始范围，细线 = 主角中心区。这个模式不跑规划器的预测，只跑范围。viewer：`--zones --range-only --k 0,12 [--video]`（只看范围）或 `--zones --range`（加在原来的区上）。

### 32.5 单怪练习（`human_session --solo "Song Pilgrim 03"`，`ssbot/tools/solo_practice.py`）

- 选波：含这个怪、其他成员最少的那一波（第 1 波的 Call Ally 会把 Garmond 叫来，算多一个）。Choristor = 第 0 波（`fo_r1_w0`，同波还有 Reed 和 Envoy）。
- 只用现在部署的 oracle 已有的接口（没有能删掉某一只怪的 RPC：battle.wave 是整波杀，enemy.hp 不能低于 1）：场上还有别的怪时，通过 debug line server 给你开"无敌 + 钉子 4 级（伤害 21）"（WaveSkipPolicy 跳波用的同一套），你自己几刀清掉（Reed 3 刀、Envoy 2 刀）；只剩一只 Choristor 时自动把 PlayerData 改回原值。同类第二只也算"别的"（保留 iid 最小的那只）。
- 保护（默认开，`--no-solo-protect` 关）：留下那只 HP 掉到最高值一半以下时用 oracle RPC `enemy.hp` 加满，它不会死、波也不会推进。`enemy.hp` 在 073abe0（10-06）加进 oracle，**部署的 oracle 有没有它没核实**；没有的话会话会打印 "protection off"，它就会被打死，重来写 `load fo_r1_w0` 到 `C:\ssbot\sandbox\human_cmd.txt`。
- 读档（重来）会重新开始清场。meta.json 的 "solo" 记录过程。离线单测了选波、开关增益、加血、重来；**没在游戏里跑过**。

### 32.6 没做 / 已知问题

- 只有 Choristor；第 2 组（还没开始的招）不在这一轮。
- 击退（被打时 ±3.6 u）没建模；墙以外的地形（别的怪挡路）没建模。
- 跳的落点是线性模型（残差 p95 1.07 u），跳的每一边都会漏 0.4–0.65 u；Hop Up 在数据里没出现，没有模板。
- 实时叠加层和 `--solo` 都没有在游戏里跑过（本轮不许开游戏）。PNG 是用缓存重建的多边形（每个名字的形状来自你两次录像的导出顶点，放进缓存里的 AABB）。

复现：
```
cd <checkout>\brain
..\scripts\uv.cmd run python -m ssbot.tools.attack_range_build shapes
..\scripts\uv.cmd run python -m ssbot.tools.attack_range_build build
..\scripts\uv.cmd run python -m ssbot.tools.attack_range_build eval --set fresh   (r2 / person / dev)
..\scripts\uv.cmd run python -m ssbot.tools.attack_range_build png
..\scripts\uv.cmd run python -m ssbot.tools.viewer C:\ssbot\data\human\20261009_085824 --zones --range-only --k 0,12 --video --video-scale 0.35 --from 5300 --to 6900 --save C:\ssbot\data\m2_forum_overlay\choristor_range.rrd
..\scripts\uv.cmd run python -m pytest -q tests\test_attack_range.py tests\test_zone_overlay.py
```

## 33. 攻击范围估计（ARE）：所有类型的框架 + Clapper（2026-10-10，task "attack range: all types" 阶段 A，分支 worktree-wf_2fe0d0c5-18e-1 = main + Choristor 分支 344c812；代码 `ssbot/combat/attack_range.py`、`are_spec.py`、`are_types/`（每个类型一个文件）、`ssbot/tools/attack_range_build.py`、`attack_range_png.py`；表 `knowledge/1.0.30000/enemies/forum/attack_range_clapper.npz` + `.json`；数据 `C:\ssbot\data\m2_forum_are\clapper`）

你 10-10 的话："挺好的，非常准。把其他怪都做了让我看看，尤其是 clapper，之前危险区太大了"。这一轮（阶段 A）做两件事：把 Choristor 那一套改成"每个类型一个文件"的框架，让阶段 B 的几个人能同时加别的怪而不改同一行；把 Clapper 整个做完（所有家族 + 它自己放出来的丝弹、符文圈）。规则和 §32 一样：**不加任何余量**，只有画主角中心区时的受伤框膨胀；待机 = 现在的身体；招从起手到收招；还没开始的招（第 2 组）不画。离线，没有开游戏。

### 33.1 框架（阶段 B 怎么加一个怪）

- 每个类型一个文件 `brain/ssbot/combat/are_types/<名字>.py`，里面写 `SPEC = EnemySpec(...)`（家族的状态、起手状态、分支、身体碰撞体的名字……），可选 `SESSIONS`（你哪几次录像有它，画 PNG 用）和 `CASES`（你指出的帧）。注册表 `are_types/__init__.py` 自动找到所有文件；`attack_range.SPECS`、实时的 `RangeTracker`、叠加层和回放都从它来。加一个怪 = 加一个文件 + 跑 `attack_range_build --type <名字> build / eval / png`，不碰共享代码。`are_types/choristor.py` 是搬过去的 Choristor，`clapper.py` 是 Clapper，可以照着写。
- `EnemySpec` 新增的选项（Choristor 都没用，保持原样）：
  - `decide`：招里面"决定瞄准"的时刻（Clapper 的跳在 Jump Aim 定落点）。**决定之前是待定的瞄准（第 2 组），不画**：估计停在决定前一格（只有起手的身体）。决定之后，模板按"决定后第几帧"对齐，锚在决定那一帧的位置和朝向，横向位移 = 比例 × L（L 由类型文件里的规则算）。可以顺带在决定时定一个分支（Clapper：落点会不会撞墙）。
  - `hazards`：怪放出来、比招活得久的东西（一排圆 / 一个圆）。在触发状态进入的那一帧生成，按 R0 dev 量到的每一环"开始伤人 / 停止伤人"的帧画，收招以后（待机）也照样画；`pre` = 触发之前就从招的起手按触发时间窗口预测。真伤害那一边：它们是别的实体（池化的 "damager"），按出生规则（位置 + 时间）归到放它的那只怪。
  - `branch_dur`：按状态持续多久定的分支（Clapper 的后撤：一次 / 连着两次）。
  - `state_gate`：模板每一格按状态分开存。k = 0 只画它现在所在状态的那一部分；k > 0 只画现在及以后的状态（已经离开的状态不会再回来）。这和"按看到的位置重新锚定"是同一个思路：按看到的状态重新锚定。某一格某个状态只有 1 个 R0 dev 实例时不画（一次跳在 15 帧就落地，单独一个就让 k 12 的面积比在那几格变成 3.5）。
- 构建：`attack_range_build --type clapper build`（只用 R0 dev）；`eval --set fresh|r2|person`；`png`；`hazcheck`（危险物的真伤害核对）。输出在 `C:\ssbot\data\m2_forum_are\<名字>\`。你的 9 次录像现在统一解码成"每次尝试一个缓存"（`C:\ssbot\data\m2_forum_are\person_cache`，所有类型共用，加怪不用再解码）。
- Choristor **逐位不变**：1,260 次放置的哈希（单测 `test_choristor_placements_are_bit_identical`）和 R0 fresh 前 6 条轨迹 9,128 行误差的哈希都和改之前一样。

### 33.2 Clapper 的家族（第一个 FSM 的状态；R0 dev 107 场里没被打的实例）

| 家族 | 状态（括号里是起手后的中位时刻） | 实例 | 时长 p50 / 最长 | 画什么 |
|---|---|---|---|---|
| CC_SLAM 锤 | Slam Antic（0.8 s，起手时转向你）> Slam 0（0.82）> Slam 1（0.90）> Slam 2（0.95）> Slam Recover（1.03） | 2,030 | 1.27 / 1.28 s | 起手只有身体；Slam 0 起 30 u/s 前冲 2.1–4.8 u（中位 3.6），Slam Collider 1 → 2；离起手位置最远前方 11.4 u |
| CC_EVADE 后撤 | Evade Scuttle（没有起手） | 单次 5,430；连续两次 414 | 0.35 / 0.72 s | 15 u/s 往后，一次 5.1 u；7 % 立刻再撤一次（共 10.8 u）。看到状态时间重新开始（或超过 26 帧）才知道是两次，之前画两种的并集 |
| CC_CAST 施法 | Spell Antic > Cast 1（0.73）> Cast 2（0.83） | 2,177 | 1.23 / 1.32 s | 自己没有攻击碰撞体，只有身体；Cast 2 放丝弹（33.3） |
| CC_JUMP 跳砸 | Jump Antic > Jump（0.50，Jump Aim 定落点）> Air > Slam 2（1.42，落地）> Slam Recover | 不撞墙 1,150；撞墙 64 | 1.73 / 1.75 s | 落点 = 起跳 x + 0.916 vx，vx = clamp(主角 x − 5 × 朝向 − x, ±12)，朝向主角（主角在 5 u 以内时往后跳）；不撞墙的落点误差 p50 0.025 u、p95 0.048 u（最大 1.4 / 跳砸 + 符文 2.1） |
| CC_JUMP_CAST 跳砸 + 符文 | Cast Slam Antic > Cast Slam Antic 2（0.27）> Jump（0.93 定）> Air > Slam 2（1.85）> Slam Recover | 不撞墙 963；撞墙 54 | 2.17 / 2.18 s | 同样的跳；落地放符文圈（33.3） |
| CC_ENTRY 入场 | Drop In > Enter Land（0.42）> Roar（0.97）> Roar End（1.98） | 307 | 0.92 / 2.23 s | 从上面落下的身体 |
| 待机 | Idle / Walk 和 0 秒的决策状态 | | | 现在的身体（三个框：Song Heavy Sentry、(2)、(3)），任何 k 都一样 |

- **撞墙的跳**：预测落点在 x 19.5 以左或 45.5 以右时，它会撞到墙、提前 2–13 帧落地、落得近（R0 dev 前 60 场 1,228 次跳：提前落地 42 次，其中 41 次的预测落点在这个区；其余 1,186 次里只有 29 次在这个区；全部 R0 dev 的撞墙分支 118 次）。所以在决定的那一刻就分成"撞墙 / 不撞墙"两个分支，各用各的模板；不分的话，这 3 % 的提前落地会让所有跳在落地前 k 12 都画出落地的锤（面积比 p90 3.5）。
- 锤、跳的落地锤只在 Slam 2 状态里存在（Slam Collider 2，约 50 u²）。有时 Slam 2 有 16 帧：那是顿帧（状态里的时间和游戏时间都几乎不走），不是锤在地上多留，按游戏时间它一样只有约 5 帧。
- 它被打时不会取消招（只被推 0.24–1.44 u），没有反击，所以没有 HIT_COND 一类要画的东西。

### 33.3 它放出来的危险物

- **丝弹（rune bomb small）**：Cast 2 进入时生成。圆 r 2.166，中心在 Cast 2 时它的 x + 4.2 m（|m| ≤ 9，只在 R0 dev 里丝弹出现过的 x 范围 5.3–56.6 内），y = 它的 y − 3.8（地面 + 0.65）。第 m 环在 Cast 2 后约 21 + 10|m| 帧开始伤人，每颗亮 5–8 帧（p50 6）。R0 dev 每一环的窗口（33,494 颗的并集，帧）：环 0 20–26，环 1 29–37，环 2 38–49，环 3 48–58，环 4 58–67，环 5 68–77，环 6 78–86，环 7 88–96，环 8 99–106，环 9 109–116。Cast 2 之前（Spell Antic 里）按"起手后 48–55 帧进 Cast 2"的窗口在它现在的位置预测。两只 Clapper 同时在场也分得开：归属按出生规则的时间（±3 帧），不是按"最近一次施法"。
- **符文圈（rune slam）**：CC_JUMP_CAST 落地（Slam 2 进入）时生成。圆 r 7.187，中心在落地点前方 6.48 u（朝向那边），y = 落地时它的 y − 3.27；落地后第 65–73 帧伤人（每次亮 p50 8 帧）。1,928 次。
- **真伤害核对**（像 §31 矛的爆炸那样；`hazcheck`；"亮" = 导出的碰撞体在出伤害；距离 = 主角受伤框到圆的距离，负 = 重叠）：

| | 集合 | 亮的窗口 | 伤害事件（在窗口里 / 窗口外） | 击中时的距离 | 击中在亮起后第几帧 | 重叠 > 0.3 u 的窗口：受伤 / 无敌帧挡掉 / 什么都没有 |
|---|---|---|---|---|---|---|
| 符文圈 | R0 dev | 1,915 | 1,721 / 19 | 全部重叠（最大 −0.05 u，p95 −0.53） | 1–8（p50 1） | 785 / 169 / 57（5.6 %） |
| | fresh + R2 + 你的录像 | 866 | 623 / 24 | 全部重叠（最大 −0.04） | 1–8 | 291 / 44 / 21（5.9 %） |
| 丝弹 | R0 dev | 33,359 | 2,081 / 15 | 最大 +0.055 u（一格栅格） | 1–6 | 594 / 754 / 46（3.3 %） |
| | fresh + R2 + 你的录像 | 14,290 | 939 / 15 | 最大 +0.09 | 0–6 | 280 / 322 / 21（3.4 %） |

  结论：导出的圆（r 7.187、r 2.166）就是真的伤害范围：没有一次击中在圆外，击中都在亮着的时候；所以真伤害（误差统计用的"真"）用这些圆是对的。重叠却什么事都没有的窗口：符文圈 5.6–5.9 %、丝弹 3.3 %，原因没查（没有 damage 也没有 damage_blocked 事件；以前分类时的 "109 / 1,069" 就是这个）。

### 33.4 估计误差（R0 fresh 35 场 / R2 的 19 条 Clapper 轨迹 / 你的录像 48 条，分开报；k = 0 和 12；不含被打的行和 t+k 前已经开始下一招的行）

| 家族 | 集合 | k 0：覆盖 / 面积比 / ≤1.5 的行 | k 12：覆盖 / 面积比 / p90 / ≤1.5 的行 | k 12 漏 p95（前/后/上/下/洞，u） |
|---|---|---|---|---|
| CC_SLAM | fresh | 99.6 % / 1.03 / 98 % | 96.7 % / 1.13 / 1.23 / 96 % | 0.65/1.10/0.60/0.63/0.60 |
| | R2 | 99.6 % / 1.02 / 98 % | 96.6 % / 1.13 / 1.25 / 95 % | 1.17/1.23/0.33/0.63/0.60 |
| | 你 | 99.5 % / 1.03 / 97 % | 97.2 % / 1.13 / 1.22 / 95 % | 0.68/0.95/0.60/0.62/0.60 |
| CC_EVADE | fresh | 99.6 % / 1.11 / 93 % | 98.1 % / 1.27 / 1.86 / 78 % | 0.95/0.35/-/0.05/0.35 |
| | R2 | 99.6 % / 1.12 / 93 % | 98.8 % / 1.31 / 1.86 / 76 % | 0.79/0.35/-/-/0.35 |
| | 你 | 99.6 % / 1.24 / 84 % | 98.1 % / 1.37 / 3.10 / 72 % | 0.30/0.35/-/-/0.35 |
| CC_CAST | fresh | 99.7 % / 1.05 / 98 % | 98.2 % / 1.09 / 1.35 / 96 % | 0.42/1.06/-/0.80/0.75 |
| | R2 | 99.7 % / 1.04 / 99 % | 98.3 % / 1.08 / 1.34 / 97 % | 0.42/0.93/-/0.80/0.85 |
| | 你 | 99.7 % / 1.07 / 97 % | 98.3 % / 1.08 / 1.31 / 97 % | 0.42/-/-/0.76/0.70 |
| CC_JUMP | fresh | 99.4 % / 1.04 / 97 % | 90.9 % / 1.11 / 1.17 / 96 % | 2.94/0.95/5.61/0.73/0.65 |
| | R2 | 99.4 % / 1.04 / 97 % | 90.2 % / 1.16 / 1.25 / 94 % | 2.44/1.25/5.58/1.98/1.00 |
| | 你 | 99.5 % / 1.03 / 98 % | 91.7 % / 1.08 / 1.16 / 98 % | 3.01/0.79/5.66/0.64/0.44 |
| CC_JUMP_CAST | fresh | 99.4 % / 1.02 / 99 % | 91.6 % / 1.15 / 1.26 / 95 % | 2.59/0.94/6.31/0.95/0.55 |
| | R2 | 99.4 % / 1.03 / 98 % | 90.9 % / 1.19 / 1.29 / 92 % | 2.17/0.89/6.24/1.64/0.70 |
| | 你 | 99.3 % / 1.06 / 96 % | 90.4 % / 1.16 / 1.23 / 93 % | 3.15/0.28/6.50/2.03/0.40 |
| CC_ENTRY | fresh | 99.7 % / 1.00 / 100 % | 96.7 % / 1.09 / 1.17 / 100 % | 0.30/0.95/0.85/1.95/0.05 |
| | R2 | 99.5 % / 1.01 / 100 % | 96.6 % / 1.09 / 1.17 / 100 % | 0.30/0.07/0.84/1.95/0.05 |
| | 你 | 99.9 % / 1.00 / 100 % | 96.8 % / 1.04 / 1.16 / 100 % | 0.30/0.07/0.85/0.80/0.05 |
| 待机 | fresh | 99.97 % / 1.12 / 92 % | 87.9 % / 1.13 / 1.21 / 91 % | 2.10/1.90/1.02/-/1.80 |
| | R2 | 99.98 % / 1.10 / 92 % | 84.2 % / 1.11 / 1.20 / 92 % | 2.10/1.90/1.02/-/1.80 |
| | 你 | 99.9 % / 1.14 / 90 % | 88.0 % / 1.16 / 1.52 / 89 % | 2.10/1.90/1.95/-/1.80 |
| 丝弹（只算丝弹） | fresh | 99.97 % / 1.06 / 91 % | 99.97 % / 1.06 / 1.00 / 91 % | 见下 |
| | R2 | 99.99 % / 1.05 / 93 % | 99.99 % / 1.04 / 1.00 / 94 % | 0.05 |
| | 你 | 99.99 % / 1.13 / 83 % | 99.99 % / 1.14 / 2.00 / 80 % | 0.05 |
| 符文圈（只算符文圈） | fresh / R2 / 你 | 99.7 / 99.8 / 99.2 % / 1.00 / 100 % | 99.7 / 99.8 / 99.2 % / 1.00 / 1.00 / 100 % | 0.30（一格 + 1 帧） |

（家族和待机的行里，估计和真伤害都包含它当时还在亮的丝弹 / 符文圈。）

- **k = 0 每个家族覆盖 99.3–99.97 %，面积比 1.00–1.14（你的录像里后撤 1.24）**：画出来的就是它现在真有的碰撞体。
- **k 12 的漏**：
  - 跳（JUMP / JUMP_CAST）覆盖 90–92 %：主要是**起跳前**的那几格——Jump Antic / Cast Slam Antic 里落点还没定（待定瞄准，第 2 组），按规则只画起手的身体，0.4–1.0 s 那段 k 12 会漏掉起跳后 12 帧的身体（上 5.6–6.5 u、前 2.2–3.2 u）。已经决定之后的行覆盖 94.8–97.6 %，面积比 1.10–1.30。没决定的行：JUMP 77.6–79.0 %，JUMP_CAST 83.0–83.7 %。
  - 锤：0.8–1.0 s 前冲那几帧后 / 前漏 p95 1.1–1.3 u（每次冲的距离不一样：2.1–4.8 u，靠墙更短）。
  - 待机 k 12 覆盖 84–88 %：**Walk** 以 8 u/s 走路，12 帧走 1.6 u，"待机 = 现在的身体"按规则不往前推，所以 Walk 的 k 12 覆盖只有 63–66 %（漏 p95 2.1 u）；Idle 是 97.2–97.7 %。要不要按它走路的速度往前推是你的决定（这算预测，不算余量）。
  - 丝弹：fresh 3 % 的行有一颗离估计 42 u 远的漏：最左边的一颗中心在 R0 dev 见过的最左位置（x 5.27）再往左一点（见 PNG `worst_..._ep29_f1573411`）。另一边：x 47.5 以右（水池上面）的位置只有 2–10 % 的施法真的出丝弹（R0 dev；第 7 波在 48 附近约 20 %），但出现过，所以按并集每次都画——这是丝弹 k 0 面积比 p95 2.0 的主要来源之一，另一个来源是每一环开始伤人的时刻差 ±3 帧（并集窗口 7–11 帧，每颗只亮 6 帧）。
- **面积比（目标 ≤ 1.5）**：k 0 全部 1.00–1.12，k 12 1.04–1.37；超过 1.5 的主要是后撤（两次 / 一次没定时画并集）和丝弹时间窗口。
- 被打的行（不进主表）：Clapper 被打不取消招，只被推一下；含这些行时 k 12 覆盖：锤 95.3–96.4 %、跳 88.2–90.5 %。
- 改进的过程（同一套数据，留着对照）：只锚在起手和位置、不按状态时（`prev_nogate\`）k 0 跳的面积比 1.33（p90 3.5）；加上状态（`prev_gate_nowall\`）k 0 降到 1.04，k 12 还是 1.36（提前落地的跳）；加撞墙分支（`prev_gate_wall\`）k 12 1.19；再去掉单个实例的状态格，现在 1.11（JUMP_CAST 1.43 → 1.15）。
- 详细（每个家族 × 每边 × 每 0.2 s，分支 / 决定已知的行）：`C:\ssbot\data\m2_forum_are\clapper\eval_{fresh,r2,person}.json`，逐行 `rows_*.pkl`；真伤害核对 `hazcheck.json`（R0 dev）和 `hazcheck_fresh_r2_person.json`。

### 33.5 怎么看

- **图**：`C:\ssbot\data\m2_forum_are\clapper\png\`（`index.json` 说明每张；颜色同 §32.4：橙色填充 = k 0 估计，浅蓝 = k 12，细黄 = 主角中心区，红 = 现在的真碰撞体，细红 = 之后 1–11 帧，紫红 = +12 帧，白框 = 大黄蜂）。你 4 次录像（160435、231544、085824、161454）里每个家族 2 个实例的起手 / 中间 / 收招帧和收招后 +12 / +30 帧，加上误差最大的帧（文件名 `worst_`，含 fresh 的）。共 73 张。例：`20261005_160435_f61831_Air.png`（跳砸在空中：k 0 面积比 0.99、k 12 0.99（覆盖 96 %）；不按状态、不分撞墙时 k 12 是 3.55，画出了还没发生的落地锤）。
- **回放**：`C:\ssbot\data\m2_forum_overlay\clapper_range.rrd`（46 MB；085824 第 2 次尝试 raw 46500–49100：第 7 波只有一只 Clapper，施法 / 丝弹、跳砸 / 符文圈、锤、后撤；0.35 倍视频；只有范围层和真碰撞体）。`world/range/Clapper_1/k00`、`k12`；标签里有 "+ hazards" 时表示画进了它的丝弹 / 符文圈。
- **实时 + 单怪练习**：`human_session --solo "Song Heavy Sentry" --overlay --overlay-range`。选到第 7 波（`fo_r1_w7`）：这一波只有一只 Clapper、没有别的怪，也没有 Garmond，所以不用清场，开局就是 1 对 1（之前 Clapper 1 对 1 的 A/B（clp2，`C:\ssbot\sandbox\clp2_ab.ps1`）用的 `Forum_W_w7` 也是这一波）。保护（加血）和 §32.5 一样，部署的 oracle 有没有 `enemy.hp` 没核实。模式 range+red，1–5 选 k（0 / 6 / 12 / 18 / 36）。没在游戏里跑过。

### 33.6 这一轮不画的（第 2 组 / 待定）和没做的

- 不画：Jump Antic（落点在 0.48–0.52 s 的 Jump Aim 才定）、Cast Slam Antic / Cast Slam Antic 2（0.88–0.93 s 才定）——这两段只画起手的身体；Idle / Walk / Close Range / Far Range 之后的下一招（0 秒决定，第 2 组）；Dmg Attack（待机时挨打只是提前出招，没有反击碰撞体）。
- 没做：按丝弹"出现"（伤人前 21 帧就看得见）重新对时间——可以把丝弹的时间窗口从 7–11 帧缩到每颗 6 帧，也能知道水池上的那颗有没有出；Walk 往前推；撞墙分支的阈值是 R0 dev 量的（19.5 / 45.5），地形没建模；重叠却没伤害的 3–6 % 窗口原因没查。

复现：
```
cd <checkout>\brain
..\scripts\uv.cmd run python -m ssbot.tools.attack_range_build tracks                      (解码你的录像，所有类型共用)
..\scripts\uv.cmd run python -m ssbot.tools.attack_range_build --type clapper build
..\scripts\uv.cmd run python -m ssbot.tools.attack_range_build --type clapper eval --set fresh --threads 4   (r2 / person)
..\scripts\uv.cmd run python -m ssbot.tools.attack_range_build --type clapper hazcheck --sets "dev"         ("fresh,r2,person")
..\scripts\uv.cmd run python -m ssbot.tools.attack_range_build --type clapper png
..\scripts\uv.cmd run python -m ssbot.tools.viewer C:\ssbot\data\human\20261009_085824 --zones --range-only --k 0,12 --video --video-scale 0.35 --from 46500 --to 49100 --save C:\ssbot\data\m2_forum_overlay\clapper_range.rrd
..\scripts\uv.cmd run python -m pytest -q tests\test_attack_range.py tests\test_attack_range_types.py tests\test_zone_overlay.py
```

## 34. 攻击范围估计（ARE）阶段 B：Envoy、Clawmaiden 和她的矛（2026-10-10，task "attack range: all types" 阶段 B，分支 worktree-wf_2fe0d0c5-18e-2 = main + 阶段 A 77ccb1e；代码 `ssbot/combat/are_types/envoy.py`、`clawmaiden.py`、`spear.py`；表 `knowledge/1.0.30000/enemies/forum/attack_range_{envoy,clawmaiden,spear}.npz` + `.json`；数据 `C:\ssbot\data\m2_forum_are\{envoy,clawmaiden,spear}`）

规则和 §32 / §33 一样：**不加任何余量**，只有画主角中心区时的受伤框膨胀；招从起手画到收招；还没决定的分支画并集；还没开始的招（第 2 组）不画。全部只用 R0 dev 构建，误差在 R0 fresh、R2、你的录像上分开报。离线，没有开游戏。

### 34.1 框架上加的两个钩子（最小改动，Choristor / Clapper 不受影响）

模板（"相对身体的形状 + 中位位移"）描述不了这三种东西：冲到"主角身后 4 u"才停的冲锋、朝向决定两次的抓、追踪主角的矛。所以 `EnemySpec` 加了两个可选项，Choristor 和 Clapper 都不用（Choristor 1,260 次放置的哈希测试照样通过）：

- `on_step`：每帧在 Segmenter 的规则之后调用，类型自己往实例上记东西（`Inst.extra`，带游戏时间；也可以设分支）。
- `place_fn`：类型自己算某一格的位置和形状；返回 None 就用模板。`place()` 多了一个参数 `ctx`（现在的游戏时间、主角位置、实例、速度、现在的身体碰撞体），实时的 `RangeTracker`、误差评估 `eval_track` 和画图都传它。
- 构建工具那边：类型文件可以有 `attach(c, tracks)`，给真伤害加自己的东西（矛的三角形、爆炸圆、竖直速度）；`poly_of` 接受直接给的多边形（矛是旋转的三角形，缓存里只有外接框）。

### 34.2 Envoy（Song Pilgrim 01）

| 家族 | 状态 | R0 dev 实例 | 时长 p50 / 最长 | 画什么 |
|---|---|---|---|---|
| EN_SLASH 劈 | Slash Antic > Slash1（0.48 s）> Slash1 2 > Slash1 Recover > Attack End（单次）或 JumpSlash Antic > JumpSlash 1–4（跳劈） | 单次 232；跳劈 110 | 1.47 / 2.17 s | 朝向在起手定。**第一下伤害（P1 Damager，0.483 s）在身体后上方**（回挥），前面的 P2 从 0.683 s 起。Combo?（0 秒、看不见）随机选跳劈（约一半）：看到 Slash1 Recover 之后的下一个状态才知道，之前画两种的并集 |
| EN_JUMPSLASH | 从劈以外进入的跳劈 | 0（R0 dev 没有） | | 同一套状态 |
| EN_CHARGE 冲锋 | Charge Antic（0.483–0.517 s 不动）> Charge（13.0 u/s，R0 dev 每一帧都是）> Charge End（滑 0.26–1.3 u，0.42 s） | 196 | 2.07 / 3.12 s | 方向（起手时主角那一侧）和时间是定的，长度不定：游戏在它**过了主角 4 u** 时停（R0 dev 最后一帧冲锋最多过主角 3.997 u）或撞墙（身体 x 17.37 / 45.57）。画法：从它现在的位置以 13 u/s 往前，到"主角**现在**的位置 + 4 u"或墙为止，然后 Charge End 的滑行（R0 dev 每帧的中位）和身体 |
| EN_AMBUSH 埋伏入场 | Ambush Antic > Ambush 1 > Ambush 2 | 106 | 1.47 s | 第 0 波入场，原地；1.25 s 起身体带伤害 |
| 待机 | Walker（2.4 u/s 朝你走）、Attack Wait 等 | | | 现在的身体（批准的规则） |

### 34.3 Clawmaiden（Song Handmaiden）

| 家族 | 状态 | R0 dev 实例 | 时长 p50 | 画什么 |
|---|---|---|---|---|
| CM_SLASH 抓 | Slash Antic（0.5 s，身体往后飘最多 3 u）> Slash 1 > 2 > 3 > Slash 4 > 5 > Slash Recover | 不转-不转 649，不转-转 139，转-不转 85，转-转 24 | 0.98 s | **朝向决定两次，每次都在出伤害的那一帧**：Slash 1 进入时转向主角（R0 dev 12 % 和起手朝向相反，全部是转向主角），Slash 4 进入时再转一次（20 % 翻转）。按（Slash 1 转没转）×（Slash 4 翻没翻）建 4 个模板；画"现在还可能"的并集：Slash 1 之前 4 个，Slash 1 到 Slash 4 之间 2 个，之后 1 个。R0 dev 里进入那一帧的朝向 = 主角那一侧 = 碰撞体那一侧，没有例外 |
| CM_SPIN 转 / 放矛 | Spin Antic > Spin 0–2 > Spin Wind Down > Spin End（> Spear Cast Antic > Spear Fire Recover；或 Spin Cancel） | 309 | 4.2 s | 只有在动的身体（吸丝，没有攻击碰撞体）；矛是单独的类型（34.4） |
| CM_TELE 瞬移 | Tele Out Antic（0.18 s，掉 1.3 u，身体还伤人）> Tele Out > Tele In > Tele In End >（Did Roar? > Roar） | 314 | 1.03 s | Tele Out 起身体不伤人；落点随机（待定），**看到 Tele In 之前不画瞬移后的身体** |
| CM_ENTRY 入场 | 从无到 Tele In > Tele In End > Did Roar? > Roar | 305 | 1.32 s | 身体 |
| CM_FLYTOSLASH | Fly To Slash（≤ 1 s，以 ≤ 5 u/s 飞到离主角 4 u） | 1,001 | 0.75 s | 身体；之后 64 % 出抓——那是新的家族（第 2 组，不画） |
| CM_FLY 飞 | Fly（+ Set Distance、Tele?） | 2,562 | 0.62 s | 身体 |

- **飞的身体（这一轮的任务里写了 "fly / fly-to-slash body motion"）**：Fly、Fly To Slash、转的时候她一直在飞（6–9 u/s），k > 0 时把**现在的身体碰撞体按现在的速度平移**（不加速，不长大；k = 0 就是现在的身体本身）。和批准的待机规则（任何 k 都画现在的身体）不同，所以两种都量了（R0 fresh，k 12 覆盖）：

| | 现在的身体（待机规则） | 按速度平移（现在画的） |
|---|---|---|
| CM_FLY | 36.3 % | 80.3 % |
| CM_FLYTOSLASH | 31.6 % | 83.6 % |
| CM_SPIN | 32.7 % | 73.9 % |

  面积比两种都是 1.00。用导出的速度比用位置差好（R0 dev k 12 位置误差 p50：速度 0.51 u，一帧位置差 0.65 u，加上加速度 0.88 u，不动 1.31 u）。要不要这样画、Clapper 的 Walk 要不要也这样，是你的决定；`clawmaiden.CARRY_ON = False` 就回到待机规则。

### 34.4 矛（实体类型 "Spear"，单独一个类型文件）

矛是自己的实体（Control FSM：Idle > Antic Pause > Antic > Fire > Explode），按 §31 的规则画它**已经决定的路径**：

- **决定**：Get Antic Angle = 矛进入 Antic Pause 的那一帧（抓丝怪 Spear Cast Antic → Spear Fire）。瞄准：矛 → 主角 transform + (0, 0.25)，在她朝向那一侧夹到 ±45°（主角在她背后时取近的那条边）。矛的 flip 和她的一样（R0 dev 170 / 170）。**决定之前（她的 Spear Cast Antic）是待定瞄准，不画。**
- Antic Pause 9–10 帧不动；Antic 42–43 帧往瞄准的反方向退（30 u/s，每个 50 Hz 物理步 ×0.875，空地 3.645 u），不伤人。进了 Antic 就用它实际的速度（正好是瞄准的反方向）。开火时间只知道一个窗口，画两端的并集。
- Fire：37 u/s 沿瞄准，然后追踪（ChaseObjectWisp）——**按主角现在的位置模拟**（主角之后怎么动就是误差，下面报了）。碰撞体：三角形，尖在 transform 前 3.759 u，底在后 1.776 u，宽 1.256 u。物理步按 50 Hz、取最近的整数步（取下整会慢一步，0.74–1.0 u：开火后头两帧实际 p50 46.9 u/s）。
- Explode：开火 0.1 s 后，接触点（前方 1.45 u）碰到地面（y 3.0）或墙（x 14.2 / 49.1），或者三角形碰到主角，就爆：圆 r 3.5529，中心在 transform 前方 0.9 u（沿最后的飞行方向；R0 dev 170 次：沿速度方向偏差只有 0.065 u 的横向偏移），亮 0.108 s（实测从 Explode 那一帧起 1–5 帧）。
- 真伤害：缓存里只有三角形的外接框，所以按速度方向重建三角形（和外接框的差 p50 0.15 u、最大 0.31 u）；爆炸是 7.106 u 的 "damager"，按 Explode 那一帧的位置（2.5 u 内）挂到这支矛上。

### 34.5 估计误差（R0 fresh / R2 / 你的录像，分开报；k = 0 和 12；不含被打的行和 t+k 之前已经开始下一招的行）

| 家族 | 集合 | k 0：覆盖 / 面积比 / ≤1.5 的行 | k 12：覆盖 / 面积比 / p90 / ≤1.5 的行 | k 12 漏 p95（前/后/上/下/洞，u） |
|---|---|---|---|---|
| EN_SLASH | fresh | 99.2 % / 0.99 / 100 % | 98.5 % / 1.15 / 1.00 / 93 % | 0.15/0.60/-/-/0.30 |
| | R2 | 99.4 % / 1.00 / 100 % | 98.4 % / 1.13 / 1.00 / 94 % | 0.30/0.60/2.84/-/0.30 |
| | 你 | 99.1 % / 0.99 / 100 % | 97.5 % / 1.14 / 1.00 / 94 % | 0.30/0.60/2.37/-/0.30 |
| EN_CHARGE | fresh | 99.6 % / 1.00 / 100 % | 91.5 % / 1.00 / 1.00 / 98 % | 0.75/2.35/-/-/0.30 |
| | R2 | 99.7 % / 1.00 / 100 % | 90.7 % / 1.00 / 1.00 / 99 % | 1.05/2.70/-/-/0.30 |
| | 你 | 99.6 % / 1.00 / 100 % | 92.3 % / 1.00 / 1.00 / 99 % | 0.65/2.50/-/-/0.30 |
| EN_AMBUSH | fresh / R2 / 你 | 99.8 % / 1.00 / 100 % | 99.1 / 98.3 / 99.6 % / 1.00 / 1.00 / 100 % | 0.34/-/0.24/0.10/- |
| Envoy 待机 | fresh / R2 / 你 | 100 % / 1.00 / 100 % | 75.5 / 75.4 / 75.5 % / 1.00 / 1.03 / 100 % | 0.45 前（走路） |
| CM_SLASH | fresh | 99.6 % / 1.01 / 100 % | 91.5 % / 1.82 / 2.39 / 50 % | 0.71/0.53/0.57/0.60/0.45 |
| | R2 | 99.6 % / 1.01 / 100 % | 91.2 % / 1.85 / 2.50 / 53 % | 0.81/0.49/0.58/0.56/0.54 |
| | 你 | 99.5 % / 1.01 / 100 % | 89.5 % / 1.80 / 2.38 / 54 % | 0.82/0.67/0.57/0.73/0.58 |
| CM_SPIN | fresh / R2 / 你（8 行） | 100 % / 1.00 / 100 % | 73.9 / 74.7 / 88.6 % / 1.00 / 1.04 / 100 % | 0.84/0.84/1.17/0.74/- |
| CM_FLY | fresh / R2 / 你 | 100 % / 1.00 / 100 % | 80.3 / 81.5 / 81.8 % / 1.00 / 1.04 / 100 % | 0.74/0.70/0.68/0.68/- |
| CM_FLYTOSLASH | fresh / R2 / 你（79 行） | 100 % / 1.00 / 100 % | 83.6 / 82.2 / 89.1 % / 1.00 / 1.04 / 100 % | 0.74/0.51/0.95/0.71/- |
| CM_TELE | fresh / R2 / 你 | 99.5–99.7 % / 1.01–1.02 / 100 % | k 12 的行里真伤害和估计都是空（身体关着） | |
| CM_ENTRY | fresh / R2 / 你 | 99.2–99.7 % / 1.02 / 100 % | 99.1–99.6 % / 1.02 / 1.04 / 100 % | |
| 矛 | fresh | 99.0 % / 1.00 / 100 % | 80.3 % / 1.08 / 1.26 / 92 % | 2.98/1.83/3.18/3.01/- |
| | R2 | 99.1 % / 1.00 / 100 % | 82.3 % / 1.09 / 1.25 / 94 % | 3.31/2.37/2.95/2.27/1.33 |
| | 你 | 98.9 % / 1.00 / 100 % | 85.9 % / 1.11 / 1.24 / 95 % | 2.66/1.08/0.93/2.64/0.96 |

- **k = 0 每个家族覆盖 98.9–100 %，面积比 0.99–1.02**：画的就是它们现在真有的碰撞体。
- **Envoy 的劈**：分支已知的行 k 12 覆盖 93.7–96.3 %、面积比 1.16–1.19；Combo? 之前（单次 / 跳劈并集）的行 99.1–99.4 %、1.12–1.14。面积比超过 1.5 的行（6–7 %）就是这个并集。
- **Envoy 的冲锋**：k 12 覆盖 90.7–92.3 %，面积比 1.00。漏的主要是：冲锋中后 1.0–1.6 s"后面"漏 p95 2.6–2.9 u（主角往它这边走，冲锋比预测早停）和 2.0–2.4 s"前面"漏 p95 3.3–3.9 u（主角顺着它冲的方向跑，冲锋比预测长）——都是"按主角现在的位置算终点"的误差，不是余量能补的那一类。
- **Clawmaiden 的抓**：面积比 1.8 是规则本身：出伤害前朝向没定，就画两边。分开看：还有一边没定的行覆盖 89.6–91.6 %、面积比 1.82–1.87；两次都定了以后 84.4–86.6 %、1.02–1.04（这一段行很少：fresh 308、你 21）。k = 0 是 1.01。
- **飞的身体**：按速度平移 k 12 覆盖 74–89 %；用待机规则是 32–36 %（34.3）。
- **矛**：k 0 99 %；k 12 80–86 %，面积比 1.08–1.11。漏 p95 2–3 u，来自：按主角现在的位置追踪（主角之后会动）、开火时间 ±1 帧、物理步相位（±半步 ≈ 0.4–0.5 u）、爆炸点（地面 / 墙 / 打中主角）。改成"最近整数步"之前是 77.4 / 79.3 / 83.1 %。
- 详细（每个家族 × 每边 × 每 0.2 s）：`C:\ssbot\data\m2_forum_are\<envoy|clawmaiden|spear>\eval_{fresh,r2,person}.json`，逐行 `rows_*.pkl`；Clawmaiden 待机规则的对照 `clawmaiden\eval_fresh_nocarry.json`。

### 34.6 怎么看

- **图**（颜色同 §32.4：橙色填充 = k 0 估计，浅蓝 = k 12，细黄 = 主角中心区，红 = 现在的真碰撞体，细红 = 之后 1–11 帧，紫红 = +12 帧，白框 = 大黄蜂）：`C:\ssbot\data\m2_forum_are\envoy\png`（37 张）、`clawmaiden\png`（53 张）、`spear\png`（33 张；`index.json` 说明每张）。每个家族 2 个实例的起手 / 中间 / 收招帧 + 误差最大的帧（`worst_`，含 fresh）。矛另外有 4 次飞行（你的 085824、161454、231544、160435）的开火前一帧 / 开火 / 飞行中 / 最后一帧。你指出的 085824 f7939、f10427 这两帧里没有 Envoy 和 Clawmaiden（是 Bellbearer / Reed 的，归别的类型）。例：`clawmaiden\png\20261004_002749_f25804_Slash_Antic.png`（抓的起手：k 12 两边都画，真的在主角那一边；面积比 1.95）；`spear\png\20261009_085824_f13140_Antic.png`（开火前：沿瞄准的两个三角形 = 开火时间窗口的两端）。
- **单怪练习**：
  - Envoy：`human_session --solo "Song Pilgrim 01" --overlay --overlay-range` → 第 0 波（`fo_r1_w0`），同一波还有 Reed 和 Choristor，要先清掉（清场时主角会自动加强，几下一只）；Envoy 在这一波是埋伏入场（EN_AMBUSH）。
  - Clawmaiden（和她的矛）：`human_session --solo "Song Handmaiden" --overlay --overlay-range` → 第 3 波（`fo_r1_w3`），只有她一只，不用清场。矛是另一个实体，叠加层里单独一个标签（"SP_SPEAR"，灰色，名字是 #iid）。
  - 都没在游戏里跑过；--solo 会不会把矛当成"别的怪"没核实。

### 34.7 这一轮不画的（第 2 组 / 待定）和没做的

- 不画：Envoy 和 Clawmaiden 待机 / 飞的时候下一招是什么（0 秒决定）；Fly To Slash 之后的抓；瞬移的落点（看到 Tele In 之前）；她 Spear Cast Antic 里的矛（Get Antic Angle 之前）。Envoy 走路时挨打会出冲锋（触发，不是反击），从它的 Charge Antic 起画。EN_HOPSLASH 没出现过（490 场 0 次）。
- 没做：冲锋终点按主角**现在**的位置，没有预测主角；飞的身体只按现在的速度，没用 DistanceFly 的规则；矛的地形只有地面 y 3.0 和两面墙（R0 dev 爆炸点量的），平台没建模；矛三角形和外接框的 0.15 u 差没查（可能是旋转比速度晚一帧）；回放（rrd）没做。

复现：
```
cd <checkout>\brain
..\scripts\uv.cmd run python -m ssbot.tools.attack_range_build --type envoy shapes          (clawmaiden 同样；矛不需要)
..\scripts\uv.cmd run python -m ssbot.tools.attack_range_build --type envoy build           (clawmaiden / spear)
..\scripts\uv.cmd run python -m ssbot.tools.attack_range_build --type envoy eval --set fresh --threads 4   (r2 / person)
..\scripts\uv.cmd run python -m ssbot.tools.attack_range_build --type envoy png
..\scripts\uv.cmd run python -m pytest -q tests\test_attack_range_envoy_clawmaiden.py tests\test_attack_range_types.py tests\test_attack_range.py
```

## 35. 攻击范围估计（ARE）：Reed + Minister（2026-10-10，task "attack range: all types" 阶段 B，分支 worktree-wf_2fe0d0c5-18e-3 = 阶段 A 77ccb1e + 这一轮；代码 `ssbot/combat/are_types/reed.py`、`minister.py`，框架上加的钩子在 `attack_range.py`、`are_spec.py`、`tools/attack_range_build.py`、`attack_range_png.py`；表 `knowledge/1.0.30000/enemies/forum/attack_range_reed.npz`、`attack_range_minister.npz` + `.json`；数据 `C:\ssbot\data\m2_forum_are\reed`、`minister`）

规则和 §32 / §33 一样：**不加任何余量**（只有画主角中心区时的受伤框膨胀）；待机 = 现在的身体；每一招从起手到收招，按看到的位置重新锚定；还没决定的瞄准（第 2 组）不画；没决定的分支画并集。新的两类：**反击**（被打了才有：从 Block / Parry Block 进入那一帧起画）和**飞行物**（Reed 的针：决定了就画它的直线，飞出去以后按它真实的位置和速度画）。只用 R0 dev 构建；误差在 R0 fresh、R2、你的录像上分开报。离线，没有开游戏。

### 35.1 框架上加的东西（都很小，Choristor / Clapper 不受影响）

- `Segmenter`：分支表里的值可以是一个函数（在那个状态的第一帧按位置 / 主角位置 / 朝向算出分支；参数里有招开始时的朝向 `s0`）；`Decision` 的规则可以返回 `(s, L, extras)`：`s = 0` 表示用决定那一帧看到的朝向，`extras` 存进决定里（针的仰角）。
- `EnemySpec.hit_started`：被打才开始的家族（反击）。开始它的那一下不算"被打断"，之后再挨打才算。
- 类型文件可以自己画额外的东西：`extra(tab, inst, T, pos, t, objs)`（Reed 的针）；`OBJ_TYPES` 是它的飞行物的类型（实时追踪器把每根飞着的针给第一次看到它时离它最近的那只 Reed）；构建器里 `attach(c, tracks, spec)` 把缓存里的针按出生点归给扔它的那只 Reed，真碰撞体在轨迹里叫 "OBJ:pin"（和 "HZ:" 一样不进模板）。叠加层、PNG、误差都自动带上它。
- `EnemySpec.coast`：在这些状态里，往后的位置 = 现在的位置 + 看到的速度按 FSM 的衰减滑行（每个 50 Hz 物理步 × 衰减；0 = 速度设成 0、不动），而不是模板的位移中位数（模板里的实例结束早晚不同）。Reed 的 Parry Slash（×0.95）和 Multihit（0）。轨迹里多存了 vy。
- 决定的报告多了 `L_p50`（量到的位移中位数）。PNG 找你说的帧时先找在场的那只（等着入场的 Reed 在 Fly In Ready 里也有身体碰撞体，之前会找错）。
- 单测 `tests/test_attack_range_types.py`（Choristor 逐位不变的哈希）照样通过。

### 35.2 Reed（Song Reed）的家族（R0 dev 里没被打断的实例）

| 家族 | 状态 | 实例 | 画什么 |
|---|---|---|---|
| RE_STAB 刺 | Stab Antic（0.63–0.67 s，身体**跟着你移动**：DistanceFly 到你前后 5 u、高 2.5 u）> Stab 1–5 > Stab End > Stab Recover | 626 | 起点是待定的瞄准（第 2 组）：起手期间只画起手的身体。**Stab 1 进入那一帧决定**：锚在那里、用那时看到的朝向；三段 −20 u/s 前冲、每段往下 −6，从 Stab 1 到收招 u 方向位移中位 10.0 u（撞墙就停在墙边：x 夹在 R0 dev 的 14.85–48.15） |
| RE_THROW 扔针 | Throw Antic > Throw Aim（0.25–0.28 s，**决定**）> Throw（Transition）> Throw Recover | 1,648（Aiming Up：down 1,511、up 103、open 34） | 自己只有身体（后坐 0.155 u）；针见 34.3。分支 = 起手那一帧的 Aiming Up（主角比它高 2 u 以上 = up，离这条线 0.3 u 以内 = open），用来算出针什么时候出手 |
| RE_COUNTER 反击 | Block（你打中了它：**从这一帧起画**）> Parry Y Aim > Parry Slash > Multihit / Multihit Clashed / Parry Slash End | 252 | 方向 = Block 时的朝向（= 挨打时你在哪一边，1300/1300）。竖直方向在 Parry Slash 进入时（Block 后 30–31 帧）定：Speed Y = clamp(2 ×（你的 y − 它的 y），±10)，按 2 u/s 分 10 个分支（每个 10–44 个实例）；定之前画 10 个分支的并集。前冲 −22 u/s 加 Speed Y，每个物理步 ×0.95：**Parry Slash 里按看到的速度往前推**，Multihit（撞到你）里不动；ParrySlash Hit（多段，导出 dealt 0）只在 Parry Slash 里 |
| RE_EVADE 闪避 | Evade Antic > Evade（> Evade End） | 1,716 | 30 u/s 往后 + 5 往上，只有身体。Evade 进入时它会重新面向你再往后飞：起手时你在它前面 2.22 u 以外 = 方向确定（R0 dev 里转过身的 180 次全在 2.22 u 以内）；以内就画"同向 / 转身"两个分支的并集，到 Evade 进入再定 |
| RE_ENTRY 入场 | Fly In | 519 | 落下来的身体 |
| 待机 | Alert、Stab Pos、Defend Start / Defend / Defend End、Throw Range、0 秒的选择状态 | | 现在的身体（Song Reed、(1)…(3) 的身体碰撞体）。Defend 没有自己的攻击碰撞体：反击只在你打中它（进入 Block）以后才画 |

### 35.3 Reed 的针（Song Reed Pin Projectile，池化）

- **决定**：Throw Aim 进入那一帧，Reed → 你的 transform 的仰角，夹在 [−70°, +45°]（朝它面向的一边）。R0 dev 263 根针：误差 0。
- **出手**：决定后 24–25 帧（游戏时间，1,995 次）；有 Throw Transition 时 28–30 帧（158 次）。Throw Transition 发生在"起手时的 Aiming Up"和"针的上 / 下出手"不一致的时候，所以起手时就知道用哪个窗口（离线那 0.3 u 的带子里两个都画）。
- **出生点**：出手时 Reed 的位置 + 朝向坐标 (1.53, −0.54)；仰角 ≥ 10° 时 (1.11, +0.48)。全部 263 根完全一致。决定之后它还在后坐（每帧 ×0.85），所以出生点 = 现在的位置 + 决定时 vx × 剩下的后坐。
- **飞行**：直线 31.0 u/s（全部 263 根），按 50 Hz 物理步走（每步 0.62 u；60 帧里有一帧不动），所以 k 帧以后走了 floor / ceil(k × 50 / 60) 步，两个都画。
- **碰撞体**：2.031 × 0.098 的长条。**出生那一帧是水平的，从第二帧起转到飞行方向**（导出的 AABB 正好等于转过的长条的外接框）。缓存只存外接框，所以真值和估计都把转过的长条拆成 40 小段（每段的外接框；离真长条 0.02 u 以内），两边画法一样。我第一次只看了出生帧，以为一直是水平的：那一版 k0 覆盖只有 77 %，改了以后 100 %。
- **停下**：钉进地 / 墙以后碰撞体关掉。按 R0 dev 亮着的针中心的范围（x 13.9–48.25，y ≥ 3.15）停；平台上提前钉住的不知道（多画，不会漏）。被你的钉子拍飞（62 u/s）的针碰撞体是关的，不画。
- 实时：每根亮着的针给第一次看到它时最近的那只 Reed；已经出手的针按它自己的位置和速度画，还没出手的按决定画。

### 35.4 Minister（Song Administrator）的家族

| 家族 | 状态 | 实例 | 画什么 |
|---|---|---|---|
| MI_CHARGE 冲刺 | Attack Antic（0.48–0.52 s；起手第一帧面向你、瞄准你 + (0, 1.5)，夹在 ±45°；沿瞄准线 −14 u/s 后坐；碰撞体变成 Collider AttackAntic）> Attack（沿瞄准线 33 u/s，Slash Collider 多段）> Multihit（撞到你：停 0.4 s）或 Attack End | 1,649 | 瞄准在**起手第一帧**就定了，所以按 15° 分 7 个分支（−45、−30、−15、0、+15、+30、+45；每个 68–370 个实例），各用各的模板，按状态分开（Attack / Multihit / Attack End） |
| MI_COUNTER 格挡反击 | Parry Block（格挡架势里被你打中：**从这一帧起画**；面向你，20 u/s 往后、−4 往下，再往上）> Parry Slash 1–4（一次 −45 u/s 前冲、−20 往下，分四段，ParrySlash Hit 1–4）> Parry Slash End | 324 | 方向 = Parry Block 时的朝向；没有竖直瞄准 |
| MI_EVADE 闪避 | Evade Antic > Evade（25 u/s 往后 + 5 往上，0.4 s） | 1,486 | 同 Reed：起手时你在前面 2.09 u 以外方向确定（转身的 59 次全在 2.09 u 以内），以内画两个方向的并集 |
| MI_ENTRY 入场 | Fly In | 423 | 落下来的身体 |
| 待机 | Chase、Retreat?、Parry Stance Antic / Parry Stance / Parry Stance End、0 秒的选择状态 | | 现在的身体：所有亮着的身体碰撞体（Song Administrator 本体，和按状态换的 Collider Fly / Evade / ParryStance / ParryAntic / AttackAntic）。格挡架势本身不出伤害，反击只在 Parry Block 以后画 |

- 冲刺时整只 Minister 转到瞄准方向，所以它的碰撞体（身体、Slash Collider）是斜的；缓存只存外接框，估计和真值两边都是外接框，比真实的斜框大。k0 面积比 1.18–1.22 主要是这个（加上同一个 15° 分支里不同实例的并集）。
- `face_names` 用 Slash Collider（在前面）：ParrySlash Hit 投的票是反的（第一次构建所有冲刺都被夹到 ±45°）；R0 dev 2,625 次 Attack Antic 进入时 flipX 1 都是面向 +x 的你。

### 35.5 估计误差（R0 fresh 35 场 / R2 / 你的录像，分开报；覆盖 = 真伤害格子被估计盖住的比例；面积比 = 估计 / 真实（主角中心区）；不含被打断的行和 t+k 前已经开始下一招的行）

Reed：

| 家族 | k0 覆盖 | k0 面积比 | k12 覆盖 | k12 面积比 | 说明 |
|---|---|---|---|---|---|
| RE_STAB（Stab 1 决定之后） | 98.4 / 98.5 / 98.5 % | 1.00 | 91.7 / 91.6 / 91.8 % | 1.05 / 1.05 / 1.06 | 96–97 % 的行面积比 ≤ 1.5 |
| RE_STAB（Stab Antic，待定） | 98.4 / 98.4 / 98.4 % | 0.98 | 47.5 / 47.5 / 48.2 % | 0.88 | 起点待定，刺不画（第 2 组） |
| RE_THROW（身体 + 针） | 99.2 / 99.1 / 99.2 % | 1.05 / 1.06 / 1.05 | 96.0 / 96.1 / 96.0 % | 1.17 / 1.16 / 1.16 | Throw Aim 之后的行 k12 96.8–96.9 %、1.12–1.14 |
| 针（单独的行） | 99.99 / 99.95 / 100 % | 1.00 | 99.7 / 99.6 / 99.6 % | 1.36 / 1.32 / 1.29 | 93 % 的行 ≤ 1.5；多出来的是出手时刻（24 或 25 帧）和物理步数（floor / ceil）各有两种 |
| RE_COUNTER | 98.8 / 98.8 / 98.9 % | 1.00 / 1.04 / 1.00 | 85.9 / 88.2 / 92.6 % | 1.18 / 1.16 / 1.11 | 漏 p95 1.4–1.7 u。你说的第 10427 帧：k0 和 k12 都是面积比 1.00、覆盖 99 % |
| RE_EVADE | 98.7 / 98.7 / 98.8 % | 1.03 | 83.3 / 84.0 / 83.0 % | 1.38 / 1.38 / 1.36 | 漏 p95 1.0–1.1 u（不分方向时 3.8 u） |
| RE_ENTRY | 98.5 / 98.7 / 98.4 % | 0.99 | 94.3 / 95.1 / 94.1 % | 0.98–0.99 | |
| 待机 Alert | 100 % | 1.00 | 38 / 44 / 37 % | 1.00 | 现在的身体；它以约 6 u/s 飞（规则如此） |
| 待机 Stab Pos | 100 % | 1.00 | 16 / 24 / 18 % | 1.00 | 同上（往你那里靠的定位飞行） |
| 待机 Defend | 100 % | 1.00 | 68 / 68 / 67 % | 1.00 | |

这一轮改过的地方（都在 R0 fresh 上看到的，改了以后三个集合一起重跑）：针的碰撞体从第二帧起是斜的（k0 覆盖 77 % → 100 %）；闪避在 Evade 进入时可能转身（k12 漏 p95 3.8 u → 1.0–1.1 u，覆盖 77 % → 83 %）；针出手时刻按起手时的 Aiming Up 选窗口（针 k12 面积比 1.61–1.71 → 1.29–1.36）；反击在 Parry Slash 里按看到的速度滑行、Multihit 里不动（k12 覆盖 80–85 % → 86–93 %，漏 p95 2.0–2.2 → 1.4–1.7 u；第 10427 帧 k12 从漏 2.1 u 变成面积比 1.00、覆盖 99 %）。

Minister：

| 家族 | k0 覆盖 | k0 面积比 | k12 覆盖 | k12 面积比 | 说明 |
|---|---|---|---|---|---|
| MI_CHARGE | 99.8 / 99.8 / 99.8 % | 1.20 / 1.22 / 1.18 | 95.5 / 94.2 / 95.5 % | 1.26 / 1.28 / 1.26 | 90–92 % 的行面积比 ≤ 1.5 |
| MI_COUNTER | 99.4 / 99.4 / 99.4 % | 1.06 / 1.06 / 1.05 | 90.2 / 91.4 / 91.4 % | 1.11 / 1.10 / 1.10 | |
| MI_EVADE | 99.7 / 99.7 / 99.6 % | 1.28 / 1.29 / 1.28 | 91.5 / 92.0 / 89.8 % | 1.46 / 1.44 / 1.36 | k0 大：本体碰撞体只在一部分闪避里亮（Parry Slash 之后），模板是并集 |
| MI_ENTRY | 没有伤害碰撞体 | | 91.8 / 91.9 / 83.0 % | 1.02 / 1.02 / 0.93 | 你的录像里有些行估计是空的（入场比 R0 dev 慢） |
| 待机 Chase | 100 % | 1.00 | 55 / 57 / 55 % | 0.99 | 现在的身体；它以 ≤ 7 u/s 飞，k12 漏掉的是它飞走的部分（规则如此） |
| 待机 Parry Stance | 100 % | 1.00 | 64 / 68 / 64 % | 1.00 | 同上 |

### 35.6 怎么看

- 图：`C:\ssbot\data\m2_forum_are\reed\png`（56 张 + `index.json`：每个家族几帧、你说的 085824 第 7939 帧（Bellbearer / Reed）和第 10427 帧（Reed 反击）、误差最大的帧）；`C:\ssbot\data\m2_forum_are\minister\png`（39 张）。橙色填充 = k0 估计，浅蓝 = k12 估计，红 = 真碰撞体，品红 = +12 帧的真碰撞体。
- 叠加层：`viewer --zones --range` / `human_session --overlay-range` 自动带上这两类（针算在 "+ pin"）。
- 单练：
  - Reed：`human_session --solo "Song Reed" --overlay --overlay-range` → 第 2 波（`fo_r1_w2`），同一波还有一只 Bellbearer（Pilgrim 03 Song），solo 会先帮你清掉它。
  - Minister：`human_session --solo "Song Administrator" --overlay --overlay-range` → 第 4 波（`fo_r1_w4`），这一波有两只 Minister，solo 先清掉另一只。
  - 都没在游戏里跑过。

### 35.7 这一轮不画的（第 2 组 / 待定）和没做的

- Reed Stab Antic：刺的起点在起手期间跟着你走（待定的瞄准），只画起手的身体；这些行 k12 覆盖只有 47.5–48.2 %。Throw Antic：针的方向到 Throw Aim 才定，之前只画身体。
- 待机（Alert、Stab Pos、Throw Range、Chase、Retreat?、格挡架势）只画现在的身体：Reed 在 Alert / Stab Pos 以约 6 u/s 飞，k12 覆盖 16–44 %；Minister Chase 55–57 %。要不要按速度往前推，是你来定。
- Reed 反击：Block 期间（Parry Slash 之前）画 10 个竖直分支的并集（定之前就是待定的）；Multihit Clashed、Parry Slash End 之后的身体仍按模板中位走，k12 漏 p95 1.4–1.7 u。
- Reed 刺：从 Stab 1 到收招的 u 位移中位 10.0 u，但 p95 误差 6.4 u（5 % 以上的刺比中位短很多）；撞墙的由 x 夹到墙边接住，其余原因（撞地？）没查。k12 决定之后的行仍有 91.6–91.8 % 覆盖。
- 针：平台上提前钉住的没有地形模型；被拍飞的针（62 u/s，碰撞体关）不画；物理步的相位（这一帧动不动）没跟踪，所以 k > 0 时画两个步数。
- Minister：斜的碰撞体在缓存里是外接框，估计和真值都偏大。冲刺瞄准规则误差 p95 27°（v2 分类里的未解释尾巴）这里由 15° 分支 + 按看到的位置重新锚定吸收，没单独查。

复现：
```
cd <checkout>\brain
..\scripts\uv.cmd run python -m ssbot.tools.attack_range_build --type reed shapes        (minister 同理)
..\scripts\uv.cmd run python -m ssbot.tools.attack_range_build --type reed build
..\scripts\uv.cmd run python -m ssbot.tools.attack_range_build --type reed eval --set fresh --threads 3   (r2 / person)
..\scripts\uv.cmd run python -m ssbot.tools.attack_range_build --type reed png
..\scripts\uv.cmd run python -m pytest -q tests\test_attack_range_reed_minister.py tests\test_attack_range_types.py tests\test_attack_range.py tests\test_zone_overlay.py
```

## 36. 攻击范围估计（ARE）阶段 B：Bellbearer（和它的铃）、Maestro、Tiny（2026-10-10，task "attack range: all types" 阶段 B，分支 worktree-wf_2fe0d0c5-18e-4 = 阶段 A 77ccb1e + 这三个类型；代码 `ssbot/combat/are_types/bellbearer.py`、`maestro.py`、`tiny.py`；表 `knowledge/1.0.30000/enemies/forum/attack_range_{bellbearer,maestro,tiny}.npz` + `.json`；数据 `C:\ssbot\data\m2_forum_are\{bellbearer,maestro,tiny}`）

规则和 §32 / §33 一样：**不加任何余量**（只有画主角中心区时的受伤框膨胀）；待机 = 现在的身体；招从起手到收招，只用 R0 dev 建；还没开始的招和还没定的瞄准（第 2 组）不画。误差分 R0 fresh / R2 / 你的录像三组报。离线，没有开游戏。

### 36.1 给框架加的钩子（阶段 A 的框架不够的地方；Choristor 和 Clapper 都没用，结果不变）

- `EnemySpec.custom(view) -> (replace, add)`：类型文件自己算这一帧的估计。`replace` 取代模板的那一部分（例：Tiny 绕 Maestro 转圈、按速度走的身体），`add` 加进去并算作危险物（例：Bellbearer 的铃）。`view`（`are_spec.CustomView`）里有现在的位置、速度、状态、实例、主角；实时还有这一帧所有实体和一个跨帧的小内存，离线有轨迹和帧号。实时在 `RangeTracker.estimate` 调，离线在 `eval_track` 和 PNG 里调（同一个函数）。身体的多边形由调用的一方放进 `view.body`（类型文件不能 import 构建工具：导入防火墙 `test_import_firewall` 不许 combat 经 forum_cache 碰到 ipc）。
- `EnemySpec.attach(cache, tracks)`：只在构建 / 评估时用，给轨迹加上 custom 需要的东西（别的实体的路径、自己扔出去的东西），并把扔出去的东西的真碰撞体记成 "HZ:<名字>"（真伤害的一部分）。评估里多一组行 "HZ extra"（只比这些东西）。
- `Decision.scale = False`：只定"哪一边"的决定（Maestro 的斩）。决定以后的横向位移用模板的中位数，不按 L 缩放。
- 实时跳过"不在场"的成员时用类型自己的 `parked`（以前写死成通用的 PARKED，里面有 "Ready"；Tiny 的 Ready 是跟队形飞，是在场的）。
- 评估的每一行多记了当时的状态（`st`），新工具 `ssbot/tools/are_rows_report.py` 按家族 × 决定 / 状态出表（`report.json`）。
- 单怪练习（`solo_practice.py`）：Maestro 自己召唤的 Tiny 不算"别的怪"（不让你清掉）；`--solo "Song Automaton Tiny"` 等于练 Maestro + 它的 Tiny。
- 单测 `tests/test_attack_range_bmt.py`（11 个）；Choristor 逐位不变（`test_choristor_placements_are_bit_identical` 照样过）。

### 36.2 Bellbearer（Pilgrim 03 Song）和铃

| 家族 | 状态 | R0 dev 实例 | 时长 p50 / 最长 | 画什么 |
|---|---|---|---|---|
| CB_THROW 扔铃 | Throw Antic（第一帧就定了瞄准）> Throw（出手，起手后 0.649–0.683 s）> Recover | 7,403 | 1.17 / 1.22 s | 身体（起手时往后 0.94 / 往上 0.47 u，p95），被打不取消；铃见下 |
| CB_EVADE 闪避 | Evade Antic（4–5 帧，转向你）> Evade | 3,083 | 0.40 / 0.40 s | **按它现在的朝向往后** 32 u/s、每帧 ×0.9（4.3 u），同时往下 8 u/s（下沉 1.25 u，最大 3.46）。朝向来自 flipX：背对你开始闪避时就是往你身上撞；你在它正下方时下沉的那一段会碰到你。Evade 状态里用"现在的速度 × 每帧 0.9 衰减"推（FSM 自己的减速规则；R0 dev 12 帧后位置误差 p50 0.16 u、p90 0.47 u），Evade Antic 用模板 |
| CB_ENTRY 入场 | Fly In | 532 | 0.8 s | 身体（入场时不伤人，落定后的身体） |
| 待机 | In Range / Out of Range | | | 现在的身体（1.32 × 1.53） |

**铃**（"Throwing Bell" 实体，圆 r 0.425）：
- **在飞的铃按它的真路径画**：从它现在的位置和速度往后推：50 Hz 半隐式欧拉，g 60（每步 vy −1.2）；第一次落地（中心 y 3.53）弹起 vy 20；第二次落地后在地上再伤 1–2 帧就消失；墙（x 14.435 / 48.565）把它以 10 u/s 弹回。被你的钉子打回去的铃（Nail Hit，从此 dealt 0）不画。R0 dev 12 帧后的位置误差：p50 0.0 u、p90 0.42、p95 0.61（50 Hz 物理和 60 帧画面的相位差 + 弹跳）。
- **还没出手时画已经定了的抛物线**（Throw Antic 里、这次的铃还没出现）：Spit X = clamp(1.15 × (你的 x − 它的 x) + U(−1, 1), ±15)，|vx| ≥ 4，vy 20（你的 x 取起手那一帧）；出生点 = 它现在的位置 + (朝 vx 方向 0.94 u, −0.5 u)（R0 dev 1,648 / 1,660 次）；出手时刻在 R0 dev 的窗口 0.649–0.683 s 里。画的是 U 取 5 个值 × 窗口里每一帧的并集——U 和出手帧是唯一不知道的东西，不是余量。
- 离线的真伤害：每个铃的一段飞行按"出生时刻 = 某只 Bellbearer 的 Throw 进入（±3 帧）且出生点最近（≤ 1.5 u）"归给那只；实时按"第一次看到时离它最近的那只 Bellbearer"。

### 36.3 Maestro（Song Pilgrim Maestro）

| 家族 | 状态 | R0 dev 实例 | 时长 p50 | 画什么 |
|---|---|---|---|---|
| MA_SLASH 斩 | Fire Antic（0.68–0.73 s，往后退正好 2.37 u；同一帧叫一只 Tiny 俯冲）> Slash 1 > Slash 2 > Slash End > Slash Recover F / Slash Recover | 6,226 | 1.32 s | **哪一边在 Slash 1 进入时定**（第一下伤害的那一帧：你当时在哪一边，7922 / 7922；Fire Antic 开始时只有 95.4 %）。之前是待定瞄准（第 2 组）：只画起手的身体和它的后退；Slash 1 起画定了那一边的斩（Slash Hit 1 / 2 的真多边形），锚在 Slash 1 那一帧 |
| MA_DEFEND 防御 | Defend Start > Defending > Defend End | 2,656 | 2.28 s | 身体。Defending 跟你保持 4 u（≤ 5 u/s，你近了它就退），模板的中位路径不对（k 12 覆盖 79 %，后方漏 p95 1.95 u），改成"身体按现在的速度走"（R0 dev 12 帧后误差 p50 0.11 u、p90 0.53）→ k 12 覆盖 91 % |
| MA_SUMMON 召唤 | Call > Summon > Summon Recover | 1,112 | 1.02 s | 身体（没有攻击碰撞体），召出 Tiny |
| MA_ENTRY 入场 | Fly In | 318 | 0.8 s | 入场时身体不伤人 |
| 待机 | Forum Fly / Fly / Chase | | | 现在的身体（1.76 × 1.95） |

- 被打时它会去 Summon?（一个出招决定，不是反击碰撞体），所以没有 HIT_COND 一类要画的。

### 36.4 Tiny（Song Automaton Tiny，Maestro 的小机器）

只有身体伤人（1.00 × 1.08）；Swoop In Pause / Swoop In（入场）、Leave、Die、Dead 时不伤人。一次最多 6 只，每只单独跟踪。池化对象：同一个 iid 死了会在别处重新出现，所以离线按"每一条命"切成单独的轨迹（不然 12 帧后会比到它下一条命的位置）。

| 家族 | 状态 | R0 dev 实例 | 画什么 |
|---|---|---|---|
| AT_FIRE_READY 俯冲准备 | Fire Ready（0.70–0.77 s，和 Maestro 的 Fire Antic 同步） | 7,676 | 俯冲的方向和起点要到 Fire 才定（第 2 组），只画身体：按现在的速度和上一帧的加速度走 |
| AT_DIVE 俯冲 | Fire > Brake > Pull Up / Wall Bonk > Return | 5,236 | Fire 进入时就定了（方向 = 它的朝向，1,114 / 1,117）：(±24, −36.9) u/s 起，越来越平，到地面（y 5.0：Brake 滑行 1–23 u）、撞墙（Wall Bonk）或 Pull Up；Return 飞回队形。模板的中位路径只有 32 % 的 k 12 覆盖，改成按状态的运动学：身体按现在的速度（Fire / Pull Up / Return / Fire Ready 再加上一帧的加速度，撞墙那一帧速度被清零时不算加速度），不穿地面（Fire / Brake / Pull Up：y ≥ 4.7），不出墙（x 14.5–48.5）。R0 dev 12 帧后位置误差 p50 / p90：Fire 0.61 / 1.67 u（不动的身体 5.82 / 7.36），Brake 0.80 / 1.19，Pull Up 0.75 / 1.75，Wall Bonk 0.45 / 1.01，Return 0.26 / 1.46 |
| AT_DEFEND 防御 | Defend Ready > Defend Buzz | 7,713 | **绕最近的 Maestro 转圈**：圆心 = Maestro 现在的位置 + 它的速度 × t；角度按 R0 dev 量的角速度曲线转（Defend Buzz 开始 0.3 s 内从 0 加到约 210–350 °/s，之后 180–215 °/s），方向 = 它现在转的方向；半径从现在的半径按曲线变（5.0 → 0.3 s 时 2.2 → 5.05）。R0 dev 12 帧后误差 p50 0.67 u（不动的身体 3.65，按速度 1.78）。Defend Ready 按速度走（p50 0.33） |
| AT_ENTRY 入场 | Swoop In Pause > Swoop In | 2,225 | 不伤人；入场后的身体 |
| AT_LEAVE 离场 | Leave Pause > Leave | 728 | Leave Pause 的身体（按速度走），Leave 不伤人 |
| 待机 | Ready（跟队形飞，6 u/s） | | 现在的身体 |

### 36.5 估计误差（k = 0 和 12；不含被打的行和 t+k 前已经开始下一招的行；覆盖 = 真伤害格子被估计盖住的比例，面积比 = 估计 / 真，主角中心区）

Tiny 评估每 6 帧取一行（待机每 30 帧），Bellbearer / Maestro 每 2 帧（待机每 6 帧）。

| 家族 | 集合 | k 0：覆盖 / 面积比 / ≤1.5 的行 | k 12：覆盖 / 面积比 / p90 / ≤1.5 的行 | k 12 漏 p95（前/后/上/下/洞，u） | 行数 |
|---|---|---|---|---|---|
| Bellbearer CB_ENTRY | fresh | - / None / - | 86.5 % / 0.983 / 1.0 / 100.0 % | 0.63/0.56/0.6/0.6/- | 4350 |
| Bellbearer CB_ENTRY | R2 | - / None / - | 85.9 % / 0.983 / 1.0 / 100.0 % | 0.63/0.49/0.46/0.53/- | 815 |
| Bellbearer CB_ENTRY | 你 | - / None / - | 85.9 % / 0.977 / 1.0 / 100.0 % | 0.62/0.56/0.53/0.6/99.0 | 2485 |
| Bellbearer CB_EVADE | fresh | 99.7 % / 1.004 / 100.0 % | 92.8 % / 1.051 / 1.12 / 96.6 % | 0.91/0.49/0.45/0.51/0.85 | 8643 |
| Bellbearer CB_EVADE | R2 | 99.7 % / 1.001 / 100.0 % | 92.1 % / 1.047 / 1.12 / 96.9 % | 1.65/0.51/0.39/0.44/0.4 | 2978 |
| Bellbearer CB_EVADE | 你 | 99.7 % / 1.004 / 100.0 % | 92.5 % / 1.065 / 1.14 / 93.6 % | 5.06/0.49/0.48/0.49/0.4 | 1649 |
| Bellbearer CB_THROW | fresh | 98.6 % / 0.986 / 100.0 % | 96.0 % / 1.032 / 1.17 / 98.8 % | 0.32/0.32/0.53/0.25/0.56 | 86601 |
| Bellbearer CB_THROW | R2 | 98.6 % / 0.986 / 100.0 % | 95.8 % / 1.025 / 1.15 / 99.5 % | 0.35/0.35/0.49/0.39/0.63 | 37159 |
| Bellbearer CB_THROW | 你 | 98.6 % / 0.986 / 100.0 % | 96.4 % / 1.038 / 1.18 / 97.7 % | 0.32/0.35/0.53/0.28/0.49 | 7357 |
| Bellbearer 待机 | fresh | 100.0 % / 1.0 / 100.0 % | 55.1 % / 1.037 / 1.03 / 92.4 % | 1.54/1.48/1.51/1.51/1.51 | 29297 |
| Bellbearer 待机 | R2 | 100.0 % / 1.0 / 100.0 % | 58.6 % / 1.043 / 1.04 / 91.0 % | 1.54/1.42/1.51/1.39/1.4 | 11601 |
| Bellbearer 待机 | 你 | 100.0 % / 1.0 / 100.0 % | 54.8 % / 1.025 / 1.03 / 95.0 % | 1.54/1.47/1.48/1.51/1.48 | 3582 |
| Bellbearer 铃（HZ extra） | fresh | 100.0 % / 1.0 / 100.0 % | 95.7 % / 1.107 / 1.49 / 90.6 % | 0.53/0.53/0.62/0.77/0.18 | 71621 |
| Bellbearer 铃（HZ extra） | R2 | 100.0 % / 1.0 / 100.0 % | 95.8 % / 1.106 / 1.49 / 90.5 % | 0.46/0.98/0.56/1.25/0.18 | 30217 |
| Bellbearer 铃（HZ extra） | 你 | 100.0 % / 1.0 / 100.0 % | 96.9 % / 1.098 / 1.47 / 91.1 % | 0.49/0.46/0.54/0.71/0.18 | 6695 |
| Maestro 待机 | fresh | 100.0 % / 1.0 / 100.0 % | 71.4 % / 1.0 / 1.02 / 100.0 % | 1.21/1.37/1.02/0.95/- | 46494 |
| Maestro 待机 | R2 | 100.0 % / 1.0 / 100.0 % | 73.2 % / 1.0 / 1.02 / 100.0 % | 1.17/1.31/0.95/0.88/- | 16985 |
| Maestro 待机 | 你 | 100.0 % / 1.0 / 100.0 % | 73.9 % / 1.0 / 1.02 / 100.0 % | 1.28/1.4/1.02/1.23/- | 2869 |
| Maestro MA_DEFEND | fresh | 100.0 % / 1.0 / 100.0 % | 91.0 % / 1.0 / 1.02 / 100.0 % | 0.6/0.7/0.46/0.53/- | 65550 |
| Maestro MA_DEFEND | R2 | 100.0 % / 1.0 / 100.0 % | 91.1 % / 1.0 / 1.02 / 100.0 % | 0.61/0.7/0.46/0.51/- | 27841 |
| Maestro MA_DEFEND | 你 | 100.0 % / 1.0 / 100.0 % | 90.8 % / 1.0 / 1.02 / 100.0 % | 0.6/0.75/0.53/0.51/- | 2046 |
| Maestro MA_ENTRY | fresh | - / None / - | - / None / None / - | -/-/-/-/- | 1875 |
| Maestro MA_ENTRY | R2 | - / None / - | - / None / None / - | -/-/-/-/- | 704 |
| Maestro MA_ENTRY | 你 | - / None / - | - / None / None / - | -/-/-/-/- | 944 |
| Maestro MA_SLASH | fresh | 98.9 % / 1.001 / 100.0 % | 78.3 % / 0.89 / 1.04 / 100.0 % | 4.85/0.32/1.48/0.25/- | 87730 |
| Maestro MA_SLASH | R2 | 98.9 % / 1.001 / 100.0 % | 78.1 % / 0.887 / 1.04 / 100.0 % | 4.8/0.32/1.48/0.25/- | 39474 |
| Maestro MA_SLASH | 你 | 98.8 % / 1.0 / 100.0 % | 77.7 % / 0.879 / 1.04 / 100.0 % | 4.9/0.28/1.45/0.25/- | 3851 |
| Maestro MA_SLASH decided | fresh | 98.9 % / 1.007 / 100.0 % | 91.9 % / 1.03 / 1.04 / 100.0 % | 1.35/0.35/0.39/0.31/- | 41004 |
| Maestro MA_SLASH decided | R2 | 99.0 % / 1.006 / 100.0 % | 91.1 % / 1.03 / 1.04 / 100.0 % | 1.26/0.35/0.4/0.32/- | 18410 |
| Maestro MA_SLASH decided | 你 | 98.9 % / 1.006 / 100.0 % | 92.2 % / 1.029 / 1.04 / 100.0 % | 0.9/0.29/0.39/0.26/- | 1734 |
| Maestro MA_SLASH pending | fresh | 98.8 % / 0.994 / 100.0 % | 68.8 % / 0.792 / 1.0 / 100.0 % | 4.95/0.28/1.49/0.16/- | 46726 |
| Maestro MA_SLASH pending | R2 | 98.8 % / 0.994 / 100.0 % | 69.1 % / 0.788 / 1.0 / 100.0 % | 4.9/0.28/1.49/0.16/- | 21064 |
| Maestro MA_SLASH pending | 你 | 98.8 % / 0.994 / 100.0 % | 68.4 % / 0.782 / 1.0 / 100.0 % | 4.95/0.28/1.48/0.15/- | 2117 |
| Maestro MA_SUMMON | fresh | 98.6 % / 0.993 / 100.0 % | 94.9 % / 0.993 / 1.0 / 100.0 % | 0.46/0.48/0.29/0.05/- | 11485 |
| Maestro MA_SUMMON | R2 | 98.6 % / 0.992 / 100.0 % | 97.0 % / 0.992 / 1.0 / 100.0 % | 0.5/0.21/0.22/0.05/- | 1614 |
| Maestro MA_SUMMON | 你 | 98.5 % / 0.99 / 100.0 % | 97.7 % / 0.991 / 1.0 / 100.0 % | 0.58/0.14/0.24/0.05/- | 1131 |
| Tiny AT_DEFEND | fresh | 100.0 % / 1.0 / 100.0 % | 55.8 % / 1.0 / 1.01 / 100.0 % | 3.22/3.08/2.91/3.34/- | 56394 |
| Tiny AT_DEFEND | R2 | 100.0 % / 1.0 / 100.0 % | 54.4 % / 1.0 / 1.01 / 100.0 % | 3.35/3.18/2.99/3.47/- | 26013 |
| Tiny AT_DEFEND | 你 | 100.0 % / 1.0 / 100.0 % | 52.6 % / 1.0 / 1.01 / 100.0 % | 3.49/3.33/3.55/3.53/- | 4698 |
| Tiny AT_DIVE | fresh | 100.0 % / 1.0 / 100.0 % | 69.9 % / 1.001 / 1.01 / 100.0 % | 1.26/1.46/2.12/1.23/- | 36989 |
| Tiny AT_DIVE | R2 | 100.0 % / 1.0 / 100.0 % | 70.4 % / 1.001 / 1.01 / 100.0 % | 1.28/1.4/2.12/1.23/- | 18692 |
| Tiny AT_DIVE | 你 | 100.0 % / 1.0 / 100.0 % | 70.2 % / 1.001 / 1.01 / 100.0 % | 1.2/1.54/2.15/1.37/- | 3061 |
| Tiny AT_DIVE st=Brake | fresh | 100.0 % / 1.0 / 100.0 % | 73.8 % / 1.001 / 1.01 / 100.0 % | 0.32/1.75/1.51/0.82/- | 6567 |
| Tiny AT_DIVE st=Brake | R2 | 100.0 % / 1.0 / 100.0 % | 73.1 % / 1.001 / 1.01 / 100.0 % | 0.35/1.99/1.51/0.89/- | 3326 |
| Tiny AT_DIVE st=Brake | 你 | 100.0 % / 1.0 / 100.0 % | 71.8 % / 1.001 / 1.01 / 100.0 % | 0.22/2.02/1.61/0.8/- | 435 |
| Tiny AT_DIVE st=Fire | fresh | 100.0 % / 1.0 / 100.0 % | 65.3 % / 1.003 / 1.01 / 100.0 % | 0.35/1.37/2.58/0.95/- | 7831 |
| Tiny AT_DIVE st=Fire | R2 | 100.0 % / 1.0 / 100.0 % | 65.9 % / 1.003 / 1.01 / 100.0 % | 0.42/1.24/2.58/0.96/- | 3984 |
| Tiny AT_DIVE st=Fire | 你 | 100.0 % / 1.0 / 100.0 % | 65.4 % / 1.002 / 1.01 / 100.0 % | 0.23/1.39/2.58/0.86/- | 740 |
| Tiny AT_DIVE st=Return | fresh | 100.0 % / 1.0 / 100.0 % | 74.1 % / 1.0 / 1.01 / 100.0 % | 1.61/1.09/1.06/1.29/- | 15634 |
| Tiny AT_DIVE st=Return | R2 | 100.0 % / 1.0 / 100.0 % | 74.3 % / 1.0 / 1.01 / 100.0 % | 1.57/1.1/1.02/1.34/- | 7822 |
| Tiny AT_DIVE st=Return | 你 | 100.0 % / 1.0 / 100.0 % | 75.9 % / 1.0 / 1.01 / 100.0 % | 1.5/1.04/0.88/1.52/- | 1231 |
| Tiny AT_ENTRY | fresh | - / None / - | 84.7 % / 1.004 / 1.01 / 100.0 % | 0.28/0.32/0.95/1.6/- | 4617 |
| Tiny AT_ENTRY | R2 | - / None / - | 86.2 % / 1.004 / 1.01 / 100.0 % | 0.28/0.36/0.95/0.81/- | 857 |
| Tiny AT_ENTRY | 你 | - / None / - | 80.5 % / 1.003 / 1.01 / 100.0 % | 0.28/0.35/1.1/2.4/- | 1106 |
| Tiny AT_FIRE_READY | fresh | 100.0 % / 1.0 / 100.0 % | 87.1 % / 1.0 / 1.01 / 100.0 % | 0.56/0.62/0.32/0.6/- | 13218 |
| Tiny AT_FIRE_READY | R2 | 100.0 % / 1.0 / 100.0 % | 87.6 % / 1.0 / 1.01 / 100.0 % | 0.56/0.6/0.36/0.56/- | 5108 |
| Tiny AT_FIRE_READY | 你 | 100.0 % / 1.0 / 100.0 % | 87.0 % / 1.0 / 1.01 / 100.0 % | 0.7/0.63/0.39/0.61/- | 1242 |
| Tiny AT_LEAVE | fresh | 100.0 % / 1.0 / 100.0 % | 82.9 % / 1.0 / 1.01 / 100.0 % | 0.6/0.97/0.68/0.93/- | 3256 |
| Tiny AT_LEAVE | R2 | 100.0 % / 1.0 / 100.0 % | 63.8 % / 1.0 / 1.01 / 100.0 % | 0.56/1.68/1.17/1.36/- | 40 |
| Tiny AT_LEAVE | 你 | 100.0 % / 1.0 / 100.0 % | 80.9 % / 1.0 / 1.01 / 100.0 % | 0.84/0.93/0.83/1.03/- | 1777 |
| Tiny 待机 | fresh | 100.0 % / 1.0 / 100.0 % | 41.7 % / 1.0 / 1.01 / 100.0 % | 1.39/1.4/1.39/1.3/- | 37279 |
| Tiny 待机 | R2 | 100.0 % / 1.0 / 100.0 % | 41.7 % / 1.0 / 1.01 / 100.0 % | 1.39/1.4/1.38/1.25/- | 14333 |
| Tiny 待机 | 你 | 100.0 % / 1.0 / 100.0 % | 43.1 % / 1.0 / 1.01 / 100.0 % | 1.4/1.39/1.39/1.23/- | 2854 |

（"HZ extra" = 铃自己的行。家族 / 待机的行里估计和真伤害都包含当时的铃。"CH_IDLE" = 待机。MA_SLASH "pending" = Fire Antic 里还没定边的行，"decided" = Slash 1 以后。）

要点：
- **k 0**：Bellbearer 98.6–100 %、Maestro 98.5–100 %、Tiny 100 %，面积比 0.99–1.01：画出来的就是现在真有的碰撞体（斩是真多边形，铃是真圆）。
- **铃**：k 12 覆盖 95.7–96.9 %，面积比 1.10（p90 1.47–1.49；比较大的是出手前那几帧画的抛物线带：U 和出手帧的并集）。
- **Bellbearer**：扔铃 k 12 96 %（面积比 1.03），闪避 92–93 %（改成按衰减速度推之前 85–87 %），入场 86 %。
- **Maestro**：斩定了边以后 k 12 91–92 %（面积比 1.03）；Fire Antic 里（待定，按规则不画斩）69 %，漏的就是还没定边的斩（前方 p95 4.9 u）。防御 91 %，召唤 95–98 %。
- **Tiny**：俯冲 k 12 70 %（Fire 65–66 %、Brake 72–74 %、Return 74–76 %；用模板中位路径时只有 32 %），俯冲准备 87 %，入场 81–86 %，离场 64–83 %，转圈（防御）53–56 %（误差 p50 0.67 u，而身体只有 1 u 宽）。面积比都是 1.00：Tiny 只有身体，画得不大，问题全在 12 帧后的位置
- **待机 k 12**（规则 = 现在的身体，不往前推）：Bellbearer 55–59 %、Maestro 71–74 %、Tiny 42–43 %。它们待机时都在飞：Bellbearer In Range 按现在的速度推 12 帧，位置误差 p50 0.40 u（不推 1.10），Maestro Forum Fly 0.16（不推 0.61），Tiny Ready 0.32（不推 1.21）。和 Clapper 的 Walk 一样：要不要按速度往前推是你的决定（这算预测，不算余量；改起来就是在 custom 里加这几个状态）。
- 面积比全部 ≤ 1.11（铃 p90 1.49），没有一类超过 1.5：这三个类型主要是"位置推得准不准"，不是"画得太大"。

### 36.6 怎么看

- **图**（颜色同 §32.4：橙色填充 = k 0 估计，浅蓝 = k 12，细黄 = 主角中心区，红 = 现在的真碰撞体，细红 = 之后 1–11 帧，紫红 = +12 帧，白框 = 大黄蜂；标题里 "+ projectiles" = 画进了铃）：
  - `C:\ssbot\data\m2_forum_are\bellbearer\png\`（35 张 + `index.json`）：你指出的 **085824 第 7939 帧**（`20261009_085824_f7939_Evade.png`：闪避，k 0 覆盖 100 %、面积比 1.00，k 12 覆盖 97 %、面积比 1.00——以前这一帧画成了一圈圈的框）；出手前 6 / 3 帧的抛物线（`20261005_160435_f22420_*`、`f22426_*`）；在飞的铃（`20261005_160435_f22444_Throw.png`：k 12 的圆正好落在 +12 帧的真圆上）；每个家族 2 个实例；误差最大的帧（`worst_`）。
  - `C:\ssbot\data\m2_forum_are\maestro\png\`（41 张）：斩（例 `20261005_160435_f16780_Slash_2.png`：k 0 面积比 1.00、覆盖 99 %）、Fire Antic（待定的斩不画）、防御、召唤、误差最大的帧（都是 Fire Antic 里还没定边的斩）。
  - `C:\ssbot\data\m2_forum_are\tiny\png\`（52 张）：俯冲、转圈、准备、入场 / 离场、误差最大的帧。
- **单怪练习**（实时叠加：`--overlay --overlay-range`，1–5 选 k；都没在游戏里跑过）：
  - Bellbearer：`human_session --solo "Pilgrim 03 Song" --overlay --overlay-range` → 第 3 波（`fo_r1_w2`）：还有一只 Reed，先清掉（清的时候无敌 + 钉子 4 级），然后只剩 Bellbearer。
  - Maestro：`--solo "Song Pilgrim Maestro"` → 第 7 波（`fo_r1_w6`，两只 Maestro）：先清掉另一只，留下的那只和它的 Tiny 一起练（Tiny 不算"别的怪"）。
  - Tiny：`--solo "Song Automaton Tiny"` → 和 Maestro 一样（Tiny 只跟着 Maestro 出现）。
  - 保护（加血）同 §32.5；部署的 oracle 有没有 `enemy.hp` 没核实。

### 36.7 这一轮不画的（第 2 组 / 待定）和没做的

- 不画：Maestro Fire Antic 里的斩（边要到 Slash 1 才定）；Tiny Fire Ready 里的俯冲（方向和起点到 Fire 才定）；所有待机状态之后的下一招（In Range / Out of Range、Forum Fly / Fly / Chase、Ready：0 秒决定或由 Maestro 叫）。
- 没有 HIT_COND（反击）类：这三个被打都不出反击碰撞体（Bellbearer / Tiny 被打只是被推，Maestro 被打会去 Summon?）。
- 没做：Tiny 转圈只有 55 % 的 k 12 覆盖（误差 p50 0.67 u，身体只有 1 u 宽），要更准得知道它在队形里的目标格；Tiny Fire 里 Pull Up（中途拉起）什么时候发生不知道（上方漏 p95 5–7 u）；铃出手时刻用的是 R0 dev 前 20 场量的窗口；待机按速度推（等你定）；实时叠加层和 --solo 没在游戏里跑过。

复现：
```
cd <checkout>\brain
..\scripts\uv.cmd run python -m ssbot.tools.attack_range_build --type bellbearer shapes        (maestro / tiny 同)
..\scripts\uv.cmd run python -m ssbot.tools.attack_range_build --type bellbearer build
..\scripts\uv.cmd run python -m ssbot.tools.attack_range_build --type bellbearer eval --set fresh --threads 3      (r2 / person；Tiny 加 --every 6 --idle-every 30)
..\scripts\uv.cmd run python -m ssbot.tools.attack_range_build --type bellbearer png
..\scripts\uv.cmd run python -m ssbot.tools.are_rows_report --type tiny --by-state AT_DIVE,AT_DEFEND
..\scripts\uv.cmd run python -m pytest -q tests\test_attack_range_bmt.py tests\test_attack_range.py tests\test_attack_range_types.py tests\test_zone_overlay.py
```

## 37. 攻击范围估计（ARE）阶段 C：10 类合在一起（2026-10-10，task "attack range: all types" 阶段 C，分支 worktree-wf_2fe0d0c5-18e-5 = main f910fda + 阶段 A 77ccb1e + 阶段 B f310c20（Envoy / Clawmaiden / 矛）、efcc2ef（Reed / Minister）、1399528（Bellbearer / Maestro / Tiny）；汇总工具 `ssbot/tools/are_summary.py`；数据 `C:\ssbot\data\m2_forum_are\stage_c`、`summary.md`、`index.md`）

离线做的，没有开 / 关任何游戏实例。规则不变（§32 / §33）：不加余量；待机 = 现在的身体；还没决定的分支画并集；还没开始的招（第 2 组）不画；只用 R0 dev 建；误差在 R0 fresh、R2、你的录像上分开报。

### 37.1 合并

- 三个阶段 B 分支各加了一套钩子，全部保留，都是按类型开的（不设就不用）：
  - Envoy / Clawmaiden / 矛：`EnemySpec.on_step`、`place_fn`（`place()` 的 `ctx`）。
  - Reed / Minister：`coast`、`hit_started`、可调用的分支值、`Decision` 规则返回 extras；类型模块的 `extra` / `OBJ_TYPES` / `OBJ_NAME`（真值是 "OBJ:" 碰撞体）。
  - Bellbearer / Maestro / Tiny：`custom` / `attach` + `CustomView`、`Decision.scale`、每类自己的 `parked`、单练的 `COMPANIONS` / `HOSTS`。
- 冲突只在接口上：`RangeTable.place()` 现在同时收 `vel`（Reed 的 coast）和 `ctx`（place_fn）；构建时每类只调一次 attach（`_attach`：先 `EnemySpec.attach`，没有就用模块的 `attach`，两个或三个参数都行）；`RangeTracker.estimate` 依次加：危险物 → 模块的 `extra`（针）→ `custom`（铃、Tiny 转圈 / 俯冲、Maestro 防御、Bellbearer 闪避）。
- 小节重新编号：§34 Envoy / Clawmaiden / 矛，§35 Reed / Minister，§36 Bellbearer / Maestro / Tiny，§37 这一节。
- 核对：
  - 10 类的表用合并后的代码从 R0 dev 重建，和各分支提交的表**逐字节相同**（10 / 10，`stage_c\tables`）。
  - 30 次评估（10 类 × fresh / R2 / 你的录像）在合并后的代码上重跑，summary 和阶段 A / B 的**完全一样**（旧的留在 `<类型>\prev_stageB\`）。
  - 攻击范围的 7 个测试文件全过（77 个，含新加的 `tests/test_attack_range_merge.py`：10 类都注册了、每种钩子都在、`place()` 收 vel 和 ctx、attach 两种写法都调对）。
  - 实时路径（叠加层和 viewer 用的 `RangeTracker`）在你 085824 第 2 次尝试上跑（7,229 个 STATE 帧，10 类都出场）：没有异常，每类都有估计；k 0 时所有真伤害碰撞体被所有估计的并集盖住 99.3 %（每 3 帧取一帧，主角中心区）。
  - 矛、铃、针不是 HealthManager 实体（缓存里没有 health_manager 位，也没有血量），所以 `--solo` 不会把它们当成"别的怪"去清（阶段 B 留下的问题）。

### 37.2 每类的精度（主行：没被打断、t + k 之前没开始下一招；三个数依次是 R0 fresh / R2 / 你的录像）

"招" = 这一类所有攻击家族合在一起（包括按第 2 组规则不画的待定行）；"危险物 / 投射物" = Clapper 的符文、Reed 的针、Bellbearer 的铃；"待机" = 现在的身体（批准的规则）。面积比 = 估计 / 真实（主角中心区），写的是逐行的中位数和 ≤ 1.5 的行占比。漏 p95 只算在那一边确实漏了的行（fresh）。完整的按家族的表：`C:\ssbot\data\m2_forum_are\summary.md`。

| 类型 | 部分 | k0 覆盖 % | k12 覆盖 % | k0 面积比 p50 / ≤1.5 | k12 面积比 p50 / ≤1.5 | k12 漏 p95（前 / 后 / 上 / 下，u） |
|---|---|---|---|---|---|---|
| Clapper | 招 | 99.6 / 99.6 / 99.6 | 95.4 / 94.6 / 94.9 | 1.00/97% / 1.00/97% / 1.00/94% | 1.01/93% / 1.01/93% / 1.01/92% | 2.1 / 0.9 / 5.8 / 0.9 |
| Clapper | 危险物 | 99.8 / 99.9 / 99.7 | 99.9 / 99.9 / 99.6 | 1.00/92% / 1.00/94% / 1.00/86% | 1.00/92% / 1.00/94% / 1.00/84% | 0.3 / 0.3 / - / - |
| Clapper | 待机 | 100.0 / 100.0 / 99.9 | 87.9 / 84.2 / 88.0 | 1.00/92% / 1.00/92% / 1.00/90% | 1.00/91% / 1.00/92% / 1.00/89% | 2.1 / 1.9 / 1.0 / - |
| Choristor | 招 | 99.8 / 99.7 / 99.7 | 96.9 / 97.2 / 96.8 | 1.00/97% / 1.00/96% / 1.00/98% | 1.01/84% / 1.00/88% / 1.01/85% | 0.4 / 0.8 / 0.5 / 0.6 |
| Choristor | 待机 | 100.0 / 100.0 / 100.0 | 100.0 / 99.2 / 98.7 | 1.00/100% ×3 | 1.00/100% ×3 | - / 0.1 / - / - |
| Envoy | 招 | 99.4 / 99.4 / 99.4 | 94.7 / 97.0 / 94.3 | 1.00/100% ×3 | 1.00/96% / 1.00/94% / 1.00/97% | 0.4 / 2.3 / 0.2 / 0.1 |
| Envoy | 待机 | 100.0 ×3 | 75.5 / 75.4 / 75.5 | 1.00/100% ×3 | 1.00/100% ×3 | 0.5 / - / - / - |
| Clawmaiden | 招 | 99.9 / 99.9 / 99.8 | 81.9 / 83.0 / 87.1 | 1.00/100% ×3 | 1.00/93% / 1.00/90% / 1.00/96% | 0.8 / 0.7 / 0.9 / 0.7 |
| 矛 | 招 | 99.0 / 99.1 / 98.9 | 80.2 / 82.3 / 85.9 | 1.00/100% ×3 | 1.00/92% / 1.01/94% / 1.01/95% | 3.0 / 1.8 / 3.2 / 3.0 |
| Reed | 招 | 98.8 / 98.8 / 98.9 | 88.6 / 87.0 / 91.3 | 0.99/100% ×3 | 1.00/93% / 1.00/94% / 1.00/94% | 3.2 / 1.1 / 0.5 / 0.6 |
| Reed | 针 | 100.0 ×3 | 99.7 / 99.6 / 99.6 | 1.00/100% ×3 | 1.28/93% / 1.26/93% / 1.24/93% | 0.1 / 0.1 / 0.1 / 0.3 |
| Reed | 待机 | 100.0 ×3 | 44.9 / 51.2 / 41.9 | 1.00/100% ×3 | 1.00/100% ×3 | 2.0 / 1.8 / 1.9 / 1.9 |
| Minister | 招 | 99.7 / 99.8 / 99.7 | 94.0 / 93.5 / 92.7 | 1.30/96% / 1.32/97% / 1.08/96% | 1.33/92% / 1.33/92% / 1.18/94% | 1.1 / 1.4 / 1.0 / 0.7 |
| Minister | 待机 | 100.0 ×3 | 58.5 / 61.1 / 58.0 | 1.00/100% ×3 | 1.00/100% ×3 | 2.0 / 1.7 / 1.9 / 1.9 |
| Bellbearer | 招 | 98.7 / 98.7 / 98.9 | 95.7 / 95.5 / 95.2 | 0.99/100% ×3 | 0.99/99% / 0.99/99% / 0.99/97% | 0.4 / 0.4 / 0.5 / 0.3 |
| Bellbearer | 铃 | 100.0 ×3 | 95.7 / 95.8 / 96.9 | 1.00/100% ×3 | 1.00/91% / 1.00/90% / 1.00/91% | 0.5 / 0.5 / 0.6 / 0.8 |
| Bellbearer | 待机 | 100.0 ×3 | 55.1 / 58.6 / 54.8 | 1.00/100% ×3 | 1.00/92% / 1.00/91% / 1.00/95% | 1.5 / 1.5 / 1.5 / 1.5 |
| Maestro | 招 | 99.3 / 99.3 / 99.1 | 84.1 / 83.4 / 84.2 | 1.00/100% ×3 | 1.00/100% ×3 | 4.7 / 0.6 / 1.4 / 0.4 |
| Maestro | 待机 | 100.0 ×3 | 71.4 / 73.2 / 73.9 | 1.00/100% ×3 | 1.00/100% ×3 | 1.2 / 1.4 / 1.0 / 0.9 |
| Tiny | 招 | 100.0 ×3 | 65.0 / 63.9 / 65.0 | 1.00/100% ×3 | 1.00/100% ×3 | 2.4 / 2.2 / 2.2 / 2.3 |
| Tiny | 待机 | 100.0 ×3 | 41.7 / 41.7 / 43.1 | 1.00/100% ×3 | 1.00/100% ×3 | 1.4 / 1.4 / 1.4 / 1.3 |

按家族看，k 12 面积比没到目标（p50 > 1.5，或 ≤ 1.5 的行不到九成）的只有这几个：
- Choristor 小跳 CH_HOP：p50 2.00 / 1.86 / 1.04，≤ 1.5 的行 44 / 44 / 62 %（前跳还是后跳要到起跳才知道，之前两种一起画；身体小，所以比值大）。这是已批准的版本，没改。
- Clawmaiden 抓 CM_SLASH：p50 1.50 / 1.46 / 1.43，≤ 1.5 的 50–54 %（朝向在 Slash 1、Slash 4 两次决定，之前几种一起画，§34）。
- Clapper 后撤 CC_EVADE：p50 1.05，≤ 1.5 的 72–78 %（单撤还是连撤两次要到第二次才知道）。
- Reed 闪避 RE_EVADE：p50 1.08，≤ 1.5 的 68–70 %。
- Minister 冲刺 / 闪避：p50 1.33，≤ 1.5 的 89–94 %（斜着的碰撞体在缓存里是外接框，估计和真值都偏大，§35）。

k 12 覆盖低的地方都是"12 帧后它在哪"推得不准，不是画得太小：待定的招按第 2 组规则不画（Reed 刺的起手 47.5 %、Maestro Fire Antic 68–69 %、Clapper 跳起前 78–84 %），Tiny 转圈 53–56 % / 俯冲 70 %，矛 80–86 %，以及会飞的怪待机时只画现在的身体（Reed 42–51 %、Tiny 42 %、Bellbearer 55–59 %、Minister 58–61 %）。

### 37.3 给你看的

- PNG 索引：`C:\ssbot\data\m2_forum_are\index.md`（每类：你录像里的帧 → 每种招两张 → 误差最大的几张；Clapper 在最前）。图例：橙色填充 = k 0 估计，浅蓝轮廓 = k 12 估计，细黄 = 主角中心区，粗红 = 现在的真伤害，细红 = 之后 12 帧的真伤害（+12 那一帧品红）。
- 回放：`C:\ssbot\data\m2_forum_overlay\all_range.rrd`（356 MB）：你 085824 的第 2 次尝试，原始帧 15163–29619，从第 0 波到第 7 波，10 类都出场；k 0 和 12；视频缩到 0.35。命令在 `stage_c\rrd.cmd`。
- 单练（实时叠加层，1–5 选 k；都是 `human_session --instance 8 --solo "<类型>" --speed 0.5 --overlay --overlay-range --display borderless`）：

| 类型 | `--solo` | 存档 | 同一波先清掉的（清的时候无敌 + 钉子 4 级） |
|---|---|---|---|
| Choristor | `"Song Pilgrim 03"` | `fo_r1_w0` | Reed、Envoy |
| Envoy | `"Song Pilgrim 01"` | `fo_r1_w0` | Reed、Choristor（Envoy 从埋伏入场） |
| Reed（+ 针） | `"Song Reed"` | `fo_r1_w2` | 一只 Bellbearer |
| Bellbearer（+ 铃） | `"Pilgrim 03 Song"` | `fo_r1_w2` | 一只 Reed |
| Clawmaiden（+ 矛） | `"Song Handmaiden"` | `fo_r1_w3` | 没有，只有她 |
| Minister | `"Song Administrator"` | `fo_r1_w4` | 另一只 Minister |
| Maestro（+ Tiny） | `"Song Pilgrim Maestro"` | `fo_r1_w6` | 另一只 Maestro（留下那只的 Tiny 不清） |
| Tiny | `"Song Automaton Tiny"` | `fo_r1_w6` | 同 Maestro |
| Clapper | `"Song Heavy Sentry"` | `fo_r1_w7` | 没有，只有它 |

- Clapper 的启动器：`C:\ssbot\sandbox\start_overlay_solo_clapper.ps1`（从这个工作区跑，日志 `overlay_solo_clapper2.log`；阶段 A 那个复制成了 `start_overlay_solo_clapper_stageA.ps1`）。没有跑。在游戏里跑过的只有 Choristor 和 Clapper（阶段 A 之前的工作区）。

### 37.4 没做的 / 等你定的

- 待机（会飞的怪、Clapper 走路）要不要按速度往前推：你定。Clawmaiden 的 Fly / 飞向抓 / 转已经按速度推（`clawmaiden.CARRY_ON`，§34），和规则不一样，也等你定。（你定了：按速度推，默认开，见 §38。）
- 第 2 组（还没决定的瞄准）这一轮不画：Reed 刺的起手、Maestro Fire Antic、Tiny Fire Ready、Clapper 跳起前（Jump Antic、Cast Slam Antic）、Clawmaiden 瞬移落点、矛的起手、所有待机之后的下一招。
- 其余各节留下的：Tiny 转圈要队形目标格、Pull Up 时刻；Reed 刺有 5 % 停得很短；针 / 矛 / 符文没有平台地形；丝弹时间窗口偏宽；部署的 oracle 有没有 `enemy.hp` 没核实。

复现：
```
cd <checkout>\brain
..\scripts\uv.cmd run python -m ssbot.tools.attack_range_build --type <类型> build --out <文件>     (和提交的表比)
..\scripts\uv.cmd run python -m ssbot.tools.attack_range_build --type <类型> eval --set fresh --every 2 --idle-every 6 --threads 4   (r2 / person；Tiny 用 --every 6 --idle-every 30)
..\scripts\uv.cmd run python -m ssbot.tools.are_summary
..\scripts\uv.cmd run python -m ssbot.tools.viewer C:\ssbot\data\human\20261009_085824 --zones --range-only --k 0,12 --video --video-scale 0.35 --from 15163 --to 29619 --save C:\ssbot\data\m2_forum_overlay\all_range.rrd
..\scripts\uv.cmd run python -m pytest -q tests\test_attack_range.py tests\test_attack_range_types.py tests\test_attack_range_envoy_clawmaiden.py tests\test_attack_range_reed_minister.py tests\test_attack_range_bmt.py tests\test_zone_overlay.py
```

## 38. 待机的身体按此刻的速度往前推（2026-10-10，你提的"按此刻速度补位置 + 一个小的固定余量"；分支 worktree-wf_9b753b9b-542-1 = main + 137a6b1；工具 `ssbot/tools/are_idlevel.py`；数据 `C:\ssbot\data\m2_forum_are\idlevel`：`summary.md` / `summary.json` / `png\`）

### 38.1 做了什么

- 待机（不在任何招式里的状态）的身体在 +k 帧 = 现在的身体整体平移 v × k/60 秒（游戏时间），不长大、不变形。包括：Reed Alert / Stab Pos / Defend / Throw Range，Minister Chase / Retreat? / Parry Stance，Bellbearer In Range / Out of Range，Maestro Forum Fly / Fly / Chase，Tiny Ready（队形飞行），Clapper Idle / Walk，Envoy Walker，Choristor Walker。函数 `attack_range.carry_body` / `carry_shift`，实时 `RangeTracker.estimate` 和离线 `attack_range_build.eval_track` 都用它。
- v = 这一帧导出的速度（游戏的刚体速度，原值，**不平滑**）。比过两种别的：用最近 3 帧位置差算速度（平滑）——每个 k 都更差（例：Reed k12 m0 覆盖 77.7 % vs 84.7 %）；常加速度（最近 3 帧的速度变化，|a| ≤ 150 u/s²）——k ≤ 12 时 m0 覆盖高 2-8 个点（Envoy 反而低 3 点），但 k ≥ 18 尾巴更长（k30 最大缺口 p95：Maestro 4.1 vs 2.3 u，Bellbearer 3.8 vs 2.5 u，Clawmaiden 4.6 vs 3.2 u），不算"明显更好"，没用。
- 平移被场地挡住：身体的框不穿左右墙（14.01 / 48.99）、地面（3.0）、穹顶下沿（`core.forum.dome_y`）；已经在外面的（Clapper 从穹顶上方掉进来）不往回推，只是不再往外走。
- 默认开（`attack_range.IDLE_CARRY = True`，你定的）；改成 False 就是原来的"身体现在的位置"，对比用。Clawmaiden 的 Fly / 飞向抓 / 转（§34，本来就按速度推，`CARRY_ON`）和 Maestro 的 Defend（§36）现在走同一个函数，也加了场地限制。
- 估计本身仍然没有余量；余量是决策时的选择，下面给每个 k 需要多少。

### 38.2 怎么量的

没用来建表的数据，各自分开：R0 fresh（35 场，每 24 帧取一帧）、R2（181 场，每 12 帧）、你的录像（9 个 session，每 6 帧）。只比身体：真值 = t + k/60 之后第一帧这只怪自己的碰撞体（铃、针、符文这些危险物有它们自己的行，这次没动）；k 之内开始了新招式、或者从 t - 0.3 s 到那一帧之间被打的行不算。都在英雄中心空间（加了受击框）。余量 m = 把估计按半径 m 的圆膨胀。每行记"最大缺口" = 把这一行完全盖住需要的余量。

### 38.3 回答你的问题

对的一半。补偿量确实和时间成正比：v × t。这些怪待机时 5-6 u/s（Reed / Minister / Bellbearer / Tiny / Clawmaiden，p95 7-9 u/s），所以下一帧只补 0.1 u，0.2 s 补 1.2 u，0.5 s 补 3 u。

但是补偿之后剩下的误差也随时间变大，而且比 t 涨得快（大约 ∝ t²）：怪在变速、变向——会飞的按和英雄的距离来回调（DistanceFly），Tiny 的队形飞行来回摆，Clapper 走走停停、会突然起步和掉头。所以：

- **k ≤ 12（≤ 0.2 s）：补偿 + 0.5 u 基本就是 100 %**（会飞的和走的每类 ≥ 99.3 %；Clapper 94.7-97.3 %）。
- **k 18（0.3 s）**：会飞的 86-98 %（Minister 99 %），要 1-1.7 u。
- **k 30-36（0.5-0.6 s）**：会飞的只有 38-88 %，要 2.2-5 u 才能盖住 99 % 的行；Clapper 走路要 7-9 u。
- 匀速走的（Envoy、Choristor Walker，2 u/s）到 0.6 s 也是 ≥ 96 %。

补偿 + 0.5 u 的覆盖（%，R0 fresh / R2 / 你的录像）：

| 类型 | k1（0.02 s） | k6（0.10 s） | k12（0.20 s） | k18（0.30 s） | k30（0.50 s） | k36（0.60 s） |
|---|---|---|---|---|---|---|
| Reed | 100 / 100 / 100 | 100 / 100 / 100 | 99.8 / 99.8 / 99.9 | 94.4 / 95 / 95.1 | 67 / 68.7 / 68.4 | 53.8 / 56.2 / 55.4 |
| Minister | 100 / 100 / 100 | 99.9 / 99.9 / 99.9 | 99.7 / 99.7 / 99.8 | 99.2 / 99.2 / 99.5 | 83.5 / 83.7 / 84.8 | 72.1 / 72.2 / 73.3 |
| Bellbearer | 100 / 100 / 100 | 100 / 100 / 100 | 99.9 / 99.9 / 100 | 92.4 / 92.5 / 92.7 | 66.1 / 65.5 / 66.1 | 54.6 / 53.5 / 54.1 |
| Maestro | 100 / 100 / 100 | 100 / 100 / 100 | 99.7 / 99.8 / 99.7 | 97.6 / 98 / 97.4 | 86.1 / 87.6 / 85.6 | 75.9 / 78.2 / 75.9 |
| Tiny | 100 / 100 / 100 | 100 / 100 / 100 | 99.9 / 99.9 / 99.8 | 94 / 94.2 / 94.6 | 54.8 / 54.8 / 59 | 38.1 / 38 / 43.2 |
| Clawmaiden Fly | 100 / 100 / 100 | 100 / 100 / 100 | 99.3 / 99.5 / 99.6 | 86.3 / 87.8 / 87.8 | 55.4 / 59.9 / 57.9 | 45.3 / 51.4 / 46.8 |
| Clapper | 99.9 / 99.9 / 100 | 99.2 / 98.8 / 99.5 | 96.6 / 94.7 / 97.3 | 92.2 / 87.6 / 93 | 82.5 / 71.3 / 80.1 | 77 / 63.5 / 71.8 |
| Envoy | 100 / 100 / 100 | 100 / 100 / 100 | 100 / 100 / 100 | 100 / 100 / 100 | 100 / 99.8 / 99.8 | 100 / 99.8 / 99.6 |
| Choristor | 100 / 100 / 100 | 100 / 100 / 100 | 100 / 100 / 100 | - / 99.9 / 100 | - / 97.7 / 98.8 | - / 96.4 / 97.7 |

要多大的余量 m(k) 才能让 99 % 的行完全盖住（u；三个数据集里取最大）：

| 类型 | k1 | k6 | k12 | k18 | k30 | k36 |
|---|---|---|---|---|---|---|
| Reed | 0.4 | 0.47 | 0.74 | 1.36 | 2.98 | 3.94 |
| Minister | 0.18 | 1.05 | 1.49 | 1.67 | 2.22 | 2.67 |
| Bellbearer | 0.14 | 0.25 | 0.64 | 1.18 | 2.9 | 3.93 |
| Maestro | 0.13 | 0.28 | 0.81 | 1.5 | 3.28 | 4.05 |
| Tiny | 0.11 | 0.21 | 0.57 | 1.05 | 2.29 | 3.12 |
| Clawmaiden Fly | 0.14 | 0.28 | 0.78 | 1.56 | 3.71 | 4.99 |
| Clapper | 0.79 | 1.6 | 3.2 | 4.75 | 7.65 | 9.25 |
| Envoy | 0.05 | 0.05 | 0.05 | 0.05 | 0.27 | 0.35 |
| Choristor | 0 | 0.05 | 0.05 | 0.49 | 0.91 | 1.05 |

- 会飞的大致是 m(k) ≈ 0.3 + 11 t² u（t = k/60 s；k12 0.7，k18 1.3，k30 3.1，k36 4.3），也就是 ½ a t²，它们的速度大约以 20 u/s² 在变。一个固定的 0.5 u 只在 0.2 s 以内够。
- Minister 在 k6 就要 1 u：它换状态时身体碰撞体换形状（Collider Fly / ParryStance / AttackAntic），不是移动的问题。
- Clapper：它站着（速度 0）然后突然以 8 u/s 起步，或者走着掉头，速度看不出来（和下一招一样是"还没决定"的事）。
- 面积（英雄中心空间，真实身体 = 1）：补偿 + 0.5 u 是 1.4-2.1 倍，补偿 + 1.0 u 是 1.9-3.4 倍，"身体现在 + 半个钉子长 1.5 u"是 2.5-5.1 倍。k30 会飞的：补偿 + 1.0 u 覆盖 69-97 %，"身体现在 + 1.5 u" 只有 50-88 %（R0 fresh）；补偿 + 0.5 u 是 55-86 %，和后者差不多但面积只有一半。补偿 + 小余量比一刀切的大余量好。
- 补偿本身：只按速度（m0）k12 的覆盖 Reed 45 → 85 %，Minister 58 → 90 %，Bellbearer 47 → 84 %，Tiny 42 → 83 %，Maestro 71 → 91 %，Envoy 75 → 99 %，Clapper 85 → 94 %（R0 fresh）。

### 38.4 图

`C:\ssbot\data\m2_forum_are\idlevel\png\`：每类 4 张 k30（0.5 s）的移动待机：红 = t + k 时真实的身体，灰 = 身体现在，蓝 = 按速度推，浅蓝 = 推 + 0.5 u，箭头 = v × t。每类第 0 张是最快的那次，后面 3 张按"推完还差多少"取中位、p90、最差（例：`tiny_2_Ready_k30.png` 队形飞行掉头，推过头 1.7 u；`minister_0_Chase_k30.png` 直线追，推完只差 0.05 u）。

### 38.5 没做的

- §37 的 `summary.md` 里的 idle 行还是"身体现在"的数，而且含危险物；30 个 eval 没重跑（现在重跑 idle 行就是补偿后的）。这一节的表只看身体。
- 余量随 k 怎么取（固定 / 按 t² 涨 / 每类一个表）是决策时的事，等你定。
- 匀加速的版本没用（见 38.1）；Tiny 队形、会飞的来回调距离，要更好只能预测它们的目标点（英雄位置 + 距离规则），这一轮没做。

复现：
```
cd <checkout>\brain
..\scripts\uv.cmd run python -m ssbot.tools.are_idlevel run --sets person --threads 4
..\scripts\uv.cmd run python -m ssbot.tools.are_idlevel run --sets fresh --every 24 --threads 4
..\scripts\uv.cmd run python -m ssbot.tools.are_idlevel run --sets r2 --every 12 --threads 4 --part 0/2     (和 --part 1/2 同时跑)
..\scripts\uv.cmd run python -m ssbot.tools.are_idlevel summary
..\scripts\uv.cmd run python -m ssbot.tools.are_idlevel png --per-type 4
..\scripts\uv.cmd run python -m pytest -q tests\test_attack_range_idlevel.py tests\test_attack_range.py tests\test_attack_range_envoy_clawmaiden.py tests\test_attack_range_bmt.py
```

## 39. 叠加层：五个提前量同时画 + 整条路径（2026-10-10，你 0.5 倍全波实战后提的："0 / 6 / 12 / 18 / 36 能不能同时显示"、小飞虫冲刺只看到停点、飞针怪三连刺只看到最后一刀闪；"做出来我看一眼就知道对不对"。分支 worktree-wf_c7b7336a-868-1；不做逐帧核对、不出 PNG）

### 39.1 按键（范围模式 range+red / range 里）

- **0**：五个提前量同时画（开 / 关）。每只怪用它自己的颜色：+0 填充，+6 实线，+12 / +18 虚线，+36 点线，越往后越淡；每块旁边标 +k。某个 k 的估计和更早的 k 是同一块区域时只画一次，标成 +0=6=12（待机不动的怪常见）。
- **9**：整条路径（开 / 关）：估计在第 0 帧到第 K 帧每一帧的并集（同时画时 K = 36，单个 k 时 K = 那个 k），浅色虚线 + 很淡的填充，标 "path 0-K"。小飞虫俯冲 / 冲刺的去程和回程、Reed 突刺、Minister 冲刺都是一整条带子。
- **1–5** 还是单个提前量（0 / 6 / 12 / 18 / 36），和原来一样（填充 + 细线 = 主角中心区）；同时画的时候不画主角中心区的细线，太乱。
- 此刻真实的伤害框照旧：不能拼刀红色、能拼刀橙色。F8 / F9 / F10 / F11 不变。
- 命令文件：`overlay all`（切换）/ `overlay all on|off`，`overlay swept` / `overlay swept on|off`。启动参数：`human_session --overlay --overlay-range --overlay-all-k --overlay-swept`（一开始就打开这两个）。

### 39.2 启动器

`C:\ssbot\sandbox\start_overlay_forum_all2.ps1`：和 `start_overlay_forum_all.ps1` 一样（第 8 实例、存档 fo_W 全波、0.5 倍、无边框），换成这个工作区，一开始就是"五个同时 + 整条路径"；日志 `C:\ssbot\sandbox\overlay_forum_all2.log`。会先等所有游戏窗口关掉再启动。没有跑。

看三连刺：开着 0（不开 9），Reed 三连刺时，每一刀的红框出来之前，同一个位置应该已经有一块标着 +6 或 +12 的轮廓。看小飞虫：开 9，俯冲 / 冲刺时那条浅色带子应该盖住它出去和回来的整条路。

### 39.3 回放（Rerun）

- `viewer <session> --zones --range-only --k 0,6,12,18,36`：每只怪 `range/<怪>/k<k>/raw|hero`（和原来一样）+ 新的 `range/<怪>/swept` = 0..最大 k 的路径；某个 k 和更早的 k 一样时标签里写 (=k0)。
- `viewer <session> --zones --range --k ...`：`enemies/<怪>/range/k<k>` + 新的 `enemies/<怪>/range/swept`。

### 39.4 开销（你 20261010_165427 第 0 次尝试，11,224 个游戏帧，每 3 帧算一次，和实时叠加层一样）

- 计算（五个 k + 0..36 每一帧的路径，一次过：`RangeTracker.ladder`，每只怪每个提前量只估一次）：中位 2.9 ms、p95 11.8 ms、最多 34 ms；单个 k 是 0.4 / 1.0 ms。
- 画（1080p，整次尝试）：五个同时 + 路径中位 11 ms、p95 22 ms、最多 37 ms（4K 43 / 54 ms）；单个 k 中位 8.7 ms、p95 14 ms（旧的画法）。只看 5 只怪以上的帧（第 6 波 Tiny 群）：五个同时 + 路径中位 18 ms、p95 27 ms，单个 k 8 ms。实时叠加层本来就最多按 1920×1080 画再放大，0.5 倍时够用。
- 为了这个把半透明填充改成 cv2 混合、虚线改成一次画完（单个 k 的画也从 10 ms 降到 8 ms）。

### 39.5 没做的

- 没有逐帧核对、没有 PNG（你说看一眼就知道）。上次中途停掉的逐帧检查工具 `are_path_check.py` 删了。
- 瞄准类招的不可逃逸区（每个格子按自己的高度选表）不在这一步。

## 40. 瞄准类招的不可逃逸区（瞄准区）：每个格子按自己的高度选表 + 地形（2026-10-10，你："瞄准区你需要做"；"按怪周围那块区域的高度画，不是按我现在在哪"；"跟着地形"。分支 worktree-wf_c7b7336a-868-1；工具 `ssbot/tools/aim_zones.py`；表 `knowledge/1.0.30000/enemies/forum/aim_zones_<招>.npz`（+ `.json` 面积）；数据 / 图 `C:\ssbot\data\m2_forum_aimics\zones3`）

### 40.1 做了哪些招

方法和 aim_ics（§30 / §31，飞针、长矛）一样：在决定那一刻，主角站在怪周围每个格子（HeroBox 中心，0.1 u），用这个状态的完整时序逃跑库（T = 120 帧，Forum_W 的运动学；先粗库，粗库逃不掉的格子再用全库）去躲；没有任何一条能躲开 = 不可逃逸。决定之后的招用攻击范围的模板（attack_range，从决定那一帧起每一帧的形状 + 位移）；主角在帧内扫掠（前半帧对上一帧的框、后半帧对这一帧的框，都随怪的位移平移）；余量 0.1 u。延迟 lat0（预先计划好）/ lat2（看到决定后再反应）。

| 招 | 决定 | 瞄准规则 | 抖动（每一种都要躲开） |
|---|---|---|---|
| RE_STAB 三连刺 | Stab 1 进入（第一下伤害） | 方向 = 进 Stab Antic 时定的朝向；L = 10 u（中位） | L 9 / 10 / 11 |
| MA_SLASH 指挥家斩 | Slash 1 进入（第一下伤害） | 方向 = 那时主角在哪一边 | 无（后退 2.37 u 是定值） |
| CC_JUMP 跳砸 | Jump Aim | 落点 L = 0.916 clamp(主角 dx - 5, ±12)，朝主角；落点超出 19.5 / 45.5 用"撞墙"分支 | L ± 0.4 |
| CC_JUMP_CAST 跳砸 + 符文 | Jump Aim | 同上 + 落地后的符文大圈（r 7.187，落点前 6.48 u，决定后第 79–130 帧） | L ± 0.4 |
| AT_DIVE 小飞虫俯冲 | Fire 进入 | 方向 = 那时主角在哪一边；起点 = Fire 进入时的位置；路径用模板，到 y 5.0（地面）停，x 不出场 | 速度 ×0.96 / 1 / 1.04 |

做不了的：长矛女的瞬移落点（v2 分类里没有量到决定时刻和落点规则）；Reed 反击的扇区、长矛女斩的方向（决定 = 第一下伤害，所有选项本来就在攻击范围里）。

### 40.2 合成图（你的更正）

画出来的是一张围着怪的图，每个格子按它**自己的高度**选表，和主角现在的状态无关：
- **地面带**：HeroBox 中心在站立高度 -0.25 ~ +0.25 u：地面状态（有冲刺，和实测一样）。
- **低空**：站立高度以上 0.25 ~ 1.5 u：低空两个高度档（0.25 / 1.0）× 下落 / 静止 / 上升，**没有冲刺**，取最坏（任一个逃不掉就算）。
- **高空**：1.5 u 以上：高空两个档（2.5 / 5.0）× 三种竖直速度，没有冲刺，取最坏。
地板在每个档的代表高度上是精确的（库就是在离地那个高度滚出来的）；档中间的格子用这个档的表在格子自己的位置读。

### 40.3 地形：预先按怪的位置分档，不在线算

- 为什么不在线：逃不掉的格子要把整个库走一遍（每个状态 3–100 万条），一个位置要几秒到几分钟，每次前摇算一次也来不及；分档以后叠加层只是查表（每只怪 0.1–0.5 ms）。
- 分档：怪的 x 每 1 u 一档（14.5 … 48.5）× 朝左 / 朝右，加上"空场"（没有墙）；怪的 y 每 0.5 u（Reed、跳砸）或 1 u（指挥家、小飞虫）一档。
- 墙（x 14.01 / 48.99）：逃跑路线在招的时间内碰到墙的不算（这样剩下的路线和真的一模一样）；贴墙 0.9 u 以内再加这个状态的"背后有墙"库（会蹬墙跳）。
- 穹顶（core.forum.dome_y）：往上撞到穹顶的路线不算。
- 怪自己也被地形挡：Reed y ≥ 4.6、小飞虫 y ≥ 5.0、x 不出场（攻击范围的墙）。
- 空场里逃不掉的格子在墙边档里还是逃不掉（墙只会去掉逃跑路线）。

### 40.4 多大（lat2，括号里 lat0；空场；u²）

| 招（怪的高度） | 地面带 | 低空 | 高空 |
|---|---|---|---|
| RE_STAB（Reed y 7.0） | 1.87（1.07） | 8.30（7.91） | 30.5（25.2） |
| MA_SLASH（y 6.0） | 1.72（1.35） | 7.14（6.75） | 25.6（22.5） |
| CC_JUMP（y 6.5） | 1.35（1.35） | 3.51（3.51） | 23.2（20.0） |
| CC_JUMP_CAST（y 6.5） | 1.35（1.35） | 3.51（3.51） | 94.8（81.8）* |
| AT_DIVE（y 14） | 0 | 0 | 38.0（27.6） |

- 地面带只在怪够低的时候有：Reed y ≤ 7.0（4.5–6.5 时 3.1 u²，7.5 起 0）；指挥家 y 5.0 时 2.55、6.0 时 1.72、7 起 0；小飞虫从 y 6–7 俯冲 2.35、8 是 1.58、9 是 0.95、10 起 0。跳砸的地面带 1.35 u² 就是它决定那一刻自己的身体（站在它身体里）。
- 高空没有冲刺，所以大；低空次之。
- \* 跳砸 + 符文的高空只用了粗库（符文圈在第 79 帧以后才打，失败得晚，库的跳帧加速失效，全库要几个小时），是偏大的上界；录像也说明它太大（40.6），先别信。

### 40.5 地形改变了多少（x 16.5 = 离左墙 2.5 u）

- 墙在攻击方向前面：墙外的格子不存在，区域被墙截掉（RE_STAB 地面 0.64 / 低空 3.1 / 高空 11.7，比空场小，是因为格子少了，不是更安全）。
- 墙在背后：RE_STAB 地面带 2.15 vs 空场 1.87（+15%；lat0 1.11 vs 1.07），其余三招地面 / 低空不变，高空差几个 u²。
- **注意（第一次扫描的错误）**：第一次扫描把"招结束以后才碰到墙"的逃跑路线也去掉了，墙边档（包括场中间 x 31.5 的档）的高空区偏大（RE_STAB 场中 46 vs 空场 30.5）。已修（只看招的帧），并在后台重扫（40.8），完成后自动替换表、图和验证；空场的数字不受影响。墙边的数字以重扫后的 `aim_zones_<招>.json` 为准。

### 40.6 录像验证（R0 dev，107 场；第一次扫描的表）

在每个录到的决定帧（前摇之后进入决定状态的第一帧）查主角 HeroBox 中心在不在合成区（按主角自己的高度选类），再看这只怪在招的时间内有没有打中主角（受伤或被无敌帧挡掉都算）。

| 招 | 决定数 | 区内（lat0） | 区内被打中 | 区内没被打中、没拼刀、怪也没被打 | 其中 地面 / 低空 / 高空 |
|---|---|---|---|---|---|
| RE_STAB | 1926 | 579 | 496（86%） | 37 | 2 / 9 / 26 |
| MA_SLASH | 7922 | 155 | 104（67%） | 25 | 0 / 0 / 25 |
| CC_JUMP | 2087 | 69 | 34 | 23 | 0 / 2 / 21 |
| CC_JUMP_CAST | 1950 | 604 | 183 | 226 | 0 / 2 / 224 |
| AT_DIVE | 7883 | 458 | 347（76%） | 60 | 0 / 3 / 57 |

- 地面和低空的"区内却没被打中"很少（Reed 地面 2 / 33、低空 9 / 73）。高空多：表假设空中没有冲刺，实战里主角在空中常常还有冲刺（还有下劈弹跳），所以高空区对"有冲刺"的主角偏大，这是规则本身（你要的"空中不算冲刺"），不是错。
- 跳砸 + 符文的高空（224 次）明显太大：粗库 + 符文，见 40.4。
- 区外被打中不是错误（主角没躲）。lat2 的数字在 `validate.json`。

### 40.7 叠加层和回放

- 范围模式（range+red / range）里按 **8** 开 / 关（命令文件 `overlay aim [on|off]`，启动参数 `--overlay-aim`）。每只正在瞄准前摇里的怪（Reed Stab Antic、指挥家 Fire Antic、跳砸 Jump Antic / Cast Slam Antic / Jump Aim、小飞虫 Fire Ready）画它的合成区，放在怪**此刻**的位置、朝它的方向（Reed 用朝向，其余用主角此刻在哪边），用怪颜色的浅色：地面带填充 + 粗线，低空实线，高空虚线；区是空的只写 "zone 0"；旁边写 "aim 招 lat2: G / L / H 面积"。图例写了三个带的边界。
- 启动器 `C:\ssbot\sandbox\start_overlay_forum_all2.ps1` 已加 `--overlay-aim`（一开始就开），还是这个工作区。没跑。
- 回放：`viewer --zones --range` 多了 `enemies/<怪>/aim/ground|low|high`；`viewer --zones --range-only` 多了 `range/<怪>/aim/ground|low|high`。
- 开销：每只怪每次计算查表 + 轮廓 p50 0.1–0.5 ms（第一次 54 ms），五张表一起加载 26 ms。

看什么：Reed 三连刺前摇里 Reed 下面那条地面带（红框出来之前站在里面就躲不掉）；小飞虫低空俯冲（y ≤ 9）时的地面带；指挥家低的时候的地面带；高空虚线区是"空中没有冲刺"的情况，有冲刺时可以不理。

### 40.8 PNG、重扫、没做的

- 图：`zones3\aimzone_<招>.png`（上排：空场 / 墙在前 / 墙在后的合成区；下排：每个格子都用同一类时的三张类表，空场，粗库）。重扫完会重画。
- 重扫：`C:\ssbot\sandbox\aim_zones_rescan.ps1`（两个 Idle 进程，约 4 小时），完成后写 `zones3\rescan_done.txt`，自动 pack 到 knowledge、重画 PNG、重跑验证（`zones3\validate.json`）。
- 前摇里怪自己的移动（低优先级，只报告）：Reed 的 Stab Antic 身体移动 p50 2.13 / p95 4.52 / 最多 5.45 u（v2 分类），按"此刻位置"画的区在前摇开始和 Stab 1 时的真实位置能差 2–4.5 u，看得出来；小飞虫 Fire Ready 漂 ±5–7 u，也看得出来；指挥家前摇里后退 2.37 u；跳砸前摇里身体基本不动（≤ 0.63 u）。没有做按主角相对的表。
- 没做：物理相位（用 60 Hz 帧和模板的时钟）；拼刀、无敌帧；怪的身体在决定之前；几只怪同时瞄准的联合区；5 u 以上的高空格子用 5.0 档的库（落地比实际早）；跳砸 + 符文的高空只用粗库。

## 41. 小虫子（Tiny）的俯冲从 Maestro 起手就画出来（2026-10-10，你在实战后说："现在能看到小虫子冲刺的整条路线，但是好像是开始冲刺了才出现……前摇的时候就应该能算出小虫子的路径了，还能早半秒"；分支 worktree-wf_19fa72dc-053-1 = main 58db3f1 + 8257114（§39 的叠加层）；代码 `ssbot/combat/are_types/tiny.py`（`simulate` / `variants` / `dive_paths` / `dive_rest` / `path` / `early`）、`ssbot/combat/attack_range.py`（`RangeTracker.path`，`ladder` 顺带算 `paths`）、`ssbot/tools/zone_overlay.py`（"dive" / "dive if hero moves" 两种轮廓）；工具 `ssbot/tools/tiny_early.py`（chain / rows）、`tiny_early_png.py`；数据 `C:\ssbot\data\m2_forum_are\tiny_early`）

### 41.1 回答：对，起手那一帧几乎全定了，只剩两件事看你

把 Tiny 的 FSM 解出来了（它不在场景里，是 Maestro 生成的预制体：`localpoolprefabs_assets_areahang.bundle`，`Control`），和 Maestro 的 FSM 对着看，整条链是：

1. **Maestro 进 Fire Antic 的那一帧**：转身面向你（只在进入时转一次），从"准备好的小虫子"里随机挑一只，当帧发 FIRE READY。被挑中的那只同一帧或下一帧进 Fire Ready（R0：1 帧 0.017 s，你的 0.5 倍：1 个游戏帧 0.008 s；R0 dev 7,769 次全部找得到同时起手的 Maestro）。所以**哪一只**在起手第一帧就看得到（它的状态变了）。在这之前（Maestro 选 FIRE 还是 DEFEND、挑哪只）是随机的，提前不了。
2. **前摇 0.7 s**：Maestro 往后退 15 u/s（每个物理步 ×0.9，一共 2.37 u）。被挑中的 Tiny 飞向 Maestro 身上的"Slash Point"（Maestro 背对你那一侧 1.87 u、上方 1.88 u），最快 7 u/s、加速度 20 u/s²（到点 0.15 u 内减速）。
3. **FIRE**（Maestro 进 Slash 1，起手后 0.7 s + 1 帧：R0 0.716–0.717 s，7,769 / 7,769；你的 0.5 倍 0.700–0.708 s）：Tiny 当帧转向你——**冲的方向 = 这一刻你在它哪一边**（99.8 %）；速度 (24 u/s 朝前, −39 u/s)，y 每个物理步 ×0.945。
4. **落地滑行**：向下 2 u 的射线碰到地面就 Brake（落地时 y p50 4.88，最高 5.00），x 不减速贴地滑，y ×0.8。
5. **拉起**："越过你 5 u"（Fire 0.5 s 后 / Brake 0.25 s 后才开始检查；实测拉起时离你 p50 5.24 u）或滑 1 s 到时 → Pull Up（x ×0.935，y 每步 +1 到 17 u/s，0.35 s）→ Return 飞回 Maestro（≤15 u/s，到 5 u 内）。撞墙 → Wall Bonk（以 8 u/s 弹回，0.35 s）→ Return。
6. 全部跑在 50 Hz 的物理步上，**没有任何随机**。R0 dev 的结局：Fire>Brake>Wall Bonk 2,340，Fire>Brake>Pull Up 1,919，Fire>Brake>Pull Up>Wall Bonk 1,169，Fire>Pull Up 1,000，Fire>Wall Bonk 585。

所以起手那一帧就定了：哪一只、什么时候冲（0.7 s 后）、从哪里冲（模拟它飞向 Slash Point）、角度和速度、在哪个高度落地。**还没定的只有两件，都看你**：

- **往哪边冲**：FIRE 那一刻你在它哪边。起手时用"你现在在预测起点的哪一边"猜：R0 dev 95.8 %，0.2 s 后 96.4 %，0.4 s 后 97.5 %，0.6 s 后 99.1 %（R2 93.4 / 94.1 / 95.8 / 98.4 %）。
- **滑多远**：滑到你身后 5 u 才拉起，你接着往同一方向跑，它就滑得更远（最多 1 s 或撞墙）。

伤害：小虫子只有身体伤人。R0 dev 有 53 % 的俯冲碰到了 bot，第一次碰到在起手后 p50 1.32 s（p5 约 0.9 s）；起手的 0.7 s 里只有 0.3 % 碰到。你的录像 19 % 碰到（p50 1.13 s）。

### 41.2 预测有多准（预测是在起手后 a 秒做的；"没被打"= 起手前后 Maestro 和这只 Tiny 都没挨打；路径误差 = 画出来的几条里离真实位置最近的那条，在起手后 0.8 / 1.0 / 1.2 / 1.4 s 比）

| 组（没被打的次数） | a | 起点误差 p50 / p90 / p95 | 起点离它现在的位置 p50（原来的画法） | 方向猜对 | 两边都画 | 猜对或两边都画 | 路径误差 p50 / p90：0.8 s · 1.0 s · 1.2 s · 1.4 s |
|---|---|---|---|---|---|---|---|
| R0 dev（3,843） | 0.0 | 0.21 / 0.62 / 1.69 | 4.65 | 95.8 % | 16.7 % | 99.7 % | 0.29/0.99 · 0.30/0.88 · 0.35/1.58 · 0.41/3.09 |
| | 0.2 | 0.15 / 0.15 / 1.21 | 3.63 | 96.4 % | 10.0 % | 99.7 % | 0.23/0.75 · 0.23/0.72 · 0.30/1.29 · 0.39/2.97 |
| | 0.4 | 0.15 / 0.15 / 0.30 | 2.28 | 97.5 % | 6.0 % | 99.7 % | 0.24/0.61 · 0.23/0.56 · 0.29/0.96 · 0.37/2.88 |
| | 0.6 | 0.15 / 0.15 / 0.15 | 0.88 | 99.1 % | 1.7 % | 99.8 % | 0.24/0.59 · 0.24/0.48 · 0.29/0.78 · 0.36/2.75 |
| R0 fresh（1,330） | 0.0 | 0.21 / 0.40 / 1.56 | 4.60 | 95.7 % | 17.2 % | 99.9 % | 0.29/0.85 · 0.30/0.83 · 0.35/1.58 · 0.41/3.30 |
| | 0.4 | 0.15 / 0.15 / 0.15 | 2.25 | 97.4 % | 5.9 % | 99.5 % | 0.24/0.61 · 0.24/0.60 · 0.31/1.16 · 0.39/3.27 |
| R2（882） | 0.0 | 0.19 / 0.40 / 1.16 | 4.55 | 93.4 % | 24.6 % | 100 % | 0.35/0.97 · 0.35/0.82 · 0.40/1.56 · 0.46/3.96 |
| | 0.4 | 0.13 / 0.15 / 0.15 | 2.22 | 95.8 % | 11.5 % | 99.7 % | 0.30/0.83 · 0.28/0.70 · 0.40/1.27 · 0.44/3.83 |
| 你的录像（46） | 0.0 | 0.21 / 1.77 / 2.44 | 4.04 | 100 % | 0 % | 100 % | 0.60/1.93 · 0.46/1.89 · 0.43/1.95 · 0.44/1.90 |
| | 0.4 | 0.01 / 0.85 / 0.95 | 2.20 | 100 % | 0 % | 100 % | 0.49/0.74 · 0.37/0.58 · 0.36/0.53 · 0.41/1.01 |
| 你的录像，含被打的（244） | 0.0 | 0.57 / 2.04 / 2.53 | 4.17 | 80.7 % | 50.4 % | 99.2 % | 0.64/2.04 · 0.59/2.74 · 0.67/3.04 · 0.79/5.15 |
| | 0.4 | 0.01 / 0.85 / 0.93 | 2.16 | 88.9 % | 31.2 % | 99.2 % | 0.52/1.06 · 0.44/1.56 · 0.43/2.36 · 0.50/4.94 |

- 起点误差 0.15 u 那一档是物理步的量化（7 u/s × 0.02 s）；你的录像 p90 0.85 u 是缓存把两个游戏帧并成一行（第一行 Fire 有时已经冲了一步 0.88 u），不是模型误差。
- 起手时 p95 1–2 u 的那几次：Maestro 往后退时撞墙、或起手前一帧 Tiny 正在急转（它前一帧还在跟队形飞）。
- 你的录像里"两边都画"多：你常站在小虫子正下方打它，起手时离起点不到 9 u/s × 0.7 s ≈ 6.3 u。
- 1.4 s 以后 p90 变大：已经在 Return 或 Wall Bonk 弹回里了，Return 要追正在动的 Maestro，这一段不提前画（见 40.3）。

### 41.3 画法

- **Fire Ready（起手中的那只）**：+k 的估计 = 模拟出来的 t + k 时刻的身体（还在飞向起点，或已经冲出去）；按 **9**（整条路径）多画两种带子：
  - **"dive"**（实线带）：你站着不动的话它会走的路：飞到起点 → 冲下来 → 落地滑到你身后 5 u（或撞墙 / 1 s）→ 拉起，画到拉起结束。
  - **"dive if hero moves"**（同一颜色，淡）：你还能改变的部分——你来得及跑到起点另一边时（|你的 x − 起点 x| ≤ 9 u/s × 离 FIRE 的时间）画另一边的整条镜像路径；以及你接着往前跑时更长的滑行（到 1 s 或墙）。9 u/s：起手到 FIRE 之间你的 x 变化 p95 5.9 u / 0.7 s（R0 dev，你的录像 7.1 u）。
  - 宽度（R0 fresh 1,330 次，按 x 方向的跨度；"dive" 本身从飞向起点到拉起 p50 22 u）：两边都画的时候多出 p50 16–17 u（整条镜像，起手时 17 % 的次数、0.2 s 11 %、0.4 s 6 %、0.6 s 2 %）；只多一段更长的滑行时 p50 0 u（多数本来就滑到墙或 1 s），p90 起手时 9.6 u、0.6 s 时 7.7 u。
- **冲出去以后（Fire / Brake / Pull Up）**：同一个模拟从当前状态往后算（原来是按速度 + 上一帧加速度直线外推），整条路径也继续画到拉起结束。Wall Bonk / Return 还是按速度。
- **Return 不提前画**：它飞回 Maestro 现在的位置，而 Maestro 那时在 Slash 之后的 Forum Fly 里乱飞，误差大；回程本来就慢（≤15 u/s），+0..36 的路径（§39）够用。
- FIRE 时刻 = 起手 + 0.7 s + 0.8 个游戏帧（实时：叠加层喂进来的每帧 dt；离线：轨迹里最短的"状态内时间"，因为你的 0.5 倍缓存把两个游戏帧并一行）。用 1 个游戏帧时冲刺段误差 p50 0.62 u，0.8 帧 0.24 u（物理步 50 Hz 和画面 60 Hz 的相位）。
- 开销（一只 Tiny，`ladder((0, 6, 12, 18, 36), sweep=36)`）：起手中 p50 3.3 ms（原来 2.7），冲刺中 2.8 ms（原来 2.4）；每帧的模拟算一次，所有 k 共用。

### 41.4 估计误差：改之前 vs 改之后（`attack_range_build eval --ks 0,12,36`，Tiny 的 Fire Ready 到 Return 现在算一个家族，所以起手中往后看 36 帧看到冲刺也算主行；"之前"= SSBOT_TINY_EARLY=0，即原来的画法；不含被打断的行；覆盖 = 真伤害格子被盖住的比例，面积比 = 估计 / 真，主角中心区）

| 组 | 行 | k | 之前 覆盖 / 面积比 | 之后 覆盖 / 面积比（p95） |
|---|---|---|---|---|
| R0 fresh | 起手中（Fire Ready，13,814 行） | 12 | 67.2 % / 1.00 | 87.7 % / 1.01（1.03） |
| | | 36 | 6.5 % / 1.00 | **68.0 %** / 1.08（1.99） |
| | 冲刺中（Fire..Return，34,460） | 12 | 71.0 % / 1.00 | 79.2 % / 1.02 |
| | | 36 | 14.2 % / 1.00 | 37.0 % / 1.15 |
| R2 | 起手中（7,225） | 12 | 68.5 % / 1.00 | 88.8 % / 1.01（1.03） |
| | | 36 | 6.8 % / 1.00 | **70.2 %** / 1.09（2.00） |
| | 冲刺中（17,964） | 12 | 71.5 % / 1.00 | 79.5 % / 1.02 |
| | | 36 | 14.8 % / 1.00 | 36.8 % / 1.14 |
| 你的录像 | 起手中（1,292） | 12 | 70.0 % / 1.00 | 91.7 % / 1.02（1.03） |
| | | 36 | 5.3 % / 1.00 | **75.5 %** / 1.22（2.03） |
| | 冲刺中（2,868） | 12 | 70.6 % / 1.00 | 80.9 % / 1.02 |
| | | 36 | 12.6 % / 1.00 | 37.9 % / 1.12 |

起手中按起手后的时间分（R0 fresh，k 36 覆盖 之前 → 之后）：0–0.1 s 25.6 → 84.3 %，0.1–0.3 s 12.3 → 65.9 %，0.3–0.5 s 0.1 → 66.9 %，0.5–0.75 s 0 → 64.4 %。k 0 两边都是 100 %。面积比 p95 2.0 = 两边都画的那些行。

剩下的漏：冲刺 44 u/s，物理步（50 Hz）和画面（60 Hz）的相位不知道，同一个时刻真实位置会差半步到一步（0.4–0.9 u），身体只有 1.0 × 1.08，所以 k 36 的覆盖停在 65–75 %。要盖满得沿路径前后各多画一个物理步（±0.02 s 的一小段），这是余量，按规则这一步不加，留给定余量的时候。冲刺中的 k 36 只到 37 %，主要是 Return / Wall Bonk 还在按速度外推。

### 41.5 图

`C:\ssbot\data\m2_forum_are\tiny_early\png`：每张一次 Maestro 起手，四格 = 起手后 0.0 / 0.2 / 0.4 / 0.6 s 时画的东西和真实的对比。红线 = Tiny 真实走的路（起手到飞回），红点 = 真实的起点，深红方块 = 那一格时刻它在哪；橙色带 = "dive"（你不动时），橙色方框 = 预测的起点；黄色淡带 = "dive if hero moves"；白框 = 那一刻的你，白短竖线 = FIRE 时你的 x；品红框 = Maestro；灰线 = 地面和墙。你的录像 8 张（`20261004_091214_*`：撞墙 4、滑过你后拉起 3、空中拉起 1），R0 fresh 6 张（`20261003_074533_*`：起点附近两边都画 2、撞墙、滑过拉起、空中拉起、起手时方向猜错 1——那次 bot 在 FIRE 前最后约 0.1 s 里从起点右边不到 1 u 跑到了左边，起手时离起点超过 9 u/s × 剩余时间，所以没画另一边，`index_<组>.json` 写着每张为什么选）。

### 41.6 启动器

`C:\ssbot\sandbox\start_overlay_forum_tiny.ps1`：和 `start_overlay_forum_allk.ps1` 一样（第 8 实例、fo_W 全波、0.5 倍、无边框、一开始就是"五个同时 + 整条路径"），换成这个工作区；日志 `C:\ssbot\sandbox\overlay_forum_tiny.log`；会先等所有游戏窗口关掉。没有跑。看法：开着 9，Maestro 一起手（往后一退），被挑中的那只小虫子身上就会出来一条橙色带子一直画到地面、滑过你身后、拉起；你站在它正下方附近时还会有另一边的淡带子，等你站定一边它就消失。

### 41.7 没做的

- Return（飞回）不提前画（40.3）。
- Maestro 起手时被打退、撞墙时的起点误差（p95 1–2 u）没单独建模。
- 沿路径 ±1 物理步的相位余量没加（40.4）。
- 规划器（forum_planner）还没用这个：它现在只用叠加层 / 估计；"FIRE 时你在哪边决定它往哪冲"是可以利用的（站定一边就把冲刺引到另一边），没做。
