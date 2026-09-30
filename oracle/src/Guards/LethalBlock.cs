using System;
using System.Collections;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using GlobalEnums;
using GlobalSettings;
using HarmonyLib;
using UnityEngine;

namespace SsOracle.Guards
{
    /// <summary>
    /// LethalBlock, two nets (DESIGN §3.1.1 Guards; m0:C2, m0 §2.5). Every C# decrease of health goes through
    /// PlayerData.TakeHealth, and Die has exactly three callers (TakeDamage, DoSpecialDamage, CheckDeathCatch), so:
    /// <list type="bullet">
    /// <item>Net 1, PlayerData.TakeHealth prefix: replays 1.0.30000's TakeHealth on copies of its inputs (blue health
    /// absorbs first and overflows recursively; the Fractured Mask saves when equipped and AmountLeft &gt; 0, clamping
    /// to 1 HP, and is consumed only when allowFracturedMaskBreak). Only when the replay ends at 0 HP is the call
    /// cancelled (health left as it was, raised to 1 if already 0) and a "catastrophe" emitted; a mask that should
    /// break is left to break, and under the PreventDeath cheat (vanilla ends at 1 HP) the hit is recorded, not
    /// cancelled. This also covers the paths that never enter TakeDamage (TakeQuickDamage can leave 0 HP without dying,
    /// frost, chomp, tags, critical). After a cancelled TakeDamage hit the rest of TakeDamage runs as for any
    /// non-lethal hit (recoil and i-frames, or a hazard respawn for spikes/lava), so Hornet is left in a normal state.</item>
    /// <item>Net 2, HeroController.Die prefix: Die is an iterator whose body runs synchronously up to its first yield
    /// inside StartCoroutine, and that body already writes disablePause and permadeathMode = Dead (m0:N7). Returning
    /// false from a prefix on the iterator method itself means the state machine is never created; StartCoroutine
    /// gets an empty routine instead. Emits "would_die" and leaves Hornet at &gt;= 1 HP.</item>
    /// <item>Watchers: GameManager.PlayerDead (reached only if Die ran, i.e. net 2 missed), a per-frame
    /// permadeathMode On -&gt; Dead comparison, and "0 HP while alive" (a death that is only postponed, m0 §2.5).</item>
    /// </list>
    /// Prefixes on the damage entry points only record the cause chain for attribution. CheatManager.PreventDeath is
    /// not a substitute (it hides DoSpecialDamage and CriticalDamage completely, m0:N43).
    /// </summary>
    internal static class LethalBlock
    {
        /// <summary>Result of replaying PlayerData.TakeHealth on copies of its inputs.</summary>
        internal struct Outcome
        {
            public int Health, Blue, MaskLeft;
            /// <summary>Vanilla takes the "health - amount &lt;= 0" branch: health becomes 0 (1 under the PreventDeath cheat).</summary>
            public bool ReachesZero;
            /// <summary>The Fractured Mask clamp to 1 HP fired.</summary>
            public bool MaskSaved;
            /// <summary>... and the mask was consumed (AmountLeft = 0).</summary>
            public bool MaskConsumed;
        }

        /// <summary>
        /// Pure replay of PlayerData.TakeHealth (1.0.30000, PlayerData.cs:3605-3655), statement by statement,
        /// including the CurrentMaxHealth fix-up and the recursive blue-health overflow.
        /// </summary>
        public static Outcome Simulate(int health, int maxHealth, int currentMaxHealth, int blue, bool maskEquipped,
            int maskLeft, int amount, bool allowFracturedMaskBreak, bool preventDeath)
        {
            var o = new Outcome { Health = health, Blue = blue, MaskLeft = maskLeft };
            Step(ref o, maxHealth, currentMaxHealth, maskEquipped, amount, allowFracturedMaskBreak, preventDeath);
            return o;
        }

