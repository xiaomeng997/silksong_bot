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
- **Inflate 的速度**：SetVelocity2dConditional 的 vector 是常量 (0, 0)（不是 None），所以它每步从 (0, 0) 出发、y 条件 0 < 0.05 成立 → 每步 v = (0, 0.5)；英雄带 `UmbrellaWindObject`，UmbrellaMotionX 改的是它的"自身 x 速度"（再由它写回刚体），Inflate 进入时这个速度从 0 开始：实测 vx 0（进入帧）、−2、−3 … −8.5（每步 ±1）。Antic 的 UmbrellaMotionX(8.5) 进入时就把自身速度拉满，刚体从下一步才显示。
- 各阶段长度（实测，见 5）：Antic 5/6 帧、Inflate 12 帧、Deflate 5/6 帧。
- 落地 / Deflate 结束交还控制时，若 0.1 s 内按过跳（InputHandler 的跳键队列，见 1.3）且能跳 → 立刻起跳（实测：离地很近时按下的滑翔在 Antic 中落地，按住的跳键让她当帧跳起）。

### 1.3 冲刺（Swift Step = hasDash）与 sprint FSM

- `HeroDash`（9058）：地面 `dash_timer` = `DASH_TIME` 0.1 s，空中 `AIR_DASH_TIME` 0.02 s（一步）并记 airDashed；滑墙中冲刺先翻转（背离墙）；否则按方向键定朝向；`DASH_COOLDOWN` 0.425 s；冲刺键排队 10 步。`Dash()`（4334）：每步若可滑墙则开始滑墙并结束；重力关；vx = ±`DASH_SPEED` 28，vy = 0；计时减 0.02。注意 FixedUpdate 后段的空中悬停逻辑在不按跳时会把重力倍数立刻恢复为 1，所以每步仍有一次重力积分（−1.2 u/s）。
- `FinishedDashing` → sprint FSM：Start Sprint（重力倍数 1，夺控）→ 地面：vx = 28 → 地面 sprint（每步 AccelerateToX 1.1 向 17.5）；空中：Air Sprint（0.235 s，AccelerateToX 1.1 向 12，vy 下限从 −10 线性放宽到 −30（EaseFloat easeType 21 = linear，1 s））→ Air Sprint Loop（直到冲刺键松开、撞墙或落地；落地仍按着冲刺 → 地面 sprint）。所以空中冲刺即便是点按，也有约 0.235 s 的"空中 sprint"，水平约 5 u。
- **冲刺结束那一步**（实测 C / D）：Dash() 发现计时到了只调 FinishedDashing、不改速度；sprint FSM 在同一个 FixedUpdate 里进 Air / Ground Sprint，其 AccelerateToX OnEnter 已经作用（28 → 26.9，这一步就按 26.9 移动）。冲刺步数：地面 0.1 s、空中 0.02 s 用 float32 每步减 0.02 留下 3.7e-9 的余数，所以地面 6 步、空中 2 步。
- **Ground Sprint R / L OnEnter 的 Translate 0.05 u（朝前）**：从**绘制位置**（上一帧的插值位置）平移，刚体跟过去，然后这一步再积分——25 次松键地面冲刺里 24 次用记录的 alpha 反推平移量正好 0.05（剩下一次 alpha 0.048 是读数绕回）。模型新增状态行 RX0 / RY0 记录每帧开始时的绘制位置（只在有 abilities 时写）。空中冲刺落地转地面 sprint（LAND 来自落地那步的碰撞回调）时变换就在刚体处：平移从刚体位置算（实测落地帧移动 = 17.0 × 0.02 + 0.05）。
- **地面 sprint 松开冲刺键**：Sprint Timer（地面 sprint 中按帧累计）< Sprint Grace 0.3 s 或速度 < 4 → 不打滑，Regain Control To Idle（下一步按输入走：无输入则 vx = 0）；否则 Skid End 1 / 2（片段 0.2 + 0.05 s，DecelerateXY 0.85，朝面向方向按着方向键时 0.95）。
- Air Sprint 的下落速度下限（EaseFloat −10 → −30，1 s）比状态时间晚一帧（实测 −15.20，状态时间算出 −15.53，C / D 每次都是）。
- **InputHandler 的跳键队列**：每次按跳（WasPressed）设 0.1 s（非缩放时间）计时；RegainControl 的普通分支（不是 startWithWallslide 等）若能跳就消费它起跳。模型新增状态行 JBUF。
- 未建模（模型里这些按键不做事，规划器不应选）：滑墙中朝墙按冲刺 = 爬墙（Wall Scramble FSM）、下冲（按下 + 冲刺）、sprint 中跳跃的特殊跳（按普通跳近似）、Sprint Turn。

