using System;
using System.Collections.Generic;
using System.Diagnostics;
using SsOracle.Events;
using UnityEngine;

namespace SsOracle.Progress
{
    /// <summary>
    /// PROGRESS messages (DESIGN §4.6, ≤ 2 Hz; field sources m0 §3.2 ProgressExporter). Every frame one step of a
    /// rotation runs: a chunk of the ~1300 primitive PlayerData fields is compared with its last value, or (once
    /// per rotation) a checksum of the tool data (Tools with toolAmountsOverride, ToolEquips, ExtraToolEquips).
    /// A full rotation takes ~22 frames, so no frame pays for the whole scan. Changes accumulate and go out at
    /// most every 0.5 s as {full: false, changed: {field: value}}, plus the tools/crest sections when the tool
    /// checksum changed. A full snapshot (all fields plus tools, crest and ToolEquips) is sent on brain connect,
    /// when PlayerData is replaced (load, new game, quit: m0:N42) and on RPC "progress.full"; it is read in one
    /// frame and written over several (<see cref="FullSliceUs"/> per frame, the tool part in a frame of its own).
    /// Enum fields are written by name. Everything runs inside the "prog" exporter, so its cost is part of cost_ex.
    /// </summary>
    internal sealed class ProgressExporter : Export.IExporter
    {
        public const int ChunkSize = 64;
        public const double MinIntervalSeconds = 0.5;

        /// <summary>Main-thread budget per frame for writing a full snapshot.</summary>
        public const long FullSliceUs = 200;

        private static ProgressExporter instance;

        private readonly Ipc.MsgPackWriter writer = new Ipc.MsgPackWriter(64 * 1024);
        private readonly Ipc.MsgPackWriter fullWriter = new Ipc.MsgPackWriter(64 * 1024);
        private readonly List<int> changed = new List<int>(64);
        private readonly List<int> dirtyList = new List<int>(128);
        private readonly List<Ipc.Rpc.Reply> fullWaiters = new List<Ipc.Rpc.Reply>();
        private readonly PdIdentity identity = new PdIdentity();
        private PlayerDataScanner scanner;
        private bool[] dirty;
        private bool broken;
        private int chunk;
        private bool baselined;
        private string fullReason;   // requested, not started yet
        private string buildReason;  // being written (null: no full snapshot in progress)
        private int buildIndex;
        private long buildStartFrame;
        private long toolsHash;
        private bool toolsDirty;
        private long lastSendQpc;
        private int seq;
        private int lastBytes;

        public string Key => "prog";

        public static void Install(GameObject host)
        {
            instance = new ProgressExporter();
            try
            {
                var sw = Stopwatch.StartNew();
                instance.CreateScanner();
                instance.scanner.Warm();
                Core.Plugin.Log.LogInfo($"ProgressExporter: {instance.scanner.Slots.Length} PlayerData fields in {instance.scanner.ChunkCount} chunks " +
                                        $"(IL readers: {instance.scanner.Emitted}), ready in {sw.Elapsed.TotalMilliseconds:F1} ms");
            }
            catch (Exception e)
            {
                instance.broken = true;
                Core.Plugin.Log.LogError("ProgressExporter disabled: " + e);
            }
            Export.FrameExporter.Register(instance);
            EventsRunner.BrainConnected += () => instance.RequestFull("connect", null);
            Ipc.Rpc.Register("progress.full", (args, reply) => instance.RequestFull("rpc", reply));
        }

        private void CreateScanner()
        {
            scanner = new PlayerDataScanner(ChunkSize);
            dirty = new bool[scanner.Slots.Length];
        }

        private void RequestFull(string reason, Ipc.Rpc.Reply reply)
        {
            if (broken)
            {
                reply?.Fail("progress exporter is disabled (see the BepInEx log)");
                return;
            }
            if (reply != null) fullWaiters.Add(reply);
            // A snapshot being written restarts, so a waiter always gets one read after its request.
            if (fullReason == null || reason == "rpc") fullReason = reason;
        }

