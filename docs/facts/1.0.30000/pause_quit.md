# 1.0.30000 暂停 / 退出压力测试（M2 W5，DESIGN §3.7.5 G1）

链 H（工作区 `wf_c0d56d51-4cb-4`，实例 4，种子 100000–104999）。上一轮（11b4ca0，`20261002_180411_..._inject`）：112 次注入受击全部暂停并退到主菜单，暂停延迟 p99 2 帧、最大 4 帧，0 外来按键、0 意外取消暂停、0 错误确认；但只有 3.6 % 落在难点时刻 ±3 帧内（目标 30 %）。

## 1. 难点时刻的时序（离线，录像实测）

数据：`20261002_190611_BellBeast_eval_planner_oracle`（代码 11b4ca0，oracle）前 6 场，脚本 scratchpad `h/calib.py`（按键沿取 STATE `act.hf.latched`）。

| 时刻 | 从按键锁存到事件（帧） | 说明 |
|---|---|---|
| 丝矛命中（"Needle Damage"） | 18 / 19 / 20：12 / 13 / 1 次（共 26） | 丝矛命中 15 HP；投出后不受按键影响，可提前预测 |
| 横砍 Slash / AltSlash 命中 | +1：38 / 56，+2 / +3 / +4 其余 | |
| 上砍命中 | +3 到 +7 | |
| 下劈弹起（downSpikeBouncing 起始） | 下键 + 攻击 → +11：12 / 20，+8：5 / 20，其余 7 / 12 / 13 | 47 次下劈起势只有 20 次弹起 |
| 击杀 | 6 场：丝矛 4、Slash 1、AltSlash 1 | 击杀帧同时有 BossDeathSlow 冻结（96 帧） |

- 这些录像里没有 EnemyDeath 一类的冻结事件：普通命中不产生 FreezeMoment（只有 BossDeathSlow），所以"命中"本身不算暂停门被关的难点时刻。
- Bell Beast 没有 BossStun；cstate `parrying` 6 场 0 次，拼刀很少（只有砍到铃铛的弹刀）。
- 上一轮只有 3.6 % 的原因：注入的受击打断了主角自己的攻击，计划中的弹起 / 击杀就不再发生（弹起类注入都落在 "DownSpike Antic"）；而且用的 "起手帧 + 2" 对下劈太早（实际 +8 到 +13）。

## 2. 注入器（`ssbot/train/hit_injection.py`，提交 f06b1bd）

- 三类故障（每场一个）：**受击**（hurt.special 打到 1 HP，Q1，同上一轮）；**触发**（`Supervisor.inject` 的退出触发 QF，不扣血：暂停循环从游戏和按键路径的任意状态开始，通常暂停门开着、规划器的键还按着）；**菜单**（同一 tick 内既触发又受击：受击在第一次 Pause 按下到达游戏前 0–2 帧落地，即菜单本应打开的那一帧）。
- 难点时刻在第一帧触发（或对已确定的事件提前）：击杀（受击：击杀首帧；触发：偏移 −3..+2，负偏移只用于已投出的丝矛，按下后 + 19 + 偏移，或横砍按下帧）、弹起（受击：起始 + 1，避开下劈 2 个物理步的无敌；触发：+0..2）、丝矛起手（NeedleThrow 首帧 +0..2）、拼刀 / 弹刀（+0..2）。权重 弹起 3 : 丝矛 3 : 菜单 2 : 击杀 1 : 拼刀 1，占 `--inject-hits SHARE`；其余为覆盖类（空中 / 攻击 / 下劈中的受击，规划器按着键时的触发）。
- `ssbot/tools/pause_stress.py`：故障帧 = 受击的 damage 帧，或触发的第一个 PAUSE_PENDING 帧；难点时刻 kill / stun / bounce / clash / cast / hurt / menu（菜单只对含受击的故障算：受击离循环第一次 Pause 锁存帧 ≤ 3 帧）。

## 3. 按键泄漏进暂停菜单（HoldFilter）

- 机制：按键路径（oracle HoldFilter，最终 inputd 同规则）保留每个边沿并按最短按下 / 松开 2 / 2 帧重放。规划器在 f−1 发给 f+1 的 ACTION 仍在途；暂停机在 f 发出的第一次 Pause（落在 f+2）可能与 f+1 刚按下的键同帧（该键要到 f+3 才能松开），或被最短松开推迟的再按下在菜单里才触发。上一轮受击注入没有出现，只是因为受击关门 15 帧，期间过滤器早已放空；37 次门槛 / 实战 QUIT 中有 9 次移动键在暂停后 1–2 帧仍锁存、4 次在暂停帧新按下。
- Python 侧修复（提交 f06b1bd）：`ssbot/safety/key_guard.py`。从 STATE `act.hf` 出发，把已发出但尚未生效的 ACTION（`act.target` 之后到 f+1，包括错过本帧、下一帧和下一个一起生效的那一个）重放一遍；只有 Pause 落地那一帧没有任何其他键锁存、也没有排队的边沿时，暂停循环才开始按（`PauseCues.keys_clear`，最多等 `keys_wait_s` 0.25 s）。
  - 模拟按键路径（`tests/test_key_guard.py`，2000 次，规划器随机键流、10 % 的 ACTION 晚一帧）：不加保护 706 次泄漏；在途列表只取 f+1（漏掉晚到的 ACTION）56 次；完整保护 0 次。代价：暂停按下推迟 0 / 1 / 2 / 3 / 4 帧的比例 56 / 33 / 9 / 2 / 0.2 %（这个随机键流比实战密得多）。
- oracle 侧（提交 10d3948，**只编译未部署**）：ACTION 第 5 个元素 flags，EXCLUSIVE = 1：从该 ACTION 的帧起，掩码外的键立即松开（必要时短于最短按下）并丢弃排队边沿（`HoldFilter.Exclusive`）。暂停机发出的所有 ACTION 都带它；掉线看门狗的 Pause 点按也改用它（原来 `ReleaseAllNow` 保留最短按下，刚按下的键会和 Pause 同帧）。HELLO 新增 `action_flags: ["exclusive"]`；旧 oracle 只读前 4 个元素。`oracle/tests/InputLogicCheck` 全部通过（新增：Pause 那一帧没有其他键、之后不重放）。Python 保护保留（按普通过滤器建模），两层独立。