### 1.4 Reaper 下劈（Crest Attacks FSM "RPR DOWNSLASH"）

- `DownSlashType` = Custom：`Attack` 先设 attacking 并 `DidAttack`（冷却 0.5 s），FSM：Rpr Downslash Antic（"v3 Down Slash Antic"）：夺控、重力关、进入时和每步 vx、vy ×0.85（DecelerateV2）。**模板里同一状态的 DecelerateXY（y ×0.8）和 UmbrellaMotionX 是禁用的**（ActionData.actionEnabled = false，见 1.6）：实测进入帧（无物理步）vy 就 ×0.85，此后每步只 ×0.85；Rpr Downslash（"v3 Down Slash"）：v = 0 后 `SetVelocityByScale` → vx = 朝向 × 30、vy = −30，每步 ×0.7；动画触发帧后 Fall（重力恢复）→ Fall 2 → End（交还控制，`FinishDownspike`：下劈恢复期）。命中 → Bounce（`SetStartWithDownSpikeBounce`，交还控制后弹起）；Fall 中按冲刺 → 取消。
- HeroBox 在下劈中是 `HeroBoxReaperDownSlash`（0.4554 × 1.601，偏移 (0.37, 0.632)）。
- **地形撞击（thunk）**：下劈判定体上的 `NailSlashTerrainThunk` 碰到地面层（8）且接触点在 hero.pos 下方 → `THUNKED DOWN` → Rpr Downslash Thunk：DecelerateV2 0.715（进入时一次 + 每步；该状态的 SetVelocity2d y 28 被禁用，所以不弹起），同一个动画触发帧结束进入 Fall。撞击那一步的速度比 = 0.7 × 0.715 ≈ 0.50（实测）。触发条件实测：28 次下劈逐步看"碰撞盒中心离下方地面的高度"，前 4 帧（MODE_T < 0.058 s）高度 ≤ 2.18 u 撞、≥ 2.19 不撞，之后 ≤ 2.33 撞（下劈特效动画的判定体随帧变大）；贴着墙的下劈（墙在身后 0.27 u）离地高时从不撞——墙不触发。模型：`rpr_thunk` 判断前方 0.5–2.2 u 内的地面段，阶段 4 = Thunk。
- FinishDownspike（End）：`vy = −10`、ResetGravity、RegainControl（实测交还控制那帧 vy 正好 −10）。
- 下劈的伤害对象是 FSM 用 FindChild 找到的 `Attacks/Scythe/DownSlash New`，命中事件 src = "DownSlash New"（Bell Beast 实测 18 次全是它）；slash.dump 的 down 槽给的是配置组的 `DownSlash` 对象，不是它（见 3）。

### 1.4b 爬墙（Wall Scramble FSM，hornet_wall_scramble）与翻越（Mantle）

