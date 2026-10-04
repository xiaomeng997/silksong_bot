using System;
using System.Collections.Generic;
using System.Reflection;
using BepInEx.Bootstrap;

namespace SsOracle.Train
{
    /// <summary>
    /// RPC "time.scale" {scale} (2026-10-04, the person asked for half-speed manual practice of the Forum): slows or
    /// speeds the whole game. Only where the profile allows cheats (training copy); never part of the formal read-only
    /// run. Returns {scale, time_scale, via, debugmod_scale}. No argument: the current scale.
    ///
    /// scale &lt; 1 holds one of the game's own multiplicative <c>TimeManager.TimeControlInstance</c>s (1.0.30000
    /// TimeManager.cs), so the game's freezes and slow motions still compose with it. That path cannot speed up:
    /// TimeManager.UpdateTimeScale clamps any product above 1 to 1 unless CheatManager.IsCheatsEnabled, which is a
    /// constant false in the release build (CheatManager.cs:215; seen live 2026-10-04: scale 2 gave Time.timeScale 1).
    /// scale &gt; 1 (Forum plan R1, data collection at 2x) therefore goes through DebugMod's own TimeScale
    /// (DebugMod.MonoBehaviours.TimeScale.CustomTimeScale, by reflection): DebugMod patches IsCheatsEnabled true for the
    /// duration of UpdateTimeScale when its scale is above 1, and IL-hooks GameManager's FreezeMoment / SetTimeScale
    /// coroutines so their real-time waits shrink with the speed (a hit-stop or the battle-end slow motion then spans
    /// the same game-time share as at 1x; with only the clamp lifted they would last the same real time and so twice
    /// the share of a 2x run). Setting one path resets the other to 1, so the two never multiply.
    /// </summary>
    internal static class TimeScaleRpc
    {
        private static TimeManager.TimeControlInstance control;
        private static PropertyInfo dmScale;
        private static string dmError;

        public static void Register() => Ipc.Rpc.Register("time.scale", Set);

        /// <summary>DebugMod's TimeScale.CustomTimeScale (static float property), or null with dmError set.</summary>
        private static PropertyInfo DebugModScale()
        {
            if (dmScale != null) return dmScale;
            try
            {
                if (!Chainloader.PluginInfos.TryGetValue(DebugModBridge.Guid, out var info) || info?.Instance == null)
                {
                    dmError = "DebugMod is not loaded";
                    return null;
                }
                var t = info.Instance.GetType().Assembly.GetType("DebugMod.MonoBehaviours.TimeScale");
                var p = t?.GetProperty("CustomTimeScale", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static);
                if (p == null || p.PropertyType != typeof(float) || !p.CanRead || !p.CanWrite)
                {
                    dmError = "DebugMod.MonoBehaviours.TimeScale.CustomTimeScale not found";
                    return null;
                }
                dmScale = p;
                dmError = null;
                return p;
            }
            catch (Exception e)
            {
                dmError = e.GetType().Name + ": " + e.Message;
                return null;
            }
        }

        private static double DebugModValue()
        {
            var p = DebugModScale();
            return p != null ? (double)(float)p.GetValue(null) : 1.0;
        }

        private static void SetDebugMod(float s)
        {
            var p = DebugModScale();
            if (p == null)
            {
                if (s > 1f) throw new InvalidOperationException("scale > 1 needs DebugMod's TimeScale: " + dmError);
                return;
            }
            if (Math.Abs((float)p.GetValue(null) - s) > 1e-4f) p.SetValue(null, s);
        }

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
                try
                {
                    if (s > 1f + 1e-4f)
                    {
                        control?.Release();
                        control = null;
                        SetDebugMod(s);
                    }
                    else
                    {
                        SetDebugMod(1f);
                        if (Math.Abs(s - 1f) < 1e-4f)
                        {
                            control?.Release();
                            control = null;
                        }
                        else if (control == null)
                            control = new TimeManager.TimeControlInstance(s, TimeManager.TimeControlInstance.Type.Multiplicative);
                        else
                            control.TimeScale = s;
                    }
                }
                catch (Exception e)
                {
                    reply.Fail(e.Message);
                    return;
                }
                Core.Plugin.Log.LogInfo($"time.scale {s:0.00}");
            }
            var dm = DebugModValue();
            var mine = control != null ? (double)control.TimeScale : 1.0;
            reply.Ok(new Dictionary<string, object>
            {
                ["scale"] = mine * dm,
                ["time_scale"] = (double)UnityEngine.Time.timeScale,
                ["via"] = dm > 1.0 + 1e-4 ? "debugmod" : control != null ? "game" : "none",
                ["debugmod_scale"] = dm,
                ["debugmod_error"] = dmError,
            });
        }
    }
}
