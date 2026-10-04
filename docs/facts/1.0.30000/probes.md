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
| 负重环带下的受击无敌（`INVUL_TIME` × `weightedAnkletDmgInvulnMult`，资产值 1.3，代码初值 1.2 被覆盖） | **1.30 s**：你装着负重环带的半速练习 `20261004_133855` 里 88 次受击，扣血那帧到 `invulnerable` 清除的游戏时间（逐帧 udt × timeScale 求和）p10 / p50 / p90 = 1.304 / 1.304 / 1.308 s（实时约 2.8 s）；`HeroParams.with_weighted()` 的 1.3 在录像上第一次核对（脚本 `scratchpad/iframes.py`，2026-10-04） | — |
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
- **时钟**：Unity Mono 的 `Stopwatch.GetTimestamp()` 在 Windows 上从进程内第一次调用开始计（`mono_100ns_ticks` 减去起始值），不能与大脑的 QueryPerformanceCounter 比较（差了约 5 小时）。STATE / 事件的 `q` 与 HELLO 的 `qpc_freq` 现在用原始 QPC（`Core.Qpc`），EOF→大脑 延迟 p50 0.09 ms、p99 0.23 ms。**此前录的人类会话（20260930_005501）的 `q` 是旧时钟，对齐视频时要另找偏移。** 已离线找到（`record/align_legacy.py`，只读）：视频帧 i 显示满足 `q_ns + 偏移 ≤ pts_ns[i]` 的最新 STATE 帧，偏移 **−1939.9 ms**（`q_ns = q × 100`，pts 为 video.mkv 的容器时间戳）。依据：13 段游戏中定格（dt = 0）共 76 对"应静止"的视频帧全部静止、0 误判，相邻帧相位得分明显更低（128.8 对 86.6），帧级映射唯一；相位带 −1942.3 至 −1937.5 ms。实测规律：定格内部的帧与上一帧逐像素相同，定格后第一帧必变，但定格的**第一帧**仍会变（受击效果在上一帧渲染之后才生效）。
- **危险物重生**：TakeDamage 在 HazardRespawn 开始后 0.5 s 内会把环境伤害变成又一次重生（不扣血）；危险物死亡期间 `CanTakeDamage()` 为假，伤害被直接丢弃。测试伤害前要等重生结束。
- **掉线看门狗**：只有"持续控制（hold 0）且有键按下"的 ACTION 才进入驱动状态；一次性点按和纯释放都不会，否则探针结束后会被自动按暂停。
- 进程第一次构建 STATE 约 141 ms（JIT），只在启动时的标题画面出现一次。

## M1 soak 准备中发现的问题（2026-09-30）

- **多实例同时启动的竞争**：两个实例同时启动时，BepInEx 预加载器都在类型初始化里写 `BepInEx\config\BepInEx.cfg`（`ConfigFile.Save`），输的一方出现文件共享冲突，预加载器崩溃（游戏根目录 `preloader_*.log`），该实例**以原版运行**：没有 oracle，也没有存档重定向。启动器现在逐个启动，每个等上一个的 oracle 开始监听。
- **AppConfig.ini**：游戏的 `ConfigManager.LoadConfig` 每次启动都读一次 `persistentDataPath\AppConfig.ini` 并原样写回（`[Accessibility] ReducedCameraShake/ReducedControllerRumble`）。它不经过 `DesktopPlatform`，所以存档重定向拦不住：M0 以来每次启动训练副本都改写了真实 `LocalLow\Team Cherry\Hollow Knight Silksong\AppConfig.ini`（内容不变）。SaveRedirect 现在把 `LoadConfig/SaveConfig` 里对 `_path` 的读取换成 `<沙盒>\AppConfig.ini`，已在游戏内验证真实文件不再被触碰。
- **DebugMod 数据目录**：DebugMod 把 `Settings.json`、`Savestates 1.0`、`Savestate Packs` 放在 `persistentDataPath\DebugModData`（真实 LocalLow）。它在 SsOracle 之前加载，Awake 里的 `CreateDirectory` 在首次启动时（9-29 21:59）已在真实目录建了空文件夹。SaveRedirect 现在把 DebugMod 里所有读取这三个路径字段的方法（13 个）转到 `<沙盒>\DebugModData`；savestate 读取照常（p50 327 ms）。
- **一个原版运行的实例就足以写真实目录**：冒烟测试中预加载器失败的那个实例在标题画面就改写了 `AppConfig.ini`。训练副本没有"模组没加载就拒绝运行"的保护；目前靠启动器等端口就绪（超时则杀掉）兜底。
- **WHEA**：System 日志里 10 条硬件纠错（ID 2/19）全部在 9-02（BIOS 1836 之前）；9-29 20:46–21:13 的 3 条是 ID 3 信息级（重启时记录）。soak 只看运行期间新出现的 1–3 级事件。

