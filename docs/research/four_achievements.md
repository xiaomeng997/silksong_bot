# 一局钢铁之魂录像能否拿齐四个通关成就（PC 1.0.30000）

**问题：** 同一个 Steel Soul 存档、一次不死的录像里，能不能先在 Ending 1（Weaver Queen，`ENDING_A`）拿到 Steel Soul（`STEEL_SOUL`）和 Speedrunner（`SPEEDRUN_1`，playTime < 5 h），然后继续玩同一个存档，到 100 % 和一个更晚的结局时再拿 Speed Completion（`SPEED_COMPLETION`，100 % 且 < 30 h）和 Steel Heart（`STEEL_SOUL_FULL`，Steel Soul 下 100 %）？录像里还要能看到 Steam 弹出的成就提示。

**标签：** 【码 文件:行】反编译 1.0.30000 C#（`C:\ssbot\decomp\1.0.30000\Assembly-CSharp`）；【包】离线 UnityPy 读训练副本 `C:\ssbot\game\train` 的场景包和数据包（只读）；【攻】社区资料或我对游戏的记忆，没有用游戏数据核对；【推】由代码或数据推出、未实测；【估】估计；【未核实】待实测或待查。

**脚本与原始输出：** `C:\ssbot\sandbox\four_ach_scripts\`（全部离线、idle 优先级，没有连接任何游戏实例）。方法沿用 `research/forum_route.md`（分支 `worktree-wf_c0d56d51-4cb-5`）和 `research/benches.md`（分支 `research-benches`）。主要文件：`scene_all.py`（场景对象和组件字段）、`fsm_dump3.py` / `raw_state.py`（FSM 导出，后者看原始 actionData）、`scan_str.py` / `find_str.py`（字符串扫描）、`tools_count.py` + `masterlists.py`（工具、纹章、成就和主列表）、`item_ids.py` + `scan_items.py` → `scan_items.jsonl`（全部 590 个场景包里引用 100 % 物品的组件）、`summ2.py` → `summ2_tools.txt`、`quest_rewards.py` / `quest_dump.py`（任务奖励和条件）、`shops_compact.py` → `shops_compact.txt`（读 forum_route 的 `shops_all.txt`）、`scan_endings.txt`、`scan_grindle.txt`、`scan_settoollocked.txt`。

**导出器的已知限制：** 1.0.30000 的部分 FSM 是 `dataVersion 2`，float 和 bool 参数放在 `fsmFloatParams` / `fsmBoolParams` 里，`fsm_dump3.py` 解不出来（输出里的 `err15/err17` 和 bool 值不可信）。下文只引用字符串、枚举、对象引用、action 是否启用这几类可靠字段；唯一引用的 float（Award FSM 的 5.75 s）是用 `raw_state.py` 从原始数据读出的。

---

## 0. 结论

1. **可以，代码和数据里没有任何阻碍。** 四个成就都只在 `GameManager.CheckCompletionAchievements()` 里发放，每次片尾结束后的完成度画面都会调用它，每次都用存档当时的状态重新判断，跟第几次通关、之前看过哪个结局都无关【码 GameManager.cs:2999-3025】【包 end_game_completion】。
2. **顺序是固定的：Ending 1（A）→ 继续同一存档 → 完成 Silk and Soul 前置 → 第二次打 GMS，用 Needolin 拿 Snared Silk（C）进入 Act 3 → 在 Act 3 收齐 100 % → Sister of the Void（E）片尾。** 100 % 必须有 Everbloom（`HasWhiteFlower`），它只能在 Act 3 拿到【包】；Act 3 里能触发片尾的只有 Ending E【推】，所以后两个成就只能在 Ending E 的片尾里拿到（§2、§4）。
3. **最早的发放点：**
   - `ENDING_A`：Ending 1 片尾（`End_Credits`）开始的下一帧。
   - `STEEL_SOUL`、`SPEEDRUN_1`：同一次通关，完成度画面（`End_Game_Completion` 的 "Game Completion Act 2"）出现约 5.75 s 后。按路线 P50 约 3.5 h 游戏时间【估，DESIGN §3.6.4】。
   - `COMPLETION`、`STEEL_SOUL_FULL`、`SPEED_COMPLETION`：Ending E 之后的完成度画面（"Game Completion Act 3"）出现约 5.75 s 后，前提是此时已收齐 100 %，且最后一次存档时的 playTime ≤ 108000 s。
4. **代价和风险集中在 Ending 1 之后。** Ending 1 之后死一次，这个存档就拿不到 `STEEL_SOUL_FULL` 和 `SPEED_COMPLETION`（`COMPLETION` 也随之没了，但它可以在普通存档里另拿）；已经推送到 Steam 的 `STEEL_SOUL` 和 `SPEEDRUN_1` 不受影响【码 AchievementHandler.cs:84-94】。100 % 要多打一遍 GMS，再加上 Act 3 的 Lost Lace、三到四个"心脏" boss，以及 Phantom、First Sinner 等原路线不碰的 boss 和大量许愿任务，A 类遭遇大约是原路线的两到三倍【估】。
5. **录像要看到 Steam 弹窗，有三个前提：** 账号上还没有这些成就（已有的不会再弹，FIRST_TOOL 已在 M0-P5 解锁）；Steam 叠加层打开；录制软件能录到叠加层。DESIGN §2.6 目前把叠加层和原生弹窗都关掉了，所以要改成只在最后一章（Cradle 工作台 → GMS → 片尾）打开叠加层（§3.6）。

---

## 1. 结局之后存档怎么样（问题 1）

### 1.1 各结局的流程【包】【码】

| 结局 | 触发（FSM） | 写入的状态 | 过场链 | 回到菜单 | 下次 Continue |
|---|---|---|---|---|---|
| **A** Weaver Queen | `Cradle_03` `Boss Scene/Death Sequence` FSM `Control` 的 `To End Cinematic A` 状态 | `QueueAchievement ENDING_A`、`MenuStyleUnlockAction ENDING_A`、`ReportGameEnding`、`SetEndingCompleted` = 1（Act2Regular） | `ChangeToScene Cinematic_Ending_A` → 视频（`videoType` 4 = Ending）→ `End_Credits` → `End_Game_Completion` | `EndingSequence.OnSequenceComplete` → `ReturnToMainMenu(willSave: true)` | 最后一张坐过的工作台（`respawnScene`），仍在 Act 2 |
| **C** Snared Silk | 同一 FSM 的 `To End Cinematic C` | `ENDING_C`、`SetEndingCompleted` = 4（Act2SoulSnare）、**`StartBlackThreadWorld`** | `Cinematic_Ending_C`（`fireQueuedAchievements` = 1）→ `End_Credits` → `End_Game_Completion` | 同上 | 进入 Act 3：`Opening_Sequence_Act3`，重生点改为 `Song_Tower_Destroyed` |
| **D** Twisted Child | `Boss Scene/Death Sequence Cursed` FSM `Contorl` | `ENDING_D`、`SetEndingCompleted` = 2（Act2Cursed） | `Cinematic_Ending_D` → `End_Credits` → `End_Game_Completion` | 同上 | 同 A |
| **E** Sister of the Void | `Abyss_Cocoon` `Boss Control/Superjump Sequence` FSM `Control` 的 `Transition To Ending` | `SetEndingCompleted` = 8（Act3Ending）；`ENDING_E` 由 `Cinematic_Ending_E` 场景里的 `Award Achievement` FSM 发放 | `Cinematic_Ending_E`（`videoType` 5 = EndingE）→ `End_Credits_Scroll`（若 `MushroomQuestCompleted` 则先 `Cinematic_MrMushroom`，它会排队 `HERALD_WISH` 再进 `End_Credits_Scroll`）→ `End_Game_Completion` | 同上 | 最后一张工作台，仍在 Act 3【推】 |
| B（Embrace） | `Death Sequence` 的 `Path Check` 只有一个 `BoolTest` 能发 `EMBRACE`，它被禁用（`[DISABLED]`） | 会排队 `ENDING_B`，但成就列表里没有这个键 | — | — | **正常游戏中触发不了**【包 + 推】 |

代码出处：视频结束后 `Ending` 类型载入 `End_Credits`，`EndingE` 类型载入 `Cinematic_MrMushroom` 或 `End_Credits_Scroll`【码 CinematicPlayer.cs:735-746】；`End_Credits` 和 `End_Credits_Scroll` 的 `CutsceneHelper.nextSceneType` = 3 = GameCompletionScreen → `LoadScene("End_Game_Completion")`【包】【码 CutsceneHelper.cs:132-134】；`End_Game_Completion` 的 `EndingSequence` 在链结束时调用 `ReturnToMainMenu(willSave: true, isEndGame: true)`【码 EndingSequence.cs:54-58】。**跳过视频或片尾不会绕过完成度画面**：片尾的 Skip 直接走 `DoSceneLoad`，下一站不变【码 CutsceneHelper.cs:88-104】；视频的 Skip 只是淡出并停止播放器，之后照常进入 `FinishVideo` → `End()`【码 CinematicPlayer.cs:354-383，300，695-753；后半段为推断】。

### 1.2 存档被保留，不会锁定【码】

- `ReturnToMainMenu` 依次调用 `AwardQueuedAchievements()`、`TimePasses()`、`SaveGame(...)`，然后进入 `Quit_To_Menu`【码 GameManager.cs:5339-5426】。整个流程里没有任何按 `permadeathMode` 分支的逻辑。
- 全部按 `permadeathMode` 分支的代码只有：`PlayerDead` 把 On 改成 Dead【码 HeroController.cs:9375-9377】，存档槽在 Dead 时显示 Defeated【码 SaveSlotButton.cs:808】，几个 Steel Soul 专属内容（日志条目、Materium、`SlaveDeliveryQuestCompleted`）【码 EnemyJournalRecord.cs:105，MateriumItem.cs:49-50，PlayerData.cs:3043-3053】，以及成就检查本身。**结局不改 `permadeathMode`，存档槽仍是 SavePresent，可以继续玩。**
- `SetEndingCompleted` 只做 `CompletedEndings |= 状态` 和 `LastCompletedEnding = 状态`【码 SetEndingCompleted.cs:15-25】；`RecordGameComplete()` 是空函数【码 GameManager.cs:3027-3029】。这两个字段只用于存档槽上的结局图标【码 SaveSlotCompletionIcons.cs:68-81，SaveStats.cs:85-86】。全部场景包的 MonoBehaviour 里都找不到字符串 `CompletedEndings`（`LastCompletedEnding` 也包含这个子串）【包 `scan_endings.txt`】，所以**没有任何 FSM 依据"看过哪个结局"改变世界**。
- Continue 的入口 `RunContinueGame`：`IsAct3IntroQueued`（`blackThreadWorld && !act3_wokeUp`）为真时调用 `StartAct3()` 并载入 `Opening_Sequence_Act3`，否则 `ReadyForRespawn` 回到 `respawnScene`/`respawnMarkerName`【码 GameManager.cs:5229-5299，PlayerData.cs:3118-3128】。A、D 不会改这两个字段，所以回到最后一张坐过的工作台；我们的路线上是 S26 末尾的 Cradle 工作台【推，DESIGN §3.6.4】。这与社区 wiki "结局 1、3 之后在最后存档点重生"一致【攻，claims.txt 结局备注】。
- 只有 C 调用 `StartBlackThreadWorld()`（`blackThreadWorld = true`、`act3_wokeUp = false`）【码 GameManager.cs:2159-2163】。在 Continue 之前，存档槽显示 BlackThreadInfected 状态【码 SaveStats.cs:80，SaveSlotButton.cs:808】。

### 1.3 Ending 1 之后会写入哪些东西

`CompletedEndings`/`LastCompletedEnding` = Act2Regular；可能还有 `UnlockSilkFinalCutscene` = true（`Death Sequence` 的 `To Bind 2` 状态写它，这个状态是否在 A 的路径上未逐状态核对；全部场景包里只有这一处引用它，用途未查）；Steam 成就 `ENDING_A`（在 `End_Credits` 开始时发放），满足条件时还有 `STEEL_SOUL`、`SPEEDRUN_1`；菜单样式 `ENDING_A` 和 `COMPLETED_STEEL`【码 GameManager.cs:3007】；第一次在 Steel Soul 下通关时，`Steel Soul Unlock` 序列会写 `RecPermadeathMode = 1`【码 SteelSoulUnlockSequence.cs】（最终副本已经是 1，DESIGN §2.7）；最后存档，并把会话计时并入 `playTime`。**没有写入任何"已通关"之类的锁定标志。**

---

## 2. Ending 1 会不会挡住 Act 3 和 100 %（问题 2）

### 2.1 GMS 可以重打【包】

- `Cradle_03` 的 `Boss Scene` 在场景包里是激活的，挂在它上面的只有 `Soul_Snare` 的 `TestGameObjectActivator`，没有任何按结局或"已击败"控制 boss 战的组件【包 `scene_cradle_03.txt`】。
- `Intro Sequence` FSM `First Challenge` 和 `Silk Boss` FSM `Control` 的 `Init` 都读 `encounteredSilk`，用来在重打时快速开场【包 `find_str.py encounteredSilk`】。结局 A 的路径不写任何"已击败 GMS"的标志【包 `fsm_cradle03_death.txt`】。
- 结论：Ending 1 之后回到 Cradle 工作台，可以随时再打 GMS【推，未实测】。

### 2.2 Snared Silk（C）的条件【包】

- `Death Sequence` 的 `Init` 读 `soulSnareReady`；最后一次 Bind 前的 `Soul Snare?` / `Bind Or Needolin` 状态分出 `BIND` → A 和 `NEEDOLIN` → C 两条路【包】。所以 Ending 1 用过 Bind 不影响以后选 Needolin。**DESIGN 1.2 现在规定"GMS 场景中硬禁 Needolin"，第二次打 GMS 必须解除这条禁令。**
- `soulSnareReady` 来自许愿 **Silk and Soul**（任务 `Soul Snare Pre` → `Soul Snare`）。`Soul Snare` 的目标是 3 个 Snare Soul（Churchkeeper、Bell Hermit、Swamp Bug）加 Silk Snare 工具【包 `quest_dump.py`】。
- **`Soul Snare Pre` 出现前要满足 `QuestCompleteTotalGroup "Soul Snare"`**【包】【码 QuestCompleteTotalGroup.cs `IsFulfilled`】：
  - 10 个必做许愿（`IsRequired`）：Brolly Get、Building Materials、Building Materials (Bridge)、Crow Feathers、Songclave Donation 1、Songclave Donation 2、Belltown House Start、Belltown House Mid、Shakra Final Quest、Save Sherma；
  - 另外 28 个可选许愿的分值合计 ≥ **17**（多数 1 分，五个送货任务各 0.5 分），包括 Mossberry Collection 1、Building Materials (Statue)、Shell Flowers、Rock Rollers、Save Courier Short/Tall、A Pinsmiths Tools、Skull King、Fine Pins、Roach Killing、Great Gourmand、Extractor Blue、Journal、Shiny Bell Goomba、Beastfly Hunt、Huntress Quest、Pilgrim Rags、Save City Merchant (+Bridge)、Song Knight、Song Pilgrim Cloaks、Broodmother Hunt 和送货任务；
  - 附加条件：`CaravanTroupeLocation` == 3（跳蚤商队在 Aqueduct，即 Fleatopia）、`hasDoubleJump`（Faydown Cloak）、`defeatedLaceTower`（Lace 2）、`BelltownGreeterHouseFullDlg`。
- 所以在 5 h 内直接打出 C 来同时拿四个成就里的前两个不现实，先打 A 是唯一合理的顺序【推 + 估】。

### 2.3 一个存档里结局能出现的顺序

- Act 2 时 A 可以反复打。D 需要被锁在 Cursed Crest 里（`Silk Boss` FSM `Phase Control` 的 `Death Type` 状态引用 Cursed 纹章【包】），之后找 Doctor 换成 Witch 纹章就回到 A/C 的分支【包 `belltown_room_doctor` `Crest Change`；推】。
- C 一旦触发就进入 Act 3：`StartAct3` 把重生点放到 `Song_Tower_Destroyed`【码 GameManager.cs:2165-2254】，Cradle 有毁坏版本的场景包（`cradle_03_destroyed` 等）【包】，GMS 应当不能再打，Act 3 里能触发的结局只有 E【推】。
- 所以可能的顺序是：**{A, D}（任意次数、任意顺序）→ C → E**。四个可得的结局（A、C、D、E）都能在同一个存档里出现【推】。
- `Abyss_Cocoon` 的 `Boss Control` FSM 只用 `EncounteredLostLace` 决定是否跳过开场，我没找到"已击败 Lost Lace"之类的锁定，所以 E 大概也能重打【推，未实测】。有了这一点，即使第一次 E 时还没到 100 %，也有补救机会，但计划上应当在第一次 E 之前收齐。

### 2.4 进入 Act 3 时被改写的东西（对 bot 有影响）【码 GameManager.cs:2165-2254】

- 自动换回 Hunter 纹章（`AutoEquip`，`removeTools: true`），清空额外工具槽，技能槽换回默认 Silk Spear。bot 的装备逻辑要在 Act 3 开场后重新装备。
- 强制写入 `defeatedTrobbio`、`spinnerDefeated`、`defeatedSongGolem` 等若干世界标志；把 Pilgrim Rags、Skull King、Roach Killing、Rock Rollers 四个**未完成**的许愿重置（`RemoveIncompleteActiveQuest`）。
- 为 Act 1–2 商店关门准备了后备：Grindle（`Coral_42` 的 `Thief NPC Shop`）在 `blackThreadWorld` 下出售 Bonebottom 和 Pilgrim's Rest 的面具碎片、工具袋、纹章槽、钥匙、工艺金属，并与原商品共用购买标志【包 `shops_compact.txt`、`scan_grindle.txt`】；Tack 在 Act 3 的 `Dust_Shack`（Black Thread World）另有一份拾取【包】。我没有逐项核对这些重置会不会让某个 100 % 物品错过，按现有数据看都有后备【推】。

---

## 3. 成就检查本身（问题 3）

### 3.1 代码【码 GameManager.cs:2999-3025】

```csharp
CountGameCompletion();
bool flag  = playerData.permadeathMode > PermadeathModes.Off;   // Steel Soul（On 或 Dead）
bool flag2 = playerData.completionPercentage >= 100f;
if (flag)  { AwardAchievement("STEEL_SOUL"); MenuStyleUnlock.Unlock("COMPLETED_STEEL", false); }
if (flag2) { AwardAchievement("COMPLETION"); if (flag) AwardAchievement("STEEL_SOUL_FULL"); }
if (playerData.playTime <= 18000f) AwardAchievement("SPEEDRUN_1");
if (flag2 && playerData.playTime <= 108000f) AwardAchievement("SPEED_COMPLETION");
```

| 成就 | 条件 | 备注 |
|---|---|---|
| `STEEL_SOUL` | `permadeathMode` > Off | 与时间、完成度、结局都无关 |
| `SPEEDRUN_1` | `playTime` ≤ 18000 s | 与模式无关，含等号 |
| `COMPLETION` | `completionPercentage` ≥ 100 | 与模式无关 |
| `STEEL_SOUL_FULL` | 100 % **且** Steel Soul | |
| `SPEED_COMPLETION` | 100 % **且** `playTime` ≤ 108000 s | 与模式无关，含等号 |

### 3.2 什么时候运行【包 end_game_completion】【码】

- C# 里没有任何地方调用它；唯一的调用者是 `End_Game_Completion` 场景里两个 `Award Achievements` 对象上的 FSM `Award`：`Pause` 状态 `Wait` **5.75 s**（`realTime` = false）→ `Done` 状态 `CallMethodProper GameManager.CheckCompletionAchievements`【包 `scan_endings.txt`、`raw_state.py`】。
- 这两个对象分别在序列 `Game Completion Act 2`（条件 `HasWhiteFlower` == false）和 `Game Completion Act 3`（条件 `HasWhiteFlower` == true）下面。`Sequence` 上的 `ChainSequence` 依次播放 `End Credits Thank`（条件：非 Black Thread 世界，或 Black Thread 世界且有 Everbloom）、Act 2 或 Act 3 完成度画面（两者必有其一）、`Steel Soul Unlock`（只在 `RecPermadeathMode` == 0 时）【包】【码 ChainSequence.cs、SteelSoulUnlockSequence.cs】。
- 所以 **A、C、D、E 每一次片尾都会运行一次检查，不只是第一次**；没有任何"已发过就跳过"的判断。
- 完成度画面上的数字就是这次检查用的数字：`GameCompletionScreen.Start` 调用 `CountGameCompletion` 并显示 `playerData.completionPercentage` 和 `playerData.playTime`【码 GameCompletionScreen.cs:12-20】，存档槽上的百分比也是同一字段【码 SaveStats.cs:78】。
- 结局成就另有出处：`ENDING_A/C/D` 在 boss 的 Death Sequence 里排队，`End_Credits` 场景的 `Award Achievements` FSM 在下一帧调用 `AwardQueuedAchievements`；C 的视频设置了 `fireQueuedAchievements`，视频结束 1 s 后就会发放；`ReturnToMainMenu` 也会兜底调用一次【包】【码 CinematicPlayer.cs:701-705，GameManager.cs:5344】。

### 3.3 已经拿到的成就会怎样【码 AchievementHandler.cs:84-94，SteamOnlineSubsystem.cs:181-221】

`AwardAchievementToPlayer` 要求：不是 Demo、键在成就列表里、`CanAwardAchievement`（只对 GODS_GLORY 地图区有白名单）、并且 **`CheatManager.AlwaysAwardAchievement` 为真或 Steam 报告尚未解锁**。满足后才调用 `SteamUserStats.SetAchievement` + `StoreStats`（Player.log 记 "Pushing achievement X"，回调记 "Steam achievement X (a/b) upload complete"）。所以：

- 已解锁的成就什么也不做，**不会再弹窗**，也不会出错；
- 账号上的成就状态与存档无关，换存档、换副本都不会重置；
- 成就列表里没有 `ENDING_B`，这也说明 B 是废弃内容【包 achievementslist】。

### 3.4 检查用的是"最后一次存档时"的 playTime【码】

`playerData.playTime` 只在存档时更新：`PreparePlayerDataForSave` / `GetSaveGameData` 执行 `playTime += sessionPlayTimer` 再清零会话计时【码 GameManager.cs:4474-4490，4242-4245】；会话计时每帧在 PLAYING/ENTERING_LEVEL/EXITING_LEVEL 状态下累加【码 GameManager.cs:541，4223-4229】。结局 A 的 Death Sequence 和整条过场链里都没有存档【包，三个 FSM 都没有 Save 类动作】，所以完成度画面上检查的值，是**最后一次坐椅子或 FSM 存档时的时间**，不含之后走到 GMS 和打 GMS 的时间。DESIGN §1.2、§1.3 已经写了这一点，这里从结局链这一侧再确认一次。两条后果：

- 5 h 和 30 h 两个门槛实际上都比实时略宽松一点，用实时做预算是保守的；
- 回到菜单时的存档会把这段时间并进去，所以存档槽上的时间可能比检查时多，不能用槽位时间判断成败（DESIGN §3.6.1 已规定以 Player.log 和 Steam 为准）。

### 3.5 不能在 5.75 s 内跳过完成度画面【码 ChainSequence.cs，AnimatorSequence.cs】【推】

- 完成度序列 `canSkip` = 0，要等动画事件调用 `AllowSkip` 才能跳；`waitForSkip` = 1，播完后要按一次键才进入下一段【包】。
- 如果 `AllowSkip` 早于 5.75 s，而 bot 立刻按键，会切到 `Act 2 End` 动画；这段动画放完后，`ChainSequence.Next()` 会把整个序列（包括 `Award Achievements`）关掉。若此时 `Wait` 还没走完，**这一次就不会运行检查**，后面的 `ReturnToMainMenu` 只会补发排队中的 `ENDING_A`。动画时长在另一个资产包里，我没有查到【未核实】。
- 处理办法：完成度画面出现后至少等 8 s，或者等到 Player.log 出现 `STEEL_SOUL` 的 upload complete，再按键。放进 ENDING 状态机作为硬规则。

### 3.6 Steam 弹窗与录像（用户关心的"带 Steam 跳成就的视频"）

- 在 Steam 上，弹窗由 Steam 叠加层显示：`SetAchievement` + `StoreStats` 后由客户端弹出【码 SteamOnlineSubsystem.cs:181-198】。游戏自带的弹窗（`AchievementPopupHandler`）只在平台没有原生弹窗时启用，Steam 上不会显示【码 AchievementPopupHandler.cs:37-40】。
- 弹窗出现的时间：`ENDING_A` 在 `End_Credits` 开头；`STEEL_SOUL` 和 `SPEEDRUN_1` 在完成度画面出现 5.75 s 后（代码里先 STEEL_SOUL 后 SPEEDRUN_1）。100 % 那一次是 `ENDING_E` 先在 `Cinematic_Ending_E` 里弹出，再在完成度画面上依次弹 `COMPLETION`、`STEEL_SOUL_FULL`、`SPEED_COMPLETION`。这些都在非游戏画面上，不会干扰 bot 操作。
- 与现有设计的冲突：DESIGN §2.6 规定"原生成就弹窗和 Steam 叠加层全部关闭"，因为叠加层画在游戏帧里，会被视觉管线看到。建议：**只在最后一章打开叠加层**。最后一章从 Cradle 工作台开始（GMS → 片尾），开打前本来就要重启 Steam 和游戏（DESIGN §3.6.1），叠加层设置只在游戏启动时生效，正好跟着这次重启改。GMS 战斗中不会有成就弹出，第一个弹窗就是 `ENDING_A`。100 % 部分同样处理：最后一章从 Lost Lace 前的工作台开始。录屏软件要录到叠加层（例如 OBS 游戏捕获要勾选"捕获第三方叠加层"）【攻】。
- 账号上已经有的成就不会再弹：`FIRST_TOOL` 已在 M0 探针 P5 中于最终副本上解锁（DESIGN M0 探针表）。训练副本没有 Steam 子系统并开着 AchievementGuard（DESIGN §1.4、§2.3），不应解锁成就。正式录制前请在 Steam 个人资料页确认这四个成就和 `ENDING_A/C/E` 都还没解锁。重置成就是账号层面的操作，由你决定，我不会去做。

---

## 4. 100 % 清单（问题 4）

### 4.1 公式【码 PlayerData.cs:3830-3873】【包 dataassetsmasterlists、toolitems、crestitems】

`completionPercentage` 是各项计数之和，每项算 1 %，满分正好 100，**没有余量，100 % 就是全收集**：

| 项 | 代码 | 最大值 | 数据依据 |
|---|---|---|---|
| 工具 + 丝技 | `ToolItemManager.GetCount(GetUnlockedTools())`：主列表中已解锁、未隐藏、`isCounted` 的工具，按 `countKey` 去重 | **57**（工具 51 + 丝技 6） | `Master Tool List` 65 项；不计数：Silk Snare、Extractor；同键合并：Curve Claws Upgraded→Curve Claws、Dazzle Bind Upgraded→Dazzle Bind、Mosscreep Tool 2→Mosscreep Tool 1、Shell Satchel→Dead Mans Purse、WebShot Forge/Architect/Weaver→一个键。资产包里另有 Dustpilo、Ladybug Straight Pin 两个工具，不在主列表，不计数 |
| 纹章 | `GetUnlockedCrestsCount() - 1`：未隐藏且是基础版本的已解锁纹章，减去 Hunter | **6** | `Master Crest List` 11 项；隐藏：Cursed、Cloakless；非基础版：Hunter_v2、Hunter_v3；计数的是 Reaper、Wanderer、Warrior（Beast）、Witch、Toolmaster（Architect）、Spell（Shaman） |
| 针升级 | `nailUpgrades` | 4 | Plinney（`Belltown_Room_Pinsmith` 的 `Upgrade` 状态）【包】；上限 4【攻】 |
| 工艺包 | `ToolKitUpgrades` | 4 | Forge 180、Architect 450、Grindle 700 三家商店，加许愿 Crow Feathers【包】 |
| 工具袋 | `ToolPouchUpgrades` | 4 | Pilgrim's Rest 220、Belltown 250、许愿 Journal（看过 100 条图鉴）、`Bone_12` 的 `Black Thread World/Ladybugs_Act_3` 制作拾取；Grindle 220 与 Pilgrim's Rest 共用购买标志，只是后备【包】 |
| 丝心 | `silkRegenMax` | 3 | 三个记忆场景 `Memory_Silk_Heart_BellBeast/LaceTower/WardBoss`【包】 |
| 能力 | `hasNeedolin`、`hasDash`、`hasWalljump`、`hasHarpoonDash`、`hasSuperJump` | 5 | Needolin、Swift Step、Cling Grip、Clawline、Silk Soar。**Drifter's Cloak（`hasBrolly`）和 Faydown Cloak（`hasDoubleJump`）不计数** |
| 面具 | `maxHealthBase - 5` | 5 | 20 片碎片 = 14 个场景拾取 + 2 家商店（Bonebottom 300 / Grindle 后备、City Merchant 750）+ 4 个许愿（Beastfly Hunt、Sprintmaster Race、Ant Trapper、Destroy Thread Cores），数量正好对上【包】 |
| 丝轴 | `silkMax - 9` | 9 | 18 段 = 13 个场景拾取 + 3 家商店（Belltown 270、City Merchant 500、Grindle 680）= 16，**还有 2 段的来源我没找到**【未核实】 |
| 其他 | `hasChargeSlash`、`HasBoundCrestUpgrader`、`HasWhiteFlower` | 3 | Needle Strike、Sylphsong（Eva）、Everbloom |
| **合计** | | **100** | 57 + 6 + 4 + 4 + 4 + 3 + 5 + 5 + 9 + 3 |

关于"工具被交出去会不会掉百分比"：被锁定（隐藏）的工具不计数。会锁定工具的只有对话交易（`DialogueYesNoBox`）、`getReplaces` 升级和 `SetToolLocked` 动作【码 DialogueYesNoBox.cs:314-322，ToolItem.cs:554，SetToolLocked.cs】。用到 `SetToolLocked` 的只有 Mottled Ant Child（Curve Claws）和 Moss Creep（Mosscreep 1→2），都是同键替换，不会掉百分比【包 `scan_settoollocked.txt`】。

### 4.2 计数的工具（按内部名，57 个键）【包】

- 丝技 6：Silk Spear、Thread Sphere、Parry（Cross Stitch，`Organ_01` Phantom）、Silk Charge、Silk Bomb（`Slab_10b` First Sinner）、Silk Boss Needle（Pale Nails）。
- 红 18：Straight Pin、Tri Pin、Sting Shard、Tack、Harpoon、Curve Claws、Shakra Ring、Pimpilo、Conch Drill、WebShot（三选一）、Screw Attack、Cogwork Saw、Cogwork Flier、Rosary Cannon、Lightning Rod、Flintstone、Flea Brew、Lifeblood Syringe。
- 蓝 21：Mosscreep、Lava Charm、Bell Bind、Poison Pouch、Fractured Mask、Multibind、White Ring、Brolly Spike、Quickbind、Spool Extender、Reserve Bind、Dazzle Bind、Revenge Crystal、Thief Claw、Zap Imbuement、Quick Sling、Maggot Charm、Longneedle、Wisp Lantern、Flea Charm、Pinstress Tool。
- 黄 12：Compass、Bone Necklace、Rosary Magnet、Weighted Anklet、Barbed Wire、Dead Mans Purse（Steel Soul 下是 Shell Satchel，同键）、Magnetite Dice、Scuttlebrace、Wallcling、Musician Charm、Sprintmaster、Thief Charm。

每个工具的来源（场景拾取、商店、许愿、NPC）见 `summ2_tools.txt`、`shops_compact.txt`、`quest_rewards.txt`。

### 4.3 必须进 Act 3 才能拿的部分

| 物品 | 占 % | 依据 |
|---|---|---|
| Everbloom（`White Flower`） | 1 | 只在 `Memory_Red` 的 `Wake Up` FSM 里给出【包】；主线 `Black Thread Pt6 Flower` 是 Act 3 主线的最后一步，前一步 `Pt5 Heart` 要 Coral / Flower / Ant 三颗心（另有 Clover Heart 作为替代目标）【包】，对应 Act 3 的 Coral King / Flower Queen / Hunter Queen / Green Prince（成就键 `DEFEATED_*`）【包 + 攻】 |
| Pale Nails（`Silk Boss Needle`） | 1 | 只在 `Cradle_03_Destroyed` 的 `Silk Needle Spell Get` FSM 里给出（毁坏的 Cradle 只在 Act 3 存在）【包】 |
| Magnetite Dice | 1 | 唯一来源是 Grindle 商店的 `Grindle Lucky Dice Tool`（300），条件是 `blackThreadWorld` == 1；场景里引用它的只有掉钱和铃铛掉落的判定（检查是否装备）【包】。**这推翻了 claims 里"可考虑在 Act 1–2 带 Magnetite Dice"的建议** |
| 第 4 个工具袋 | 1 | 四个来源中的 `Bone_12` `Ladybugs_Act_3` 在 Black Thread World 下【包】 |
| 第 5 个面具（第 20 片碎片） | 1 | 许愿 `Destroy Thread Cores` 需要先完成 `Black Thread Pt1 Shamans`【包】；20 片碎片一片不能少 |
| Shaman 纹章（`Spell`） | 1 | 在 `Tut_04` 的 Snail Shamans 处取得（`States/Intro Scene/Snail Shamans Set`，`CompletedRedMemory` 之后换成 Outro），与 Act 3 主线 `Black Thread Pt1 Shamans` 相连【包 + 推】 |
| 其余（第 4 次针升级、Sylphsong、未找到的 2 段丝轴、部分场景碎片） | ? | 【未核实】 |

所以至少有 6 个百分点必须在 Act 3 拿，还可能更多。

### 4.4 Steel Soul 下的差异

- `Crawl_01` 的 `Tool Conditions`：普通模式给 Dead Mans Purse，Steel Soul 给 Shell Satchel，两者同键，计数不变【包】。
- `Dust_11` 的 `Steel Soul States`（Regular / Steel Soul 两个分支，按 `permadeathMode` 切换）、`Coral_37` 的 `Room_States`（Normal 分支是丝虫茧，Steel 分支是 Jinn 房间的美术）是两处场景差异，我没看到它们影响计数物品【包，未逐项核实】。
- 代码里 Steel Soul 把送货任务 Dustpens Slave 当作已完成（`SlaveDeliveryQuestCompleted`）【码 PlayerData.cs:3043-3053】。这是 PlayerData 属性，`Soul Snare` 组用的是任务完成数据，两者是否相关未查。

### 4.5 与 Ending 1 路线的规模对比【估】

- **Ending 1 路线大约拿到 20–25 %**：约 6 个工具、1 个丝技、0–1 个纹章、针 2、工艺包 1、工具袋 1、丝心 2、能力 4（Silk Soar 不在路线上）、约 8 片碎片（2 个面具）、少量丝轴碎片【估，按 DESIGN §3.6.4 路线表】。
- **还要补 75–80 个百分点**：约 45 个工具和丝技、5 个纹章、约 12 片面具碎片、约 15 段丝轴、2 次针升级、3 个工艺包、3 个工具袋、1 个丝心，以及 Everbloom 和 Sylphsong。
- **Ending 1 之后新增的强制战斗**：第二次 GMS（C）；Phantom（Cross Stitch）、First Sinner（Rune Rage）【包】；`Ward_02` 的 boss（第三个丝心）、`Coral_29` 的 boss（Zap Imbuement）、`Belltown_08` 的 boss（Wisp Lantern）、`Arborium_07` 和 `Weave_03` 的连战（Lightning Rod、White Ring）、`Coral_Tower_01`（Conch Drill）【包，boss 名未逐一对照】；Silk and Soul 前置里的许愿战斗（Skull King、Broodmother Hunt、Beastfly Hunt、Great Gourmand、Song Knight 等，可按难度选 17 分）【包 + 攻】；Act 3 的三到四个心脏 boss 和 Lost Lace【包 + 攻】。原路线有 10 个 A 类段，Ending 1 之后大约还要 20–30 场 boss 或连战，其中有全游戏最难的几场【估】。
- **时间**：按原路线约 3.5 h 拿 20–25 % 的节奏，再加上 Act 3 和许愿任务的往返，100 % + Ending E 大约 15–25 h 游戏时间【估】。30 h 的上限够用，但对谨慎打法来说余量不算大；真正卡住的是不死，而不是时间。

---

## 5. 结论与风险（问题 5）

### 5.1 结论

**"5 h 内打完 Ending 1，然后继续同一存档到 100 %，30 h 内打出更晚的结局，全程不死"在代码和数据上完全可行。** 它不是"同一次片尾拿四个"，而是两次：

| 时点 | 片尾 | 新弹出的成就（账号上尚未拥有时） |
|---|---|---|
| ① 约 3.5–4.5 h | Ending A | `ENDING_A`（片尾开头），`STEEL_SOUL`、`SPEEDRUN_1`（完成度画面 +5.75 s） |
| （中途） | Ending C（第二次 GMS，Needolin） | `ENDING_C`；检查照常运行，不会有新的完成成就 |
| ② ≤ 30 h，已 100 % | Ending E（Lost Lace） | `ENDING_E`，`COMPLETION`、`STEEL_SOUL_FULL`、`SPEED_COMPLETION`（完成度画面 +5.75 s） |

另外，进入 Act 3 后所有收集类和 boss 类成就也会陆续在游戏中弹出（如果叠加层打开）。

### 5.2 风险

1. **Ending 1 之后死亡**：Steel Soul 存档变成 Defeated，不能继续，这个存档的 `STEEL_SOUL_FULL` 和 `SPEED_COMPLETION` 没了（`COMPLETION` 可以在任何普通存档里另拿）。`STEEL_SOUL` 和 `SPEEDRUN_1` 已在 Steam 上，不受影响。恢复备份或改 `permadeathMode` 技术上能绕过（claims [ach6]），但那就不是"一次不死"的录像了，由你决定。
2. **战斗量**：见 §4.5。Ending 1 之后的 A 类遭遇大约是原路线的两到三倍，而且更难。粗略地说，如果 bot 每场 A 类遭遇的死亡率是 1–3 %，再打 25 场就有约 22–53 % 的机会失败【估】。这是整个计划的主要风险，应当分开评估：先保证 ①，② 视 bot 的实力再决定是否当作同一个录像目标。
3. **两次打 GMS**：A 必须在 C 之前（§2.2），所以 GMS 一定要打两次；第二次要用 Needolin 收尾，必须修改 DESIGN 1.2 里"GMS 场景硬禁 Needolin"的规则。
4. **完成度画面不能抢按键**（§3.5），否则这一次片尾的检查会丢失。
5. **Steam 必须在线并初始化**：否则不会推送成就，存档还会落到 `default` 目录（DESIGN §3.6.1 的预检已覆盖）。100 % 部分的最后一章也要做同样的预检。
6. **弹窗前提**（§3.6）：账号上尚未拥有、叠加层只在最后一章打开、录屏要能录到叠加层。
7. **Act 3 开场会重置装备**，bot 要重新装纹章和工具（§2.4）。
8. **Silk and Soul 前置很重**：10 个必做许愿、17 分可选许愿，加上 Faydown Cloak、Fleatopia 商队和 Belltown 房子对话（§2.2），这些都要纳入 Ending 1 之后的路线规划。
9. **数据缺口**：2 段丝轴的来源没找到；第 4 次针升级、Sylphsong 和部分场景碎片的取得时机【未核实】。100 % 路线需要一张经过验证的完整清单，否则可能在最后才发现差 1 %。
10. **版本**：Sea of Sorrow 资料片可能增加物品，改变 100 % 的分母（claims [ach10]），所以必须锁定在 1.0.30000。

### 5.3 待实测

- 完成度画面上 `AllowSkip` 和 5.75 s 的先后（§3.5）。
- Ending A 后 Continue 的位置，以及 GMS 能否立刻重打（§1.2、§2.1）。
- Ending E 之后能否重打 Lost Lace（§2.3）。
- §4.3 最后一行和 §4.1 里丝轴缺口的来源与时机。

### 5.4 对 claims.txt 的修正

- 关于 Magnetite Dice：1.0.30000 里它只在 Act 3 由 Grindle 出售（§4.3），Ending 1 路线拿不到，应从"最低防御配置"里删掉。
- 结局备注里"结局 1、3 之后在最后存档点重生"与代码一致（§1.2）。补充：Snared Silk（C）之后不是回到最后存档点，而是进入 Act 3 开场（`StartAct3`）。
