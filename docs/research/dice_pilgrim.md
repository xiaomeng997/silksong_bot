# 磁石骰与蚀阶的赌徒兰布尔（PC 1.0.30000）

**问题（你，2026-10-04）：** "骰子是在蚀阶跟一个 NPC 赌博拿到的；开着 mod，赌骰子不就很容易吗？" 本文核对：骰子到底从哪来（§1）、那个 NPC 在哪、什么时候在（§2）、赌局怎么实现、能不能稳赢（§3）、只读 oracle 比画面多看到什么（§4）、骰子值不值一个黄槽（§5）。

**标签：** 【码 文件:行】反编译 1.0.30000 C#（`C:\ssbot\decomp\1.0.30000`）；【包】离线 UnityPy 读训练副本 `C:\ssbot\game\train` 的场景包和数据包（只读）；【本地化】解密后的语言表（`C:\ssbot\sandbox\forum_tools_scripts\loc`）；【攻】社区资料（rando 逻辑图 `room_graph_data.json`，不是游戏数据）；【推】由代码或数据推出、未实测；【估】估计；【未核实】待实测。

**脚本与原始输出：** `C:\ssbot\sandbox\dice_pilgrim_scripts\`（全部离线、低优先级，没有连接任何游戏实例）：`scan_all.py` → `scan_all.txt`（590 个场景包里含 `dicePilgrim` / `Dice` 字符串的组件）；`scan_pptr.py` → `scan_pptr_dice.txt`（全部 2,068 个包里引用磁石骰资产的组件）；`dump_fsm.py`（dataVersion 2 逐参数解码，沿用 `four_ach_fix/rawp.py`）→ `fsm_play_point.txt`（赌桌）、`fsm_dialogue.txt`（兰布尔对话）、`fsm_control.txt`（场景状态）、`fsm_die_octagon.txt`（骰子漂浮）、`fsm_bell_dropper.txt`；`scene_pos.py` → `scene_coral33_dice.txt`、`scene_coral32_dice.txt`（对象、坐标、组件字段）；`tk2d_clips.py` → `tk2d_dice.txt`、`tk2d_dice_hornet.txt`（动画帧率、帧、触发帧、精灵号）；`mapzone.py`、`threats.py`、`geo_magnet.py`、`imbue.py`、`fcall.py`；`gamble_math.py` → `gamble_math.txt`（赌局和护盾的精确概率）。

---

## 0. 摘要（可直接转述）

1. **你说得对，`four_achievements.md` §4.3 错了。** 磁石骰（Magnetite Dice，内部 `Lucky Dice` / 工具名 `Magnetite Dice`，黄色）在 Act 1–2 来自蚀阶（Blasted Steps）`Coral_33` 的朝圣者**兰布尔**（Lumble，称号"幸运儿"）。来源有三个【包】【码】：
   - **赌赢他**：让他输光本钱，他付不起最后一注，改送骰子（`Play Point` FSM 的 `Get Reward`：`SetToolUnlocked Magnetite Dice` + `dicePilgrimDefeated`）。
   - **他的尸体**：没赢过他时，只要打过**齿轮舞者**（Cogwork Dancers）或拿到**飞针**（Clawline），之后在蚀阶以外发生一次 TimePasses（坐椅子、死亡、存档退出），他就死在赌桌旁，尸体边有一个骰子拾取物，**免费，不用赌**（Act 1–2）。
   - **Grindle 300 念珠**：只在 Act 3（`blackThreadWorld`），而且只在你还没有骰子时出现，是后备。
2. **赌局不靠运气。** 每局胜负平时是 50/50 抛硬币，但有"**完美掷骰**"：按住"掷骰"约 4.5 s（或 4.8 s，见 §3.3），霍内特换成特殊的掷骰动作并响一声，**之后 0.3 s 内松手，这一局必赢**【包】。这个信号在画面上（和声音里）就有，所以**视觉在 Switch 上也能做**，不需要 mod。数据里还有一个疑似漏洞：完美一次以后标志不复位，之后几局只要在窗口结束前松手（随手一按）都算完美【推，待实测】。
3. **赌注和风险：** 每局 4 念珠（"一拍子念珠"），兰布尔本钱 16；要**净赢 5 局**，第 5 局他付不起，改给骰子。所以只要打完，一定净赚 **+16 念珠**，中途输掉的都会赢回来；只有中途放弃才会净亏（亏的部分记在他的本钱里，存档保留）。坐下和每局继续都要求身上至少 4 念珠，**不会输掉身上没有的念珠**【包】。全靠抛硬币时要净赢 5 局，平均要几十到上百局（§3.5），完美掷骰时 5 局就完。
4. **开 mod 有没有额外好处：基本没有。** 只读 oracle 能直接读到的东西（FSM 是否在完美窗口、完美标志、兰布尔剩余本钱）都能从画面推出来。抛硬币是在两人都掷完之后才用 Unity 全局随机数抽的，**之前没有任何预先决定、可以偷看的值**【包】【码】。所以视觉能做的完美掷骰就是最优策略，不需要也不应该用隐藏状态（§4）。
5. **骰子的作用（代码）：** 被**敌人**打中时，按"连续没挡住的次数" 0/1/2/3/4/≥5 给 0/2/4/6/8/10 %（实际是 /99）的概率**整下免伤**（2 格的重击也整下免掉，击退和无敌帧照常）；挡住一次后归零。长期平均每 12.8 次敌人命中挡 1 次（7.8 %）。运气 ×1.1 只影响 Wanderer 暴击（2 % → 2.2 %）和火焰附魔的"幸运命中"；**不影响念珠、壳片掉落**（只在同时带念珠磁铁时让念珠早 30 % 开始被吸）【码】【包】。
6. **建议（Ending 1 路线）：默认不去拿。** 它占一个黄槽，而 Hunter 只有 2 个黄槽，已分给负重环带（确定性的减击退、加无敌帧，规划器在用）和爬墙爪（Forum 口袋）。我们的 bot 每场挨打很少（Bell Beast 门槛 66 场共 3 次），随机护盾几乎碰不到，也不能被安全监督当作保护。绕路 + 赌局约 **3–4.5 min**【估】。如果 K1 的 A/B（训练里用 DebugMod 直接给骰子）证明某场 A 类战斗换掉负重环带更好，再在 S17 加这段（确定性、视觉合法）。**100 % 部分：不用赌**，Ending 1 之后（还在 Act 2，Dancers 已打）到 `Coral_33` 免费捡尸体旁的骰子；错过了就 Act 3 找 Grindle（300）。
7. **DESIGN §3.6.4 "永不交战"里的"Lumble 的骰子"** 理由要改：它不是战斗，是可以稳赢的小游戏；不做的理由是占槽和时间（§6）。

---

## 1. 骰子从哪来（问题 1）

### 1.1 兰布尔的对象和 FSM【包】

`Coral_33` 的 `Black Thread States`（`TestGameObjectActivator`：`blackThreadWorld` 为真时开 `Black Thread World`、关 `Normal World`）下，`Normal World/Dice Game Control`：

| 对象 | 组件 | 作用 |
|---|---|---|
| `Dice Game Control` | FSM `Control` | `Init`：读 `dicePilgrimState`，`IntSwitch` 0 → `Active`（开赌局）、1 → `Dead`（开尸体）、2 → `Departed`（两个都关） |
| `Dice Game/Dice Pilgrim` (18.9, 61.4) | `PlayMakerNPC` + FSM `Dialogue` | 对话：第一次 `DICE_PILGRIM_MEET`（置 `metDicePilgrim`），第二次 `DICE_PILGRIM_MEET2`（讲规则，置 `dicePilgrimGameExplained`）→ `Activate Game`：0.5 s 后打开 `Play Point`；以后每次来 `DICE_PILGRIM_REMEET` → `Activate Game`。场景载入时 `Init` 先关掉 `Play Point`；`dicePilgrimBank` < 0 时直接进"输光后"的待机 |
| `Dice Game/Play Point` (22.6, 60.1) | `PlayMakerNPC`（`targetDistance` 1.25）+ FSM `Play Control` | 赌局本身（§3） |
| `Dice Game/Dice/Die Octagon` / `Die Diamond` / `Die Triangle` | FSM `floating_die`、`floating_die_mid_drift` + 物理 | 三颗磁石骰被抛出、漂浮、吸到一起，纯表演 |
| `Dice Game Corpse/Collectable Item Pickup` (20.2, 60.3) | `CollectableItemPickup`（`item` = 磁石骰资产，`PersistentBoolItem`） | 尸体旁的骰子拾取物 |
| `Coral_32` 的 `Dice Pilgrim Corpse` (52.5, 55.1) | `PlayerDataTestResponse`：`dicePilgrimState` ≠ 2 时关闭自己 | 赢过他以后他"上路"，死在 `Coral_32`，只是布景，没有拾取物 |

资产核对：`Get Reward` 的 `SetToolUnlocked` 和尸体拾取物的 `item` 都指向 pathID −7183278955027662741，即 `toolitems` 包里的 `Magnetite Dice`（`item_ids.txt`）【包】。

### 1.2 三个来源

| 来源 | 条件 | 依据 |
|---|---|---|
| **赌赢** | `Coral_33` 里 `dicePilgrimState` = 0（Act 1–2、Dancers / Clawline 之前或之后但还没在蚀阶外 TimePasses）；净赢 5 局 | `Play Control` 的 `Gain Rosaries` → `PILGRIM DEPLETED` → `Pilgrim Depleted`（对话 `DICE_PILGRIM_DEPLETED`）→ `Hornet Get 1/2` → `Get Reward`：`SetToolUnlocked`、`dicePilgrimDefeated = 1`、向 `Dice Pilgrim` 发 `LOST DICE`【包】 |
| **尸体** | 没赢过他；`defeatedCogworkDancers` 或 `hasHarpoonDash`；之后在**蚀阶以外**（当前地图区不是 `JUDGE_STEPS`）发生一次 `TimePasses` → `dicePilgrimState = 1`；Act 1–2（Act 3 时 `Normal World` 整个关掉） | 【码 GameManager.cs:1457-1464】；`TimePasses` 的调用点：死亡 `PlayerDead`、存档退出 `ReturnToMainMenu`、`MazeMistZone`，以及工作台 `Bench Control` 的 `Save Game` 等 FSM（`research/benches.md`、`forum_route.md` 已查）【码】【包】；`Control` FSM 的 `Dead` 状态开 `Dice Game Corpse`【包】 |
| **Grindle** | Act 3（`blackThreadWorld` = 1），**且还没有骰子**：`ShopItem.IsPurchased` 在 `savedItem` 不能再拿时为真，工具的 `CanGetMore()` = `!IsUnlocked` | `Grindle Lucky Dice Tool`，300 念珠【包 `shops_all.txt`】【码 ShopItem.cs:308-351，ToolItem.cs:632】 |

赢过他（`dicePilgrimDefeated`）以后，同样的条件把状态改成 2（离开），`Coral_33` 里什么都不剩，`Coral_32` 出现他的尸体布景【码 GameManager.cs:1457-1460】【包】。

社区 rando 逻辑图对 `Coral_33`（"Lumble the Lucky"）的写法与此一致："（Bankrupt Lumble 或 Clawline 或 Cogwork Dancers）且 Act 1 或 Act 2"；Grindle 一项注明"IF NOT Acquired from Lumble"【攻】。

### 1.3 `four_achievements.md` §4.3 为什么错

修订轮的原始扫描 `four_ach_scripts\scan_items.jsonl` **其实扫到了**这两处（`coral_33` 的 `Play Point` / `Get Reward` 和 `Dice Game Corpse/Collectable Item Pickup`）。但汇总表 `summ2_tools.txt` 对磁石骰列出 117 个引用时，前面 101 个是念珠预制体 `GeoControl` 的"磁铁加速工具"字段（§5.1），14 个是 Bellhart 许愿的铃铛掉落判定，只显示了前几条，后面两条被截断；§4.3 按截断后的汇总下了"唯一来源是 Grindle"的结论。教训：汇总不能截断，100 % 清单要按"来源类组件"（拾取物、`SetToolUnlocked`、商店、许愿奖励）单独列，不能和"检查是否装备"的引用混在一起。本分支已改正 §4.3 和相关结论（见 §6）。

### 1.4 赌注不是"一串念珠"

- 每局赌注是 FSM 整数变量 `Wager Amount` = **4**，`Lose Rosaries` 用它调用 `HeroController.TakeGeo(int)`，`Gain Rosaries` 用它调用 `AddGeo(int)`【包 `fcall.py`】【码 HeroController.cs `AddGeo`/`TakeGeo`】。这就是对话里的"一拍子念珠"（a beat of rosaries）【本地化 `DICE_PILGRIM_NOTENOUGH`、`MEET2`】。不涉及"念珠串"物品。
- 兰布尔的本钱 `dicePilgrimBank` 默认 **16**【码 PlayerData.cs:517-518】。赢一局 −4，输一局 +4，存在 PlayerData 里（随存档保存）。

---

## 2. 在哪、什么时候在（问题 2）

### 2.1 位置【包】

- 场景 `Coral_33`，地图区 `JUDGE_STEPS`（蚀阶；`Coral_43`、`Coral_35`、`Bellway_08`、`Coral_03`、`Coral_32` 也是）【包 `mapzone.py`】。
- 死胡同房间，只有 right1 (57.5, 66) 通 `Coral_43`。赌桌 `Play Point` (22.6, 60.1)，兰布尔 (18.9, 61.4)，尸体拾取物 (20.2, 60.3)。
- 房间里 Normal World 没有敌人（14 个 `DamageHero`、4 个 `HealthManager` 都在 Act 3 的 Garmond 场景下）；`Coral_43` 没有敌人和伤害体；`Coral_35` 有 3 个尖刺碰撞体【包 `threats.py`；只查场景内对象，生成器生成的敌人没查】。

### 2.2 从 S17 路线过去【包：门坐标】【攻：能力要求】【估：时间】

S17 在 `Coral_03` 竖井顶端从 right1 (60.5, 203) 去 `Coral_32` → Last Judge。竖井顶端另一侧 left1 (−0.5, 203) 就是 `Bellway_08`：

| 段 | 门到门 | 直线距离 |
|---|---|---|
| `Coral_03` 顶端 → left1 | 竖井出口到 left1 | ≤ 61 u（取决于爬到顶时站在哪） |
| `Bellway_08` right1 (150.5, 14) → left1 (64, 16) | 经过钟椅 (120.6, 14.0)（40 念珠，付一次） | 86.5 u |
| `Coral_35` right1 (28, 27) → left1 (2, 12) | 往下 | 30 u |
| `Coral_43` right1 (109, 9) → left1 (1.5, 9) | 两个沙坑 | 107.5 u |
| `Coral_33` right1 (57.5, 66) → 赌桌 (22.6, 60.1) | | 35.5 u |

- 单程从 `Coral_03` left1 起约 260 u、4 道门；往返约 520 u、8 道门，加竖井顶端横穿最多 2 × 61 u。按 `benches.md` 的方法（4–8 u/s，每门 0.5 s）**往返约 70–165 s**【估】。
- 能力：`Coral_43` 的沙坑两侧要冲刺、Drifter's Cloak、飞针等任一（路线 S05/S08 已有）；回程在 `Coral_35` 从下半段爬回 right1 要 Cling Grip 等（S12 已有）【攻 `room_graph_data.json`】。
- 拿到后要装上得坐工作台（DESIGN §3.6.5 只在工作台换装）。回程正好经过 `Bellway_08` 的钟椅（40 念珠，`benches.md` 里本来就是 S17 的条件购买），坐下约 +10 s。

### 2.3 什么时候在【码】【包】

- `dicePilgrimState` = 0（在赌桌）从开局一直保持到"打过 Dancers **或** 有 Clawline，**并且**在蚀阶以外发生一次 TimePasses"。S17 在 S19（Dancers）和 S23（Clawline）之前，**路线经过 S17 时他一定在**。
- S19 打完 Dancers 后第一次在别处坐椅子（或死亡、存档退出），他就变成 1（死，尸体 + 骰子）或 2（赢过他：离开）。路线 S17 之后不再回蚀阶（DESIGN §3.6.4 路线表），**"回程顺路"不存在**。
- 每次进场都要先和他说话，赌桌才出现：第一次来要说两次（`MEET` 5 页 → 回到待机；再说一次 `MEET2` 3 页 → 0.5 s 后赌桌出现），之后每次来说一次（`REMEET` 2 页）【包 `fsm_dialogue.txt`】。
- 他对 Needolin 有反应（`Sing` 状态，唱歌时暂时不能交互），但 bot 在这里不会按 Needolin【包】。

---

## 3. 赌局本身（问题 3）

### 3.1 流程（`Play Point` 的 `Play Control` FSM）【包 `fsm_play_point.txt`、`tk2d_dice.txt`】

| 状态 | 内容 | 时长 |
|---|---|---|
| `Kneel Start` | 本钱 < 0 → 输光后的对话；身上念珠 < 4 → `DICE_PILGRIM_NOTENOUGH`；否则隐藏英雄、跪坐动画 | 0.33 s 触发 |
| `Give Anim` → `Dice Idle` | 兰布尔递骰子；提示"掷骰"（菜单确认键）。**这里没有取消键**：跪下后第一局必须掷 | 约 0.4 s + 等按键 |
| `Roll Start` | 按下确认；置 `Hornet Turn`、`Perfect Roll = 0`（**不清 `Perfect Timing`**）；播 `Hornet Roll` | 0.5 s |
| `Rolling` | 一直按住；松开（`ListenForMenuSubmit` 的 isNotPressed）→ `Throw Antic`。`Wait 4.0 s`（游戏时间）后 → `Wait For Anim Loop` | 按住时长 |
| `Wait For Anim Loop` | 等 `Hornet Roll` 的下一个触发帧；松开 → `Throw Antic` | 0–0.33 s |
| `Perfect Anim` | **完美窗口**：`Perfect Timing = 1`，换播 `Hornet Roll Special`，响一声；松开 → `Throw Antic` | 0.3 s |
| `Rolling 2` | 窗口过了：`Perfect Timing = 0`，音高回落；松开 → `Throw Antic` | 不限 |
| `Throw Antic` → `Perfect?` | `Perfect Timing` 为真 → 镜头震动、三颗骰子闪光、音效、`Perfect Roll = 1`；否则普通掷 | 0.08 s |
| `Throw` → `Get Middle` → 形状状态 → `Combine Pause` | 三颗骰子抛出，离赌桌水平最近的那颗当"主骰"，另两颗被吸过去（**纯表演，不参与胜负**） | 1.5–1.75 + 2.5 s |
| `Pilgrim Collect 1/2` → `Pilgrim Roll` → `Pilgrim Throw` → … `Combine Pause` | 兰布尔收骰、掷骰，同样是表演 | 0.5 + 1–2 + 1.25–1.5 + 2.5 s |
| `Who Won?` | 见 §3.2 | 0 |
| `Lose Rosaries` / `Gain Rosaries` | 输：`TakeGeo(4)`，本钱 +4。赢：本钱 −4；本钱 < 0 → `PILGRIM DEPLETED`（**这时不执行后面的 `AddGeo`**，最后一注不付），否则 `AddGeo(4)` | 0 |
| `Hornet Turn Pause` → `Hornet Choice` | 身上念珠 < 4 → 兰布尔赢光的对话后结束；确认键 = "继续游戏"，取消键 = "停止" | 0.5 s + 等按键 |

最后一注不付的依据：PlayMaker 在某个动作触发转移后不再执行同一状态后面的动作【码 PlayMaker FsmState.cs:293-324（每个动作的 `OnEnter` 后 `IsSwitchingState` 为真就返回）、Fsm.cs:2671-2688（`DoTransition` 置 `switchToState`）】；对话也说"最后这把的赌注我给不起"【本地化】。

**每局时长**（从按下确认算起，不含按住）：0.5（收骰，第一局是跪坐）+ 0.5 + 0.08 + 1.5–1.75 + 2.5 + 0.5 + 1–2 + 1.25–1.5 + 2.5 + 0.5 ≈ **11.3–12.8 s，均值约 11.6 s**；完美掷骰要多按住约 4.1–4.5 s，**约 15.7–17.3 s 一局**【包：FSM 等待和动画长度；推：没算帧对齐和输入延迟】。

### 3.2 胜负怎么抽【包】【码】

`Who Won?` 三个动作依次：
1. `Perfect Roll` 为真 → 霍内特赢。
2. `Always Win` 为真 → 霍内特赢。这个变量只出现在这个 FSM 里，默认假，没有任何地方去置它（`Coral_33`、`Coral_32`、`Coral_35`、`Coral_43` 全文搜索）【包】，是开发用的开关。
3. `SendRandomEvent`（PILGRIM 0.5 / HORNET 0.5）→ `ActionHelpers.GetRandomWeightedIndex`：`UnityEngine.Random.Range(0f, 1.0f)`，< 0.5 兰布尔赢，否则霍内特赢【码 SendRandomEvent.cs、ActionHelpers.cs】。（抽到正好 1.0 时返回 −1、不发事件、状态卡住，概率可忽略。）

**没有任何东西取决于英雄**：不看骰子形状、不看运气（这两个 FSM 里没有 `GetLuckModifier` 或检查工具装备的动作），磁石骰对赌局本身没有作用。唯一的玩家技巧就是完美窗口。

### 3.3 完美掷骰：时机和画面【包 `tk2d_dice_hornet.txt`】【推】

- `Hornet Roll`：12 fps，6 帧，帧 0–1 后循环帧 2–5，触发帧在帧 2（循环起点），所以每 4/12 = 0.333 s 一次触发；精灵号 55, 56, **57–60**。
- `Hornet Roll Special`：12 fps，6 帧，精灵号 **80, 81**, 57–60 —— **只有前两帧（1/6 s，约 10 个 60 fps 画面帧）和普通掷骰不同**，之后和普通循环一样。
- 窗口起点 T0：`Roll Start` 进入时开始播 `Hornet Roll`，0.5 s 后进 `Rolling`，再 4.0 s 后等下一个触发帧。触发帧出现在按下后 0.167 + 0.333·n s，`Rolling` 结束在约 4.5 s，正好落在第 13 个触发点上，同一帧里谁先谁后取决于帧对齐和更新顺序，所以 **T0 ≈ 4.5 s 或 ≈ 4.83 s（双峰）**【推，待实测】。两个窗口 [4.5, 4.8) 和 [4.83, 5.13) 不重叠，**盲按固定时长不可靠**，要看画面。
- **视觉做法（Switch 也能用）**：按住确认 → 等霍内特出现精灵 80/81（或听到提示音）→ 下一帧松开。窗口 0.3 s，前 0.167 s 有专用精灵，按 60 fps 采集、1–3 帧识别、1–2 帧输入延迟，松开会落在 T0 后约 0.05–0.1 s，余量足够【推】。成功的确认信号：松手后镜头震动 + 三颗骰子闪光 + 音效（`Perfect?` 状态）；没有这些就是普通掷，按 50/50 处理。
- **疑似漏洞（`Perfect Timing` 不复位）**：`Perfect Timing` 只在 `Perfect Anim` 置 1、在 `Rolling 2` 置 0，`Roll Start` 不清它【包：`Roll Start` 里只清 `Perfect Roll`；全场景搜索 `Perfect Timing` 只出现在 `Perfect?`、`Rolling 2`、`Perfect Anim`】。所以完美一次之后，只要下一局在窗口结束前松手（包括按一下就松），`Perfect?` 仍读到真，照样算完美；按住超过窗口进了 `Rolling 2` 才会清掉。离开场景再回来 FSM 重新初始化为 0。【推，待实测】稳妥的脚本不依赖它：每局都看画面掐窗口；想省时间就在确认上一局完美后试一次"按一下"，看到成功信号再继续这样做。
- `Perfect?` 里还留着一个关掉的旧判定（`FloatInRange Roll Time` 3.8–4.2），说明早期版本按"按住时长"判定，现在改成跟动画对齐的窗口【包】。

### 3.4 玩家能做的选择

只有两个：每局按住多久（松手时机）；每局结束后"继续游戏 / 停止"。赌注固定 4，不能加注，没有重掷、保留骰子这类选择。第一局跪下后不能取消（`Dice Idle` 没有取消事件）。

### 3.5 胜率、局数、时间（`gamble_math.txt`）【推：模型】

把每局记为：概率 q 完美（必赢），否则 50/50。要净赢 5 局；身上念珠 R，掉到 4 以下就不能继续（可以以后再来，本钱记在存档里）。

| 打法 | R | 打完的概率 | 打完所需局数 P50 / P90 / P99 | 平均时间 |
|---|---|---|---|---|
| 纯抛硬币（q = 0，每局 11.6 s） | 20 | 0.50 | 19 / 51 / 97 | 约 4.8 min（打完的那一半） |
| | 100 | 0.83 | 37 / 247 / 663 | 约 18 min |
| | 200 | 0.91 | 45 / 471 / 1,811 | 约 34 min |
| 完美掷骰 q = 0.5（每局约 16 s） | ≥ 40 | 1.00 | 9 / 17 / 29 | 约 2.7 min |
| q = 0.8 | ≥ 20 | 1.00 | 5 / 9 / 13 | 约 1.7 min |
| q = 0.95 | ≥ 20 | 1.00 | 5 / 7 / 9 | 约 1.4 min |
| q = 1 | ≥ 4 | 1.00 | 5 / 5 / 5 | 约 1.3 min |
| 有漏洞时 q = 0.5 | ≥ 40 | 1.00 | 5 / 9 / 13 | 约 1.6 min |

- 纯抛硬币是对称随机游走：打完的概率 = a / (a + 5)，a = ⌊R / 4⌋；平均局数（不论打完与否）= 5a，R = 100 时 125 局、约 24 min。**纯靠运气不可行**；有完美掷骰就是 5 局。
- **念珠：** 打完时净赚恒为 +16（W − L = 5，最后一胜不付：4 × (W − 1) − 4 × L = 16）。需要的只是"身上 ≥ 4"；完美掷骰下最多输几局，身上有 20 念珠就够【推】。
- **桌边总时间**（完美掷骰，每局都掐窗口）：对话（第一次 `MEET` 5 页 + `MEET2` 3 页）约 10 s + 5 局约 80–85 s + 赢后对话 `DICE_PILGRIM_DEPLETED` 5 页和拿骰子动作约 10 s ≈ **100–110 s**；漏洞成立、后 4 局按一下就松时约 85–90 s。得到工具时是否有需要按键关掉的弹窗【未核实】。
- **加上往返**（§2.2，70–165 s）：**整段约 3–4.5 min**【估】。

---

## 4. 只读 oracle 比画面多看到什么（问题 4）

| 隐藏信息 | oracle 能读到 | 画面上的对应 | 用它能多得什么 |
|---|---|---|---|
| 这一局抛硬币的结果 | **读不到**：在 `Who Won?` 那一帧才抽，之前没有存在任何变量里 | 结果当场就显示（念珠计数 ±4） | 无 |
| 下一局的结果 | 理论上可以读 Unity 全局随机数状态（`Random.state`），但从玩家最后一个决定（松手或"继续游戏"）到抽签之间有约 6–12 s，期间骰子位置（`TranslateRandom`）、角速度、抛出速度和角度、兰布尔的 `WaitRandom`、音高随机、场景里其他脚本每帧都在消耗同一个随机数，次数跟帧时序有关 | 无 | 实际上不可能预测；即使能预测，也只能用来"不开这一局"，而完美掷骰已经让每局必赢 |
| 完美窗口 | FSM 当前状态 `Perfect Anim` / 变量 `Perfect Timing` | 精灵 80/81 + 提示音 | 少几帧反应时间，别无他用 |
| 漏洞标志 | `Perfect Timing` 的当前值 | 由上一局是否出现成功信号推出 | 无 |
| 兰布尔剩余本钱 | `dicePilgrimBank` | 由每局念珠 ±4 记账推出（Ledger 记一个数） | 无 |

- **视觉合法（Switch 可复现）：** 按画面掐完美窗口；每局后"继续游戏"；身上念珠 < 4 时停。这就是最优策略。
- **只能靠隐藏状态的策略：** 用 FSM 状态掐窗口（只省反应时间）、读随机数状态预测硬币（不可行）。设计上禁止依赖视觉做不到的隐藏状态，这里也没有理由用。oracle 在训练里可以用 `Perfect Anim` 状态给视觉模型打标签（精灵 80/81 模板）。
- **存档读回（另一个问题）：** 输掉的 4 念珠在 `Lose Rosaries` 那一刻就写进内存里的 PlayerData（`geo`、`dicePilgrimBank`），下一次存档（坐椅子、死亡、暂停菜单的存档退出）写盘；暂停菜单退出一定先存档（`ReturnToMainMenu` → `TimePasses` + `SaveGame`）【码 GameManager.cs:5339-5360】，所以"退出重来"撤不掉输局，只有杀进程或还原备份能回到上一个存档点，正式运行不允许。赌局中途没有押金（念珠只在结算时转移），中途离开既不扣也不退。赌局中能不能暂停：NPC 交互没有显式禁止暂停，`ListenForMenuSubmit` 在暂停时不读按键【码 ListenForMenuButton.cs】，实际表现【未核实】。

---

## 5. 骰子值不值（问题 5）

### 5.1 全部效果（代码 + 全部 2,068 个包里引用它的组件）【码】【包 `scan_pptr_dice.txt`】

1. **敌人命中护盾**【码 HeroController.cs:5430-5453、5723-5734】：装备时、伤害类型为 `ENEMY`、且这一下已经通过了无敌帧等判定，按计数器 `luckyDiceShieldedHits`（连续没挡住的敌人命中次数）取阈值 0/2/4/6/8/10，`Random.Range(1, 100)`（1–99）≤ 阈值就把这一下伤害置 0。挡住 → 计数归零；没挡住 → +1。非 `ENEMY` 的伤害（尖刺、岩浆、酸、爆炸等）或没装备时挨打 → 计数归零。挡下的一下照样走 `HeroDamaged`、取消攻击、受击音和 `StartRecoil`（以伤害 0 调用；无敌帧时长是否随伤害变化没查），和 Warding Bell 一样；跳过的是 `damageAmount > 0` 那一段：扣血、受击特效、伤害事件、Hunter 纹章蓄力重置、Warrior / Reaper 状态扣减、Thief Charm 掉钱【码 HeroController.cs:5455-5672】。计数器是 HeroController 的字段，不存档，跨场景、跨战斗保留，回主菜单后重建为 0【推】。2 格的重击也整下免掉。Warding Bell 已经把伤害置 0 的那一下仍会推进计数【码：铃的判定在骰子之前】。
2. **运气 ×1.1**（`GetLuckModifier`，只有两个调用点）【码 DamageEnemies.cs:1029、1286】：Wanderer 暴击率 2 % → 2.2 %（`wandererCritChance` 0.02【包 globalsettings】）；针附魔的"幸运命中"概率 ×1.1，数据里只有 `Fire Nail` 有（0.2 → 0.22，命中 2–5 次挂火 vs 普通 3–4 次）【包 profiles】。路线用 Hunter、不带火焰附魔，**对路线无效**。
3. **念珠磁铁加速**：念珠预制体 `Geo Small/Med/Large` 的 `magnetBuffTool` 就是磁石骰：同时装着念珠磁铁（`magnetTool`）时，念珠开始被吸的延迟 1.0–1.7 s × 0.7【码 CurrencyObjectBase.cs:596-607】【包 `geo_magnet.py`】。没装念珠磁铁时无效；壳片不受影响。**不增加任何掉落量**。
4. **Bellhart 铃铛许愿**：`Belltown_04`、`Belltown_Basement_03` 的 `Quest Bell Dropper`，装备时银铃概率 30 %（否则 25 %）【包 `fsm_bell_dropper.txt`】。路线外。
5. 其余引用只是工具主列表、Grindle 商品和赌局本身。没有别的作用。

### 5.2 护盾能挡多少（`gamble_math.txt`）【推：按代码精确计算】

- 每次敌人命中的护盾概率：计数 0/1/2/3/4/≥5 → 0 / 2.0 / 4.0 / 6.1 / 8.1 / 10.1 %。**每次挡住后的第一下必定不挡**。
- 长期平均：7.8 % 的敌人命中被挡，约每 12.8 下一次。

| 一场挨的敌人命中数 N | 期望挡下（计数从 0 开始） | 至少挡 1 下 | 期望挡下（计数处于长期分布） | 至少挡 1 下 |
|---|---|---|---|---|
| 1 | 0.00 | 0 % | 0.08 | 8 % |
| 2 | 0.02 | 2 % | 0.16 | 16 % |
| 3 | 0.06 | 6 % | 0.23 | 23 % |
| 5 | 0.19 | 19 % | 0.39 | 37 % |
| 6 | 0.28 | 27 % | 0.47 | 44 % |
| 13 | 0.82 | 65 % | 1.01 | 73 % |
| 18 | 1.21 | 80 % | 1.40 | 84 % |

- **对我们实测的挨打频率：** Bell Beast 门槛（oracle）66 场共 3 次受击、510 场 98.6 % CLEAR【`docs/facts/1.0.30000/m2_vision_view.md`、`probes.md`】：每场期望挡下 < 0.01，**几乎没用**。你的 Forum 半速练习赢的 4 场受击 7 / 13 / 6 / 18 次【`forum_human_demo.md`】：每场期望挡下约 0.3–1.4 次（即少掉 1–3 格），但 bot 的 Forum 目标是"每分钟 1–2 次受击以下"，期望挡下也会跟着降到 1 场 1 次以下。
- **安全监督不能把它算作保护**：它是随机的，`hits_to_death` 和交战门都按最坏情况算；`brain/ssbot/combat/hero_damage.py` 把它列为 `KNOWN_NEUTRAL` 是对的。它的价值只是"偶尔白挡一下"，降低真实死亡概率，但不改变任何规划上界。

### 5.3 占哪个槽、挤掉谁

- 黄色工具。Hunter（含 Hunter_v2）只有 2 个黄槽：1 个开着、1 个要 Memory Locket【DESIGN §3.6.5】【`forum_tools.md` §8】。S17（Last Judge）时只有 1 个黄槽（S18 的 Locket 才开第 2 个）。
- 现计划：黄 1 = **负重环带**（S09：受击无敌 ×1.3、击退 ×0.5【包，`forum_tools.md`】；规划器的击退包络在用，多怪时少被打进另一只怪）；黄 2 = **爬墙爪**（S20：Forum 末波左墙顶口袋、Dancers 贴角）。
- 磁石骰只能换掉其中一个。换爬墙爪等于放弃 Forum 口袋，不考虑；换负重环带 = 用"确定性的减击退 + 多 30 % 无敌帧"换"约 8 % 的命中白挡"。哪一个更好要按 boss 用 K1 的 A/B 测，不能凭直觉。

### 5.4 100 % 需不需要

- 需要：磁石骰是 57 个计数工具键之一，占 1 %【`four_achievements.md` §4.1–4.2】。
- 但**不用赌**：Ending 1 之后存档还在 Act 2，Dancers 已经打过，在别处坐一次椅子后兰布尔就死在 `Coral_33`，尸体旁的骰子免费捡（Act 1–2 都在）；Act 3 再错过也有 Grindle（300，只要没有就一直卖）【码】【包】。所以 100 % 部分**没有错过风险**，赌局对 100 % 也不是必要的。

### 5.5 建议

**Ending 1 路线：默认不拿。**
- 价值低：bot 挨打少，护盾期望很小；而且只能挤掉负重环带（S17 只有 1 个黄槽）。
- 代价：整段约 3–4.5 min（§3.5），落在 CP2（S17）这个本来就紧的检查点前；念珠 +16 可忽略。
- 风险：绕路几乎无风险（`Coral_43`、`Coral_33` 没有敌人，`Coral_35` 有尖刺）；赌局本身没有战斗风险。
- **什么时候改主意：** K1 用 DebugMod 在训练副本里直接给骰子（训练允许写，正式运行不允许），按 boss 对比"负重环带 vs 磁石骰"的 WOULD_DIE 上界和险情率；如果某场 A 类（Last Judge、Lace 2、GMS、Forum 等）换上骰子明显更好，再在 S17 加："爬完 `Coral_03` → left1 → `Bellway_08`（买钟椅 40，`benches.md` 本来就有这个条件购买）→ `Coral_35` → `Coral_43` → `Coral_33`：说话两次 → 赌 5 局（每局看画面掐完美窗口）→ 原路回 `Bellway_08` 坐下装上 → `Coral_03` → `Coral_32` → Last Judge"。交互目录要加一条"兰布尔赌局"（INTERACT 原语 + 新的"按住直到看到精灵 80/81 再松开"原语 + 成功信号检查）。

**100 % 部分：** 不赌。Ending 1 之后到 `Coral_33` 捡尸体旁的骰子（路过蚀阶时顺路，免费）；或 Act 3 在 `Coral_42` 找 Grindle 买（300）。

---

## 6. 对现有文档的修正

- **`research/four_achievements.md`**（本分支已改）：§4.3 表里磁石骰一行改为"Act 1–2 可得"，结论里"只能在 Act 3 拿、有数据直接证明的"从 3 个百分点改为 2 个（Everbloom、Pale Nails）；§5.4 第一条改为"Act 1–2 就能拿，可以不删，但没有空黄槽"；修订记录加一条。
- **DESIGN §3.6.4 "永不交战"**（建议，未改）：删掉"Lumble 的骰子"，在"仅 A/B，默认不做"里加"磁石骰（S17 绕路 + 兰布尔赌局约 3–4.5 min，完美掷骰稳赢，视觉合法；只能换掉负重环带；见 research/dice_pilgrim.md）"。
- **`research/claims.txt` [com11] 与"Consider Magnetite Dice in a spare yellow slot"**：取得方式没问题（Act 1–2 就有），问题是 Hunter 没有空黄槽。
- **100 % 清单**（`four_achievements.md` §4.3 末尾要求的那张）：磁石骰的来源写三条（§1.2），门槛"Act 1–2：赌赢，或 Dancers/Clawline 后的尸体；Act 3：Grindle 300"。

## 7. 待实测

1. 完美窗口的起点 T0（4.5 s 还是 4.83 s，是否每次一样），精灵 80/81 的样子和识别延迟，提示音；成功信号（震动 + 闪光）。oracle 可在训练里用 `Play Control` 的当前状态给这些画面打标签。
2. `Perfect Timing` 不复位的漏洞：完美一次后，下一局按一下就松是否仍算完美。
3. 每局实际时长、对话翻页时间、拿到工具时的弹窗是否要按键。
4. 赌局中暂停和存档退出的表现。
5. S17 绕路的实际往返时间（含 `Coral_43` 沙坑、`Coral_35` 爬升）。
6. 如果 K1 要比较负重环带和磁石骰：训练里用 DebugMod 给工具，按 boss 跑 A/B。
