# Forum 前路线上能拿的便宜工具（调研，2026-10-04）

起因：你说"多打几次半速应该能无伤过；刚才只装了一个道具，正常流程打到那里时还有什么便宜的道具吗"。本文回答三件事：(1) S25（Forum）之前在路线上或附近能拿到的全部工具和丝技，各自在哪、多少钱、要什么前置、绕路多久、计划里有没有；以及 S25 时的槽位够装几样；(2) 每样东西对 Forum 各波威胁有什么用（伤害、次数、甲壳碎片消耗、范围），按"Forum 价值 ÷ 代价"排序，并给出放得进槽位的组合；(3) 灵丝风暴和你说的"电串"在哪拿、多少钱、绕多远。

**标签：** 【包】离线 UnityPy 读训练副本 1.0.30000 的资产包（`dataassets`、场景包、`herodynamic`/`heroloading`、`globalsettings`、`resources.assets` 本地化）；【码】反编译 1.0.30000 C#（`C:\ssbot\decomp\1.0.30000\Assembly-CSharp`，文件:行）；【录】我们自己的录像（forum_human_demo.md）；【攻】社区资料（wiki 文本存档、社区路线逻辑图 `room_graph_data.json`），没有用游戏数据核对；【推】推断；【估】门距模型估计（方法同 forum_route.md §6：门坐标直线距离，4–8 u/s，每道门 0.5 s）；【未核实】待实测。

