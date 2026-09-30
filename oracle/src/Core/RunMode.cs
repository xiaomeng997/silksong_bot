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

        private static bool HasFlag(string flag)
        {
            foreach (var a in Environment.GetCommandLineArgs())
                if (string.Equals(a, flag, StringComparison.OrdinalIgnoreCase)) return true;
            return false;
        }
    }
}