- 滑墙中**按住朝墙方向再按冲刺**（`HeroDashPressed` → `CanWallScramble`：在滑墙、有 Cling Grip、能控制、按着朝墙方向）不是冲刺而是爬墙：Take Control（夺控，滑墙结束）→ Scramble Antic（片段 "Wall Scramble Antic"，速度清零、重力关、y 每步 ×0.85）→ Start Scramble（vy = 22，Quickening 时 30）→ Scramble Up（每步 AddForce2d 向下 72，冲刺键仍按着时 48；英雄刚体质量 1（预制体 Rigidbody2D m_Mass）；AddForce2d 的 OnEnter 也加一次力，所以第一步是两份（实测 −1.92 = 2 × 0.96 占 74/83，−2.88 是那帧有两步）；Scramble Antic 的 DecelerateXY 被禁用（只有 SetVelocity 0）；vy < 0.5 → Scramble End；按跳 → 蹬墙跳；不再面对可滑的墙（到顶）→ Mantle 翻越）→ Scramble End（片段 "Wall Scramble End"，y 每步 ×0.8；再按冲刺（松开过、按着朝墙）→ 再爬一次）→ 回到滑墙。Scramble End：DecelerateXY 0.8 进入时一次 + 每步，brakeOnExit（离开时 vy = 0）。**撞顶（Hit Roof）**：Scramble Up / End 里每步 `HeroCheckForBumpVertical`（CharacterBumpCheck 顶边射线：从碰撞盒顶下 0.1 u、离朝向侧边 0.2 u 处向上 0.1 + 0.03 + |vy|·0.02 u）碰到天花板 → Hit Roof（发生在 FixedUpdate，这一步就恢复重力且这一步的向下力照算：实测 8.56 → 5.92 = −1.44 − 1.2）→ Hit Roof Soft（播 End 片段）→ Detach：Transform.Translate x 0.2 u 离墙（从**绘制位置**平移，刚体随之：实测这一帧 y 也跳到插值高度 +0.01）→ 交还控制（不贴墙，重力开），之后按住朝墙会重新贴上。kn_forum_wall 的墙顶（y ≈ 25.99）就在天花板下，这条路线和 Forum 左墙顶"墙顶紧贴天花板台阶"相同。一次爬升约 22² / (2 × 72) ≈ 3.4 u（按住冲刺 ≈ 5.0 u）。这是爬上高墙（Forum 左墙顶）的方法。模型已加入（`M_SCRAMBLE`，片段长度 `scr_antic_t` / `scr_end_t` 待测）；Mantle FSM 未建模（到顶时模型只是交还控制）。
- 空中翻越（Update 2558）：不在滑墙、在空中、vy < 5、按着朝墙方向、碰撞盒中部或底部射线碰墙等条件下发 "AIR MANTLE"，Mantle FSM 把英雄翻上墙沿。贴墙 / 滑墙中不会触发；从墙顶附近跳向墙沿时会。未建模：靠近墙沿的计划要以实测为准。

### 1.6 模板里被禁用的动作

FSM 模板每个状态的 ActionData 有 `actionEnabled` 数组；之前的转储没读它。读出来（UnityPy，`fsmtemplates_assets_shared.bundle`）与本配装有关的禁用动作：crest_attacks 的 Rpr Downslash Antic（DecelerateXY、UmbrellaMotionX）、Rpr Downslash Thunk（SetVelocity2d）；hornet_wall_scramble 的 Scramble Antic（DecelerateXY）、Scramble End 和 Mantle Antic（各一个 RayCast2dV2）、Mantle Shift（Translate）、Hit Roof（SendEventByNameV2）；hornet_sprint 的 Wallrun Antic（SetGravity2dScale）、Restart Sprint（SetVelocityByScale）、Attack Antic（SetVelocity2d）等；hornet_umbrella_float 的 Inflate（SetHeroCState）。模型按启用的动作写。

### 1.5 硬着陆

`FallCheck`（9730）：下落中、未夺控（或在 sprint）、vy ≤ −`MAX_FALL_VELOCITY`（30）且不在滑墙时累计 fallTimer，超过 `BIG_FALL_TIME` 0.5 s → willHardLand；着地时 `DoHardLanding` → hero_state hard_landing 0.67 s，每步速度清零。Bell Beast 场地落差不够，Hunter 模型没有它；Forum 从墙顶掉下来可能触发，所以 Forum 参数里打开（`AB_HARD_LAND`）。

