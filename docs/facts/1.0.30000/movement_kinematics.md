# Forum 配装的运动学、Reaper 攻击判定与安全口袋工具（M2 W8，1.0.30000）

> 2026-10-02 起（开发代理 W）。范围：贴墙滑行 / 爬墙爪贴墙（Ascendant's Grip）/ 蹬墙跳 / 贴墙出刀、滑翔（Drifter's Cloak）、冲刺（Swift Step）与之后的 sprint FSM、Reaper 下劈与硬着陆进入运动学模型；Reaper 各攻击的伤害碰撞体多边形与生效时间做成数据；覆盖图 / 安全口袋工具。没有二段跳和 Silk Soar（你说"二段跳可能没有"：社区存档 High Halls 时刻 p7_s3 正是 hasDoubleJump = false、hasSuperJump = false，模型不含二段跳）。
>
> 代码：`brain/ssbot/knowledge/kin_jit.py`（"Forum loadout" 一节）、`kinematics.py`（`HeroParams.abilities` 与新参数、新状态行、`forum_mode`、`ForumRows`）、`knowledge/attack_shapes.py`、`tools/attack_table_build.py`、`tools/coverage_map.py`、`tools/kin_bench_forum.py`、`probes/room_scout.py`、`probes/kin_excite_forum.py`。数据：`knowledge/1.0.30000/attacks/{reaper,hunter}.json`。没有反编译文件名的行号都指 `HeroController.cs`。

## 1. 反编译与 FSM 模板得到的机制

FSM 来源：Hero_Hornet 预制体在 `heroloading_assets_all.bundle`，它的 PlayMakerFSM 都引用 `fsmtemplates_assets_shared.bundle` 里的模板（Umbrella Float → `hornet_umbrella_float`，Sprint → `hornet_sprint`，Crest Attacks → `crest_attacks`，Wall Scramble → `hornet_wall_scramble`）；用 UnityPy 读模板的状态、动作参数、转移（含 SendMessage 的函数名）。实例变量覆盖模板默认值（Sprint 实例：Sprint Speed Regular −17.5、Air Sprint Speed −12、Dash Speed −28；模板默认是 −20 / −12 / −28）。

### 1.1 贴墙（Cling Grip = hasWalljump）

- **触墙**：`OnCollisionStay2D`（11469）只在 hero_state ≠ no_input 时更新 `touchingWallL/R`：与任一地面层碰撞体有接触时，用 `CheckStillTouchingWall`（`WallTouchCache`：碰撞盒左 / 右边的中点和底点各一条 0.1 u 射线；不看顶点）判断；完全没有接触时由 `OnCollisionExit2D` 清掉。模型：贴墙接触 = 墙面离碰撞盒侧面不超过 skin + 0.01 u，或站在地上；再用 0.1 u 射线判左右。
- **开始滑墙**（`LookForInput` 8397 → `BeginWallSlide` 8461）：能输入、未被夺控、触墙、`CanStartWithWallSlide`（不在地上、`falling`（FallCheck：vy ≤ ε 且不贴地）或已在滑、不在攻击或在墙砍、不是非滑墙、`IsFacingNearSlideableWall`：从 hero.pos 沿朝向 0.6 u 射线打到墙，并且上下每隔 0.1 u 的射线连续命中合计 ≥ 1.5 u），并且**按住朝墙方向**。开始时：朝向墙、CancelJump（也解除蹬墙锁）、取消冲刺、airDashed = false、重力关（保存原重力倍数）、冲刺冷却清零。
- **滑墙速度**（`LateUpdate` 3869，每个渲染帧）：贴墙抓住时 vy 下限 −10，vy < 0 时每帧 +80·dt，vy > 0 时置 0；否则前 `WALLSLIDE_STICK_TIME` 0.15 s vy = 0（"粘住"），之后每帧 vy += −24·dt。滑墙中 `Move` 不用输入设 vx，不转身；`FixedUpdate` 的空中悬停仍会在第一次 vy < 0 时把重力倍数设成 0.1（`didAirHang` 未置位时），滑墙中重力倍数不回升。
- **离开**：Update（2198）落地、不再触墙 → 翻转朝向并取消；`CanContinueWallSlide` 不成立（被夺控、朝向不再对着墙等）→ 取消；FixedUpdate（3140）只按背离墙方向连续 `WALL_STICKY_STEPS` 3 步 → 翻转并取消；墙射线不再命中 → 翻转并取消；按下（且没按朝墙）→ 取消并翻转。
- **爬墙爪贴墙**（2229-2263）：滑墙中每帧 `wallClinging = 不在禁贴区 && wallClingCooldownTimer ≤ 0 && Gameplay.WallClingTool 已装备 && 按住朝墙方向`；贴住时重力关；从贴住变成没贴住时冷却 `WALLCLING_COOLDOWN` 0.3 s（所以松开方向键后 0.3 s 内重新按住不会立刻再贴住，只是滑）。工具名 `Wallcling`（crests.json gameplay.wallClingTool）。
- **蹬墙跳**（`DoWallJump` 8855）：在滑墙中或（触墙、在空中且 `CanChainWallJumps`：仍在锁定、连跳窗口 `wallJumpChainStepsLeft` > 0、或有水平输入）时按跳。背向墙，`currentWalljumpSpeed` = `WJ_KICKOFF_SPEED` 25，每步减 (25 − 8.25) / 15，锁定期间每个 FixedUpdate 把 vx 设成 ±速度，`WJLOCK_STEPS_LONG` 15 步后解锁并开 10 步连跳窗口；`cState.jumping` = true、`jumped_steps` = 5，所以松跳会立刻把 vy 减半并 CancelJump（同时解锁）；`Jump()` 在 jump_steps 超过 8 时 CancelJump，也解锁——满按住的蹬墙跳实际锁 10 步左右。锁定 5 步后按回墙方向解锁（8407-8414）。按跳太早（离墙 1 u 内、面对墙、可连跳）会排队 `queuedWallJumpInterrupt`，下一帧自动蹬墙跳。
- **墙上出刀**（`Attack` 4125）：滑墙中横砍 = 墙砍（WallSlash，打向背离墙的一侧），Reaper 配置 `WallSlashSlowdown` = true：vy 减半、不低于 −5；墙砍期间继续滑墙（`!attacking || wallSlashing`）。上砍：`MovePosition` 离墙 0.8 u，再翻转并取消滑墙。下砍：翻转并取消滑墙后照常下劈。

