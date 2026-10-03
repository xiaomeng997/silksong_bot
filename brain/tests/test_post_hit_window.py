"""Q1's post-hit window (DESIGN §3.7.4 / §3.7.5, the person's rule of 2026-10-03): after a hit that leaves h <= 1 the
pause must land on the first pausable frame of the window that is both invulnerable and pausable. Stand-in game: the
hit's freeze shuts the gate (pause.blk 3) through the time scale's hold (ts 0) and its 0.1 s ramp (ts 0.17 ... 0.83,
sometimes a last 1.0 frame still shut), the four shapes of the 2143 measured hits; G is the first frame whose STATE
shows the gate open, and a press pauses from G + 1 on (the time scale comes back after InputHandler's Update: live
check 20261003_111244, a press latched on G did not pause); an ACTION answers the STATE two frames earlier; a Pause
press is an edge."""
import math

import pytest

from ssbot.core.worldstate import E, Ev, Event, HitTaken, WorldState
from ssbot.ipc.framing import BIT
from ssbot.safety import game_codes as gc
from ssbot.safety import pause_quit as pq
from ssbot.safety import supervisor as sv
from ssbot.safety.hits_to_death import SupportEvent, SupportSet
from ssbot.safety.supervisor import Q1_HIT, SupervisorConfig
from ssbot.train.supervision import SupervisedControl

QPC = 1e7
FPS = 60.0
PAUSE = 1 << BIT["pause"]
LEAD = 2                                   # training: the ACTION for frame f + 2 goes out at STATE f
RAMP = (0.17, 0.33, 0.5, 0.67, 0.83)
# (first ramp frame after the hit, the ramp's end frame shows ts 1 with the gate still shut): the four measured shapes
SEQUENCES = ((8, True), (9, True), (9, False), (8, False))


def gate_sequence(first_ramp: int, extra_shut: bool, n: int = 40) -> list[tuple[int, float]]:
    """(pause.blk, ts) for frames hit + 0 .. n - 1: the opening is at first_ramp + 5 (+1 when extra_shut)."""
    out = [(gc.BLK_DISABLE_PAUSE | gc.BLK_TIME_SLOWED, 0.0)] * first_ramp
    out += [(3, ts) for ts in RAMP]
    if extra_shut:
        out.append((3, 1.0))
    out += [(0, 1.0)] * (n - len(out))
    return out[:n]


def state(f: int, blk: int, ts: float, inv: float = 1.0, paused: bool = False) -> dict:
    return {"f": f, "q": int(round(f / FPS * QPC)), "ev": [], "ts": 0.0 if paused else ts,
            "game": {"gs": gc.GS_PAUSED if paused else gc.GS_PLAYING, "ui": gc.UI_PAUSED if paused else 1,
                     "menu": 0, "paused": paused, "scene": "Bone_05", "fading": False},
            "pause": {"blk": 100 if paused else blk}, "hero": {"health": 1, "max_health": 5, "tm": {"inv": inv}}}


def run_loop(seq, start: int, cues_of, lead: int = LEAD) -> int | None:
    """Drive a PauseQuit started at frame `start` (the trigger) through the stand-in game; the frame the pause lands."""
    m = pq.PauseQuit(pq.PauseQuitConfig(emulate_quit=True))
    sent: dict[int, int] = {}
    for f in range(len(seq)):
        pressed = bool(sent.get(f, 0) & PAUSE)
        if pressed and not sent.get(f - 1, 0) & PAUSE and f > 0 and seq[f - 1][0] == 0:
            return f                     # pausable: the gate was open in the previous frame's STATE (G + 1 on)
        if f < start:
            continue
        if f == start:
            m.start(f / FPS)
        c = cues_of(f, seq)
        keys = m.step(c, f / FPS)
        sent[f + lead] = pq.to_mask(keys, BIT)
    return None


def oracle_cues(f: int, seq) -> pq.PauseCues:
    return pq.cues_from_state(state(f, *seq[f]), QPC)


def no_prediction(f: int, seq) -> pq.PauseCues:
    c = oracle_cues(f, seq)
    c.gate_open_at = None
    return c


@pytest.mark.parametrize("first_ramp,extra_shut", SEQUENCES)
def test_oracle_lands_the_pause_on_the_first_pausable_frame(first_ramp, extra_shut):
    """Oracle view: Q1 on the hit frame. With a last shut 1.0 frame the press goes there and pauses on G + 1, the
    first pausable frame; without one the observed gate puts it on G + 2, as before. Never earlier: a press on G is
    dropped and the next edge comes 6 frames later (the first version timed the press for G: +20 / +21 live)."""
    seq = gate_sequence(first_ramp, extra_shut)
    g = next(i for i, (b, _) in enumerate(seq) if b == 0)
    landed = run_loop(seq, 0, oracle_cues)
    assert landed == (g + 1 if extra_shut else g + 2)
    assert run_loop(seq, 0, no_prediction) == g + LEAD
    # the trigger seen late (a skipped tick) changes nothing as long as it comes before the ramp's end
    assert run_loop(seq, 6, oracle_cues) == landed


