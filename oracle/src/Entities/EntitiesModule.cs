using System.Collections.Generic;
using HarmonyLib;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace SsOracle.Entities
{
    /// <summary>
    /// Entities and FSMs (DESIGN §3.1.1 EntityRegistry + FsmTap, §3.1.2 entities[], §4.6 get_fsm_graph):
    /// STATE "ents", event "fsm", RPCs "fsm.graph", "fsmtap.set" and "ents.stats".
    /// </summary>
    internal static class EntitiesModule
    {
        public static void Install(GameObject host, Harmony harmony)
        {
            EntityRegistry.Install(harmony);
            FsmTap.Install(harmony);
            Export.FrameExporter.Register(new EntityExporter());

            SceneManager.sceneUnloaded += _ => EntityRegistry.MarkSceneChanged();
            SceneManager.activeSceneChanged += (_, __) => EntityRegistry.MarkSceneChanged();

            Ipc.Rpc.Register("fsm.graph", FsmGraph.Handle);
            Ipc.Rpc.Register("fsmtap.set", args =>
            {
                if (args.ContainsKey("all")) FsmTap.All = Ipc.Rpc.Bool(args, "all");
                if (args.ContainsKey("enabled")) FsmTap.Enabled = Ipc.Rpc.Bool(args, "enabled");
                return new Dictionary<string, object>
                {
                    ["enabled"] = FsmTap.Enabled,
                    ["all"] = FsmTap.All,
                    ["emitted"] = FsmTap.Emitted,
                    ["dropped"] = FsmTap.Dropped,
                    ["cached"] = FsmTap.CacheSize,
                };
            });
            Ipc.Rpc.Register("ents.stats", args => EntityRegistry.Stats());
        }
    }
}
