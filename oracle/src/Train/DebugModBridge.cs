using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using BepInEx.Bootstrap;
using HarmonyLib;
using UnityEngine;

namespace SsOracle.Train
{
    /// <summary>
    /// Reflection bridge to DebugMod's savestates (io.github.hk-speedrunning.debugmod, MIT; verified against the installed
    /// 1.1.2 and REF\Silksong.DebugMod\SaveStates; same approach as REF\SilksongRL\...\SaveStates\DebugModSaveStates.cs),
    /// and to its hitbox display (the reference for the projection check, see the hitbox section at the end).
    /// We use DebugMod's own capture (SaveState.Save) and restore (SaveState.Load, a coroutine we pump ourselves so we
    /// know when its tail — HUD fixes, bench and water fixes — has finished), but keep the files ourselves: DebugMod's
    /// store lives in the real LocalLow (DebugMod.ModBaseDirectory is not covered by SaveRedirect) and is organised in
    /// numbered pages, so our states are plain JSON in DebugMod's file format under C:\ssbot\sandbox\savestates\.
    /// Resolution is lazy (first RPC) because DebugMod may load after us; failures are retried on the next call.
    /// Main thread only.
    /// </summary>
    internal static class DebugModBridge
    {
        public const string Guid = "io.github.hk-speedrunning.debugmod";

        private static bool resolved;
        private static Type saveStateType, dataType, managerType;
        private static ConstructorInfo saveStateCtor, dataCtor;
        private static MethodInfo saveMethod, loadMethod, isSetMethod, beforeSerialize, afterDeserialize, getFileState;
        private static PropertyInfo loadingProperty, numPagesProperty;
        private static FieldInfo dataField, identifierField, sceneField, posField, savedPdField;
        private static MethodInfo refreshMasks, refreshSpool;
        private static PropertyInfo settingsProperty;
        private static Func<object, bool, string> toJson;
        private static Action<string, object> fromJsonOverwrite;

        public static string Version { get; private set; }
        public static string Error { get; private set; } = "not resolved yet";