**脚本与原始输出：** `C:\ssbot\sandbox\forum_tools_scripts\`（全部离线、below-normal 优先级，没有连接任何游戏实例）。`loc.py` → `loc/`（解密的 EN/ZH 本地化）；`tools_all.py` → `tools_all.txt/json`（66 个 ToolItem 的类型、容量、补充方式、中英名、描述）和 `gameplay.txt`（Global Gameplay Settings）；`tool_tree.py`（单个工具的完整字段）；`damagers.py` → `damagers_*.txt`（英雄与工具预制体上的全部 DamageEnemies）；`throw_prefabs.py`、`find_pids.py`、`prefab_dump.py`（工具投射物预制体，`pf_cogfly.txt`）；`shop_lists.py` → `shop_lists.txt`（各商店的货单）；`shrine_skill.py`、`shrine_enum.py`（编织者神龛给哪个能力）；`forum_hm.py`（Forum 敌人的 HealthManager 伤害系数）；`forum_dh_flags.py`（Forum 伤害的属性标志）；`item_pos.py`（拾取物世界坐标）；`room_logic.py`、`reach.py`、`bfs.py`（社区逻辑图上的可达性和门数）；`ttk.py`（§3.2 的击杀次数表）、`ttk_kits.py` → `ttk_kits.txt`（§3.2b，制作匣 1 / 2 / 4 个）；`boomer_path.py` → `boomer_path.txt`（弧爪 `ToolBoomerang` 的字段、曲线关键帧、采样轨迹）、`curveclaw_tree.txt`（弧爪的 `usageOptions`）；`run.cmd`（运行器）；`fsm_weave10_eva.txt`。复用了 `four_ach_scripts`（`shops_compact.txt`、`summ2_tools.txt`、`quest_rewards.txt`、`quest_dump.py`、`fsm_dump3.py`）、`four_ach_fix/rawp.py`、`bench_scripts`（`gates_all.json`、`walk.py`、`costs.txt`）和 `forum_route_scripts`（`shops_all.txt`、`fx_crest_slots.txt`）。

## 0. 摘要（可直接转述）

1. **制作匣（Crafting Kit）计划里已经有一个，但买贵了、买晚了：** DESIGN 路线表 S23 的 "Crafting Kit" 是 Underworks 第十二席建筑师（`Under_17`）卖的，**450 念珠**【包 `Architect Stock`】【DESIGN §3.6.4 S23】（§3.6.5 的念珠合计没算这 450）。同样的东西 Deep Docks 熔炉之女卖 **180**，和计划里的熔岩钟同一家店（S06），不要工艺金属、没有出现条件【包】。**建议换店：S06 买熔炉之女的，S23 不再买建筑师的**——Forum 时还是 1 个，省 270 念珠，而且早 17 段到手（Lace 1 到 Trobbio 之间用工具都按 1 个制作匣算）。每个制作匣让所有**工具**伤害 +60%（不影响织针和丝技）【码】【包】。两家都买（2 个）只再多一点：第一波三只的受伤系数在 2 级降到 0.8 / 0.9，第二个制作匣每击只多 **9–29%**（多数 12–20%），但齿轮蜂杀一只 Reed 从 3 只变 2 只【包】【码】（§3.2b）。
2. **弧爪（Curveclaw）**：Hunter's March 斑驳斯卡尔，**140 念珠**，和计划里的裂痕面具同一家店（S10），零绕路【包】【攻】。它**不是飞出去再飞回手里**：0.38 s 飞到前方约 11 u 时只高约 2 u，然后边往回飞边升高，0.8 s 时在投掷点身后约 2 u、上方约 5.5 u（随机 ±5° 旋转，4.5–6.4 u），之后以约 68 u/s 水平往后直飞，插进墙里 3 s 后碎掉【包 `Curve Claw` 的曲线和缩放】【码 `ToolBoomerang.cs:519-566`】。Reed 在出生高度时比地面上的主角高约 8 u，**站在地上扔够不着**，要在它下方小跳 2–3 u 出手，或等它俯冲下来【推】。每次命中 3（1 个制作匣时 5），8 次，每次 5 甲壳碎片。它和直针抢第二个红槽，算 K1 A/B 候选，便宜，值得买来试。
3. **计划里已经有、但你练习时没用的：** **齿轮蜂 Cogfly**（S25，1 块工艺金属；自动追 11 u 内的敌人，每只约 5 击）【包】【攻】——两段录像 46 次尝试一只都没放【录】；**护佑钟 Warding Bell**（S08，免费）——Bind 时挨打**不掉血**并对周围造成 9（1 个制作匣时 14）【码】【攻】，但**这次 Bind 照样被打断：不回血、这次的丝白花、击退照旧**【攻 wiki】。它把"在不安全的时候 Bind = 掉血"变成"= 丢丝"，降低试 Bind 的代价；你 20 / 46 次死时丝是满的【录】，它能救一部分，但找空档本身还得靠打法。
4. **免费、顺路的：** **爪镜 Claw Mirror**（S22 打完 Trobbio 掉在台上，Bind 时伤周围敌人 21，有制作匣 28）【包】【攻】。**忆境纪念盒（Memory Locket）**：计划里已有 3 个（#1 S09 买、#2 S10 竞技场后拾取、**S18 Choral Chambers 的拾取**，应当就是 Grand Bellway `Bellway_City` 那个）【DESIGN §3.6.4】【包】【推：Choral Chambers 一带唯一的 Locket 拾取物】，正好开满 Hunter 的 3 个锁槽，所以 Bellhart 的 330 对 Hunter 不需要。另外路上还有 `Library_08`（S21）、`Under_08`（S23）两个免费拾取【包，拾取条件未查】，可以作为 #4 / #5 给 Reaper 开槽（Forum 组 A）。
5. **小绕路、免费：** **灵丝风暴 Thread Storm** 在 Greymoor 鸦湖（Craw Lake）上方的神龛 `Greymoor_22`，离 S11 本来要去的 Greymoor 钟（`Bellshrine_02`）**4 道门、约 283 u**，估 **2.5–4.5 min**；同一个湖里还有**三重镖 Threefold Pin**（顺手 +0.5–1 min）【包】【攻】【估】。注意：路线上的四个纹章（Hunter / Hunter_v2 / Reaper / Wanderer）都**只有 1 个技能槽**【包】，灵丝风暴和丝之矛只能二选一。
6. **你练习里的"电串"不便宜，正常路线拿不到：** 如果指**电枢球（Voltvessels，内部名 Lightning Rod）**：在 Memorium `Arborium_07`，要打完一场竞技场才出现【包】；按社区逻辑图要**雪灵披风（Faydown）**才进得去（只有灵丝升腾 Silk Soar 不够），路线在 Forum 前没有【攻】。如果指**伏特丝（Volt Filament，内部名 Zap Imbuement，丝技伤害 ×1.25）**【码】【包】：要在 Voltnest `Coral_29` 打 Voltvyrm，社区逻辑图要 Faydown 或 Silk Soar（任一），路线在 Forum 前也都没有【攻】。
7. **半速练习那套配装在正常路线上凑不出来：** 漫游纹章开着的只有 技能 1 + 红 1 + 黄 1，蓝 ×2 和第 2 个黄槽是锁的，**总共只有 2 个黄槽**【包】；那套（红 1 + 蓝 2 + 黄 3）比漫游开满还多一个黄槽，只能靠 Eva 的 Vesticrest（12 点纹章点数给黄、20 点给蓝；路线最多 8 点），再给漫游花 2–3 个忆境纪念盒【包】【码】【推】；多重缚丝器要 880 念珠 + 一个许愿【包】；制作匣 4 个、工具袋 3 个也远超路线（路线现实是各 1 个）。那次练习对第一波三只的工具伤害约是路线配装（1 个制作匣）的 **1.6–2.0 倍（多数 1.7–1.8）**：4 个制作匣是 ×3.4，但它们在 4 级的受伤系数降到 0.8 / 0.9【码】【包】（§3.2b）。**建议照路线能拿到的配装做一个练习存档**（§3.4 的组合 A），半速练出来的才能代表正式路线。
8. **S25 时的槽位（Hunter_v2，按计划的 3 个 Locket）：** 技能 1、红 2、蓝 2、黄 2【包】【DESIGN】。推荐：红 = 齿轮蜂 + 直针或弧爪（K1 实测弧爪对 Reed 的命中再定）；蓝 = 裂痕面具 + 护佑钟；黄 = 负重环带 + 爬墙爪；技能 = 丝之矛或灵丝风暴；制作匣 1 个（改在 S06 买）。念珠相对 DESIGN 路线表：制作匣换店 −270、弧爪 +140，**净省约 130**；时间约 +0.5 min 以内（不含灵丝风暴的绕路）。熔岩钟在 Forum 没用：Forum 场景里所有伤害都不带火焰标志【包】。

## 1. S25 时的槽位

**纹章槽**【包，`dataassets/tools/crestitems.bundle` 的 `ToolCrest.slots`，`forum_route_scripts/fx_crest_slots.txt`】：

| 纹章 | 开着的槽 | 锁着的槽（各要 1 个忆境纪念盒） |
|---|---|---|
| Hunter / Hunter_v2 | 技能 1、红（上）、蓝、黄 | 红（下）、蓝、黄 |
| Reaper | 技能 1、红（上）、蓝、黄 | 红（下）、蓝、黄 |
| Wanderer | 技能 1、红（上）、黄 1 | 蓝 ×2、黄 1（总共 6 个槽，只有 2 个黄槽） |

- 槽的类型必须和工具类型一致【码 `InventoryItemToolManager.cs:631`、`:868`】：**丝技只能进技能槽**；路线上的四个纹章（Hunter / Hunter_v2 / Reaper / Wanderer）**都只有 1 个技能槽**，所以丝之矛、灵丝风暴、丝刃冲刺只能装一个。（不是所有纹章都这样：Shaman `Spell` 有 3 个技能槽，Architect `Toolmaster` 0 个【包 `fx_crest_slots.txt`】；路线不用这两个。）
- 忆境纪念盒按纹章分别记录，花在 Hunter 上的对 Reaper / Wanderer 无效【码，forum_route.md §5】；Hunter 上开的槽进化成 Hunter_v2 时会带过去【码 `ToolCrest.cs:230-239`】。计划里有 3 个【DESIGN §3.6.4、§3.6.5】：#1（Pilgrim's Rest 150，S09）→ Hunter 红 2；#2（S10 Hunter's March 竞技场后拾取，`Ant_20` 的笼子尸体【包】【推】）→ 蓝 2；**S18 Choral Chambers 拾取**——Choral Chambers 一带唯一的 Crest Socket Unlocker 拾取物是 Grand Bellway `Bellway_City` (67.6, 24.3)【包】，所以就是它【推】→ 黄 2（DESIGN §3.6.5 还没给它分配用途；forum_route.md §7 提议 K1 选 Reaper 时给 Reaper 黄 2）。Bellhart 330 的 Locket（DESIGN 的"#3 可选"）在这 3 个都给 Hunter 时对 Hunter 已经没用。
- **计划外的免费忆境纪念盒**（场景包里引用 Crest Socket Unlocker 的拾取物；拾取条件、是否要解谜都**没查**）【包】：`Library_08`（Whispering Vaults 工作台房间，(105.3, 33.5)，S21）、`Under_08`（(61.1, 16.5)，S23 Underworks）；路线外或位置偏的还有 `Belltown`、`Coral_02`、`Halfway_01`、`Greymoor_16`、`Dock_13`、`Bone_East_25`、`Crawl_09`、`Shadow_20`、`Slab_Cell_Quiet` 等【包 `summ_tools.txt`】。`Library_08` / `Under_08` 可以当 #4 / #5：给 Reaper 开蓝 2 + 黄 2（组合 B 就能同带面具 + 护佑钟、爬墙爪 + 负重环带），或者在 S18 那个给了 Reaper 时补 Hunter 的黄 2【推，待查条件】。
- **Eva 的额外槽（Vesticrest）**：Weave_10 的 FSM 在"纹章点数" ≥ 12 时给第一个额外槽（**黄**）、≥ 20 给第二个（**蓝**）、≥ 27 给 Hunter_v3【包 `fsm_weave10_eva.txt`，rawp 解码；FSM 的 `Slot Bools` 数组顺序是 `UnlockedExtraYellowSlot`、`UnlockedExtraBlueSlot`】【攻 wiki：12 点给黄、20 点给蓝】。点数 = 已解锁、未进化的基础纹章上已开的槽数（技能槽也算）【码 `CountCrestUnlockPoints.cs`】，Hunter 进化后不再计入。我们的路线最多 Reaper 4 + Wanderer 4 = 8，**到不了 12**【推】。

**S25 时能同时装的（Hunter_v2，计划的 3 个 Locket 都给 Hunter）：** 技能 1 + 红 2 + 蓝 2 + 黄 2。Reaper（Forum 组 A）不花 Locket 时只有 技能 1 + 红 1 + 蓝 1 + 黄 1；Wanderer 不花 Locket 时只有 技能 1 + 红 1 + 黄 1，没有蓝槽，**装不了裂痕面具**。

## 2. S25 之前在路线上或附近能拿的工具和丝技

数值列：容量 = 基础容量（工具袋每个 +25%、壳囊 +50%，向下取整【码 `ToolItemManager.GetToolStorageAmount`】【包 `toolPouchUpgradeIncrease 0.25`、`shellSatchelToolIncrease 0.5`】）；**每次甲壳碎片 = 40 ÷ 基础容量**（所有红色工具补满基础容量都是 40 片）【码 `ToolItemManager.TryReplenishTools`】【包 `toolReplenishCost 40`】。伤害见 §3。

### 2.1 已经在计划里的

| 工具 / 丝技 | 类型 | 在哪、怎么拿 | 代价 | 段 | 容量 / 每次碎片 |
|---|---|---|---|---|---|
| 丝之矛 Silkspear | 技能 | Mosshome 神龛 `Mosstown_02`【包】 | 免费 | S02 | 每次 4 丝【码 `PlayerData.SilkSkillCost`】 |
| 直针 Straight Pin | 红 | Marrow `Bone_12`（Grindle 的牢房）拾取【包】【攻】 | 免费 | S04 ✚ | 12 / 3.33 |
| 熔岩钟 Magma Bell | 蓝 | 熔炉之女 110 念珠 + 1 工艺金属【包】 | 110 + 金属 | S06 ✚ | — |
| 蜇刺碎片 Sting Shard | 红 | 熔炉之女 140 念珠 + 1 工艺金属【包】 | 140 + 金属 | S06（"最先舍"） | 6 / 6.67 |
| 护佑钟 Warding Bell | 蓝 | `Dock_03b` 尸体上拾取（Far Fields 下方、Deep Docks 入口旁）【包】【攻】 | 免费 | S08 ✚ | — |
| 负重环带 Weighted Belt | 黄 | Pilgrim's Rest Mort 160【包】 | 160 | S09 ✚ | — |
| 工具袋 Tool Pouch | 升级 | Pilgrim's Rest 220【包】 | 220 | S09 | 所有红色工具容量 +25% |
| 裂痕面具 Fractured Mask | 蓝 | Hunter's March 斑驳斯卡尔 260【包】 | 260 | S10 ✚ | 1（工作台修复） |
| 登极握爪 Ascendant's Grip | 黄 | Songclave Jubilana 350（要先救她）【包，forum_route.md §1】 | 350 | S20（K1） | — |
| 制作匣 Crafting Kit | 升级（工具伤害） | 第十二席建筑师 `Under_17` 的 "Architect Tool Kit"（货单 `Architect Stock`）【包】 | **450**，没有条件【包】（DESIGN §3.6.5 的念珠合计没算） | S23 | 所有工具伤害 +60% |
| 齿轮蜂 Cogfly | 红 | High Halls `Hang_09` 合成桌，1 工艺金属【包】 | 金属 1 | S25 ✚ | 4 / 10 |

### 2.2 顺路、便宜（零绕路或不到 1 分钟）

| 工具 | 类型 | 在哪、怎么拿 | 代价 | 前置 | 绕路 | 计划里？ |
|---|---|---|---|---|---|---|
| **制作匣 Crafting Kit（熔炉之女）** | 升级（工具伤害） | 熔炉之女货单 `Forgedaughter Stock` 的 "Forge Tool Kit"，和熔岩钟同店（S06）【包】 | **180 念珠**，不要金属【包】 | 无（`extraAppearConditions` 空）【包】 | 0（同店，购买约 10–15 s【估】） | **计划里有制作匣，但是 S23 建筑师的 450**（§2.1）。建议换成这个；两家都买就是 2 个 |
| **弧爪 Curveclaw** | 红 | 斑驳斯卡尔的 "Ant Merchant Curve Claws Tool"，和裂痕面具同店（S10）【包】；wiki：Act 1 在他那里买，140【攻】 | **140 念珠** | 无【包】 | 0（同店，约 10 s【估】） | 否 |
| **爪镜 Claw Mirror** | 蓝 | Trobbio 打完后台上出现的拾取物（`Library_13` 的 `Boss Scene Trobbio/Collectable Item Pickup`，(73.8, 13.7)）【包】；"击败 Trobbio 的奖励"【攻】 | 免费 | 打败 Trobbio（S22 本来就打） | 约 5–10 s【估】 | 否 |
| 长针 Longpin | 红 | `Belltown_Room_shellwood`（Shellwood_01 的右门，Bellhart 正门上方，被木蜂巢挡着）【包】【攻】，房间内 37 u | 免费 | 社区逻辑图：无【攻】 | 若路线经过 Shellwood_01：约 20–40 s【估】 | 否 |
| 掘洞钻 Delver's Drill | 红 | Underworks `Under_14`（`Under_02` 的死胡同房间，入口到物品 72 u）【包】 | 免费 | 社区逻辑图：无【攻】 | 若路线经过 Under_02：约 45–80 s 往返【估】 | 否 |
| 碎壳挂坠 Shard Pendant | 黄 | Marrow `Bone_17`（离 Bell Beast 工作台 `Bone_04` 2 道门）【包】 | 免费 | 无【攻】 | 约 1–1.5 min【估】 | 否（只影响碎片收入，+25%【包】） |

### 2.3 小绕路（1–5 分钟）

| 工具 | 类型 | 在哪、怎么拿 | 代价 | 前置 | 绕路 | 计划里？ |
|---|---|---|---|---|---|---|
| **灵丝风暴 Thread Storm** | 技能 | Greymoor 编织者神龛 `Greymoor_22`（神龛 FSM 的 `Ability` = SilkSphere）【包】，从鸦湖 `Greymoor_15b` 顶上的 top1 进去 | 免费 | 社区逻辑图：S11 的能力就够，但要**游泳**过鸦湖，并用到鸦巢里的气球拉杆或踩怪弹跳【攻】（游泳是不是天生能力【推：是】） | 从 Greymoor 钟（`Bellshrine_02`）到神龛 283 u、4 道门，单程 37–73 s；往返 + 过湖 + 神龛过场 ≈ **2.5–4.5 min**【估】 | 否 |
| 三重镖 Threefold Pin | 红 | 同一个鸦湖右上的鸦巢 (184.3, 100.4)【包】，Tallcraw 看守【攻】 | 免费 | 同上【攻】 | 单独去 272 u、3 道门，往返 ≈ 1.5–3 min；和灵丝风暴一起只多 0.5–1 min【估】 | 否 |
| 壳囊 Shell Satchel | 黄 | 蠕道 `Crawl_01`，钢铁之魂专属（普通模式是亡虫囊）【包 `Tool Conditions`】【攻】 | 免费 | 社区逻辑图：从 Shellwood 一侧经 `Aspid_01` 下到蠕道，要 Cling Grip（S12 之后）【攻】 | 约 2–4 min【估，粗】 | 否 |
| 织光仪 Weavelight（灵丝恢复加快） | 蓝 | Weavenest Atla `Weave_03`，打完两只 Moss Mother 出现【包】【攻】 | 免费，但是一场 boss 战 | 离 Eva（S15）3 道门【包】 | 约 2–3 min + 一场双 boss【估】 | 否（风险不便宜） |
| 注丝套针 Injector Band | 蓝 | Whiteward `Ward_03`【包】 | 白愈钥匙（Jubilana 卖 220，条件是没在别处拿到）【包】 | 社区逻辑图：要白愈钥匙开电梯【攻】 | 从 `Song_05` 5 道门单程，约 3–6 min【估】 | 否 |

### 2.4 不便宜，或路线在 Forum 前拿不到

| 工具 | 为什么不算便宜 |
|---|---|
| **电枢球 Voltvessels**（Lightning Rod） | Memorium `Arborium_07`，要打完 Memoria 竞技场才出现（`Battle Scene/End Scene/Collectable Item Pickup Battle`）【包】；社区逻辑图下要 **Faydown**（只有 Silk Soar 到不了）【攻 `reach.py` A2F / A2S】。见 §4 |
| **伏特丝 Volt Filament**（Zap Imbuement） | Voltnest `Coral_29` 打 Voltvyrm 的奖励【包】【攻】；社区逻辑图下要 Faydown 或 Silk Soar（任一）【攻 `reach.py`】。见 §4 |
| 多重缚丝器 Multibinder | Bellhart，**880 念珠**（价格资产 "Multibind" 覆盖商品条目里的 120：`Cost` 取值器在 `costReference` 存在时返回它的值【码 `ShopItem.cs:282-292`】），而且要先完成"失踪送货员"许愿【包】 |
| 储备缚丝 Reserve Bind | Grindle 800【包】，或 "Final Audience" 许愿【攻】 |
| 钉刺 Tacks | 罪途"蟑螂内脏"许愿（10 个淤秽蟑螂内脏）的奖励【包 quest `Roach Killing`】；熔炉之女的条目不在她的货单里【包】 |
| 花芯囊 Pollip Pouch | 壳木林灰根的"花芯仪式"许愿，收 6 朵壳花【包】 |
| 长爪 Longclaw | 腐殖渠女猎手的"育巢盛宴"许愿【包】 |
| 念珠炮 Rosary Cannon | 拾取物在 Forum 隔壁的 `Hang_06` 场景包里【包】；wiki 说它在一扇要简易钥匙的门后【攻，门锁没用游戏数据核对】（简易钥匙在 Bone Bottom 卖 500【包】）；子弹是念珠 |
| 燧石板 Flintslate | Deep Docks 简易钥匙门后【攻】 |
| 机轮刃 / 迅捷脊锁 / 锯齿环 | 第十二席建筑师 360 / 140 / 230 + 各 1 工艺金属【包】。**锯齿环 Sawtooth Circlet**（内部名 `Brolly Spike`，**蓝**）：货单条件 `hasBrolly`（有 Drifter's Cloak 才上架，路线 S08 就有）【包 shops_all.txt】；开披风（滑翔）时旋转利刃伤周围敌人【loc】，代码里二段跳也会触发（`HeroController.cs:8948`，我们没有二段跳）；滑翔触发走 Brolly FSM，伤害数值和判定范围**还没读**；你 10-04 问能不能拿：能（S23 Underworks 的建筑师店，但 `Under_17` 是否在 S23 路径上没查）；代价是 230 + 第 3 块工艺金属（DESIGN 只预留了 2 块）和一个蓝槽（Hunter_v2 蓝 2 = 裂痕面具 + 护佑钟；Wanderer 路线没有蓝槽） |
| 丝弹 Silkshot | 要先在 Weavenest Murglin 拿到坏掉的工具，再花念珠 + 工艺金属修【攻】 |
| 爆燃囊 Pimpillo | Greymoor 西北的隐藏房间合成（`Wisp_06` 合成桌）【包】【攻】，要材料，位置偏 |
| 丝刃冲刺 Sharpdart | 蠕道 `Crawl_05` 神龛【包】；社区逻辑图下我们的能力到不了【攻】 |
| 德鲁伊之眼 Druid's Eye | Mosshome 许愿（苔莓）【攻】；只在挨打时给丝，Forum 里价值低（crests.md §4） |

## 3. 对 Forum 的价值

### 3.1 伤害怎么算

- **工具伤害** = 工具基础伤害 × (1 + 0.6 × 制作匣个数)【码 `DamageEnemies.cs:1014`】【包 `toolKitDamageIncrease 0.6`】，再乘敌人的等级系数，等级 = 制作匣个数【码 `HealthManager.cs:937`】。织针和丝技不吃制作匣，它们的等级 = 织针升级次数。伏特丝让丝技 ×1.25【码 `DamageEnemies.cs:1017`】【包 `zapDamageMult 1.25`】。
- **Forum 敌人的等级系数**（`HealthManager.damageScaling` 的 Level1–5，第 n 级用 Level(n+1)）【包 `hang_04_boss`】：

| 敌人（HP） | 0 级 | 1 级 | 2 级 | 3–4 级 |
|---|---|---|---|---|
| Reed 簧片战士（55） | 1.0 | 1.0 | 0.8 | 0.8 |
| Envoy 圣咏特使（38） | 1.0 | 1.0 | 0.9 | 0.9 |
| Choristor 圣咏使徒（55） | 1.0 | 1.0 | 0.8 | 0.8 |
| Choir Bellbearer 圣咏钟卫（35） | 1.4 | 1.0 | 1.0 | 0.8 |
| Clawmaiden 丝偶侍女（48） | 1.25 | 1.0 | 0.9 | 0.9 |
| Minister 圣咏大臣（60） | 1.25 | 1.0 | 1.0 | 1.0 |
| Maestro 圣咏指挥（65） | 1.0 | 1.0 | 0.8 | 0.75 |
| Choir Clapper 圣咏槌手（230） | 1.5 | 1.15 | 1.0 | 0.9 |

  所以第一个制作匣（不管在哪家买）对第一波三只是完整的 +60%；对 Bellbearer、Clawmaiden、Minister、Clapper 少一些，因为它们在 0 级本来就多吃伤害。**第二个制作匣**让第一波三只降到 2 级（Reed / Choristor 0.8、Envoy 0.9），每击只多 9–29%（多数 12–20%，§3.2b）；计划里已经有 1 个（S23 建筑师），所以"再买熔炉之女的"只值这一点，"换成熔炉之女的"才是省钱的做法。顺带：**Needle 2 对 Reed / Choristor / Maestro 只多 11%**（13 × 0.8 = 10，对 Needle 1 的 9）【包】【推】。
- **工具基础伤害**（游戏数据，和 wiki 表一致）：直针 5（`Tool Pin`）、弧爪每次命中 3、齿轮蜂每次命中 3（伤害资产 "Clockwork Hatchling"）、蜇刺碎片每根刺 4、电枢球投出 5 + 电击 3【包 `damagers_herodynamic.txt`】；三重镖 4+2+1、整次蜇刺碎片 10、护佑钟 9、爪镜 11+5×2【攻 wiki】。丝技用织针伤害的倍数：丝之矛 ×3、灵丝风暴每击 ×0.75（每 6 物理步一击）、丝刃冲刺 ×2.75【包 `damagers_heroloading.txt`】，wiki 的灵丝风暴是前 4 击 ×0.75 + 第 5 击 ×0.25【攻】。

### 3.2 每次使用的伤害 / 杀一只要几次

格子 = 一次使用的伤害 / 杀死这只要几次（全部命中）。`ttk.py` 生成【包】+【攻】，舍入按 round-half-even【推】。

| 手段 | 等级 | Reed (55) | Envoy (38) | Choristor (55) | Bellbearer (35) | Clawmaiden (48) | Minister (60) | Maestro (65) | Clapper (230) |
|---|---|---|---|---|---|---|---|---|---|
| 直针（每根） | 制作匣 0 | 5 / 11 | 5 / 8 | 5 / 11 | 7 / 5 | 6 / 8 | 6 / 10 | 5 / 13 | 8 / 29 |
| 直针（每根） | 制作匣 1 | 8 / 7 | 8 / 5 | 8 / 7 | 8 / 5 | 8 / 6 | 8 / 8 | 8 / 9 | 9 / 26 |
| 弧爪（每次命中） | 制作匣 0 | 3 / 19 | 3 / 13 | 3 / 19 | 4 / 9 | 4 / 12 | 4 / 15 | 3 / 22 | 4 / 58 |
| 弧爪（每次命中） | 制作匣 1 | 5 / 11 | 5 / 8 | 5 / 11 | 5 / 7 | 5 / 10 | 5 / 12 | 5 / 13 | 6 / 39 |
| 三重镖（每次 3 击） | 制作匣 0 | 7 / 8 | 7 / 6 | 7 / 8 | 10 / 4 | 8 / 6 | 8 / 8 | 7 / 10 | 11 / 21 |
| 三重镖（每次 3 击） | 制作匣 1 | 11 / 5 | 11 / 4 | 11 / 5 | 11 / 4 | 11 / 5 | 11 / 6 | 11 / 6 | 12 / 20 |
| 齿轮蜂（每只 5 击） | 制作匣 0 | 15 / 4 | 15 / 3 | 15 / 4 | 20 / 2 | 20 / 3 | 20 / 3 | 15 / 5 | 20 / 12 |
| 齿轮蜂（每只 5 击） | 制作匣 1 | 25 / 3 | 25 / 2 | 25 / 3 | 25 / 2 | 25 / 2 | 25 / 3 | 25 / 3 | 30 / 8 |
| 蜇刺碎片（整次） | 制作匣 0 | 10 / 6 | 10 / 4 | 10 / 6 | 14 / 3 | 12 / 4 | 12 / 5 | 10 / 7 | 15 / 16 |
| 蜇刺碎片（整次） | 制作匣 1 | 15 / 4 | 15 / 3 | 15 / 4 | 15 / 3 | 15 / 4 | 15 / 4 | 15 / 5 | 17 / 14 |
| 爪镜（每次 Bind） | 制作匣 0 | 21 / 3 | 21 / 2 | 21 / 3 | 29 / 2 | 26 / 2 | 26 / 3 | 21 / 4 | 32 / 8 |
| 爪镜（每次 Bind） | 制作匣 1 | 28 / 2 | 28 / 2 | 28 / 2 | 28 / 2 | 28 / 2 | 28 / 3 | 28 / 3 | 33 / 7 |
| 护佑钟（Bind 中挨打时） | 制作匣 0 | 9 / 7 | 9 / 5 | 9 / 7 | 13 / 3 | 11 / 5 | 11 / 6 | 9 / 8 | 14 / 17 |
| 护佑钟（Bind 中挨打时） | 制作匣 1 | 14 / 4 | 14 / 3 | 14 / 4 | 14 / 3 | 14 / 4 | 14 / 5 | 14 / 5 | 16 / 15 |
| 织针一刀 | Needle 1（9） | 9 / 7 | 9 / 5 | 9 / 7 | 9 / 4 | 9 / 6 | 9 / 7 | 9 / 8 | 10 / 23 |
| 织针一刀（Hunter_v2 连击 ×1.3，**只在连击计量 ≥ 6 击之后**【码 `DamageEnemies.cs:977-984`】【包 `hunterComboHits 6`】） | Needle 1 | 12 / 5 | 12 / 4 | 12 / 5 | 12 / 3 | 12 / 4 | 12 / 5 | 12 / 6 | 14 / 17 |
| 织针一刀 | Needle 2（13） | 10 / 6 | 12 / 4 | 10 / 6 | 13 / 3 | 12 / 4 | 13 / 5 | 10 / 7 | 13 / 18 |
| 丝之矛 | Needle 1 | 27 / 3 | 27 / 2 | 27 / 3 | 27 / 2 | 27 / 2 | 27 / 3 | 27 / 3 | 31 / 8 |
| 丝之矛 | Needle 2 | 31 / 2 | 35 / 2 | 31 / 2 | 39 / 1 | 35 / 2 | 39 / 2 | 31 / 3 | 39 / 6 |
| 灵丝风暴（4+1 击全中） | Needle 1 | 30 / 2 | 30 / 2 | 30 / 2 | 30 / 2 | 30 / 2 | 30 / 2 | 30 / 3 | 34 / 7 |
| 灵丝风暴（4+1 击全中） | Needle 2 | 34 / 2 | 39 / 1 | 34 / 2 | 43 / 1 | 39 / 2 | 43 / 2 | 34 / 2 | 43 / 6 |

### 3.2b 制作匣 1 / 2 / 4 个时的工具伤害

工具每击 = RoundToInt(基础 × (1 + 0.6 × 制作匣个数))（`DamageStack.PopDamage` 的乘数是叠加的，银行家舍入）【码 `DamageStack.cs:29-45`】，再乘敌人在"制作匣个数"那一级的系数并舍入【码 `HealthManager.cs:935-939`】。`ttk_kits.py` 生成（输出 `ttk_kits.txt`）。1 个 = 路线（不管哪家买），2 个 = 两家都买，4 个 = 半速练习那套。

| 手段 | 制作匣（每击） | Reed (55) | Envoy (38) | Choristor (55) | Bellbearer (35) | Clawmaiden (48) | Minister (60) | Maestro (65) | Clapper (230) |
|---|---|---|---|---|---|---|---|---|---|
| 直针（每根） | 1（8） | 8 / 7 | 8 / 5 | 8 / 7 | 8 / 5 | 8 / 6 | 8 / 8 | 8 / 9 | 9 / 26 |
| 直针（每根） | 2（11） | 9 / 7 | 10 / 4 | 9 / 7 | 11 / 4 | 10 / 5 | 11 / 6 | 9 / 8 | 11 / 21 |
| 直针（每根） | 4（17） | 14 / 4 | 15 / 3 | 14 / 4 | 14 / 3 | 15 / 4 | 17 / 4 | 13 / 5 | 15 / 16 |
| 弧爪（每次命中） | 1（5） | 5 / 11 | 5 / 8 | 5 / 11 | 5 / 7 | 5 / 10 | 5 / 12 | 5 / 13 | 6 / 39 |
| 弧爪（每次命中） | 2（7） | 6 / 10 | 6 / 7 | 6 / 10 | 7 / 5 | 6 / 8 | 7 / 9 | 6 / 11 | 7 / 33 |
| 弧爪（每次命中） | 4（10） | 8 / 7 | 9 / 5 | 8 / 7 | 8 / 5 | 9 / 6 | 10 / 6 | 8 / 9 | 9 / 26 |
| 三重镖（每次 3 击） | 1（6+3+2） | 11 / 5 | 11 / 4 | 11 / 5 | 11 / 4 | 11 / 5 | 11 / 6 | 11 / 6 | 12 / 20 |
| 三重镖（每次 3 击） | 2（9+4+2） | 12 / 5 | 14 / 3 | 12 / 5 | 15 / 3 | 14 / 4 | 15 / 4 | 12 / 6 | 15 / 16 |
| 三重镖（每次 3 击） | 4（14+7+3） | 19 / 3 | 22 / 2 | 19 / 3 | 19 / 2 | 22 / 3 | 24 / 3 | 17 / 4 | 22 / 11 |
| 齿轮蜂（每只 5 击） | 1（5） | 25 / 3 | 25 / 2 | 25 / 3 | 25 / 2 | 25 / 2 | 25 / 3 | 25 / 3 | 30 / 8 |
| 齿轮蜂（每只 5 击） | 2（7） | 30 / 2 | 30 / 2 | 30 / 2 | 35 / 1 | 30 / 2 | 35 / 2 | 30 / 3 | 35 / 7 |
| 齿轮蜂（每只 5 击） | 4（10） | 40 / 2 | 45 / 1 | 40 / 2 | 40 / 1 | 45 / 2 | 50 / 2 | 40 / 2 | 45 / 6 |
| 护佑钟（Bind 中挨打时） | 1（14） | 14 / 4 | 14 / 3 | 14 / 4 | 14 / 3 | 14 / 4 | 14 / 5 | 14 / 5 | 16 / 15 |
| 护佑钟（Bind 中挨打时） | 2（20） | 16 / 4 | 18 / 3 | 16 / 4 | 20 / 2 | 18 / 3 | 20 / 3 | 16 / 5 | 20 / 12 |
| 护佑钟（Bind 中挨打时） | 4（31） | 25 / 3 | 28 / 2 | 25 / 3 | 25 / 2 | 28 / 2 | 31 / 2 | 23 / 3 | 28 / 9 |

对第一波三只：2 个比 1 个每击多 9–29%（直针 8 → 9 / 10、弧爪 5 → 6、齿轮蜂每只 25 → 30、护佑钟 14 → 16 / 18），齿轮蜂杀一只 Reed / Choristor 从 3 只变 2 只；4 个比 1 个是 1.6–2.0 倍（多数 1.7–1.8）【码】【包】【推：齿轮蜂按每只 5 击全中，wiki】。

### 3.3 逐个看：对 Forum 各波的作用

第一波（索引 0：Reed + Envoy + Choristor，Garmond 还没来）是你 22 / 46 次死亡的地方；Reed 活得最久（中位 44 s），它打中你的 149 次里 101 次你在空中够它，飞针 49 次是单招最多【录 forum_human_demo.md §4】。

- **齿轮蜂（计划内，S25）**：放出后自己追 11 u 内的敌人（`Enemy Range` 圆半径 10.99），每只 5 点血、攻击间隔 0.5–1.0 s【包 `pf_cogfly.txt`】，wiki 说每只约 5 击【攻】。好处是**你躲的时候它在打**，不用跳起来够 Reed。4 只（工具袋 5 只）一共 60 / 100 伤害（制作匣 0 / 1），够打掉一只 Reed 或 Choristor。每只 10 片甲壳碎片。**建议第一波开场就放 2 只打 Reed。**
- **弧爪（140，S10）**：轨迹由 `SamplePosAtTime` 按两条曲线插值：目标点 = 投掷点 + 预制体变换（缩放 1.1、随机旋转 ±5°）作用后的 `flyOutPosition` (10, 5)，即约 (11, 5.5)【码 `ToolBoomerang.cs:333`、`:661-667`，`HeroController.cs:3722-3733`】【包 `Curve Claw`：`flyOutCurveDuration 0.8`、`startRotation ±5`、缩放 1.1】。`flyOutCurveX` 的关键帧是 (0, 0)、(0.5, 1)、(1, −0.2)，`flyOutCurveY` 从 0 平缓升到 1【包】，所以（面朝右、相对投掷点，`boomer_path.txt`）：0.38 s 到最远 (11, 2.1)，0.56 s (9.0, 3.8)，0.72 s (2.7, 5.0)，**0.8 s 到 (−2.2, 5.5)，也就是主角身后上方**（随机 ±5° 旋转作用在目标点上，终点高度在 4.5–6.4 u 之间）；之后转为刚体，按曲线末端的切线速度约 (−68, +5) u/s 一直往后飞，插进墙里停 3 s 后碎掉（`stuckIdleDuration 3`），**不回到手里**【码 `ToolBoomerang.cs:519-566`、`:569-576`】。伤害体在碎掉之前一直开着，所以身后那条约 5.5 u 高的水平线上也能打到敌人【码 `Break` 才关 damager】。伤害圈半径 0.9（×1.1）【包】。
  - 对 Reed：出生高度 y 12.53，地面上的主角 y 4.6【包 forum.md §2】，差约 8 u；地面出手最高只到投掷点上方约 4.5–6.4 u，而且是在身后【推】。**要打悬停的 Reed 得在它下方或稍前方小跳 2–3 u 出手，或者等它俯冲下来**；"地面就能打到飞着的 Reed"不成立。
  - 命中时速度先降到 20%，0.15 s 内恢复（`damageVelocityLerpCurve` 0.2 → 1、`damageVelocityLerpTime 0.15`）【包】【码 `ToolBoomerang.cs:627-636`】，伤害体每 9 物理步可再中一次（`multiHitter`）【包】，所以每次投掷打中几下**没有依据**（之前写的"每次 2 下、约 6 次投掷杀一只 Reed"是推测，去掉）。敌人在这个方向格挡时（`IsBlockingByDirection`）弧爪被弹开、直接跳到回程，0.1 s 内不造成伤害【码 `ToolBoomerang.cs:505-517`、`:776-790`】。
  - 命中伤害低（3 / 5），8 次。和直针比：直针水平直线，打地面的 Envoy / Choristor；弧爪打斜上方和身后上方。
- **直针（计划内，S04）**：水平速度 60 的直线飞镖【包 `usageOptions.ThrowVelocity (60, 0)`】，对地面的 Envoy / Choristor 好用，打 Reed 要跳到它的高度。12 根（工具袋 15），每根 3.33 片。和弧爪抢第二个红槽：两样打 Reed 都要跳；弧爪的优势是往斜上方和身后上方飞、能多段命中，直针每根伤害高、直线好瞄。**二选一要等 K1 实测弧爪对 Reed 的命中数再定**（§7），在那之前保留直针（计划内、免费）【推】。
- **护佑钟（计划内，S08）**：Bind 时被打**不掉血**——代码只是在 `bellBind` FSM 的 `Is Shielding` 为真时把这次的 `damageAmount` 置 0，之后照常走受击流程（`HeroDamaged`、`CancelAttack`、`RegainControl`）【码 `HeroController.cs:5414-5418`、`:5583-5585`、`:5802-5813`】；并对周围造成 9 / 14（制作匣 0 / 1）【攻】【§3.2b】。**但 Bind 照样被取消：不回血，这次 Bind 已经花掉的丝白花（没花掉的保留），击退照旧**；Bind 结束后护盾还会留一小会儿【攻 wiki Warding Bell】。所以它把"在不安全的时候 Bind = 掉血"变成"= 丢一次 Bind 的丝"，降低了试 Bind 的代价；但连续两次被打断就是两次的丝，而且不解决"找不到空档"。你 20 / 46 次死时丝是满的，14 次死前一次都没 Bind 过【录】：它能让"敢 Bind"便宜一些，**不能当成"带钟就随便 Bind"**。蓝槽和裂痕面具共用（Hunter_v2 开了蓝 2 就能同带）。
- **爪镜（免费，S22）**：Bind 时对周围造成 21 / 28【攻】。和护佑钟同是"Bind 时起作用"的蓝色工具，但它是进攻（清出空间），护佑钟是保护。钢铁之魂优先护佑钟；第三个蓝槽才考虑爪镜（Hunter 最多 2 个蓝槽）。
- **制作匣**：计划里已有 1 个（S23 建筑师 450）。第 1 个让上面所有工具 ×1.6，对第一波三只是完整的 +60%（系数 1.0），齿轮蜂从"4 只杀 1 只 Reed"变成"3 只"——这在现计划里已经算进去了。**熔炉之女的 180 有两种用法**：(a) 换店：S06 买它、S23 不买建筑师的，Forum 不变，省 270 念珠，早 17 段到手；(b) 两家都买：Forum 时 2 个，第一波每击再多 9–29%（多数 12–20%），齿轮蜂 3 只 → 2 只杀一只 Reed，相对现计划 +180【§3.2b】。建议 (a)；(b) 看念珠宽裕程度，由 K1 / 经济定【推】。
- **灵丝风暴（绕路 2.5–4.5 min）**：以主角为中心的旋转丝线，每 0.12 s 一击【包 `Sphere Ball` multiHitter 6 步】，Needle 1 全中 30，每次 4 丝。适合 Reed 俯冲突刺、Choristor 贴身时反打；丝之矛（27，直线穿透，射程远）更适合打远处的 Reed。**同一个技能槽**，只能二选一；你半速练习用的是灵丝风暴【录】。是否有无敌帧【未核实】。
- **三重镖（顺带）**：每次 3 击 7 / 11，10 次，每次 4 片。比直针每次伤害高，容量少。
- **蜇刺碎片（计划内但"最先舍"）**：放在地上的陷阱，整次 10 / 15【攻】，对冲过来的 Envoy（冲锋 42 次打中你【录】）和地面的 Choristor 有用，对飞着的 Reed 没用。要多 1 块工艺金属（Pebb 60）【包】。
- **负重环带（计划内）**：受击无敌 ×1.3、击退 ×0.5【包】；多只同时在场时（你的 237 / 437 次受击时场上 3 只【录】）减少被击退进另一只怪的风险。
- **裂痕面具（计划内）**：挡一次致命伤；Forum 的多段连招（Choristor 鞭、Reed 招架反击、Minister 连斩）每条正好 2 格【录】，面具在 1 格时只能挡第一下【攻 claims com10】。
- **熔岩钟**：Forum 场景里 229 个 DamageHero 只有 Garmond 的 5 个带标志（NonLethal），没有火焰【包 `forum_dh_flags.py`】（敌人运行时放出的炸弹不在场景里，forum.md 记为普通伤害）。**Forum 前把蓝槽从熔岩钟换成护佑钟。**
- **后面几波**：Clawmaiden（48，矛和矛爆炸 2 格）、Minister（60，每分钟最密）、Maestro（65）和它召出的小机械（28，每只 Maestro 3 只）、两只 Clapper（230）。这些波次有 Garmond 帮忙（13 场完整连战里 Garmond 杀了 201 只）【包 forum.md §9】；工具在这里的价值主要是快速清掉 Minister / Clawmaiden。Clapper 230 HP，工具只占小头（齿轮蜂 8 只才够一只），靠 Garmond 和左墙顶口袋（forum.md §10）。

### 3.4 排名和组合

按"Forum 价值 ÷（念珠 + 绕路 + 风险）"排【推】：

| 名次 | 东西 | 代价 | 理由 |
|---|---|---|---|
| 1 | 制作匣换店（S06 熔炉之女 180 代替 S23 建筑师 450） | −270 念珠，0 绕路 | Forum 不变（还是 1 个），省钱，早 17 段到手 |
| 2 | 齿轮蜂（已计划） | 1 金属 | 自动打 Reed，你躲的时候它在打；人工演示从没用过 |
| 3 | 护佑钟（已计划） | 免费 | 被打断的 Bind 不掉血（但不回血、丝白花），降低试 Bind 的代价 |
| 4 | 弧爪 | 140 念珠，0 绕路 | 往斜上方和身后上方飞，打 Reed 要小跳出手；和直针抢红槽，K1 实测定 |
| 5 | 额外的忆境纪念盒（`Library_08` / `Under_08`，#4 / #5） | 绕路未知，条件未查 | 计划的 3 个已开满 Hunter；这两个用于 Reaper 开蓝 2 / 黄 2（组合 B） |
| 6 | 灵丝风暴（+ 三重镖） | 2.5–4.5 min（+0.5–1 min） | 近身反打；和丝之矛二选一，K1 A/B |
| 7 | 第二个制作匣（两家都买） | 相对换店后 +450（相对现计划 +180） | 第一波每击 +9–29%，齿轮蜂 2 只杀一只 Reed |
| 8 | 爪镜 | 免费、S22 | 只有在不带护佑钟时才有槽 |
| 9 | 壳囊 | 2–4 min，占黄槽 | 齿轮蜂 4 → 7（加工具袋）；抢黄槽 |
| — | 电枢球、伏特丝、多重缚丝器、注丝套针、储备缚丝 | 见 §2.4 / §4 | 正常路线在 Forum 前拿不到或太贵 |

**组合 A（Hunter_v2，推荐给路线和练习存档）：** 技能 = 丝之矛（或灵丝风暴）；红上 = 齿轮蜂，红下 = 直针或弧爪（K1 定）；蓝 = 裂痕面具 + 护佑钟；黄 = 负重环带 + 爬墙爪（S18 的 Locket 给 Hunter 黄 2）；制作匣 1、工具袋 1。齿轮蜂 5 只，每只 25；直针 15 根或弧爪 10 次。

**组合 B（Reaper，Forum 组 A）：** 不给 Reaper 花 Locket 时：技能 = 丝之矛；红 = 齿轮蜂；蓝 = 裂痕面具（护佑钟装不下）；黄 = 爬墙爪（负重环带装不下，forum_route.md §5）。Reaper 的锁槽是红（下）、蓝 2、黄 2；用 `Library_08` / `Under_08` 两个免费拾取（条件待查）开蓝 2 + 黄 2，就能带面具 + 护佑钟、爬墙爪 + 负重环带；拿不到就要把 S18 那个给 Reaper（Hunter 的黄 2 改用 Bellhart 330）。

**组合 C（Wanderer）：** 不花 Locket 时只有 技能 1 + 红 1 + 黄 1，没有蓝槽，连裂痕面具都装不了；要用就得给 Wanderer 花至少 1 个 Locket（2 个才有面具 + 护佑钟），而且它总共只有 1 个红槽，齿轮蜂和直针 / 弧爪只能带一样。

## 4. 灵丝风暴和"电串"

**灵丝风暴（Thread Storm，内部 `Thread Sphere`，PlayerData `hasThreadSphere`）**
- 在哪：Greymoor `Greymoor_22` 的编织者神龛；8 个神龛共用一个 FSM，用 `Ability` 枚举区分，`Greymoor_22` 的值是 2 = SilkSphere【包 `shrine_enum.py`】。其他神龛：`Mosstown_02` 丝之矛、`Bone_East_05` Swift Step、`Shellwood_10` Cling Grip、`Under_18` Clawline、`Crawl_05` 丝刃冲刺、`Abyss_08` Silk Soar、`Slab_10b` 符文之怒【包】。
- 怎么去：`Bellshrine_02`（Greymoor 钟，S11 的目标）→ `Greymoor_02` → `Greymoor_15` → `Greymoor_15b`（鸦湖）→ top1 → `Greymoor_22`，4 道门、283 u【包 门坐标】【估】。社区逻辑图：要游泳过湖，再经鸦巢的气球拉杆或踩怪弹跳上到湖顶；S11 时的能力够用，不需要 Cling Grip【攻】。
- 代价：免费；时间约 2.5–4.5 min（往返 75–145 s + 过湖和拉杆 + 神龛过场）【估】。湖里有鸦虫、看守三重镖的 Tallcraw【攻】，算 B 类；神龛过场的禁暂停窗口要登记进 quit map【未核实时长】。
- 用法：每次 4 丝【码】，Needle 1 全中 30（Needle 2 43）【攻】【包】；有伏特丝时 ×1.25【码】。

**"电串"：两个候选都在路线外**（你练习里两个都装了，请你确认指哪个）
- **电枢球 Voltvessels**（中文 电枢球，内部 `Lightning Rod`，红色，`ToolItemToggleState`，两种形态）【包】：容量 5，每次 8 片碎片【包】【码】；投出（流星锤）5 + 电击 3 ×4，立桩（长矛）的伤害按织针等级【攻】【包】。在 Memorium `Arborium_07`（Memorium 和 Voltnest 是两个不同的地图区：本地化 `Map Zones` 里 `ARBORIUM` = Memorium、`VOLTNEST` = Voltnest 各自一条【包】；`Coral_29` 属于 Voltnest 是 wiki 的说法【攻】），物品挂在 `Battle Scene/End Scene` 下，要打完那里的 Memoria 竞技场才出现【包】；wiki 说在 Memorium 东北的隐藏墙后【攻】。社区逻辑图（`reach.py`）：有 Faydown 时从 `Song_25`（Dancers 和 Songclave 之间）经 `Arborium_01` … 到 `Arborium_07` 7 道门；**只有 Silk Soar、没有 Faydown 时到不了**；两样都没有也到不了【攻】。我们在 Forum 前两样都没有（forum.md §7 的组装记录：路线在 Forum 时没有二段跳和 Silk Soar）。**结论：不便宜**——要多拿雪灵披风（DESIGN "仅 A/B，默认不做"）再加一个真死竞技场。
- **伏特丝 Volt Filament**（中文 伏特丝，内部 `Zap Imbuement`，蓝色）：丝技伤害 ×1.25【码】【包】。Voltnest `Coral_29` 打败 Voltvyrm 的奖励【包】【攻】。社区逻辑图：有 Faydown 或 Silk Soar（任一）时从 `Bellway_08` 经 `Coral_35`、`Coral_35b` 3 道门；两样都没有时到不了【攻 `reach.py` A2 / A2F / A2S】；还要打一个 boss（A 类）。**结论：不便宜。**

## 5. 经济

- **念珠**：
  - DESIGN 路线表 S23 已经有一个制作匣（建筑师 450），但 §3.6.5 的念珠合计（约 1,200–1,600；加爬墙爪后约 1,550–1,950，forum_route.md §7）**没算它**，合计本来就该再加 450（换店后是 180）。
  - 组合 A 相对路线表：制作匣换店 −270、弧爪 +140 = **净省约 130**；相对 §3.6.5 那个漏算的合计是 +320（180 + 140）。
  - 如果两家都买（2 个制作匣）：相对路线表 +180，加弧爪 +320。
- **甲壳碎片**：每次补满一件红色工具的基础容量 40 片（工具袋、壳囊多出来的容量按同样的单价）【码】【包】。组合 A 一次补满：齿轮蜂 5 只 50 + 直针 15 根 50（或弧爪 10 次 50）= 100 片；碎片上限 400，每个工具袋 +25%（有 1 个工具袋时 500）【包 `currencyCaps`】【码 `Gameplay.GetCurrencyCap`】。正式跑 Forum 只需要进场前补满一次；Forum 之前各段用掉的要另算（DESIGN §3.6.5 的公式）。
- **工艺金属**：制作匣（两家都）、弧爪不要金属【包】；DESIGN 预留的 2 块（熔岩钟、齿轮蜂）不变；蜇刺碎片要第 3 块（Pebb 60）【包】。

## 6. DESIGN 修改建议（只是提案，DESIGN 未改，由你和 lead 定）

- §3.6.4 S06：加"**✚ 制作匣（熔炉之女 180，和熔岩钟同店）**"；S23：删去"Crafting Kit"（建筑师 450），或者保留成"第二个制作匣（K1 / 经济定）"。§3.6.5 念珠合计补上制作匣（180，或两家都买 630）。
- §3.6.4 S10：加"✚ 弧爪（斑驳斯卡尔 140，和裂痕面具同店；和直针的 K1 A/B 候选）"。S22：加"拾取爪镜（Trobbio 奖励，约 5–10 s）"。
- §3.6.4 S11：加"✚ 灵丝风暴 + 三重镖（鸦湖，`Greymoor_15b` / `Greymoor_22`；离 Greymoor 钟 4 道门；约 3–5 min；K1 定）"。
- §3.6.5 槽位：写明 S18 的 Choral Chambers 拾取（`Bellway_City`）给谁——默认 Hunter 黄 2（负重环带 + 爬墙爪）；K1 选 Reaper 打 Forum 时先试 `Library_08` / `Under_08` 两个免费拾取（#4 / #5，条件待查）给 Reaper 开蓝 2 / 黄 2，拿不到再把 S18 那个给 Reaper、Hunter 黄 2 改用 Bellhart 330。Forum 前在 `Hang_06b` 把熔岩钟换成护佑钟（Forum 没有火焰伤害）。
- §3.6.4 绕路排序：制作匣（S06）、齿轮蜂、护佑钟列"必留"；弧爪列"必留（便宜，K1 定装不装）"；灵丝风暴列"K1 A/B"；电枢球（要 Faydown）、伏特丝（要 Faydown 或 Silk Soar）列"不做"。
- Forum 计划（forum_planner_plan.md）：第一波剧本加"开场放齿轮蜂打 Reed"；带弧爪时"在 Reed 下方小跳出手，不从地面扔"。Bind 规则加护佑钟的上下文："被打断的 Bind 不掉血，但 Bind 取消、不回血、已花的丝白花、击退照旧"（只从审计确认的已装备工具推出，DESIGN §3.6.5 已有此规则）；**不能写成"带钟就随便 Bind"**。
- 练习存档：按组合 A 做一个 fo_* 存档（Hunter_v2、制作匣 1、工具袋 1、5 面具或 7 面具两版），替代半速练习用的那套（4 制作匣、3 工具袋、漫游的 Locket 槽 + Vesticrest 的额外槽、多重缚丝器、伏特丝、电枢球）。

## 7. 待实测 / 未核实

1. `Library_08`、`Under_08` 两个计划外的 Locket 拾取在路线经过时是否可拿、要不要解谜；`Bellway_City` 那个（S18 计划内）的具体拾取条件也没查。
2. 鸦湖路线：游泳是不是天生能力、气球拉杆在哪、S11 时能否不靠 Cling Grip 到 `Greymoor_22`（社区逻辑图说可以）；灵丝风暴神龛过场的禁暂停时长。
3. 弧爪对 Reed 的实际命中：每次投掷中几下（命中减速到 20%、每 9 物理步可再中，没有依据）、要跳多高才够得着悬停的 Reed、Reed 格挡时被弹开的比例；投掷点 `toolThrowPoint` 相对主角的偏移没查。齿轮蜂每只的实际击数和存活时间（它有 5 点血，会被打掉）。
4. 护佑钟：`bellBind` FSM 的 `Is Shielding` 从 Bind 哪一帧开始、到结束后多久为真；被打断时具体丢多少丝（wiki：已花的丢、没花的留）。灵丝风暴有没有无敌帧。
5. 路线是否经过 `Shellwood_01`（长针）、`Under_02`（掘洞钻）、`Under_17`（建筑师；如果 S23 本来不经过，换店还省一段绕路），决定它们是不是真的零绕路；绕路时间全是先验，等 oracle 跑路线的实测值替换。
6. 电枢球（要 Faydown）/ 伏特丝（要 Faydown 或 Silk Soar）的前置来自社区逻辑图，没用游戏数据核对。

## 8. 复现

```
C:\ssbot\sandbox\forum_tools_scripts\run.cmd loc.py            # 本地化
C:\ssbot\sandbox\forum_tools_scripts\run.cmd tools_all.py      # 工具表 + Gameplay 设置
C:\ssbot\sandbox\forum_tools_scripts\run.cmd damagers.py herodynamic_assets_all.bundle heroloading_assets_all.bundle
C:\ssbot\sandbox\forum_tools_scripts\run.cmd shop_lists.py
C:\ssbot\sandbox\forum_tools_scripts\run.cmd shrine_enum.py greymoor_22 bone_east_05 crawl_05 shellwood_10 under_18 mosstown_02 abyss_08 slab_10b
C:\ssbot\sandbox\forum_tools_scripts\run.cmd forum_hm.py
C:\ssbot\sandbox\forum_tools_scripts\run.cmd item_pos.py greymoor_15b library_13 arborium_07 ...
python C:\ssbot\sandbox\forum_tools_scripts\reach.py A1 Bellshrine_02,Greymoor_02 "thread storm,threefold pin"
python C:\ssbot\sandbox\forum_tools_scripts\ttk.py
python C:\ssbot\sandbox\forum_tools_scripts\ttk_kits.py        # §3.2b（制作匣 1 / 2 / 4）
C:\ssbot\sandbox\forum_tools_scripts\run.cmd boomer_path.py   # 弧爪轨迹 -> boomer_path.txt
python C:\ssbot\sandbox\forum_tools_scripts\reach.py A2S Song_25,Bellway_08 "voltvessels,volt filament"   # 另跑 A2 / A2F 对照
```
