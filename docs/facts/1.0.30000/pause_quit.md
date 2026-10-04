# 1.0.30000 暂停 / 退出压力测试（M2 W5，DESIGN §3.7.5 G1）

链 H（工作区 `wf_c0d56d51-4cb-4`，实例 4，种子 100000–104999）。上一轮（11b4ca0，`20261002_180411_..._inject`）：112 次注入受击全部暂停并退到主菜单，暂停延迟 p99 2 帧、最大 4 帧，0 外来按键、0 意外取消暂停、0 错误确认；但只有 3.6 % 落在难点时刻 ±3 帧内（目标 30 %）。

## 1. 难点时刻的时序（离线，录像实测）

数据：`20261002_190611_BellBeast_eval_planner_oracle`（代码 11b4ca0，oracle）前 6 场；按键沿取 STATE `act.hf.latched`，事件取 STATE `ev`。

| 时刻 | 从按键锁存到事件（帧） | 说明 |
|---|---|---|
| 丝矛命中（"Needle Damage"） | 18 / 19 / 20：12 / 13 / 1 次（共 26） | 命中 15 HP；投出后不受按键影响，可提前预测 |
| 横砍 Slash / AltSlash 命中 | +1：38 / 56，+2 / +3 / +4 其余 | |
| 上砍命中 | +3 到 +7 | |
| 下劈弹起（downSpikeBouncing 起始） | 下 + 攻击 → +11：12 / 20，+8：5 / 20，其余 7 / 12 / 13 | 47 次下劈起势只有 20 次弹起 |
| 击杀 | 6 场：丝矛 4、Slash 1、AltSlash 1 | 击杀帧有 BossDeathSlow 冻结（约 96 帧，暂停门关闭） |

- 这些录像里普通命中不产生冻结事件（只有 BossDeathSlow），所以"命中"本身不算难点时刻。Bell Beast 没有 BossStun；cstate `parrying` 6 场 0 次。
- 上一轮只有 3.6 % 的原因：注入的受击打断了主角自己的攻击，计划中的弹起 / 击杀就不再发生（弹起类注入都落在 "DownSpike Antic"）；"起手帧 + 2" 对下劈也太早（实际 +8 到 +13）。
- 弹起后几帧内敌人的伤害进不来：弹起把 `downspikeInvulnerabilitySteps` 设为长值（STATE `hero.cstate_int[1]` 起始帧读 8，每个物理步减 1，约 10 帧后到 0；`DOWNSPIKE_INVULNERABILITY_STEPS_LONG = 10`），TakeDamage 对 ENEMY 直接返回。实测在起始 +2、+3 帧注入的 4 次受击全部被拒（take_health_calls 0）。被拒的受击仍产生 "damage" 事件，规划器把它算作"未预测命中"，两次就触发 Q4 退出（不是注入的故障）。所以弹起只做"触发"类故障，所有受击注入都等主角能吃伤害时（无下劈无敌步、非 invulnerable、无弹反无敌）。
- 拼刀（parrying 起始或无命中的弹刀后坐）对 Bell Beast 太少：5 次试验 20 s 内都没等到，权重设 0（代码保留给其他遭遇）。

## 2. 注入器与测量（`ssbot/train/hit_injection.py`、`ssbot/tools/pause_stress.py`）

- 三类故障（每场一个）：**受击**（hurt.special 打到 1 HP，Q1）；**触发**（`Supervisor.inject` 的退出触发 QF，不扣血：暂停循环从游戏和按键路径的当时状态开始，通常暂停门开着、规划器的键还按着）；**菜单**（触发后同一 tick 或下一 tick 受击：受击在循环第一次 Pause 到达游戏的前一帧或同一帧落地，即菜单本应打开的那一帧）。
- 难点时刻：击杀（受击：击杀首帧；触发：偏移 −3..+2，负偏移只用于规划器判为命中的已出手攻击：丝矛按下 + 19 + 偏移，横砍按下帧）、弹起（触发 +0..2）、丝矛起手（NeedleThrow 首帧，受击 +0..1 / 触发 +0..2）、菜单。权重 弹起 3 : 丝矛 3 : 菜单 2 : 击杀 1，占 `--inject-hits SHARE`（0.5）；其余为覆盖类：空中 / 攻击 / 下劈中的受击，以及"在途按键"触发（发往 f+1 的 ACTION 按下了一个 f 时未锁存的键：按键泄漏的前提）。`SSBOT_INJECT_KINDS=menu,...` 只抽指定种类。
- `pause_stress`：故障帧 = 受击的 damage 帧，或触发的第一个 PAUSE_PENDING 帧；难点 kill / stun / bounce / clash / cast / hurt / menu（菜单只对含受击的故障算：受击离循环第一次 Pause 锁存帧 ≤ 3 帧）；延迟 = 暂停帧 − 暂停所在那段"门开"区间的第一帧；菜单可见帧（第一个暂停帧到主菜单）上的按键：菜单可接受输入前只允许 Pause，之后只允许 Pause / 上 / 下 / 确认；`--natural` 把没有注入的监督器暂停也算进来（基线）。

## 3. 按键泄漏进暂停菜单（HoldFilter）

- 机制：按键路径（oracle HoldFilter，最终 inputd 同规则）保留每个边沿并按最短按下 / 松开 2 / 2 帧重放。规划器在 f−1 发给 f+1 的 ACTION 仍在途；暂停机在 f 发出的第一次 Pause（落在 f+2）可能与 f+1 刚按下的键同帧（该键要到 f+3 才能松开），或被最短松开推迟的再按下在菜单里才触发。受击注入看不到它：受击关门 15 帧，过滤器早已放空。
- 基线（`pause_stress --natural`，没有保护的代码，监督器自己的 62 次暂停：20261002_152649 / 162847 / 171806 / 190611 / 210643）：7 次暂停帧上有游戏键（152649：6，162847：1），菜单可见帧上共 10 帧有游戏键（左 8、右 1、**攻击 1**：X = 菜单取消），3 次在暂停帧新按下；较新的 171806 / 190611 / 210643 只有 8 次暂停，0 次。
- Python 侧修复：`ssbot/safety/key_guard.py`。从 STATE `act.hf` 出发，把已发出但尚未生效的 ACTION（`act.target` 之后到 f+1，包括错过本帧、要和下一个一起生效的那一个）按三种落地方式重放；只有 Pause 落地那一帧没有其他键锁存、也没有排队边沿时，暂停循环才开始按（`PauseCues.keys_clear`，最多等 `keys_wait_s` 0.25 s，过时照按并记录）。
  - 模拟按键路径（`tests/test_key_guard.py`，2000 次，规划器随机键流、10 % 的 ACTION 晚一帧）：不加保护 706 次泄漏；在途列表只取 f+1 时 56 次；完整保护 0 次。
  - 实战（第 4 节，30d542b）：13 / 99 次暂停的第一次按下等了 1 帧（"在途按键"触发 11 / 11，弹起触发 2 次），0 次超时，这 13 次的延迟都是 3 帧（其余 2 帧）；暂停帧和菜单可见帧上 0 个游戏键。
