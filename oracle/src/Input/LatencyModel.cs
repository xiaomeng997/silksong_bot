using System;
using System.Collections.Generic;

namespace SsOracle.Input
{
    /// <summary>
    /// InputPathEmulator delay model (DESIGN §3.9.2 DelayLine/InputPathEmulator, §3.1.1 Input): how many frames an
    /// ACTION takes, on top of its target frame, to reach the game on the final input path (SendInput → next input
    /// poll). Either delay + uniform integer jitter in [-jitter, +jitter], or an explicit distribution of
    /// (frames, weight) pairs such as the loopback prior 2/3/4 frames weighted 0.3/0.5/0.2. Draws come from a
    /// System.Random seeded by the brain, one per ACTION in arrival order, so a replay with the same seed and the same
    /// action stream gets the same delays. Default: 0 frames (oracle-exact). Pure logic, main thread only.
    /// </summary>
    internal sealed class LatencyModel
    {
        public const int MaxDelayFrames = 60;

        private int[] distFrames;
        private double[] distCumulative;
        private Random rng = new Random(0);

        public int DelayFrames { get; private set; }
        public int JitterFrames { get; private set; }
        public int Seed { get; private set; }
        public int LastSample { get; private set; }
        public bool IsIdentity => DelayFrames == 0 && JitterFrames == 0 && distFrames == null;

        /// <summary>Replace the model; returns an error message or null. dist may be null (use delay/jitter).</summary>
        public string Configure(int delayFrames, int jitterFrames, int seed, IList<KeyValuePair<int, double>> dist)
        {
            if (delayFrames < 0 || delayFrames > MaxDelayFrames) return $"delay_frames must be in [0, {MaxDelayFrames}]";
            if (jitterFrames < 0 || jitterFrames > MaxDelayFrames) return $"jitter_frames must be in [0, {MaxDelayFrames}]";
            int[] frames = null;
            double[] cumulative = null;
            if (dist != null && dist.Count > 0)
            {
                frames = new int[dist.Count];
                cumulative = new double[dist.Count];
                var total = 0.0;
                for (var i = 0; i < dist.Count; i++)
                {
                    var k = dist[i].Key;
                    var w = dist[i].Value;
                    if (k < 0 || k > MaxDelayFrames) return $"dist frames must be in [0, {MaxDelayFrames}]";
                    if (!(w > 0) || double.IsInfinity(w)) return "dist weights must be positive";
                    total += w;
                    frames[i] = k;
                    cumulative[i] = total;
                }
                for (var i = 0; i < cumulative.Length; i++) cumulative[i] /= total;
                cumulative[cumulative.Length - 1] = 1.0;
            }
            DelayFrames = delayFrames;
            JitterFrames = jitterFrames;
            Seed = seed;
            distFrames = frames;
            distCumulative = cumulative;
            rng = new Random(seed);
            LastSample = 0;
            return null;
        }

        public void Reset() => Configure(0, 0, 0, null);

        /// <summary>Frames to add to one ACTION (>= 0).</summary>
        public int Sample()
        {
            int d;
            if (distFrames != null)
            {
                var u = rng.NextDouble();
                var i = 0;
                while (i < distCumulative.Length - 1 && u >= distCumulative[i]) i++;
                d = distFrames[i];
            }
            else if (JitterFrames > 0)
            {
                d = DelayFrames + rng.Next(-JitterFrames, JitterFrames + 1);
            }
            else
            {
                d = DelayFrames;
            }
            LastSample = d < 0 ? 0 : d;
            return LastSample;
        }

        /// <summary>The configuration as a plain map (RPC results).</summary>
        public Dictionary<string, object> Describe()
        {
            var d = new Dictionary<string, object>
            {
                ["delay_frames"] = DelayFrames,
                ["jitter_frames"] = JitterFrames,
                ["seed"] = Seed,
            };
            if (distFrames != null)
            {
                var list = new List<object>();
                var prev = 0.0;
                for (var i = 0; i < distFrames.Length; i++)
                {
                    list.Add(new List<object> { distFrames[i], distCumulative[i] - prev });
                    prev = distCumulative[i];
                }
                d["dist"] = list;
            }
            return d;
        }
    }
}