        private static void Step(ref Outcome o, int maxHealth, int currentMaxHealth, bool maskEquipped, int amount,
            bool allowBreak, bool preventDeath)
        {
            if (amount > 0 && o.Health == maxHealth && o.Health != currentMaxHealth)
                o.Health = currentMaxHealth;
            if (o.Blue > 0)
            {
                var overflow = amount - o.Blue;
                o.Blue -= amount;
                if (o.Blue < 0) o.Blue = 0;
                if (overflow > 0)
                    Step(ref o, maxHealth, currentMaxHealth, maskEquipped, overflow, allowBreak, preventDeath);
                return;
            }
            if (o.Health - amount <= 0 && maskEquipped && o.MaskLeft > 0)
            {
                if (allowBreak)
                {
                    o.MaskLeft = 0;
                    o.MaskConsumed = true;
                }
                amount = o.Health - 1;
                o.MaskSaved = true;
            }
            if (o.Health - amount <= 0)
            {
                o.ReachesZero = true;
                o.Health = preventDeath ? 1 : 0;
            }
            else
            {
                o.Health -= amount;
            }
        }

        public static void Install(Harmony harmony)
        {
            var hc = typeof(HeroController);
            var me = typeof(LethalBlock);

            // Priority.Last: see the amount after other mods' prefixes (DebugMod's TakeHealthHook zeroes it for
            // infinite HP or when it loads a savestate on death).
            var net1 = Patching.Apply(harmony,
                AccessTools.Method(typeof(PlayerData), nameof(PlayerData.TakeHealth), new[] { typeof(int), typeof(bool), typeof(bool) }),
                "PlayerData.TakeHealth", me, nameof(TakeHealthPrefix), nameof(TakeHealthPostfix), Priority.Last);
            var net2 = Patching.Apply(harmony, AccessTools.Method(hc, "Die", new[] { typeof(bool), typeof(bool) }),
                "HeroController.Die", me, nameof(DiePrefix), priority: Priority.First);
            Patching.Apply(harmony, AccessTools.Method(typeof(GameManager), nameof(GameManager.PlayerDead), new[] { typeof(float) }),
                "GameManager.PlayerDead", me, nameof(PlayerDeadPrefix), priority: Priority.First);

            // Cause attribution only: which entry point is on the stack when a net fires.
            var pop = nameof(PopPostfix);
            Patching.Apply(harmony, AccessTools.Method(hc, nameof(HeroController.TakeDamage),
                    new[] { typeof(GameObject), typeof(CollisionSide), typeof(int), typeof(HazardType), typeof(DamagePropertyFlags) }),
                "HeroController.TakeDamage", me, nameof(TakeDamagePrefix), pop);
            Patching.Apply(harmony, AccessTools.Method(hc, "DoSpecialDamage",
                    new[] { typeof(int), typeof(bool), typeof(string), typeof(bool), typeof(bool), typeof(bool), typeof(bool) }),
                "HeroController.DoSpecialDamage", me, nameof(SpecialPrefix), pop);
            Patching.Apply(harmony, AccessTools.Method(hc, nameof(HeroController.TakeQuickDamage), new[] { typeof(int), typeof(bool), typeof(bool) }),
                "HeroController.TakeQuickDamage(int,bool,bool)", me, nameof(QuickPrefix), pop);
            Patching.Apply(harmony, AccessTools.Method(hc, nameof(HeroController.TakeFrostDamage), new[] { typeof(int) }),
                "HeroController.TakeFrostDamage", me, nameof(FrostPrefix), pop);
            Patching.Apply(harmony, AccessTools.Method(hc, nameof(HeroController.TakeChompDamage), Type.EmptyTypes),
                "HeroController.TakeChompDamage", me, nameof(ChompPrefix), pop);
            Patching.Apply(harmony, AccessTools.Method(hc, nameof(HeroController.ApplyTagDamage), new[] { typeof(DamageTag.DamageTagInstance) }),
                "HeroController.ApplyTagDamage", me, nameof(TagPrefix), pop);
            Patching.Apply(harmony, AccessTools.Method(hc, nameof(HeroController.CriticalDamage), Type.EmptyTypes),
                "HeroController.CriticalDamage", me, nameof(CriticalPrefix), pop);
            Patching.Apply(harmony, AccessTools.Method(hc, nameof(HeroController.TakeHealth), new[] { typeof(int) }),
                "HeroController.TakeHealth", me, nameof(HeroTakeHealthPrefix), pop);
            Patching.Apply(harmony, AccessTools.Method(hc, nameof(HeroController.CheckDeathCatch), Type.EmptyTypes),
                "HeroController.CheckDeathCatch", me, nameof(DeathCatchPrefix), pop);

            GuardState.LethalHealthy = net1 && net2;
            if (!net1) GuardState.Refuse("lethal_block net 1 (PlayerData.TakeHealth) is not patched");
            if (!net2) GuardState.Refuse("lethal_block net 2 (HeroController.Die) is not patched");

            Ipc.Rpc.Register("lethal.simulate", SimulateRpc);
        }