- oracle 侧（提交 10d3948，**只编译未部署**）：ACTION 第 5 个元素 flags，EXCLUSIVE = 1：从该 ACTION 的帧起，掩码外的键立即松开（必要时短于最短按下）并丢弃排队边沿（`HoldFilter.Exclusive`，`input.stats` 新计数 `released_early`）。暂停机发出的所有 ACTION 都带它；掉线看门狗的 Pause 点按也改用它（原来 `ReleaseAllNow` 保留最短按下，刚按下的键会和 Pause 同帧）。HELLO 新增 `action_flags: ["exclusive"]`；旧 oracle 只读前 4 个元素，所以现在发 5 个元素也安全。`oracle/tests/InputLogicCheck` 全部通过。Python 保护保留（按普通过滤器建模），两层独立；部署后 Python 的等待（0–2 帧）可以改为按 EXCLUSIVE 建模而取消。
  - 集成分支 m2-integration-6 的修正（审查 10d3948 时指出：暂停机自己的按键也带 EXCLUSIVE，若其点按只锁存了一帧——第一个 ACTION 晚到、与下一个同帧生效——下一个 EXCLUSIVE ACTION 会把它切到短于最短按下）：`HoldFilter.QueueExclusive` 只切断本段 EXCLUSIVE 之外的键（规划器的键），本段 EXCLUSIVE ACTION 自己要过的键照常受最短按下 / 松开约束；普通 ACTION（规划器恢复）清空这一集合（`EndExclusive`）；掉线看门狗的 Pause 点按先清空，仍切断所有键。`InputLogicCheck` 新增 `ExclusiveSparesTheLoopsOwnKeys`（全部通过），`dotnet build -p:Deploy=false` 通过，**仍未部署**。
  - 集成修复轮：KeyboardInjector 进入过滤器的三条路径改为调用 HoldFilter 的方法，让 `InputLogicCheck` 跑到同一段代码：普通 ACTION `TryQueueMask` = `QueuePlain`（`EndExclusive` + 两次 `Push`），EXCLUSIVE ACTION = `QueueExclusive`，看门狗 `SetMaskExclusive` = `QueueExclusiveCutAll`（`EndExclusive` + `QueueExclusive`；现在先校验掩码，被拒的请求不再结束这一段）。新检查 `InjectorExclusiveWiring`：同一段内自己的键被保留；中间有普通 ACTION 时下一段切断它；看门狗的 Pause 切断暂停机自己的键。全部通过，仍未部署。

## 4. 实战（实例 4，oracle，`--real-quit 1.0 --inject-hits 0.5 --threads 4`）

| 运行 | 代码 | 试验 | 说明 |
|---|---|---|---|
| 20261002_225013 | 10d3948 | 13 | 试跑（实例 4 首次：先补沙盒 1 号槽） |
| 20261002_225739 | d7d3585 | 11 | 试跑（弹起受击 +1 被拒 → Q4） |
| 20261002_230409 | f4de530 | 24 | 试跑（弹起受击 +3 仍被拒；拼刀全超时） |
| 20261002_231847 | a92f547 | 4 | 中止（改在途按键种类） |
| **20261002_232051** | **30d542b** | **100** | **测量块** |
| **20261003_001326** | **e34da27** | **93** | **最终代码的检查块**（第 93 次后游戏进程无日志地消失，见下） |

**测量块 20261002_232051（30d542b，100 次，99 次有注入）**：
- 难点时刻 ±3 帧：**52.5 %**（不算菜单 43.4 %）。按种类：弹起 20 / 20，丝矛起手 19 / 19，击杀 4 / 4（触发 −1 两次、受击 +1 / +2），菜单 9 / 9（全是 −1：受击先于按下一帧，按下被 disablePause 吞掉，循环在门开后重按）；覆盖类 0。偏移分布 −1：12、0：12、+1：13、+2：16、+3：1。
- 99 / 99 暂停并退到主菜单；暂停延迟（从门开起）p50 2、p99 3、最大 3 帧，0 次超过 6；到主菜单最多 5.12 s。
- 菜单可见帧上的游戏键 0、暂停帧游戏键 0；意外取消暂停 0，错误确认 0；循环自己的 Pause 在暂停后最多 2 帧（在途那一次）。
- 3 次 HARNESS_FAIL，都不是暂停循环的问题：2 次是测试框架把"暂停先于击杀开始、击杀后退出"记成了记录的默认值（ep 26 / 39，已修 45c8ebb，回归测试 `tests/test_episode_kill_pause.py`）；1 次（ep 87）大脑 14 帧没发 ACTION，oracle 的掉线看门狗按了 Pause（"paused unasked"；当时我在同机低优先级预热另一个工作区的 numba，另有其他代理在跑，CPU 约 73 %）。
- 每次试验平均 30.4 s（受击 / 触发类 25–32 s，击杀类 83 s，含真实退出和读档）。

**检查块 20261003_001326（e34da27：上述修复全部在内，93 次）**：
- 难点时刻 ±3 帧：**49.5 %**（不算菜单 38.7 %）。弹起 15 / 15，丝矛起手 17 / 17，击杀 4 / 6（两次击杀前触发：攻击没打出击杀，QUIT），菜单 10 / 11。
- 菜单故障的两种落点都测到：受击先于按下一帧 5 次、与按下同一帧 5 次。同一帧的 5 次里按下全部被吞（受击的 disablePause 赢了这一帧），循环在门开后重按，门开 + 2 帧暂停，与先一帧的情况相同。另 1 次键保护等了 2 帧，受击落在按下之前 3 帧以上（不算难点）。
- 93 / 93 暂停并退到主菜单；延迟 p50 2、最大 3 帧；菜单可见帧游戏键 0；意外取消暂停 0；错误确认 0；被拒的注入受击 0（等无敌结束后再注入）；HARNESS_FAIL 0；击杀前开始的暂停 4 次都记为 CLEAR（"quit after the kill"）。
- 键保护等待：9 次（在途按键 8 / 8 等 1 帧，菜单 1 次等 2 帧），0 次超时。
- 第 93 次试验后（01:02）实例 4 的游戏进程消失：player 日志在主菜单读档途中直接截断，没有崩溃转储、没有应用程序事件，启动器登记表里还在；原因不明（不是本链的进程操作）。worker 随之 ConnectionReset 退出。已用启动器重启实例 4（新 player 日志覆盖了旧的；截断前最后一行是 "MenuButton missing flashEffect!"）。

**合计**（已分析的 236 次有注入的试验：试跑 22 + 230409 的 22 + 232051 的 99 + 001326 的 93；中止块 231847 的 4 次未分析）：全部暂停并退到主菜单，暂停延迟最大 4 帧（230409 一次击杀受击：BossDeathSlow 结束后 4 帧），其余最大 3 帧；菜单可见帧游戏键 0，意外取消暂停 0，错误确认 0。

## 5. 10⁴ 次的规模（G1）

- 时长估计：30.4 s / 次（232051 的 100 次，含真实退出、回主菜单、读存档、读 savestate；击杀类 83 s 占 5 %），单实例 10⁴ 次约 **84 h（3.5 天）**；本链种子段只剩 4400 个（100600–104999），约 37 h。到 10⁴ 需要另一个种子段，或多实例并行（每实例同样约 30 s / 次）。
- 已启动的后台运行（脱离会话，Win32_Process Create）：工作区 `C:\ssbot\live_pq_e34da27`（e34da27，numba 已预热），`C:\ssbot\sandbox\pq_campaign_start.cmd C:\ssbot\live_pq_e34da27 100600 4400 C:\ssbot\sandbox\pq_campaign.log`，运行目录 `C:\ssbot\data\runs\m2\20261003_010522_BellBeast_eval_planner_oracle_inject`。停止：在 `C:\ssbot\live_pq_e34da27\brain` 里 `..\scripts\uv.cmd run python -m ssbot.tools.combat_run stop <运行目录>`（或 STOP_AGENTS），当前这一次结束后退出。实例 4 在运行期间锁着 SsOracle.dll：部署前先停。汇总：`..\scripts\uv.cmd run python -m ssbot.tools.pause_stress <运行目录> --quiet --json <运行目录>\pause_stress.json`。

