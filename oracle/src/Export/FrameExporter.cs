using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using UnityEngine;

namespace SsOracle.Export
{
    /// <summary>
    /// Builds and sends one STATE message per rendered frame, sampled at WaitForEndOfFrame (DESIGN §3.1.1
    /// FrameExporter). Base fields are written here; the rest comes from registered IExporters. Measures its own
    /// main-thread cost (C14 budget: p50 <= 0.3 ms, p99 <= 1.0 ms) and reports it in the next STATE.
    /// </summary>
    internal sealed class FrameExporter : MonoBehaviour
    {
        private static readonly List<IExporter> Exporters = new List<IExporter>();
        private static readonly object EventLock = new object();
        private static List<FrameEvent> pendingEvents = new List<FrameEvent>();

        private readonly Ipc.MsgPackWriter writer = new Ipc.MsgPackWriter(64 * 1024);
        private readonly FrameContext ctx = new FrameContext();
        private readonly Stopwatch cost = new Stopwatch();
        private long lastCostTicks;
        private long fixedCycles;
        private long fixedCyclesAtLastFrame;
        private readonly Dictionary<string, long> sectionTicks = new Dictionary<string, long>();
        private readonly Dictionary<string, long> lastSectionTicks = new Dictionary<string, long>();

        public static void Register(IExporter exporter)
        {
            foreach (var e in Exporters)
                if (e.Key == exporter.Key) throw new InvalidOperationException($"exporter key '{exporter.Key}' registered twice");
            Exporters.Add(exporter);
        }

        /// <summary>Time.frameCount as of the last main-thread Update, for events emitted off the main thread.</summary>
        private static volatile int lastUpdateFrame;
        private static readonly int MainThreadId = System.Threading.Thread.CurrentThread.ManagedThreadId;

        /// <summary>Any thread (usually a Harmony hook on the main thread): record an event for this frame's STATE.
        /// Time.frameCount is only valid on the main thread (hooks in FixedUpdate run before this frame's Update, so a
        /// cached value would be one frame behind there); other threads get the last Update's frame.</summary>
        public static void Emit(string kind, Dictionary<string, object> data = null)
        {
            var frame = System.Threading.Thread.CurrentThread.ManagedThreadId == MainThreadId ? Time.frameCount : lastUpdateFrame;
            var ev = new FrameEvent { Kind = kind, Frame = frame, Qpc = Core.Qpc.Now(), Data = data };
            lock (EventLock) pendingEvents.Add(ev);
        }

        private void Update() => lastUpdateFrame = Time.frameCount;

        private void Start() => StartCoroutine(EndOfFrameLoop());

        private void FixedUpdate() => fixedCycles++;

        private IEnumerator EndOfFrameLoop()
        {
            var eof = new WaitForEndOfFrame();
            while (true)
            {
                yield return eof;
                var server = Ipc.FramedServer.Instance;
                if (server == null || !server.Connected)
                {
                    lock (EventLock) pendingEvents.Clear();
                    fixedCyclesAtLastFrame = fixedCycles;
                    continue;
                }
                cost.Restart();
                try
                {
                    Build();
                    var t = cost.ElapsedTicks;
                    server.EnqueueState(writer);
                    sectionTicks["enqueue"] = cost.ElapsedTicks - t;
                }
                catch (Exception e)
                {
                    Core.Plugin.Log.LogError("STATE build failed: " + e);
                }
                cost.Stop();
                lastCostTicks = cost.ElapsedTicks;
                lastSectionTicks.Clear();
                foreach (var kv in sectionTicks) lastSectionTicks[kv.Key] = kv.Value;
                sectionTicks.Clear();
            }
        }

