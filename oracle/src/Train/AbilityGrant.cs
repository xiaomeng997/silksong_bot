using System;
using System.Collections.Generic;
using GlobalEnums;
using Rpc = SsOracle.Ipc.Rpc;

namespace SsOracle.Train
{
    /// <summary>
    /// Training-only ability grants on the sandbox save (soak --abilities), through the game's own data paths
    /// (1.0.30000, m0 §2.9):
    ///   abilities.grant {set: "movement"|"combat"|"all", tools?: [name, ...], skill?: name, unlock_slots?: false}
    ///   abilities.list  {all_tools?: false}
    /// <list type="bullet">
    /// <item>movement: PlayerData hasDash (Swift Step: dash, held = sprint), hasWalljump (Cling Grip), hasBrolly
    /// (Drifter's Cloak: glide), hasDoubleJump (Faydown Cloak), hasHarpoonDash (Clawline), hasSuperJump (Silk Soar).
    /// HeroController reads these fields directly (CanDash, CanWallSlide, CanFloat, CanDoubleJump, HasHarpoonDash,
    /// CanSuperJump); PlayerData.GetAllPowerups and DebugMod's GiveAllSkills set them the same way. The crest's
    /// HeroControllerConfig can still forbid some (CanHarpoonDash, CanDoubleJump, CanBrolly: "config" in the reply).</item>
    /// <item>combat: hasChargeSlash (Needle Strike), the six silk skills, and tools (default Straight Pin). A silk
    /// skill is a ToolItem of type Skill ("Silk Spear" = Silkspear, "Thread Sphere" = Thread Storm, "Parry" = Cross
    /// Stitch, "Silk Charge" = Sharpdart, "Silk Bomb" = Rune Rage, "Silk Boss Needle" = Pale Nails) in a Skill slot of
    /// the current crest. QuickCast uses whatever attack tool (Red or Skill) the crest binds to the held direction
    /// (HeroController.GetWillThrowTool: Up, else Down, else Neutral; a missing Up/Down tool falls back to Neutral);
    /// a skill needs PlayerData.SilkSkillCost silk (4, 3 with the Flea charm at full health) of the spool's 9, which
    /// is left as it is. Each granted skill also gets its flag (hasNeedleThrow, hasThreadSphere, hasParry,
    /// hasSilkCharge, hasSilkBomb, hasSilkBossNeedle), as the game's own pickups leave both. Only "skill" (default
    /// Silk Spear) is equipped.</item>
    /// <item>all: movement + combat + hasNeedolin.</item>
    /// </list>
    /// Tools are unlocked with the data ToolItem.Unlock writes (SavedData: unlocked, not hidden, AmountLeft = the
    /// storage amount) but without Unlock's side effects: popup, tutorial message, Tools-pane "new" marks and
    /// ToolItemManager.ReportToolUnlocked, which awards FIRST_TOOL / FIRST_SILK_SKILL (AchievementGuard would block it,
    /// but a grant must not depend on that). Equipping goes through ToolItemManager.SetEquippedTools, then
    /// ReportAllBoundAttackToolsUpdated and SendEquippedChangedEvent(force), as the inventory and TryReplenishTools do.
    /// ToolItemManager.AutoEquip is not used: it ignores locked slots. Each tool (the skill first) goes into a slot of its
    /// type, preferring in this order: a binding reachable without Up (attack tools), a binding no other attack tool
    /// uses (only the first in slot order is ever thrown), an unlocked slot, Neutral over Down, a free slot over
    /// replacing a tool that was not asked for. Locked slots are only used with unlock_slots, which unlocks them the way
    /// spending a Memory Locket does (SlotData.IsUnlocked; no locket taken).
    ///
    /// Refused unless the profile allows probe tools, the guards are not refused, saves go to the sandbox
    /// (SaveRedirect.Redirected) and a Steel Soul session has its snapshot; also refused over a dead hero, during a
    /// load, a harness operation or a transition. Names are checked before anything changes. permadeathMode is never
    /// written. The grant lives in PlayerData only: it reaches disk only through a save (redirected into the sandbox;
    /// guards.set save_suppression keeps it off disk entirely) and survives episode resets once a savestate captured
    /// it. Replies with the list of changes plus the abilities.list answer. Main thread (RPC handlers).
    /// </summary>
    internal static class AbilityGrant
    {
        public const string DefaultSkill = "Silk Spear";
        private static readonly string[] DefaultTools = { "Straight Pin" };
        private static readonly string[] NoTools = new string[0];

