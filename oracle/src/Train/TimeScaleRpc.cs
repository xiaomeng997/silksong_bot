using System;
using System.Collections.Generic;

namespace SsOracle.Train
{
    /// <summary>
    /// RPC "time.scale" {scale} (2026-10-04, the person asked for half-speed manual practice of the Forum): slows or
    /// speeds the whole game by holding one of the game's own multiplicative <c>TimeManager.TimeControlInstance</c>s
    /// (1.0.30000 TimeManager.cs), so the game's freezes and slow motions still compose with it. scale 1 releases it.
    /// Only where the profile allows cheats (training copy); never part of the formal read-only run. Returns
    /// {scale, time_scale}. No argument: the current scale.
    /// </summary>
    internal static class TimeScaleRpc
    {
        private static TimeManager.TimeControlInstance control;

        public static void Register() => Ipc.Rpc.Register("time.scale", Set);

        private static void Set(Dictionary<string, object> args, Ipc.Rpc.Reply reply)
        {
            if (args.ContainsKey("scale"))
            {
                if (!Core.Profile.Rules.CheatsAllowed)
                {
                    reply.Fail($"time.scale is disabled in profile {Core.Profile.Current}");
                    return;
                }
                var s = (float)Ipc.Rpc.Double(args, "scale", 1.0);
                if (!(s > 0f && s <= 4f))
                {
                    reply.Fail("scale must be in (0, 4]");
                    return;
                }
                if (Math.Abs(s - 1f) < 1e-4f)
                {
                    control?.Release();
                    control = null;
                }
                else if (control == null)
                    control = new TimeManager.TimeControlInstance(s, TimeManager.TimeControlInstance.Type.Multiplicative);
                else
                    control.TimeScale = s;
                Core.Plugin.Log.LogInfo($"time.scale {s:0.00}");
            }
            reply.Ok(new Dictionary<string, object>
            {
                ["scale"] = control != null ? (double)control.TimeScale : 1.0,
                ["time_scale"] = (double)UnityEngine.Time.timeScale,
            });
        }
    }
}