        private void Build()
        {
            ctx.Frame = Time.frameCount;
            ctx.QpcEndOfFrame = Core.Qpc.Now();   // raw QPC: the brain's clock
            ctx.Gm = GameManager._instance;
            ctx.Pd = ctx.Gm != null ? ctx.Gm.playerData : null;
            ctx.Hero = HeroController.UnsafeInstance;
            ctx.MainCamera = Camera.main;
            ctx.Events.Clear();
            lock (EventLock)
            {
                ctx.Events.AddRange(pendingEvents);
                pendingEvents.Clear();
            }

            sectionTicks["ctx"] = cost.ElapsedTicks;
            var w = writer;
            w.Reset();
            w.MapHeader(BaseFieldCount + Exporters.Count);
            w.Key("f"); w.Int(ctx.Frame);
            w.Key("q"); w.Int(ctx.QpcEndOfFrame);
            w.Key("fc"); w.Int(fixedCycles);
            w.Key("fs"); w.Int(fixedCycles - fixedCyclesAtLastFrame);
            fixedCyclesAtLastFrame = fixedCycles;
            w.Key("udt"); w.Float(Time.unscaledDeltaTime);
            w.Key("dt"); w.Float(Time.deltaTime);
            w.Key("ts"); w.Float(Time.timeScale);
            w.Key("fdt"); w.Float(Time.fixedDeltaTime);
            w.Key("focus"); w.Bool(Application.isFocused);
            w.Key("cost_us"); w.Int(lastCostTicks * 1_000_000 / Stopwatch.Frequency);  // previous frame's build cost
            w.Key("drop"); w.Int(Ipc.FramedServer.Instance.DroppedStates);
            w.Key("cost_ex"); WriteSectionCosts(w);
            w.Key("act"); WriteAction(w);
            w.Key("ev"); WriteEvents(w);
            var mark = cost.ElapsedTicks;
            sectionTicks["base"] = mark - sectionTicks["ctx"];
            foreach (var e in Exporters)
            {
                w.Key(e.Key);
                if (Disabled.Contains(e.Key)) { w.Nil(); continue; }
                try
                {
                    e.Write(w, ctx);
                }
                catch (Exception ex)
                {
                    // A half-written value cannot be patched in msgpack: drop this STATE and write nil for the
                    // exporter from now on, so one broken section does not cost every frame.
                    Disabled.Add(e.Key);
                    throw new InvalidOperationException($"exporter '{e.Key}' failed and is now disabled", ex);
                }
                finally
                {
                    var now = cost.ElapsedTicks;
                    sectionTicks[e.Key] = now - mark;
                    mark = now;
                }
            }
        }

        private static readonly HashSet<string> Disabled = new HashSet<string>();

        private const int BaseFieldCount = 14;

        /// <summary>Previous frame's main-thread cost per section in microseconds (C14 budget accounting).</summary>
        private void WriteSectionCosts(Ipc.MsgPackWriter w)
        {
            w.MapHeader(lastSectionTicks.Count);
            foreach (var kv in lastSectionTicks)
            {
                w.Key(kv.Key);
                w.Int(kv.Value * 1_000_000 / Stopwatch.Frequency);
            }
        }

        private static void WriteAction(Ipc.MsgPackWriter w)
        {
            w.MapHeader(6);
            w.Key("mask"); w.UInt(Input.KeyboardInjector.LatchedMask);
            w.Key("ack"); w.UInt(Input.ActionScheduler.LastAck);
            w.Key("applied"); w.Int(Input.ActionScheduler.LastAppliedFrame);
            w.Key("target"); w.Int(Input.ActionScheduler.LastAppliedTarget);
            w.Key("stale"); w.Int(Input.ActionScheduler.StaleDropped);
            w.Key("lost"); w.Bool(Input.ActionScheduler.BrainLost);
        }

        private void WriteEvents(Ipc.MsgPackWriter w)
        {
            w.ArrayHeader(ctx.Events.Count);
            foreach (var e in ctx.Events)
            {
                w.MapHeader(4);
                w.Key("k"); w.Str(e.Kind);
                w.Key("f"); w.Int(e.Frame);
                w.Key("q"); w.Int(e.Qpc);
                w.Key("d"); Ipc.FramedServer.WriteObject(w, e.Data);
            }
        }
    }
}
