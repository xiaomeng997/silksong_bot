using System;
using System.Collections.Generic;
using HarmonyLib;
using UnityEngine;
using Rpc = SsOracle.Ipc.Rpc;

namespace SsOracle.Input
{
    /// <summary>
    /// Input-side harness (DESIGN §3.1.1 Input, §3.9.2 InputPathEmulator, §4.6): the legacy anyKeyDown shim and the RPCs
    ///   input.latency_model {delay_frames, jitter_frames, seed, dist?: [[frames, weight], ...],
    ///                        min_press_frames?, min_release_frames?}  -> the active model (no args = query)
    ///   input.stats   -> scheduler, hold-filter, brain-lost and legacy-shim counters
    ///   input.release -> release every key and stop driving (disarms the brain-lost Pause; call before disconnecting)
    /// Emulation settings last for one brain connection; a new connection starts oracle-exact (0 delay, minimum press
    /// and release 2/2 frames as C19).
    /// </summary>
    internal static class InputModule
    {
        public static void Install(GameObject host, Harmony harmony)
        {
            LegacyInputShim.Install(harmony);
            Rpc.Register("input.latency_model", SetLatencyModel);
            Rpc.Register("input.stats", args => Stats());
            Rpc.Register("input.release", args =>
            {
                ActionScheduler.StopDriving();
                return Stats();
            });
        }

        private static object SetLatencyModel(Dictionary<string, object> args)
        {
            if (args.ContainsKey("delay_frames") || args.ContainsKey("jitter_frames") || args.ContainsKey("seed") || args.ContainsKey("dist"))
            {
                List<KeyValuePair<int, double>> dist = null;
                if (args.TryGetValue("dist", out var d) && d != null)
                {
                    if (!(d is List<object> rows)) throw new ArgumentException("dist must be a list of [frames, weight]");
                    dist = new List<KeyValuePair<int, double>>(rows.Count);
                    foreach (var row in rows)
                    {
                        if (!(row is List<object> pair) || pair.Count != 2) throw new ArgumentException("dist must be a list of [frames, weight]");
                        dist.Add(new KeyValuePair<int, double>(Convert.ToInt32(pair[0]), Convert.ToDouble(pair[1])));
                    }
                }
                var error = ActionScheduler.ConfigureLatency(
                    (int)Rpc.Long(args, "delay_frames"), (int)Rpc.Long(args, "jitter_frames"),
                    unchecked((int)Rpc.Long(args, "seed")), dist);
                if (error != null) throw new ArgumentException(error);
            }
            if (args.ContainsKey("min_press_frames") || args.ContainsKey("min_release_frames"))
            {
                var f = KeyboardInjector.Filter;
                var press = (int)Rpc.Long(args, "min_press_frames", f.MinPressFrames);
                var release = (int)Rpc.Long(args, "min_release_frames", f.MinReleaseFrames);
                if (press < 1 || press > 30 || release < 1 || release > 30)
                    throw new ArgumentException("min_press_frames and min_release_frames must be in [1, 30]");
                f.SetLimits(press, release);
            }
            var result = ActionScheduler.DescribeLatency();
            result["min_press_frames"] = KeyboardInjector.Filter.MinPressFrames;
            result["min_release_frames"] = KeyboardInjector.Filter.MinReleaseFrames;
            Core.Plugin.Log.LogInfo("input.latency_model: " + Describe(result));
            return result;
        }

        private static Dictionary<string, object> Stats()
        {
            var s = ActionScheduler.Describe(Time.frameCount);
            s["hold"] = KeyboardInjector.DescribeFilter();
            s["requested"] = KeyboardInjector.RequestedMask;
            s["latched"] = KeyboardInjector.LatchedMask;
            s["owns_keyboard"] = KeyboardInjector.OwnsKeyboard;
            s["legacy"] = LegacyInputShim.Describe();
            return s;
        }

        private static string Describe(Dictionary<string, object> d)
        {
            var parts = new List<string>();
            foreach (var kv in d) parts.Add(kv.Key + "=" + (kv.Value is List<object> l ? l.Count + " bins" : Convert.ToString(kv.Value)));
            return string.Join(", ", parts.ToArray());
        }
    }
}