### 1.2 滑翔（Drifter's Cloak = hasBrolly，Umbrella Float FSM）

- 在空中按跳且不能蹬墙跳、不能跳、没有二段跳时，`CanFloat`（11069：不在地上、不在冲刺锁定、`ledgeBufferSteps` 用完、不在滑墙、不在攻击硬直、不能排队蹬墙跳、`IsApproachingSolidGround` 不成立：vy > 0 或碰撞盒两个底角下方 1.1 u 内不都有地）→ FSM "FLOAT"。冷却状态中（结束后 0.1 s）FLOAT 被忽略，这次按跳也就没了。
- Take Control：`RelinquishControlNotVelocity`（hero_state no_input，重力倍数复位为 1，取消跳跃 / 滑墙 / 冲刺）。Antic（动画 "Umbrella Inflate Antic"）：重力照常，UmbrellaMotionX（加速 8.5 / 减速 0.25 / 上限 8.5，每个物理步按方向键改 vx）。Inflate（"Umbrella Inflate"）：重力关；每步若 vy < 0.05 则 vy = 0.5；UmbrellaMotionX(1, 0.25, 8.5)。Start：vy = 0.5。Float Idle（"Umbrella Float"）：每步 vy 以 0.13 向 −6 逼近；UmbrellaMotionX(1, 0.25, 8.5)；**松开跳**（`ListenForJump` isNotPressed）→ Deflate（"Umbrella Deflate"，重力恢复，不再控制 x）→ 交还控制。任何阶段落地（下侧碰撞）→ 交还控制。Inflate 0.075 s 后 / Float Idle / Deflate 中按攻击或冲刺 → 交还控制并执行该动作。左右 0.7 u 射线碰到墙：有 Cling Grip 且按住朝墙 → 交还控制并从那里开始滑墙；否则被推开（vx = ±6，碰左墙时 vy 至多 −0.5）。
- 各阶段长度由动画片段决定（模型参数 `glide_antic_t` / `glide_inflate_t` / `glide_deflate_t`，待实测）。

### 1.3 冲刺（Swift Step = hasDash）与 sprint FSM

