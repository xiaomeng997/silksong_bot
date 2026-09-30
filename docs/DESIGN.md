# Silksong 钢铁之魂 + 速通 Bot 设计文档

**标签约定**

| 标签 | 含义 |
|---|---|
| `[xxxN]` | [`research/claims.txt`](research/claims.txt) 中的结论编号（详细内容和来源 URL 见 [`research/research.json`](research/research.json)） |
| `[VER]` | [`research/claims.txt`](research/claims.txt) 的 VERIFICATION 段。两处冲突时以它为准 |
| `[dec]` | 来自发布版 1.0.28324 反编译，需在 M0 用 1.0.30000 复核。本次定稿时在本地反编译中抽查确认了以下几处：`PauseGameToggle` 的 `TimeSlowed`/`GenericMessageCanvas` 分支、`PauseAllowed` 与两处 `WaitForSecondsRealtime(0.3f)`、`MenuButtonSaveQuitListCondition` 中的 `disableSaveQuit`、`HeroController.CriticalDamage`、`CogMultiHitter`。M0 已核对的条目改标 `[m0:…]`，未核对的见 m0 §2.8 |
| `[m0:C#]` / `[m0:N#]` | [`facts/1.0.30000/m0.md`](facts/1.0.30000/m0.md) §1.1（C1–C18，设计说法已变化）/ §1.2（N1–N43，新发现）的条目，基于 1.0.30000 反编译，带"文件:行号"证据。引用该文件其他部分时写 "m0 §x" |
| `[probe:Pn]` | [`facts/1.0.30000/probes.md`](facts/1.0.30000/probes.md) 中探针 Pn 的运行时实测；HeroController 常量全表见同目录 `hero_constants.json` |
| `[local:…]` | 调研时下载的 wiki 页面摘录（未收入仓库；对应页面见 hollowknight.wiki） |
| `[SW]` | Switch 可行性检查，见 [`research/switch.json`](research/switch.json) |
| `[待验证 Pn]` | 待验证项，编号对应 §5 的探针 |

本次定稿没有做新的网络调研，只查阅了本地已有的反编译和 wiki 摘录。2026-09-29 按 M0 的代码核对（m0.md）和运行时探针（probes.md）修订，与二者冲突的旧说法已替换。

---

## 0. 一页摘要

- **目标。** 用一个 Steel Soul 存档打出 Weaver Queen（结局 1），存档中的 `playTime` ≤ 18000 s，这样 STEEL_SOUL 和 SPEEDRUN_1 会同时解锁 [ach1][com15][VER]。优先级依次为：活下来、通关、时间。
- **一局怎么打。**
  - 走 Bell 路线（经 Last Judge），不进 Mist。
  - 安全绕路：Fractured Mask、Weighted Belt、Warding/Magma Bell、第 7 个面具、2–3 个 Memory Locket。
  - 每个 A/B 类单元开打前，先在工作台补满状态（交战门）。
  - 唯一的撤销手段是"暂停 → 退出到菜单 → 读档"，而且必须在致命一击之前触发：Dead 在致命那一帧就写进内存，下一帧开始保存 [m0:N7]。
- **时间先验。** 按当前先验，全程期望约 16,100 s（含恢复开销），P(≤17,400 s) 约 0.8。Act 1 实测后在检查点 K3 决定打一局还是两局（D4'）。
- **架构一句话。** 训练时由 BepInEx 插件 `SsOracle` 提供精确状态、标签和裁判。正式运行时游戏是原版，只读屏幕像素（WGC），生成视觉 `WorldState`，交给同一套规则、规划器、安全过滤器和监督器，再通过 `SendInput` 按键。`FrameSource`/`ControllerSink` 是可插拔插件，Switch 版只需换成 UVC 采集卡 + RP2040。
- **感知原则："能查的就不看"。** 地形、危险物、门、敌人行为表离线导出到 Knowledge DB。视觉只负责：场景和相机位姿、动态物体的检测与跟踪、HUD/UI、A 类 boss 与竞技场敌人的动作阶段。
- **安全核心。**
  - 按行为的"支撑集"（可能发生的所有情况）推理，而不是按概率。
  - `hits_to_death` 计入挂起伤害（DamageTag、霜冻）和面具失效的例外；危险物和 DoSpecialDamage 类伤害穿透 i-frame。
  - 暂停键无条件按/放循环，看到暂停的最早线索（暗幕开始变暗）就停手：0.3 s 锁定一过，再按 Esc 就会解除暂停 [m0:C11]。
  - 退出是否可用（`disableSaveQuit`、预加载；预加载一旦启动，本房间内 Quit 一直灰）单独建成 quit map。退出序列：Esc → 选中"退出至菜单" → Submit → 确认框默认"否" → 上 → Submit，每次 Submit 前读高亮项 [probe:P7]。
  - 解除暂停前必须通过冻结态检查。
  - 焦点丢失 = 英雄失控：原版失焦后世界和计时照常运行，键盘却被断开 [probe:P6]，所以焦点守护是必需的。
- **评估。** 按单元做序贯贝叶斯门槛：G0 训练、G1 影子、G2 分段预演、G3 全程预演，配合前兆（near-miss）故障树模型。发射条件：P10(P_run) ≥ 0.7。
- **最大风险。**
  1. 纯视觉在 Forum 杂乱画面、暗房、闪光帧上的长尾错误。诚实估计，F1 达到发射门槛的概率约 30–50%。
  2. Forum、Dancers、Lace 2、Last Judge 的死亡率压不到约 1%。
  3. 某些窗口里暂停或退出不可用。
  4. 时间预算紧。
  5. 单人工作量：原始约 63 FTE 周，加 1.5× 余量约 95 FTE 周。
- **回退阶梯。** 触发条件事先约定，到时由你拍板：工作台存档恢复（D3）、外部只读内存（F2）、进程内观察插件（F3）、两局（D4'）。
- **前三个里程碑。**
  1. M0：探针、锁版、隔离，2 周。
  2. M1：基于 SilksongRL + DebugMod 的精简 Oracle，4 周。
  3. M2：Oracle 实时战斗 spike（Bell Beast + Forum），6 周，结束于检查点 K1。

  之后是 M3 视觉 spike（覆盖 Forum、Lace 2、一个暗房），结束于 K2。中途有两个可交付物：OR1 = oracle 驱动的全流程通关 bot，OR2 = 纯视觉 Act 1 演示。

---

## 1. 目标与硬性事实

### 1.1 目标与优先级

- **目标。** 一个 Steel Soul 存档以 Weaver Queen（ENDING_A）结束，存档 `playerData.playTime ≤ 18000 s` [ach1][com15][VER]。
- **优先级。** 生存 > 通关 > 时间。调速器永远不会为了省时间降低安全阈值。
- **兜底（D4）。** 如果中途判断速通已不可能，继续为钢铁之魂打完，速通以后在 Classic 局单独拿。

### 1.2 成就与结局规则

| 事实 | 来源 | 设计后果 |
|---|---|---|
| STEEL_SOUL 要求 `CheckCompletionAchievements` 被调用时 `permadeathMode > Off`（Dead 也满足，但 Dead 存档到不了结局）。SPEEDRUN_1 要求 `playTime ≤ 18000f`（含等号），与模式和完成度无关。检查读的是最后一次 flush 的 `playerData.playTime`，不含未保存的 session 时间，也不 flush 计时。这个方法没有 C# 调用者，由序列化 FSM 按名调用，它与 Bind、保存的先后关系待 P13。 | [ach1][VER][m0 §2.1][m0:N29] | 一局可同时拿两个。按实时时间做预算是保守的。 |
| `AwardAchievementToPlayer` 只检查四项：非 DemoMode、键在列表中、`CanAwardAchievement`、尚未解锁。没有 mod 检测。 | [VER][mod14] | 训练用 BepInEx 不会危及账号，但必须隔离，防止训练中误解锁（§2.7）。 |
| Weaver Queen 的条件：① 存档没有 Snared Silk；② 击败 GMS 后按 **Bind**（不是 Needolin）；③ 没有被锁定在 Cursed Crest。有人类通关实例确认可以同时拿到两个成就。 | [VER] | GMS 场景中硬禁 Needolin；永不启动 Rite of Rebirth。 |
| 在 Extras 菜单输入 上下上下左右左右 可解锁 Steel Soul，不需要先通关一次。代码经 `PermadeathUnlock.Unlock` 把 `RecPermadeathMode` 写进 `<saveDir>/shared.dat`，所以 `<AccountID>/shared.dat` 和 `default/shared.dat` 各自独立。按错一键就清空缓冲；只在 `RecPermadeathMode == 0` 时生效。未解锁时选空槽不会出现模式菜单，而是直接静默开始 Classic。 | [ach4][m0:N32][m0:N30] | 训练用的 AchievementGuard 对 `RecPermadeathMode` 放行。P5 已在最终副本上按过一次 8 键，`<AccountID>/shared.dat` 现为 `RecPermadeathMode=1` [probe:P5]。MenuDriver 在空槽按 Submit 之前先确认当前目录已解锁 Steel Soul；FINAL 中不再输入代码。 |
| Steel Soul 死亡：`Die` 在致命的 TakeDamage 同一次调用里设 `disablePause`，并把内存中的 `permadeathMode` 改为 Dead；下一帧 `PlayerDead` 调 `SaveGame`（后台线程序列化，几帧后落盘），Dead 同时写进版本备份 `user{N}_1.0.30000.dat`。槽位显示 DEFEATED。记忆场景（MapZone 为 MEMORY 或 CLOVER）中的死亡被强制为非致命，待逐场景运行时确认。 | [ach5][com13][m0:N7][m0:N5] | 安全动作必须在致命一击之前完成；反应式杀进程基本来不及（§3.7.7）。运行时确认之前，所有死亡都按致命处理。 |
| Pause → Quit to Menu → 读档不算死亡。hit-freeze 期间暂停被禁用；`Die()` 会立即设置 `disablePause`。自 1.0.29242 起，暂停或存档退出被禁时 ReturnToMainMenu 会拒绝执行。 | [com13][VER] | 预判式紧急退出是唯一的撤销手段。 |
| **暂停门控。** `InputHandler` 只在 `acceptingInput` 为真、GameState 为 PLAYING（解除暂停时为 PAUSED）、且 `Pause.WasPressed && PauseAllowed && !disablePause` 时切换暂停，是边沿触发；门关闭时按下的暂停键直接丢弃，不排队。EXITING_LEVEL、ENTERING_LEVEL（整个走入动画）、CUTSCENE、LOADING 期间都不能暂停。`PauseGameToggle` 在 `TimeSlowed`（任意 FreezeMoment：EnemyDeath ≈0.10 s、NailClash ≈0.36 s、BossStun ≈0.35 s、BindBreak ≈0.51 s；长时类型 BossDeathSlow 1.35 s、EnemyBattleEndSlow 1.85 s、RaceWinSlow 3.8 s）或 `GenericMessageCanvas` 显示时直接 `yield break`，暂停和解除暂停都被挡住，不给任何反馈。英雄自己的受击冻结用 Hero prefab 上的 `DAMAGE_FREEZE_DOWN/WAIT/UP`（0/0.1/0.1 s），不是 HeroDamage 预设；每次会产生后坐的非致命命中还同步设 `disablePause`，冻结结束才清。每次暂停或解除暂停后，`PauseAllowed` 有 0.3 s 实时为 false（60 fps 下 18 帧）。Esc 同时绑定 Pause 和 MenuCancel：锁定一过，暂停菜单里任何一次 Esc 都会解除暂停。 | [m0:N12][m0:N13][m0:C5][m0:N8][m0:C12][m0:C11][probe:P11] | 暂停键必须无条件按/放循环，并在真实暂停后约 230 ms 内停手；暂停和解除暂停后 0.3 s 实时内都不能再切换（§3.7）。 |
| **退出门控。** `PlayerData.disableSaveQuit` 为真或 `ScenePreloader.HasPendingOperations` 时，暂停菜单的 Save & Quit 变灰：仍然显示，但不可交互，上下导航会跳过它并回绕。按钮状态只在 `ShowMenu` 时算一次，暂停期间不刷新。PC 上预加载一旦启动，`HasPendingOperations` 就一直为真，直到目标场景的加载把它取走，所以本房间剩下的时间里 Quit 一直是灰的，暂停中也一样。退出确认的"是"在 `disablePause` 或 `disableSaveQuit` 时被静默拒绝，界面停在确认框，没有任何消息。`disableSaveQuit` 由 FSM/场景数据写入；C# 只在 `HeroRespawned` 和 `ResetCutsceneBools` 中清除它，换房间不清。 | [m0:C8][m0:N17][m0:C10][m0 §2.4] | 用 quit map 建模；视觉识别灰色的 Quit 按钮；永不按灰色控件；不按计数导航。 |
| 写存档时先写 `user{N}.dat.new`，再用 `File.Replace` 把旧文件轮换成 `user{N}.dat.bak{K}`（K 递增；已有 3 个及以上时删编号最小的，没有固定的 `.bak1`）。每次 SaveGame 还重写版本备份 `user{N}_1.0.30000.dat`。自动存档写 `Restore_Points{N}/restoreData{K}.dat`，约保留 20 个（ACT_1/2/3 为 `NODELrestoreData{K}.dat`，不参与裁剪），包含完整的 SaveGameData 和 playTime。恢复旧文件会同时回滚状态和 playTime；把 2 改回 1 不会回滚时间。存活的 Steel Soul 槽有 Restore Save 按钮；DEFEATED 槽只显示 Clear，两次 Submit 就会删除 `user{N}.dat` 和整个 `Restore_Points{N}`（不删 `.bak*` 和版本备份）。 | [VER][m0:C13][m0:N31] | 软件总是写备份，备份和 SlotGuard 工具匹配 `user{N}.dat.bak*`；死亡后只有 `.bak*` 和 `Restore_Points` 还是存活状态。恢复策略由 D3 决定；MenuDriver 永远不聚焦 Restore/Clear，永不在 DEFEATED 槽上按 Submit。 |
| 成就只在 `CheckCompletionAchievements` 被调用时推送一次；`CheckAllAchievements` 是空操作，事后不会补发。桌面端 `PushAchievementUnlock` 先调 Steam，然后**总是**把键写进 `<saveDir>/shared.dat`，所以 shared.dat 里的 true 不能证明 Steam 收到了。Steam 未初始化或已关闭时只记一行日志；初始化时 `SetAchievement` 不看返回值，照样记 "Pushing achievement X"，只有 "Steam achievement X (a/b) upload complete" 才表示送达。`steam_api64.dll` 存在但 `SteamAPI.Init()` 失败时，存档和 shared.dat 静默落到 `/default`。 | [m0:N26][m0:N27][m0:N28][m0 §2.1] | 最后一章前先重启 Steam，以 Player.log 确认在线（§3.6.1）；结局后两条 "upload complete" 都在、并在 Steam 上核对过，再碰存档。 |
| `EndingSequence` 使用 `SKIP_INSTANT`：CUTSCENE 中任何 legacy `Input.anyKeyDown`（键盘或鼠标）或手柄按键都会跳过；一次按键只跳过当前子序列（且仅当它 CanSkip），不会跳过整个结局。 | [m0 §2.1] | 进入 ENDING 状态后锁定输入，OS 级按键同样会触发跳过（§3.6.1）。 |
| 结局 1 之后，存档在最后保存点重生。结局和片尾场景（Cinematic_Ending_A..E、End_Credits、End_Game_Completion 等）都是 CUTSCENE，不计时。C# 中结局附近唯一的保存是片尾链结束后的 `ReturnToMainMenu(willSave:true)`，它会把检查之后在 GMS 场景里的时间也 flush 进去，所以槽位最终时间可能高于检查时的值，即使 SPEEDRUN_1 已触发也可能显示超过 5 h。End_Game_Completion 以 `Hh MMm SSs`（向下取整）显示 `playerData.playTime`；如果检查和这个画面之间没有保存（P13），它就是被检查值的秒级读数。 | [VER ev][m0:C18][m0:N25][m0 §2.1] | 片尾不计时。结局后以 Steam 为准核对成就，不用槽位时间判断成败。 |

### 1.3 计时器规则（速通时钟）

- **规则** [ach3][VER][m0 §2.3]：当且仅当 GameState ∈ {PLAYING, ENTERING_LEVEL, EXITING_LEVEL}、库存界面关闭、且该帧 `unscaledDeltaTime` < 1 s（严格小于；≥ 1 s 的帧整帧丢弃，不钳位）时，执行 `sessionPlayTimer += Time.unscaledDeltaTime`，保存时再 flush 进 `playerData.playTime`。
- **计时的情形：**
  - 房间切换全程：场景读取、激活、卸载、GC 都计时（P6 实测一次切换墙钟 8.51 s、PlayTime 8.52 s）[m0 §2.3][probe:P6]。
  - 引擎内的 FSM 过场/对话/boss 登场、hit-freeze（它用的是 unscaled 时间）。
  - 独立面板：商店、Bellway 目的地地图、Ventrica 管道地图、任务板、遗物/收藏板、是/否框（GameState 保持 PLAYING）[m0:N20]。
  - Bellway 的地图选择、上车和到站动画，以及进出视频场景的加载与卸载 [m0:N21]。
  - 从主菜单 Continue 之后：只有加载 GlobalPool 和 Hero_Hornet prefab 那一段是 LOADING，随后的工作台场景加载、激活、GC 和醒来动画都计时 [m0:C7]。
  - 新游戏：从 Opening_Sequence 的加载开始计时，Tut_01 的加载也计时 [m0:N23]。
  - Quick Map（按住 Tab）：PlayTime/墙钟 = 0.998；代码路径不碰 isInventoryOpen、GameState 或 timescale，世界不冻结 [m0 §2.3][probe:P6]。
  - 失去焦点：原版 `runInBackground = True`，失焦后继续模拟和计时 [probe:P6]。
- **不计时的情形：** 暂停菜单；库存（含 Map 页；打开时同样冻结世界，P6 实测 PlayTime/墙钟 = 0.000）[m0:N24][probe:P6]；LOADING（只指 Continue 的 prefab 加载段）；CUTSCENE（InGameVideo、开场动画、Bellway 乘车视频及其后台加载、含 `InGameCutsceneInfo` 组件的场景、End_Credits 等）[m0:N21][m0:N22]；≥1 s 的单帧。
- **暂停只能从 PLAYING 开始**：ENTERING_LEVEL/EXITING_LEVEL 期间的秒数一定计时，且不能暂停 [m0:N12]。
- **未知 [待验证 P6]：** Ventrica 管道（`Cinematic_Submarine_travel`，预计与 Bellway 相同）；Bellway 和片尾尚未做运行时确认。策略不变：永不使用 Quick Map，永不失焦。
- **成就读取的是 `playerData.playTime`，它只在保存时写入** [VER]：每次 SaveGame 和每次创建恢复点（包括静默自动存档）都会 flush [m0 §2.3]。因此被检查的值 ≤ 实时时间，按实时时间做预算是保守的。
- **推论：**
  - 正式运行就是实时的。
  - lockstep 训练不省预算，所以已移除（C15）。
  - 暂停状态下思考不花时间；库存打开时同样冻结且不计时，可作路线和审计的"思考态"，但不能用来退出 [m0:N24]。
  - 路线应尽量减少房间切换：少一次切换，同时省走路时间和加载时间。

### 1.4 版本锁定与安装

- **构建。** 1.0.30000：app 1030300，depot 1030301，manifest `4421626056705534276`，buildid 22479045，2026-03-24 [VER]。
- **Sea of Sorrow。** 截至 2026-09-28 尚未发布 [VER]，但已宣布在 2026 年发布 [ach10]。项目周期 3–5 年，期间大概率会发布，所以 R8 定为"高"。
- **运行时和工具。** Mono [mod0]；BepInEx 5.4.23.4 [mod3]；Silksong.GameLibs 1.2.0-silksong1.0.30000；DebugMod 1.1.2 [mod9]。Unity 6000.0.50f1（uum-100966-branch1），Input System 1.14.2 [probe:P1][m0:N40]。
- **输入后端。** InControl `HeroActions` 跑在 Unity Input System 之上 [VER][mod13]。键盘和鼠标永远走 Input System（`UnityKeyboardProvider` 总会安装）；高级手柄设置里的 NativeInput/XInput/MFi 只影响手柄后端，改动要重启才生效。注册表快照中冻结 NativeInput（当前为 1）[m0:C15]。legacy `Input.anyKeyDown` 仍用于过场跳过、`GameManager.UpdateEngagement` 和 `IdleMemoryCleaner` [m0:N36]。
- **安装布局（修订）：**

| 副本 | 获取方式 | 内容 | 启动方式 | 用途 |
|---|---|---|---|---|
| **最终副本** | Steam 控制台 `download_depot 1030300 1030301 4421626056705534276`（不需要把 Steam 登录交给第三方工具）。实际做法：直接复制当时 buildid 已确认的库副本，library/final/train 三份 2268 个文件 sha256 逐一相同 [probe:P1] | 原版文件 + `steam_appid.txt`（1030300）。**不含** `winhttp.dll`、`doorstop_config.ini`、`BepInEx/` | Steam 客户端在线时直接运行 exe | VANILLA 预演、M0-P5 成就探针、FINAL |
| **训练副本** | 同一 depot 的另一份拷贝 | + BepInEx + SsOracle + DebugMod（+ Benchwarp）；Steam 子系统缺席（D15） | 启动脚本（按配置） | TRAIN / SHADOW / REHEARSAL，以及你自己录制的游玩 |
| Steam 库托管副本 | Steam | — | **项目期间永不按"开始"**：一启动就会更新；没有 `steam_appid.txt` 时 `RestartAppIfNecessary` 会经 Steam 重启 [m0:N28] | 只在 M0-P1 做哈希比对，之后卸载 |

- **每次启动后：** 枚举进程已加载 DLL 的哈希，与 `versions.lock` 比对；OCR 标题画面上的版本号（`SetVersionNumber`）。
- **每章之前：** 查看 Steam 新闻；备份真实存档目录。正式运行尽量在最少的自然日内完成。
- **D14：** 如果到 M7 时 1.0.30000 仍是 Steam 上线版本，你可以选择改用库副本。

### 1.5 驱动设计的战斗与世界事实

| 事实 | 来源 |
|---|---|
| 初始 5 个面具。Act 1 有 6 个碎片，打 Act 2 结局最多 9 个面具。4 个碎片 = +1 面具，补满一个面具会回满血。 | [com0] |
| 几乎所有 boss 招式和接触伤害都是 2 格；另有 1+1、1+1+1 的形式。 | [com1] |
| 危险物伤害：SPIKES 1、ACID 1、LAVA 2、COAL 1、COAL_SPIKES 1、ZAP 1、STEAM 2；Flame 2；Void 2 并吸丝。 | [com2] |
| 受击和弹反 i-frame 只挡 ENEMY、NON_HAZARD、EXPLOSION：SPIKES、ACID、LAVA、PIT、COAL、ZAP、STEAM、COAL_SPIKES 都会穿透，SINK 永远生效。例外：危险物重生后 0.5 s 内再碰到非敌人危险物，只会再重生一次，不扣血。 | [com3][m0:N1] |
| 受击 i-frame `INVUL_TIME` = 1.0 s（游戏时间；受击冻结期间 timeScale 下降，实时长度更长）。Weighted Belt（中文名“负重环带”，资产名 Weighted Anklet；离线资产值 i-frame ×1.3、击退 ×0.5、水平后坐 4 步，待 P17 运行时确认 [asset]）的代码默认值（代码字段 `weightedAnklet*`）：i-frame ×1.2、击退 ×0.5、拼刀后坐 2 步，装备后最大下落速度改用 `MAX_FALL_VELOCITY_WEIGHTED`；GlobalSettings 资产可能覆盖，待 P11 读取。 | [com4][probe:P11][m0:C6] |
| 弹反 i-frame `INVUL_TIME_PARRY` = 0.15 s（[com5] 的 0.25 s 恰好是 NailClashEffect 冻结的保持时长）；Cross Stitch 0.35 s、SILKDASH 0.5 s（由 SilkChargeEnd 设置，可能是 Sharpdart，名称对应待 P11）、QUAKE 0.4 s。下劈 i-frame 8 个物理步（长版 16 步，即 0.16/0.32 s），只挡 ENEMY，不挡 EXPLOSION、危险物和 noBounceCooldown 伤害源。**冲刺、疾跑、Bind 都没有无敌。** | [com5][probe:P11][m0 §2.5] |
| Bind：9 丝，+3 面具，1.37 s（带 Injector Band 0.89 s）。闪光前被打断会清空**全部**丝；脚下平台消失也会打断。丢丝规则在 Bind FSM 里，代码无法确认（`BindInterrupted()` 不碰 `silk`），待 FSM 导出。 | [com6][m0 §2.5] |
| 丝：初始上限 9，最大 18；丝技能消耗 4。 | [com7] |
| Fractured Mask（Hunter's March 的 Mottled Skarr 处 260 念珠），坐工作台修复。1.0.30000 的语义：只要已装备且 `AmountLeft > 0`，致命伤一律被钳到剩 1 HP；只有 `allowFracturedMaskBreak` 为真（命中不带 MidChain 标志）时才消耗面具。所以连招中段（MidChain）的致命命中能救命且不耗面具。社区列出的失效案例（Muckroach Maul、Wraith 抓取、Slubberlug 抓取、Greymoor 和 Mist 的爪形陷阱）在 1.0.30000 上可能已部分修复，导出 DamageHero/FSM 的 flags 之前仍按失效处理。 | [com10][m0:C2] |
| DoSpecialDamage 类伤害（酸等 DamageTag 标签、Chomp、霜冻、TakeQuickDamage）不查 i-frame，也不给 i-frame、后坐或冻结；标签栈在工作台和危险物重生后都不清除。 | [m0:N2] |
| 拿到 Faydown 之前：`frostAmount ≥ 1` 时每 1.75 s 扣 1 HP，无视 i-frame，可以致死，也会打碎面具。拿到 Faydown 后永不结冰。 | [m0:N3] |
| barnacle 抓取不看 i-frame、弹反和 isInvincible，后坐结束后、i-frame 还没结束时就能被抓；Underworks 锯块的 'Multihitter' FSM 同样穿透 i-frame。普通抓取遵守 i-frame。 | [m0:N4][m0 §2.5] |
| Barbed Wire（代码 `barbedWire`；游戏内名称待 P11 名称对应确认，应即 §3.6.4 的 Barbed Bracelet）：受到的伤害 ×2（向下取整，在危险物覆盖值之后再乘）。永不装备。 | [m0:N10] |
| 必打 boss：Moss Mother、Bell Beast、Lace 1、Widow、Last Judge、Cogwork Dancers、Trobbio、Forum 连战、Lace 2、GMS。Fourth Chorus、Moorwing、Sister Splinter 常被跳过。 | [com16] |
| 最危险的是 Forum 连战、Dancers、Lace 2、Last Judge/Mist。人类 Steel Soul 的死因主要是危险物、1+1 抓取和连战。 | [com17][com18] |
| Last Judge 720 HP，540 进二阶段；自 1.0.29909 起死亡爆炸为 2 格。Lace 1 250 HP，Lace 2 800 HP。Dancers 190+190，然后 220+220 两轮，最后 180。Forum 13 波，最后是 2 只 Choir Clapper（各 230 HP）。GMS 1224 HP，6 个阶段。 | [VER] |
| Mist 是随机迷宫，需要 Needolin → 走 Last Judge 的 Bell 路线。 | [spe9][VER] |
| 拿到 Cling Grip 之后、拿到 Faydown 之前，Wardenfly 可以把 Hornet 抓到 The Slab（没收 Needle 和披风）。 | [spe13] |
| Shakra 只有在尚未去过 Greymoor、Bellhart、Shellwood 时才会在 Hunter's March 竞技场助战，所以 S10 必须排在这三个区域之前。 | [local:x_Shakra] |
| 必须先和 Garmond 对过话，打开 Whispering Vaults 屋顶捷径后他才会在屋顶出现，提出切磋。赢了之后可以在 Forum 外招募他们助战。他一旦进入 Citadel，就不会再出现在已见过他的房间。切磋输了不会丢档，**但被击落到下方尖刺致死会丢档**。 | [local:x_Garmond_and_Zaza] |
| Hunter Crest 的工具槽：红、蓝、黄各 1 个已解锁 + 1 个需 Memory Locket 解锁。Memory Locket 来源：Pilgrim's Rest 购买、Hunter's March 竞技场后拾取、Bellhart 购买（可选）、Choral Chambers 拾取。 | [local:Hunter_Crest][local:g1][local:dis] |
| Pebb 的面具碎片在 **Bone Bottom** 出售，300 念珠。 | [local:maskshard] |
| 红色工具在工作台补充，通常消耗 Shell Shards。 | [local:Tools] |
| 敌人 AI 是 PlayMaker FSM：要枚举全部 FSM，不能假设叫 "Control"。DebugMod 的 HitboxRender 已能给威胁分类。 | [int12][int15][VER][mod6] |
| RNG 不够确定，一切都必须闭环。 | [pri7] |
| 所有有记录的成功案例都读了游戏内部状态；像素 RL 在难 boss 上只有中等胜率；没有项目自动化过完整通关。 | [pri0][pri9][pri24] |
| 人类成就局约 3.5–4 h 游戏内时间；any% NMG 世界纪录 48:04。 | [spe10][spe4] |

### 1.6 需在 M0 复核的 `[dec]` 事实

本表已由 [`facts/1.0.30000/m0.md`](facts/1.0.30000/m0.md) 用 1.0.30000 代码核对。设置行、存档槽 `isIncompatible`、Unscaled 时间、HUD 的 Weaver 图标这几条本轮未核对（m0 §2.8）。