## 6. 发现并修复的缺陷

1. **监督器 Q1 在"确认为空"的支撑下不触发**（ep 35）：受击打到 1 HP 时 Boss 正在地下（支撑被确认为空，hits_to_death = UNBOUNDED），Q1 不触发、风险档保持 GREEN，规划器继续操作 15 帧，直到 Q4 才暂停。修复（10bfb66）：支撑确认为空时，Q1 按本遭遇最坏已知事件（worst_known_damage、本次受过的最大伤害；完好的碎面具照常抵挡）计算，于是 1–2 HP（对 2 格伤害）在地下阶段就暂停，而不是等 Boss 冒出来。行为变化：以前地下阶段还能回血继续，现在直接退出（与 Boss 可见时 h = 1 立即 Q1 一致）。门槛 / 实战日志里（171806、190611、210643、180411、230409 的记录行）0 次出现，只有这一场。
2. 测试框架：暂停先于击杀开始时结果记成 HARNESS_FAIL（45c8ebb）。
3. 测试框架：新实例的沙盒没有 1 号槽，Enter 开了新游戏，worker 在 Tut_01 等进入游戏超时；读到的菜单状态还是 SAVE_PROFILES（67cbaca：PLAYING 时不看菜单状态，改为读存档点）。
4. 注入器：弹起受击被无敌拒绝并累积成 Q4；拼刀等不到；只按"任意锁存键"的触发从不触发保护（f4de530、a92f547、30d542b、e34da27）。
5. oracle 掉线看门狗的 Pause 点按可能与刚按下的键同帧（EXCLUSIVE，待部署）。
- 双重 Esc 关菜单、卡在暂停、错误确认：本轮所有试验 0 次。

## 7. 低血量：先回血，h ≤ 1 在受击后的窗口里退出（任务 Q，DESIGN §3.7.4 Q1 / Q1a，你 2026-10-03 的规则）

工作区 `wf_9edc2274-509-2`，实例 4，种子 105000–109999，代码 5126afd … （第 7.5 节列提交）。

### 7.1 实现

- **h 的定义**（`safety/supervisor.py`）：对支撑算 hits_to_death；支撑被确认为空（0.8 s 内什么都打不到，例如 Bell Beast 在地下）时改为对本遭遇最坏已知事件算（`worst_known_damage`、本次受过的最大伤害，完好的碎面具照常抵挡），`h_basis = "worst known"`。风险档、Q1、Q1a、Q3、Q5、Q6、Bind 提交条件里的"值得回血"一项都读这个 h。10bfb66 只在 Q1 里这样算；以前 3 HP + Boss 在地下时 h = UNBOUNDED、风险档 GREEN，Bind 提交条件因"HP 3 > max − 3 且 h > 2"判为不值得——恰好在最安全的空档里不回血。
- **Q1（h ≤ 1）**：PAUSE_PENDING + 退出，不尝试 Bind（PAUSE_PENDING 只允许躲避；战术层在 h ≤ 1 时也永不要求 Bind）。原因写明是否受击后（1.1 s 内有受击 = 受击后窗口；否则 = 霜冻、挂起伤害等，按第一个能暂停的帧）。修复轮（f9dcbba）：掉血只有同时看到受击击退才算"受击"（`SupervisorInput.hurt`：cState recoilFrozen / recoiling，视觉 = 主角 hurt 姿态）。TakeDamage 的 StartRecoil 在受击当帧就置 recoilFrozen（抽查 112406 / 114708 / 014409 / 053033 的 28 个受击帧，28 / 28 当帧 hurt 且掉血）；霜冻、DamageTag 走 DoSpecialDamage 的只扣血路径（HeroController.cs 5184–5231），没有击退、冻结、关门和无敌，所以算"无受击"，立即按。
- **战术层读本 tick 的 h**（修复轮 f9dcbba）：战术层和安全过滤在本 tick 监督器 step 之前运行（step 要用规划结果），以前读的是上一 tick 的决定；受击把 h 从 2 打到 1 的那一 tick，上一 tick 的决定还写着 h = 2、先回血，战术层可能要 Bind，只是因为同一 tick Q1 让暂停机的按键整个替换了规划器的按键才没发出去。现在 PlannerPolicy 给战术层 `SupervisedControl.h_now`（`Supervisor.peek_h`：同样的输入、不改状态），先回血也按这个 h 现算。
- **Q1a（h ≥ 2 且 HP < max）**：`Restrictions.heal_first`，任何风险档都设（以前只是 YELLOW / RED 的标志，没人读）。战术层（`combat/tactics/modes.py`）：满足 §3.5.6 提交条件（丝 ≥ 9、T_min ≥ 1.37 + 0.15 s、HP ≤ max − 3 或 h ≤ 2、不在 PAUSE_PENDING；击退包络内的危险物由规划器的 Bind 推演检查）就原地 Bind，4 / 5 HP 也算（以前剧本的 hp_missing_min = 2 挡掉了 4 / 5）；否则若只差"位置"，去剧本里已核验的安全点（`bind.safe_spots`，`SafeSpot.usable`：有覆盖图核验、在地面、不需要额外能力，且预测也同意那里 T_bind + δ_b 内打不到），走过去（每一步过规划器的支撑检查）再 Bind（模式 HEAL_SPOT）；都不行就继续打，照 Q3 / Q6 处理（修复轮起 h = 2 不再有 Q6，见 7.7）。Bell Beast 没有可用安全点：覆盖图（movement_kinematics.md 第 4 节）里地面全被覆盖，只有两扇门内侧墙上的贴墙点（左 1.44 u、右 1.59 u），需要贴墙能力，路线在 S03 没有，规划器也没有贴墙原语。

### 7.2 受击后的暂停窗口：哪一帧能暂停

