using System.Collections.Generic;
using GlobalSettings;
using HarmonyLib;
using UnityEngine;

namespace SsOracle.Crest
{
    /// <summary>
    /// RPC "crest.dump" (read-only; crests.md §5 a, i). Reply:
    /// <code>
    /// {frame,
    ///  current: {crest, previous, temp, cursed, silk, config, group, override_group, crest_config, rage, reaper,
    ///            hunter_meter, values} | {crest, previous, temp, cursed, silk} without a hero,
    ///  crests:  [{name, hidden, base, previous_version, upgraded_version, unlocked, equipped, has_custom_action,
    ///             config, config_group: {index, special, rule} | null (no hero),
    ///             slots: [{i, type, binding, locked, pos, saved: {tool, unlocked} | null}],
    ///             saved: {present, unlocked, new, slots}}],
    ///  groups:  [{index, kind: "configs" | "special", config, active_root, root_active, objects: {normal, alt, up, alt_up,
    ///             down, alt_down, wall, dash_stab, dash_stab_alt, charge, taunt}}]      (empty without a hero),
    ///  configs: {config name: {name, type, fields: {serialized field: value}, values: {...} | null}},
    ///  extra_equips: {slot id: tool},
    ///  tool_amounts: {tool: AmountLeft}}     (every tool, PlayerData.GetToolData: what a crest switch's UpdateToolCap caps)
    /// </code>
    /// How the hero picks a config (HeroController.UpdateConfig, 1.0.30000 :1801): crestConfig = the equipped crest's
    /// HeroConfig (ResetAllCrestState); a null crestConfig means configs[0]; otherwise the first group in "configs" whose
    /// Config is that asset (none: "configGroup was null!" and the old group stays); an override group is the first
    /// "special" group with the same Config, used for the Warrior crest only in rage. config_group.rule says which case a
    /// crest falls under, so "how Hunter maps to a config" is answered by the dump rather than assumed.
    /// "values" are the config's public getters (HeroControllerConfigWarrior's switch to the rage values in rage);
    /// "fields" are the serialized fields, which hold both. Crest state is read from PlayerData.ToolEquips directly:
    /// ToolCrest.IsUnlocked/IsVisible go through PlayerData.instance.
    /// </summary>
    internal static class CrestDump
    {
        private static readonly AccessTools.FieldRef<ToolCrest, ToolCrest> PreviousVersion = Hero.Refs.Field<ToolCrest, ToolCrest>("previousVersion");
        private static readonly AccessTools.FieldRef<ToolCrest, ToolCrest> UpgradedVersion = Hero.Refs.Field<ToolCrest, ToolCrest>("upgradedVersion");
        public static readonly AccessTools.FieldRef<HeroController, HeroController.ConfigGroup[]> Configs =
            Hero.Refs.Field<HeroController, HeroController.ConfigGroup[]>("configs");
        public static readonly AccessTools.FieldRef<HeroController, HeroController.ConfigGroup[]> SpecialConfigs =
            Hero.Refs.Field<HeroController, HeroController.ConfigGroup[]>("specialConfigs");
        private static readonly AccessTools.FieldRef<HeroController, HeroControllerConfig> CrestConfigRef =
            Hero.Refs.Field<HeroController, HeroControllerConfig>("crestConfig");
        private static readonly AccessTools.FieldRef<SerializableNamedList<ToolCrestsData.SlotData, FloatingCrestSlotsData.NamedData>, Dictionary<string, ToolCrestsData.SlotData>> ExtraSlots =
            Hero.Refs.Field<SerializableNamedList<ToolCrestsData.SlotData, FloatingCrestSlotsData.NamedData>, Dictionary<string, ToolCrestsData.SlotData>>("RuntimeData");

        /// <summary>HeroController.configs (the groups UpdateConfig matches against), or null when unresolved.</summary>
        public static HeroController.ConfigGroup[] GroupsOf(HeroController hero) => Configs != null ? Configs(hero) : null;

        /// <summary>HeroController.specialConfigs (override groups), or null.</summary>
        public static HeroController.ConfigGroup[] SpecialGroupsOf(HeroController hero) => SpecialConfigs != null ? SpecialConfigs(hero) : null;

