using System;
using System.Collections.Generic;
using System.IO;
using GlobalEnums;
using HarmonyLib;

namespace SsOracle.Guards
{
    /// <summary>
    /// SaveSuppression (DESIGN §3.1.1 Guards; adapted from SilksongRL's SaveSuppression, MIT): while on, the save
    /// paths write nothing to disk and report success to their callers, which is exactly what the game itself does
    /// when CheatManager.AllowSaving is false (synchronous callback(true)). Off by default: probes and savestate
    /// curation rely on real saves; guards.set turns it on.
    ///
    /// Hooked where every save ends up: the private GameManager.SaveGame(int, Action&lt;bool&gt;, bool, AutoSaveName)
    /// (public SaveGame, SaveGameWithAutoSave, the queued save, PlayerDead and ReturnToMainMenu all land there),
    /// CreateRestorePoint(int, AutoSaveName, Action&lt;bool&gt;) (the AutoSaveName overload and the queued autosave
    /// forward to it) and SaveGameData.
    ///
    /// Fix over SilksongRL (m0 §2.3): the game flushes the live session timer into playerData.playTime only inside a
    /// save (PreparePlayerDataForSave), and CheckCompletionAchievements reads that flushed value. Skipping the whole
    /// method would freeze playerData.playTime and break the timer model and the SPEEDRUN_1 check in training, so the
    /// in-memory part still runs (SaveLevelState, PreparePlayerDataForSave; restore points also clear the autosave
    /// queue) and only the serialization and file writes are skipped. Invalid slots and disableSaveGame keep their
    /// vanilla failure path. PreparePlayerDataForSave also flushes shared.dat (AchievementHandler.FlushRecordsToDisk);
    /// that file is in the sandbox (SaveRedirect) and AchievementGuard keeps achievement keys out of it, so it is left
    /// alone: SaveSuppression is about the slot files (user{N}.dat, backups, Restore_Points).
    ///
    /// The same three hooks are LethalBlock's last line, whatever the SaveSuppression switch says: while LethalBlock
    /// blocks and permadeathMode is Dead in memory (a Steel Soul death that got past both nets, m0:N7), every save is
    /// vetoed the same way (nothing written, callback(true), "save_vetoed"), so a queued save, an FSM SaveGame action,
    /// a restore point or Save &amp; Quit cannot write a DEFEATED slot. A failure callback is not an option: the game
    /// answers it with a modal SAVE_FAILED message.
    /// </summary>
    internal static class SaveSuppression
    {
        private static Action<GameManager, int> prepareForSave;
        private static AccessTools.FieldRef<GameManager, bool> isAutoSaveQueued;

        public static void Install(Harmony harmony)
        {
            var gm = typeof(GameManager);
            var me = typeof(SaveSuppression);
            try
            {
                prepareForSave = AccessTools.MethodDelegate<Action<GameManager, int>>(
                    AccessTools.Method(gm, "PreparePlayerDataForSave", new[] { typeof(int) }));
                isAutoSaveQueued = AccessTools.FieldRefAccess<GameManager, bool>("isAutoSaveQueued");
            }
            catch (Exception e)
            {
                Core.Plugin.Log.LogError("SaveSuppression: cannot bind PreparePlayerDataForSave / isAutoSaveQueued: " + e.Message);
            }
            var ok = prepareForSave != null && isAutoSaveQueued != null;
            ok &= Patching.Apply(harmony, AccessTools.Method(gm, "SaveGame", new[] { typeof(int), typeof(Action<bool>), typeof(bool), typeof(AutoSaveName) }),
                "GameManager.SaveGame(int, Action<bool>, bool, AutoSaveName)", me, nameof(SaveGamePrefix), priority: Priority.First);
            ok &= Patching.Apply(harmony, AccessTools.Method(gm, nameof(GameManager.CreateRestorePoint), new[] { typeof(int), typeof(AutoSaveName), typeof(Action<bool>) }),
                "GameManager.CreateRestorePoint(int, AutoSaveName, Action<bool>)", me, nameof(RestorePointPrefix), priority: Priority.First);
            ok &= Patching.Apply(harmony, AccessTools.Method(gm, nameof(GameManager.SaveGameData), new[] { typeof(int), typeof(SaveGameData), typeof(bool), typeof(Action<bool>) }),
                "GameManager.SaveGameData", me, nameof(SaveGameDataPrefix), priority: Priority.First);
            GuardState.SaveSuppressionHealthy = ok;
            if (!ok)
            {
                GuardState.SaveSuppression = false;
                Core.Plugin.Log.LogError("SaveSuppression unavailable: guards.set save_suppression=true will be refused");
            }

            Ipc.Rpc.Register("save.trigger", TriggerRpc);
        }

        /// <summary>Slots and configurations where vanilla would really write; everything else keeps its own path.</summary>
        private static bool WouldWrite(GameManager gm, int saveSlot) =>
            saveSlot >= 0 && (gm.gameConfig == null || !gm.gameConfig.disableSaveGame) && !DemoHelper.IsDemoMode;

