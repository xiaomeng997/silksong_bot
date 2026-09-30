using System;
using System.Collections.Generic;
using HarmonyLib;

namespace SsOracle.Guards
{
    /// <summary>
    /// Keeps training from unlocking anything achievement-like (DESIGN §2.7; m0:C1, N26). The training copy has no
    /// Steam subsystem, so this is the second layer: it stops the local record too (DesktopPlatform.PushAchievementUnlock
    /// always writes the key into shared.dat, which is what the Achievements screen and IsAchievementUnlocked fall back
    /// to). Hooks are on the concrete methods that run: Platform.PushAchievementUnlock is abstract and DesktopPlatform's
    /// UpdateAchievementProgress does not call base, so patches there would fail or never fire (m0:C1).
    /// RecPermadeathMode (the Steel Soul unlock record, written with SetInt) is never touched.
    /// If any target cannot be patched the oracle refuses to start sessions (SessionGate) and says so in guards.get.
    /// </summary>
    internal static class AchievementGuard
    {
        public static void Install(Harmony harmony)
        {
            var me = typeof(AchievementGuard);
            var ok = true;
            ok &= Patching.Apply(harmony, AccessTools.Method(typeof(DesktopPlatform), nameof(DesktopPlatform.PushAchievementUnlock), new[] { typeof(string) }),
                "DesktopPlatform.PushAchievementUnlock", me, nameof(PushPrefix), priority: Priority.First);
            ok &= Patching.Apply(harmony, AccessTools.Method(typeof(DesktopPlatform), nameof(DesktopPlatform.UpdateAchievementProgress), new[] { typeof(string), typeof(int), typeof(int) }),
                "DesktopPlatform.UpdateAchievementProgress", me, nameof(PlatformProgressPrefix), priority: Priority.First);
            ok &= Patching.Apply(harmony, AccessTools.Method(typeof(AchievementHandler), nameof(AchievementHandler.AwardAchievementToPlayer), new[] { typeof(string) }),
                "AchievementHandler.AwardAchievementToPlayer", me, nameof(AwardPrefix), priority: Priority.First);
            ok &= Patching.Apply(harmony, AccessTools.Method(typeof(AchievementHandler), nameof(AchievementHandler.UpdateAchievementProgress), new[] { typeof(string), typeof(int), typeof(int) }),
                "AchievementHandler.UpdateAchievementProgress", me, nameof(HandlerProgressPrefix), priority: Priority.First);
            ok &= Patching.Apply(harmony, AccessTools.Method(typeof(MenuStyleUnlock), nameof(MenuStyleUnlock.Unlock), new[] { typeof(string), typeof(bool) }),
                "MenuStyleUnlock.Unlock", me, nameof(MenuStylePrefix), priority: Priority.First);
            // Defense in depth for callers we do not know about: achievement keys written straight into shared data.
            ok &= Patching.Apply(harmony, AccessTools.Method(typeof(CustomSharedData), nameof(CustomSharedData.SetBool), new[] { typeof(string), typeof(bool) }),
                "CustomSharedData.SetBool", me, nameof(SharedSetBoolPrefix), priority: Priority.First);

            GuardState.AchievementHealthy = ok;
            if (!ok) GuardState.Refuse("achievement_guard: at least one patch target is missing or failed (see errors above)");
        }

        private static bool PushPrefix(string achievementId) => Allow("DesktopPlatform.PushAchievementUnlock", achievementId);

        private static bool PlatformProgressPrefix(string achievementId, int value, int max) =>
            Allow("DesktopPlatform.UpdateAchievementProgress", achievementId, value, max);

        private static bool AwardPrefix(string key) => Allow("AchievementHandler.AwardAchievementToPlayer", key);

        private static bool HandlerProgressPrefix(string key, int value, int max) =>
            Allow("AchievementHandler.UpdateAchievementProgress", key, value, max);

        private static bool MenuStylePrefix(string key) => Allow("MenuStyleUnlock.Unlock", key);

        private static bool SharedSetBoolPrefix(string key, bool val)
        {
            if (!val || !IsAchievementKey(key)) return true;
            return Allow("CustomSharedData.SetBool", key);
        }

        private static bool IsAchievementKey(string key)
        {
            if (string.IsNullOrEmpty(key)) return false;
            try
            {
                var gm = GameManager._instance;
                var handler = gm != null ? gm.achievementHandler : null;
                var list = handler != null ? handler.AchievementsList : null;
                return list != null && list.FindAchievement(key) != null;
            }
            catch (Exception)
            {
                return false;
            }
        }

        /// <summary>Returns whether the original may run; records every attempt either way.</summary>
        private static bool Allow(string via, string key, int value = -1, int max = -1)
        {
            var d = new Dictionary<string, object> { ["key"] = key, ["via"] = via, ["stack"] = Patching.Stack() };
            if (value >= 0) { d["value"] = value; d["max"] = max; }
            if (!GuardState.AchievementGuard)
            {
                Core.Plugin.Log.LogWarning($"AchievementGuard is OFF: {via}({key}) passes");
                Export.FrameExporter.Emit("achievement_passed", d);
                return true;
            }
            GuardState.AchievementsBlocked++;
            Core.Plugin.Log.LogWarning($"AchievementGuard blocked {via}({key})");
            Export.FrameExporter.Emit("achievement_blocked", d);
            return false;
        }

