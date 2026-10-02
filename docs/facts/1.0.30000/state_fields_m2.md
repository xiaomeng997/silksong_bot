# STATE 的 M2 新字段（SsOracle，1.0.30000）

> 2026-10-01。M2 跨模块决定 5 规定的 oracle 新导出：每个字段的来源成员、单位与时间基准，以及同批修复的"首次 Charge Emerge 没有碰撞体"问题。代码在 `oracle/src`，读取约定见 `brain/ssbot/ipc/ents.py`。所有新字段都是在原有 STATE 之上增加的键：旧录像里没有它们，Python 端一律用 `.get()` 读，缺失时按"未知"处理（决定 4：未知从不等于安全）。
>
> 游戏内验证：`brain/ssbot/probes/m2_exports.py`（实例 0，`bellbeast_arena`，逐项 PASS/FAIL）**尚未运行**（本轮禁止启动游戏）。离线已验证：所有新成员在 1.0.30000 中存在（`oracle/tools/symcheck`：630/630 个符号，41 个补丁签名 0 问题），纯逻辑部分（`tm.inv`、标签伤害、`room.gates` 满表替换、"hit" 嵌套、`act.hf` 恢复）见 `oracle/tests/EntitiesCheck`、`oracle/tests/InputLogicCheck`。探针没有覆盖的导出（本场战斗不产生它们）：`ApplyExtraDamage` 的命中（毒、电标签、`DamageEffectTicker`）、`hero.tags` 的条目、真实的 `hero.wall`、菜单 `sel` 的 "back" / "ok"、`menu.quitting` 为真；"yes" / "no" 只在可选的 `--quit-prompt` 步骤里读。

