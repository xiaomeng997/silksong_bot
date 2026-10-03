# Forum 配装的运动学、Reaper 攻击判定与安全口袋工具（M2 W8，1.0.30000）

> 2026-10-02 起（开发代理 W）。范围：贴墙滑行 / 爬墙爪贴墙（Ascendant's Grip）/ 蹬墙跳 / 贴墙出刀、滑翔（Drifter's Cloak）、冲刺（Swift Step）与之后的 sprint FSM、Reaper 下劈与硬着陆进入运动学模型；Reaper 各攻击的伤害碰撞体多边形与生效时间做成数据；覆盖图 / 安全口袋工具。没有二段跳和 Silk Soar（你说"二段跳可能没有"：社区存档 High Halls 时刻 p7_s3 正是 hasDoubleJump = false、hasSuperJump = false，模型不含二段跳）。
>
> 2026-10-03 第三轮（修正代理）：第二轮的"留出验收"其实不是留出（B / D 用来找过错误），按复核意见重做：模型冻结后另录两段留出录像只算一次（第 5 节）；验收不再用日志里的接触事件、不再排除斜边和 mantle 窗口；补了刀砍地形的后坐、斜边碰撞；Reaper 命中核对的假阳性原因更正；覆盖图改为保守栅格。
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
- **Bump L / R 之后**（2026-10-03）：被墙推开（vx ±6）后 FSM 停在 Bump 状态，它自己不改速度；松开跳直接进 Deflate，否则下一帧进 Float Idle（s98000 f405707：Inflate 中碰右墙，下一帧松键，vy 保持 0.5 一帧后才有重力）。模型 PHASE 5。
- 落地 / Deflate 结束交还控制时，若 0.1 s 内按过跳（InputHandler 的跳键队列，见 1.3）且能跳 → 立刻起跳（实测：离地很近时按下的滑翔在 Antic 中落地，按住的跳键让她当帧跳起）。

### 1.3 冲刺（Swift Step = hasDash）与 sprint FSM

- `HeroDash`（9058）：地面 `dash_timer` = `DASH_TIME` 0.1 s，空中 `AIR_DASH_TIME` 0.02 s（一步）并记 airDashed；滑墙中冲刺先翻转（背离墙）；否则按方向键定朝向；`DASH_COOLDOWN` 0.425 s；冲刺键排队 10 步。`Dash()`（4334）：每步若可滑墙则开始滑墙并结束；重力关；vx = ±`DASH_SPEED` 28，vy = 0；计时减 0.02。注意 FixedUpdate 后段的空中悬停逻辑在不按跳时会把重力倍数立刻恢复为 1，所以每步仍有一次重力积分（−1.2 u/s）。
- `FinishedDashing` → sprint FSM：Start Sprint（重力倍数 1，夺控）→ 地面：vx = 28 → 地面 sprint（每步 AccelerateToX 1.1 向 17.5）；空中：Air Sprint（0.235 s，AccelerateToX 1.1 向 12，vy 下限从 −10 线性放宽到 −30（EaseFloat easeType 21 = linear，1 s））→ Air Sprint Loop（直到冲刺键松开、撞墙或落地；落地仍按着冲刺 → 地面 sprint）。所以空中冲刺即便是点按，也有约 0.235 s 的"空中 sprint"，水平约 5 u。
- **冲刺结束那一步**（实测 C / D）：Dash() 发现计时到了只调 FinishedDashing、不改速度；sprint FSM 在同一个 FixedUpdate 里进 Air / Ground Sprint，其 AccelerateToX OnEnter 已经作用（28 → 26.9，这一步就按 26.9 移动）。冲刺步数：地面 0.1 s、空中 0.02 s 用 float32 每步减 0.02 留下 3.7e-9 的余数，所以地面 6 步、空中 2 步。
- **Ground Sprint R / L OnEnter 的 Translate 0.05 u（朝前）**：从**绘制位置**（上一帧的插值位置）平移，刚体跟过去，然后这一步再积分——25 次松键地面冲刺里 24 次用记录的 alpha 反推平移量正好 0.05（剩下一次 alpha 0.048 是读数绕回）。模型新增状态行 RX0 / RY0 记录每帧开始时的绘制位置（只在有 abilities 时写）。空中冲刺落地转地面 sprint（LAND 来自落地那步的碰撞回调）时变换就在刚体处：平移从刚体位置算（实测落地帧移动 = 17.0 × 0.02 + 0.05）。
- **地面 sprint 松开冲刺键**：Sprint Timer < Sprint Grace 0.3 s 或速度 < 4 → 不打滑，Regain Control To Idle（下一步按输入走：无输入则 vx = 0）；否则 Skid End 1 / 2（片段 0.2 + 0.05 s，DecelerateXY 0.85，朝面向方向按着方向键时 0.95）。**计时从哪里开始未定**：拟合录像里唯一能区分的一次（s98200 f774201：空中 sprint 0.20 s + 地面 0.283 s 后松键，打滑）让第三轮把计时改成从 Start Sprint 起算（空中落地进地面 sprint 不清零）；留出录像 s98700 f1201778（空中 0.30 s + 地面 0.117 s，没有打滑）与之矛盾。7 次地面松键（拟合 3、开发 6、留出 1，部分重叠）都符合"只算地面时间、阈值在 0.183–0.283 s 之间"。要读 hornet_sprint 模板的 Sprint Timer 动作再定；模型（冻结版）用的是 Start Sprint 起算。
- Skid 片段播放时 isSprinting 已清，模式仍判为 sprint（之前判成 LOCKED，s98200 f774201）。
- Air Sprint 的下落速度下限（EaseFloat −10 → −30，1 s）比状态时间晚一帧（实测 −15.20，状态时间算出 −15.53，C / D 每次都是）。
- **InputHandler 的跳键队列**：每次按跳（WasPressed）设 0.1 s（非缩放时间）计时；RegainControl 的普通分支（不是 startWithWallslide 等）若能跳就消费它起跳。模型新增状态行 JBUF。
- 未建模（模型里这些按键不做事，规划器不应选）：滑墙中朝墙按冲刺 = 爬墙（Wall Scramble FSM）、下冲（按下 + 冲刺）、sprint 中跳跃的特殊跳（按普通跳近似）、Sprint Turn。

