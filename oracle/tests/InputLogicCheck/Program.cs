using System;
using System.Collections.Generic;
using System.Linq;
using SsOracle.Input;

/// <summary>
/// Offline checks of the oracle's input path between an ACTION's arrival and the key set the game samples:
/// DelayLine (target frame, stale drop, order) -> LatencyModel (InputPathEmulator delay) -> HoldFilter (C19 minimum
/// press / release, left-right exclusion). Path.Frame mirrors ActionScheduler.Tick + KeyboardInjector.TryQueueMask +
/// KeyboardInjector.OnBeforeUpdate. The in-game counterpart is brain/ssbot/probes/m1_harness.py (sections hold, stream).
/// </summary>
internal static class Program
{
    private const uint Jump = 1u << 0, Attack = 1u << 1, Left = 1u << 20, Right = 1u << 21;

    /// <summary>The loopback prior of DESIGN §3.9.2: 2/3/4 frames weighted 0.3/0.5/0.2.</summary>
    private static readonly KeyValuePair<int, double>[] Prior =
    {
        new KeyValuePair<int, double>(2, 0.3), new KeyValuePair<int, double>(3, 0.5), new KeyValuePair<int, double>(4, 0.2),
    };

    private static int fails;

    private static void Check(bool ok, string what)
    {
        if (!ok) fails++;
        Console.WriteLine($"{(ok ? "ok  " : "FAIL")} {what}");
    }

    private static int Main()
    {
        OneFrameTap();
        RePressKeepsBothEdges();
        LeftRightNeverTogether();
        ReleaseAllDropsQueuedEdges();
        ExclusiveClearsOtherKeysAtOnce();
        BoundedBacklog();
        ExportedStateIsSufficient();
        LatencyModelDraws();
        DelayLineOrderAndStale();
        BunchedPressAndReleaseBothLatched();
        LatencyChangeDoesNotReorder();
        StreamedTaps("delay prior 2/3/4, one ACTION per frame", Prior, burst: 1, seeds: 2000);
        StreamedTaps("no delay, brain delivering 3 frames of ACTIONs at once", null, burst: 3, seeds: 2000);
        StreamedTaps("delay prior 2/3/4 and bursts of 3", Prior, burst: 3, seeds: 2000);
        Console.WriteLine(fails == 0 ? "ALL OK" : $"{fails} FAILED");
        return fails == 0 ? 0 : 1;
    }

    /// <summary>ActionScheduler + KeyboardInjector for one instance, without Unity.</summary>
    private sealed class Path
    {
        public readonly DelayLine Line = new DelayLine();
        public readonly LatencyModel Latency = new LatencyModel();
        public readonly HoldFilter Filter = new HoldFilter(Left, Right);
        private uint requested;
        public int Stale;

        public uint Frame(long frame, IEnumerable<DelayLine.Item> arriving)
        {
            foreach (var item in arriving)
            {
                var a = item;
                if (!Line.Accept(ref a, frame, Latency)) Stale++;
            }
            while (Line.TryTakeDue(frame, out var act))
            {
                Filter.Push(requested);
                Filter.Push(act.Buttons);
                requested = act.Buttons;
            }
            return Filter.Step(requested);
        }

        public uint Frame(long frame, params (long Target, uint Buttons)[] arriving) =>
            Frame(frame, arriving.Select(x => new DelayLine.Item { TargetFrame = x.Target, Buttons = x.Buttons }));
    }

