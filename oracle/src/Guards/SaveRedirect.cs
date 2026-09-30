using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Reflection.Emit;
using HarmonyLib;
using UnityEngine;

namespace SsOracle.Guards
{
    /// <summary>
    /// Moves every save of the training copy (user*.dat, backups, Restore_Points, shared.dat) out of the
    /// real LocalLow folder into C:\ssbot\sandbox\saves\&lt;instance&gt;\. DesktopPlatform.Awake derives all of
    /// these from Application.persistentDataPath; the transpiler swaps that one call for the sandbox root.
    /// This keeps the real "default" folder empty, which matters because the final copy silently falls
    /// back to it when Steam fails to initialize (m0:N28), so anything appearing there is an alarm.
    ///
    /// Two more writers use Application.persistentDataPath directly and are redirected into the same root
    /// (found by the M1 soak write check, 2026-09-30):
    ///  - ConfigManager (AppConfig.ini): LoadConfig reads the file and always writes it back, on every launch
    ///    once the platform becomes current. LoadConfig/SaveConfig read the static _path; the transpiler swaps
    ///    those loads for &lt;root&gt;\AppConfig.ini.
    ///  - DebugMod (training only): DebugModData\ (Settings.json, "Savestates 1.0", "Savestate Packs"). DebugMod
    ///    loads before this plugin, so its Awake has already run LoadSettings (Directory.CreateDirectory on the
    ///    real path, a no-op once it exists, and a read). Every DebugMod method that loads one of its three path
    ///    fields is transpiled to &lt;root&gt;\DebugModData\..., so nothing it writes afterwards leaves the sandbox.
    /// </summary>
    internal static class SaveRedirect
    {
        public const string SandboxBase = @"C:\ssbot\sandbox\saves";

        /// <summary>Instance id from "-ssbot-instance N" on the command line; "0" when absent.</summary>
        public static readonly string Instance = ReadInstance();

        public static string SandboxRoot => Path.Combine(SandboxBase, Instance);

        private static bool redirected;
        private static bool configRedirected;
        private static int debugModMethods = -1;

        private static readonly FieldInfo ConfigPathField = AccessTools.Field(typeof(ConfigManager), "_path");
        private static readonly Dictionary<FieldInfo, MethodInfo> DebugModFields = new Dictionary<FieldInfo, MethodInfo>();

        public static string AppConfigPath => Path.Combine(SandboxRoot, "AppConfig.ini");
        public static string DebugModRoot => Path.Combine(SandboxRoot, "DebugModData");

        /// <summary>How many DebugMod methods now use the sandbox (-1: DebugMod not loaded).</summary>
        public static int DebugModMethodsRedirected => debugModMethods;

        /// <summary>True once DesktopPlatform.Awake took the sandbox root: every save file of this process is a sandbox
        /// file (tools that edit PlayerData check it, since the edit reaches disk with the next save).</summary>
        public static bool Redirected => redirected;

        public static void Install(Harmony harmony)
        {
            var awake = AccessTools.Method(typeof(DesktopPlatform), "Awake");
            harmony.Patch(awake, transpiler: new HarmonyMethod(typeof(SaveRedirect), nameof(Transpiler)));

            var configTranspiler = new HarmonyMethod(typeof(SaveRedirect), nameof(ConfigTranspiler));
            foreach (var name in new[] { "LoadConfig", "SaveConfig" })
                harmony.Patch(AccessTools.Method(typeof(ConfigManager), name), transpiler: configTranspiler);

            RedirectDebugMod(harmony);
        }

        /// <summary>Called from Plugin once the game is running: fails loudly if the patch never took effect.</summary>
        public static bool Verify()
        {
            if (!redirected)
                Core.Plugin.Log.LogError("SaveRedirect did not run: DesktopPlatform.Awake ran before the patch; saves may go to LocalLow!");
            if (!configRedirected)
                Core.Plugin.Log.LogError("SaveRedirect: ConfigManager has not used the sandbox AppConfig.ini; LoadConfig may have written to LocalLow before the patch");
            return redirected;
        }

        // ---- ConfigManager ------------------------------------------------------------------------------------

        private static IEnumerable<CodeInstruction> ConfigTranspiler(IEnumerable<CodeInstruction> instructions, MethodBase original)
        {
            var getter = AccessTools.Method(typeof(SaveRedirect), nameof(ConfigPath));
            var swapped = 0;
            foreach (var ins in instructions)
            {
                if (ins.opcode == OpCodes.Ldsfld && Equals(ins.operand, ConfigPathField))
                {
                    swapped++;
                    yield return new CodeInstruction(OpCodes.Call, getter).WithLabels(ins.labels).WithBlocks(ins.blocks);
                    continue;
                }
                yield return ins;
            }
            if (swapped == 0)
                Core.Plugin.Log.LogError($"SaveRedirect: no ConfigManager._path load in {original?.Name}; AppConfig.ini stays in LocalLow");
        }

        private static string ConfigPath()
        {
            if (!configRedirected)
            {
                configRedirected = true;
                Directory.CreateDirectory(SandboxRoot);
                Core.Plugin.Log.LogInfo($"SaveRedirect: AppConfig.ini for instance {Instance} is {AppConfigPath}");
            }
            return AppConfigPath;
        }

