# 1.0.30000 运行时探针记录（M0）

实测环境：Windows 11，RTX 4060 Ti，LG TV 桌面 3840×2160@60 Hz；训练副本 `C:\ssbot\game\train`（BepInEx 5.4.23.4 + SsOracle 0.0.1，`steam_api64.dll` 已改名）。状态数据来自 SsOracle 的 1 Hz 探针（`C:\ssbot\sandbox\oracle_probe.jsonl`），按键由 `brain/ssbot/io/sinks/sendinput.py` 经 SendInput 发出。

## P1 构建与版本 — 通过（2026-09-29）

| 项目 | 结果 |
|---|---|
| Steam 库副本 | buildid 22479045，depot 1030301 manifest `4421626056705534276` = 1.0.30000 |
| 副本一致性 | library / final / train 三份 2268 个文件逐一 sha256 相同（见 `versions.lock`） |
| Unity | `6000.0.50f1-uum-100966-branch1`（`Player.log`；BepInEx 报 6000.0.50.1503346） |
| 运行时版本 | `Constants.GAME_VERSION = "1.0.30000"`；标题画面右下角也显示 1.0.30000 |

偏离设计：没有用 `download_depot`，而是直接复制了当时 buildid 已确认的库副本。库副本的"自动更新"仍为默认，它更新不会影响两份固定副本。

## P9 无 Steam 运行 — 通过

