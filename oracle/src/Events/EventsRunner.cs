using System;
using System.Diagnostics;
using UnityEngine;

namespace SsOracle.Events
{
    /// <summary>
    /// Main-thread driver for the tap: detects brain (re)connection, drains events raised on other threads, and
    /// runs the per-frame poll in LateUpdate. The poll runs before FrameExporter's end-of-frame build, so the
    /// changes it finds (direct field writes that no hook sees) land in the same frame's STATE. Its cost is
    /// reported as "tap".poll_us because it is not part of the STATE build that cost_ex measures.
    /// </summary>
    internal sealed class EventsRunner : MonoBehaviour
    {
        /// <summary>Raised on the main thread when a brain completes the HELLO exchange.</summary>
        public static event Action BrainConnected;

        public static long PollUs { get; private set; }

        private bool wasConnected;

        private void Update()
        {
            Tap.DrainForeign();
            var connected = Tap.Active;
            if (connected && !wasConnected)
            {
                // Values that changed while nobody listened are not events: start from what is there now.
                HpTap.Rebaseline();
                PdModeTap.Rebaseline();
                GateTap.Reset();
                DamageTap.ResetBlocked();
                HunterMeterTap.Rebaseline();
                try { BrainConnected?.Invoke(); }
                catch (Exception e) { Core.Plugin.Log.LogError("EventTap: BrainConnected handler failed: " + e); }
            }
            wasConnected = connected;
        }

        private void LateUpdate()
        {
            var t0 = Stopwatch.GetTimestamp();
            var gm = GameManager._instance;
            // Bookkeeping that must not pile up while no brain is connected (all are a few field reads).
            DamageCtx.ResetIfStale();
            HunterMeterTap.ResetIfStale();
            FreezeTap.Poll(gm);
            FlowTap.Poll(gm);
            if (!Tap.Active) return;
            var pd = gm != null ? gm.playerData : null;
            HpTap.Observe(pd, "poll", false);
            PdModeTap.Observe(pd, "poll");
            GateTap.Poll(gm, pd);
            DamageTap.PollBlocked();
            HunterMeterTap.Poll(HeroController.UnsafeInstance);
            PollUs = Tap.Us(t0, Stopwatch.GetTimestamp());
        }
    }

    /// <summary>
    /// STATE "tap": {n: last event sequence number, hp: [health, healthBlue], gates: GateTap bits (1 disable_pause,
    /// 2 disable_save_quit, 4 disable_inventory, 8 inventory_open, 16 pause_allowed, 32 msg_canvas), freezes: open
    /// FreezeMoment count, respawns: open hazard respawns, poll_us: this frame's poll cost, hooks_failed: hooks
    /// that could not be installed}.
    /// </summary>
    internal sealed class TapExporter : Export.IExporter
    {
        public string Key => "tap";

        public void Write(Ipc.MsgPackWriter w, Export.FrameContext ctx)
        {
            w.MapHeader(7);
            w.Key("n"); w.Int(Tap.Seq);
            w.Key("hp");
            if (ctx.Pd != null) { w.ArrayHeader(2); w.Int(ctx.Pd.health); w.Int(ctx.Pd.healthBlue); }
            else w.Nil();
            w.Key("gates"); w.UInt(GateTap.Bits);
            w.Key("freezes"); w.Int(FreezeTap.OpenCount);
            w.Key("respawns"); w.Int(FlowTap.OpenRespawnCount);
            w.Key("poll_us"); w.Int(EventsRunner.PollUs);
            w.Key("hooks_failed"); w.Int(Tap.FailedHooks);
        }
    }
}
