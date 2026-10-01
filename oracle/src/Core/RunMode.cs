using System;

namespace SsOracle.Core
{
    /// <summary>
    /// Command-line switches of the training copy. "-ssbot-human" = a person plays (DESIGN D12): the oracle only
    /// records; it does not own the keyboard, does not disable the mouse or force the cursor, and keeps the
    /// vanilla focus behaviour. Guards that change gameplay stay off in this mode.
    /// </summary>
    internal static class RunMode
    {
        public static readonly bool Human = HasFlag("-ssbot-human");

        /// <summary>"-ssbot-minimal": only the save redirect (and its AppConfig/DebugMod parts), nothing per frame: no IPC,
        /// exporters, hooks or input. The near-vanilla baseline of the frame-time comparison (DESIGN C14: + 0.5 ms vs
        /// vanilla, PresentMon). "-ssbot-minimal-load N" also loads save slot N once from the title screen.</summary>
        public static readonly bool Minimal = HasFlag("-ssbot-minimal");

        /// <summary>Save slot to load in minimal mode (1-4), 0 when the flag is absent.</summary>
        public static readonly int MinimalLoadSlot = IntArg("-ssbot-minimal-load");

        private static int IntArg(string flag)
        {
            var args = Environment.GetCommandLineArgs();
            for (var i = 0; i < args.Length - 1; i++)
                if (string.Equals(args[i], flag, StringComparison.OrdinalIgnoreCase) && int.TryParse(args[i + 1], out var v))
                    return v;
            return 0;
        }

        private static bool HasFlag(string flag)
        {
            foreach (var a in Environment.GetCommandLineArgs())
                if (string.Equals(a, flag, StringComparison.OrdinalIgnoreCase)) return true;
            return false;
        }
    }
}