- `HeroDash`（9058）：地面 `dash_timer` = `DASH_TIME` 0.1 s，空中 `AIR_DASH_TIME` 0.02 s（一步）并记 airDashed；滑墙中冲刺先翻转（背离墙）；否则按方向键定朝向；`DASH_COOLDOWN` 0.425 s；冲刺键排队 10 步。`Dash()`（4334）：每步若可滑墙则开始滑墙并结束；重力关；vx = ±`DASH_SPEED` 28，vy = 0；计时减 0.02。注意 FixedUpdate 后段的空中悬停逻辑在不按跳时会把重力倍数立刻恢复为 1，所以每步仍有一次重力积分（−1.2 u/s）。
- `FinishedDashing` → sprint FSM：Start Sprint（重力倍数 1，夺控）→ 地面：vx = 28 → 地面 sprint（每步 AccelerateToX 1.1 向 17.5）；空中：Air Sprint（0.235 s，AccelerateToX 1.1 向 12，vy 下限从 −10 线性放宽到 −30（EaseFloat easeType 21 = linear，1 s））→ Air Sprint Loop（直到冲刺键松开、撞墙或落地；落地仍按着冲刺 → 地面 sprint）。所以空中冲刺即便是点按，也有约 0.235 s 的"空中 sprint"，水平约 5 u。
- 未建模（模型里这些按键不做事，规划器不应选）：滑墙中朝墙按冲刺 = 爬墙（Wall Scramble FSM）、下冲（按下 + 冲刺）、地面 sprint 松键后的 skid 细节（参数 `skid_*` 暂定，待实测）、sprint 中跳跃的特殊跳（按普通跳近似）。

### 1.4 Reaper 下劈（Crest Attacks FSM "RPR DOWNSLASH"）

- `DownSlashType` = Custom：`Attack` 先设 attacking 并 `DidAttack`（冷却 0.5 s），FSM：Rpr Downslash Antic（"v3 Down Slash Antic"）：夺控、重力关、每步 vx、vy ×0.85（DecelerateV2）再 vy ×0.8，UmbrellaMotionX(3, 1, 12)；Rpr Downslash（"v3 Down Slash"）：v = 0 后 `SetVelocityByScale` → vx = 朝向 × 30、vy = −30，每步 ×0.7；动画触发帧后 Fall（重力恢复）→ Fall 2 → End（交还控制，`FinishDownspike`：下劈恢复期）。命中 → Bounce（`SetStartWithDownSpikeBounce`，交还控制后弹起）；Fall 中按冲刺 → 取消。
- HeroBox 在下劈中是 `HeroBoxReaperDownSlash`（0.4554 × 1.601，偏移 (0.37, 0.632)）。

### 1.5 硬着陆

`FallCheck`（9730）：下落中、未夺控（或在 sprint）、vy ≤ −`MAX_FALL_VELOCITY`（30）且不在滑墙时累计 fallTimer，超过 `BIG_FALL_TIME` 0.5 s → willHardLand；着地时 `DoHardLanding` → hero_state hard_landing 0.67 s，每步速度清零。Bell Beast 场地落差不够，Hunter 模型没有它；Forum 从墙顶掉下来可能触发，所以 Forum 参数里打开（`AB_HARD_LAND`）。

## 2. 模型实现

- `HeroParams.abilities` 位掩码（`AB_WALL`、`AB_CLING`、`AB_DASH`、`AB_BROLLY`、`AB_RPR_DOWN`、`AB_WALLSLASH_SLOW`、`AB_HARD_LAND`）；为 0 时新规则一条也不走，Hunter 的 rollout 逐位不变（kinematics + knockback 原有 47 个测试全部通过，含 numba 与 NumPy 参考逐位相同、跟踪器与 state_table 逐行相同）。
- 新增 21 个状态行（`WSIDE`、`WTOUCH`、`CLING`、`CLING_CD`、`WSTICK`、`UNSTICK`、`WLOCK`、`WJ_DIR`、`WJ_V`、`WJ_CHAIN`、`WJQ`、`WSLASH`、`PREV_GS`、`GL_CD`、`DASH_T`、`DASH_CD`、`AIRDASHED`、`DQ`、`FALL_T`、`HARD`、`SP_X`），5 个新模式（`M_GLIDE`、`M_DASH`、`M_SPRINT`、`M_RPR_DS`、`M_HARD_LAND`），59 个新参数（反编译常量、FSM 动作参数、待测的动画长度）。
- 新规则只写了一份：`kin_jit` 的标量代码（NumPy 参考只覆盖 Hunter 规则；`backend="numpy"` 配 abilities ≠ 0 会报错）。FSM 动作（UmbrellaMotionX、AccelerateToX/Y、DecelerateV2/XY、SetVelocity2dConditional）按物理步执行，读的是上一帧的输入（FixedUpdate 在本帧输入更新之前）；动画定时的 FSM 状态用"进入后下一帧起累计的缩放时间"判断结束（同丝矛阶段）。
- 估计器：`classify_modes(tr, forum=True)` / `StateTracker`（abilities ≠ 0 时）用 `forum_mode` 从 cstate（dashing、isSprinting）、hero_state（no_input、hard_landing）和动画片段（`GLIDE_CLIPS`、`SPRINT_CLIPS`、`RPR_CLIPS`）判模式；`ForumRows` 从 wallSliding / wallClinging / hero.wall / 片段 / hero.tm 推新状态行，state_table 与跟踪器共用同一个逐帧函数。`Trace` 新增 `wall`（hero.wall），`_CS_USED` 末尾追加 6 个 cstate 名（旧的 Trace 存档少这几列，`flag()` 读作 False）。

