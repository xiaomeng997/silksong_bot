using System.Collections.Generic;
using System.Reflection;
using GlobalSettings;
using HarmonyLib;

namespace SsOracle.Crest
{
    /// <summary>
    /// RPC "gameplay.dump" (read-only; crests.md §5 c): the crest and tool numbers of the "Global Gameplay Settings"
    /// asset (GlobalSettings.Gameplay; the code defaults are overridden by the asset). Reply:
    /// <code>
    /// {asset,
    ///  crests: {hunter, hunter_v2, hunter_v3, warrior, reaper, wanderer, cursed, witch, toolmaster, spell, cloakless},
    ///  hunter: {combo_hits, combo_damage_mult, combo2_hits, combo2_damage_mult, combo2_extra_hits,
    ///           combo2_extra_damage_mult, combo2_damage_extra_scale},
    ///  wanderer: {crit_chance, crit_multiplier, crit_magnitude_mult, lucky_min_silk, lucky_dice_bonus},
    ///  warrior: {rage_duration, rage_grace_time, rage_hit_add_time_per_hit, damage_multiplier, rage_damaged_remove_time},
    ///  reaper: {mode_duration},
    ///  weighted_anklet: {tool, damage_knockback_mult, damage_invuln_mult, recoil_steps},
    ///  barbed_wire: {tool, damage_dealt_mult, damage_taken_mult},
    ///  moss: {tools: [creep1, creep2], hits_per_silk, silk: [creep1, creep2]},
    ///  long_needle: {tool, multiplier}, lucky_dice: {tool},
    ///  equipped: {tool name: bool} | null (no hero or no ToolItemManager),
    ///  hero: {silk, wanderer_lucky, luck_modifier, wanderer_queued_crit, wanderer_crits_locked, hunter_meter,
    ///         dash_combo_window} | null,
    ///  fields: {every plain field of the asset}}
    /// </code>
    /// Code constants, not asset values (1.0.30000): Wanderer's luck needs silk >= 9 and not maggoted
    /// (HeroController.IsWandererLucky) and Lucky Dice adds 0.1 to the crit chance multiplier (GetLuckModifier); the moss
    /// tools (Druid's Eyes) add 1 / 2 silk on every second hit taken (DoMossToolHit), and BindInterrupted clears the count.
    /// </summary>
    internal static class GameplayDump
    {
        private static readonly MethodInfo Get = AccessTools.Method(typeof(Gameplay), "Get", new System.Type[0]);