## 2. 模型实现

- `HeroParams.abilities` 位掩码（`AB_WALL`、`AB_CLING`、`AB_DASH`、`AB_BROLLY`、`AB_RPR_DOWN`、`AB_WALLSLASH_SLOW`、`AB_HARD_LAND`）；为 0 时新规则一条也不走，Hunter 的 rollout 逐位不变（kinematics + knockback 原有 47 个测试全部通过，含 numba 与 NumPy 参考逐位相同、跟踪器与 state_table 逐行相同）。
- 新增 21 个状态行（`WSIDE`、`WTOUCH`、`CLING`、`CLING_CD`、`WSTICK`、`UNSTICK`、`WLOCK`、`WJ_DIR`、`WJ_V`、`WJ_CHAIN`、`WJQ`、`WSLASH`、`PREV_GS`、`GL_CD`、`DASH_T`、`DASH_CD`、`AIRDASHED`、`DQ`、`FALL_T`、`HARD`、`SP_X`），5 个新模式（`M_GLIDE`、`M_DASH`、`M_SPRINT`、`M_RPR_DS`、`M_HARD_LAND`），59 个新参数（反编译常量、FSM 动作参数、待测的动画长度）。
- 新规则只写了一份：`kin_jit` 的标量代码（NumPy 参考只覆盖 Hunter 规则；`backend="numpy"` 配 abilities ≠ 0 会报错）。FSM 动作（UmbrellaMotionX、AccelerateToX/Y、DecelerateV2/XY、SetVelocity2dConditional）按物理步执行，读的是上一帧的输入（FixedUpdate 在本帧输入更新之前）；动画定时的 FSM 状态用"进入后下一帧起累计的缩放时间"判断结束（同丝矛阶段）。
- 2026-10-03 补：状态行再加 `WCON`、`SHOVE`（上砍离墙的 MovePosition 待下一物理步执行：那一步按偏移 + 重力份额移动、速度保持原值，实测 x −0.8、y −g·fdt²、vy 仍 0）、`RX0` / `RY0`（每帧开始时的绘制位置，FSM 的 Transform.Translate 从这里平移）、`JBUF`（InputHandler 跳键队列 0.1 s）；模式 `M_SCRAMBLE`；阶段：Reaper 下劈 4 = Thunk，爬墙 3 = Hit Roof Soft。参数共 81 个新项（含 `scr_roof_*`、`rpr_thunk_*`、`sprint_shift` / `sprint_grace` / `skid_*`、`air_fall_clamp_lag`）。拟合值在 `knowledge/1.0.30000/kinematics/hero_reaper_forum.json`（`tools/kin_fit_forum`，见 5）。
- 估计器：`classify_modes(tr, forum=True)` / `StateTracker`（abilities ≠ 0 时）用 `forum_mode` 从 cstate（dashing、isSprinting）、hero_state（no_input、hard_landing）和动画片段（`GLIDE_CLIPS`、`SPRINT_CLIPS`、`RPR_CLIPS`）判模式；`ForumRows` 从 wallSliding / wallClinging / hero.wall / 片段 / hero.tm 推新状态行，state_table 与跟踪器共用同一个逐帧函数。`Trace` 新增 `wall`（hero.wall），`_CS_USED` 末尾追加 6 个 cstate 名（旧的 Trace 存档少这几列，`flag()` 读作 False）。估计器补的细节（都来自 B / D 的失败窗口）：wallSlashing（滑墙中横砍到攻击结束）；蹬墙锁在按回墙方向且锁满 5 步时解除；空中悬停用这一步开始时的速度（滑墙在 LateUpdate 改 vy，悬停晚一步；只对 Forum，Hunter 不变）；墙接触位由地形几何补（OnCollisionEnter 那一步 hero.wall 还是 0）；FSM 在 FixedUpdate 进入的阶段（撞顶、冲刺结束进 sprint）进入帧就开始计时；OnEnter 的速度改动（爬墙的第一份力、滑翔各阶段的 UmbrellaMotionX、Thunk）在下一物理步前保持"待生效"；滑翔按下的跳不进跳键队列。

