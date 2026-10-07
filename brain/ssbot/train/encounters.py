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
from dataclasses import dataclass, field, replace
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
    post_clear_s: float = 1.0          # the episode goes on this long after the kill (late hazards; a lethal hit
                                       # there is still a death: ssbot.train.episode)
    # The post-kill tail (DESIGN §3.5.7, the Last Judge row's rule for every encounter that sets it): after the kill
    # the episode goes on until no damage source has been live for tail_quiet_s of game time (ssbot.train.episode
    # live_threats: an enabled damage collider, or a hazard in one of tail_armed's states, which hurts later), at most
    # tail_max_s after the kill (then STUCK); None: the fixed post_clear_s window above.
    tail_quiet_s: float | None = None
    tail_max_s: float = 15.0
    tail_armed: tuple[tuple[str, tuple[str, ...]], ...] = ()   # (type_key prefix, FSM states) armed, no collider yet
    # the kill as the boss's "hit" event with dead (hp_before > 0, hp_after <= 0) when its Control FSM has no death
    # state (Lace 1: the defeat runs outside Control); the death states still count when there are any
    death_on_kill: bool = False
    # how the savestate differs from the route at this point (docs/facts/1.0.30000/route_bosses.md), for the record
    notes: str = ""
    # training-only late-phase start: after the wake the boss's HP is multiplied by a seeded draw from this range
    # (oracle RPC enemy.hp; ssbot.train.episode). None: the boss keeps its HP
    start_boss_hp: tuple[float, float] | None = None


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
    arena_x=(73.5, 97.5), floor_y=3.5677,   # the person's fight: hero x 78.3-97.4, boss x 73.5-97.4
    # what outlives the boss (docs/facts/1.0.30000/post_kill.md): the two attack bells of a kill in Burst Out (in
    # flight at the kill, rolling until their End Timer), a drop bell already falling; a drop bell in its Antic is
    # cancelled by the death (Antic -> Cancel on the kill frame), so Antic is armed only while the boss lives
    tail_quiet_s=2.0, tail_armed=(("BoneBeast DropBell", ("Antic",)),))

# The same fight with the Reaper crest equipped (M2 W8: the Reaper's attack polygons against the game's hit events,
# tools/attack_hit_audit). Savestate kn_bb_reaper: bellbeast_arena + crest.equip Reaper + Silk Spear in a Reaper skill
# slot (the intro cuts the vines with it), saved by the game (probes/kin_excite_forum --setup-bb).
BELL_BEAST_REAPER = replace(BELL_BEAST, name="BellBeastReaper", savestate="kn_bb_reaper")


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


# After the last kill BattleScene.EndBattle runs FreezeMoment EnemyBattleEndSlow (GameManager.cs:5132: ramp to 0.25x
# in 0.1 s, hold 1 s unscaled, back to 1x in 0.75 s: about 1.85 s of real time for 0.78 s of game time), then waits
# 1 s + battleEndPause 2 s of game time before it sets hang04Battle and sends FORUM BATTLE END (BattleScene.cs:444):
# about 4.1 s (245 frames) after the kill. The dying Clappers' bodies, rune slams and bombs still hurt meanwhile
# (runs 20261002_223640 ep0 f808877 and 230325 f910457: body contacts 13 and 2 frames after the freeze), so the
# episode runs 4.5 s past the kill. Complete gauntlets with the random data policy took 714-990 s (10 of 2026-10-02).
FORUM = Encounter(
    name="Forum", scene="Hang_04", savestate="fo_A", boss_type="", control_fsm="Control", dormant=(),
    death_states=(), intro=forum_intro, timebox_s=1500.0, arena_x=(14.0, 49.0), floor_y=4.5677,
    waves=FORUM_WAVES, battle_name="Battle Scene",   # gates' inner faces x 14.01 / 48.99; floor y: savestate p7_s3
    post_clear_s=4.5)


def forum_variant(arm: str) -> Encounter:
    """FORUM on another savestate arm (fo_A, fo_B, fo_C, fo_A5; docs/facts/1.0.30000/forum.md)."""
    return replace(FORUM, name=f"Forum_{arm}", savestate=f"fo_{arm}")