        /// <summary>Index of the hero's CurrentConfigGroup in HeroController.configs, or null.</summary>
        public static int? CurrentGroupIndex(HeroController hero) => IndexOf(GroupsOf(hero), hero.CurrentConfigGroup);

        private static HeroControllerConfig CrestConfig(HeroController hero) => CrestConfigRef != null ? CrestConfigRef(hero) : null;

        public static object Dump(Dictionary<string, object> args)
        {
            var pd = CrestModule.RequirePd();
            var hero = HeroController.UnsafeInstance;
            var configs = new Dictionary<string, object>();
            var crests = new List<object>();
            foreach (var crest in ToolItemManager.GetAllCrests())
                crests.Add(Crest(crest, pd, hero, configs));
            var groups = new List<object>();
            if (hero != null)
            {
                AddGroups(groups, GroupsOf(hero), "configs", configs, hero);
                AddGroups(groups, SpecialGroupsOf(hero), "special", configs, hero);
            }
            return new Dictionary<string, object>
            {
                ["frame"] = Time.frameCount,
                ["current"] = Current(pd, hero, configs),
                ["crests"] = crests,
                ["groups"] = groups,
                ["configs"] = configs,
                ["extra_equips"] = ExtraEquips(pd),
                ["tool_amounts"] = ToolAmounts(pd),
            };
        }

        private static Dictionary<string, object> Current(PlayerData pd, HeroController hero, Dictionary<string, object> configs)
        {
            var d = new Dictionary<string, object>
            {
                ["crest"] = pd.CurrentCrestID,
                ["previous"] = pd.PreviousCrestID,
                ["temp"] = pd.IsCurrentCrestTemp,
                ["cursed"] = ToolItemManager.IsCursed,
                ["silk"] = pd.silk,
            };
            if (hero == null) return d;
            var cfg = hero.Config;
            if (cfg != null) AddConfig(configs, cfg, hero);
            d["config"] = CrestModule.Name(cfg);
            d["group"] = CurrentGroupIndex(hero);
            d["override_group"] = OverrideIndex(hero, CrestConfig(hero));
            d["crest_config"] = CrestModule.Name(CrestConfig(hero));
            d["rage"] = hero.WarriorState.IsInRageMode;
            d["reaper"] = hero.ReaperState.IsInReaperMode;
            d["hunter_meter"] = hero.HunterUpgState.CurrentMeterHits;
            d["values"] = cfg != null ? Values(cfg) : null;
            return d;
        }

        private static Dictionary<string, object> Crest(ToolCrest crest, PlayerData pd, HeroController hero, Dictionary<string, object> configs)
        {
            var saved = CrestModule.SavedCrest(pd, crest.name, out var present);
            var cfg = crest.HeroConfig;
            if (cfg != null) AddConfig(configs, cfg, hero);
            var prev = PreviousVersion != null ? PreviousVersion(crest) : null;
            var slots = new List<object>();
            var infos = crest.Slots ?? new ToolCrest.SlotInfo[0];
            for (var i = 0; i < infos.Length; i++)
            {
                var s = infos[i];
                object savedSlot = null;
                if (saved.Slots != null && i < saved.Slots.Count)
                {
                    var sd = saved.Slots[i];
                    savedSlot = new Dictionary<string, object>
                    {
                        ["tool"] = string.IsNullOrEmpty(sd.EquippedTool) ? null : sd.EquippedTool,
                        ["unlocked"] = sd.IsUnlocked,
                    };
                }
                slots.Add(new Dictionary<string, object>
                {
                    ["i"] = i,
                    ["type"] = s.Type.ToString(),
                    ["binding"] = s.Type.IsAttackType() ? s.AttackBinding.ToString() : null,
                    ["locked"] = s.IsLocked,
                    ["pos"] = s.Position,
                    ["saved"] = savedSlot,
                });
            }
            return new Dictionary<string, object>
            {
                ["name"] = crest.name,
                ["hidden"] = crest.IsHidden,
                ["base"] = prev == null,
                ["previous_version"] = CrestModule.Name(prev),
                ["upgraded_version"] = UpgradedVersion != null ? CrestModule.Name(UpgradedVersion(crest)) : null,
                ["unlocked"] = saved.IsUnlocked,
                ["equipped"] = pd.CurrentCrestID == crest.name,
                ["has_custom_action"] = crest.HasCustomAction,
                ["config"] = CrestModule.Name(cfg),
                ["config_group"] = hero != null ? GroupFor(hero, cfg) : null,
                ["slots"] = slots,
                ["saved"] = new Dictionary<string, object>
                {
                    ["present"] = present,
                    ["unlocked"] = saved.IsUnlocked,
                    ["new"] = saved.DisplayNewIndicator,
                    ["slots"] = saved.Slots != null ? (object)saved.Slots.Count : null,
                },
            };
        }

