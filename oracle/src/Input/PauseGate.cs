using GlobalEnums;

namespace SsOracle.Input
{
    /// <summary>
    /// Whether a Pause key press would be accepted right now: the same blocker bits as STATE "pause.blk"
    /// (Export.PauseExporter; DESIGN §3.1.2 pause_blockers; m0 §2.4, N12, N14). A press while any bit is set is
    /// dropped by the game, not queued. Read-only: the oracle pauses only through real key injection and never writes
    /// disablePause / timeSlowedCount / ignoreUnpause (m0:N43). Meant as the single definition of those bits: until
    /// PauseExporter calls Blockers too, the two must be kept identical (same order as GameManager.PauseGameToggle plus
    /// InputHandler's PauseAllowed / acceptingInput gates).
    /// </summary>
    internal static class PauseGate
    {
        public const uint DisablePause = 1, TimeSlowed = 2, PauseLockout = 4, MsgCanvas = 8,
            BlockingInteract = 16, NotAcceptingInput = 32, GameStateNotPlaying = 64, NoGame = 128;

        /// <summary>0 = a Pause press this frame pauses the game. Main thread only; no allocation.</summary>
        public static uint Blockers(GameManager gm, PlayerData pd)
        {
            var ih = gm != null ? gm.inputHandler : null;
            if (gm == null || pd == null || ih == null) return NoGame;
            uint blk = 0;
            if (pd.disablePause) blk |= DisablePause;
            if (gm.TimeSlowed) blk |= TimeSlowed;
            if (!ih.PauseAllowed) blk |= PauseLockout;
            if (GenericMessageCanvas.IsActive) blk |= MsgCanvas;
            if (InteractManager.BlockingInteractable != null && !pd.atBench) blk |= BlockingInteract;
            if (!ih.acceptingInput) blk |= NotAcceptingInput;
            if (gm.GameState != GameState.PLAYING) blk |= GameStateNotPlaying;
            return blk;
        }
    }
}