        public void Write(Ipc.MsgPackWriter w, Export.FrameContext ctx)
        {
            if (ctx.Pd != null && !broken)
            {
                try
                {
                    Step(ctx);
                }
                catch (Exception e)
                {
                    // Keep the STATE section alive; report and stop scanning.
                    broken = true;
                    buildReason = null;
                    Core.Plugin.Log.LogError("ProgressExporter disabled: " + e);
                    foreach (var r in fullWaiters) r.Fail("progress exporter failed: " + e.Message);
                    fullWaiters.Clear();
                }
            }
            else if (ctx.Pd == null && fullWaiters.Count > 0)
            {
                // Between Quit_To_Menu and the new GameManager there is no PlayerData (m0:N42); a connect
                // request stays pending, an RPC gets an answer now.
                foreach (var r in fullWaiters) r.Fail("no PlayerData right now");
                fullWaiters.Clear();
            }
            w.MapHeader(6);
            w.Key("seq"); w.Int(seq);
            w.Key("pending"); w.Int(dirtyList.Count);
            w.Key("chunk"); w.Int(chunk);
            w.Key("fields"); w.Int(scanner != null ? scanner.Slots.Length : 0);
            w.Key("building"); w.Bool(buildReason != null);
            w.Key("ok"); w.Bool(!broken);
        }

        private void Step(Export.FrameContext ctx)
        {
            var pd = ctx.Pd;
            if (!identity.Same(pd) || !baselined)
            {
                // A different PlayerData needs a new baseline; a full snapshot already requested covers it, and
                // one being written for the old PlayerData restarts.
                if (fullReason == null) fullReason = baselined ? "pd_swap" : "start";
                baselined = true;
            }
            if (fullReason != null) BeginFull(ctx);
            if (buildReason != null)
            {
                ContinueFull(ctx);
                return;
            }

            // Rotation: ChunkCount field chunks, then the tool checksum.
            if (chunk < scanner.ChunkCount)
            {
                changed.Clear();
                scanner.ScanChunk(pd, chunk, changed);
                foreach (var i in changed)
                {
                    if (dirty[i]) continue;
                    dirty[i] = true;
                    dirtyList.Add(i);
                }
            }
            else
            {
                var h = ToolsHash(pd);
                if (h != toolsHash)
                {
                    toolsHash = h;
                    toolsDirty = true;
                }
            }
            chunk = (chunk + 1) % (scanner.ChunkCount + 1);
            if ((dirtyList.Count > 0 || toolsDirty) && Stopwatch.GetTimestamp() - lastSendQpc >= (long)(MinIntervalSeconds * Stopwatch.Frequency))
                SendDiff(ctx);
        }

        private void Header(Ipc.MsgPackWriter w, Export.FrameContext ctx, bool full, string reason, int extraKeys)
        {
            w.MapHeader(7 + extraKeys);
            w.Key("seq"); w.Int(++seq);
            w.Key("frame"); w.Int(ctx.Frame);
            w.Key("full"); w.Bool(full);
            w.Key("reason"); w.Str(reason);
            w.Key("scene"); w.Str(ctx.Gm != null ? ctx.Gm.sceneName : null);
            w.Key("t_live"); if (ctx.Gm != null) w.Float(ctx.Gm.PlayTime); else w.Nil();
        }

        private void SendDiff(Export.FrameContext ctx)
        {
            var w = writer;
            w.Reset();
            var tools = toolsDirty;
            Header(w, ctx, false, "diff", tools ? 5 : 0);
            w.Key("changed");
            w.MapHeader(dirtyList.Count);
            foreach (var i in dirtyList)
            {
                w.Key(scanner.Slots[i].Name);
                scanner.WriteValue(w, i);
                dirty[i] = false;
            }
            dirtyList.Clear();
            if (tools)
            {
                WriteTools(w, ctx.Pd);
                toolsDirty = false;
            }
            Send(w);
        }

        /// <summary>
        /// Read every field now (one frame, a few tens of microseconds) and start writing the snapshot; it is
        /// finished by <see cref="ContinueFull"/> over the next frames. Diff scanning pauses meanwhile; changes made
        /// in those frames show up in the first diffs after it, because the baseline is this frame's read.
        /// </summary>
        private void BeginFull(Export.FrameContext ctx)
        {
            buildReason = fullReason;
            fullReason = null;
            scanner.ReadAll(ctx.Pd);
            foreach (var i in dirtyList) dirty[i] = false;
            dirtyList.Clear();
            chunk = 0;
            buildIndex = 0;
            buildStartFrame = ctx.Frame;
            var w = fullWriter;
            w.Reset();
            Header(w, ctx, true, buildReason, 6);
            w.Key("changed");
            w.MapHeader(scanner.Slots.Length);
        }