        /// <summary>True when DebugMod is loaded and every member we need exists; sets Error otherwise.</summary>
        public static bool Resolve()
        {
            if (resolved) return true;
            try
            {
                if (!Chainloader.PluginInfos.TryGetValue(Guid, out var info) || info?.Instance == null)
                    return Fail("DebugMod is not loaded (needed for savestates; install it into the training copy)");
                var asm = info.Instance.GetType().Assembly;
                Version = info.Metadata.Version.ToString();

                managerType = asm.GetType("DebugMod.SaveStates.SaveStateManager");
                saveStateType = asm.GetType("DebugMod.SaveStates.SaveState");
                dataType = saveStateType?.GetNestedType("SaveStateData", BindingFlags.Public | BindingFlags.NonPublic);
                if (managerType == null || saveStateType == null || dataType == null)
                    return Fail("DebugMod savestate types not found");

                const BindingFlags inst = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
                const BindingFlags stat = BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic;
                saveStateCtor = saveStateType.GetConstructor(inst, null, Type.EmptyTypes, null);
                dataCtor = dataType.GetConstructor(inst, null, Type.EmptyTypes, null);
                saveMethod = saveStateType.GetMethod("Save", inst, null, Type.EmptyTypes, null);
                loadMethod = saveStateType.GetMethod("Load", inst, null, Type.EmptyTypes, null);
                isSetMethod = saveStateType.GetMethod("IsSet", inst, null, Type.EmptyTypes, null);
                loadingProperty = saveStateType.GetProperty("loadingSavestate", stat);
                dataField = saveStateType.GetField("data", inst);
                beforeSerialize = dataType.GetMethod("BeforeSerialize", inst, null, Type.EmptyTypes, null);
                afterDeserialize = dataType.GetMethod("AfterDeserialize", inst, null, Type.EmptyTypes, null);
                identifierField = dataType.GetField("saveStateIdentifier", inst);
                sceneField = dataType.GetField("saveScene", inst);
                posField = dataType.GetField("savePos", inst);
                savedPdField = dataType.GetField("savedPd", inst);
                getFileState = managerType.GetMethod("GetFileState", stat, null, new[] { typeof(int), typeof(int) }, null);
                numPagesProperty = managerType.GetProperty("NumPages", stat);

                var missing = Missing(("SaveState()", saveStateCtor), ("SaveStateData()", dataCtor), ("Save", saveMethod),
                    ("Load", loadMethod), ("IsSet", isSetMethod), ("loadingSavestate", loadingProperty), ("data", dataField),
                    ("BeforeSerialize", beforeSerialize), ("AfterDeserialize", afterDeserialize),
                    ("saveStateIdentifier", identifierField), ("saveScene", sceneField), ("savePos", posField),
                    ("savedPd", savedPdField));
                if (missing != null) return Fail($"DebugMod {Version} savestate API differs from 1.1.2: missing {missing}");
                if (loadMethod.ReturnType != typeof(IEnumerator)) return Fail("DebugMod SaveState.Load is not a coroutine");

                // JsonUtility lives in UnityEngine.JSONSerializeModule, which the project does not reference; naming the
                // assembly loads it even if nothing has touched it yet.
                var json = Type.GetType("UnityEngine.JsonUtility, UnityEngine.JSONSerializeModule", false)
                           ?? AccessTools.TypeByName("UnityEngine.JsonUtility");
                var to = json?.GetMethod("ToJson", BindingFlags.Static | BindingFlags.Public, null, new[] { typeof(object), typeof(bool) }, null);
                var from = json?.GetMethod("FromJsonOverwrite", BindingFlags.Static | BindingFlags.Public, null, new[] { typeof(string), typeof(object) }, null);
                if (to == null || from == null) return Fail("UnityEngine.JsonUtility not found");
                toJson = (Func<object, bool, string>)Delegate.CreateDelegate(typeof(Func<object, bool, string>), to);
                fromJsonOverwrite = (Action<string, object>)Delegate.CreateDelegate(typeof(Action<string, object>), from);

                // Optional extras: HUD refresh after we change masks / silk, and the "safe loading" setting (slower loads).
                var hud = asm.GetType("DebugMod.Helpers.HudHelper");
                refreshMasks = hud?.GetMethod("RefreshMasks", stat, null, Type.EmptyTypes, null);
                refreshSpool = hud?.GetMethod("RefreshSpool", stat, null, Type.EmptyTypes, null);
                settingsProperty = asm.GetType("DebugMod.DebugMod")?.GetProperty("settings", stat);

                resolved = true;
                Error = null;
                Core.Plugin.Log.LogInfo($"DebugModBridge: using DebugMod {Version} savestates");
                return true;
            }
            catch (Exception e)
            {
                return Fail("resolving DebugMod failed: " + e.Message);
            }
        }

        private static bool Fail(string error)
        {
            if (Error != error) Core.Plugin.Log.LogError("DebugModBridge: " + error);
            Error = error;
            return false;
        }

        private static string Missing(params (string Name, object Member)[] members)
        {
            string missing = null;
            foreach (var (name, member) in members)
                if (member == null) missing = missing == null ? name : missing + ", " + name;
            return missing;
        }

        /// <summary>A DebugMod load coroutine is in flight (ours or one started from DebugMod's own UI / hotkeys).</summary>
        public static bool LoadInProgress => resolved && loadingProperty.GetValue(null, null) != null;

        /// <summary>Capture the current game state with DebugMod's SaveState.Save, named <paramref name="name"/>.</summary>
        public static object Capture(string name)
        {
            var state = saveStateCtor.Invoke(null);
            if (!(bool)saveMethod.Invoke(state, null)) throw new InvalidOperationException("DebugMod SaveState.Save returned false");
            identifierField.SetValue(dataField.GetValue(state), name);
            return state;
        }

        /// <summary>DebugMod's on-disk format (SaveStateManager.SaveToFile): BeforeSerialize, then pretty JsonUtility.</summary>
        public static string ToJson(object state)
        {
            var data = dataField.GetValue(state);
            beforeSerialize.Invoke(data, null);
            return toJson(data, true);
        }

