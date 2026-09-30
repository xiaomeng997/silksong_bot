using System;
using System.Collections.Generic;
using System.Reflection;

namespace SsOracle.Core
{
    /// <summary>The run configurations that load SsOracle (DESIGN §2.3). VANILLA and FINAL run without any mod.</summary>
    internal enum ProfileName
    {
        TRAIN = 0,
        SHADOW = 1,
        REHEARSAL_SEG = 2,
        REHEARSAL_FULL = 3,
    }

    /// <summary>What a profile permits (DESIGN §2.3 table, §3.1.1 Profile).</summary>
    internal sealed class ProfileRules
    {
        /// <summary>LethalBlock mode the profile starts with; when Fixed it may not be changed.</summary>
        public Guards.LethalMode Lethal;
        public bool LethalFixed;
        public bool SaveSuppressionAllowed;
        public bool AchievementGuardRequired;
        /// <summary>CheatManager invincibility and DebugMod cheats (infinite HP, noclip, force pause, ...).</summary>
        public bool CheatsAllowed;
        /// <summary>DebugMod savestates (other modules' savestate RPCs must check this).</summary>
        public bool Savestates;
        /// <summary>Oracle key injection (ACTION); REHEARSAL drives the final sink instead (checked by the input modules).</summary>
        public bool Injection;
        /// <summary>Training probe tools that write game state: hurt.special, save.trigger, guards.test_achievement, pdset.</summary>
        public bool ProbeTools;
    }

    /// <summary>
    /// Profile (DESIGN §3.1.1 Core): which run configuration this oracle serves, and refusal of forbidden
    /// combinations. Chosen by "-ssbot-profile NAME" (default TRAIN) or the profile.set RPC; switching applies the
    /// profile's guard defaults, then validates. Rules:
    /// <list type="bullet">
    /// <item>TRAIN: anything (guards default on, SaveSuppression off, cheats and probe tools allowed).</item>
    /// <item>SHADOW: no cheats, LethalBlock blocks (veto), AchievementGuard on.</item>
    /// <item>REHEARSAL_SEG: no cheats, no injection (final sink), LethalBlock only records WOULD_DIE, no
    /// SaveSuppression (starts come from real Continue), savestates allowed.</item>
    /// <item>REHEARSAL_FULL: as SEG but no savestates at all (DebugMod must not be loaded); entering Die counts as a
    /// death and the run continues.</item>
    /// <item>Every non-TRAIN profile needs SymbolCheck.Ok and healthy, non-refused guards, and a Steel Soul session
    /// only in a slot that has a snapshot (SteelSoulSnapshot; SessionGate takes one before a Steel Soul Continue).</item>
    /// </list>
    /// Non-TRAIN profiles are checked on the first frame, about once a second and at every session start; a new
    /// violation emits "profile_violation". While a non-TRAIN profile is violated (<see cref="Ok"/> false, including a
    /// violated -ssbot-profile at startup) SessionGate refuses StartNewGame and ContinueGame, so no gate evidence is
    /// collected under a forbidden setup; a violation that appears mid-session is reported, and the next session is
    /// refused until it is fixed.
    /// </summary>
    internal static class Profile
    {
        public static ProfileName Current { get; private set; } = ProfileName.TRAIN;
        public static ProfileRules Rules => For(Current);

        /// <summary>No known violation of the current profile (TRAIN: always). Non-TRAIN profiles are false until the
        /// first-frame check ran.</summary>
        public static bool Ok => Current == ProfileName.TRAIN || (startupChecked && violations.Count == 0);

        private static readonly List<string> violations = new List<string>();
        private static string lastViolationKey = "";
        private static int nextCheckFrame;
        private static bool startupChecked;

        // One immutable instance per profile: Rules is read every frame (input latch), so it must not allocate.
        private static readonly ProfileRules ShadowRules = new ProfileRules { Lethal = Guards.LethalMode.Block, LethalFixed = true, SaveSuppressionAllowed = true, AchievementGuardRequired = true, Savestates = true, Injection = true };
        private static readonly ProfileRules RehearsalSegRules = new ProfileRules { Lethal = Guards.LethalMode.Observe, LethalFixed = true, AchievementGuardRequired = true, Savestates = true };
        private static readonly ProfileRules RehearsalFullRules = new ProfileRules { Lethal = Guards.LethalMode.Observe, LethalFixed = true, AchievementGuardRequired = true };
        private static readonly ProfileRules TrainRules = new ProfileRules { Lethal = Guards.LethalMode.Block, SaveSuppressionAllowed = true, CheatsAllowed = true, Savestates = true, Injection = true, ProbeTools = true };