**约定。** 所有值都在第 f 帧的 `WaitForEndOfFrame` 采样，与该帧 STATE 的其他字段同一时刻。"缩放时间"指游戏时间（各计时器每帧减或加 `Time.deltaTime`，随 `Time.timeScale` 变慢、暂停时为 0）；"步"指 `FixedUpdate` 步（`Time.fixedDeltaTime` = 0.02 s，与 STATE 的 `fdt` 相同）或游戏读输入的帧，按游戏自己的计数方式。没有前缀的 `.cs` 在 `C:\ssbot\decomp\1.0.30000\Assembly-CSharp\` 下，`TK2D\` 指 `TeamCherry.TK2D\`。

## 1. hero.tm：英雄的私有计时器与步数计数器

`oracle/src/Hero/HeroExporter.cs` `WriteTimers`。除 `grav` 外都是 `AccessTools.FieldRef` 委托读字段（每帧无反射、无分配）。某个字段在将来的版本里找不到时，该键写 nil（`Hero.Refs` 记错误，SymbolCheck 判硬失败）。

| 键 | 来源成员 | 单位 / 时间基准 | 说明 |
|---|---|---|---|
| `inv` | `cState.invulnerable` 为真时：`HeroController.invulnerableFreezeDuration`（1382）+ `invulnerableDuration`（1384），各自取 max(0, ·)；否则 0（`HeroExporter.InvLeft`） | s，缩放时间 | `StartInvulnerable`（9670）设定，`Invulnerable()` 协程（9693）每帧减 `Time.deltaTime`。受击后为 `INVUL_TIME` = 1.0（Weighted Anklet 乘 `WeightedAnkletDmgInvulnMult`；`DAMAGE_FREEZE_DOWN` = 0，见 hero_constants.json），然后递减到 0。`HeroController.SceneInit`（1913）清掉 `cState.invulnerable` 却不动这两个计时器，协程照样往下减：受击后 1 s 内换房或读档，计时器读数可达约 1.0 而 `CanTakeDamage` 为真，所以标志为假时导出 0（否则读取方会把它当成无敌帧，失效于不安全一侧）。只覆盖这一条无敌来源：招架（`parry_invuln_timer`）、`invulnerable_count`、下劈无敌步（`cstate_int`）、`invincibility_source` 仍在原来的键里；是否真的不受伤以 `can_take_damage` / `invulnerable` 为准 |
| `recoil` | `cState.recoiling` 时为 `RECOIL_DURATION`（367）− `recoilTimer`（536）；`cState.recoilFrozen` 时为整段 `RECOIL_DURATION`；否则 0 | s，缩放时间 | 伤害击退还剩多久。`recoilTimer` 在 `no_input` 状态下每帧加 `Time.deltaTime`（2015-2017），到 0.2 s 时 `CancelDamageRecoil`。`recoilFrozen` 阶段（受击 `FreezeMoment`，9658）还没开始计时 |
| `recoil_steps` | `recoilStepsLeft`（538） | 步（FixedUpdate） | 砍击后坐剩余步数（`FixedUpdate` 2977-2979 递减） |
| `dash_cd` | `dashCooldownTimer`（548） | s，缩放时间 | 每帧减 `Time.deltaTime`（2300） |
| `atk_cd` | `attack_cooldown`（518） | s，缩放时间 | 每帧减（2292） |
| `atk_t` | `attack_time`（516） | s，缩放时间 | 当前攻击已进行的时间（2045 每帧加） |
| `tool_cd` | `throwToolCooldown`（520） | s，缩放时间 | 每帧减（2294-2296） |
| `jump_steps` | `jump_steps`（506） | 步 | 本次跳跃已上升的步数 |
| `jumped_steps` | `jumped_steps`（508） | 步 | |
| `ds` | `downSpikeTimer`（574，public） | s，缩放时间 | 下劈前摇 / 下劈计时 |
| `ds_rec` | `downSpikeRecoveryTimer`（576，public） | s，缩放时间 | 下劈恢复计时 |
| `grav` | `HeroController.Body.gravityScale` | 倍数 | 刚体重力倍数（刚体缺失时 nil） |
| `qj` / `qa` / `qt` | `jumpQueueSteps`（854）/ `attackQueueSteps`（866）/ `toolThrowQueueSteps`（874） | 帧（按住期间每帧 +1，3205/3217/3225） | 输入排队计数；与 `JUMP_QUEUE_STEPS` 2、`ATTACK_QUEUE_STEPS` 8、`TOOLTHROW_QUEUE_STEPS` 5 比较（8691、8719、8723） |

## 2. hero.alpha：物理相位

`(Time.timeAsDouble − Time.fixedTimeAsDouble) / Time.fixedDeltaTime`，帧末计算（`HeroExporter.WriteAlpha`），无单位，正常在 [0, 1)：本帧在当前物理步里走到了哪里。Unity 限制长帧的物理步数（`maximumDeltaTime`）时可能 ≥ 1，原样导出。用 double：float 时钟在约一天的游戏时间后误差达到 0.02 s 步长的五分之一。`fixedDeltaTime` ≤ 0 时为 nil。PlayMaker 的 `ScaleTime` 动作在 `adjustFixedDeltaTime` 为真时把 `Time.fixedDeltaTime` 设为 0.02 × timeScale（`HutongGames.PlayMaker.Actions\ScaleTime.cs:45`）：慢动作中 `fdt` < 0.02，timeScale 为 0 时 alpha 为 nil，步长在一步中途改变时 alpha 可能瞬时 ≥ 1。读取方应以同一 STATE 的 `fdt` 为步长；探针只要求 alpha ≥ 0，≥ 1 的帧计数（上限 1%）。试跑 26 892 个 STATE 的 `fdt` 全为 0.02，没有 `dt` > 0.1 s 的帧。

依据：运动学审阅发现每帧 0 步还是 1 步由帧时间抖动决定（试跑中 `fs` = 0 的帧占 20.7%，因为 0.02 s 的物理步比 1/60 s 的帧长），规划器需要实时相位，而不是从历史估计。

## 3. hero.wall

`[HeroController.touchingWallL, touchingWallR]`（878、880，public bool）。墙在哪一侧。此前 WorldState 用朝向推断（`BeginWallSlide` 把朝向设为朝墙，8456-8457），被击退撞到身后的墙时会判反（WorldState 审阅）。

## 4. hero.tags：英雄身上生效的伤害标签

列表，每项 `{kind, dmg_left, t_left}`，来源 `HeroController.tagDamageTaker`（1175，`TagDamageTaker`）的 `TaggedDamage`（`TagDamageTaker.cs:18`）。没有 `TagDamageTaker` 时为 nil，没有标签时为 []。

| 键 | 来源 | 单位 / 时间基准 | 说明 |
|---|---|---|---|
| `kind` | `DamageTag` 资产名（`Object.name`，按引用缓存） | — | 如酸液、霜水标签 |
| `dmg_left` | 剩余次数 × 每次的面具数。次数：`DamageTagInfo.HitsLeft`（`DamageTagInfo.cs:7`）；每次：`DamageTag.damageAmount`（`DamageTag.cs:29`，私有）按游戏的算法放大（`HeroExporter.TagHitDamage`） | 面具 | 还会造成的伤害的**上界**。次数规则按 `TagDamageTaker.Tick`（标签在 `RemoveAfterNextHit` 时、或一次命中把 `HitsLeft` 从 1 减到 0 时被移除）：`RemoveAfterNextHit`（13）→ 1 次；`HitsLeft` > 0 → `HitsLeft` 次（来自 `totalHitLimit`（47），或 `AddDamageTagToStack` 的 `hitAmountOverride`，后者即使标签本身不限次数也有效）；`HitsLeft` = 0 且标签有次数上限 → 0（最后一次已落下，移除排队中）；`HitsLeft` = 0 且不限次数 → 不递减，直到来源移除它为止（如在霜水里游泳时），记为 −1（无上界）。每次的面具数：`DamageTag.OnHit` 对工具标签（`isToolDamage`）取 RoundToInt(damageAmount × (1 + `ToolKitUpgrades` × `Gameplay.ToolKitDamageIncrease`))（`DamageTag.cs:119-124`）；`HeroController.ApplyTagDamage` 把霜标签交给 `TakeFrostDamage`、其他交给 `DoSpecialDamage`，两者都进 `DoSpecialDamage`，它在装备 Barbed Wire 时把非霜伤害乘 `Gameplay.BarbedWireDamageTakenMultiplier`（资产默认 2）后取 floor（`HeroController.cs:5171-5196`）。装备状态在 `SafeReads.ToolsReadable` 为假时读不了，按已装备计（保持上界）；读不到伤害量时记 −1。只会更少、不会更多的情形：Fractured Mask 吸收一次、`DoSpecialDamage` 在转场 / 过场 / 无敌作弊时不扣血、英雄不能受伤时 `Tick` 不经命中直接移除有上限的标签 |
| `t_left` | max(0, `DamageTagInfo.NextHitTime`（9）− `Time.timeAsDouble`) | s，缩放时间（标签自己用的 `Time.timeAsDouble` 时钟） | 距**下一次**命中的时间 |

`dmg_left` 与 `t_left` 是给 hits_to_death 的保守组合：待落下的全部伤害，以及其中最早一次落下的时刻（`TagDamageTaker.Tick`，105：到时命中，之后间隔 `delayPerHit`）。

## 5. hero.tool_max

与 `hero.tools` 逐项对齐：`ToolItemManager.GetToolStorageAmount(ToolItemManager.GetToolByName(name))`（`ToolItemManager.cs:927-944`：基础容量 + Tool Pouch 升级 + Shell Satchel；被临时覆盖的工具取覆盖值）。空槽或未知工具名为 nil。`SafeReads.ToolsReadable` 为假时整个键为 nil（该 getter 会经过 `ToolItemManager.Instance` 与 `IsEquippedHud`，见 `oracle/src/Hero/SafeReads.cs`）。单位：次数（与 `tool_amounts` 相同）。

## 6. ents[].hidden

每个实体都写（bool）。为真表示：该实体是本场景中**曾经导出过**的 HealthManager 根对象，现在它的 HealthManager 不活动（组件禁用或 GameObject 不活动；`isDead` 为假且 `hp` > 0：有特殊死亡的 boss 在 "Death Broadcast" 关掉 HealthManager 时 `isDead` 仍为假，它是尸体而不是潜地，照旧离开 `ents`），本帧也没有它自己的活动伤害源把它拉进导出，并且仍在视野（+6 u 余量 + 自身范围）内（`EntityRegistry.HiddenPass`）。hidden 实体保留 `pos`（根变换）、`flipX`、`fsms`、`anim`、`hp`/`is_dead`/`inv`，`colliders` 恒为 []，GameObject 不活动时 `render_aabb` 为 nil。每帧最多 16 个。

依据：行为表构建（99 场）中 Bell Beast 每次攻击有 1.0-2.2 s 不在 `ents` 里。试跑（2 场）按 Control 状态统计的缺失帧：Submerged 5045、Emerge Antic L/C 1821/1699、Burst Antic 1768、Burst Recovery 1662、Ptn L 924、Rage Rumble/Antic/Pos/Submerge 242/146/122/122，其间 Control FSM 的转移事件照常到达（FSM 只在活动的 GameObject 上运行），所以是 HealthManager 组件被关掉（`OnDisable` 把它移出 `_activeHealthManagers`，`HealthManager.cs:716`），GameObject 仍活动；这时它的 Control FSM 已经决定了出土位置（Burst 的出土 x 81.2-91.2 在 Burst Pos 时就已确定，比现在早约 1.2 s）。试跑 f42894-43015：最后一帧导出位置 (73.6, 5.49) 在相机视野内，之后消失而 FSM 仍在转移，说明是 HealthManager 失活而不是出了视野。由活动伤害源拉进来的实体永远不是 hidden，所以不会因此丢掉威胁碰撞体。

**对读取方的影响（部署前提）**：以前"在 `ents` 里"等于"活动"，现在不是了。按 type_key 找 boss、统计碰撞体覆盖的代码要跳过 hidden 实体，统一用 `ssbot.ipc.ents.boss_entity(ents, type_key)`（默认跳过 hidden；`include_hidden=True` 连同 hidden 一起返回，它的 `pos`/`fsms`/`hp` 仍有效）。本分支已改：`train/data_policy.py`（跳过，保持数据采集与旧 oracle 一致；`tests/test_data_policy.py`）、`train/episode.py`（结束时的 boss hp，包括 hidden）、`probes/m2_bellbeast.py`。main 上另外两处由各自模块的 M2 分支处理，**这两个分支合并之前不要部署本插件**：`knowledge/behaviour_tables.py`（main 454 行按 type_key 取第一个实体并置 `boss_now`；行为分支 71e43db 中 hidden 的 boss 只记为 `boss_hidden`，不进 `boss_now`，`_entities` 对 hidden 实体单独计数）；`backends/oracle_backend.py` 与 `observability.py`（WorldState 分支 0f72eb9：hidden 实体导出为 `Entity.hidden`、无碰撞框，按部件找 boss 时跳过 hidden，`test_oracle_backend.py::test_hidden_entity_is_exported_without_boxes`）。

## 7. ents[].colliders[].name

碰撞体所在 GameObject 的名字（缓存于实体重建时，`ColliderSlot.Name`）：子物体上的如 `"PolyCollider"`、`"LeapCollider"`，根物体上的是根的名字（如 `"Bone Beast"`）。多路径多边形的每条路径同名。行为模板此前只能用 type_key + kind + 顶点数区分碰撞体（行为表构建的 open issue）。

## 8. 事件 "hit"（英雄或任何来源对 HealthManager 造成伤害）

`oracle/src/Events/HitTap.cs`：前缀 + 后缀挂在 HealthManager 降低 hp 的三处：`TakeDamage(HitInstance)`（943，经 `Hit` 到达：刀、工具、法术）、`ApplyExtraDamage(HitInstance)`（1469：延迟连击与伤害标签，如毒、电）、`ApplyExtraDamage(int)`（1460：`DamageEffectTicker`）。只有 hp 变化或死亡的调用才发事件（免疫与 0 伤害不发）。所有来源都算，不只英雄：用 `src` 区分。被 `sendDamageTo` 转发时（1299-1306）`TakeDamage` 直接改接收方的 `hp`，不再调用接收方的 `TakeDamage`，所以记接收方、只发一次；两个 `ApplyExtraDamage` 重载（1460-1477）总是降低自身的 `hp`，不转发，记自身。嵌套：`TakeDamage` 先扣 hp（1299-1306），再用 `TagDamageTaker.AddDamageTagToStack` 加上这一击的毒 / 电层数（1310-1316）；对一个标记了 `RemoveAfterNextHit` 的标签再次加层会立即调用 `DamageTag.OnHit`（`TagDamageTaker.cs:49-53`）→ `HealthManager.ApplyTagDamage` → `ApplyExtraDamage`（1523），在外层调用里面、打在同一个目标上。这时内层先发事件，外层只报它自己那部分（`HitTap.OwnDamage`），所以同一目标的 `dmg` 之和总等于它的 hp 变化。延迟连击（lag hits）不会嵌套：`DamageEnemies` 在 `Hit` 返回之后才调 `DoLagHits`（`DamageEnemies.cs:834`、1305）。前提是内层调用都发生在外层自己的扣血之后（上面这条路径如此）；若有内层调用在外层扣血之前，外层事件的 `hp_after` 会多出内层的伤害，击杀一击的 `dead` 也会是假。同一帧里内层事件先于外层到达，所以按事件顺序串 `hp_before`/`hp_after` 不一定首尾相接；按帧看，各事件 `hp_before` 的最大值等于该帧之前的 hp，`dmg` 之和等于该帧的 hp 变化（探针 `hp_chain` 就这样核对）。不报告的 hp 写入（不是攻击伤害）：PlayMaker 动作 `SetHP` / `SubtractHP`（脚本设定），`BlackThreadState` / `LifebloodState` 的 hp 缩放，以及 Silksong 中未用到的 `SpellFluke`；这些仍体现在 `ents[].hp` 里。

| 键 | 来源 | 说明 |
|---|---|---|
| `ent` | 失血的 HealthManager 的 `gameObject.GetInstanceID()` | 与它在 `ents` 中的 `iid` 相同；不在 `ents` 里（视野外、未导出）也发 |
| `type_key` | `EntityRegistry.TypeKey(gameObject.name)` | |
| `dmg` | `hp_before − hp_after` | 面具外的敌人 HP 单位。游戏把 hp 下限钳在 −1000，所以超量的击杀一击也按全额计（试跑中 Bell Beast 每一刀都是 5，56/56） |
| `dealt` | 进入时的 `HitInstance.DamageDealt`（`int` 重载为其参数） | 攻击方给出的值，未经目标的 `damageScaling`、Wanderer 暴击倍数与 `HitInstance.Multiplier`。前缀里记录，因为 `TakeDamage` 会改写自己的参数 |
| `attack` | `AttackTypes` 名 | `"Nail"`、`"Generic"`（`int` 重载）等 |
| `src` | `HitInstance.Source.name` | 如英雄的 `"Slash"`、`"DownSlash"`、工具物体；没有来源为 null |
| `hp_before`, `hp_after` | `HealthManager.hp`（229） | |
| `dead` | `hp_after <= 0` 或调用后 `isDead` | 有特殊死亡的 boss（`hasSpecialDeath`，403/1657，如 Bell Beast）不置 `isDead`，经 FSM 死亡，所以以 hp 为准：击杀一击 `dead` 为真。击杀一击 = `hp_before > 0` 且 `hp_after <= 0` 的那一次；之后打在尸体上的命中（若 hp 还在变）也带 `dead` 为真，但不是击杀 |
| `crit` | `HitInstance.CriticalHit` | |

另有 EventTap 的序号 `n`。时间基准：事件帧 = 调用发生的那一帧（`Time.frameCount`），与 STATE `ev` 中其他事件相同。

## 9. STATE "menu"（暂停菜单）

`oracle/src/Export/MenuExporter.cs`。在暂停时（`UIManager.uiState == PAUSED` 或 `GameManager.isPaused`）、取消暂停后菜单淡出期间（遮罩 alpha > 0）、以及从退出淡出开始直到 GameManager 消失这段时间写入；其余时候为 nil。

| 键 | 来源 | 说明 |
|---|---|---|
| `sel` | `EventSystem.current.currentSelectedGameObject` 的角色 | `"continue"`/`"options"`/`"quit"`：`PauseMenuButton.pauseButtonType`（`UnityEngine.UI\PauseMenuButton.cs:23`）；`"yes"`/`"no"`：返回主菜单确认框的按钮，按其持久监听调用的 UIManager 方法判定（`UIReturnToMainMenu` 909 / `UILeaveExitToMenuPrompt` 899），判定不了时按在 `returnMainMenuPrompt`（251）内的高度（P7：是在否之上）；`"back"`：某个 `MenuScreen.backButton`（如选项菜单），或监听调用 `UIGoBack`；`"ok"`：`GenericMessageCanvas` 内（如 SAVE_FAILED）；没有选中或其他为 nil。按 instance id 缓存，只在选中项变化时调 `GetComponent` |
| `quit_ok` | 暂停菜单里 Quit 按钮的 `Selectable.interactable` | 只有本次暂停中暂停菜单的 `MenuButtonList.SetupActive`（107）运行过之后才给值，之前为 nil：`ShowMenu`（2126）在暂停的下一帧才调用它，在此之前的值是上一次暂停留下的。`MenuButtonSaveQuitListCondition` 在 `disableSaveQuit` 或 `ScenePreloader.HasPendingOperations` 时把 Quit 置灰（m0:C8） |
| `dim` | `UIManager.modalDimmer.alpha`（57） | 暂停时淡入到 0.8（`GoToPauseMenu`，1698），取消暂停时淡出到 0（`UIClosePauseMenu`，837） |
| `alpha` | `UIManager.fadingMenuScreen`（280，私有）的 `MenuScreen.ScreenCanvasGroup`（= 其 `GetComponent<CanvasGroup>()`，`MenuScreen.cs:28`，按屏缓存）`.alpha` | 最近一次 `ShowMenu` 显示的菜单屏。`ShowMenu` 一开始就设置它，早于 `menuState` 改变（人类会话中前 8 个暂停帧的 `menuState` 是旧值，安全监督审阅） |
| `ignore_unpause` | `UIManager.ignoreUnpause`（274，私有） | `GoToPauseMenu` 运行期间为真，此时 Continue / Cancel 被忽略（1988） |
| `quitting` | `CameraController.FadeOut(CameraFadeType.TO_MENU)` 已在当前 GameManager 上调用（后缀补丁） | `GameManager.ReturnToMainMenu` 已过了存档（5339 起；存档失败时在淡出前就返回，m0:C9），在 5378 开始淡出到菜单：退出已不可撤销。GameManager 换了或回到 MAIN_MENU 时清除 |

## 10. act.hf：HoldFilter 状态

STATE 基础字段 `act` 新增 `hf`（`oracle/src/Export/FrameExporter.cs` `WriteHoldFilter`）：本帧锁存之后（`KeyboardInjector.OnBeforeUpdate` 在本帧动态输入更新中已运行）的 `KeyboardInjector.Filter` 状态。

| 键 | 说明 |
|---|---|
| `pending` | 每个按钮（ACTION 按钮位顺序，22 个）已请求但尚未锁存的边沿数 |
| `age` | 每个按钮在当前状态下已锁存的帧数，上限 255（过滤器只把它和最短按下 / 松开帧数比较，C19 为 2，所以 ≥ 最大限值的任何值作用相同） |
| `latched` | 锁存的按钮掩码（= `act.mask`） |
| `desired` | 过滤器最后收到的期望掩码 |

这四项是过滤器的完整状态（`deferred`、`exclusiveWaiting` 只影响计数器）：`HoldFilter.Restore` 从它们恢复后，之后每一帧的锁存与原过滤器完全相同。`oracle/tests/InputLogicCheck` 在 3 组限值、1200 个随机切点上验证 0 帧不同；只用锁存掩码恢复（当作所有键早已稳定）则有 59273 帧不同。运动学审阅指出 `hold_filter` 没有初始状态，规划器每帧重规划时前 1-2 帧（正是重按发生处）复现不了锁存流；规划器应从 `act.hf` 起步。

## 11. room.gates：战斗 / 竞技场门与其他状态已变的地形

STATE `room` 新增 `gates`（`oracle/src/SceneDump/GateWatch.cs`）。TERRAIN 是进房时的快照：为战斗关闭的竞技场门在快照里是关的，战斗中消失的墙在快照里是开的（Bone_05：`"Threaded Bell Gate"` x 67.2-69.2 与 102.0-104.0 进房时 off、战斗时关闭；`"Wall"` x 91.7-100.3 进房时 on、战斗时消失；运动学审阅，试跑与实跑）。被监视的固体：`BattleScene.gates` 下的所有碰撞体、快照时为 off 的固体、以及快照后被看到状态变了的其他固体（每帧轮询 16 个，Bone_05 共 31 个固体，每个约每 2 帧看一次）。每项：

| 键 | 说明 |
|---|---|
| `name` | 碰撞体所在 GameObject 名 |
| `id` | 碰撞体 instance id，等于 TERRAIN `solids[].id`（用它把状态套到 TERRAIN 固体上） |
| `enabled` | 现在 `Collider2D.enabled && gameObject.activeInHierarchy` |
| `box` | [x0, y0, x1, y1] 世界坐标 AABB：快照时的轮廓，按变换位置自快照以来的平移移动（不跟随旋转与缩放） |

当前房间的快照完成之前为 nil（未知，不是"没有门"）；没有被监视的固体时为 []。最多 32 项，`BattleScene.gates` 下的先占位，所以快照时 off 的固体再多也挤不掉竞技场门。表满时，一个状态与快照不同的固体会顶替一个"只因快照时 off 才列出、现在仍 off"的项（它说的和 TERRAIN 一样，被顶替后回到轮询池；`GateWatch.EvictSlot`/`Admit`）。竞技场门和见过状态变化的固体一旦列出就不会被顶替；只有表里全是这两类、又发现一个变化了的固体时它才列不进去，这时 STATE `room.gates_trunc` 变为真并保持到离开该房间：读取方此后要把所有未列出的 TERRAIN 固体的状态当作未知（而不是"未变"）。`room.gates_trunc`：`gates` 为 nil 时为 nil，否则为 bool。Bone_05 没有 `BattleScene`：两扇 `"Threaded Bell Gate"` 因为快照时 off 而被监视，`"Wall"` 在轮询看到它消失后加入（试跑 TERRAIN：31 个固体，off 的还有 `"Roof Collider_Basic (1)"`）。

注意与 TERRAIN 的 `gates`（场景转换门 `bot1`、`left1` 等）不是一回事。`id` 是决定 5 之外多给的键（{name, enabled, box} 之外），用来对上 TERRAIN `solids[].id`。

## 12. 修复：Bell Beast 第一次 Charge Emerge 导出 colliders == []

**现象**（行为审阅）：每场战斗第一次 Charge Emerge 的整个过程中 boss 的 `colliders` 为 []，而它在造成伤害。试跑 f42726-42769 与 f56714-56758（89 帧），实跑 i0_000 1211 帧中 1209 帧，其间 22 次受击都落在这些帧上。

**根因**（不是审阅猜测的 `SafeRefresh` 失败：失败时 `SafeRefresh` 会把 `Fsms` 也清成空，而这些帧里 boss 的 `fsms` 照常带着 Control 状态 "Charge Emerge"；实跑 i1-i3 的 player 日志中 "cache rebuild" 警告为 0 条，i0 的日志已被之后的会话覆盖）：Bell Beast 的身体碰撞框不是预制体里的组件，而是 tk2d 在运行时添加的。`tk2dBaseSprite.UpdateCollider`（`TK2D\tk2dBaseSprite.cs:447`）在精灵**第一次**显示带 Box 碰撞类型的帧时才 `AddComponent<BoxCollider2D>()`（484-487；多边形 528/533、边 568/573 同理），之后按帧启用 / 禁用并改尺寸。读档重新加载场景，boss 是新对象；oracle 在它第一次出现（Charge Emerge 第 0 帧，该帧精灵没有碰撞框）时建立组件缓存，此后几帧 tk2d 才加上 BoxCollider2D，缓存不知道它。根上只有这个框，子物体 PolyCollider 当时不活动（缓存里有，但不活动的子碰撞体不导出），所以整段 Charge Emerge 都是 []。直到某个无关的重建（试跑中晚了 85 帧与 71 帧：f42811、f56785）才出现这个 4 顶点的 box。证据：试跑每场第一次之后的 26 次 Charge Emerge 全部在第 0 帧就导出这个 4 顶点的 box（前 4 帧 enabled = false，之后 true，尺寸随动画帧变，正是 tk2d 精灵碰撞体的行为）；而 `GetComponentsInChildren(true)` 会找到预制体里已有的禁用组件，第一次没找到说明组件当时不存在。

**修复**（`oracle/src/Entities/EntityRegistry.cs`）：重建时记下实体拥有的每个 tk2d 精灵及其 `boxCollider2D` 引用、`polygonCollider2D.Count`、`edgeCollider2D.Count`（`SnapshotSprites`）；每帧对被导出的实体比较这三项（`SpritesChanged`：每个精灵三次托管字段读取，无引擎调用），变了就在同一帧重建。另外，重建失败（异常）后不再等 600 帧的周期刷新，而是 30 帧后重试（`RetryFrame`）。`ents.stats` RPC 新增 `sprite_refreshes`、`refresh_failures`、`seen_hm`、`hidden_exports`。

修复前的录像（截至 2026-10-01 的所有 M2 录像）仍带着这个洞；`ents.py` 的说明里记了受影响的帧。

## 13. 每帧开销（纸面估计）

基线（`cost_us`，上一帧的 STATE 构建时间）：试跑 i0_000（单实例，26 892 个 STATE）p50 117 µs、p99 176 µs，`cost_ex` 中 `hero` 段 p50 18 µs，`ents` 24 µs，`room` 0 µs；实跑 i1_000（4 实例并行，273 201 个 STATE）p50 191 µs、p99 291 µs。预算 C14：p50 ≤ 300 µs、p99 ≤ 1 ms。

| 新增 | 每帧读取 | 估计 |
|---|---|---|
| `hero.tm` | 13 个 FieldRef 委托 + 2 个 public 字段 + `cState` 两个 bool + 1 次 `gravityScale`（引擎调用）；15 个键 | ~1-2 µs |
| `hero.alpha` / `wall` | 3 个 `Time` getter；2 个 public 字段 | < 0.5 µs |
| `hero.tags` | 1 个 FieldRef + 属性 + `Count`；有生效标签时再读 `Gameplay` 的 Barbed Wire 设置与 `IsEquipped`（同 `silk_max` 的读法，`SafeReads` 保护），每个标签一次字典枚举（名字按引用缓存） | ~0.1 µs（无标签） |
| `hero.tool_max` | 每个工具：`GetToolByName`（字典）+ `GetToolStorageAmount`（含 `IsEquippedHud` 的 `toolCache` 命中） | ~0.2 µs × 工具数 |
| `ents` | 每个实体每个 tk2d 精灵 3 次托管字段读；每个"见过且未导出"的 HealthManager 实体约 6 次引擎调用（hidden 判定）；多写 `hidden` 与碰撞体 `name` | < 1 µs（Bone_05） |
| `room.gates` | 每个被监视项约 5 次引擎调用（Bone_05 约 4 项；上限 32 项时约 13 µs）+ 轮询 16 × 3 次（表满时照常轮询，顶替只扫 32 项、不分配） | ~1-2 µs（Bone_05） |
| `menu` | 未暂停：`uiState`、`isPaused`、遮罩 alpha（1 次引擎调用），写 nil；暂停：再加选中项角色缓存查找、`interactable`、2 次 alpha | < 0.5 µs |
| `act.hf` | 44 次数组读，44 个小整数 | ~0.3 µs |
| 事件 `hit` | 只在命中时：前缀 2 次字段读，后缀构建字典与 2 次 `name` | 每秒几次 |

合计约 5-10 µs/帧，约为单实例基线 p50 的 5-8%；4 实例负载下 p50 约 200 µs、p99 约 300 µs，仍在预算内。STATE 增大约 0.3-0.5 KB/帧（`act.hf` ~70 B、`hero.tm` ~150 B、gates 每项 ~60 B、每个碰撞体名 ~10 B）。实测数字等新插件部署后从 STATE `cost_ex` 读取。