        private sealed class Flag
        {
            public readonly string Set, Field, Ability;
            public readonly Func<PlayerData, bool> Get;
            public readonly Action<PlayerData, bool> Put;

            public Flag(string set, string field, string ability, Func<PlayerData, bool> get, Action<PlayerData, bool> put)
            {
                Set = set;
                Field = field;
                Ability = ability;
                Get = get;
                Put = put;
            }
        }

        /// <summary>PlayerData ability fields (PlayerData.cs:230-269) and the set that grants each.</summary>
        private static readonly Flag[] Flags =
        {
            new Flag("movement", "hasDash", "Swift Step", pd => pd.hasDash, (pd, v) => pd.hasDash = v),
            new Flag("movement", "hasWalljump", "Cling Grip", pd => pd.hasWalljump, (pd, v) => pd.hasWalljump = v),
            new Flag("movement", "hasBrolly", "Drifter's Cloak", pd => pd.hasBrolly, (pd, v) => pd.hasBrolly = v),
            new Flag("movement", "hasDoubleJump", "Faydown Cloak", pd => pd.hasDoubleJump, (pd, v) => pd.hasDoubleJump = v),
            new Flag("movement", "hasHarpoonDash", "Clawline", pd => pd.hasHarpoonDash, (pd, v) => pd.hasHarpoonDash = v),
            new Flag("movement", "hasSuperJump", "Silk Soar", pd => pd.hasSuperJump, (pd, v) => pd.hasSuperJump = v),
            new Flag("combat", "hasChargeSlash", "Needle Strike", pd => pd.hasChargeSlash, (pd, v) => pd.hasChargeSlash = v),
            new Flag("all", "hasNeedolin", "Needolin", pd => pd.hasNeedolin, (pd, v) => pd.hasNeedolin = v),
        };

        private sealed class Skill
        {
            public readonly string Tool, Name;
            public readonly Flag Flag;

            public Skill(string tool, string name, Flag flag)
            {
                Tool = tool;
                Name = name;
                Flag = flag;
            }
        }

        /// <summary>Silk skills: ToolItem name, in-game name, PlayerData flag (m0 §2.7; DebugMod MainPanel tool table).</summary>
        private static readonly Skill[] Skills =
        {
            new Skill("Silk Spear", "Silkspear", new Flag("combat", "hasNeedleThrow", "Silkspear", pd => pd.hasNeedleThrow, (pd, v) => pd.hasNeedleThrow = v)),
            new Skill("Thread Sphere", "Thread Storm", new Flag("combat", "hasThreadSphere", "Thread Storm", pd => pd.hasThreadSphere, (pd, v) => pd.hasThreadSphere = v)),
            new Skill("Parry", "Cross Stitch", new Flag("combat", "hasParry", "Cross Stitch", pd => pd.hasParry, (pd, v) => pd.hasParry = v)),
            new Skill("Silk Charge", "Sharpdart", new Flag("combat", "hasSilkCharge", "Sharpdart", pd => pd.hasSilkCharge, (pd, v) => pd.hasSilkCharge = v)),
            new Skill("Silk Bomb", "Rune Rage", new Flag("combat", "hasSilkBomb", "Rune Rage", pd => pd.hasSilkBomb, (pd, v) => pd.hasSilkBomb = v)),
            new Skill("Silk Boss Needle", "Pale Nails", new Flag("combat", "hasSilkBossNeedle", "Pale Nails", pd => pd.hasSilkBossNeedle, (pd, v) => pd.hasSilkBossNeedle = v)),
        };

        public static void Register()
        {
            Rpc.Register("abilities.grant", Grant);
            Rpc.Register("abilities.list", args =>
            {
                var (_, hero, pd) = Game(steady: false);
                return Describe(pd, hero, Rpc.Bool(args, "all_tools"));
            });
        }

        private static bool Includes(string set, string flagSet) => set == "all" || flagSet == set;

        // ---- grant -----------------------------------------------------------------------------------------------

