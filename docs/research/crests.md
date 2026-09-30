# 纹章与用户推荐配装调研（2026-09-30）

起因：用户（Switch 玩家）建议"操作不好时用漫游（Wanderer）：攻速快、怪死得快、招架多、丝多；带重力指环 + 绿梅 + 记忆晶石莽，没血退后回血"；又补充"操作好时猎人最好，只要不挨打攻击力一直很高"、"速通时钱只够开 Bellway，漫游要 500 念珠"、"出刀可以弹开部分攻击（招架）"。

方法：多代理调研（代码、中文资料、英文资料、路线影响四路并行 → 汇总 → 独立挑错）。标签：`[code]` 反编译 1.0.30000 C#；`[asset]` 离线解析 1.0.30000 资产包（三次独立解析一致，**未经运行时确认**）；`[rt]` 运行时导出；`[MS]`/`[SS]` 多个/单个社区来源；`[inf]` 推断。下文已按挑错意见修正。

## 1. 用户说的道具是什么

| 用户说法 | 官方中文名 / 英文 | 内部名 | 结论 |
|---|---|---|---|
| 漫游 | 漫游者纹章 / Wanderer Crest | ToolCrest `Wanderer`，键 CREST_PILGRIM_NAME | 确认 |
| 记忆晶石 | 记忆晶石 / Memory Crystal（蓝色工具） | ToolItem `Revenge Crystal` | 名称完全一致，确认。**不是** Memory Locket（忆境纪念盒） |
| 重力指环 | 很可能是 负重环带 / Weighted Belt（黄色工具） | `Weighted Anklet` | 推断（强）：1.0.30000 中英繁中文本里都没有"重力""指环"；游戏内描述称其为"重环"，装备后最大下落速度 30→38。**需用户确认**（另一个候选"棘刺手环"会让受到伤害 ×2，绝不能装） |
| 绿梅 | 很可能是 德鲁伊之眼 / Druid's Eye（蓝色工具） | `Mosscreep Tool 1` | 推断（强）：苔莓做的绿色护符，"莓/梅"同音。**需用户确认** |

## 2. 数值（离线资产 + 代码）