### 1.4 Reaper 下劈（Crest Attacks FSM "RPR DOWNSLASH"）

- `DownSlashType` = Custom：`Attack` 先设 attacking 并 `DidAttack`（冷却 0.5 s），FSM：Rpr Downslash Antic（"v3 Down Slash Antic"）：夺控、重力关、进入时和每步 vx、vy ×0.85（DecelerateV2）。**模板里同一状态的 DecelerateXY（y ×0.8）和 UmbrellaMotionX 是禁用的**（ActionData.actionEnabled = false，见 1.6）：实测进入帧（无物理步）vy 就 ×0.85，此后每步只 ×0.85；Rpr Downslash（"v3 Down Slash"）：v = 0 后 `SetVelocityByScale` → vx = 朝向 × 30、vy = −30，每步 ×0.7；动画触发帧后 Fall（重力恢复）→ Fall 2 → End（交还控制，`FinishDownspike`：下劈恢复期）。命中 → Bounce（`SetStartWithDownSpikeBounce`，交还控制后弹起）；Fall 中按冲刺 → 取消。
- HeroBox 在下劈中是 `HeroBoxReaperDownSlash`（0.4554 × 1.601，偏移 (0.37, 0.632)）。
- **地形撞击（thunk）**：下劈判定体上的 `NailSlashTerrainThunk` 碰到地面层（8）且接触点在 hero.pos 下方 → `THUNKED DOWN` → Rpr Downslash Thunk：DecelerateV2 0.715（进入时一次 + 每步；该状态的 SetVelocity2d y 28 被禁用，所以不弹起），同一个动画触发帧结束进入 Fall。撞击那一步的速度比 = 0.7 × 0.715 ≈ 0.50（实测）。触发条件实测（2026-10-03 只用拟合录像 s98000 + A + C 重拟，`kin_fit_forum.thunk_reach`：321 个单步帧、20 次撞击）：碰撞盒中心离前方 0.5–2.2 u 内地面的高度，MODE_T < 0.0583 s 时 ≤ 2.165 撞、≥ 2.194 不撞 → 2.1795；之后 ≤ 2.347 撞、≥ 2.356 不撞 → 2.3515（第二轮用 A / B / C 手拟的 2.33 会漏掉拟合录像里两次 2.347 的撞击）；贴着墙的下劈（墙在身后 0.27 u）离地高时从不撞——墙不触发。模型：`rpr_thunk` 判断前方 0.5–2.2 u 内的地面段，阶段 4 = Thunk。
- FinishDownspike（End）：`vy = −10`、ResetGravity、RegainControl（实测交还控制那帧 vy 正好 −10）。
- 下劈的伤害对象是 FSM 用 FindChild 找到的 `Attacks/Scythe/DownSlash New`，命中事件 src = "DownSlash New"（Bell Beast 实测 18 次全是它）；slash.dump 的 down 槽给的是配置组的 `DownSlash` 对象，不是它（见 3）。

### 1.4b 爬墙（Wall Scramble FSM，hornet_wall_scramble）与翻越（Mantle）

- 滑墙中**按住朝墙方向再按冲刺**（`HeroDashPressed` → `CanWallScramble`：在滑墙、有 Cling Grip、能控制、按着朝墙方向）不是冲刺而是爬墙：Take Control（夺控，滑墙结束）→ Scramble Antic（片段 "Wall Scramble Antic"，速度清零、重力关、y 每步 ×0.85）→ Start Scramble（vy = 22，Quickening 时 30）→ Scramble Up（每步 AddForce2d 向下 72，冲刺键仍按着时 48；英雄刚体质量 1（预制体 Rigidbody2D m_Mass）；AddForce2d 的 OnEnter 也加一次力，所以第一步是两份（实测 −1.92 = 2 × 0.96 占 74/83，−2.88 是那帧有两步）；Scramble Antic 的 DecelerateXY 被禁用（只有 SetVelocity 0）；vy < 0.5 → Scramble End；按跳 → 蹬墙跳；不再面对可滑的墙（到顶）→ Mantle 翻越）→ Scramble End（片段 "Wall Scramble End"，y 每步 ×0.8；再按冲刺（松开过、按着朝墙）→ 再爬一次）→ 回到滑墙。Scramble End：DecelerateXY 0.8 进入时一次 + 每步，brakeOnExit（离开时 vy = 0）。**撞顶（Hit Roof）**：Scramble Up / End 里每步 `HeroCheckForBumpVertical`（CharacterBumpCheck 顶边射线：从碰撞盒顶下 0.1 u、离朝向侧边 0.2 u 处向上 0.1 + 0.03 + |vy|·0.02 u）碰到天花板 → Hit Roof（发生在 FixedUpdate，这一步就恢复重力且这一步的向下力照算：实测 8.56 → 5.92 = −1.44 − 1.2）→ Hit Roof Soft（播 End 片段）→ Detach：Transform.Translate x 0.2 u 离墙（从**绘制位置**平移，刚体随之：实测这一帧 y 也跳到插值高度 +0.01）→ 交还控制（不贴墙，重力开），之后按住朝墙会重新贴上。kn_forum_wall 的墙顶（y ≈ 25.99）就在天花板下，这条路线和 Forum 左墙顶"墙顶紧贴天花板台阶"相同。
  - 2026-10-03 补（拟合录像 A / s98000 的 22 次撞顶）：撞顶检查在 Scramble Up 的 **OnEnter** 也跑一次（Start Scramble 的那个 Update，射线长度用起始速度 22）：天花板近时当帧就进 Hit Roof（A f696151、f716016）；Hit Roof Soft 播 End 片段，从片段出现那帧到 Detach 是 5 帧（18 次）或 4 帧（4 次）→ `scr_roof_t` = 0.0835（第二轮的拟合把进入帧算了两次，得 0.1002，模型因此晚 1–2 帧，A 上爬墙只有 93 %）。Scramble Up 中再按冲刺（按着朝墙方向）也直接回 Scramble Antic（s98000 f419074，vy 1.84 时），不只在 End 里。
  - 上升在离天花板不到皮厚（0.015）但超过 5 mm 处结束时，这一步不碰撞、速度不变，下一步才接触并清掉 vy（A f708617：顶边离天花板 0.0099 u，vy 16.96 保持一步）；同地面的"迟接触"带。一次爬升约 22² / (2 × 72) ≈ 3.4 u（按住冲刺 ≈ 5.0 u）。这是爬上高墙（Forum 左墙顶）的方法。模型已加入（`M_SCRAMBLE`，片段长度 `scr_antic_t` / `scr_end_t` 待测）；Mantle FSM 未建模（到顶时模型只是交还控制）。