- 受击冻结：pause.blk = 3（DISABLE_PAUSE | TIME_SLOWED），时间缩放 0 持续 8–9 帧，然后 0.1 s 线性回升（ts 0.17、0.33、0.5、0.67、0.83，约 60 % 的受击还有一帧 0.999 仍关门）。记 G = STATE 第一次显示门开（blk 0）的帧。2143 次关门的受击（数据运行 20261001_122249 i0_000 / i2_000、实战 152649 / 171806 / 053033 各两路）：2138 次 G 在受击后 0.213–0.267 s（p50 0.232；13 / 14 / 15 / 16 帧 = 327 / 1286 / 524 / 1 次）；另 5 次是 Bind 中受击（BindBreak 冻结，G 在 0.532–0.550 s）。从回升的某一帧（ts）到 G：(1 − ts) × 0.1 s − 0.003 … + 0.022 s（2895 帧）。
- **第一个能暂停的帧是 G + 1，不是 G**：时间缩放和 TIME_SLOWED 在冻结协程里恢复，晚于 InputHandler 的 Update。实测（72baaf3 的第一版按回升斜率把按键对准 G，20261003_111244）：落在 G（+15，那一帧 STATE 已显示 blk 0）的按键全部被丢弃，8 / 8 次 h = 1 试验都在下一次按键（+20 / +21）才暂停；修正后（8beb806）16 / 16 次落在 G + 1（+16）就暂停（见 7.4）。链 H 只看观测到的门时按键落在 G + 2（+17）。
- 实现（`safety/pause_quit.py`）：`PauseCues.gate_open_at` = 预测的第一个能暂停的帧；在它之前不发新按键（按早了会被丢弃、按住跨过开门又没有新边沿，要多等一整个 6 帧周期），到点后即使看到的门还关着也照按。oracle：只在回升的最后一个仍关门帧（blk = 3、ts ≥ 0.999、主角无敌中）预测"G + 1 = 两帧后"，于是 60 % 的受击暂停落在 G + 1，其余（0.83 直接开门）照旧由观测到的门落在 G + 2；更早的回升帧分不清这两种，不预测。视觉视图（`train/supervision.py`，只读延迟视图）：从它看到的受击（HIT_TAKEN 或 HUD 血量下降，且主角在受击击退中；修复轮起没有击退的掉血 = 霜冻 / DamageTag，不等，立即按）的采集时间起加 `POST_HIT_OPEN_MAX_S` = 0.285 s（G 最大 0.2668 s + 1 帧）；Bind 中受击（视图看到主角在 Bind）加 0.57 s。于是不论视图延迟 k = 2–4，第一次按键都落在 G + 1 之后 0–3 帧（盲按节奏是 0–5 帧）。
- 无敌：受击后 i-frame 1.10–2.08 s（pause_window），注入的受击 1.2 s（72 帧）；h = 1 的暂停落在受击后 0.264–0.268 s，暂停时还剩 0.925 s 无敌。

### 7.3 回放：录像里的低血量决定（Bell Beast 实战，2026-10-02 起，oracle 与 degraded_dust）

`tools/lowhp_replay`（a2d0ec9）：61 个 eval 运行（20261002_* / 20261003_* 的 oracle 与 degraded_dust，不含还在跑的 074533）里每一场 Q1 / Q6 退出和每一场战斗中回过血的，用本代码的 PlannerPolicy 开环回放（实况按键作前缀；受击前 60 帧起完整 tick，之前只走感知路径），从"打到 h ≤ 2 的那次受击"到实况的暂停（或实况的 Bind）为止，比较三者：实况（各运行自己的代码，23 个版本）、新规则、旧规则（main 5a83283）的反事实（新规则选了 Bind 的那一 tick，旧规则只有在 HP ≤ max − 2 且 h 按支撑算时才会选；退出两者相同，10bfb66 已经让 Q1 用最坏已知事件）。新 Bind 再用录像核对：支撑的 T_min，以及 Bind 全程（决定帧 + 2 起 92 帧）录像里所有威胁碰撞体到主角框的最小距离（站着：+2 帧的框不动；空中：Bind 推演的框）；实况暂停后世界冻结，之后的帧算删失。耗时 29 min（11:25–11:54，低于正常优先级，NUMBA 4 线程；同时实例 4 在跑实战检查，CPU 约 75 %）。

结果（`C:\ssbot\sandbox\pq_lowhp_replay.json`，324 场，35 个运行）：
- 选出 311 场 Q6 退出（**这 35 个普通 eval 运行里** 0 次 Q1：那里所有低血量退出都在 3 HP、h = 2，第二次受击前就退出了；旧 Q3 读法和 Q5 不在本题范围）和 13 场战斗中回过血的。**没有一次 h ≤ 1 的 Bind**（13 次回血全部是 3 → 5 HP），所以"Bind 变成退出"为 **0**。**更正（修复轮）**：任务点名的范围还包括链 H 的暂停压力运行（`*_oracle_inject`：20261002_180411 … 20261003_074533），那里有约 580 次 Q1 退出（注入的受击一次打到 1 HP），第一轮没有回放；修复轮补上（7.7）。
- 126 场（全部 degraded_dust，任务 V 之前的视觉运行）实况在受击那一帧就暂停（监督器读当前 oracle STATE / 受击帧 FORCED_RISK 未计无敌），录像在那里结束，没有可回放的部分。
- 其余 198 场：
  - 实况 Bind → 新 Bind：13 场（oracle），新代码在同一 tick 或更早 Bind（实况 +196…+754 帧，新 +194…+602）；旧规则反事实在同一 tick Bind，差别来自那些运行之后的其他改动，不是 Q1 / Q1a。
  - 实况退出 → 新 Bind：**1 场**，20261002_232157 i1 ep49（degraded_dust）：实况 Q6 在受击后 +221 帧；新规则在 +152 帧 Bind（h 按最坏已知事件 = 2，Boss 在地下、支撑确认为空，丝 9，T_min 1.78 s，站在地面），旧规则要到 +214 帧（Boss 冒出、h 按支撑）才会 Bind。这是唯一一处 Q1 / Q1a 本身带来的不同：地下空档里提前 62 帧回血。
  - 实况退出 → 新退出：71 场（全部 Q6），57 场同一 tick（±3 帧），14 场更早；新退出原因 72 / 72 为 Q6，0 次 Q1。
  - 实况退出 → 到实况暂停为止新代码没退出：113 场（之后录像不再跟随新代码，无法判断），都是 Q6。**更正（修复轮）**：第一轮说"差别来自 Q6 只看 0.8 s 视野（d73fe65）等之后的改动"，没有逐场归因；按实况代码版本数，只有 44 场来自 d73fe65 之前的代码，69 场的实况代码已含 d73fe65（开环回放的漂移：规划器每次的计划不同，FORCED_RISK 随之不同；未逐场查明）。
- **新 Bind 的安全核对**：14 次新 Bind（13 + 1），支撑 T_min 全部 ≥ 1.7 s（9 次 2 s 内支撑根本到不了）。12 次全程有录像，最近的威胁碰撞体 1.07–2.71 u，**没有被打中**（开环：录像里的 Boss 是对实况主角的反应）；2 次删失，**不能算核对过**（修复轮更正；工具现在把删失的 Bind 判为 "unverified"）：152649 i2 ep3 只有 5 / 92 帧，而实况在同一个 Bind 开始 3 帧后就因 Q6 FORCED_RISK 退出、威胁碰撞体距主角 0.93 u，未核对；232157 i1 ep49（唯一一处 Q1 / Q1a 本身带来的不同）有 69 / 92 帧，期间没有威胁碰撞体，删失段处在 Emerge Antic C（Boss 在 x 95.7）：其他录像里 196 次在 x 95.7 的 Emerge Antic C 开始后 150 帧内没有威胁碰撞体到达 Bind 框，Charge Emerge 要到 +60 帧才跟上，所以在 +246 前结束的 Bind 很可能安全（核验者的补充核对，非本工具结果）。
- 为什么新规则几乎不改变决定：198 场里只有 14 场受击后丝曾 ≥ 9（13 oracle、1 dust）；其余都是满血时丝矛把丝花掉（链 H 的结论：37 次门槛 QUIT 受击时丝 0–6）。h 按最坏已知事件算的 tick 有 9495 个（95 场，地下阶段），这些 tick 的风险档从 GREEN 变 YELLOW，但没有丝就没有 Bind。要让 Q1a 真正起作用，剧本的 `bind.reserve_at_full_hp`（满血也留 9 丝）要做 A/B：实战检查里开着它，h = 2 的 Bind 在 oracle 视图 11 / 14 场完成。

