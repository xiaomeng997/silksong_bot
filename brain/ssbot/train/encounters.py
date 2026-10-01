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
"""
import time
from dataclasses import dataclass, field
from typing import Callable

from ssbot.ipc.framing import mask
from ssbot.ipc.oracle_link import OracleLink

R = mask("right")
L = mask("left")


@dataclass(frozen=True)
class Encounter:
    name: str
    scene: str
    savestate: str
    boss_type: str                     # entity type_key of the boss
    control_fsm: str                   # its FSM whose transitions mark the fight
    dormant: tuple[str, ...]           # Control states before the trigger
    death_states: tuple[str, ...]      # Control states that mean the boss is dying (CLEAR)
    intro: Callable[["Ctx"], int]      # starts the fight; returns the frame the boss woke
    timebox_s: float                   # STUCK after this long from the wake
    arena_x: tuple[float, float]       # walkable arena floor, for policies (x min, x max)
    floor_y: float


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

ENCOUNTERS = {e.name: e for e in (BELL_BEAST,)}
