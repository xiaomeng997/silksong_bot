using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Reflection;
using System.Text;
using HarmonyLib;

namespace SsOracle.Guards
{
    /// <summary>What LethalBlock does with a hit that would leave Hornet at 0 HP or start Die (DESIGN §2.3).</summary>
    internal enum LethalMode
    {
        /// <summary>No detection at all (only for guard tests in TRAIN).</summary>
        Off = 0,
        /// <summary>Record CATASTROPHE / WOULD_DIE and let the death happen (REHEARSAL-SEG/FULL: the real outcome counts).</summary>
        Observe = 1,
        /// <summary>Record and veto (TRAIN, SHADOW).</summary>
        Block = 2,
    }

    /// <summary>
    /// Switches, health and counters of the training guards (DESIGN §3.1.1 Guards). Defaults are the TRAIN profile:
    /// LethalBlock blocking, AchievementGuard on, SaveSuppression off (probes and savestate curation need real
    /// saves; guards.set turns it on). A guard is healthy only if every Harmony patch it relies on was applied. A
    /// switch can be on while its guard is unhealthy; guards.get and the "guards" STATE section make that loud.
    /// Main thread only, except the counters, which are only informational.
    /// </summary>
    internal static class GuardState
    {
        public static LethalMode Lethal = LethalMode.Block;
        public static bool SaveSuppression;
        public static bool AchievementGuard = true;

        /// <summary>Net 1 (TakeHealth) and net 2 (Die) are both patched.</summary>
        public static bool LethalHealthy;
        public static bool SaveSuppressionHealthy;
        /// <summary>All AchievementGuard targets (m0:C1) are patched.</summary>
        public static bool AchievementHealthy;
        /// <summary>StartNewGame/ContinueGame are patched, so a refusal can actually stop a session from starting.</summary>
        public static bool SessionGateHealthy;

        /// <summary>
        /// Why the oracle refuses guard-dependent features: new game sessions (SessionGate), non-TRAIN profiles,
        /// training probe tools and slot restores. Filled at install time when a safety patch is missing.
        /// </summary>
        public static readonly List<string> Refusals = new List<string>();
        public static bool Refused => Refusals.Count > 0;

        public static int Catastrophes, WouldDie, AchievementsBlocked, SavesSuppressed, SavesVetoed, SessionsRefused;
        public static Dictionary<string, object> LastCatastrophe, LastWouldDie;

        public static string LethalName(LethalMode m) => m == LethalMode.Block ? "block" : m == LethalMode.Observe ? "observe" : "off";

        public static bool TryParseLethal(object v, out LethalMode mode)
        {
            switch (v)
            {
                case bool b:
                    mode = b ? LethalMode.Block : LethalMode.Off;
                    return true;
                case string s:
                    switch (s.ToLowerInvariant())
                    {
                        case "block": case "on": case "true": mode = LethalMode.Block; return true;
                        case "observe": case "record": mode = LethalMode.Observe; return true;
                        case "off": case "false": mode = LethalMode.Off; return true;
                    }
                    break;
                case long l when l >= 0 && l <= 2:
                    mode = (LethalMode)l;
                    return true;
            }
            mode = LethalMode.Off;
            return false;
        }

        public static void Refuse(string reason)
        {
            if (Refusals.Contains(reason)) return;
            Refusals.Add(reason);
            Core.Plugin.Log.LogError("GUARD FAILURE, refusing guard-dependent features (new sessions, non-TRAIN profiles, probe tools): " + reason);
        }

        /// <summary>Snapshot for guards.get / profile.get (plain values only; serialized by FramedServer.WriteObject).</summary>
        public static Dictionary<string, object> Describe()
        {
            return new Dictionary<string, object>
            {
                ["lethal_block"] = LethalName(Lethal),
                ["save_suppression"] = SaveSuppression,
                ["achievement_guard"] = AchievementGuard,
                ["healthy"] = new Dictionary<string, object>
                {
                    ["lethal_block"] = LethalHealthy,
                    ["save_suppression"] = SaveSuppressionHealthy,
                    ["achievement_guard"] = AchievementHealthy,
                    ["session_gate"] = SessionGateHealthy,
                },
                ["symbols_ok"] = Core.SymbolCheck.Ok,
                ["refused"] = Refused,
                ["refusals"] = new List<string>(Refusals),
                ["profile"] = Core.Profile.Current.ToString(),
                ["profile_ok"] = Core.Profile.Ok,
                ["counts"] = new Dictionary<string, object>
                {
                    ["catastrophe"] = Catastrophes,
                    ["would_die"] = WouldDie,
                    ["achievement_blocked"] = AchievementsBlocked,
                    ["save_suppressed"] = SavesSuppressed,
                    ["save_vetoed"] = SavesVetoed,
                    ["session_refused"] = SessionsRefused,
                },
                ["last_catastrophe"] = LastCatastrophe,
                ["last_would_die"] = LastWouldDie,
                ["mask"] = LethalBlock.MaskInfo(),
                ["steel_soul"] = SteelSoulSnapshot.SessionInfo(),
            };
        }
    }

    /// <summary>Harmony helpers shared by the guards: a missing target or a failed patch is logged, never thrown.</summary>
    internal static class Patching
    {
        /// <summary>Patch <paramref name="target"/> with methods of <paramref name="owner"/> by name. Returns false (and
        /// logs an error) when the target is missing or Harmony throws.</summary>
        public static bool Apply(Harmony harmony, MethodBase target, string what, Type owner,
            string prefix = null, string postfix = null, int priority = -1)
        {
            if (target == null)
            {
                Core.Plugin.Log.LogError($"patch target missing: {what}");
                return false;
            }
            try
            {
                harmony.Patch(target,
                    prefix: prefix == null ? null : Method(owner, prefix, priority),
                    postfix: postfix == null ? null : Method(owner, postfix, priority));
                return true;
            }
            catch (Exception e)
            {
                Core.Plugin.Log.LogError($"patching {what} failed: {e}");
                return false;
            }
        }

        private static HarmonyMethod Method(Type owner, string name, int priority)
        {
            var m = new HarmonyMethod(AccessTools.Method(owner, name));
            if (priority >= 0) m.priority = priority;
            return m;
        }

        /// <summary>
        /// Compact caller chain for rare guard events ("A.B &lt; C.D &lt; ..."), skipping the oracle's and Harmony's own
        /// frames. Costs ~0.1-1 ms, so only call it when a guard actually fires.
        /// </summary>
        public static string Stack(int maxFrames = 10)
        {
            var st = new StackTrace(1, false);
            var sb = new StringBuilder(256);
            var n = 0;
            for (var i = 0; i < st.FrameCount && n < maxFrames; i++)
            {
                var m = st.GetFrame(i)?.GetMethod();
                if (m == null) continue;
                var t = m.DeclaringType;
                var ns = t?.Namespace;
                if (ns != null && (ns.StartsWith("SsOracle", StringComparison.Ordinal) || ns.StartsWith("HarmonyLib", StringComparison.Ordinal)))
                    continue;
                if (n++ > 0) sb.Append(" < ");
                if (t != null) sb.Append(t.Name).Append('.');
                sb.Append(m.Name);
            }
            return sb.ToString();
        }
    }
}
