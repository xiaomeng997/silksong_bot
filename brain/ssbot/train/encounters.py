"""Combat encounters for training (M2 W0): where an episode starts, how the fight is started, and how it ends.

An encounter is a savestate (the hero in front of the arena, made by ssbot.probes.m2_bellbeast or a community
savestate checked the same way), an intro that does what the route does to start the fight, and the boss's "Control"
FSM, whose transitions (oracle "fsm" events) tell when the fight starts and ends. A DebugMod savestate load reloads the
scene fresh, so every episode replays the intro.

BELL_BEAST (route S03): Bone_05, "Bone Beast" (150 HP, the "Control" FSM: Dormant until the trigger, then Charge /
Leap / Bell Burst cycles; one Rage pattern at about 65 HP; the kill goes Control -> "Death Broadcast"). The way into
the arena is shut by "Thick Silk Vines" at x ~88; the route cuts them with Silkspear (quickcast, 4 silk), which the
savestate cannot keep (the vines grow back on every load). From a person's session (2026-09-30): the trigger fired at
hero x ~87.5 just after the cut; the boss emerges about 2 s after waking.

FORUM (route S25, M2 W8): Hang_04 with the additive Hang_04_boss, whose "Battle Scene" (BattleScene) runs 14 waves
(FORUM_WAVES, from the scene bundle; docs/facts/1.0.30000/forum.md) and is tracked by ssbot.train.gauntlet.GauntletTap
instead of a boss Control FSM. The hero enters from Hang_06 on the right (community savestate p7_s3: x 53.24); the
"Start Range" trigger (x 12.04-32.75) runs a short roar-and-pull cutscene and calls BattleScene.StartBattle, which
closes the gates (x 10.5-14.0 and 49.0-53.2) and starts wave 0 0.75 s later. Helpers: 4 s after wave index 1 starts
its "Call Ally" FSM sends ENTER FORUM to "Garmond Fighter" if PlayerData garmondAidForumBattle, else to "Shakra
Fighter" if shakraAidForumBattle (both reset by GameManager.LoadedFromMenu).
"""
import time
from dataclasses import dataclass, field
from typing import Callable

from ssbot.ipc.framing import mask
from ssbot.ipc.oracle_link import OracleLink
from ssbot.train.gauntlet import Wave

R = mask("right")
L = mask("left")


@dataclass(frozen=True)
class Encounter:
    name: str
    scene: str
    savestate: str
    boss_type: str                     # entity type_key of the boss ("" for a gauntlet)
    control_fsm: str                   # its FSM whose transitions mark the fight
    dormant: tuple[str, ...]           # Control states before the trigger
    death_states: tuple[str, ...]      # Control states that mean the boss is dying (CLEAR)
    intro: Callable[["Ctx"], int]      # starts the fight; returns the frame the boss woke
    timebox_s: float                   # STUCK after this long from the wake
    arena_x: tuple[float, float]       # walkable arena floor, for policies (x min, x max)
    floor_y: float
    waves: tuple[Wave, ...] = ()       # a gauntlet's BattleScene waves (ssbot.train.gauntlet); () for a boss
    battle_name: str = ""              # its BattleScene GameObject (STATE room.battles[].name)


@dataclass
class Ctx:
    """What an intro needs: the link and the tracker of the boss's Control FSM (ssbot.train.episode.FightTap)."""
    link: OracleLink
    tap: "object"
    log: list = field(default_factory=list)


def _walk_until(ctx: Ctx, button: int, done: Callable[[dict], bool], timeout_s: float) -> dict:
    link = ctx.link
    last = link.frame
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        s = link.wait_state(newer_than=last, timeout_s=1.0)
        last = s["f"]
        if done(s):
            link.act(last + 2, 0, hold_frames=0)
            return s
        link.act(last + 2, button, hold_frames=0)
    link.act(link.frame + 2, 0, hold_frames=0)
    raise TimeoutError("intro: walk condition not met")