## 3. Reaper 攻击判定（数据）

`knowledge/1.0.30000/attacks/reaper.json`（`tools/attack_table_build` 从 crests.json P17 的 slash.dump 生成，坐标：沿朝向向前为 +x、向上为 +y、相对英雄碰撞盒中心；NailSlash 用挥刀时的缩放 `shapes_swing`，Downspike 组件用当前缩放——Hunter 下劈的当前缩放多边形正是实战 240/241 命中的那个）：

| 槽 | 命中事件 src | 生效（动画事件） | x 范围 | y 范围 |
|---|---|---|---|---|
| normal（横砍） | Slash | 2/24–5/24 s（0.083–0.208） | −0.25 … +3.60 | −0.42 … +2.69 |
| alt（第二刀） | AltSlash | 0.083–0.208 s | +0.11 … +3.67 | −1.00 … +1.02 |
| up（上砍） | UpSlash | 2/24–6/24 s（0.083–0.250） | −2.12 … +0.81 | −0.63 … +3.77 |
| wall（墙砍） | WallSlash | 0.083–0.208 s | −3.94 … −0.15（背向墙） | −0.32 … +2.73 |
| down（下劈，FSM） | DownSlash | 未测（片段 4 帧 24 fps） | −1.80 … +2.26 | −2.61 … +1.81 |
| dash_stab / charge / taunt | … | 未测（见 5.4） | | |

Reaper 配置（crests.json table.configs）：攻击持续 0.35 s、冷却 0.5 s、硬直 0.3 s（Hunter 0.35 / 0.41 / 0.15）。命中后坐：`RECOIL_HOR_VELOCITY` 3.75 × 8 步（与 Hunter 同一路径，长后坐只在 RecoilLeftLong 等调用时）。逐帧实测（slash.dump 每帧采样）与命中核对见第 5 节。

### 3.1 英雄受伤判定框（HeroBox）与碰撞盒不是一回事

Hero_Hornet 预制体（heroloading_assets_all.bundle，UnityPy 读取）：碰撞盒 BoxCollider2D 偏移 (0, −0.5132)、尺寸 0.5 × 2.0789（即 hero.box：transform 下方 1.5527、上方 0.5262）；子物体 HeroBox 在 transform 原点（局部 (0, 0)），触发器 BoxCollider2D，尺寸随状态由 `HeroBox.cs` 改写：正常（`HeroBoxNormal`，进入 idle / running / airborne / grounded 时设置）偏移 (0, −0.3799)、0.4554 × 2.2498，即 transform 下方 1.505、上方 0.745——**比碰撞盒高出 0.22 u（头顶），两侧各窄 0.045 u**；滑墙 / 贴墙（`HeroBoxWallSlide`）偏移 (0.2101, −0.2755)、0.8757 × 1.2805（局部 +x 是朝左时的前方：贴左墙时向右偏，背离墙一侧伸出 0.65 u）；下劈 0.4554 × 1.218；Reaper 下劈 偏移 (0.37, 0.632)、0.4554 × 1.601；sprint、空中冲刺、招架姿态等各有一套（HeroBox.cs 166-273 行）。规划器和预测器至今用碰撞盒加余量判接触；头顶 0.22 u 的差靠余量吸收（余量小于 0.22 u 的检查会漏掉擦头顶的命中）。覆盖图工具用 HeroBox。

## 4. 覆盖图 / 安全口袋工具

