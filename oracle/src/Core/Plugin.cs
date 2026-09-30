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
        public const string Version = "0.0.1";
        public const string ExpectedGameVersion = "1.0.30000";

        internal static ManualLogSource Log;

        private Ipc.Server server;

        private void OnDestroy() => server?.Stop();

        private void Awake()
        {
            Log = Logger;

            // Constants.GAME_VERSION is a const and would be inlined at compile time, so read it from the loaded assembly.
            var field = typeof(Constants).GetField("GAME_VERSION", BindingFlags.Public | BindingFlags.Static);
            var gameVersion = field?.GetRawConstantValue() as string;
            if (gameVersion != ExpectedGameVersion)
            {
                Log.LogError($"Game version {gameVersion ?? "<unknown>"} != pinned {ExpectedGameVersion}; SsOracle disabled.");
                enabled = false;
                return;
            }

            var harmony = new Harmony(Guid);
            Guards.SaveRedirect.Install(harmony);
            TrainingEnvironment.Install(gameObject, harmony);
            Input.KeyboardInjector.Install();
            gameObject.AddComponent<MainThread>();
            gameObject.AddComponent<Export.StateProbe>();
            server = new Ipc.Server(Ipc.Server.DefaultPort);
            server.Start();
            Log.LogInfo($"{Name} {Version} loaded: game {gameVersion}, Unity {Application.unityVersion}");
        }
    }
}