        private static bool SaveGamePrefix(GameManager __instance, int saveSlot, Action<bool> ogCallback, bool withAutoSave, AutoSaveName autoSaveName)
        {
            var kind = withAutoSave ? "save+restore_point" : "save";
            if (VetoDead(__instance.playerData, kind, saveSlot, ogCallback)) return false;
            if (!GuardState.SaveSuppression || !WouldWrite(__instance, saveSlot)) return true;
            __instance.SaveLevelState();
            prepareForSave(__instance, saveSlot);
            Suppressed(__instance, kind, saveSlot, autoSaveName);
            ogCallback?.Invoke(true);
            return false;
        }

        private static bool RestorePointPrefix(GameManager __instance, int saveSlot, AutoSaveName autoSaveName, Action<bool> callback)
        {
            if (VetoDead(__instance.playerData, "restore_point", saveSlot, callback))
            {
                if (isAutoSaveQueued != null) isAutoSaveQueued(__instance) = false;   // as vanilla does
                return false;
            }
            if (!GuardState.SaveSuppression || !WouldWrite(__instance, saveSlot)) return true;
            __instance.SaveLevelState();
            isAutoSaveQueued(__instance) = false;
            prepareForSave(__instance, saveSlot);
            Suppressed(__instance, "restore_point", saveSlot, autoSaveName);
            callback?.Invoke(true);
            return false;
        }

        private static bool SaveGameDataPrefix(GameManager __instance, int saveSlot, SaveGameData saveData, Action<bool> ogCallback)
        {
            // The data being written, not necessarily the live PlayerData.
            if (VetoDead(saveData != null ? saveData.playerData : __instance.playerData, "save_data", saveSlot, ogCallback)) return false;
            if (!GuardState.SaveSuppression) return true;
            Suppressed(__instance, "save_data", saveSlot, AutoSaveName.NONE);
            ogCallback?.Invoke(true);
            return false;
        }

        /// <summary>
        /// LethalBlock's last line (see the class summary): true (and the caller's callback answered with success) when
        /// LethalBlock blocks and <paramref name="pd"/> is a dead Steel Soul state. Nothing of it is written or flushed.
        /// </summary>
        private static bool VetoDead(PlayerData pd, string kind, int slot, Action<bool> callback)
        {
            if (GuardState.Lethal != LethalMode.Block || pd == null || pd.permadeathMode != PermadeathModes.Dead) return false;
            GuardState.SavesVetoed++;
            Export.FrameExporter.Emit("save_vetoed", new Dictionary<string, object>
            {
                ["kind"] = kind,
                ["slot"] = slot,
                ["reason"] = "permadeath_dead",
                ["stack"] = Patching.Stack(6),
            });
            Core.Plugin.Log.LogError($"LethalBlock: vetoed {kind} to slot {slot}: permadeathMode is Dead in memory (a Steel Soul death got " +
                                     "past both nets); nothing written. Load a savestate or slot.restore to continue.");
            callback?.Invoke(true);
            return true;
        }

        private static void Suppressed(GameManager gm, string kind, int slot, AutoSaveName autoSave)
        {
            GuardState.SavesSuppressed++;
            var pd = gm.playerData;
            Export.FrameExporter.Emit("save_suppressed", new Dictionary<string, object>
            {
                ["kind"] = kind,
                ["slot"] = slot,
                ["auto"] = autoSave.ToString(),
                ["t_saved"] = pd != null ? pd.playTime : 0f,
                ["stack"] = Patching.Stack(6),
            });
            Core.Plugin.Log.LogInfo($"SaveSuppression: {kind} to slot {slot} suppressed (playTime flushed to {(pd != null ? pd.playTime : 0f):F2})");
        }

        /// <summary>
        /// save.trigger {kind: save|restore_point} (TRAIN probe tool): runs a real GameManager save and replies with the
        /// callback result, the slot file's last-write time and playerData.playTime, so a probe can check that
        /// SaveSuppression writes nothing yet still flushes the timer. Writes only inside the sandbox (SaveRedirect).
        /// </summary>
        private static void TriggerRpc(Dictionary<string, object> args, Ipc.Rpc.Reply reply)
        {
            if (!Core.Profile.Rules.ProbeTools) { reply.Fail($"probe tools are disabled in profile {Core.Profile.Current}"); return; }
            var gm = GameManager._instance;
            if (gm == null || gm.playerData == null || HeroController.UnsafeInstance == null) { reply.Fail("no game in progress"); return; }
            var kind = Ipc.Rpc.Str(args, "kind", "save");
            var slot = gm.profileID;
            var file = SteelSoulSnapshot.PrimaryFile(slot);
            var frame = UnityEngine.Time.frameCount;
            Action<bool> done = ok =>
            {
                var pd = GameManager._instance != null ? GameManager._instance.playerData : null;
                reply.Ok(new Dictionary<string, object>
                {
                    ["ok"] = ok,
                    ["kind"] = kind,
                    ["slot"] = slot,
                    ["suppressed"] = GuardState.SaveSuppression,
                    ["file"] = file,
                    ["mtime_utc_ticks"] = File.Exists(file) ? File.GetLastWriteTimeUtc(file).Ticks : 0L,
                    ["t_saved"] = pd != null ? pd.playTime : 0f,
                    ["frames"] = UnityEngine.Time.frameCount - frame,
                });
            };
            switch (kind)
            {
                case "save":
                    gm.SaveGame(done);
                    break;
                case "restore_point":
                    gm.CreateRestorePoint(AutoSaveName.NONE, done);
                    break;
                default:
                    reply.Fail("kind must be save|restore_point");
                    break;
            }
        }
    }
}