    /// <summary>
    /// STATE act.hf = {pending, age (clamped like FrameExporter.HfAgeCap), latched, desired}: a filter restored from it
    /// in the middle of a stream latches exactly what the original latches from then on (the planner replays the
    /// latch from the exported state instead of from "all keys up for a long time").
    /// </summary>
    private static void ExportedStateIsSufficient()
    {
        const int cap = 255;   // FrameExporter.HfAgeCap
        var mismatches = 0;
        var naiveMismatches = 0;   // control: only the latched mask, as if every key had been stable for long
        var cases = 0;
        foreach (var limits in new[] { (2, 2), (3, 1), (1, 4) })
        {
            for (var seed = 0; seed < 400; seed++)
            {
                var rng = new Random(seed);
                var a = new HoldFilter(Left, Right);
                a.SetLimits(limits.Item1, limits.Item2);
                var keys = new[] { Jump, Attack, Left, Right };
                var wants = new List<List<uint>>();
                for (var f = 0; f < 160; f++)
                {
                    var pushes = new List<uint>();
                    var n = rng.Next(1, 4);
                    for (var p = 0; p < n; p++)
                    {
                        uint m = 0;
                        foreach (var k in keys)
                            if (rng.NextDouble() < 0.35) m |= k;
                        if ((m & Left) != 0 && (m & Right) != 0) m &= ~(rng.Next(2) == 0 ? Left : Right);
                        pushes.Add(m);
                    }
                    wants.Add(pushes);
                }
                var cut = rng.Next(5, 120);
                HoldFilter b = null, naive = null;
                for (var f = 0; f < wants.Count; f++)
                {
                    if (f == cut)
                    {
                        var pend = new int[32];
                        var age = new int[32];
                        for (var i = 0; i < 32; i++)
                        {
                            pend[i] = a.PendingOf(i);
                            age[i] = Math.Min(a.AgeOf(i), cap);
                        }
                        b = new HoldFilter(Left, Right);
                        b.SetLimits(limits.Item1, limits.Item2);
                        b.Restore(a.Desired, a.Latched, pend, age);
                        naive = new HoldFilter(Left, Right);
                        naive.SetLimits(limits.Item1, limits.Item2);
                        naive.Restore(a.Latched, a.Latched, null, null);
                        cases++;
                    }
                    var ps = wants[f];
                    for (var p = 0; p < ps.Count - 1; p++)
                    {
                        a.Push(ps[p]);
                        b?.Push(ps[p]);
                        naive?.Push(ps[p]);
                    }
                    var la = a.Step(ps[ps.Count - 1]);
                    if (b != null && b.Step(ps[ps.Count - 1]) != la) mismatches++;
                    if (naive != null && naive.Step(ps[ps.Count - 1]) != la) naiveMismatches++;
                }
            }
        }
        Check(mismatches == 0 && naiveMismatches > 0,
            $"act.hf state (pending, age capped at {cap}, latched, desired) restores the latch exactly: {cases} cuts, " +
            $"{mismatches} differing frames (latched mask alone: {naiveMismatches})");
    }

    /// <summary>Latched runs of one key: (first frame, length).</summary>
    private static List<(int Start, int Length)> Runs(IList<uint> masks, uint bit)
    {
        var runs = new List<(int, int)>();
        for (var i = 0; i < masks.Count; i++)
        {
            if ((masks[i] & bit) == 0 || (i > 0 && (masks[i - 1] & bit) != 0)) continue;
            var n = 0;
            while (i + n < masks.Count && (masks[i + n] & bit) != 0) n++;
            runs.Add((i, n));
        }
        return runs;
    }

    private static void OneFrameTap()
    {
        var f = new HoldFilter(Left, Right);
        var seen = new List<uint> { f.Step(Jump) };
        for (var i = 0; i < 5; i++) seen.Add(f.Step(0));
        var runs = Runs(seen, Jump);
        Check(runs.Count == 1 && runs[0] == (0, 2), $"1-frame tap is latched for exactly 2 frames ({string.Join(",", runs)})");
        Check(f.HoldsExtended == 1, $"holds_extended counts the deferred release ({f.HoldsExtended})");
    }

    private static void RePressKeepsBothEdges()
    {
        var f = new HoldFilter(Left, Right);
        var want = new uint[] { Jump, 0, Jump, 0, 0, 0, 0, 0, 0, 0 };
        var seen = want.Select(w => f.Step(w)).ToList();
        var runs = Runs(seen, Jump);
        var gap = runs.Count == 2 ? runs[1].Start - (runs[0].Start + runs[0].Length) : -1;
        Check(runs.Count == 2 && runs.All(r => r.Length >= 2) && gap >= HoldFilter.DefaultMinReleaseFrames,
            $"press, release, re-press: two presses of >= 2 frames with a release gap of {gap} (>= {HoldFilter.DefaultMinReleaseFrames})");
    }