## 3. Reaper 攻击判定（数据）

`knowledge/1.0.30000/attacks/reaper.json`（`tools/attack_table_build` 从 crests.json P17 的 slash.dump 生成，坐标：沿朝向向前为 +x、向上为 +y、相对英雄碰撞盒中心；NailSlash 用挥刀时的缩放 `shapes_swing`，Downspike 组件用当前缩放——Hunter 下劈的当前缩放多边形正是实战 240/241 命中的那个）：

| 槽 | 命中事件 src | 生效（动画事件） | x 范围 | y 范围 |
|---|---|---|---|---|
| normal（横砍） | Slash | 2/24–5/24 s（0.083–0.208） | −0.25 … +3.60 | −0.42 … +2.69 |
| alt（第二刀） | AltSlash | 0.083–0.208 s | +0.11 … +3.67 | −1.00 … +1.02 |
| up（上砍） | UpSlash | 2/24–6/24 s（0.083–0.250） | −2.12 … +0.81 | −0.63 … +3.77 |
| wall（墙砍） | WallSlash | 0.083–0.208 s | −3.94 … −0.15（背向墙） | −0.32 … +2.73 |
| down（下劈，FSM） | DownSlash | 未测（片段 4 帧 24 fps） | −1.80 … +2.26 | −2.61 … +1.81 |
| dash_stab / charge / taunt | … | 未测 | | |

Reaper 配置（crests.json table.configs）：攻击持续 0.35 s、冷却 0.5 s、硬直 0.3 s（Hunter 0.35 / 0.41 / 0.15）。命中后坐：`RECOIL_HOR_VELOCITY` 3.75 × 8 步（与 Hunter 同一路径，长后坐只在 RecoilLeftLong 等调用时）。逐帧实测（slash.dump 每帧采样）与命中核对见第 5 节。

## 4. 覆盖图 / 安全口袋工具

`tools/coverage_map.py`：录像中每帧敌人的伤害碰撞体（`ents.is_threat`）按（type_key, Control 状态）栅格化（默认 0.05 u）求并集；候选英雄姿态 = 每段地面上的站立点 + 每面能贴的墙（`facing_near_wall` 通过）从底到"碰撞盒中心到墙顶"的贴墙点，各配自己的 HeroBox（HeroBox.cs：普通 0.4554 × 2.2498 偏移 (0, −0.38)；滑墙 0.876 × 1.280 偏移 (0.21, −0.276)，x 随朝向镜像，背离墙一侧更宽）；输出每点与每个招式并集的间隙（负数 = 重叠）、最近的招式、安全点（间隙 ≥ --margin）、每面墙最高贴墙点的间隙，可选 PNG。
Bell Beast 试用（20261002_171806，4 实例各 4 场，55 580 帧，40 组）：11 s。左门内侧墙（x 69.21，英雄在门右侧）最高贴墙点 y 13.29 间隙 1.91 u（最近：DropBell L Bounce Air）；右门内侧（x 102.0）最高点间隙 0.34 u（DropBell R Air）。即：有爬墙爪的话，Bell Beast 场地左门顶是有 1.9 u 余量的口袋（按已记录的招式）。

## 5. 实测（待补）

## 6. 性能

`tools/kin_bench_forum`（512 × 48，threads 4，随机按键含跳 / 冲刺 / 滑翔 / 下劈，起点贴墙附近；实例 0-3 跑门槛评估时，CPU 负载 60-75 %）：Forum 参数 nominal p50 1.95 / p99 2.49 ms；同样输入 Hunter 参数 0.99 / 1.94 ms。"bounds" 9 条时序分支：Forum p50 8.3 / p99 12.4 ms，Hunter 3.1 / 4.3 ms（优化前测）。
