namespace SsOracle.Input
{
    /// <summary>
    /// Minimum press / release durations on the latched key set (DESIGN C19, m0:N37/N38). The Input System samples
    /// keys once per rendered frame, so a press and release inside one update is lost, and a re-press of the same key
    /// needs a sampled release in between. Every edge the caller asks for is kept and replayed in order: a release is
    /// held back until the key has been down for MinPressFrames latched frames, a press until it has been up for
    /// MinReleaseFrames (C19: both 2 frames, as the final inputd sink holds them). Left and right are never latched
    /// together (N41: MoveVector cancels but both IsPressed stay true), so a press of one waits for the release of the
    /// other. Several key sets may be pushed within one latched frame (Push); their edges all queue up. Pure logic
    /// (no Unity), main thread only.
    /// </summary>
    internal sealed class HoldFilter
    {
        public const int DefaultMinPressFrames = 2;
        public const int DefaultMinReleaseFrames = 2;

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
        /// <summary>Presses dropped before they were latched: queue overflow, a tap that could never be latched, or
        /// a queued press cancelled by ReleaseAll.</summary>
        public long TapsCollapsed { get; private set; }

        public uint Desired => desired;
        public uint Latched => latched;

        /// <summary>Edges of key <paramref name="bit"/> requested but not latched yet (STATE act.hf.pending).</summary>
        public int PendingOf(int bit) => pending[bit];

        /// <summary>Latched frames key <paramref name="bit"/> has been in its current state, saturating at 2^20
        /// (STATE act.hf.age).</summary>
        public int AgeOf(int bit) => age[bit];

        /// <summary>
        /// (desired, latched, pending, age) is the whole state that decides future output: deferred and
        /// exclusiveWaiting only feed the counters. Restore puts a filter into a state exported by STATE act.hf, which
        /// is how a planner replays the latch from the middle of a key stream (InputLogicCheck checks the equivalence).
        /// </summary>
        public void Restore(uint desiredMask, uint latchedMask, int[] pendingEdges, int[] ages)
        {
            desired = desiredMask;
            latched = latchedMask;
            exclusiveOwn = 0;
            for (var i = 0; i < Bits; i++)
            {
                pending[i] = pendingEdges != null && i < pendingEdges.Length ? pendingEdges[i] : 0;
                age[i] = ages != null && i < ages.Length ? ages[i] : Long;
                deferred[i] = false;
                exclusiveWaiting[i] = false;
            }
        }

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

        /// <summary>The caller now wants <paramref name="want"/>: queue one edge per key that differs from the last
        /// wanted set. Nothing is latched until Step, so several sets pushed in one frame all keep their edges.</summary>
        public void Push(uint want)
        {
            var changed = want ^ desired;
            if (changed == 0) return;
            desired = want;
            for (var i = 0; i < Bits; i++)
            {
                if ((changed & (1u << i)) == 0) continue;
                if (++pending[i] > MaxPendingToggles)
                {
                    pending[i] -= 2;
                    TapsCollapsed++;
                }
            }
        }

        /// <summary>One latched frame: the caller's wanted key set in, the key set the game sees this frame out.</summary>
        public uint Step(uint want)
        {
            Push(want);
            var next = latched;
            uint pressedNow = 0;

            for (var i = 0; i < Bits; i++)
            {
                if (pending[i] == 0) continue;
                var bit = 1u << i;

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

        /// <summary>Want nothing, and drop every queued edge: a latched key keeps only its release (still held to
        /// MinPressFrames), a key that is up stays up. For brain lost, input.release and harness operations, where a
        /// press queued earlier must not fire later (e.g. inside randomize_start's no-input wait).</summary>
        public void ReleaseAll()
        {
            desired = 0;
            exclusiveOwn = 0;
            for (var i = 0; i < Bits; i++)
            {
                var down = (latched & (1u << i)) != 0;
                var keep = down ? 1 : 0;
                if (pending[i] == keep) continue;
                // Queued edges alternate starting with a release when the key is down, with a press when it is up.
                TapsCollapsed += down ? pending[i] / 2 : (pending[i] + 1) / 2;
                pending[i] = keep;
                if (!down)
                {
                    deferred[i] = false;
                    exclusiveWaiting[i] = false;
                }
            }
        }

        /// <summary>Keys Exclusive released below their minimum press.</summary>
        public long ReleasedEarly { get; private set; }

        /// <summary>
        /// The ACTION EXCLUSIVE flag (DESIGN §3.7.5, §3.8.2 "no game key may reach a visible menu"): from this latch
        /// on, no key outside <paramref name="keep"/> is down. Every other key is released now, below its minimum
        /// press if need be (a key being abandoned for the pause menu needs no guarantee that the game sampled it), and
        /// every edge still queued for it is dropped, so no deferred press replays into the menu. The kept keys follow
        /// the usual limits (call Push / Step with them after this). Before it, a planner key pressed on the frame
        /// before the pause stayed latched on the pause frame (2-frame minimum press) and a press deferred by the
        /// minimum release fired inside the menu (pause_stress: 9 of 37 gate / live QUITs, 20261002_123347 ...).
        /// </summary>
        public void Exclusive(uint keep)
        {
            for (var i = 0; i < Bits; i++)
            {
                var bit = 1u << i;
                if ((keep & bit) != 0) continue;
                if (pending[i] > 0 && (latched & bit) == 0) TapsCollapsed += (pending[i] + 1) / 2;
                pending[i] = 0;
                deferred[i] = false;
                exclusiveWaiting[i] = false;
                if ((latched & bit) != 0)
                {
                    if (age[i] < MinPressFrames) ReleasedEarly++;
                    latched &= ~bit;
                    age[i] = 0;          // Step ages it to 1: released on this latch, like any release
                }
            }
            desired &= keep;
        }

        private uint exclusiveOwn;   // keys EXCLUSIVE sets asked for since the last plain set (QueueExclusive)

        /// <summary>
        /// The ACTION EXCLUSIVE path (KeyboardInjector.TryQueueMaskExclusive): Exclusive, sparing the keys that earlier
        /// EXCLUSIVE sets of the same stretch asked for, then Push. The pause loop sends all its ACTIONs EXCLUSIVE; its
        /// own taps keep the usual limits, so a tap latched for one frame (its first ACTION late, or two applied in
        /// one update) is not cut below the minimum press by the loop's next ACTION (review of 10d3948). Only the
        /// keys of other sets (the planner's) are cut. EndExclusive (a plain set: the planner is back) forgets them.
        /// </summary>
        public void QueueExclusive(uint want)
        {
            Exclusive(want | exclusiveOwn);
            exclusiveOwn |= want;
            Push(want);
        }

        /// <summary>A plain (non-EXCLUSIVE) set: the next EXCLUSIVE spares nothing it did not ask for itself.</summary>
        public void EndExclusive() => exclusiveOwn = 0;

        /// <summary>A plain ACTION (KeyboardInjector.TryQueueMask): EndExclusive, then the edges of
        /// <paramref name="previous"/> (a set another caller made since the last latch keeps its edges too) and of
        /// <paramref name="want"/>. Here rather than in KeyboardInjector so that InputLogicCheck runs the same calls.</summary>
        public void QueuePlain(uint previous, uint want)
        {
            EndExclusive();
            Push(previous);
            Push(want);
        }

        /// <summary>The brain-lost Pause tap (KeyboardInjector.SetMaskExclusive): EndExclusive, then QueueExclusive, so
        /// every key outside <paramref name="want"/> is cut, the pause loop's own included.</summary>
        public void QueueExclusiveCutAll(uint want)
        {
            EndExclusive();
            QueueExclusive(want);
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