    private static void LeftRightNeverTogether()
    {
        var f = new HoldFilter(Left, Right);
        var rng = new Random(1);
        var both = 0;
        for (var i = 0; i < 20000; i++)
        {
            var r = rng.Next(4);
            var want = r == 0 ? Left : r == 1 ? Right : r == 2 ? 0u : Jump;
            var m = f.Step(want);
            if ((m & Left) != 0 && (m & Right) != 0) both++;
        }
        Check(both == 0, $"left and right never latched together over 20000 random frames ({both}; lr_deferred {f.ExclusiveDeferred})");

        // Several ACTIONs due in one frame push several sets before the latch (left, then right, ...).
        var g = new HoldFilter(Left, Right);
        both = 0;
        for (var i = 0; i < 20000; i++)
        {
            for (var k = rng.Next(1, 4); k > 0; k--)
            {
                var r = rng.Next(4);
                g.Push(r == 0 ? Left : r == 1 ? Right : r == 2 ? 0u : Jump);
            }
            var m = g.Step(g.Desired);
            if ((m & Left) != 0 && (m & Right) != 0) both++;
        }
        Check(both == 0, $"... also with 1-3 sets pushed per frame ({both}; lr_deferred {g.ExclusiveDeferred})");
    }

    /// <summary>Review item: a pending re-press must not fire after ReleaseAll (brain lost, input.release, harness).</summary>
    private static void ReleaseAllDropsQueuedEdges()
    {
        var f = new HoldFilter(Left, Right);
        var seen = new List<uint> { f.Step(Jump) };  // latched, age 1
        f.Push(0);                                    // brain releases ...
        f.Push(Jump);                                 // ... and presses again, both still queued
        f.ReleaseAll();
        for (var i = 0; i < 8; i++) seen.Add(f.Step(0));
        var runs = Runs(seen, Jump);
        Check(runs.Count == 1 && runs[0] == (0, 2), $"ReleaseAll: the held key keeps its minimum press, the queued re-press never fires ({string.Join(",", runs)})");
        Check(f.TapsCollapsed == 1 && f.PendingToggles == 0, $"ReleaseAll counts the dropped press ({f.TapsCollapsed}) and leaves nothing queued ({f.PendingToggles})");

        var g = new HoldFilter(Left, Right);
        g.Step(0);
        g.Push(Attack);  // a press not latched yet
        g.ReleaseAll();
        var any = Enumerable.Range(0, 6).Select(_ => g.Step(0)).Any(m => m != 0);
        Check(!any && g.TapsCollapsed == 1, "ReleaseAll: a press queued but not yet latched is dropped");
    }

    /// <summary>
    /// The ACTION EXCLUSIVE flag (HoldFilter.Exclusive, the pause loop's ACTIONs): on the Pause press's own latch no
    /// other key is down, even one pressed on the frame before (released below its 2-frame minimum press), and a
    /// press queued for a game key never fires later (the pause_stress key leak: a planner key latched on the pause
    /// frame, or a deferred re-press replayed into the menu).
    /// </summary>
    private static void ExclusiveClearsOtherKeysAtOnce()
    {
        const uint Pause = 1u << 14;
        var f = new HoldFilter(Left, Right);
        f.Step(Right);
        f.Step(Right | Jump);                           // jump pressed on the frame before the pause (age 1)
        f.Push(Right);                                  // the planner releases right ...
        f.Push(Right | Attack);                         // ... and queues right + attack again
        f.Exclusive(Pause);
        f.Push(Pause);
        var seen = new List<uint> { f.Step(Pause) };
        for (var i = 0; i < 10; i++) seen.Add(f.Step(i < 2 ? Pause : 0));
        Check(seen[0] == Pause, $"Exclusive: the Pause press's latch carries nothing else (0x{seen[0]:x})");
        Check(seen.All(m => (m & ~Pause) == 0) && f.PendingToggles == 0,
            $"Exclusive: no game key latched afterwards, nothing queued ({string.Join(",", seen.Select(m => m.ToString("x")))})");
        Check(f.ReleasedEarly == 1, $"Exclusive counts the key released below its minimum press ({f.ReleasedEarly})");
        // the abandoned keys obey the minimum release afterwards like any released key
        f.Push(Jump);
        var again = Enumerable.Range(0, 4).Select(_ => f.Step(Jump)).ToList();
        Check(again.All(m => (m & Jump) != 0), "Exclusive: a later press of an abandoned key latches normally");
    }

