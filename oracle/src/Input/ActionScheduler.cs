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
    /// 3 frames after their target are dropped. Brain lost (§4.6, §3.7.6): when the brain has been driving and no ACTION
    /// arrives for 250 ms (and 6 rendered frames), or it disconnects while driving, every key is released and one Pause
    /// tap (2 frames down) is injected as soon as the game is PLAYING and pausable — the same blockers as STATE
    /// pause.blk — retried at most twice if the game did not pause; given up outside gameplay (title screen, no hero).
    /// The InputPathEmulator delay (input.latency_model) is drawn per ACTION on arrival. Harness operations (savestate
    /// load, randomized start) suspend ACTIONs and the watchdog while they run. The brain ends a session cleanly with
    /// input.release (no Pause tap).
    /// </summary>
    internal static class ActionScheduler
    {
        private struct PendingAction
        {
            public long TargetFrame;
            public long EffectiveFrame;
            public uint Buttons;
            public int HoldFrames;
            public uint AckSeq;
        }

        private const int MaxLateFrames = 3;
        private const long WatchdogMs = 250;
        /// <summary>The watchdog also needs this many rendered frames without an ACTION, so a main-thread hitch (scene
        /// load, GC) that starved the brain of STATEs is not mistaken for a dead brain.</summary>
        private const int WatchdogMinFrames = 6;
        private const int PauseTapFrames = 2;
        private const int PauseVerifyFrames = 20;
        private const int MaxPauseTaps = 3;

        private static readonly ConcurrentQueue<PendingAction> Incoming = new ConcurrentQueue<PendingAction>();
        private static readonly List<PendingAction> Pending = new List<PendingAction>();
        private static readonly LatencyModel Latency = new LatencyModel();
        private static long lastEnqueueTimestamp;   // Stopwatch ticks, written by the IPC reader thread
        private static long received;

        private static bool driving;
        private static long lastActionFrame;
        private static long releaseAtFrame = -1;
        private static long lastEffective = long.MinValue;
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
        public static long Superseded { get; private set; }
        public static long Suppressed { get; private set; }
        public static long Rejected { get; private set; }
        public static long LostEvents { get; private set; }
        public static long LostPauseTaps { get; private set; }
        public static long LostPausesConfirmed { get; private set; }

        public static bool HarnessBusy => harnessDepth > 0;

        /// <summary>IPC reader thread: payload is a msgpack array [target_frame, buttons, hold_frames, ack_seq].</summary>
        public static void Enqueue(byte[] body, int offset, int count)
        {
            if (!(new Ipc.MsgPackReader(body, offset, count).Read() is List<object> a) || a.Count < 4) return;
            Incoming.Enqueue(new PendingAction
            {
                TargetFrame = Convert.ToInt64(a[0]),
                Buttons = (uint)Convert.ToUInt64(a[1]),
                HoldFrames = Convert.ToInt32(a[2]),
                AckSeq = (uint)Convert.ToUInt64(a[3]),
            });
            Interlocked.Exchange(ref lastEnqueueTimestamp, Stopwatch.GetTimestamp());
            Interlocked.Increment(ref received);
        }

        /// <summary>Main thread, called by KeyboardInjector at each dynamic input update before it latches.</summary>
        public static void Tick(long frame)
        {
            while (Incoming.TryDequeue(out var a)) Accept(a, frame);

            PendingAction? apply = null;
            for (var i = Pending.Count - 1; i >= 0; i--)
            {
                var a = Pending[i];
                if (a.EffectiveFrame > frame) continue;
                Pending.RemoveAt(i);
                if (apply == null) apply = a;
                else if (a.TargetFrame > apply.Value.TargetFrame) { apply = a; Superseded++; }
                else Superseded++;
            }

            if (apply is PendingAction act)
            {
                if (!KeyboardInjector.TrySetMask(act.Buttons, out var error))
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
            else if (releaseAtFrame >= 0 && frame >= releaseAtFrame)
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

        private static void Accept(PendingAction a, long frame)
        {
            if (harnessDepth > 0)
            {
                Suppressed++;
                return;
            }
            if (a.TargetFrame < frame - MaxLateFrames)
            {
                StaleDropped++;
                return;
            }
            // The emulated path adds its delay to the moment the action exists (target, or arrival when late), and
            // edges never overtake each other on a real wire, hence the running maximum.
            var effective = Math.Max(a.TargetFrame, frame) + Latency.Sample();
            if (effective < lastEffective) effective = lastEffective;
            lastEffective = effective;
            a.EffectiveFrame = effective;
            Pending.Add(a);
            driving = true;
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
            KeyboardInjector.ReleaseAll();
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
            if (pauseTapReleaseAt >= 0) KeyboardInjector.ReleaseAll();
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
            if (!KeyboardInjector.TrySetMask(KeyboardInjector.PauseBit, out _)) return;
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
            lastEffective = long.MinValue;
            // Emulation settings belong to one brain session; the next one starts oracle-exact.
            Latency.Reset();
            KeyboardInjector.Filter.SetLimits(HoldFilter.DefaultMinPressFrames, HoldFilter.DefaultMinReleaseFrames);
        }

        /// <summary>Main thread (input.release): the brain stops driving on purpose, e.g. before it disconnects. Releases
        /// every key and disarms the watchdog, so no Pause is tapped.</summary>
        public static void StopDriving()
        {
            driving = false;
            EndLost();
            Pending.Clear();
            while (Incoming.TryDequeue(out _)) { }
            releaseAtFrame = -1;
            KeyboardInjector.ReleaseAll();
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

        /// <summary>Main thread (input.latency_model).</summary>
        public static string ConfigureLatency(int delay, int jitter, int seed, IList<KeyValuePair<int, double>> dist)
        {
            var error = Latency.Configure(delay, jitter, seed, dist);
            if (error == null) lastEffective = long.MinValue;
            return error;
        }

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
                ["superseded"] = Superseded,
                ["stale"] = StaleDropped,
                ["suppressed"] = Suppressed,
                ["rejected"] = Rejected,
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