- **挥刀间隔** = max(冷却, 持续) `[code]`：Wanderer 0.30 s（持续 0.25、收招 0.10），Hunter 0.41 s（持续 0.35、收招 0.15）`[asset]` → Wanderer 每秒多挥约 37%。
- **收招** `AttackRecoveryTime` 同时挡冲刺、跳、Bind、施法 `[code]`：Wanderer 每刀早约 50 ms 可脱离，约等于 P8 测得的按键→画面延迟。
- **每刀伤害与产丝相同**：普通挥刀伤害倍率都是 1.0、产丝 Full `[asset]`；每次命中 +1 丝与纹章无关 `[code]`。所以对基础 Hunter，**每场战斗得到的丝一样多，只是来得更快**；对 Hunter_v2，因为 v2 用更少刀数杀敌，Wanderer 每场多约 25% 丝 `[inf]`。
- **Hunter 进化（用户第二条已证实）**：v2 连续 6 次命中后 ×1.3，v3 再 6 次后 ×1.5 `[asset]`；计数只增不减，任何扣血（含霜冻、酸等特殊伤害）、换装、`MaxHealth()` 清零 `[code]`。v3 需要其他纹章合计解锁 27 格，本路线达不到 `[SS]`。
- **DPS 对比**：对基础 Hunter（路线里 S15 进化之前，包括 Widow）Wanderer 约 +37%；对不挨打的 Hunter_v2（S17–S27 的 A 类 boss）只约 +9–12% `[inf]`。
- **判定**：离线按变换计算，Wanderer 的**向前距离与 Hunter 相同（差 < 2%）**，少的是高度（约 −33%）和身后覆盖 `[asset, 挑错复算]`；游戏内描述"距离较短"与此不符，待运行时碰撞体导出确认。
- **下劈**：Wanderer 正下方 Slash，Hunter 斜向 DownSpike `[asset][com8]`；Wanderer 下劈收招 0.09 s（Hunter 0.25 s）。两者下劈对象挂的是同一个无字段组件 `HeroDownAttack`，**很可能有同样的 8/16 步下劈 i-frame** `[asset]`，确认前按 0 步计。
- **暴击**（Wanderer）：丝 ≥ 9 且未被蛆附时，**每次针攻击命中**都有 2% 概率（Magnetite Dice ×1.1）×3 伤害、×1.5 击退 `[code, DamageEnemies.cs:1022]`；期望伤害只多约 4%。每次暴击触发 0.2 s 不可暂停的 HeroDamageShort 冻结。
- **dash-combo**：Wanderer 冲刺后 0.15 s 窗口内按攻击会触发冲刺连段，而不是普通挥刀 `[code]`；规划器要避免误触或学会使用。
- **槽位** `[asset]`：Hunter/v2/v3 相同：技能 1，红/蓝/黄各 1 + 各 1 锁定。Wanderer：技能 1、红 1、黄 2；**蓝槽 2 个全部锁定**，另黄 1 锁定。Memory Locket 按纹章分别记录，花在 Hunter 上的不带到 Wanderer `[code]`。→ 没花 Locket 的 Wanderer **装不了 Fractured Mask（蓝）**。
- **招架（用户第四条）**：弹刀与纹章无关，要求敌方判定 `canClashTink` `[code]`；成功后 0.15 s 无敌，0.1 s 后清掉攻击冷却，随后约 0.36 s NailClash 冻结不可暂停。挥得越快出刀机会越多 `[inf]`。离线看两种纹章所有基本挥刀 `canHitSpikes` 都为真，所以弹刀不会反伤 Hornet `[asset]`。
- **负重环带** `[asset]`：受击 i-frame ×1.3（1.0 s → 1.3 s），击退 ×0.5，攻击/弹刀水平后坐 8 → 4 步；代码默认 1.2/0.5/2 被资产覆盖。
- **德鲁伊之眼** `[code]`：每受 2 次伤害 +1 丝（升级版 +2）；丝满或 Bind 被打断时计数清零。
- **记忆晶石**：受击时生成晶体分身，敌人碰到后炸开 `[游戏文本]`；伤害数值只有 wiki 单一来源；爆炸可能触发 Lace 等会弹反的敌人的反击 `[SS]`。

## 3. 在哪拿、多少钱

- **漫游者纹章**：Bonegrave 的 Chapel of the Wanderer（Bone Bottom 西侧，Ruined Chapel 再往外）。两种进法 `[MS]`：
  - 早：Swift Step（S05）+ 从 Pebb 买 Simple Key **500 念珠**（即用户说的 500）+ 绕 Wormways；
  - 晚：有 Cling Grip（S12）后从 Ruined Chapel 上方翻门进入，**不用钥匙**（有来源称还需 Drifter's Cloak，路线 S08 已有）；此入口在 1.0.30000 是否仍可用、是否属于设计意图（NMG 规则）待确认。
  - 里面是 4 波竞技场（Pilgrim Hulk ×2、Hornfly、Winged Pilgrim 等），**死亡是真死**；结束有 1.85 s 不可暂停慢放；拾取时 `AutoEquipCrestV2` 强制装上 Wanderer 并**卸下全部非技能工具**（含 Fractured Mask）直到下一个工作台 `[code]`，Hunter 自己的配装保留。
- **负重环带**：Pilgrim's Rest 的 Mort，160 念珠；路线 S09 已计划购买。
- **德鲁伊之眼**：Mosshome 苔藓德鲁伊的"莓果采集"愿望，交 3 个苔莓（Moss Grotto、Bone Bottom 的飞行 Aknid 身上）；绕路时间未测。
- **记忆晶石**：Mount Fay 山脚（Act 2，经 The Slab，路上有霜冻）；不在路线上。

## 4. 结论

