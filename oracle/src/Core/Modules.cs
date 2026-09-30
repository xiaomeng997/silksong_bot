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
            Export.BasicExporters.Register();
        }
    }
}