- 空中翻越（Update 2558）：不在滑墙、在空中、vy < 5、按着朝墙方向、碰撞盒中部或底部射线碰墙等条件每帧发 "AIR MANTLE"，Mantle FSM（Check Forward 的 4 条射线判断墙沿，Cling → Vault 上移 1.6 → Land）把英雄翻上墙沿。**未建模**。激励房间 Hang_06 左侧有墙沿，蹬墙跳过去会翻越（A 6 次、B 若干、留出 s98600 54 个窗口）；Forum 竞技场两侧墙面一直顶到穹顶（forum.md 8.1），没有墙沿，不会翻越。验收把这些窗口算作未命中（"locked"，第 5 节）。

### 1.6 模板里被禁用的动作

FSM 模板每个状态的 ActionData 有 `actionEnabled` 数组；之前的转储没读它。读出来（UnityPy，`fsmtemplates_assets_shared.bundle`）与本配装有关的禁用动作：crest_attacks 的 Rpr Downslash Antic（DecelerateXY、UmbrellaMotionX）、Rpr Downslash Thunk（SetVelocity2d）；hornet_wall_scramble 的 Scramble Antic（DecelerateXY）、Scramble End 和 Mantle Antic（各一个 RayCast2dV2）、Mantle Shift（Translate）、Hit Roof（SendEventByNameV2）；hornet_sprint 的 Wallrun Antic（SetGravity2dScale）、Restart Sprint（SetVelocityByScale）、Attack Antic（SetVelocity2d）等；hornet_umbrella_float 的 Inflate（SetHeroCState）。模型按启用的动作写。

### 1.7 刀砍到地形的后坐（NailSlashTerrainThunk，2026-10-03）

- 每个挥刀对象带一个 "Terrain Thunker" 子物体（`generateChild`：复制刀的碰撞体，自带运动学刚体）。它和地面层（8）的接触开始时（OnCollisionEnter2D）：`TerrainThunkUtils.GenerateTerrainThunk` 只取挥刀方向一侧的接触点（横砍：接触点 x 在 hero.pos 前方；上砍：在上方），从 (hero.x 或 hero.y, 接触点) 打射线取表面法线；横砍碰到法线水平的面（surfaceDir 0 / 2，即墙）→ `RecoilLeft / Right`（`SetAllowRecoilWhileRelinquished(true)`：夺控中也后坐；已在后坐中不再触发；`Recoil` 还取消冲刺、清掉蹬墙跳的推力）；上砍碰到法线竖直的面（天花板）→ `RecoilDown`（CancelJump，上升停止）。墙砍朝背离墙一侧挥，接触点总在背后，不触发。
- 时机：刀的碰撞体在片段第一个动画事件（Reaper 2/24 s）打开、第二个事件（横砍 5/24、上砍 6/24）关闭；片段时间含挥刀那帧的 dt，所以按模型的 ATK_T（挥刀帧为 0）是 ATK_T ≥ 4/60 后的第一个物理步开始接触。拟合录像 s98000 + A 的 27 次横砍撞墙：后坐出现在挥刀后第 5 / 6 / 7 帧，正是"第 4 或第 5 帧的 Update 开刀（帧时抖动决定）+ 之后第一个有物理步的帧"。
- 第几刀：`Attack()` 的 altAttack 规则（距上一刀超过 AttackRecoveryTime + ALT_ATTACK_RESET = 0.3 + 0.5 s 或换方向就清零；普通刀 / 上砍有 alt 时用 alt 并清零，否则用普通刀并置位；Custom 下劈不算挥刀但记方向）。normal / alt 多边形不同（前伸 3.60 / 3.67 u），按此选。
- 模型：`AB_THUNK`；挥刀多边形（reaper.json normal / alt / up）放在参数向量尾部；状态行 ATK_KIND（本刀种类，后坐过后取负，一刀只后坐一次）/ ALT / ALT_T / ATK_PDIR；每个物理步按这一步开始时的刚体位置测多边形与墙段（横砍）或天花板段 / 平缓斜边（上砍）相交。估计器从 cstate 的 altAttack（挥刀后立即的值）判第几刀。
- 效果：拟合录像（不用日志事件）contact 窗口 9.3 % → 100 %，开发 14 % → 100 %。

### 1.8 斜边与天花板接触（2026-10-03）

- Hang_12 的天花板是一串斜边，Forum 竞技场的穹顶全是斜边（forum.md 8.1：左墙顶上方 (13.93, 14.19)–(15.44, 14.99) 等）。模型（`AB_SLOPES`）按 Box2D 的多边形-边接触处理：每条斜边对碰撞盒取穿透最小的分离轴（边的法线，朝这一步开始时碰撞盒所在一侧；或碰撞盒的 x / y 轴：边的端点戳进盒子的面），法线优先（容差 1 mm）；推出到皮厚，速度去掉朝表面的分量（无摩擦）。实测：s98200 f761658 跳进斜天花板，重力后的 (8.25, 0.60) 变成 (7.11, −2.56)，正是投影到法线 (−0.339, −0.941)；f755635 顶到两段斜边的拐点，当步停在其下 0.014 u、vy 0。
- 接触从多近开始：离斜边 0.0095 u 时还没碰（f761657，模型若用地面的皮厚 0.015 会早一步）；`slope_contact` = 0.005（Box2D 的 linear slop；拟合录像上 0.003 / 0.005 / 0.007 的斜边窗口覆盖 91.6 / 92.1 / 92.1 %）。已经贴着斜边时，下一步先投影速度再移动（f770141：沿 45° 天花板下滑，从离它 7 mm 的瓦片拐角下面过去）。
- 顶到天花板（法线朝下 ≥ 60°，或水平天花板）= OnCollisionEnter2D 的 top：CancelJump（Hunter 模型没有这条，按住跳会贴在天花板上直到 JUMP_STEPS 用完）。滚动重物的圆形碰撞体仍按外接盒的边放在 `slopes` 里，同样被碰撞。
- Hunter 规则不碰撞斜边（abilities 0 时逐位不变）。kin_check 的斜边窗口现在是计入的类别 "slope"（不再是 uncovered:slope）。