        private static object Grant(Dictionary<string, object> args)
        {
            if (!Core.Profile.Rules.ProbeTools) throw new InvalidOperationException($"probe tools are disabled in profile {Core.Profile.Current}");
            if (Guards.GuardState.Refused) throw new InvalidOperationException("guards are refused: " + string.Join("; ", Guards.GuardState.Refusals.ToArray()));
            if (!Guards.SaveRedirect.Redirected)
                throw new InvalidOperationException("saves are not redirected into the sandbox (SaveRedirect did not run): a grant could reach a real save");
            var set = Rpc.Str(args, "set");
            if (set != "movement" && set != "combat" && set != "all") throw new ArgumentException("set must be movement, combat or all");
            var combat = set != "movement";
            if (!combat && args.ContainsKey("skill")) throw new ArgumentException("skill needs set combat or all");
            var (gm, hero, pd) = Game(steady: true);
            if (Guards.SteelSoulSnapshot.Unprotected(out var slot))
                throw new InvalidOperationException($"the Steel Soul session in slot {slot} has no snapshot (slot.snapshot first)");

            // Everything is resolved and checked before the first write.
            var tools = new List<ToolItem>();
            foreach (var n in Names(args, "tools", combat ? DefaultTools : NoTools))
            {
                var t = ToolItemManager.GetToolByName(n);
                if (t == null) throw new ArgumentException($"unknown tool '{n}' (abilities.list {{all_tools: true}} lists them)");
                if (t.Type == ToolItemType.Skill) throw new ArgumentException($"'{n}' is a silk skill: pass it as skill");
                if (!tools.Contains(t)) tools.Add(t);
            }
            var skillTools = new List<ToolItem>();
            ToolItem equipSkill = null;
            if (combat)
            {
                var wanted = Rpc.Str(args, "skill", DefaultSkill);
                var chosen = Array.Find(Skills, s => Same(s.Tool, wanted) || Same(s.Name, wanted));
                if (chosen == null)
                    throw new ArgumentException($"skill must be one of {string.Join(", ", Array.ConvertAll(Skills, s => $"{s.Tool} ({s.Name})"))}");
                foreach (var s in Skills)
                {
                    var t = ToolItemManager.GetToolByName(s.Tool);
                    if (t == null || t.Type != ToolItemType.Skill) throw new InvalidOperationException($"no Skill tool '{s.Tool}' in this build");
                    skillTools.Add(t);
                    if (s == chosen) equipSkill = t;
                }
            }
            ToolCrest crest = null;
            if (equipSkill != null || tools.Count > 0)
            {
                crest = ToolItemManager.GetCrestByName(pd.CurrentCrestID);
                if (crest == null || crest.Slots == null) throw new InvalidOperationException($"current crest '{pd.CurrentCrestID}' not found");
            }

            var changed = new List<string>();
            var unplaced = new List<string>();
            foreach (var f in Flags)
                if (Includes(set, f.Set)) SetFlag(pd, f, changed);
            var toolsChanged = false;
            for (var i = 0; i < skillTools.Count; i++)
            {
                SetFlag(pd, Skills[i].Flag, changed);
                toolsChanged |= Unlock(skillTools[i], changed);
            }
            foreach (var t in tools) toolsChanged |= Unlock(t, changed);
            var equipped = new List<ToolItem>();
            if (equipSkill != null) equipped.Add(equipSkill);
            equipped.AddRange(tools);
            var equipsChanged = crest != null && Equip(pd, crest, equipped, Rpc.Bool(args, "unlock_slots"), changed, unplaced);
            if (toolsChanged || equipsChanged)
            {
                ToolItemManager.ReportAllBoundAttackToolsUpdated();
                ToolItemManager.SendEquippedChangedEvent(force: true);
            }

            if (changed.Count > 0)
                Core.Plugin.Log.LogWarning($"abilities.grant {set} (training edit, scene {gm.sceneName}): {string.Join("; ", changed.ToArray())}");
            Export.FrameExporter.Emit("harness", new Dictionary<string, object> { ["op"] = "abilities.grant", ["set"] = set, ["changes"] = changed.Count });
            var reply = Describe(pd, hero, false);
            reply["set"] = set;
            reply["changed"] = changed;
            reply["unplaced"] = unplaced;
            reply["requested"] = equipped.ConvertAll(t => t.name);
            return reply;
        }

