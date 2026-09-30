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
    /// </summary>
    internal static class SaveRedirect
    {
        public const string SandboxBase = @"C:\ssbot\sandbox\saves";

        /// <summary>Instance id from "-ssbot-instance N" on the command line; "0" when absent.</summary>
        public static readonly string Instance = ReadInstance();

        public static string SandboxRoot => Path.Combine(SandboxBase, Instance);

        private static bool redirected;

        public static void Install(Harmony harmony)
        {
            var awake = AccessTools.Method(typeof(DesktopPlatform), "Awake");
            harmony.Patch(awake, transpiler: new HarmonyMethod(typeof(SaveRedirect), nameof(Transpiler)));
        }

        /// <summary>Called from Plugin once the game is running: fails loudly if the patch never took effect.</summary>
        public static bool Verify()
        {
            if (!redirected)
                Core.Plugin.Log.LogError("SaveRedirect did not run: DesktopPlatform.Awake ran before the patch; saves may go to LocalLow!");
            return redirected;
        }

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