def forum_wave_intro(wave: int) -> Callable[[Ctx], int]:
    """The intro of a wave-start savestate (ssbot.train.wave_start: fo_r1_w<i>, taken during wave i): no walk and no
    roar; DebugMod's load restarts the battle at wave i by itself. Waits for room.battles to report the battle
    started, removes the earlier waves' never-run members (wave_start.prune_ghosts; needs the oracle's battle.prune),
    then waits for the wave's members to be activated and moves the tap's battle start there (the episode's
    wake_frame and waves[0] then mark the wave's real start, as in a full gauntlet)."""
    def intro(ctx: Ctx) -> int:
        from ssbot.train.wave_start import prune_ghosts, wait_wave_active, wait_wave_start
        s = wait_wave_start(ctx.link, FORUM, wave)
        started_f = ctx.tap.wake_frame
        pr = prune_ghosts(ctx.link) if wave > 0 else {"pruned": []}
        a = wait_wave_active(ctx.link, FORUM, wave, after=s["f"])
        if started_f is None:
            raise RuntimeError("intro: room.battles started but the tap saw no start")
        ctx.tap.rebase_start(a["f"], "wave active")
        ctx.log.append({"wave_start": wave, "f": s["f"], "battle_start_f": started_f, "active_f": a["f"],
                        "activation_s": round((a["f"] - started_f) / 60.0, 3),
                        "ghosts": ("unpruned" if pr.get("pruned") is None else len(pr["pruned"])),
                        **({"prune_error": pr["error"]} if pr.get("error") else {})})
        return ctx.tap.wake_frame
    return intro


# Wave starts for targeted data collection (Forum plan R1): fo_A's route loadout at wave i of a battle reached by the
# skip policy (wave_start.make_wave_states). What such a start keeps and what it does not (no helper from wave 2 on,
# an earlier overlapping wave's survivors gone, the earlier waves' never-run members until battle.prune is deployed):
# docs/facts/1.0.30000/forum.md 13.1. Data only: gates stay on full gauntlets. Timebox 180 s (an episode is a slice
# of a gauntlet, not a whole one).
FORUM_WAVE_STARTS = tuple(replace(FORUM, name=f"Forum_A_w{i}", savestate=f"fo_r1_w{i}", intro=forum_wave_intro(i),
                                  timebox_s=180.0) for i in range(14))


# ---- route bosses (Task route bosses, 2026-10-06; docs/facts/1.0.30000/route_bosses.md) ----------------------------
# Training savestates rb_* (ssbot.probes.route_bosses save): a community "Boss - <name>" savestate (vichisuki
# BellRoute-LP, pinned 0557f703fa25; copies vs_p6_* / vs_p7_*) loaded, the encounter flag set where the first meeting
# has a dialogue (the refight path starts the same battle without it), saved by the game. The intro walks into the
# arena trigger until the boss's Control FSM leaves its dormant states; that frame is the wake.


def walk_intro(enc_name: str, button: int, timeout_s: float = 8.0) -> Callable[[Ctx], int]:
    """Walk with `button` held until the boss wakes (its Control FSM leaves the encounter's dormant states)."""
    def intro(ctx: Ctx) -> int:
        enc = ENCOUNTERS[enc_name]
        tap = ctx.tap
        s = _walk_until(ctx, button, lambda s: tap.control not in enc.dormant + (None,), timeout_s=timeout_s)
        ctx.log.append({"walked_to_x": round(s["hero"]["pos"][0], 2), "f": s["f"], "control": tap.control})
        if tap.wake_frame is None:
            # the boss left its dormant states before the tap's reset (the first Lace 1 smoke: the savestate stood
            # inside the trigger), so the fight has no wake frame and is useless for the tables
            raise RuntimeError(f"intro: the boss woke before the walk (control {tap.control})")
        return tap.wake_frame
    return intro


