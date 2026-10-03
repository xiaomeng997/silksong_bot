using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.Threading;
using GlobalEnums;

namespace SsOracle.Input
{
    /// <summary>
    /// Applies brain ACTION messages at their target frame (DESIGN §4.6): an action takes effect at the first
    /// dynamic input update whose frame >= target_frame (+ the InputPathEmulator delay); actions that arrive more than
    /// 3 frames after their target are dropped (DelayLine). When several actions fall due in one update (a burst from a
    /// lagging brain, or delays that bunch them up), each one's key edges go into the HoldFilter in arrival order and
    /// are replayed with the minimum press / release, so no press is lost to a later mask. Brain lost (§4.6, §3.7.6):
    /// when the brain has been driving (it sent a continuous-control ACTION with a key down, hold_frames 0; one-shot
    /// presses with hold_frames > 0 and a bare release do not count) and no ACTION arrives for 250 ms (and 6 rendered frames), or it disconnects
    /// while driving, every key is released (queued edges dropped) and one Pause tap (2 frames down) is injected as
    /// soon as the game is PLAYING and pausable — the same blockers as STATE pause.blk — retried at most twice if the
    /// game did not pause; given up outside gameplay (title screen, no hero). The InputPathEmulator delay
    /// (input.latency_model) is drawn per ACTION on arrival. Harness operations (savestate load, randomized start)
    /// suspend ACTIONs and the watchdog while they run. The brain ends a session cleanly with input.release (no Pause
    /// tap).
    /// </summary>
    internal static class ActionScheduler
    {
        private const long WatchdogMs = 250;
        /// <summary>The watchdog also needs this many rendered frames without an ACTION, so a main-thread hitch (scene
        /// load, GC) that starved the brain of STATEs is not mistaken for a dead brain.</summary>
        private const int WatchdogMinFrames = 6;
        private const int PauseTapFrames = 2;
        private const int PauseVerifyFrames = 20;
        private const int MaxPauseTaps = 3;

        /// <summary>ACTION flags (optional 5th element). EXCLUSIVE: from this ACTION's frame no key outside its mask is
        /// down: every other key is released at once, below its minimum press if need be, and every edge still queued
        /// for it is dropped (HoldFilter.Exclusive). The brain's pause loop and quit sequence send it, so no planner key
        /// is latched on the pause frame or replayed into the pause menu (DESIGN §3.8.2: Z submits, X / A cancel).</summary>
        public const uint FlagExclusive = 1;
        public static readonly string[] FlagNames = { "exclusive" };

        private static readonly ConcurrentQueue<DelayLine.Item> Incoming = new ConcurrentQueue<DelayLine.Item>();
        private static readonly DelayLine Pending = new DelayLine();
        private static readonly LatencyModel Latency = new LatencyModel();
        private static long lastEnqueueTimestamp;   // Stopwatch ticks, written by the IPC reader thread
        private static long received;

        private static bool driving;
        private static long lastActionFrame;
        private static long releaseAtFrame = -1;
        private static int harnessDepth;

        private static bool lostPauseArmed;
        private static long pauseTapReleaseAt = -1;
        private static long pauseVerifyAt = -1;
        private static int pauseTaps;

        // Reported in STATE ("act").
        public static uint LastAck { get; private set; }
        public static long LastAppliedFrame { get; private set; } = -1;
        public static long LastAppliedTarget { get; private set; } = -1;
        public static long StaleDropped { get; private set; }
        public static bool BrainLost { get; private set; }

        // Reported by input.stats.
        public static long Applied { get; private set; }
        /// <summary>ACTIONs that fell due in the same input update as a later one: the later mask is what is requested
        /// after the update, but their edges were queued in the HoldFilter all the same (none is dropped).</summary>
        public static long Coalesced { get; private set; }
        public static long Suppressed { get; private set; }
        public static long Rejected { get; private set; }
        /// <summary>ACTIONs applied with the EXCLUSIVE flag.</summary>
        public static long Exclusives { get; private set; }
        public static long LostEvents { get; private set; }
        public static long LostPauseTaps { get; private set; }
        public static long LostPausesConfirmed { get; private set; }

        public static bool HarnessBusy => harnessDepth > 0;

        /// <summary>IPC reader thread: payload is a msgpack array [target_frame, buttons, hold_frames, ack_seq, flags?]
        /// (flags optional: brains that send four elements are unchanged).</summary>
        public static void Enqueue(byte[] body, int offset, int count)
        {
            if (!Core.Profile.Rules.Injection) return;  // REHEARSAL profiles: ACTIONs go through the final sink instead
            if (!(new Ipc.MsgPackReader(body, offset, count).Read() is List<object> a) || a.Count < 4) return;
            Incoming.Enqueue(new DelayLine.Item
            {
                TargetFrame = Convert.ToInt64(a[0]),
                Buttons = (uint)Convert.ToUInt64(a[1]),
                HoldFrames = Convert.ToInt32(a[2]),
                AckSeq = (uint)Convert.ToUInt64(a[3]),
                Flags = a.Count > 4 && a[4] != null ? (uint)Convert.ToUInt64(a[4]) : 0u,
            });
            Interlocked.Exchange(ref lastEnqueueTimestamp, Stopwatch.GetTimestamp());
            Interlocked.Increment(ref received);
        }

