using System.Collections.Generic;
using System.Runtime.CompilerServices;
using GlobalEnums;
using HarmonyLib;
using UnityEngine;

namespace SsOracle.Events
{
    /// <summary>
    /// "hp" events: one per change of health or healthBlue (DESIGN §3.1.2 health_changes; m0 §3.1 MVP hooks).
    /// Every C# path that lowers health goes through PlayerData.TakeHealth (m0 §2.5); FSMs and restores write
    /// through the name-based setters or directly. So: hooks on TakeHealth (with the Fractured Mask outcome) and
    /// on the other writers attribute a change to its source, and a per-frame poll (EventsRunner) catches the rest
    /// as src "poll". All of them diff against the last observed values, so each change is reported exactly once.
    /// </summary>
    internal static class HpTap
    {
        private static bool baselined;
        private static int pdId;
        private static int lastH, lastB;

        // Outermost TakeHealth call (it recurses once when blue health overflows).
        private static int takeDepth;
        private static int thAmount, thBeforeH, thBeforeB, thMaskBefore;
        private static bool thAllowBreak, thBlueFlag;

        public static int LastHealth => lastH;
        public static int LastBlue => lastB;

        public static void Install(Harmony h)
        {
            var pd = typeof(PlayerData);
            Tap.Patch(h, pd, "TakeHealth", new[] { typeof(int), typeof(bool), typeof(bool) }, typeof(HpTap), nameof(TakeHealthPrefix), nameof(TakeHealthPostfix));
            Tap.Patch(h, pd, "AddHealth", new[] { typeof(int) }, typeof(HpTap), postfix: nameof(AddHealthPostfix));
            Tap.Patch(h, pd, "MaxHealth", new System.Type[0], typeof(HpTap), postfix: nameof(MaxHealthPostfix));
            Tap.Patch(h, pd, "AddToMaxHealth", new[] { typeof(int) }, typeof(HpTap), postfix: nameof(AddToMaxHealthPostfix));
            Tap.Patch(h, pd, "SetInt", new[] { typeof(string), typeof(int) }, typeof(HpTap), postfix: nameof(SetIntPostfix));
            Tap.Patch(h, pd, "IntAdd", new[] { typeof(string), typeof(int) }, typeof(HpTap), postfix: nameof(IntAddPostfix));
            Tap.Patch(h, pd, "IncrementInt", new[] { typeof(string) }, typeof(HpTap), postfix: nameof(IncrementIntPostfix));
            Tap.Patch(h, pd, "DecrementInt", new[] { typeof(string) }, typeof(HpTap), postfix: nameof(DecrementIntPostfix));
            Tap.Patch(h, typeof(HeroItemsState), "Apply", new[] { typeof(HeroController) }, typeof(HpTap), postfix: nameof(HeroItemsApplyPostfix));
            // PlayerData.OnUpdatedVariable (the SetVariable<T> path) is shared with GateTap; see GateTap.OnUpdatedVariablePostfix.
        }

        /// <summary>Forget the baseline (brain reconnected, PlayerData replaced): the next observation is silent.</summary>
        public static void Rebaseline() => baselined = false;

        /// <summary>
        /// Compare <paramref name="pd"/> with the last observed values and emit "hp" if they differ (or if
        /// <paramref name="force"/>, e.g. a mask broke without a visible change). A different PlayerData instance
        /// (new game, load, quit: m0:N42) only re-baselines.
        /// </summary>
        public static void Observe(PlayerData pd, string src, bool withCaller, Dictionary<string, object> extra = null, bool force = false)
        {
            if (pd == null) return;
            var id = RuntimeHelpers.GetHashCode(pd);
            int h = pd.health, b = pd.healthBlue;
            if (!baselined || id != pdId)
            {
                baselined = true;
                pdId = id;
                lastH = h;
                lastB = b;
                return;
            }
            if (h == lastH && b == lastB && !force) return;
            int dh = h - lastH, db = b - lastB;
            lastH = h;
            lastB = b;
            if (!Tap.Active) return;
            var d = extra ?? Tap.Data(14);
            d["h"] = h;
            d["hb"] = b;
            d["delta"] = dh;
            d["blue_delta"] = db;
            d["src"] = src;
            DamageCtx.Fill(d);
            Tap.Attribute(d, withCaller);
            Tap.Emit("hp", d);
        }

        private static bool IsHealthName(string name) => name == "health" || name == "healthBlue";