        public static ProfileRules For(ProfileName p)
        {
            switch (p)
            {
                case ProfileName.SHADOW: return ShadowRules;
                case ProfileName.REHEARSAL_SEG: return RehearsalSegRules;
                case ProfileName.REHEARSAL_FULL: return RehearsalFullRules;
                default: return TrainRules;
            }
        }

        public static void Install()
        {
            var requested = ReadArg();
            if (requested != null)
            {
                if (TryParse(requested, out var p))
                {
                    Current = p;
                }
                else
                {
                    Plugin.Log.LogError($"-ssbot-profile '{requested}' is not one of TRAIN|SHADOW|REHEARSAL_SEG|REHEARSAL_FULL; staying in TRAIN");
                }
            }
            ApplyDefaults(Current);
            Plugin.Log.LogInfo($"profile {Current}");
            Ipc.Rpc.Register("profile.get", args => Describe());
            Ipc.Rpc.Register("profile.set", Set);
        }

        private static bool TryParse(string s, out ProfileName p) =>
            Enum.TryParse(s.Replace('-', '_').ToUpperInvariant(), out p) && Enum.IsDefined(typeof(ProfileName), p);

        private static string ReadArg()
        {
            var args = Environment.GetCommandLineArgs();
            for (var i = 0; i < args.Length - 1; i++)
                if (args[i] == "-ssbot-profile") return args[i + 1];
            return null;
        }

        private static void ApplyDefaults(ProfileName p)
        {
            var r = For(p);
            Guards.GuardState.Lethal = r.Lethal;
            Guards.GuardState.SaveSuppression = false;
            Guards.GuardState.AchievementGuard = true;
        }

        /// <summary>Violations of the guard switches alone (guards.set checks these before changing anything).</summary>
        public static List<string> CheckGuards(ProfileName p, Guards.LethalMode lethal, bool saveSuppression, bool achievementGuard)
        {
            var r = For(p);
            var v = new List<string>();
            if (r.LethalFixed && lethal != r.Lethal)
                v.Add($"{p} requires lethal_block={Guards.GuardState.LethalName(r.Lethal)}");
            if (saveSuppression && !r.SaveSuppressionAllowed)
                v.Add($"{p} forbids save_suppression (it needs real saves and Continue)");
            if (!achievementGuard && r.AchievementGuardRequired)
                v.Add($"{p} requires achievement_guard");
            return v;
        }

        /// <summary>All violations of profile <paramref name="p"/> in the current game and guard state.</summary>
        public static List<string> Check(ProfileName p)
        {
            var r = For(p);
            var v = CheckGuards(p, Guards.GuardState.Lethal, Guards.GuardState.SaveSuppression, Guards.GuardState.AchievementGuard);
            if (p == ProfileName.TRAIN) return v;

            if (!SymbolCheck.Ok) v.Add("SymbolCheck failed: " + string.Join(", ", SymbolCheck.Missing.ToArray()));
            if (Guards.GuardState.Refused) v.Add("guards refused: " + string.Join("; ", Guards.GuardState.Refusals.ToArray()));
            if (!Guards.GuardState.LethalHealthy) v.Add("lethal_block unhealthy");
            if (!Guards.GuardState.AchievementHealthy) v.Add("achievement_guard unhealthy");
            if (!r.CheatsAllowed)
            {
                if (CheatManager.Invincibility != CheatManager.InvincibilityStates.Off)
                    v.Add($"cheat: CheatManager.Invincibility = {CheatManager.Invincibility}");
                foreach (var c in DebugModCheats()) v.Add("cheat: DebugMod." + c);
            }
            if (!r.Savestates && DebugModLoaded())
                v.Add($"{p} allows no savestates, but DebugMod is loaded");
            if (Guards.SteelSoulSnapshot.Unprotected(out var slot))
                v.Add($"Steel Soul session in slot {slot} has no snapshot (slot.snapshot first)");
            return v;
        }

        /// <summary>Main thread, every frame (cheap unless a check is due).</summary>
        internal static void Tick()
        {
            if (!startupChecked)
            {
                // First frame: every plugin (DebugMod) has loaded, so the startup profile can be validated.
                startupChecked = true;
                if (Validate("startup").Count > 0)
                    Plugin.Log.LogError($"profile {Current} (from -ssbot-profile) is violated: new game sessions are refused until it is fixed " +
                                        "(or profile.set TRAIN)");
                return;
            }
            if (Current == ProfileName.TRAIN || UnityEngine.Time.frameCount < nextCheckFrame) return;
            nextCheckFrame = UnityEngine.Time.frameCount + 60;
            Validate("periodic");
        }