        /// <summary>Build a SaveState from DebugMod-format JSON (as SaveStateManager.LoadFromFile does).</summary>
        public static object FromJson(string json)
        {
            var data = dataCtor.Invoke(null);
            fromJsonOverwrite(json, data);
            afterDeserialize.Invoke(data, null);
            var state = saveStateCtor.Invoke(null);
            dataField.SetValue(state, data);
            if (!(bool)isSetMethod.Invoke(state, null)) throw new InvalidDataException("savestate has no saveStateIdentifier");
            return state;
        }

        /// <summary>A state from DebugMod's own page/slot store (read-only use), or null when that slot is empty.</summary>
        public static object FileState(int page, int index)
        {
            if (getFileState == null || numPagesProperty == null) throw new InvalidOperationException("DebugMod file states unavailable");
            var pages = (int)numPagesProperty.GetValue(null, null);
            if (page < 0 || page >= pages || index < 0 || index >= 10) return null;
            var state = getFileState.Invoke(null, new object[] { page, index });
            return state != null && (bool)isSetMethod.Invoke(state, null) ? state : null;
        }

        public static int FilePages => numPagesProperty != null ? (int)numPagesProperty.GetValue(null, null) : 0;

        /// <summary>DebugMod's SaveState.Load coroutine: starts the load when first advanced.</summary>
        public static IEnumerator LoadCoroutine(object state) => (IEnumerator)loadMethod.Invoke(state, null);

        public static string Identifier(object state) => identifierField.GetValue(dataField.GetValue(state)) as string;
        public static string Scene(object state) => sceneField.GetValue(dataField.GetValue(state)) as string;
        public static UnityEngine.Vector3 Position(object state) => (UnityEngine.Vector3)posField.GetValue(dataField.GetValue(state));

        /// <summary>The PlayerData captured in the state (DebugMod restores all of it on load, permadeathMode included).</summary>
        public static PlayerData SavedPlayerData(object state) => savedPdField.GetValue(dataField.GetValue(state)) as PlayerData;

        /// <summary>DebugMod's "safe savestate loading" (loads a dummy scene first; slower resets). Null if unknown.</summary>
        public static bool? SafeLoading
        {
            get
            {
                try
                {
                    var settings = settingsProperty?.GetValue(null, null);
                    var p = settings?.GetType().GetProperty("SafeSaveStateLoading");
                    return p != null ? (bool?)(bool)p.GetValue(settings, null) : null;
                }
                catch
                {
                    return null;
                }
            }
        }

        /// <summary>Redraw the mask and spool HUD after a direct PlayerData change (as DebugMod's HUDFixes does).</summary>
        public static void RefreshHud(bool masks, bool spool)
        {
            try
            {
                if (masks) refreshMasks?.Invoke(null, null);
                if (spool) refreshSpool?.Invoke(null, null);
            }
            catch (Exception e)
            {
                Core.Plugin.Log.LogWarning("DebugMod HUD refresh failed: " + (e.InnerException ?? e).Message);
            }
        }

        // ---- hitbox display ----------------------------------------------------------------------------------------
        //
        // DebugMod.Hitbox (REF\Silksong.DebugMod\Hitbox, identical in the installed 1.1.2). Settings.ShowHitBoxes (0 off,
        // 1 hitboxes, 2 all hitboxes; its setter saves Settings.json, which SaveRedirect keeps in the sandbox, so the
        // value survives restarts) is applied by GUIController.Update in gameplay scenes: HitboxViewer.Load/Unload, and
        // Load adds a HitboxRender whose Start fills its private "colliders" dictionary (Collider2D -> HitboxType) from
        // Resources.FindObjectsOfTypeAll plus later hooks. HitboxRender.OnGUI (Repaint) draws every collider in it that
        // isActiveAndEnabled, is not on layer IGNORE_RAYCAST and whose bounds overlap Camera.main's viewport, with
        // Camera.main.WorldToScreenPoint of the collider's authored outline at that moment (after rendering, so without
        // the camera shake CameraShakeManager adds in OnPreCull and removes in OnPostRender), each vertex rounded to an
        // integer GUI pixel, as antialiased lines of width HitboxRender.LineWidth in the HitboxType's colour. Resolved
        // separately from the savestate API, so either works without the other.

