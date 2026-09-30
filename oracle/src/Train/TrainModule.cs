using HarmonyLib;
using UnityEngine;

namespace SsOracle.Train
{
    /// <summary>
    /// Training harness (DESIGN §3.1.1 Harness): savestate bridge to DebugMod and randomized episode starts. Registers
    /// savestate.save / savestate.load / savestate.list and randomize_start; multi-frame operations run on HarnessRunner.
    /// Also the projection calibration against DebugMod's hitbox display (DESIGN §3.1.3): hitbox.show, projection.sample.
    /// </summary>
    internal static class TrainModule
    {
        public static void Install(GameObject host, Harmony harmony)
        {
            HarnessRunner.Install(host);
            SavestateBridge.Register();
            StartRandomizer.Register();
            ProjectionSample.Install(host);
        }
    }
}
