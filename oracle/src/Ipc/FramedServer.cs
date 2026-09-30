using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Threading;
using UnityEngine;

namespace SsOracle.Ipc
{
    /// <summary>
    /// Oracle IPC v1 server (DESIGN §4.6): one brain client at a time. The main thread only enqueues finished
    /// frames; a writer thread drains the queue and a reader thread parses ACTION / RPC_REQ / HELLO. The oracle
    /// never blocks: when the brain falls behind, the oldest STATE frames are dropped and counted.
    /// </summary>
    internal sealed class FramedServer : MonoBehaviour
    {
        private const int MaxQueuedStates = 120; // 2 s at 60 fps

        public static FramedServer Instance { get; private set; }

        /// <summary>STATE frames dropped because the brain did not keep up (frame-delivery metric).</summary>
        public long DroppedStates => Interlocked.Read(ref droppedStates);
        public long SentStates => Interlocked.Read(ref sentStates);
        public bool Connected => client != null && helloReceived;

        private int port;
        private TcpListener listener;
        private Thread acceptThread;
        private volatile bool running;
        private volatile TcpClient client;
        private volatile bool helloReceived;
        private long droppedStates, sentStates;
        private uint seq;

        private readonly BlockingCollection<byte[]> outbox = new BlockingCollection<byte[]>(new ConcurrentQueue<byte[]>());
        private int queuedStates;
        private readonly ConcurrentQueue<Action> mainThreadWork = new ConcurrentQueue<Action>();

        public static FramedServer Install(GameObject host, string instance)
        {
            var s = host.AddComponent<FramedServer>();
            s.port = Protocol.Port(instance);
            s.StartListening();
            Instance = s;
            return s;
        }

        private void StartListening()
        {
            running = true;
            listener = new TcpListener(IPAddress.Loopback, port);
            listener.Start();
            acceptThread = new Thread(AcceptLoop) { IsBackground = true, Name = "SsOracle.Ipc.Accept" };
            acceptThread.Start();
            Core.Plugin.Log.LogInfo($"IPC v1 listening on 127.0.0.1:{port}");
        }

        private void OnDestroy()
        {
            running = false;
            try { listener?.Stop(); } catch { }
            try { client?.Close(); } catch { }
            outbox.CompleteAdding();
        }

        /// <summary>Main thread: queue a finished STATE payload. Drops the oldest queued STATE when full.</summary>
        public void EnqueueState(MsgPackWriter payload)
        {
            if (!Connected) return;
            var frame = Protocol.Frame(Protocol.MsgType.State, unchecked(seq++), payload.Buffer, payload.Length);
            if (Interlocked.Increment(ref queuedStates) > MaxQueuedStates)
            {
                Interlocked.Decrement(ref queuedStates);
                Interlocked.Increment(ref droppedStates);
                return;
            }
            outbox.Add(frame);
        }

        /// <summary>Any thread: send a non-STATE message (TERRAIN, PROGRESS, RPC_RES). Never dropped.</summary>
        public void Send(Protocol.MsgType type, MsgPackWriter payload)
        {
            if (client == null) return;
            outbox.Add(Protocol.Frame(type, unchecked(seq++), payload.Buffer, payload.Length));
        }

        private void Update()
        {
            while (mainThreadWork.TryDequeue(out var work))
            {
                try { work(); }
                catch (Exception e) { Core.Plugin.Log.LogError("IPC main-thread work failed: " + e); }
            }
        }

        private void AcceptLoop()
        {
            while (running)
            {
                TcpClient c;
                try { c = listener.AcceptTcpClient(); }
                catch { return; }
                c.NoDelay = true;
                client = c;
                helloReceived = false;
                Core.Plugin.Log.LogInfo("IPC v1 brain connected");
                var writer = new Thread(() => WriteLoop(c)) { IsBackground = true, Name = "SsOracle.Ipc.Write" };
                writer.Start();
                SendHello();
                try { ReadLoop(c); }
                catch (Exception e) when (running) { Core.Plugin.Log.LogWarning("IPC v1 read ended: " + e.Message); }
                client = null;
                helloReceived = false;
                try { c.Close(); } catch { }
                // Drain what is left for the dead connection.
                while (outbox.TryTake(out var f)) if (f.Length > 4 && f[4] == (byte)Protocol.MsgType.State) Interlocked.Decrement(ref queuedStates);
                mainThreadWork.Enqueue(() => Input.ActionScheduler.OnBrainDisconnected());
                Core.Plugin.Log.LogInfo("IPC v1 brain disconnected");
            }
        }

        private void WriteLoop(TcpClient c)
        {
            var stream = c.GetStream();
            try
            {
                foreach (var frame in outbox.GetConsumingEnumerable())
                {
                    if (client != c) return;
                    if (frame[4] == (byte)Protocol.MsgType.State)
                    {
                        Interlocked.Decrement(ref queuedStates);
                        Interlocked.Increment(ref sentStates);
                    }
                    stream.Write(frame, 0, frame.Length);
                }
            }
            catch (Exception e) when (running)
            {
                Core.Plugin.Log.LogWarning("IPC v1 write ended: " + e.Message);
            }
        }