`tools/coverage_map.py`：录像中每帧敌人的伤害碰撞体（`ents.is_threat`）按（type_key, Control 状态）栅格化（默认 0.05 u）求并集；候选英雄姿态 = 每段地面上的站立点 + 每面能贴的墙（`facing_near_wall` 通过）从底到"碰撞盒中心到墙顶"的贴墙点，各配自己的 HeroBox（HeroBox.cs：普通 0.4554 × 2.2498 偏移 (0, −0.38)；滑墙 0.876 × 1.280 偏移 (0.21, −0.276)，x 随朝向镜像，背离墙一侧更宽）；输出每点与每个招式并集的间隙（负数 = 重叠）、最近的招式、安全点（间隙 ≥ --margin）、每面墙最高贴墙点的间隙，可选 PNG。
Bell Beast 试用（20261002_171806，4 实例各 4 场，55 580 帧，40 组）：11 s。左门内侧墙（x 69.21，英雄在门右侧）最高贴墙点 y 13.29 间隙 1.91 u（最近：DropBell L Bounce Air）；右门内侧（x 102.0）最高点间隙 0.34 u（DropBell R Air）。即：有爬墙爪的话，Bell Beast 场地左门顶是有 1.9 u 余量的口袋（按已记录的招式）。

## 5. 实测

### 5.1 激励录像（实例 3，2026-10-02 晚，CPU 30–65 %：其余实例和代理在跑）

| 名称 | 录像（C:\ssbot\data\runs\m2\kn_excite_forum\2026-10-02\TRAIN\…） | 存档 | 种子 / 次数 | 用途 |
uns\m2\kn_excite_forum6-10-02\TRAIN\…） | 存档 | 种子 / 次数 | 用途 |
|---|---|---|---|---|
| s98000 | kn_excite_forum_s98000 | kn_forum_wall | 98000，125（中途停） | 拟合 |
| A | kn_excite_forum_s98010 | kn_forum_wall | 98010，170 + 40 次逐帧攻击采样 | 拟合、攻击帧 |
| B | kn_excite_forum_s98100 | kn_forum_wall | 98100，120 | 留出（墙） |
| C | kn_excite_forum_s98200 | kn_forum_floor | 98200，160（滑翔、冲刺、Reaper） | 拟合 |
| D | kn_excite_forum_s98300 | kn_forum_floor | 98300，100 | 留出（地面） |

帧时间：这些录像的帧并不是"每帧 0.01665 s"（前一节说法有误），而是 0.01665 / 0.016682 / 0.016667 轮换（记录的 hero.alpha 每帧正好走 dt / 0.02）。

### 5.2 拟合（`tools/kin_fit_forum` on s98000 + A + C → hero_reaper_forum.json）

阶段长度 L（进入那帧到结束那帧的帧数）；单一 L 取区间中点，相邻两个 L 都出现（帧时间抖动决定）取分界 + 0.4 × timer_bias 偏向多数，让 ±timer_bias 的时序分支两边都覆盖：

| 参数 | 观测 L（次数） | 值 (s) |
|---|---|---|
| rpr_antic_t | 9 (11)、10 (38) | 0.1502 |
| rpr_slash_t（x 速度 ×0.7 衰减停止的触发帧） | 10 (3)、11 (33) | 0.1669 |
| rpr_fall_t（到 FinishDownspike 交还控制，Fall 2 占最后一帧） | 9 (3)、10 (33) | 0.1502 |
| scr_antic_t | 4 (83) | 0.0583 |
| scr_end_t | 4 (9)、5 (47) | 0.0669 |
| scr_roof_t（FixedUpdate 进入，偏一帧） | 5 (4)、6 (16) | 0.1002 |
| glide_antic_t | 5 (5)、6 (23) | 0.0835 |
| glide_inflate_t | 12 (28) | 0.1917 |
| glide_deflate_t | 5 (3)、6 (9) | 0.0835 |

对照（反编译值，不拟合）：贴墙爪贴住时 vy 恒 0（15 645 帧）；滑墙粘住期过后每帧 vy 变化 −24 /s（p50，p5 −31.2：有空中悬停重力 0.1 的帧）；冲刺 |vx| 28；滑翔 Float Idle vy 向 −6 逼近；爬墙第一步 −1.92（74 次）/ −2.88（9 次，那帧两步）。动画片段（UnityPy 读 herodynamic / herocollections 包）：Wall Scramble Antic / End 1 帧 @12 fps（0.083 s）、Umbrella Inflate Antic 0.1 s、Inflate 0.1875 s、Deflate 0.1 s、Skid End 1 0.2 s、Skid End 2 0.05 s、Sprint Air 0.294 s。