1. **不采用用户的三件套作为配装。** 负重环带本来就在计划里（S09）。德鲁伊之眼和记忆晶石都只在**挨打时**生效；bot 的战斗设计以不挨打为不变式，这两件几乎不触发。记忆晶石还在 Act 2 路线外，永不去取。"莽上去、没血退后回血"是用挨打换输出的人类打法，钢铁之魂下 bot 不这样打。
2. **S01–S12 保持 Hunter。** 早拿 Wanderer 要多花 500 念珠，在现有约 1,200–1,600 的预算上再加；是否值得等 P10 测出念珠收入再定。
3. **Wanderer 作为 A/B 候选，与 Reaper 一起，而不是默认。** 收益（挥刀快、收招短、丝来得快）在进化前的 Widow 最大（约 +37%），对 S17 以后不挨打的 Hunter_v2 只有约 +9–12%；代价是：
   - 绕路约 300–600 s（未实测），且落在现在"≤ 17,400 s 概率约 0.84"的预算上；
   - 新增一个死亡是真死的 B 类竞技场；
   - 额外一个 Locket（Bellhart 330 念珠）才能在 Wanderer 上装面具 + 钟；红槽上限 1；
   - 第二套运动学模型和视觉模板（Hornet 攻击动画、HUD 线轴框、存档槽图）。
4. **决策规则（K1，M2 结束时）：** 用 S15 之后的 boss savestate（Last Judge、Lace 2，另加 Forum、Widow）比较**纹章 + 配装的组合**（Hunter_v2 / Wanderer / Reaper），每组 ≥ 200 次随机起点。先看 WOULD_DIE 上界和险情率，击杀时间次之。同时统计丝/秒、Bind 次数、弹刀次数、不可暂停时间占比、惩罚窗口利用率。纹章可以在工作台按 playbook 切换，所以结论可以是按 boss 选。
5. 社区的钢铁之魂配装并不统一（Hunter、Reaper、Wanderer 都有）。唯一找到的中文"钢铁之魂 + 速通"通关（3 h 59 m）用的是 Wanderer + 德鲁伊之眼 + Warding Bell，但作者说明中间用了 SL 和备份，不能直接当一命通关的依据 `[SS]`。

## 5. 运行时确认清单（P17，soak 结束后用 oracle 做）

- a. 每个纹章（Hunter、Hunter_v2、Wanderer、Reaper）的 `HeroControllerConfig` 实际值；确认 Hunter 走 'Default' 配置。
- b. 每种挥刀对象的伤害倍率、产丝、`canHitSpikes`、`doesNotParry`、世界坐标碰撞体多边形（带旋转），定下攻击距离。
- c. `Global Gameplay Settings` 中的暴击、猎人连击、负重环带、棘刺手环、苔藓工具参数。
- d. Wanderer 下劈是否给 8/16 步 i-frame、弹跳高度和速度。
- e. 每场战斗每个纹章的 FreezeMoment 记录（暴击、弹刀），不可暂停时间占比。
- f. `HunterUpgState.CurrentMeterHits` 的逐帧轨迹和每次清零原因；确认坐工作台会调用 `MaxHealth()`。
- g. Sprint FSM 的 Wanderer dash-combo：谁打开窗口、效果（伤害、位移、i-frame），普通输入会不会误触。
- h. 每个纹章的 Bind 回血量和时长。
- i. 花 Locket 之后的 `ToolCrest.slots` 与 `PlayerData.ToolEquips`，确认 Locket 不在纹章之间转移。
- j. Chapel_Wanderer：Cling Grip 入口在 1.0.30000 是否可用、是否需要 Drifter's Cloak、4 波敌人、暂停/退出阻塞、往返最近工作台的时间。
- k. 拾取 FSM 确认卸下哪些工具。
- l. Weave_10（Eva）的 `AutoEquipCrestV4` 是否强制换回 Hunter_v2（wiki 称 Patch 3 修了卸工具的问题）；最简单的规避是进 S15 前在工作台换回 Hunter。
- m. Wanderer 的 HUD/菜单模板：线轴框、"幸运"动画、存档槽线轴（普通 + Steel）、`wanderer_*` 攻击动画。
- n. 各 Memory Locket 的确切位置和价格；Bellhart 的 Locket 是否在 Widow 之前就卖（有单一来源称 Greymoor 车站附近可拾取一个）。
