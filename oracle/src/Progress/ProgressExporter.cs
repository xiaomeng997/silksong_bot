using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.CompilerServices;
using SsOracle.Events;
using UnityEngine;

namespace SsOracle.Progress
{
    /// <summary>
    /// PROGRESS messages (DESIGN §4.6, ≤ 2 Hz; field sources m0 §3.2 ProgressExporter). Every frame one chunk of
    /// the ~1300 primitive PlayerData fields is compared with its last value (a full pass takes ~21 frames), so
    /// no frame pays for the whole scan; changed fields accumulate and go out at most every 0.5 s as
    /// {full: false, changed: {field: value}}. A full snapshot (all fields plus tools, crest and ToolEquips) is
    /// sent on brain connect, when PlayerData is replaced (load, new game, quit: m0:N42) and on RPC
    /// "progress.full". Enum fields are written by name. The scan runs inside the "prog" exporter, so its cost
    /// is part of cost_ex.
    /// </summary>
    internal sealed class ProgressExporter : Export.IExporter
    {
        public const int ChunkSize = 64;
        public const double MinIntervalSeconds = 0.5;

        private static ProgressExporter instance;

        private readonly Ipc.MsgPackWriter writer = new Ipc.MsgPackWriter(64 * 1024);
        private readonly List<int> changed = new List<int>(64);
        private readonly List<int> dirtyList = new List<int>(128);
        private readonly List<Ipc.Rpc.Reply> fullWaiters = new List<Ipc.Rpc.Reply>();
        private PlayerDataScanner scanner;
        private bool[] dirty;
        private bool broken;
        private int chunk;
        private bool baselined;
        private int pdId;
        private string fullReason;
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
            w.MapHeader(5);
            w.Key("seq"); w.Int(seq);
            w.Key("pending"); w.Int(dirtyList.Count);
            w.Key("chunk"); w.Int(chunk);
            w.Key("fields"); w.Int(scanner != null ? scanner.Slots.Length : 0);
            w.Key("ok"); w.Bool(!broken);
        }

        private void Step(Export.FrameContext ctx)
        {
            var pd = ctx.Pd;
            var id = RuntimeHelpers.GetHashCode(pd);
            if (!baselined || id != pdId)
            {
                // A different PlayerData needs a new baseline; a full snapshot already requested covers it.
                if (fullReason == null) fullReason = baselined ? "pd_swap" : "start";
                baselined = true;
                pdId = id;
            }
            if (fullReason != null)
            {
                SendFull(ctx);
                return;
            }

            changed.Clear();
            scanner.ScanChunk(pd, chunk, changed);
            chunk = (chunk + 1) % scanner.ChunkCount;
            foreach (var i in changed)
            {
                if (dirty[i]) continue;
                dirty[i] = true;
                dirtyList.Add(i);
            }
            if (dirtyList.Count > 0 && Stopwatch.GetTimestamp() - lastSendQpc >= (long)(MinIntervalSeconds * Stopwatch.Frequency))
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
            Header(w, ctx, false, "diff", 0);
            w.Key("changed");
            w.MapHeader(dirtyList.Count);
            foreach (var i in dirtyList)
            {
                w.Key(scanner.Slots[i].Name);
                scanner.WriteValue(w, i);
                dirty[i] = false;
            }
            dirtyList.Clear();
            Send(w);
        }

        private void SendFull(Export.FrameContext ctx)
        {
            var reason = fullReason;
            fullReason = null;
            scanner.ReadAll(ctx.Pd);
            foreach (var i in dirtyList) dirty[i] = false;
            dirtyList.Clear();
            chunk = 0;

            var w = writer;
            w.Reset();
            Header(w, ctx, true, reason, 6);
            w.Key("changed");
            w.MapHeader(scanner.Slots.Length);
            for (var i = 0; i < scanner.Slots.Length; i++)
            {
                w.Key(scanner.Slots[i].Name);
                scanner.WriteValue(w, i);
            }
            var pd = ctx.Pd;
            w.Key("crest");
            Ipc.FramedServer.WriteObject(w, new Dictionary<string, object> { ["current"] = pd.CurrentCrestID, ["previous"] = pd.PreviousCrestID });
            w.Key("tools"); Ipc.FramedServer.WriteObject(w, Tools(pd));
            w.Key("tool_equips"); Ipc.FramedServer.WriteObject(w, CrestEquips(pd));
            w.Key("extra_equips"); Ipc.FramedServer.WriteObject(w, ExtraEquips(pd));
            w.Key("equipped"); Ipc.FramedServer.WriteObject(w, Equipped(pd));
            w.Key("fields"); w.Int(scanner.Slots.Length);
            Send(w);
            var result = new Dictionary<string, object> { ["seq"] = seq, ["bytes"] = lastBytes, ["fields"] = scanner.Slots.Length, ["reason"] = reason };
            foreach (var r in fullWaiters) r.Ok(result);
            fullWaiters.Clear();
        }

        private void Send(Ipc.MsgPackWriter w)
        {
            lastBytes = w.Length;
            lastSendQpc = Stopwatch.GetTimestamp();
            Ipc.FramedServer.Instance?.Send(Ipc.Protocol.MsgType.Progress, w);
        }

        /// <summary>
        /// Every tool the game knows (ToolItemManager) with its save data; falls back to the saved entries when
        /// the manager is not up. Never touches PlayerData.instance without an instance (it would create one).
        /// </summary>
        private static Dictionary<string, object> Tools(PlayerData pd)
        {
            var tools = new Dictionary<string, object>();
            if (ManagerSingleton<ToolItemManager>.UnsafeInstance != null && PlayerData.HasInstance)
            {
                foreach (var tool in ToolItemManager.GetAllTools())
                {
                    if (tool == null) continue;
                    var data = pd.Tools != null ? pd.Tools.GetData(tool.name) : default;
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
                    tools[kv.Key] = new Dictionary<string, object>
                    {
                        ["unlocked"] = kv.Value.IsUnlocked, ["amount"] = kv.Value.AmountLeft, ["hidden"] = kv.Value.IsHidden, ["seen"] = kv.Value.HasBeenSeen,
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