def _idle(ctx: Ctx, frames: int) -> dict:
    link = ctx.link
    last = link.frame
    end = last + frames
    s = link.state
    while last < end:
        s = link.wait_state(newer_than=last, timeout_s=1.0)
        last = s["f"]
        link.act(last + 2, 0, hold_frames=0)
    return s


def _hold(ctx: Ctx, button: int, frames: int) -> dict:
    link = ctx.link
    last = link.frame
    s = link.state
    for _ in range(frames):
        link.act(last + 2, button, hold_frames=0)
        s = link.wait_state(newer_than=last, timeout_s=1.0)
        last = s["f"]
    return s


def bell_beast_intro(ctx: Ctx) -> int:
    """Walk to the vines, cut them with Silkspear, walk on until the boss wakes. Returns the wake frame."""
    tap = ctx.tap
    s = _walk_until(ctx, R, lambda s: s["hero"]["pos"][0] >= 84.4, timeout_s=6.0)
    s = _idle(ctx, 8)
    if s["hero"]["silk"] < 4:
        raise RuntimeError(f"intro: silk {s['hero']['silk']} < 4, cannot cut the vines")
    # 4 of the first data run's 85 intros never cast (silk stayed 9): the load was still sliding the hero back to the
    # savestate's x, so the walk ended at once and the press came while the game was moving her (the episode now
    # waits for the hero to settle first, ssbot.train.episode.wait_settled). The cast locks her for ~73 frames
    # (1.2 s); a press that is eaten anyway is retried while silk is unspent.
    link = ctx.link
    cut_from = len(tap.freezes)
    cut = False
    for attempt in range(3):
        silk0 = link.state["hero"]["silk"]
        _hold(ctx, mask("quickcast"), 4)
        deadline = time.monotonic() + 1.5
        while time.monotonic() < deadline and not cut:
            s = _idle(ctx, 2)
            cut = any("Vines" in str(f.get("fsm")) for f in tap.freezes[cut_from:])
        ctx.log.append({"attempt": attempt, "vines_cut": cut, "silk_after": link.state["hero"]["silk"]})
        if cut or link.state["hero"]["silk"] < silk0:
            break
        _idle(ctx, 10)
    if not cut:
        raise RuntimeError("intro: the Silkspear cast did not cut the vines")
    _idle(ctx, 20)
    _walk_until(ctx, R, lambda s: tap.control not in BELL_BEAST.dormant + (None,), timeout_s=8.0)
    return tap.wake_frame


BELL_BEAST = Encounter(
    name="BellBeast", scene="Bone_05", savestate="bellbeast_arena", boss_type="Bone Beast", control_fsm="Control",
    dormant=("Init", "Dormant"), death_states=("Death Broadcast",), intro=bell_beast_intro, timebox_s=240.0,
    arena_x=(73.5, 97.5), floor_y=3.5677)   # the person's fight: hero x 78.3-97.4, boss x 73.5-97.4