        private static int MaskLeft(out bool equipped)
        {
            equipped = false;
            try
            {
                var tool = GlobalSettings.Gameplay.FracturedMaskTool;
                if (tool == null) return -1;
                equipped = tool.IsEquipped;
                return tool.SavedData.AmountLeft;
            }
            catch
            {
                return -1;
            }
        }

        private static void TakeHealthPrefix(PlayerData __instance, int amount, bool hasBlueHealth, bool allowFracturedMaskBreak)
        {
            if (takeDepth++ > 0) return;
            // Flush direct writes made just before (CriticalDamage zeroes healthBlue, then calls TakeHealth).
            Observe(__instance, "direct", false);
            thAmount = amount;
            thBlueFlag = hasBlueHealth;
            thAllowBreak = allowFracturedMaskBreak;
            thBeforeH = __instance.health;
            thBeforeB = __instance.healthBlue;
            thMaskBefore = MaskLeft(out _);
        }

        private static void TakeHealthPostfix(PlayerData __instance)
        {
            if (--takeDepth > 0) return;
            takeDepth = 0; // a guard prefix may have skipped ours: never go negative
            var maskAfter = MaskLeft(out var equipped);
            var broke = thMaskBefore > 0 && maskAfter == 0;
            var d = Tap.Data(20);
            d["amount"] = thAmount;
            d["lifeblood"] = thBlueFlag;
            d["allow_mask_break"] = thAllowBreak;
            d["mask_left"] = maskAfter;
            d["mask_broke"] = broke;
            // The mask clamps a lethal hit to 1 HP whether or not it breaks (m0:C2).
            d["mask_saved"] = equipped && thMaskBefore > 0 && thBeforeH + thBeforeB - thAmount <= 0 && __instance.health > 0;
            Observe(__instance, "TakeHealth", true, d, broke);
        }

        private static void AddHealthPostfix(PlayerData __instance) => Observe(__instance, "AddHealth", true);
        private static void MaxHealthPostfix(PlayerData __instance) => Observe(__instance, "MaxHealth", true);
        private static void AddToMaxHealthPostfix(PlayerData __instance) => Observe(__instance, "AddToMaxHealth", true);

        private static void SetIntPostfix(PlayerData __instance, string intName)
        {
            if (IsHealthName(intName)) Observe(__instance, "SetInt", true);
        }

        private static void IntAddPostfix(PlayerData __instance, string intName)
        {
            if (IsHealthName(intName)) Observe(__instance, "IntAdd", true);
        }

        private static void IncrementIntPostfix(PlayerData __instance, string intName)
        {
            if (IsHealthName(intName)) Observe(__instance, "IncrementInt", true);
        }

        private static void DecrementIntPostfix(PlayerData __instance, string intName)
        {
            if (IsHealthName(intName)) Observe(__instance, "DecrementInt", true);
        }

        /// <summary>SetVariable&lt;T&gt; ends in OnUpdatedVariable; routed here by GateTap.</summary>
        public static void OnUpdatedVariable(PlayerData pd, string name)
        {
            if (IsHealthName(name)) Observe(pd, "SetVariable", true);
        }

        private static void HeroItemsApplyPostfix()
        {
            var gm = GameManager._instance;
            if (gm != null) Observe(gm.playerData, "HeroItemsState.Apply", true);
        }
    }

    /// <summary>
    /// What is hurting Hornet right now: set by the TakeDamage / special-damage prefixes and cleared by their
    /// postfixes, so a TakeHealth underneath can name its hazard and source without parsing the stack. A small
    /// stack because ApplyTagDamage(Frost) -> TakeFrostDamage -> DoSpecialDamage nests.
    /// </summary>
    internal static class DamageCtx
    {
        private struct Frame
        {
            public string Kind, Hazard, Source;
            public bool Reported;
        }

        private static readonly Frame[] Stack = new Frame[8];
        private static int depth;
        private static long pushedFrame = -1;

        public static int Depth => depth;

        public static void Push(string kind, string hazard, string source)
        {
            if (depth < Stack.Length) Stack[depth] = new Frame { Kind = kind, Hazard = hazard, Source = source };
            depth++;
            pushedFrame = Time.frameCount;
        }

        /// <summary>Returns whether a DoSpecialDamage event was reported inside this frame of the stack.</summary>
        public static bool Pop()
        {
            if (depth <= 0) return false;
            depth--;
            return depth < Stack.Length && Stack[depth].Reported;
        }

        /// <summary>Name of the outermost special-damage entry point, e.g. "TakeQuickDamage".</summary>
        public static string OuterKind => depth > 0 ? Stack[0].Kind : null;