### 5.3 留出验收（`tools/kin_check B D --params hero_reaper_forum.json`，0.5 s = 30 帧，容差 0.1 u）

决策时信息（历史估计状态，名义 / 抖动帧时，不读未来事件），看真实位置是否落在时序分支包络内（planner_bounds）：

| 类别 | 窗口数 | bounds_ft（11 条） | bounds（9 条） |
|---|---|---|---|
| 全部可覆盖 | 27 388 | **99.69 %** | 99.51 % |
| wall（滑墙 / 贴墙 / 蹬墙跳 / 墙砍 / 上砍下砍离墙） | 10 434 | **99.90 %** | 99.75 % |
| scramble（爬墙，含撞顶） | 1 475 | **100 %** | 100 % |
| dash（地面 / 空中冲刺 + sprint） | 1 183 | **100 %** | 100 % |
| plain（跑跳攻击空中待机） | 11 208 | **100 %** | 99.97 % |
| glide（滑翔） | 1 137 | 98.95 % | 98.59 % |
| reaper_down（Reaper 下劈，含 Thunk） | 980 | 98.78 % | 98.78 % |
| contact | 307 | 100 % | 99.35 % |
| hitch（有一帧 > 18 ms） | 236 | 83.5 % | 73.7 % |
| uncovered:slope | 597 | （不计） | |

未达 99 % 的两类与原因：
- **glide 98.95 %**：剩下 12 个窗口是滑翔落地 / Deflate 结束那一两帧的时间（落地发生在 Deflate 内还是之后，差一步），以及 Umbrella Turn 的单窗口；剩余误差 ≤ 0.22 u。
- **reaper_down 98.78 %**：12 个窗口来自 B 里 4 次下劈，都是 Antic 9 帧与下劈 10 帧同时出现的短组合（时序分支把所有缩放计时器同向移动，覆盖了"都早"，但估计的起始阶段时间在边界上）；最大 0.27 u。
- **uncovered:slope**（新类别）：Hang_12 的天花板是一串斜边（y 9.88–11.1），模型的 rollout 不碰撞斜边（`Terrain2D.slopes` 只保存）；D 里高跳 / 滑翔顶到它就偏 2–4 u。kin_check 现在把碰撞盒离斜边 ≤ 0.05 u 的窗口记为 uncovered:slope。Forum 竞技场若有斜边（天花板、台阶）同样不准——这是地形模型的缺口，不是 Forum 动作的。
- replay_events（用记录的帧时间）与 planner_events（单条最可能轨迹）：B + D covered 98.3 % / 96.8 %；单条轨迹在 reaper_down 83.9 %、scramble 89.2 %、glide 92.5 %——都是阶段长度 ±1 帧的抖动，只有包络能覆盖。

修正过程（B / D 的失败窗口逐一对日志，按影响排序）：模板禁用动作（1.6）；Thunk（1.4）；地面 sprint 起步的 Translate 从绘制位置平移（1.3）；冲刺结束那步已有 sprint 的加速；滑翔 Inflate 速度从 0（1.2）；撞顶（1.4b）；上砍离墙的 MovePosition 晚一步；wallSlashing、蹬墙锁、空中悬停、墙接触位、FixedUpdate 进入的计时、跳键队列（2）。B 上 wall 从 96.7 % → 99.9 %，reaper_down 87.8 % → 98.8 %；D 上 dash 96.6 % → 100 %，glide 84.5 % → 99.0 %。

### 5.4 Reaper 攻击：逐帧采样与命中核对