# Hang_04_boss "Battle Scene".waves in order (UnityPy dump of the 1.0.30000 scene bundle, BattleWave fields and the
# HealthManager children; hp: Song Reed 55, Song Pilgrim 01 38, Song Pilgrim 03 55, Pilgrim 03 Song 35, Song Handmaiden
# 48, Song Administrator 60, Song Pilgrim Maestro 65, Song Heavy Sentry 230). remaining_to_end 2 / 1 lets the next wave
# start while enemies of this one still live (waves 2, 4, 9).
FORUM_WAVES = (
    Wave(0, "Wave 1", 0.0, 0, ("Song Reed", "Song Pilgrim 01", "Song Pilgrim 03")),
    Wave(1, "Wave 2 - Call Ally", 1.0, 0, ("Song Pilgrim 03 (2)", "Song Pilgrim 03 (3)")),
    Wave(2, "Wave 3", 1.0, 2, ("Pilgrim 03 Song", "Song Reed (1)")),
    Wave(3, "Wave 4", 0.5, 0, ("Song Handmaiden",)),
    Wave(4, "Wave 5 - Song Admins", 1.0, 1, ("Song Administrator", "Song Administrator (1)")),
    Wave(5, "Wave 6", 0.0, 0, ("Song Handmaiden",)),
    Wave(6, "Wave 7 - Maestro x 2", 1.0, 0, ("Song Pilgrim Maestro", "Song Pilgrim Maestro (1)")),
    Wave(7, "Wave 8 - Heavy Sentry", 1.5, 0, ("Song Heavy Sentry",)),
    Wave(8, "Wave 9", 3.0, 0, ("Song Reed (2)", "Song Reed (3)", "Pilgrim 03 Song")),
    Wave(9, "Wave 10", 1.0, 2, ("Song Pilgrim 03 (2)", "Pilgrim 03 Song", "Pilgrim 03 Song (1)")),
    Wave(10, "Wave 11", 0.5, 0, ("Song Handmaiden",)),
    Wave(11, "Wave 12", 1.0, 0, ("Pilgrim 03 Song (1)", "Song Administrator", "Song Administrator (1)")),
    Wave(12, "Wave 13 - Maestro", 2.0, 0, ("Song Pilgrim Maestro", "Song Reed")),
    Wave(13, "Wave 14 - Finale", 2.0, 0, ("Song Heavy Sentry (2)", "Song Heavy Sentry (3)")),
)

FORUM_START_X = 32.75          # right edge of the "Start Range" trigger box (x 12.04-32.75, y 0.95-25.04)


def forum_intro(ctx: Ctx) -> int:
    """Walk left from the Hang_06 side into the "Start Range" trigger, then wait out the roar-and-pull cutscene until
    the battle has started (GauntletTap.wake_frame: room.battles started, or wave 0's enemies spawning). Returns the
    battle-start frame."""
    tap = ctx.tap

    def inside(s: dict) -> bool:
        # in the trigger, or the roar cutscene has taken control (it can stop her right at its edge)
        x = s["hero"]["pos"][0]
        return (tap.wake_frame is not None or x <= FORUM_START_X - 1.0
                or (x <= FORUM_START_X + 1.0 and not s["hero"]["hero_accepting_input"]))

    s = _walk_until(ctx, L, inside, timeout_s=10.0)
    ctx.log.append({"walked_to_x": round(s["hero"]["pos"][0], 2), "f": s["f"]})
    link = ctx.link
    deadline = time.monotonic() + 15.0
    last = link.frame
    while tap.wake_frame is None and time.monotonic() < deadline:
        s = link.wait_state(newer_than=last, timeout_s=1.0)
        last = s["f"]
        link.act(last + 2, 0, hold_frames=0)
    if tap.wake_frame is None:
        raise RuntimeError("intro: the Forum battle did not start")
    ctx.log.append({"battle_start_f": tap.wake_frame, "how": tap.control})
    return tap.wake_frame


FORUM = Encounter(
    name="Forum", scene="Hang_04", savestate="fo_A", boss_type="", control_fsm="Control", dormant=(),
    death_states=(), intro=forum_intro, timebox_s=900.0, arena_x=(14.0, 49.0), floor_y=4.5677,
    waves=FORUM_WAVES, battle_name="Battle Scene")   # gates' inner faces x 14.01 / 48.99; floor y: savestate p7_s3


def forum_variant(arm: str) -> Encounter:
    """FORUM on another savestate arm (fo_A, fo_B, fo_C, fo_A5; docs/facts/1.0.30000/forum.md)."""
    from dataclasses import replace
    return replace(FORUM, name=f"Forum_{arm}", savestate=f"fo_{arm}")


ENCOUNTERS = {e.name: e for e in (BELL_BEAST, FORUM, *(forum_variant(a) for a in ("A", "B", "C", "A5")))}