        // ---- cause chain -----------------------------------------------------------------------------------

        private struct Cause
        {
            public string Kind;
            public int Amount;
            public int Hazard;   // HazardType, -1 = n/a (kept as int: no ToString allocation per hit)
            public int Flags;    // DamagePropertyFlags
            public GameObject Src;
        }

        private static readonly Cause[] Causes = new Cause[16];
        private static int causeDepth;
        private static int takeHealthDepth;

        private static void Push(string kind, int amount, int hazard = -1, int flags = 0, GameObject src = null)
        {
            if (causeDepth < Causes.Length)
                Causes[causeDepth] = new Cause { Kind = kind, Amount = amount, Hazard = hazard, Flags = flags, Src = src };
            causeDepth++;
        }

        private static void PopPostfix()
        {
            if (causeDepth <= 0) return;
            causeDepth--;
            if (causeDepth < Causes.Length) Causes[causeDepth] = default;
        }

        private static void TakeDamagePrefix(GameObject go, int damageAmount, HazardType hazardType, DamagePropertyFlags damagePropertyFlags) =>
            Push("damage", damageAmount, (int)hazardType, (int)damagePropertyFlags, go);

        private static void SpecialPrefix(int damageAmount) => Push("special", damageAmount);
        private static void QuickPrefix(int damageAmount) => Push("quick", damageAmount);
        private static void FrostPrefix(int damageAmount) => Push("frost", damageAmount);
        private static void ChompPrefix() => Push("chomp", 1);
        private static void TagPrefix(DamageTag.DamageTagInstance damageTagInstance) =>
            Push("tag", damageTagInstance.amount, -1, (int)damageTagInstance.specialDamageType);
        private static void CriticalPrefix() => Push("critical", 0);
        private static void HeroTakeHealthPrefix(int amount) => Push("hero_take_health", amount);
        private static void DeathCatchPrefix() => Push("death_catch", 0);

        /// <summary>Called once per frame: nothing legitimately stays on the damage stack across frames, so an
        /// exception inside a patched method can never leave stale attribution behind.</summary>
        private static void ResetFrameState()
        {
            if (causeDepth != 0)
            {
                for (var i = 0; i < Causes.Length; i++) Causes[i] = default;
                causeDepth = 0;
            }
            takeHealthDepth = 0;
        }

        // ---- net 1 -----------------------------------------------------------------------------------------

        private static bool TakeHealthPrefix(PlayerData __instance, int amount, bool hasBlueHealth, bool allowFracturedMaskBreak)
        {
            // The blue-health overflow recurses into TakeHealth; the outer call already judged the whole hit.
            if (takeHealthDepth++ > 0) return true;
            var mode = GuardState.Lethal;
            if (mode == LethalMode.Off) return true;

            var pd = __instance;
            var preventDeath = CheatManager.Invincibility == CheatManager.InvincibilityStates.PreventDeath;
            var cur = pd.CurrentMaxHealth;
            // Vanilla reads the mask only when the hit would reach 0 HP; do the same (reading it fills tool caches).
            var o = Simulate(pd.health, pd.maxHealth, cur, pd.healthBlue, false, 0, amount, allowFracturedMaskBreak, preventDeath);
            if (!o.ReachesZero) return true;
            ReadMask(out var maskEq, out var maskLeft);
            o = Simulate(pd.health, pd.maxHealth, cur, pd.healthBlue, maskEq, maskLeft, amount, allowFracturedMaskBreak, preventDeath);
            if (!o.ReachesZero) return true;

            // Under the PreventDeath cheat vanilla itself ends at 1 HP, not 0: record the lethal hit, never cancel it
            // (cancelling would leave more HP than vanilla). The cheat is TRAIN-only and never replaces this guard.
            var block = mode == LethalMode.Block && o.Health <= 0;
            var d = Describe("take_health", pd);
            d["amount"] = amount;
            d["lifeblood"] = hasBlueHealth;
            d["allow_mask_break"] = allowFracturedMaskBreak;
            d["mask_eq"] = maskEq;
            d["mask_left"] = maskLeft;
            d["prevent_death_cheat"] = preventDeath;
            d["net"] = 1;
            if (block && RestoreHealth(pd, null)) d["hp_restored"] = true;
            Report("catastrophe", d, block);
            return !block;
        }

