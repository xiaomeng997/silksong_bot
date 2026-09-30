namespace SsOracle.Input
{
    /// <summary>
    /// Placeholder for the M1 legacy-input shim (DESIGN §3.1.1 Input, m0:N36): OR injected key-down edges into the
    /// callers of UnityEngine.Input.anyKeyDown (InputHandler.CutsceneInput / StagCutsceneInput,
    /// GameManager.UpdateEngagement, IdleMemoryCleaner). KeyboardInjector reports every latched mask here.
    /// </summary>
    internal static partial class LegacyInputShim
    {
        private static uint previous;

        /// <summary>True during the frame in which some injected button went from up to down.</summary>
        public static bool InjectedKeyDownThisFrame { get; private set; }

        public static void OnLatched(uint mask)
        {
            InjectedKeyDownThisFrame = (mask & ~previous) != 0;
            previous = mask;
        }
    }
}
