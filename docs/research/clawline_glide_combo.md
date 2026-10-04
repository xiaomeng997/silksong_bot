# 飞针–飘飘–下劈–飘飘 连招与锯齿环（调研，2026-10-04）

起因：你说"YouTube 上有人教 飞针-飘飘-下劈-飘飘 的连招，说 DPS 非常高"，又问到建筑师卖的锯齿环（Sawtooth Circlet）。本文回答：(1) 连招每一段在游戏数据里是什么（飞针 Clawline 的 FSM 和伤害、滑翔 Drifter's Cloak 的进入和取消、各纹章的下劈、锯齿环）；(2) 逐帧重建这个连招、周期、每周期伤害和 DPS，与地面砍比；(3) 在 Forum 里安不安全；(4) 我们的录像里有没有这些东西；(5) 规划器要什么才能自己找到它，以及锯齿环在 K1 里值不值。

**标签：** 【码】反编译 1.0.30000 C#（`C:\ssbot\decomp\1.0.30000\Assembly-CSharp`，文件:行）；【包】离线 UnityPy 读训练副本资产包（FSM 模板 `fsmtemplates_assets_shared`、预制体 `localpoolprefabs_assets_shared` / `globalsettings_assets_all` / `heroloading_assets_all`、动画 `animations_assets_shared`、动画片段 `herodynamic_assets_all`）；【录】我们的录像（你的四段：`C:\ssbot\data\human\20261004_002749`（Reaper）、`012300`（Wanderer）、`091214`、`133855`（Wanderer，带锯齿环）；R1 数据跑 `20261004_111158_Forum_A_w2_mix_data2`、`..._w0_data2_envoy`）；【模】运动学模型 kin_jit（Forum Reaper 参数 `hero_reaper_forum.json`）脚本化模拟；【推】推断；【文】仓库已有文档。没有连接任何游戏实例。