### 7.4 实战检查（实例 4，注入受击留 1 / 2 / 3 HP，`--start-silk 9 9 --silk-reserve`：开局 9 丝且满血时不花，以便 h = 2 时能回血）

| 运行 | 代码 | 视图 | 场 | 说明 |
|---|---|---|---|---|
| 20261003_111244 | 72baaf3 | oracle | 12（中途停） | 第一版时机：按键落在 G，h = 1 暂停在 +20 / +21；h = 2 Bind 4 / 4 完成 |
| **20261003_112406** | **8beb806** | **oracle** | **30** | 修正后 |
| **20261003_114708** | **8beb806** | **degraded_dust** | **30** | 修正后；监督器和暂停机只读延迟视图 |

**20261003_112406（oracle，30 场，CPU 约 75 %：5 个游戏实例 + 回放批处理）**：
- h = 1（留 1 HP 8 场、2 HP 8 场）：16 / 16 在受击帧进入 PAUSE_PENDING（2 次原因是"支撑为空、按最坏已知事件"），16 / 16 暂停在受击后 +16 帧 = G + 1（0.264–0.268 s），全部在无敌窗口内（暂停时剩 0.925 s），0 次 Bind。
- h = 2（留 3 HP，14 场）：11 次 Bind，11 / 11 完成（3 → 5 HP），0 次 Bind 中受击，这 11 场全部 CLEAR；Bind 在受击后 31–260 帧开始（0.5–4.3 s）。另 3 场 Q6（h = 2 时 FORCED_RISK，清空时间 0.02 / 0.02 / 0.22 s）在受击后 59–105 帧退出。
- 第一版运行的 h = 2 四场同样 4 / 4 完成、全部 CLEAR。

**20261003_114708（degraded_dust，30 场）**：
- h = 1（留 1 HP 9 场、2 HP 13 场）：22 / 22 在受击后 2–4 帧（视图延迟 k）进入 PAUSE_PENDING，21 次暂停在 +17 帧（G + 2，0.282–0.284 s），1 次 +18（0.300 s），全部在无敌窗口内（剩 0.89–0.91 s），0 次 Bind。视觉视图看不到门和时间缩放，按"受击采集时间 + 0.285 s"落在 G + 1 之后 1–2 帧，与预期（0–3）一致。1 次原因被记成"no hit"（ep 0：那次 HIT_TAKEN 落在被跳过的帧上；暂停时机按 HUD 掉血仍按受击处理，+18）：已改为 HUD 掉血也算受击（d0c2327），并把 Q1 的原因在暂停期间锁定（3afa1e1）。
- h = 2（留 3 HP，8 场）：5 次 Bind，5 / 5 完成，0 次 Bind 中受击，其中 4 场 CLEAR；另 1 场 Bind 之后 72 s 又一次 h = 2 时 Q6；3 场在 Bind 之前 Q6（受击后 64–99 帧）。视觉视图的支撑更宽，Bind 机会比 oracle 少（5 / 8 对 11 / 14）。
- 两个视图合计（修正后 60 场 + 第一版 12 场）：h = 1 的 46 次全部暂停、全部在无敌窗口内，0 次 Bind；h = 2 的 Bind 20 次全部完成、0 次被打中。
- **只覆盖了一种冻结形状（修复轮补充）**：这些检查里每一次注入的受击都是 G = +15、G 前一帧是 ts 0.999 的最后关门帧（`lowhp_check --q1` 的 ramp999）——正是 oracle 能提前一帧按、落在 G + 1 的最好情况。自然受击约 40 % 没有这一帧，oracle 落在 G + 2；视觉视图在 G = 13 / 14 / 16 和 Bind 中受击时的 0.285 / 0.57 s 也没有实战过。所以"16 / 16 落在 G + 1"只说明注入受击；自然受击见 7.7。

### 7.5 提交

5126afd（Q1 / Q1a、h 的定义、gate_open_at、战术层 HEAL / HEAL_SPOT、测试）、72baaf3（注入器留血量、combat_run --start-silk / --silk-reserve、tools/lowhp_check）、3bc9da8（视觉视图 Bind 中受击的等待）、8beb806（G + 1 修正）、b957be6 / a2d0ec9（tools/lowhp_replay）、05382a7（lowhp_check 的"窗口内"判定）、d0c2327（HUD 掉血也算受击）、3afa1e1（Q1 原因在暂停期间锁定）。全套测试（8beb806 之后、d0c2327 之前的代码）：903 通过、1 失败（已知：机器负载下 support query 计时 p99 2.76 / 4.39 ms 超 3 ms 预算，未放宽）、1 跳过、1 xfail；之后两处只改 supervisor，相关测试（supervisor、supervision、post_hit_window、planner_policy、pause_stress）86 通过。

### 7.6 10⁴ 暂停压力测试（重启）

链 H 的运行 20261003_010522 在 07:13 第 722 次后中断（真实退出后 `load_slot` 等进入游戏超时 120 s，worker 没有重试），不是本链停的。本链在最终代码上重启：工作区 `C:\ssbot\live_pq_3bc9da8`（名字是旧的，检出 3afa1e1，numba 已预热），`pq_campaign_start.cmd C:\ssbot\live_pq_3bc9da8 105330 4670 C:\ssbot\sandbox\pq_campaign_q2.log`（种子 105330–109999，约 39 h）。中途在 d0c2327 上试跑了 23 次（20261003_120827，105300–105322），为锁定 Q1 原因停掉。另：链 H 在 07:45 重启过一次（20261003_074533 `_inject`，`pq_campaign2.log`），4 次 Q1 真实退出后 ep 4 / ep 5 都是 HARNESS_FAIL（"state condition not met within 2.0s"），随后 worker 在 `guards.set` RPC 超时退出（实例 4 无响应），3 分钟内就停了。

修复轮：20261003_122030（3afa1e1）在 13:22 优雅停止（123 次，105330–105452；它和 120827 合计 Q1 85 次（`lowhp_check --q1`，`C:\ssbot\sandbox\pq_q1scan_campaign.json`）：82 次注入受击 ramp999 → 82 / 82 落在 G + 1，3 次 Boss 死亡慢动作里的注入受击 G = +82 / +83、暂停在 G + 3…5，都在无敌窗口内；0 次自然受击的 Q1）。实战检查后在最终代码上重启：工作区 `C:\ssbot\live_pq_final`（5026372，numba 已预热），`pq_campaign_start.cmd C:\ssbot\live_pq_final 105453 4347 C:\ssbot\sandbox\pq_campaign_q3.log`，运行目录 20261003_153044_BellBeast_eval_planner_oracle_inject（种子 105453–109799；109800–109919 是修复轮检查用的）。

### 7.7 修复轮（核验后，2026-10-03 下午；代码 f9dcbba / 4eb57db / 5026372）