        private void ContinueFull(Export.FrameContext ctx)
        {
            var w = fullWriter;
            var n = scanner.Slots.Length;
            if (buildIndex < n)
            {
                var t0 = Stopwatch.GetTimestamp();
                var budget = FullSliceUs * Stopwatch.Frequency / 1_000_000;
                while (buildIndex < n)
                {
                    w.Key(scanner.Slots[buildIndex].Name);
                    scanner.WriteValue(w, buildIndex);
                    buildIndex++;
                    if ((buildIndex & 15) == 0 && Stopwatch.GetTimestamp() - t0 > budget) break;
                }
                return; // the tool part (ToolItemManager, managers) gets a frame of its own
            }

            var pd = ctx.Pd;
            WriteTools(w, pd);
            w.Key("fields"); w.Int(n);
            toolsHash = ToolsHash(pd);
            toolsDirty = false;
            Send(w);
            var reason = buildReason;
            buildReason = null;
            var result = new Dictionary<string, object>
            {
                ["seq"] = seq, ["bytes"] = lastBytes, ["fields"] = n, ["reason"] = reason, ["frames"] = ctx.Frame - buildStartFrame + 1,
            };
            foreach (var r in fullWaiters) r.Ok(result);
            fullWaiters.Clear();
        }

        /// <summary>crest, tools, tool_equips, extra_equips, equipped (5 keys).</summary>
        private static void WriteTools(Ipc.MsgPackWriter w, PlayerData pd)
        {
            w.Key("crest");
            Ipc.FramedServer.WriteObject(w, new Dictionary<string, object> { ["current"] = pd.CurrentCrestID, ["previous"] = pd.PreviousCrestID });
            w.Key("tools"); Ipc.FramedServer.WriteObject(w, Tools(pd));
            w.Key("tool_equips"); Ipc.FramedServer.WriteObject(w, CrestEquips(pd));
            w.Key("extra_equips"); Ipc.FramedServer.WriteObject(w, ExtraEquips(pd));
            w.Key("equipped"); Ipc.FramedServer.WriteObject(w, Equipped(pd));
        }

        private void Send(Ipc.MsgPackWriter w)
        {
            lastBytes = w.Length;
            lastSendQpc = Stopwatch.GetTimestamp();
            Ipc.FramedServer.Instance?.Send(Ipc.Protocol.MsgType.Progress, w);
        }

        /// <summary>
        /// Checksum of the saved tool data as the game reads it: PlayerData.GetToolData (Tools with
        /// toolAmountsOverride applied), ToolEquips and ExtraToolEquips. PlayerData only (no managers), order
        /// independent; one rotation step.
        /// </summary>
        private static long ToolsHash(PlayerData pd)
        {
            unchecked
            {
                long h = 0;
                if (pd.Tools != null)
                {
                    foreach (var kv in pd.Tools.Enumerate())
                    {
                        var data = pd.GetToolData(kv.Key);
                        var v = ((long)data.AmountLeft << 3) | (data.IsUnlocked ? 1L : 0) | (data.IsHidden ? 2L : 0) | (data.HasBeenSeen ? 4L : 0);
                        h += Mix(1, kv.Key, v);
                    }
                }
                if (pd.ToolEquips != null)
                {
                    foreach (var kv in pd.ToolEquips.Enumerate())
                    {
                        long v = kv.Value.IsUnlocked ? 1 : 0;
                        var slots = kv.Value.Slots;
                        if (slots != null)
                            for (var i = 0; i < slots.Count; i++)
                                v = v * 31 + (slots[i].EquippedTool?.GetHashCode() ?? 0) * 2L + (slots[i].IsUnlocked ? 1 : 0);
                        h += Mix(2, kv.Key, v);
                    }
                }
                if (pd.ExtraToolEquips != null)
                {
                    foreach (var kv in pd.ExtraToolEquips.Enumerate())
                        h += Mix(3, kv.Key, (kv.Value.EquippedTool?.GetHashCode() ?? 0) * 2L + (kv.Value.IsUnlocked ? 1 : 0));
                }
                return h;
            }
        }