## M1 12 小时 4 实例 soak（2026-09-30 07:15–19:19，soak_071544）

判定 **FAIL（两项，原因已查清）**；其余 15 项 PASS。8801 个回合，4 个实例全程无崩溃、无卡死、无重启，0 次掉线暂停，0 次读档失败。
- **录制交付**：48 个分段全部 100 %。
- **重置**：p50 393 ms、p99 1081 ms；同场景最大 2930 ms（**FAIL：唯一一次超过 2 s**），跨场景最大 1618 ms。
- **帧时间**：稳态游戏平均 16.8 ms；超过 25 ms 的卡顿帧每小时约 1000 个（约 0.1 %）。
- **内存**：私有内存每实例约 +34 MB/h（线性，未趋平；门槛 100 MB/h 内），句柄约 +6/h；见 `probes/mem_growth.py` 待查。
- **WHEA**：运行期间 0 条硬件错误。PlayerPrefs 运行中只变了 Unity 的 Screenmanager 键，结束后恢复 golden。
- **沙盒外写入**：真实 LocalLow/Team Cherry、MSIX LocalCache、原版副本、Steam 云存档快照全部零变化；训练副本只有 BepInEx 日志。"需复核"15,640 条（**FAIL**）：报告里列出的都是 pytest 的 `tmp_path`（测试在 Temp 里建的假游戏目录），但报告当时只保存了按名排序的前 200 条，其余无法逐条核实。已修：pytest 临时目录归为"mine"，并保存所有违规/复核路径的按目录汇总。

**并发负载的影响（重要）**：第 5–6 小时（12:15–14:15）卡顿帧升到平时的 4–8 倍（4218、8247 个/小时），超过 1 s 的重置从约 5 次/小时升到 21–30 次，那次 2.93 s 的重置也在其中（13:12）；第 7 小时起回到基线。这段时间我在同一台机器上并行跑多代理开发，其中对齐的合成测试用 numpy/BLAS 占满全部线程。游戏进程平均 CPU 占用和 GPU 占用都没变，说明不是缺算力，而是调度延迟。训练时 bot 的推理与数据处理也在本机，所以这是 P12 的实际证据：训练需要 CPU 隔离（游戏固定在 P 核、brain 在 E 核或限线程、游戏进程更高优先级），并在 soak 中加"负载下"一项。

结论：基础设施稳定性达标；重置门槛只在外部负载下失守。合并后的新插件（P17、帧标记、mem.stats 等）还需要一次无并发负载的 soak。

## M1 合并后的游戏内验证（2026-09-30 晚，插件含 P17 / 帧标记 / mem.stats）

