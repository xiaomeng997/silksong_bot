using HarmonyLib;
using UnityEngine;

namespace SsOracle.Train
{
    /// <summary>
    /// Training harness (DESIGN §3.1.1 Harness): savestate bridge to DebugMod, randomized episode starts and ability
    /// grants for the sandbox save. Registers savestate.save / savestate.load / savestate.list, randomize_start and
    /// abilities.grant / abilities.list; multi-frame operations run on HarnessRunner.
    /// Also the projection calibration against DebugMod's hitbox display (DESIGN §3.1.3): hitbox.show, projection.sample.
    /// </summary>
    internal static class TrainModule
    {
        public static void Install(GameObject host, Harmony harmony)
        {
            HarnessRunner.Install(host);
            SavestateBridge.Register();
            StartRandomizer.Register();
            AbilityGrant.Register();
            TimeScaleRpc.Register();
            BattleWaveRpc.Register();
            EnemyHpRpc.Register();
            ProjectionSample.Install(host);
        }
    }
}
