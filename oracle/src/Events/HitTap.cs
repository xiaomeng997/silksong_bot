using HarmonyLib;
using UnityEngine;

namespace SsOracle.Events
{
    /// <summary>
    /// "hit" events: damage applied to a HealthManager (M2 cross-module decision 5; the WorldState review's open issue:
    /// HIT_DEALT was inferred from HP drops between consecutive STATEs, which misses killing blows, two hits in one
    /// frame and every enemy outside "ents"). Prefix + postfix on the three places HealthManager lowers hp:
    /// TakeDamage(HitInstance) (nail, tools, spells; reached through Hit), ApplyExtraDamage(HitInstance) (lag hits and
    /// damage tags such as poison and zap) and ApplyExtraDamage(int) (DamageEffectTicker). Payload:
    ///   ent       GetInstanceID of the HealthManager that lost hp (TakeDamage forwards to sendDamageTo when set; the
    ///             ApplyExtraDamage overloads never forward), the same id as its "ents" iid; reported whether or not it
    ///             is in "ents" this frame
    ///   type_key  its GameObject name without instance suffixes (EntityRegistry.TypeKey)
    ///   dmg       hp_before - hp_after (the game floors hp at -1000, so an overkill still counts in full)
    ///   dealt     HitInstance.DamageDealt as the attacker passed it, before the target's damage scaling, the Wanderer
    ///             crit multiplier and HitInstance.Multiplier (the int argument for ApplyExtraDamage(int))
    ///   attack    AttackTypes name ("Nail", "Generic", ...)
    ///   src       name of HitInstance.Source (the hero's "Slash", "DownSlash", a tool's object, ...), null without one
    ///   hp_before, hp_after
    ///   dead      hp_after &lt;= 0 or HealthManager.isDead after the call (a boss with a special death, e.g. the Bell
    ///             Beast, keeps isDead false and dies through its FSM, so hp is the test)
    ///   crit      HitInstance.CriticalHit
    /// Only calls that changed hp or killed are reported (an immune or zero-damage hit is not). A call nested inside
    /// another on the same target (a lag hit with no delay) is reported first and the outer call reports only its own
    /// part, so a target's events always add up to its hp change. Every source counts,
    /// not only the hero: src tells them apart. Cost: two field reads per call in the prefix; the payload is built only
    /// for a real hit while a brain is connected (a handful per second in combat).
    /// </summary>
    internal static class HitTap
    {
        public static void Install(Harmony h)
        {
            var hm = typeof(HealthManager);
            Tap.Patch(h, hm, "TakeDamage", new[] { typeof(HitInstance) }, typeof(HitTap), nameof(HitPrefix), nameof(TakeDamagePostfix));
            Tap.Patch(h, hm, "ApplyExtraDamage", new[] { typeof(HitInstance) }, typeof(HitTap), nameof(ExtraHitPrefix), nameof(ExtraHitPostfix));
            Tap.Patch(h, hm, "ApplyExtraDamage", new[] { typeof(int) }, typeof(HitTap), nameof(ExtraIntPrefix), nameof(ExtraIntPostfix));
        }

        internal struct Before
        {
            public HealthManager Target;
            public int Hp;
            public bool Dead;
            public int Dealt;
            public bool Tracked;   // pushed on the nesting stack below
            public int Depth;
        }

        // Nesting: LagHits is a coroutine, so with no start delay and a zero HitDelay its first ApplyExtraDamage runs
        // inside the TakeDamage that started it, on the same HealthManager. The inner call reports first; the outer
        // call then reports only its own part, so the "hit" events of one target add up to its hp change. A postfix
        // skipped by an exception leaves the depth high; the next top-level postfix pops back to its own depth.
        private const int MaxDepth = 8;
        private static int depth;
        private static readonly HealthManager[] DepthTarget = new HealthManager[MaxDepth];
        private static readonly int[] InnerDmg = new int[MaxDepth];

