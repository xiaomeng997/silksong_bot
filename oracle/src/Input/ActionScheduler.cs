using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;

namespace SsOracle.Input
{
    /// <summary>
    /// Applies brain ACTION messages at their target frame (DESIGN §4.6): an action takes effect at the first
    /// dynamic input update whose frame >= target_frame; actions more than 3 frames late are dropped. When the
    /// brain has been driving and no ACTION arrives for 250 ms (real time), every key is released.
    /// </summary>
    internal static class ActionScheduler
    {
        private struct PendingAction
        {
            public long TargetFrame;
            public uint Buttons;
            public int HoldFrames;
            public uint AckSeq;
        }

        private const int MaxLateFrames = 3;
        private const long WatchdogMs = 250;

        private static readonly ConcurrentQueue<PendingAction> Incoming = new ConcurrentQueue<PendingAction>();
        private static readonly List<PendingAction> Pending = new List<PendingAction>();
        private static readonly Stopwatch SinceLastAction = new Stopwatch();
        private static volatile bool driving;
        private static long releaseAtFrame = -1;

        // Reported in STATE ("act").
        public static uint LastAck { get; private set; }
        public static long LastAppliedFrame { get; private set; } = -1;
        public static long LastAppliedTarget { get; private set; } = -1;
        public static long StaleDropped { get; private set; }
        public static bool BrainLost { get; private set; }

        /// <summary>IPC reader thread: payload is a msgpack array [target_frame, buttons, hold_frames, ack_seq].</summary>
        public static void Enqueue(byte[] body, int offset, int count)
        {
            if (!(new Ipc.MsgPackReader(body, offset, count).Read() is List<object> a) || a.Count < 4) return;
            Incoming.Enqueue(new PendingAction
            {
                TargetFrame = System.Convert.ToInt64(a[0]),
                Buttons = (uint)System.Convert.ToUInt64(a[1]),
                HoldFrames = System.Convert.ToInt32(a[2]),
                AckSeq = (uint)System.Convert.ToUInt64(a[3]),
            });
            lock (SinceLastAction) SinceLastAction.Restart();
            driving = true;
        }

        /// <summary>Main thread, called by KeyboardInjector at each dynamic input update before it latches.</summary>
        public static void Tick(long frame)
        {
            while (Incoming.TryDequeue(out var a)) Pending.Add(a);

            PendingAction? apply = null;
            for (var i = Pending.Count - 1; i >= 0; i--)
            {
                var a = Pending[i];
                if (a.TargetFrame > frame) continue;
                Pending.RemoveAt(i);
                if (a.TargetFrame < frame - MaxLateFrames) { StaleDropped++; continue; }
                if (apply == null || a.TargetFrame >= apply.Value.TargetFrame) apply = a;
            }

            if (apply is PendingAction act)
            {
                if (!KeyboardInjector.TrySetMask(act.Buttons, out var error))
                    Core.Plugin.Log.LogWarning("ACTION rejected: " + error);
                LastAck = act.AckSeq;
                LastAppliedFrame = frame;
                LastAppliedTarget = act.TargetFrame;
                releaseAtFrame = act.HoldFrames > 0 ? frame + act.HoldFrames : -1;
                BrainLost = false;
            }
            else if (releaseAtFrame >= 0 && frame >= releaseAtFrame)
            {
                KeyboardInjector.ReleaseAll();
                releaseAtFrame = -1;
            }

            if (driving)
            {
                long ms;
                lock (SinceLastAction) ms = SinceLastAction.ElapsedMilliseconds;
                if (ms > WatchdogMs && !BrainLost)
                {
                    KeyboardInjector.ReleaseAll();
                    BrainLost = true;
                    Core.Plugin.Log.LogWarning($"no ACTION for {ms} ms: released all keys");
                }
            }
        }

        /// <summary>Main thread.</summary>
        public static void OnBrainDisconnected()
        {
            if (driving) KeyboardInjector.ReleaseAll();
            driving = false;
            Pending.Clear();
            while (Incoming.TryDequeue(out _)) { }
            releaseAtFrame = -1;
        }
    }
}