    private static void BoundedBacklog()
    {
        var f = new HoldFilter(Left, Right);
        var maxPending = 0;
        for (var i = 0; i < 1000; i++)
        {
            f.Step(i % 2 == 0 ? Jump : 0);  // toggling every frame: far faster than 2/2 frames allow
            maxPending = Math.Max(maxPending, f.PendingToggles);
        }
        Check(maxPending <= HoldFilter.MaxPendingToggles && f.TapsCollapsed > 0,
            $"toggling every frame: backlog stays <= {HoldFilter.MaxPendingToggles} ({maxPending}), excess taps collapsed ({f.TapsCollapsed})");
    }

    private static void LatencyModelDraws()
    {
        var a = new LatencyModel();
        var b = new LatencyModel();
        a.Configure(3, 1, 5, null);
        b.Configure(3, 1, 5, null);
        var da = Enumerable.Range(0, 1000).Select(_ => a.Sample()).ToList();
        var db = Enumerable.Range(0, 1000).Select(_ => b.Sample()).ToList();
        Check(da.SequenceEqual(db) && da.Min() == 2 && da.Max() == 4, $"delay 3 jitter 1: seeded, deterministic, within 2..4 ({da.Min()}..{da.Max()})");

        var m = new LatencyModel();
        m.Configure(0, 0, 7, Prior);
        var n = 200000;
        var counts = new int[5];
        for (var i = 0; i < n; i++) counts[m.Sample()]++;
        var p2 = counts[2] / (double)n;
        var p3 = counts[3] / (double)n;
        var p4 = counts[4] / (double)n;
        Check(Math.Abs(p2 - 0.3) < 0.01 && Math.Abs(p3 - 0.5) < 0.01 && Math.Abs(p4 - 0.2) < 0.01 && counts[0] + counts[1] == 0,
            $"dist 2/3/4: frequencies {p2:0.000}/{p3:0.000}/{p4:0.000}");

        m.Reset();
        Check(m.IsIdentity && m.Sample() == 0, "Reset: 0 frames");
    }

    private static void DelayLineOrderAndStale()
    {
        var line = new DelayLine();
        var lat = new LatencyModel();
        lat.Configure(0, 0, 11, Prior);
        var last = long.MinValue;
        var ordered = true;
        for (long t = 0; t < 5000; t++)
        {
            var a = new DelayLine.Item { TargetFrame = t + 2 };
            line.Accept(ref a, t, lat);
            if (a.EffectiveFrame < last || a.EffectiveFrame < a.TargetFrame + 2) ordered = false;
            last = a.EffectiveFrame;
            while (line.TryTakeDue(t, out _)) { }
        }
        Check(ordered, "effective frames never decrease and never undercut target + delay");

        // A stale ACTION is dropped without drawing a delay, so the delay sequence stays the same.
        var withStale = new DelayLine();
        var l1 = new LatencyModel();
        var l2 = new LatencyModel();
        l1.Configure(3, 2, 9, null);
        l2.Configure(3, 2, 9, null);
        var stale = new DelayLine.Item { TargetFrame = 100 - DelayLine.MaxLateFrames - 1 };
        var edge = new DelayLine.Item { TargetFrame = 100 - DelayLine.MaxLateFrames };
        Check(!withStale.Accept(ref stale, 100, l1), $"an ACTION more than {DelayLine.MaxLateFrames} frames late is dropped");
        Check(withStale.Accept(ref edge, 100, l1), $"an ACTION exactly {DelayLine.MaxLateFrames} frames late is kept");
        l2.Sample();
        var same = Enumerable.Range(0, 50).All(_ => l1.Sample() == l2.Sample());
        Check(same, "the stale ACTION drew no delay");
    }

    /// <summary>Review item (major): press at t with delay 4 and release at t+2 with delay 2 fall due together at t+4;
    /// the press must still be latched for the minimum press, not superseded by the release.</summary>
    private static void BunchedPressAndReleaseBothLatched()
    {
        var p = new Path();
        var seen = new List<uint>();
        for (long t = 0; t < 12; t++)
        {
            var arriving = new List<(long, uint)>();
            if (t == 1) { p.Latency.Configure(4, 0, 0, null); arriving.Add((1, Jump)); }
            if (t == 3) { p.Latency.Configure(2, 0, 0, null); arriving.Add((3, 0)); }
            seen.Add(p.Frame(t, arriving.ToArray()));
        }
        var runs = Runs(seen, Jump);
        Check(runs.Count == 1 && runs[0] == (5, 2), $"press (delay 4) and its release (delay 2) due in one frame: jump latched {string.Join(",", runs)} (expected (5, 2))");
    }