        /// <summary>GameManager, hero and PlayerData, all present and the tool API usable without a scene search
        /// (SafeReads). steady: also no load, harness operation or transition in progress and a living hero.</summary>
        private static (GameManager, HeroController, PlayerData) Game(bool steady)
        {
            var gm = GameManager._instance;
            var hero = HeroController.UnsafeInstance;
            var pd = gm != null ? gm.playerData : null;
            if (gm == null || hero == null || pd == null) throw new InvalidOperationException("no game loaded (no GameManager, hero or PlayerData)");
            if (!Hero.SafeReads.ToolsReadable(hero) || !ReferenceEquals(pd, PlayerData.instance))
                throw new InvalidOperationException("the tool system is not ready (no ToolItemManager, or PlayerData.instance is not the game's PlayerData)");
            if (!steady) return (gm, hero, pd);
            if (HarnessRunner.Busy != null) throw new InvalidOperationException($"harness busy ({HarnessRunner.Busy})");
            if (DebugModBridge.LoadInProgress) throw new InvalidOperationException("a DebugMod savestate load is in progress");
            if (gm.GameState != GameState.PLAYING || gm.IsInSceneTransition || hero.cState.transitioning)
                throw new InvalidOperationException($"not in a steady gameplay state (GameState {gm.GameState})");
            if (hero.cState.dead || pd.permadeathMode == PermadeathModes.Dead || pd.health <= 0)
                throw new InvalidOperationException("the hero is dead");
            return (gm, hero, pd);
        }

        private static void SetFlag(PlayerData pd, Flag f, List<string> changed)
        {
            if (f.Get(pd)) return;
            f.Put(pd, true);
            changed.Add($"{f.Field} ({f.Ability})");
        }

        /// <summary>ToolItem.Unlock's data write (ToolItem.cs:497-565) without its popups, marks and achievement report.
        /// Returns whether anything changed.</summary>
        private static bool Unlock(ToolItem tool, List<string> changed)
        {
            var d = tool.SavedData;
            var storage = ToolItemManager.GetToolStorageAmount(tool);
            if (d.IsUnlocked && !d.IsHidden && d.AmountLeft >= storage) return false;
            var was = d.IsUnlocked && !d.IsHidden ? $"{d.AmountLeft} left" : "locked";
            d.IsUnlocked = true;
            d.IsHidden = false;
            if (d.AmountLeft < storage) d.AmountLeft = storage;
            tool.SavedData = d;
            changed.Add($"tool {tool.name} ({tool.Type}): {was} -> unlocked, {d.AmountLeft} left");
            return true;
        }

        /// <summary>Put each tool (in order) into a slot of the crest (see the class summary for the choice); one
        /// SetEquippedTools call for the crest. Returns whether any slot changed.</summary>
        private static bool Equip(PlayerData pd, ToolCrest crest, List<ToolItem> want, bool unlockSlots, List<string> changed, List<string> unplaced)
        {
            var infos = crest.Slots;
            var saved = pd.ToolEquips.GetData(crest.name).Slots;
            var names = new List<string>(infos.Length);
            for (var i = 0; i < infos.Length; i++) names.Add(saved != null && i < saved.Count ? saved[i].EquippedTool ?? "" : "");
            var keep = new HashSet<string>();
            foreach (var t in want) keep.Add(t.name);
            var usable = new bool[infos.Length];
            for (var i = 0; i < infos.Length; i++) usable[i] = SlotUnlocked(infos, saved, i);
            var unlock = new List<int>();
            var edited = false;
            foreach (var tool in want)
            {
                if (names.Contains(tool.name)) continue;
                var best = ChooseSlot(tool.Type, infos, names, usable, keep, unlockSlots, IsAttackTool);
                if (best < 0)
                {
                    unplaced.Add($"{tool.name}: no {(unlockSlots ? "" : "unlocked ")}{tool.Type} slot on {crest.name} that is free or holds a tool not asked for");
                    continue;
                }
                if (!usable[best])
                {
                    unlock.Add(best);
                    usable[best] = true;
                }
                changed.Add($"{crest.name} slot {best} ({SlotName(infos[best])}): '{names[best]}' -> '{tool.name}'");
                names[best] = tool.name;
                edited = true;
            }
            if (!edited) return false;
            ToolItemManager.SetEquippedTools(crest.name, names);
            if (unlock.Count > 0)
            {
                var data = pd.ToolEquips.GetData(crest.name);  // SetEquippedTools made Slots at least infos.Length long
                foreach (var i in unlock)
                {
                    var s = data.Slots[i];
                    s.IsUnlocked = true;
                    data.Slots[i] = s;
                    changed.Add($"{crest.name} slot {i} ({SlotName(infos[i])}) unlocked (as a Memory Locket would; none taken)");
                }
                pd.ToolEquips.SetData(crest.name, data);
            }
            return true;
        }