### 1.9 贴墙时提前落地（2026-10-03）

`OnCollisionStay2D`（和墙的接触每步都触发）里：`CheckTouchingGround()`（碰撞盒左 / 中 / 右三条向下射线，到盒底下方 0.16 u）看到地面且 falling → `BackOnGround()`。所以贴墙下滑到离地 0.16 u 内就算落地：滑墙被取消、下一步按输入跑动（A f695370：离地 0.11 u 时 "Land To Run"）。模型在墙接触的回调里加了这条。估计器补了 wallUnstickSteps（背离墙按键的步数，用上一帧的按键）和蹬墙锁结束后的连跳窗口（WJLOCK_CHAIN_STEPS）。

### 1.5 硬着陆

`FallCheck`（9730）：下落中、未夺控（或在 sprint）、vy ≤ −`MAX_FALL_VELOCITY`（30）且不在滑墙时累计 fallTimer，超过 `BIG_FALL_TIME` 0.5 s → willHardLand；着地时 `DoHardLanding` → hero_state hard_landing 0.67 s，每步速度清零。Bell Beast 场地落差不够，Hunter 模型没有它；Forum 从墙顶掉下来可能触发，所以 Forum 参数里打开（`AB_HARD_LAND`）。

## 2. 模型实现

- `HeroParams.abilities` 位掩码（`AB_WALL`、`AB_CLING`、`AB_DASH`、`AB_BROLLY`、`AB_RPR_DOWN`、`AB_WALLSLASH_SLOW`、`AB_HARD_LAND`）；为 0 时新规则一条也不走，Hunter 的 rollout 逐位不变（kinematics + knockback 原有 47 个测试全部通过，含 numba 与 NumPy 参考逐位相同、跟踪器与 state_table 逐行相同）。
- 新增 21 个状态行（`WSIDE`、`WTOUCH`、`CLING`、`CLING_CD`、`WSTICK`、`UNSTICK`、`WLOCK`、`WJ_DIR`、`WJ_V`、`WJ_CHAIN`、`WJQ`、`WSLASH`、`PREV_GS`、`GL_CD`、`DASH_T`、`DASH_CD`、`AIRDASHED`、`DQ`、`FALL_T`、`HARD`、`SP_X`），5 个新模式（`M_GLIDE`、`M_DASH`、`M_SPRINT`、`M_RPR_DS`、`M_HARD_LAND`），59 个新参数（反编译常量、FSM 动作参数、待测的动画长度）。
- 新规则只写了一份：`kin_jit` 的标量代码（NumPy 参考只覆盖 Hunter 规则；`backend="numpy"` 配 abilities ≠ 0 会报错）。FSM 动作（UmbrellaMotionX、AccelerateToX/Y、DecelerateV2/XY、SetVelocity2dConditional）按物理步执行，读的是上一帧的输入（FixedUpdate 在本帧输入更新之前）；动画定时的 FSM 状态用"进入后下一帧起累计的缩放时间"判断结束（同丝矛阶段）。
- 2026-10-03 第三轮：abilities 加 `AB_THUNK`（刀砍地形后坐，1.7）和 `AB_SLOPES`（斜边碰撞、顶天花板 CancelJump、天花板迟接触，1.8）——不是配装，但只在 Forum 参数里打开，保证 Hunter 逐位不变（main f329afb 与本分支在 20261002_171806 i0_000 前 40 000 帧上：planner / replay 四种设置、planner_bounds、模式、state_table 0–50 行、跟踪器 30 000 帧、窗口类别全部相同）；hero_reaper_forum.json 的 abilities = 511。状态行加 ATK_KIND / ALT / ALT_T / ATK_PDIR（K = 82）；参数加 thunk_on / thunk_off / thunk_off_up / slope_contact 和 thunk_polys（向量尾部，`P_THK`）；glide PHASE 5 = Bump；cstate 加 altAttack 列。每个手设值在参数文件的 source 里写了出处（`kin_fit_forum.HAND_SET`）。
- 2026-10-03 补：状态行再加 `WCON`、`SHOVE`（上砍离墙的 MovePosition 待下一物理步执行：那一步按偏移 + 重力份额移动、速度保持原值，实测 x −0.8、y −g·fdt²、vy 仍 0）、`RX0` / `RY0`（每帧开始时的绘制位置，FSM 的 Transform.Translate 从这里平移）、`JBUF`（InputHandler 跳键队列 0.1 s）；模式 `M_SCRAMBLE`；阶段：Reaper 下劈 4 = Thunk，爬墙 3 = Hit Roof Soft。参数共 81 个新项（含 `scr_roof_*`、`rpr_thunk_*`、`sprint_shift` / `sprint_grace` / `skid_*`、`air_fall_clamp_lag`）。拟合值在 `knowledge/1.0.30000/kinematics/hero_reaper_forum.json`（`tools/kin_fit_forum`，见 5）。
- 估计器：`classify_modes(tr, forum=True)` / `StateTracker`（abilities ≠ 0 时）用 `forum_mode` 从 cstate（dashing、isSprinting）、hero_state（no_input、hard_landing）和动画片段（`GLIDE_CLIPS`、`SPRINT_CLIPS`、`RPR_CLIPS`）判模式；`ForumRows` 从 wallSliding / wallClinging / hero.wall / 片段 / hero.tm 推新状态行，state_table 与跟踪器共用同一个逐帧函数。`Trace` 新增 `wall`（hero.wall），`_CS_USED` 末尾追加 6 个 cstate 名（旧的 Trace 存档少这几列，`flag()` 读作 False）。估计器补的细节（第二轮，来自 B / D 的失败窗口——所以 B / D 是开发集，不是留出集）：wallSlashing（滑墙中横砍到攻击结束）；蹬墙锁在按回墙方向且锁满 5 步时解除；空中悬停用这一步开始时的速度（滑墙在 LateUpdate 改 vy，悬停晚一步；只对 Forum，Hunter 不变）；墙接触位由地形几何补（OnCollisionEnter 那一步 hero.wall 还是 0）；FSM 在 FixedUpdate 进入的阶段（撞顶、冲刺结束进 sprint）进入帧就开始计时；OnEnter 的速度改动（爬墙的第一份力、滑翔各阶段的 UmbrellaMotionX、Thunk）在下一物理步前保持"待生效"；滑翔按下的跳不进跳键队列。

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