        private void SendHello()
        {
            var w = new MsgPackWriter(1024);
            w.MapHeader(8);
            w.Key("role"); w.Str("oracle");
            w.Key("schema"); w.UInt(Protocol.SchemaVersion);
            w.Key("plugin"); w.Str(Core.Plugin.Version);
            w.Key("game"); w.Str(Core.Plugin.GameVersion);
            w.Key("instance"); w.Str(Guards.SaveRedirect.Instance);
            w.Key("qpc_freq"); w.Int(System.Diagnostics.Stopwatch.Frequency);
            w.Key("rpcs"); var names = new List<string>(Rpc.Names); w.ArrayHeader(names.Count); foreach (var n in names) w.Str(n);
            w.Key("buttons"); w.ArrayHeader(Input.KeyboardInjector.ButtonNames.Length); foreach (var b in Input.KeyboardInjector.ButtonNames) w.Str(b);
            Send(Protocol.MsgType.Hello, w);
        }

        private void ReadLoop(TcpClient c)
        {
            var stream = c.GetStream();
            var lenBuf = new byte[4];
            while (running && client == c)
            {
                ReadExactly(stream, lenBuf, 4);
                var length = BitConverter.ToInt32(lenBuf, 0);
                if (length < Protocol.HeaderBytes || length > Protocol.MaxMessageBytes)
                    throw new InvalidDataException($"bad frame length {length}");
                var body = new byte[length];
                ReadExactly(stream, body, length);
                var type = (Protocol.MsgType)body[0];
                var schema = body[1];
                var reqSeq = BitConverter.ToUInt32(body, 4);
                if (schema != Protocol.SchemaVersion)
                    throw new InvalidDataException($"schema {schema} != {Protocol.SchemaVersion}");
                switch (type)
                {
                    case Protocol.MsgType.Hello:
                        helloReceived = true;
                        break;
                    case Protocol.MsgType.Action:
                        Input.ActionScheduler.Enqueue(body, Protocol.HeaderBytes, length - Protocol.HeaderBytes);
                        break;
                    case Protocol.MsgType.RpcReq:
                        HandleRpc(new MsgPackReader(body, Protocol.HeaderBytes, length - Protocol.HeaderBytes).Read() as Dictionary<string, object>);
                        break;
                    default:
                        Core.Plugin.Log.LogWarning($"IPC v1: ignoring message type {type} (seq {reqSeq})");
                        break;
                }
            }
        }

        private void HandleRpc(Dictionary<string, object> req)
        {
            if (req == null) return;
            var id = Rpc.Long(req, "id");
            var name = Rpc.Str(req, "name");
            var args = req.TryGetValue("args", out var a) ? a as Dictionary<string, object> : null;
            var reply = new Rpc.Reply((ok, value) =>
            {
                var w = new MsgPackWriter(1024);
                w.MapHeader(3);
                w.Key("id"); w.Int(id);
                w.Key("ok"); w.Bool(ok);
                w.Key(ok ? "result" : "error");
                WriteObject(w, value);
                Send(Protocol.MsgType.RpcRes, w);
            });
            mainThreadWork.Enqueue(() => Rpc.Invoke(name, args, reply));
        }

        /// <summary>Serialize plain values returned by RPC handlers.</summary>
        internal static void WriteObject(MsgPackWriter w, object v)
        {
            switch (v)
            {
                case null: w.Nil(); break;
                case bool b: w.Bool(b); break;
                case string s: w.Str(s); break;
                case float f: w.Float(f); break;
                case double d: w.Double(d); break;
                case int i: w.Int(i); break;
                case long l: w.Int(l); break;
                case uint u: w.UInt(u); break;
                case ulong ul: w.UInt(ul); break;
                case Vector2 v2: w.Vec2(v2.x, v2.y); break;
                case Vector3 v3: w.Vec3(v3.x, v3.y, v3.z); break;
                case byte[] bytes: w.Bin(bytes, 0, bytes.Length); break;
                case System.Collections.IDictionary map:
                    w.MapHeader(map.Count);
                    foreach (System.Collections.DictionaryEntry e in map) { w.Str(Convert.ToString(e.Key)); WriteObject(w, e.Value); }
                    break;
                case System.Collections.IEnumerable list:
                    var items = new List<object>();
                    foreach (var x in list) items.Add(x);
                    w.ArrayHeader(items.Count);
                    foreach (var x in items) WriteObject(w, x);
                    break;
                default:
                    if (v.GetType().IsEnum) w.Str(v.ToString());
                    else w.Str(Convert.ToString(v, System.Globalization.CultureInfo.InvariantCulture));
                    break;
            }
        }

        private static void ReadExactly(Stream s, byte[] buf, int n)
        {
            var off = 0;
            while (off < n)
            {
                var r = s.Read(buf, off, n - off);
                if (r <= 0) throw new EndOfStreamException("brain closed the connection");
                off += r;
            }
        }
    }
}