- **回归**：m1_hero 46 过 0 败（新增 `hunter_meter`）；STATE 构建 p50 131–146 µs、p99 229–278 µs（新增字段后，仍在 C14 预算内）。
- **P17 纹章实测**（`docs/facts/1.0.30000/crests.json`）：Hunter / Hunter_v2 / Hunter_v3 共用 'Default' 配置（规则 no_config → configs[0]），挥刀 0.41 s、持续 0.35、收招 0.15、DownSpike，攻击对象与范围完全相同：**猎人升级不改动作，只加连击伤害**。Wanderer：0.30 / 0.25 / 0.10，下劈 Slash（带 HeroDownAttack，收招 0.09 s）；向前距离与 Hunter 相同（3.12 对 3.17 u），向上 0.69 对 1.23、向下 1.08 对 1.43、身后 −0.19 对 0.42；上劈小得多；蓄力斩 ×0.55 分 6 段、产丝 FirstHit。Reaper：0.50 / 0.35 / 0.30，向前 3.6、向上 2.2，蓄力斩 ×2.5。弹刀距离 Hunter 2.81、Wanderer 2.92、Reaper 3.64。所有普通挥刀 canHitSpikes 与 parry 均为真。恢复校验 PASS（纹章、PreviousCrestID、temp、丝、解锁集、各纹章槽位、工具数量）。
- **投影精度**：顶点误差 p99 0.0004 px（projector.py 与 Unity WorldToScreenPoint 一致）；IoU p5 0.984（PASS）。局限：Bonetown 地形是 EdgeCollider（线段，无面积），只比到 Hornet 自己的碰撞盒（15 帧）；需在有多边形地形和敌人的房间再测。
- **对齐（帧标记真值）**：3279 帧截图全部解码。按时间戳标签，只有 **95.8 %** 显示标签帧，137 帧（4.2 %）显示的是前一帧（FAIL，门槛 99.5 %）。真实滞后（截图时刻 − 所示帧帧末）k=0 时 44.7–48.1 ms，k=−1 时 61–65 ms（多一个刷新周期）；WGC 截到 3279 帧/3648 个游戏帧（54 fps，无重复，351 帧从未被截到）。迟一帧的截图多数紧跟在一次漏截之后（98/137），但漏截之后的截图有 254 张并不迟，另有 39 张迟一帧的不在漏截之后：**仅凭截图时间戳无法给 4 % 的帧打对标签**，这是 WGC 的不确定性。监视器在这段真实录像上没有误判为对齐（false aligned 0），但因视差大多数帧为 mixed（预期之内）。
- **内存泄漏定位**：每次 DebugMod 读档泄漏 2 个材质实例（"Sprites-Default (Instance)"、"Cherry-Sprites-Default (Instance)"，Renderer.material 产生），约 +21 MB 私有内存 / 100 次连续读档；`Resources.UnloadUnusedAssets` 全部回收（游戏自己换场景时会调用，DebugMod 读档路径不调用）。已修：读档每 25 次顺带卸载一次（在重置内）。修后材质与对象数恒定；私有内存仍约 +12 MB / 100 次连续读档，约一半是强制 GC 后仍存活的托管内存（来源未定位；对原版运行无影响，训练用定期重启实例应对）。

## 训练时常开帧标记 + 共享遮挡（2026-09-30 夜，用户决定）

- 决定：训练截图与人类试玩都画帧号标记（右上角，单元格 max(3, round(h/270)) px），截图路径在全分辨率下解码后立即用共享遮挡（`ssbot/vision/mask.py`，归一化 26/640 × 11/360，720p 下 52×22 px、1080p 下 78×33 px，约 0.12 %）填掉再存；正式运行的视觉输入第一步也填同一块，训练与正式运行看到的像素一致。标记在遮挡外时同样填掉并标 mask_mismatch（不作训练数据）。人类试玩：ffmpeg 主视频先填遮挡再编码，角落单独无损存 corner.mkv 用于解码。
- 游戏内验证（m1_align，1280×720，60 s）：3589 张截图全部在截图路径解出标记，**标签 100 % 精确，门槛 PASS**；遮挡生效，mask_mismatch 0，training_safe True。同一录像里只用时间戳标签也有 99.94 %（截图器只漏 41 帧；上一次漏 351 帧时只有 95.8 %：时间戳标签的错帧与截图器漏帧有关，而漏帧随系统负载变化）。监视器 false aligned 0。
- 标记解码 + 遮挡的开销：1080p 每帧约 0.06 ms（截图回调约 0.9 ms）。

## M1 帧时间与投影精度补测（2026-09-30 23:00–23:40）

