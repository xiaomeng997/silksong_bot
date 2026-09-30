using HarmonyLib;
using UnityEngine;

namespace SsOracle.Train
{
    /// <summary>
    /// Training harness (DESIGN §3.1.1 Harness): savestate bridge to DebugMod, randomized episode starts and ability
    /// grants for the sandbox save. Registers savestate.save / savestate.load / savestate.list, randomize_start and
    /// abilities.grant / abilities.list; multi-frame operations run on HarnessRunner.
    /// </summary>
    internal static class TrainModule
    {
        public static void Install(GameObject host, Harmony harmony)
        {
            HarnessRunner.Install(host);
            SavestateBridge.Register();
            StartRandomizer.Register();
            AbilityGrant.Register();
        }
    }
}