坐标系（2026-10-03 更正）：导出的伤害多边形顶点来自挥刀对象的 transform（localToWorldMatrix），跟着英雄的**插值（绘制）位置**走；hero.box 是物理碰撞盒（刚体位置）。运动中两者差一个插值滞后：第二轮按 hero.box 中心取样，单个样本相对转储多边形偏 −0.6 × 碰撞盒每帧位移（相关 −0.92），最多 0.41 u，中位数让 up 槽"移动"了 0.024 u。现在按绘制位置 hero.pos 加碰撞盒相对 transform 的偏移（中心在 transform 下方 0.5133）取样：normal / alt / up / wall / charge 的 508 / 22 / 103 / 66 / 288 个样本全部是转储多边形的刚体平移（最大偏差 0.000 u），up 槽恢复转储多边形。表的坐标 = 静止刚体的碰撞盒中心，规划器按模型（刚体）位置放置；命中核对把多边形放在 hero.box 上（放在绘制位置反而更差：normal 96 / 2 / 7），说明命中按刚体位置判定。ents 的敌人轮廓也是从 transform 导出的绘制位置。
Reaper 配置（crests.json table.configs）：攻击持续 0.35 s、冷却 0.5 s、硬直 0.3 s（Hunter 0.35 / 0.41 / 0.15）。命中后坐：`RECOIL_HOR_VELOCITY` 3.75 × 8 步（与 Hunter 同一路径，长后坐只在 RecoilLeftLong 等调用时）。逐帧实测（slash.dump 每帧采样）与命中核对见第 5 节。

### 3.1 英雄受伤判定框（HeroBox）与碰撞盒不是一回事

Hero_Hornet 预制体（heroloading_assets_all.bundle，UnityPy 读取）：碰撞盒 BoxCollider2D 偏移 (0, −0.5132)、尺寸 0.5 × 2.0789（即 hero.box：transform 下方 1.5527、上方 0.5262）；子物体 HeroBox 在 transform 原点（局部 (0, 0)），触发器 BoxCollider2D，尺寸随状态由 `HeroBox.cs` 改写：正常（`HeroBoxNormal`，进入 idle / running / airborne / grounded 时设置）偏移 (0, −0.3799)、0.4554 × 2.2498，即 transform 下方 1.505、上方 0.745——**比碰撞盒高出 0.22 u（头顶），两侧各窄 0.045 u**；滑墙 / 贴墙（`HeroBoxWallSlide`）偏移 (0.2101, −0.2755)、0.8757 × 1.2805（局部 +x 是朝左时的前方：贴左墙时向右偏，背离墙一侧伸出 0.65 u）；下劈 0.4554 × 1.218；Reaper 下劈 偏移 (0.37, 0.632)、0.4554 × 1.601；sprint、空中冲刺、招架姿态等各有一套（HeroBox.cs 166-273 行）。规划器和预测器至今用碰撞盒加余量判接触；头顶 0.22 u 的差靠余量吸收（余量小于 0.22 u 的检查会漏掉擦头顶的命中）。覆盖图工具用 HeroBox。

## 4. 覆盖图 / 安全口袋工具

`tools/coverage_map.py`：录像中每帧敌人的伤害碰撞体（`ents.is_threat`）按（type_key, Control 状态）栅格化（默认 0.05 u）求并集；候选英雄姿态 = 每段地面上的站立点 + 每面能贴的墙（`facing_near_wall` 通过）从底到"碰撞盒中心到墙顶"的贴墙点，各配自己的 HeroBox（HeroBox.cs：普通 0.4554 × 2.2498 偏移 (0, −0.38)；滑墙 0.876 × 1.280 偏移 (0.21, −0.276)，x 随朝向镜像，背离墙一侧更宽）；输出每点与每个招式并集的间隙（负数 = 重叠）、最近的招式、安全点（间隙 ≥ --margin）、每面墙最高贴墙点的间隙，可选 PNG。
2026-10-03 改为保守栅格（复核发现的问题）：原来只填中心在多边形内的格子（每条边最多少半格）、细于一格的多边形和 EdgeCollider 只标顶点格、帧间没有扫掠、隐藏实体的伤害碰撞体被跳过，圆形还以八边形的第一个顶点为圆心（偏约 1.2 u）。现在：中心填充 + 轮廓经过的每一格（supercover），边碰撞体 / 两点碰撞体按线段栅格化，胶囊的弧点向外推到外接，圆直接用 oracle 的外接八边形；同一实体同一碰撞体相邻两帧的轮廓按顶点线性插值扫掠（每条边四个端点的凸包），一帧跳超过 3 u 视为传送不扫；隐藏实体照算。测试：3 × 0.02 u 的细条、边碰撞体、两点碰撞体、止于 x 2.024 的多边形、每帧移动 1.2 u 的盒子，都不再报正间隙。
Bell Beast 试用（20261002_171806，4 实例各 4 场，55 580 帧，40 组，44 788 个轮廓带扫掠、0 次传送）：10 s。左门内侧墙（x 69.21）最高贴墙点 y 13.29 间隙 **1.44 u**（原 1.91）；右门内侧（x 102.0）**1.59 u**（原 0.34）——两处变化都来自圆心更正（落铃原来被画在右上方约 1.2 u），扫掠不改变这两个数。

