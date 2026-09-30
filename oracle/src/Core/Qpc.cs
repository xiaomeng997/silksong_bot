using System.Runtime.InteropServices;
using System.Security;

namespace SsOracle.Core
{
    /// <summary>
    /// The raw QueryPerformanceCounter, the clock the brain stamps received messages and captured video frames with.
    /// Mono's Stopwatch.GetTimestamp cannot stand in for it across processes: on Windows it counts from the first call
    /// in this process (mono_100ns_ticks subtracts a start value and rescales to 10 MHz), which put STATE "q" about
    /// five hours behind the brain's QPC in the M1 record probe (2026-09-30). Durations inside the oracle may keep
    /// using Stopwatch; timestamps that leave the process (STATE and event "q", HELLO qpc_freq) use this.
    /// </summary>
    [SuppressUnmanagedCodeSecurity]
    internal static class Qpc
    {
        [DllImport("kernel32.dll")]
        private static extern bool QueryPerformanceCounter(out long value);

        [DllImport("kernel32.dll")]
        private static extern bool QueryPerformanceFrequency(out long value);

        public static readonly long Frequency = ReadFrequency();

        public static long Now()
        {
            QueryPerformanceCounter(out var v);
            return v;
        }

        private static long ReadFrequency()
        {
            QueryPerformanceFrequency(out var f);
            return f;
        }
    }
}