**改动**
- **Q6（你的规则，main 1c0a082）**：h = 2 时 FORCED_RISK 不再退出（`SupervisorConfig.q6_max_h` = 1；2 = 以前的规则，供 A/B），照常选风险最低的方案、丝技能照旧只在满血时用；Q3（绕过面具、多实例、危险物、Critical、未知支撑）在 h = 2 照旧退出；第二下把 h 打到 1 就是 Q1，在受击后窗口里退出。攒丝：h ≥ 2、HP < max、丝 < 9 时命中权重 × 剧本的 `bind.gather_hit_x`（Bell Beast 1.5，第一个值，未调；YELLOW 仍限每个惩罚窗口 1 下）。
- 战术层读本 tick 的 h、掉血要有击退才算受击（7.1）；视觉视图没有击退的掉血不等 0.285 s（7.2）。
- 工具：`lowhp_replay` 删失的新 Bind 判 "unverified"、实况在受击帧的 Q1 也回放、`--q6-max-h`；`lowhp_check` 每次受击的冻结形状（ramp999）、受击后攒丝、第二下（自然受击）的窗口、`--q1`（任意运行的 Q1 按受击来源和形状汇总）；`combat_run --start-hp`。

**回放（最终代码 4eb57db，`C:\ssbot\sandbox\pq_lowhp_replay2.json` 与 `pq_lowhp_replay2_010522.json`，13:24–13:54，低于正常优先级、NUMBA 4 线程，同时实例 4 在跑实战检查）**：78 个运行目录（2026-10-02 起所有 Bell Beast eval 运行，本链自己的检查和还在跑的除外），其中有低血量决定的：38 个普通 eval 运行（第一轮的 35 个，加 20261003_074533 degraded_dust 10 场、第一轮没列入的 20261002_061942 degraded_tell 3 场和 061751 degraded 1 场）和链 H 的 9 个 `_inject` 运行（20261003_010522 按顺序取前 80 场），共 649 场。
- **链 H 的暂停压力运行（第一轮漏掉的）**：304 场，303 场实况 Q1（298 次 Q1、5 次 Q1 + Q4）全部"退出 → 退出"，新代码都在**受击那一 tick**（+0）进入 PAUSE_PENDING、原因只有 Q1，**0 次 Bind**；另 1 场实况 Q6 → 新代码到实况暂停为止没退出。所以"Q1 退出变 Bind"在录像里的 303 次 Q1 上为 0。
- 普通 eval 运行 345 场：实况 Q6 → 新代码到实况暂停为止没退出 201 场（第一轮的 71 场"退出 → 退出"全部在这里：h = 2 不再有 Q6，按设计；之后录像不再跟随新代码，结果看实战检查）；受击帧暂停（不回放）130 场；Bind → Bind 13 场、退出 → Bind 1 场（232157 i1 ep49），与第一轮相同；新代码在这些片段里一次也没退出（新退出全部来自 Q1）。
- **新 Bind 的安全核对**：14 次，与第一轮相同；工具判定 12 次 "clear"（全程有录像，最近威胁碰撞体 1.07–2.71 u；开环），**2 次 "unverified"**（152649 i2 ep3：5 / 93 帧；232157 i1 ep49：69 / 92 帧，见 7.3）。去掉 h = 2 的 Q6 没有在这些片段里带来新的 Bind（片段在实况暂停处结束，那之前丝都不到 9）。

**实战检查 1：注入受击留 1 或 3 HP（`SSBOT_INJECT_LEAVE_HP=1,3,3`，不设开局丝、不留 Bind 丝：受击后要自己攒丝），实例 4**

| 运行 | 视图 | 场 | h = 1 | h = 2 |
|---|---|---|---|---|
| 20261003_132436 | oracle | 30 | 10 / 10 暂停在 +16 = G + 1（0.265–0.268 s），全在无敌窗口内（剩 0.925 s），0 次 Bind | 20 场：受击时丝 0–8，20 / 20 攒到 9 丝（受击后 35–2004 帧），**20 次 Bind、20 次完成、0 次 Bind 中受击，20 / 20 CLEAR，0 次退出**；没有第二下 |
| 20261003_135244 | degraded_dust | 30 | 5 / 5 暂停在 +17 = G + 2（0.282–0.284 s；视图延迟 2–4 帧后进入 PAUSE_PENDING），全在无敌窗口内（剩 0.908 s），0 次 Bind；受击要有击退才算（f9dcbba）之后视觉时机不变 | 25 场：受击时丝 0–5，25 / 25 攒到 9 丝（392–2852 帧），**25 次 Bind、25 次完成、0 次 Bind 中受击，23 CLEAR、2 STUCK（240 s 时限），0 次退出**；没有第二下到 1 HP |

（第一轮同类检查开局 9 丝、留 Bind 丝、有 Q6：h = 2 的 oracle 14 场里 11 次 Bind、3 次 Q6 退出；dust 8 场里 5 次 Bind、4 次 Q6。）两个视图合计 h = 2 的 45 场：45 次 Bind 全部完成、0 次被打中、0 次退出、43 CLEAR。CPU：dust 臂期间约 49 %（采样 10 s；oracle 臂时回放在同时跑，未采样）。

**2 次 STUCK 的原因（新问题，未改）**：两场都是 Bind 回满后又挨一下回到 3 HP（h = 2），Boss 只剩 15 / 20 HP（视图的计数）；决策日志最后 1500 tick（25 s）全是 YELLOW、h 2、3 HP、丝 0 / 4 不变、没有一个计划含攻击。推断（日志没记允许集）：YELLOW 下"下一下可能打死 Boss"时禁止一切伤害动作（I3：Boss 死亡慢动作 1.35 s 不能暂停，只能在满血且 h ≥ 3 时进入）；视觉视图按计数的 Boss HP − 3σ ≤ 主角最大一击（`VISION_HERO_HIT` = 15，丝矛）判断，于是 Boss 20 HP 以下就不打了，而不打就攒不到丝、回不了血：一直躲到时限。旧规则下这种局面多半先因 Q6 退出。可选的改法（需主管 / 你决定，涉及安全规则）：(a) 低于满血时用"现在允许的最大一击"（丝技能被禁，只剩针击 5）判断下一下会不会打死，缩小禁区；但针的暴击等未知倍率是取"见过的最大一击"的原因，要先核实；(b) h = 2、丝 < 9 且伤害动作被 I3 禁止时直接退出（没有回血的路）。最终运行里 STUCK 会被进度看门狗（Q8）暂停退出，不会死。

**实战检查 2：自然受击（`combat_run --start-hp 3 3 --start-silk 0 0`，不注入；代码 5026372）**：开局 3 HP（h = 2）、0 丝，Boss 的第一下就该是 Q1 的自然受击。结果 Boss 几乎打不到人：
- oracle 20261003_144536（18 场后停）：18 / 18 先攒丝回血（第一次 Bind 在苏醒后 18–29 s），18 / 18 CLEAR；有 FORCED_RISK 的 18 场共 2591 tick（旧规则下 h = 2、H 内的 FORCED_RISK 就是 Q6 退出），0 次退出；4 场各挨 1 下（都在回满之后）。
- degraded_dust 20261003_150835（12 场后停）：12 / 12 回血（20–54 s），12 / 12 CLEAR（击杀 83–128 s），FORCED_RISK 12 场 2955 tick，0 次退出，1 场挨 1 下。
- 所以**自然受击的 Q1 暂停时机在实战里仍没有样本**（两臂 0 次 Q1）。今天实例 4 上能分形状的受击 62 次（60 次注入、2 次自然、都在 dust 臂）全部是 G = +15、有 0.999 帧；7.2 的 2143 次分布（G 13–16）来自 2026-10-01 的数据运行。oracle 对四种形状的按键时机由 `test_post_hit_window.py` 的替身游戏覆盖；实战的自然受击样本留给重启的 10⁴ 暂停压力测试（h = 2 不再退出，第二下自然受击就是 Q1），用 `lowhp_check --q1 <运行目录>` 按来源和形状汇总。