## 5. 实测

### 5.1 激励录像（实例 3）

| 名称 | 录像（C:\ssbot\data\runs\m2\kn_excite_forum\…\TRAIN\…） | 存档 | 种子 / 次数 | 用途 |
|---|---|---|---|---|
| s98000 | 2026-10-02\kn_excite_forum_s98000 | kn_forum_wall（Hang_06） | 98000，125（中途停） | 拟合 |
| A | 2026-10-02\kn_excite_forum_s98010 | kn_forum_wall | 98010，170 + 40 次逐帧攻击采样 | 拟合、攻击帧 |
| C | 2026-10-02\kn_excite_forum_s98200 | kn_forum_floor（Hang_12） | 98200，160（滑翔、冲刺、Reaper） | 拟合 |
| B | 2026-10-02\kn_excite_forum_s98100 | kn_forum_wall | 98100，120 | **开发**（第二轮按它的失败窗口改过模型） |
| D | 2026-10-02\kn_excite_forum_s98300 | kn_forum_floor | 98300，100 | **开发**（同上） |
| T1 | 2026-10-03\kn_excite_forum_s98600 | kn_forum_wall | 98600，220（wall_hold ×2、wall_jump ×2、wall_attack ×2、wall_scramble ×2、reaper_attack 的权重） | **留出** |
| T2 | 2026-10-03\kn_excite_forum_s98700 | kn_forum_floor | 98700，180（glide ×2、dash ×2、reaper_attack，随机方向） | **留出** |

T1 / T2 在 2026-10-03 第三轮开头从提交 d4ffef8 的独立工作区（C:\ssbot\live_kn_d4ffef8）录制（实例 3，CPU 70–85 %：5 个游戏实例和其他代理在跑），之后一直没有读，直到模型在 f6c75de 冻结；验收只跑了一次，没有再按它改模型。
帧时间：这些录像的帧不是"每帧 0.01665 s"，而是 0.01665 / 0.016682 / 0.016667 轮换；30 帧窗口的平均帧时要么正好是限帧器的 0.01665（相位比名义帧时少走 0.024 步：s98000 全程、其余录像 ≥ 5 % 的窗口），要么在名义值 +0.003 步以内（p99；A 的 p99.9 是 +0.03）。Bell Beast 实战 20261002_171806 i0_000 同样（见 5.5）。

### 5.2 拟合（`tools/kin_fit_forum` on s98000 + A + C → hero_reaper_forum.json；B / D / T1 / T2 都不用）

阶段长度 L（进入那帧到结束那帧的帧数）；单一 L 取区间中点，相邻两个 L 都出现（帧时间抖动决定）取分界 + 0.4 × timer_bias 偏向多数，让 ±timer_bias 的时序分支两边都覆盖：

| 参数 | 观测 L（次数） | 值 (s) |
|---|---|---|
| rpr_antic_t | 9 (11)、10 (38) | 0.1502 |
| rpr_slash_t（x 速度 ×0.7 衰减停止的触发帧） | 10 (3)、11 (33) | 0.1669 |
| rpr_fall_t（到 FinishDownspike 交还控制，Fall 2 占最后一帧） | 9 (3)、10 (33) | 0.1502 |
| scr_antic_t | 4 (83) | 0.0583 |
| scr_end_t | 4 (9)、5 (47) | 0.0669 |
| scr_roof_t（从 End 片段出现那帧算，FixedUpdate / OnEnter 进入那帧的 Update 已计时） | 4 (4)、5 (18) | **0.0835**（第二轮 0.1002：进入帧算了两次） |
| glide_antic_t | 5 (5)、6 (23) | 0.0835 |
| glide_inflate_t | 12 (28) | 0.1917 |
| glide_deflate_t | 5 (3)、6 (9) | 0.0835 |
| rpr_thunk_reach0 / reach1 / reach_t（`thunk_reach`，321 个单步帧、20 次撞击） | 早：撞 ≤ 2.165、不撞 ≥ 2.194；晚：撞 ≤ 2.347、不撞 ≥ 2.356 | 2.1795 / 2.3515 / 0.0583 |

手设值（模板 / 反编译 / 单项实测）的出处写在参数文件的 source 里：rpr_thunk_decel、rpr_thunk_lobe0/1、sprint_shift、sprint_grace、skid_*、air_fall_clamp_lag、scr_roof_ray、scr_detach、wall_up_shove、thunk_on / off / off_up、thunk_polys、slope_contact。
对照（反编译值，不拟合）：贴墙爪贴住时 vy 恒 0（15 645 帧）；滑墙粘住期过后每帧 vy 变化 −24 /s（p50，p5 −31.2：有空中悬停重力 0.1 的帧）；冲刺 |vx| 28；滑翔 Float Idle vy 向 −6 逼近；爬墙第一步 −1.92（74 次）/ −2.88（9 次，那帧两步）。动画片段（UnityPy 读 herodynamic / herocollections 包）：Wall Scramble Antic / End 1 帧 @12 fps（0.083 s）、Umbrella Inflate Antic 0.1 s、Inflate 0.1875 s、Deflate 0.1 s、Skid End 1 0.2 s、Skid End 2 0.05 s、Sprint Air 0.294 s。

### 5.3 验收（`tools/kin_check <录像> --params hero_reaper_forum.json --lanes bounds_lo_mix --bounds-events none`，0.5 s = 30 帧，容差 0.1 u）

口径（复核意见后）：规划器能拿到的信息——历史估计的起始状态（因果）、名义帧时加时序分支、**不用日志里的接触事件**（房间里没有敌人，威胁层没有东西可报；砍墙的后坐、下劈撞地都由模型自己算）；分支 = 规划器要用的那一组（5.5）；看真实碰撞盒是否落在分支包络内。斜边窗口（"slope"）和翻越窗口（"locked"：Mantle 未建模，日志里的翻越不是规划器的信息）都**计入**。只排除非游戏帧（uncovered:invalid / harness / slide / nail_charge：读档、试验之间、读档后的滑回、蓄力斩）。"covered" = 计入的窗口。

