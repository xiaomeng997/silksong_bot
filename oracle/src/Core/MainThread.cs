using System;
using System.Collections.Concurrent;
using System.Threading;
using UnityEngine;

namespace SsOracle.Core
{
    /// <summary>Runs work queued from other threads (the IPC thread) on Unity's main thread.</summary>
    internal sealed class MainThread : MonoBehaviour
    {
        private sealed class Job
        {
            public Func<string> Work;
            public string Result;
            public readonly ManualResetEventSlim Done = new ManualResetEventSlim(false);
        }

        private static readonly ConcurrentQueue<Job> Queue = new ConcurrentQueue<Job>();

        /// <summary>Blocks the calling (non-main) thread until the work has run on the main thread.</summary>
        public static string Run(Func<string> work, int timeoutMs = 2000)
        {
            var job = new Job { Work = work };
            Queue.Enqueue(job);
            return job.Done.Wait(timeoutMs) ? job.Result : "err main thread did not respond (game paused by the OS or loading?)";
        }

        private void Update()
        {
            while (Queue.TryDequeue(out var job))
            {
                try
                {
                    job.Result = job.Work();
                }
                catch (Exception e)
                {
                    job.Result = "err " + e.GetType().Name + ": " + e.Message;
                }
                job.Done.Set();
            }
        }
    }
}