## 8. EXCLUSIVE 部署清单（任务 Q，2026-10-03；main 里已有、未部署）

部署内容：main 的 `oracle/` = 已部署的 oracle-deploy-20261003（2783573：Forum room.battles + allies、slash.dump paths）+ 链 H 的输入 / IPC 文件 + EXCLUSIVE（10d3948）+ 集成轮的修正（`HoldFilter.QueueExclusive` 保留本段暂停循环自己的键）+ 修复轮的接线（`QueuePlain` / `QueueExclusiveCutAll`，ef3ea8f）。

**部署前**
1. 停掉实例 4 上的暂停压力测试（它锁着 SsOracle.dll）：在其工作区 `brain` 里 `..\scripts\uv.cmd run python -m ssbot.tools.combat_run stop <运行目录>`（运行目录见 HANDOFF 链 Q 一节），等当前这一次结束；其他实例上的作业按主管的窗口停。
2. 在要部署的提交上：`dotnet run --project oracle/tests/InputLogicCheck` 全部 OK（含 `ExclusiveSparesTheLoopsOwnKeys`、`InjectorExclusiveWiring`）；`dotnet build oracle/SsOracle.csproj` 0 警告 0 错误。

**部署后，每个实例**
3. HELLO：`OracleLink(instance=k).hello["action_flags"] == ["exclusive"]`（旧 DLL 没有这个键）。
4. `input.stats` 有 `released_early`（新计数，启动时 0）；`lost_pause_taps` 等旧键照旧。
5. 旧导出没丢：`python -m ssbot.probes.m2_exports --instance k --skip-fight`（act.hf、hero.tm、menu 一节）全 PASS；Forum 实例上 room.battles / allies 照常（Forum 采集日志里 allies 非空）。
6. 普通 ACTION 不受影响：任何非暂停的对局里 `released_early` 不增长（规划器、数据策略、Forum 采集都只发 flags 0）。对照：部署后第一段运行开始和结束各读一次 `input.stats`，增长只能来自暂停循环。

**实例 4 上的实战检查（部署后第一件事）**
7. 掉线看门狗（`ssbot.probes.m1_harness --lost --instance 4`）：检查"held keys released"和"game paused with 1 tap"都 PASS；另加一条看录像：看门狗那次 Pause 落地帧 STATE `act.hf.latched` 只有 Pause 位（CutAll：掉线前刚按下的键当帧就被切掉，旧 `ReleaseAllNow` 会保留最短按下）。
8. 短暂停块：`SSBOT_INJECT_KINDS=keys,menu`，`combat_run run --instances 4 --mode eval --policy planner --view oracle --real-quit 1.0 --inject-hits 1.0 --episodes 40 --seed <本链种子>`，然后 `pause_stress <运行目录>`：菜单可见帧游戏键 0、暂停帧游戏键 0、意外取消暂停 0、错误确认 0、延迟最大 ≤ 6 帧（之前 3）；暂停循环自己的点按每次锁存 ≥ 2 帧（录像里 `act.hf.latched` 的 Pause 位连续 ≥ 2 帧：确认 QueueExclusive 没有切掉循环自己的键）；块结束后 `input.stats.released_early` > 0（"在途按键"试验里规划器的键被切）。
9. 低血量检查（7.7 的命令：`SSBOT_INJECT_LEAVE_HP=1,3,3`、`--inject-hits 1.0`，oracle 视图 10 场，`lowhp_check` 汇总）：结果与部署前同（h = 1 暂停帧 = G + 1（ramp999）或 G + 2，全在无敌窗口内；h = 2 攒丝后 Bind 完成、没有 Q6 退出），证明 EXCLUSIVE 不影响暂停时机，也不切掉 Bind 的按键（Bind 不在暂停循环里，ACTION flags 0）。
10. 通过后在新 DLL 上重启 10⁴ 暂停压力测试（HANDOFF 链 Q 一节的命令），它就是 KeyboardInjector 一侧的长期实战检查。

**之后可选（主管决定）**：Python 键保护（`safety.key_guard`）按 EXCLUSIVE 建模，`keys_clear` 恒真，省掉 0–2 帧的等待；先跑一块关掉保护的对照（需要加一个开关），确认只靠 EXCLUSIVE 时菜单帧游戏键仍为 0 再改。

## 9. h = 2 时的击杀一击死锁（STUCK at 15 HP，任务 2026-10-04；DESIGN §3.7.3 YELLOW、§3.7.4 Q6 修订）

**现象**：main 9d86e71（新 Q6：h = 2 不退出、攒丝回血）起，Bell Beast oracle 实战约 2 % 以 STUCK（240 s 时限）结束。共 8 场：20261003_175813 i2 ep 58 / 70 / 73（129 场中 3 场）、231255 i0 ep 39 / 57、231257 i1 ep 5 / 52 / 53（这两个门控运行共 107 场中 5 场）。

### 9.1 核实（录像 events.jsonl + 决策日志，`ssbot.tools.stuck_replay`，`C:\ssbot\sandbox\stuck_replay_fix.json`）

- 8 / 8 场 Boss 最后停在 **15 HP**，主角 **3 HP（h = 2）**，都只挨了一下（DropBell M2，2 格）。
- 每场在挨打之前都中过 3–4 次丝矛（"Needle Damage"，dmg 15），其余命中全是针击（Slash / AltSlash / UpSlash / DownSlash，19–21 次命中里每一刀都是 dmg 5、dealt 5）；**crit 全部为 false（0 / 8 场）**。
- 旧规则：训练胶水 `SupervisedControl.hero_hit` = max(5, 本场见过的最大一击)。丝矛命中一次后它就是 15，于是 YELLOW 里 Boss HP ≤ 15 → `next_hit_may_kill` → 允许集去掉**所有**伤害原语（R_ALLOW）。决策日志对得上：Boss 到 15 之后 2064–2621 个记录 tick 里 HOLD 模式的允许候选恒为 169 = 442 − 273（常规候选集 441 个 + 延续计划；带伤害原语的正好 273 个），而 Boss 在 30–20 HP、同样 h = 2 时为 400 = 442 − 42（只去掉丝矛）。规划器自己的 U 也用 `SPEAR_DAMAGE = 15` 对待每一刀。
- 后果：不出刀 → 不攒丝（丝停在 7 / 3 / 4 / 7 / 7 / 7 / 7 / 7，决策日志全程不变）→ 回不了血 → 一直 YELLOW（ep 73 有 57 个 GREEN tick，是挨打前满血时）→ 时限。Boss 15 HP 只差 3 刀，丝 7 的场次 2 刀后就够 Bind。旧 Q6 在 h = 2 遇到 FORCED_RISK 就退出，把这个死锁盖住了。
- **结论**：假设基本成立（"可能致死"的上界把一刀当成 15），但原因不是暴击倍率：Hunter 纹章没有暴击（录像 crit 全 false），而是"本场见过的最大一击"把丝矛的 15 套到了每一刀上；丝矛本身在不满血时已被禁用（丝技能只在满血时用）。