| 领域 | 事实 |
|---|---|
| 相机 | 透视 tk2d 相机；`ForceCameraAspect` 把宽高比限制在 1.6–2.39 并加黑边；HUD 用单独的正交相机。中心被限制在 x ≥ 14.6、y ≥ 8.3；可视平面约 29.2 × 16.6 u，1080p 下约 65 px/u；`lookOffset` ±6 u。（已确认，是否真的是透视待 P11 [m0 §2.7]） |
| 设置 | 相机震动 On/Reduced/**Off**；`particleEffectsLevel`；`hudScaleSetting`；`brightnessAdjustment`；`targetFrameRate`；`vSync`；`showNativeAchievementPopups`。这些都存在 PlayerPrefs（HKCU 注册表）里。游戏的"垂直同步"和"帧率上限"互斥：开 VSync 时 `targetFrameRate = -1`，帧率等于刷新率 [probe:P8][probe:P11]。 |
| Hit-freeze | `FreezeMoment` 各配置（下降/保持/上升，秒，unscaled）：HeroDamage 0.01/0.28/0.10，NailClash 0.01/0.25/0.10，BindBreak 0.01/0.40/0.10，BossStun 0/0.25/0.10，EnemyDeath 0.04/0.024/0.04（已确认）。长时类型：BossDeathSlow 1.35 s（速度 0.05）、EnemyBattleEndSlow 1.85 s（每个 BattleScene 结束时，除非 noEndSlomo）、RaceWinSlow 3.8 s、BossDeathStrike 0.45 s、HeroDamageShort 0.2 s（Wanderer 暴击）、BigEnemyDeathSlow 0.14 s [m0:N13]。每一种都让 `TimeSlowed` 为真，同时吞掉暂停和解除暂停。英雄自己受击不用 HeroDamage 预设，而是调用 prefab 上的 `DAMAGE_FREEZE_DOWN/WAIT/UP` = 0/0.1/0.1 s [m0:C5][probe:P11]。 |
| 暂停/退出 | §1.2 所列门控；还包括 `InteractManager.BlockingInteractable`（工作台处除外）、`acceptingInput`、Patch 4 之后 ReturnToMainMenu 的拒绝条件，以及退出时（`ReturnToMainMenu(willSave:true)`）保存失败后停在 PAUSED 而 `PauseAllowed` 一直为 false 的分支（§3.6.8）[m0:C9]；游戏中（如工作台）保存失败则在 PLAYING 下弹出 SAVE_FAILED MSG_CANVAS，是另一种情况（§3.6.8 另有一行）。逐条代码核对见 m0 §2.4。 |
| 扣血路径 | `TakeHealth`（Fractured Mask 的语义见 §1.5 [m0:C2]）；经 `ApplyTagDamage` 的 `DoSpecialDamage`（`DamageTag` 的 startDelay/delayPerHit，例如带 Acid 标志的命中会挂上 acidDamageTag）；`TakeChompDamage`；`TakeFrostDamage`；`CriticalDamage`（HP 设为 1 并清空蓝血）；`CogMultiHitter`（1.0.28497 已删除双倍伤害：触发时只查 `isHeroInPosition` 和 `!isInvincible`，0.35 s（scaled）后 `DamageHeroDirectly` → `TakeDamage(1, SPIKES)`，共 1 格 + 一次危险物重生，穿透 i-frame；任一齿轮命中后所有齿轮冷却 1.0 s）[m0:C3]；FSM 动作 `DamageHeroDirectly`/V2 清除 `isInvincible`、`cState.parrying` 和下劈步数，**不清** `cState.invulnerable` 和 `parryInvulnTimer`，所以 ENEMY 类直接伤害仍被受击 i-frame 挡住，SPIKES/SINK 类穿透（Patch 4 加入了 `CheckDeathCatch`）[m0:C4]。 |
| HUD | 每单位丝对应一个 `SilkChunk`；`HudGlobalHide`；绑定 GMS 后切换为 Weaver 面具图标和更大的线轴。 |
| 焦点 | 原版 `Application.runInBackground = True`、InControl `SuspendInBackground = False`、Input System `backgroundBehavior` 为默认的 ResetAndDisableNonBackgroundDevices：失焦时键盘被断开，Hornet 失去控制，而世界和 PlayTime 照常运行；游戏代码不会因为失焦而暂停 [m0:C16][probe:P6][probe:P11]。 |
| 存档槽 | `SaveSlotButton` 有 `isIncompatible` 分支（新版本碰过的存档在旧版本可能读不了）。 |
| Unscaled 时间 | 49 个文件读取 `unscaledDeltaTime`，其中约 8 处影响玩法。只有在启用 lockstep（§3.11）时才相关。 |

### 1.7 用户约束的落实

| 约束 | 落实方式 |
|---|---|
| mod 只用于训练；正式运行是原版，只看屏幕、只发按键 | 配置 FINAL = F1。任何放宽（F2/F3、音频、读存档、杀进程 D13）都是你的明确决定，从不作为默认。 |
| Switch（采集卡 + 单片机）是延伸目标 | `FrameSource`/`ControllerSink` 是插件，带域标签和延迟模型（§3.8、§4.5）。 |
| 你的四部分分解 | §3.0 一一对应，并补齐缺失的子系统。 |
| 用 mod 提取的知识（地图、敌人表）能否用于正式运行 | 默认可以，相当于"背过 wiki 的玩家"（D2）；另有纯像素地形的后备方案。 |

---

## 2. 总体架构

### 2.1 原则

1. **一个 `WorldState` 契约，两个生产者。** `OracleBackend` 给精确值；`VisionBackend` 给估计值并附带不确定度。"大脑"在所有配置下是同一份代码。
2. **能查的不看。** 静态内容离线导出到版本化的 Knowledge DB。
3. **Oracle 是老师、标注员和裁判。** 所有标签都来自它，不需要手工标注 [pri16]。
4. **进入正式运行的模块只能消费 `VisionView`。** 靠三重手段强制：类型检查、import 禁令测试、进程防火墙。
5. **安全推理基于支撑集，并且手写、有单元测试。** 学习只在安全盾内部调性能参数。
6. **一切闭环。** "回放"只指重看录像和重跑感知，不指重新模拟 [pri7]。
7. **一套冻结配置用于所有配置，每条日志都带配置指纹。**

### 2.2 关键设计决策

| # | 主题 | 决定 | 理由 |
|---|---|---|---|
| C1 | 帧率 | **60 fps、60 Hz、游戏内 VSync 开**（2026-09-29 定：LG TV 最高 60 Hz，不考虑 120 Hz）；显示模式必须无撕裂 | 计算预算 16.7 ms；物理 50 Hz（`fixedDeltaTime` = 0.02 已确认）[int14][probe:P11]；游戏开 VSync 时帧率等于刷新率（P11）；P8 实测 60 Hz 下按键 → 画面开始变化 p50 45.6 ms、最大 49.6 ms |
| C2 | 捕获 | 只实现 WGC（窗口模式、DWM 合成，§2.6）。只有 P8 证明 WGC 不达标时才加 DXGI | 窗口级捕获、不会被其他窗口遮挡、支持多实例；少维护一个后端 |
| C3 | PC 输入 | **默认 `SendInput`**，由独立的 `inputd` 进程发送。RP2040 为 Switch 而做，PC 上作为可选项 | RP2040 挡不住主机崩溃或焦点丢失（游戏会随主机一起死；按键只发往前台窗口），唯一多出的保护是 rt/inputd 崩溃 |
| C4 | 帧与标签对齐 | QPC 时间戳 + 相机轨迹互相关；不往像素里烧条码 | 训练像素必须与正式运行一致 |
| C5 | 相机模型 | 透视；保存 V/P 矩阵 | [dec]；相机组件和钳位已由 m0 §2.7 确认，是否真的是透视待 P11 读取；`fovOffset` 生效时 px/u 不是常数 |
| C6 | 定位 | v0 = 把分割出的地形掩码与 `SceneGeometry` 碰撞栅格做配准。图集、描述子、LK 按需再加（§3.11） | 先用便宜的方案 |
| C7 | 战斗核心 | 规则表 + 搜索规划器 + 安全过滤器 + 监督器；学习只做盾内参数调优；PPO/DAgger 移到 §3.11 | [pri9][pri10][pri11] |
| C8 | 前摇识别 | 可观测阶段分类 + HMM，只针对 A 类 boss 和竞技场敌人 | 不训练像素无法区分的标签；缩小范围 |
| C9 | 安全对冲集 | 支撑集 = 所有观测到的转移 + 所有 FSM 图边；样本 < 30 时按最坏情况处理 | 用 1% 概率截断，在约 40 场危险遭遇里就是个漏洞 |
| C10 | 证据 | 按单元的序贯贝叶斯门槛 + 前兆故障树 + 全程预演 | 原来的"连续计数、失败即重置"数学上过不去（见附录 A） |
| C11 | 全程预演 | 打到片尾只在训练副本上做；原版预演在 GMS 前硬停 | 防止提前解锁 SPEEDRUN_1 |
| C12 | HUD 精度 | HP 高估：0 / 10⁶ 帧；任意不一致 ≤ 5e-4 | 只有高估才危险 |
| C13 | 时间 | 硬上限 17,400 s；自底向上预算 + 调速器；K3 决定一局还是两局 | §3.6.6 |
| C14 | Oracle 开销 | 主线程 p50 ≤ 0.3 ms、p99 ≤ 1.0 ms；帧时间 p99 相对原版 ≤ +0.5 ms | 取各方最严的组合 |
| C15 | 训练时钟 | 只用实时，4–6 个实例；移除 lockstep 和 timeScale | 计时用 unscaled 时间，lockstep 省不了预算 [VER]；timeScale 有保真陷阱 [pri5] |
| C16 | 死人开关 | 100 ms；菜单和 CUTSCENE 中解除；按/放循环，`inputd` 自己看到暂停的最早线索（暗幕开始变暗）即停手，必须在真实暂停后约 230 ms 内 | 单次 Esc 可能被丢弃；0.3 s 锁定一过，再按 Esc 就会解除暂停 [m0:C11]；CUTSCENE 中任何按键都会跳过过场 |
| C17 | IPC | TCP 传状态和动作；不再需要帧共享内存 | 移除 TRAIN-V 后没有帧要传 |
| C18 | 插件 | 一个 `SsOracle`，从 SilksongRL（MIT）分叉 | 复用 socket、致命取消、多实例代码。输入注入改为 `InputSystem.QueueStateEvent`（§3.1.1）：SilksongRL 的注入只覆盖 ← → ↑ ↓ Z X（Extended 加 C），按控件名匹配还会命中手柄，写入帧不确定 [m0:N39] |
| C19 | 按键保持 | PC 按帧计数：每次按下保持到看到 ≥ 2 个新帧，下限 max(34 ms, 2 × 实测帧时间)；同一键两次按下之间的松开同理。Switch 40 ms。暂停循环为按 ≥34 ms / 放 ≥34 ms | Input System 每个渲染帧采样一次按键（`ProcessEventsInDynamicUpdate`），同一次更新内的按下加松开会丢；原来的 21 ms 短于 60 fps 下的两帧 [m0:N37][probe:P11] |
| C20 | 计时估计 | 低估 ≤ 30 s/局，高估 ≤ 300 s | 只有低估危险 |

### 2.3 运行配置

| 配置 | 游戏副本 | mod | 策略输入 | 画面 | 输出 | 守卫/裁判 | 存档 | 用途 |
|---|---|---|---|---|---|---|---|---|
| **TRAIN** | 训练副本（无 Steam 子系统） | SsOracle + DebugMod (+Benchwarp) | Oracle → `ObservabilityFilter` → 简单噪声 → `DelayLine` | 无（720p 窗口） | `OracleInjectSink` + `InputPathEmulator` | LethalBlock 双网、SaveRedirect、SaveSuppression、AchievementGuard | 沙盒目录 | T0/T1、G0；4–6 实例 |
| **SHADOW** | 训练副本 | SsOracle（无作弊） | `driver=oracle`（测视觉误差）或 `driver=vision` | WGC（最终路径） | OracleInject + 延迟模拟 | LethalBlock 否决；oracle 当裁判 | 沙盒 | 视觉指标、G1；2 实例（受 GPU 限制） |
| **REHEARSAL-SEG** | 训练副本 | SsOracle 被动 + savestate | 视觉 | 最终路径 | **最终 sink**，1 个前台实例 | LethalBlock 只记 WOULD_DIE | 沙盒 | G2（≥50% 的起点来自真实 Continue） |
| **REHEARSAL-FULL** | 训练副本 | SsOracle 被动 + AchievementGuard，无 savestate | 视觉 | 最终路径 | 最终 sink | 进入 Die 即记为死亡，继续跑以采数据 | 沙盒：Classic，或 Steel Soul（`RecPermadeathMode` 白名单）+ 快照 | G3、结局预演 ×5 |
| **VANILLA** | **最终副本** | 无（校验哈希）；可选外部只读内存读取器作被动裁判 | 视觉 | 最终路径 | 最终 sink | 无 | 真实存档目录中的 Classic 槽；定位器在 GMS 竞技场和 Cradle 前的场景硬拦截（暂停 → 退出）；结束后由你手动归档 | 验证没有 mod 时行为无差异 |
| **FINAL** | 最终副本 | 无（F1） | 视觉 | 最终路径 | 最终 sink | 无 | Steel Soul 槽 | 正式尝试 |

### 2.4 拓扑（训练 vs 正式运行）

```
 TRAINING (training copy, no Steam subsystem)                 FINAL RUN (pinned depot copy, vanilla)
┌── Silksong 1.0.30000 + BepInEx 5.4.23.4 ──────────────┐    ┌── Silksong 1.0.30000 ───┐
│ SsOracle: Export · Guards · Harness · Input · Ipc     │    └────┬─────────────▲──────┘
└─┬ STATE/TERRAIN/PROGRESS/EVENT (TCP) ─▲ ACTION ── pixels┘         │ pixels (WGC)   │ keys (SendInput)
  ▼                                      │       │ (SHADOW/REHEARSAL      ▼                │
 OracleBackend                           │       ▼  use final path) VisionBackend   inputd: focus guard,
  ├─► ObservabilityFilter ► noise ► DelayLine ─┐ VisionBackend        │           dead-man, own
  │                                            ▼        │             ▼           pause-menu detector
  └─► ShadowComparator ◄── vision WS ── Brain (same code) ────────────┘                 ▲
          │                              Supervisor · Run/Route/Interact · Nav ·        │
          ▼                              Combat · Ledger ──── ControllerSink ───────────┘
   metrics · precursor stats ·        Recorder ─► DatasetBuilder ─► trainers ─► frozen bundle
   gate reports                                     (models + Knowledge DB + config, hashed)
```

**每帧数据流：**

```
FrameSource ─► ScreenMode(+menu read, tear flag) ─┬─► HUDReader ───────────────────────────┐
                                                  ├─► Localiser (mask ↔ SceneGeometry raster)┤
                                                  ├─► Detector+Seg ─► Tracker ─► PhaseCls ─► HMM ┤
                                                  └─► TerrainVerify (2 Hz, reuses seg) ─────┤
   KnowledgeDB (read-only) ──────────────────────────────────────►  Fusion ─► WorldState (60 Hz)
   Ledger (two-phase, persisted per event) ◄───────────────────────►   │
         ┌──────────────────────────────────────────────────────────┼──────────────────────────┐
         ▼                                                          ▼                          ▼
  Supervisor (every frame)                   RunManager/Route/Interact + GlobalNav   Tactics ─► Planner ─► SafetyFilter
  PAUSE_PENDING, pause/quit loop ──┐         (planner process, 5–10 Hz goals)        (10 Hz)    (60 Hz)    (60 Hz)
                                   └───────────────────────►  ControllerSink  ◄──────────────────────────┘
```

### 2.5 进程与核心（i9-13900K，RTX 4060 Ti 16 GB）

| 进程 | 工作 | 优先级 / 核心 |
|---|---|---|
| `rt` | 捕获 → GPU 感知（2 个 CUDA stream、CUDA graph）→ 融合 → 监督器 → 战斗 → sink。**计算截止 p99 ≤ 12 ms/帧。** | HIGH，P 核 2–7 |
| `planner` | 世界图、路线目标、房间内寻路、Ledger；通过无锁队列给 `rt` 发目标 | NORMAL |
| `inputd` | 用高精度可等待定时器（约 0.5 ms）执行按键；强制最短保持；心跳看门狗；**焦点守护**（每 1 ms 轮询 `GetForegroundWindow`）；**自带暂停检测**（独立的 WGC 会话，固定 ROI 模板，60 Hz；以暗幕开始变暗为最早线索，§3.7.5）；操作员热键 Ctrl+Alt+P | TIME_CRITICAL 线程，1 个 P 核 |
| `recorder` | NVENC 视频 + 状态/动作/事件日志；宁可丢帧也不拖慢 `rt`；有专用数据盘后**不写 C: 盘**（在那之前写 C: 上的专用目录，C: 空闲 < 200 GB 时停录） | BELOW_NORMAL，E 核 |
| `shadow`（仅训练） | 比较视觉与 oracle，写指标 | NORMAL，E 核 |

在 Python 3.13 下 GIL 不是瓶颈：TensorRT、CuPy、numpy、捕获都会释放 GIL；A* 放在独立进程。

### 2.6 冻结配置（所有配置一致）

| 项目 | 设置 | 理由 |
|---|---|---|
| 构建 | 1.0.30000，哈希锁定 | [mod2][VER] |
| 显示 | 游戏画面 1920×1080、16:9，窗口模式（DWM 合成）运行在 4K@60 Hz 桌面上（与 `versions.lock` 的 `display_mode` 一致；P8 即在此配置下测得）；游戏内 VSync 开；关 HDR/Auto HDR。捕获发生在 PC 内部，电视自身的显示延迟不影响 bot。**模式必须无撕裂**：P8 在这个冻结模式下报告撕裂率；不为零就上报并查明原因，不自行改动 60 Hz / VSync 开的冻结配置 | 约 65 px/u；撕裂会把 HUD 和目标拆到两帧里 |
| 帧率 | 60 fps = 60 Hz 刷新 + 游戏内 VSync 开（`vSyncCount = 1`、`targetFrameRate = -1`）。不设游戏内帧率上限：它与 VSync 互斥，设了就会关掉 VSync | [pri22][probe:P8][probe:P11] |
| 相机震动 | **Off** | 配准时没有抖动 |
| 粒子 | **Low** | 画面更干净 |
| HUD 缩放、亮度、着色器质量 | 固定，记录在 `versions.lock` | HUD 区域和颜色统计稳定 |
| 原生成就弹窗、Steam/Discord/NVIDIA 叠加层、Game Bar、Windows 通知 | 全部关闭；Steam 状态设为隐身 | 屏幕上不出现入侵 |
| 输入 | 默认键盘键位（P4 核对与注册表一致 [probe:P4]）；键盘固定走 Input System，注册表快照冻结 NativeInput [m0:C15]；中文界面（2026-09-29 定，沿用你自己的设置；菜单 OCR 模板按中文字体做）；英文键盘布局（无输入法）；**PC 上不接任何手柄**（含 Switch Pro 和 RP2040 手柄模式）：活动手柄断开会自动暂停，任何手柄输入都会切换菜单的键盘别名 [m0:N19][m0:N16] | 扫描码映射有效；菜单别名和意外暂停可预测 |
| Windows | 专注助手开；暂停更新；关闭睡眠；GPU 驱动锁版本；`SPI_SETFOREGROUNDLOCKTIMEOUT` 设为最大；关闭粘滞键/筛选键/切换键的快捷键；**章节期间拔掉鼠标**（悬停会改变菜单选中项）；调试 UI 放在第二显示器，窗口带 `WS_EX_NOACTIVATE` | 保护焦点和捕获 |
| 硬件 | BIOS 更新到带 Intel 微码 0x12B 或更新版本 | 13 代 Vmin 不稳定问题；部分挂起比整机挂起更危险 |

**配置指纹**：设置文件（注册表快照）哈希 + 模型哈希 + Knowledge DB 哈希 + 捕获后端 + fps + sink。门槛只统计指纹与最终配置一致的会话。

### 2.7 共享状态隔离

| 共享物 | 风险 | 措施 |
|---|---|---|
| 存档目录 `LocalLow/Team Cherry/Hollow Knight Silksong/<AccountID>/`（目录名是 32 位 Steam AccountID，不是 SteamID64 [m0:C14]） | 训练写坏真实槽；Steel Soul 槽被覆盖；最终副本的 Steam 初始化失败时，存档和 shared.dat 静默落到 `default` 目录，与训练副本的默认目录相同 [m0:N28] | ① 训练副本不带 Steam 子系统（D15，重命名 `steam_api64.dll` 已由 P9 验证），不重定向时存档落到 `default` 目录，成就只能本地 [probe:P9]。② SsOracle 再把存档和共享数据路径重定向到 `C:\ssbot\sandbox\saves\<instance>\`（`-ssbot-instance N`，默认 0）：已在 `oracle/src/Guards/SaveRedirect.cs` 实现（Harmony 转译补丁替换 `DesktopPlatform.Awake` 里唯一一次 `Application.persistentDataPath` 调用，user*.dat、`.bak*`、Restore_Points、shared.dat 都进沙盒），实测通过 [probe:P9]。真实的 `persistentDataPath\default` 已删除，必须保持不存在：它一旦重新出现，就说明最终副本的 Steam 初始化失败了 [m0:N28]，compat 第 7 项报警。未重定向：DebugMod 的 `DebugModData\`（它自己的设置和存档点，不含游戏存档）仍在真实 LocalLow 下。③ SlotGuard 作第二层。④ compat 在会话前后对真实 `<AccountID>` 目录做哈希，并确认 `default` 不存在。 |
| `shared.dat`（RoamingSharedData：`RecPermadeathMode`、菜单样式、本地成就后备） | 训练误解锁；Steel Soul 解锁流程直到正式那天才第一次执行 | 同上隔离；AchievementGuard 放行 `RecPermadeathMode`，其余照常拦截。`RecPermadeathMode` 按存档目录存放，每个目录各一份 [m0:N32]；M0 已在最终副本上输入过一次 Steel Soul 代码（无害），`<AccountID>\shared.dat` 现为 `RecPermadeathMode=1` [probe:P5]。训练沙盒里的结局预演会经 `PermaDeath_Unlock` 把 `RecPermadeathMode` 写进沙盒 shared.dat，同样无害。 |
| PlayerPrefs（HKCU `Software\Team Cherry\Hollow Knight Silksong`：视频设置、所有键位、NativeInput/XInput、GameLang；所有副本共用） | 训练实例或你的游玩改了设置/键位，泄漏到正式运行；Unity 退出时还会把启动参数 `-screen-width/-screen-height/-screen-fullscreen` 写回该键 [probe:P9] | 在 `versions.lock` 中保存 `.reg` 快照，冻结 GameLang = ZH（界面语言定为中文）和 NativeInput [m0:N40][m0:C15]。`scripts/launch_train.ps1` 启动前导出该键，退出后删除并导入快照（P9 实测还原后 0 处差异）。每次 VANILLA/FINAL 会话前恢复并做哈希；compat 再 OCR 选项页，与黄金模板比对。 |
| Steam Cloud | 冲突弹窗或静默回滚 | 整个项目期间对 Silksong 关闭 Steam Cloud。 |
| 成就 | SPEEDRUN_1/STEEL_SOUL 提前解锁（不可逆） | 训练副本本身没有 Steam 通道 + AchievementGuard：patch `DesktopPlatform.PushAchievementUnlock`、`DesktopPlatform.UpdateAchievementProgress`、`AchievementHandler.AwardAchievementToPlayer`、`AchievementHandler.UpdateAchievementProgress`、`MenuStyleUnlock.Unlock`，并拦截或重定向 `RoamingSharedData` 写入（Push 总会写 shared.dat），任一 patch 失败就拒绝启动。`Platform.PushAchievementUnlock` 是 abstract、`Platform.UpdateAchievementProgress` 被重写且不调 base，挂在它们上面的 patch 要么失败、要么永不执行 [m0:C1][m0:N26]。原版预演在 GMS 前硬停。 |
| 真实存档目录中的槽位 | MenuDriver 误选 Restore/Clear；继续了错误的槽 | 正式运行时该目录只留最终槽，其他槽由你手动归档；FINAL 配置里把删除/清除动作编译掉（§3.6.2）。 |

---

## 3. 子系统设计

### 3.0 与你的分解的对应关系

| 你的条目 | 模块 | 章节 |
|---|---|---|
| (1) 视觉：低频地形扫描、高频敌人/弹道跟踪、轨迹预测、前摇识别、学习敌人规则 | `perception/localize`（每帧）+ `terrain_verify`（2 Hz）、`detect`、`track`（运动学 + 蒙特卡洛命中预测）、`phase_cls` + `phase_hmm`、`knowledge/phase_tables` + `behaviour_tables`（P(招式 \| 距离, 阶段)） | 3.1、3.2 |
| (2) 自身状态：HP/丝、上限、已学技能 | `perception/hud`、`inventory`、hero 滤波器、事件计时器、挂起伤害、两阶段 `world/ledger`、计时估计器 | 3.3 |
| (3) 地图：不买地图；商人、Bellway、工作台、任务物品；世界变化 | `world/graph`、`predicates`、`entities`、`ledger`、`nav/*`、定位、地形验证 | 3.4 |
| (4) 战斗：什么时候按哪个键，取决于地形、敌人数量和类型 | `combat/tactics`、`planner`、`safety_filter`、`bind`、`parry`、`pogo`、playbook | 3.5 |
| 新增 | 路线执行器 + **交互子系统** + **恢复表**、安全监督、I/O 后端（含 Switch）、训练与评估、日志回放 | 3.6–3.10 |

### 3.1 感知 I：训练 Oracle（`SsOracle`）

#### 3.1.1 模块（从 SilksongRL 分叉）

SilksongRL 已经有 socket 桥、`ButtonControl.get_isPressed` 注入（有缺口，见 C18 [m0:N39]）、致命伤取消、存档抑制、`BossStateLogger`、多实例启动器 [pri1][VER]。在此基础上改造和补充：

- **Core：**
  - `Plugin`：加载配置；TRAIN 下保持 `runInBackground = true`（原版已是 True [probe:P11]），并设 `InputSystem.settings.backgroundBehavior = IgnoreFocus`，否则失焦时键盘被禁用，注入的事件被丢弃 [probe:P3]；跳过 `SetCursorEnabled`、释放鼠标，并在 Input System 中禁用鼠标设备（悬停会改变菜单选中项 [probe:P7]）。
  - `Profile`：拒绝被禁止的组合，例如 SHADOW 中开作弊。
  - `SymbolCheck`：按名字解析约 150 个类型/字段/方法，失败时出报告并硬失败。
- **Export：**
  - `HeroExporter`：位置、速度（`Body.linearVelocity`，不用已过时的 `Rigidbody2D.velocity`）、`hero_state`、cState 位集（用 `onGround`、`isBinding`；`Invulnerable = invulnerable || invulnerableCount > 0` [VER]；`parryInvulnTimer`、下劈步数、`isInvincible`、`HeroInvincibilitySource` 不在其中，分别导出）、PlayerData 标量（经 `GameManager.UnsafeInstance.playerData` 读取，不用 `hero.playerData` 缓存）、`Can*()`。退出时 GameManager、英雄和 PlayerData 都会重建，不跨帧缓存引用 [m0:N42][m0 §2.7]。
  - `EntityRegistry`：移植 DebugMod `HitboxRender.CategorizeHitbox` [mod6]。
  - `FsmTap`：采集**全部** FSM 的状态及停留时间、tk2d clip/帧，发出 `FSM_TRANSITION`。
  - `SceneDumper`、`ProgressExporter`（≤2 Hz）、`CameraExporter`（V/P 矩阵）、`HudProbe`、`FrameExporter`（在 `WaitForEndOfFrame` 采样）。
  - `EventTap`：
    - TakeDamage、HealthManager.TakeDamage、EnterScene、SaveGame（含失败）、Die、工作台、拾取、`GameManager.SetState`（GameState 边沿）。
    - **所有暂停/退出阻塞源**：`disablePause`、`TimeSlowed`（postfix 挂在 `FreezeMoment(FreezeMomentTypes, Action)` 和 `FreezeMoment(float×4)`，记录类型、开始、结束）、`PreventPause`/`AllowPause`（`PauseAllowed`）、GameState、`SetIsInventoryOpen`、`UIMsgProxy.SetIsInMsg`、`GenericMessageCanvas`、`BlockingInteractable`、`acceptingInput`、`disableSaveQuit` 的变化沿（hook `PlayerData.SetBool`/`SetVariable`，按 boolName ∈ {disablePause, disableSaveQuit, disableInventory} 过滤，FSM 写入都走这两个入口）、`ScenePreloader.HasPendingOperations`、Save & Quit 按钮的 `interactable` [m0 §2.4]。
    - **每次 health/healthBlue 变化的调用栈摘要**：TakeHealth 的调用者、DoSpecialDamage、DamageTag、CriticalDamage、FSM DamageHeroDirectly、SetPlayerDataInt。
- **Guards：**
  - `SaveRedirect` + `SlotGuard` + `SaveSuppression`（`SaveGame`/`CreateRestorePoint` 返回 false）。
  - `LethalBlock`，**两张网**：
    1. 第一网：在 `PlayerData.TakeHealth` 前缀中**完整复刻 1.0.30000 的 Fractured Mask 逻辑**：蓝血先吸收；能活 = 已装备且 `AmountLeft > 0`（致命伤钳到 1 HP）；只有 `allowFracturedMaskBreak` 为真时才消耗面具 [m0:C2]。只有结算后 health 会变成 0 时才取消，并发出 `CATASTROPHE`。面具该碎就让它碎。
    2. 第二网：`HeroController.Die` 的前缀必须在内存写 Dead 之前生效（阻止迭代器创建）；另挂 `GameManager.PlayerDead`、`CheckDeathCatch`、`permadeathMode` 的写入。即使第一网漏了，也会记 `WOULD_DIE`。
    
    单元测试覆盖脚本化的尖刺、齿轮、抓取、熔岩死亡，以及 i-frame 期间撞尖刺 [m0:N1]。`CheatManager.PreventDeath` 不能代替 LethalBlock，评估时必须关闭 [m0:N43]。
  - **永不写** `timeSlowedCount`、`ignoreUnpause`、`disablePause`：oracle 只能用真实按键注入来暂停（DebugMod 的 `TIME_FORCEPAUSE` 会绕过所有门）[m0:N43]。
  - `AchievementGuard`（见 §2.7；放行 `RecPermadeathMode`）。
  - `SteelSoulSnapshot`：Steel Soul 训练槽必须开着快照才能用。
- **Harness：** `SavestateBridge`（DebugMod API [mod9]）；`StartRandomizer`（HP、丝、x 偏移、朝向、0–60 帧等待、`Random.InitState`）；`Warp`（Benchwarp）。
- **Input：**
  - `KeyboardInjector`（已实现：`oracle/src/Input/KeyboardInjector.cs` [probe:P3]）：在主线程的 `InputSystem.onBeforeUpdate`（动态更新）中每帧锁存一次按键集合，用 `InputSystem.QueueStateEvent` 向 `Keyboard.current` 排队一个完整的 `KeyboardState`，覆盖**每个**逻辑按键，包括 Esc/Enter/Tab/I/[/]。游戏走与真实按键相同的读取路径（Input System → InControl `KeyBindingSource` → `HeroActions`），按电平采样、亚帧点按丢失、边沿、LastInputType 和菜单别名都一致 [m0 §3.3]。P3 实测：全程不在前台，能从主菜单读档、暂停、取消暂停、走和跳。永不在 PlayerAction/HeroActions 层注入。
  - legacy shim（M1）：把注入的按下边沿并进 `Input.anyKeyDown` 的调用者（`InputHandler.CutsceneInput`/`StagCutsceneInput`、`GameManager.UpdateEngagement`、`IdleMemoryCleaner`），否则 TRAIN 和 FINAL 的过场跳过（含 ENDING 误跳过）和 GC 卡顿不一致 [m0:N36]。M1 实现覆盖 1.0.30000 的全部 6 个调用点（另有 PlayMaker `ActionHelpers.AnyKeyDown` 和 `BossDoorChallengeCompleteUI.Update`）。注入器占用键盘时只报告注入的按下边沿，物理 legacy 键和鼠标被屏蔽（与 Input System 一侧一致：点击聚焦训练窗口不会跳过过场）；不占用键盘时就是 `Input.anyKeyDown || 注入边沿`。
  - 后备：只作用于 Keyboard 设备、每帧锁存一次的 `ButtonControl.get_isPressed` 前缀 [mod13][pri2]。
  - `InputPathEmulator` 加观测延迟和边沿抖动（`input.latency_model`：每个 ACTION 按到达顺序抽一次延迟，动作不互相超车）。同一帧到期的多个 ACTION，每个的按键边沿都按顺序进入最短保持过滤（C19：按下和同键两次按下之间的松开都 ≥ 2 帧），不会被后到的掩码吞掉。
- **IPC：** TCP；序列化用 MessagePack-CSharp 或固定二进制结构。**只有帧时间门槛失败时才手写优化或追求零分配。**

**预算（C14）：** 主线程 p50 ≤ 0.3 ms、p99 ≤ 1.0 ms；1 h soak 中游戏帧时间 p99 相对原版 ≤ +0.5 ms（用 PresentMon 测）。

#### 3.1.2 每帧导出（`FrameLabel` = `STATE` 消息，约 2–20 KB）

```text
FrameLabel {                                   # 字段来源见 m0 §3.1
  frame u64, qpc_eof i64, fixed_update_cycle u64, fixed_steps u8, unscaled_dt/dt/time_scale/fixed_dt f32
  game_state u8, ui_state, inventory_open, hud_hidden
  cheat_flags u32 {cheat_invincibility, hero_keep_health, tools_active_state, boss_scene_controller}
  pause_blockers u16 {DISABLE_PAUSE, TIME_SLOWED, PAUSE_LOCKOUT (= !PauseAllowed), MSG_CANVAS, BLOCKING_INTERACT,
                      NOT_ACCEPTING_INPUT, GAME_STATE_NOT_PLAYING}, pause_allowed, ih_accepting_input,
  disable_save_quit, preload_pending, savequit_interactable
  scene_raw, scene_base, additive[], transitioning, memory_scene, permadeath_mode
  play_time_live f32, play_time_saved f32, session_timer f32, session_start f32   # PlayTime / playerData.playTime / 私有计时
  camera { pos, fov, aspect, viewport, V mat4, P mat4, shake_offset, mode, lock_area, look_offset }
  hero { pos, vel, facing, colliders[], cState[92] + 4 int, hero_state, anim{clip,frame,n,fps,sprite_id},
         health, maxHealth, healthBlue, silk, silk_max (= CurrentSilkMax), silk_parts, crest, tools[], tool_amounts[],
         geo, shellShards, invuln_sources[], parry_invuln_timer, is_invincible, can_take_damage,
         fractured_mask{equipped, amount_left}, bind{active,t},
         damage_tags[{kind, ticks_left, dmg_per_tick, next_tick_s}] }
  entities [ { iid, type_key, category, layer, pos, vel, gravity_scale, hp, fsms[{name,state,t}],
               anim{…}, flipX, render_aabb, colliders[{shape, verts_world, enabled, layer,
               damage{dealt, hazard_type, parryable, flags} | null}] } ]      # 视锥 + 6 u 余量内
  hud [ {elem_id, kind, rect_px, state} ]
  input { actions_pressed u32, move vec2, source }
  health_changes [ {delta, blue_delta, caller_path, hazard_type, mask_broke} ]  # 本帧发生的
}
```

#### 3.1.3 碰撞体投影到屏幕（离线，`tools/projector`）

`clip = P·V·[x,y,z_o,1]ᵀ`，NDC 按 viewport 映射到像素，y 轴翻转。始终使用保存下来的 V/P。

**每个构建做一次校准：** 打开 DebugMod 碰撞箱渲染 2,000 帧，与我们的投影比较。要求平均 IoU ≥ 0.95、顶点误差 ≤ 1.5 px。这些帧用完即删。

M1 实现（`brain/ssbot/probes/m1_projection.py` + `ssbot/tools/projection_check.py`；oracle RPC `hitbox.show`、`projection.sample`，见 `oracle/src/Train/ProjectionSample.cs`）：
- 顶点误差：`projection.sample` 在主相机 `onPreRender`（与 STATE V/P 同一时刻）对同一帧的碰撞体顶点调用 Unity 自己的 `WorldToScreenPoint`，与 projector 在该帧 STATE `cam` 上的结果比较，门槛 p99 ≤ 1.5 px。
- IoU：按颜色找出截图中 DebugMod 的线（只在它报告画线的位置附近找），填充成区域，与 oracle 标签多边形（TERRAIN 实体/危险物按碰撞体 id、STATE ents 按完全相同的轮廓、英雄 box）逐个比较；门槛取更严的 **p5 ≥ 0.95**。只比较截图前后几帧都静止的多边形（截图对应哪一帧只能确定到 ±1–2 帧）。
- DebugMod 的画法（1.1.2）决定了比较方式：在 `OnGUI` 里用 `Camera.main` 投影，此时 `CameraShakeManager` 已撤掉震屏偏移，所以震屏时它的框与精灵错开一个震屏量，比较时要把 STATE 的渲染时 V 换回无震屏的位姿；每个顶点取整到整像素；圆画成 16 边以上的折线（半径 < 64 px 时是 16 边形，对真圆 IoU 0.974）；不画 box 的 `edgeRadius`；相机渲染到缩小的 RenderTexture（CameraRenderScaled）时它按纹理像素画，框会错位。`ShowHitBoxes` 的改动只在本次运行内有效：DebugMod 只在 `Awake` 里从真实 LocalLow 的 `Settings.json` 读一次设置（早于 SaveRedirect 生效），之后的保存写进沙盒副本且不会被读回，重启即恢复 LocalLow 里的值。但重启前开着的碰撞箱会画进之后的每张截图，所以探针结束时恢复原值（中途崩溃时用 `--off`，只在 TRAIN 配置下可用，或直接重启实例）；非 TRAIN 配置把 `ShowHitBoxes` ≠ 0 当作违规。
- 门槛只统计标签形状与 DebugMod 所画形状一致的多边形（世界坐标偏差 ≤ 0.001）。英雄 box 是 `Collider2D.bounds`（可能含 Box2D 的接触皮肤），ents 的 box 含 `edgeRadius`：这类标签单独报告偏差、IoU 与 IoU(DebugMod, oracle)，不计入门槛，以免把标签定义差异当成投影误差。可比较的多边形少于 10 个（或没有 DebugMod）时判 FAIL。

#### 3.1.4 帧与标签对齐（C4）

- oracle 记录 `qpc_eof`，WGC 给出 `SystemRelativeTime`（同为 QPC 时钟）。P8 发现 `Frame.timespan` 比回调到达时刻晚约 7–10 ms（像是下一次刷新的目标时间），不能当作帧产生时刻 [probe:P8]；对齐前先用下面的互相关标定这一偏移。
- 每个捕获帧匹配"预测呈现时间 ≤ 捕获时间"的最新 `FrameLabel`。
- 用像素配准得到的相机轨迹与 oracle 相机轨迹做互相关，**偏移为 0 的帧须 ≥ 99.5%**，否则整个会话丢弃。

#### 3.1.5 标签产品

| 产品 | 来源 | 用于 |
|---|---|---|
| 威胁多边形：启用中的 `DamageHero` 碰撞体，分 {contact, attack, projectile, dynamic_hazard} | 碰撞体 + 投影 | 检测器 |
| 实体框：{hornet, enemy, npc, pickup, breakable, interactable} | render AABB + 碰撞体 | 检测器 |
| 分割 4 类：{terrain = 投影的 TERRAIN 碰撞体, hazard = 投影的静态危险物碰撞体, other, background} | 场景导出 + 投影 | 分割头；定位配准 |
| 阶段 ID（A 类 boss 和竞技场敌人） | 阶段分类体系（§3.2.6） | 阶段头 / HMM |
| Hornet 小状态（约 12 类：idle/run/air/wall/dash/attack/hurt/recoil/bind/bench/cutscene/dead） | cState + anim | 受击和 Bind 检测、一致性检查 |
| 距命中时间（ttd） | 标签序列 | ttd 头、阶段表 |
| HUD 槽位状态、屏幕模式、菜单状态（光标、Quit 是否灰色、存档槽高亮） | `hud[]`、ui_state、阻塞位 | HUD/屏幕模式 |
| 相机位姿、动作标签 | camera、input | 定位；行为克隆 |

#### 3.1.6 数据采集与规模

所有数据在冻结配置、**最终捕获路径**下采集。视频用 NVENC HEVC CQP 16，每 10 帧另存 1 帧无损。训练副本采集前：DebugMod 界面在 `Settings.json` 里关掉，Modlist 禁用或遮掉菜单左上角区域（§3.1.8 L1）[probe:P9][probe:P14]。

| 来源 | 小时 | 内容 |
|---|---|---|
| 你自己的 PC 游玩（训练副本，无 Steam 子系统，AchievementGuard 开） | 30–40 | 4–5 次 Classic 路线；1–2 个 Steel Soul 训练槽（用于 Steel Soul HUD 皮肤 [ach7]）；每次交互录一遍（交互目录的素材） |
| Savestate 训练 | 80–100 | 每个 A 类单元 ≥ 60 场、竞技场、危险物、平台 |
| 自动路线遍历 | 20 | 路线上所有场景和房间切换 |

| 数据集 | 规模 |
|---|---|
| 检测 + 分割 | 训练/验证/测试 = 250k / 25k / 25k 帧，按会话划分；跑图 4 fps、战斗 15 fps 采样；难例挖掘后战斗占 60% |
| A 类 boss 阶段 crop | 每个 boss ≥ 60 场，约 200–300k crop；每个 clip ≥ 2k |
| 竞技场敌人类型（约 30 种） | 每种 ≥ 8k crop |
| Hornet 小状态 | 100k crop |
| HUD | 300k 真实 ROI + 合成样本（面具 0–9 × 蓝血 × 丝 0–18 × 发光 × 皮肤 × Fractured Mask 状态 × 结局皮肤） |
| 屏幕模式 + 菜单 | 60k 帧，类别均衡（含暂停菜单光标、Quit 灰色、存档选择的各种高亮、模式选择） |
| 场景分类 / 定位测试 | 100k 帧，带精确位姿 |

- **存储：** 约 1 TB。现有 Samsung 980 PRO 2 TB（C:，2026-09-29 时空闲约 1,040 GB）足够撑到 M3；M6 之前加一块专用于数据的 2 TB NVMe（主板 ASUS TUF GAMING Z790-PLUS WIFI 有空余 M.2 槽，购买前核对说明书）。
- **算力：** YOLO11s 级模型在 960×544 下约 40 min/epoch，30 epoch ≈ 20 h。训练安排在不与门槛运行重叠的时间窗，或租用云 GPU。

#### 3.1.7 数据增强

- **游戏内真实多样性：** 随机起点和 RNG、不同护符与装备、两种 HUD 皮肤、暗房、特效密集的战斗、低血量状态。
- **图像空间：** gamma/亮度 ±6%、色相 ±2°、模糊 σ ≤ 0.8、噪声 σ ≤ 2/255、闪光 α ≤ 0.8、暗区遮罩、特效合成、cutout；另加**合成撕裂**，用于训练撕裂检测器。
- 只有 Switch 分支加 HEVC/4:2:0/有限色域增强。HUD 的增强只限 ±3% 亮度。

#### 3.1.8 标签泄漏控制

| # | 泄漏 | 控制 |
|---|---|---|
| L1 | mod 在画面上有叠加 | SsOracle 什么都不画。但训练副本的画面里还有别的 mod 叠加：菜单左上角 Modlist 画的版本和模组列表（`v1.0.30000-0.3.1 / DebugMod / SsOracle`，最终副本没有）[probe:P14]；DebugMod 界面默认打开，遮住大半画面 [probe:P9]。采集前在 DebugMod 的 `Settings.json` 里关掉界面；Modlist 要么禁用，要么在菜单帧用作训练数据前遮掉该区域。检查方法（CI 每个数据集构建都跑）：① DebugMod 冻结同一个 savestate 帧，分别在 SsOracle 开/关下截图，逐像素平均差 < 1/255；② 完整训练 mod 组合（按采集时的配置）对原版副本，同一静止画面（标题画面、菜单页、同一存档暂停中的画面），遮罩区域外逐像素平均差 < 1/255 |
| L2 | 作弊改变了画面 | 只取消致命一击；`cheat_flags ≠ 0` 的帧只用于检测器子集 |
| L3 | 时间统计失真 | 只用实时数据（lockstep 已移除） |
| L4 | 划分泄漏 | 按会话划分；留出房间单独报告 |
| L5 | savestate 单调 | 随机起点，混入人类游玩 |
| L6 | 标签没有视觉依据 | 用可观测阶段分类体系 |
| L7 | 策略用了特权信息 | `ObservabilityFilter(VISION_EQUIVALENT)` |
| L8 | 代码路径泄漏 | 进程防火墙 + CI import 禁令（§8） |

#### 3.1.9 Knowledge DB（离线构建，按构建版本化，带哈希）

| 产物 | 内容 |
|---|---|
| `SceneGeometry` | 按场景 × 变体（§4.3），含地形栅格（16 px/u）、剧情序列、门的进入风险 |
| `HitboxTable` | [type][clip][frame] → 碰撞多边形 |
| 阶段表、行为表 | 每种敌人（§3.2.6、§4.4） |
| 伤害表 | [com1][com2] + 扣血路径清单（齿轮、DamageTag、CriticalDamage 的来源） |
| 常量 | `constants_1.0.30000.json`：INVUL_TIME、INVUL_TIME_PARRY/CROSS_STITCH/SILKDASH/QUAKE、DAMAGE_FREEZE_*、RECOIL_*、DOWNSPIKE_INVULNERABILITY_STEPS(_LONG)、各动作预输入步数（含 DASH_QUEUE_STEPS）、MAX_FALL_VELOCITY(_WEIGHTED)、DASH_*、RUN_SPEED、固定步长、PauseAllowed 锁定时长。M0 已从 HeroController 预制体导出一版（`docs/facts/1.0.30000/hero_constants.json`，读档后坐椅子状态的实例值；纹章、工具、状态效果可能改动其中一部分，M1 起按事件逐帧导出）[probe:P11] |
| **quit map** | 每个场景 × 状态的 P(可暂停)、P(可退出)，含阻塞原因，来自 oracle 日志 |
| 覆盖图、世界图、配方、playbook、交互目录、恢复表 | §3.4–3.6 |

### 3.2 感知 II：运行时视觉 v0（正式运行）

#### 3.2.1 每帧管线（60 fps）

```
capture (WGC, GPU BGRA 1920×1080, D3D11→CUDA zero-copy)
 ├─ stream A: resize 960×544 → [Detector + Seg(4 classes)] → NMS → ROI list
 │            → [PhaseCls, class-A bosses / arena types only, ≤ 8 ROIs, 4-frame stacks] + [Hornet state head]
 ├─ stream B: 480×272 → [Localiser: seg terrain mask ↔ SceneGeometry raster]; [HUD]; [ScreenMode+Menu];
 │            [Scene classifier]; [tear detector]
 └─ CPU (numba): association → kinematics → HMM → hit prediction → fusion → WorldState
Low frequency (2 Hz): TerrainVerify (reuses seg; projects switchables), relocalisation when lost
Event-driven (timer stopped): inventory/shop reads at benches and after reloads
```

TensorRT 10 FP16、静态形状、CUDA graph。最多只有一次检测在途，总是用最新帧。

#### 3.2.2 屏幕模式与菜单读取

- **模型：** MobileNetV3-S 级，224×128 + 4 个固定 crop，约 0.2 ms。
- **类别：** PLAYING、PLAYING_HUD_HIDDEN、DIALOG、ITEM_POPUP、AREA_TITLE、BENCH、SHOP、BELLWAY_MAP、INVENTORY、QUICK_MAP、PAUSE_MENU、MAIN_MENU、SAVE_SELECT、**MODE_SELECT**、FADE、TRANSITION、CUTSCENE_VIDEO、DEATH/PERMADEATH、**ENDING**、CREDITS、**FOREIGN_WINDOW**、**MSG_CANVAS**（SAVE_FAILED/SAVE_CORRUPTED 对话框 [m0 §2.4]）。
- **菜单读取（模板 + 固定字体 OCR）：**
  - 暂停菜单：光标所在项（鼠标悬停会改变选中项 [probe:P7]）、**Quit 是否灰色**、退出确认框"保存并退出？"的高亮项（默认"否"）。
  - 存档选择：光标所在槽、该槽的游戏时间/地点/Steel Soul 标记、**Restore/Clear 是否被高亮**。
  - 模式选择：是否已有 Steel Soul 选项。
- **精度目标：**
  - PAUSE_MENU / PLAYING / DEATH：≥ 99.99%，延迟 ≤ 2 帧。
  - 其他类别 ≥ 99.9%。
  - 菜单和 UI 状态（含 Quit 灰色判断、槽位身份）：10⁴ 次菜单中 0 误读。

#### 3.2.3 场景识别与定位

- **场景 ID：** 图先验（计划走的门 → `targetScene`；**当前场景所有门的 `targetScene` 都作为候选**，以应对被击退穿门等计划外切换）+ MobileNetV3-S 分类器。切换后 ≤ 3 帧内正确，游戏帧准确率 ≥ 99.9%。
- **位姿 v0：**
  1. **先验**：房间切换后用 DB 里的 `entry_poses`；否则用重新实现的 `CameraController`（限位、`CameraLockArea`、lookOffset ±6）。
  2. **精化**：把分割出的 terrain 掩码与该场景 `SceneGeometry` 的碰撞栅格配准。相位相关求 (tx, ty)，再用 ECC 精化 (tx, ty, s)。
  3. **验证**：内点率 ≥ 0.6 且残差低于阈值时记为 `reliable`，否则只用先验并逐步放大 σ。闪光、淡入淡出、撕裂、特效密度 > 40% 的帧只用先验。
  4. **重定位**：连续 0.5 s 不可靠，或发生重生/读档/传送后，依次在预期场景、图上邻居、全局中搜索。
- **目标：** 位姿 p99 ≤ 0.08 u；严重失败（> 0.5 u）≤ 1e-4。某个房间不达标时才为它启用 §3.11 的图集/LK。
- **主动感知：** 下落前可以按住上看/下看（±6 u）。这会花计时时间，计入预算。

#### 3.2.4 地形：以 DB 为准，2 Hz 验证

- 地形、危险物、门、钩点都来自当前变体的 `SceneGeometry`，规划在世界坐标下进行。
- **验证：** 把每个 `switchable` 的开/关两种多边形投影到画面，与分割出的 terrain 掩码比较（不另加分类器）。结果用来更新 `world_flags`，并确认 Ledger 中 PENDING 的世界标志（§3.3.4）。
- **`WORLD_MISMATCH`：** 无法解释的差异 > 1.5 u² 且持续 > 1 s。处理：减速，把该区域当作未知实体，重新规划。
- **纯像素后备（D2 的"纯粹派"方案）：** 分割掩码 + 位姿积分成 8 格/u 的占据栅格。只在 DB 缺条目时使用。

#### 3.2.5 检测与分割

- YOLO11s 级模型，输入 960×544；P3–P5 头加 **P2 stride-4 头**，用于小弹丸（0.3 u ≈ 10 px）；stride-4 分割头（4 类）；每个框一个 `damaging_now` logit。
- **类别：** hornet、enemy_body、enemy_attack、projectile、dynamic_hazard、npc、pickup、breakable、interactable。`type_key` 由第二阶段的 ResNet-18 crop 分类器给出，并用场景先验限制候选。
- **攻击框的标签是投影后启用中的 `DamageHero` 碰撞体**，所以模型能学到看不见的判定框。查 `HitboxTable` 得到第二个估计，融合时取**并集**。
- **耗时：** 约 3.5 ms（p99 4.5 ms）。只有超预算、且 INT8 让每类召回下降 ≤ 0.2 pp 时才用 INT8。

#### 3.2.6 可观测阶段、HMM 与"学到的敌人规则"（你的第 1 项）

**离线，针对每个 A 类 boss 和竞技场敌人**，数据来自 `FSM_TRANSITION` 日志 [int15][pri12]：

1. 构造序列：（全部 FSM 状态、clip、帧、朝向、相对 Hornet 的位置、启用中的伤害碰撞体）。
2. 视觉 token v = (clip, 帧桶, 朝向)。计算 P(s | v) 和 H(s | v, v₋₁..v₋₃)。
3. **合并**：token 分布相近（JS < 0.2）**且**未来一致（首次伤害时间分布的 Wasserstein 距离 < 50 ms，伤害区域质心相距 < 0.5 u）的 FSM 状态合并。
4. token 相同但未来不同的状态保持分开，标注"在 token X 出现前无法区分"，并测出消歧延迟。
5. **每个阶段存储：** token、ttd 分布、敌人坐标系下随时间变化的伤害区域、能否弹反、**后续表** P(下一阶段 | 阶段, 距离桶, 高度桶, 英雄状态)、**支撑集**（所有观测到的转移 + 所有 FSM 图边；样本 < 30 时假设最快的可达攻击立刻发生）。这些表就是你要的"哪种距离出哪招"的规则。

**普通跑图敌人：** 只用检测框 + 类型 + 表中的禁入区（所有攻击的 reach 并集），不做阶段识别。

**运行时，每条轨迹一个 HMM：** 隐状态是 (clip, frame)，发射概率来自分类器 softmax，前向滤波 < 0.1 ms。输出 `PhasePost`：top-k、阶段内已过时间、`ttd_mean`、`ttd_p05`、`support_region`（安全用）、`prob_regions`（性能用）。

**目标（A 类）：** 阶段帧准确率 ≥ 98%；前摇在该状态第 3 帧时 ≥ 99.5% 正确；**攻击起始相对 oracle 延迟 ≤ 33 ms 的比例 ≥ 99%**；ttd p05 保守（≤ 真值）的比例 ≥ 99.5%。

#### 3.2.7 跟踪、轨迹预测与游戏时间

- **关联：** ByteTrack 风格，在**世界坐标**下进行，代价 = IoU + 马氏距离门限 + 类型一致性（不用 re-ID 嵌入）。轨迹最多惯性延续 0.5 s；在 atlas 前景已知遮挡物后面最多 2 s。丢失的轨迹变成**幽灵威胁**，以 3 u/s 膨胀，最长 1 s。
- **弹丸运动模型**（参数从日志拟合）：`linear`、`ballistic`、`bounce`（对 DB 地形做射线检测）、`template`（例如 Last Judge 的香炉）。
- **命中预测：** 每个弹丸 64 个蒙特卡洛样本，10 ms 步长，1.2 s 视野，对**实际执行的**英雄受击盒轨迹做扫掠，输出 P(命中) 和 `t_hit` p05。20 个弹丸 < 0.5 ms。
- **游戏时间：**
  - hit-freeze 期间时间缩放降到 0 或很低，但画面帧照常到达。英雄受击 0/0.1/0.1 s [probe:P11]，拼刀、硬直约 0.35 s，长时类型 BossDeathSlow 1.35 s（速度 0.05）、EnemyBattleEndSlow 1.85 s（0.25）、RaceWinSlow 3.8 s（0.1）[m0:N13]。跟踪器按 `t_game` 推进。
  - 检测到事件时套用对应的 FreezeMoment 配置，并用 clip 帧推进速率估计时间缩放做交叉验证。
  - **冻结期间预测也冻结。**
  - 暂停时轨迹保持不变，解除后重新验证 3 帧。
- **目标：** 弹丸到达时间 p95 误差 ≤ 50 ms，偏差 ≤ 1 帧。

#### 3.2.8 视觉干扰

| 干扰 | 处理 |
|---|---|
| 相机震动 | 设为 Off；配准会测出残余 |
| 粒子/特效 | Low；标签只来自 `DamageHero`，无害特效学成背景；增强时合成特效 |
| 黑暗 | DB 的 `darkness` 多边形抬高 σ 先验；暗房清单单独做慢速、以先验为主的通过方案 |
| 闪光 | 亮度跳变检测；配准退回先验；轨迹惯性延续；HUD 下降需 2 帧确认，闪光中不接受上升 |
| **撕裂** | 行间不连续检测 → 该帧只用先验，HUD 不更新；P8 报告各模式的撕裂率 |
| Hit-freeze | FreezeMoment 配置 + 时间缩放估计 |
| 前景遮挡 | 只用 terrain 类像素做配准 |
| 淡入淡出、对话、弹窗 | 屏幕模式冻结感知更新，只允许确认/前进 |
| 系统/Steam 弹窗、焦点被抢 | `FOREIGN_WINDOW` / `OVERLAY_INTRUSION` → 焦点守护（§3.7.6） |

#### 3.2.9 像素看不到的东西及补偿

| 看不到 | 补偿 |
|---|---|
| playTime | 计时估计器（§3.3.5） |
| 敌人 HP | 数己方命中 × 伤害；遇到阶段切换 clip 时按日志中的 HP 阈值重新锚定 |
| FSM 变量、RNG | 后续分布 + 支撑集 |
| 看不见的伤害碰撞体 | 静态的查 DB；动态的用 sprite + `HitboxTable` 求并并膨胀 |
| i-frame、冲刺冷却、挂起的 DamageTag | 事件计时器 + oracle 测得的常量；状态暗角（酸蚀/火焰/碾压）作为挂起伤害标志 |
| 屏幕外实体 | 轨迹记忆、DB 出生点、`arena_waves`、上看/下看侦察 |
| 屏幕外的世界标志 | 两阶段 Ledger + DB 谓词 + 可见时验证 |
| `disablePause`、`disableSaveQuit`、预加载 | quit map 模型（§3.7.5）；暂停菜单里直接读 Quit 是否灰色（暂停中不刷新，Options → 返回会重算 [m0:C8]） |
| 死亡是否已成定局 | 只能靠预测；事后由屏幕模式检测 PermaDeath 并停机 |

#### 3.2.10 融合

- 每帧合并：相机与英雄、实体（轨迹 + HMM）、威胁（检测器与表的并集，按 σ 膨胀）、资源（HUD、事件、库存同步、挂起伤害）、世界标志（验证 + Ledger）、计时。
- 本帧未能刷新的字段置 `unobservable` 位。
- **消费方一律用悲观界：** HP 下界、最早 ttd、2σ 膨胀后的多边形。

### 3.3 自身状态（你的第 2 项）

#### 3.3.1 英雄

- **位置：** hornet 检测框 → `sprite_id → (pivot, hurtbox)` 表精化 → 以自身按键驱动的**辨识运动学**模型（§3.5.2）→ 贴地时 y 吸附到 DB 地面 → Kalman 滤波。相对地形 p99 ≤ **0.10 u**，速度 p99 ≤ 0.5 u/s。
- **接触面、模式：** 由运动学 + 地形推出，再用 Hornet 小状态头做一致性检查（受击、Bind、硬直）。macro-F1 ≥ 0.995。
- **计时器：**
  - i-frame = 受击时刻 + `INVUL_TIME` 1.0 s 游戏时间 [probe:P11]（有 Weighted Belt 时 ×1.2，这是代码默认值，资产值待 P11 [m0:C6]；**由库存审计确认已装备才算**），用闪烁确认（闪烁从受击冻结之后开始）。`Invulnerable()` 协程按 scaled 时间计数，冻结期间 timeScale 下降，所以实时长度长于游戏时间，两者都要测。i-frame 只对 ENEMY/EXPLOSION/NON_HAZARD 有效 [m0:N1]。
  - 冲刺冷却（`DASH_COOLDOWN` 0.425 s [probe:P11]）。
  - Bind 进度；打断的判断 = clip 变化 + 丝清空 [com6]（丢丝规则待 Bind FSM 导出）。

#### 3.3.2 HUD 读取

- 区域来自 oracle 的 `hud[]`，按域（pc/switch）和皮肤（Classic、Steel、**结局 Weaver 皮肤**）分别存储。
- **每个槽两条路径：** 确定性模板 + 32×32 小 CNN，一次批处理，约 0.2 ms。两者不一致时标为 uncertain，取下界。
- **时间逻辑：**
  - HP 或丝的**下降立即接受**，其他变化需 2 帧一致才接受。
  - HUD 隐藏时保持上一值，改为事件记账。
  - 交叉验证：冻结事件、Bind 完成（+3）。低血暗角不作 HP 线索：面具完好时 `IsHealthCritical` 返回 false，不会出现暗角 [m0 §2.5]。
- **目标（C12）：** HP 高估 0 / 10⁶ 可见帧，且单次不超过 5 帧；面具精确 ≥ 99.95%；丝精确 ≥ 99.9%；`bind_ready` 保守一致 ≥ 99.99%。
- **ENDING 状态下** HUD 读取切换到结局皮肤模式，不触发 Q5。

#### 3.3.3 Fractured Mask 与挂起伤害

- Fractured Mask：优先读 HUD 指示（P10）；否则按事件跟踪：装备（审计）→ 致命命中（按模型伤害 ≥ 剩余 HP）后 HP = 1：命中不带 MidChain 标志时面具被消耗（碎），MidChain（连招中段）命中时面具**不**消耗 [m0:C2] → 修复（坐工作台）。分不清是否 MidChain 时按已碎处理。**UNKNOWN 按 BROKEN 处理。** 目标：≥ 200 次碎裂/修复事件中 100% 正确。
- **挂起伤害 `pending_dmg`：** 所有已挂上的 DamageTag（例如酸蚀）的剩余 tick × 每 tick 伤害，加上 Faydown 之前的霜冻时钟（`frostAmount ≥ 1` 后每 1.75 s 1 HP，无视 i-frame [m0:N3]）。标签栈在工作台和危险物重生后都不清除 [m0:N2]。在视觉中由状态暗角推断，并按保守上界计。它会被减进 `hits_to_death`。

#### 3.3.4 库存审计与两阶段 Ledger

- **审计：** 每个工作台、每次读档后打开库存（计时停止，世界冻结 [ach3][probe:P6]），用固定字体模板 OCR 读取纹章、**已装备工具**、能力、念珠、Shell Shards、面具和丝轴碎片、Memory Locket 数。**读档后，装备、运动学配置（Weighted Belt）、货币只以审计结果为准。**
- **Ledger（两阶段）：**
  - 每个事件写盘，初始状态为 `PENDING`。
  - 屏幕上**观测到一次保存**（坐工作台、退出淡出到主菜单、存档图标）后，`PENDING` 转为 `COMMITTED`。
  - 读档前如果没有观测到保存（崩溃、断电、退出时保存失败），所有 `PENDING` 回滚。
  - `PENDING` 状态的世界标志必须重新看到才能被规划依赖。
  - 字段覆盖：钟、站点、工作台、捷径、boss、物品、工具、纹章、碎片、丝轴、针等级、货币、Memory Locket、幕、NPC 对话标志（例如 `talked_to_garmond`）。
- 读档后丝 = 丝心数量 [local:Silk][待验证 P7]。

#### 3.3.5 计时估计器（`perception/timer`）

- **计时：** 屏幕模式 ∈ {PLAYING、PLAYING_HUD_HIDDEN、TRANSITION、房间间的 FADE、DIALOG、AREA_TITLE、ITEM_POPUP、SHOP、BELLWAY_MAP（独立面板，GameState 保持 PLAYING [m0:N20]）、QUICK_MAP [probe:P6]}；Continue 之后从第一个 EXITING_LEVEL 起（工作台场景加载和醒来动画）[m0:C7]；新游戏之后从第一个 EXITING_LEVEL 起 [m0:N23]；以及**未知状态**（保守起见计入）。
- **不计时：** PAUSE_MENU、INVENTORY、MAIN_MENU、SAVE_SELECT、LOADING（只指 Continue 的 prefab 加载段）、CUTSCENE_VIDEO（含 Bellway 乘车视频 [m0:N21]）、CREDITS。
- **校准：** 每次读档后在存档选择界面 OCR "Xh YYm"：显示值向下取整，比实际少 0–59.99 s，所以显示值本身就是下限 [m0:N25]。估计值 = max(当前估计, OCR 下限)。结局时如果看到 End_Game_Completion 的 `Hh MMm SSs`，用这个秒级读数校准估计器。
- **验证：** 每局低估 ≤ 30 s、高估 ≤ 300 s。调速器用"估计 + 3σ"与 17,400 s 比较。

### 3.4 地图、导航与定位（你的第 3 项）

#### 3.4.1 世界图

- **数据来源：**
  - Silksong.Benchwarp（1,508 个门、81 个工作台、590 个场景）[mod10]
  - Archipelago `entrance_pool.json`（632 条边）+ `room_graph_data.json`（DNF）[int19][mod11]
  - zerounit AP 逻辑 [VER]
  - ItemChanger/silksong-data-dump 坐标和商店价格 [mod12]
  - HKSplitMaker `any-bells.json`
  - **oracle 运行时导出的 `TransitionPoint.targetScene/entryPoint` 为权威** [int21]，其他来源都与它交叉核对。
- **节点和边：** 节点 =（场景，门 | 工作台 | 站点 | 商店 | NPC | 物品 | 交互点）。边 =（场景，门，谓词），类型有 walk/drop/door/lift/bellway/ventrica/oneway。
- **谓词**在视觉模式下对 Ledger 求值（只用 COMMITTED，或已重新看到的 PENDING），在 oracle 模式下对 PlayerData/SceneData 求值 [int22]。
- **变体层：** Act 1/2、`_caravan`/`_festival`、`_Destroyed`、Steel Soul 差异 [ach7]。
- **世界变化** = 谓词翻转 + 变体几何；到场后由验证确认，矛盾时重新规划。
- **实体表：** 工作台、带库存/价格/前置条件的商人、任务 NPC 和物品、Bellway/Ventrica 站点（费用 [int24]）。
- **永远不需要买地图或读游戏内地图** [int27]。

#### 3.4.2 规划

- **全局：** 在（场景，门）上做 A*，代价 = 实测时间 p50 + 风险代价。**Wardenfly 标记的边在"已有 Cling Grip 且无 Faydown"期间代价为 ∞。** 尽量减少房间切换。
- **局部：**
  - 在 DB 碰撞体上对运动原语做 A*，使用辨识出的运动学 [pri11]。
  - 原语：跑、跳（按住 2/4/8/12/max 帧）、蹬墙跳、冲刺、滑翔、Clawline、按纹章的下劈弹跳。
  - 危险物代价 ∞ 并加缓冲区。
  - **h ≤ 2 时，门的多边形作为软危险物**，击退包络不得穿过。
- **配方：** 每条已验证的门到门路径闭环执行，带检查点。**必须 50/50 通过才能启用。**
- **门的进入风险表：** 由出生点导出建立。发生计划外切换后，保持只躲避的策略，直到场景和位姿都可靠。

#### 3.4.3 Wardenfly 策略 [spe13]

- 标记边在上述期间不可行（不是"加罚分"）。
- **原 S16（Marrow ↔ Deep Docks 碎片）默认删除**；只有图证明能在 S12 之前拿到时才提前。
- 刷钱循环不得经过标记场景。
- 如果 Act 2 路线必须走标记边，Faydown 改为**必选**，其获取段和代价由 M5 的数据决定。
- **捕获检测器**（抓取 clip，或场景 = The Slab）→ 停止所有输入，报警，不即兴处理。捕获后退出的行为由 P16 确定。

### 3.5 战斗（你的第 4 项）

#### 3.5.1 层次

| 层 | 频率 | 职责 | 实现 |
|---|---|---|---|
| L3 遭遇 playbook | 每场 | 前置条件、配装、阶段脚本、安全口袋、Bind 窗口、变体 | YAML（§4.4），人工审阅 |
| L2 战术 | 10 Hz + 事件 | 模式（ENGAGE/KITE/HEAL/HOLD/EVADE/TRAVERSE/BAIT）、允许的原语、目标优先级 | 规则表 |
| L1 规划器 | 60 Hz | 在威胁管道上做短视野搜索 | 基于辨识运动学的 rollout |
| L0 安全过滤器 | 60 Hz | 否决违反不变式的计划；危险物即墙 | 规则 + 单元测试 |
| 监督器 | 60 Hz | 风险档、PAUSE_PENDING、暂停/退出 | §3.7 |

#### 3.5.2 英雄运动学（从日志辨识，不靠猜）

- **模型：** 混合模式（地面、空中、墙、冲刺、滑翔、攻击后坐、下劈、受击后坐、Bind）；物理子步 0.02 s（50 Hz，已实测 [probe:P11]），控制频率 60 Hz，每帧 0–2 个物理步。
- **击退包络：** 冻结 + 后坐期间，任何输入下所有可达位置，方向背离伤害来源；装备 Weighted Belt 时减半（代码默认 ×0.5 [m0:C6]，**以审计确认已装备为准**）。装备后最大下落速度改用 `MAX_FALL_VELOCITY_WEIGHTED`，RecoilDown 时向上速度减半，要单独辨识。
- **执行流建模：**
  - rollout 基于**实际执行的**命令流：最短按住之后的结果，加上在最终路径上实测的帧时间抖动模型。
  - 在 TRAIN 中辨识，**再用 REHEARSAL-SEG 的实时 + 最终 sink 数据验证**。
  - 实测的"按住时长 → 跳跃高度"方差加进危险物余量。
- **验收：** 99% 的原语序列在 0.5 s 后预测位置误差 ≤ 0.1 u；运行时残差监视器把结果报给监督器。

#### 3.5.3 威胁预测：支撑 vs 概率

- **每个攻击 A 离线计算：** 时空判定模板；`reach_union(A)`（支撑）；瞄准模型（仅概率）；`tell_lead_vision(A)`（从视觉能确信看到前摇到判定生效的时间，在影子模式中测得）。
- **逃离时间** `esc(A, x)`。
- **可反应：** 当 `tell_lead_vision ≥ L + esc + 2 帧` 时，可以等前摇再动；否则按**位置处理**，敌人处于任何能在前摇时间内发出 A 的状态时，都不进入膨胀后的 reach。
- **管道：** 观测管道 + 预测管道（在支撑集上按 p0.5–p99.5 时长分支）。
- **膨胀余量：** `m = 0.15 u + k·σ_perception + L 期间的英雄漂移 + 按住高度方差`。

#### 3.5.4 规划器

```
every frame:
  if committed_primitive.active and not abort_needed: continue its hold schedule   # 按住时序在按下时就承诺
  s     = state_at(now + L)                          # 在已执行的命令流上前推（最短按住 + 抖动）
  tubes = forecast(s, H = 0.8 s)                     # 每条管道：in_support + p
  mode, prefs = tactics(s, tubes, supervisor_flags)  # PAUSE_PENDING / YELLOW 会裁剪原语
  C = expand(s, prefs, depth=3, dt=4 frames)         # 150–600 个候选（含显式 ABORT 原语）
  for c in C:
      roll = kin.rollout(s, c)
      Hz(c) = roll ∩ hazards ≠ ∅ or knockback_envelope(roll) ∩ (hazards ∪ soft_gates if h≤2)
      S(c)  = any(roll ∩ tube for tube in tubes if tube.in_support)
      U(c)  = roll 经过"不可暂停/不可退出"窗口（含解除暂停后 0.3 s 实时）时按 I3 加严
      V(c)  = viable_continuations(roll.end) >= 2
      P(c)  = Σ tube.p · overlap(roll, tube)
      J(c)  = 惩罚窗口伤害 + 丝 + 诱敌位置 + 节奏
  pick lexicographically: not Hz > not U > S = 0 > V > min P > max J
  no candidate with S = 0 → pick min P, emit FORCED_RISK
  emit; replan next frame (≤ 512 rollouts × 48 steps, numba, p99 ≤ 3 ms)
```

- **原语：** MOVE、JUMP(hold)、DOUBLEJUMP、DASH、WALLJUMP、GLIDE、ATTACK(side/up/down)、TOOL(i)、SILKSKILL(k)、CLAWLINE、BIND、WAIT、**ABORT**。每个都做合法性检查。
- **"什么时候按哪个键，取决于地形、敌人数量和类型"的答案：** 地形通过碰撞和危险物进入，敌人数量和类型通过管道和战术表进入。

#### 3.5.5 战术、诱敌、目标优先级

```yaml
- enemy: LastJudge
  when: {attack: LJ_SLAM, phase: P1}
  do: [EVADE(axis: x, clear: reach+0.5u), PUNISH(window_from: "Slam Recover", max_hits: auto)]
  forbid: [BIND, PARRY]
- enemy: Lace2
  when: {state_prob: {"Guard*": ">0.02"}}
  forbid: [MELEE]            # 反击为 1+1 [com9]
  do: [HOLD, TOOL(ranged)]
```

- **诱敌：** 选择使"最可惩罚攻击的概率 × 窗口"最大的距离带；风险是约束，只用于性能。
- **群战：** 先杀偷丝者（Clawmaiden），再远程、近战、坦克。6 u 内 ≥ 3 个敌人时，先调整站位让它们排到同一侧。

#### 3.5.6 Bind、弹反、下劈、危险物、伤害模型扩展

- **Bind 提交条件（全部满足）：** 丝 ≥ 9；HP ≤ max − 3 或 hits_to_death ≤ 2；`T_min ≥ T_bind + δ_b`（1.37 s，带 Injector Band 0.89 s；δ_b = 0.15 s + 感知余量）；不在会塌的地面上；击退包络内无危险物；**不处于 PAUSE_PENDING**。
- **Warding Bell**（审计确认已装备才算）：δ_b 可降到 0.05 s，允许 ≤ 5% 概率暴露。铃挡住的敌人命中伤害为 0，但击退和 i-frame 照常发生，击退包络照算；铃不挡危险物 [m0 §2.5]。
- **保留 Bind 用丝：** HP < max 时丝永不低于 9；丝技能只在满血时用。
- **补丝：** 丝 < 9 时，A/B playbook 开打前补丝，最长 90 s。
- **弹反白名单**（全部满足）：日志里观测到过拼刀；视觉 G1 成功率 ≥ 99.5%；弹反失败不靠面具也能活（HP − D ≥ 2）。**Lace 防御姿态时永不出手。** YELLOW 档和 PAUSE_PENDING 中禁用弹反（拼刀冻结会吞掉暂停）。弹反 i-frame 只有 0.15 s，且挡不住危险物 [probe:P11][m0:N1]。
- **下劈：** 用每个纹章的下劈多边形 [com8]；下劈 i-frame 8 步（长版 16 步），只挡 ENEMY，不挡 EXPLOSION、危险物和 noBounceCooldown 伤害源 [probe:P11][m0 §2.5]；落空的轨迹也必须在支撑下安全且无危险物；永不在尖刺上下劈。
- **危险物：** 任何 HP 下都是 ∞ 代价的墙。当 HP − D1 ≤ 危险物伤害时，击退包络不得碰到危险物。热地面宽限 0.7 s（Magma Bell +2 s）。危险平台只在支撑中无敌人且 HP ≥ 3 时进入。
- **伤害模型扩展：**
  - `pending_dmg` 计入（含霜冻时钟）。
  - **齿轮碾压**：触发后 0.35 s（scaled）结算 1 格 SPIKES 伤害 + 一次危险物重生，穿透 i-frame 和弹反，仍然硬避 [m0:C3]。
  - **CriticalDamage 来源**：在支撑中记为"h → 1"（不消耗面具）。
  - 抓取类：`mask_covers = False`。barnacle 抓取不看 i-frame，后坐结束后、i-frame 结束前就能生效，不能进入"受击后"的计划 [m0:N4]。
  - 用 oracle 调用栈清单核对每个 A/B 单元是否有表外的扣血路径。

#### 3.5.7 竞技场与 A 类 playbook

- **波次脚本**来自日志；每波出现前预先站进**安全口袋**；在实测的波间空隙 Bind。
- **覆盖图** = 敌人可达位置上所有可达判定的并集，其补集就是可核验的"安全点"。
- 助战者（Garmond & Zaza、Shakra）是单独的检测类，它们的攻击永远不算威胁。

| 单元 | 要点 |
|---|---|
| **Fourth Chorus**（S08，默认开打，A 类） | 手的攻击为 2 格。研究结论是不依赖 Fourth Chorus Skip [spe 隐含]。只有当跳过方法是 NMG 允许的非帧精确移动、且配方 ≥ 99.5% 零伤害暴露时才改为跳过。 |
| **Last Judge**（S17） | 前置：Magma Bell + Fractured Mask + Weighted Belt，满血，丝 ≥ 9。第一招固定是香炉投掷，开局闪避预先规划。P1：Slam 在悬停时离开 reach，落地后惩罚；Throw 靠近或远离，跳过回程的球；Spin 待在半径外。P2：穿过 Blazing Rings，避开 Exploding Throw，跳过 Searing Slam 冲击波和 Pillar Charge；香雾是一级火焰前摇。216 HP 时 Judgement：约 5 s 光环后力竭，Bind 和惩罚窗口预先登记。死亡后退到爆炸半径外，2 s 内无伤害威胁才算结束。 |
| **Cogwork Dancers**（S19） | 两个本体、两套管道；接触 2；Configuration/Clash 为 1+1。有 Ascendant's Grip 时贴角挂墙 [待验证]，否则用口袋 + 远程工具。 |
| **G&Z 切磋**（S21，**B 类且有危险物**） | 下方尖刺 = 危险物；I2 适用；Q 触发全部保持生效；远离边缘作战。 |
| **Forum 连战**（S25） | 前置：G&Z 助战（Ledger 标志须是对话观测确认的 COMMITTED）、Cogfly 已合成、7 面具。先杀 Clawmaiden；最后 2 只 Choir Clapper（230 HP，全部 2 格，交替出手）按 boss 对待，用口袋 + Cogfly 输出。**后备 playbook**（只用 Cogfly、无助战）在 G1 中单独测量；标志缺失时自动切换。 |
| **Lace 2**（S26） | 800 HP。针挥为 1+1（D1 = 2）。防御中不近战，只做远程；只在收招时惩罚。Fractured Mask 在连招最后一击时碎。 |
| **GMS**（S27） | 攻击 2；尖刺平台 1（危险物）。Silk Web 1+1+1 抓取是否被面具覆盖未知，所以只要它在支撑中，就要求**不算面具**的 HP ≥ 4。击败后进入 ENDING 状态（§3.6.1）。 |
| Bell Beast、Lace 1、Widow、Trobbio | 标准模式，从日志填表和 playbook。 |

#### 3.5.8 学什么，不学什么

| 组件 | 方法 | 用途 |
|---|---|---|
| 行为表 | 计数、Dirichlet 平滑、分位数 | 支撑 + 概率；n < 30 时按最坏情况 |
| 攻击模板、reach 并集 | 碰撞体聚合 | 支撑（按 p99 残差膨胀） |
| 瞄准模型 | 回归 | 仅概率 |
| 运动学 | 系统辨识 | 支撑 + 运行时残差监视 |
| 感知 | oracle 标签监督学习 | 带校准置信度的输入 |
| 战术权重、余量 | 在 savestate 批次上做 CMA-ES / 贝叶斯优化 | 仅性能，碰不到不变式 |

**永不学习**（手写、有单元测试、人工审阅）：不变式、hits_to_death、危险物处理、Bind 提交测试、交战门、紧急流程、quit map 的使用、结局动作。学习型战术选择器（BC/PPO/DAgger）移到 §3.11。

### 3.6 路线执行器

#### 3.6.1 运行管理器与 ENDING 状态

- **状态机：** `MENU`、`TRAVEL`、`COMBAT`、`INTERACT`、`WAIT`、`RECOVER`、**`ENDING`**、`STOPPED`。
- **章节：** 整局切成若干章，每章结束于"坐工作台保存 + 退出到菜单"，每章开始前跑预检（§3.10）。**最后一章（S26–S27）开始前**：重启 Steam 并确认在线 → 重新启动游戏 → 预检以 Player.log 为准：必须有 "Selected online subsystem SteamOnlineSubsystem"、"Steam logged in as"、"Steam stats received."，且没有 "Steam failed to initialize" 和 "Steam shut down." [m0:N27][m0:N28] → 操作员在决策回路之外复核这几行。Extras → Achievements 界面**不能**作为 Steam 收到成就的证据：Steam 缺席或返回 null 时它退回 shared.dat，本机推送过的成就在两种情况下显示相同 [m0:N35]，P14 已确认不能区分 [probe:P14]。它最多作画面参考，不参与预检和结局核对。
- **ENDING：** 同时满足两个条件才进入：检测到 GMS 击败线索（模板来自 oracle 记录的击败序列）**且**看到 Bind 提示。进入后：
  - Q1–Q6 和死人开关解除，只保留 PERMADEATH 和崩溃检测。
  - HUD 切换到结局皮肤模式。
  - 唯一允许的动作是交互目录里脚本化的 BIND（绕过战斗 Bind 测试；永不按 Needolin）。
  - 之后 `neutral()`，零输入，直到看到 MAIN_MENU。零输入覆盖所有来源：跳过监听 legacy `Input.anyKeyDown`（含鼠标）和手柄，OS 级按键同样会跳过当前子序列 [m0 §2.1]。
  - 然后停机：Player.log 中 STEEL_SOUL 和 SPEEDRUN_1 都要有 "Steam achievement X (a/b) upload complete"（只有 "Pushing achievement" 不算）[m0:N27]，再请你在 Steam 个人资料页确认两个成就，确认前不动存档。不以槽位时间判断成败：片尾后的保存会把检查之后的时间也 flush 进去 [m0:C18]。
- **结局预演：** GMS → Bind → 片尾 → 主菜单，在训练副本上用最终 sink 和纯屏幕 MenuDriver 预演 ≥ 5 次（G3 的一部分）。

#### 3.6.2 MenuDriver（槽位安全）

- 每一步都由屏幕模式和菜单读取验证。
- **白名单：** 只允许聚焦"槽 N"和 Steel Soul 新游戏控件。一旦 Restore 或 Clear 被高亮，立刻 Cancel 并重新验证。**永不在 DEFEATED 槽上按 Submit**：它只显示 Clear，两次 Submit 就删档 [m0:N31]。**FINAL 配置中删除/清除动作被编译掉。**
- **导航：** 每次 Submit 前读高亮项，不按计数导航：灰色 Quit 会被跳过并回绕 [m0:N17]，鼠标悬停也会改变选中项 [probe:P7]。菜单里不得出现游戏键：键盘下 Z = Submit，X/A = Cancel [m0:N16]。
- **按 Enter 前：** OCR 槽 N 的游戏时间和地点，并检查 Steel Soul 标记。
- **槽位文件只在游戏未运行时放入或移出：** 主菜单打开之后才放进存档目录的存档，存档选择界面看不到；选中该槽时游戏把它当空槽，静默开始一局普通模式新游戏 [probe:P5][m0:N30]。所以每次进入存档选择界面都先读出槽位内容再操作。
- **读档后：** 2 s 内必须识别出 Steel Soul HUD 皮肤，否则退出。
- **新游戏：** 在空槽按 Submit 之前确认当前存档目录已解锁 Steel Soul：未解锁时不会出现模式菜单，而是直接静默开始 Classic [m0:N30]（没有才输入代码，**FINAL 中永不输入**）。全新注册表下会先弹出 overscan 和亮度校准菜单，要先处理。然后确认 Steel Soul 确认画面和第一帧游戏 HUD（钢铁面具皮肤）；60 s 内任何一项不对就中止。
- **每次退出：** 按 §3.7.5 步骤 4 的退出序列执行。按"是"后约 0.5 s 仍停在确认框且没有开始淡出 = Patch 4 拒绝（`disablePause` 或 `disableSaveQuit`）：保持暂停，重查标志，绝不盲目解除暂停。出现 SAVE_FAILED 对话框 = 保存失败：游戏停在 PAUSED，但 `PauseAllowed` 一直为 false，Continue、Cancel、Esc 全都无效，世界冻结，按 §3.6.8 处理 [m0:C9]。重走 Esc 循环没有任何效果。
- **MenuDriver 误删或误恢复槽位**属于基础设施事件，用章节前的备份恢复（写入 D3）。

#### 3.6.3 交互子系统（`run/interact/` + 交互目录）

- **目录：** `knowledge/1.0.30000/interactions/*.yaml`，每条包含 {id, 场景, 锚点, 前置条件, steps: [(输入, 预期画面/模板/OCR 文本, 超时)], 成功谓词, 恢复}（§4.4）。预计 80–150 条。
- **来源：** 你自己的 PC 游玩（D12）+ oracle EventTap 的对话/商店/工作台/物品事件。每个交互先录一遍，再写成脚本。
- **覆盖范围：**
  - (a) Grand Gate 前演奏 Needolin（5 钟之后）；Dancers 雕像处为 Threefold Melody 演奏 Needolin。
  - (b) 敲响 5 座钟；Greymoor 钟的伏击屋。
  - (c) NPC 对话和 Yes/No：Seamstress、Mottled Skarr、Pebb、Plinney、合成、Garmond、Forum 外的 G&Z 助战请求、**许愿板**——只接受目录中列出的愿望，**永不接受 "A Vassal Lost"**。
  - (d) 商店：**按 OCR 出的名字选择，不按序号**。
  - (e) 纹章/工具装备格：按图标模板定位，布局随工具获取和 Hunter 进化而变。
  - (f) Bellway/Ventrica：付费解锁；目的地按 OCR 或模板选择，光标顺序由已解锁站点计算并验证。
  - (g) 能力获得序列、首次使用教程卡、物品弹窗、面具和丝轴补满。
  - (h) 拉杆、钥匙门、升降机、跳蚤笼、Sacred Cylinder → Vaultkeeper's Melody、Architect's Melody 解谜（从 oracle 日志得到解法，写成脚本）。
- **新增原语：**
  - `INTERACT(UP)`：提示图标可见时点按 UP ≤ 100 ms，与"长按上看"区分。
  - `NEEDOLIN_PLAY(duration)`。
  - `HIT_TARGET(lever|bell|cage)`。
- **规则：** 每一步闭环验证；任何 Yes/No 默认 **Cancel**，除非条目另有规定；失败最多重试 2 次，之后把 Ledger 标为 UNCERTAIN 并重新规划。
- **退出标准：** 每条路线交互在 SHADOW 视觉下 20/20，在原版副本上 3/3。

#### 3.6.4 路线：1.0.30000 上的 Bell / Last Judge 路线（修订）

A 类 = 以 2 格攻击为主的 boss 或连战；B 类 = 竞技场、小 boss、危险平台；C 类 = 跑图。P50/P90 是游戏内秒数的**人类谨慎节奏先验**，会被实测值替换。✚ 表示安全绕路。

**路线表由数据生成：** 用图路径计算每段访问的场景，并断言段内每个物品、NPC、商店都在访问过的场景里（silksong-data-dump/ItemChanger 坐标 [mod12]），不一致就让构建失败（`tools/route_check.py`）。

| # | 段 | 内容 | 类 | P50 / P90 |
|---|---|---|---|---|
| S01 | Moss Grotto → Moss Mother | 60 念珠箱、工作台 | B | 300 / 420 |
| S02 | Bone Bottom、Mosshome → Silk Spear | 第一个竞技场；✚ 碎片（位置以数据为准） | B | 480 / 660 |
| S03 | Marrow → Bell Beast + Marrow Bell | 丝心 1 | **A** | 360 / 540 |
| S04 | Marrow/Bone Bottom 扫荡 | 工艺金属 1、✚ Straight Pin、跳蚤、✚ 丝轴碎片；**✚ Pebb 碎片（Bone Bottom，300）**：如果 P10 收入投影允许就在此购买，否则 S13 前经 Bellway 回 Bone Bottom 购买（+120 s） | C | 240 / 360 |
| S05 | → Swift Step | 竞技场 | B | 300 / 420 |
| S06 | Deep Docks | Bellway 40、竞技场、✚ Magma Bell（110 + 1 工艺金属）、Sting Shard | B | 420 / 600 |
| S07 | Lace 1 + Deep Docks Bell | 250 HP | **A** | 300 / 480 |
| S08 | Far Fields | 站点 40、Drifter's Cloak、✚ 碎片、✚ Warding Bell；**Fourth Chorus（默认开打）** | **A** | 900 / 1,260 |
| S09 | Pilgrim's Rest | ✚ Weighted Belt 160、Tool Pouch、**Memory Locket #1** → 红槽 2 | C | 180 / 300 |
| S10 | Hunter's March（**必须早于首次进入 Greymoor/Bellhart/Shellwood**） | 竞技场（Shakra 助战）、**Memory Locket #2** → 蓝槽 2、✚ Fractured Mask 260（在该工作台休息前买 [待验证原因]） | B | 600 / 840 |
| S11 | Greymoor → Greymoor Bell | 伏击竞技场、爪形陷阱区（绕过面具）；**与 Garmond 对话**（Ledger 标志，对话观测验证）；Moorwing 通过跳蚤商队跳过 | B | 540 / 780 |
| S12 | Shellwood | 竞技场、✚ 碎片、Sister Splinter（默认跳过，被迫开打则为 A）、Cling Grip | B | 600 / 900 |
| S13 | Bellhart | **Widow** → Needolin + Bellhart Bell；✚ Needle 1；✚ Memory Locket #3（可选购买） | **A** | 480 / 720 |
| S14 | Shellwood Bell | — | C | 180 / 300 |
| S15 | ✚ Weavenest Atla | Hunter 进化、碎片、丝轴碎片 | B | 480 / 660 |
| ~~S16~~ | ~~Marrow ↔ Deep Docks 碎片~~ | **已删除**（Wardenfly），碎片缺口由 Act 2 补 | — | — |
| S17 | Blasted Steps → Grand Gate（交互：Needolin）→ **Last Judge** → Citadel（Act 2） | 路上有 Steel Soul 变体房间 | **A** | 600 / 900 |
| S18 | Citadel → Choral Chambers、Songclave | 工作台、站点；✚ Memory Locket（拾取）；S11 没对话时在此与 Garmond 对话 | C | 420 / 540 |
| S19 | **Cogwork Dancers** | — | **A** | 420 / 660 |
| S20 | ✚ Cogwork Core 西侧连战碎片、捷径、Jubilana | — | B | 360 / 540 |
| S21 | Whispering Vaults | 竞技场、✚ 碎片、✚ Pale Oil、**屋顶捷径**、✚ **G&Z 切磋**（B，有危险物） | B | 780 / 1,020 |
| S21b | ✚ Bellhart：Plinney → Needle 2（带 Pale Oil 回去） | — | C | 240 / 360 |
| S22 | **Trobbio** | Magma Bell A/B 测试 | **A** | 360 / 600 |
| S23 | Underworks | Clawline + 竞技场、Crafting Kit、Sacred Cylinder → Vaultkeeper's Melody；熔岩 | B | 780 / 1,080 |
| S24 | Cogwork Core 解谜 → Architect's Melody | 交互目录中的解法 | C | 420 / 600 |
| S25 | High Halls → ✚ Cogfly → **Forum 连战** → Conductor's Melody | — | **A** | 780 / 1,200 |
| S26 | Threefold Melody（Needolin）→ **Lace 2** → Lace 后竞技场 → Cradle 工作台 | — | **A** | 660 / 1,020 |
| S27 | **GMS** → **Bind** → 片尾 | ENDING 状态 | **A** | 420 / 600 |
| | **核心合计** | Act 1 ≈ 6,960，Act 2 ≈ 5,640，**≈ 12,600 s** | | |

- **面具算术：** 对 2 格 boss 且有 Fractured Mask 时，死亡前能挨的击数：5 面具 → 4、6 → 4、**7 → 5**。7 面具需要 **8 个碎片**（Act 1 拿 5–6 个 + Act 2 拿 2–3 个），**在 Trobbio 之前**凑齐。
- **绕路排序：** 价值 = （下游风险降低 − 自身风险）/ Δt，在 G1 中用 A 类 savestate 做 A/B 测量。
  - **必留：** Fractured Mask、Weighted Belt、Warding Bell、Magma Bell、Memory Locket #1/#2、Needle 1、Cogfly、G&Z（Garmond 对话 + 屋顶捷径 + 切磋）。
  - **调速器压力大时才舍：** 7 面具碎片、Needle 2、Straight Pin。
  - **最先舍：** 丝轴碎片、Sting Shard、Ascendant's Grip、Memory Locket #3。
  - **仅 A/B，默认不做：** Faydown（除非 Wardenfly 迫使）、Injector Band、Pollip Pouch。
- **Fourth Chorus、Moorwing、Sister Splinter 的打/跳决定**在 M1 前由你的游玩和社区路线定下；凡是要打的 boss 都算 A 类，配 playbook 和门槛。
- **永不交战：** Savage Beastfly、Skull Tyrant、Great Conchflies、Forebrothers、Groal、First Sinner、Summoned Saviour、Lumble 的骰子、所有 Act 3 内容。
- **永不做：** 装 Barbed Bracelet；去 Mount Fay 取 Memory Crystal（Act 2 路线外，只在受击时触发，爆炸可能引发 Lace 等的弹反反击 [research/crests.md]）；启动 Rite of Rebirth；在 GMS 竞技场按 Needolin；NMG 禁止的 glitch 或帧精确跳过。

#### 3.6.5 配装、槽位可行性与经济

- **纹章：** 默认全程 Hunter（S15 进化为 Hunter_v2）。Wanderer 和 Reaper 是 A/B 候选，K1（M2 结束）用 S15 之后的 boss savestate（Last Judge、Lace 2，另加 Forum、Widow）比较**纹章 + 配装的组合**，每组 ≥ 200 次随机起点：先看 WOULD_DIE 上界和险情率，击杀时间次之；纹章可在工作台按 playbook 切换，结论可以按 boss 选。Wanderer 的取得（S12 后经 Cling Grip 进 Bonegrave 的 4 波竞技场，死亡为真死；或 500 念珠买 Simple Key 提早拿）、数值和代价见 [`research/crests.md`](research/crests.md) [asset][code]（2026-09-30 调研，起因是你的建议：漫游攻速快、丝多、弹刀多）。
- **槽位（Hunter：红/蓝/黄各 1 个已解锁 + 1 个锁定）：**
  - Locket #1（S09）→ 红 2：Straight Pin + playbook 工具。
  - Locket #2（S10）→ 蓝 2：Fractured Mask + Warding 或 Magma Bell。
  - 黄：Weighted Belt。Locket #3（可选）→ 黄 2。
  - **配装规划器做槽位可行性检查**：playbook 要求的装备在槽数不够时构建失败。
  - **监督器的上下文**（火焰 D1、Warding Bell 规则、击退减半）**只从审计确认的已装备工具推出，不从 playbook 推出。**
  - 只在工作台换装。
- **经济（三种货币）：**
  - **念珠：** Magma Bell 110 → 站点 → Weighted Belt 160 + 入场费 → Fractured Mask 260 → Pebb 300 → Bellhart 站 60 → Needle/Locket #3 等。合计约 1,200–1,600。
  - **Shell Shards：** 需求 = 每把红色工具的补充费用 × 预期休息次数（含 P90 退出次数）。
  - **工艺金属：** 预留 2 块（Magma Bell、Cogfly）。
  - 每段收入取 oracle 路线实测的 P10。预计短缺时跑预先勘测好、远离 Wardenfly 场景的刷取循环，时间由调速器定价。
  - 紧急退出后念珠是否保留 [待验证 P7]。
- **交战门：** 工具 ≥ playbook 最低要求；不足时自动选保守变体，不阻塞等待。

#### 3.6.6 时间预算 v2 与调速器

| 项目 | 秒 |
|---|---|
| 核心路线（Σ P50，人类谨慎节奏） | 12,600 |
| 交战门的工作台回撤 | 700 |
| 补丝循环 | 500 |
| 侦察、保守等待 | 300 |
| 刷念珠/壳片（P50） | 300 |
| 紧急退出恢复：约 4.5 次 × 380 s。380 s 是 C7 之前的估计，**尚未包含** Continue 后工作台场景加载 + 醒来的计时部分 [m0:C7]（取决于硬件）；P7 测出后按每次退出加上。在此之前本行和下面的合计都是暂定值 | 1,700（暂定） |
| **期望合计** | **≈ 16,100** |
| σ | ≈ 1,300 |
| P(≤ 17,400) | **≈ 0.84** |
| **维持单局所需的目标** | 开销 ≤ 1,200、退出 ≤ 3 次 → 期望 ≤ 15,300，P ≥ 0.95 |
| 调速器硬上限 / 成就上限 | 17,400 / 18,000 |

| 检查点 | 在…之后 | 期望 | 告警（≈P95） | 告警动作 |
|---|---|---|---|---|
| CP1 | S10 | 5,100 | 6,300 | 舍弃第 3 档绕路 |
| CP2（= K3 测量点） | S17 | 8,700 | 10,300 | 继续舍第 3 档；Needle 2 或 G&Z 只在实测价值低于阈值时才舍 |
| CP3 | S22 | 12,000 | 13,800 | 舍弃剩余所有可选绕路 |
| CP4 | S25 | 14,700 | 16,300 | — |
| CP5 | 片尾 | 16,100 | 上限 17,400 | — |

- **调速器：** 每个段边界对剩余段的分布（含退出）做蒙特卡洛，估计 P(T ≤ 17,400)。< 0.95 时按顺序舍弃绕路；舍完仍 < 0.5 时切换到**只保钢铁之魂模式**（D4）：时间权重归零，恢复所有安全绕路。
- **K3（oracle Act 1 实时实测）：** Act 1 实测（含退出模型）≤ 8,700 s，且 MC P(T ≤ 17,400) ≥ 0.9（Act 2 先验按 Act 1 实测/先验的比例缩放），才维持单局；否则带着数据请你做 D4'。
- **视觉 Act 1（M6）复核：** SHADOW 下 Act 1 ≤ 9,000 s（含退出）。

#### 3.6.7 进度看门狗

- **触发条件（满足其一）：** 自上一检查点起的计时时间 > 该段 P99 × 1.3；或连续 120 s 计时时间内没有到达新的图节点。
- **动作：** 暂停（不花时间）→ 导出诊断 → 报警。只有你手动恢复，或重新规划通过检查后才继续。G3 中每次卡住都算失败。

#### 3.6.8 恢复表（`run/recover/`）

每一行是（检测 → 动作 → 退出检查），每行在 REHEARSAL 中做故障注入测试（默认每行 20 次）。

| 情形 | 检测 | 动作 | 退出检查 |
|---|---|---|---|
| 游戏进程崩溃/挂起 | 进程退出、窗口消失、帧源 > 2 s 无帧 | 重启固定副本 → 校验 DLL 哈希 + OCR 版本 → 继续预留槽（模板 + OCR）→ 审计 → Ledger 回滚/对账 → 从重生工作台继续 | 90 s 内在预期工作台场景看到 PLAYING |
| GPU TDR / 捕获 ACCESS_LOST | 帧源异常 | 暂停循环 → 重建捕获 → 自检 | 自检通过 |
| 走错门 / 被击退穿门 | 场景 ≠ 计划 | 只躲避，直到位姿可靠 → 重新规划 | 回到路线 |
| 危险物重生落在意外位置 | HazardRespawn 事件、场景切换 | 同上 | 同上 |
| 卡在地形上 | 进度看门狗 | 暂停 → 诊断 → 报警 | 人工 |
| 靠近 NPC 误触对话 / 战斗中弹出物品提示 | 屏幕模式 DIALOG/ITEM_POPUP | neutral()，按目录推进或取消 | PLAYING |
| Bellway 到错站 | 场景 OCR | 重新规划 | — |
| 交互静默失败 | 审计时发现 | 最多重试 2 次 → UNCERTAIN → 重新规划 | — |
| 退出按钮灰色 | 菜单读取 | 保持暂停（不花时间），不被动等待：暂停中按钮状态不刷新。`disableSaveQuit` 引起的：Options → 返回让菜单重算（纯视觉，不按 Esc）。预加载引起的：本房间内不会恢复，该房间应事先按 quit map 设为 I3 提交区；否则走"离开房间"后备（§3.7.5 步骤 4）[m0:C8] | 可退出 |
| 退出时保存失败 | SAVE_FAILED 对话框 | Submit OK → 读退出确认框的高亮项 → 有限次重试"是" → 仍失败就报警等人。等待是安全的（世界冻结），但无法原地继续游戏 [m0:C9] | 主菜单 |
| 游戏中出现 SAVE_FAILED（工作台等保存失败） | MSG_CANVAS | 按 OK；对话框显示时 `PauseGameToggle` 拒绝执行，不走暂停循环；这次保存不算 SAVE_OBSERVED [m0 §2.4] | PLAYING |
| 意外暂停（例如手柄断开 [m0:N19]） | PAUSE_MENU，但监督器没有请求暂停 | 按解除暂停规则（§3.7.5）检查后用 Continue + Submit 解除，或直接走退出 | PLAYING 或主菜单 |
| 启动时 Steam 初始化失败 | Player.log 有 "Steam failed to initialize"，或缺少 "Steam logged in as" | 退出游戏 → 修复 Steam → 重启；不继续，否则存档落到 `default` [m0:N28] | 预检通过 |
| 焦点被抢 | 焦点守护 | 松开所有键 → 抢回焦点 → 暂停循环。失焦期间原版照常模拟和计时，但键盘被断开，英雄失控 [probe:P6] | 自检 |
| 录制器或磁盘故障 | 写入错误 | 降级为只记元数据；可用空间 < 10 GB 时暂停 | — |
| Wardenfly 捕获 / PERMADEATH | 检测器 | 停止所有输入，报警 | 人工 |
| 未知画面 | 屏幕模式 UNKNOWN > 0.5 s | neutral()；能暂停就暂停 | — |

**退出时可能保存半完成的剧情状态：** 剧情序列（能力授予、敲钟、Grand Gate 的 Act 2 序列）标为"除非致命已成定局，否则不退出"。M5 在路线上的每个剧情序列里各做一次退出测试，检查是否会软锁。

### 3.7 安全监督

#### 3.7.1 hits_to_death

```python
def hits_to_death(hp, blue, mask_intact, ctx):
    """还能承受多少次“支撑集内最坏事件”（含致死那一次）。"""
    h, m = hp + blue - ctx.pending_dmg, mask_intact      # pending：已挂上的 DamageTag（如酸蚀）剩余伤害
    if h < 1:                                            # 挂起伤害本身即致命
        if not (m and ctx.pending_mask_covers): return 0
        h, m = 1, False
    n = 0
    while True:
        n += 1
        d = max(ctx.D1, h - 1 if ctx.critical_in_support else 0)   # CriticalDamage：h→1，不耗面具
        if h - d >= 1:                  h -= d; continue
        if m and ctx.mask_covers:       h, m = 1, False; continue
        return n
```

- `ctx.D1` = 支撑中最坏的单次事件伤害总和（1+1 算 2；齿轮碾压算 1，外加危险物重生 [m0:C3]）。
- `mask_covers = False` 的情形：Muckroach Maul、Wraith/Slubberlug 抓取、爪形陷阱 [com10]、GMS 网（未验证）。导出 DamageHero/FSM 的 flags 之前这个列表不变。
- MidChain 命中救命时不消耗面具 [m0:C2]；上面的代码总是把面具记为已用，更保守，保留。
- 危险物和 DoSpecialDamage 类伤害无视 i-frame [m0:N1][m0:N2]：i-frame 期间不把它们从支撑中剔除。`ctx.pending_dmg` 包括霜冻时钟和所有活动标签。
- `fractured_mask = UNKNOWN` 按已碎处理；装备状态只认审计结果。

#### 3.7.2 不变式

- **I1：** 在**可退出**（quit map 中暂停和退出都可达）的状态下，`hits_to_death ≥ 2`。
- **I2：** 若 HP − D1 ≤ 危险物伤害，击退包络不得碰危险物；h ≤ 2 时门算软危险物。
- **I3（提交区）：** 任何退出不可达超过 0.5 s 的窗口——boss 登场、升降机、剧情序列、对话、会设 `disableSaveQuit` 的竞技场、预加载启动后本房间的剩余部分 [m0:C8]、危险物死亡序列（实测尖刺 1 格约 2.3 s 不可暂停 [probe:P7]）[m0:N9]、竞技场结束 1.85 s 和 boss 死亡 1.35 s 的慢动作 [m0:N13]、从过场/菜单/stag 场景进入 gameplay 房间后的 0.5 s（HUDCamera）[m0:N14]、**解除暂停后 0.3 s 实时**——只有在满血、面具完好、并且"窗口内最坏事件之后 h ≥ 2"时才能进入。每个提交区有自己的 G2 计数。
- **I4：** 各模块置信度高于阈值，否则执行降级规则。

#### 3.7.3 风险档

- **GREEN：** h ≥ 3 且最优计划 S = 0。
- **YELLOW：** h = 2，或 S = 1 且 h ≥ 3。效果：先回血；惩罚最多 1 击；**不弹反**；**不打可能致死的一击**（击杀冻结会吞暂停）；危险物上方不下劈；不开新战斗。
- **RED：** 触发下表任一项。
- 每次尝试维护一个"每帧死亡风险"的积分，超过训练期望的 2× 时触发 Q4。

#### 3.7.4 触发器

| ID | 条件 | 动作 |
|---|---|---|
| Q1 | h ≤ 1（含面具刚碎且 HP = 1） | **PAUSE_PENDING** + 暂停循环 → 退出 |
| Q2 | 违反 I2，且没有候选能在 0.2 s 内离开暴露 | 同上 |
| Q3 | h = 2，且支撑中有绕过面具、多实例、危险物或 Critical 威胁 | 同上 |
| Q4 | 一次尝试中出现两次未预测到的命中，或风险积分 > 2× | 在下一个可暂停的 GREEN 帧退出 → 保守变体 → 标记重训 |
| Q5 | 帧龄 > 50 ms、HUD 不可读 > 100 ms（ENDING 除外）、h ≤ 2 时英雄丢失 > 300 ms、未知场景、OVERLAY_INTRUSION、连续撕裂 | 暂停循环 → 自检 → **只有 h ≥ 3 且冻结态检查通过才恢复**，否则能退出就退出，不能就保持暂停并报警 |
| Q6 | h ≤ 2 时出现 FORCED_RISK | PAUSE_PENDING → 退出 |
| Q7 | FOCUS_LOST | `inputd`：松开所有键 → 抢回焦点 → 暂停循环 → 自检 |
| Q8 | 进度看门狗 | 暂停 → 诊断 → 报警 |
| Q9 | 捕获或 PERMADEATH | 停止所有输入，报警 |
| P1 | 需要 > 3 ms 的规划（新房间组合、重新规划） | **只允许 GREEN 且在 A/B 遭遇之外，或在登记过的安全窗口内**（硬直、波间）。战斗中改用预计算的计划缓存 |

- **PAUSE_PENDING 模式：** 禁止所有攻击（包括会暴击的：Wanderer 暴击带 0.2 s HeroDamageShort 冻结）、弹反、下劈、投掷工具、丝技能、Bind（凡是能触发 FreezeMoment 的动作都禁止）；禁止开始任何交互（对话、门、拾取、拉杆：它们设 `BlockingInteractable` 或 `disablePause`）[m0:N15][m0 §2.4]。只允许躲避性移动，I2 照常生效。
- **暂停不会结束威胁：** 恢复后世界从原处继续。

#### 3.7.5 暂停/退出可用性模型与紧急流程

**`pause_available` / `quit_available` 的组成：**
- 屏幕模式；
- 检测到的冻结起点 + 实测的阻塞时长分布；
- `unpause_lockout_until`（每次暂停和解除暂停后 0.3 s 实时）；
- quit map：P(可暂停)、P(可退出)，按场景 × 状态，来自 oracle 直接记录的 `acceptingInput`、GameState（只有 PLAYING 能暂停）、`PauseAllowed`、`disablePause`、`TimeSlowed`、`GenericMessageCanvas`、`BlockingInteractable`、`disableSaveQuit`、`HasPendingOperations`、Patch 4 的拒绝条件 [m0:N12][m0:N14]。
- 时序约束：敌人伤害在 FixedUpdate 末尾结算，暂停在同一帧稍后的 Update 里读取，所以暂停必须在致命物理步的前一个渲染帧被处理（再加输入延迟）才能救命 [m0:N6]。受击后后坐期间 `disablePause` 为真，Q1 的暂停只能落在 [受击冻结结束, i-frame 结束] 之间 [m0:N8]；这个窗口要显式计算，并在运行时验证它总是长于"检测 + 循环延迟"。实测（敌人 1 格）：命中后 0–250 ms（15 帧）不可暂停，其间前 150 ms 世界完全冻结；250 ms 到约 1.2 s 可暂停且仍有 i-frame；受伤后 30/100/200 ms 按下的 Esc 均被丢弃，300 ms 起均生效 [probe:P7]。

**流程：**

1. **进入 PAUSE_PENDING。**
2. **暂停循环（在 `inputd` 中执行）：** 按下 ≥ 34 ms（2 帧）→ 松开 ≥ 34 ms → 重复，**不管有没有检测到冻结，一直循环**，直到看到暂停的最早线索（步骤 3），或出现 DEATH/PERMADEATH。门关闭时按下的暂停键被游戏直接丢弃，不排队 [m0:N12]，所以循环本身就是重试。
3. **看到暂停的最早线索就停手。** Esc 同时绑定 Pause 和 MenuCancel：0.3 s 实时锁定一过，任何一次 Esc 都会解除暂停（经 InputHandler 或 `PauseMenuButton.OnCancel`），世界再跑约 0.3 s 才被下一次按键重新暂停 [m0:C11]。所以 `inputd` 必须在真实暂停后约 230 ms 内（300 ms 减去一次在途按键）停止按键。最早线索是暗幕从暂停那一帧开始变暗（60 fps 下每帧约 +0.053 alpha）和世界冻结；P8 实测 SendInput → 首个变暗的捕获帧 p50 45.6 ms、最大 49.6 ms [probe:P8]，按它停手有余量；等"完整菜单连续 3 帧"再停必然超时（菜单淡入约 0.30 s 才到 0.95 alpha）。停手后在锁定结束前用菜单淡入确认 PAUSE_MENU；未确认视为误检，立即恢复循环。
4. **读 Quit 按钮状态**（按钮状态只在显示菜单时算一次，暂停中不刷新 [m0:C8]）：
   - **可用** → 退出序列：选中"退出至菜单" → Submit → 确认框"保存并退出？"（默认高亮"否"）→ 上 → Submit [probe:P7]。每次 Submit 前读高亮项，不按计数：灰色 Quit 会被跳过并回绕，盲按"下、下、Submit"会落到 Continue 并解除暂停 [m0:N17]。确认后一直是 PAUSED、timeScale = 0，约 3 s 后到 MAIN_MENU，只花墙钟时间 [probe:P6][probe:P7]。按"是"后约 0.5 s 仍停在确认框且没开始淡出 = Patch 4 拒绝：保持暂停，重查标志，绝不盲目解除暂停。出现 SAVE_FAILED → §3.6.8。
   - **灰色** → 保持暂停（不花时间），不再被动等待。`disableSaveQuit` 引起的：Options → 返回让菜单重算（纯视觉，不按 Esc）。预加载引起的：本房间内不会恢复（这个房间本应按 I3 规划）。之后三选一：冻结态检查通过则解除暂停，以 EVADE 离开房间，再暂停退出；D13 已启用且条件满足则杀进程；否则保持暂停，报警等人。**永不按灰色控件。**
5. **主菜单 → 槽位验证 → 读档 → 验证 Steel Soul 皮肤 → 工作台（满血；读档时面具是否修复 [待验证 P7]，否则再坐一次）→ 审计 → Ledger 回滚 PENDING。**
6. **计时代价：** 从暂停到主菜单不计时，但 Continue 后的工作台场景加载和醒来动画计时（取决于硬件，P7 实测）[m0:C7]；另外的代价是跑回原处 + 重新清场。

**解除暂停的规则（适用于 Q5、P1、意外暂停、看门狗误触发）：**
- 保存暂停前最后一个 `WorldState`。暂停会松开跳跃（`HeroController.Pause()` 调 `JumpReleased()`），检查按"跳跃已松开"预测轨迹，计划缓存也不能假设跳跃在继续 [m0:N18]。
- 只有当所有支撑管道在 0.3 s + L + 0.1 s（再加 HideMenu 淡出时长，P7 测）内都够不到"按击退膨胀后的受击盒"时，才允许解除暂停。
- 用 Continue + Submit 解除，不用 Esc：一次 Esc 可能被 InputHandler 和菜单各处理一次。Continue 在 Submit 后一帧生效，菜单显示期间和 0.3 s 锁定内会被拒绝，所以要用视觉确认 [m0 §2.4][m0 §2.6]。
- 解除后 0.3 s 实时在 I1/I3 和 S(c) 中按不可暂停处理。

**验证（G1）：**
- 10⁴ 次故障注入触发，**其中 ≥ 30% 落在击杀、弹反或 boss 硬直前后 ±3 帧内**；另注入灰色 Quit、焦点丢失、Steam 弹窗。
- 要求 **0 失败**、**非预期解除暂停 = 0** [m0:C11]；从可暂停时刻起算，暂停生效延迟 p99.9 ≤ 6 帧。
- 退出淡出期间世界冻结：代码已确认（`ReturnToMainMenu` 不解除暂停、不改 timeScale），P7 只需复核 HP 不变、没有 unscaled 时间驱动的 FSM 危险物 [m0 §2.4]。

#### 3.7.6 看门狗、死人开关、焦点守护、交战门、重试

- **心跳：** `rt` 每帧给 `inputd` 发心跳。
- **死人开关（`inputd`）：** 静默 100 ms，且最后已知画面是 PLAYING 时：松开所有键 → 按 Esc（2 帧按下 / 3 帧松开）循环，直到**自己的**检测器看到暂停的最早线索（暗幕开始变暗）即停手，同样必须在真实暂停后约 230 ms 内（§3.7.5 步骤 3 [m0:C11]）。**菜单可见时永不按键**；在菜单中开关解除。CUTSCENE 状态下也解除：任何按键都会跳过过场 [m0 §2.6]。
- **Pico（可选 sink）：** 只有在 max(100 ms, 3 × 链路 p99.9 包间隔) 内收不到包、且主机最后报告的状态是"PLAYING 且菜单不可见"时，才按一次 Esc。链路抖动在 soak 中测量。
- **焦点守护：**
  - 每 1 ms 轮询前台窗口。
  - 失去焦点时：松开所有键 → 利用 `AllowSetForegroundWindow`/`AttachThreadInput` 抢回（游戏由 `inputd` 启动）→ 验证 → 暂停循环。
  - 50 ms 内抢不回来就报警。无论用哪种 sink，按键都只发往前台窗口；发送前确认前台，失败就中止，不发任何键 [probe:P8]。
  - 原版失焦行为（已测）：`runInBackground = True`、`SuspendInBackground = False`，Input System 默认在失焦时断开键盘，所以世界和 PlayTime 继续走，Hornet 站着挨打 [m0:C16][probe:P6][probe:P11]。在 Steel Soul 下这是致命的，"永不失焦"是硬要求。
  - 屏蔽 Shift+Tab：Steam 叠加层不会暂停游戏 [m0:C16]。
- **交战门（任何 A/B 单元前，全部满足）：**
  - 在 playbook 指定的工作台休息过（满血、面具修复、重生点已设置、工具补充）；
  - 已装备 = playbook 要求（以审计为准）；
  - 丝 ≥ 9（或补丝用尽且 playbook 允许一阶段攒丝）；
  - 工具 ≥ 最低要求，否则用保守变体；
  - 感知自检通过；
  - 调速器 OK。
- **跑图规则：** 拒绝可选战斗；挡路的先远程处理；危险平台前先清房；HP ≤ 2 时不进危险平台。
- **正式运行中退出后的重试：** 第 1–2 次用同一 playbook；第 3–4 次用保守变体；第 5 次在调速器允许时加一个安全绕路；再失败就停在主菜单并通知你。

#### 3.7.7 最后防线（D13，默认关闭）

- **预测式杀进程（TerminateProcess）。** 仅在以下两条同时满足时使用：
  - (a) 在退出不可达的窗口内预测到致命一击，且 `t_hit` p05 > 杀进程延迟；
  - (b) 没有保存正在进行（无存档图标、无工作台或退出淡出）。
- **效果：** 回到上次存档，**丢失此后的进度和 playTime**，效果上接近 SL，所以与 D3 一起决定。
- **只能预测式：** `Die` 在致命的 TakeDamage 同一次调用里就把内存中的 permadeathMode 改为 Dead，下一帧 `PlayerDead` 开始 `SaveGame`，反应式杀进程基本无效 [m0:N7]。
- **P15 在沙盒中验证：** Die 之前杀进程，槽位仍是存活的；Die 之后杀无效；SaveGame 期间杀对 `user{N}.dat` 有什么影响（D3 的备份必须能覆盖这种情况）；致命帧 → `user{N}.dat` 落盘的耗时（序列化 + 写盘）；Dead 是否同时写入 `user{N}_1.0.30000.dat`；死亡后 `.bak*` 和 `Restore_Points` 的状态 [m0:N7][m0:C13]。
- **不启用时：** 保留 I3，并扩展到 quit map 找出的所有退出不可达窗口。

#### 3.7.8 基础设施加固

- 两份副本 + 共享状态隔离（§2.7）。
- 存档目录会话前后做哈希；每章前、每晚备份。
- 最终机器上跑 24 h soak：0 次 > 50 ms 的管线卡顿，并注入焦点抢占事件。
- 存档盘可用空间 ≥ 10 GB。

### 3.8 I/O 后端

#### 3.8.1 PC 捕获

- **`WgcSource`：** 窗口级捕获，忽略覆盖在上面的窗口，时间戳为 QPC `SystemRelativeTime`，关闭捕获边框；经 D3D11→CUDA 零拷贝。P8：`Frame.timespan` 比回调到达时刻晚约 7–10 ms，不能当作帧产生时刻，延迟一律以回调到达的 QPC 计；遮挡不影响捕获，最小化会停止出帧 [probe:P8]。
- **`DxgiSource`** 只在 P8 证明 WGC 不达标时实现。
- **P8 测量：** 冻结显示配置（60 Hz、窗口模式、VSync 开）下 present→capture 的 p50/p99；10 min 内丢帧/重复帧 < 0.1%；**撕裂率**（用 oracle 每帧相机位姿对比检查）。M0 初测（游戏在后台，10 s）：58.9 fps，帧间隔 p50 16.67 ms，但 581 帧中有 12 个 33 ms 间隔（约 2%，超过 0.1% 门槛），待与前台对比 [probe:P8]。

#### 3.8.2 PC 输入

| Sink | 细节 |
|---|---|
| **`SendInputSink`（默认）** | 由 `inputd` 发出；自写 ctypes 扫描码（**不用** pydirectinput，它每次调用 sleep 100 ms [pri13]）；所有键都设 `KEYEVENTF_SCANCODE`，方向键另带 E0 扩展位（否则被当成未绑定的小键盘 2/4/6/8）；每个决策一次批量 `SendInput`；按键状态做差分。**按帧计数的最短保持**：每次按下保持到看见 ≥ 2 个新帧，下限 max(34 ms, 2 × 实测帧时间)，同一键两次按下之间的松开同理 [m0:N37]。缓冲动作按住到执行或预输入窗口过期（物理步：跳 2、二段跳 10、攻击 8、冲刺 10、工具 5、飞针 8），松开 Dash/Attack/SuperDash/QuickCast 会立即清空对应队列，每个离散动作都先松开再按 [m0:N38][probe:P11]。左右互斥，同一批里先松后按；Clawline 前先松开 ↓（只按住 ↓ 时 S 是 Silk Soar）[m0:N41]。暂停循环按/放各 34 ms。菜单可见时不得漏出游戏键（Z = 确认，X/A = 取消）[m0:N16]。需要焦点（焦点守护），每次发送前确认前台 [probe:P8] |
| `PicoHidKbdSink`（可选） | RP2040 模拟 1 kHz USB 键盘，经 USB-CDC 驱动，多约 1–2 ms；固件死人开关。主要作用是给 Switch 固件做台架测试 |
| `OracleInjectSink` | 仅训练；`InputSystem.QueueStateEvent` 注入（`KeyboardInjector`）+ legacy shim + 每帧锁存（§3.1.1）[probe:P3] |
| 不使用 | ViGEmBus（已停止维护）、Interception |

**默认键位（扫描码集 1）：** jump Z 0x2C、attack X 0x2D、dash C 0x2E、bind A 0x1E、clawline S 0x1F、needolin D 0x20、quick-cast F 0x21、taunt V 0x2F、quick map Tab 0x0F（永不使用）、inventory I 0x17、pause Esc 0x01、confirm Enter 0x1C、背包翻页 `[` 0x1A / `]` 0x1B、方向键 E0 扩展码 48/50/4B/4D。P4 核对与注册表中的默认键位一致 [probe:P4]。启动时从注册表推导扫描码表，并断言等于默认值 [m0 §2.6]。预检确认 PC 上没有任何手柄 [m0:N19]。

P4：游戏在前台时，扫描码 SendInput 能驱动菜单和游戏 [probe:P4]。与 `KeyboardInjector` 注入在无敌人房间中的轨迹对比留到 M1。

#### 3.8.3 Switch（延伸，只换插件）[SW]

- **Switch 上的成就只存在本地**，这是演示，不是拿 Steam 成就的途径。证据是录像 + 成就界面 + 存档槽 + 标题画面版本号。
- **主机：** Switch 2 底座模式 1080p120 优先（Switch 1 为 720p60，约 43 px/u，模型需要缩放）；关闭 HDR。
- **捕获：** `UvcSource`，USB 3 UVC 采集卡，YUY2/NV12。Elgato HD60 X 在 1080p60 约 63 ms、1080p120 约 44 ms；MS2130 ≥ 50 ms；**避免 MS2109**（170–220 ms）。
- **输入：** `PicoSwitchSink`。RP2040 模拟 HORI Pokken（VID 0x0F0D / PID 0x0092）；UART 1–3 Mbaud；包格式 `A5|seq|buttons u16|hat|lx ly rx ry|flags|crc8`，Pico 回显 (seq, µs)；固件看门狗；不用蓝牙；**`min_hold_ms` = 40**。
- **域适配：** PC 模型 + Switch 增强；按域的 HUD 区域；伪标签 + 约 2k 帧人工检查；对比阶段时长，检测不同构建间的行为差异（Switch 构建号从标题画面读取）。

#### 3.8.4 延迟预算

| 阶段（ms） | PC：60 fps、60 Hz、SendInput（p50 / p99；估计值，实测见 P8） | Switch：UVC + Pico |
|---|---|---|
| 游戏 Update → present | 4 / 9 | – |
| present → 帧可用 | 9 / 17 | 45 / 70 |
| 上传 + 缩放 | 0.5 / 1 | 2 / 4 |
| 感知（stream A；B 并行） | 5 / 7 | 5 / 7 |
| 跟踪 + HMM + 融合 | 1 / 2 | 1 / 2 |
| 战术 + 规划 + 过滤 + 监督 | 2 / 3 | 2 / 3 |
| sink → 设备 | 0.2 / 1 | 3 / 10 |
| 等待下一次输入轮询 | 8 / 16.7 | 8 / 16 + 1 帧 |
| **合计** | **≈ 30 / ≈ 57 → 目标 p99 ≤ 60** | **≈ 70–110 → 计划 p99 ≤ 130** |

- **P8 实测（60 Hz）：** SendInput Esc → 第一帧画面开始变暗（回调时刻）p50 45.6 ms、p90 46.3 ms、最大 49.6 ms（10 次）；→ 画面变暗 30 %（含暂停菜单淡入）p50 约 95 ms（30 次）[probe:P8]。45.6 ms 包含输入采样、暂停协程自身的帧数、渲染、DWM 合成、WGC 捕获和 Python 回调，不含计算；比表中 p50 估计高，加上约 8–10 ms 计算后接近 60 ms 上限。M1 的延迟工具改用即时反应的刺激（如开始奔跑）重测。
- 物理量化对任何代理（包括 oracle）额外带来 0–20 ms。
- 规划器从 `state_at(now + L)` 出发，L 按 FrameSource × Sink 实测（PC 约 3 帧）。
- GPU 争用门槛：bot 运行时游戏帧时间 p99 ≤ +0.5 ms。
- **回环测试：** sink 在记录的 QPC 时刻按 PAUSE/INVENTORY，FrameSource 记录第一帧被识别为该画面的时刻。M0 做 200 次；每章前的自检做 50 次。

### 3.9 训练与评估

#### 3.9.1 只用实时训练

- TRAIN 开 4–6 个实例（720p 窗口、`runInBackground`、每个约 730 MB 内存），SHADOW 开 2 个实例。
- 用 DebugMod savestate + 随机起点，重置 ≤ 2 s。
- timeScale 训练不可用 [pri5]；lockstep 省不了计时预算 [VER]，都已移除（按需重新引入见 §3.11）。
- G0 需要约 2,000 次 A 类、3,000 次 B 类、3,000 次 C 类尝试，约 400 h 游玩，5 个实例约 3.5 天。

#### 3.9.2 模拟最终路径

```
OracleBackend → ObservabilityFilter(VISION_EQUIVALENT) → 简单噪声 → DelayLine → brain
                    InputPathEmulator（插件内，动作一侧）
```

- **`ObservabilityFilter`：** 用**和视觉路径相同的估计器代码**替换 O-only 字段：敌人 HP → 数命中估计；FSM 状态 → 可观测阶段；屏幕外实体 → 隐藏，只保留记忆中的轨迹；精确计时器 → 模型估计；playTime → 墙钟估计。
- **简单噪声：** 位置加高斯噪声，σ 按类别取 M3 实测值；检测丢失率 p；HUD/阶段混淆矩阵来自 M3。
- **`DelayLine`/`InputPathEmulator`：** 延迟 k 帧的分布来自回环实测（初始先验：2/3/4 帧，权重 0.3/0.5/0.2）；加边沿抖动和最短保持。
- **门槛：** 策略在模拟下的成功率须与 SHADOW 下的成功率在 95% CI 内一致（M6）。不一致时启用拟合版 NoiseModel（§3.11）。

#### 3.9.3 课程与 savestate

| 阶段 | 配置 | 目的 | 退出 |
|---|---|---|---|
| T0 | TRAIN | 运动学辨识；行为日志（每个攻击 ≥ 200 次）；场景导出；配方；quit map | 运动学验收；配方 50/50 |
| T1 | TRAIN（VisionView 模拟） | 战术、playbook、余量 | G0 |
| T2 | SHADOW | 感知指标、前兆对比 | G1 |
| T3 | REHEARSAL-SEG | 最终延迟和输入路径；在实时数据上验证运动学 | G2 |
| T4 | REHEARSAL-FULL + VANILLA + 结局预演 | 集成、时间、经济、Ledger 漂移 | G3 + 发射模型 |
| T5 | FINAL | 正式 | — |

- savestate 由 bot 自己在 T1 跑的路线生成；vichisuki 的 79 个 Bell 路线 savestate 只用于早期起步。
- 阶段 savestate（例如 Last Judge P2、Forum 第 11–13 波）只用于练习，**不计入门槛**。

#### 3.9.4 门槛（序贯贝叶斯）

- **"干净通过"的定义：** CLEAR，且无 WOULD_DIE、无任何 Die、不可暂停时没有违反不变式、h ≤ 2 时没有未预测到的命中。**时间不再是"干净"的一部分**；每个单元的时间分布单独记录，交给调速器。
- **每个单元 i 的死亡率 d_i：**
  - 后验 Beta(1 + 失败数, β₀ + Σ wₛ·通过数)。
  - β₀ ≤ 20，由前兆模型给出（前兆率越高，β₀ 越小）。
  - **失败一律按权重 1 计**；通过按阶段加权：TRAIN 0.1、SHADOW 0.3、REHEARSAL-SEG 1.0（savestate 起点先按 0.7 计，直到两比例检验显示它与真实 Continue 起点无差异）。
- **通过条件：** P(d_i ≤ d_budget) ≥ 0.9，d_budget：A 1.0%、B 0.35%、C 0.15%。
  - A 类单元各自独立计算。零失败约需 n_eff ≈ 230（例如 60 SEG + 300 SHADOW×0.3 + 800 TRAIN×0.1）；有一次失败约需 390。
  - B/C 类用分层 Beta-二项模型按类部分汇总：类级 P(d̄ ≤ budget) ≥ 0.9；单元最低证据为 B ≥ 150 SHADOW + 40 SEG、C ≥ 50 SHADOW + 20 SEG，且 0 死亡。
- **每次 WOULD_DIE 都要做 postmortem。** 只有代码、模型或配置（按指纹）变化才重置该单元的证据；离线回放证明相关指标无退化时，旧证据按 0.3 权重并入先验。

| 门槛 | 配置 | 条件 |
|---|---|---|
| G0 | TRAIN | 上述贝叶斯条件（只用 TRAIN 证据，目标放宽到 2× budget）；A 类退出率 ≤ 30% |
| G1 | SHADOW | 贝叶斯条件；§3.9.5 全部感知阈值；安全分歧 ≤ 10⁻⁴/tick（A 类）；**对等性：视觉前兆率 ≤ 1.5 × oracle 前兆率**（单侧 95% 泊松率比检验）；最近 100 次 0 CPE；10⁴ 次暂停注入 0 失败（§3.7.5） |
| G2 | REHEARSAL-SEG | A 类 ≥ 60 次（**≥ 50% 从真实 Continue 开始，经 MenuDriver + 跑回**）、B ≥ 40、C ≥ 20，满足贝叶斯条件；A 类退出率 ≤ 20%；每个提交区单独计数 |
| G3 | REHEARSAL-FULL | **最近 4 次全程中 ≥ 3 次干净**，其中 ≥ 2 次为 Steel Soul 模式；每次退出 ≤ 15 次；经济和 Ledger 检查通过；卡住计为失败；结局预演 ≥ 5 次通过 |
| Vanilla | VANILLA | 在 GMS 前停下且干净；帧时间、延迟、动作时序直方图与 G3 一致（两样本 KS p > 0.05）；外部只读裁判核对计时估计与 HUD |
| **发射** | 模型 | **P10(P_run) ≥ 0.7**；包冻结并哈希；当天 compat + 预检通过 |

**CPE（灾难性感知错误）** 指以下任一：HP 高估 ≥ 1 格且持续 > 5 帧；漏掉的威胁随后命中；场景错误 > 1 s；紧急退出时误读暂停菜单或 Quit 状态；漏掉死亡/PermaDeath 画面；误读存档槽身份。

**每轮门槛的机器时间：** G1 ≈ 260 h（2 实例），G2 ≈ 160 h（1 实例），G3 + 原版 ≈ 30 h，合计约 3 周无人值守。

#### 3.9.5 感知阈值（属于 G1）与 M3 spike 门槛

| 字段 | 指标 | 最终 | M3 spike 门槛 |
|---|---|---|---|
| 屏幕模式 | 准确率（全部 / PAUSE-PLAYING-DEATH）；延迟 | ≥ 99.9% / ≥ 99.99%；≤ 2 帧 | ≥ 99.9% |
| 菜单：Quit 灰色、槽位身份、Restore/Clear 高亮 | 误读 | 0 / 10⁴ | 0 / 10³ |
| 场景 | 准确率；切换后帧数 | ≥ 99.9%；≤ 3 | ≥ 99.5% |
| 相机位姿 | p99；严重失败 | ≤ 0.08 u；≤ 1e-4 | ≤ 0.15 u |
| 英雄位置（相对地形）/ 速度 | p99 | ≤ 0.10 u / ≤ 0.5 u/s | ≤ 0.15 u |
| 面具 | 高估；精确率 | 0 / 10⁶ 帧；≥ 99.95% | 0 / 10⁵；≥ 99.9% |
| 丝 / bind_ready | 精确；保守一致 | ≥ 99.9%；≥ 99.99% | — |
| Fractured Mask 状态 | 事件准确率 | ≥ 200 次中 100% | — |
| 威胁事件 | 接触前 ≥ 100 ms 检出（或出生即检出） | ≥ 99.9% | ≥ 99.5%（**含 Forum**） |
| 伤害区域 | 每个物体帧的召回（4 u 内；12 u 内） | ≥ 99.95%；≥ 99.5% | ≥ 99.5%（8 u 内） |
| 判定范围 | p99 误差 | ≤ 0.25 u | — |
| 幻影威胁 | 导致的多余闪避 | ≤ 1 次/分钟 | — |
| 弹丸到达时间 | p95 / 偏差 | ≤ 50 ms / ≤ 1 帧 | — |
| 攻击起始（A 类） | 相对 oracle 延迟 | ≤ 33 ms 的比例 ≥ 99% | 150 ms 内 top-1 ≥ 95%（**Forum、Lace 2**） |
| ttd p05 | 保守比例 | ≥ 99.5% | — |
| 撕裂检测 | 召回 | ≥ 99.9% | — |
| playTime 估计 | 低估 / 高估 | ≤ 30 s / ≤ 300 s | — |
| 延迟 | 端到端 p99；计算 p99 | ≤ 60 ms；≤ 12 ms | ≤ 70 ms；≤ 12 ms |
| 游戏帧时间 | p99 增量 | ≤ +0.5 ms | — |
| 泄漏 | 插件开/关像素差；训练 mod 组合对原版像素差（遮罩区外，L1） | < 1/255 | < 1/255 |

#### 3.9.6 全程存活模型

- 单元 i：通过率 c_i、退出率 q_i、死亡率 d_i，c + q + d = 1。退出只是重试。
- `P_run = Π c_i/(c_i + d_i) · (1 − p_infra) ≈ exp(−Σ d_i/c_i − p_infra)`。
- **P_run = 0.8 的预算：** Σ ≤ 0.223。例：A 10 × 0.010 + B 15 × 0.0035 + C 30 × 0.0015 + 基础设施 0.02 ≈ 0.218。
- **三种估计器，取死亡估计较大者：**
  1. 按单元的贝叶斯后验（§3.9.4）。
  2. **前兆故障树（主估计器）：** h ≤ 2 时的 HUD 误读率；临界余量上的击退包络违反率；实际伤害 > 建模 D1 的爆发事件（必须为 0）；暂停/退出失败（注入试验）；不可退出窗口中 h ≤ 1 的时间；面具例外事件；无面具时 h ≤ 2 的未预测命中；挂起伤害低估。
  3. G3 全程。
- 另外显式加入相关性失败项（Q4 异常率）。
- **发射时的算例：** Σ ≈ 0.072 → E[P_run] ≈ 0.93，P10 ≈ 0.80，每局约 4.5 次退出。

### 3.10 日志、回放与工具

**Episode 目录** `runs/<date>/<profile>/<episode>/`：

| 文件 | 内容 |
|---|---|
| `meta.json` | 配置、构建与 DLL 哈希、git SHA、配置指纹、模型哈希、延迟模型 |
| `video.mkv` | NVENC HEVC；日常 720p 约 6 Mbps；数据集会话 1080p CQP 14–16 |
| `state.msgpack.zst` | 每帧 WorldState，600 帧一块 + 索引 |
| `oracle.msgpack.zst` | 裁判 `FrameLabel`（训练配置） |
| `actions.parquet` | 决定的按键、实际发出的边沿（QPC）、sink 回显 |
| `events.jsonl` | 事件 + **决策追踪**（模块、原因、关键特征） |
| `timing.parquet`、`fsm.parquet`、`attempts.parquet` | 各阶段延迟；FSM 转移；`AttemptRecord` |

**工具：**
- **Rerun 查看器：** oracle 与视觉并排、扫掠威胁、决策文字。
- **postmortem 剪辑器：** 每个 DAMAGE_TAKEN / CATASTROPHE / 触发 / STALL / STUCK 剪 −5 s/+1 s，并写入 `review.csv`。
- **离线重感知回归：** 用新模型重跑已录的 SHADOW 数据，不需要游戏。
- **VANILLA 外部只读裁判：** 自动分割器式读取 HP/丝/场景/playTime，只做核对。
- **`route_check.py`：** 路线数据一致性检查。

**compat 套件**（`ssbot compat --profile X`，< 3 min，每次会话和每章前运行）：

1. 哈希与 `versions.lock` 一致；FINAL/VANILLA 下不得有 `winhttp.dll`、`doorstop_config.ini`、`BepInEx/`；**运行进程已加载 DLL 的哈希**一致；OCR 标题版本号。
2. 恢复注册表快照并做哈希；**OCR 选项页，核对所有键位和设置**。
3. SymbolCheck（训练）。
4. 每个 sink 的输入冒烟测试，**覆盖所有动作键**：训练副本在测试房间里验证各自效果；最终副本在工作台房间验证移动 Δx ±5%、跳跃、攻击、库存开关、暂停开关。
5. 视觉黄金集 2,000 帧；标题画面 SSIM ≥ 0.98。
6. 50 次延迟回环。
7. 守卫探针；存档目录哈希不变；真实的 `persistentDataPath\default` 不存在（出现即报警：最终副本的 Steam 初始化失败，存档和 shared.dat 落到了 `default` [m0:N28][probe:P9]）。
8. 环境检查：Steam 在线（FINAL/VANILLA 看 Player.log 的 Steam 行，§3.6.1）、Cloud 关、可用空间 ≥ 10 GB、微码版本、Game Bar/通知/粘滞键快捷键已关、鼠标已拔、没有任何手柄 [m0:N19]。

**存储：** 4 h 的正式运行约 15–25 GB。

### 3.11 按需扩展（默认不实现）

| 扩展 | 启用触发条件 | 代价 |
|---|---|---|
| L1/L-fast lockstep + UnscaledPatches + VirtualPlayTime + 保真门 | 规则在某单元 2 轮调参后仍过不了 G0，且需要快于实时的学习 | 3–4 FTE 周 + 维护 |
| 学习型战术选择器（BC → PPO，非对称 actor-critic，SHADOW 中 DAgger） | 同上，且规则的退出率或时间明显劣于目标 | 3–5 |
| TRAIN-V（引擎内抓帧 + 像素等价测试） | 需要大量视觉在环训练 | 2 |
| 拟合版 NoiseModel（按上下文） | 模拟与影子的成功率不在 95% CI 内 | 1–2 |
| 房间图集 + 对比学习描述子 + LK v1 + FAISS 检索 | 某房间位姿指标不达标 | 3–4 |
| re-ID 嵌入 | ID 交换导致 CPE | 1 |
| 普通敌人的完整阶段识别 | 表中禁入区导致过多绕行或伤害 | 2–3 |
| 地形开/关 ResNet 分类器 | 复用分割的验证误判 > 阈值 | 1 |
| DXGI 后端 | P8 表明 WGC 不达标 | 1 |
| ~~120 fps~~ | 不可用：显示器最高 60 Hz（2026-09-29） | — |

---

## 4. WorldState 数据结构与接口

### 4.1 约定

- 世界坐标 W：当前场景的 Unity 单位 u，+x 向右，+y 向上，位置指碰撞体中心。屏幕坐标：像素，原点在左上。
- 时间单位为秒，时钟为 QPC 纳秒，伤害单位为面具格。
- 估计字段包在 `E[T]` 中（值、σ、校准置信度、来源、年龄）。
- 可观测性标签：**V**（视觉提供）、**O**（仅 oracle；在 VisionView 中为 `None`）、**D**（推导）。
- 线格式：`msgspec.Struct`，`array_like=True`；C# 侧在 `Schema.cs` 手工镜像。

### 4.2 Schema v2

```python
class Src(IntEnum): ORACLE=0; VISION=1; DB=2; LEDGER=3; PREDICTED=4; EVENT=5; AUDIT=6; UNKNOWN=7
class Screen(IntEnum):
    PLAYING=0; PLAYING_HUD_HIDDEN=1; DIALOG=2; ITEM_POPUP=3; AREA_TITLE=4; BENCH=5; SHOP=6
    BELLWAY_MAP=7; INVENTORY=8; QUICK_MAP=9; PAUSE_MENU=10; MAIN_MENU=11; SAVE_SELECT=12; MODE_SELECT=13
    FADE=14; TRANSITION=15; CUTSCENE_VIDEO=16; DEATH=17; ENDING=18; CREDITS=19; FOREIGN_WINDOW=20
    MSG_CANVAS=21; UNKNOWN=31                                            # MSG_CANVAS：SAVE_FAILED 等对话框
class PauseBlock(IntFlag):
    DISABLE_PAUSE=1; TIME_SLOWED=2; PAUSE_LOCKOUT=4; MSG_CANVAS=8; BLOCKING_INTERACT=16
    NOT_ACCEPTING_INPUT=32; DISABLE_SAVEQUIT=64; PRELOAD_PENDING=128; FOCUS_LOST=256
    GAME_STATE_NOT_PLAYING=512           # PAUSE_LOCKOUT = !PauseAllowed（0.3 s 锁定、HUDCamera 0.5 s、ReturnToMainMenu）
class Kind(IntEnum): ENEMY=0; BOSS=1; PROJECTILE=2; ENEMY_ATTACK=3; HAZARD_DYN=4; HERO_ATTACK=5
    PICKUP=6; NPC=7; BREAKABLE=8; LEVER=9; PLATFORM_MOVING=10; HOOK=11; HELPER=12; UNKNOWN=15
class Hazard(IntEnum): ENEMY=0; SPIKES=1; ACID=2; LAVA=3; COAL=4; COAL_SPIKES=5; ZAP=6; STEAM=7
    RESPAWN_PIT=8; EXPLOSION=9; NON_HAZARD=10; COG=11; PIT=12; SINK=13; OTHER=15
    # PIT 穿透 i-frame、SINK 永远生效（§1.5、§3.3.1 [m0:N1]）；OTHER 只作兜底
class FM(IntEnum): NOT_EQUIPPED=0; INTACT=1; BROKEN=2; UNKNOWN=3        # UNKNOWN 按 BROKEN 处理

class E(Struct, Generic[T]):
    v: T; sigma: float = 0.0; conf: float = 1.0; src: Src = Src.ORACLE; age_ms: float = 0.0

class Stamp(Struct):
    frame: int; t_sample_qpc_ns: int; t_pub_qpc_ns: int
    t_game_s: float                     # 冻结与暂停期间为 0 速推进
    backend: str; config_fp: str

class MenuRead(Struct):                 # V：模板 + OCR；O：UI 状态
    cursor_item: str | None
    quit_greyed: bool | None
    slot_index: int | None; slot_playtime_s: float | None; slot_location: str | None
    slot_steel_soul: bool | None
    forbidden_highlight: bool           # Restore / Clear 被高亮
    mode_has_steel_soul: bool | None

class PlayTimeEst(Struct):
    live_s: float; sigma_s: float; counting: bool; last_calib_s: float | None
    saved_s: float | None               # O：playerData.playTime（最后一次 flush，成就检查读它）；live 对应 GameManager.PlayTime

class Game(Struct):
    screen: E[Screen]; menu: MenuRead | None
    game_state: int | None                              # O
    scene: E[str]; scene_variant: E[str]; entry_gate: str | None; transitioning: bool
    memory_scene: bool | None                            # O：IsMemoryScene()，死亡非致命（待确认）
    pause_available: E[bool]; quit_available: E[bool]    # V：quit map + 冻结检测；O：精确
    pause_blockers: int                                  # PauseBlock 位掩码（V 为推断）
    unpause_lockout_until_s: float                       # 暂停/解除暂停后 0.3 s
    focus_ok: bool
    permadeath_mode: int | None                          # O；V：来自槽位验证 + HUD 皮肤
    play_time: PlayTimeEst
    unobservable: int

class CameraPose(Struct):
    x: float; y: float; z: float; fov: float
    V: tuple[float, ...] | None; P: tuple[float, ...] | None
    sigma_xy: float; reliable: bool; src: Src

class PhasePost(Struct):
    topk: list[tuple[str, float]]
    t_in_phase: float; ttd_mean: float; ttd_p05: float
    support_region: list[Vec2] | None                    # 安全
    prob_regions: list[tuple[list[Vec2], float, float, float]]   # (poly, t_on, t_off, p)，性能

class HeroState(Struct):
    pos: E[Vec2]; vel: E[Vec2]; facing: E[int]; hurtbox: list[Vec2]
    contact: E[str]                                      # GROUND|WALL_L|WALL_R|AIR|WATER|HAZARD
    mode: E[str]                                         # ground|air|wall|dash|glide|attack|pogo|bind|hurt|recoil|bench|cutscene
    iframes_left: E[float]; recoil_left: E[float]; dash_cd_left: E[float]; action_lock_left: E[float]
    binding: E[str]                                      # NONE|IN_PROGRESS|INTERRUPTED|DONE
    committed_primitive: tuple[str, int] | None          # (原语, 剩余按住帧)
    can: dict[str, bool] | None                          # O only

class ToolSlot(Struct): tool_id: str; ammo: E[int]; ammo_max: int

class Resources(Struct):
    hp: E[int]; hp_max: E[int]; blue: E[int]
    silk: E[int]; silk_max: E[int]; silk_hearts: int; bind_ready: E[bool]   # silk_max = CurrentSilkMax（断轴 9、诅咒 3）
    fractured_mask: E[FM]; magma_ready: E[bool] | None
    pending_dmg: E[int]                                  # 已挂上的 DamageTag 剩余伤害 + 霜冻时钟（保守上界）
    status: frozenset[str]                               # ACID, FLAME, GRIND, FROST, ...
    crest: E[str]; equipped: list[str]                   # 只来自库存审计（Src.AUDIT）
    tools: list[ToolSlot]
    rosaries: E[int]; shell_shards: E[int]; craftmetal: E[int]; lockets_free: int

class DamageBox(Struct):
    poly: list[Vec2]; active: bool; dmg_seq: tuple[int, ...]; hazard: Hazard
    flags: frozenset[str]   # PARRYABLE DEFLECTABLE FLAME VOID MASK_BYPASS IGNORES_IFRAMES
                            # IGNORES_PARRY FIRST_NO_MASK CRITICAL GRAB TAG_ACID

class Entity(Struct):
    id: int; kind: Kind; type_key: E[str]
    pos: E[Vec2]; vel: E[Vec2]; acc: Vec2; facing: E[int]
    body_polys: list[list[Vec2]]; dmg_boxes: list[DamageBox]
    phase: PhasePost | None                              # 仅 A 类 boss / 竞技场敌人
    keepout: list[Vec2] | None                           # 普通敌人：表中的 reach 并集
    hp_est: E[float] | None
    fsm: list[tuple[str, str, float]] | None             # O only
    visible_frac: float; last_seen_ms: float

class Threat(Struct):                                    # D：两种后端共用同一份代码
    id: int; source_id: int | None
    kind: str                                            # enemy_body|attack|projectile|hazard|grab|cog|tag
    shape: list[Vec2]; swept: list[tuple[float, list[Vec2]]]
    motion: str; params: list[float]; vel: Vec2; acc: Vec2
    t_on: float; t_off: float
    dmg_seq: tuple[int, ...]; hazard: Hazard | None; flags: frozenset[str]
    in_support: bool; p: float; conf: float
    t_hit_hero: E[float]

class PerceptionHealth(Struct):
    frame_age_ms: float; dropped_frames: int; flash: bool; torn: bool; fx_density: float
    conf: dict[str, float]

class TerrainRef(Struct):
    scene: str; variant: str; db_version: str; dynamic_deltas: list[tuple[str, bool]]

class WorldState(Struct):
    stamp: Stamp; game: Game; cam: CameraPose; hero: HeroState; res: Resources
    entities: list[Entity]; threats: list[Threat]; terrain: TerrainRef
    world_flags: dict[str, E[bool]]
    events: list["Event"]; ledger_rev: int
    perception: PerceptionHealth
    def view(self, profile: str) -> "WorldState": ...    # VISION_EQUIVALENT：所有 O 字段置 None
```

**事件：**
- 战斗：`HIT_TAKEN(amount, hazard, source_type, caller_path?)`、`HIT_DEALT`、`ENEMY_KILLED`、`PARRY`、`CLASH`、`BIND_START/DONE/BROKEN`、`FREEZE(profile)`、`STATUS_TAG(kind, remaining)`
- 行为：`FSM_TRANSITION(enemy_id, fsm, from, to, hero_rel_pos)`
- 进度：`SCENE_ENTER(scene, gate, planned: bool)`、`ITEM(id)`、`PURCHASE(id, cost)`、`BENCH_REST`、`SAVE_OBSERVED(kind)`、`INTERACTION(id, ok)`
- 暂停/退出：`PAUSE_ON/OFF`、`PAUSE_BLOCKED(reason)`、`DISABLE_PAUSE_ON/OFF`、`DISABLE_SAVEQUIT_ON/OFF`、`QUIT_BLOCKED`
- 异常：`CATASTROPHE(blocked_lethal)`、`WOULD_DIE(path)`、`GUARD_TRIPPED(kind)`、`PERCEPTION_LOST(ms)`、`FOCUS_LOST`、`WORLD_MISMATCH`、`FORCED_RISK`、`OVERLAY_INTRUSION`、`STUCK`、`CAPTURED`

### 4.3 低频记录

```python
class SceneGeometry(Struct):      # 每个 (scene, variant)；oracle 导出；视觉中作静态数据
    scene: str; variant: str; variant_key: str; build: str; db_version: str; bounds: AABB
    cam_limits: tuple[float, float, float, float]
    solids: list[Poly]; nonslider: list[Poly]; soft_terrain: list[Poly]; no_clamber: list[Poly]
    terrain_raster: str                                     # 16 px/u 碰撞栅格（定位配准用）
    harpoon_hooks: list[Vec2]
    gates: list[tuple[str, Poly, str, str, bool]]           # (name, poly, target_scene, entry_point, is_door)
    gate_entry_risk: dict[str, float]                       # 来自出生点导出
    hazards: list[tuple[Hazard, int, Poly, tuple[float, float] | None]]
    hazard_respawns: list[tuple[Poly, Vec2]]
    switchables: list[tuple[str, str, Poly, Poly, str]]
    camera_locks: list[tuple[Poly, float, float, float, float, bool]]
    darkness: list[Poly]; water: list[Poly]
    benches: list[tuple[str, Vec2]]; npcs: list[tuple[str, Vec2]]; shops: list[tuple[str, Vec2]]
    pickups: list[tuple[str, Vec2, str]]; spawns: list[tuple[str, Vec2, str]]
    arena_waves: list[tuple[int, list[tuple[str, Vec2]], str]]
    entry_poses: list[tuple[str, Vec2, Vec2]]
    scripted_sequences: list[tuple[str, Poly, str]]         # (id, 触发区, quit_policy: normal|lethal_only)
    quit_map: str                                           # 引用 knowledge/…/quit_map.json 的键

class LedgerStatus(IntEnum): PENDING=0; COMMITTED=1; UNCERTAIN=2; ROLLED_BACK=3
class LedgerEntry(Struct):
    key: str; value: int | bool | str; status: LedgerStatus
    t_event_s: float; save_seq_at_event: int                # 事件时最近一次“观测到的保存”序号
    verify: str; conf: float
class Ledger(Struct):
    entries: dict[str, LedgerEntry]
    save_seq: int                                           # 每次 SAVE_OBSERVED +1，PENDING→COMMITTED
    # 读档时若 save_seq 未前进：status==PENDING 的条目全部 ROLLED_BACK

class Progress(Struct):           # O：PlayerData/SceneData；V：Ledger + 审计
    skills: dict[str, bool]; mask_shards: int; spool_parts: int; needle_level: int; silk_hearts: int
    crests: list[str]; tools: list[str]; lockets: int
    bosses: set[str]; bells: set[str]; bellway: set[str]; ventrica: set[str]; benches: set[str]
    rosaries: int; shell_shards: int; craftmetal: int; keys: dict[str, int]
    act2_started: bool; flags: dict[str, bool]; persistent: dict[tuple[str, str], bool]
    respawn: tuple[str, str]; src: Src; rev: int
```

### 4.4 知识文件与记录

```yaml
# knowledge/1.0.30000/enemies/LastJudge.yaml（状态名仅示意，真实名称来自 FSM 日志）
enemy: LastJudge
build: "1.0.30000"
fsms: [discovered_from_logs]            # 不假设叫 "Control" [VER]
hp: 720
phases: {P1: "hp>540", P2: "hp<=540", JUDGEMENT: "once at hp<=216"}
observable_phases:
  SLAM_ANTIC: {fsm_states: ["Slam Antic"], tokens: [...], ttd_s: {p0_5: 0.52, p50: 0.58, p99_5: 0.66, n: 412},
               ambiguous_until: null, parryable: false}
attacks:
  LJ_SLAM:
    trigger_phases: [SLAM_ANTIC, SLAM_AIR, SLAM_LAND]
    hitboxes: [{t0: 0.82, t1: 0.95, shape: aabb, x: [-1.6, 1.6], y: [-0.2, 2.8], dmg: [2], type: ENEMY}]
    aim: {model: hero_x_at_state_entry}          # 仅概率
    reach_union: polygon                         # 支撑
    tell_lead_vision_s: {p0_5: 0.61}
    select: {dist_bins_u: [0, 3, 6, 10, 99], counts: {P1: [...], P2: [...]}}
support_transitions: {SLAM_ANTIC: [SLAM_AIR], ...}
coverage: {logged_instances_min: 200, fsm_edges_extracted: true}   # M2/M5 退出条件
```

```yaml
# knowledge/1.0.30000/graph/edges/Bone_05_right1.yaml
edge:
  from: {scene: Bone_05, gate: right1}
  to:   {scene: Bone_06, gate: left1}
  kind: walk
  requires: "hasDash & (hasWalljump | hasDoubleJump)"
  world: ["PB:Bone_05:Breakable Wall (1) == true"]
  act: [1, 2]
  cost_s: {p50: 11.2, p90: 14.0}
  risk: {class: C, hazards: [SPIKES], enemies: ["MossBone Crawler x2"], wardenfly: false}
  recipe: recipes/Bone_05_right1__Bone_06_left1.json      # 已验证 50/50
```

```yaml
# knowledge/1.0.30000/playbooks/LastJudge.yaml
encounter: LastJudge
unit_class: A
pre:
  bench: <nearest Blasted Steps bench>
  runback_s: {p50: measured, p90: measured}
  loadout: {crest: Hunter, blue: [FracturedMask, MagmaBell], yellow: [WeightedBelt], red: [StraightPin, <tool>]}
  slots_required: {red: 2, blue: 2, yellow: 1}             # 槽位可行性检查
  require: {hp: max, fractured_mask: INTACT, silk_min: 9, tools_min: {StraightPin: 10}, perception_selftest: pass}
  silk_topup: {sources: [...], max_s: 90}
policy: {phases: [...], rules: [...], bind_windows: [...], forbid: [PARRY]}
post_kill: {retreat_min_u: explosion_radius_plus_1, closed_when: "no damage threats for 2.0 s"}
supervisor: {D1: 2, mask_covers: true, fire_with_magma: 1}   # 仅当审计确认 Magma Bell 已装备
variants: [standard, conservative]
```

```yaml
# knowledge/1.0.30000/interactions/grand_gate_needolin.yaml
id: grand_gate_needolin
scene: <Grand Gate scene from oracle dump>
anchor: {pos: [x, y], tol_u: 0.5}
pre: {ledger: ["bells_rung == 5"], screen: PLAYING, threats_in_support: none}
steps:
  - {input: "NEEDOLIN_PLAY(3.0)", expect: {template: grand_gate_open}, timeout_s: 8}
success: {ledger_set: ["grand_gate_open"], observe: grand_gate_open}
recovery: {retry_max: 2, else: mark_uncertain_and_replan}
yes_no_default: CANCEL
---
id: pebb_mask_shard
scene: <Bone Bottom Pebb scene>
steps:
  - {input: "INTERACT(UP)", expect: {screen: DIALOG}, timeout_s: 3}
  - {input: "ADVANCE", expect: {screen: SHOP}, timeout_s: 5}
  # OCR 文本跟随冻结的中文界面（§2.6）：条目写与语言无关的物品键，运行时从游戏的 ZH 本地化表解析为商店里显示的中文名，
  # 并用录制的商店画面核对；不写英文标签
  - {input: "SELECT_BY_OCR(item: mask_shard)", expect: {ocr_price: 300}, timeout_s: 5}
  - {input: "CONFIRM", expect: {event: PURCHASE, rosaries_delta: -300}, timeout_s: 3}
  - {input: "EXIT_SHOP", expect: {screen: PLAYING}, timeout_s: 5}
```

```yaml
# knowledge/1.0.30000/recover/game_process_lost.yaml
id: game_process_lost
detect: "process exited | window gone | no frames > 2 s"
action: [relaunch_pinned, verify_loaded_dll_hashes, ocr_title_version, continue_reserved_slot_verified,
         inventory_audit, ledger_rollback_pending, resume_from_respawn_bench]
exit_check: "PLAYING at expected bench scene within 90 s"
fault_injection: {count: 20, where: random}
```

```python
class AttemptRecord(Struct):
    unit: str; stage: str; profile: str; build: str; code_rev: str; model_revs: dict[str, str]; config_fp: str
    start_kind: str                 # savestate | continue | continuous
    outcome: str                    # CLEAR | QUIT | WOULD_DIE | STUCK | HARNESS_FAIL
    ingame_s: float; wall_s: float  # 单独给调速器，不影响“干净”
    hits: int; unpredicted_hits: int; forced_risk_events: int; min_hits_to_death: int
    invariant_violations_unpausable: int; pause_latency_frames: list[int]; quit_blocked_events: int
    safety_divergence_ticks: int
    cpe: list[str]; precursors: dict[str, int]; root_cause: str | None
```

### 4.5 接口

```python
class Frame(Struct):
    idx: int; t_sample_qpc_ns: int; t_present_qpc_ns: int | None
    image: "cupy.ndarray | torch.Tensor"     # BGRA8 (PC) 或 NV12/YUY2 (UVC)，留在 GPU
    size: tuple[int, int]; color: str; domain: str   # pc_wgc | switch_uvc | replay
    dropped_before: int

class FrameSource(Protocol):
    info: "SourceInfo"
    def open(self, cfg: dict) -> None: ...
    def latest(self, timeout_ms: int) -> Frame | None: ...
    def close(self) -> None: ...
# 实现：WgcSource, UvcSource, ReplaySource（DxgiSource 按需）

class Btn(IntFlag):
    LEFT=1; RIGHT=2; UP=4; DOWN=8; JUMP=16; ATTACK=32; DASH=64; BIND=128; CLAWLINE=256; NEEDOLIN=512
    QUICKCAST=1024; TAUNT=2048; QUICKMAP=4096; INVENTORY=8192; PAUSE=16384; SUBMIT=32768; CANCEL=65536

class PadCommand(Struct):
    buttons: Btn; move: tuple[float, float] = (0.0, 0.0)
    hold_schedule: list[tuple[Btn, int]] | None = None     # 按下时承诺的按住时序（帧）
    target_frame: int | None = None; min_hold_ms: float | None = None; issued_qpc_ns: int = 0

class ControllerSink(Protocol):
    info: "SinkInfo"            # name, keymap, min_hold（PC：≥ 2 个新帧且 ≥ max(34 ms, 2×帧时间) / Switch 40 ms）, latency, needs_focus
    def open(self, cfg: dict) -> None: ...
    def apply(self, cmd: PadCommand) -> "Receipt": ...
    def neutral(self) -> None: ...
    def pause_loop(self, press_ms: float = 34, release_ms: float = 34) -> "PauseResult": ...
        # 在 inputd 内执行；看到暂停最早线索（暗幕变暗）即停，须在真实暂停后约 230 ms 内；
        # 锁定结束前确认 PAUSE_MENU，未确认则恢复循环；或 DEATH（§3.7.5）
    def heartbeat(self, screen: Screen, menu_visible: bool) -> None: ...
    def arm_deadman(self, armed: bool) -> None: ...
    def close(self) -> None: ...
# 实现：OracleInjectSink, SendInputSink(inputd), PicoHidKbdSink, PicoSwitchSink, NullSink

class FocusGuard(Protocol):
    def ok(self) -> bool: ...
    def restore(self, timeout_ms: int = 50) -> bool: ...

class PerceptionBackend(Protocol):
    def step(self) -> WorldState: ...
# 实现：OracleBackend, DegradedOracleBackend (= Oracle ∘ ObservabilityFilter ∘ noise ∘ DelayLine),
#       VisionBackend, ShadowBackend（唯一同时看到两路的实现）
```

### 4.6 Oracle IPC（仅训练，只有实时模式）

- TCP `127.0.0.1:47017 + instance`，`TCP_NODELAY`。
- 帧格式：`u32 length | u8 msg_type | u8 schema_ver | u16 flags (bit0 = zstd) | u32 seq | msgpack payload`。

| 类型 | 方向 | 频率 | 大小 |
|---|---|---|---|
| `HELLO` | ↔ | 一次（构建 + DLL 哈希、schema、配置；不匹配则拒绝） | < 1 KB |
| `STATE`（= FrameLabel） | O → B | 每帧 | 2–20 KB |
| `TERRAIN` | O → B | 每个场景/变体 | 20–300 KB |
| `PROGRESS` | O → B | 变化时，≤ 2 Hz | 2–8 KB |
| `ACTION` | B → O | 每帧：`[target_frame u64, buttons u32, hold_frames u8, ack_seq u32]` | 16 B |
| `RPC_REQ/RES` | ↔ | `set_latency_model`、`savestate.load/save`、`randomize_start`、`set_guards`、`warp`、`dump_scene`、`get_fsm_graph`、`dump_quit_blockers`、`ping` | 小 |

oracle 从不阻塞：动作在第一个 ≥ `target_frame` 的帧生效，超过 3 帧的旧动作丢弃；250 ms 收不到 ACTION 就松开所有键并暂停。

M1 实现的细化（brain lost，只在 brain 正在驱动时生效）：
- 看门狗同时要求 250 ms 和 ≥ 6 个渲染帧没有 ACTION，主线程卡顿（场景加载、GC）饿死 STATE 时不会误判；驱动中断开连接也算 brain lost。
- 先松开所有键并丢弃排队的边沿，然后等 `pause.blk == 0`（且背包未打开）时按一次 Pause（按住 2 帧）。20 帧后仍未 PAUSED 就再按，最多 3 次：`PauseGameToggle` 在读到按键的同一帧就置 PAUSED，所以重按不会取消暂停。标题画面或没有英雄时放弃。
- brain 主动结束（断开前、空闲前、局间工作前）调用 `input.release`：松开所有键、停止驱动，不按 Pause。任何发过 ACTION 之后要空闲的客户端都必须先调它，否则游戏中会被暂停。savestate.load / randomize_start 运行期间忽略 ACTION，看门狗暂停。

---

## 5. 里程碑路线图

FTE 周按全职计；每周投入 15–20 h 时乘以约 2–2.7。门槛运行的无人值守机器时间另计。

| 里程碑 | 交付物 | 退出标准 | 预估工作量（FTE 周） | 验证的风险 |
|---|---|---|---|---|
| **M0** 探针、锁版、隔离 | 两份固定副本（计划用 `download_depot`；实际：直接复制 buildid 已确认的库副本，三份 2268 个文件 sha256 一致 [probe:P1]；库副本未卸载，自动更新为默认，它更新不影响固定副本，按 R8 从不启动）；change-list 差异 + 定点反编译；hello-world 插件；`docs/facts/1.0.30000/m0.md`；冻结配置 + 注册表快照；BIOS 微码；延迟测量 v0 | P1–P12、P14、P15 有答案；P3/P5/P7/P8 为绿；无撕裂显示模式已定；训练副本在无 Steam 子系统下能运行且存档落在沙盒 | 2 | R4 R7 R8 R9 R10 R13 R21 R26 |
| **M1** 精简 Oracle v1 | SilksongRL 分叉：导出（含暂停/退出阻塞、扣血调用栈、V/P、HUD 矩形）、守卫（SaveRedirect、LethalBlock 双网、AchievementGuard 白名单）、savestate 桥 + 随机化、多实例启动器、录制器、Rerun、compat v1；**P13 结局探针** | 60 min 录制 ≥ 99.9% 帧送达；p50 ≤ 0.3 / p99 ≤ 1.0 ms；帧时间 +0.5 ms / 1 h；投影 IoU ≥ 0.95、顶点 ≤ 1.5 px；对齐 ≥ 99.5%；4 实例 12 h soak、重置 ≤ 2 s、沙盒外 0 写入；LethalBlock 单元测试（尖刺/齿轮/抓取/熔岩）全过 | 4 | R9 R10 R11 R23 |
| **M2** Oracle 实时战斗 spike → **K1** | 运动学辨识；行为表与阶段工具；预测器、规划器（承诺按住时序）、安全过滤器、监督器 v1（暂停循环、PAUSE_PENDING、冻结态检查、quit map v0）；ObservabilityFilter + DelayLine + 简单噪声；Bell Beast + **Forum**（+ Lace 2 如有时间），用社区 savestate | 运动学验收；Bell Beast 500 次随机起点 0 WOULD_DIE、≥ 90% 通过；Forum ≥ 70% 通过且 WOULD_DIE ≤ 1%（时间盒内）；每个 A 类攻击 ≥ 200 次记录 | 6 | R2 R4 R5 |
| **M3** 精简视觉 spike → **K2** | 数据：Moss Grotto→Bell Beast、Forum、Lace 2、1 个暗房（约 80k 帧）；视觉 v0 全部头；TensorRT 管线；WGC；回环延迟报告 | §3.9.5 spike 门槛（**含 Forum 的威胁和前摇指标**） | 6 | R1 R3 R12 R16 |
| **M4** 移动、导航与交互（Act 1） | 运动模型、平台图、配方、执行器、危险图；交互目录 + `run/interact`；MenuDriver（槽位安全）；`run/recover` v1；进度看门狗 | Act 1 房间 ≥ 200 次遍历 ≥ 99.5% 成功、**0 次危险物命中**、≤ **1.15×** 每房间预算；每个配方 50/50；Act 1 交互 20/20（oracle） | 8 | R6 R24 R27 |
| **M5** Oracle 全流程到片尾 → **K3、K4，OR1** | 图导入器、谓词、两阶段 Ledger、数据生成的路线表 + 一致性检查、经济（念珠 + 壳片 + 工艺金属）、调速器、全部 A/B playbook（含 Fourth Chorus、G&Z、Forum 后备）、Act 2 交互、P16（Wardenfly）、剧情序列中退出的软锁测试 | **K3**：oracle Act 1 实时实测（含退出模型）≤ 8,700 s 且 MC P(T ≤ 17,400) ≥ 0.9，否则提出 D4'；新游戏 → 片尾 3 次连续（TRAIN，实时），0 WOULD_DIE；所有单元 G0；每个支出点在 P10 收入下余额 ≥ 需求；A 类所有 FSM 图边已提取；**K4 = 路线和配装冻结** | 15 | R2 R14 R15 R17 R24 R25 R28 |
| **M6** 规模化视觉（冻结路线）→ **OR2** | 全路线数据集；A 类和竞技场阶段头；SHADOW；前兆对比 | 所有单元 G1；Act 1 SHADOW 连续 3 次 0 WOULD_DIE，且 Act 1 ≤ 9,000 s（含退出）；Act 2 链 ×2；模拟与影子成功率在 95% CI 内 | 13 | R1 R3 R11 R12 |
| **M7** 预演与发射模型 | REHEARSAL-SEG（≥ 50% 真实 Continue 起点）、REHEARSAL-FULL、结局预演 ×5、VANILLA（外部只读裁判）、全部恢复表故障注入、24 h soak、P_run 模型、运行手册 | G2 全部单元；G3；原版等价；P10(P_run) ≥ 0.7 → D1、D3、D13 最终确认；包冻结 | 7 | R3 R13 R20 R22 |
| **M8** 正式运行 | 预检；分章运行 | STEEL_SOUL + SPEEDRUN_1 解锁，在 Steam 页面核对 | 2（+ 重试） | — |
| **M9** Switch（延伸） | PicoSwitchSink、UvcSource、域适配 | Act 1 开局（→ Bell Beast）3/3 | 6–10 | R20 |

**工作量：** M0–M8 原始合计约 **63 FTE 周**，含 1.5× 余量约 **95 FTE 周**（全职约 22 个月；每周 15–20 h 约 3.6–4.9 年）。
- **OR1**（M5 结束，oracle 驱动的全流程 bot）：原始约 41，含余量约 62 FTE 周。经你同意后，它也能以 F3 方式直接拿成就。
- F2 大约省 4 周，F3 大约省 12–15 周。

**M0/M1 探针**（在手动玩 PC 版之前完成）。M0 结果（记录在 [`facts/1.0.30000/probes.md`](facts/1.0.30000/probes.md)）：P1、P3（QueueStateEvent 注入的基本路径）、P4（前台）、P5、P9（无 Steam 运行、存档重定向）通过；P14 已回答（成就界面不能区分，只认 Player.log）；P15 已回答（死后杀进程无效，D13 关）；P7 已测受伤后的不可暂停窗口；P6、P7、P8、P11 部分完成；P10、P12 推迟到 M1/M3（需要碎裂面具和真实的感知负载）；P9 的多实例和每实例内存仍未测；P2 的代码核对是 [`facts/1.0.30000/m0.md`](facts/1.0.30000/m0.md)，其 §4 列出各探针还需运行时确认的事项。

| # | 探针 |
|---|---|
| P1 | 用 Steam 控制台下载两份副本；确认 buildid 22479045 和哈希一致；记录 Unity 版本；之后卸载库副本。**已通过**：实际直接复制库副本，library/final/train 三份 2268 个文件 sha256 一致，Unity `6000.0.50f1-uum-100966-branch1` [probe:P1]。库副本未卸载（自动更新为默认，它更新不影响两份固定副本；按 R8 从不启动它），卸载不再是必需步骤 |
| P2 | 从 EylonShachmon change-list 找出 1.0.28324→1.0.30000 的差异，只反编译涉及的文件，覆盖：`IncreaseGameTimer`、`CheckCompletionAchievements` 及其调用者、`AwardAchievementToPlayer`、`Die`/`PlayerDead`、`TakeDamage`/`TakeHealth`（含面具逻辑）、**所有扣血写入点**、**暂停门控**、**`disableSaveQuit` 的全部 FSM 写入动作（导出后与路线场景对应）**、`ScenePreloader`、ReturnToMainMenu 的保存失败分支、`EndingSequence`、`SteamOnlineSubsystem`、每一条 `[dec]` 事实、帧率设置（VSync 与帧率上限，P8 已查：二者互斥）。结果见 m0.md |
| P3 | 游戏内注入所有逻辑按键（含 Pause/Tab/I/Enter/[/]/菜单导航）。QueueStateEvent 注入已通过（菜单导航/Enter、读档、Esc 暂停、Continue 解除、走、跳，全程不在前台）[probe:P3]。余下：Tab、I、[、] 未测；键盘过滤的 isPressed 注入（后备方案，m0 §4 P3 ①）未测；legacy `Input.anyKeyDown` shim（过场跳过、Stag 跳过、UpdateEngagement、IdleMemoryCleaner）；`NativeInput=1` 是否生效；FSM 中的 PlayerInput*/Gamepad* 动作 |
| P4 | SendInput：前台有效（已通过 [probe:P4]）、后台无效、亚帧点按会丢；扫描码 vs 仅 VK、方向键带与不带 E0；按住时长与丢键率；与 `KeyboardInjector` 注入的轨迹等价 |
| P5 | **在最终副本本身**（原版 + `steam_appid.txt`，无任何加载器，叠加层和原生弹窗关闭）拿一个便宜成就（FIRST_TOOL 或 FIRST_SILK_SKILL）；输入一次 Steel Soul 代码；之后由你手动归档该槽。**已通过（2026-09-29）**：Player.log 有 `Steam stats received.` 和 `Steam achievement FIRST_TOOL (0/0) upload complete`（在商店"获得工具"提示关闭时发放）；在"额外内容"页输入代码后 `<AccountID>\shared.dat` 的 `RecPermadeathMode=1`；用过的 2 号槽已移到 `C:\ssbot\backups\` [probe:P5]。余下：解锁后选空槽是否出现模式菜单；stats 收到之前 SetAchievement 是否成功 |
| P6 | 计时器：逐帧记录 `PlayTime`，覆盖暂停、库存、**Quick Map**、**失焦**、切换、对话、**Bellway 乘车**、Ventrica、独立面板（商店、任务板、Bellway/管道地图、是/否框）、含 `InGameCutsceneInfo` 的场景、新游戏的计时起点 [m0:N23]、退出 → 读档、片尾。M0 已测：暂停不计时、库存 0.000、Quick Map 0.998、切换全程计时、原版失焦继续模拟和计时 [probe:P6] |
| P7 | 暂停与退出：按键到进入暂停的帧数；**确认门关闭时暂停键被丢弃**（代码已给出答案 [m0:N12]）；精确的循环节奏；暂停菜单中一次 Esc 是干净解除还是解除后又暂停，X/A 是否解除暂停，Continue 解除的一帧延迟；从暂停生效到检测器看到最早线索的延迟，须在 230 ms 预算内 [m0:C11]；击杀、拼刀、硬直冻结的阻塞时长；0.3 s 锁定；`disablePause` 时长分布；**运行时的 `disableSaveQuit` 来源和 Quit 灰色的状态**；Options → 返回能否刷新灰色 Quit；确认框的"否"回到哪个菜单（是否重算 Quit）；保存失败后 `PauseAllowed` 保持 false、第二次"是"能否保存；退出淡出期间世界冻结（代码已确认，只需复核）；退出 → 继续的墙钟和计时时间（C7）；HUDCamera 0.5 s 锁定；重生点；念珠是否保留；读档后丝量；读档时面具是否修复。M0 已测：退出序列与确认框默认"否"、鼠标悬停改变选中项、退出过程一直 PAUSED 且 timeScale = 0；受伤后不可暂停窗口：敌人 1 格约 250 ms、尖刺 1 格约 2.3 s，门关闭时按键被丢弃 [probe:P7] |
| P8 | WGC × 冻结显示配置（60 Hz、窗口、VSync 开）：present→capture 的 p50/p99；丢帧/重复 < 0.1%；**撕裂率**；暂停最早线索的检测延迟（P7 的 230 ms 预算的一部分）；200 次回环。M0 已测：SendInput → 首个变化帧 p50 45.6 ms、最大 49.6 ms；后台约 2% 的 33 ms 帧间隔 [probe:P8] |
| P9 | 多实例；无 Steam 子系统的运行方式（D15）；存档重定向；每实例内存。M0 已通过：无 Steam 运行（`No online subsystems packaged.`）、存档重定向到 `C:\ssbot\sandbox\saves\<instance>\`、PlayerPrefs 快照还原 [probe:P9]。余下：多实例、每实例内存 |
| P10 | Fractured Mask 的 HUD 指示；Steel Soul HUD 皮肤 |
| P11 | 序列化值（完整清单见 m0 §4）。**Hero prefab**：M0 已导出 `hero_constants.json`（INVUL_TIME 1.0 s、INVUL_TIME_PARRY 0.15 s、下劈 8/16 步、DASH_QUEUE_STEPS 10、DAMAGE_FREEZE 0/0.1/0.1、DASH_COOLDOWN 0.425 s、`fixedDeltaTime` 0.02）[probe:P11]；余下 acidDamageTag/frostWaterDamageTag 资产值。**全局**：已读 runInBackground、SuspendInBackground、InputSystem updateMode/backgroundBehavior、InControl updateMode [probe:P11]；余下 Physics2D.simulationMode、MENU_FADE_SPEED、tk2dCamera 投影类型和 initialFov、各组件每帧调用顺序。**资产**：Gameplay（weightedAnklet*、lavaBell 冷却、barbedWire 倍率、currencyCaps）、GameConfig（useSaveEncryption 等）、AchievementsList 是否含 STEEL_SOUL/SPEEDRUN_1。**逐场景**：MEMORY/CLOVER 与 ForceNotMemory、HeroKeepHealth、FrostSpeed/FrostRegions、PIT/SINK 伤害、带 TinkEffect 的尖刺、BossSceneController、ScenePreloader 与 activateTrigger、InGameCutsceneInfo、noEndSlomo。**FSM 导出**：disablePause/disableSaveQuit/disableInventory 写入、SetInputHandlerSkipMode、FreezeMoment 类型、特殊扣血动作和 DamageHeroDirectly 的调用者、Bind FSM、路线敌人的 DamageHero flags（核对 [com10]）、CogMultiHitter 的 WOUND START、Underworks 锯。**外部裁判**：为 1.0.30000 重新推导 Mono 字段偏移。**名称对应表**（WeightedAnkletTool = Weighted Belt、LavaBellTool = Magma Bell、bellBindFSM = Warding Bell、SilkChargeEnd = Sharpdart、MultibindTool = Multibinder，另加 barbedWire = Barbed Bracelet）一并确认 |
| P12 | 推理负载下 60 fps 的帧时间；超过 21 ms 的帧出现频率（影响点按 [m0:N37]）；长时间暂停时 IdleMemoryCleaner 的 GC 卡顿 |
| P13（M1） | 结局：训练副本加载社区 GMS savestate，AchievementGuard 设为只记录。记录哪个 FSM 调用 `CheckCompletionAchievements`，它和 `SaveGame` 相对于 Bind、`SetEndingCompleted`、结局动画、End_Credits 的帧位置；被检查的 playTime 值；是否位于可跳过步骤内；跳过片尾是否有影响；Ending A 是否显示 End_Game_Completion（秒级读数 [m0:N25]）；Ending A 之后同一存档能否重打 GMS 并再次触发检查（Steam 故障时唯一的补救途径） |
| P14 | Extras → Achievements 界面在 Steam 已初始化和未初始化时是否真的不同。按代码它会退回 shared.dat [m0:N35]。**结果：不能区分**——无 Steam 子系统的训练副本只凭沙盒 shared.dat 里的本地 `FIRST_TOOL=1` 就把该成就显示为已解锁；预检和结局核对只认 Player.log（`Steam logged in as`、`Steam stats received.`、每个成就的 `upload complete`）[probe:P14] |
| P15 | 杀进程的语义（D13）：Die 前杀、Die 后杀、SaveGame 期间杀；致命帧 → `user{N}.dat` 落盘的耗时；Dead 是否同时写入版本备份 `user{N}_1.0.30000.dat`；死亡后 `.bak*` 轮换与 `Restore_Points` 的状态。在沙盒 Steel Soul 槽上测。**M0 已测：** 致命伤后约 142 ms `user{N}.dat` 已是 Dead；死后 +103 ms（taskkill 最快）到 +1123 ms 杀进程均留下 DEFEATED 槽；`.bak1` 保留存活状态 [probe:P15] |
| P16（M5） | Wardenfly 捕获 + 捕获后退出，确定恢复方案 |
| P17（M2 前） | 纹章运行时导出（清单见 [`research/crests.md`](research/crests.md) §5）：各纹章 `HeroControllerConfig`、各挥刀的伤害/产丝/`canHitSpikes`/世界坐标碰撞体、下劈 i-frame、Hunter 连击计数与清零原因、Wanderer dash-combo 与暴击冻结、槽位与 Locket、Chapel_Wanderer 入口与竞技场、Eva 的强制换装；离线资产值（`[asset]`）以此为准 |

**MVP 阶梯（每级都能停下来，并有通过门槛）：**
1. Oracle 录制 + 查看器：60 min ≥ 99.9% 帧送达。
2. Bell Beast savestate：500 次 0 WOULD_DIE、≥ 90% 通过（oracle）。
3. 新游戏 → Bell Beast（oracle）：10/10。
4. 同上（视觉，SHADOW）：10/10，0 CPE。
5. Act 1 视觉：连续 3 次 0 WOULD_DIE。
6. 全流程 SHADOW：2 次。
7. 正式运行。

**检查点与回退阶梯的触发条件**（事先约定，届时你带着数据决定）：
- **K1（M2）：** Forum 在 2× 时间盒内 WOULD_DIE 仍 > 2% → 先改路线、配装或助战，再继续投入。
- **K2（M3）：** Forum 上前摇 top-1 < 90%，或伤害区域召回（4 u 内）< 99%，并且 2× 时间盒后仍不达标 → 讨论 F2/F3 或 D3。
- **Act 1 SHADOW（M6）：** 视觉前兆率 > 2× oracle，或 Act 1 P_run < 0.9 → 同上。
- **M7：** 两轮改进后 P10(P_run) < 0.7 → 同上。
- **K3（M5）：** 时间条件不满足 → D4'。

**分段完成的定义：** 图和路线条目存在 → G0 → 视觉数据入库并通过离线重感知 → G1 → 时间 p50/p90 写入预算 → 交互条目 20/20。

**正式运行失败（死亡）后的策略：** 做 postmortem；为出问题的单元重新取得 G1/G2 证据，加 1 次 REHEARSAL-FULL；然后由你归档 DEFEATED 槽，开新的 Steel Soul 槽。预计间隔 1–3 周。

---

## 6. 风险清单

| # | 风险 | 可能性 / 影响 | 缓解 | 早期测试 |
|---|---|---|---|---|
| R1 | 视觉漏看前摇、威胁或 HUD | H / H | oracle 大规模标注；可观测阶段 HMM；与表中判定框求并；回退阶梯 | M3 spike |
| R2 | 难点单元死亡率高于约 1% | H / H | 禁入区；助战者；Cogfly；配装；保守变体；绕路 A/B | M2 |
| R3 | 训练与正式运行的差距（延迟、输入语义、执行时序） | M / H | 回环实测；承诺按住时序；在实时数据上验证运动学；G2 | P4、P8；M6 CI |
| R4 | 暂停/退出不可用或迟到（TimeSlowed、0.3 s 锁定、`disableSaveQuit`、预加载），或循环停得太晚导致非预期解除暂停 [m0:C11] | M / H | 无条件循环 + 最早线索停手；PAUSE_PENDING；quit map；I1/I3；灰色 Quit 策略；D13 | P7；G1 注入 |
| R5 | 爆发或绕过面具的伤害（抓取、GMS 网、齿轮、DamageTag、Critical） | M / H | 挂起伤害；`mask_covers`；路线回避；爆发前兆必须为 0 | P2 扣血清单；M2 日志 |
| R6 | 危险物、击退致死（人类的主要死因 [com18]） | M / H | 危险物即墙；击退包络；I2；门作软危险物 | M4：0 次命中 |
| R7 | `[dec]` 事实在 1.0.30000 上不同 | M / M | 复核；数据驱动的校准 | P2 |
| R8 | 版本漂移 / Sea of Sorrow | **H** / M | 固定 depot 副本；从不启动库副本；已加载 DLL 哈希 + OCR 版本号；按构建打标签的知识 | P1、P5 |
| R9 | 训练或预演中意外解锁成就 | L / M | 无 Steam 子系统 + 重定向 + AchievementGuard；原版预演硬停 | M1 |
| R10 | 训练损坏真实存档 | L / H | 重定向、SlotGuard、哈希、备份 | M1 |
| R11 | 标签或特权信息泄漏 | M / H | 防火墙；import 禁令；像素差；ObservabilityFilter | M1/M3 CI |
| R12 | 相关性失败（例如某个暗房） | M / H | Q4 异常项；按房间报告；暗房清单 | M6 |
| R13 | 环境中断（焦点、UAC、更新、弹窗、ACCESS_LOST）；失焦时英雄失控而世界和计时照常 [probe:P6] | M / H | 焦点守护；预检设置；拔鼠标；不接手柄；分章；恢复表 | 24 h soak |
| R14 | 经济短缺（念珠、壳片） | M / M | P10 收入；刷取循环；变体降级 | M5 |
| R15 | Wardenfly 捕获 | L / H | 标记边不可行；删除 S16；捕获检测器 | P16 |
| R16 | GPU 争用 | L / M | +0.5 ms 门槛；训练时间窗与门槛运行错开 | P12、M3 |
| R17 | 计时超限 | **M / M** | 自底向上预算；K3；调速器；D4/D4' | M5 实测 |
| R18 | 单人范围蔓延 | H / H | 按需扩展清单；off-ramp；检查点 | 每个里程碑 |
| R19 | Python 3.13 缺 wheel | L / L | uv 管理的 3.12 venv | M1 |
| R20 | Switch 版本或延迟不匹配 | M / L | 读取版本号；对比阶段时长 | M9 |
| R21 | 共享状态泄漏（设置、键位、`shared.dat`、Cloud） | M / H | §2.7；注册表快照；OCR 选项页 | M0 |
| R22 | 结局成就推送静默失败 | L / H | 最后一章重启 Steam；P14；ENDING 锁输入；先核对 Steam | P13、P14 |
| R23 | LethalBlock 定义错误导致统计失真 | M / M | 面具后判定；第二网；单元测试 | M1 |
| R24 | 交互或 UI 执行错误（错误许愿、购买、Restore/Clear） | M / H | 交互目录；默认 Cancel；OCR 选择；白名单；删除动作编译掉 | M4 |
| R25 | Ledger 与存档不同步 | M / H | 两阶段提交；读档后以审计为准 | M5 故障注入 |
| R26 | CPU 不稳定导致部分挂起 | M / H | 微码 0x12B+；心跳；死人开关 | M0 soak |
| R27 | 无进展循环烧时间 | M / M | 进度看门狗 | M4 |
| R28 | 退出时保存半完成的剧情状态导致软锁 | L / H | 剧情序列只在必死时退出；逐序列测试 | M5 |

**对 F1 的诚实估计：** 即使 oracle bot 成功，纯视觉达到发射门槛的概率也只有约 30–50%，而且它决定了整个进度。这就是回退阶梯存在的原因。

---

## 7. 需要你决定的事项

M0 之前只需要决定 D8、D9、D15。

| # | 决策 | 选项 | 推荐 | 时间点 |
|---|---|---|---|---|
| D1 | 正式运行能感知什么 | **F1 纯视觉（你的意愿）** / F2 外部只读内存（仅 HP、丝、场景、playTime，敌人仍靠视觉）[pri19][mod8] / F3 进程内只读观察插件（作弊代码编译掉；成就仍可解锁 [mod14]） | 以 F1 为计划；在 K2、M6、M7 按 §5 约定的触发条件带数据再决定 | K2、M6、M7 |
| 回退阶梯 | 按与你意愿的偏离程度排序（最终排序由你定） | ① D3 工作台存档恢复（游戏仍是原版，仍纯视觉，成就仍然有效 [ach6]；恢复会回滚 playTime，死亡只花墙钟时间；可容忍的单元死亡率从约 1% 升到 10–20%，门槛工作量约减少 70%）② F2 ③ F3 ④ 两局（D4'） | 我们的默认顺序是 ①→②→③，④ 与之正交 | 同上 |
| D2 | 正式运行能否用 mod 提取的知识 | 能（像背过 wiki） / 不能（纯像素地形和规则） | **能** | M1 前 |
| D3 | 存档备份恢复策略 | 不恢复 / 仅限基础设施事件（断电、系统弹窗、驱动崩溃、MenuDriver 误删/误恢复；事先书面定义并记录） / 工作台检查点恢复 | **仅限基础设施事件**。软件总是写备份；允许恢复时关闭 Cloud | M7 前 |
| D4 | 中途判断速通已不可能 | 继续拿钢铁之魂，速通以后 Classic 单独打 / 放弃重来 | **继续** | M8 前 |
| **D4'** | 一局还是两局 | 一局（默认）/ 两局：Steel Soul 局取消调速器和精密计时，保留所有安全绕路；另打一次 Classic 速通，它同时充当原版到片尾的全程预演，允许死亡 | 在 K3 按实测决定；K3 条件不满足时推荐两局 | K3（M5） |
| D5 | PC 正式运行的输入设备 | SendInput（inputd）/ RP2040 USB 键盘 | **SendInput**。RP2040 只多挡 rt/inputd 崩溃，挡不住主机崩溃和焦点丢失；它为 Switch 而做，届时如果通过等价测试也可在 PC 上使用 | M7 |
| D6 | 章节之间能否由操作员从存档文件读 playTime | 能 / 不能 | **不能**。用存档选择界面 OCR，600 s 余量覆盖其分钟级分辨率（向下取整，少 0–59.99 s）。补充：存档加密的固定密钥在代码中可见，技术上可以离线读出 playTime [m0:N33]；End_Game_Completion 提供秒级读数 [m0:N25]。决定仍由你来做 | M5 |
| D7 | 音频作为额外传感器 | 关 / 开 | **关**。只有在前摇确实模糊、而声音能区分时再考虑 | K2 |
| D8 | 正式运行前会解锁哪些成就 | 接受：P5 的一个便宜成就 + 原版预演中的进度成就 | **接受**。除 P5 外永不手动玩最终副本；到片尾的预演只在训练副本上做 | **已定（2026-09-29）：接受。** 你说这份 PC 版专门给 bot 用 |
| D9 | 硬件 | 显示器：现有 LG TV（最高 60 Hz），不换；第二显示器（放调试界面，可选）；数据盘：现有 980 PRO 2 TB 够用到 M3，M6 前再加一块 2 TB NVMe；BIOS：原为 1402（2023-09，微码 0x11D），2026-09-29 已更新到 1836（微码 0x133，含 Vmin 修复）；更新前 9-02 曾出现 P-core 0 的 WHEA 纠错，需在 M0 soak 中复查；以后再买 RP2040 和采集卡 | ~~现在就更新 BIOS~~ 已完成（2026-09-29）；M0 soak 后复查 WHEA；显示器保持 60 Hz（最高 60 Hz）；NVMe 等到 M3 结束再买 | M0 |
| D10 | 帧率 | 60 | **已定：60**（显示器最高 60 Hz，2026-09-29） | — |
| D11 | Switch 延伸 | 做 / 不做 | M8 之后再说；只是演示（本地成就） | M8 后 |
| D12 | 你自己录制的 PC 游玩（30–40 h） | 做 / 不做 | **做**，在训练副本上（无 Steam 子系统，含 1–2 个 Steel Soul 训练槽）；同时是交互目录的素材 | M1–M3 |
| **D13** | 预测式杀进程作为最后防线 | 关 / 开 | **已定：关**（2026-09-29）。P15：死后约 142 ms 已写盘，而视觉确认死亡就要约 46 ms，死后杀进程必然太晚；预测式杀进程与紧急暂停退出没有实质区别 [probe:P15] | — |
| **D14** | 最终副本的身份 | 固定 depot 文件夹 + `steam_appid.txt`（推荐）/ Steam 库副本（仅当届时仍是 1.0.30000） | **固定 depot**。请确认 `steam_appid.txt` 在你看来不算"修改"（它不改游戏代码，只告诉 Steamworks 应用 ID） | M0 / M7 |
| **D15** | 训练副本如何脱离 Steam | 重命名 `steam_api64.dll` / DisableSteam 类插件 / `steam_appid.txt = 480` | **重命名**：P9 已验证能启动，日志为 "No online subsystems packaged."，不经 Steam 重启，存档落到 `default` [probe:P9]。插件和 480 只作后备 | M0 |

---

## 8. 技术栈与仓库结构

### 8.1 技术栈

- **C#（仅训练）：** .NET 8 SDK，目标 net472 或 netstandard2.1（按 GameLibs 模板）；BepInEx.Core 5.4.x、HarmonyX、MonoMod、Silksong.GameLibs 1.2.0-silksong1.0.30000；DebugMod 为软依赖；MessagePack-CSharp。检查工具：ILSpy/dnSpyEx、UnityExplorer、FsmMaster/FSMExpress、AssetRipper [mod20]。
- **Python：** uv 管理的 3.13 venv（GPU 或捕获相关 wheel 缺 cp313 时用 3.12）。
  - numpy、numba、msgspec、zstandard、pyarrow
  - torch（CUDA 12.x）、ultralytics（AGPL-3.0，个人使用没问题）、TensorRT 10 或 onnxruntime-gpu（TensorRT EP）、CuPy
  - windows-capture（WGC）、opencv-python、PyAV
  - rerun-sdk、networkx、pyserial、pytest
- **固件（延伸）：** pico-sdk + TinyUSB；参考 GP2040-CE 和 Pokemon Automation 固件。
- **复用**（核对许可证；优先写导入脚本，而不是把代码拷进来）：

| 来源 | 取用内容 |
|---|---|
| SilksongRL（MIT） | **插件骨架**：socket、存档抑制、BossStateLogger、多实例启动器；它的 ButtonControl 注入只作后备（§3.1.1），LethalDamagePatch 要按 [m0:C2] 重写（完整复刻蓝血和面具；它的 `pd.health - amount > 0` 忽略二者，m0 §2.5） |
| DebugMod（MIT） | savestate、`CategorizeHitbox`、FreezeMoment hook 写法 |
| EylonShachmon/Silksong-change-list | P2 的版本差异 |
| Silksong.Benchwarp、Archipelago APWorld、zerounit AP logic | 世界图 |
| silksong-autosplit-wasm | F2 字段表；VANILLA 外部只读裁判；约 167 个分割 ID 作 Ledger 检查点 |
| ItemChanger.Silksong（LGPL）/ silksong-data-dump | 只用数据，不链接代码；路线一致性检查 |
| HKSplitMaker `any-bells.json` | 目标顺序 |
| vichisuki savestate | 早期起步；M2/M3 的 Forum、Lace 2 场景 |
| hollow_knight_bot | 设计参考（postmortem 剪辑） |

### 8.2 仓库结构（`C:\modeling\silksong_bot`）

```
silksong_bot/
  versions.lock                 # 构建、manifest、buildid、DLL 哈希（两份副本）、加载器版本、
                                # 注册表快照哈希、冻结设置（fps、震动 Off、粒子 Low、HUD 缩放、键位、输入后端）
  docs/  design.md  adr/  facts/1.0.30000/*.md
         runbooks/{preflight.md, final_run.md, emergency.md, final_chapter_steam_check.md, pin_depot.md}
  oracle/                       # 从 SilksongRL 分叉的 BepInEx 5 插件 SsOracle（仅训练）
    SsOracle.csproj
    src/Core/{Plugin,Profile,SymbolCheck}.cs
    src/Export/{Hero,EntityRegistry,FsmTap,SceneDumper,Progress,EventTap,PauseQuitTap,HealthTap,
                Camera,HudProbe,FrameExporter,Schema}.cs
    src/Input/{InjectTable,KeyboardInjector,ButtonControlPatch(后备),InputPathEmulator}.cs
    src/Train/{SavestateBridge,StartRandomizer,Warp}.cs
    src/Guards/{SaveRedirect,SlotGuard,SaveSuppression,LethalBlockTakeHealth,LethalBlockDieNet,
                AchievementGuard,SteelSoulSnapshot}.cs
    src/Ipc/{Server,Rpc}.cs
    tests/                      # LethalBlock：尖刺/齿轮/抓取/熔岩脚本
  brain/  pyproject.toml  ssbot/
    core/        worldstate.py  config.py  profiles.py  fingerprint.py  clock.py
    io/frame_sources/  wgc.py  uvc.py  replay.py
    io/sinks/          oracle_inject.py  sendinput.py  inputd.py  focus_guard.py  pause_detector.py
                       pico_hid.py  pico_switch.py  null.py
    ipc/         oracle_client.py  framing.py
    backends/    oracle_backend.py  observability.py  noise_simple.py  delay_line.py  vision_backend.py  shadow.py
    perception/  screenmode/  menu_read/  hud/  inventory/  localize/  terrain_verify/  detect/
                 phase_cls/  phase_hmm/  hero_state/  track/  timer/  tear/  fuse/
    knowledge/   scene_db.py  hitbox_tables.py  phase_tables.py  behaviour_tables.py  damage_tables.py
                 kinematics.py  quit_map.py  coverage_maps.py
    world/       graph.py  predicates.py  ledger.py (two-phase)  entities.py
                 importers/{benchwarp,archipelago,itemchanger,splitmaker}.py
    nav/         motion_model.py  platform_graph.py  planner.py  recipes.py  executor.py
    combat/      forecast.py  tactics/  planner.py  safety_filter.py  bind.py  parry.py  pogo.py  playbooks.py
    safety/      supervisor.py  hits_to_death.py  invariants.py  pause_quit.py  unpause_check.py
                 watchdog.py  progress_watchdog.py  last_resort.py (D13, 默认禁用)
    run/         manager.py  ending.py  menus.py  route_bell.py  economy.py  loadout.py (slot feasibility)
                 time_governor.py  chapters.py  interact/  recover/
    record/      recorder.py  formats.py
    train/       detector/  phase/  hud/  screenmode/  localize/  tuning/ (CMA-ES)
    tools/       viewer.py  postmortem.py  dataset_builder.py  projector.py  pixel_leak_test.py
                 latency_harness.py  shadow_gate.py  bayes_gate.py  prun_model.py  compat.py
                 route_check.py  external_referee.py (VANILLA, 只读)
    tests/       test_import_firewall.py  test_invariants.py  test_hits_to_death.py  test_pause_loop.py
                 test_menu_whitelist.py  test_ledger_rollback.py
  knowledge/1.0.30000/          # 生成、版本化、带哈希（Git LFS）：scenes/ enemies/ playbooks/ graph/
                                # recipes/ interactions/ recover/ constants.json quit_map.json
  pico/    hid_kbd/  switch_hori/
  scripts/ launch.ps1 (profiles)  preflight.ps1  registry_snapshot.ps1  verify_versions.py
  models/  (gitignored; registry.json 带哈希)
  data/  runs/  (gitignored；放在专用 NVMe 上)
```

**CI 规则：**
- import 防火墙：`perception/`、`combat/`、`nav/`、`run/`、`safety/` 不得 import `ipc/` 或 `backends/oracle_backend`；正式运行模块只接受 `VisionView`。
- 每次构建数据集都跑像素泄漏测试。
- 每次改动知识或路线都跑 `route_check.py`。
- 每个会话前跑 compat 套件。
- `test_menu_whitelist.py` 保证 FINAL 构建中不存在删除/清除路径。

---

## 附录 A：审阅记录

说明："采纳"表示按评审建议修改；"部分采纳"会写明理由。定稿时只核查了本地反编译和 wiki 摘录，没有做网络调研。

| # | 来源 | 问题 | 处理 | 位置 |
|---|---|---|---|---|
| 1 | death-redteam（阻断） | 暂停只在检测到冻结时重按；TimeSlowed、0.3 s 锁定、边沿触发 | 采纳：无条件按/放循环（34/34 ms）、PAUSE_PENDING、阻塞源全部记录、G1 注入中 ≥ 30% 落在击杀/弹反/硬直附近 | §1.2、§3.7.4–3.7.5 |
| 2 | death-redteam（阻断） | 退出可用性 ≠ 暂停可用性 | 采纳：quit map；I1 改为以"可退出"为前提；`disableSaveQuit` 区域并入 I3；识别灰色 Quit；灰色时保持暂停轮询 60 s；P2/P7 导出 FSM 写入点 | §3.7.2、§3.7.5、§5 |
| 3 | death-redteam | 解除暂停后直接回到威胁中 | 采纳：18 帧视为不可暂停；冻结态检查；P1 受限 + 计划缓存；Q5 附加条件 | §3.7.4–3.7.5 |
| 4 | death-redteam | 暂停和退出都不可用时没有后手 | 采纳为决定 D13，默认关闭；不启用时扩展 I3 | §3.7.7、D13 |
| 5 | death-redteam | 焦点丢失与输入路由 | 采纳：焦点守护、预检设置、P6、注入测试；D5 理由已更正，推荐改为 SendInput | §2.6、§3.7.6、D5 |
| 6 | death-redteam | 伤害模型漏掉非 TakeDamage 的扣血 | 采纳：扣血清单、调用栈记录、`pending_dmg`、齿轮、Critical、状态暗角 | §1.6、§3.5.6、§3.7.1 |
| 7 | death-redteam | LethalBlock 定义错误 | 采纳：按面具结算后判定 + 第二网 + 单元测试；任何 Die 都记为死亡 | §3.1.1 |
| 8 | death-redteam | "只在启动时更新"不算锁版 | 采纳：固定 depot 副本为最终副本；P5 在该副本上做；卸载库副本；加载 DLL 哈希 + OCR 版本 | §1.4、D14 |
| 9 | death-redteam | 共享状态；AchievementGuard 是单点 | 采纳：无 Steam 子系统 + 重定向 + Guard 三层；注册表快照；OCR 选项页；关 Cloud；放行 `RecPermadeathMode`；原版预演硬停。appid 480 只作最后手段（多余地向 Steam 发调用） | §2.7、D15 |
| 10 | death-redteam | 结局时成就推送可能静默失败 | 采纳：最后一章重启 Steam；P14；ENDING 锁输入；先核对再动存档；结局预演 ×5 | §3.6.1 |
| 11 | death-redteam | 存档选择界面误操作 | 采纳：白名单、OCR 核对槽位、皮肤验证、新游戏验证、拔鼠标、写入 D3 | §3.6.2 |
| 12 | death-redteam | 非保存退出后 Ledger 不同步 | 采纳：两阶段 Ledger；读档后以审计为准；BIOS 微码；磁盘空间预检 | §3.3.4、§4.3 |
| 13 | death-redteam | 时间预算不现实；Pebb 位置错 | 采纳：预算 v2（期望约 16,100 s）；M4 改为 1.15×；Pebb 改到 Bone Bottom。部分采纳：go/no-go 从 6,700 s 改为 8,700 s + MC 条件，因为 6,700 来自旧的乐观先验 | §3.6.4、§3.6.6 |
| 14 | death-redteam | 没有无进展看门狗 | 采纳 | §3.6.7 |
| 15 | death-redteam | Wardenfly 被当作有限代价 | 采纳：标记边不可行、删除 S16、刷取循环回避、必要时 Faydown 必选、捕获检测器 | §3.4.3 |
| 16 | death-redteam | 配装超出可用槽位 | 采纳：Locket #1/#2（+#3）、槽位可行性检查、上下文只从审计推出 | §3.6.5 |
| 17 | death-redteam | 死人开关的 Esc 会切换 | 采纳：inputd 自带检测器循环；Pico 抖动下限 | §3.7.6 |
| 18 | death-redteam | 退出可能保存半完成状态；保存失败 | 采纳：剧情序列只在必死时退出；逐序列测试；5 s 内必须到主菜单 | §3.6.2、§3.6.8 |
| 19 | death-redteam | 计划输入与执行输入不一致 | 采纳：承诺按住时序 + ABORT；在执行流上 rollout；实时数据验证；余量加入方差 | §3.5.2、§3.5.4 |
| 20 | death-redteam | 独占全屏撕裂 | 采纳：只用无撕裂模式、撕裂检测、P8 撕裂率 | §2.6、§3.2.8 |
| 21 | death-redteam | 击退穿门 | 采纳：门作软危险物、进入风险表、只躲避、场景先验含所有门 | §3.4.2、§3.2.3 |
| 22 | death-redteam | Shell Shard 经济 | 采纳：纳入经济；交战门降级为保守变体 | §3.6.5 |
| 23 | death-redteam | savestate 起点抬高 G2 证据 | 采纳：≥ 50% 真实 Continue；两比例检验前按 0.7 折扣 | §3.9.4 |
| 24 | scope（阻断） | 门槛数学上过不去 | 采纳：时间移出"干净"定义、序贯贝叶斯、只有指纹变化才重置、前兆比 ≤ 1.5×、G3 为最近 4 次中 ≥ 3 次；B/C 用分层汇总（补充） | §3.9.4 |
| 25 | scope（阻断） | 缺少非战斗交互子系统 | 采纳：`run/interact` + 交互目录 + 三个新原语 + 默认 Cancel；退出标准 20/20 与 3/3 | §3.6.3、§4.4 |
| 26 | scope | 存档隔离与锁版的操作细节 | 采纳（与 #8、#9 合并）；R8 升为 H | §1.4、§2.7 |
| 27 | scope | 结局序列 | 采纳：ENDING 状态、P13 | §3.6.1、§5 |
| 28 | scope | G&Z 助战 | 采纳：Garmond 对话步骤、屋顶捷径、切磋改为有危险物的 B 类、Forum 后备 playbook | §3.6.4、§3.5.7 |
| 29 | scope | AchievementGuard 挡住了 Steel Soul 解锁 | 采纳：白名单；MenuDriver 先查模式选择；FINAL 中不输入代码 | §1.2、§3.6.2 |
| 30 | scope | 意外状态的恢复 | 采纳：恢复表 + 故障注入 | §3.6.8 |
| 31 | scope | 里程碑顺序 | 采纳：战斗 spike 含 Forum → 视觉 spike 含 Forum/Lace 2/暗房 → oracle 全流程 → 冻结路线 → 规模化视觉 | §5 |
| 32 | scope | 纯视觉可行性与诚实的回退 | 采纳：30–50% 估计、回退阶梯、事先约定的触发条件、量化 D3 | §0、§5、§6、§7 |
| 33 | scope | 速通预算 | 采纳：开销分项、实时节奏测量、R17 升为 M/M、D4' | §3.6.6、D4' |
| 34 | scope | 工作量与 off-ramp | 采纳：自底向上约 63 + 1.5× ≈ 95；OR1/OR2/OR3 | §5 |
| 35 | scope | lockstep 与 RL 基础设施过度设计 | 部分采纳：lockstep、UnscaledPatches、TRAIN-V、PPO/DAgger、拟合 NoiseModel 移到 §3.11；配置合并。**保留 ObservabilityFilter**：它让 oracle 上开发的规则能迁移到视觉并防止特权泄漏，成本约 1 周 | §3.9、§3.11 |
| 36 | scope | 视觉栈过度设计 | 部分采纳：去掉图集/描述子/LK/检索/re-ID/前向 MLP/普通敌人阶段/ResNet 地形/对抗泄漏测试/双后端，数据约 1 TB。**保留**：复用分割的轻量地形验证（崩溃后 Ledger 回滚需要视觉确认，零额外模型）；Hornet 约 12 类的小状态头（受击和 Bind 检测，100k crop） | §3.2、§3.11 |
| 37 | scope | 暂停重按策略 | 采纳，并与 #1 统一：看到菜单后 500 ms 不按；利用 0.3 s 锁定去抖；P7 测节奏与排队 | §3.7.5 |
| 38 | scope | 路线数据一致性 | 采纳：由数据生成 + `route_check.py`；碎片算术更正为 8 个；Fourth Chorus 默认开打（A）；三个可跳过 boss 在 M1 前定 | §3.6.4 |
| 39 | scope | Shell Shard | 采纳（与 #22 合并） | §3.6.5 |
| 40 | scope | 最终槽位与设置管理 | 采纳：删除动作编译掉；按模板核对槽位；compat 检查设置 | §3.6.2、§3.10 |
| 41 | scope | 复用现有项目 | 采纳：分叉 SilksongRL；标准序列化；P2 基于 change-list；VANILLA 外部只读裁判 | §3.1.1、§8 |
| 42 | scope | 缺少退出标准 | 采纳：MVP 通过门槛；M5 经济与交互条件；A 类覆盖度；正式运行失败后的策略；删去 M3 的"≥10× 实时" | §5 |
| 43 | scope | CPU 稳定性、单 GPU、撕裂 | 采纳：微码、训练时间窗或云 GPU、无边框 + WGC、撕裂检查 | §2.6、§3.1.6、§3.8.1 |
| 44 | M0 代码核对（m0.md）+ 运行时探针（probes.md），2026-09-29 | 1.0.28324 的说法在 1.0.30000 上有 18 处要改（C1–C18），另有 43 项新发现（N1–N43）；探针给出实测常量和失焦行为 | 采纳 m0 §5 的修改和探针结果。推翻的旧结论：#37 的"0.3 s 锁定天然去抖"（锁定后 Esc 会解除暂停，改为最早线索停手）；#3 的"18 帧"改为 0.3 s 实时；#2/#18 的"灰色 Quit 轮询 60 s""5 s 内到主菜单否则重走暂停"改为 Options → 返回、I3 预规划和 SAVE_FAILED 流程；§1.6 焦点行的"失焦只清空输入"改为实测行为（世界和计时继续，英雄失控） | §0、§1.2–§1.6、§2、§3、§5、§6、D6、D15 |
| 45 | 用户决定（2026-09-29）与 m0 冲突 | m0:N40 和 m0 §5 第 14 条要求 FINAL 前设 GameLang = EN | 不采纳：界面语言冻结为中文，菜单模板和 OCR 按中文做 | §2.6、§2.7 |
| 46 | 用户决定（2026-09-29）与 m0 冲突 | m0:C12 和 m0 §5 第 4 条写"120 fps 下 36 帧" | 不采纳：显示器最高 60 Hz，只写 60 fps 下 18 帧 | §1.2 |

---

## 附录 B：关键参考资料

**成就、版本、计时**
- Steam 成就页：https://steamcommunity.com/stats/1030300/achievements
- 发布版反编译（1.0.28324）：https://github.com/ROWANIVERSON-debug/decompiled-silksong （GameManager.cs、AchievementHandler.cs、PermadeathUnlock.cs、UnityEngine.UI/SaveSlotButton.cs、HeroController.cs、InputHandler.cs）
- 版本差异：https://github.com/EylonShachmon/Silksong-change-list
- Manifest 与降级：https://github.com/hk-speedrunning/Silksong-Resources/blob/main/manifests.md ，https://github.com/hk-speedrunning/Silksong-Resources/blob/main/setup.md ，https://www.speedrun.com/api/v2/GetGuide?id=6puuo
- SteamCMD 信息：https://api.steamcmd.net/v1/info/1030300
- Team Cherry 补丁说明：https://www.teamcherry.com.au/blog/silksong-patch-4 ，https://www.teamcherry.com.au/blog/silksong-patch-5
- Unity `captureDeltaTime`：https://docs.unity3d.com/ScriptReference/Time-captureDeltaTime.html

**Wiki（hollowknight.wiki）**
- 结局：https://hollowknight.wiki/w/Endings_(Silksong)
- Steel Soul：https://hollowknight.wiki/w/Steel_Soul_Mode_(Silksong)
- 存档数据：https://hollowknight.wiki/w/Save_Data_(Silksong)
- Fractured Mask：https://hollowknight.wiki/w/Fractured_Mask
- Bind：https://hollowknight.wiki/w/Bind
- 面具碎片：https://hollowknight.wiki/w/Mask_Shard_(Silksong)
- Hunter Crest：https://hollowknight.wiki/w/Hunter_Crest
- Garmond & Zaza：https://hollowknight.wiki/w/Garmond_and_Zaza
- Shakra：https://hollowknight.wiki/w/Shakra
- 连战：https://hollowknight.wiki/w/Enemy_Gauntlets_(Silksong)
- Last Judge：https://hollowknight.wiki/w/Last_Judge
- Cogwork Dancers：https://hollowknight.wiki/w/Cogwork_Dancers
- The Mist：https://hollowknight.wiki/w/The_Mist
- The Slab：https://hollowknight.wiki/w/The_Slab
- Warding Bell：https://hollowknight.wiki/w/Warding_Bell
- Magma Bell：https://hollowknight.wiki/w/Magma_Bell
- Weighted Belt：https://hollowknight.wiki/w/Weighted_Belt
- 版本更新：https://hollowknight.wiki/w/Updates_(Silksong)

**Mod 与工具**
- BepInExPack_Silksong：https://thunderstore.io/c/hollow-knight-silksong/p/silksong_modding/BepInExPack_Silksong/
- Silksong.GameLibs：https://www.nuget.org/packages/Silksong.GameLibs
- DebugMod：https://github.com/hk-speedrunning/Silksong.DebugMod （Hitbox/HitboxRender.cs、SaveStates/SaveState.cs）
- SilksongRL：https://github.com/jimmie-jams/SilksongRL （SaveStates/LethalDamagePatch.cs、Encounters/BossStateLogger.cs）
- DisableSteam（D15 参考）：https://github.com/jakobhellermann/silksongmod-DisableSteam
- 自动分割器：https://github.com/AlexKnauth/silksong-autosplit-wasm
- Benchwarp：https://github.com/homothetyhk/Silksong.Benchwarp
- ItemChanger.Silksong：https://github.com/homothetyhk/ItemChanger.Silksong
- silksong-data-dump：https://github.com/jakobhellermann/silksong-data-dump
- Archipelago APWorld：https://github.com/Batatvideogames/silksong-archipelago-randomizer
- zerounit AP logic：https://github.com/zerounit-dev/silksong-rando-ap-logic
- HKSplitMaker 分类：https://github.com/slaurent22/hk-split-maker/tree/main/src/asset/silksong/categories
- vichisuki savestate：https://github.com/vichisuki/vichisuki-Silksong-Practice-Resources/blob/main/BellRoute-LP/Savestates/BELLROUTE-SAVESTATES-README.md
- FSMExpress（skong 分支）：https://github.com/nesrak1/FSMExpress/tree/skong
- FsmMaster：https://github.com/ConstructiveCynicism/FsmMaster

**路线与指南**
- 速通规则：https://github.com/hk-speedrunning/Silksong-Rules/blob/main/nmg_rules.md
- Steam 安全优先的成就路线指南：https://steamcommunity.com/sharedfiles/filedetails/?id=3581413736
- Steam any% 指南：https://steamcommunity.com/sharedfiles/filedetails/?id=3569566036
- 中文结局 1 双成就实例：https://www.sina.cn/news/detail/5226083123202836.html

**先行工作**
- hollow_knight_bot：https://github.com/hnguyentran03/hollow_knight_bot
- OC-STORM（像素 RL）：https://oc-storm.weipuzhang.com/ ，https://arxiv.org/abs/2501.16443
- seermer HK RL：https://raw.githubusercontent.com/seermer/HollowKnight_RL/hornet_new/README.md
- celeste-rl：https://github.com/shihaab453/celeste-rl
- Mario AI（前向模型规划）：http://julian.togelius.com/Togelius2010The.pdf
- DXcam / BetterCam：https://github.com/ra1nty/DXcam/blob/main/README.md ，https://github.com/ZCban/BetterCam
- ViGEmBus（已停止维护）：https://github.com/nefarius/ViGEmBus