- **帧时间（PresentMon 2.6，管理员运行，v2 指标）**：同一沙盒存档、长椅旁不动、单实例 1280×720 窗口、垂直同步开。基线 = SsOracle 最小模式（`-ssbot-minimal`：只保留存档重定向，每帧什么都不做）且移走 DebugMod，10 分钟 36001 帧；训练配置 = SsOracle 全功能 + DebugMod + 连着录制器 + 帧标记，9 分钟 32401 帧。帧时间平均 16.667 对 16.666 ms，p99 17.991 对 18.098 ms（**+0.107 ms，门槛 +0.5 ms：PASS**），p99.9 18.448 对 18.644 ms；超过 25 ms 的帧 1 对 0。GPU busy p50 5.9 对 5.6 ms。注：PresentMon v2 的 CPUBusy 在垂直同步下包含主线程等待呈现的时间（约 16.6 ms），不能当作插件开销；插件自己的每帧开销见 STATE cost_us（p50 约 130–150 µs）。工具：`brain/ssbot/probes/frametime_compare.py`（run / analyze）。
- 一次异常：训练阶段第一次运行时，脚本在用 windows-capture 截图那一步无声退出（没有回溯、没有 finally、系统崩溃日志里也没有记录），游戏进程被留下；跳过截图后重跑正常。截图库与录制器在同一进程时可能出现这种原生层面的退出，待查。
- **投影精度（Bone_01，有方块/多边形地形）**：顶点误差 p99 0.00025 px；IoU p5 0.998（36 个多边形帧：Hornet 碰撞盒和一块 NonSliderTerrain 多边形；24 条线段地形跳过；那只 Goomba 在画面上方平台外，没比到敌人）。截图整体偏 1 px（纵向），应是客户区裁剪的取整，不影响结论。PASS。

## M1 最终 12 小时 4 实例 soak（2026-09-30 23:38 – 10-01 11:41，soak_233809，最终插件）

**SOAK PASS，19 项全部通过**，期间本机不跑任何开发或测试。8867 个回合，4 个实例全程无崩溃、无卡死、无重启，0 次掉线暂停，0 次读档失败，0 次误触交互，0 次死亡（LethalBlock 拦截 4 次致命伤）。
- 重置 p50 378 ms、p99 777 ms、最大 1444 ms（同场景 p99 457 ms，跨场景 p99 1160 ms）：全部 ≤ 2 s。
- 录制交付：48 个分段全部 100 %；帧标记在 10,327,056 / 10,331,791 帧中画出（其余为标记打开前的启动帧）。
- 帧时间：稳态平均 16.78 ms；超过 25 ms 的卡顿帧 0.13 %，各小时稳定（上一次 soak 的第 5–6 小时异常确由并发负载造成）。
- 内存：私有内存每实例约 +31–33 MB/h（材质泄漏已修；剩余增长见前文，训练时定期重启实例）。
- 沙盒外写入 0；需复核 0；PlayerPrefs 运行中只变 Screenmanager 键，结束恢复 golden；WHEA 硬件错误 0。

**M1 验收项至此全部有结果**：60 min 录制交付 100 %；STATE 构建 p50 约 80–150 µs、p99 约 130–280 µs（≤ 300 / 1000 µs）；帧时间 p99 +0.107 ms（≤ +0.5 ms）；投影 IoU p5 0.998、顶点 p99 0.0003 px；对齐（帧标记）100 %；4 实例 12 h soak PASS；重置 ≤ 2 s；沙盒外 0 写入；LethalBlock 单元测试全过。未完成：P13 结局探针（需要社区 GMS savestate）。

## M2：社区 savestate 与 cstate 字段表（2026-10-01）

- vichisuki 的 savestate（为 1.0.29315 制作，固定在提交 `0557f703fa25`）在 1.0.30000 训练副本上读档可用：抽查 9 个 boss 页（Bell Beast、Lace 1、Widow、Last Judge、Dancers、Trobbio、High Halls/Forum 前、Lace 2 电梯、GMS），全部落在文件记录的场景和位置，读档 0.4–0.9 s（`ssbot.probes.community_check`）。全程 5 面具、Hunter。
- `docs/facts/1.0.30000/cstate_schema.json`（从反编译源码推出的 HeroControllerStates 字段顺序，92 bool + 4 int）与 oracle RPC `schema.cstate` 完全一致。
- 读档后游戏可能还要把主角滑回 savestate 位置：最多 17 帧、每帧约 0.63 u，期间速度为 0、`hero_accepting_input` 和 `can.cast` 均为真；Bell Beast 首轮数据中 85 个开场里有 4 个在这段时间按丝矛被吞。回合框架改为等主角位置连续 10 帧不变再开始（`ssbot.train.episode.wait_settled`）。
- Bell Beast 行为采集首轮（`20261001_122249`，4 实例 3.5 h，data 策略）：263 场打到苏醒，241 CLEAR、22 超时（240 s），开场失败 17 场（旧代码）；每场约 175 s；四类攻击各 ≥ 200 次（狂暴 263）。

## M2：Bell Beast 门槛（oracle，2026-10-02）