def test_hit_ramp_open_at_only_on_the_ramps_last_shut_frame():
    t = 1.0
    assert hit_at(state(10, 3, 1.0), t) == pytest.approx(t + 2 / 60)          # G next frame, pausable after it
    assert hit_at(state(10, 3, 0.83), t) is None                               # 0.83 -> 1.0 or 0.83 -> open: unknown
    assert hit_at(state(10, 3, 0.0), t) is None                                # the hold: its length unknown
    assert hit_at(state(10, 0, 1.0), t) is None                                # open
    assert hit_at(state(10, 3 | gc.BLK_GAME_STATE, 1.0), t) is None           # another blocker
    assert hit_at(state(10, 3, 1.0, inv=0.0), t) is None                       # no i-frames: not a hit's freeze
    # the vision cues never carry it (no time scale, no gate in the view)
    assert pq.vision_cues_from_state(state(10, 3, 1.0), QPC).gate_open_at is None


def hit_at(s: dict, t: float) -> float | None:
    return pq.hit_ramp_open_at(s, t)


@pytest.mark.parametrize("k", (2, 3, 4))
@pytest.mark.parametrize("opening", (13, 14, 15, 16))
def test_vision_prediction_never_presses_into_the_shut_gate(k, opening):
    """Vision view: Q1 seen k frames after the hit (the delayed view); the press waits for the hit's capture time plus
    POST_HIT_OPEN_MAX_S and lands 0-3 frames after the first pausable frame (G 13-16 frames measured, pausable from
    G + 1), whatever k. The blind cadence from the trigger landed 0-5 after it."""
    seq = [(3, 0.0)] * opening + [(0, 1.0)] * 40
    t_hit = 0.0

    def vision(f, s):
        c = pq.vision_cues_from_state(state(max(0, f - k), *s[max(0, f - k)]), QPC)
        c.gate_open_at = t_hit + pq.POST_HIT_OPEN_MAX_S
        return c

    def blind(f, s):
        return pq.vision_cues_from_state(state(max(0, f - k), *s[max(0, f - k)]), QPC)
    landed = run_loop(seq, k, vision)
    assert landed is not None and 0 <= landed - (opening + 1) <= 3 and landed <= 17
    b = run_loop(seq, k, blind)
    assert b is not None and 0 <= b - (opening + 1) <= 5


def test_no_hit_presses_at_once():
    """Q1 without a hit (frost, pending damage): no prediction, the first press goes on the trigger's frame and lands
    on the first pausable frame (lead 2)."""
    seq = [(0, 1.0)] * 30
    assert run_loop(seq, 5, oracle_cues) == 5 + LEAD
    assert run_loop(seq, 5, lambda f, s: pq.vision_cues_from_state(state(f, *s[f]), QPC)) == 5 + LEAD


def _ws(hp: int, hit: bool, frame: int, hurt: bool = False) -> WorldState:
    """The delayed view's WorldState; hurt: the hero in a hit's knockback (HeroState.mode "hurt": from the hit's own
    frame through the freeze and the recoil)."""
    ws = WorldState()
    ws.hero.pos = E((85.0, 3.05))
    ws.hero.mode = E("hurt" if hurt else "ground")
    ws.res.hp, ws.res.hp_max, ws.res.silk, ws.res.blue, ws.res.pending_dmg = E(hp), E(5), E(3), E(0), E(0)
    ws.stamp.frame = frame
    if hit:
        ws.events = [Event(Ev.HIT_TAKEN, frame, frame / FPS, HitTaken(amount=2))]
    return ws


RECOIL_F = 25                              # the hurt mode's frames after a hit (freeze ~15, then the recoil)


@pytest.mark.parametrize("k", (2, 4))
def test_supervised_control_vision_times_the_q1_press_from_the_hit(k):
    """SupervisedControl(vision=True): the delayed view shows a hit to 1 HP k frames late; Q1 (cause "hit") starts
    the loop at once, but no press reaches the game before the hit's capture time + POST_HIT_OPEN_MAX_S; afterwards
    the loop presses. The key guard (current STATE act.hf) is clear in this stand-in."""
    sc = SupervisedControl(SupervisorConfig(worst_known_damage=2), support=lambda s: SupportSet(
        (SupportEvent("Bone Beast", 2),), True), vision=True)
    hit_f = 100
    first_pending, first_press = None, None
    for f in range(hit_f - 10, hit_f + 40):
        fo = f - k
        obs = state(fo, 0 if fo < hit_f else 3, 1.0 if fo < hit_f else 0.0)
        cur = state(f, 0, 1.0)
        ws = _ws(5 if fo < hit_f else 1, fo == hit_f, fo, hurt=hit_f <= fo < hit_f + RECOIL_F)
        r = sc.step(cur, obs=obs, ws=ws)
        if r.decision.pause_pending and first_pending is None:
            first_pending = f
            assert r.decision.q1_cause == Q1_HIT
        if r.mask and r.mask & PAUSE and first_press is None:
            first_press = f
    assert first_pending == hit_f + k
    assert sc.t_hit_seen == pytest.approx(hit_f / FPS, abs=1e-6)
    land = first_press + LEAD
    assert (land - hit_f) / FPS >= pq.POST_HIT_OPEN_MAX_S - 0.5 / FPS        # never into the shut gate
    assert land - hit_f <= math.ceil(pq.POST_HIT_OPEN_MAX_S * FPS)            # and on the first sure frame


