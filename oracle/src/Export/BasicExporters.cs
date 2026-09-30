using HarmonyLib;
using UnityEngine.SceneManagement;

namespace SsOracle.Export
{
    /// <summary>
    /// The core STATE sections every consumer needs (DESIGN §3.1.2; field sources m0 §3.1):
    /// "game" (GameManager state, scenes, timers, cheat flags) and "pause" (pause/quit blockers).
    /// </summary>
    internal static class BasicExporters
    {
        public static void Register()
        {
            FrameExporter.Register(new GameExporter());
            FrameExporter.Register(new PauseExporter());
            FrameExporter.Register(new InputExporter());
        }
    }

    internal sealed class GameExporter : IExporter
    {
        private static readonly AccessTools.FieldRef<GameManager, float> SessionPlayTimer =
            AccessTools.FieldRefAccess<GameManager, float>("sessionPlayTimer");
        private static readonly AccessTools.FieldRef<GameManager, float> SessionStartTime =
            AccessTools.FieldRefAccess<GameManager, float>("sessionStartTime");
        private static readonly AccessTools.FieldRef<GameManager, int> TimeSlowedCount =
            AccessTools.FieldRefAccess<GameManager, int>("timeSlowedCount");

        public string Key => "game";

        public void Write(Ipc.MsgPackWriter w, FrameContext ctx)
        {
            var gm = ctx.Gm;
            if (gm == null) { w.Nil(); return; }
            var pd = ctx.Pd;
            var ui = gm.ui;

            w.MapHeader(19);
            w.Key("gs"); w.UInt((ulong)gm.GameState);
            w.Key("ui"); if (ui != null) w.UInt((ulong)ui.uiState); else w.Nil();
            w.Key("menu"); if (ui != null) w.UInt((ulong)ui.menuState); else w.Nil();
            w.Key("paused"); w.Bool(gm.isPaused);
            w.Key("slowed"); w.Int(TimeSlowedCount(gm));
            w.Key("transition"); w.Bool(gm.IsInSceneTransition);
            w.Key("entered"); w.Bool(gm.HasFinishedEnteringScene);
            w.Key("scene_raw"); w.Str(SceneManager.GetActiveScene().name);
            w.Key("scene"); w.Str(gm.sceneName);
            w.Key("gate"); w.Str(gm.entryGateName);
            w.Key("next"); w.Str(gm.nextSceneName);
            w.Key("additive");
            var n = SceneManager.sceneCount;
            w.ArrayHeader(n);
            for (var i = 0; i < n; i++) w.Str(SceneManager.GetSceneAt(i).name);
            w.Key("memory"); w.Bool(gm.sm != null && gm.IsMemoryScene());
            w.Key("pd_mode"); if (pd != null) w.UInt((ulong)pd.permadeathMode); else w.Nil();
            w.Key("t_live"); w.Float(gm.PlayTime);
            w.Key("t_saved"); if (pd != null) w.Float(pd.playTime); else w.Nil();
            w.Key("t_sess"); w.Float(SessionPlayTimer(gm));
            w.Key("t_start"); w.Float(SessionStartTime(gm));
            w.Key("cheat"); w.UInt(CheatFlags(gm));
        }

        /// <summary>bit0 CheatManager.Invincibility != Off, bit1 scene HeroKeepHealth, bit2 tools in Cutscene state,
        /// bit3 BossSceneController present (should never be set on the route; m0:N11).</summary>
        private static uint CheatFlags(GameManager gm)
        {
            uint f = 0;
            if (CheatManager.Invincibility != CheatManager.InvincibilityStates.Off) f |= 1;
            if (gm.sm != null && gm.sm.HeroKeepHealth) f |= 2;
            if (ToolItemManager.ActiveState == ToolsActiveStates.Cutscene) f |= 4;
            if (BossSceneController.Instance != null) f |= 8;
            return f;
        }
    }

    /// <summary>
    /// Pause and quit blockers (DESIGN §3.1.2 pause_blockers; m0 §2.4). "blk" bits:
    /// 1 DISABLE_PAUSE, 2 TIME_SLOWED, 4 PAUSE_LOCKOUT (!PauseAllowed), 8 MSG_CANVAS,
    /// 16 BLOCKING_INTERACT (and not at a bench), 32 NOT_ACCEPTING_INPUT, 64 GAME_STATE_NOT_PLAYING.
    /// Esc pauses only when blk == 0.
    /// </summary>
    internal sealed class PauseExporter : IExporter
    {
        public string Key => "pause";

        public void Write(Ipc.MsgPackWriter w, FrameContext ctx)
        {
            var gm = ctx.Gm;
            var pd = ctx.Pd;
            var ih = gm != null ? gm.inputHandler : null;
            if (gm == null || pd == null || ih == null) { w.Nil(); return; }

            var blocking = InteractManager.BlockingInteractable != null;
            var blk = Input.PauseGate.Blockers(gm, pd);   // one definition of the pause gate, shared with the input harness

            w.MapHeader(8);
            w.Key("blk"); w.UInt(blk);
            w.Key("dsq"); w.Bool(pd.disableSaveQuit);
            w.Key("dinv"); w.Bool(pd.disableInventory);
            w.Key("inv"); w.Bool(pd.isInventoryOpen);
            w.Key("bench"); w.Bool(pd.atBench);
            w.Key("interact"); w.Bool(blocking);
            w.Key("preload"); w.Bool(ScenePreloader.HasPendingOperations);
            w.Key("hero_input"); w.Bool(ctx.Hero != null && ctx.Hero.acceptingInput);
        }
    }
}