### 9.2 游戏里一刀的伤害（反编译 1.0.30000）

`DamageEnemies.cs` 948–1031、`HealthManager.cs` 1011–1022：针击 = `PlayerData.nailDamage`（按 nailUpgrades 为 5 / 9 / 13 / 17 / 21，`PlayerData.cs` 2896）× 该挥砍的 `nailDamageMultiplier`（纹章攻击表：Hunter / Reaper 普通挥砍都是 1.0，蓄力斩 1.4 / 2.5，机器人不按住攻击键所以不会出）× 附魔倍率（工具给针附魔时）× Warrior 狂怒 1.25（仅 Warrior）× Hunter 连击（仅 Hunter_v2 1.3、Hunter_v3 1.3 / 1.5，基础 Hunter 没有）× 丝嘲讽 1.5（嘲讽后的下一击；机器人没有嘲讽原语）× Barbed Wire 1.25（装备时），之后 Wanderer 暴击 × 3：`IsWandererLucky` 要求装备 Wanderer 纹章（`HeroController.cs` 1492），其他纹章不会暴击。丝矛：针等级 0 时 15（460 / 460 次）。

### 9.3 修复（代码 54d7e67，工作区 wf_9520bd11-c70-1）

1. **每种攻击的伤害上限来自装备**（`ssbot/combat/hero_damage.py`，`HeroDamage.from_loadout(纹章, 针等级, 工具)`）：Hunter、针 0 级、只带丝矛：针击 5、丝矛 15、不暴击，与剧本 `hit_damage` 一致。未知部分只往大取：未知纹章取所有纹章倍率之积（含暴击 × 3），没有攻击表的纹章取最大挥砍倍率 2.5，不认识的工具按附魔 + Barbed Wire 算，丝矛随针等级放大，投掷工具和 Clawline 记为无上限（M2 配装里都没有）。`observe()`：录像 / STATE 里某类命中超过上限就抬高该类上限并报警（表错了）。针等级来自剧本 `loadout.needle_level`（逐帧导出里没有），纹章和工具来自审计（STATE hero.crest / tools）。监督器的 `kill_prims` 按原语算：Boss 15 HP 时只有丝矛（不满血时本就不允许）可能致死，针击照常允许。
2. **击杀一击不死锁**（L0 安全过滤器 `combat/safety_filter.py`，硬否决 R_KILL）：
   - "可能致死"不看几何：候选里每一次攻击 / 快速施放的按键沿（连同前缀里已发出的、开局正在进行的）都假设命中，按该攻击的上限累加，达到敌人最低 HP（oracle 精确；视觉为计数 − 3σ；HP 未知的 Boss 记 0）就算可能致死。致死一击最早落在使累加达标的那次按键，最晚落在其后最后一次按键的攻击起始（标称通道；找不到则按键 + 攻击队列 10 帧）+ 命中窗（横砍 6、上挑 8、下劈 16、丝矛 20 帧）+ 其他计时通道余量 4 帧。
   - 只有两种情况放行：I3（GREEN、满血、h ≥ 3，同以前）；或**经认证穿过击杀慢动作是安全的**：h ≥ 2、支撑已认证、该计划整个推演（含命中效果两个分支）S = 0，并且"最晚致死帧 + 0.17 s + 0.15 s 余量（20 帧）"仍在推演之内。窗长实测：20261003_175813 的 120 次击杀（另 6 次录像截断），从致死一击到第一个可暂停帧 95–101 帧（1.65–1.72 s 实时），**游戏时间只走 0.150–0.167 s**（BossDeathSlow 0.1 / 1.15 / 0.1 s、速度 0.05）；支撑的管道按游戏时间算，所以慢动作期间铃和 Boss 的威胁也只推进这么多。
   - 其余情况继续不致死地打（不能致死的刀照常出、照常攒丝）。监督器：YELLOW / RED 里只有在**无法认证**（支撑未认证或 h < 2）时才把可能致死的原语从允许集去掉，否则留给 L0 逐个计划认证；规划器的 U 以前只是排序键，现在是否决。
3. **僵局兜底 QS**（`safety/supervisor.py`）：击杀规则压住针击（每一刀都可能致死）连续 20 s、没有打中任何东西也没有回血 → 锁存，在第一个安全帧（可暂停、选中计划 S = 0、非 FORCED_RISK）暂停退出，而不是撞时限。
4. 安全性质（`tests/test_kill_rule.py`，固定种子的随机扫描）：U ⊆ 可能致死；I3 成立时从不否决；认证过的计划从不否决；认证必须 S = 0、h ≥ 2、支撑已认证、窗口在推演内；可能致死 ⇔ 有自己的按键且按键上限之和 ≥ HP，HP 越低集合只增不减；监督器在无法认证时绝不放行可能致死的原语、PAUSE_PENDING 只允许闪避；QS 只在安全帧触发，命中或回血都会重置。规划器上的整合测试：Boss 15 HP 时一两刀的计划不受影响；5 HP 时窗口放得下的计划被认证，其余 R_KILL；支撑未认证或 h = 1 时一个都不放；GREEN 满血 h 3 无需认证。全量测试 938 过、1 个失败是 `test_support_query_budget...`（计时预算 3.66 ms > 3 ms，机器同时在跑录制；本修复没碰 hitbox_tables / forecast）。

### 9.4 开环回放（8 / 8 场 STUCK，新代码，`stuck_replay`，Boss 到 15 HP 后 60 s = 3601 tick）

| | 结果 |
|---|---|
| 旧规则的"一刀"上限 | 8 / 8 场为 15（都由丝矛抬高），Boss 15 HP ≤ 15 → 全部伤害原语被禁 |
| 新代码允许攻击的 tick | 3486–3601 / 3486–3601（全部），针击从不在 kill_prims 里 |
| 选中计划在前 3 帧按攻击 | 367–544 tick / 场；计划里有预测命中的 688–1086 tick |
| 第一次选中会命中的计划 | Boss 到 15 后 1–13 帧（7 场）、252 帧（ep 73） |
| 新代码进入 PAUSE_PENDING | 0 场 |

反事实（`--kill-hp 5`：把 Boss 读成 5 HP，最后一刀可能致死；`stuck_replay_fix_hp5.json`）：每场 3267–3433 / 3601 tick（91–95 %）至少有一个经认证的击杀计划；选中会命中的击杀计划从 Boss 到位后 5–255 帧开始，前 20 s 内 93–361 tick。开环录像里主角并没有真的出刀，命中不会发生，所以 8 / 8 场在 20.0 s 后由 QS 在第一个安全帧退出（兜底在真实状态上触发正常）。录像不跟随新选择，闭环结果看 9.5。

### 9.5 实战检查（实例 0 / 1，oracle，Bell Beast，种子 115000 起，--threads 4）

（待跑：DEMO_SOON 期间不开新实战。）

### 9.6 待定

- 这是对 I3 / §3.7.3 YELLOW 的细化（h = 2 且经认证时允许击杀一击），DESIGN 正文需要主管 / 你确认后再改。
- 视觉视图同样用计数 HP − 3σ 和装备上限；degraded_dust 未做实战复核。