        // SplitMix64 finalizer over (table, name, value).
        private static long Mix(int table, string name, long value)
        {
            unchecked
            {
                var x = (ulong)(((long)(name?.GetHashCode() ?? 0) << 2) + table) * 0x9E3779B97F4A7C15UL ^ (ulong)value;
                x = (x ^ (x >> 30)) * 0xBF58476D1CE4E5B9UL;
                x = (x ^ (x >> 27)) * 0x94D049BB133111EBUL;
                return (long)(x ^ (x >> 31));
            }
        }

        /// <summary>
        /// Every tool the game knows (ToolItemManager) with its save data; falls back to the saved entries when
        /// the manager is not up. Never touches PlayerData.instance without an instance (it would create one).
        /// Amounts come from PlayerData.GetToolData, which applies toolAmountsOverride like the game does.
        /// </summary>
        private static Dictionary<string, object> Tools(PlayerData pd)
        {
            var tools = new Dictionary<string, object>();
            if (ManagerSingleton<ToolItemManager>.UnsafeInstance != null && PlayerData.HasInstance)
            {
                foreach (var tool in ToolItemManager.GetAllTools())
                {
                    if (tool == null) continue;
                    var data = pd.Tools != null ? pd.GetToolData(tool.name) : default;
                    var e = new Dictionary<string, object>
                    {
                        ["unlocked"] = tool.IsUnlocked,
                        ["amount"] = data.AmountLeft,
                        ["hidden"] = data.IsHidden,
                        ["seen"] = data.HasBeenSeen,
                        ["type"] = tool.Type.ToString(),
                    };
                    try
                    {
                        e["storage"] = ToolItemManager.GetToolStorageAmount(tool);
                        e["equipped"] = tool.IsEquipped;
                    }
                    catch (Exception)
                    {
                        // Storage and equip state depend on managers that may be mid-rebuild; skip them.
                    }
                    tools[tool.name] = e;
                }
            }
            else if (pd.Tools != null)
            {
                foreach (var kv in pd.Tools.Enumerate())
                {
                    var data = pd.GetToolData(kv.Key);
                    tools[kv.Key] = new Dictionary<string, object>
                    {
                        ["unlocked"] = data.IsUnlocked, ["amount"] = data.AmountLeft, ["hidden"] = data.IsHidden, ["seen"] = data.HasBeenSeen,
                    };
                }
            }
            return tools;
        }

        private static Dictionary<string, object> CrestEquips(PlayerData pd)
        {
            var crests = new Dictionary<string, object>();
            if (pd.ToolEquips == null) return crests;
            foreach (var kv in pd.ToolEquips.Enumerate())
            {
                var slots = new List<object>();
                if (kv.Value.Slots != null)
                    foreach (var slot in kv.Value.Slots)
                        slots.Add(new Dictionary<string, object> { ["tool"] = slot.EquippedTool, ["unlocked"] = slot.IsUnlocked });
                crests[kv.Key] = new Dictionary<string, object> { ["unlocked"] = kv.Value.IsUnlocked, ["slots"] = slots };
            }
            return crests;
        }

        private static Dictionary<string, object> ExtraEquips(PlayerData pd)
        {
            var extra = new Dictionary<string, object>();
            if (pd.ExtraToolEquips == null) return extra;
            foreach (var kv in pd.ExtraToolEquips.Enumerate())
                extra[kv.Key] = new Dictionary<string, object> { ["tool"] = kv.Value.EquippedTool, ["unlocked"] = kv.Value.IsUnlocked };
            return extra;
        }

        /// <summary>Tool names equipped on the current crest, then the extra (floating) slots.</summary>
        private static List<object> Equipped(PlayerData pd)
        {
            var names = new List<object>();
            if (pd.ToolEquips != null && !string.IsNullOrEmpty(pd.CurrentCrestID))
            {
                var slots = pd.ToolEquips.GetData(pd.CurrentCrestID).Slots;
                if (slots != null)
                    foreach (var slot in slots)
                        if (!string.IsNullOrEmpty(slot.EquippedTool)) names.Add(slot.EquippedTool);
            }
            if (pd.ExtraToolEquips != null)
                foreach (var kv in pd.ExtraToolEquips.Enumerate())
                    if (!string.IsNullOrEmpty(kv.Value.EquippedTool)) names.Add(kv.Value.EquippedTool);
            return names;
        }
    }
}
