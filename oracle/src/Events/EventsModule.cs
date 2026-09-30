using HarmonyLib;
using UnityEngine;

namespace SsOracle.Events
{
    /// <summary>
    /// M1 package events-scene-progress: EventTap hooks (STATE "ev" + "tap"), SceneDumper (TERRAIN + "room",
    /// RPC scene.dump) and ProgressExporter (PROGRESS + "prog", RPC progress.full). Everything here observes;
    /// nothing changes game behaviour (the guards package owns blocking and suppression).
    /// </summary>
    internal static class EventsModule
    {
        public static void Install(GameObject host, Harmony harmony)
        {
            Tap.Init();
            HpTap.Install(harmony);
            DamageTap.Install(harmony);
            GateTap.Install(harmony);
            FreezeTap.Install(harmony);
            FlowTap.Install(harmony);
            HunterMeterTap.Install(harmony);
            host.AddComponent<EventsRunner>();
            Export.FrameExporter.Register(new TapExporter());

            SceneDump.SceneDumper.Install(host);
            Progress.ProgressExporter.Install(host);

            if (Tap.FailedHooks > 0)
                Core.Plugin.Log.LogError($"EventTap: {Tap.FailedHooks} hook(s) failed to install; their events will be missing");
            else
                Core.Plugin.Log.LogInfo("EventTap, SceneDumper and ProgressExporter installed");
        }
    }
}
