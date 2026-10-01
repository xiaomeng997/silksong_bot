using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Text;
using System.Text.RegularExpressions;
using GlobalEnums;
using HarmonyLib;
using UnityEngine;
using Rpc = SsOracle.Ipc.Rpc;

namespace SsOracle.Train
{
    /// <summary>
    /// Savestates for episode resets (DESIGN §3.1.1 Harness, §3.9.1: reset <= 2 s), through DebugModBridge.
    ///   ("name" may also be sent as "state")
    ///   savestate.save {name}              capture now; writes C:\ssbot\sandbox\savestates\&lt;name&gt;.json (DebugMod format,
    ///                                      shared by all instances; a DebugMod JSON copied there works too)
    ///   savestate.load {name, timeout?, force?}
    ///                                      answers only when the load has finished: DebugMod's coroutine (incl. its HUD
    ///                                      fixes) is done, the hero exists, GameState is PLAYING, the scene has been
    ///                                      entered. Reports the duration. "dm:&lt;page&gt;/&lt;slot&gt;" loads from DebugMod's own
    ///                                      store (read-only), e.g. community packs imported through DebugMod's UI.
    ///   savestate.list                     our files + DebugMod's filled slots
    /// Parsed states are cached per file (size + mtime), so a reset does not re-parse the JSON.
    /// A death is never saved and never silently undone: save refuses a dead hero (cState.dead, permadeathMode Dead or
    /// hp 0), a state captured dead is never loaded, and a load over a dead hero (which DebugMod would quietly revive:
    /// its LoadImpl aborts the death coroutines and restores permadeathMode from the file) is refused unless force is
    /// set, and then logged as an error and reported as a "harness" event {op: "death_reset"} before loading.
    /// On a timeout the reply fails at once, but the harness stays busy (ACTIONs ignored) until DebugMod's load ends.
    /// </summary>
    internal static class SavestateBridge
    {
        public const string Folder = @"C:\ssbot\sandbox\savestates";
        private const double DefaultTimeoutS = 15;
        private const double PreLoadWaitS = 5;
        private const int HeroInputGraceFrames = 30;

        /// <summary>
        /// Every DebugMod savestate load leaves two unreferenced material instances behind ("Sprites-Default (Instance)"
        /// and "Cherry-Sprites-Default (Instance)", made by Renderer.material in the reloaded scene), about 100 KB each of
        /// private memory: about +21 MB per 100 loads, +35 MB/h per instance in the M1 soak (probes/mem_growth,
        /// 2026-09-30). The game frees such assets on its own scene transitions; DebugMod's load path does not. So every
        /// UnloadEvery loads the load step also runs Resources.UnloadUnusedAssets and waits for it, inside the reset (no
        /// brain input runs then), which freed all of them in game.
        /// </summary>
        private const int UnloadEvery = 25;
        private const double UnloadTimeoutS = 5;
        private static int loadsSinceUnload;

        private static readonly Regex NamePattern = new Regex(@"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,79}$");
        private static readonly Regex DmPattern = new Regex(@"^dm:(\d+)/(\d)$");
        private static readonly Regex ScenePattern = new Regex("\"saveScene\"\\s*:\\s*\"([^\"]*)\"");

        private sealed class Cached
        {
            public long Length;
            public DateTime WriteTimeUtc;
            public object State;
        }

        private static readonly Dictionary<string, Cached> Cache = new Dictionary<string, Cached>(StringComparer.OrdinalIgnoreCase);

        // DebugMod's SaveState.LoadImpl dereferences these without null checks; they exist once the gameplay HUD is built.
        private static readonly FieldInfo[] HudSingletons =
        {
            AccessTools.Field(typeof(DialogueBox), "_instance"),
            AccessTools.Field(typeof(DialogueYesNoBox), "_instance"),
            AccessTools.Field(typeof(QuestYesNoBox), "_instance"),
        };

        public static void Register()
        {
            Rpc.Register("savestate.save", Save);
            Rpc.Register("savestate.load", Load);
            Rpc.Register("savestate.list", args => List());
        }

        // ---- save ------------------------------------------------------------------------------------------------

        /// <summary>The savestate name: "name", or "state" for callers whose RPC helper already uses a parameter called
        /// name (brain/ssbot/ipc/oracle_link.py OracleLink.rpc).</summary>
        private static string NameArg(Dictionary<string, object> args) => Rpc.Str(args, "name") ?? Rpc.Str(args, "state");