        public static void MarkReported()
        {
            for (var i = 0; i < depth && i < Stack.Length; i++) Stack[i].Reported = true;
        }

        public static void Fill(Dictionary<string, object> d)
        {
            if (depth <= 0) return;
            var f = Stack[0];
            d["ctx"] = f.Kind;
            if (f.Hazard != null) d["hazard_type"] = f.Hazard;
            if (f.Source != null) d["source"] = f.Source;
        }

        /// <summary>Per frame: a context left open by an exception must not leak into the next frame.</summary>
        public static void ResetIfStale()
        {
            if (depth != 0 && pushedFrame != Time.frameCount) depth = 0;
        }
    }

    /// <summary>
    /// "damage" (HeroController.TakeDamage prefix), "special_damage" (every non-TakeDamage path that takes
    /// health, m0:N2), "die" (Die prefix, observe only), "hazard_death" (DieFromHazard) and "player_dead".
    /// </summary>
    internal static class DamageTap
    {
        public static void Install(Harmony h)
        {
            var hc = typeof(HeroController);
            Tap.Patch(h, hc, "TakeDamage", new[] { typeof(GameObject), typeof(CollisionSide), typeof(int), typeof(HazardType), typeof(DamagePropertyFlags) },
                typeof(DamageTap), nameof(TakeDamagePrefix), nameof(PopPostfix));
            Tap.Patch(h, hc, "TakeQuickDamage", new[] { typeof(int), typeof(bool), typeof(bool) }, typeof(DamageTap), nameof(QuickPrefix), nameof(EntryPostfix));
            Tap.Patch(h, hc, "TakeFrostDamage", new[] { typeof(int) }, typeof(DamageTap), nameof(FrostPrefix), nameof(EntryPostfix));
            Tap.Patch(h, hc, "TakeChompDamage", new System.Type[0], typeof(DamageTap), nameof(ChompPrefix), nameof(EntryPostfix));
            Tap.Patch(h, hc, "ApplyTagDamage", new[] { typeof(DamageTag.DamageTagInstance) }, typeof(DamageTap), nameof(TagPrefix), nameof(EntryPostfix));
            Tap.Patch(h, hc, "DoSpecialDamage", new[] { typeof(int), typeof(bool), typeof(string), typeof(bool), typeof(bool), typeof(bool), typeof(bool) },
                typeof(DamageTap), nameof(DoSpecialDamagePrefix));
            Tap.Patch(h, hc, "CriticalDamage", new System.Type[0], typeof(DamageTap), nameof(CriticalPrefix), nameof(PopPostfix));
            Tap.Patch(h, hc, "Die", new[] { typeof(bool), typeof(bool) }, typeof(DamageTap), nameof(DiePrefix));
            Tap.Patch(h, hc, "DieFromHazard", new[] { typeof(HazardType), typeof(float) }, typeof(DamageTap), nameof(DieFromHazardPrefix));
            Tap.Patch(h, typeof(GameManager), "PlayerDead", new[] { typeof(float) }, typeof(DamageTap), nameof(PlayerDeadPrefix));
        }

        /// <summary>PlayerData through GameManager, not the hero's cached copy (m0 §2.7).</summary>
        private static PlayerData Pd()
        {
            var gm = GameManager._instance;
            return gm != null ? gm.playerData : null;
        }

        private static string NameOf(GameObject go)
        {
            if (go == null) return null;
            var p = go.transform.parent;
            return p != null ? p.name + "/" + go.name : go.name;
        }

        private static void TakeDamagePrefix(HeroController __instance, GameObject go, CollisionSide damageSide, int damageAmount,
                                             HazardType hazardType, DamagePropertyFlags damagePropertyFlags)
        {
            var source = NameOf(go);
            DamageCtx.Push("damage", hazardType.ToString(), source);
            if (!Tap.Active) return;
            var pd = Pd();
            var d = Tap.Data(16);
            d["source"] = source;
            d["side"] = damageSide.ToString();
            d["amount"] = damageAmount;
            d["hazard"] = hazardType.ToString();
            d["flags"] = (int)damagePropertyFlags;
            d["flag_names"] = damagePropertyFlags.ToString();
            d["can_take"] = __instance.CanTakeDamage();
            d["invuln"] = __instance.cState.Invulnerable;
            d["parry_t"] = __instance.parryInvulnTimer;
            d["recoiling"] = __instance.cState.recoiling;
            if (pd != null)
            {
                d["h"] = pd.health;
                d["hb"] = pd.healthBlue;
            }
            Tap.Attribute(d, false);
            Tap.Emit("damage", d);
        }

