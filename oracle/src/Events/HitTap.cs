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
    ///   ent       GetInstanceID of the HealthManager that lost hp (TakeDamage forwards to sendDamageTo when set), the
    ///             same id as its "ents" iid; reported whether or not it is in "ents" this frame
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
    /// Only calls that changed hp or killed are reported (an immune or zero-damage hit is not). Every source counts,
    /// not only the hero: src tells them apart. Cost: two field reads per call in the prefix; the payload is built only
    /// for a real hit while a brain is connected (a handful per second in combat).
    /// </summary>
    internal static class HitTap
    {
        public static void Install(Harmony h)
        {
            var hm = typeof(HealthManager);
            Tap.Patch(h, hm, "TakeDamage", new[] { typeof(HitInstance) }, typeof(HitTap), nameof(HitPrefix), nameof(TakeDamagePostfix));
            Tap.Patch(h, hm, "ApplyExtraDamage", new[] { typeof(HitInstance) }, typeof(HitTap), nameof(HitPrefix), nameof(ExtraHitPostfix));
            Tap.Patch(h, hm, "ApplyExtraDamage", new[] { typeof(int) }, typeof(HitTap), nameof(ExtraIntPrefix), nameof(ExtraIntPostfix));
        }

        internal struct Before
        {
            public HealthManager Target;
            public int Hp;
            public bool Dead;
            public int Dealt;
        }

        private static Before Capture(HealthManager hm, int dealt)
        {
            var t = hm.SendDamageTo != null ? hm.SendDamageTo : hm;
            return new Before { Target = t, Hp = t.hp, Dead = t.isDead, Dealt = dealt };
        }

        // The postfix reads hitInstance after the body ran: TakeDamage reassigns its parameter (damage scaling, crit),
        // so the amount the attacker passed is captured here.
        private static void HitPrefix(HealthManager __instance, HitInstance hitInstance, out Before __state)
        {
            __state = default;
            try { __state = Capture(__instance, hitInstance.DamageDealt); }
            catch { }
        }

        private static void ExtraIntPrefix(HealthManager __instance, int damageAmount, out Before __state)
        {
            __state = default;
            try { __state = Capture(__instance, damageAmount); }
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
                var t = b.Target;
                if (ReferenceEquals(t, null) || t == null) return;
                var after = t.hp;
                var dead = t.isDead;
                if (after == b.Hp && dead == b.Dead) return;
                if (!Tap.Active) return;
                var go = t.gameObject;
                var d = Tap.Data(12);
                d["ent"] = go.GetInstanceID();
                d["type_key"] = Entities.EntityRegistry.TypeKey(go.name);
                d["dmg"] = b.Hp - after;
                d["dealt"] = b.Dealt;
                d["attack"] = EnumName<AttackTypes>.Of(attack);
                d["src"] = src != null ? src.name : null;
                d["hp_before"] = b.Hp;
                d["hp_after"] = after;
                d["dead"] = after <= 0 || dead;
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