        private static object Save(Dictionary<string, object> args)
        {
            var name = NameArg(args);
            if (name == null || !NamePattern.IsMatch(name))
                throw new ArgumentException("name must match [A-Za-z0-9][A-Za-z0-9_.-]{0,79}");
            if (!DebugModBridge.Resolve()) throw new InvalidOperationException(DebugModBridge.Error);
            if (HarnessRunner.Busy != null) throw new InvalidOperationException($"harness busy ({HarnessRunner.Busy})");
            if (DebugModBridge.LoadInProgress) throw new InvalidOperationException("a DebugMod savestate load is in progress");
            var gm = GameManager._instance;
            var hero = HeroController.UnsafeInstance;
            if (gm == null || hero == null) throw new InvalidOperationException("no game loaded (no GameManager or hero)");
            if (gm.GameState != GameState.PLAYING || gm.IsInSceneTransition || hero.cState.transitioning)
                throw new InvalidOperationException($"not in a steady gameplay state (GameState {gm.GameState}, transition {gm.IsInSceneTransition || hero.cState.transitioning})");
            var death = DeathState(hero, gm.playerData);
            if (death != null)
                throw new InvalidOperationException($"refusing to save a dead hero ({death}); LethalBlock should have prevented this death");

            var sw = System.Diagnostics.Stopwatch.StartNew();
            var state = DebugModBridge.Capture(name);
            var json = DebugModBridge.ToJson(state);
            Directory.CreateDirectory(Folder);
            var path = PathOf(name);
            var tmp = path + ".tmp" + Guards.SaveRedirect.Instance;
            File.WriteAllText(tmp, json, new UTF8Encoding(false));
            if (File.Exists(path)) File.Replace(tmp, path, null);
            else File.Move(tmp, path);
            var info = new FileInfo(path);
            Cache[name] = new Cached { Length = info.Length, WriteTimeUtc = info.LastWriteTimeUtc, State = state };

            var pd = gm.playerData;
            Core.Plugin.Log.LogInfo($"savestate.save '{name}': {gm.sceneName} at {hero.transform.position} -> {path} ({info.Length} B, {sw.ElapsedMilliseconds} ms)");
            Export.FrameExporter.Emit("harness", new Dictionary<string, object> { ["op"] = "savestate.save", ["name"] = name });
            return new Dictionary<string, object>
            {
                ["name"] = name,
                ["path"] = path,
                ["scene"] = gm.sceneName,
                ["pos"] = hero.transform.position,
                ["facing_right"] = hero.cState.facingRight,
                ["hp"] = pd != null ? pd.health : -1,
                ["silk"] = pd != null ? pd.silk : -1,
                ["bytes"] = info.Length,
                ["ms"] = sw.ElapsedMilliseconds,
            };
        }

        // ---- load ------------------------------------------------------------------------------------------------

        private static void Load(Dictionary<string, object> args, Rpc.Reply reply)
        {
            var name = NameArg(args);
            if (name == null) { reply.Fail("name is required"); return; }
            if (!DebugModBridge.Resolve()) { reply.Fail(DebugModBridge.Error); return; }
            var timeout = Rpc.Double(args, "timeout", DefaultTimeoutS);
            var force = Rpc.Bool(args, "force");
            object state;
            try
            {
                state = Resolve(name);
            }
            catch (Exception e)
            {
                reply.Fail(e.Message);
                return;
            }
            var gm = GameManager._instance;
            var death = DeathState(HeroController.UnsafeInstance, gm != null ? gm.playerData : null);
            if (death != null && !force)
            {
                reply.Fail(DeadRefusal(death));
                return;
            }
            HarnessRunner.Run("savestate.load", reply, op => LoadBody(op, name, state, timeout, force));
        }

