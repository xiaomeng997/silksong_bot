using System;
using System.Collections.Generic;
using GlobalEnums;
using HarmonyLib;
using UnityEngine;

namespace SsOracle.Hero
{
    /// <summary>
    /// Self-state exporters (DESIGN §3.1.1 HeroExporter, CameraExporter, HudProbe): STATE keys "hero", "cam" and
    /// "hud", in that order, plus the schema RPCs the brain needs to decode them. No Harmony patches: everything
    /// is read at end-of-frame except the camera matrices, which come from Camera.onPreRender.
    /// </summary>
    internal static class HeroModule
    {
        public static void Install(GameObject host, Harmony harmony)
        {
            try
            {
                CStateSchema.Init();
            }
            catch (Exception e)
            {
                // Missing HeroControllerStates would be a SymbolCheck failure; keep the rest of the oracle alive.
                Core.Plugin.Log.LogError("cState schema failed: " + e);
            }
            RenderCapture.Install();

            Export.FrameExporter.Register(new HeroExporter());
            Export.FrameExporter.Register(new CameraExporter());
            Export.FrameExporter.Register(new HudProbe());

            Ipc.Rpc.Register("schema.cstate", args => CStateSchema.Describe());
            Ipc.Rpc.Register("schema.hero", args => Enums());
            Ipc.Rpc.Register("hud.dump", args => HudProbe.Dump(args));
        }

        /// <summary>RPC "schema.hero": names for the enum-valued ints in "hero", "cam" and "hud".</summary>
        private static object Enums() => new Dictionary<string, object>
        {
            ["hero_state"] = Enum.GetNames(typeof(ActorStates)),
            ["transition_state"] = Enum.GetNames(typeof(HeroTransitionState)),
            ["damage_mode"] = Enum.GetNames(typeof(DamageMode)),
            ["lock_state"] = FlagValues(typeof(HeroLockStates)),
            ["camera_mode"] = Enum.GetNames(typeof(CameraController.CameraMode)),
            ["hazard_respawn_facing"] = Enum.GetNames(typeof(HazardRespawnMarker.FacingDirection)),
            ["tool_binding"] = Enum.GetNames(typeof(AttackToolBinding)),
            ["cstate"] = CStateSchema.Ready ? CStateSchema.Describe() : null,
        };

        private static Dictionary<string, object> FlagValues(Type t)
        {
            var d = new Dictionary<string, object>();
            foreach (var v in Enum.GetValues(t)) d[Enum.GetName(t, v)] = Convert.ToInt64(v);
            return d;
        }
    }
}
