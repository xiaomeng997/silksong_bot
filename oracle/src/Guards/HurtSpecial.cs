using System;
using System.Collections.Generic;
using GlobalEnums;

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
    /// Replies with health before/after; guard events arrive in the next STATE "ev".
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
            var hpBefore = pd.health;
            var blueBefore = pd.healthBlue;
            var invulnBefore = hero.cState.Invulnerable;
            var frame = UnityEngine.Time.frameCount;
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
                    var hazard = (HazardType)Enum.Parse(typeof(HazardType), Ipc.Rpc.Str(args, "hazard", "ENEMY"), ignoreCase: true);
                    var side = (CollisionSide)Enum.Parse(typeof(CollisionSide), Ipc.Rpc.Str(args, "side", "left"), ignoreCase: true);
                    var flags = ParseFlags(args);
                    hero.TakeDamage(hero.gameObject, side, amount, hazard, flags);
                    break;
                case "death_catch":
                    pd.health = (int)Ipc.Rpc.Long(args, "set_health", 0);
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
                ["dead"] = hero != null && hero.cState.dead,
                ["pd_mode"] = pd != null ? pd.permadeathMode.ToString() : null,
            };
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