        /// <summary>The inventory's rule (InventoryToolCrestSlot.IsLocked, CountCrestUnlockPoints): a slot is usable
        /// unless its asset marks it locked and its saved data does not say it was unlocked. The game itself (the
        /// bound-tool lookup) never checks this.</summary>
        private static bool SlotUnlocked(ToolCrest.SlotInfo[] infos, List<ToolCrestsData.SlotData> saved, int i) =>
            !infos[i].IsLocked || (saved != null && i < saved.Count && saved[i].IsUnlocked);

        /// <summary>
        /// The slot for a tool of <paramref name="type"/>, or -1 (pure: replayed offline by tools/symcheck). Candidates:
        /// slots of that type that are usable (unlocked, or any with <paramref name="unlockSlots"/>) and free or holding
        /// a tool not in <paramref name="keep"/>. Lowest key wins, then the lowest index: +1000 bound to Up (the soak
        /// never presses it), +500 another slot with the same binding already holds an attack tool (only the first in
        /// slot order is ever thrown: ToolItemManager.GetToolForBinding), +100 locked, +10 Down (Neutral first), +1
        /// occupied. Bindings only count for attack types (Red, Skill).
        /// </summary>
        internal static int ChooseSlot(ToolItemType type, ToolCrest.SlotInfo[] infos, List<string> names, bool[] usable,
            ICollection<string> keep, bool unlockSlots, Func<string, bool> isAttackTool)
        {
            int best = -1, bestKey = int.MaxValue;
            for (var i = 0; i < infos.Length; i++)
            {
                if (infos[i].Type != type || (!usable[i] && !unlockSlots)) continue;
                var occupied = !string.IsNullOrEmpty(names[i]);
                if (occupied && keep.Contains(names[i])) continue;
                var key = (usable[i] ? 0 : 100) + (occupied ? 1 : 0);
                if (type.IsAttackType())
                {
                    var b = infos[i].AttackBinding;
                    if (b == AttackToolBinding.Up) key += 1000;
                    if (BindingTaken(infos, names, i, b, isAttackTool)) key += 500;
                    if (b != AttackToolBinding.Neutral) key += 10;
                }
                if (key < bestKey)
                {
                    best = i;
                    bestKey = key;
                }
            }
            return best;
        }

        private static bool BindingTaken(ToolCrest.SlotInfo[] infos, List<string> names, int slot, AttackToolBinding b, Func<string, bool> isAttackTool)
        {
            for (var j = 0; j < infos.Length; j++)
            {
                if (j == slot || string.IsNullOrEmpty(names[j]) || !infos[j].Type.IsAttackType() || infos[j].AttackBinding != b) continue;
                if (isAttackTool(names[j])) return true;
            }
            return false;
        }

        private static bool IsAttackTool(string name)
        {
            var t = ToolItemManager.GetToolByName(name);
            return t != null && t.Type.IsAttackType();
        }

        private static string SlotName(ToolCrest.SlotInfo info) =>
            info.Type.IsAttackType() ? $"{info.Type} {info.AttackBinding}" : info.Type.ToString();

        // ---- list ------------------------------------------------------------------------------------------------