        /// <summary>
        /// guards.test_achievement {key="FIRST_TOOL"} (TRAIN only, guard must be on and healthy): calls every guarded
        /// entry point once with the key and reports how many were blocked (6 of 6 in the training copy). Proves the
        /// guard in the running game, including the shared.dat hook (CustomSharedData.SetBool), which the other calls
        /// never reach because PushAchievementUnlock is blocked before it writes the key.
        /// </summary>
        internal static object TestRpc(Dictionary<string, object> args)
        {
            if (!Core.Profile.Rules.ProbeTools) throw new InvalidOperationException($"probe tools are disabled in profile {Core.Profile.Current}");
            if (!GuardState.AchievementGuard || !GuardState.AchievementHealthy)
                throw new InvalidOperationException("refusing: AchievementGuard is off or unhealthy");
            var key = Ipc.Rpc.Str(args, "key", "FIRST_TOOL");
            var gm = GameManager._instance;
            var before = GuardState.AchievementsBlocked;
            var calls = new List<string>();
            var expected = 0;
            if (gm != null && gm.achievementHandler != null)
            {
                gm.achievementHandler.AwardAchievementToPlayer(key);
                gm.achievementHandler.UpdateAchievementProgress(key, 1, 2);
                calls.Add("AchievementHandler");
                expected += 2;
            }
            if (Platform.Current is DesktopPlatform desktop)
            {
                desktop.PushAchievementUnlock(key);
                desktop.UpdateAchievementProgress(key, 1, 2);
                calls.Add("DesktopPlatform");
                expected += 2;
            }
            MenuStyleUnlock.Unlock(key, false);
            calls.Add("MenuStyleUnlock");
            expected += 1;
            // Only a real achievement key and only the CustomSharedData the hook covers: anything else would really be
            // written to shared.dat (the hook lets non-achievement keys through by design).
            var shared = Platform.Current != null ? Platform.Current.RoamingSharedData : null;
            if (shared is CustomSharedData && IsAchievementKey(key))
            {
                shared.SetBool(key, true);
                calls.Add("CustomSharedData.SetBool");
                expected += 1;
            }
            return new Dictionary<string, object>
            {
                ["key"] = key,
                ["calls"] = calls,
                ["blocked"] = GuardState.AchievementsBlocked - before,
                ["expected"] = expected,
            };
        }
    }

    /// <summary>
    /// "Refuse to start": GameManager.StartNewGame and ContinueGame do nothing, with a loud error and a
    /// "session_refused" event, while
    /// <list type="bullet">
    /// <item>GuardState.Refused (DESIGN §2.7: a failed AchievementGuard patch must stop the plugin from being used), so
    /// no game session (and therefore no achievement, death or save) can happen with a broken guard;</item>
    /// <item>a non-TRAIN profile is violated (Profile.Validate, run fresh here: cheats on in SHADOW, DebugMod loaded in
    /// REHEARSAL_FULL, a violated -ssbot-profile at startup ...), so gate evidence is never collected under a forbidden
    /// setup;</item>
    /// <item>(ContinueGame only) the loaded save is Steel Soul, its slot has no snapshot and taking one fails
    /// (SteelSoulSnapshot.EnsureForContinue; DESIGN §3.1.1).</item>
    /// </list>
    /// A refused start from the title menu goes back to the main menu, as a failed load does in vanilla.
    /// </summary>
    internal static class SessionGate
    {
        public static void Install(Harmony harmony)
        {
            var me = typeof(SessionGate);
            var a = Patching.Apply(harmony, AccessTools.Method(typeof(GameManager), nameof(GameManager.StartNewGame), new[] { typeof(bool), typeof(bool) }),
                "GameManager.StartNewGame", me, nameof(StartNewGamePrefix), priority: Priority.First);
            var b = Patching.Apply(harmony, AccessTools.Method(typeof(GameManager), nameof(GameManager.ContinueGame), Type.EmptyTypes),
                "GameManager.ContinueGame", me, nameof(ContinueGamePrefix), priority: Priority.First);
            GuardState.SessionGateHealthy = a && b;
        }

        private static bool StartNewGamePrefix(GameManager __instance) => BackToMenuUnless(__instance, Allow("StartNewGame", null));

        private static bool ContinueGamePrefix(GameManager __instance) =>
            BackToMenuUnless(__instance, Allow("ContinueGame", () => SteelSoulSnapshot.EnsureForContinue(__instance)));

        /// <summary>The menu code hid the save-select menu before calling in; on a refusal bring the main menu back
        /// (what LoadGameFromUIRoutine does when a load fails) instead of leaving a black screen.</summary>
        private static bool BackToMenuUnless(GameManager gm, bool allowed)
        {
            if (!allowed && gm.IsMenuScene() && gm.ui != null) gm.ui.UIGoToMainMenu();
            return allowed;
        }

        /// <param name="extra">Further check run only when everything else passed; returns a refusal reason or null.</param>
        private static bool Allow(string what, Func<string> extra)
        {
            var reasons = new List<string>(GuardState.Refusals);
            if (!GuardState.Refused)
            {
                foreach (var v in Core.Profile.Validate("session " + what))
                    reasons.Add($"profile {Core.Profile.Current}: {v}");
                if (reasons.Count == 0 && extra != null)
                {
                    var why = extra();
                    if (why != null) reasons.Add(why);
                }
            }
            if (reasons.Count == 0) return true;
            GuardState.SessionsRefused++;
            Core.Plugin.Log.LogError($"SessionGate: refusing GameManager.{what}: {string.Join("; ", reasons.ToArray())}");
            Export.FrameExporter.Emit("session_refused", new Dictionary<string, object> { ["what"] = what, ["reasons"] = reasons });
            return false;
        }
    }
}