        /// <summary>
        /// Leaves Hornet at &gt;= 1 HP after a veto (a hit can find her at 0 HP after a TakeQuickDamage or an FSM write).
        /// Writes GameManager's PlayerData and, if it is a different object, the hero's cached copy, which is the one
        /// TakeDamage/DoSpecialDamage test for 0 right after TakeHealth. Never touches disablePause (m0:N43).
        /// </summary>
        private static bool RestoreHealth(PlayerData pd, HeroController hero)
        {
            var restored = false;
            if (pd != null && pd.health < 1) { pd.health = 1; restored = true; }
            var cached = hero != null ? hero.playerData : null;
            if (cached != null && !ReferenceEquals(cached, pd) && cached.health < 1) { cached.health = 1; restored = true; }
            return restored;
        }

        private static void TakeHealthPostfix()
        {
            if (takeHealthDepth > 0) takeHealthDepth--;
        }

        // ---- net 2 -----------------------------------------------------------------------------------------

        private static int lastDieReportFrame = -1000;

        private static bool DiePrefix(HeroController __instance, bool nonLethal, bool frostDeath, ref IEnumerator __result)
        {
            var mode = GuardState.Lethal;
            if (mode == LethalMode.Off) return true;
            var gm = GameManager._instance;
            var pd = gm != null ? gm.playerData : null;
            var block = mode == LethalMode.Block;

            var d = Describe("die", pd);
            d["net"] = 2;
            d["nonlethal"] = nonLethal;
            d["frost"] = frostDeath;
            d["already_dead"] = __instance.cState.dead;
            d["memory"] = gm != null && gm.sm != null && gm.IsMemoryScene();
            if (block && RestoreHealth(pd, __instance)) d["hp_restored"] = true;
            lastDieReportFrame = Time.frameCount;
            Report("would_die", d, block);
            if (!block) return true;
            __result = new NoOpRoutine();
            return false;
        }

        private static bool PlayerDeadPrefix(GameManager __instance, float waitTime, ref IEnumerator __result)
        {
            var mode = GuardState.Lethal;
            if (mode == LethalMode.Off) return true;
            var pd = __instance.playerData;
            var block = mode == LethalMode.Block;
            // Die starts PlayerDead one frame after its own (already reported) would_die. Without that report, net 2 missed.
            var missed = Time.frameCount - lastDieReportFrame > 30;
            if (!missed && !block)
            {
                Export.FrameExporter.Emit("player_dead", new Dictionary<string, object>
                {
                    ["pd_mode"] = pd != null ? pd.permadeathMode.ToString() : null,
                    ["wait"] = waitTime,
                });
                return true;
            }
            var d = Describe("player_dead", pd);
            d["net"] = 2;
            d["missed_die"] = missed;
            Report("would_die", d, block);
            if (!block) return true;
            Core.Plugin.Log.LogError("GameManager.PlayerDead reached while LethalBlock blocks: HeroController.Die was not stopped. " +
                                     "Skipped the death save; the hero stays dead until a savestate load or slot.restore.");
            __result = new NoOpRoutine();
            return false;
        }

        /// <summary>What StartCoroutine receives instead of a blocked Die/PlayerDead state machine.</summary>
        private sealed class NoOpRoutine : IEnumerator
        {
            public object Current => null;
            public bool MoveNext() => false;
            public void Reset() { }
        }

        // ---- per-frame watchers ------------------------------------------------------------------------------

        private static int lastPdId;
        private static PermadeathModes lastPdMode;
        private static bool zeroSeen, deadSeen;
        private static int maskRefreshFrame;