        private static IEnumerator LoadBody(HarnessOp op, string name, object state, double timeoutS, bool force)
        {
            // DebugMod refuses while the hero is transitioning (SaveStateManager.LoadLockout); wait that out briefly.
            string why;
            while ((why = CannotStartLoad()) != null)
            {
                if (op.Clock.Elapsed.TotalSeconds > PreLoadWaitS)
                {
                    op.Error = "cannot load now: " + why;
                    yield break;
                }
                yield return null;
            }

            // Checked again right before DebugMod runs: the hero may have died during the wait above.
            var gmNow = GameManager._instance;
            var death = DeathState(HeroController.UnsafeInstance, gmNow != null ? gmNow.playerData : null);
            if (death != null)
            {
                if (!force)
                {
                    op.Error = DeadRefusal(death);
                    yield break;
                }
                Core.Plugin.Log.LogError($"savestate.load '{name}' with force over a DEAD hero ({death}): the load undoes a death that slipped past LethalBlock");
                Export.FrameExporter.Emit("harness", new Dictionary<string, object>
                {
                    ["op"] = "death_reset", ["name"] = name, ["death"] = death, ["scene"] = gmNow != null ? gmNow.sceneName : null,
                });
            }

            var startMs = op.Clock.ElapsedMilliseconds;
            var pump = new HarnessRunner.Pump();
            // If this body gives up (timeout, settle failure), DebugMod's load keeps running: keep brain input out of it.
            op.BusyWhile = () => !pump.Done || DebugModBridge.LoadInProgress;
            HarnessRunner.Start(pump.Run(DebugModBridge.LoadCoroutine(state)));
            while (!pump.Done)
            {
                if (op.Clock.Elapsed.TotalSeconds > timeoutS)
                {
                    op.Error = $"DebugMod load of '{name}' did not finish within {timeoutS:0.#} s";
                    yield break;
                }
                yield return null;
            }
            if (pump.Error != null)
            {
                op.Error = "DebugMod load failed: " + pump.Error.Message;
                yield break;
            }
            var dmMs = op.Clock.ElapsedMilliseconds - startMs;

            while ((why = NotSettled()) != null)
            {
                if (op.Clock.Elapsed.TotalSeconds > timeoutS)
                {
                    op.Error = $"load of '{name}' did not settle within {timeoutS:0.#} s: {why}";
                    yield break;
                }
                yield return null;
            }
            var settledMs = op.Clock.ElapsedMilliseconds;
            // Controllable from here on in most rooms; a state saved in a scripted moment may never accept input.
            for (var i = 0; i < HeroInputGraceFrames; i++)
            {
                var h = HeroController.UnsafeInstance;
                if (h == null || h.acceptingInput) break;
                yield return null;
            }

            long unloadMs = -1;
            if (++loadsSinceUnload >= UnloadEvery)
            {
                loadsSinceUnload = 0;
                var t0 = op.Clock.ElapsedMilliseconds;
                var unload = Resources.UnloadUnusedAssets();
                while (!unload.isDone && (op.Clock.ElapsedMilliseconds - t0) < UnloadTimeoutS * 1000)
                    yield return null;
                unloadMs = op.Clock.ElapsedMilliseconds - t0;
            }

            var gm = GameManager._instance;
            var hero = HeroController.UnsafeInstance;
            if (gm == null || hero == null)
            {
                op.Error = "game unloaded right after the savestate load";
                yield break;
            }
            var pd = gm.playerData;
            var ms = op.Clock.ElapsedMilliseconds;
            Core.Plugin.Log.LogInfo($"savestate.load '{name}': {gm.sceneName} in {ms} ms (DebugMod {dmMs} ms, settled at {settledMs} ms)");
            Export.FrameExporter.Emit("harness", new Dictionary<string, object> { ["op"] = "savestate.load", ["name"] = name, ["ms"] = ms });
            op.Result = new Dictionary<string, object>
            {
                ["name"] = name,
                ["scene"] = gm.sceneName,
                ["ms"] = ms,
                ["dm_ms"] = dmMs,
                ["settle_ms"] = ms - startMs - dmMs,
                ["unload_ms"] = unloadMs,                   // -1: no unused-asset unload on this load
                ["frames"] = Time.frameCount - op.StartFrame,
                ["frame"] = (long)Time.frameCount,
                ["pos"] = hero.transform.position,
                ["facing_right"] = hero.cState.facingRight,
                ["hp"] = pd != null ? pd.health : -1,
                ["silk"] = pd != null ? pd.silk : -1,
                ["hero_input"] = hero.acceptingInput,
                ["time_scale"] = Time.timeScale,
                ["safe_loading"] = DebugModBridge.SafeLoading,
                ["death_reset"] = death != null,
            };
        }

        /// <summary>Why the hero counts as dead (null when alive or when there is no hero, e.g. at the title screen, where
        /// PlayerData is not a run's): the death coroutine has started (cState.dead), the Steel Soul death is already in
        /// memory (permadeathMode Dead), or health reached 0.</summary>
        private static string DeathState(HeroController hero, PlayerData pd)
        {
            if (hero == null) return null;
            string why = null;
            if (hero.cState.dead) why = "cState.dead";
            if (pd != null && pd.permadeathMode == PermadeathModes.Dead) why = (why == null ? "" : why + ", ") + "permadeathMode Dead";
            if (pd != null && pd.health <= 0) why = (why == null ? "" : why + ", ") + "hp " + pd.health;
            return why;
        }

        private static string DeadRefusal(string death) =>
            $"the hero is dead ({death}), a death LethalBlock did not stop; savestate.load will not quietly undo it. " +
            "Pass force=true to reset anyway (logged as an error and reported as a 'harness' death_reset event)";