        private static void PopPostfix() => DamageCtx.Pop();

        // Entry points only open a context; DoSpecialDamage reports (once), or EntryPostfix reports that the
        // entry never reached it (e.g. TakeQuickDamage cancelled right after a hazard respawn).
        private static void QuickPrefix() => DamageCtx.Push("special:TakeQuickDamage", null, Tap.FsmNow());
        private static void FrostPrefix() => DamageCtx.Push("special:TakeFrostDamage", null, Tap.FsmNow());
        private static void ChompPrefix() => DamageCtx.Push("special:TakeChompDamage", null, Tap.FsmNow());

        private static void TagPrefix(DamageTag.DamageTagInstance damageTagInstance)
        {
            DamageCtx.Push("special:ApplyTagDamage:" + damageTagInstance.specialDamageType, null, Tap.FsmNow());
        }

        private static void EntryPostfix()
        {
            var kind = DamageCtx.OuterKind;
            var reported = DamageCtx.Pop();
            if (reported || kind == null || DamageCtx.Depth > 0 || !Tap.Active) return;
            var d = Tap.Data(6);
            d["method"] = kind.Substring("special:".Length);
            d["reached_special"] = false;
            Tap.Attribute(d, true);
            Tap.Emit("special_damage", d);
        }

        private static void DoSpecialDamagePrefix(HeroController __instance, int damageAmount, bool playEffects, string damageEvent,
                                                  bool canDie, bool allowFracturedMaskBreak, bool justTakeHealth, bool isFrostDamage)
        {
            var outer = DamageCtx.OuterKind;
            DamageCtx.MarkReported();
            if (!Tap.Active) return;
            var pd = Pd();
            var d = Tap.Data(16);
            d["method"] = outer != null && outer.StartsWith("special:") ? outer.Substring("special:".Length) : "DoSpecialDamage";
            d["amount"] = damageAmount;
            d["event"] = damageEvent;
            d["can_die"] = canDie;
            d["allow_mask_break"] = allowFracturedMaskBreak;
            d["just_take_health"] = justTakeHealth;
            d["frost"] = isFrostDamage;
            d["transitioning"] = __instance.cState.transitioning;
            if (pd != null)
            {
                d["h"] = pd.health;
                d["hb"] = pd.healthBlue;
            }
            Tap.Attribute(d, true);
            Tap.Emit("special_damage", d);
        }

        private static void CriticalPrefix(HeroController __instance)
        {
            DamageCtx.Push("special:CriticalDamage", null, Tap.FsmNow());
            DamageCtx.MarkReported();
            if (!Tap.Active) return;
            var pd = Pd();
            var d = Tap.Data(8);
            d["method"] = "CriticalDamage";
            if (pd != null)
            {
                d["h"] = pd.health;
                d["hb"] = pd.healthBlue;
            }
            Tap.Attribute(d, true);
            Tap.Emit("special_damage", d);
        }

        private static void DiePrefix(HeroController __instance, bool nonLethal, bool frostDeath)
        {
            if (!Tap.Active) return;
            var gm = GameManager._instance;
            var pd = Pd();
            var d = Tap.Data(12);
            d["non_lethal"] = nonLethal;
            d["frost"] = frostDeath;
            d["dead_already"] = __instance.cState.dead;
            if (pd != null)
            {
                d["h"] = pd.health;
                d["pd_mode"] = pd.permadeathMode.ToString();
            }
            if (gm != null && gm.sm != null) d["memory"] = gm.IsMemoryScene();
            DamageCtx.Fill(d);
            Tap.Attribute(d, true);
            Tap.Emit("die", d);
        }

        private static void DieFromHazardPrefix(HeroController __instance, HazardType hazardType)
        {
            if (!Tap.Active) return;
            var d = Tap.Data(6);
            d["hazard"] = hazardType.ToString();
            var pd = Pd();
            if (pd != null) d["h"] = pd.health;
            DamageCtx.Fill(d);
            Tap.Emit("hazard_death", d);
        }

        private static void PlayerDeadPrefix(GameManager __instance, float waitTime)
        {
            if (!Tap.Active) return;
            var pd = Pd();
            var d = Tap.Data(6);
            d["wait"] = waitTime;
            if (pd != null)
            {
                d["h"] = pd.health;
                d["pd_mode"] = pd.permadeathMode.ToString();
            }
            Tap.Emit("player_dead", d);
        }
    }
}