        /// <summary>Main thread, called by KeyboardInjector at each dynamic input update before it latches.</summary>
        public static void Tick(long frame)
        {
            while (Incoming.TryDequeue(out var a)) Accept(a, frame);

            // Every due ACTION in arrival order: each one's edges are queued in the HoldFilter (TryQueueMask), which
            // replays them with the minimum press / release, as inputd holds a press until the game has sampled it.
            var applied = false;
            while (Pending.TryTakeDue(frame, out var act))
            {
                if (applied) Coalesced++;
                applied = true;
                var exclusive = (act.Flags & FlagExclusive) != 0;
                if (exclusive) Exclusives++;
                if (!(exclusive ? KeyboardInjector.TryQueueMaskExclusive(act.Buttons, out var error)
                        : KeyboardInjector.TryQueueMask(act.Buttons, out error)))
                {
                    Rejected++;
                    Core.Plugin.Log.LogWarning("ACTION rejected: " + error);
                }
                LastAck = act.AckSeq;
                LastAppliedFrame = frame;
                LastAppliedTarget = act.TargetFrame;
                releaseAtFrame = act.HoldFrames > 0 ? frame + act.HoldFrames : -1;
                Applied++;
            }
            if (!applied && releaseAtFrame >= 0 && frame >= releaseAtFrame)
            {
                KeyboardInjector.ReleaseAll();
                releaseAtFrame = -1;
            }

            if (driving && harnessDepth == 0 && !BrainLost)
            {
                var ms = MsSinceLastAction();
                if (ms > WatchdogMs && frame - lastActionFrame >= WatchdogMinFrames)
                    BeginLost($"no ACTION for {ms} ms ({frame - lastActionFrame} frames)");
            }
            if (lostPauseArmed) StepLostPause(frame);
        }

        private static void Accept(DelayLine.Item a, long frame)
        {
            if (harnessDepth > 0)
            {
                Suppressed++;
                return;
            }
            if (!Pending.Accept(ref a, frame, Latency))
            {
                StaleDropped++;
                return;
            }
            // Only continuous control ("hold until my next ACTION", hold_frames 0) with a key down commits the brain to
            // keep sending, so only it arms the brain-lost watchdog. A one-shot press (hold_frames > 0) releases itself,
            // and a bare release (mask 0) leaves nothing held; probes and menu drivers that tap or walk and then wait
            // must not end with a surprise Pause tap once the game becomes pausable. Once driving, every ACTION (mask 0
            // included) keeps the watchdog fed.
            if (a.HoldFrames == 0 && a.Buttons != 0) driving = true;
            lastActionFrame = frame;
            if (BrainLost) EndLost();
        }

        private static long MsSinceLastAction()
        {
            var t = Interlocked.Read(ref lastEnqueueTimestamp);
            return t == 0 ? long.MaxValue : (Stopwatch.GetTimestamp() - t) * 1000 / Stopwatch.Frequency;
        }

        private static void BeginLost(string reason)
        {
            BrainLost = true;
            LostEvents++;
            KeyboardInjector.ReleaseAllNow();
            Pending.Clear();
            releaseAtFrame = -1;
            lostPauseArmed = true;
            pauseTaps = 0;
            pauseTapReleaseAt = -1;
            pauseVerifyAt = -1;
            Core.Plugin.Log.LogWarning($"brain lost ({reason}): released all keys; Pause will be tapped once the game is pausable");
        }

        private static void EndLost()
        {
            if (pauseTapReleaseAt >= 0) KeyboardInjector.ReleaseAllNow();
            BrainLost = false;
            lostPauseArmed = false;
            pauseTapReleaseAt = -1;
            pauseVerifyAt = -1;
        }