- 逐帧采样（A 的 40 次攻击试验，343 帧有效）：横砍 / 墙砍伤害体在按键到达游戏后第 5–12 帧开启，上砍 5–15 帧，多边形与 slash.dump 相差 ≤ 0.024 u（`attack_table_build --live`，已写入 reaper.json）。旧采样把配置组里未激活对象（down / charge / taunt）的碰撞体当成"开启"（每帧都开）——探针现在同时要求对象 activeInHierarchy，构建工具跳过这种旧样本。
- 下劈的真实伤害对象是 `Attacks/Scythe/DownSlash New`：oracle `slash.dump` 加了可选 `paths` 参数（已编译、未部署），探针默认带上它；部署后再采样即可得到它的多边形和帧窗口。冲刺攻击（dash_attack）与蓄力斩（charge）探针原语已加，采样见 HANDOFF。
- 命中核对（`attack_hit_audit`，Bell Beast + Reaper 数据跑 20261002_225836，实例 3，9 场：7 CLEAR、2 STUCK；CPU ~60 %）：

| 槽 | TP | FP | FN | 接触比命中早（帧） |
|---|---|---|---|---|
| normal | 103 | 27 | 0 | 主要 1–3（58 次 2 帧） |
| alt | 17 | 2 | 0 | 1–3 |
| up | 34 | 5 | 0 | 0–3 |
| down（src DownSlash New，多边形暂用组对象的） | 17 | 2 | 1 | 1–2 |

无漏判（normal / alt / up 0 FN），下劈 1 FN；接触普遍比命中事件早 1–3 帧（伤害在下一物理步结算、事件再晚一帧）。normal 的 27 个 FP 待查（候选：Boss 处于不可伤状态、铃铛挡刀、窗口 5–12 帧偏长）。

### 5.5 bounds_ft 时序分支要不要（M2 任务第 4 项）

| 录像 | bounds（9 条，alpha_margin 0.01） | bounds + alpha_margin 0.03 | bounds_ft（11 条） |
|---|---|---|---|
| Hunter Bell Beast 实战 20261002_171806 i0_000（69 474 窗口） | 97.51 %，包络 p95 0.006 u | 97.89 %，p95 0.12 u | 98.06 %，p95 0.35 u |
| Forum 留出 B + D（27 388） | 99.51 %，p95 0.17 u | 99.43 % | 99.69 %，p95 0.35 u |
| 把名义帧时设成 0.01665（Forum B + D，bounds） | 99.22 % | | |

结论 / 建议：ft 两条分支多覆盖 0.2–0.6 个百分点，但把包络 p95 宽度从 0.006–0.17 u 拉到 0.35 u（单步之差：帧时 0.01665 vs 0.01698 跑 30 帧，物理相位差半步），给规划器的安全检查当余量太贵；rollout 成本 +22 %（11 / 9 条）。建议：规划器的安全判断继续用 bounds；bounds_ft 只用于验收（kin_check）和残差监视器。把名义帧时跟着实例走没用（帧时是轮换的，平均仍是 1/60）；加大 alpha_margin 也不划算（覆盖 +0.4 pp，p95 却到 0.12 u，且 Forum 上反而略降）。


## 6. 性能

`tools/kin_bench_forum`（512 × 48，threads 4，随机按键含跳 / 冲刺 / 滑翔 / 下劈，起点贴墙附近；实例 0-3 跑门槛评估时，CPU 负载 60-75 %）：Forum 参数 nominal p50 1.95 / p99 2.49 ms；同样输入 Hunter 参数 0.99 / 1.94 ms。"bounds" 9 条时序分支：Forum p50 8.3 / p99 12.4 ms，Hunter 3.1 / 4.3 ms（优化前测）。
2026-10-03（本轮全部修正后，CPU 负载约 62 %：实例 3 在采样、其余代理在跑）：Forum nominal p50 2.40 / p99 4.29 ms，bounds 6.92 / 10.71 ms；Hunter nominal 1.19 / 2.25 ms，bounds 3.34 / 4.84 ms（同一时刻对照，Forum ≈ 2 × Hunter）。