        public static object Dump(Dictionary<string, object> args)
        {
            var gp = Get != null ? Get.Invoke(null, null) as Gameplay : null;
            if (gp == null) throw new System.InvalidOperationException("Global Gameplay Settings not loaded");
            var hero = HeroController.UnsafeInstance;
            return new Dictionary<string, object>
            {
                ["asset"] = gp.name,
                ["crests"] = new Dictionary<string, object>
                {
                    ["hunter"] = CrestModule.Name(Gameplay.HunterCrest),
                    ["hunter_v2"] = CrestModule.Name(Gameplay.HunterCrest2),
                    ["hunter_v3"] = CrestModule.Name(Gameplay.HunterCrest3),
                    ["warrior"] = CrestModule.Name(Gameplay.WarriorCrest),
                    ["reaper"] = CrestModule.Name(Gameplay.ReaperCrest),
                    ["wanderer"] = CrestModule.Name(Gameplay.WandererCrest),
                    ["cursed"] = CrestModule.Name(Gameplay.CursedCrest),
                    ["witch"] = CrestModule.Name(Gameplay.WitchCrest),
                    ["toolmaster"] = CrestModule.Name(Gameplay.ToolmasterCrest),
                    ["spell"] = CrestModule.Name(Gameplay.SpellCrest),
                    ["cloakless"] = CrestModule.Name(Gameplay.CloaklessCrest),
                },
                ["hunter"] = new Dictionary<string, object>
                {
                    ["combo_hits"] = Gameplay.HunterComboHits,
                    ["combo_damage_mult"] = Gameplay.HunterComboDamageMult,
                    ["combo2_hits"] = Gameplay.HunterCombo2Hits,
                    ["combo2_damage_mult"] = Gameplay.HunterCombo2DamageMult,
                    ["combo2_extra_hits"] = Gameplay.HunterCombo2ExtraHits,
                    ["combo2_extra_damage_mult"] = Gameplay.HunterCombo2ExtraDamageMult,
                    ["combo2_damage_extra_scale"] = Gameplay.HunterCombo2DamageExtraScale,
                },
                ["wanderer"] = new Dictionary<string, object>
                {
                    ["crit_chance"] = Gameplay.WandererCritChance,
                    ["crit_multiplier"] = Gameplay.WandererCritMultiplier,
                    ["crit_magnitude_mult"] = Gameplay.WandererCritMagnitudeMult,
                    ["lucky_min_silk"] = 9,
                    ["lucky_dice_bonus"] = 0.1f,
                },
                ["warrior"] = new Dictionary<string, object>
                {
                    ["rage_duration"] = Gameplay.WarriorRageDuration,
                    ["rage_grace_time"] = Gameplay.WarriorRageGraceTime,
                    ["rage_hit_add_time_per_hit"] = Gameplay.WarriorRageHitAddTimePerHit,
                    ["damage_multiplier"] = Gameplay.WarriorDamageMultiplier,
                    ["rage_damaged_remove_time"] = Gameplay.WarriorRageDamagedRemoveTime,
                },
                ["reaper"] = new Dictionary<string, object> { ["mode_duration"] = Gameplay.ReaperModeDuration },
                ["weighted_anklet"] = new Dictionary<string, object>
                {
                    ["tool"] = CrestModule.Name(Gameplay.WeightedAnkletTool),
                    ["damage_knockback_mult"] = Gameplay.WeightedAnkletDmgKnockbackMult,
                    ["damage_invuln_mult"] = Gameplay.WeightedAnkletDmgInvulnMult,
                    ["recoil_steps"] = Gameplay.WeightedAnkletRecoilSteps,
                },
                ["barbed_wire"] = new Dictionary<string, object>
                {
                    ["tool"] = CrestModule.Name(Gameplay.BarbedWireTool),
                    ["damage_dealt_mult"] = Gameplay.BarbedWireDamageDealtMultiplier,
                    ["damage_taken_mult"] = Gameplay.BarbedWireDamageTakenMultiplier,
                },
                ["moss"] = new Dictionary<string, object>
                {
                    ["tools"] = new[] { CrestModule.Name(Gameplay.MossCreep1Tool), CrestModule.Name(Gameplay.MossCreep2Tool) },
                    ["hits_per_silk"] = 2,
                    ["silk"] = new[] { 1, 2 },
                },
                ["long_needle"] = new Dictionary<string, object>
                {
                    ["tool"] = CrestModule.Name(Gameplay.LongNeedleTool),
                    ["multiplier"] = Gameplay.LongNeedleMultiplier,
                },
                ["lucky_dice"] = new Dictionary<string, object> { ["tool"] = CrestModule.Name(Gameplay.LuckyDiceTool) },
                ["equipped"] = Equipped(hero),
                ["hero"] = HeroState(hero),
                ["fields"] = PlainValues.Fields(gp),
            };
        }

        /// <summary>IsEquipped of the tools above; only when ToolItem.IsEquipped cannot reach a scene search (SafeReads).</summary>
        private static object Equipped(HeroController hero)
        {
            if (!Hero.SafeReads.ToolsReadable(hero)) return null;
            var d = new Dictionary<string, object>();
            foreach (var tool in new[] { Gameplay.WeightedAnkletTool, Gameplay.BarbedWireTool, Gameplay.MossCreep1Tool, Gameplay.MossCreep2Tool,
                                         Gameplay.LongNeedleTool, Gameplay.LuckyDiceTool, Gameplay.FracturedMaskTool })
                if (tool != null) d[tool.name] = tool.IsEquipped;
            return d;
        }

        private static object HeroState(HeroController hero)
        {
            var gm = GameManager._instance;
            var pd = gm != null ? gm.playerData : null;
            if (hero == null || pd == null) return null;
            return new Dictionary<string, object>
            {
                ["silk"] = pd.silk,
                // IsWandererLucky reads Gameplay.WandererCrest.IsEquipped (PlayerData.instance) and the hero's cached playerData.
                ["wanderer_lucky"] = CrestModule.Try(() => hero.IsWandererLucky),
                ["luck_modifier"] = Hero.SafeReads.ToolsReadable(hero) ? CrestModule.Try(() => hero.GetLuckModifier()) : null,
                ["wanderer_queued_crit"] = hero.WandererState.QueuedNextHitCritical,
                ["wanderer_crits_locked"] = hero.WandererState.CriticalHitsLocked,
                ["hunter_meter"] = hero.HunterUpgState.CurrentMeterHits,
                ["dash_combo_window"] = hero.DASHCOMBO_WINDOW_TIME,
            };
        }
    }
}