        /// <summary>Main thread, once per frame (GuardsMonitor.LateUpdate). A handful of field reads.</summary>
        internal static void Tick(GameManager gm, PlayerData pd, HeroController hero)
        {
            ResetFrameState();
            if (gm == null || pd == null)
            {
                lastPdId = 0;
                zeroSeen = deadSeen = false;
                maskKnown = false;
                return;
            }

            // PlayerData is replaced on Save & Quit (m0:N42); compare modes only within one instance.
            var id = RuntimeHelpers.GetHashCode(pd);
            var pdMode = pd.permadeathMode;
            if (id == lastPdId && lastPdMode == PermadeathModes.On && pdMode == PermadeathModes.Dead)
                OnPermadeathDead(pd);
            lastPdId = id;
            lastPdMode = pdMode;

            if (hero == null)
            {
                zeroSeen = deadSeen = false;
                maskKnown = false;
                return;
            }
            var dead = hero.cState.dead;
            if (dead != deadSeen)
            {
                deadSeen = dead;
                if (dead)
                    Export.FrameExporter.Emit("hero_dead", new Dictionary<string, object> { ["hp"] = pd.health, ["pd_mode"] = pdMode.ToString() });
            }
            if (!dead && pd.health <= 0 && gm.GameState == GameState.PLAYING && GuardState.Lethal != LethalMode.Off)
            {
                var block = GuardState.Lethal == LethalMode.Block;
                if (!zeroSeen)
                {
                    zeroSeen = true;
                    var d = Describe("health_zero_observed", pd);
                    d["net"] = "monitor";
                    if (block) d["hp_restored"] = true;
                    Report("catastrophe", d, block, withStack: false);
                }
                if (block) pd.health = 1;
            }
            else if (pd.health > 0)
            {
                zeroSeen = false;
            }

            if (Time.frameCount - maskRefreshFrame >= 30)
                RefreshMask();
        }

        private static void OnPermadeathDead(PlayerData pd)
        {
            Core.Plugin.Log.LogError("permadeathMode went On -> Dead in memory (Steel Soul death). Any later save writes a DEFEATED slot.");
            Export.FrameExporter.Emit("permadeath_dead", new Dictionary<string, object> { ["hp"] = pd.health });
            if (GuardState.Lethal != LethalMode.Off && Time.frameCount - lastDieReportFrame > 30)
            {
                var d = Describe("permadeath_dead", pd);
                d["net"] = "monitor";
                d["missed_die"] = true;
                Report("would_die", d, false, withStack: false);
            }
        }

        // ---- reporting -----------------------------------------------------------------------------------------

        /// <summary>Common event payload: outermost cause, the full chain, and the live health state.</summary>
        private static Dictionary<string, object> Describe(string fallbackCause, PlayerData pd)
        {
            var d = new Dictionary<string, object>();
            var n = Math.Min(causeDepth, Causes.Length);
            if (n > 0)
            {
                var c = Causes[0];
                d["cause"] = c.Kind;
                var path = c.Kind;
                for (var i = 1; i < n; i++) path += ">" + Causes[i].Kind;
                d["path"] = path;
                d["dmg"] = c.Amount;
                if (c.Hazard >= 0) d["hazard"] = ((HazardType)c.Hazard).ToString();
                if (c.Flags != 0) d["flags"] = c.Flags;
                if (c.Src != null) d["src"] = c.Src.name;
            }
            else
            {
                d["cause"] = fallbackCause;
            }
            if (pd != null)
            {
                d["hp"] = pd.health;
                d["blue"] = pd.healthBlue;
                d["max"] = pd.maxHealth;
                d["pd_mode"] = pd.permadeathMode.ToString();
            }
            var gm = GameManager._instance;
            if (gm != null) d["scene"] = gm.sceneName;
            return d;
        }

        private static void Report(string kind, Dictionary<string, object> d, bool blocked, bool withStack = true)
        {
            d["mode"] = GuardState.LethalName(GuardState.Lethal);
            d["blocked"] = blocked;
            if (withStack) d["stack"] = Patching.Stack();
            if (kind == "catastrophe")
            {
                GuardState.Catastrophes++;
                GuardState.LastCatastrophe = d;
            }
            else
            {
                GuardState.WouldDie++;
                GuardState.LastWouldDie = d;
            }
            Export.FrameExporter.Emit(kind, d);
            d.TryGetValue("path", out var path);
            Core.Plugin.Log.LogWarning($"LethalBlock {kind} ({(blocked ? "BLOCKED" : "observed")}) at frame {Time.frameCount}: " +
                                       $"cause={d["cause"]} path={path} hp={(d.TryGetValue("hp", out var hp) ? hp : "?")}");
        }