def test_vision_hit_through_a_bind_waits_for_the_bindbreak_freeze():
    """Q1a's own risk: a hit through a Bind (to 1 HP) adds the BindBreak freeze; the gate opened 0.53-0.55 s after
    such hits (5 measured), so the vision view's first press waits for POST_HIT_OPEN_MAX_BIND_S instead."""
    sc = SupervisedControl(SupervisorConfig(worst_known_damage=2), support=lambda s: SupportSet(
        (SupportEvent("Bone Beast", 2),), True), vision=True)
    hit_f, k, first_press = 100, 3, None
    for f in range(hit_f - 10, hit_f + 50):
        fo = f - k
        ws = _ws(3 if fo < hit_f else 1, fo == hit_f, fo, hurt=hit_f <= fo < hit_f + RECOIL_F)
        ws.hero.binding = E("IN_PROGRESS" if fo < hit_f else "INTERRUPTED")
        r = sc.step(state(f, 0, 1.0), obs=state(fo, 0, 1.0), ws=ws)
        if r.mask and r.mask & PAUSE and first_press is None:
            first_press = f
    assert sc.hit_open_s == pq.POST_HIT_OPEN_MAX_BIND_S
    assert (first_press + LEAD - hit_f) / FPS >= pq.POST_HIT_OPEN_MAX_BIND_S - 0.5 / FPS


@pytest.mark.parametrize("event", (False, True))
@pytest.mark.parametrize("k", (2, 4))
def test_vision_hud_drop_without_knockback_presses_at_once(k, event):
    """Frost / DamageTag damage (DoSpecialDamage's take-health path: no recoil, no freeze, no shut gate, no i-frames)
    taking the HUD to 1 HP: Q1 is "no hit" and the first press goes on Q1's own tick, not 0.285 s later with the hero
    vulnerable (fixer review 2026-10-03). With or without a HIT_TAKEN for it (the oracle backend emits one for
    special_damage), and a skipped frame (the drop seen 2 frames late) changes nothing."""
    sc = SupervisedControl(SupervisorConfig(worst_known_damage=2), support=lambda s: SupportSet(
        (SupportEvent("Bone Beast", 2),), True), vision=True)
    drop_f, first_pending, first_press = 100, None, None
    for f in range(drop_f - 10, drop_f + 30):
        fo = f - k
        if fo == drop_f + 1:
            continue                                         # the live loop skipped a tick
        ws = _ws(3 if fo < drop_f else 1, event and fo == drop_f, fo, hurt=False)
        r = sc.step(state(f, 0, 1.0), obs=state(fo, 0, 1.0), ws=ws)
        if r.decision.pause_pending and first_pending is None:
            first_pending = f
            assert r.decision.q1_cause == sv.Q1_NO_HIT
        if r.mask and r.mask & PAUSE and first_press is None:
            first_press = f
    assert sc.t_hit_seen is None and first_pending == drop_f + k and first_press == first_pending


def test_vision_hit_seen_late_still_shows_the_knockback():
    """A hit on a frame the live loop skipped reaches the view as the lower HUD with the hero still in the knockback
    (the hurt mode lasts through the freeze and the recoil): timed as a hit from that capture."""
    sc = SupervisedControl(SupervisorConfig(worst_known_damage=2), support=lambda s: SupportSet(
        (SupportEvent("Bone Beast", 2),), True), vision=True)
    hit_f, k = 100, 3
    for f in range(hit_f - 10, hit_f + 10):
        fo = f - k
        if fo == hit_f:
            continue                                         # skipped: its HIT_TAKEN is never seen
        r = sc.step(state(f, 0, 1.0), obs=state(fo, 0, 1.0),
                    ws=_ws(5 if fo < hit_f else 1, False, fo, hurt=hit_f <= fo < hit_f + RECOIL_F))
        if r.decision.pause_pending:
            assert r.decision.q1_cause == Q1_HIT
    assert sc.t_hit_seen == pytest.approx((hit_f + 1) / FPS, abs=1e-6)
