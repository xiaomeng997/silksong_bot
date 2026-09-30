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

## P4 SendInput — 通过（前台）

- 游戏在前台时，扫描码 SendInput 能驱动菜单（回车确认）和游戏：按住"右"1.5 s，Hornet 从 x=238.78 移到 249.84。
- 键位与默认键盘绑定一致：Z 跳、X 攻击、C 冲刺、A 缚丝、S 飞针、D 织针曲、F 快速施放、V 嘲讽、I 背包、Tab 快速地图、M/Q/J/T 背包分页、方向键、Esc 暂停。
- 与 Harmony 注入的轨迹对比尚未做（等 M1 的注入模块）。

## P6 计时器（部分）

| 情形 | 结果 |
|---|---|
| PLAYING | `GameManager.PlayTime` 按真实时间每秒 +1 |
| 暂停菜单 | GameState=PAUSED，timeScale=0，PlayTime 3 s 内不变 |
| 取消暂停 | 立即恢复计时 |
| 保存并退出 | 确认的那一刻把会话时间写入 `playerData.playTime`（447.464 → 470.497，正好等于暂停时的 PlayTime）；之后约 3 s 保持 PAUSED、timeScale=0，然后进入 MAIN_MENU |
| 失焦 | 训练副本（插件强制 `runInBackground=true`）失焦后继续以 60 fps 运行。**原版失焦是否继续模拟仍未测** |

仍未测：背包、Quick Map、Bellway 乘车、房间切换、片尾。

## P7 暂停与退出（部分）

- 紧急退出的完整按键序列：Esc → 移到"退出至菜单" → 回车 → 确认框"保存并退出？"（**默认选中"否"**）→ 上 → 回车。暂停一旦生效，世界就冻结，后面几步只花墙钟时间，不花游戏时间。
- 退出过程中（确认后到主菜单）一直是 PAUSED、timeScale=0，淡出期间世界不动。
- **鼠标悬停会改变菜单选中项。** 第一次暂停时光标落在"退出至菜单"，是因为鼠标正停在那个位置；第二次（鼠标不在菜单上）落在"继续"。结论：正式运行必须拔掉鼠标或把光标停在游戏窗口外；菜单操作前必须先读出光标位置。
- 未测：hit-freeze 中按暂停是丢弃还是排队、0.3 s 锁定、`disableSaveQuit` 的来源、灰色退出按钮。

## 训练副本的桌面行为（新增）

- 原版在前台时会隐藏并锁定鼠标（`InputHandler.SetCursorEnabled`、PlayMaker 动作 `SetMouseCursor`、`LanguageSelector`），用户无法操作其他窗口。
- SsOracle 的 `TrainingEnvironment`：跳过 `SetCursorEnabled`，每帧强制显示和释放鼠标、保持 `runInBackground`，并在 Input System 中禁用鼠标设备（悬停不再影响菜单）。实测失焦后照常运行。
- 训练阶段应改用游戏内注入输入（无需前台）。外部 SendInput 只用于最终路径的测试，测试时必须先告知用户，且操作完立即把前台还回去（`drive.py` 已实现，并会把鼠标移到游戏窗口外）。