        // ---- Fractured Mask state ---------------------------------------------------------------------------------

        private static bool maskKnown, maskEq;
        private static int maskLeft, maskFrame;

        /// <summary>Exactly the expression vanilla evaluates in TakeHealth (fills the same tool caches).</summary>
        private static void ReadMask(out bool eq, out int left)
        {
            var tool = Gameplay.FracturedMaskTool;
            eq = tool && tool.IsEquipped;
            left = eq ? tool.SavedData.AmountLeft : 0;
            maskKnown = true;
            maskEq = eq;
            maskLeft = left;
            maskFrame = Time.frameCount;
        }

        /// <summary>
        /// Low-rate refresh for the "guards" STATE section. Guarded so it never takes the lookup paths that search
        /// the scene (ManagerSingleton.Instance = FindAnyObjectByType when unset) or create a PlayerData.
        /// </summary>
        internal static void RefreshMask()
        {
            maskRefreshFrame = Time.frameCount;
            if (!PlayerData.HasInstance || ManagerSingleton<ToolItemManager>.UnsafeInstance == null)
            {
                maskKnown = false;
                return;
            }
            try
            {
                ReadMask(out _, out _);
            }
            catch (Exception e)
            {
                maskKnown = false;
                Core.Plugin.Log.LogWarning("Fractured Mask read failed: " + e.Message);
            }
        }

        /// <summary>Writes [equipped, amount_left] or nil (STATE "guards".mask).</summary>
        internal static void WriteMask(Ipc.MsgPackWriter w)
        {
            if (!maskKnown) { w.Nil(); return; }
            w.ArrayHeader(2);
            w.Bool(maskEq);
            w.Int(maskLeft);
        }

        internal static Dictionary<string, object> MaskInfo() => new Dictionary<string, object>
        {
            ["known"] = maskKnown,
            ["equipped"] = maskEq,
            ["amount_left"] = maskLeft,
            ["frame"] = maskFrame,
        };

        // ---- RPC -------------------------------------------------------------------------------------------------

        /// <summary>
        /// lethal.simulate {amount, allow_mask_break=true, lifeblood=false}: replay TakeHealth against the live state
        /// without applying it, so probes know which branch (blue, mask save, mask consumed, 0 HP) a hit will take.
        /// </summary>
        private static object SimulateRpc(Dictionary<string, object> args)
        {
            var gm = GameManager._instance;
            var pd = gm != null ? gm.playerData : null;
            if (pd == null || HeroController.UnsafeInstance == null) throw new InvalidOperationException("no hero");
            var amount = (int)Ipc.Rpc.Long(args, "amount", 1);
            var allow = Ipc.Rpc.Bool(args, "allow_mask_break", true);
            ReadMask(out var eq, out var left);
            var preventDeath = CheatManager.Invincibility == CheatManager.InvincibilityStates.PreventDeath;
            var o = Simulate(pd.health, pd.maxHealth, pd.CurrentMaxHealth, pd.healthBlue, eq, left, amount, allow, preventDeath);
            return new Dictionary<string, object>
            {
                ["hp"] = pd.health,
                ["blue"] = pd.healthBlue,
                ["max"] = pd.maxHealth,
                ["current_max"] = pd.CurrentMaxHealth,
                ["mask_eq"] = eq,
                ["mask_left"] = left,
                ["amount"] = amount,
                ["allow_mask_break"] = allow,
                ["hp_after"] = o.Health,
                ["blue_after"] = o.Blue,
                ["mask_left_after"] = o.MaskLeft,
                ["reaches_zero"] = o.ReachesZero,
                ["mask_saved"] = o.MaskSaved,
                ["mask_consumed"] = o.MaskConsumed,
                ["prevent_death_cheat"] = preventDeath,
                ["lethal_block"] = GuardState.LethalName(GuardState.Lethal),
            };
        }
    }
}
