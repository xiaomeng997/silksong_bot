"""Game enum values and oracle bit layouts that the safety code reads from STATE in oracle mode. Copies, not imports:
safety/ may not import ssbot.ipc (DESIGN §8.2 import firewall). Sources: 1.0.30000 GlobalEnums (GameState, UIState,
MainMenuState, PermadeathModes) and oracle/src/Input/PauseGate.cs (STATE pause.blk).
"""
# GlobalEnums.GameState
GS_INACTIVE, GS_MAIN_MENU, GS_LOADING, GS_ENTERING_LEVEL, GS_PLAYING, GS_PAUSED, GS_EXITING_LEVEL, GS_CUTSCENE, \
    GS_PRIMER = range(9)
GS_NAMES = ("INACTIVE", "MAIN_MENU", "LOADING", "ENTERING_LEVEL", "PLAYING", "PAUSED", "EXITING_LEVEL", "CUTSCENE",
            "PRIMER")

# GlobalEnums.UIState
UI_PAUSED = 5

# GlobalEnums.MainMenuState (UIManager.menuState; only meaningful while UIState is PAUSED during a game: it keeps its
# last value otherwise, e.g. SAVE_PROFILES = 6 until the first pause of a session)
MENU_OPTIONS_MENU = 2
MENU_EXIT_PROMPT = 10
MENU_PAUSE_MENU = 17

# GlobalEnums.PermadeathModes
PD_DEAD = 2

# STATE pause.blk (PauseGate.Blockers): a Pause press pauses only when blk == 0; otherwise the game drops it
BLK_DISABLE_PAUSE = 1
BLK_TIME_SLOWED = 2
BLK_PAUSE_LOCKOUT = 4          # !InputHandler.PauseAllowed (0.3 s after a pause / unpause, ReturnToMainMenu, ...)
BLK_MSG_CANVAS = 8             # GenericMessageCanvas (SAVE_FAILED in game)
BLK_BLOCKING_INTERACT = 16
BLK_NOT_ACCEPTING_INPUT = 32
BLK_GAME_STATE = 64            # GameState != PLAYING
BLK_NO_GAME = 128
BLK_NAMES = {BLK_DISABLE_PAUSE: "DISABLE_PAUSE", BLK_TIME_SLOWED: "TIME_SLOWED", BLK_PAUSE_LOCKOUT: "PAUSE_LOCKOUT",
             BLK_MSG_CANVAS: "MSG_CANVAS", BLK_BLOCKING_INTERACT: "BLOCKING_INTERACT",
             BLK_NOT_ACCEPTING_INPUT: "NOT_ACCEPTING_INPUT", BLK_GAME_STATE: "GAME_STATE", BLK_NO_GAME: "NO_GAME"}


def blk_names(blk: int) -> list[str]:
    return [name for bit, name in BLK_NAMES.items() if blk & bit]
