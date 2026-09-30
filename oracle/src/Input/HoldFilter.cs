namespace SsOracle.Input
{
    /// <summary>
    /// Minimum press / release durations on the latched key set (DESIGN C19, m0:N37/N38). The Input System samples
    /// keys once per rendered frame, so a press and release inside one update is lost, and a re-press of the same key
    /// needs a sampled release in between. Every edge the caller asks for is kept and replayed in order: a release is
    /// held back until the key has been down for MinPressFrames latched frames, a press until it has been up for
    /// MinReleaseFrames. Left and right are never latched together (N41: MoveVector cancels but both IsPressed stay
    /// true), so a press of one waits for the release of the other. Pure logic (no Unity), main thread only.
    /// </summary>
    internal sealed class HoldFilter
    {
        public const int DefaultMinPressFrames = 2;
        public const int DefaultMinReleaseFrames = 1;

        /// <summary>Queued toggles per key beyond which the oldest press+release pair is dropped, so a caller that
        /// toggles faster than the limits allow cannot build up unbounded input lag.</summary>
        public const int MaxPendingToggles = 3;

        private const int Bits = 32;
        private const int Long = 1 << 20;

        private readonly uint exclusiveA, exclusiveB;
        private readonly int[] pending = new int[Bits];      // edges requested but not latched yet (they alternate)
        private readonly int[] age = new int[Bits];          // latched frames the key has been in its current state
        private readonly bool[] deferred = new bool[Bits];   // the next edge was already counted as deferred
        private readonly bool[] exclusiveWaiting = new bool[Bits];
        private uint desired, latched;

        public int MinPressFrames { get; private set; } = DefaultMinPressFrames;
        public int MinReleaseFrames { get; private set; } = DefaultMinReleaseFrames;

        /// <summary>Releases held back to reach the minimum press (one count per deferred edge).</summary>
        public long HoldsExtended { get; private set; }
        /// <summary>Presses held back to reach the minimum release gap.</summary>
        public long PressesDeferred { get; private set; }
        /// <summary>Presses held back because the opposite direction was still latched.</summary>
        public long ExclusiveDeferred { get; private set; }
        /// <summary>Press+release pairs dropped (queue overflow, or a tap that could never be latched).</summary>
        public long TapsCollapsed { get; private set; }

        public uint Desired => desired;
        public uint Latched => latched;

        public HoldFilter(uint exclusiveA, uint exclusiveB)
        {
            this.exclusiveA = exclusiveA;
            this.exclusiveB = exclusiveB;
            for (var i = 0; i < Bits; i++) age[i] = Long;
        }

        public int PendingToggles
        {
            get
            {
                var n = 0;
                for (var i = 0; i < Bits; i++) n += pending[i];
                return n;
            }
        }

        public void SetLimits(int minPressFrames, int minReleaseFrames)
        {
            MinPressFrames = minPressFrames < 1 ? 1 : minPressFrames;
            MinReleaseFrames = minReleaseFrames < 1 ? 1 : minReleaseFrames;
        }

        /// <summary>One latched frame: the caller's wanted key set in, the key set the game sees this frame out.</summary>
        public uint Step(uint want)
        {
            var changed = want ^ desired;
            desired = want;
            var next = latched;
            uint pressedNow = 0;

            for (var i = 0; i < Bits; i++)
            {
                var bit = 1u << i;
                if ((changed & bit) != 0 && ++pending[i] > MaxPendingToggles)
                {
                    pending[i] -= 2;
                    TapsCollapsed++;
                }
                if (pending[i] == 0) continue;

                if ((latched & bit) != 0)
                {
                    if (age[i] >= MinPressFrames)
                    {
                        next &= ~bit;
                        pending[i]--;
                        deferred[i] = false;
                    }
                    else if (!deferred[i])
                    {
                        deferred[i] = true;
                        HoldsExtended++;
                    }
                }
                else if (age[i] >= MinReleaseFrames)
                {
                    next |= bit;
                    pressedNow |= bit;
                    pending[i]--;
                    deferred[i] = false;
                }
                else if (!deferred[i])
                {
                    deferred[i] = true;
                    PressesDeferred++;
                }
            }

            if ((next & exclusiveA) != 0 && (next & exclusiveB) != 0)
            {
                RevertPress(ref next, exclusiveA, pressedNow);
                RevertPress(ref next, exclusiveB, pressedNow);
            }

            var toggled = next ^ latched;
            for (var i = 0; i < Bits; i++)
            {
                if ((toggled & (1u << i)) != 0)
                {
                    age[i] = 1;
                    exclusiveWaiting[i] = false;
                }
                else if (age[i] < Long)
                {
                    age[i]++;
                }
            }
            latched = next;
            return latched;
        }

        /// <summary>Un-latch a press made this frame that collides with the opposite direction. If the caller no longer
        /// wants the key, what is left queued is a stale tap (an even number of edges): drop it rather than fire it
        /// later.</summary>
        private void RevertPress(ref uint next, uint mask, uint pressedNow)
        {
            for (var i = 0; i < Bits; i++)
            {
                var bit = 1u << i;
                if ((mask & bit) == 0 || (pressedNow & bit) == 0) continue;
                next &= ~bit;
                pending[i]++;
                if (!exclusiveWaiting[i])
                {
                    exclusiveWaiting[i] = true;
                    ExclusiveDeferred++;
                }
                if ((desired & bit) == 0)
                {
                    TapsCollapsed += pending[i] / 2;
                    pending[i] = 0;
                    exclusiveWaiting[i] = false;
                }
            }
        }
    }
}
