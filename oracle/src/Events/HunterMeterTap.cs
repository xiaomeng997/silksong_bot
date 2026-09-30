using GlobalEnums;
using HarmonyLib;
using UnityEngine;

namespace SsOracle.Events
{
    /// <summary>
    /// "hunter_meter" {reason, from, to, crest, caller?}: the Hunter combo meter (HeroController.HunterUpgState
    /// .CurrentMeterHits, STATE hero.hunter_meter) went down, i.e. ResetHunterUpgCrestState ran (DESIGN P17; crests.md
    /// §5 f). The meter only counts up in NailHitEnemy (Hunter_v2/v3 equipped, a silk-generating hit) and is only ever
    /// zeroed, so any decrease is a reset. 1.0.30000 resets it from (HeroController.cs):
    /// <list type="bullet">
    /// <item>TakeDamage after health is taken (:5512) -> "damage"; DoSpecialDamage (:5207, the frost/quick/chomp/tag
    /// paths) -> "special_damage".</item>
    /// <item>ResetAllCrestState(clearHunterState: true) (:5948-5970), reached from MaxHealth (:6329, death respawn, bosses,
    /// HeroSlabCapture; whether a bench calls it is decided by FSMs) -> "max_health"; SetIsMaggoted(true) (:2603) ->
    /// "maggoted"; the "TOOL EQUIPS CHANGED" event, i.e. ToolItemManager.SendEquippedChangedEvent, unless the tools'
    /// active state is changing (cutscenes; :5961) -> "equips_changed"; anything else (hero Awake,
    /// GameManager.FixUpSaveState) -> "crest_reset" with the managed caller.</item>
    /// </list>
    /// ResetHunterUpgCrestState itself is a one-line method the JIT may inline, so the hooks wrap the entry points: the
    /// outermost hooked call on the stack names the reason, and its postfix compares the meter before and after. The
    /// per-frame poll catches what no hook saw ("hero_rebuilt" for a new HeroController, else "unknown"). Only decreases
    /// from a positive value are events; base Hunter never fills the meter.
    /// </summary>
    internal static class HunterMeterTap
    {
        private static int depth;
        private static int pushedFrame = -1;
        private static string outerReason;
        private static int before;

        // What the poll compares against: the meter as last seen by the poll or a hook, and whose meter it was.
        private static int lastSeen;
        private static int lastHeroId;

        public static void Install(Harmony h)
        {
            var hc = typeof(HeroController);
            var me = typeof(HunterMeterTap);
            Tap.Patch(h, hc, "TakeDamage", new[] { typeof(GameObject), typeof(CollisionSide), typeof(int), typeof(HazardType), typeof(DamagePropertyFlags) },
                me, nameof(DamagePrefix), nameof(ExitPostfix));
            Tap.Patch(h, hc, "DoSpecialDamage", new[] { typeof(int), typeof(bool), typeof(string), typeof(bool), typeof(bool), typeof(bool), typeof(bool) },
                me, nameof(SpecialPrefix), nameof(ExitPostfix));
            Tap.Patch(h, hc, "MaxHealth", new System.Type[0], me, nameof(MaxHealthPrefix), nameof(ExitPostfix));
            Tap.Patch(h, hc, "SetIsMaggoted", new[] { typeof(bool) }, me, nameof(MaggotedPrefix), nameof(ExitPostfix));
            Tap.Patch(h, hc, "ResetAllCrestState", new[] { typeof(bool) }, me, nameof(CrestResetPrefix), nameof(ExitPostfix));
            Tap.Patch(h, typeof(ToolItemManager), "SendEquippedChangedEvent", new[] { typeof(bool) }, me, nameof(EquipsPrefix), nameof(ExitPostfix));
        }

        /// <summary>Meter of the current hero, 0 without one. A field read (HunterUpgState copies a one-int struct).</summary>
        public static int Meter(HeroController hero) => hero != null ? hero.HunterUpgState.CurrentMeterHits : 0;

        private static void DamagePrefix() => Enter("damage");
        private static void SpecialPrefix() => Enter("special_damage");
        private static void MaxHealthPrefix() => Enter("max_health");
        private static void MaggotedPrefix() => Enter("maggoted");
        private static void CrestResetPrefix() => Enter("crest_reset");
        private static void EquipsPrefix() => Enter("equips_changed");

        private static void Enter(string reason)
        {
            var frame = Time.frameCount;
            if (depth > 0 && pushedFrame != frame) depth = 0;   // left open by an exception in an earlier frame
            if (depth++ == 0)
            {
                outerReason = reason;
                before = Meter(HeroController.UnsafeInstance);
            }
            pushedFrame = frame;
        }

        private static void ExitPostfix()
        {
            if (depth == 0 || --depth > 0) return;
            var hero = HeroController.UnsafeInstance;
            var now = Meter(hero);
            if (before > 0 && now < before) Report(outerReason, before, now, hero, outerReason == "crest_reset");
            outerReason = null;
        }

        /// <summary>Per frame, connected or not: a context left open by an exception must not leak into the next frame.</summary>
        public static void ResetIfStale()
        {
            if (depth != 0 && pushedFrame != Time.frameCount) depth = 0;
        }

        /// <summary>Per frame while a brain is connected (EventsRunner.LateUpdate, before the STATE build).</summary>
        public static void Poll(HeroController hero)
        {
            if (hero == null) return;   // menus, loads, Save & Quit: judge the next hero against the last value
            var id = hero.GetInstanceID();
            var now = Meter(hero);
            if (id != lastHeroId)
            {
                if (now < lastSeen) Report("hero_rebuilt", lastSeen, now, hero, false);
                lastHeroId = id;
            }
            else if (now < lastSeen)
            {
                Report("unknown", lastSeen, now, hero, false);
            }
            lastSeen = now;
        }

        /// <summary>Brain (re)connected: drops from before are not reported.</summary>
        public static void Rebaseline()
        {
            var hero = HeroController.UnsafeInstance;
            lastSeen = Meter(hero);
            lastHeroId = hero != null ? hero.GetInstanceID() : 0;
        }

        private static void Report(string reason, int from, int to, HeroController hero, bool withCaller)
        {
            lastSeen = to;
            if (hero != null) lastHeroId = hero.GetInstanceID();
            if (!Tap.Active) return;
            var gm = GameManager._instance;
            var pd = gm != null ? gm.playerData : null;
            var d = Tap.Data(8);
            d["reason"] = reason;
            d["from"] = from;
            d["to"] = to;
            d["crest"] = pd != null ? pd.CurrentCrestID : null;
            Tap.Attribute(d, withCaller);
            Tap.Emit("hunter_meter", d);
        }
    }
}
