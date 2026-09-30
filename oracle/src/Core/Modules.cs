using HarmonyLib;
using UnityEngine;

namespace SsOracle.Core
{
    /// <summary>
    /// The one place where feature modules are wired in: exporters (FrameExporter.Register), guards (Harmony
    /// patches), harness RPCs (Ipc.Rpc.Register). Runs in Plugin.Awake before the IPC server starts, so the HELLO
    /// message lists every RPC. Order of exporters here = order of keys in STATE.
    /// </summary>
    internal static class Modules
    {
        public static void InstallAll(GameObject host, Harmony harmony)
        {
            Ipc.Rpc.Register("ping", args => "pong");

            // First: SymbolCheck's report precedes every patch error, and guard refusals are known before other
            // modules install (STATE "guards").
            Guards.GuardsModule.Install(host, harmony);
            if (RunMode.Human)
            {
                // A person is playing a normal game: deaths happen as in the vanilla game and are only recorded.
                Guards.GuardState.Lethal = Guards.LethalMode.Observe;
            }

            Export.BasicExporters.Register();              // game, pause, input
            Export.FrameMarker.Install(host);              // frame.marker (STATE "mk" is a base field)
            Hero.HeroModule.Install(host, harmony);        // hero, cam, hud
            Entities.EntitiesModule.Install(host, harmony); // ents; FSM transition events
            Events.EventsModule.Install(host, harmony);    // tap, room, prog; TERRAIN and PROGRESS messages
            Input.InputModule.Install(host, harmony);      // legacy anyKeyDown shim, latency model
            Train.TrainModule.Install(host, harmony);      // savestates, randomized starts
            Crest.CrestModule.Install(host, harmony);      // crest/attack dumps, crest.equip (P17)
        }
    }
}