**脚本与原始输出：** `C:\ssbot\sandbox\combo_scripts\`（离线、below-normal 优先级）。`fsmx.py`（FSM 模板 / 物体 FSM 转储，dataVersion 2 的参数解码）→ `fsm_umbrella_float.txt`、`fsm_harpoon_dash.txt`、`fsm_crest_attacks.txt`；`spike_dump.py` → `spike_glide.txt` / `spike_dj.txt`（锯齿环预制体、伤害体、多边形）；`anim_dump.py` → `anim_spike_glide.txt`（锯齿环动画曲线）；`laghits.py`（追加伤害 lag hit）；`hero_clips.py` → `hero_clips.txt`（主角动画片段长度）；`combo_evidence.py` → `evidence_human.txt` / `evidence_r1.txt`；`combo_timing.py` → `timing_human.txt` / `timing_all.txt`；`saw_hits.py` → `saw_hits_133855.txt`；`saw_geom.py` → `saw_geom_133855_l11.txt`；`hurtboxes.py`（Forum 敌人受伤框）；`sim_cycles.py` / `sim_matrix.py` → `sim_matrix.jsonl`（kin_jit 模拟）。运行器 `ux.sh`（UnityPy）、`bx.sh`（在工作区 brain 环境里跑）。

## 0. 摘要（可直接转述）

1. **没有锯齿环时，这个连招的 DPS 并不高。** 飞针打中一只怪是两下，每下半刀（Needle 1：4 + 4）【包】【码】【录】；滑翔本身没有伤害【包】；下劈是一整刀（9）【文 crests.json】。用运动学模型模拟收割者（Reaper）对着一只站着的地面怪：自然的下劈弹跳循环每 0.87 s 一刀（10.5 /s）；下劈弹起后**立刻滑翔、在充气（Inflate）阶段用攻击键取消成下一次下劈**，循环缩到 0.43–0.53 s 一刀（下劈部分 12.8–16.5 /s）【模】。站在地上横砍是 9 / 0.5 s = 18 /s。所以没有锯齿环时，这招的好处是"一直在空中、不落地也能连续打"，不是更高的 DPS【推】。
2. **滑翔快的原因有两个，都在游戏代码里：** (a) 滑翔的充气阶段每个物理步把竖直速度设成 +0.5，等于把下劈弹起的上升立刻刹住，下一刀马上又够得着【包 hornet_umbrella_float Inflate】；(b) 滑翔里按攻击走的是"攻击取消"：`SetStartWithAttack` → 交还控制 → `DoAttack()`，这条路**不检查攻击冷却（收割者 0.5 s）、不检查下劈恢复期、不检查是否正在攻击**【码 HeroController.cs:7655、4057、10956】。收割者的下劈 FSM 一夺控就调用 `RelinquishControlNotVelocity` → `ResetAttacks`，所以下劈弹起后滑翔不受"攻击收招锁"挡【码 7449-7467】【录 R1：下劈到滑翔最短 0.167 s】。
3. **"DPS 非常高"要靠锯齿环。** 锯齿环（内部名 Brolly Spike，蓝色）在**每一次滑翔起手**（滑翔 FSM 的 Antic 结束、进入 Inflate 之前的 `Damager?` 状态）生成一圈刀刃，跟着主角走【包】。伤害体是左右两块多边形，**前方 0.2–5.0 u、身后 0–4.7 u，竖直从主角脚下约 0.4 u 到头顶约 0.2 u**（只打和主角身体同高的东西，不往下延伸）；前方那块在生成后 0.10–0.20 s 有效，身后那块 0.05–0.175 s【包】【录 33 次首击 31 次只有这个朝向能解释】。每只敌人每次滑翔只吃一下：基础 8，**吃制作匣**（×1.6 / 个：1 个时 13），0.1 s 后再追加 1 点【包】【码】【录：13 + 1，Clapper 上 15 + 1】。没有冷却、没有次数限制、不耗甲壳碎片、不给丝【包】【码】。
4. **锯齿环的伤害来自"贴着怪的高度起手滑翔"，不来自下劈：** 下劈弹起后主角在怪头顶 1–3 u，刀圈够不着地面怪（模拟 17 次滑翔只中 5 次）【模】。在地面怪旁边 2 u **小跳 + 滑翔**、用攻击取消、再滑翔，模拟收割者每 0.57 s 一轮（刀圈 13+1 + 横砍 9）= **36 /s**，Wanderer / Hunter 的收招时间下每 0.5 s 一轮 = **45–47 /s**，约是地面砍的 2 倍；只滑翔不砍也有 23 /s【模】。刀圈两边各 5 u，范围内每只怪都吃。飞针这一步的价值是把人拉到怪身边、同一高度（之后的第一次滑翔几乎必中）。
5. **飞针不是无敌的**（R1 的结论成立）：飞针冲刺时受伤框换成一个更小的框（0.46 × 1.46）但一直开着；被钩住的那只怪**只有身体**（它根物体上的 DamageHero）在冲刺开始到 FSM 回到 Idle（结束后约 0.2 s）被关掉，它的攻击判定和别的怪照样伤人；飞针结束后的弹起也没有无敌帧（下劈命中才有 0.16 s）【码】【包】【录 R1：5 次钩中后 0.5 s 内被同一只打中】。
6. **Forum 里的安全：** 刀圈打法要站在地面怪的近战范围里（Choristor 斩 p99 9.5 u、Envoy 斩 4.6 u、Clapper 锤 12.1 u，跳起的主角 1–4 u 高都在判定里）【文 R0 strikes.json】；下劈–滑翔循环让主角停在怪头顶 1–3 u，Choristor 鞭 / 跳、Envoy 斩 / 跳斩、Clapper 锤和 rune slam（顶到 y≈10.5）都打得到这个高度；飞行怪（Reed、Minister、Clawmaiden、Maestro）的招上下覆盖 ±5–12 u，和它们同高或在它们上方都不安全【文】。这个连招不是安全的打法，是"在怪出招的空档里多打几下"的打法。
7. **我们的录像：** 你在 `133855`（路线配装半速）装了锯齿环：70 次带锯齿环的滑翔里 29 次打中东西，61 次命中（主要对 Clapper），合计 505 点伤害（这段战斗 1,413 s）【录】。你的收割者录像里下劈 218 次命中、飞针 37 次（17 次两下全中），但**飞针后接滑翔只有 2–3 次，滑翔后的下劈都是等滑翔收起来才劈**（滑翔到下劈中位 0.67 s，不是取消）；R1 的数据策略倒是常用攻击取消（滑翔到下劈中位 0.27–0.32 s）【录】。
8. **规划器要找到它，缺三样：** (a) kin_jit 的滑翔攻击取消现在按普通出刀判（要冷却到、要按着键），游戏里是无条件出刀——要改；(b) 锯齿环的伤害形状和时间（新的攻击槽 `glide_spike`，滑翔起手后 0.13–0.28 s 内命中、算进 0.6 s 视野）；(c) `M_HARPOON` 原语（水平 10.5 u 射线、3 个高度、0.15 + 0.15 + ≤0.1 + 0.1 s、吸附到命中点、两次半刀伤害、-1/+1 丝、不无敌）。K1：锯齿环 vs 护佑钟——锯齿环让对地面怪的伤害约翻倍，但要 230 念珠 + 第 3 块工艺金属 + 去建筑师那里 + 让出一个蓝槽，而且它的打法要贴身；**建议先做模型和探针，再在 K1 用 A/B 决定**（§5）。

## 1. 机制（游戏数据）

### 1.1 飞针 Clawline（`Hero_Hornet` 的 `Harpoon Dash` FSM，模板 `hornet_harpoon_dash`）

| 阶段（状态） | 时长 | 做什么 | 出处 |
|---|---|---|---|
| Can Do? | 0 | 丝 > 0 才继续，否则发 `BIND FAILED NOT ENOUGH` 不出招 | 【包】 |
| Take Control | 0 | `RelinquishControlNotVelocity`（含 `ResetAttacks`）、重力关、**扣 1 丝**（`TakeSilk 1`） | 【包】【码 HeroController.cs:7449】 |
| Flip? / Kick Up? | 0 | 按着方向就转向；在地上先上移 0.25 u | 【包】 |
| Antic | 片段 `Harpoon Antic` 3 帧 @20 fps = 0.15 s | 速度夹到 x ±20、y −10…+5，每步 x ×0.975、y ×0.875 | 【包】 |
| Ring Check L/R | 0 | `HarpoonDashRayCheck`：朝面向**水平**打 6 条射线，长 10.5 u：敌人层 3 条在主角 transform 的 +0.425、−0.3125、−1.05 u，地形 3 条在 +0.056、−0.681、−0.3125 u；地形比敌人近就钩墙 | 【码 HarpoonDashRayCheck.cs】 |
| Enemy Needle | 0 | **第 1 下**：`Harpoon Damager` 直接对钩中的物体 `DoDamage`：钉子伤害 ×0.5（Needle 1：RoundToInt(4.5) = 4；Needle 2：6），攻击类型 Nail，**不给丝**（silkGeneration None） | 【包 damagers_herodynamic.txt】【码 DamageEnemies.cs:952、DamageStack.cs:29】【录 4】 |
| Throw | 片段 `Harpoon Throw` 0.15 s | 速度每步 ×0.9 | 【包】 |
| Dash To Enemy | ≤ 0.1 s | 被钩物体的 DamageHero 关掉（`SetDamageHeroAndRecord`）；以 70 u/s 冲向针（偏移 (0, 0.6)）；受伤框换成 `HeroBoxHarpoon`（0.4554 × 1.46，偏移 (0, −0.33)）；离针 x 距离 < 1 时 `To Needle`：**主角 x 直接设到针的位置**（=射线打中对方碰撞体的那一点） | 【包】【码 HeroBox.cs:270】 |
| Do Enemy Damage | 0 | 速度清零，**第 2 下**：`Harpoon Dash Damager` ×0.5（4），Nail，**给 1 丝**（抵掉起手扣的 1 丝）；偷念珠 / 碎片 | 【包】【码 HealthManager.cs:1107】 |
| Enemy Bounce | 片段 `Harpoon Catch` 0.1 s | 速度 0；有 `HarpoonHook` 的物体走 Hook Bounce | 【包】 |
| Bounce Up → Harpoon Dash End | 0 | `SetStartWithHarpoonBounce`；交还控制；**飞针冷却 0.16 s（落地清零）**；之后 FSM 再等 0.2 s 才回 Idle，回 Idle 时把被钩怪的 DamageHero 打开 | 【包】【码 4825、2310】 |
| 交还控制后 | — | `DownspikeBounce(harpoonRecoil: true)`：跳跃步数从 4 开始，5 个物理步 vy = 18.6，之后自由减速：**约 +4.7 u，0.41 s 到顶**；下劈恢复期 0.15 s（计时从 0.1 开始）；**没有无敌帧**（无敌帧只在 `HeroDownAttack` 下劈命中时给） | 【码 6374、10370、HeroDownAttack.cs:126】【文 hero_constants.json】 |

- 没打中：针飞 9.25 u（Air Needle）→ Throw → Pull Back 0.15 s → Catch Back 0.1 s；钩墙：冲到墙上，接 Wall Slide?【包】。
- **能取消它的：** 受击（全局 `HERO DAMAGED`）、离开场景、`SPRINT CANCEL`、`BOUNCE CANCEL`；FSM 里没有攻击 / 跳取消；结束时只有 Catch（钩墙、空针）路径会记"按过跳"并自动接滑翔（`Jump Queue Check` → `Queued Brolly` → `SetStartWithDoubleJump` → 交还控制时 `StartFloat()`）；**钩中敌人的路径不记**，要在交还控制后再按一次跳【包】【码 7563-7571】。
- 实测：按键到第 2 下 0.30–0.42 s（你的录像中位 0.367 s，n 21；R1 0.35 s，n 42）【录】，与 FSM 0.15 + 0.15 + 距离/70 一致【推】。

### 1.2 滑翔（`Umbrella Float` FSM，模板 `hornet_umbrella_float`）

**进入**：空中按跳、不能跳也不能二段跳时，`CanFloat` 为真就发 `FLOAT`：有披风、不在地上、冲刺不在锁定、离开平台的缓冲用完、不在滑墙、**不在攻击收招锁里**（`cState.attacking && attack_time < AttackRecoveryTime`：收割者 0.3 s、Hunter 0.15、Wanderer 0.1）、不在二段跳、能做 FSM 取消动作、不会排队蹬墙跳、**不在"快落地"**（vy ≤ 0 且碰撞盒两个底角下方 1.1 u 内都有地）【码 11069、8622】。没有"每次腾空只能滑一次"的限制【码】。

| 阶段 | 时长（实测，movement_kinematics §5.2） | 速度 | 可取消 | 出处 |
|---|---|---|---|---|
| Take Control | 0 | `CancelAttack` + `RelinquishControlNotVelocity`（又一次 `ResetAttacks`） | — | 【包】【码】 |
| Antic | 5–6 帧（0.083 s；片段 0.1 s） | 重力照常，上升的速度继续；横向 UmbrellaMotionX(8.5) | **只有飞针**（`HARPOON CANCEL`，飞针可用时） | 【包】【文】 |
| Damager? | 0 | **锯齿环在这里生成**（§1.4） | — | 【包】 |
| Inflate | 12 帧（0.19 s） | **每步 vy = +0.5（停住上升也停住下落）**，重力关 | 进入 **0.075 s 后**攻击 / 冲刺；随时道具、飞针 | 【包】 |
| Float Idle | 按住跳就一直在 | vy 每步以 0.13 逼近 −6 | 攻击、冲刺、道具；**松跳 → Deflate** | 【包】 |
| Deflate | 5–6 帧（0.083 s） | 重力恢复 | 攻击、冲刺、道具 | 【包】 |
| Cooldown | 0.1 s（只在到过 Inflate 时） | — | 这期间再按跳被吞掉 | 【包】【文】 |

- **攻击取消**（Attack Cancel）：`SetStartWithAttack` → Relinquish Control → 交还控制时 `DoAttack()`。`DoAttack` 按住下就 `Attack(downward)`，**不查 `attack_cooldown`、不查 `CanDownAttack`（下劈弹起中 / 下劈恢复期）、不查 `cState.attacking`**；正常按键走的 `CanAttack()` 才查冷却【码 7655-7664、4057-4085、10956-10963、11010-11021】。所以"下劈 → 弹起 → 滑翔 → 0.158 s 后按攻击"可以早于攻击冷却出下一刀。
- 进入滑翔的时机：**飞针后**：钩中敌人时交还控制后要再按跳，最早约在第 2 下后 0.1 s（Catch 片段）+ 1 帧【包】，实测 0.133–0.575 s【录 R1 9 次、你 3 次】；**下劈弹起后**：收割者的下劈 FSM 夺控时 `ResetAttacks`，所以弹起一交还控制就能滑（R1：下劈起手到滑翔起手最短 0.167 s，201 次里 30 次 < 0.3 s）【码】【录】；Hunter 的 DownSpike 本来就不设 `attacking`【码 4110】；Wanderer 的下劈是普通挥刀，要等 0.1 s 收招锁【码】【文 crests.json】。弹起时按着的跳**不会**自动变成滑翔（`startWithDownSpikeBounce` 分支不走 `regainControlJumpQueued`），要新按一次【码 7676-7744】。
- 滑翔起手到能取消成攻击：0.083 + 0.075 ≈ 0.158 s（10 帧左右）【包】【文】。

### 1.3 各纹章的下劈

| 纹章 | 类型 | 伤害 | 判定（相对碰撞盒中心，朝向为 +x） | 时间 | 弹起 / 之后 | 出处 |
|---|---|---|---|---|---|---|
| Hunter / Hunter_v2 | DownSpike（HeroController 自己做） | ×1 钉子（v2 计量 ≥ 6 后 ×1.3） | 前 1.21、后 0.68、下到 −2.32 | 前摇 0.1 s（夺控、重力关）+ 冲刺 0.1 s 沿斜下 (±26, −26) | 命中：`DownspikeBounce`（+4.7 u）、0.16 s 无敌帧（8 物理步）；之后下劈恢复 0.25 s；攻击冷却 0.41 s；不设 `attacking` → 交还控制就能滑翔 | 【文 crests.json、kinematics.py】【码 4247-4284、HeroDownAttack.cs:126】 |
| Reaper | Custom（Crest Attacks FSM `RPR DOWNSLASH`） | ×1 | x −1.80…+2.26、y −2.61…+1.81（reaper.json down） | 前摇 0.15 s（v ×0.85/步）；下劈 0.167 s：速度 (朝向×30, −30) 每步 ×0.7（约斜冲 2 u） | 命中 → Bounce → End → 交还控制 → `DownspikeBounce`；无敌帧同上；冷却 0.5 s；恢复 0.25 s；FSM 夺控时 `ResetAttacks` → 弹起即可滑翔 | 【包 fsm_crest_attacks.txt】【文 movement_kinematics §1.4】【码】 |
| Wanderer | Slash（普通挥刀朝下） | ×1 | 前 1.48、后 1.74、下到 −2.68 | 挥刀 0.25 s、冷却 0.3 s；**收招锁 0.1 s**；没有自己的位移 | 命中弹起（`NailSlash.DoDownspikeBounce`，默认弹起配置同样 4 步起跳【推：弹起配置可能按纹章不同，未读】）；下劈恢复 0.09 s | 【文 crests.json】【码 4286-4302】 |

- 实测按键（片段起手）到下劈命中：收割者 0.15–0.33 s、中位 0.183 s（n 201）；Wanderer 0.033–0.16 s、中位 0.05–0.067 s【录】。
- 收割者斜冲约 2 u：自然的弹跳循环里下一刀要等主角从 4.7 u 的弧线落回够得着的高度，模型里每 0.87 s 一刀（§2.2）【模】。

### 1.4 锯齿环 Sawtooth Circlet（`Brolly Spike`，蓝色，ToolItemBasic）

- **触发**：滑翔 FSM 的 `Damager?` 状态（Antic 播完才进；Antic 被打断走 `Anim Canceled` 直接进 Inflate，不生成）：`CheckIfToolEquipped(Brolly Spike)` → 从对象池生成 `Tool_brolly_spike`（`localpoolprefabs_assets_shared`）→ 挂到主角下 → z 0.002 → 本地 x 缩放 −1【包 fsm_umbrella_float.txt】。二段跳另有 `Tool_brolly_spike_dj`（`HeroController.cs:8948`，我们没有二段跳）【码】。**每次滑翔起手一份，没有冷却、没有次数限制**；物体 0.375 s 后回收（`AutoRecycleSelf`）【包】。
- **伤害体**（`spike_glide.txt`）：`brolly_slash_enemy_damager` 下的 `Damager L` / `Damager R`，两块 PolygonCollider2D（触发器），共享 `SharedDamagedGroup`（同一次生成里**每只敌人只吃一下**）【包】【码 SharedDamagedGroup.cs】。`DamageEnemies`：攻击类型 **Generic**，`damageAsset` = `Tool_brolly_spike`（值 **8**，覆盖序列化的 5）【包】【码 DamageEnemies.cs:544】，`representingTool` = Brolly Spike → **工具伤害 ×(1 + 0.6 × 制作匣)**【码 DamageEnemies.cs:1012】，再乘敌人在"制作匣个数"那一级的系数【文 forum_tools §3.1】：制作匣 0 / 1 / 2 / 4 个 = **8 / 13 / 18 / 27**（Clapper 1 级 ×1.15 → 15，录像核对）；`magnitudeMult` 1.5、`stunDamage` 0.5、`ignoreInvuln`、非多段；**追加伤害（lag hit）**：命中 0.1 s 后再扣 **1 点**（`lagHitOptions`：HitDamage 1、StartDelay 0.1、HitCount 1）【包 laghits.py】【录：每次 13 / 15 之后 0.10–0.11 s 一次 1】。Generic 攻击**不给丝、不算 Hunter 计量**（`HealthManager` 只对 Nail 给丝）【码 HealthManager.cs:1099-1117】。
- **有效时间**（动画 `Tool_brolly_spike`，40 fps、阶梯曲线）：整组 0.025–0.2 s，`Damager L` 0.05–0.175 s，`Damager R` 0.10–0.20 s（从生成算；生成 = 滑翔按键后约 0.083 s）【包 anim_spike_glide.txt】。录像里命中出现在滑翔片段起手后 0.158–0.171 s（L）和 0.208–0.233 s（R）【录 saw_hits_133855.txt】。
- **形状**（相对主角 transform；主角朝右时，前方 = R；预制体根节点 y 缩放 −1 保留）：前方 R：x +0.19…+5.05、y −1.78…+0.60；身后 L：x −4.74…−0.04、y −1.92…+0.76（多边形顶点见 `spike_glide.txt`，y 取反）。主角物理碰撞盒在 transform 下 1.55 到上 0.53：**刀圈是一条约 10 u 宽、2.7 u 高的横带，从脚下约 0.4 u 到头顶约 0.2 u**【包】。朝向的核对：33 次首击里 31 次只有这个朝向（y 取反）能和敌人的受伤框重叠，不取反只能解释 15 次【录 saw_geom_133855_l11.txt】。
- **代价**：建筑师（`Under_17`）230 念珠 + 1 工艺金属，货单条件 `hasBrolly`【文 forum_tools §2.4】；容量 0、不补充：**每次使用不耗甲壳碎片**【包 tools_all.txt】；占一个蓝槽。

## 2. 连招逐帧重建与 DPS

### 2.1 FSM 时间线（收割者，Needle 1，制作匣 1，目标是同一高度、10 u 内的地面怪；飞针没有建模，这一段按 FSM 和实测）

| 时间 (s) | 事件 | 伤害 | 出处 |
|---|---|---|---|
| 0.00 | 按飞针（−1 丝） | | 【包】 |
| ≈0.16 | 针打中：第 1 下 | 4 | 【包】【录】 |
| ≈0.30–0.42 | 冲到对方碰撞体边上，第 2 下（+1 丝） | 4 | 【录 中位 0.35–0.37】 |
| ≈0.45–0.52 | Catch 0.1 s 后交还控制，弹起开始（vy 18.6） | | 【包】 |
| +1 帧 | 按跳 → 滑翔 Antic（弹起的上升继续约 1.4 u） | | 【包】【模】 |
| +0.083 | 生成刀圈；怪就在身边、同高 → 0.05–0.2 s 内命中，0.1 s 后追加 | 13 + 1 | 【包】【录】 |
| +0.158 | Inflate 0.075 s 后按 下+攻击 → 下劈（无视 0.5 s 冷却） | | 【码】 |
| +0.15–0.2 | 下劈命中 → 弹起 | 9 | 【录】 |
| 之后 | 弹起 → 滑翔（刀圈）→ 取消成下劈……每 0.43–0.53 s 一刀（§2.2） | 9（+ 刀圈 13+1，够得着时） | 【模】 |

开头约 1.3 s（飞针 + 一次滑翔 + 一次下劈）约 30–35 点，约 25 /s；没有锯齿环时约 17 点、13 /s【推，由上表相加】。之后能不能再接飞针：飞针是水平的，主角弹到怪头顶以后就钩不到地面怪，要落回同一高度（或等对方跳起来）才行，所以"飞针–滑翔–下劈–滑翔"更像一个**开场 / 贴近的套路**，持续输出靠后面的下劈–滑翔循环或贴身滑翔（§2.2）【推】。

### 2.2 运动学模拟（kin_jit）

做法（`sim_cycles.py` / `sim_matrix.py`）：Forum 收割者参数，一帧一帧地按脚本按键；地面 y 3.0 两侧墙；目标是静止的受伤框（尺寸取自你两段录像的受伤框中位数，`hurtboxes.py`）；下劈命中 = reaper.json 下劈多边形在下劈阶段与目标重叠 → 下一帧注入 `EV_POGO`；锯齿环 = §1.4 的多边形和时间，每次生成一次主击 + 追加；横砍 = reaper.json normal / alt，挥刀后 0.083–0.208 s 有效。每种 12 s。"B*""C*"在取消那一帧把模型的攻击冷却 / 下劈恢复清掉，模拟游戏的 `DoAttack` 绕过（§3 指出的模型缺口）。Wanderer / Hunter 只换攻击时长、冷却、收招锁（0.25 / 0.3 / 0.1、0.35 / 0.41 / 0.15），**它们的下劈没有模拟**（Wanderer 的挥刀式下劈不在模型里），形状仍用收割者的【模】。

| 打法（收割者，除非注明） | 周期 | Choristor（1.52 × 2.93） | Envoy（1.16 × 2.01） | Clapper（3.59 × 3.90） | 主角脚离目标顶 |
|---|---|---|---|---|---|
| A 自然下劈弹跳（够得着才劈） | 0.87 s / 刀 | 10.5 /s | 10.5 | 10.5 | p50 +3.0 u |
| B 弹起 → 滑翔 → 取消成下劈（模型的冷却：等 0.5 s） | 0.53 s | 15.0 + 刀圈 1.2 | — | 16.5 + 3.5 | +1.0…+1.8 |
| B* 同上，按游戏的取消（绕过冷却） | 0.43–0.47 s | 12.8 + 刀圈 5.8 = **18.6** | 12.0 + 0 | 15.8 + 5.8 = **21.6** | +0.9…+1.4 |
| C 地面怪旁 2 u：小跳 + 滑翔、松跳、再跳（只有刀圈） | 0.60 s / 滑翔 | **23.3** | 23.3 | 23.3 | 地面 0–2 u |
| C* 小跳 + 滑翔、攻击取消（横砍）、再滑翔 | 0.57 s | 14.2 + 22.2 = **36.4** | 36.4 | 36.4 | 地面 0–3 u |
| C* 用 Wanderer 的攻击时间 | 0.50 s | 18.0 + 29.1 = **47.1** | 38.1 | 47.1 | |
| C* 用 Hunter 的攻击时间 | 0.50 s | 17.2 + 27.9 = **45.2** | 44.4 | 45.2 | |
| 对照：站着横砍（理论上限，不中断） | 0.5 / 0.3 / 0.41 s | 收割者 18、Wanderer 30、Hunter 22（v2 计量满 28.5） | | | |

（单位：伤害 / s；Needle 1 = 9，制作匣 1 个，刀圈 13 + 1。完整输出 `sim_matrix.jsonl`；B 这一行来自单独的 `sim_cycles.py --ctrl A,A2,B,B*`（Choristor）和 `--ctrl A2,B`（Clapper），Envoy 没跑。A2 = 自然弹跳、在弧顶附近就劈：太高够不着，反而更慢（1.0 s），所以 A 用"够得着才劈"。）

- **Hunter / Wanderer 的下劈–滑翔循环（没模拟，按 FSM 估）**：Hunter 的 DownSpike 前摇 0.1 s + 斜冲 ≤ 0.1 s（26 u/s），命中后一交还控制就能滑，0.158 s 后取消成下一次 DownSpike（`DoAttack` 不看 0.41 s 冷却和 0.25 s 恢复期）：若够得着，约 0.27–0.36 s 一刀，25–33 /s（v2 计量满再 ×1.3）；Wanderer 的下劈 0.05 s 左右就命中，但要等 0.1 s 收招锁才能滑，滑翔起手时已弹起约 2–3 u，而它的下劈没有自己的下冲（判定到中心下 2.68 u），多半要等落下来才够得着，估计 0.5–0.8 s 一刀，不比它站着砍（30 /s）强【推】。探针第 2 项能先确认"取消绕过冷却"这一条。
- 对飞行怪（Reed、Minister 悬停高度），A 一样是 10.5 /s；B / C 这两套脚本从地面出发、错过一刀就掉回地面再也上不去，数字没有意义（不代表打法不行）【模】。
- **结论**：(1) 收割者的下劈–滑翔循环把自然弹跳的 0.87 s 缩到 0.43–0.53 s（滑翔刹住上升 + 取消绕过冷却），但也只到地面横砍的水平；(2) 锯齿环从怪头顶往下打不太到地面怪（B* 17 次中 5 次），它的大头在"贴身同高起手滑翔"（C / C*），这时约是地面横砍的 2 倍，而且两侧 5 u 内的怪都吃；(3) 飞针每次只有 8 点，主要作用是把人送到"贴身同高"的位置【模】【推】。

### 2.3 伤害到底从哪来

| 部分 | 每次 | 频率上限 | 说明 |
|---|---|---|---|
| 飞针 | 4 + 4（Needle 1） | 冷却 0.16 s，但每次约 0.45 s 不能动、要丝、要同高 | 开场 / 追人用 |
| 滑翔本身 | 0 | — | 价值在刹住弹起、在空中重新瞄准、取消成攻击 |
| 下劈 | 9 | 自然弹跳 0.87 s；滑翔取消 0.43–0.53 s | 收割者这条循环 15–16 /s |
| 滑翔取消绕过攻击冷却 | — | 每次取消都出一刀 | C* 里横砍从 0.5 s 一刀变成每个滑翔周期一刀 |
| 锯齿环刀圈 | 13 + 1（制作匣 1） | 每次滑翔起手（约 0.5–0.6 s 一次） | 对贴身、同高的怪；两侧都打；**这才是"DPS 非常高"的来源** |

## 3. Forum 里的安全

- **主角在哪**（§2.2）：下劈–滑翔循环停在目标顶上 0.9–1.8 u（脚）；贴身滑翔在地面怪旁 2 u、离地 0–3 u【模】。
- **地面怪打得到头顶上方的主角**（R0 `strikes.json` 的攻击判定相对敌人位置的范围，加上敌人 transform 高度；敌人受伤框来自录像）【文】【录】：
  - Choristor（transform y≈4.87，框顶 5.95）：斩 y 到 +3.3（≈8.2）、鞭 +4.9（≈9.7）、跳 +11.2：头顶 1–2 u 的主角在鞭和跳的范围里；
  - Envoy（5.40，框顶 5.02）：斩 +4.3（≈9.7）、跳斩 +3.5（≈8.9）都够得着；冲锋 +0.6 够不着；
  - Clapper（7.45，框顶 6.92）：锤 +3.2（≈10.6）、跳（身体到 15.9）、rune slam 圆 r 7.19 中心 y≈3.3（顶≈10.5）都够得着；rune bomb 顶≈5.8 够不着头顶的人【文 forum.md §10】。
  - 贴身滑翔就在它们的水平判定里：Choristor 斩 p99 9.5 u、Envoy 斩 4.6 u、Clapper 锤 12.1 u【文 strikes.json】。
- **飞行怪**：Reed 刺 y −12.6…+8.4、防御反击 −8.1…+6.9；Minister 冲刺 −8.6…+12.6、格挡反击 −8.7…+9.4；Clawmaiden 斩 −7.9…+7.6；Maestro 斩 −4.6…+6.6【文 strikes.json】。R0 的 `below.json` 说 Bellbearer、Maestro、Tiny、Reed 的招在它们**正下方**比前方安全，Minister、Clawmaiden 会俯冲、正下方不安全【文 forum.md §12.4】；这个连招是在它们同高或上方，不在正下方，所以那条"正下方安全"用不上。飞针钩飞行怪本来就要和它同高（水平射线）——正好在它们刺 / 冲刺的主线上【推】。
- **无敌**：下劈命中给 8 物理步（0.16 s）对敌人伤害的无敌，并把碰到的、不是 HealthManager 根的 DamageHero（攻击判定、投射物）冷却 0.5 s【码 HeroDownAttack.cs:62-72、126；hero_constants DOWNSPIKE_INVULNERABILITY_STEPS 8】；模型对三种纹章都用 `pogo_invul` 0.16【文】（收割者的 `DownSlash New` 上是否挂 `HeroDownAttack` 没有查，crests.md 只核对过 Hunter / Wanderer 的下劈对象）。**飞针、飞针后的弹起、滑翔都没有无敌**（滑翔受击直接 `Force Cancel`）【码】【包】。飞针冲刺时被钩的那只怪只有根物体的 DamageHero 关掉（`SetDamageHeroAndRecord` 只取目标 GameObject 上的那一个组件），到 FSM 回 Idle（结束后约 0.2 s）才打开【码 SetDamageHeroAndRecord.cs】【包】；所以 R1 看到的"钩中后 0.5 s 内被同一只打中 5 次"是它的攻击判定或打开之后的身体，**R1 的结论"飞针中不无敌"成立**【文 forum.md §13.6】。
- **结论**：这个连招不躲招。下劈命中那 0.16 s 和"踩掉的攻击判定 0.5 s"是唯一的保护；在 Forum 里它只适合在对方出招后摇或 Garmond 吸引时用，规划器的支撑检查照常要过【推】。

## 4. 我们的录像里的证据（`combo_evidence.py`、`combo_timing.py`、`saw_hits.py`）

**你的收割者录像（`20261004_002749`，51 min，战斗 2,287 s）**【录】
- 下劈 309 次起手、218 次命中（`DownSlash New` 每下 9）；按键到命中中位 0.183 s。
- 飞针 37 次（战斗中 34）：两下全中 17 次（8 点）、一下 5 次、没中 15 次；按键到第 2 下 0.317–0.400 s（中位 0.367，n 21）；飞针命中后 0.6 s 内接滑翔只有 2 次（0.23、0.42 s），0.8 s 内接下劈 5 次（0.63–0.78 s）；飞针后 0.5 s 内掉血 6 次（37 次里）。
- 下劈命中后同一次腾空里接滑翔 57 次（延迟中位约 0.48 s，最短 0.125 s），其中 28 次滑翔后又下劈（0.40–0.83 s）。滑翔到下劈：中位 0.667 s，下劈时的片段多是 `Airborne` / `Umbrella Deflate`——**你是等滑翔收起来再劈，不是在充气阶段取消**。
- 下劈到下一次下劈（同一次腾空）：中间没滑翔中位 0.817 s（最短 0.458）；中间滑翔过中位 1.33 s（1.03–1.81）。同一次腾空 ≥ 2 次下劈命中 42 段（最长 7 次、63 点、5.0 s）。
- 下劈起手到滑翔起手最短 0.292 s。

**R1 数据跑（收割者，数据策略）**【录】
- 波次起点运行（4 段录像）：飞针 111 次，两下全中 28、一下 19、没中 64；按键到第 2 下 0.30–0.42 s（中位 0.35）；飞针命中后接滑翔 9 次（0.133–0.575 s）；飞针后 0.5 s 内掉血 2 次（这个窗口比 forum.md §13.6 的"同类怪 0.5 s 内"宽，数不同）。
- Envoy 专场（5 段）：下劈 349 次命中；**下劈起手到滑翔起手最短 0.167 s（201 次里 30 次 < 0.3 s）**——弹起一交还控制就能滑，不受 0.3 s 收招锁挡（§1.2）；滑翔到下劈中位 0.27–0.32 s，下劈时片段大多是 `Umbrella Inflate`（攻击取消）；下劈到下劈中间滑翔过中位 0.72–0.78 s、没滑翔中位 0.55–0.58 s（最短 0.43 s）。

**你的 Wanderer + 锯齿环（`20261004_133855`，路线配装半速）**【录】
- 锯齿环在第 6123 帧装上，之后几次和护佑钟（`Bell Bind`）互换（67827、96700、121152、122472、173215、175122 帧）；80 次滑翔里 70 次带锯齿环。
- 61 次锯齿环命中（攻击类型 Generic）：`Damager R` 52、`Damager L` 9；主击 13（Clapper 上 15）、追加 1；33 次主击按目标：Clapper 24、Reed 4、Clawmaiden 2、Tiny 2、Minister 1。命中出现在滑翔片段起手后 0.158–0.408 s（主击 0.158–0.233 s，追加的在其后约 0.1 s）。
- 29 次滑翔打中东西：26 次一只（24 次主击 + 追加、2 次只有主击：对方先死了）、3 次两只（例：f168271 同一次滑翔身后、前方各打中一只 Clapper）。命中时主角 transform y 6.1–9.6（脚离地 1.6–5 u），目标在水平 3–7 u。
- 合计 505 点（这段战斗 1,413 s；同段钉子 + 刀圈约 9,650 点）。你只是偶尔用（70 次 / 23.6 min）；对 Clapper 的 24 次主击说明"Clapper 旁边起跳滑翔"在实战里打得中。
- 你的另外两段 Wanderer 录像（`012300`、`091214`）没有锯齿环，下劈很少（7 / 38 次起手）。

## 5. 规划器要什么才能自己找到它；K1

**规划器（forum_planner_plan R7 之外再加）**
1. **kin_jit 的滑翔攻击取消**：现在模型在 Inflate ≥ 0.075 s / Float / Deflate 按攻击时 `regain` 后走普通出刀判断（`can_attack`：攻击冷却、下劈弹起 / 恢复、正在攻击都要满足，而且按键要在下一帧还按着才从队列出刀）【码 kin_jit.py:1305-1308、1966-2009】。游戏里是无条件出刀（`SetStartWithAttack` → `DoAttack`）。不改，规划器在冷却期间看不到 B* / C* 这类周期。
2. **锯齿环的伤害形状**：在攻击表里加一个槽（建议 `knowledge/1.0.30000/attacks/tools.json` 的 `glide_spike`）：两块多边形（§1.4，相对主角 transform、按朝向镜像、y 取反后的值）、有效时间（滑翔起手 + Antic 长度之后 L 0.05–0.175 s、R 0.10–0.20 s）、每只敌人每次一击、追加 1 点 0.1 s 后、伤害 = 8 × (1 + 0.6 × 制作匣) × 敌人等级系数；装备了才放（审计确认的配装）。命中都在滑翔按键后 0.13–0.28 s，**在 0.6 s 视野内**，伤害评分要把这些延迟命中算进去。
3. **`M_HARPOON`**：按 §1.1 的阶段（Antic 0.15、Throw 0.15、冲刺 ≤ 0.1 s @70 u/s 朝针 + (0, 0.6)、Catch 0.1、之后 harpoon 弹起）；目标选择 = 朝面向的水平射线（3 个敌人高度、10.5 u，地形更近就钩墙）；冲刺末端 x 吸附到命中点；两次半刀伤害（第 1 次在 Antic 结束时）；丝 −1 / +1；冷却 0.16 s（落地清零）；受伤框 `HeroBoxHarpoon`；被钩怪的身体伤害关闭窗口；**不无敌**。规划器的候选键里加"飞针"（方向键 + clawline）。
4. **视野**：B* 周期 0.43–0.47 s、C* 0.50–0.57 s，都在 0.6 s 内，规划器的局部搜索能看到一整个周期；"飞针 → 滑翔 → 下劈"开场约 1.3 s，超出 0.6 s，要做宏（R7 的 CLAWLINE_TO 后面接"滑翔 + 取消"）或者靠价值函数【推】。
5. 滑翔起手不能在"快落地"时（脚下 1.1 u 内有地、vy ≤ 0）——模型已有（`glide_ground_ray` 1.1）【文】。

**K1：锯齿环 vs 护佑钟（蓝槽）**
- 锯齿环：贴身打法下对地面怪约 +18–29 /s（C / C* 的刀圈部分，制作匣 1 个），两侧 5 u 内的怪都吃；对飞行怪要和它同高才打得到。Forum 里地面怪的血量：Choristor 4 × 55、Envoy 38、Clapper 3 × 230，共 948，占 14 波固定敌人 1,977 的 48 %（Clapper 690，35 %）【文 forum.md §2】【推】。拿 Clapper 当例子（230 HP，1 级系数 1.15）：站着横砍每 0.5 s 10 点 = 20 /s ≈ 11.5 s 一只（不算躲招）；C* 每 0.57 s 横砍 10 + 刀圈 15 + 1 ≈ 46 /s ≈ 5 s 一只【推，由 §2.2 换系数】——但 C* 的位置正在锤和 rune slam 里。
- 代价：230 念珠 + 第 3 块工艺金属（DESIGN 预留 2 块）+ 去 Underworks 建筑师（`Under_17` 是否在 S23 路径上没查）+ 一个蓝槽：Hunter_v2 的 2 个蓝槽现在是裂痕面具 + 护佑钟，装锯齿环就要让掉护佑钟；Reaper 不花 Locket 只有 1 个蓝槽（裂痕面具）；Wanderer 不花 Locket 没有蓝槽【文 forum_tools §1、§3.3】。
- 护佑钟的作用是"被打断的 Bind 不掉血"【文 forum_tools §3.3】，和输出无关。
- **建议**：锯齿环值得进 K1 的 A/B（Hunter_v2：面具 + 锯齿环 对 面具 + 护佑钟），但前提是第 1、2 条模型改动先做、探针确认 §1.4 的形状和时间（§7）；度量看每波用时和每分钟受击，而不是只看 DPS。没做完这两步之前不要为它改路线（230 念珠 + 金属）【推】。

## 6. 和现有模型 / 文档的出入

- kin_jit 的滑翔攻击取消（§5 第 1 条）：模型把它当普通出刀，游戏是无条件出刀【码】。
- kin_jit 收割者下劈不设 `ATTACKING`：和游戏一致（FSM 夺控时 `ResetAttacks`），R1 的 0.167 s 下劈→滑翔佐证【码】【录】。（本文模拟的第一版曾按 0.3 s 收招锁去挡滑翔，是错的，已改。）
- forum_tools.md §2.4 的"伤害数值和判定范围还没读"：本文补上（§1.4）；"开披风时旋转利刃伤周围敌人"准确地说是"每次滑翔起手（Antic 播完）一次"。
- forum_human_demo.md §8 的"飞针 34 次，命中 38"：34 是战斗中的按键数，38 是命中事件数（`Harpoon Damager` 17 + `Harpoon Dash Damager` 21）；按按键算 37 次（34 次在战斗中），22 次至少中一下【录】。

## 7. 待实测 / 未核实（探针已写，未运行）

探针 `brain/ssbot/probes/combo_probe.py`（训练副本，savestate `fo_r1_w0`，LethalBlock + 存档抑制，可选 `--invincible`）：
1. `saw`：锯齿环的实时多边形（slash.dump 加刀圈路径）、L / R 的有效帧、命中与追加伤害——确认 §1.4 的 y 取反和时间（离线证据是 31 / 33 次首击）。
2. `bypass`：横砍后 0.3 s 滑翔、充气 0.08 s 时按攻击，看是否早于 0.5 s 冷却出刀；对照组不滑翔。
3. `claw`：飞针的逐帧位置、两次伤害、吸附点、弹起高度、交还控制后几帧能滑翔、被钩怪的身体在冲刺中是否伤人。
4. `rprlock`：收割者下劈后第 k 帧按跳，最早几帧能滑翔（预期：交还控制即可）。

其他未核实：Wanderer 下劈的弹起配置（`HeroSlashBounceConfig` 是否按纹章不同）；Hunter / Wanderer 的下劈–滑翔循环没有模拟（模型没有挥刀式下劈）；锯齿环 `NoiseMaker` 等对敌人行为的影响未查；`Under_17` 是否顺路未查。

## 8. 复现

```
sh C:\ssbot\sandbox\combo_scripts\ux.sh fsmx.py tpl fsmtemplates_assets_shared.bundle hornet_umbrella_float > fsm_umbrella_float.txt
sh C:\ssbot\sandbox\combo_scripts\ux.sh fsmx.py tpl fsmtemplates_assets_shared.bundle hornet_harpoon_dash > fsm_harpoon_dash.txt
sh C:\ssbot\sandbox\combo_scripts\ux.sh fsmx.py tpl fsmtemplates_assets_shared.bundle crest_attacks > fsm_crest_attacks.txt
sh C:\ssbot\sandbox\combo_scripts\ux.sh spike_dump.py localpoolprefabs_assets_shared.bundle Tool_brolly_spike > spike_glide.txt
sh C:\ssbot\sandbox\combo_scripts\ux.sh anim_dump.py localpoolprefabs_assets_shared.bundle Tool_brolly_spike > anim_spike_glide.txt
sh C:\ssbot\sandbox\combo_scripts\ux.sh laghits.py localpoolprefabs_assets_shared.bundle "damager l" "damager r"
sh C:\ssbot\sandbox\combo_scripts\ux.sh hero_clips.py harpoon umbrella "down slash" downspike
# 录像与模拟（工作区 brain 环境；NUMBA_NUM_THREADS=4）
sh C:\ssbot\sandbox\combo_scripts\bx.sh <worktree> C:\ssbot\sandbox\combo_scripts\combo_evidence.py C:\ssbot\data\human\20261004_002749 ... --json evidence_human.json
sh C:\ssbot\sandbox\combo_scripts\bx.sh <worktree> C:\ssbot\sandbox\combo_scripts\combo_timing.py <sessions / run dirs>
sh C:\ssbot\sandbox\combo_scripts\bx.sh <worktree> C:\ssbot\sandbox\combo_scripts\saw_hits.py C:\ssbot\data\human\20261004_133855
sh C:\ssbot\sandbox\combo_scripts\bx.sh <worktree> C:\ssbot\sandbox\combo_scripts\saw_geom.py C:\ssbot\data\human\20261004_133855
sh C:\ssbot\sandbox\combo_scripts\bx.sh <worktree> C:\ssbot\sandbox\combo_scripts\sim_matrix.py > sim_matrix.jsonl
# 探针（训练副本，排期由 lead 定）
cd brain
..\scripts\uv.cmd run python -m ssbot.probes.combo_probe --instance 3 --savestate fo_r1_w0 --trials 12 --invincible
```
