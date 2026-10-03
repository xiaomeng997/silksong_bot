# Forum 配装与助战的路线调研（2026-10-02，M2 W8 / K1 输入）

起因：你的 Forum 打法（G&Z 助战 + 收割者纹章 Reaper + 爬墙爪 Ascendant's Grip 吸左墙顶 + Cogfly，见 [`plans/M2.md`](../plans/M2.md) "Forum 打法"）需要路线上先拿到这几样东西。本文回答：每样东西在哪、要什么条件、花多少钱和时间、对钢铁之魂有什么风险，以及 DESIGN §3.6.4 / §3.6.5 该怎么改（§7，只是提案，DESIGN 未改）。

**标签：** 【包】离线 UnityPy 读训练副本 1.0.30000 资产包（场景包 `scenes_scenes_scenes/*.bundle`、`dataassets`），实测数值；【码】反编译 1.0.30000 C#（`C:\ssbot\decomp\1.0.30000\Assembly-CSharp`）；【录】我们自己的录像实测；【攻】攻略和社区资料（wiki 文本、Steam 指南 g1 "Easy route to get SteelSoul/Speedrunner"、社区路线逻辑图 silksong-logic-manager-export），未经游戏数据核对；【推】推断；【未核实】待实测。

**脚本与原始输出：** `C:\ssbot\sandbox\forum_route_scripts\`（`shops.py` 商店表、`ids.py`/`scan_ids.py`/`scan_some.py` 资产引用扫描、`fsm_dump2.py` 状态机导出、`scene_tree.py` 场景树、`gates.py` 门位置、`threats.py` 敌人和伤害源、`toolitem.py` 工具字段、`graph.py` 房间图、`pace.py` 录像节奏；同名 `.txt` 是输出；复核时新增的脚本和输出以 `fx_` 开头：`fx_mono_fields.py` 组件字段、`fx_crest_slots.py` 纹章槽位）。Forum 本身的结构、波次、助战进场见 Forum 链的 `docs/facts/1.0.30000/forum.md`（分支 `worktree-wf_946a7803-63c-2`）。

**复核修订（2026-10-02，同日）：** 核对员指出的问题已逐条复查并改正：(1) Songclave 的许愿板、Jubilana、Songclave 工作台只在 `enclaveLevel` ≥ 1 时存在，前置是"敲 Songclave 钟 → Caretaker 过场 → 在 Songclave 以外的场景发生一次 TimePasses"（§1.1，影响爬墙爪、S18 方案和 S21 的工作台）；(2) `WildSlash Hero Damager 5` 的第二个 `DamageHero`（flags 0）未排除致死，按致命处理（§3.3）；(3) "看得见 Garmond = 未招募"只在进入 `Hang_06` 时成立，同一次停留里招募后他仍可见，改用对话键判断（§3.4、§3.6）；(4) `LoadSceneSingleCustom` 不调用 `LoadedFromMenu`，已从清除路径中删除（§3.5）；(5) 删掉"S11 与 Garmond 说两次话"的建议（§3.1）；(6) Forum 组 A 的增量时间改为分情况给出（§6）；(7) Reaper 槽位改为直接引用资产包（§5）。

## 0. 结论摘要

1. **爬墙爪 = Jubilana（City Merchant）在 Songclave 的商店，350 念珠**；商品条目本身没有购买条件【包】，但商店有两层前置：(a) **Songclave 必须已到 `enclaveLevel` ≥ 1**：许愿板、Jubilana、Songclave 工作台都在 `Song_Enclave` 的 "Level 1" 组里，`enclaveLevel` 为 0 时这一组不存在；从 0 升到 1 要先敲 Songclave 钟（`bellShrineEnclave`）、再进 `Song_Enclave` 看完 Caretaker 的强制见面过场（`metCaretaker`）、然后在 `Song_Enclave` 和 `Bellshrine_Enclave` **以外**的场景发生一次 TimePasses（坐工作台、坐车等），回来才有许愿板【包】【码】（§1.1）；(b) 她已被救：在许愿板接 "Save City Merchant" → 去 Choral Chambers 的 `Song_07` 打一波伏击（2 只小怪，伤害 1）→ 对话完成许愿 → 回 Songclave 她才出现【包】。黄色工具。**Dancers（S19）在 Jubilana 营救（S20）之前**，所以按现行路线顺序 Dancers 用不上爬墙爪；要用就得把 (a) 和 (b) 都提前到 S18。
2. **Reaper 纹章 = Greymoor 的收割者礼拜堂**：`Greymoor_07` 左门 → `Greymoor_20b`（门在拿到纹章前一直开着）→ `Greymoor_20c`。礼拜堂里有**4 波小竞技场**（6 只 Farmer 系小怪，伤害 1，含会抓人的 Farmer Scissors）、尖刺、爪形陷阱【包】。拿纹章要在神龛按 3 次 Bind，过程约 20 s，其中约 8–9 s 禁止暂停；拿到后**强制装上 Reaper 并卸下全部非技能工具（Fractured Mask、Weighted Belt、钟都没了），直到下一个工作台**；重生点改到礼拜堂并自动存档【码】【包】。S11 阶段的能力就够【攻】。增量绕路约 2–3.5 min。
3. **G&Z 链**【码】【包】：`metGarmond`（S11 在 `Greymoor_05` 的首遇是强制过场，期间禁止暂停）→ 打开 Whispering Vaults 屋顶捷径（`Library_09` 的拉杆，`libraryRoofShortcut`）→ **之后要发生一次"时间流逝"（坐工作台、坐 Bellway、存档退出、死亡、纹章神龛都算）**，`garmondInLibrary` 才会置真 → 回 `Library_09` 对话、切磋（460 HP），赢了置 `garmondWillAidInForumBattle` → Forum 前在 `Hang_06` 对话招募，置 `garmondAidForumBattle`。拉杆之后最近的工作台：Songclave 的 Level 1 工作台（要 `enclaveLevel` ≥ 1）或隔壁 `Bellshrine_Enclave` 的钟塔工作台（敲钟后出现），从拉杆过去距离几乎相同（§3.2）。
4. **从主菜单读档清除助战标志，已逐行核实**【码】：清除只发生在 `GameManager.LoadedFromMenu()`；它只在"读档进入第一个场景"时调用，也就是 Continue 和新游戏。普通过门、死亡重生、危险物重生、DebugMod 读 savestate 都不清（最后一项 Forum 链实测过）。**可以重新招募**：Garmond 一直站在 `Hang_06`（工作台房间 `Hang_06b` → Forum 门的必经路上），再对话一次就行，代价约 15–25 s 对话。**判断标志状态**：NPC 是否隐藏只在场景加载时判断一次，所以**刚进入 `Hang_06` 时**看得见 Garmond = 未招募；但同一次停留里招募之后他仍然站着，直到重新进入场景。可靠的判据是对话键：GARMOND_AID_MEET_FORUM / GARMOND_AID_REPEAT 后跟 REQUEST_AID 提示 = 未招募；GARMOND_AID_READY = 已招募【包】。
5. **切磋的致命源比 DESIGN 写的多**【包】【码】：G&Z 的大部分攻击和身体碰撞带 `NonLethal` 标志，打空血只是输掉切磋；但下方 8 段尖刺（SPIKES 1）、**G&Z 被打晕时的 `Stun Box`**（碰到扣 1，不带 NonLethal），以及 **`WildSlash Hero Damager 5` 上第二个不带 NonLethal 的 `DamageHero`**（代码上大概率不生效，但没排除，按致命处理）都可能扣掉最后一格面具（§3.3）。
6. **Cogfly 在 `Hang_09` 的合成桌做，消耗 1 块工艺金属，不花念珠**【包】。从确认合成到拿到物品约 8.3–9.3 s 禁止暂停；合成区所在楼层没有活动敌人，唯一的敌人（Understore Mite Giant）在下层排水区【包】。路线从上方顺 `Hang_08` 竖井下到 Forum 时会路过 `Hang_09`，增量约 30–40 s。
7. **Reaper 已解锁的槽：技能 1、红 1（上）、蓝 1、黄 1**；红（下）、蓝 2、黄 2 锁着【包】。Forum 配装是丝矛（技能/中立，与 Hunter 键位相同）+ Cogfly（红/上）+ Fractured Mask（蓝）+ 爬墙爪（黄）。**爬墙爪占掉唯一的黄槽，Weighted Belt 装不上**，除非在 Reaper 上花一个 Memory Locket，而 Locket 只给指定纹章的指定槽【码】。换纹章只能在工作台：Forum 前在 `Hang_06b` 换 Reaper 并重新摆工具，打完在下一个工作台换回 Hunter_v2。

## 1. 爬墙爪（Ascendant's Grip，ToolItem `Wallcling`）

**取得**
- 商店条目 `City Merchant Wallcling Tool`：货币 Money（念珠），**350**；`requiredItem` 无、`extraAppearConditions` 空、`questsAppearConditions` 空【包，`dataassets/shopitems.bundle`】。条目在 `City Merchant Stock` 列表里；`Song_Enclave` 的两个 `City Merchant Enclave` 对象（Normal World 的 Level 1 版在 (78.99, 8.14)，Black Thread World 版在 (101.47, 7.59)）的 `ShopOwner.stockList` 引用这个列表。场景包里没有任何拾取物直接给 `Wallcling`【包，全场景包按 path id 扫描】。
- 工具字段：`type` = 2 = Yellow，`baseStorageAmount` 0（被动工具，不用补充）【包，`tools/toolitems.bundle`】。
- 其他同店条目（参考）：Simple Key 650、Spool Extender 720、Heart Piece 750，以及若干要求 "Save City Merchant Bridge" 许愿完成的条目【包】。

**Jubilana 什么时候出现在 Songclave**【包】
- 两个 `City Merchant Enclave` 各带两个 `TestGameObjectActivator`：quest "Save City Merchant" 已完成 → 激活；quest "Save City Merchant Bridge" 可接且未完成 → 隐藏（Bridge 许愿要 `cityMerchantCanLeaveForBridge`，`GameManager.cs:1863` 只在 `enclaveLevel` > 2 且有二段跳时置真，我们的路线到不了）。只在场景加载时判断，所以救完要重新进一次 Songclave（g1 是存档退出后再回去买）【攻】。
- Normal World 那个 Jubilana 是 "Level 1" 组的子对象，`enclaveLevel` 为 0 时整组不存在（§1.1）。
- 第一次和她说话先走 `Meet`（CITY_MERCHANT_MEET 3 页）再开商店【包】。

### 1.1 Songclave 的前置：`enclaveLevel` ≥ 1【包】【码】

- `Song_Enclave` 的 `Enclave States` FSM `State Setup`（`fx_enclave_states_fsm.txt`）：读 `enclaveLevel`；1/2/3 → 打开 "Level 1"（2、3 再叠加 "Level 2"/"Level 3"）；0 时看 `bellShrineEnclave`：真 → 只开 "Meet Caretaker" 组，假 → 只开 "Pre Bellshrine" 组。
- **"Level 1" 组里有**：许愿板 `Quest_Board` (73.51, 9.11)、Jubilana `City Merchant Enclave` (78.99, 8.14)、Songclave 工作台 `RestBench` (38.84, 6.654)、Caretaker 等 NPC（`fx_enclave_states_tree.txt`）。"Meet Caretaker" 和 "Pre Bellshrine" 组里没有工作台、许愿板或商店。
- **0 → 1 的条件**只在 `GameManager.TimePasses()` 里（`GameManager.cs:1776-1785`）：当前场景**不是** `Song_Enclave` 也**不是** `Bellshrine_Enclave`，且 `metCaretaker` 为真。所以在 Songclave 里或钟塔里坐工作台、或在这两个场景里存档退出，都不会升级。
- `metCaretaker` 只由 "Meet Caretaker" 组里的 `Enclave Caretaker FirstMeet`（FSM `Dialogue`，状态 `Meet End`）设置（`fx_caretaker_firstmeet.txt`）。这是**进场景自动触发的过场**：`WaitForFinishedEnteringScene` → 关掉 `door1` 的碰撞 → 交出控制 1.0 s → CARETAKER_MEET_1 → 帐篷晃动 → CARETAKER_MEET_2 → Caretaker 出帐篷 → CARETAKER_MEET_3 → 置 `metCaretaker`、恢复 `door1`。FSM 里没有改 `disablePause`。时长取决于三段对话的页数，估约 20–40 s【推】。
- `bellShrineEnclave` 由 `Bellshrine_Enclave`（`Song_Enclave` door1 (65.79, 6.63) → `Bellshrine_Enclave` left1 (4, 7)）的 `Bellshrine Sequence` 设置：打 `Bell Shrine Lever`（(28.49, 5.03)）敲钟（`fx_bellshrine_flag.txt`）。钟塔的 `Bell Bench`（(28.51, 5.16)，和拉杆同一位置）由同一序列里的 `Bench Appear Sequence` 显出来，所以**敲钟之后才有**（`fx_bellshrine_seq_full.txt`）。
- **完整前置链**：进 `Song_Enclave`（Pre Bellshrine 状态，没有工作台）→ door1 进钟塔敲钟 → 回 `Song_Enclave`（场景重载，进入 Meet Caretaker 状态，强制过场，置 `metCaretaker`）→ 去 Songclave 以外的场景坐工作台、坐 Bellway 或 Ventrica 等 → 再进 `Song_Enclave` 才是 Level 1（有许愿板、Jubilana 和工作台）。
- 最近的"外面的工作台"【包：门位置】【攻：房间图】：`Library_08` 的 `RestBench` (26.09, 24.62)，路线 `Song_Enclave` bot1 (86, 3) → `Library_04` top1 (27, 218.5) → 下到 right2 (67.5, 134) → `Library_08` left1 (−0.5, 7) → 工作台；单程约 126 u、2 次过门，往返约 250 u、4 次过门 ≈ **1–1.5 min**【推】（回程要在 `Library_04` 里爬升约 84 u，能否爬上去【未核实】）。`Library_10`（right5，y 12）更远。`Song_05` 和 `Song_20` 的 `Lace NPC Citadel Meet` 也调用 TimePasses，但那是一次性剧情事件，不作计划依据。
- **对路线的意义**：DESIGN S18 写的 "Songclave：工作台" 在第一次到达时不存在；S20/S21 用 Songclave 的许愿板、Jubilana、工作台，都要求 S18 已敲钟、见过 Caretaker，且之后在别处坐过一次工作台。DESIGN S18 没写明要敲钟（§7 提议写上）；只要 S18 敲钟、见过 Caretaker，按现行顺序（S19 Dancers 前后在别处休息 → S20 回 Songclave）就自然满足；要在 Dancers 之前用许愿板（S18 方案）就要额外跑一次外面的工作台。route_check 要在任何 Songclave 许愿板、Jubilana、Songclave 工作台的访问前断言 `enclaveLevel` ≥ 1（或断言之前的段里依次有敲钟、Caretaker、Songclave 以外的 TimePasses）。

**营救（quest "Save City Merchant"）**【包】
- quest 资产本身没有出现条件（`playerDataTest` 空、`requiredCompleteQuests` 空），在 **Songclave 许愿板**（`Enclave Quest Board` 列表里有它；板子 `Quest_Board` 在 `Song_Enclave` (73.51, 9.11)）上接；许愿板本身要 `enclaveLevel` ≥ 1（§1.1）。
- 地点 `Song_07`（"Choral Chambers Merchant Room"，死胡同，唯一出口 right1 → `Song_05` left4）。`City Merchant Scene` 的激活条件是"已接且未完成"：没接许愿时这个场景不存在。场景里是一个 1 波的 `BattleScene`（`Song Pilgrim 01` 38 HP + `Song Pilgrim 03` 55 HP，伤害全是 1，flags 0）；战斗结束后她从桶里出来（约 4 s 动画），对话 CITY_MERCHANT_SAVED_1（5 页）→ `EndQuest` → SAVED_2（2 页）。
- `Song_27` 有一个只在"商人许愿已接"时才出现的侧拉杆（`Song_lever_side - merchant quest accepted`，(4.15, 10.37)，在 left1 → `Song_05` 旁边），接了许愿后从东边也能进 `Song_05`【包】【推：用途是给营救开路】。

**与路线的关系与绕路**
- DESIGN 现在把 Jubilana 放在 S20（✚）。许愿要先在 Songclave 的许愿板接，许愿板要 `enclaveLevel` ≥ 1（§1.1）；S18 敲钟、见过 Caretaker 的话，S20 时一般已满足（S19 前后在别处休息过）。
- **Dancers 问题**：DESIGN §3.5.7 和 §3.6.4 写着"Dancers 的贴角也靠爬墙爪"，但 Dancers 是 S19，Jubilana 是 S20：按现行顺序 Dancers 时还没有爪。要用就得在 S18、Dancers 之前完成"敲钟 → Caretaker 过场 → Songclave 以外的 TimePasses → 回 Songclave 接许愿 → `Song_07` 营救 → 回 Songclave 购买"。可行性取决于 S18 的实际路径能否到 `Song_05`/`Song_07`，以及 S18 路径上 Caretaker 之后有没有 Songclave 以外的工作台【未核实，路线数据生成后用 route_check 确认】。
- 时间（方法见 §6）：
  - **(a) S20 本来就经过 `Song_05`、`enclaveLevel` 已是 1**：增量 ≈ 1–2 min（接许愿 10–15 s、进出 `Song_07` 共 74 u + 2 次过门、伏击 15–40 s、对话 15–20 s、Songclave 见面加购买 15–20 s）。
  - **(b) 单独从 Songclave 工作台出发**：往返约 1,250 u、12 次过门（`Song_Enclave` → `Library_02` → `Song_20b` → `Song_20` → `Song_27` → `Song_05` → `Song_07`），总计 ≈ 4–7 min。
  - **(c) Dancers 之前（S18）**：在 (a) 或 (b) 之上再加 `enclaveLevel` 前置：外面工作台往返 ≈ 1–1.5 min（S18 路径在 Caretaker 之后本来就有外面的工作台时为 0）；如果现行 S18 不敲钟，再加敲钟 + Caretaker 过场 ≈ 0.5–1 min。合计 ≈ 1–4.5 min（S18 经过 `Song_05`）或 4–9.5 min（不经过），下限对应两项额外开销都为 0【推】。
- **念珠 +350**：DESIGN §3.6.5 的念珠预算（约 1,200–1,600）要加上这一项。

## 2. 收割者纹章（Reaper，`Greymoor_20b` / `Greymoor_20c`）

**位置与通路**【包】【攻】
- `Greymoor_07`（"Western Room"）的 left1 (−0.5, 43) → `Greymoor_20b` right1 (50.5, 5)；`20b` 的 door1 (16.72, 3.74) → `Greymoor_20c` left1 (0.5, 34)；神龛 `Crest Get Shrine` 在 `20c` 的 (37.77, 74.97)，比入口高 41 u。`Greymoor_07` 还连着 `Greymoor_06`（right1/right2）和 `Greymoor_08` 的 top1（bot1 (26, −0.5)）。
- **门**：`20b` 的 `Chapel Door Control`：纹章**未解锁 → 门开**；已解锁且 `chapelClosed_reaper` 为假 → 关门，并置 `chapelClosed_reaper`、把死亡重生点设到 `20b` 的标记。所以门不需要任何条件，拿到纹章后门在身后关上【包】。`Greymoor_07` 的 `Flames`/`candle glow` 只是按 `chapelClosed_reaper` 切换的装饰。
- **礼拜堂内部**：`20c` 有一个 `BattleScene`（4 波：Farmer Scissors ×1（29 HP）→ Farmer Catcher ×2（21 HP）→ Farmer Centipede ×1（50 HP）→ Farmer Scissors ×2；`startDelay` 1.0 / 1.5 / 1.5 / 2.0 s；`BattleScene.waves` 数组按 Wave 1–4 的顺序引用，`fx_g20c_battlescene.txt`；场景里各敌人和攻击判定的 `DamageHero` 都是伤害 1、flags 0，只有 Farmer Scissors 的 `RapidSlash Hit` 在场景里是 0，运行时由 FSM 设定【推】）；`Battle Scene` 带不可半持久的 `PersistentBoolItem`，打完永久完成。门是一座吊桥（`drop bridge`，(35.94, 37.05)），`openGatesOnEnd` 1。另有 1 段尖刺（SPIKES 1）和 3 个 `dustpen_trap`（ENEMY 1，【推】即 DESIGN S11 说的爪形陷阱）。房间里的敌人就是这 6 只波次敌人；Farmer Scissors 有 `Cut Down Hero Grab`（抓取）【包】。
- 社区路线图给的房间内要求：入口区 → 竞技场区要"拉开竞技场气闸（打拉杆）"且（尖刺下劈或攀边或 Cling Grip 或 Faydown……）；竞技场区 → 上层（神龛）要"竞技场完成"且（攀边或 Cling Grip 或……）；上层 → 入口可走"砍断绑住的平台"捷径（破藤），不用再穿过竞技场【攻】。攀边是初始能力，所以 **S11（还没有 Cling Grip）就能拿**【攻】【推】。g1 指南在 Bellhart 之后从 Greymoor_08 一侧去拿，"拿 Reaper 并打开捷径"【攻】。

**拿纹章的过程**（`20c` 的 `Crest Get Shrine` FSM `Control`）【包】【码】
- 交互 → 跳起刺下（0.5 + 0.05 s）→ `isInvincible` 置真 → 等你**按 Bind（施法键）3 次**（`Binds` = 3，每次约 0.7 s 爆发）→ 终爆 1.0 s → `Cancel Rumble` 2.0 s → `To Memory`（Reaper 的 `Load Memory Scene` 为假，不进记忆场景，`isInvincible` 置假）→ 置 `completedMemory_reaper`、显示纹章消息 2.5 s → **重新加载本场景**（`BeginSceneTransition` 到 `Greymoor_20c` 的 `door_memoryEnd`）→ `Set Return`：`RefillAll`、**重生点设到神龛的 `Death Respawn Marker`**（`SetDeathRespawnMarker` → `HeroController.SetBenchRespawn`，类型 0）、**`disablePause` = 1** → `QueueAutoSave` → 2.0 s → 2.25 s → `Crest Change`：`UnlockCrest` + **`AutoEquipCrestV2`** + 3.0 s → 收尾动画 → `End 2`：`GameManager.TimePasses()`、`disablePause` = 0、`SaveGameV2(createAutoSave)`。
- FSM 等待合计约 20 s，加上按 3 次 Bind 的反应时间约 25 s；**禁止暂停约 8–9 s**（`Set Return` 到 `End 2`），前面还有一次场景加载。这时房间的波次已打完，没有活动敌人，所以这段不能暂停的时间是安全的，但要登记进 quit map。
- **`AutoEquipCrestV2` 的后果**【码，`ToolItemManager.AutoEquip(crest, markTemp:false, removeTools:true)`】：立即装上 Reaper；Reaper 的槽只放技能（丝矛从旧纹章挪过来），**红、蓝、黄全空**。Hunter 自己存的配装不动，回工作台换回 Hunter 就恢复。所以**从神龛到下一个工作台这一路是 Reaper 手感、没有 Fractured Mask、没有 Weighted Belt**（血是 `RefillAll` 补满的）。
- **重生点和自动存档**：拿完后存档退出再 Continue，会出生在礼拜堂神龛（不是上一个工作台）。走到 `20b` 时门控又把重生点设到 `20b` 的标记【包】。章节边界和恢复表（§3.6.8）要知道这一点。

**最近的工作台**【包】
- `Greymoor_08` 的 `RestBench` (43.88, 4.36)：它在附加场景 `greymoor_08_caravan` 里（`Caravan Scene Loader` 按条件加载），只有跳蚤商队停在 Greymoor 时才有【推：DESIGN S11 写的"Moorwing 通过跳蚤商队跳过"说明 S11 时商队就在那里，待核实】。从神龛走：`20c` → `20b` → `07`（left1 → bot1）→ `08` top1 → 工作台，约 206 u、3 次过门。
- `Bellshrine_02`（Greymoor 钟）的 `Bell Bench` (20.51, 5.16)，S11 本来就要去。从礼拜堂过去要走 7–8 个房间【攻：房间图】，全程是没有工具的 Reaper，**不推荐**。

**绕路估计**（§6 的方法）
- 设 S11 在 `Greymoor_05` 上层（Garmond 处，(16, 52)）对话后继续向西。"`05` → `06` → `07` → `20b` → `20c` 神龛 → 捷径下来 → `20b` → `07` → `08` 商队工作台"约 450 u、7 次过门；不拿纹章直接 "`05` → `06` → `07` → `08`" 约 237 u、3 次过门。**增量**：213 u（27–53 s）+ 4 次过门（2 s）+ 竞技场（179 HP、S11 时针伤 5 → 36 刀，加波间 6 s，约 40–90 s【推】）+ 拿纹章 ≈ 25 s + 工作台换回 Hunter 并重摆工具 20–30 s ≈ **2–3.5 min**。
- 从 Bellhart 一侧（`Greymoor_08` 商队工作台出发往返）：约 412 u、6 次过门，加上相同的固定开销，≈ 2.5–4 min。
- 也可以推迟到 Act 2 坐 Bellway 回 Greymoor 拿（`Bellway_04` 紧挨 `Greymoor_05`），但要多两次 Bellway 来回，没有理由更好【推】。

## 3. Garmond & Zaza：完整链条

### 3.1 首遇（S11，`Greymoor_05`）
- `Greymoor_05` 的 `Garmond Scene`（`Garmond Sleep NPC` 在 (16.26, 52.05)，房间左上；left1 (−0.5, 52) 通 `Greymoor_06`，right1 (110.5, 43) 通 `Greymoor_04` 塔）。场景在 `garmondMoorwingConvoReady` 为真时被关掉；另一个 `PlayerDataTestResponse` 测 `defeatedVampireGnatBoss` / `garmondMoorwingConvoReady` / `visitedCitadel` / `garmondInDust05` / `garmondSeenInGreymoor10`（任一为真）【包】。所以要在**进 Citadel 之前、Moorwing 相关进展之前**和他说话。S11 正合适。
- **强制过场**：他被吵醒（主角进入触发区或发出声响）时，如果主角在他的视野范围（`Can See Range`）里，第一次会走 `Take Control`：`disablePause` = 1、强制对话 → 吼叫锁定 → `Meet`（GARMOND_MEET，5 页，置 `metGarmond`）→ `End Dialogue`（`disablePause` = 0）【包】。**从被看见到第一段对话结束都不能暂停**（约 15–25 s），要登记进 quit map，并且只在附近没有敌人时走进他的视野（`Greymoor_05` 有 Farmer Catcher、Centipede、Mitefly ×6、Slab Fly Large Cage（64 HP，身体 2））【包】。
- **只说一次（首遇过场）就够，不建议在 S11 再说第二次**【包】：第二次对话走 `Talk State?`，先测 Moorwing 分支（遇到过 Moorwing 且没打败、不在备用位置、没听过 Moorwing 对话、跳蚤商队不在 Greymoor 时 → GARMOND_MOORWING_INFORM，置 `garmondMoorwingConvo`，**不置** `garmondPurposeConvo`），否则才是 `Talk 1`（GARMOND_TALK1，置 `garmondPurposeConvo`）。`garmondPurposeConvo` 的唯一用处是 `Library_09` 少一次交互（那边对应的是 `Purpose` = GARMOND_TALK1_CITADEL，见 3.3），等于把一段对话从图书馆挪到 S11 有敌人的房间里，净收益约为 0，还要处理 Moorwing 分支。
- 也可以不在 S11 说：`metGarmond` 在 Choral Chambers 的"并肩作战"场景（`Song_01/02/13/17` 的 `Victory NPC`，条件是 `bellShrineEnclave` 或 `defeatedCogworkDancers` 或 `hasHarpoonDash`，再加上进过该房间）和 Sinner's Road `Dust_05` 也会设置【码 `GameManager.TimePasses`】【包】。这就是 DESIGN S18 的后备。

### 3.2 屋顶捷径与 `garmondInLibrary`（S21）
- 拉杆 `Song_lever_side` 在 `Library_09`（"Whispering Vaults Jumps"）的 (16.24, 17.42)，紧挨 left1 (−0.5, 13)；它置 `libraryRoofShortcut`。left1 → `Library_04` right1 (67.5, 189)，`Library_04` top1 (27, 218.5) → **`Song_Enclave`**（Songclave）bot1 (86, 3)。所以屋顶捷径把 `Library_09` 和 Songclave 连起来，只隔一个房间【包】。
- **`garmondInLibrary` 只在 `GameManager.TimePasses()` 里设置**：`!garmondInLibrary && libraryRoofShortcut && metGarmond`【码】。`TimePasses` 的调用点：死亡后 `PlayerDead`、`ReturnToMainMenu`（存档退出）、`MazeMistZone`【码】；FSM 里 89 个 `RestBench`、Bellway 站（`Bone Beast NPC`）、Ventrica（`City Travel Tube`）、6 个纹章神龛等也用 `SendMessage` 调它【包，全场景包扫描】。**也就是说拉完拉杆后必须先坐一次工作台（或坐车、存档退出），再回 `Library_09`，G&Z 才会在。** 这里的 TimePasses 没有场景限制（`GameManager.cs:1306-1309`），哪个工作台都行。最近的两个【包：门和工作台位置】：
  - Songclave 的 Level 1 工作台 (38.84, 6.654)：拉杆 → `Library_09` left1 17 u → `Library_04` right1 → top1 50 u → `Song_Enclave` bot1 → 工作台 47 u；**要 `enclaveLevel` ≥ 1**（§1.1）。
  - `Bellshrine_Enclave` 的钟塔工作台 (28.51, 5.16)：`Song_Enclave` bot1 → door1 20.5 u → 钟塔 left1 → 工作台 24.6 u，多一次进门，总距离和上一个几乎一样；**要已敲钟**（敲钟后才出现），不依赖 `enclaveLevel`。
  - 两个都没有（S18 没敲钟）时：`Library_09` left1 → `Library_04` 下到 right2 → `Library_08` 工作台 (26.09, 24.62)。
  - 路线规划只需断言"S21 之前已敲钟"（钟塔工作台）或"`enclaveLevel` ≥ 1"（Songclave 工作台）之一。
- `Library_09` 的 `Scene Control` 激活条件：`garmondInLibrary && !garmondWillAidInForumBattle && !garmondInEnclave`（后者要拿齐三首旋律加 Fine Pins 许愿，Forum 之前不会发生）【包】【码】。第一次看见时有一段 Garmond 冲撞 Song Pilgrim 的小场景，附带 `Enemy Scene`（Song Pilgrim 03 等，伤害 1，能致死）【包】。

### 3.3 切磋（`Library_09`）
- 对话（`Citadel Library NPC`，FSM `Dialogue`）【包】：每次交互进 `Check`：`garmondLibraryMet` 为假 → `Meet`（GARMOND_CITADEL_MEET，4 页）→ 结束；否则 `garmondPurposeConvo` 为假 → `Purpose`（GARMOND_TALK1_CITADEL，5 页，置 `garmondPurposeConvo`）→ 结束；否则 `Offer`（1 页）/`Reoffer` → Yes/No（SPAR_GARMOND）→ `Accept`（置 `garmondLibraryDefeatedHornet`，1 页）→ 开战。按 §3.1 的建议（S11 只有首遇），这里要交互 3 次。
- 开战（模板 `garmond_control`，`fsmtemplates_assets_garmond.bundle`）：`SetDeathRespawnNonLethal` "Death Respawn Marker Garmond" (81.08, 16.01)；G&Z 被限制在 x 54–94【包】。G&Z 的 `HealthManager` hp = **460**【包】（wiki 也是 460【攻】）。
- **致命性**【包】【码】：`HeroController` 扣到 0 血时调用 `Die((damagePropertyFlags & NonLethal) != 0, …)`（`HeroController.cs:5623`）；非致命死亡不改 `permadeathMode`、不留茧、不扣念珠，在标记处重生【码】。G&Z 的身体、Charge、Stomp、WildSlash Hero Damager 1–4 都是伤害 1、**flags 2 = NonLethal**。致命或未排除致命的有：
  1. 平台下方 8 段尖刺（SPIKES 1，x ≈ 57–101、y ≈ 7.5–13.3）。
  2. **`Stun Box`**（G&Z 被打晕时激活，layer 11，伤害 1，flags 0）。
  3. **`WildSlash Hero Damager 5`**：同一个对象上挂了两个 `DamageHero`，组件顺序是先 flags 2、后 flags 0（两个都启用，伤害都是 1）。代码分析：身体接触走 `HeroBox.CheckForDamage` → `GetComponent<DamageHero>()`，取第一个组件，即 flags 2；拼刀路径 `DamageHero.TryClashTinkCollider` 是每个组件各自执行、各自带自己的 flags 调 `TakeDamage`，但第一个处理的组件会对 G&Z 的 `HealthManager` 调 `PreventDamage`，第二个随后 `HasBeenDamaged` 为真直接返回（`DamageEnemies.cs:1417/1435`），而且只在挥刀 `CanHitSpikes` 为假时才扣血。所以**大概率**只有 flags 2 那个生效，但这依赖 Unity 对同一对象上两个组件的调用顺序，没有实测【码】【推】。**在 LethalBlock 的 `would_die` 实测排除之前按致命处理。**
  - 所以"切磋只有尖刺致命"（DESIGN §3.5.7、M2.md）要改成"尖刺、打晕状态下的 G&Z 本体，以及（未排除的）WildSlash 第 5 段"。实际规则：**切磋中剩 1 格面具时，任何 G&Z 的伤害都当致命**：不靠"输掉切磋"兜底，先 Bind 回血或拉开距离；打晕时不要贴身。
- 赢：`Death Hit` 把 `$Set PD On Defeated` 置真；`Library_09` 的 `PlaymakerFSMVariableOverrides` 把这个变量设为 **`garmondWillAidInForumBattle`**【包】。输了在标记处重生，可以 `Reoffer` 再打【包】。
- 时间：S21 时针伤 9（Needle 1；5/9/13/17/21 是 wiki 数值【攻】），460 HP 约 51 刀（Hunter_v2 连击 ×1.3 后约 40 刀）→ 60–150 s【推】。

### 3.4 招募（S25，`Hang_06`）
- `Hang_06` 的 `Aid NPC Control`：`hang04Battle` 为真 → 没人；"Shakra Final Quest" 已完成 → 出 Shakra 并把 `garmondAidForumBattle` 置假（我们路线不做这个许愿）；否则 `garmondWillAidInForumBattle` 为真 → 出 `Garmond Aid NPC`（(18.20, 5.81)）【包】。
- `Garmond Aid NPC`（FSM `Behaviour`，`fx_hang06_aid_npc.txt`）【包】：`Init`（场景加载后一帧）时 `garmondAidForumBattle` 为真 → `Accepted` → **NPC 隐藏**；`Accepted` 只能从 `Init` 进入。对话（全局 `INTERACT` → `Convo Check`）：标志为真 → `Ready`（GARMOND_AID_READY，不再提问）；否则 FSM 局部变量 `Activated` 为假 → `Meet`（GARMOND_AID_MEET_FORUM，2 页），为真 → `Repeat`（GARMOND_AID_REPEAT）；两者之后都是 Yes/No（REQUEST_AID）→ `Accept`：置 `garmondAidForumBattle`、GARMOND_AID_ACCEPT（3 页）→ `Accept 2` → `End Dialogue` → `Close By`。**招募后 NPC 留在原地**，直到下次进入 `Hang_06` 才因 `Init` 隐藏。选 No → `Refuse`（GARMOND_AID_REFUSE），再对话走 `Repeat`。约 15–25 s。
- 位置：`Hang_06b` 工作台 (12.83, 3.53) → left1 → `Hang_06` right1 (86.5, 5) → Garmond (18.2, 5.8) → left1 (−0.5, 7) → `Hang_04`（Forum）。**Garmond 正好在工作台到 Forum 门的直线路上**【包】。社区 Forum 存档的重生点就是 `Hang_06b` 的 `RestBench`【包，p7_s3】。
- Forum 里的进场：第 2 波开始 4 s 后读标志（Garmond 优先）。见 forum.md §4。

### 3.5 从主菜单读档清除助战标志：精确时机【码】
- `GameManager.LoadedFromMenu()` 清除 `vampireGnatRequestedAid`、`garmondAidForumBattle`、`shakraAidForumBattle`，并恢复记忆场景前的状态。
- 唯一调用点是 `GameManager.BeginSceneTransition(info)` 里的 `if (info.IsFirstLevelForPlayer) { ResetGameTimer(); LoadedFromMenu(); }`（`GameManager.cs:636-645`）。经 `BeginSceneTransition` 且 `IsFirstLevelForPlayer = true` 的来源：`RunContinueGame` → `ReadyForRespawn(isFirstLevelForPlayer: true)`（主菜单 Continue，也包括非菜单调用的 `ContinueGame`）；`RunStartNewGame`；`RunContinueGame` 里的 Act 3 开场；`OpeningSequence`。（PlayMaker 动作 `LoadSceneSingleCustom` 虽然也构造 `IsFirstLevelForPlayer = true` 的 `SceneLoad`，但它直接用 Addressables 加载场景、不调用 `BeginSceneTransition`，所以**不**清标志【码 `LoadSceneSingleCustom.cs`】。）
- **不清**的情况：普通过门；死亡后 `PlayerDead` 里的 `ReadyForRespawn(isFirstLevelForPlayer: false)`（钢铁之魂不涉及）；危险物重生；DebugMod 读 savestate（Forum 链实测，forum.md §7）。
- 标志本身是普通的 PlayerData 布尔值，工作台、自动存档、存档退出时照常以"真"写进存档；**清除发生在下次 Continue 读入内存之后**。`garmondWillAidInForumBattle` 不受影响。

### 3.6 对钢铁之魂的意义
- 招募之后、进 Forum 之前**任何一次存档退出 + Continue**（监督器的紧急退出，或章节在这里结束），助战都会丢。Forum 中途紧急退出也一样：Forum 在 `EndBattle` 写 `hang04Battle` 之前没有持久进度，Continue 后从 `Hang_06b` 出来、Forum 从第 0 波重打，标志已被清除。
- **可以重新招募，而且便宜**：上面三个条件不变，NPC 会重新出现在 `Hang_06`；工作台到 Forum 门本来就经过他，增量只是一段对话（约 15–25 s）。
- **Ledger 规则**（提案）：每次 Continue 后，若 `hang04Battle` 为假，就把"G&Z 助战"置为未提交；进 `Hang_04` 前必须重新确认。
  - 提交证据是对话观测：REQUEST_AID 提示后选 Yes，并看到 GARMOND_AID_ACCEPT 文本 → 已提交。
  - 视觉判据**只在刚进入 `Hang_06`（场景加载）时**有效：看得见 Garmond = 未招募，要对话；看不见 = 已招募（前提是 `garmondWillAidInForumBattle` 为真、没有 Shakra）。同一次停留里招募之后他仍然可见，不能据此判"未招募"。
  - 拿不准时对他交互一次：GARMOND_AID_READY（无提问）= 已招募，直接走；GARMOND_AID_MEET_FORUM 或 GARMOND_AID_REPEAT 后跟 REQUEST_AID = 未招募，选 Yes。不要因为"还看得见他"反复对话。
- 训练注意：savestate（DebugMod）不会触发清除，所以训练里永远看不到这个行为。路线预演要加一项：Continue 后读 PlayerData，确认标志为假、NPC 可见【未核实，待实测】。

## 4. Cogfly（ToolItem `Cogwork Flier`）

**合成**【包】
- 地点 `Hang_09`（"High Halls Cogfly Room"），`Craft Pickup` 在 (71.10, 35.71)；房间唯一出口 right1 (114.5, 35) → `Hang_08`（"Big Shaft"）left2 (−0.5, 90)。`Hang_08` 的 bot1 (15, −0.5) 通 `Hang_06` top1 (72, 30.5)，`Hang_06` → top1 要 Cling Grip（或 Faydown + 攀边、或 Silk Soar）【攻】；`Hang_08` 有 30 段尖刺和一只 Song Administrator【包】。
- FSM `FSM`：检视（COG_FLIER 1 页）→ `DialogueYesNoItemV3`（WISP_BOMB_PROMPT "Construct tool?"，`RequiredItem` = **Tool Metal ×1、ConsumeItem = 1**）。**不花念珠，只要 1 块工艺金属**。
- 物品字段：`type` 0 = Red，`baseStorageAmount` **4**，`replenishResource` = Shard（工作台用 Shell Shards 补充）【包】。

**禁止暂停的窗口**【包】
- `Wait`：`disablePause` = 1、交出控制、0.3 s → `Move Hero to Table`（走到 x 71.1，按交互区很短）→ `Hero Face Table` 1.5 s → `Craft` 4.5 s → `Turn Back`（淡屏 1.0 s、等 1.5 s、转身动画、0.5 s）→ `Get Item`：`disablePause` = 0、`SavedItemGet`。合计约 **8.3–9.3 s 禁止暂停**，之后还有获得物品弹窗【推：弹窗期间能否暂停未核实】。forum.md 的"约 8 s"与此一致。
- 安全：合成桌所在楼层（y ≈ 35）没有活动敌人；`Understore Mite Giant`（100 HP，身体 2）在 (92.92, 17.46) 的下层排水区，中间隔着 `Roof Collider`【包】【推：它上不来，待实测】。

**怎么排进路线**
- 只在以下条件都满足时按确认：房间里没有活动威胁（敌人已死或确认在下层）、监督器为 GREEN、没有 PAUSE_PENDING、满血。这 9 s 作为确定性过场登记进 quit map（§3.7.5）：监督器在窗口内收到退出请求时延后执行，这里没有威胁，所以不增加风险。
- 第一次进 High Halls 一般是 `Hang_01` → `Hang_02` → `Hang_03` → `Hang_13` → `Hang_08`（从 left1 y 154 进）→ 竖井下到 `Hang_06` → `Hang_04`【攻：房间图】；`Hang_07` → `Hang_06` 是从 `Hang_06` 一侧打开的单向门。**顺竖井下来时 `Hang_09` 就在 y 90 的侧门**：进出共 86 u、2 次过门、检视加确认约 4 s、合成约 9 s、弹窗 2–3 s，增量约 **30–40 s**。若从 `Hang_06b` 工作台专门上去：往返约 350 u、6 次过门（含 90 u 的尖刺竖井），约 1–2 min。
- 工艺金属预留 2 块（Magma Bell、Cogfly），与 DESIGN §3.6.5 一致。

## 5. Forum 配装：Reaper 的槽与和 Hunter 配装的冲突

**槽位**【包，`dataassets/tools/crestitems.bundle` 的 `ToolCrest.slots`（`Type`、`AttackBinding`、`IsLocked`），离线读取：`fx_crest_slots.py` → `fx_crest_slots.txt`；与 P17 运行时导出 `crests.json` 的 `crest_dump` 一致（该文件在主 checkout 的 `docs/facts/1.0.30000/` 下，尚未入库）】。Reaper 的原始行：槽 0 Skill/Neutral、1 Red/Up、4 Blue、6 Yellow 解锁；2 Red/Down、3 Blue、5 Yellow 锁定。

| 纹章 | 已解锁 | 锁定（需 Memory Locket） |
|---|---|---|
| Hunter / Hunter_v2 | 红（上）、蓝、黄、技能（中立） | 红（下）、蓝、黄 |
| Reaper | 技能（中立）、红（上）、蓝、黄 | 红（下）、蓝、黄 |
| Wanderer（参考） | 技能、红（上）、黄 ×2 | 蓝 ×2、黄 |

- **Locket 按纹章分别记录**：`InventoryToolCrestSlot` 解锁时只写当前纹章该槽的 `SaveData.IsUnlocked`，并消耗 1 个 "Crest Socket Unlocker"【码】。DESIGN 把 Locket #1（红 2）和 #2（蓝 2）花在 Hunter 上，这对 Reaper 没有作用。
- 工具类型【包】：丝矛 = Skill，Cogfly = Red，Fractured Mask = Blue，Warding/Magma Bell = Blue【攻】，Weighted Belt（`Weighted Anklet`）= Yellow，爬墙爪 = Yellow。

**Forum 组 A（你的打法）的配装**：技能（中立）= 丝矛；红（上）= Cogfly；蓝 = Fractured Mask；黄 = 爬墙爪。Forum 链的 `fo_A` 存档就是这样摆的（蓝槽空着，补上 Fractured Mask 即可，forum.md §7）。
- **丝矛键位不变**：两个纹章的技能槽都是 Neutral（不按方向 + 工具键）。Cogfly 在两个纹章上都是"上 + 工具键"。
- **冲突**：
  1. **爬墙爪和 Weighted Belt 抢 Reaper 唯一的黄槽**。不花 Locket 时 Forum 里没有负重环带（受击无敌 ×1.3、击退 ×0.5 都没了，DESIGN §1.5）。监督器的击退减半上下文只按审计到的已装工具推出（DESIGN §3.6.5 已有此规则），所以安全不受影响，但击退包络要按"无负重环带"计算。要两样都带，就要把一个 Locket 花在 Reaper 的黄 2 上：Choral Chambers 拾取的那个（S18）或 Bellhart 330 念珠的 #3；Pilgrim's Rest 那个是 150（DESIGN 的 #1）【包：商店价格】。
  2. Fractured Mask 和 Warding/Magma Bell 抢唯一的蓝槽；Cogfly 和 Straight Pin 抢唯一的红槽。
  3. 每个纹章有自己的已存配装。Reaper 从神龛拿到时只存了丝矛，所以第一次在 `Hang_06b` 换 Reaper 要把 Cogfly、Fractured Mask、爬墙爪逐个放进去（MenuDriver 用图标模板），之后再换就自动恢复【码 `AutoEquip`/`SetEquippedTools`】【推】。
  4. 换装和换纹章只能在工作台。Hunter_v2 的连击计数在换装时清零（crests.md），不影响安全。
- **换纹章的时间点**：Forum 前在 `Hang_06b`（Forum 的重生工作台，也是 Ventrica 站）换 Reaper + 摆工具 + 补 Cogfly，坐下存档，然后去 `Hang_06` 招募、进 Forum；打完在下一个工作台换回 Hunter_v2（Lace 2 等）。K1 若判定 Hunter_v2 地面打法够好，就不用换。
- 运动学和攻击判定：Reaper 的运动学行（贴墙、蹬墙、Reaper 下劈等）和攻击多边形已由运动学链做好（`worktree-wf_946a7803-63c-3`：`knowledge/1.0.30000/attacks/reaper.json`、`kin_jit` Forum 行），视觉层还需要 Reaper 的攻击动画模板【推】。

## 6. 时间估计的方法与汇总

- **距离**：门的世界坐标取自场景包里的 `TransitionPoint`（`gates.py`），按每个房间入口门到出口门的直线距离求和，没有算真实的平台路径。
- **节奏**：用你的录像 `C:\ssbot\data\human\20260930_210337` 校准（`pace.py`）【录】。直穿房间的直线等效速度：有敌人或平台的房间 3.1–4.1 u/s（`Bone_04` 205 u / 54.6 s、`Bone_East_03` 211 u / 54.1 s、`Bone_East_05` 188.5 u / 45.8 s、`Bone_09` 138 u / 45.2 s），通畅走廊 6.6–8.3 u/s（`Bonetown` 75.8 u / 11.3 s、`Dock_08` 108 u / 13.0 s、`Bone_03` 56.7 u / 6.9 s）。过门的实际耗时（前一场景最后一帧到后一场景第一帧）中位数 0.47 s（p10 0.45、p90 0.55，96 次）。所以按 **4 u/s（谨慎）到 8 u/s（通畅）** 估区间，每次过门加 0.5 s；固定开销（对话、过场、竞技场、合成）另加。这是先验，以后用 oracle 跑路线的实测值替换。

| 项 | 路线位置 | 增量时间（先验） | 其他代价 | 风险 |
|---|---|---|---|---|
| Garmond 首遇（只说一次） | S11 `Greymoor_05` | DESIGN 已有；首遇过场约 15–25 s | — | 首遇过场约 15–25 s 不能暂停 |
| Reaper 纹章 | S11（`05` → 礼拜堂 → `08` 商队工作台） | 2–3.5 min | — | 4 波 B 类竞技场（伤害 1，有抓取）；神龛 8–9 s 不能暂停；之后到工作台前没有工具；重生点改到礼拜堂 |
| Songclave 前置：敲钟 + Caretaker 过场 | S18 Songclave | 0.5–1 min（现行 S18 已敲钟则为 0） | — | Caretaker 过场交出控制约 20–40 s（不改 `disablePause`） |
| Songclave 前置：Songclave 以外的 TimePasses | Caretaker 之后、第一次用许愿板之前 | 按现行顺序为 0（S19 前后在别处休息）；S18 方案且 S18 路径上没有外面的工作台时 1–1.5 min（`Library_08` 往返） | — | — |
| 接 Jubilana 许愿 | S20（S18 方案：S18） | 10–15 s | 要 `enclaveLevel` ≥ 1 | — |
| Jubilana 营救 + 买爬墙爪 | S20；要用于 Dancers 就提前到 S18 | (a) 经过 `Song_05` 1–2 min；(b) 单独跑 4–7 min | **350 念珠** | 1 波伏击（2 只，伤害 1） |
| 屋顶捷径之后坐工作台 + G&Z 切磋 | S21 | 2–5 min（Songclave Level 1 工作台或钟塔工作台往返约 346 u、4–6 次过门 + 对话 3 次约 25–40 s + 切磋 60–150 s） | — | B 类：尖刺、打晕的 G&Z 本体、（未排除的）WildSlash 第 5 段致命；剩 1 格时任何 G&Z 伤害都当致命 |
| Cogfly 合成 | S25 竖井路过 `Hang_09` | 30–40 s（专门跑 1–2 min） | 1 块工艺金属 | 8.3–9.3 s 不能暂停（无威胁） |
| `Hang_06b` 换 Reaper + 摆工具 | S25 | 30–45 s | — | — |
| 招募 G&Z | S25 `Hang_06` | 15–25 s；每次 Continue 后再来一次 | — | 判据用对话键，不用"看得见他" |
| 打完换回 Hunter_v2 | S26 前的工作台 | 20–30 s | — | — |

**Forum 组 A 的增量**（Reaper 2–3.5 min + 两次换纹章约 1 min + 爬墙爪；不算已经在 DESIGN 里的 G&Z 和 Cogfly），按爬墙爪的取法分情况【推】：

| 情况 | 爬墙爪部分 | 组 A 合计 |
|---|---|---|
| (a) S20 买，S20 本来就经过 `Song_05` | 1–2 min | **约 4–7 min** |
| (b) S20 买，S20 不经过 `Song_05`（从 Songclave 单独跑） | 4–7 min | **约 7–12 min** |
| (c1) S18 买（用于 Dancers），S18 经过 `Song_05` | 1–4.5 min（含 `enclaveLevel` 前置） | **约 4–9.5 min** |
| (c2) S18 买，S18 不经过 `Song_05` | 4–9.5 min | **约 7–14.5 min** |

另加 **350 念珠**。如果现行路线在 S20 之前根本不敲 Songclave 钟，(a)(b) 再加约 0.5–1 min（敲钟 + Caretaker 过场；(c) 的区间已含这一项），否则许愿板不存在。K1 排序时按实际路线落在哪一行取值。

## 7. DESIGN 修改提案（§3.6.4 / §3.6.5；DESIGN 未改，由你和 lead 决定）

**§3.6.4 路线表**
- **S11** 内容改为："伏击竞技场、爪形陷阱区（绕过面具）；**与 Garmond 对话（首遇过场一次即可）**（`Greymoor_05` 左上 (16, 52)：GARMOND_MEET 置 `metGarmond`；首遇是强制过场，从他醒来到对话结束不能暂停，只在附近无敌人时靠近他；不必再说第二次）；**✚ Reaper 纹章**（`Greymoor_07` → `20b` → `20c`：4 波 B 类小竞技场、拉杆气闸、尖刺、爪形陷阱；神龛按 3 次 Bind；拿到后强制装 Reaper、卸下非技能工具，直到下一个工作台；重生点改到礼拜堂并自动存档 → 立即去 `Greymoor_08` 商队工作台换回 Hunter）；Moorwing 通过跳蚤商队跳过"。P50/P90 加约 +150 / +210 s（K1 判定不需要 Reaper 时去掉）。
- **S18** 的"Songclave：工作台"改为："**敲 Songclave 钟**（`Song_Enclave` door1 → `Bellshrine_Enclave` 的拉杆，置 `bellShrineEnclave`；钟塔工作台随之出现）→ 回 `Song_Enclave` 看 **Caretaker 强制见面过场**（置 `metCaretaker`，约 20–40 s 交出控制）。Songclave 的 Level 1 工作台、许愿板、Jubilana 要等之后在 Songclave 和钟塔以外的场景发生一次 TimePasses、`enclaveLevel` 升到 1 才出现；这一段要用工作台就用钟塔工作台"。若要在 Dancers 用爬墙爪，再加："Caretaker 之后去外面坐一次工作台（最近 `Library_08`，往返约 1–1.5 min；S18 路径上本来有外面的工作台则不用）→ 回 Songclave 许愿板接 'Save City Merchant' → `Song_07` 营救 → 回 Songclave 购买（350）"。
- **S19** Dancers 的"有 Ascendant's Grip 时贴角"加注："只有在 S18 已买到爪时才成立"。
- **S20** 改为："✚ Cogwork Core 西侧连战碎片、捷径、**Songclave 许愿板接 'Save City Merchant' → Jubilana 营救（`Song_07`，1 波伏击）→ 回 Songclave 见面并购买爬墙爪（350）**"；前提 `enclaveLevel` ≥ 1。
- **S21** 改为："竞技场、✚ 碎片、✚ Pale Oil、**屋顶捷径**（`Library_09` 拉杆 (16, 17)）→ **经捷径上 Songclave 坐工作台**（Level 1 工作台要 `enclaveLevel` ≥ 1；或隔壁钟塔工作台，要已敲钟，距离相同；`garmondInLibrary` 只在 TimePasses 时置真）→ 回 `Library_09` → ✚ **G&Z 切磋**（460 HP，交互 3 次；B 类：下方尖刺、打晕时的 G&Z 本体（`Stun Box`）、以及未排除的 `WildSlash Hero Damager 5` 第二个判定都按致命处理；**剩 1 格面具时任何 G&Z 伤害都当致命**，先 Bind 或拉开，不靠输掉切磋兜底）"。
- **S25** 改为："High Halls → 顺 `Hang_08` 竖井下行时在 `Hang_09` 合成 Cogfly（1 块工艺金属，确认后约 9 s 不能暂停，满足无威胁、GREEN、无 PAUSE_PENDING 才确认）→ `Hang_06b` 工作台（坐下存档；组 A：换 Reaper，摆丝矛 / Cogfly / Fractured Mask / 爬墙爪，补 Cogfly）→ `Hang_06` 招募 G&Z（对话观测确认：REQUEST_AID 选 Yes + GARMOND_AID_ACCEPT；刚进场景时看得见 Garmond = 未招募，但招募后他在本次停留中仍可见；拿不准时交互一次，GARMOND_AID_READY = 已招募）→ **Forum 连战** → Conductor's Melody → 下一个工作台换回 Hunter_v2"。
- **章节边界**加一条："S25 那一章从 `Hang_06b` 工作台开始（招募之前）。招募之后、进 Forum 之前不安排章节结束。任何 Continue（紧急退出或 Forum 中途退出）之后，Ledger 把 G&Z 助战置为未提交，重走 `Hang_06` 招募（约 20 s）"。
- **route_check** 加断言："任何 Songclave 许愿板、Jubilana、Songclave Level 1 工作台的访问之前，路线里已依次有：敲 Songclave 钟、Caretaker 过场、在 `Song_Enclave` 和 `Bellshrine_Enclave` 以外的 TimePasses（等价于 `enclaveLevel` ≥ 1）；钟塔工作台之前已敲钟"。
- **绕路排序**：
  - "必留"里的 G&Z 改写为"G&Z（Garmond 对话 + 屋顶捷径 + 坐工作台 + 切磋 + `Hang_06` 招募）"。
  - 新增"**Reaper 纹章：K1 定**（Forum 组 A 需要；约 2–3.5 min，S11 拿）"。
  - "Ascendant's Grip 暂列必留"改为"**Ascendant's Grip：K1 定**（350 念珠 + Songclave `enclaveLevel` ≥ 1 + Jubilana 营救；S20 买约 1–2 min（经过 `Song_05`）到 4–7 min（单独跑）；用于 Dancers 时必须在 S18 买，约 1–4.5 min 到 4–9.5 min；组 A 合计见 §6 的分情况表）"。

**§3.6.5 配装、槽位与经济**
- 纹章段加："Reaper 槽：技能（中立）、红（上）、蓝、黄已解锁，红（下）、蓝 2、黄 2 锁定；Locket 按纹章分别记录。Forum 组 A：丝矛 / Cogfly / Fractured Mask / 爬墙爪。Weighted Belt 只有在 Reaper 的黄 2 上花 Locket 时才能同带（Choral Chambers 拾取的那个，或 Bellhart #3），否则击退包络按无负重环带计算。只在工作台换纹章；Reaper 神龛的强制换装会卸下工具，直到下一个工作台"。
- 槽位段的 Locket 分配加选项："Locket #3（或 Choral Chambers 的那个）→ Reaper 黄 2（若 K1 选 Reaper + 爪 + 负重环带）"。
- 经济段的念珠加："爬墙爪 350（Jubilana）"，合计约 1,550–1,950；"工艺金属预留 2 块（Magma Bell、Cogfly）"不变；Shell Shards 加 Cogfly（红色工具，4 次，工作台按用量补充）。
- 监督器上下文："Reaper 神龛之后到下一个工作台：无 Fractured Mask、无负重环带、Reaper 运动学"——这只能从审计推出（规则已有），要在 S11 的绕路里显式写成一段"无工具行走"。

**§3.5.7 / §3.7.5（顺带）**
- G&Z 切磋一行把"唯一致命途径是下方尖刺"改为"尖刺、打晕状态的 G&Z 本体（`Stun Box`，flags 0），以及 `WildSlash Hero Damager 5` 的第二个 `DamageHero`（flags 0，代码上大概率不生效，LethalBlock `would_die` 实测前按致命处理）；剩 1 格面具时任何 G&Z 伤害都当致命"。
- quit map 加三个确定性禁暂停窗口：Garmond 首遇过场（`Greymoor_05`）、Reaper 神龛（场景重载 + 约 8–9 s）、Cogfly 合成（8.3–9.3 s）。Caretaker 见面过场交出控制但不改 `disablePause`，不必登记（暂停是否真的可用待实测）。

## 8. 待实测 / 未核实

1. Continue 之后 `garmondAidForumBattle` 为假、`Hang_06` 的 Garmond 重新可见、再对话能重新置真（实例上：组 A 存档 → 存档退出 → Continue → PROGRESS 读 PlayerData + 截图）。
2. Reaper 神龛：3 次 Bind 的输入窗口、`disablePause` 的实际时长、重载后重生点和自动存档、`AutoEquipCrestV2` 之后 Hunter 的已存配装确实不变。
3. G&Z 的 `Stun Box` 和 `WildSlash Hero Damager 5` 第二个 `DamageHero` 是否真能致死（用 LethalBlock 记录 `would_die` 而不实际死亡；WildSlash 第 5 段要分别测身体接触和拼刀两条路径）。
4. `Hang_09` 的 Understore Mite Giant 能否到达合成层；获得物品弹窗期间能否暂停。
5. `greymoor_08_caravan` 工作台在 S11 时是否存在（跳蚤商队的位置）。
6. S18 的路径能否到 `Song_05`/`Song_07`（决定爬墙爪能否用于 Dancers），以及现行 S18 是否敲 Songclave 钟、Caretaker 之后有没有 Songclave 以外的工作台。由数据生成的路线表和 route_check 回答。
7. Songclave 前置的实测：敲钟后钟塔工作台出现；回 `Song_Enclave` 触发 Caretaker 过场（时长、能否暂停）；在 Songclave 或钟塔坐工作台后 `enclaveLevel` 仍为 0，在外面坐一次后变 1，许愿板、Jubilana、Level 1 工作台出现。`Library_04` 从 right2 爬回 top1 是否可行。
8. 第 6 节的时间全是先验，等 oracle 跑路线的实测值替换。
