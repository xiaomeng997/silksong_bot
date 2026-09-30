using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using UnityEngine;

namespace SsOracle.Train
{
    /// <summary>One running harness operation: what its body reports back through the RPC.</summary>
    internal sealed class HarnessOp
    {
        public string Name;
        public readonly Stopwatch Clock = Stopwatch.StartNew();   // from RPC receipt: the reset time the brain sees
        public readonly int StartFrame = Time.frameCount;
        public string Error;
        public Dictionary<string, object> Result;
    }

    /// <summary>
    /// Runs multi-frame harness operations (savestate load, randomized start) as coroutines on the plugin host, one at
    /// a time. While one runs, ActionScheduler ignores ACTIONs and the brain-lost watchdog, so no key is held into the
    /// new episode and a slow load is not mistaken for a dead brain. The RPC is answered only when the body finishes.
    /// </summary>
    internal sealed class HarnessRunner : MonoBehaviour
    {
        private static HarnessRunner instance;

        /// <summary>Name of the running operation, or null.</summary>
        public static string Busy { get; private set; }

        public static void Install(GameObject host) => instance = host.AddComponent<HarnessRunner>();

        public static void Run(string name, Ipc.Rpc.Reply reply, Func<HarnessOp, IEnumerator> body)
        {
            if (Busy != null)
            {
                reply.Fail($"harness busy ({Busy})");
                return;
            }
            var op = new HarnessOp { Name = name };
            instance.StartCoroutine(instance.Wrap(op, body(op), reply));
        }

        /// <summary>Start a coroutine on the host (for code that must keep running beside the body, e.g. a pump we
        /// time out from outside).</summary>
        public static Coroutine Start(IEnumerator routine) => instance.StartCoroutine(routine);

        private IEnumerator Wrap(HarnessOp op, IEnumerator body, Ipc.Rpc.Reply reply)
        {
            Busy = op.Name;
            Input.ActionScheduler.HarnessBegin();
            try
            {
                while (true)
                {
                    object current;
                    try
                    {
                        if (!body.MoveNext()) break;
                        current = body.Current;
                    }
                    catch (Exception e)
                    {
                        op.Error = e.GetType().Name + ": " + e.Message;
                        Core.Plugin.Log.LogError($"{op.Name} failed: {e}");
                        break;
                    }
                    yield return current;
                }
            }
            finally
            {
                Busy = null;
                Input.ActionScheduler.HarnessEnd();
            }
            if (op.Error != null)
            {
                Core.Plugin.Log.LogWarning($"{op.Name}: {op.Error}");
                reply.Fail(op.Error);
            }
            else
            {
                reply.Ok(op.Result);
            }
        }

        /// <summary>Advances <paramref name="inner"/> as its own coroutine and records completion or the exception, so the
        /// caller can wait for it with a timeout even when it blocks inside a WaitUntil.</summary>
        public sealed class Pump
        {
            public bool Done;
            public Exception Error;

            public IEnumerator Run(IEnumerator inner)
            {
                while (true)
                {
                    object current;
                    try
                    {
                        if (!inner.MoveNext()) break;
                        current = inner.Current;
                    }
                    catch (Exception e)
                    {
                        Error = e;
                        break;
                    }
                    yield return current;
                }
                Done = true;
            }
        }
    }
}
