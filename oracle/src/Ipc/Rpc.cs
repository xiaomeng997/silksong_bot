using System;
using System.Collections.Generic;

namespace SsOracle.Ipc
{
    /// <summary>
    /// RPC registry (DESIGN §4.6 RPC_REQ/RES). Handlers run on Unity's main thread and receive the decoded
    /// args plus a reply callback; long operations (savestate load) may call it frames later. Modules register
    /// their own names in their Install methods, e.g. Rpc.Register("savestate.load", SavestateBridge.Load).
    /// </summary>
    internal static class Rpc
    {
        public delegate void Handler(Dictionary<string, object> args, Reply reply);

        /// <summary>Call exactly once: Ok(result) or Fail(message). Thread-safe.</summary>
        public sealed class Reply
        {
            private readonly Action<bool, object> send;
            private bool done;
            internal Reply(Action<bool, object> send) => this.send = send;

            public void Ok(object result = null) => Finish(true, result);
            public void Fail(string error) => Finish(false, error);

            private void Finish(bool ok, object value)
            {
                lock (this)
                {
                    if (done) return;
                    done = true;
                }
                send(ok, value);
            }
        }

        private static readonly Dictionary<string, Handler> Handlers = new Dictionary<string, Handler>();

        public static void Register(string name, Handler handler)
        {
            lock (Handlers)
            {
                if (Handlers.ContainsKey(name))
                    throw new InvalidOperationException($"RPC '{name}' registered twice");
                Handlers[name] = handler;
            }
        }

        /// <summary>Convenience for synchronous handlers returning a result.</summary>
        public static void Register(string name, Func<Dictionary<string, object>, object> handler) =>
            Register(name, (args, reply) => reply.Ok(handler(args)));

        public static IEnumerable<string> Names
        {
            get { lock (Handlers) return new List<string>(Handlers.Keys); }
        }

        /// <summary>Called on the main thread by the server's dispatch pump.</summary>
        internal static void Invoke(string name, Dictionary<string, object> args, Reply reply)
        {
            Handler h;
            lock (Handlers) Handlers.TryGetValue(name, out h);
            if (h == null) { reply.Fail($"unknown rpc '{name}'"); return; }
            try
            {
                h(args ?? new Dictionary<string, object>(), reply);
            }
            catch (Exception e)
            {
                reply.Fail(e.GetType().Name + ": " + e.Message);
            }
        }

        // Typed arg helpers.
        public static long Long(Dictionary<string, object> a, string k, long def = 0) =>
            a.TryGetValue(k, out var v) && v != null ? Convert.ToInt64(v) : def;

        public static double Double(Dictionary<string, object> a, string k, double def = 0) =>
            a.TryGetValue(k, out var v) && v != null ? Convert.ToDouble(v) : def;

        public static string Str(Dictionary<string, object> a, string k, string def = null) =>
            a.TryGetValue(k, out var v) && v != null ? Convert.ToString(v) : def;

        public static bool Bool(Dictionary<string, object> a, string k, bool def = false) =>
            a.TryGetValue(k, out var v) && v != null ? Convert.ToBoolean(v) : def;
    }
}