        private static string CannotStartLoad()
        {
            var gm = GameManager._instance;
            var hero = HeroController.UnsafeInstance;
            if (gm == null || hero == null) return "no game loaded (load a save first; DebugMod cannot load from the title screen)";
            if (gm.GameState == GameState.MAIN_MENU) return "at the main menu";
            if (DebugModBridge.LoadInProgress) return "a DebugMod savestate load is in progress";
            if (hero.cState.transitioning || gm.IsInSceneTransition) return "scene transition in progress";
            foreach (var f in HudSingletons)
                if (f != null && f.GetValue(null) as UnityEngine.Object == null) return f.DeclaringType.Name + " not created yet";
            return null;
        }

        private static string NotSettled()
        {
            if (DebugModBridge.LoadInProgress) return "DebugMod still loading";
            var gm = GameManager._instance;
            var hero = HeroController.UnsafeInstance;
            if (gm == null) return "no GameManager";
            if (hero == null) return "no hero";
            if (gm.GameState != GameState.PLAYING) return "GameState " + gm.GameState;
            if (gm.IsInSceneTransition) return "scene transition";
            if (!gm.HasFinishedEnteringScene) return "scene not entered";
            if (hero.cState.transitioning) return "hero transitioning";
            return null;
        }

        private static object Resolve(string name)
        {
            var dm = DmPattern.Match(name);
            if (dm.Success)
            {
                var state = DebugModBridge.FileState(int.Parse(dm.Groups[1].Value), int.Parse(dm.Groups[2].Value));
                return Alive(name, state ?? throw new FileNotFoundException($"DebugMod slot {name} is empty"));
            }
            if (!NamePattern.IsMatch(name)) throw new ArgumentException($"bad savestate name '{name}'");
            var path = PathOf(name);
            var info = new FileInfo(path);
            if (!info.Exists) throw new FileNotFoundException($"no savestate '{name}' ({path})");
            if (Cache.TryGetValue(name, out var c) && c.Length == info.Length && c.WriteTimeUtc == info.LastWriteTimeUtc)
                return Alive(name, c.State);
            var parsed = DebugModBridge.FromJson(File.ReadAllText(path));
            Cache[name] = new Cached { Length = info.Length, WriteTimeUtc = info.LastWriteTimeUtc, State = parsed };
            return Alive(name, parsed);
        }

        /// <summary>A state captured after a Steel Soul death (or at 0 HP) would load a dead run: refuse it.</summary>
        private static object Alive(string name, object state)
        {
            var pd = DebugModBridge.SavedPlayerData(state);
            if (pd == null) throw new InvalidDataException($"savestate '{name}' has no player data");
            if (pd.permadeathMode == PermadeathModes.Dead || pd.health <= 0)
                throw new InvalidDataException($"savestate '{name}' was captured dead (permadeathMode {pd.permadeathMode}, hp {pd.health}); refusing to load it");
            return state;
        }

        private static string PathOf(string name) => Path.Combine(Folder, name + ".json");

        // ---- list ------------------------------------------------------------------------------------------------

        private static object List()
        {
            var ours = new List<object>();
            if (Directory.Exists(Folder))
            {
                foreach (var path in Directory.GetFiles(Folder, "*.json"))
                {
                    var info = new FileInfo(path);
                    var name = Path.GetFileNameWithoutExtension(path);
                    ours.Add(new Dictionary<string, object>
                    {
                        ["name"] = name,
                        ["scene"] = ReadScene(path),
                        ["bytes"] = info.Length,
                        ["mtime"] = info.LastWriteTimeUtc.ToString("o"),
                        ["cached"] = Cache.ContainsKey(name),
                    });
                }
            }
            var dm = new List<object>();
            if (DebugModBridge.Resolve())
            {
                for (var page = 0; page < DebugModBridge.FilePages; page++)
                    for (var slot = 0; slot < 10; slot++)
                    {
                        var state = DebugModBridge.FileState(page, slot);
                        if (state == null) continue;
                        dm.Add(new Dictionary<string, object>
                        {
                            ["name"] = $"dm:{page}/{slot}",
                            ["id"] = DebugModBridge.Identifier(state),
                            ["scene"] = DebugModBridge.Scene(state),
                        });
                    }
            }
            return new Dictionary<string, object>
            {
                ["folder"] = Folder,
                ["states"] = ours,
                ["debugmod"] = dm,
                ["debugmod_error"] = DebugModBridge.Error,
                ["debugmod_version"] = DebugModBridge.Version,
            };
        }

        /// <summary>saveScene is the second field DebugMod writes, so the first few KB of the file are enough.</summary>
        private static string ReadScene(string path)
        {
            try
            {
                using (var r = new StreamReader(path, Encoding.UTF8))
                {
                    var buf = new char[4096];
                    var n = r.Read(buf, 0, buf.Length);
                    var m = ScenePattern.Match(new string(buf, 0, n));
                    return m.Success ? m.Groups[1].Value : null;
                }
            }
            catch (IOException)
            {
                return null;
            }
        }
    }
}