        // ---- DebugMod -----------------------------------------------------------------------------------------

        private static void RedirectDebugMod(Harmony harmony)
        {
            Assembly asm = null;
            foreach (var a in AppDomain.CurrentDomain.GetAssemblies())
            {
                if (a.GetName().Name == "DebugMod")
                {
                    asm = a;
                    break;
                }
            }
            if (asm == null) return;  // not installed

            Map(asm.GetType("DebugMod.DebugMod"), "ModBaseDirectory", nameof(DebugModBase));
            var states = asm.GetType("DebugMod.SaveStates.SaveStateManager");
            Map(states, "saveStatesBaseDirectory", nameof(DebugModSaveStates));
            Map(states, "packsBaseDirectory", nameof(DebugModPacks));
            if (DebugModFields.Count == 0) return;

            var transpiler = new HarmonyMethod(typeof(SaveRedirect), nameof(DebugModTranspiler));
            const BindingFlags All = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static | BindingFlags.DeclaredOnly;
            Type[] types;
            try { types = asm.GetTypes(); }
            catch (ReflectionTypeLoadException e) { types = Array.FindAll(e.Types, t => t != null); }
            var patched = 0;
            foreach (var t in types)
            {
                var methods = new List<MethodBase>(t.GetMethods(All));
                foreach (var c in t.GetConstructors(All))
                {
                    if (!c.IsStatic) methods.Add(c);  // the type initializers only compute the fields replaced here
                }
                foreach (var m in methods)
                {
                    if (m.IsAbstract || m.ContainsGenericParameters || m.GetMethodBody() == null || !LoadsDebugModPath(m)) continue;
                    try
                    {
                        harmony.Patch(m, transpiler: transpiler);
                        patched++;
                    }
                    catch (Exception e)
                    {
                        Core.Plugin.Log.LogError($"SaveRedirect: could not redirect DebugMod {t.Name}.{m.Name}: {e.Message}");
                    }
                }
            }
            debugModMethods = patched;
            Core.Plugin.Log.LogInfo($"SaveRedirect: DebugMod data for instance {Instance} goes to {DebugModRoot} ({patched} methods redirected)");
        }

        private static void Map(Type t, string field, string getter)
        {
            var f = t != null ? AccessTools.Field(t, field) : null;
            if (f == null)
            {
                Core.Plugin.Log.LogError($"SaveRedirect: DebugMod field {t?.Name}.{field} not found; its data may go to LocalLow");
                return;
            }
            DebugModFields[f] = AccessTools.Method(typeof(SaveRedirect), getter);
        }

        private static bool LoadsDebugModPath(MethodBase m)
        {
            try
            {
                foreach (var ins in PatchProcessor.GetOriginalInstructions(m))
                {
                    if (ins.opcode == OpCodes.Ldsfld && ins.operand is FieldInfo f && DebugModFields.ContainsKey(f))
                        return true;
                }
            }
            catch (Exception)
            {
                // A body Harmony cannot read is not one it can patch either.
            }
            return false;
        }

        private static IEnumerable<CodeInstruction> DebugModTranspiler(IEnumerable<CodeInstruction> instructions)
        {
            foreach (var ins in instructions)
            {
                if (ins.opcode == OpCodes.Ldsfld && ins.operand is FieldInfo f && DebugModFields.TryGetValue(f, out var getter))
                {
                    yield return new CodeInstruction(OpCodes.Call, getter).WithLabels(ins.labels).WithBlocks(ins.blocks);
                    continue;
                }
                yield return ins;
            }
        }

        private static string DebugModBase() => DebugModRoot;
        private static string DebugModSaveStates() => Path.Combine(DebugModRoot, "Savestates 1.0");
        private static string DebugModPacks() => Path.Combine(DebugModRoot, "Savestate Packs");

        private static IEnumerable<CodeInstruction> Transpiler(IEnumerable<CodeInstruction> instructions)
        {
            var getter = AccessTools.PropertyGetter(typeof(Application), nameof(Application.persistentDataPath));
            var replacement = AccessTools.Method(typeof(SaveRedirect), nameof(PersistentDataPath));
            var swapped = 0;
            foreach (var ins in instructions)
            {
                if (ins.Calls(getter))
                {
                    swapped++;
                    yield return new CodeInstruction(OpCodes.Call, replacement).WithLabels(ins.labels);
                    continue;
                }
                yield return ins;
            }
            if (swapped != 1)
                Core.Plugin.Log.LogError($"SaveRedirect expected 1 persistentDataPath call in DesktopPlatform.Awake, found {swapped}");
        }

        private static string PersistentDataPath()
        {
            Directory.CreateDirectory(SandboxRoot);
            redirected = true;
            Core.Plugin.Log.LogInfo($"SaveRedirect: saves for instance {Instance} go to {SandboxRoot}");
            return SandboxRoot;
        }

        private static string ReadInstance()
        {
            var args = Environment.GetCommandLineArgs();
            for (var i = 0; i < args.Length - 1; i++)
            {
                if (args[i] == "-ssbot-instance")
                    return args[i + 1];
            }
            return "0";
        }
    }
}