# Lace 1 (route S07): Bone_East_12, "Lace Boss1" (250 HP). Control: Dormant -> (ENTER at hero x ~90.5) Scene Start ->
# Location Check -> Encountered? (PlayerData encounteredLace1) -> Refight -> Start Battle -> Evade; the first meeting
# (MEET) runs Take Control and three dialogues first. No ZERO HP state in Control: the kill is the hit event.
# rb_lace1 = vs_p6_s3 (x 89.94, 5 / 5 masks, 9 silk) walked left to x 83.50 (at 89.94 the load itself started the
# fight before the tap's reset: no wake frame) + encounteredLace1 True. The walk wakes her at hero x ~88.2.
LACE_1 = Encounter(
    name="Lace1", scene="Bone_East_12", savestate="rb_lace1", boss_type="Lace Boss1", control_fsm="Control",
    dormant=("Pause", "Init", "Use Wall Range?", "Grotto Refight Setup", "Dormant"), death_states=(),
    # arena (341 fights of 20261006_070641 / 072930, route_bosses.md §6): the floor y 7.568 spans hero x 82.0-106.0;
    # lava pits on both sides (hero x 77.4-81.5 and 106.5-110.4, pit bottom y ~2.2-2.5; the "Lava Box" hazard
    # x 70.7-119.4 below y 2.41: all 1,553 lava contacts inside the static support); boss x 78.2-109.7
    intro=walk_intro("Lace1", R), timebox_s=300.0, arena_x=(82.0, 106.0), floor_y=7.5677, death_on_kill=True,
    notes="encounteredLace1 True (refight: no dialogue); the route meets her for the first time")

# Last Judge (route S17): Coral_Judge_Arena, "Last Judge" (720 HP). Control: Dormant -> (REFIGHT: the savestate has met
# the judge) Intro Fall Antic Q -> Intro Fall -> Intro Land -> Intro Roar Antic -> Intro Roar -> First Idle; global
# ZERO HP -> Death. rb_lastjudge = vs_p6_s8 (x 33.54, y 24.57).
LAST_JUDGE = Encounter(
    name="LastJudge", scene="Coral_Judge_Arena", savestate="rb_lastjudge", boss_type="Last Judge",
    control_fsm="Control", dormant=("Pause", "Init", "Dormant"), death_states=("Death",),
    # arena: the first smoke fight (hero x 7.56-52.41, boss 8.05-53.73, floor y 24.568 on 5,881 frames)
    intro=walk_intro("LastJudge", R), timebox_s=420.0, arena_x=(7.5, 53.7), floor_y=24.5677,
    notes="the savestate is a refight (Intro Fall Antic Q); the route's first fight takes Intro Fall Antic")

# Trobbio (route S22): Library_13, "Trobbio" (700 HP). Control: State (PlayerData test) -> Wait Refight -> (ENTER)
# Start Pause -> Quick Entrance 1-3 -> Appear 1 / Rise / Burst -> Fall 2 -> Land 2 -> Start Idle; the first meeting
# goes Wait -> Take Control -> Intro Jet -> Convo 1. Global ZERO HP -> Death Hit (then a long fake-death show).
# rb_trobbio = vs_p7_s1 (x 57.73, y 14.57).
TROBBIO = Encounter(
    name="Trobbio", scene="Library_13", savestate="rb_trobbio", boss_type="Trobbio", control_fsm="Control",
    dormant=("Init", "State", "Wait Refight", "Wait"), death_states=("Death Hit",),
    # arena: the first smoke fight (hero x 59.28-88.72, boss 59.61-88.41, floor y 14.568 on 6,079 frames)
    # timebox: CLEAR game time p50 287, p99 392, max 415 s over 324 fights of 20261006_072930 (the data policy's
    # damage rate); the two STUCK at 420 s were ordinary fights with 52 / 7 HP left (route_bosses.md §6)
    intro=walk_intro("Trobbio", R), timebox_s=540.0, arena_x=(59.3, 88.7), floor_y=14.5677,
    notes="the savestate is a refight (Wait Refight); the route's first fight has Convo 1")

ROUTE_BOSSES = (LACE_1, LAST_JUDGE, TROBBIO)

# Late-phase starts (data only, never a gate): the boss HP cut to 25-60 % right after the wake, so the phases its
# Control FSM enters by HP (CompareHP) get data at the rate of the early ones. Needs the oracle's enemy.hp (deploy).
ROUTE_BOSSES_LOW = tuple(replace(e, name=f"{e.name}_low", start_boss_hp=(0.25, 0.6)) for e in ROUTE_BOSSES)


ENCOUNTERS = {e.name: e for e in (BELL_BEAST, BELL_BEAST_REAPER, *ROUTE_BOSSES, *ROUTE_BOSSES_LOW, FORUM,
                                  *(forum_variant(a) for a in ("A", "B", "C", "A5")), *FORUM_WAVE_STARTS)}