        /// <summary>One collider DebugMod's HitboxRender knows, with its HitboxType name ("Knight", "Enemy", "Terrain",
        /// "NonSliderTerrain", ...) and colour.</summary>
        internal struct HitboxEntry
        {
            public Collider2D Col;
            public string Type;
            public Color Color;
        }

        /// <summary>DebugMod.Settings bools that show its UI panels (MODUI_TOGGLEALLUI flips all of them).</summary>
        public static readonly string[] PanelSettings =
            { "MainPanelVisible", "EnemiesPanelVisible", "ConsoleVisible", "InfoPanelVisible", "SaveStatePanelVisible" };

        private static bool hitboxResolved;
        private static PropertyInfo dmSettingsProperty, showHitBoxesProperty, viewerStateProperty, renderInstanceProperty, lineWidthProperty;
        private static FieldInfo renderCollidersField, typeColorField;
        private static readonly Dictionary<object, string> HitboxTypeNames = new Dictionary<object, string>();

        public static string HitboxError { get; private set; } = "not resolved yet";

        /// <summary>True when DebugMod is loaded and its hitbox display API is as expected; sets HitboxError otherwise.</summary>
        public static bool ResolveHitboxes()
        {
            if (hitboxResolved) return true;
            try
            {
                if (!Chainloader.PluginInfos.TryGetValue(Guid, out var info) || info?.Instance == null)
                    return FailHitbox("DebugMod is not loaded (its hitbox display is the reference for the projection check)");
                var asm = info.Instance.GetType().Assembly;
                Version = info.Metadata.Version.ToString();

                const BindingFlags inst = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
                const BindingFlags stat = BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic;
                var render = asm.GetType("DebugMod.Hitbox.HitboxRender");
                var viewer = asm.GetType("DebugMod.Hitbox.HitboxViewer");
                var type = render?.GetNestedType("HitboxType", BindingFlags.Public | BindingFlags.NonPublic);
                dmSettingsProperty = asm.GetType("DebugMod.DebugMod")?.GetProperty("settings", stat);
                showHitBoxesProperty = dmSettingsProperty?.PropertyType.GetProperty("ShowHitBoxes", inst);
                viewerStateProperty = viewer?.GetProperty("State", stat);
                renderInstanceProperty = render?.GetProperty("Instance", stat);
                lineWidthProperty = render?.GetProperty("LineWidth", stat);
                renderCollidersField = render?.GetField("colliders", inst);
                typeColorField = type?.GetField("Color", inst);

                var missing = Missing(("DebugMod.settings", dmSettingsProperty), ("Settings.ShowHitBoxes", showHitBoxesProperty),
                    ("HitboxViewer.State", viewerStateProperty), ("HitboxRender.Instance", renderInstanceProperty),
                    ("HitboxRender.LineWidth", lineWidthProperty), ("HitboxRender.colliders", renderCollidersField),
                    ("HitboxType.Color", typeColorField));
                if (missing != null) return FailHitbox($"DebugMod {Version} hitbox API differs from 1.1.2: missing {missing}");
                if (showHitBoxesProperty.PropertyType != typeof(int) || typeColorField.FieldType != typeof(Color)
                    || !typeof(IDictionary).IsAssignableFrom(renderCollidersField.FieldType))
                    return FailHitbox($"DebugMod {Version} hitbox API differs from 1.1.2: member types changed");

                // HitboxType has one static readonly instance per kind (Knight, Enemy, ...); name them by field.
                HitboxTypeNames.Clear();
                foreach (var f in type.GetFields(stat))
                {
                    if (f.FieldType != type) continue;
                    var v = f.GetValue(null);
                    if (v != null) HitboxTypeNames[v] = f.Name;
                }
                if (HitboxTypeNames.Count == 0) return FailHitbox($"DebugMod {Version}: no HitboxType instances found");

                hitboxResolved = true;
                HitboxError = null;
                Core.Plugin.Log.LogInfo($"DebugModBridge: using DebugMod {Version} hitbox display ({HitboxTypeNames.Count} hitbox types)");
                return true;
            }
            catch (Exception e)
            {
                return FailHitbox("resolving DebugMod's hitbox display failed: " + e.Message);
            }
        }