        private static Dictionary<string, object> Describe(PlayerData pd, HeroController hero, bool allTools)
        {
            var flags = new Dictionary<string, object>();
            var movement = true;
            var combat = pd.hasChargeSlash;
            foreach (var f in Flags)
            {
                flags[f.Field] = f.Get(pd);
                if (f.Set == "movement") movement &= f.Get(pd);
            }
            var skills = new List<object>();
            foreach (var s in Skills)
            {
                var t = ToolItemManager.GetToolByName(s.Tool);
                var unlocked = t != null && t.IsUnlockedNotHidden;
                flags[s.Flag.Field] = s.Flag.Get(pd);
                combat &= unlocked && s.Flag.Get(pd);
                skills.Add(new Dictionary<string, object>
                {
                    ["tool"] = s.Tool,
                    ["name"] = s.Name,
                    ["flag"] = s.Flag.Field,
                    ["flag_value"] = s.Flag.Get(pd),
                    ["unlocked"] = unlocked,
                    ["equipped"] = ToolItemManager.IsToolEquipped(s.Tool),
                });
            }

            var tools = new List<object>();
            foreach (var t in ToolItemManager.GetAllTools())
            {
                if (t == null || t.Type == ToolItemType.Skill || !(allTools || t.IsUnlockedNotHidden)) continue;
                tools.Add(new Dictionary<string, object>
                {
                    ["name"] = t.name,
                    ["type"] = t.Type.ToString(),
                    ["unlocked"] = t.IsUnlockedNotHidden,
                    ["amount"] = t.SavedData.AmountLeft,
                    ["storage"] = ToolItemManager.GetToolStorageAmount(t),
                    ["equipped"] = ToolItemManager.IsToolEquipped(t.name),
                });
            }

            var slots = new List<object>();
            var crest = ToolItemManager.GetCrestByName(pd.CurrentCrestID);
            if (crest != null && crest.Slots != null)
            {
                var saved = pd.ToolEquips.GetData(crest.name).Slots;
                for (var i = 0; i < crest.Slots.Length; i++)
                {
                    var info = crest.Slots[i];
                    var name = saved != null && i < saved.Count ? saved[i].EquippedTool : null;
                    slots.Add(new Dictionary<string, object>
                    {
                        ["index"] = i,
                        ["type"] = info.Type.ToString(),
                        ["binding"] = info.Type.IsAttackType() ? info.AttackBinding.ToString() : null,
                        ["locked"] = !SlotUnlocked(crest.Slots, saved, i),
                        ["tool"] = string.IsNullOrEmpty(name) ? null : name,
                    });
                }
            }

            var cfg = hero.Config;
            Hero.SafeReads.TrySilkMax(pd, hero, out var silkMax);
            return new Dictionary<string, object>
            {
                ["sets"] = new Dictionary<string, object>
                {
                    ["movement"] = movement,
                    ["combat"] = combat,
                    ["all"] = movement && combat && pd.hasNeedolin,
                },
                ["flags"] = flags,
                ["skills"] = skills,
                ["tools"] = tools,
                ["crest"] = pd.CurrentCrestID,
                ["slots"] = slots,
                // What QuickCast throws per held direction now (the HUD's read: no Up/Down -> Neutral fallback, which
                // the throw itself applies).
                ["bindings"] = new Dictionary<string, object>
                {
                    ["neutral"] = Bound(AttackToolBinding.Neutral),
                    ["up"] = Bound(AttackToolBinding.Up),
                    ["down"] = Bound(AttackToolBinding.Down),
                },
                ["tools_active_state"] = ToolItemManager.ActiveState.ToString(),
                ["config"] = cfg == null ? null : new Dictionary<string, object>
                {
                    ["can_harpoon_dash"] = cfg.CanHarpoonDash,
                    ["can_double_jump"] = cfg.CanDoubleJump,
                    ["can_brolly"] = cfg.CanBrolly,
                    ["can_nail_charge"] = cfg.CanNailCharge,
                    ["can_play_needolin"] = cfg.CanPlayNeedolin,
                },
                ["silk"] = pd.silk,
                ["silk_max"] = silkMax,
                ["silk_skill_cost"] = pd.SilkSkillCost,
                ["save_redirected"] = Guards.SaveRedirect.Redirected,
                ["save_suppression"] = Guards.GuardState.SaveSuppression,
            };
        }

        private static string Bound(AttackToolBinding b)
        {
            var t = ToolItemManager.GetBoundAttackTool(b, ToolEquippedReadSource.Hud);
            return t != null ? t.name : null;
        }

        // ---- args ------------------------------------------------------------------------------------------------

        /// <summary>A list of names, one name, or absent (then <paramref name="def"/>).</summary>
        private static List<string> Names(Dictionary<string, object> args, string key, string[] def)
        {
            if (!args.TryGetValue(key, out var v) || v == null) return new List<string>(def);
            if (v is string one) return new List<string> { one };
            if (v is List<object> list) return list.ConvertAll(x => Convert.ToString(x));
            throw new ArgumentException($"{key} must be a list of names");
        }

        private static bool Same(string a, string b) => string.Equals(a, b, StringComparison.OrdinalIgnoreCase);
    }
}
