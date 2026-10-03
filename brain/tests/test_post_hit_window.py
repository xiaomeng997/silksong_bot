"""Q1's post-hit window (DESIGN §3.7.4 / §3.7.5, the person's rule of 2026-10-03): after a hit that leaves h <= 1 the
pause must land on the first pausable frame of the window that is both invulnerable and pausable. Stand-in game: the
hit's freeze shuts the gate (pause.blk 3) through the time scale's hold (ts 0) and its 0.1 s ramp (ts 0.17 ... 0.83),
opening on the ramp's end frame or the next (the four sequences of the 2143 measured hits, pause_quit constants); an
ACTION answers the STATE two frames earlier; a Pause press is an edge, and it pauses only on an open frame."""
import math

import pytest

from ssbot.core.worldstate import E, Ev, Event, HitTaken, WorldState
from ssbot.ipc.framing import BIT
from ssbot.safety import game_codes as gc
from ssbot.safety import pause_quit as pq
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
        if pressed and not sent.get(f - 1, 0) & PAUSE and seq[f][0] == 0:
            return f
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
def test_oracle_ramp_lands_the_pause_on_the_opening_frame(first_ramp, extra_shut):
    """Oracle view: Q1 on the hit frame; the time-scale ramp predicts the opening, so the first press lands on the
    opening frame or the next (before: on the observed gate alone, 2 frames after it, the training lead)."""
    seq = gate_sequence(first_ramp, extra_shut)
    opening = next(i for i, (b, _) in enumerate(seq) if b == 0)
    landed = run_loop(seq, 0, oracle_cues)
    assert landed is not None and 0 <= landed - opening <= 1
    assert run_loop(seq, 0, no_prediction) == opening + LEAD
    # the trigger seen late (a skipped tick) changes nothing as long as it comes before the ramp's end
    assert run_loop(seq, 6, oracle_cues) == landed


def test_hit_ramp_open_at_only_in_a_hit_freeze():
    t = 1.0
    s = state(10, 3, 0.83)
    assert hit_at(s, t) == pytest.approx(t + 0.017 + 1 / 60)
    assert hit_at(state(10, 3, 1.0), t) == pytest.approx(t + 1 / 60)          # ramp done, gate one frame behind
    assert hit_at(state(10, 3, 0.0), t) is None                                # the hold: its length unknown
    assert hit_at(state(10, 0, 1.0), t) is None                                # open
    assert hit_at(state(10, 3 | gc.BLK_GAME_STATE, 0.5), t) is None           # another blocker
    assert hit_at(state(10, 3, 0.5, inv=0.0), t) is None                       # no i-frames: not a hit's freeze
    # the vision cues never carry it (no time scale, no gate in the view)
    assert pq.vision_cues_from_state(state(10, 3, 0.83), QPC).gate_open_at is None


def hit_at(s: dict, t: float) -> float | None:
    return pq.hit_ramp_open_at(s, t)


@pytest.mark.parametrize("k", (2, 3, 4))
@pytest.mark.parametrize("opening", (13, 14, 15, 16))
def test_vision_prediction_never_presses_into_the_shut_gate(k, opening):
    """Vision view: Q1 seen k frames after the hit (the delayed view); the press waits for the hit's capture time plus
    POST_HIT_OPEN_MAX_S and lands 0-3 frames after the opening (13-16 frames measured), whatever k. The blind cadence
    from the trigger landed 0-5 after it."""
    seq = [(3, 0.0)] * opening + [(0, 1.0)] * 40
    t_hit = 0.0

    def vision(f, s):
        c = pq.vision_cues_from_state(state(max(0, f - k), *s[max(0, f - k)]), QPC)
        c.gate_open_at = t_hit + pq.POST_HIT_OPEN_MAX_S
        return c

    def blind(f, s):
        return pq.vision_cues_from_state(state(max(0, f - k), *s[max(0, f - k)]), QPC)
    landed = run_loop(seq, k, vision)
    assert landed is not None and 0 <= landed - opening <= 3 and landed <= 16
    b = run_loop(seq, k, blind)
    assert b is not None and 0 <= b - opening <= 5


def test_no_hit_presses_at_once():
    """Q1 without a hit (frost, pending damage): no prediction, the first press goes on the trigger's frame and lands
    on the first open frame (lead 2)."""
    seq = [(0, 1.0)] * 30
    assert run_loop(seq, 5, oracle_cues) == 5 + LEAD
    assert run_loop(seq, 5, lambda f, s: pq.vision_cues_from_state(state(f, *s[f]), QPC)) == 5 + LEAD


def _ws(hp: int, hit: bool, frame: int) -> WorldState:
    ws = WorldState()
    ws.hero.pos = E((85.0, 3.05))
    ws.res.hp, ws.res.hp_max, ws.res.silk, ws.res.blue, ws.res.pending_dmg = E(hp), E(5), E(3), E(0), E(0)
    ws.stamp.frame = frame
    if hit:
        ws.events = [Event(Ev.HIT_TAKEN, frame, frame / FPS, HitTaken(amount=2))]
    return ws


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
        ws = _ws(5 if fo < hit_f else 1, fo == hit_f, fo)
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
