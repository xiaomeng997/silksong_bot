using System;
using System.Collections.Generic;
using GlobalEnums;
using GlobalSettings;
using UnityEngine;

namespace SsOracle.Guards
{
    /// <summary>
    /// hurt.special (training probe tool, TRAIN profile only): drives Hornet through the game's own damage entry
    /// points, so LethalBlock is tested on the real code paths (DESIGN §3.1.1 LethalBlock unit tests; m0 §2.5):
    /// <list type="bullet">
    /// <item>quick {amount, allow_mask_break=false}: TakeQuickDamage, i.e. DoSpecialDamage(canDie: false). Cog/grab
    /// chains. Ignores i-frames; can leave 0 HP without dying.</item>
    /// <item>chomp: TakeChompDamage (1 damage, canDie, may break the mask). Grab-like.</item>
    /// <item>frost {amount}: TakeFrostDamage (canDie, may break the mask).</item>
    /// <item>critical: CriticalDamage (blue health to 0, health to 1; never lethal on its own).</item>
    /// <item>take_health {amount}: HeroController.TakeHealth, the FSM "TakeHealth" path.</item>
    /// <item>damage {amount, hazard=ENEMY, flags=0, side=left}: TakeDamage with DamagePropertyFlags (MidChain, NonLethal ...).</item>
    /// <item>death_catch {set_health=0}: writes health (as an FSM SetPlayerDataInt would) and calls CheckDeathCatch,
    /// which starts Die: exercises net 2 without net 1.</item>
    /// </list>
    /// A hit that could kill (a conservative replay of what the entry point would take, ignoring the Fractured Mask,
    /// Lucky Dice and the Lava Bell) is refused unless LethalBlock blocks, and always while a Steel Soul session has no
    /// snapshot. The one exception is allow_death=true in a Classic session (a death there costs nothing permanent), for
    /// testing observe mode. Replies with health before/after and take_health_calls (0 = the hit never reached
    /// PlayerData.TakeHealth: Lucky Dice, Warding Bell, a parry, i-frames ...); guard events arrive in the next STATE "ev".
    /// </summary>
    internal static class HurtSpecial
    {
        public static void Install() => Ipc.Rpc.Register("hurt.special", Hurt);

        private static object Hurt(Dictionary<string, object> args)
        {
            if (!Core.Profile.Rules.ProbeTools) throw new InvalidOperationException($"probe tools are disabled in profile {Core.Profile.Current}");
            if (GuardState.Refused) throw new InvalidOperationException("guards are refused: " + string.Join("; ", GuardState.Refusals.ToArray()));
            var hero = HeroController.UnsafeInstance;
            var gm = GameManager._instance;
            var pd = gm != null ? gm.playerData : null;
            if (hero == null || pd == null) throw new InvalidOperationException("no hero");

            var kind = Ipc.Rpc.Str(args, "kind", "quick");
            var amount = (int)Ipc.Rpc.Long(args, "amount", 1);
            var hazard = kind == "damage" ? (HazardType)Enum.Parse(typeof(HazardType), Ipc.Rpc.Str(args, "hazard", "ENEMY"), ignoreCase: true) : HazardType.ENEMY;
            var flags = kind == "damage" ? ParseFlags(args) : DamagePropertyFlags.None;
            var setHealth = (int)Ipc.Rpc.Long(args, "set_health", 0);
            CheckLethal(args, kind, amount, hazard, flags, setHealth, pd);

            var hpBefore = pd.health;
            var blueBefore = pd.healthBlue;
            var invulnBefore = hero.cState.Invulnerable;
            var callsBefore = LethalBlock.TakeHealthCalls;
            var frame = Time.frameCount;
            Core.Plugin.Log.LogWarning($"hurt.special {kind} {amount} at frame {frame} (training probe)");
            switch (kind)
            {
                case "quick":
                    hero.TakeQuickDamage(amount, true, Ipc.Rpc.Bool(args, "allow_mask_break"));
                    break;
                case "chomp":
                    hero.TakeChompDamage();
                    break;
                case "frost":
                    hero.TakeFrostDamage(amount);
                    break;
                case "critical":
                    hero.CriticalDamage();
                    break;
                case "take_health":
                    hero.TakeHealth(amount);
                    break;
                case "damage":
                    var side = (CollisionSide)Enum.Parse(typeof(CollisionSide), Ipc.Rpc.Str(args, "side", "left"), ignoreCase: true);
                    hero.TakeDamage(hero.gameObject, side, amount, hazard, flags);
                    break;
                case "death_catch":
                    pd.health = setHealth;
                    hero.CheckDeathCatch();
                    break;
                default:
                    throw new ArgumentException("kind must be quick|chomp|frost|critical|take_health|damage|death_catch");
            }
            gm = GameManager._instance;
            pd = gm != null ? gm.playerData : null;
            return new Dictionary<string, object>
            {
                ["frame"] = frame,
                ["kind"] = kind,
                ["hp_before"] = hpBefore,
                ["blue_before"] = blueBefore,
                ["invuln_before"] = invulnBefore,
                ["hp_after"] = pd != null ? pd.health : -1,
                ["blue_after"] = pd != null ? pd.healthBlue : -1,
                ["take_health_calls"] = LethalBlock.TakeHealthCalls - callsBefore,
                ["dead"] = hero != null && hero.cState.dead,
                ["pd_mode"] = pd != null ? pd.permadeathMode.ToString() : null,
            };
        }