| 类别 | 拟合 s98000 + A + C | 开发 B + D | **留出 T1 + T2** |
|---|---|---|---|
| **全部（计入）** | 99.06 %（59 230） | 99.08 %（28 189） | **99.26 %（49 700）**；T1 99.45 %（32 953），T2 98.90 %（16 747） |
| plain（跑跳攻击空中待机） | 99.95 %（19 252） | 100 %（11 208） | 99.82 %（17 530） |
| wall（滑墙 / 贴墙 / 蹬墙跳 / 墙砍 / 上砍下砍离墙） | 100 %（24 843） | 100 %（10 434） | 100 %（17 336） |
| scramble（爬墙，含撞顶） | 100 %（3 918） | 100 %（1 475） | 99.48 %（5 417） |
| dash（地面 / 空中冲刺 + sprint + skid） | 100 %（2 391） | 100 %（1 228） | **97.34 %**（3 048） |
| glide | 100 %（2 491） | 98.59 %（1 137） | **98.12 %**（2 453） |
| reaper_down | 99.18 %（2 793） | 98.88 %（980） | 99.94 %（1 695） |
| contact（砍墙后坐等） | 100 %（721） | 100 %（307） | **89.78 %**（274） |
| slope（离斜边 ≤ 0.05 u） | 92.13 %（927） | 98.49 %（597） | 98.36 %（973） |
| world_freeze（试验之间的 timeScale 0） | 96.67 %（962） | 97.20 %（428） | 93.94 %（792） |
| hitch（有一帧 > 18 ms） | 89.95 %（557） | 73.73 %（236） | 71.88 %（128） |
| locked（翻越） | 2.67 %（375） | 6.29 %（159） | 3.70 %（54） |
| 包络宽度 p95 | 0.186 u | 0.178 u | 0.186 u |

不计翻越窗口时：拟合 99.67 %、开发 99.61 %、留出 99.37 %（这个排除用了日志里的未来帧，只作参考）。单条最可能轨迹（planner_events / planner_inputs）：留出 97.7 %；用记录帧时重放（replay_events）：留出 99.40 %。

**留出未达 99 % 的类别（诊断，模型没有按它改）：**
- **dash 97.34 %（81 个窗口）**：(a) T1 里 6 次贴着墙的地面冲刺（拟合录像在墙房间没有冲刺试验）：冲刺结束时 Ground Sprint 的 Translate 0.05 u 把模型的碰撞盒推进墙里，之后 sprint 穿过实体跑出 3 u；游戏里 sprint FSM 碰墙立刻结束（"Dash To Run"）。(b) T2 的 Sprint Grace：见 1.3，冻结模型用"从 Start Sprint 起算"（一个拟合样本），T2 f1201778 与之矛盾。
- **glide 98.12 %（46）**：Inflate 只持续了 11 帧（拟合 28 次全是 12 帧）的几次、以及 Deflate 前后的一帧。
- **contact 89.78 %（28）**：T2 f1192090 一次横砍后坐，砍向的一侧 3.7 u 内没有任何 TERRAIN 线段——碰到了地形导出里没有的物体（可能是 ForceThunker / 可破坏物），模型无从得知。
- **locked（52）**：T1 里蹬墙跳过去的翻越；Forum 竞技场没有墙沿。
- world_freeze / hitch：测试框架的 timeScale 0 与 CPU 负载造成的长帧，规划器无从预测。

第二轮报告的"留出 99.69 %"作废：B / D 当时用于找错，且 contact 窗口用了日志事件（不用事件时 14 %）、斜边和翻越窗口被排除。第三轮修正（按影响）：砍墙后坐（1.7，contact 9 % → 100 %）、斜边碰撞（1.8，slope 27–29 % → 92–98 %）、撞顶 OnEnter 与 scr_roof_t（1.4b，A 的爬墙 93 % → 100 %）、贴墙提前落地 / unstick / 连跳窗口（1.9，拟合的 wall 99.57 → 100 %）、时序分支 bounds_lo_mix（5.5）、滑翔 Bump（1.2）、天花板迟接触（1.4b）。

### 5.4 Reaper 攻击：逐帧采样与命中核对

- 逐帧采样（A 的 40 次攻击试验）：横砍 / 墙砍伤害体在按键到达游戏后第 5–12 帧开启，上砍 5–15 帧；多边形按绘制位置取样后与 slash.dump 完全一致（第 3 节；第二轮按物理碰撞盒取样，样本最多偏 0.41 u、up 槽被运动偏差"移动"了 0.024 u，已恢复转储多边形）。旧采样把配置组里未激活对象（down / charge / taunt）的碰撞体当成"开启"（每帧都开）——探针现在同时要求对象 activeInHierarchy，构建工具跳过这种旧样本。frame 5 只在约一半挥刀里已开启（normal 32 / 68）：第一个动画事件在挥刀后第 4 还是第 5 帧由帧时抖动决定（1.7）。
- 第二刀（alt，s98400：22 帧）与第一刀同为第 5–12 帧（从它自己的按键算；探针的两次按键相隔 31 帧）。
- 蓄力斩（charge，s98410：16 次按住 110–140 帧再松开，208 帧样本；High Halls 社区存档有 hasChargeSlash）：`Attacks/Charge Slash Scythe` 的 slash 01 在松开后第 16–19 帧开启、slash behind 16–21、slash 02 19–29（按键后先挥一刀普通横砍 0.35 s，蓄力计时在攻击结束后才走，NAIL_CHARGE_TIME 1.35 s）；多边形与转储一致。
- 下劈的真实伤害对象是 `Attacks/Scythe/DownSlash New`（Crest Attacks FSM），冲刺攻击是 `Attacks/Scythe/DashUpper Slash`（Sprint FSM 的 Reaper Antic / Upper / End：Upper 里 SetVelocityByScale 50 u/s 向前、每步 ×0.85、CurveFloat 改 vy 0.3 s，End 设 vy 7——这个位移原语没建模）。两者都不在 slash.dump 的槽里：oracle `slash.dump` 加了可选 `paths` 参数（已编译、未部署），探针默认带上这两个路径，构建工具把它们映射到 down / dash_stab 槽；部署后各采 20–40 次即可得到多边形和帧窗口。
- 命中核对（`attack_hit_audit`，Bell Beast + Reaper 数据跑 20261002_225836，实例 3，9 场：7 CLEAR、2 STUCK）。**更正**：第二轮把 normal 的 22 个假阳性归为"Boss 这些状态不吃刀"是错的——同一录像里 Boss 在那些 Control 状态都被砍中过（Charge 34、Burst Out 21、Charge Emerge 19、Leap Land 7、Rage Roar 3、Dig In 2 次 "Slash" 命中），22 个假阳性全部是英雄在挥刀第 1–5 帧（第一个开启帧之前）挨了打，`TakeDamage` 取消了这一刀（没有任何真阳性在第 6 帧前挨打）。工具现在在英雄挨打（"damage" 事件或被 LethalBlock 拦下的致命伤害）的那一帧结束这一刀：