        /// <param name="forwards">TakeDamage lowers sendDamageTo's hp when it is set (HealthManager.cs:1299-1306);
        /// both ApplyExtraDamage overloads always lower the instance's own hp (1460-1477).</param>
        private static Before Capture(HealthManager hm, int dealt, bool forwards)
        {
            var t = forwards && hm.SendDamageTo != null ? hm.SendDamageTo : hm;
            var b = new Before { Target = t, Hp = t.hp, Dead = t.isDead, Dealt = dealt };
            if (depth >= MaxDepth) depth = 0;
            b.Tracked = true;
            b.Depth = depth;
            DepthTarget[depth] = t;
            InnerDmg[depth] = 0;
            depth++;
            return b;
        }

        /// <summary>The part of a call's hp change that is its own: total minus what calls nested inside it on the same
        /// target reported (pure; oracle/tests/EntitiesCheck).</summary>
        public static int OwnDamage(int hpBefore, int hpAfter, int innerDamage) => hpBefore - hpAfter - innerDamage;

        // The postfix reads hitInstance after the body ran: TakeDamage reassigns its parameter (damage scaling, crit),
        // so the amount the attacker passed is captured here.
        private static void HitPrefix(HealthManager __instance, HitInstance hitInstance, out Before __state)
        {
            __state = default;
            try { __state = Capture(__instance, hitInstance.DamageDealt, forwards: true); }
            catch { }
        }

        private static void ExtraHitPrefix(HealthManager __instance, HitInstance hitInstance, out Before __state)
        {
            __state = default;
            try { __state = Capture(__instance, hitInstance.DamageDealt, forwards: false); }
            catch { }
        }

        private static void ExtraIntPrefix(HealthManager __instance, int damageAmount, out Before __state)
        {
            __state = default;
            try { __state = Capture(__instance, damageAmount, forwards: false); }
            catch { }
        }

        private static void TakeDamagePostfix(HitInstance hitInstance, Before __state) =>
            Report(__state, hitInstance.AttackType, hitInstance.Source, hitInstance.CriticalHit);

        private static void ExtraHitPostfix(HitInstance hitInstance, Before __state) =>
            Report(__state, hitInstance.AttackType, hitInstance.Source, hitInstance.CriticalHit);

        private static void ExtraIntPostfix(Before __state) => Report(__state, AttackTypes.Generic, null, false);

        private static int errorsLogged;

        private static void Report(Before b, AttackTypes attack, GameObject src, bool crit)
        {
            try
            {
                var inner = 0;
                if (b.Tracked)
                {
                    depth = b.Depth;
                    inner = InnerDmg[b.Depth];
                    DepthTarget[b.Depth] = null;
                }
                var t = b.Target;
                if (ReferenceEquals(t, null) || t == null) return;
                var after = t.hp;
                if (b.Tracked && b.Depth > 0 && ReferenceEquals(DepthTarget[b.Depth - 1], t)) InnerDmg[b.Depth - 1] += b.Hp - after;
                var own = OwnDamage(b.Hp, after, inner);
                var hpAfter = b.Hp - own;
                var dead = t.isDead && inner == 0;   // an inner call that killed reported it already
                if (own == 0 && !(dead && !b.Dead)) return;
                if (!Tap.Active) return;
                var go = t.gameObject;
                var d = Tap.Data(12);
                d["ent"] = go.GetInstanceID();
                d["type_key"] = Entities.EntityRegistry.TypeKey(go.name);
                d["dmg"] = own;
                d["dealt"] = b.Dealt;
                d["attack"] = EnumName<AttackTypes>.Of(attack);
                d["src"] = src != null ? src.name : null;
                d["hp_before"] = b.Hp;
                d["hp_after"] = hpAfter;
                d["dead"] = hpAfter <= 0 || dead;
                d["crit"] = crit;
                Tap.Emit("hit", d);
            }
            catch (System.Exception e)
            {
                // Never throw into HealthManager.
                if (errorsLogged++ < 10) Core.Plugin.Log.LogWarning("HitTap: " + e.GetType().Name + ": " + e.Message);
            }
        }
    }
}
