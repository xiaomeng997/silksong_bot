using System.Collections.Generic;
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
        private static readonly PdIdentity Identity = new PdIdentity();
        private static bool baselined;
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
            int h = pd.health, b = pd.healthBlue;
            if (!Identity.Same(pd) || !baselined)
            {
                baselined = true;
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
    /// "pd_mode": every change of PlayerData.permadeathMode (m0 §3.1 MVP hooks: LethalBlock's second net watches
    /// this write). HeroController.Die writes On -> Dead before its first yield (m0:N7), i.e. synchronously inside
    /// the TakeDamage / DoSpecialDamage / CheckDeathCatch call that started it, so those postfixes check it while
    /// their damage context is still open; the per-frame poll catches any other writer. Diffs against the last
    /// observed value, so each change is reported once; a different PlayerData instance only re-baselines.
    /// </summary>
    internal static class PdModeTap
    {
        private static readonly PdIdentity Identity = new PdIdentity();
        private static bool baselined;
        private static PermadeathModes last;

        /// <summary>Forget the baseline (brain reconnected): the next observation is silent.</summary>
        public static void Rebaseline() => baselined = false;

        public static void Observe(PlayerData pd, string src)
        {
            if (pd == null) return;
            var mode = pd.permadeathMode;
            if (!Identity.Same(pd) || !baselined)
            {
                baselined = true;
                last = mode;
                return;
            }
            if (mode == last) return;
            var from = last;
            last = mode;
            if (!Tap.Active) return;
            var d = Tap.Data(10);
            d["from"] = EnumName<PermadeathModes>.Of(from);
            d["to"] = EnumName<PermadeathModes>.Of(mode);
            d["src"] = src;
            var gm = GameManager._instance;
            if (gm != null) d["scene"] = gm.sceneName;
            d["h"] = pd.health;
            DamageCtx.Fill(d);
            Tap.Attribute(d, false);
            Tap.Emit("pd_mode", d);
        }
    }

    /// <summary>
    /// What is hurting Hornet right now: set by the TakeDamage / special-damage prefixes and cleared by their
    /// postfixes, so a TakeHealth underneath can name its hazard and source without parsing the stack. A small
    /// stack because ApplyTagDamage(Frost) -> TakeFrostDamage -> DoSpecialDamage nests. TakeDamage runs on every
    /// physics step of a contact, so its push stores the source object and the enum; names are only formatted
    /// when an event is actually emitted.
    /// </summary>
    internal static class DamageCtx
    {
        private struct Frame
        {
            public string Kind;
            public bool HasHazard;
            public HazardType Hazard;
            public GameObject SourceGo;
            public string Source;
            public bool Reported;
        }

        private static readonly Frame[] Stack = new Frame[8];
        private static int depth;
        private static long pushedFrame = -1;

        public static int Depth => depth;

        /// <summary>A special-damage entry point; <paramref name="source"/> is already a name (the executing FSM).</summary>
        public static void Push(string kind, string source)
        {
            if (depth < Stack.Length) Stack[depth] = new Frame { Kind = kind, Source = source };
            depth++;
            pushedFrame = Time.frameCount;
        }

        /// <summary>HeroController.TakeDamage: no string work here.</summary>
        public static void PushDamage(HazardType hazard, GameObject source)
        {
            if (depth < Stack.Length) Stack[depth] = new Frame { Kind = "damage", HasHazard = true, Hazard = hazard, SourceGo = source };
            depth++;
            pushedFrame = Time.frameCount;
        }

        /// <summary>Returns whether a DoSpecialDamage event was reported inside this frame of the stack.</summary>
        public static bool Pop()
        {
            if (depth <= 0) return false;
            depth--;
            if (depth >= Stack.Length) return false;
            var reported = Stack[depth].Reported;
            Stack[depth] = default; // do not keep the source object alive
            return reported;
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
            if (f.HasHazard) d["hazard_type"] = EnumName<HazardType>.Of(f.Hazard);
            var source = f.Source ?? DamageTap.NameOf(f.SourceGo);
            if (source != null) d["source"] = source;
        }

        /// <summary>Per frame: a context left open by an exception must not leak into the next frame.</summary>
        public static void ResetIfStale()
        {
            if (depth == 0 || pushedFrame == Time.frameCount) return;
            for (var i = 0; i < depth && i < Stack.Length; i++) Stack[i] = default;
            depth = 0;
        }
    }

    /// <summary>
    /// "damage" (HeroController.TakeDamage prefix), "damage_blocked" (collapsed no-op attempts, see
    /// <see cref="Blocked"/>), "special_damage" (every non-TakeDamage path that takes health, m0:N2), "die" (Die
    /// prefix, observe only), "death_catch" (CheckDeathCatch prefix), "hazard_death" (DieFromHazard) and
    /// "player_dead".
    /// </summary>
    internal static class DamageTap
    {
        private static readonly AccessTools.FieldRef<HeroController, double> LastHazardRespawnTime =
            AccessTools.FieldRefAccess<HeroController, double>("lastHazardRespawnTime");

        public static void Install(Harmony h)
        {
            var hc = typeof(HeroController);
            Tap.Patch(h, hc, "TakeDamage", new[] { typeof(GameObject), typeof(CollisionSide), typeof(int), typeof(HazardType), typeof(DamagePropertyFlags) },
                typeof(DamageTap), nameof(TakeDamagePrefix), nameof(TakeDamagePostfix));
            Tap.Patch(h, hc, "TakeQuickDamage", new[] { typeof(int), typeof(bool), typeof(bool) }, typeof(DamageTap), nameof(QuickPrefix), nameof(EntryPostfix));
            Tap.Patch(h, hc, "TakeFrostDamage", new[] { typeof(int) }, typeof(DamageTap), nameof(FrostPrefix), nameof(EntryPostfix));
            Tap.Patch(h, hc, "TakeChompDamage", new System.Type[0], typeof(DamageTap), nameof(ChompPrefix), nameof(EntryPostfix));
            Tap.Patch(h, hc, "ApplyTagDamage", new[] { typeof(DamageTag.DamageTagInstance) }, typeof(DamageTap), nameof(TagPrefix), nameof(EntryPostfix));
            Tap.Patch(h, hc, "DoSpecialDamage", new[] { typeof(int), typeof(bool), typeof(string), typeof(bool), typeof(bool), typeof(bool), typeof(bool) },
                typeof(DamageTap), nameof(DoSpecialDamagePrefix), nameof(DoSpecialDamagePostfix));
            Tap.Patch(h, hc, "CriticalDamage", new System.Type[0], typeof(DamageTap), nameof(CriticalPrefix), nameof(PopPostfix));
            Tap.Patch(h, hc, "Die", new[] { typeof(bool), typeof(bool) }, typeof(DamageTap), nameof(DiePrefix));
            Tap.Patch(h, hc, "CheckDeathCatch", new System.Type[0], typeof(DamageTap), nameof(CheckDeathCatchPrefix), nameof(CheckDeathCatchPostfix));
            Tap.Patch(h, hc, "DieFromHazard", new[] { typeof(HazardType), typeof(float) }, typeof(DamageTap), nameof(DieFromHazardPrefix));
            Tap.Patch(h, typeof(GameManager), "PlayerDead", new[] { typeof(float) }, typeof(DamageTap), nameof(PlayerDeadPrefix));
        }

        /// <summary>PlayerData through GameManager, not the hero's cached copy (m0 §2.7).</summary>
        private static PlayerData Pd()
        {
            var gm = GameManager._instance;
            return gm != null ? gm.playerData : null;
        }

        public static string NameOf(GameObject go)
        {
            if (go == null) return null;
            var p = go.transform.parent;
            return p != null ? p.name + "/" + go.name : go.name;
        }

        // ---- TakeDamage -----------------------------------------------------------------------------------

        /// <summary>
        /// Why an attempt is a no-op, or null if it gets past the gates. Mirrors the returns at the top of
        /// HeroController.TakeDamage (1.0.30000 HeroController.cs:5282-5372), in order: Self damage while an
        /// interactable blocks; amount &lt;= 0 (only a DamageHero "damaged" callback runs); then the i-frame gate. The
        /// branch between the last two (a hazard within 0.5 s of a hazard respawn respawns again) is not a no-op.
        /// HeroBox calls TakeDamage on every physics step of a contact, so most attempts during i-frames end here.
        /// </summary>
        private static string Blocked(HeroController hc, int amount, HazardType hazard, DamagePropertyFlags flags, out bool reRespawn)
        {
            reRespawn = false;
            if ((flags & DamagePropertyFlags.Self) != 0 && InteractManager.BlockingInteractable != null) return "interact";
            if (amount <= 0) return "zero";
            var cs = hc.cState;
            if (!cs.hazardDeath && hazard != HazardType.ENEMY && hazard != HazardType.NON_HAZARD && hazard != HazardType.EXPLOSION &&
                Time.timeAsDouble - LastHazardRespawnTime(hc) <= 0.5)
            {
                reRespawn = true;
                return null;
            }
            if (hazard == HazardType.SINK || hc.CanTakeDamage()) return null;
            var pd = Pd();
            var blocked = (!cs.Invulnerable && !(hc.parryInvulnTimer > 0f)) || cs.hazardDeath || (pd != null && pd.isInvincible) ||
                          CheatManager.Invincibility == CheatManager.InvincibilityStates.FullInvincible ||
                          hazard == HazardType.ENEMY || hazard == HazardType.NON_HAZARD || hazard == HazardType.EXPLOSION ||
                          HeroInvincibilitySource.IsActive;
            return blocked ? "iframes" : null;
        }

        private static void TakeDamagePrefix(HeroController __instance, GameObject go, CollisionSide damageSide, int damageAmount,
                                             HazardType hazardType, DamagePropertyFlags damagePropertyFlags)
        {
            DamageCtx.PushDamage(hazardType, go);
            if (!Tap.Active) return;
            var why = Blocked(__instance, damageAmount, hazardType, damagePropertyFlags, out var reRespawn);
            if (why != null)
            {
                BlockedHits.Add(go, hazardType, damageAmount, damageSide, damagePropertyFlags, why);
                return;
            }
            // This attempt gets through: first report the blocked ones before it, so the order stays readable.
            BlockedHits.FlushAll("hit");
            var pd = Pd();
            var d = Tap.Data(18);
            d["source"] = NameOf(go);
            d["side"] = EnumName<CollisionSide>.Of(damageSide);
            d["amount"] = damageAmount;
            d["hazard"] = EnumName<HazardType>.Of(hazardType);
            d["flags"] = (int)damagePropertyFlags;
            d["flag_names"] = EnumName<DamagePropertyFlags>.Of(damagePropertyFlags);
            d["can_take"] = __instance.CanTakeDamage();
            d["invuln"] = __instance.cState.Invulnerable;
            d["parry_t"] = __instance.parryInvulnTimer;
            d["recoiling"] = __instance.cState.recoiling;
            if (reRespawn) d["re_respawn"] = true;
            if (pd != null)
            {
                d["h"] = pd.health;
                d["hb"] = pd.healthBlue;
            }
            Tap.Attribute(d, false);
            Tap.Emit("damage", d);
        }

        private static void TakeDamagePostfix()
        {
            // Die (started inside TakeDamage) writes permadeathMode before its first yield (m0:N7).
            PdModeTap.Observe(Pd(), "TakeDamage");
            DamageCtx.Pop();
        }

        /// <summary>Per frame (EventsRunner.LateUpdate): report contacts whose blocked attempts have stopped.</summary>
        public static void PollBlocked() => BlockedHits.Poll();

        /// <summary>Brain (re)connected: blocked attempts from before are not reported.</summary>
        public static void ResetBlocked() => BlockedHits.Clear();

        /// <summary>
        /// Blocked TakeDamage attempts collapsed per (source object, hazard, reason) into one "damage_blocked"
        /// event {source, hazard, why, n, amount (largest), side, flags, first_f, last_f, end}. A group ends
        /// ("ended") when a physics step passes without an attempt from it (contact over, or the hero stopped
        /// being hit), when an attempt gets through ("hit": i-frames over), or when the table is full ("full").
        /// </summary>
        private static class BlockedHits
        {
            private struct Group
            {
                public int GoId;
                public HazardType Hazard;
                public string Why, Name;
                public CollisionSide Side;
                public DamagePropertyFlags Flags;
                public int Count, MaxAmount;
                public long FirstFrame, LastFrame;
                public double LastFixed;
            }

            private static readonly Group[] Groups = new Group[8];
            private static int count;

            public static void Add(GameObject go, HazardType hazard, int amount, CollisionSide side, DamagePropertyFlags flags, string why)
            {
                var id = go != null ? go.GetInstanceID() : 0;
                var frame = Time.frameCount;
                var fixedTime = Time.fixedTimeAsDouble;
                for (var i = 0; i < count; i++)
                {
                    ref var g = ref Groups[i];
                    if (g.GoId != id || g.Hazard != hazard || g.Why != why) continue;
                    g.Count++;
                    if (amount > g.MaxAmount) g.MaxAmount = amount;
                    g.LastFrame = frame;
                    g.LastFixed = fixedTime;
                    return;
                }
                if (count == Groups.Length) Flush(0, "full");
                Groups[count++] = new Group
                {
                    GoId = id, Hazard = hazard, Why = why, Name = NameOf(go), Side = side, Flags = flags, Count = 1, MaxAmount = amount,
                    FirstFrame = frame, LastFrame = frame, LastFixed = fixedTime,
                };
            }

            public static void Poll()
            {
                if (count == 0) return;
                // Time.fixedTimeAsDouble is the start of the latest physics step: a group whose last attempt is
                // older got no attempt in that step. No step (pause, freeze at timeScale 0) keeps groups open.
                var fixedTime = Time.fixedTimeAsDouble;
                for (var i = count - 1; i >= 0; i--)
                    if (fixedTime > Groups[i].LastFixed) Flush(i, "ended");
            }

            public static void FlushAll(string end)
            {
                while (count > 0) Flush(0, end);
            }

            public static void Clear()
            {
                for (var i = 0; i < count; i++) Groups[i] = default;
                count = 0;
            }

            private static void Flush(int i, string end)
            {
                var g = Groups[i];
                for (var j = i + 1; j < count; j++) Groups[j - 1] = Groups[j];
                Groups[--count] = default;
                if (!Tap.Active) return;
                var d = Tap.Data(12);
                d["source"] = g.Name;
                d["hazard"] = EnumName<HazardType>.Of(g.Hazard);
                d["why"] = g.Why;
                d["n"] = g.Count;
                d["amount"] = g.MaxAmount;
                d["side"] = EnumName<CollisionSide>.Of(g.Side);
                d["flags"] = (int)g.Flags;
                d["first_f"] = g.FirstFrame;
                d["last_f"] = g.LastFrame;
                d["end"] = end;
                Tap.Emit("damage_blocked", d);
            }
        }

        // ---- special damage -------------------------------------------------------------------------------

        private static void PopPostfix() => DamageCtx.Pop();

        // Entry points only open a context; DoSpecialDamage reports (once), or EntryPostfix reports that the
        // entry never reached it (e.g. TakeQuickDamage cancelled right after a hazard respawn).
        private static void QuickPrefix() => DamageCtx.Push("special:TakeQuickDamage", ExecutingFsm());
        private static void FrostPrefix() => DamageCtx.Push("special:TakeFrostDamage", ExecutingFsm());
        private static void ChompPrefix() => DamageCtx.Push("special:TakeChompDamage", ExecutingFsm());

        private static readonly Dictionary<DamageTag.SpecialDamageTypes, string> TagKinds = new Dictionary<DamageTag.SpecialDamageTypes, string>();

        private static void TagPrefix(DamageTag.DamageTagInstance damageTagInstance)
        {
            var type = damageTagInstance.specialDamageType;
            if (!TagKinds.TryGetValue(type, out var kind)) TagKinds[type] = kind = "special:ApplyTagDamage:" + type;
            DamageCtx.Push(kind, ExecutingFsm());
        }

        /// <summary>The executing FSM as a context source; nothing to format while no brain would see it.</summary>
        private static string ExecutingFsm() => Tap.Active ? Tap.FsmNow() : null;

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

        private static void DoSpecialDamagePostfix() => PdModeTap.Observe(Pd(), "DoSpecialDamage");

        private static void CriticalPrefix(HeroController __instance)
        {
            DamageCtx.Push("special:CriticalDamage", ExecutingFsm());
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

        // ---- death ----------------------------------------------------------------------------------------

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
                d["pd_mode"] = EnumName<PermadeathModes>.Of(pd.permadeathMode);
            }
            if (gm != null && gm.sm != null) d["memory"] = gm.IsMemoryScene();
            DamageCtx.Fill(d);
            Tap.Attribute(d, true);
            Tap.Emit("die", d);
        }

        /// <summary>
        /// CheckDeathCatch (only from DamageHeroDirectly(V2) with no damager, m0:C4) starts Die when health is
        /// already 0 and Hornet is not dead: "catch" says whether this call will.
        /// </summary>
        private static void CheckDeathCatchPrefix(HeroController __instance)
        {
            if (!Tap.Active) return;
            var pd = Pd();
            var d = Tap.Data(10);
            var dead = __instance.cState.dead;
            d["dead"] = dead;
            if (pd != null)
            {
                d["h"] = pd.health;
                d["hb"] = pd.healthBlue;
                d["catch"] = !dead && pd.health <= 0;
                d["pd_mode"] = EnumName<PermadeathModes>.Of(pd.permadeathMode);
            }
            DamageCtx.Fill(d);
            Tap.Attribute(d, true);
            Tap.Emit("death_catch", d);
        }

        private static void CheckDeathCatchPostfix() => PdModeTap.Observe(Pd(), "CheckDeathCatch");

        private static void DieFromHazardPrefix(HeroController __instance, HazardType hazardType)
        {
            if (!Tap.Active) return;
            var d = Tap.Data(6);
            d["hazard"] = EnumName<HazardType>.Of(hazardType);
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
                d["pd_mode"] = EnumName<PermadeathModes>.Of(pd.permadeathMode);
            }
            Tap.Emit("player_dead", d);
        }
    }
}