        /// <summary>The group UpdateConfig would pick for a crest whose HeroConfig is <paramref name="cfg"/>.</summary>
        private static Dictionary<string, object> GroupFor(HeroController hero, HeroControllerConfig cfg)
        {
            var groups = GroupsOf(hero);
            int? index = null;
            string rule;
            if (cfg == null)
            {
                index = groups != null && groups.Length > 0 ? 0 : (int?)null;
                rule = "no_config:configs[0]";
            }
            else
            {
                if (groups != null)
                    for (var i = 0; i < groups.Length; i++)
                        if (groups[i] != null && groups[i].Config == cfg) { index = i; break; }
                rule = index.HasValue ? "match" : "no_group";
            }
            return new Dictionary<string, object>
            {
                ["index"] = index,
                ["special"] = SpecialIndex(hero, cfg),
                ["rule"] = rule,
            };
        }

        /// <summary>First "special" group with this Config (the override candidate), ignoring the rage condition.</summary>
        private static int? SpecialIndex(HeroController hero, HeroControllerConfig cfg)
        {
            var special = SpecialGroupsOf(hero);
            if (cfg == null || special == null) return null;
            for (var i = 0; i < special.Length; i++)
                if (special[i] != null && special[i].Config == cfg) return i;
            return null;
        }

        /// <summary>The override group UpdateConfig applies now (Warrior's only in rage).</summary>
        private static int? OverrideIndex(HeroController hero, HeroControllerConfig crestConfig)
        {
            if (crestConfig == null) return null;
            var i = SpecialIndex(hero, crestConfig);
            if (!i.HasValue) return null;
            var warrior = Gameplay.WarriorCrest;
            if (warrior != null && crestConfig == warrior.HeroConfig && !hero.WarriorState.IsInRageMode) return null;
            return i;
        }

        private static int? IndexOf(HeroController.ConfigGroup[] groups, HeroController.ConfigGroup g)
        {
            if (groups == null || g == null) return null;
            for (var i = 0; i < groups.Length; i++)
                if (ReferenceEquals(groups[i], g)) return i;
            return null;
        }

        private static void AddGroups(List<object> into, HeroController.ConfigGroup[] groups, string kind, Dictionary<string, object> configs, HeroController hero)
        {
            if (groups == null) return;
            for (var i = 0; i < groups.Length; i++)
            {
                var g = groups[i];
                if (g == null) continue;
                if (g.Config != null) AddConfig(configs, g.Config, hero);
                into.Add(new Dictionary<string, object>
                {
                    ["index"] = i,
                    ["kind"] = kind,
                    ["config"] = CrestModule.Name(g.Config),
                    ["active_root"] = CrestModule.Name(g.ActiveRoot),
                    ["root_active"] = g.ActiveRoot != null ? (object)g.ActiveRoot.activeSelf : null,
                    ["objects"] = GroupObjects(g),
                });
            }
        }

        /// <summary>The group's attack GameObjects by slot (slash.dump uses the same slot names).</summary>
        public static Dictionary<string, object> GroupObjects(HeroController.ConfigGroup g) => new Dictionary<string, object>
        {
            ["normal"] = CrestModule.Name(g.NormalSlashObject),
            ["alt"] = CrestModule.Name(g.AlternateSlashObject),
            ["up"] = CrestModule.Name(g.UpSlashObject),
            ["alt_up"] = CrestModule.Name(g.AltUpSlashObject),
            ["down"] = CrestModule.Name(g.DownSlashObject),
            ["alt_down"] = CrestModule.Name(g.AltDownSlashObject),
            ["wall"] = CrestModule.Name(g.WallSlashObject),
            ["dash_stab"] = CrestModule.Name(g.DashStab),
            ["dash_stab_alt"] = CrestModule.Name(g.DashStabAlt),
            ["charge"] = CrestModule.Name(g.ChargeSlash),
            ["taunt"] = CrestModule.Name(g.TauntSlash),
        };