        /// <summary>Throws when the hit could leave Hornet at 0 HP or start Die and nothing may stop it (see the summary).</summary>
        private static void CheckLethal(Dictionary<string, object> args, string kind, int amount, HazardType hazard,
            DamagePropertyFlags flags, int setHealth, PlayerData pd)
        {
            var why = PossiblyLethal(kind, amount, hazard, flags, setHealth, pd);
            if (why == null) return;
            if (SteelSoulSnapshot.Unprotected(out var slot))
                throw new InvalidOperationException($"hurt.special {kind} could kill ({why}) and the Steel Soul session in slot {slot} has no snapshot (slot.snapshot first)");
            var mode = GuardState.Lethal;
            if (mode == LethalMode.Block) return;
            if (pd.permadeathMode != PermadeathModes.Off)
                throw new InvalidOperationException($"hurt.special {kind} could kill ({why}) and lethal_block is {GuardState.LethalName(mode)}: refused in a Steel Soul session");
            if (!Ipc.Rpc.Bool(args, "allow_death"))
                throw new InvalidOperationException($"hurt.special {kind} could kill ({why}) and lethal_block is {GuardState.LethalName(mode)}; " +
                                                    "pass allow_death=true to let a Classic death happen");
        }

        /// <summary>
        /// Why the hit could reach 0 HP or start Die, or null. Replays TakeHealth (LethalBlock.Simulate) without the
        /// Fractured Mask on an upper bound of the amount the entry point would pass: TakeDamage's hazard overrides,
        /// the boss-scene multiplier (up to 9999, so any boss scene counts) and the Barbed Wire multiplier, as in
        /// 1.0.30000 HeroController.TakeDamage / DoSpecialDamage.
        /// </summary>
        private static string PossiblyLethal(string kind, int amount, HazardType hazard, DamagePropertyFlags flags, int setHealth, PlayerData pd)
        {
            int dmg;
            switch (kind)
            {
                case "death_catch":
                    return setHealth <= 0 ? $"CheckDeathCatch with health {setHealth}" : null;
                case "critical":
                    return Replay(pd, pd.health - 1, blue: 0) ? "CriticalDamage leaves 0 HP (health above CurrentMaxHealth)" : null;
                case "quick":
                    dmg = BarbedWire(amount);
                    break;
                case "chomp":
                    dmg = BarbedWire(1);
                    break;
                case "frost":
                case "take_health":
                    dmg = amount;
                    break;
                case "damage":
                    if (amount <= 0) return null;
                    if (BossSceneController.IsBossScene) return "TakeDamage in a boss scene (damage multiplied, up to 9999)";
                    dmg = BarbedWire(HazardAmount(hazard, flags, amount));
                    break;
                default:
                    return null;   // Hurt rejects the kind
            }
            return Replay(pd, dmg, pd.healthBlue) ? $"{dmg} damage at {pd.health} HP + {pd.healthBlue} blue" : null;
        }

        private static bool Replay(PlayerData pd, int dmg, int blue) =>
            LethalBlock.Simulate(pd.health, pd.maxHealth, pd.CurrentMaxHealth, blue, false, 0, dmg, true, false).ReachesZero;

        /// <summary>TakeDamage's fixed amounts per hazard (1.0.30000 HeroController.cs:5286-5320).</summary>
        private static int HazardAmount(HazardType hazard, DamagePropertyFlags flags, int amount)
        {
            switch (hazard)
            {
                case HazardType.SPIKES:
                case HazardType.ACID:
                case HazardType.COAL:
                case HazardType.COAL_SPIKES:
                case HazardType.ZAP:
                    return 1;
                case HazardType.LAVA:
                case HazardType.STEAM:
                    return 2;
                case HazardType.RESPAWN_PIT:
                    return 0;
                default:
                    return (flags & (DamagePropertyFlags.Flame | DamagePropertyFlags.Void)) != 0 ? 2 : amount;
            }
        }

        private static int BarbedWire(int dmg)
        {
            var tool = Gameplay.BarbedWireTool;
            return tool && tool.IsEquipped ? Mathf.FloorToInt(dmg * Gameplay.BarbedWireDamageTakenMultiplier) : dmg;
        }

        /// <summary>flags as an int, a DamagePropertyFlags name, or a list of names.</summary>
        private static DamagePropertyFlags ParseFlags(Dictionary<string, object> args)
        {
            if (!args.TryGetValue("flags", out var v) || v == null) return DamagePropertyFlags.None;
            switch (v)
            {
                case long l: return (DamagePropertyFlags)l;
                case string s: return (DamagePropertyFlags)Enum.Parse(typeof(DamagePropertyFlags), s, ignoreCase: true);
                case List<object> list:
                    var f = DamagePropertyFlags.None;
                    foreach (var x in list) f |= (DamagePropertyFlags)Enum.Parse(typeof(DamagePropertyFlags), Convert.ToString(x), ignoreCase: true);
                    return f;
                default: throw new ArgumentException("flags must be an int, a name or a list of names");
            }
        }
    }
}