- **通过**：代码固定在 0c053d9（独立工作区 C:\ssbot\gate_0c053d9），4 实例，随机起点（种子 50300–51000，各段不重叠），`--real-quit 0.2`，规划器 oracle 视图。
- 有效 529 场：**CLEAR 516（97.5 %）**，QUIT 13（全部为挨一下后的 Q6 / Q5 按规则退出），**WOULD_DIE 0**，STUCK 0。击杀用时约 55–80 s（你的录像 69 s）。
- 不计入：HARNESS_FAIL 5（第 5 段，离线分析抢 CPU，4 个实例同时触发失联看门狗暂停）；第 11 段 3 号实例启动失败（上一段最后一场击杀后游戏进入"丝之心"记忆场景，读档函数等主菜单超时）。两者都是测试框架问题，待修。
- 旁证：更早的版本 6c64421（171 场）+ ab7597b（68 场）共 239 场，238 CLEAR、0 WOULD_DIE；不与门槛混计（证据按代码指纹分开）。
- 运行目录：C:\ssbot\data\runs\m2\20261002_123347 … 20261002_150453（*_eval_planner_oracle）。

## M2：下劈落空与实战回归（2026-10-02 晚）

- **起因**：主线（0c053d9 之后）实战检查 20261002_152649：80 场 60 % CLEAR（门槛代码 97.5 %），30 场 QUIT（22 场 Q6）。你看到正面下劈从不命中、从后方下劈出手太高。
- **计数更正**：下劈命中事件的来源是 `DownSlash`（在事件 data 里），不是 "DownSpike"；按此统计 152649 每次冲撞 0.50 次下劈命中（123 / 246），"0 次"是计数错误。
- **时间基准不是原因**：评估录像里 timeScale 0 的帧只有 0.1 %（0.05 慢动作 1.4 %）；"22–28 %"是 50 Hz 物理在 60 fps 下自然的无步进帧。
- **根因 1（下劈判定形状）**：规划器的下劈框是拼刀多边形的外接矩形；真正的伤害碰撞体（Attacks/Default/DownSlash）是从主角背后上方到前下方的斜条，矩形的后下角多出 0.5–1 u。工具 `attack_shape_audit`（只用录像）：152649 的 464 次下劈，矩形 TP 133 / FP 120 / FN 3（精确率 53 %，接触比命中早最多 3 帧）；多边形 TP 132 / FP 25 / FN 4（84 %），接触多在命中当帧。正面下劈飞越 Boss 背部时，真实形状离 Boss 还差 0.39–0.49 u。规划器改用多边形（e10c2b8）；你的 5 次下劈仍全部复现。
- **根因 2（预测框）**：`boss_path_audit`：(a) 一半的场次策略在 Emerge Antic C 之后才开始，追踪器丢了招式开头，第一次冲撞的预测框整段不动（+24 帧时前沿 p10 落后 9.7 u）；(b) 从 Charge Emerge 预测时用的是冒出动画当帧的碰撞体（偏高最多 2.0 u、前沿落后 1.7–4.9 u）。修复后（aa6eb4d）冲撞中前沿误差 ±0.5 u、顶部 0。
- **根因 3（延迟）**：152649 的规划 tick p99 已是 29 ms（门槛代码 9 ms），决策最多晚 2 帧；铃铛阶段的原地来回转身和被铃砸多在 40–90 ms 的 tick 之后。铃铛路径缓存、编译核、改向批量计算后（777f935），同一录像 p99 33 → 10 ms。
- **下劈后接丝矛**：e10c2b8 实战（20261002_162847）Charge End 的 17 次受击全部是下劈命中前 2 帧按了丝矛：游戏在命中时开始丝矛并取消弹起，主角悬在 Boss 高度。改为"下劈前摇 / 下劈中 / 预测弹起前后 12 帧内按丝矛 = 不安全"（6ab67e1）。
- **铃铛**：横砍下落的铃（改向）原来几乎从不选（重放 14 个 QUIT 场次：可选 3345 个 tick，选中 4 个），因为舒适度和后续检查用的是铃的两侧弹跳。改为按改向后的单一路径检查，并在 J 里计入腾出的空间（23f54c3）。
- **实战结果（6ab67e1，oracle，4 实例，每实例 4 线程，20261002_171806）**：有效 74 场，**CLEAR 73（98.6 %）**，QUIT 1，WOULD_DIE 0，受击 5 次（162847：41 次）。下劈每次冲撞 0.97 次命中；正面 22 中 / 2 空（152649：30 / 90），从后方 82 / 0（89 / 9），下劈后 40 帧内受击 0。下劈多边形对命中事件 TP 240 / FP 1 / FN 1。落铃改向每场二阶段 2.49 次（152649：0.054）。tick p99（每场 p99 的中位数）13.4 ms。击杀用时中位数 58 s。2 场 HARNESS_FAIL：新工作区首场的 numba 编译触发失联看门狗。
- **视觉等效视图（degraded_dust，6ab67e1，20261002_173956）**：有效 36 场 8 CLEAR（22 %，早先各次 15–29 %），28 场 QUIT（21 场 Q6）；受击 28 次中 19 次是落铃 M2（精确铃铛路径只在 oracle 视图启用），视图下几乎不下劈（每次冲撞 0.024 次）。未改善也未变差，待做。
- **暂停压力测试（11b4ca0，oracle，`--real-quit 1.0 --inject-hits 0.5`，20261002_180411）**：121 次试验，112 次注入受击（84 % 在空中），112 次全部暂停并退到主菜单：从首个可暂停帧起暂停延迟 p50 / p99 2 帧、最大 4 帧；暂停中外来按键 0、意外取消暂停 0、错误确认 0；到主菜单最多 5.1 s。未达标：注入落在击杀 / 弹起 / 拼刀 / 硬直 ±3 帧内的只有 3.6 %（目标 ≥ 30 %），注入时机待修。