        /// <summary>Main thread: re-check the current profile now (SessionGate calls it before every session start).
        /// Returns the violations (empty for TRAIN) and updates <see cref="Ok"/>.</summary>
        internal static List<string> Validate(string when)
        {
            var v = Check(Current);
            violations.Clear();
            violations.AddRange(v);
            var key = string.Join("|", v.ToArray());
            if (key == lastViolationKey) return v;
            lastViolationKey = key;
            if (v.Count == 0) return v;
            Plugin.Log.LogError($"profile {Current} violated ({when}): {key}");
            Export.FrameExporter.Emit("profile_violation", new Dictionary<string, object>
            {
                ["profile"] = Current.ToString(),
                ["violations"] = new List<string>(v),
                ["when"] = when,
            });
            return v;
        }

        /// <summary>profile.set {name}: apply the profile's guard defaults and switch, or refuse with the violations.</summary>
        private static object Set(Dictionary<string, object> args)
        {
            var name = Ipc.Rpc.Str(args, "name");
            if (name == null || !TryParse(name, out var p))
                throw new ArgumentException("name must be TRAIN|SHADOW|REHEARSAL_SEG|REHEARSAL_FULL");
            var saved = (Guards.GuardState.Lethal, Guards.GuardState.SaveSuppression, Guards.GuardState.AchievementGuard);
            ApplyDefaults(p);
            var v = Check(p);
            if (v.Count > 0)
            {
                (Guards.GuardState.Lethal, Guards.GuardState.SaveSuppression, Guards.GuardState.AchievementGuard) = saved;
                throw new InvalidOperationException($"profile {p} refused: " + string.Join("; ", v.ToArray()));
            }
            var old = Current;
            Current = p;
            violations.Clear();
            lastViolationKey = "";
            Plugin.Log.LogInfo($"profile {old} -> {p}");
            Export.FrameExporter.Emit("profile", new Dictionary<string, object> { ["from"] = old.ToString(), ["to"] = p.ToString() });
            return Describe();
        }

        public static Dictionary<string, object> Describe()
        {
            var r = Rules;
            var v = Check(Current);
            return new Dictionary<string, object>
            {
                ["name"] = Current.ToString(),
                ["ok"] = v.Count == 0,
                ["violations"] = v,
                ["rules"] = new Dictionary<string, object>
                {
                    ["lethal_block"] = Guards.GuardState.LethalName(r.Lethal),
                    ["lethal_fixed"] = r.LethalFixed,
                    ["save_suppression_allowed"] = r.SaveSuppressionAllowed,
                    ["achievement_guard_required"] = r.AchievementGuardRequired,
                    ["cheats"] = r.CheatsAllowed,
                    ["savestates"] = r.Savestates,
                    ["injection"] = r.Injection,
                    ["probe_tools"] = r.ProbeTools,
                },
                ["debugmod_loaded"] = DebugModLoaded(),
                ["guards"] = Guards.GuardState.Describe(),
            };
        }

        // ---- DebugMod (soft: resolved by name, absent in most profiles) -------------------------------------------

        private const string DebugModGuid = "io.github.hk-speedrunning.debugmod";

        /// <summary>DebugMod.DebugMod static cheat switches (1.1.2). A missing field is simply not checked.</summary>
        private static readonly string[] CheatFields =
            { "infiniteHP", "infiniteSilk", "infiniteTools", "playerInvincible", "noclip", "heroColliderDisabled", "forcePaused", "freeEquip" };

        public static bool DebugModLoaded() => BepInEx.Bootstrap.Chainloader.PluginInfos.ContainsKey(DebugModGuid);

        private static List<string> DebugModCheats()
        {
            var on = new List<string>();
            if (!DebugModLoaded()) return on;
            var t = SymbolCheck.ResolveType("DebugMod.DebugMod");
            if (t == null) return on;
            const BindingFlags all = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static;
            foreach (var name in CheatFields)
            {
                var f = t.GetField(name, all);
                if (f != null && f.FieldType == typeof(bool) && (bool)f.GetValue(null)) on.Add(name);
            }
            var dmg = t.GetField("extraNailDamage", all);
            if (dmg != null && dmg.FieldType == typeof(int) && (int)dmg.GetValue(null) != 0) on.Add("extraNailDamage");
            // The hitbox overlay (hitbox.show, or DebugMod's own bind) draws over the game image: vision would see it.
            var settings = t.GetProperty("settings", all)?.GetValue(null, null);
            var show = settings?.GetType().GetProperty("ShowHitBoxes");
            if (show != null && show.PropertyType == typeof(int) && (int)show.GetValue(settings, null) != 0) on.Add("ShowHitBoxes");
            return on;
        }
    }
}
