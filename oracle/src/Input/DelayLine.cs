using System;
using System.Collections.Generic;

namespace SsOracle.Input
{
    /// <summary>
    /// The ACTION queue between the IPC reader and the key latch (DESIGN §4.6, §3.9.2 InputPathEmulator): an ACTION
    /// takes effect at max(target_frame, arrival frame) + the sampled path delay, ACTIONs more than MaxLateFrames past
    /// their target on arrival are dropped, and ACTIONs never overtake each other (running maximum of the effective
    /// frame, kept across latency changes: an edge already on the wire is not re-timed). Several ACTIONs may fall due
    /// in one frame; the caller applies every one of them in arrival order (their edges go into the HoldFilter), none
    /// is dropped for being superseded. Pure logic (no Unity), main thread only.
    /// </summary>
    internal sealed class DelayLine
    {
        public struct Item
        {
            public long TargetFrame;
            public long EffectiveFrame;
            public uint Buttons;
            public int HoldFrames;
            public uint AckSeq;
        }

        public const int MaxLateFrames = 3;

        private readonly Queue<Item> pending = new Queue<Item>();
        private long lastEffective = long.MinValue;

        public int Count => pending.Count;

        /// <summary>Queue <paramref name="a"/> arriving at <paramref name="frame"/>; false (and no delay drawn) when it
        /// is stale. Delays are drawn in arrival order, one per accepted ACTION.</summary>
        public bool Accept(ref Item a, long frame, LatencyModel latency)
        {
            if (a.TargetFrame < frame - MaxLateFrames) return false;
            // The emulated path adds its delay to the moment the action exists (target, or arrival when late), and
            // edges never overtake each other on a real wire, hence the running maximum.
            var effective = Math.Max(a.TargetFrame, frame) + latency.Sample();
            if (effective < lastEffective) effective = lastEffective;
            lastEffective = effective;
            a.EffectiveFrame = effective;
            pending.Enqueue(a);
            return true;
        }

        /// <summary>The oldest ACTION due at <paramref name="frame"/>, if any. Effective frames never decrease along
        /// the queue, so the due ones are exactly its head.</summary>
        public bool TryTakeDue(long frame, out Item a)
        {
            if (pending.Count > 0 && pending.Peek().EffectiveFrame <= frame)
            {
                a = pending.Dequeue();
                return true;
            }
            a = default;
            return false;
        }

        /// <summary>Drop everything queued (brain gone, input.release, harness operation).</summary>
        public void Clear()
        {
            pending.Clear();
            lastEffective = long.MinValue;
        }
    }
}