## M2：Bell Beast 门槛重测（oracle，代码 11b4ca0，2026-10-02 晚）

- **通过**：代码固定在 11b4ca0（工作区 C:\ssbot\live_11b4ca0，numba 已预热），4 实例，每实例 4 线程，随机起点（种子 70000 段、72000 段），`--real-quit 0.2`，oracle 视图。第一段期间另有 3 个开发代理在跑（低优先级），未出现 HARNESS_FAIL。
- 有效 510 场：**CLEAR 503（98.6 %）**，QUIT 7（全部是挨一下后剩 2 格时 Q6 按规则退出），**WOULD_DIE 0**，STUCK 0。挨打：491 场 0 次、18 场 1 次、1 场 2 次。击杀用时中位数 59 s（45–76 s）。规划 tick 每场 p99 的中位数 12.7 ms。
- 运行目录：C:\ssbot\data\runs\m2\20261002_190611_BellBeast_eval_planner_oracle（386 场）、20261002_210643_BellBeast_eval_planner_oracle（124 场）。20261002_210607 为空跑（STOP_AGENTS 仍在，combat_run 也认这个停止文件），不计。

## M2：Bell Beast 门槛（模拟最终路径 degraded_dust，代码 4a90331，2026-10-03）

- **通过**：代码固定在 4a90331（工作区 C:\ssbot\live_vv，numba 已预热），实例 0、1，每实例 4 线程，随机起点，`--real-quit 0.2`，视图 degraded_dust（ObservabilityFilter VISION_EQUIVALENT + 噪声 + 2–4 帧延迟 + 可见烟尘前兆；见 m2_vision_view.md）。同期另有 Forum 采集、暂停压力测试和开发代理在跑。
- 有效 516 场（另 3 场 HARNESS_FAIL 不计）：**CLEAR 487（94.4 %）**，QUIT 29，**WOULD_DIE 0**，未预测命中 0。挨打：490 场 0 次、29 场 1 次。29 次 QUIT 全部是挨一下后 h = 2 时的 Q6（FORCED_RISK）——正是 2026-10-03 你改的规则要改掉的情形（h = 2 不再因 FORCED_RISK 退出，攒丝回血，DESIGN §3.7.4 Q6）。真实退出 6 次全部到主菜单，暂停延迟 p50 0.083 s、最大 0.165 s，0 次选错。击杀用时中位数 93 s（oracle 视图 59 s）；规划 tick 每场 p99 的中位数 14.6 ms。
- 运行目录：C:\ssbot\data\runs\m2\20261003_053033_BellBeast_eval_planner_degraded_dust（150）、20261003_074533_…（249 有效）、20261003_111705_…（117 有效）。