    /// <summary>Review item: a latency change must not let a new ACTION overtake one already queued.</summary>
    private static void LatencyChangeDoesNotReorder()
    {
        var line = new DelayLine();
        var lat = new LatencyModel();
        lat.Configure(6, 0, 0, null);
        var first = new DelayLine.Item { TargetFrame = 10, Buttons = Jump };
        line.Accept(ref first, 10, lat);
        lat.Configure(0, 0, 0, null);
        var second = new DelayLine.Item { TargetFrame = 11, Buttons = 0 };
        line.Accept(ref second, 11, lat);
        Check(first.EffectiveFrame == 16 && second.EffectiveFrame == 16, $"after a delay change 6 -> 0 the next ACTION waits for the queued one ({first.EffectiveFrame}, {second.EffectiveFrame})");
        var order = new List<uint>();
        for (long t = 10; t <= 16; t++)
            while (line.TryTakeDue(t, out var a)) order.Add(a.Buttons);
        Check(order.SequenceEqual(new[] { Jump, 0u }), "and they come out in arrival order");
    }

    /// <summary>Tap patterns the brain may ask for, as the probe streams them: per key, a press of 1-2 frames, then a
    /// gap of 3-6 frames (a 2/2-frame filter needs 4 frames per tap, so this rate never builds a backlog).</summary>
    private static uint[] TapPattern(int seed, int frames)
    {
        var rng = new Random(seed);
        var masks = new uint[frames];
        foreach (var bit in new[] { Jump, Attack })
        {
            var t = rng.Next(0, 6);
            while (t < frames)
            {
                var len = rng.Next(1, 3);
                for (var i = t; i < Math.Min(frames, t + len); i++) masks[i] |= bit;
                t += len + rng.Next(3, 7);
            }
        }
        return masks;
    }

    /// <summary>Review item (major): with the 2/3/4 prior (or ACTIONs delivered in bursts), every requested press
    /// must be latched for >= 2 consecutive frames, with >= 2 released frames before a re-press, none collapsed.</summary>
    private static void StreamedTaps(string what, KeyValuePair<int, double>[] dist, int burst, int seeds)
    {
        const int frames = 240, tail = 40;
        int badRuns = 0, missing = 0, collapsed = 0, maxLag = 0, stale = 0;
        for (var seed = 1; seed <= seeds; seed++)
        {
            var want = TapPattern(seed, frames);
            var p = new Path();
            if (dist != null) p.Latency.Configure(0, 0, seed, dist);
            var seen = new List<uint>();
            var sent = 0;
            for (long t = 0; t < frames + tail; t++)
            {
                // The ACTION for target frame k arrives at frame k; a lagging brain delivers `burst` frames' worth at
                // once, the older ones late (but not stale), so they all fall due in the same update.
                var arriving = new List<(long, uint)>();
                if ((t + 1) % burst == 0 || t >= frames)
                    while (sent < frames && sent <= t)
                    {
                        arriving.Add((sent, want[sent]));
                        sent++;
                    }
                seen.Add(p.Frame(t, arriving.ToArray()));
            }
            stale += p.Stale;
            collapsed += (int)p.Filter.TapsCollapsed;
            foreach (var bit in new[] { Jump, Attack })
            {
                var asked = Runs(want, bit);
                var got = Runs(seen, bit);
                if (asked.Count != got.Count) missing += Math.Abs(asked.Count - got.Count);
                for (var i = 0; i < got.Count; i++)
                {
                    if (got[i].Length < HoldFilter.DefaultMinPressFrames) badRuns++;
                    if (i > 0 && got[i].Start - (got[i - 1].Start + got[i - 1].Length) < HoldFilter.DefaultMinReleaseFrames) badRuns++;
                    if (i < asked.Count) maxLag = Math.Max(maxLag, got[i].Start - asked[i].Start);
                }
            }
        }
        Check(missing == 0 && badRuns == 0 && collapsed == 0 && stale == 0,
            $"{what}: {seeds} x {frames} frames of 1-2 frame taps on 2 keys: missing presses {missing}, short runs or gaps {badRuns}, " +
            $"collapsed {collapsed}, stale {stale}; max press lag {maxLag} frames");
    }
}