        /// <summary>One Pause tap while the brain is lost, only when the press would be accepted (a press into a closed
        /// gate is dropped; in CUTSCENE it would skip the cutscene; while paused it would unpause after the 0.3 s
        /// lockout). GameState turns PAUSED in the frame the press is read (GameManager.PauseGameToggle), so "still
        /// PLAYING 20 frames later" means the press was lost and a retry cannot unpause.</summary>
        private static void StepLostPause(long frame)
        {
            if (pauseTapReleaseAt >= 0)
            {
                if (frame < pauseTapReleaseAt) return;
                KeyboardInjector.ReleaseAll();
                pauseTapReleaseAt = -1;
                pauseVerifyAt = frame + PauseVerifyFrames;
                return;
            }
            var gm = GameManager._instance;
            if (gm == null || gm.GameState == GameState.MAIN_MENU || HeroController.UnsafeInstance == null)
            {
                // Not in gameplay (title screen, Save & Quit): nothing to protect, and a tap much later would surprise.
                lostPauseArmed = false;
                return;
            }
            if (gm.isPaused || gm.GameState == GameState.PAUSED)
            {
                lostPauseArmed = false;
                if (pauseTaps > 0)
                {
                    LostPausesConfirmed++;
                    Core.Plugin.Log.LogWarning($"brain lost: game paused after {pauseTaps} tap(s)");
                }
                return;
            }
            if (pauseVerifyAt >= 0 && frame < pauseVerifyAt) return;
            if (pauseTaps >= MaxPauseTaps)
            {
                lostPauseArmed = false;
                Core.Plugin.Log.LogError($"brain lost: {pauseTaps} Pause taps did not pause the game; giving up");
                return;
            }
            if (!KeyboardInjector.OwnsKeyboard) return;
            var pd = gm.playerData;
            if (pd == null || pd.isInventoryOpen || PauseGate.Blockers(gm, pd) != 0) return;
            // Exclusive: a key the brain pressed just before it was lost is not still latched (minimum press) on the
            // frame the Pause tap pauses the game, so the pause menu never opens over a game key.
            if (!KeyboardInjector.SetMaskExclusive(KeyboardInjector.PauseBit, out _)) return;
            pauseTapReleaseAt = frame + PauseTapFrames;
            pauseTaps++;
            LostPauseTaps++;
            Core.Plugin.Log.LogWarning($"brain lost: tapping Pause at frame {frame} (tap {pauseTaps})");
        }

        /// <summary>Main thread.</summary>
        public static void OnBrainDisconnected()
        {
            if (driving && !BrainLost && harnessDepth == 0) BeginLost("brain disconnected");
            driving = false;
            Pending.Clear();
            while (Incoming.TryDequeue(out _)) { }
            releaseAtFrame = -1;
            // Emulation settings belong to one brain session; the next one starts oracle-exact.
            Latency.Reset();
            KeyboardInjector.Filter.SetLimits(HoldFilter.DefaultMinPressFrames, HoldFilter.DefaultMinReleaseFrames);
        }

        /// <summary>Main thread (input.release): the brain stops driving on purpose, e.g. before it disconnects. Releases
        /// every key, drops every queued ACTION and key edge, and disarms the watchdog, so no Pause is tapped.</summary>
        public static void StopDriving()
        {
            driving = false;
            EndLost();
            Pending.Clear();
            while (Incoming.TryDequeue(out _)) { }
            releaseAtFrame = -1;
            KeyboardInjector.ReleaseAllNow();
        }

        /// <summary>Main thread: a harness operation starts. Keys are released, queued ACTIONs dropped, and further
        /// ACTIONs are ignored (counted as suppressed) until HarnessEnd; the watchdog re-arms on the next ACTION.</summary>
        public static void HarnessBegin()
        {
            harnessDepth++;
            StopDriving();
        }

        public static void HarnessEnd()
        {
            if (harnessDepth > 0) harnessDepth--;
            driving = false;
        }

        /// <summary>Main thread (input.latency_model). ACTIONs already queued keep their effective frames, and later ones
        /// still never overtake them (DelayLine keeps its running maximum across the change).</summary>
        public static string ConfigureLatency(int delay, int jitter, int seed, IList<KeyValuePair<int, double>> dist) =>
            Latency.Configure(delay, jitter, seed, dist);

        public static Dictionary<string, object> DescribeLatency() => Latency.Describe();

        /// <summary>Main thread (input.stats).</summary>
        public static Dictionary<string, object> Describe(long frame)
        {
            var ms = MsSinceLastAction();
            return new Dictionary<string, object>
            {
                ["frame"] = frame,
                ["driving"] = driving,
                ["lost"] = BrainLost,
                ["harness_busy"] = harnessDepth > 0,
                ["ms_since_action"] = ms == long.MaxValue ? -1 : ms,
                ["received"] = Interlocked.Read(ref received),
                ["applied"] = Applied,
                ["coalesced"] = Coalesced,
                ["stale"] = StaleDropped,
                ["suppressed"] = Suppressed,
                ["rejected"] = Rejected,
                ["exclusive"] = Exclusives,
                ["pending"] = Pending.Count,
                ["last_ack"] = LastAck,
                ["last_applied"] = LastAppliedFrame,
                ["last_target"] = LastAppliedTarget,
                ["last_delay"] = Latency.LastSample,
                ["latency"] = Latency.Describe(),
                ["lost_events"] = LostEvents,
                ["lost_pause_taps"] = LostPauseTaps,
                ["lost_pauses_confirmed"] = LostPausesConfirmed,
                ["lost_pause_armed"] = lostPauseArmed,
            };
        }
    }
}