- 改名 `steam_api64.dll` 后游戏正常启动，`Player.log` 记为 `No online subsystems packaged.`，不会经 Steam 重启。
- 存档目录：`DesktopPlatform.Awake` 在没有在线子系统时使用 `persistentDataPath\default\`，与真实的 `<SteamID>\` 目录分开。实测"保存并退出"只写了 `default\user1.dat`、`default\shared.dat`，真实目录未被写入。
- **设置污染（新发现）：** Unity 退出时会把启动参数 `-screen-width/-screen-height/-screen-fullscreen` 写回 `HKCU\Software\Team Cherry\Hollow Knight Silksong`，所有副本共用，会改掉你自己玩时的分辨率。处理：`scripts/launch_train.ps1` 启动前导出该键，退出后删除并导入快照。实测还原后与原值 0 处差异。

## P5 原版最终副本的成就 — 通过（2026-09-29）

- 环境：`C:\ssbot\game\final`（原版文件 + `steam_appid.txt`=1030300，没有加载器），Steam 客户端在线。`Player.log`：`Steam initializing` → `Steam logged in as …` → `Selected online subsystem SteamOnlineSubsystem` → `Steam stats received.`。
- 准备：原存档（骸底镇，0 念珠）在训练副本沙盒里读档，用 SsOracle `pdset geo 1000` 加念珠后保存退出；再把这个 `user2.dat` 放进真实目录 `<AccountID>\` 的 2 号槽。
- 操作（SendInput，每一步截图）：读 2 号槽 → 按住 → 4.5 s 走到佩珀（Pebb）旁 → 上（交谈）→ Z 翻对话（首次见面要 4 次）→ 商店第一项"磁石胸针"120 → Z → 确认框（**默认"是"**）→ Z → "获得工具"提示 → Z 关闭。
- 结果：关闭提示后 `Player.log` 出现 `Pushing achievement FIRST_TOOL` 和 `Steam achievement FIRST_TOOL (0/0) upload complete`。**原版固定副本 + `steam_appid.txt` 可以正常解锁 Steam 成就。** 成就在提示关闭时发放（商店购买走排队发放，不是购买那一刻）。本地 `shared.dat` 同时写入 `FIRST_TOOL=1`（m0:N26）。
- 钢铁之魂解锁码：主菜单 → 额外内容 → 上下上下左右左右（每键按 80 ms、间隔 150 ms）。页面没有任何反馈；解码 `<AccountID>\shared.dat` 得到 `RecPermadeathMode=1`。
- 收尾：2 号槽的三个文件已移到 `C:\ssbot\backups\p5_slot2_*`，真实目录只剩用户自己的 1 号槽（未改动）。
- 教训（都已在设计中有对应条目，这里是实测）：
  - 在商店里按 Esc 不会暂停；盲按的"下、下、回车"只移动了商店光标。每次 Submit 前必须读屏幕状态。
  - 在主菜单打开后才放进去的存档不会被存档选择界面看到。选中该槽时，游戏把它当空槽，静默开始了一局**普通模式新游戏**（m0:N30 的实例）。当时立即结束了进程，存档文件未被覆盖。MenuDriver 必须在每次进入存档选择界面时读槽位内容再操作。
  - 从商店退出后立刻按 Esc，按键会被丢弃（关闭动画期间不可暂停，m0:N12）。

## P15 钢铁之魂死亡前后强制结束进程 — 死后杀进程无效（2026-09-29）

- 准备（`brain/ssbot/probes/p15_setup.py`）：训练副本 → 额外内容输入解锁码（沙盒 `shared.dat` 得到 `RecPermadeathMode=1`）→ 空的 3 号槽 → 出现模式菜单 → 钢铁之魂 → 开场约 100 s（注入的按键跳不过，m0:N36）→ Tut_01。开场教学要求按 A 缚丝：1 格血回到 4 格。等待期间 `disablePause=True`，但 **PlayTime 照常计时**（约 35 s）。随后保存退出，存为模板：`permadeathMode=1`、PlayTime 49.97 s、4/5 格血、HUD 为钢铁皮肤。
- 实验（`brain/ssbot/probes/p15_kill.py`）：每次从模板恢复 3 号槽，读档后用 `hurt 99 ENEMY` 造成致命伤。

  | 实验 | 结果 |
  |---|---|
  | 不杀进程 | 致命伤后约 **142 ms**，`user3.dat` 已写成 `permadeathMode=2`（Dead） |
  | 死后立即 `taskkill /F`（实际在 +103 ms 生效） | Dead |
  | +220 / +422 / +1123 ms | 全部 Dead |

  每次都留下 `user3.dat.bak1`，内容是死前的存活状态（m0:C13）。
- 结论：死后再杀进程救不回来（m0:N7）。最终运行时视觉确认死亡本身就需要约 46 ms（P8），加上杀进程的时间，必然晚于约 140 ms 的写盘。D13 只可能是"预测式"的，而那样与紧急暂停退出没有实质区别，**D13 保持关闭**。死亡后存活状态只在 `.bak*` 和 Restore_Points 里，是否用它们恢复属于 D3 的决定。

## P14 成就界面能否证明 Steam 在线 — 不能（2026-09-29）

- 训练副本（没有 Steam 子系统）的沙盒 `shared.dat` 里只有本地记录 `FIRST_TOOL=1`。主菜单 → 成就界面把"利器傍身 / 获得首个工具"显示为已解锁，其余为灰色。
- 结论：成就界面按 `IsAchievementUnlocked` 显示，Steam 不在时退回本地 `shared.dat`（m0:N26/N35）。它在"Steam 在线"和"只有本地记录"两种情况下看起来一样，不能作为 Steam 收到成就的证据。预检和结局核对只以 `Player.log` 为准：`Steam logged in as`、`Steam stats received.`，以及每个成就的 `upload complete`。
- 附带：训练副本的菜单左上角有 Modlist 画出的版本和模组列表（`v1.0.30000-0.3.1 / DebugMod / SsOracle`），最终副本没有。采集菜单画面做训练数据时要遮掉这块区域。

## 存档重定向（P9 ②）— 通过

- `oracle/src/Guards/SaveRedirect.cs`：Harmony 转译补丁把 `DesktopPlatform.Awake` 里唯一一次 `Application.persistentDataPath` 调用换成 `C:\ssbot\sandbox\saves\<实例号>`（`-ssbot-instance N`，默认 0）。于是 user*.dat、`.bak*`、Restore_Points、shared.dat 都进入沙盒。
- 实测：训练副本从沙盒读到 1 号槽；真实的 `persistentDataPath\default` 已删除且保持不存在。以后这个目录一旦出现，就说明最终副本的 Steam 初始化失败了（m0:N28），应当报警。
- 备份编号实测为 `.bak1`、`.bak2` 递增（m0:C13）。
- 未重定向：DebugMod 把自己的设置和存档点放在真实的 `LocalLow\...\DebugModData\`，不含游戏存档。默认打开的 DebugMod 界面会遮住大半画面，采集视觉数据前要在它的 `Settings.json` 里关掉。

## 存档离线解码

`brain/ssbot/tools/savefile.py`（只读）：BinaryFormatter 字符串 → Base64 → AES-256-ECB-PKCS7 → JSON（m0:N33）。已验证 user*.dat（`playerData` 1311 个字段加 `sceneData`）和 shared.dat（`pairs` 列表）。

## P4 SendInput — 通过（前台）

- 游戏在前台时，扫描码 SendInput 能驱动菜单（回车确认）和游戏：按住"右"1.5 s，Hornet 从 x=238.78 移到 249.84。
- 键位与默认键盘绑定一致：Z 跳、X 攻击、C 冲刺、A 缚丝、S 飞针、D 织针曲、F 快速施放、V 嘲讽、I 背包、Tab 快速地图、M/Q/J/T 背包分页、方向键、Esc 暂停。
- 与 Harmony 注入的轨迹对比尚未做（等 M1 的注入模块）。

## P3 游戏内按键注入 — 通过（不需要前台）

- 实现：`oracle/src/Input/KeyboardInjector.cs`。每次动态输入更新（`InputSystem.onBeforeUpdate`，`currentUpdateType == Dynamic`）在主线程锁存一次按键集合，向 `Keyboard.current` 排队一个完整的 `KeyboardState` 事件。游戏走的读取路径与真实按键相同：Input System → InControl `KeyBindingSource` → `HeroActions`。Python 端通过 `127.0.0.1:47631` 的行协议发送按键集合（`brain/ssbot/io/sinks/oracle_inject.py`）。
- 训练副本需要 `InputSystem.settings.backgroundBehavior = IgnoreFocus`。默认策略会在失焦时禁用键盘，注入的事件会被丢掉。
- 实测（`brain/ssbot/probes/p3_inject.py`，全程 `focused=false`）：
  - 主菜单 → 存档选择 → 读取 1 号槽 → PLAYING。
  - 暂停：PAUSED，2 s 内 PlayTime 不变。
  - 在"继续"上回车取消暂停。
  - 向左走 8.1 u，跳跃高度 5.24 u。
- 坑 1：GameState 变为 MAIN_MENU 后，菜单还在入场动画中，这时按键会被忽略。脚本改为等 `ui.menuState` 到目标界面且 `IsFadingMenu == false`，再多等 0.3 s。
- 坑 2：读档后 Hornet 先播放坐上椅子的动画，期间方向键无效（本次"向右"被吞）。后续按英雄是否接受输入来判断，不能只看时间。
- 尚未覆盖：legacy `Input.anyKeyDown` 的调用方（过场跳过、Bellway 跳过、`IdleMemoryCleaner`），留到 M1 加垫片。

## 序列化的输入设置（P11 部分）

| 设置 | 1.0.30000 实际值 | 含义 |
|---|---|---|
| `Application.runInBackground` | **True**（原版） | 原版失焦后继续模拟，**PlayTime 继续计时** |
| `InControl.InputManager.SuspendInBackground` | False | InControl 失焦后照常更新 |
| `InputSystem.settings.updateMode` | ProcessEventsInDynamicUpdate | 每渲染帧采样一次按键；比一帧短的点按会丢 |
| `InputSystem.settings.backgroundBehavior` | 默认 ResetAndDisableNonBackgroundDevices | 原版失焦时键盘被断开：Hornet 失去控制，但世界和计时器都在走 |

对正式运行的影响：焦点一旦被抢走，Hornet 会站着挨打，计时器也继续走。设计中的焦点守护（每毫秒检查前台窗口、失焦后立即切回并按暂停）是必需的。

## P6 计时器（部分）

| 情形 | 结果 |
|---|---|
| PLAYING | `GameManager.PlayTime` 按真实时间每秒 +1 |
| 暂停菜单 | GameState=PAUSED，timeScale=0，PlayTime 3 s 内不变 |
| 取消暂停 | 立即恢复计时 |
| 保存并退出 | 确认的那一刻把会话时间写入 `playerData.playTime`（447.464 → 470.497，正好等于暂停时的 PlayTime）；之后约 3 s 保持 PAUSED、timeScale=0，然后进入 MAIN_MENU |
| 失焦 | 原版序列化设置 `runInBackground=True`，失焦后继续模拟、继续计时（见上表）。训练副本同样以 60 fps 运行 |

| 背包（I） | `isInventoryOpen=true`，PlayTime/墙钟 = **0.000**，关闭后恢复 |
| 快速地图（按住 Tab） | PlayTime/墙钟 = **0.998**，照常计时（该存档可能尚无地图，界面内容未核对） |
| 房间切换（骸底镇 → Tut_01） | 墙钟 8.51 s，PlayTime 8.52 s：切换全程计时 |

仍未测：Bellway 乘车、片尾。脚本：`brain/ssbot/probes/p6_p11.py`，逐帧轨迹写入 `C:\ssbot\sandbox\p6_trace.csv`。

## P11 序列化常量 — 通过（HeroController 预制体值）

完整导出：[`hero_constants.json`](hero_constants.json)，由 SsOracle 的 `constants` 命令生成，内容为 HeroController 上所有基本类型字段加引擎设置。

| 常量 | 实际值 | 设计原估计 |
|---|---|---|
| `Time.fixedDeltaTime` | 0.02（50 Hz 物理） | 0.02 ✓ |
| `INVUL_TIME` | 1.0 s | 约 1.0 s ✓ |
| `INVUL_TIME_PARRY` | **0.15 s** | 0.25 s ✗ |
| `INVUL_TIME_CROSS_STITCH` / `SILKDASH` / `QUAKE` | 0.35 / 0.5 / 0.4 s | — |
| `DOWNSPIKE_INVULNERABILITY_STEPS` / `_LONG` | **8 / 16 步**（0.16 / 0.32 s） | 2 / 10 步 ✗ |
| `DASH_TIME` / `DASH_COOLDOWN` / `DASH_SPEED` | 0.1 s / 0.425 s / 28 | — |
| `RUN_SPEED` / `WALK_SPEED` | 8.25 / 5 | — |
| `JUMP_SPEED` / `JUMP_STEPS` / `JUMP_STEPS_MIN` | 18.6 / 8 / 2 | — |
| 预输入窗口（物理步） | 跳 2、二段跳 10、攻击 8、冲刺 **10**、工具 5、飞针 8 | 冲刺原为"未知" |
| `DAMAGE_FREEZE_DOWN/WAIT/UP` | 0 / 0.1 / 0.1 | 设计表格 HeroDamage 0.01/0.28/0.10（来自 FreezeMoment，二者不是同一个东西，待核） |
| `RECOIL_HOR_VELOCITY` / `_LONG` / `RECOIL_DURATION` | 3.75 / 16 / 0.2 s | — |

引擎设置：`vSyncCount=1`、`targetFrameRate=-1`，即**帧率等于显示器刷新率**。电视切到 120 Hz，游戏就会跑 120 帧。设计要求固定 60 fps，所以：要么保持 60 Hz，要么在游戏选项里找到帧率上限（P8/P12 核实）。InControl `updateMode=Default`（每渲染帧更新一次），`defaultButtonPressPoint=0.5`。

注意：这些是读档后、坐椅子状态下的实例值，纹章、工具、状态效果可能在运行时改动其中一部分。M1 起按事件逐帧导出。

## P7 暂停与退出（部分）

- 紧急退出的完整按键序列：Esc → 移到"退出至菜单" → 回车 → 确认框"保存并退出？"（**默认选中"否"**）→ 上 → 回车。暂停一旦生效，世界就冻结，后面几步只花墙钟时间，不花游戏时间。
- 退出过程中（确认后到主菜单）一直是 PAUSED、timeScale=0，淡出期间世界不动。
- **鼠标悬停会改变菜单选中项。** 第一次暂停时光标落在"退出至菜单"，是因为鼠标正停在那个位置；第二次（鼠标不在菜单上）落在"继续"。结论：正式运行必须拔掉鼠标或把光标停在游戏窗口外；菜单操作前必须先读出光标位置。
- 受伤后的暂停窗口（2026-09-29，`brain/ssbot/probes/p7_pause.py`；伤害经 SsOracle `hurt` 走真实的 `HeroController.TakeDamage`；门控由 `trace` 逐帧录制）：

  | 受伤 | 逐帧门控（从命中那一帧起算） | 不可暂停 |
  |---|---|---|
  | ENEMY 1 格 | f+0：timeScale 0、timeSlowed、disablePause、invuln 同时置位 → +150 ms 起 timeScale 按 0.167/帧爬升 → +234 ms 到 1.0 → **+250 ms（f+15）disablePause 与 timeSlowed 清除** → +1200 ms invuln 结束 | **约 250 ms** |
  | SPIKES 1 格 | f+0 disablePause（DieFromHazard）→ f+2 冻结 → +250 ms 恢复 → 淡出与危险物重生 → +900 ms 重生后 invuln → **+2300 ms（f+137）disablePause 清除** → +3216 ms invuln 结束 | **约 2.3 s** |

- 敌人命中后第 d ms 按一次 Esc：d = 30/100/200 ms 均**未暂停**（按键被丢弃，不排队）；d = 300/400/500/700/1000 ms 均暂停。与门控追踪一致（m0:N8、N12、N9）。
- 结论：挨一下敌人的攻击后有约 0.25 s 无法暂停，挨一下环境伤害后约 2.3 s 无法暂停。紧急退出必须在命中之前触发；环境伤害按"致命区"处理。
- 未测：`disableSaveQuit` 的来源、灰色退出按钮、BOSS 死亡和竞技场收尾的长冻结（m0:N13）。

## P8 捕获与回环延迟（60 Hz，部分）

环境：LG TV 桌面 4K@60 Hz；训练副本 1920×1080 窗口模式（`launch_train.ps1 -Width 1920 -Height 1080`）。捕获用 Windows Graphics Capture（`windows-capture` 2.0.1，窗口级捕获，不画边框、不含鼠标）。脚本：`brain/ssbot/probes/p8_latency.py`。

| 测量 | 结果 |
|---|---|
| 帧率（游戏在后台，10 s） | 58.9 fps；帧间隔 p50 16.67 ms，但 581 帧中有 12 个 33 ms 间隔（约 2 %，超过设计的 0.1 % 门槛）。待对比前台情况 |
| `Frame.timespan` | 比回调到达时刻**晚**约 7–10 ms，不能当作"帧产生时刻"（像是下一次刷新的目标时间）。延迟一律以回调到达的 `perf_counter` 计 |
| SendInput Esc → 第一帧画面开始变暗（回调时刻），10 次 | **p50 45.6 ms，p90 46.3 ms，最大 49.6 ms** |
| SendInput Esc → 画面变暗 30 %（含暂停菜单淡入），30 次 | p50 约 95 ms，p90 112–120 ms |

- 45.6 ms 包含：输入采样（≤1 帧）、暂停协程自身的帧数、渲染、DWM 合成、WGC 捕获、Python 回调。所以纯捕获管线更短。M1 的延迟工具会改用即时反应的刺激（如开始奔跑）再测。
- 与设计预算对比（§3.8.4，60 Hz 显示器）：设计估计 p50 约 30 ms，p99 目标 ≤ 60 ms（含约 8–10 ms 计算）。实测"按键 → 看到反应"约 46 ms，加上计算后接近 60 ms 上限。120 Hz 显示能省去部分等待，但游戏开着 vSync 且不设帧率上限，会跟着跑 120 fps（见 P11），与"固定 60 fps"冲突，需先找到游戏内帧率上限选项。
- 结论：遮挡不影响捕获（WGC 抓窗口自身内容）；最小化会停止出帧。
- 帧率设置（代码：`MenuSetting` VSync 分支、`MenuFrameCapSetting`）：游戏的"垂直同步"和"帧率上限"互斥。开垂直同步时 `targetFrameRate=-1`，帧率等于刷新率；设帧率上限时垂直同步被关掉。原版只能设置 `vSyncCount` 0/1，没有"每两次刷新一帧"。
  - **已定（2026-09-29）：** 显示器（LG TV）最高 60 Hz，固定为 60 Hz + 游戏内垂直同步开 = 60 fps。这就是上表所有测量用的配置。

**事故记录：** 第一次回环测试时，脚本没能取得前台（Windows 前台锁：用户当时正在操作），却没有检查就发了按键，一个 Esc 落到了用户的窗口。修复：`game_window.focus()` 改用 `AttachThreadInput`，并在确认前台后才返回 True；所有发按键的脚本在每次发送前都检查前台，失败即中止，不发送任何键。

## 训练副本的桌面行为（新增）

- 原版在前台时会隐藏并锁定鼠标（`InputHandler.SetCursorEnabled`、PlayMaker 动作 `SetMouseCursor`、`LanguageSelector`），用户无法操作其他窗口。
- SsOracle 的 `TrainingEnvironment`：跳过 `SetCursorEnabled`，每帧强制显示和释放鼠标、保持 `runInBackground`，并在 Input System 中禁用鼠标设备（悬停不再影响菜单）。实测失焦后照常运行。
- 训练阶段应改用游戏内注入输入（无需前台）。外部 SendInput 只用于最终路径的测试，测试时必须先告知用户，且操作完立即把前台还回去（`drive.py` 已实现，并会把鼠标移到游戏窗口外）。

## M1 集成测试（2026-09-30，训练副本 1280×720 窗口，沙盒存档 1）

| 探针 | 结果 | 要点 |
|---|---|---|
| m1_hero | 39 过 / 2 警告 / 0 失败 | 移动速度 8.25 u/s；hero 15 µs、cam 4 µs、hud 23 µs（p50）；叠加图目测对齐 |
| m1_entities | 通过（敌人/伤害碰撞体已见；视野内 FSM 没换状态时事件检查跳过） | ents p50 14 µs；Bone Goomba 在 Hiding 状态不产生事件 |
| m1_events | 30/30 | 尖刺→危险物重生 84 帧（1.4 s）；TERRAIN 每帧工作量 ≤ 441 µs |
| m1_guards | 35 过 / 1 跳过（未装碎面具） | 10 种致死路径全部拦截；SaveSuppression 仍把计时写入 playTime |
| m1_harness | 全过 | 存档状态重置 p50 317 ms、最大 345 ms；270 帧流式点按零丢失；掉线看门狗松键 + 暂停 |
| m1_record | 交付率 100 %（3606/3606） | STATE 约 3 KB/帧，zstd 46 倍，0.35 MB/分钟 |
| m1_record 60 分钟（M1 验收） | **交付率 100 %（216007/216007），0 丢帧** | 60.00 fps；构建 p50 81 µs、p99 123 µs、最大 417 µs；EOF→大脑 p50 0.15 ms、最大 0.60 ms；20.3 MB/小时。Hornet 在 Bonetown 静止，敌人与 FSM 负载低 |

集成中发现并修正的事实：
- **HUD 面具**：`health_display` 对象自身的 MeshRenderer 是禁用的，画面上的面具是子对象 `Idle`（护符状态下是 `Idle Bound` / `Idle Hive`）。超出血量上限的面具对象仍是激活的，FSM 状态为 `Inactive`，不绘制。
- **窗口截图**：WGC 抓的是含标题栏的可见窗口（1280×720 客户区在 1282×752 截图中的 (1, 31)）。oracle 的像素坐标都是客户区坐标，比较前先裁剪（`game_window.client_in_capture`）。
- **时钟**：Unity Mono 的 `Stopwatch.GetTimestamp()` 在 Windows 上从进程内第一次调用开始计（`mono_100ns_ticks` 减去起始值），不能与大脑的 QueryPerformanceCounter 比较（差了约 5 小时）。STATE / 事件的 `q` 与 HELLO 的 `qpc_freq` 现在用原始 QPC（`Core.Qpc`），EOF→大脑 延迟 p50 0.09 ms、p99 0.23 ms。**此前录的人类会话（20260930_005501）的 `q` 是旧时钟，对齐视频时要另找偏移。**
- **危险物重生**：TakeDamage 在 HazardRespawn 开始后 0.5 s 内会把环境伤害变成又一次重生（不扣血）；危险物死亡期间 `CanTakeDamage()` 为假，伤害被直接丢弃。测试伤害前要等重生结束。
- **掉线看门狗**：只有"持续控制（hold 0）且有键按下"的 ACTION 才进入驱动状态；一次性点按和纯释放都不会，否则探针结束后会被自动按暂停。
- 进程第一次构建 STATE 约 141 ms（JIT），只在启动时的标题画面出现一次。

## M1 soak 准备中发现的问题（2026-09-30）

- **多实例同时启动的竞争**：两个实例同时启动时，BepInEx 预加载器都在类型初始化里写 `BepInEx\config\BepInEx.cfg`（`ConfigFile.Save`），输的一方出现文件共享冲突，预加载器崩溃（游戏根目录 `preloader_*.log`），该实例**以原版运行**：没有 oracle，也没有存档重定向。启动器现在逐个启动，每个等上一个的 oracle 开始监听。
- **AppConfig.ini**：游戏的 `ConfigManager.LoadConfig` 每次启动都读一次 `persistentDataPath\AppConfig.ini` 并原样写回（`[Accessibility] ReducedCameraShake/ReducedControllerRumble`）。它不经过 `DesktopPlatform`，所以存档重定向拦不住：M0 以来每次启动训练副本都改写了真实 `LocalLow\Team Cherry\Hollow Knight Silksong\AppConfig.ini`（内容不变）。SaveRedirect 现在把 `LoadConfig/SaveConfig` 里对 `_path` 的读取换成 `<沙盒>\AppConfig.ini`，已在游戏内验证真实文件不再被触碰。
- **DebugMod 数据目录**：DebugMod 把 `Settings.json`、`Savestates 1.0`、`Savestate Packs` 放在 `persistentDataPath\DebugModData`（真实 LocalLow）。它在 SsOracle 之前加载，Awake 里的 `CreateDirectory` 在首次启动时（9-29 21:59）已在真实目录建了空文件夹。SaveRedirect 现在把 DebugMod 里所有读取这三个路径字段的方法（13 个）转到 `<沙盒>\DebugModData`；savestate 读取照常（p50 327 ms）。
- **一个原版运行的实例就足以写真实目录**：冒烟测试中预加载器失败的那个实例在标题画面就改写了 `AppConfig.ini`。训练副本没有"模组没加载就拒绝运行"的保护；目前靠启动器等端口就绪（超时则杀掉）兜底。
- **WHEA**：System 日志里 10 条硬件纠错（ID 2/19）全部在 9-02（BIOS 1836 之前）；9-29 20:46–21:13 的 3 条是 ID 3 信息级（重启时记录）。soak 只看运行期间新出现的 1–3 级事件。