| 槽 | TP | FP | FN | 接触比命中早（帧） | 被取消的挥刀（其中在开启前） |
|---|---|---|---|---|---|
| normal | 100 | 0 | 3 | 1（66）、2（16）、0（17） | 56（25） |
| alt | 17 | 0 | 0 | 0–2 | 2（1） |
| up | 34 | 0 | 0 | 0–2 | 9（2） |
| down（src DownSlash New，多边形暂用组对象的） | 17 | 2 | 1 | 1–2 | 1（0） |

normal 的 3 个漏判：首次接触正好在英雄挨打的那一帧（这种同帧的 8 次里 3 次刀先命中），谁先结算由那个物理步内的回调顺序决定。命中预测应把"第一个开启帧之前挨打"当作这一刀作废；同帧的情况按约 3 / 8 处理。`--slack 1` 时 FP 10 / 3 / 1 / 2（多出来的都是提前一帧的接触）。

### 5.5 规划器用哪组时序分支（M2 任务第 4 项，结论更改）

30 帧窗口的累计帧时（5.1）：限帧器的 0.01665 s 是真实会持续出现的状态（−0.024 步），而 bounds_ft 的另一端 0.01698 s 持续 30 帧（+0.47 步）在所有录像的任何 30 帧窗口里都没出现过（最大 +0.03 步）。所以加一条"全程 0.01665 s、相位取下端"的分支（`bounds_lo` = bounds + ft_lo，10 条）就拿回了 bounds_ft 的大部分好处，包络几乎不变宽；`bounds_lo_mix` 再加两条"第二个计时阶段与第一、三个反向"（Reaper 下劈的 slash、滑翔的 inflate；每个阶段的结束是各自独立的帧时抛硬币，s98010 f719895 前摇早一帧、下劈准时），12 条：

| 录像（不用日志事件；Hunter / Bell Beast 用日志事件） | bounds（9） | **bounds_lo（10）** | bounds_lo_mix（12） | bounds_ft（11） |
|---|---|---|---|---|
| Forum 拟合 s98000 + A + C | 98.77 %，p95 0.176 | 98.98 %，0.186 | 99.06 %，0.186 | 99.12 %，0.348 |
| Forum 开发 B + D | 99.06 %，0.168 | 99.08 %，0.178 | 99.08 %，0.178 | 99.19 %，0.348 |
| **Forum 留出 T1 + T2** | 98.83 %，0.177 | **99.26 %，0.186** | 99.26 %，0.186 | 99.40 %，0.348 |
| Hunter Bell Beast 20261002_171806 i0_000（69 474） | 97.51 %，0.006 | **97.92 %，0.020** | 97.92 % | 98.06 %，0.348 |
| Reaper Bell Beast 数据跑 20261002_225836 i3_000（98 391；abilities = 下劈、硬着陆、砍地形后坐、斜边；locked 计入） | 97.69 %，0.300 | | 98.38 %，0.342 | 98.92 %，0.414 |

结论：规划器的安全检查用 **bounds_lo**（Hunter 和 Forum 都是；包络 p95 Hunter 0.006 → 0.020 u，Forum 0.18 → 0.19 u，覆盖 +0.2–0.4 pp）；bounds_lo_mix 只在拟合录像的下劈上更好（reaper_down 97.6 → 99.2 %），留出上与 bounds_lo 相同，而成本是 bounds 的 1.9 倍（第 6 节），所以先不进规划器，验收数字用它与用 bounds_lo 相同。bounds_ft 的额外 0.1–0.5 pp 主要在 hitch 窗口（长帧），代价是 p95 0.35 u。Reaper Bell Beast 数据跑上剩下的未命中一半以上是 hitch（3 489 个窗口，那次跑时 CPU 很满）。
（第二轮"bounds + alpha_margin 0.03"：Hunter 97.89 %、p95 0.12 u——不如 bounds_lo。）

## 6. 性能

`tools/kin_bench_forum`（512 × 48，threads 4，随机按键含跳 / 冲刺 / 滑翔 / 下劈，起点贴墙附近）。
2026-10-03 第三轮冻结模型（CPU 负载 71–84 %：5 个游戏实例和其他代理在跑），p50 / p99 ms：

| 参数 | nominal | bounds | bounds_lo | bounds_lo_mix |
|---|---|---|---|---|
| Forum | 3.04 / 4.75 | 8.34 / 12.20 | 10.32 / 15.87 | 15.70 / 22.61 |
| Hunter | 1.14 / 2.18 | 3.48 / 4.90 | 4.61 / 5.67 | 6.37 / 7.73 |

（bounds 的 9 条里，没有受击 / 世界冻结的序列只需跑 3 条不同的；ft_lo 加 1 条、mix 再加 2 条，所以 bounds_lo ≈ 1.3 ×、bounds_lo_mix ≈ 1.9 × bounds。）第二轮（CPU ~62 %）：Forum nominal 2.40 / 4.29、bounds 6.92 / 10.71；Hunter 1.19 / 2.25、3.34 / 4.84。Forum 规则（斜边、砍墙、阶段机）让 nominal 比 Hunter 贵约 2.5 倍，离 3 ms 的 p99 预算还远，规划器接入前要做剪枝。