        private static void AddConfig(Dictionary<string, object> configs, HeroControllerConfig cfg, HeroController hero)
        {
            var name = cfg.name;
            if (configs.ContainsKey(name)) return;
            configs[name] = new Dictionary<string, object>
            {
                ["name"] = name,
                ["type"] = cfg.GetType().Name,
                ["fields"] = PlainValues.Fields(cfg),
                // HeroControllerConfigWarrior's getters read HeroController.instance, which searches the scene without a hero.
                ["values"] = hero != null ? Values(cfg) : null,
            };
        }

        /// <summary>Every public getter of HeroControllerConfig (the virtual timing ones as the hero sees them now).</summary>
        public static Dictionary<string, object> Values(HeroControllerConfig c) => new Dictionary<string, object>
        {
            ["attack_duration"] = CrestModule.Try(() => c.AttackDuration),
            ["attack_cooldown"] = CrestModule.Try(() => c.AttackCooldownTime),
            ["attack_recovery"] = CrestModule.Try(() => c.AttackRecoveryTime),
            ["quick_attack_speed_mult"] = CrestModule.Try(() => c.QuickAttackSpeedMult),
            ["quick_attack_cooldown"] = CrestModule.Try(() => c.QuickAttackCooldownTime),
            ["can_turn_while_slashing"] = c.CanTurnWhileSlashing,
            ["down_slash_type"] = c.DownSlashType.ToString(),
            ["down_slash_event"] = c.DownSlashEvent,
            ["downspike_antic"] = c.DownSpikeAnticTime,
            ["downspike_time"] = c.DownSpikeTime,
            ["downspike_speed"] = c.DownspikeSpeed,
            ["downspike_recovery"] = c.DownspikeRecoveryTime,
            ["downspike_burst"] = c.DownspikeBurstEffect,
            ["downspike_thrusts"] = c.DownspikeThrusts,
            ["dash_stab_speed"] = c.DashStabSpeed,
            ["dash_stab_time"] = c.DashStabTime,
            ["dash_stab_steps"] = c.DashStabSteps,
            ["dash_stab_bounce_jump_speed"] = c.DashStabBounceJumpSpeed,
            ["force_short_dash_stab_bounce"] = c.ForceShortDashStabBounce,
            ["charge_slash_recoils"] = c.ChargeSlashRecoils,
            ["charge_slash_lunge_speed"] = c.ChargeSlashLungeSpeed,
            ["charge_slash_lunge_deceleration"] = c.ChargeSlashLungeDeceleration,
            ["charge_slash_chain"] = c.ChargeSlashChain,
            ["wall_slash_slowdown"] = c.WallSlashSlowdown,
            ["can_play_needolin"] = c.CanPlayNeedolin,
            ["can_brolly"] = c.CanBrolly,
            ["can_double_jump"] = c.CanDoubleJump,
            ["can_nail_charge"] = c.CanNailCharge,
            ["can_bind"] = c.CanBind,
            ["can_harpoon_dash"] = c.CanHarpoonDash,
            ["force_bare_inventory"] = c.ForceBareInventory,
        };

        private static Dictionary<string, object> ToolAmounts(PlayerData pd)
        {
            var d = new Dictionary<string, object>();
            foreach (var t in ToolItemManager.GetAllTools())
                if (t != null) d[t.name] = pd.GetToolData(t.name).AmountLeft;
            return d;
        }

        private static Dictionary<string, object> ExtraEquips(PlayerData pd)
        {
            var d = new Dictionary<string, object>();
            if (pd.ExtraToolEquips == null || ExtraSlots == null) return d;
            var dict = ExtraSlots(pd.ExtraToolEquips);
            if (dict == null) return d;
            foreach (var kv in dict) d[kv.Key] = string.IsNullOrEmpty(kv.Value.EquippedTool) ? null : kv.Value.EquippedTool;
            return d;
        }
    }
}
