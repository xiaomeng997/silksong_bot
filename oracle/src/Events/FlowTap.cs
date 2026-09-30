using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using GlobalEnums;
using HarmonyLib;
using HutongGames.PlayMaker;
using HutongGames.PlayMaker.Actions;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace SsOracle.Events
{
    /// <summary>
    /// Game-flow events (m0 §3.1 MVP hooks; m0 §2.7 scene lifecycle): "gs" GameState edges, "scene_leave" /
    /// "scene_enter" / "hazard_respawn", "save", "ending". Scene hooks patch methods or the static event, never
    /// instance events, because GameManager is rebuilt on Save &amp; Quit (m0:N42).
    /// </summary>
    internal static class FlowTap
    {
        private static int transitionSeq;
        private static int enteredSeq = -1;
        private static bool hazardRespawnPending;
        private static long saveSeq;

        /// <summary>Raised on the main thread when a new room has finished entering (not for hazard respawns).</summary>
        public static event Action<GameManager> RoomEntered;

        /// <summary>Raised on the main thread when a scene transition begins.</summary>
        public static event Action RoomLeaving;

        public static void Install(Harmony h)
        {
            var gm = typeof(GameManager);
            Tap.Patch(h, gm, "SetState", new[] { typeof(GameState) }, typeof(FlowTap), nameof(SetStatePrefix), nameof(SetStatePostfix));
            Tap.Patch(h, gm, "FinishedEnteringScene", new Type[0], typeof(FlowTap), postfix: nameof(FinishedEnteringScenePostfix));
            Tap.Patch(h, typeof(HeroController), "HazardRespawn", new Type[0], typeof(FlowTap), postfix: nameof(HazardRespawnPostfix));
            GameManager.SceneTransitionBegan += OnSceneTransitionBegan;

            Tap.Patch(h, gm, "SaveGame", new[] { typeof(int), typeof(Action<bool>), typeof(bool), typeof(AutoSaveName) }, typeof(FlowTap), nameof(SaveGamePrefix));
            Tap.Patch(h, gm, "CreateRestorePoint", new[] { typeof(int), typeof(AutoSaveName), typeof(Action<bool>) }, typeof(FlowTap), nameof(CreateRestorePointPrefix));

            Tap.Patch(h, gm, "CheckCompletionAchievements", new Type[0], typeof(FlowTap), nameof(CheckCompletionPrefix));
            Tap.Patch(h, typeof(SetEndingCompleted), "OnEnter", new Type[0], typeof(FlowTap), postfix: nameof(SetEndingCompletedPostfix));
        }

        // ---- GameState ---------------------------------------------------------------------------------------

        private static void SetStatePrefix(GameManager __instance, out GameState __state) => __state = __instance.GameState;

        private static void SetStatePostfix(GameManager __instance, GameState __state, GameState newState)
        {
            if (__state == newState || !Tap.Active) return;
            var d = Tap.Data(8);
            d["from"] = __state.ToString();
            d["to"] = newState.ToString();
            d["from_i"] = (int)__state;
            d["to_i"] = (int)newState;
            d["scene"] = __instance.sceneName;
            Tap.Emit("gs", d);
        }

        // ---- scenes ------------------------------------------------------------------------------------------

        private static void OnSceneTransitionBegan(SceneLoad sceneLoad)
        {
            transitionSeq++;
            hazardRespawnPending = false;
            try { RoomLeaving?.Invoke(); }
            catch (Exception e) { Core.Plugin.Log.LogError("EventTap: RoomLeaving handler failed: " + e); }
            if (!Tap.Active) return;
            var gm = GameManager._instance;
            var info = sceneLoad?.SceneLoadInfo;
            var d = Tap.Data(8);
            d["from_raw"] = SceneManager.GetActiveScene().name;
            d["from"] = gm != null ? gm.sceneName : null;
            d["to"] = info?.SceneName;
            d["gate"] = info?.EntryGateName;
            d["first_level"] = info != null && info.IsFirstLevelForPlayer;
            d["seq"] = transitionSeq;
            Tap.Emit("scene_leave", d);
        }

        private static void HazardRespawnPostfix(HeroController __instance)
        {
            hazardRespawnPending = true;
            if (!Tap.Active) return;
            var gm = GameManager._instance;
            var pd = gm != null ? gm.playerData : null;
            var d = Tap.Data(6);
            d["phase"] = "start";
            d["scene"] = gm != null ? gm.sceneName : null;
            d["from"] = (Vector2)__instance.transform.position;
            if (pd != null) d["marker"] = (Vector2)pd.hazardRespawnLocation;
            Tap.Emit("hazard_respawn", d);
        }

        /// <summary>
        /// Called once per room entry and once at the end of every hazard respawn (m0 §2.7). The first call after
        /// each SceneTransitionBegan is "scene_enter"; one after HazardRespawn is "hazard_respawn" end; any other
        /// repeat is dropped.
        /// </summary>
        private static void FinishedEnteringScenePostfix(GameManager __instance)
        {
            if (hazardRespawnPending)
            {
                hazardRespawnPending = false;
                if (!Tap.Active) return;
                var hero = HeroController.UnsafeInstance;
                var e = Tap.Data(6);
                e["phase"] = "end";
                e["scene"] = __instance.sceneName;
                if (hero != null) e["pos"] = (Vector2)hero.transform.position;
                Tap.Emit("hazard_respawn", e);
                return;
            }
            if (enteredSeq == transitionSeq) return;
            enteredSeq = transitionSeq;
            var gameplay = __instance.IsGameplayScene();
            if (Tap.Active)
            {
                var d = Tap.Data(10);
                d["scene_raw"] = SceneManager.GetActiveScene().name;
                d["scene"] = __instance.sceneName;
                d["gate"] = __instance.entryGateName;
                d["gameplay"] = gameplay;
                d["state"] = __instance.GameState.ToString();
                d["seq"] = transitionSeq;
                var hero = HeroController.UnsafeInstance;
                if (hero != null) d["pos"] = (Vector2)hero.transform.position;
                Tap.Emit("scene_enter", d);
            }
            if (!gameplay) return;
            try { RoomEntered?.Invoke(__instance); }
            catch (Exception e) { Core.Plugin.Log.LogError("EventTap: RoomEntered handler failed: " + e); }
        }

        /// <summary>Transition count; SceneDumper uses it to tell whether the room it is scanning is still current.</summary>
        public static int TransitionSeq => transitionSeq;

        /// <summary>True once the current room has finished entering (and no transition has begun since).</summary>
        public static bool RoomIsEntered => enteredSeq == transitionSeq;

        // ---- saves (observe only: the guards package owns suppression) ---------------------------------------

        private static void SaveGamePrefix(int saveSlot, ref Action<bool> ogCallback, bool withAutoSave, AutoSaveName autoSaveName) =>
            ogCallback = WrapSave("save", saveSlot, withAutoSave, autoSaveName, ogCallback);

        private static void CreateRestorePointPrefix(int saveSlot, AutoSaveName autoSaveName, ref Action<bool> callback) =>
            callback = WrapSave("restore_point", saveSlot, true, autoSaveName, callback);

        /// <summary>
        /// Emits "save" begin and swaps the completion callback for one that emits "save" done (with the
        /// success flag the game passes on) before calling the original. A save that a guard suppresses never
        /// reports done.
        /// </summary>
        private static Action<bool> WrapSave(string kind, int slot, bool auto, AutoSaveName autoName, Action<bool> original)
        {
            var id = ++saveSeq;
            var start = Stopwatch.GetTimestamp();
            if (Tap.Active)
            {
                var gm = GameManager._instance;
                var pd = gm != null ? gm.playerData : null;
                var d = Tap.Data(12);
                d["phase"] = "begin";
                d["id"] = id;
                d["kind"] = kind;
                d["slot"] = slot;
                d["auto"] = auto;
                d["auto_name"] = autoName.ToString();
                if (pd != null) d["t_saved"] = pd.playTime;
                if (gm != null) d["t_live"] = gm.PlayTime;
                Tap.Attribute(d, true);
                Tap.Emit("save", d);
            }
            return ok =>
            {
                try
                {
                    var d = Tap.Data(6);
                    d["phase"] = "done";
                    d["id"] = id;
                    d["kind"] = kind;
                    d["ok"] = ok;
                    d["ms"] = Tap.Us(start, Stopwatch.GetTimestamp()) / 1000.0;
                    Tap.Emit("save", d);
                }
                catch (Exception e)
                {
                    Core.Plugin.Log.LogError("EventTap: save callback event failed: " + e.Message);
                }
                original?.Invoke(ok);
            };
        }

        // ---- ending (P13) -------------------------------------------------------------------------------------

        /// <summary>
        /// P13: CheckCompletionAchievements has no C# caller (m0:N29), so record everything that could identify
        /// the serialized FSM that calls it. Also written to the BepInEx log, because this happens once per run
        /// and must survive a missing brain connection.
        /// </summary>
        private static void CheckCompletionPrefix(GameManager __instance)
        {
            var d = Tap.Data(16);
            d["what"] = "check_completion";
            try
            {
                var pd = __instance.playerData;
                d["scene_raw"] = SceneManager.GetActiveScene().name;
                d["scene"] = __instance.sceneName;
                d["frame"] = Time.frameCount;
                d["state"] = __instance.GameState.ToString();
                d["t_live"] = __instance.PlayTime;
                if (pd != null)
                {
                    d["t_saved"] = pd.playTime;
                    d["pd_mode"] = pd.permadeathMode.ToString();
                    d["completion"] = pd.completionPercentage;
                    d["endings"] = pd.CompletedEndings.ToString();
                }
                d["caller"] = Tap.Caller(12);
                d["executing_fsm"] = Tap.FsmNow();
                d["candidates"] = CompletionCallers();
                d["active_fsms"] = ActiveFsms(400);
            }
            catch (Exception e)
            {
                d["error"] = e.Message;
            }
            LogEnding(d);
            Tap.Emit("ending", d);
        }

        private static void SetEndingCompletedPostfix(SetEndingCompleted __instance)
        {
            var d = Tap.Data(12);
            d["what"] = "set_ending_completed";
            try
            {
                d["ending"] = __instance.EndingType?.Value?.ToString();
                var gm = GameManager._instance;
                var pd = gm != null ? gm.playerData : null;
                if (pd != null)
                {
                    d["endings"] = pd.CompletedEndings.ToString();
                    d["t_saved"] = pd.playTime;
                }
                if (gm != null) d["t_live"] = gm.PlayTime;
                d["scene_raw"] = SceneManager.GetActiveScene().name;
                d["frame"] = Time.frameCount;
                d["fsm"] = __instance.Fsm?.GameObjectName + "/" + __instance.Fsm?.Name + "/" + __instance.State?.Name;
            }
            catch (Exception e)
            {
                d["error"] = e.Message;
            }
            LogEnding(d);
            Tap.Emit("ending", d);
        }

        private static void LogEnding(Dictionary<string, object> d) =>
            Core.Plugin.Log.LogWarning("EventTap ending: " + Describe(d));

        private static string Describe(object v)
        {
            switch (v)
            {
                case null: return "null";
                case string s: return "\"" + s + "\"";
                case IDictionary map:
                    var parts = new List<string>();
                    foreach (DictionaryEntry e in map) parts.Add(e.Key + "=" + Describe(e.Value));
                    return "{" + string.Join(", ", parts.ToArray()) + "}";
                case IEnumerable list:
                    var items = new List<string>();
                    foreach (var x in list) items.Add(Describe(x));
                    return "[" + string.Join(", ", items.ToArray()) + "]";
                default: return Convert.ToString(v, System.Globalization.CultureInfo.InvariantCulture);
            }
        }

        /// <summary>
        /// FSMs with an action that calls CheckCompletionAchievements by name (CallMethodProper, CallMethod,
        /// SendMessage), in any state, with the state they are in now. Best effort; runs once per ending.
        /// </summary>
        private static List<object> CompletionCallers()
        {
            var found = new List<object>();
            foreach (var fsm in new List<PlayMakerFSM>(PlayMakerFSM.FsmList))
            {
                if (fsm == null || fsm.Fsm == null) continue;
                FsmState[] states;
                try { states = fsm.Fsm.States; }
                catch { continue; }
                if (states == null) continue;
                foreach (var state in states)
                {
                    // Only states whose actions are already loaded: reading Actions otherwise deserializes them
                    // (and logs an error for uninitialized FSMs). The FSM that is calling right now is loaded.
                    if (state == null || !state.ActionsLoaded) continue;
                    FsmStateAction[] actions;
                    try { actions = state.Actions; }
                    catch { continue; }
                    if (actions == null) continue;
                    foreach (var a in actions)
                    {
                        if (!CallsCheckCompletion(a)) continue;
                        var e = new Dictionary<string, object>
                        {
                            ["go"] = fsm.gameObject.name,
                            ["scene"] = fsm.gameObject.scene.name,
                            ["fsm"] = fsm.FsmName,
                            ["state"] = state.Name,
                            ["action"] = a.GetType().Name,
                            ["active_state"] = fsm.ActiveStateName,
                            ["state_time"] = fsm.Fsm.ActiveState != null ? fsm.Fsm.ActiveState.StateTime : -1f,
                        };
                        found.Add(e);
                    }
                }
            }
            return found;
        }

        private static bool CallsCheckCompletion(FsmStateAction a)
        {
            const string Name = "CheckCompletionAchievements";
            switch (a)
            {
                case CallMethodProper p: return p.methodName != null && p.methodName.Value == Name;
                case CallMethod m: return m.methodName != null && m.methodName.Value == Name;
                case SendMessage s: return s.functionCall != null && s.functionCall.FunctionName == Name;
                default: return false;
            }
        }

        /// <summary>
        /// "scene:GameObject/Fsm/State@t" of up to <paramref name="max"/> enabled FSMs, the active scene's first
        /// (the caller is most likely there), then the rest (DontDestroyOnLoad, additive scenes).
        /// </summary>
        private static List<object> ActiveFsms(int max)
        {
            var list = new List<object>();
            var active = SceneManager.GetActiveScene();
            for (var pass = 0; pass < 2; pass++)
            {
                foreach (var fsm in PlayMakerFSM.FsmList)
                {
                    if (list.Count >= max) return list;
                    if (fsm == null || !fsm.isActiveAndEnabled) continue;
                    var scene = fsm.gameObject.scene;
                    if ((scene == active) != (pass == 0)) continue;
                    var t = fsm.Fsm != null && fsm.Fsm.ActiveState != null ? fsm.Fsm.ActiveState.StateTime : -1f;
                    list.Add(scene.name + ":" + fsm.gameObject.name + "/" + fsm.FsmName + "/" + fsm.ActiveStateName + "@" +
                             t.ToString("F2", System.Globalization.CultureInfo.InvariantCulture));
                }
            }
            return list;
        }
    }
}
