using System.Reflection;
using BepInEx;
using BepInEx.Logging;
using HarmonyLib;
using UnityEngine;

namespace SsOracle.Core
{
    [BepInPlugin(Guid, Name, Version)]
    public sealed class Plugin : BaseUnityPlugin
    {
        public const string Guid = "ssbot.oracle";
        public const string Name = "SsOracle";
        public const string Version = "0.1.0";
        public const string ExpectedGameVersion = "1.0.30000";

        internal static ManualLogSource Log;
        internal static string GameVersion { get; private set; }

        private Ipc.DebugServer debugServer;

        private void OnDestroy() => debugServer?.Stop();

        private void Awake()
        {
            Log = Logger;

            // Constants.GAME_VERSION is a const and would be inlined at compile time, so read it from the loaded assembly.
            var field = typeof(Constants).GetField("GAME_VERSION", BindingFlags.Public | BindingFlags.Static);
            GameVersion = field?.GetRawConstantValue() as string;
            if (GameVersion != ExpectedGameVersion)
            {
                Log.LogError($"Game version {GameVersion ?? "<unknown>"} != pinned {ExpectedGameVersion}; SsOracle disabled.");
                enabled = false;
                return;
            }

            var harmony = new Harmony(Guid);
            Guards.SaveRedirect.Install(harmony);
            TrainingEnvironment.Install(gameObject, harmony);
            Input.KeyboardInjector.Install();
            gameObject.AddComponent<MainThread>();
            gameObject.AddComponent<Export.StateProbe>();
            Modules.InstallAll(gameObject, harmony);
            gameObject.AddComponent<Export.FrameExporter>();
            Ipc.FramedServer.Install(gameObject, Guards.SaveRedirect.Instance);
            debugServer = new Ipc.DebugServer(Ipc.DebugServer.DefaultPort + Ipc.Protocol.Port(Guards.SaveRedirect.Instance) - Ipc.Protocol.BasePort);
            debugServer.Start();
            Log.LogInfo($"{Name} {Version} loaded: game {GameVersion}, Unity {Application.unityVersion}, instance {Guards.SaveRedirect.Instance}");
        }
    }
}