        private static bool FailHitbox(string error)
        {
            if (HitboxError != error) Core.Plugin.Log.LogError("DebugModBridge: " + error);
            HitboxError = error;
            return false;
        }

        private static object DmSettings => dmSettingsProperty.GetValue(null, null);

        /// <summary>DebugMod's ShowHitBoxes setting (0 off, 1 hitboxes, 2 all). Setting it saves Settings.json and takes
        /// effect in the next GUIController.Update of a gameplay scene.</summary>
        public static int ShowHitboxes
        {
            get => (int)showHitBoxesProperty.GetValue(DmSettings, null);
            set => showHitBoxesProperty.SetValue(DmSettings, value, null);
        }

        /// <summary>The mode HitboxViewer last loaded (0 = unloaded).</summary>
        public static int HitboxViewerState => (int)viewerStateProperty.GetValue(null, null);

        /// <summary>The live HitboxRender, or null (hitboxes off, not a gameplay scene, or not started yet). Its static
        /// Instance keeps pointing at a destroyed renderer, which Unity's null check catches.</summary>
        public static UnityEngine.Object HitboxRenderer
        {
            get
            {
                var r = renderInstanceProperty.GetValue(null, null) as UnityEngine.Object;
                return r != null ? r : null;
            }
        }

        /// <summary>HitboxRender.LineWidth: max(0.7, Screen.width / 960 * tk2dCam.ZoomFactor) pixels (the antialiased
        /// quad is three times as wide); null when it cannot be computed (no GameCameras).</summary>
        public static float? HitboxLineWidth
        {
            get
            {
                try
                {
                    return (float)lineWidthProperty.GetValue(null, null);
                }
                catch (Exception)
                {
                    return null;
                }
            }
        }

        /// <summary>Every collider in <paramref name="renderer"/>'s dictionary (live or not; callers apply DebugMod's
        /// draw filter). Main thread: OnGUI edits the dictionary.</summary>
        public static void HitboxColliders(UnityEngine.Object renderer, List<HitboxEntry> into)
        {
            if (!(renderCollidersField.GetValue(renderer) is IDictionary map)) return;
            foreach (DictionaryEntry kv in map)
            {
                var type = kv.Value;
                if (type == null) continue;
                into.Add(new HitboxEntry
                {
                    Col = kv.Key as Collider2D,
                    Type = HitboxTypeNames.TryGetValue(type, out var name) ? name : "?",
                    Color = (Color)typeColorField.GetValue(type),
                });
            }
        }

        /// <summary>DebugMod's UI panel visibility settings (a visible panel covers part of the game image).</summary>
        public static Dictionary<string, object> Panels()
        {
            var settings = DmSettings;
            var d = new Dictionary<string, object>();
            foreach (var name in PanelSettings)
            {
                var p = settings.GetType().GetProperty(name);
                if (p != null && p.PropertyType == typeof(bool)) d[name] = (bool)p.GetValue(settings, null);
            }
            return d;
        }

        /// <summary>Show or hide DebugMod's UI panels; null leaves a panel as it is (each change saves Settings.json).</summary>
        public static void SetPanels(Func<string, bool?> visible)
        {
            var settings = DmSettings;
            foreach (var name in PanelSettings)
            {
                var p = settings.GetType().GetProperty(name);
                if (p == null || p.PropertyType != typeof(bool) || !p.CanWrite) continue;
                var v = visible(name);
                if (v.HasValue && (bool)p.GetValue(settings, null) != v.Value) p.SetValue(settings, v.Value, null);
            }
        }
    }
}
